"""Rollback-only native transactions for the HTML palette's joined edge finish.

CommandCreated never computes or executes the command. A queued custom event
drives executePreview after creation returns; a no-op execute rolls that preview
back. Only detached temporary BRep results leave the command through destroy.
"""

from dataclasses import dataclass
import traceback

import adsk.core


PREVIEW_COMMAND_ID = "sktech_partelier_hinge_compute_16e681a4"
PREVIEW_EVENT_ID = "sktech_partelier_hinge_compute_event_16e681a4"


@dataclass
class _Request:
    serial: int
    tag: object
    compute: object
    completed: object
    failed: object
    prepared: object = None
    error: object = None
    cancelled: bool = False
    executed: bool = False
    computed: bool = False


class NativePreviewRunner:
    """Serialize short compute commands and discard superseded requests."""

    def __init__(self, report_error=None):
        self._report_error = report_error
        self._command_id = PREVIEW_COMMAND_ID
        self._requested_event_id = PREVIEW_EVENT_ID
        self._event_id = self._requested_event_id
        self._definition = None
        self._created_handler = None
        self._custom_event = None
        self._custom_handler = None
        self._command = None
        self._handlers = []
        self._current = None
        self._pending = None
        self._serial = 0
        self._stopped = False

    @property
    def busy(self):
        return self._current is not None or self._pending is not None

    def _log(self, summary):
        try:
            if self._report_error is not None:
                self._report_error(summary)
            else:
                adsk.core.Application.get().log(summary + "\n" + traceback.format_exc())
        except Exception:
            pass

    def _start(self):
        if self._definition is not None:
            return
        app = adsk.core.Application.get()
        try:
            self._custom_event = app.registerCustomEvent(self._requested_event_id)
            if self._custom_event is None:
                raise RuntimeError("Fusion could not register the hinge preview driver.")
            registered = self._custom_event.eventId
            if type(registered) is not str or not registered:
                raise RuntimeError("Fusion returned an invalid hinge preview event identity.")
            self._event_id = registered
            self._custom_handler = _Driver(self)
            if self._custom_event.add(self._custom_handler) is False:
                raise RuntimeError("Fusion could not attach the hinge preview event driver "
                                   + self._event_diagnostic())
            definitions = app.userInterface.commandDefinitions
            self._definition = definitions.itemById(self._command_id)
            if self._definition is None:
                self._definition = definitions.addButtonDefinition(
                    self._command_id, "Partelier: Compute hinge preview",
                    "Compute temporary joined hinge edge finishes, then roll back.")
            self._created_handler = _Created(self)
            if self._definition.commandCreated.add(self._created_handler) is False:
                raise RuntimeError("Fusion could not attach the hinge preview command-created handler.")
        except Exception:
            self.stop()
            raise

    def request(self, tag, compute, completed, failed):
        if self._stopped:
            raise RuntimeError("The hinge preview driver has stopped. Run Partelier again.")
        if getattr(tag,'closed',False) is True or getattr(tag,'cancel_requested',False) is True:
            return
        self._start()
        self._retire_invalid_command()
        self._serial += 1
        request = _Request(self._serial, tag, compute, completed, failed)
        if self._current is not None:
            self._current.cancelled = True
            self._pending = request
        else:
            # A new request can arrive after Destroy but before its queued
            # "next" event. The newest request supersedes that pending work.
            if self._pending is not None:
                self._pending.cancelled = True
                self._pending = None
            self._launch(request)

    def cancel(self, tag=None):
        if self._current is not None and (tag is None or self._current.tag is tag):
            self._current.cancelled = True
        if self._pending is not None and (tag is None or self._pending.tag is tag):
            self._pending = None

    def _launch(self, request):
        self._current = request
        try:
            if self._definition.execute() is False:
                raise RuntimeError("Fusion could not start the temporary hinge preview.")
        except Exception as error:
            self._current = None
            self._deliver(request, error=error)
            raise

    def _event_diagnostic(self):
        return ("(requested event=" + repr(self._requested_event_id)
                + ", registered event=" + repr(self._event_id) + ").")

    def _queue(self, information):
        try:
            # Fusion 2705 can return False on the main thread even though the
            # queued handler subsequently runs. Actual delivery is authoritative;
            # only a raised API error establishes a queue-call failure here.
            adsk.core.Application.get().fireCustomEvent(self._event_id, information)
        except Exception as error:
            raise RuntimeError("Fusion could not queue the hinge preview driver "
                               + self._event_diagnostic()) from error

    def _bind(self, event, handler):
        if event.add(handler) is False:
            raise RuntimeError("Fusion could not attach the hinge preview "
                               + handler.__class__.__name__.lstrip("_").lower() + " handler.")
        self._handlers.append((event, handler))

    def _detach_handlers(self):
        for event, handler in self._handlers:
            try:
                event.remove(handler)
            except Exception:
                self._log("Partelier could not detach a temporary preview handler.")
        self._handlers.clear()

    def _retire_invalid_command(self):
        request, command = self._current, self._command
        if request is None or command is None:
            return
        try:
            if (command.isValid is not False
                    or adsk.core.Application.get().userInterface.activeCommand == self._command_id):
                return
        except Exception:
            # Inconclusive ownership must never preempt another native command.
            return
        self._detach_handlers()
        self._command = None
        self._current = None
        if not request.cancelled:
            request.cancelled = True
            self._deliver(request, error=request.error or RuntimeError(
                "The temporary hinge preview ended without its completion event. Refresh preview."))

    def created(self, command):
        request = self._current
        if self._stopped or request is None:
            # An already-cancelled empty command must close after Created;
            # neither preview computation nor execution is driven from here.
            command.isAutoExecute = True
            command.isOKButtonVisible = False
            return
        self._command = command
        destroy_bound = False
        try:
            # Bind the cleanup event first. Refused preview/execute bindings
            # can then close automatically and report through Destroy.
            self._bind(command.destroy, _Destroyed(self, request))
            destroy_bound = True
            command.isAutoExecute = False
            command.isExecutedWhenPreEmpted = False
            command.isRepeatable = False
            command.isOKButtonVisible = False
            self._bind(command.executePreview, _Preview(self, request))
            self._bind(command.execute, _Execute(self, request))
            # Never call doExecutePreview/doExecute while CommandCreated runs.
            self._queue(str(request.serial))
        except Exception as error:
            request.error = error
            # No calculation has run. Auto-execute the empty command only
            # AFTER CommandCreated returns, letting Fusion close its transaction.
            command.isAutoExecute = True
            if not destroy_bound:
                request.cancelled = True
                self._detach_handlers()
                if self._current is request:
                    self._current = None
                    self._command = None
                self._deliver(request, error=error)
            self._log("Partelier could not initialize a temporary hinge preview.")

    def drive(self, information):
        if self._stopped:
            return
        if information == "next":
            if self._current is None and self._pending is not None:
                pending, self._pending = self._pending, None
                self._launch(pending)
            return
        request, command = self._current, self._command
        if request is None or command is None or information != str(request.serial):
            return
        try:
            if not request.cancelled and not request.computed:
                if command.doExecutePreview() is False:
                    raise RuntimeError("Fusion refused the temporary hinge preview calculation.")
            # isValidResult=False makes Fusion roll back preview changes before
            # this deliberately empty execute. No model result is committed.
            if command.doExecute(True) is False:
                raise RuntimeError("Fusion could not close the temporary hinge preview.")
        except Exception as error:
            request.error = request.error or error
            try:
                ui = adsk.core.Application.get().userInterface
                if ui.activeCommand == self._command_id:
                    ui.terminateActiveCommand()
            except Exception:
                self._log("Partelier could not close a failed temporary preview command.")
            if self._current is request:
                # If Fusion could not terminate it, retain ownership until
                # Destroy/Stop but do not leave the palette stuck computing.
                self._deliver(request, error=request.error)
                request.cancelled = True
            self._log("Partelier temporary hinge preview driver failed.")

    def calculate(self, request, args):
        args.isValidResult = False
        if self._stopped or request.cancelled or request is not self._current or request.computed:
            return
        request.computed = True
        try:
            request.prepared = request.compute()
            if request.prepared is None:
                raise RuntimeError("Fusion returned no detached hinge preview.")
        except Exception as error:
            request.error = error

    def destroyed(self, request):
        if self._current is not request:
            # A proven-invalid old command may deliver a delayed Destroy after
            # a replacement has bound its own handlers. Never detach those.
            return
        self._detach_handlers()
        self._command = None
        self._current = None
        if not request.cancelled and not self._stopped:
            error = request.error
            if not request.executed and error is None:
                error = ValueError("The temporary hinge preview was interrupted. Refresh preview.")
            if error is None and request.prepared is None:
                error = ValueError("The temporary hinge preview did not finish. Refresh preview.")
            self._deliver(request, error=error)
        if not self._stopped and self._pending is not None:
            try:
                self._queue("next")
            except Exception as error:
                pending, self._pending = self._pending, None
                self._deliver(pending, error=error)

    def _deliver(self, request, *, error=None):
        if request is None or self._stopped:
            return
        try:
            if error is None:
                request.completed(request.prepared)
            else:
                request.failed(error)
        except Exception:
            self._log("Partelier could not publish the completed temporary preview.")

    def stop(self):
        if self._stopped:
            return
        self._stopped = True
        self.cancel()
        try:
            ui = adsk.core.Application.get().userInterface
            if ui.activeCommand == self._command_id:
                ui.terminateActiveCommand()
        except Exception:
            self._log("Partelier could not stop its temporary preview command.")
        for event, handler in self._handlers:
            try:
                event.remove(handler)
            except Exception:
                self._log("Partelier could not detach its temporary preview handler.")
        self._handlers.clear()
        self._command = None
        self._current = None
        if self._definition is not None:
            if self._created_handler is not None:
                try:
                    self._definition.commandCreated.remove(self._created_handler)
                except Exception:
                    self._log("Partelier could not detach its preview command-created handler.")
            try:
                if self._definition.isValid:
                    self._definition.deleteMe()
            except Exception:
                self._log("Partelier could not remove its temporary preview definition.")
        if self._custom_event is not None:
            try:
                self._custom_event.remove(self._custom_handler)
            except Exception:
                self._log("Partelier could not detach its preview event driver.")
            try:
                adsk.core.Application.get().unregisterCustomEvent(self._event_id)
            except Exception:
                self._log("Partelier could not unregister its preview event driver.")
        self._definition = None
        self._custom_event = None
        self._created_handler = None
        self._custom_handler = None


class _Created(adsk.core.CommandCreatedEventHandler):
    def __init__(self, owner):
        super().__init__()
        self.owner = owner

    def notify(self, args):
        self.owner.created(args.command)


class _Driver(adsk.core.CustomEventHandler):
    def __init__(self, owner):
        super().__init__()
        self.owner = owner

    def notify(self, args):
        self.owner.drive(args.additionalInfo)


class _Preview(adsk.core.CommandEventHandler):
    def __init__(self, owner, request):
        super().__init__()
        self.owner = owner
        self.request = request

    def notify(self, args):
        self.owner.calculate(self.request, args)


class _Execute(adsk.core.CommandEventHandler):
    def __init__(self, owner, request):
        super().__init__()
        self.owner = owner
        self.request = request

    def notify(self, args):
        self.request.executed = True


class _Destroyed(adsk.core.CommandEventHandler):
    def __init__(self, owner, request):
        super().__init__()
        self.owner = owner
        self.request = request

    def notify(self, args):
        self.owner.destroyed(self.request)

"""HTML-only snap-fit sessions and zero-input undoable Fusion commits.

Picking and temporary geometry run on Fusion's main thread. Camera commands do
not dispose the preview. Only a separate native command persists Create/Rebuild.
"""

import time
import traceback
import uuid

import adsk.core
import adsk.fusion

from .settings import SnapFitSettings
from .fusion import (prepare_snap_fit, prepare_edit_snap_fit, read_edit_target,
                     create_snap_fit, rebuild_snap_fit, preview_snap_fit,
                     preview_hide_bodies, capture_preview_sources,
                     validate_preview_sources)
from ..hinge.visibility import BodyVisibilityLease


COMMIT_COMMAND_ID = "sktech_partelier_snap_commit_b744ef2b"
SELECTIONS = ("face_a", "face_b", "axis_edge")


def _active_design():
    design = adsk.fusion.Design.cast(adsk.core.Application.get().activeProduct)
    if design is None:
        raise ValueError("Open a Fusion Design document before using snap-fits.")
    return design


def _launch_settings(values):
    if not isinstance(values, dict):
        raise ValueError("Snap-fit dimensions must be an object.")
    defaults = SnapFitSettings().to_dict()
    if set(values) - set(defaults):
        raise ValueError("Snap-fit dimensions contain unsupported fields.")
    return SnapFitSettings.from_dict({**defaults, **values})


class SnapCommands:
    """One independent logical palette session and its owned host handlers."""

    def __init__(self, report_error=None):
        self._report_error = report_error
        self._registration = None
        self._context_handlers = []
        self._session = None
        self._pending = None
        self._busy = False
        self._state_callback = None
        self._last_state = self._idle_state()

    @staticmethod
    def _idle_state():
        return {"sessionId": None, "revision": 0, "phase": "idle", "editing": False,
                "settings": None, "selections": {}, "previewCurrent": False,
                "message": "Select the base wall, lid wall and their seam edge."}

    def set_state_callback(self, callback):
        self._state_callback = callback

    def _publish(self, session=None):
        if session is not None:
            self._last_state = session.snapshot()
        if self._state_callback is not None:
            try:
                self._state_callback(self._last_state)
            except Exception:
                self._log("Partelier could not update the snap-fit palette")
        return self._last_state

    def palette_state(self):
        if self._session is not None:
            self._last_state = self._session.snapshot()
        return self._last_state

    def _log(self, summary):
        try:
            adsk.core.Application.get().log(f"{summary}\n{traceback.format_exc()}")
        except Exception:
            pass

    def start(self):
        if self._registration is not None:
            return
        app = adsk.core.Application.get()
        ui = app.userInterface
        try:
            definition = ui.commandDefinitions.itemById(COMMIT_COMMAND_ID)
            if definition is None:
                definition = ui.commandDefinitions.addButtonDefinition(
                    COMMIT_COMMAND_ID, "Partelier: Create / Rebuild snap-fit",
                    "Join a cantilever clasp and cut its matching recess in the selected bodies.")
            handler = _Created(self)
            self._registration = (definition, handler)
            definition.commandCreated.add(handler)
            for event, context in ((app.documentDeactivating, _DocumentChanging(self)),
                                   (ui.commandTerminated, _CommandEnded(self))):
                event.add(context)
                self._context_handlers.append((event, context))
        except Exception:
            self.stop()
            raise

    def stop(self):
        ui = adsk.core.Application.get().userInterface
        errors = []
        def attempt(operation):
            try:
                operation()
            except Exception as error:
                errors.append(error)
                self._log("Partelier snap-fit cleanup failed")
        if ui.activeCommand == COMMIT_COMMAND_ID:
            attempt(ui.terminateActiveCommand)
        if self._session is not None:
            attempt(self._session.close)
        for event, handler in self._context_handlers:
            attempt(lambda event=event, handler=handler: event.remove(handler))
        self._context_handlers.clear()
        if self._registration is not None:
            definition, handler = self._registration
            attempt(lambda: definition.commandCreated.remove(handler))
            if definition.isValid:
                attempt(definition.deleteMe)
            self._registration = None
        self._pending = None
        self._busy = False
        if not errors:
            self._last_state = self._idle_state()
        self._publish()
        if errors:
            raise RuntimeError("Snap-fit cleanup needs another Stop attempt. " + str(errors[0]))

    def begin_palette(self, settings_dict, editing=False):
        if type(editing) is not bool:
            raise ValueError("Edit mode must be true or false.")
        settings = _launch_settings(settings_dict)
        if self._busy or self._session is not None or self._pending is not None:
            raise ValueError("Finish or cancel the current snap-fit first.")
        if self._registration is None:
            raise ValueError("The snap-fit tool has stopped. Run Partelier again.")
        session = _Session(self, _active_design(), settings, editing)
        self._session = session
        self._busy = True
        try:
            self._publish(session)
            selections = adsk.core.Application.get().userInterface.activeSelections
            if editing and selections.count == 1:
                entity = selections.item(0).entity
                if entity is not None and entity.isValid:
                    session.set_selection("edit_target", entity)
                    return self._publish(session)
            for target in (("edit_target",) if editing else SELECTIONS):
                if not self._pick(session, target):
                    break
            return self._publish(session)
        except Exception:
            session.close()
            raise
        finally:
            self._busy = False

    def _pick(self, session, target):
        if target not in (("edit_target",) if session.editing else SELECTIONS):
            raise ValueError("Choose a supported snap-fit selection.")
        session.ensure_design()
        session.clear_preview()
        prompts = {
            "face_a": ("Select the exterior base wall for the hook. Esc to stop picking.", "PlanarFaces"),
            "face_b": ("Select the coplanar lid wall for the recess. Esc to stop picking.", "PlanarFaces"),
            "axis_edge": ("Select the facing rim on the base or lid wall. A gap is supported. Esc to stop picking.", "Edges"),
            "edit_target": ("Select a snap-fit body or a Part containing one snap-fit. Esc to stop picking.", "Occurrences,SolidBodies"),
        }
        if session.settings.snap_family == "annular":
            prompts.update({
                "face_a": ("Select the outer cylinder on body A. Esc to stop picking.", "CylindricalFaces"),
                "face_b": ("Select the matching inner cylinder on body B. Esc to stop picking.", "CylindricalFaces"),
                "axis_edge": ("Select the complete circular rim on the outer cylinder A. Esc to stop picking.", "Edges"),
            })
        prompt, filters = prompts[target]
        session.phase = "selecting"
        session.message = prompt
        self._publish(session)
        try:
            selection = adsk.core.Application.get().userInterface.selectEntity(prompt, filters)
        except RuntimeError:
            selection = None  # Fusion raises when the user presses Esc.
        session.ensure_design()
        if selection is None or selection.entity is None:
            session.validate()
            return False
        session.set_selection(target, selection.entity)
        return True

    def palette_action(self, action, session_id, revision=None, settings_dict=None, target=None):
        session = self._session
        if self._busy or self._pending is not None or (session is not None and session.command is not None):
            raise ValueError("Finish picking or wait for snap-fit creation to finish.")
        if session is None or session.closed or session.session_id != session_id:
            raise ValueError("This snap-fit session has ended. Select geometry to start again.")
        session.ensure_design()
        self._busy = True
        try:
            if action in {"snap_update", "snap_preview", "snap_commit"}:
                session.update(settings_dict, revision)
                if action == "snap_update":
                    session.validate()
                    if session.phase == "ready":
                        session.message = "Settings updated. Refresh the preview."
                elif action == "snap_preview":
                    session.show_preview()
                else:
                    session.require_selections()
                    if not session.preview_current or session.phase != "preview":
                        raise ValueError("Refresh the current snap-fit preview before creating it.")
                    validate_preview_sources(session.design, session.preview_sources)
                    session.phase = "opening"
                    session.message = "Rebuilding snap-fit…" if session.editing else "Creating snap-fit…"
                    self._publish(session)
                    self._pending = session
                    definition = self._registration[0]
                    try:
                        if not definition.execute():
                            raise RuntimeError("Fusion could not start the snap-fit transaction.")
                    except Exception:
                        self._pending = None
                        raise
            elif action == "snap_focus":
                self._pick(session, target)
            elif action == "snap_cancel":
                session.close()
            else:
                raise ValueError("This snap-fit action is unavailable.")
            return self._publish(session)
        except Exception as error:
            if not session.closed:
                session.phase = "error"
                session.message = str(error)
                self._publish(session)
            raise
        finally:
            self._busy = False


class _Session:
    def __init__(self, owner, design, settings, editing):
        self.owner, self.design, self.settings, self.editing = owner, design, settings, editing
        self.session_id = str(uuid.uuid4())
        self.revision = 0
        self.phase = "selecting"
        self.message = "Select snap-fit geometry."
        self.selections = {}
        self.edit_target = None
        self.edit_error = None
        self.preview = None
        self.preview_sources = None
        self.preview_revision = None
        self.retained_groups = []
        self.visibility = BodyVisibilityLease()
        self.closed = False
        self.command = None
        self.handlers = []

    @property
    def preview_current(self):
        return bool(self.preview is not None and self.preview.isValid
                    and self.preview_revision == self.revision and self.preview_sources is not None)

    def snapshot(self):
        selections = {}
        for key in (("edit_target",) if self.editing else SELECTIONS):
            entity = self.selections.get(key)
            valid = entity is not None and entity.isValid
            label = (getattr(entity, "name", "") or getattr(getattr(entity, "body", None), "name", "") or "Selected") if valid else "Not selected"
            selections[key] = {"selected": bool(valid), "label": str(label)[:120]}
        return {"sessionId": self.session_id, "revision": self.revision, "phase": self.phase,
                "editing": self.editing, "settings": self.settings.to_dict(),
                "selections": selections, "message": self.message,
                "previewCurrent": self.preview_current}

    def ensure_design(self):
        if self.closed or _active_design() != self.design:
            raise ValueError("The active design changed. Start a new snap-fit session.")

    def set_selection(self, key, entity):
        self.clear_preview()
        self.selections[key] = entity
        if key in {"face_a", "face_b"}:
            self.selections.pop("axis_edge", None)
        if self.editing:
            self.edit_target = None
            self.edit_error = None
            try:
                target = read_edit_target(self.design, entity)
                self.edit_target = target
                self.settings = target.settings
            except ValueError as error:
                self.edit_error = str(error)
        self.validate()

    def require_selections(self):
        self.ensure_design()
        self.settings.validate()
        for key in (("edit_target",) if self.editing else SELECTIONS):
            entity = self.selections.get(key)
            if entity is None or not entity.isValid:
                raise ValueError("Select " + {"face_a": "the base wall A", "face_b": "the lid wall B", "axis_edge": "the straight seam edge", "edit_target": "a Partelier snap-fit result"}[key] + ".")
        if self.editing and self.edit_target is None:
            raise ValueError(self.edit_error or "Select a supported Partelier snap-fit to load its dimensions.")

    def validate(self):
        try:
            self.require_selections()
            self.phase = "ready"
            self.message = "Geometry selected. Live preview will update automatically."
        except ValueError as error:
            self.phase = "error" if self.edit_error else "selecting"
            self.message = str(error)
        self.owner._publish(self)

    def update(self, values, revision):
        if type(revision) is not int or not 0 <= revision <= 1_000_000_000:
            raise ValueError("Use a valid snap-fit revision.")
        settings = SnapFitSettings.from_dict(values)
        if revision < self.revision or (revision == self.revision and settings != self.settings):
            raise ValueError("These snap-fit settings are stale. Use the current palette values.")
        if settings != self.settings:
            crossed = (settings.snap_family == "annular") != (self.settings.snap_family == "annular")
            if crossed and self.editing:
                raise ValueError("Start a new snap-fit to change between cylindrical rings and wall mechanisms.")
            if crossed:
                self.clear_preview()
                self.selections.clear()
            # Retain the last valid view while replacement geometry is computed.
            self.preview_revision = None
        self.settings, self.revision = settings, revision

    def prepare(self):
        self.require_selections()
        if self.editing:
            # Re-read ownership at each operation; never trust an old body snapshot.
            target = read_edit_target(self.design, self.edit_target.anchor)
            return prepare_edit_snap_fit(self.design, target, self.settings), target
        return prepare_snap_fit(self.design, *(self.selections[key] for key in SELECTIONS), self.settings), None

    @staticmethod
    def _delete(group):
        if group is not None and group.isValid and group.deleteMe() is False:
            raise RuntimeError("Fusion could not remove a temporary snap-fit preview.")

    def clear_preview(self):
        self.preview_revision = None
        self.preview_sources = None
        failed = []
        for group in ([self.preview] if self.preview is not None else []) + self.retained_groups:
            try:
                self._delete(group)
            except Exception:
                failed.append(group)
        self.preview = failed[0] if failed else None
        self.retained_groups = failed[1:]
        self.visibility.restore()
        if failed:
            raise RuntimeError("Fusion could not clear all snap-fit graphics. Cancel or Stop will retry.")

    def show_preview(self):
        started = time.perf_counter()
        prepared, _ = self.prepare()
        candidate = preview_snap_fit(prepared)
        try:
            if candidate is None or not candidate.isValid:
                raise ValueError("Fusion could not draw the snap-fit preview.")
            self.visibility.hide(preview_hide_bodies(prepared))
            self._delete(self.preview)
        except Exception:
            try:
                self._delete(candidate)
            except Exception:
                self.retained_groups.append(candidate)
            if self.preview is None:
                self.visibility.restore()
            raise
        self.preview = candidate
        self.preview_sources = capture_preview_sources(prepared)
        self.preview_revision = self.revision
        self.phase = "preview"
        self.message = f"{self.settings.snap_count} snap-fit(s). Review the mechanism and matching recess."
        self.owner._publish(self)
        self._timings("preview", prepared, total_ms=(time.perf_counter() - started) * 1000)

    def _timings(self, operation, prepared, **extra):
        values = {**getattr(prepared, "timings", {}), **extra}
        try:
            adsk.core.Application.get().log("Partelier snap-fit " + operation + " timings: " + " ".join(f"{key}={value:.3f}" for key, value in values.items()))
        except Exception:
            pass

    def execute(self, args):
        try:
            started = time.perf_counter()
            prepared, target = self.prepare()
            self.clear_preview()  # Restore source visibility before persistence snapshots.
            persist = time.perf_counter()
            if self.editing:
                rebuild_snap_fit(self.design, target, prepared)
            else:
                create_snap_fit(self.design, prepared)
            self._timings("rebuild" if self.editing else "create", prepared,
                          persistence_ms=(time.perf_counter() - persist) * 1000,
                          total_ms=(time.perf_counter() - started) * 1000)
            self.phase = "created"
            self.message = "Snap-fit rebuilt successfully." if self.editing else "Snap-fit joined into the selected bodies successfully."
        except Exception as error:
            args.executeFailed = True
            args.executeFailedMessage = str(error)[:1200]
            self.phase = "error"
            self.message = str(error)
            self.owner._log("Partelier could not create or rebuild the snap-fit")
            if not isinstance(error, ValueError) and self.owner._report_error is not None:
                self.owner._report_error("Partelier could not create or rebuild the snap-fit")
        self.owner._publish(self)

    def close(self):
        if self.closed:
            return
        self.clear_preview()
        if self.phase != "created":
            self.phase = "cancelled"
            self.message = "Snap-fit cancelled. Original bodies are unchanged."
        self.closed = True
        if self.owner._session is self:
            self.owner._session = None
        self.owner._publish(self)


class _Created(adsk.core.CommandCreatedEventHandler):
    def __init__(self, owner):
        super().__init__()
        self.owner = owner

    def notify(self, args):
        session = self.owner._pending
        self.owner._pending = None
        command = args.command
        command.isExecutedWhenPreEmpted = False
        command.isRepeatable = False
        try:
            if session is None or session.closed or self.owner._session is not session:
                raise ValueError("Start snap-fit creation from the Partelier palette.")
            session.ensure_design()
            session.command = command
            # Cleanup must be available before any geometry handler is bound.
            for event, handler in ((command.destroy, _Destroyed(session)),
                                   (command.execute, _Execute(session))):
                session.handlers.append((event, handler))
                if event.add(handler) is False:
                    raise RuntimeError("Fusion could not attach a snap-fit transaction handler.")
            command.isAutoExecute = True
        except Exception as error:
            # No valid execute handler remains. Close this empty command after
            # Created returns, without leaving the palette or Fusion blocked.
            command.isAutoExecute = True
            command.isOKButtonVisible = False
            if session is not None:
                session.command = None
                session.phase, session.message = "error", str(error)
                for event, handler in session.handlers:
                    try:
                        event.remove(handler)
                    except Exception:
                        self.owner._log("Partelier could not detach a refused snap-fit handler")
                session.handlers.clear()
                self.owner._publish(session)
            self.owner._log("Partelier could not open the snap-fit transaction")


class _Execute(adsk.core.CommandEventHandler):
    def __init__(self, session):
        super().__init__()
        self.session = session

    def notify(self, args):
        if self.session.command is None or self.session.phase != "opening":
            args.executeFailed = True
            args.executeFailedMessage = "The snap-fit transaction did not initialize. Refresh preview to retry."
            return
        self.session.execute(args)


class _Destroyed(adsk.core.CommandEventHandler):
    def __init__(self, session):
        super().__init__()
        self.session = session

    def notify(self, args):
        session = self.session
        for event, handler in session.handlers:
            try:
                event.remove(handler)
            except Exception:
                session.owner._log("Partelier could not detach a snap-fit transaction handler")
        session.handlers.clear()
        session.command = None
        if session.phase == "created":
            session.close()
        else:
            if session.phase == "opening":
                session.phase = "error"
                session.message = "Fusion cancelled the transaction. Refresh preview to retry."
            session.owner._publish(session)


class _DocumentChanging(adsk.core.DocumentEventHandler):
    def __init__(self, owner):
        super().__init__()
        self.owner = owner

    def notify(self, args):
        if self.owner._session is not None:
            try:
                self.owner._session.close()
            except Exception:
                self.owner._log("Partelier could not clear its snap-fit view before changing documents")


class _CommandEnded(adsk.core.ApplicationCommandEventHandler):
    def __init__(self, owner):
        super().__init__()
        self.owner = owner

    def notify(self, args):
        session = self.owner._session
        if self.owner._busy or session is None or session.closed or not session.preview_current:
            return
        if args.commandId in {COMMIT_COMMAND_ID, "SelectCommand"}:
            return
        try:
            validate_preview_sources(session.design, session.preview_sources)
        except Exception as error:
            try:
                session.clear_preview()
            except Exception:
                self.owner._log("Partelier could not clear a stale snap-fit preview")
            session.phase = "error"
            session.message = "The snap-fit sources changed. Refresh or reselect the geometry. " + str(error)
            self.owner._publish(session)

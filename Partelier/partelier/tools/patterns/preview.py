"""Rollback driver for patterns, with nonthrowing lifecycle diagnostics."""

from ...diagnostics import emit
from ..hinge.native_preview import NativePreviewRunner


def _error_text(error):
    try:
        return str(error)
    except Exception:
        return "<unprintable error>"


class PatternPreviewRunner(NativePreviewRunner):
    def __init__(self,report_error=None):
        super().__init__(report_error)
        self._command_id="sktech_partelier_pattern_compute_23bc07a1"
        self._requested_event_id="sktech_partelier_pattern_compute_event_23bc07a1"
        self._event_id=self._requested_event_id

    def _trace(self,event,request=None,**fields):
        try:
            values={"serial":getattr(request,"serial",None),
                    "current_serial":getattr(self._current,"serial",None),
                    "pending_serial":getattr(self._pending,"serial",None),
                    "event_id":self._event_id,"command_id":self._command_id,
                    "stopped":self._stopped}
            try:
                import adsk.core as core
                values["active_command"]=core.Application.get().userInterface.activeCommand
            except Exception:
                values["active_command"]=None
            values.update(fields)
            emit("pattern.runner."+event,**values)
        except Exception:
            pass

    def _start(self):
        self._trace("start.begin")
        try:
            result=super()._start()
            self._definition.name="Partelier: Compute surface pattern"
            self._definition.description="Compute a detached surface pattern, then roll back the working geometry."
        except Exception as error:
            self._trace("start.error",error_type=type(error).__name__,error=_error_text(error))
            raise
        self._trace("start.end")
        return result

    def request(self,tag,compute,completed,failed):
        serial=self._serial+1
        self._trace("request.begin",serial=serial)
        def observed_completed(prepared):
            self._trace("callback.completed.begin",serial=serial)
            try:
                result=completed(prepared)
            except Exception as error:
                self._trace("callback.completed.error",serial=serial,error_type=type(error).__name__,error=_error_text(error))
                raise
            self._trace("callback.completed.end",serial=serial)
            return result
        def observed_failed(error):
            self._trace("callback.failed.begin",serial=serial,error_type=type(error).__name__,error=_error_text(error))
            try:
                result=failed(error)
            except Exception as callback_error:
                self._trace("callback.failed.error",serial=serial,error_type=type(callback_error).__name__,error=_error_text(callback_error))
                raise
            self._trace("callback.failed.end",serial=serial)
            return result
        try:
            result=super().request(tag,compute,observed_completed,observed_failed)
        except Exception as error:
            self._trace("request.error",serial=serial,error_type=type(error).__name__,error=_error_text(error))
            raise
        self._trace("request.end",serial=serial)
        return result

    def _launch(self,request):
        self._trace("launch.begin",request)
        try:
            result=super()._launch(request)
        except Exception as error:
            self._trace("launch.error",request,error_type=type(error).__name__,error=_error_text(error))
            raise
        self._trace("launch.end",request)
        return result

    def created(self,command):
        request=self._current
        self._trace("created.begin",request)
        try:
            result=super().created(command)
        except Exception as error:
            self._trace("created.error",request,error_type=type(error).__name__,error=_error_text(error))
            raise
        self._trace("created.end",request,request_error=_error_text(request.error) if request and request.error else None)
        return result

    def _queue(self,information):
        self._trace("driver.queue.begin",self._current,information=information)
        try:
            result=super()._queue(information)
        except Exception as error:
            self._trace("driver.queue.error",self._current,information=information,error_type=type(error).__name__,error=_error_text(error))
            raise
        self._trace("driver.queued",self._current,information=information)
        return result

    def drive(self,information):
        request=self._current
        self._trace("drive.begin",request,information=information)
        try:
            result=super().drive(information)
        except Exception as error:
            self._trace("drive.error",request,information=information,error_type=type(error).__name__,error=_error_text(error))
            raise
        self._trace("drive.end",request,information=information,
                    request_error=_error_text(request.error) if request and request.error else None)
        return result

    def calculate(self,request,args):
        self._trace("compute.begin",request,cancelled=request.cancelled,computed=request.computed)
        try:
            result=super().calculate(request,args)
        except Exception as error:
            self._trace("compute.raised",request,error_type=type(error).__name__,error=_error_text(error))
            raise
        self._trace("compute.end",request,cancelled=request.cancelled,computed=request.computed,
                    has_prepared=request.prepared is not None,
                    error_type=type(request.error).__name__ if request.error else None,
                    error=_error_text(request.error) if request.error else None)
        return result

    def destroyed(self,request):
        self._trace("destroy.begin",request,cancelled=request.cancelled,executed=request.executed)
        try:
            result=super().destroyed(request)
        except Exception as error:
            self._trace("destroy.error",request,error_type=type(error).__name__,error=_error_text(error))
            raise
        self._trace("destroy.end",request)
        return result

    def _deliver(self,request,*,error=None):
        self._trace("deliver.begin",request,error_type=type(error).__name__ if error else None,
                    error=_error_text(error) if error else None)
        try:
            result=super()._deliver(request,error=error)
        except Exception as raised:
            self._trace("deliver.error",request,error_type=type(raised).__name__,error=_error_text(raised))
            raise
        self._trace("deliver.end",request)
        return result

    def cancel(self,tag=None):
        self._trace("cancel.begin",self._current,all_tags=tag is None)
        try:
            result=super().cancel(tag)
        except Exception as error:
            self._trace("cancel.error",self._current,error_type=type(error).__name__,error=_error_text(error))
            raise
        self._trace("cancel.end",self._current)
        return result

    def stop(self):
        self._trace("stop.begin",self._current)
        try:
            result=super().stop()
        except Exception as error:
            self._trace("stop.error",self._current,error_type=type(error).__name__,error=_error_text(error))
            raise
        self._trace("stop.end")
        return result

    def _log(self,summary):
        self._trace("internal.error",self._current,summary=summary)
        super()._log(summary.replace('hinge','pattern'))

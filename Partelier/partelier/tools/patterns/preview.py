"""Use the proven rollback driver with an independent pattern command/event."""

from ..hinge.native_preview import NativePreviewRunner


class PatternPreviewRunner(NativePreviewRunner):
    def __init__(self,report_error=None):
        super().__init__(report_error)
        self._command_id="sktech_partelier_pattern_compute_23bc07a1"
        self._requested_event_id="sktech_partelier_pattern_compute_event_23bc07a1"
        self._event_id=self._requested_event_id

    def _start(self):
        super()._start()
        self._definition.name="Partelier: Compute surface pattern"
        self._definition.description="Compute a detached surface pattern, then roll back the working geometry."

    def _log(self,summary):
        super()._log(summary.replace('hinge','pattern'))

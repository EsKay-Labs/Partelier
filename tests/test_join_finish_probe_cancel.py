"""Cooperative cancellation ordering with fake events; no Fusion kernel proof."""

import importlib.util
from pathlib import Path
import sys
import tempfile
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import Mock, patch


class JoinFinishProbeCancellationTests(unittest.TestCase):
    def setUp(self):
        self.app = Mock()
        self.core = ModuleType("adsk.core")
        self.core.Application = SimpleNamespace(get=lambda: self.app)
        for name in ("CommandEventHandler", "CommandCreatedEventHandler", "CustomEventHandler"):
            setattr(self.core, name, type(name, (), {}))
        adsk = ModuleType("adsk")
        adsk.__path__ = []
        adsk.core = self.core
        adsk.fusion = ModuleType("adsk.fusion")
        path = Path(__file__).resolve().parents[1] / "tools/fusion/JoinFinishProbe/JoinFinishProbe.py"
        spec = importlib.util.spec_from_file_location("_cancel_probe_test", path)
        self.probe = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, {"adsk": adsk, "adsk.core": self.core, "adsk.fusion": adsk.fusion}):
            spec.loader.exec_module(self.probe)
        self.probe.STATE.update(report={}, context={"cancel_requested": lambda: True})

    def test_queued_initial_drive_never_computes_after_cancellation(self):
        command = Mock()
        self.probe.STATE["command"] = command
        self.app.userInterface.activeCommand = self.probe.COMMAND
        self.app.userInterface.terminateActiveCommand.side_effect = lambda: self.probe.STATE.update(own_command_destroyed=True)
        with patch.object(self.probe, "finish_report") as finish:
            self.probe.Drive().notify(SimpleNamespace(additionalInfo=""))
        command.doExecutePreview.assert_not_called()
        command.doExecute.assert_not_called()
        self.app.userInterface.terminateActiveCommand.assert_called_once_with()
        finish.assert_called_once_with()

    def test_queued_runtime_start_does_not_start_another_preview_after_stop(self):
        with patch.object(self.probe, "runtime_preview_check") as runtime, patch.object(self.probe, "cancel") as cancel:
            self.probe.Drive().notify(SimpleNamespace(additionalInfo="runtime-start"))
        runtime.assert_not_called()
        cancel.assert_called_once_with()

    def test_preview_and_case_entry_guards_avoid_all_geometry(self):
        args = SimpleNamespace(isValidResult=True)
        with patch.object(self.probe, "cases") as cases:
            self.probe.Preview().notify(args)
            cases.assert_not_called()
        self.assertFalse(args.isValidResult)
        self.probe.STATE["design"] = object()
        with patch.object(self.probe, "load") as load:
            self.probe.cases()
            load.assert_not_called()

    def test_cancel_never_terminates_an_unrelated_command(self):
        self.probe.STATE["command"] = Mock()
        self.app.userInterface.activeCommand = "UnrelatedCommand"
        with patch.object(self.probe, "finish_report") as finish:
            self.probe.cancel()
        self.app.userInterface.terminateActiveCommand.assert_not_called()
        finish.assert_not_called()

    def test_cancelled_created_command_auto_executes_only_the_empty_cleanup(self):
        command = Mock()
        self.probe.Created().notify(SimpleNamespace(command=command))
        self.assertTrue(command.isAutoExecute)
        self.app.fireCustomEvent.assert_not_called()
        command.doExecutePreview.assert_not_called()

    def test_cancelled_destroy_finalizes_without_scheduling_runtime_preview(self):
        with tempfile.TemporaryDirectory() as directory:
            callback = Mock()
            self.probe.STATE.update(
                root=Path(directory), design=object(), own_command_destroyed=True,
                report={"success": True, "before": {"unchanged": 1}, "noop_execute": True},
                context={"cancel_requested": lambda: True, "quiet": True, "no_auto_terminate": True,
                         "on_complete": callback, "report_path": str(Path(directory) / "probe.json")})
            with patch.object(self.probe, "snapshot", return_value={"unchanged": 1}):
                self.probe.finish_report()
            self.app.fireCustomEvent.assert_not_called()
            callback.assert_called_once()
            report = callback.call_args.args[0]
            self.assertTrue(report["cancelled"])
            self.assertTrue(report["unchanged"])
            self.assertFalse(report["success"])

    def test_runtime_compute_callback_rechecks_cancel_before_geometry(self):
        cancelled = [False]
        self.probe.STATE.update(context={"cancel_requested": lambda: cancelled[0]},
                                adapter=SimpleNamespace(__package__="fake.hinge"), finish=Mock())
        runner = Mock()
        runtime = SimpleNamespace(PREVIEW_COMMAND_ID="test_command", PREVIEW_EVENT_ID="test_event",
                                  NativePreviewRunner=lambda callback: runner)
        with patch.object(self.probe.importlib, "import_module", return_value=runtime):
            self.probe.runtime_preview_check()
        _, compute, completed, failed = runner.request.call_args.args
        cancelled[0] = True
        with self.assertRaisesRegex(RuntimeError, "cancelled before preview"):
            compute()
        with patch.object(self.probe, "cancel") as cancel:
            completed(None)
            failed("late error")
        self.assertEqual(cancel.call_count, 2)


if __name__ == "__main__":
    unittest.main()

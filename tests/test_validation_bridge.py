"""File protocol/main-thread dispatch checks; these do not validate Fusion geometry."""

import importlib.util
import json
from pathlib import Path
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
import uuid


REPO = Path(__file__).resolve().parents[1]


def load_file(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


bridge = load_file("validation_bridge_test", REPO / "tools/fusion/PartelierValidationBridge/PartelierValidationBridge.py")
cli = load_file("validation_cli_test", REPO / "tools/run_fusion_validation.py")


class ValidationBridgeTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.queue = Path(self.directory.name)
        (self.queue / "requests").mkdir()
        (self.queue / "results").mkdir()
        bridge.STATE.clear()
        bridge.STATE.update(queue=self.queue, active=None, busy=None, stopped=False,
                            app=SimpleNamespace(userInterface=SimpleNamespace(activeCommand="SelectCommand")),
                            session_id=str(uuid.uuid4()))
        bridge._status("ready")

    def tearDown(self):
        bridge.STATE.clear()
        self.directory.cleanup()

    def request(self):
        return {"version": 2, "request_id": str(uuid.uuid4()),
                "scenario": "joined_finish", "submitted_at": time.time(),
                "session_id": bridge.STATE["session_id"]}

    def test_strict_allowlist_rejects_paths_code_other_scenarios_and_uuid_mismatch(self):
        for key, value in (("path", "script.py"), ("code", "print(1)"),
                           ("scenario", "arbitrary"), ("version", True),
                           ("request_id", str(uuid.uuid4()))):
            request = self.request()
            filename = request["request_id"]
            request[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                bridge.validate_request(request, filename)

    def test_uuid_cannot_escape_queue_or_use_noncanonical_spelling(self):
        for value in ("../escape", str(uuid.uuid4()).upper(), "abc", str(uuid.uuid1())):
            with self.subTest(value=value), self.assertRaises(ValueError):
                bridge.canonical_request_id(value)

    def test_atomic_publish_retries_windows_lock_and_cleans_temporary_files(self):
        target = self.queue / "result.json"
        replace = bridge.os.replace
        with patch.object(bridge.os, "replace", side_effect=[PermissionError("locked"), None]) as writer:
            with patch.object(bridge.time, "sleep"):
                bridge.atomic_json(target, {"success": True})
        self.assertEqual(writer.call_count, 2)
        self.assertFalse(list(self.queue.glob("*.tmp")))
        bridge.atomic_json(target, {"success": True})
        self.assertEqual(bridge.read_json(target), {"success": True})

    def test_atomic_publish_exhaustion_is_bounded(self):
        with patch.object(bridge.os, "replace", side_effect=PermissionError("locked")) as writer:
            with patch.object(bridge.time, "sleep"):
                with self.assertRaises(OSError):
                    bridge.atomic_json(self.queue / "result.json", {})
        self.assertEqual(writer.call_count, 4)
        self.assertFalse(list(self.queue.glob("*.tmp")))

    def test_busy_command_is_never_preempted_and_expires_as_blocked(self):
        request = self.request()
        bridge.atomic_json(self.queue / "requests" / (request["request_id"] + ".json"), request)
        bridge.STATE["app"].userInterface.activeCommand = "SomeUserCommand"
        with patch.object(bridge, "_start_request") as start:
            bridge._tick()
            self.assertEqual(bridge.read_json(self.queue / "status.json")["state"], "blocked")
            self.assertIn("SomeUserCommand", bridge.read_json(self.queue / "status.json")["detail"])
            self.assertTrue((self.queue / "requests" / (request["request_id"] + ".json")).exists())
            bridge.STATE["busy"]["since"] -= bridge.MAX_BUSY_SECONDS + 1
            bridge._tick()
            start.assert_not_called()
        result = bridge.read_json(self.queue / "results" / (request["request_id"] + ".json"))
        self.assertEqual(result["state"], "blocked")
        self.assertIn("SomeUserCommand", result["detail"])
        self.assertEqual(bridge.STATE["app"].userInterface.activeCommand, "SomeUserCommand")

    def test_empty_active_command_is_idle_and_dispatches_request(self):
        request = self.request()
        bridge.STATE["app"].userInterface.activeCommand = ""
        bridge.atomic_json(self.queue / "requests" / (request["request_id"] + ".json"), request)
        with patch.object(bridge, "_start_request") as start:
            bridge._tick()
            start.assert_called_once_with(request)
        self.assertEqual(bridge.STATE["app"].userInterface.activeCommand, "")

    def test_old_session_request_cannot_execute_even_with_future_submission_time(self):
        request = self.request()
        request["session_id"] = str(uuid.uuid4())
        request["submitted_at"] += 200
        bridge.atomic_json(self.queue / "requests" / (request["request_id"] + ".json"), request)
        with patch.object(bridge, "_start_request") as start:
            bridge._tick()
            start.assert_not_called()
        result = bridge.read_json(self.queue / "results" / (request["request_id"] + ".json"))
        self.assertEqual(result["state"], "cancelled")
        self.assertFalse(result["success"])

    def test_cli_refuses_a_stopped_session_without_enqueuing_work(self):
        bridge._status("stopped")
        with patch.object(bridge, "queue_root", return_value=self.queue):
            with self.assertRaisesRegex(ValueError, "Load/run"):
                cli.submit(bridge, "joined_finish")
        self.assertFalse(list((self.queue / "requests").glob("*.json")))

    def test_stop_cancels_waiting_jobs_and_requests_active_probe_cleanup(self):
        waiting = self.request()
        bridge.atomic_json(self.queue / "requests" / (waiting["request_id"] + ".json"), waiting)
        active = {"request_id": str(uuid.uuid4()), "cancel_event": threading.Event(),
                  "module": Mock(), "sources": {"sha256": "before"}}
        bridge.STATE.update(active=active, stop_event=Mock(), thread=Mock(), event=Mock(), handler=Mock())
        bridge.STATE["app"].unregisterCustomEvent = Mock()
        bridge.stop(None)
        self.assertTrue(active["cancel_event"].is_set())
        active["module"].cancel.assert_called_once_with()
        result = bridge.read_json(self.queue / "results" / (waiting["request_id"] + ".json"))
        self.assertEqual(result["state"], "cancelled")
        self.assertFalse((self.queue / "results" / (active["request_id"] + ".json")).exists())

    def test_cancelled_completion_is_recorded_after_stop(self):
        active = {"request_id": str(uuid.uuid4()), "cancel_event": threading.Event(),
                  "module_name": "cancelled_probe_test", "sources": {"sha256": "same"},
                  "queue": self.queue, "repo": object(), "session_id": bridge.STATE["session_id"]}
        active["cancel_event"].set()
        bridge.STATE.update(active=active, stopped=True)
        with patch.object(bridge, "source_manifest", return_value={"sha256": "same"}):
            bridge._complete(active["request_id"], {"success": False, "cancelled": True, "unchanged": True}, active)
        result = bridge.read_json(self.queue / "results" / (active["request_id"] + ".json"))
        self.assertEqual(result["state"], "cancelled")
        self.assertTrue(result["report"]["unchanged"])
        self.assertIsNone(bridge.STATE["active"])
        self.assertEqual(bridge.read_json(self.queue / "status.json")["state"], "stopped")

    def test_old_cancelled_callback_cannot_reset_a_new_bridge_session(self):
        old = {"request_id": str(uuid.uuid4()), "cancel_event": threading.Event(),
               "module_name": "old_probe_test", "sources": {"sha256": "same"},
               "queue": self.queue, "repo": object(), "session_id": str(uuid.uuid4())}
        old["cancel_event"].set()
        current = {"request_id": str(uuid.uuid4())}
        bridge.STATE["active"] = current
        with patch.object(bridge, "source_manifest", return_value={"sha256": "same"}):
            bridge._complete(old["request_id"], {"success": False, "cancelled": True}, old)
        self.assertIs(bridge.STATE["active"], current)
        result = bridge.read_json(self.queue / "results" / (old["request_id"] + ".json"))
        self.assertEqual(result["session_id"], old["session_id"])
        self.assertEqual(result["state"], "cancelled")

    def test_only_one_request_dispatches_while_active(self):
        bridge.STATE["active"] = {"request_id": str(uuid.uuid4())}
        with patch.object(bridge, "_next_request") as next_request:
            bridge._tick()
            next_request.assert_not_called()

    def test_malformed_queue_file_becomes_error_without_running_probe(self):
        request = self.request()
        request["scenario"] = "other"
        bridge.atomic_json(self.queue / "requests" / (request["request_id"] + ".json"), request)
        with patch.object(bridge, "_start_request") as start:
            bridge._tick()
            start.assert_not_called()
        result = bridge.read_json(self.queue / "results" / (request["request_id"] + ".json"))
        self.assertEqual(result["state"], "error")

    def test_source_manifest_is_stable_and_detects_changed_hinge_code(self):
        root = self.queue / "repo"
        hinge = root / "Partelier/partelier/tools/hinge"
        probe = root / "tools/fusion/JoinFinishProbe/JoinFinishProbe.py"
        hinge.mkdir(parents=True)
        probe.parent.mkdir(parents=True)
        snap_probe = root / "tools/fusion/SnapFitProbe/SnapFitProbe.py"
        snap_probe.parent.mkdir(parents=True)
        snap_probe.write_text("snap probe", encoding="utf-8")
        pattern_probe = root / "tools/fusion/PatternProbe/PatternProbe.py"
        pattern_probe.parent.mkdir(parents=True)
        pattern_probe.write_text("pattern probe", encoding="utf-8")
        (hinge / "planner.py").write_text("first", encoding="utf-8")
        probe.write_text("probe", encoding="utf-8")
        first = bridge.source_manifest(root)
        self.assertEqual(first, bridge.source_manifest(root))
        (hinge / "planner.py").write_text("second", encoding="utf-8")
        self.assertNotEqual(first["sha256"], bridge.source_manifest(root)["sha256"])

    def test_cli_submit_and_poll_require_the_exact_request_identity(self):
        with patch.object(bridge, "queue_root", return_value=self.queue):
            request_id = cli.submit(bridge, "joined_finish")
            request = bridge.read_json(self.queue / "requests" / (request_id + ".json"))
            bridge.validate_request(request, request_id)
            bridge.atomic_json(self.queue / "results" / (request_id + ".json"),
                               {"version": 2, "scenario": "joined_finish", "request_id": request_id,
                                "success": True, "state": "complete"})
            self.assertTrue(cli.poll(bridge, request_id, 0)["success"])

    def test_cli_timeout_does_not_cancel_the_queued_request(self):
        with patch.object(bridge, "queue_root", return_value=self.queue):
            request_id = cli.submit(bridge, "joined_finish")
            self.assertEqual(cli.poll(bridge, request_id, 0)["state"], "timeout")
            self.assertTrue((self.queue / "requests" / (request_id + ".json")).exists())

    def test_source_change_during_run_cannot_report_success(self):
        request = self.request()
        bridge.STATE.update(repo=object(), active={"request_id": request["request_id"],
                            "module_name": "fixed_test_module", "sources": {"sha256": "before"}})
        with patch.object(bridge, "source_manifest", return_value={"sha256": "after"}):
            bridge._complete(request["request_id"], {"success": True})
        result = bridge.read_json(self.queue / "results" / (request["request_id"] + ".json"))
        self.assertFalse(result["success"])
        self.assertEqual(result["state"], "error")
        self.assertEqual(result["sources_after"]["sha256"], "after")
        self.assertIsNone(bridge.STATE["active"])

    def test_probe_start_failure_finishes_request_and_releases_slot(self):
        request = self.request()
        bridge.STATE["repo"] = object()
        with patch.object(bridge, "source_manifest", side_effect=OSError("source unavailable")):
            bridge._start_request(request)
        self.assertIsNone(bridge.STATE["active"])
        result = bridge.read_json(self.queue / "results" / (request["request_id"] + ".json"))
        self.assertEqual(result["state"], "error")
        self.assertIn("could not start", result["detail"])

    def test_snap_fit_allowlist_keeps_joined_finish_default_and_rejects_arbitrary_dispatch(self):
        self.assertEqual(bridge.PROTOCOL_VERSION, 2)
        self.assertEqual(bridge.SCENARIO, "joined_finish")
        self.assertEqual(bridge.SCENARIOS, {"joined_finish", "snap_fit", "patterns"})
        request = self.request()
        request["scenario"] = "snap_fit"
        self.assertEqual(bridge.validate_request(request, request["request_id"]), request)
        self.assertEqual(bridge.PROBES["snap_fit"],
                         ("tools", "fusion", "SnapFitProbe", "SnapFitProbe.py"))
        for scenario in ("../SnapFitProbe", "snap_fit.py", "print(1)", [], None):
            candidate = dict(request, scenario=scenario)
            with self.subTest(scenario=scenario), self.assertRaises(ValueError):
                bridge.validate_request(candidate, request["request_id"])

    def test_cli_snap_fit_submit_poll_and_timeout_preserve_scenario(self):
        with patch.object(bridge, "queue_root", return_value=self.queue):
            request_id = cli.submit(bridge, "snap_fit")
            request = bridge.read_json(self.queue / "requests" / (request_id + ".json"))
            self.assertEqual(request["scenario"], "snap_fit")
            self.assertEqual(cli.poll(bridge, request_id, 0)["scenario"], "snap_fit")
            bridge.atomic_json(self.queue / "results" / (request_id + ".json"),
                               {"version": 2, "scenario": "snap_fit", "request_id": request_id,
                                "success": True, "state": "complete"})
            self.assertTrue(cli.poll(bridge, request_id, 0)["success"])
            with self.assertRaisesRegex(ValueError, "mismatched"):
                cli.poll(bridge, request_id, 0, expected_scenario="joined_finish")

    def test_cli_snap_fit_refuses_old_loaded_bridge_before_enqueuing(self):
        status_path = self.queue / "status.json"
        status = bridge.read_json(status_path)
        status.pop("scenarios")
        bridge.atomic_json(status_path, status)
        with patch.object(bridge, "queue_root", return_value=self.queue):
            with self.assertRaisesRegex(ValueError, "Reload"):
                cli.submit(bridge, "snap_fit")
            self.assertFalse(list((self.queue / "requests").glob("*.json")))
            self.assertTrue(cli.submit(bridge, "joined_finish"))

    def test_snap_fit_completion_cancel_and_blocked_results_keep_the_request_scenario(self):
        request = self.request()
        request["scenario"] = "snap_fit"
        bridge.atomic_json(self.queue / "requests" / (request["request_id"] + ".json"), request)
        bridge.STATE["app"].userInterface.activeCommand = "SomeUserCommand"
        bridge._tick()
        bridge.STATE["busy"]["since"] -= bridge.MAX_BUSY_SECONDS + 1
        bridge._tick()
        result = bridge.read_json(self.queue / "results" / (request["request_id"] + ".json"))
        self.assertEqual((result["scenario"], result["state"]), ("snap_fit", "blocked"))
        active = {"request_id": str(uuid.uuid4()), "scenario": "snap_fit",
                  "module_name": "fixed_snap_test_module", "sources": {"sha256": "same"},
                  "repo": object(), "session_id": bridge.STATE["session_id"]}
        bridge.STATE["active"] = active
        with patch.object(bridge, "source_manifest", return_value={"sha256": "same"}):
            bridge._complete(active["request_id"], {"success": True}, active)
        result = bridge.read_json(self.queue / "results" / (active["request_id"] + ".json"))
        self.assertEqual((result["scenario"], result["success"]), ("snap_fit", True))

    def test_patterns_scenario_submit_poll_and_old_bridge_refusal(self):
        request = dict(self.request(), scenario="patterns")
        self.assertEqual(bridge.validate_request(request, request["request_id"]), request)
        self.assertEqual(bridge.PROBES["patterns"],
                         ("tools", "fusion", "PatternProbe", "PatternProbe.py"))
        with patch.object(bridge, "queue_root", return_value=self.queue):
            request_id = cli.submit(bridge, "patterns")
            self.assertEqual(cli.poll(bridge, request_id, 0)["scenario"], "patterns")
            bridge.atomic_json(self.queue / "results" / (request_id + ".json"),
                               {"version": 2, "scenario": "patterns", "request_id": request_id,
                                "success": True, "state": "complete"})
            self.assertTrue(cli.poll(bridge, request_id, 0)["success"])
            status = bridge.read_json(self.queue / "status.json")
            status["scenarios"] = ["joined_finish", "snap_fit"]
            bridge.atomic_json(self.queue / "status.json", status)
            with self.assertRaisesRegex(ValueError, "Reload.*patterns"):
                cli.submit(bridge, "patterns")

    def test_manifest_covers_all_runtime_shared_code_and_all_fixed_probes(self):
        root = self.queue / "wide_repo"
        runtime = root / "Partelier/partelier"
        runtime.mkdir(parents=True)
        (runtime / "palette.py").write_text("palette", encoding="utf-8")
        shared = runtime / "tools/solid_pair.py"
        shared.parent.mkdir()
        shared.write_text("shared", encoding="utf-8")
        snap = shared.parent / "snap_fit/fusion.py"
        snap.parent.mkdir()
        snap.write_text("snap", encoding="utf-8")
        for relative in bridge.PROBES.values():
            probe = root.joinpath(*relative)
            probe.parent.mkdir(parents=True)
            probe.write_text("fixed probe", encoding="utf-8")
        first = bridge.source_manifest(root)
        self.assertEqual(len(first["files"]), 6)
        for path in (shared, snap, runtime / "palette.py", root.joinpath(*bridge.PROBES["snap_fit"])):
            old = path.read_text(encoding="utf-8")
            path.write_text("changed", encoding="utf-8")
            with self.subTest(path=path):
                self.assertNotEqual(bridge.source_manifest(root)["sha256"], first["sha256"])
            path.write_text(old, encoding="utf-8")
        root.joinpath(*bridge.PROBES["snap_fit"]).unlink()
        with self.assertRaisesRegex(ValueError, "missing"):
            bridge.source_manifest(root)

    def test_worker_uses_only_file_checks_and_custom_event_queue(self):
        stop_event = Mock()
        stop_event.wait.side_effect = [False, True]
        app = Mock(spec=["fireCustomEvent"])
        bridge._watch(stop_event, app)
        app.fireCustomEvent.assert_called_once_with(bridge.EVENT_ID)

    def test_worker_coalesces_signals_while_fusion_is_busy(self):
        request = self.request()
        bridge.atomic_json(self.queue / "requests" / (request["request_id"] + ".json"), request)
        bridge.STATE["signal_pending"] = threading.Event()
        stop_event = Mock()
        stop_event.wait.side_effect = [False, False, False, True]
        app = Mock(spec=["fireCustomEvent"])
        app.fireCustomEvent.return_value = True
        bridge._watch(stop_event, app)
        app.fireCustomEvent.assert_called_once_with(bridge.EVENT_ID)


if __name__ == "__main__":
    unittest.main()

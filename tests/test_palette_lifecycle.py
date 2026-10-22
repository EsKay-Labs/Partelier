"""Host-adapter contract checks with a fake UI; not native Fusion validation."""

import importlib.util
import json
from pathlib import Path
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from Partelier.partelier.tools.hinge.settings import HingeSettings


class Event:
    def __init__(self):
        self.handlers = []
        self.fail_remove = False

    def add(self, handler):
        self.handlers.append(handler)

    def remove(self, handler):
        if self.fail_remove:
            raise RuntimeError("simulated event teardown failure")
        self.handlers.remove(handler)


class Item:
    def __init__(self, collection, identity):
        self.collection = collection
        self.id = identity
        self.isValid = True
        self.isVisible = False
        self.commandCreated = Event()
        self.incomingFromHTML = Event()
        self.execution_count = 0
        self.sent_messages = []

    def sendInfoToHTML(self, action, data):
        self.sent_messages.append((action, json.loads(data)))
        return ""

    def deleteMe(self):
        self.collection.items.pop(self.id, None)
        self.isValid = False

    def execute(self):
        self.execution_count += 1
        return True


class Collection:
    def __init__(self):
        self.items = {}
        self.creations = 0
        self.last_arguments = None

    def itemById(self, identity):
        return self.items.get(identity)

    def add(self, identity, *arguments):
        if identity in self.items:
            raise RuntimeError("duplicate owned UI")
        self.creations += 1
        self.last_arguments = arguments
        item = Item(self, identity)
        self.items[identity] = item
        return item

    addButtonDefinition = add

    def addCommand(self, definition):
        return self.add(definition.id)


class PaletteLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.controls = Collection()
        self.ui = SimpleNamespace(
            commandDefinitions=Collection(), palettes=Collection(),
            activeCommand="unrelated-command",
        )
        panel = SimpleNamespace(controls=self.controls)
        workspace = SimpleNamespace(toolbarPanels=SimpleNamespace(itemById=lambda _: panel))
        self.ui.workspaces = SimpleNamespace(itemById=lambda _: workspace)
        self.logs = []
        application = SimpleNamespace(userInterface=self.ui, log=self.logs.append)
        core = ModuleType("adsk.core")
        core.CommandCreatedEventHandler = object
        core.HTMLEventHandler = object
        core.Application = SimpleNamespace(get=lambda: application)
        core.PaletteDockingStates = SimpleNamespace(PaletteDockStateRight="right")
        adsk = ModuleType("adsk")
        adsk.core = core
        path = Path(__file__).parents[1] / "Partelier/partelier/palette.py"
        spec = importlib.util.spec_from_file_location("Partelier.partelier._palette_contract_test", path)
        self.module = importlib.util.module_from_spec(spec)
        with patch.dict("sys.modules", {"adsk": adsk, "adsk.core": core}):
            spec.loader.exec_module(self.module)
        self.library = self.module.ToolLibrary()
        self.diagnostic = self.ui.commandDefinitions.add("diagnostic")
        self.library.start("workspace", "panel", "diagnostic", self.fail)
        self.request = json.dumps({"protocol": 1, "requestId": "ui-7"})

    def test_repeated_start_show_and_reopen_do_not_duplicate_owned_ui(self):
        self.library.start("workspace", "panel", "diagnostic", self.fail)
        self.library.show()
        palette = self.ui.palettes.itemById(self.module.PALETTE_ID)
        palette.isVisible = False
        self.library.show()
        self.assertTrue(palette.isVisible)
        self.assertEqual(len(self.controls.items), 1)
        self.assertEqual(self.ui.palettes.creations, 1)
        bundle = Path(__file__).parents[1] / "Partelier"
        version = json.loads((bundle / "Partelier.manifest").read_text(encoding="utf-8"))["version"]
        self.assertEqual(self.ui.palettes.last_arguments[1], (bundle / "partelier/ui/palette.html").resolve().as_uri() + "?v=" + version)
        self.assertEqual(len(palette.incomingFromHTML.handlers), 1)

    def test_workspace_invalidated_palette_can_be_recreated(self):
        self.library.show()
        old = self.ui.palettes.itemById(self.module.PALETTE_ID)
        old.deleteMe()
        self.library.show()
        current = self.ui.palettes.itemById(self.module.PALETTE_ID)
        self.assertIsNot(old, current)
        self.assertTrue(current.isVisible)
        self.assertEqual(len(current.incomingFromHTML.handlers), 1)

    def test_stop_continues_after_handler_cleanup_failure_and_preserves_other_ui(self):
        unrelated = self.ui.palettes.add("unrelated")
        self.library.show()
        self.ui.palettes.itemById(self.module.PALETTE_ID).incomingFromHTML.fail_remove = True
        self.library.stop()
        self.assertIsNone(self.ui.palettes.itemById(self.module.PALETTE_ID))
        self.assertIsNone(self.ui.commandDefinitions.itemById(self.module.COMMAND_ID))
        self.assertEqual(self.controls.items, {})
        self.assertTrue(unrelated.isValid)
        self.assertTrue(self.diagnostic.isValid)
        self.assertEqual(len(self.logs), 1)

    def test_ready_is_read_only_and_only_explicit_diagnostic_request_launches(self):
        reply = json.loads(self.library.handle_message("ready", self.request))
        self.assertEqual(reply["requestId"], "ui-7")
        self.assertEqual(reply["capabilities"], ["input-check"])
        self.assertEqual(self.diagnostic.execution_count, 0)
        self.library.handle_message("open_input_check", self.request)
        self.assertEqual(self.diagnostic.execution_count, 1)

    def test_unsupported_and_malformed_requests_never_launch_a_command(self):
        with self.assertRaises(ValueError):
            self.library.handle_message("create", self.request)
        with self.assertRaises(ValueError):
            self.library.handle_message("open_input_check", "{")
        self.assertEqual(self.diagnostic.execution_count, 0)

    def test_hinge_actions_dispatch_only_validated_settings(self):
        calls = []
        self.library._hinge_commands = SimpleNamespace(
            launch_create=lambda values: calls.append(("create", values)),
            launch_edit=lambda: calls.append(("edit", None)),
        )
        raw = json.dumps({"protocol": 1, "requestId": "hinge-1", "settings": {"length_mm": 30}})
        reply = json.loads(self.library.handle_message("hinge_create", raw))
        self.assertIn("hinge-create", reply["capabilities"])
        self.assertEqual(calls[0][1]["length_mm"], 30)
        self.assertEqual(calls[0][1]["knuckle_count"], 5)
        self.library.handle_message("hinge_edit", self.request)
        self.assertEqual(calls[1], ("edit", None))
        with self.assertRaises(ValueError):
            self.library.handle_message("hinge_create", json.dumps({
                "protocol": 1, "requestId": "hinge-2", "settings": {"length_mm": -1},
            }))
        self.assertEqual(len(calls), 2)

    def test_hinge_capabilities_require_a_running_library(self):
        self.assertNotIn("hinge-create", json.loads(self.library.handle_message("ready", self.request))["capabilities"])
        with self.assertRaises(RuntimeError):
            self.library.handle_message("hinge_edit", self.request)
        self.library._hinge_commands = SimpleNamespace(launch_edit=lambda: self.fail("Stopped manager called"))
        self.library.stop()
        self.assertIsNone(self.library._hinge_commands)
        with self.assertRaises(RuntimeError):
            self.library.handle_message("ready", self.request)

    def palette_manager(self):
        snapshot = {"sessionId": "caf51e65-f35b-44fc-b748-56ee3e879ae6", "revision": 0,
                    "phase": "selecting", "editing": False, "settings": HingeSettings().to_dict(),
                    "selections": {}, "message": "Select the source geometry."}
        manager = SimpleNamespace(
            set_state_callback=Mock(), begin_palette=Mock(return_value=snapshot),
            palette_action=Mock(return_value=snapshot), palette_state=Mock(return_value=snapshot),
            launch_create=Mock(), launch_edit=Mock(),
        )
        self.library.stop()
        self.library.start("workspace", "panel", "diagnostic", self.fail, manager)
        return manager, snapshot

    def test_palette_capability_and_read_only_state_require_the_complete_manager_contract(self):
        manager, snapshot = self.palette_manager()
        self.assertTrue(callable(manager.set_state_callback.call_args.args[0]))
        ready = json.loads(self.library.handle_message("ready", self.request))
        self.assertIn("hinge-palette", ready["capabilities"])
        self.assertEqual(ready["hingeState"], snapshot)
        manager.begin_palette.assert_not_called()
        manager.palette_action.assert_not_called()
        self.assertEqual(json.loads(self.library.handle_message("hinge_status", self.request))["hingeState"], snapshot)

    def test_palette_begin_and_atomic_actions_dispatch_validated_settings_to_current_session(self):
        manager, snapshot = self.palette_manager()
        self.library.handle_message("hinge_begin", json.dumps({
            "protocol": 1, "requestId": "begin", "settings": {"length_mm": 20}, "editing": True,
        }))
        settings = manager.begin_palette.call_args.args[0]
        self.assertEqual(settings["length_mm"], 20)
        self.assertEqual(manager.begin_palette.call_args.kwargs, {"editing": True})
        for action in ("hinge_update", "hinge_preview", "hinge_commit"):
            result = json.loads(self.library.handle_message(action, json.dumps({
                "protocol": 1, "requestId": action, "sessionId": snapshot["sessionId"],
                "revision": 2, "settings": settings,
            })))
            self.assertEqual(result["hingeState"], snapshot)
            self.assertEqual(manager.palette_action.call_args.args, (action, snapshot["sessionId"]))
            self.assertEqual(manager.palette_action.call_args.kwargs, {
                "revision": 2, "settings_dict": settings, "target": None,
            })
        self.library.handle_message("hinge_focus", json.dumps({
            "protocol": 1, "requestId": "focus", "sessionId": snapshot["sessionId"], "target": "axis_edge",
        }))
        self.assertEqual(manager.palette_action.call_args.kwargs["target"], "axis_edge")
        self.library.handle_message("hinge_cancel", json.dumps({
            "protocol": 1, "requestId": "cancel", "sessionId": snapshot["sessionId"],
        }))
        self.assertEqual(manager.palette_action.call_args.args[0], "hinge_cancel")
        manager.launch_create.assert_not_called()
        manager.launch_edit.assert_not_called()

    def test_stale_and_invalid_session_requests_cannot_fall_back_to_legacy_creation(self):
        manager, snapshot = self.palette_manager()
        with self.assertRaises(ValueError):
            self.library.handle_message("hinge_commit", json.dumps({
                "protocol": 1, "requestId": "invalid", "sessionId": snapshot["sessionId"],
                "revision": 1, "settings": {"length_mm": 20},
            }))
        manager.palette_action.assert_not_called()
        manager.palette_action.side_effect = ValueError("The hinge session is no longer active.")
        args = SimpleNamespace(action="hinge_commit", data=json.dumps({
            "protocol": 1, "requestId": "stale", "sessionId": snapshot["sessionId"],
            "revision": 1, "settings": snapshot["settings"],
        }))
        self.module._HTMLMessage(self.library).notify(args)
        reply = json.loads(args.returnData)
        self.assertFalse(reply["ok"])
        self.assertIn("no longer active", reply["message"])
        manager.launch_create.assert_not_called()

    def test_state_push_handles_qt_empty_return_and_ignores_response_acknowledgements(self):
        manager, snapshot = self.palette_manager()
        callback = manager.set_state_callback.call_args.args[0]
        callback(snapshot)
        self.assertEqual(self.logs, [])
        self.library.show()
        palette = self.ui.palettes.itemById(self.module.PALETTE_ID)
        callback(snapshot)
        self.assertEqual(palette.sent_messages, [("hinge_state", snapshot)])
        args = SimpleNamespace(action="response", data="arbitrary Qt acknowledgement")
        self.module._HTMLMessage(self.library).notify(args)
        self.assertEqual(args.returnData, "OK")
        self.assertEqual(self.logs, [])
        manager.palette_action.assert_not_called()
        palette.isValid = False
        callback(snapshot)
        self.assertEqual(len(palette.sent_messages), 1)

    def test_stop_unsubscribes_session_callback_even_when_palette_cleanup_fails(self):
        manager, snapshot = self.palette_manager()
        callback = manager.set_state_callback.call_args.args[0]
        self.library.show()
        self.ui.palettes.itemById(self.module.PALETTE_ID).incomingFromHTML.fail_remove = True
        self.library.stop()
        self.assertEqual(manager.set_state_callback.call_args.args, (None,))
        callback(snapshot)
        manager.palette_action.assert_not_called()
        self.assertIsNone(self.library._hinge_commands)
        with self.assertRaises(RuntimeError):
            self.library.handle_message("hinge_status", self.request)

    def test_stop_then_restart_registers_a_fresh_launcher(self):
        self.library.show()
        self.library.stop()
        self.library.start("workspace", "panel", "diagnostic", self.fail)
        self.library.show()
        self.assertEqual(len(self.controls.items), 1)
        self.assertEqual(self.ui.palettes.creations, 2)


if __name__ == "__main__":
    unittest.main()

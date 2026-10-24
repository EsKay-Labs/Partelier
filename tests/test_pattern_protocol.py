"""Pattern message validation and mutual palette ownership, without native CAD."""

import json
import math
from types import SimpleNamespace as NS
import unittest
from unittest.mock import Mock

from Partelier.partelier.palette_protocol import read_request
from Partelier.partelier.tools.patterns.settings import PatternSettings
from Partelier.partelier.tools.hinge.settings import HingeSettings
from Partelier.partelier.tools.snap_fit.settings import SnapFitSettings

try:
    from . import test_palette_lifecycle as palette_fakes
except ImportError:
    import test_palette_lifecycle as palette_fakes


IDENTITY = "caf51e65-f35b-44fc-b748-56ee3e879ae6"


def request(**values):
    return json.dumps({"protocol": 1, "requestId": "pattern-ui-1", **values})


class PatternProtocolTests(unittest.TestCase):
    def test_finish_faces_is_a_session_action_without_paths_or_settings(self):
        for action in ('pattern_finish_faces','pattern_clear_faces'):
            value=read_request(action,request(sessionId=IDENTITY))
            self.assertEqual(value.session_id,IDENTITY)
            self.assertIsNone(value.settings)
            for extra in ({'path':'script.py'},{'settings':{}},{'target':'faces'}):
                with self.subTest(action=action,extra=extra),self.assertRaises(ValueError):
                    read_request(action,request(sessionId=IDENTITY,**extra))

    def test_colour_export_accepts_only_a_user_selected_owned_result_without_paths(self):
        value=read_request('pattern_export',request())
        self.assertIsNone(value.settings)
        for extra in ({'path':'some-file.3mf'},{'settings':{}},{'sessionId':IDENTITY}):
            with self.subTest(extra=extra),self.assertRaises(ValueError):
                read_request('pattern_export',request(**extra))

    def test_begin_merges_only_pattern_defaults_and_boolean_editing(self):
        value = read_request("pattern_begin", request(settings={"pattern": "circle", "mode": "engrave"}, editing=True))
        self.assertIsInstance(value.settings, PatternSettings)
        self.assertEqual(value.settings, PatternSettings(pattern="circle", mode="engrave"))
        self.assertEqual(value.settings.layout_mode, "auto")
        self.assertTrue(value.editing)
        for editing in (1, "true", None):
            with self.subTest(editing=editing), self.assertRaises(ValueError):
                read_request("pattern_begin", request(settings={}, editing=editing))
        for supplied in ({"length_mm": 40}, {"snap_family": "hook"}, {"path": "other.py"}, [], None):
            with self.subTest(settings=supplied), self.assertRaises(ValueError):
                read_request("pattern_begin", request(settings=supplied, editing=False))

    def test_live_actions_require_all_twelve_fields_and_valid_revision(self):
        values = PatternSettings(pattern="slot", mode="emboss", rotation_deg=-45, offset_u_mm=-2,
                                 layout_mode="fixed").to_dict()
        self.assertEqual(len(values), 15)
        for action in ("pattern_update", "pattern_preview", "pattern_commit"):
            with self.subTest(action=action):
                parsed = read_request(action, request(settings=values, sessionId=IDENTITY, revision=5))
                self.assertEqual(parsed.settings.to_dict(), values)
                self.assertEqual((parsed.session_id, parsed.revision), (IDENTITY, 5))
                for missing in values:
                    partial = {key: value for key, value in values.items() if key != missing}
                    with self.subTest(missing=missing), self.assertRaisesRegex(ValueError, "exactly"):
                        read_request(action, request(settings=partial, sessionId=IDENTITY, revision=5))
                for revision in (-1, 1_000_000_001, True, 1.0, "1", None):
                    with self.subTest(revision=revision), self.assertRaises(ValueError):
                        read_request(action, request(settings=values, sessionId=IDENTITY, revision=revision))

    def test_focus_accepts_only_canonical_sessions_and_pattern_geometry_targets(self):
        for target in ("faces", "add_face", "body", "edit_target"):
            self.assertEqual(read_request("pattern_focus", request(sessionId=IDENTITY, target=target)).target, target)
        for target in ("face_a", "surface", "delete", [], 1, None):
            with self.subTest(target=target), self.assertRaises(ValueError):
                read_request("pattern_focus", request(sessionId=IDENTITY, target=target))
        for identity in (None, "", True, "other-command", IDENTITY.upper(), IDENTITY.replace("-", "")):
            with self.subTest(identity=identity), self.assertRaises(ValueError):
                read_request("pattern_cancel", request(sessionId=identity))

    def test_dimensions_and_enumerations_are_validated_before_host_dispatch(self):
        defaults = PatternSettings().to_dict()
        invalid = (("pitch_mm", 0), ("pitch_mm", True), ("web_mm", PatternSettings().pitch_mm), ("depth_mm", math.inf),
                   ("border_mm", -1), ("rotation_deg", math.nan), ("offset_u_mm", "1"),
                   ("pattern", "unsupported"), ("mode", "generate"), ("selection_scope", "all-models"),
                   ("layout_mode", "stretch"), ("layout_mode", True))
        for name, value in invalid:
            with self.subTest(name=name, value=value), self.assertRaises(ValueError):
                read_request("pattern_preview", request(settings={**defaults, name: value}, sessionId=IDENTITY, revision=0))
        parsed = read_request("pattern_preview", request(settings={**defaults, "border_mm": 0,
            "rotation_deg": -45, "offset_u_mm": -2, "offset_v_mm": -3}, sessionId=IDENTITY, revision=0))
        self.assertEqual(parsed.settings.border_mm, 0)
        self.assertEqual(parsed.settings.offset_v_mm, -3)

    def test_status_cancel_and_focus_never_accept_tokens_paths_or_settings(self):
        for action, fields in (("pattern_status", {}), ("pattern_cancel", {"sessionId": IDENTITY}),
                               ("pattern_focus", {"sessionId": IDENTITY, "target": "faces"})):
            self.assertEqual(read_request(action, request(**fields)).request_id, "pattern-ui-1")
            for injected in ({"entityToken": "unsafe"}, {"path": "file.py"}, {"settings": {}}):
                with self.subTest(action=action, injected=injected), self.assertRaises(ValueError):
                    read_request(action, request(**fields, **injected))
        for action in ("pattern_create", "pattern_edit", "pattern_delete", "pattern_run"):
            with self.subTest(action=action), self.assertRaises(ValueError):
                read_request(action, request())


class PatternPaletteTests(unittest.TestCase):
    setUp = palette_fakes.PaletteLifecycleTests.setUp

    def managers(self):
        managers, states = [], []
        for settings in (HingeSettings(), SnapFitSettings(), PatternSettings()):
            state = {"sessionId": None, "revision": 0, "phase": "idle", "editing": False,
                     "settings": settings.to_dict(), "selections": {}, "message": "Select geometry."}
            manager = NS(set_state_callback=Mock(), begin_palette=Mock(return_value=state),
                         palette_action=Mock(return_value=state), palette_state=Mock(return_value=state),
                         launch_create=Mock(), launch_edit=Mock(), busy=False)
            managers.append(manager)
            states.append(state)
        self.library.stop()
        self.library.start("workspace", "panel", "diagnostic", self.fail,
                           hinge_commands=managers[0], snap_commands=managers[1], pattern_commands=managers[2])
        return managers, states

    def test_ready_and_status_are_read_only_and_expose_pattern_contract(self):
        managers, states = self.managers()
        ready = json.loads(self.library.handle_message("ready", request()))
        self.assertIn("pattern-palette", ready["capabilities"])
        self.assertIn("pattern-edit", ready["capabilities"])
        self.assertEqual(ready["patternDefaults"], PatternSettings().to_dict())
        self.assertEqual(ready["patternState"], states[2])
        self.assertEqual(json.loads(self.library.handle_message("pattern_status", request()))["patternState"], states[2])
        for manager in managers:
            manager.begin_palette.assert_not_called()
            manager.palette_action.assert_not_called()

    def test_begin_atomic_actions_focus_and_cancel_reach_only_pattern_manager(self):
        managers, states = self.managers()
        pattern = managers[2]
        self.library.handle_message("pattern_begin", request(settings={"pattern": "diamond"}, editing=True))
        pattern.begin_palette.assert_called_once_with(PatternSettings(pattern="diamond").to_dict(), editing=True)
        settings = PatternSettings(mode="emboss", selection_scope="body").to_dict()
        for action in ("pattern_update", "pattern_preview", "pattern_commit"):
            reply = json.loads(self.library.handle_message(action, request(sessionId=IDENTITY, revision=3, settings=settings)))
            self.assertEqual(reply["patternState"], states[2])
            self.assertEqual(pattern.palette_action.call_args.args, (action, IDENTITY))
            self.assertEqual(pattern.palette_action.call_args.kwargs, {"revision": 3, "settings_dict": settings, "target": None})
        self.library.handle_message("pattern_focus", request(sessionId=IDENTITY, target="body"))
        self.assertEqual(pattern.palette_action.call_args.kwargs["target"], "body")
        self.library.handle_message("pattern_cancel", request(sessionId=IDENTITY))
        self.assertEqual(pattern.palette_action.call_args.args, ("pattern_cancel", IDENTITY))
        for manager in managers[:2]:
            manager.begin_palette.assert_not_called()
            manager.palette_action.assert_not_called()
            manager.launch_create.assert_not_called()

    def test_malformed_or_expired_commit_cannot_fall_back_to_another_tool(self):
        managers, _ = self.managers()
        with self.assertRaises(ValueError):
            self.library.handle_message("pattern_commit", request(sessionId=IDENTITY, revision=0, settings={"pitch_mm": 8}))
        managers[2].palette_action.assert_not_called()
        managers[2].palette_action.side_effect = ValueError("This pattern session has ended.")
        args = NS(action="pattern_commit", data=request(sessionId=IDENTITY, revision=0, settings=PatternSettings().to_dict()))
        self.module._HTMLMessage(self.library).notify(args)
        self.assertFalse(json.loads(args.returnData)["ok"])
        self.assertIn("ended", json.loads(args.returnData)["message"])
        for manager in managers:
            manager.launch_create.assert_not_called()

    def test_pattern_begin_refuses_hinge_or_snap_active_and_busy_states(self):
        managers, states = self.managers()
        for index in (0, 1):
            for phase in ("selecting", "ready", "computing", "preview", "opening", "error"):
                with self.subTest(tool=index, phase=phase):
                    states[index].update(sessionId=IDENTITY, phase=phase)
                    with self.assertRaisesRegex(ValueError, "Finish or cancel"):
                        self.library.handle_message("pattern_begin", request(settings={}, editing=False))
            states[index].update(sessionId=None, phase="cancelled")
            managers[index].busy = True
            with self.assertRaisesRegex(ValueError, "Wait for"):
                self.library.handle_message("pattern_begin", request(settings={}, editing=False))
            managers[index].busy = False
        managers[2].begin_palette.assert_not_called()

    def test_active_pattern_blocks_hinge_snap_and_legacy_launches(self):
        managers, states = self.managers()
        states[2].update(sessionId=IDENTITY, phase="preview")
        for action, fields in (("hinge_begin", {"settings": {}, "editing": False}),
                               ("snap_begin", {"settings": {}, "editing": False}),
                               ("hinge_create", {"settings": {}}), ("hinge_edit", {})):
            with self.subTest(action=action), self.assertRaisesRegex(ValueError, "current pattern"):
                self.library.handle_message(action, request(**fields))
        for manager in managers[:2]:
            manager.begin_palette.assert_not_called()
            manager.launch_create.assert_not_called()
            manager.launch_edit.assert_not_called()
        states[2].update(sessionId=None, phase="cancelled")
        managers[2].busy = True
        with self.assertRaisesRegex(ValueError, "Wait for"):
            self.library.handle_message("hinge_begin", request(settings={}, editing=False))

    def test_terminal_states_allow_begin_and_same_tool_cancel_stays_available(self):
        managers, states = self.managers()
        for phase in ("idle", "created", "cancelled"):
            for state in states[:2]:
                state.update(sessionId=IDENTITY, phase=phase)
            self.library.handle_message("pattern_begin", request(settings={}, editing=False))
        self.assertEqual(managers[2].begin_palette.call_count, 3)
        for state in states[:2]:
            state.update(sessionId=IDENTITY, phase="preview")
        self.library.handle_message("pattern_cancel", request(sessionId=IDENTITY))
        managers[2].palette_action.assert_called_once()

    def test_pattern_pushes_and_all_callbacks_are_cleaned_even_after_palette_failure(self):
        managers, states = self.managers()
        callback = managers[2].set_state_callback.call_args.args[0]
        callback(states[2])
        self.library.show()
        palette = self.ui.palettes.itemById(self.module.PALETTE_ID)
        callback(states[2])
        self.assertEqual(palette.sent_messages, [("pattern_state", states[2])])
        palette.incomingFromHTML.fail_remove = True
        self.library.stop()
        for manager in managers:
            self.assertEqual(manager.set_state_callback.call_args.args, (None,))
        self.assertIsNone(self.library._pattern_commands)
        callback(states[2])
        self.assertEqual(len(palette.sent_messages), 1)

    def test_pattern_capability_requires_full_manager_and_running_library(self):
        self.library._pattern_commands = NS(begin_palette=Mock())
        ready = json.loads(self.library.handle_message("ready", request()))
        self.assertNotIn("pattern-palette", ready["capabilities"])
        self.assertIsNone(ready["patternState"])
        with self.assertRaises(RuntimeError):
            self.library.handle_message("pattern_status", request())
        self.library.stop()
        with self.assertRaises(RuntimeError):
            self.library.handle_message("pattern_status", request())


if __name__ == "__main__":
    unittest.main()

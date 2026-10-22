"""The HTML bridge must not accept unimplemented model operations."""

import json
import math
import unittest

from Partelier.partelier.palette_protocol import read_request
from Partelier.partelier.tools.hinge.settings import HingeSettings
from Partelier.partelier.tools.snap_fit.settings import SnapFitSettings


class PaletteProtocolTests(unittest.TestCase):
    def request(self, **updates):
        payload = {"protocol": 1, "requestId": "ui-1"}
        payload.update(updates)
        return json.dumps(payload)

    def test_supported_ui_messages_keep_request_identity(self):
        for action in ("ready", "open_input_check"):
            with self.subTest(action=action):
                self.assertEqual(read_request(action, self.request()).request_id, "ui-1")

    def test_create_accepts_only_valid_hinge_settings(self):
        request = read_request("hinge_create", self.request(settings={"length_mm": 50}))
        self.assertEqual(request.settings.length_mm, 50)
        self.assertEqual(request.settings.pin_diameter_mm, 3)
        self.assertEqual(read_request("hinge_edit", self.request()).request_id, "ui-1")

    def test_split_seam_fields_are_validated_before_the_host(self):
        request = read_request("hinge_create", self.request(settings={
            "split_seam": True, "seam_clearance_mm": 0.45}))
        self.assertTrue(request.settings.split_seam)
        self.assertEqual(request.settings.seam_clearance_mm, 0.45)
        self.assertEqual(request.settings.axis_offset_mm, 4)
        for values in ({"split_seam": "true"}, {"split_seam": 1},
                       {"seam_clearance_mm": 0}, {"seam_clearance_mm": True},
                       {"split_seam": True, "seam_clearance_mm": 24}):
            with self.subTest(values=values), self.assertRaises(ValueError):
                read_request("hinge_create", self.request(settings=values))

    def test_distribution_settings_reach_the_create_request_without_losing_values(self):
        request = read_request("hinge_create", self.request(settings={
            "hinge_count": 3, "start_margin_mm": 5.5, "end_margin_mm": 8,
            "length_mm": 30, "include_pin": False,
        }))
        self.assertEqual(request.request_id, "ui-1")
        self.assertEqual(request.settings.hinge_count, 3)
        self.assertEqual(request.settings.start_margin_mm, 5.5)
        self.assertEqual(request.settings.end_margin_mm, 8.0)
        self.assertEqual(request.settings.length_mm, 30)
        self.assertFalse(request.settings.include_pin)
        self.assertEqual(request.settings.knuckle_count, 5)

    def test_distribution_zero_margins_and_maximum_count_are_valid(self):
        request = read_request("hinge_create", self.request(settings={
            "hinge_count": 20, "start_margin_mm": 0, "end_margin_mm": 0,
        }))
        self.assertEqual(request.settings.hinge_count, 20)
        self.assertEqual(request.settings.start_margin_mm, 0.0)
        self.assertEqual(request.settings.end_margin_mm, 0.0)

    def test_each_partial_distribution_request_merges_only_missing_defaults(self):
        cases = (
            ({}, 1, 0, 0),
            ({"length_mm": 50}, 1, 0, 0),
            ({"hinge_count": 2}, 2, 0, 0),
            ({"start_margin_mm": 7}, 1, 7, 0),
            ({"end_margin_mm": 9}, 1, 0, 9),
        )
        for supplied, count, start, end in cases:
            with self.subTest(supplied=supplied):
                settings = read_request("hinge_create", self.request(settings=supplied)).settings
                self.assertEqual((settings.hinge_count, settings.start_margin_mm,
                                  settings.end_margin_mm), (count, start, end))
                self.assertEqual(settings.length_mm, supplied.get("length_mm", 40))
                self.assertEqual(settings.pin_overhang_mm, 2)

    def test_invalid_distribution_count_never_reaches_the_host(self):
        for count in (0, -1, 21, 2.0, True, False, "2", None):
            with self.subTest(count=count), self.assertRaisesRegex(ValueError, "Hinge count"):
                read_request("hinge_create", self.request(settings={"hinge_count": count}))

    def test_invalid_distribution_margins_never_reach_the_host(self):
        for name in ("start_margin_mm", "end_margin_mm"):
            for value in (-0.01, True, "0", None, math.inf, -math.inf, math.nan):
                with self.subTest(name=name, value=value), self.assertRaisesRegex(ValueError, "nonnegative"):
                    read_request("hinge_create", self.request(settings={name: value}))

    def test_distribution_fields_are_specific_to_hinge_create(self):
        for action in ("ready", "open_input_check", "hinge_edit"):
            with self.subTest(action=action), self.assertRaisesRegex(ValueError, "Unexpected data"):
                read_request(action, self.request(settings={"hinge_count": 2}))

    def test_distribution_edge_fit_is_deferred_until_the_host_selection_is_known(self):
        settings = read_request("hinge_create", self.request(settings={
            "hinge_count": 20, "start_margin_mm": 1000000,
            "end_margin_mm": 2000000,
        })).settings
        self.assertEqual(settings.hinge_count, 20)
        self.assertEqual(settings.start_margin_mm, 1000000)
        self.assertEqual(settings.end_margin_mm, 2000000)

    def test_invalid_create_never_passes_the_bridge(self):
        for settings in ({"length_mm": -1}, {"commandId": "other"}, None, {"knuckle_count": 4}, {"include_pin": "yes"}):
            with self.subTest(settings=settings), self.assertRaises(ValueError):
                read_request("hinge_create", self.request(settings=settings))

    def test_palette_begin_merges_defaults_and_accepts_only_explicit_boolean_editing(self):
        request = read_request("hinge_begin", self.request(settings={"length_mm": 20}, editing=True))
        self.assertTrue(request.editing)
        self.assertEqual(request.settings.length_mm, 20)
        self.assertEqual(request.settings.hinge_count, 1)
        for editing in (1, "true", None):
            with self.subTest(editing=editing), self.assertRaises(ValueError):
                read_request("hinge_begin", self.request(settings={}, editing=editing))

    def test_active_palette_actions_require_complete_atomic_settings_and_revision(self):
        identity = "caf51e65-f35b-44fc-b748-56ee3e879ae6"
        settings = HingeSettings(length_mm=20, hinge_count=3).to_dict()
        for action in ("hinge_update", "hinge_preview", "hinge_commit"):
            with self.subTest(action=action):
                request = read_request(action, self.request(settings=settings, sessionId=identity, revision=4))
                self.assertEqual(request.session_id, identity)
                self.assertEqual(request.revision, 4)
                self.assertEqual(request.settings.to_dict(), settings)
                with self.assertRaisesRegex(ValueError, "exactly"):
                    read_request(action, self.request(settings={"length_mm": 20}, sessionId=identity, revision=4))
                for revision in (-1, 1_000_000_001, True, 1.0, "1", None):
                    with self.subTest(revision=revision), self.assertRaises(ValueError):
                        read_request(action, self.request(settings=settings, sessionId=identity, revision=revision))

    def test_palette_session_identifiers_and_focus_targets_are_bounded(self):
        identity = "caf51e65-f35b-44fc-b748-56ee3e879ae6"
        for invalid in (None, "", "other-command", 1, identity.replace("-", ""), identity.upper()):
            with self.subTest(identity=invalid), self.assertRaises(ValueError):
                read_request("hinge_cancel", self.request(sessionId=invalid))
        self.assertEqual(read_request("hinge_cancel", self.request(sessionId=identity)).session_id, identity)
        for target in ("face_a", "face_b", "axis_edge", "edit_target"):
            self.assertEqual(read_request("hinge_focus", self.request(sessionId=identity, target=target)).target, target)
        for target in ("any", "body", "delete", [], None, 1):
            with self.subTest(target=target), self.assertRaises(ValueError):
                read_request("hinge_focus", self.request(sessionId=identity, target=target))

    def test_palette_action_shapes_never_accept_tokens_paths_or_arbitrary_fields(self):
        identity = "caf51e65-f35b-44fc-b748-56ee3e879ae6"
        for action, fields in (("hinge_status", {}), ("hinge_cancel", {"sessionId": identity}),
                               ("hinge_focus", {"sessionId": identity, "target": "face_a"})):
            self.assertEqual(read_request(action, self.request(**fields)).request_id, "ui-1")
            with self.assertRaises(ValueError):
                read_request(action, self.request(**fields, entityToken="untrusted token"))
        with self.assertRaises(ValueError):
            read_request("hinge_begin", self.request(settings={"path": "other.py"}, editing=False))
        with self.assertRaises(ValueError):
            read_request("response", self.request())

    def test_model_operations_are_not_available(self):
        for action in ("create", "preview", "generate", "delete", "open_url"):
            with self.subTest(action=action), self.assertRaises(ValueError):
                read_request(action, self.request())

    def test_invalid_messages_are_rejected(self):
        invalid = [None, "{", "[]", "null", "true", '"text"', " " * 4097]
        for payload in invalid:
            with self.subTest(payload=str(payload)[:30]), self.assertRaises(ValueError):
                read_request("ready", payload)

    def test_unknown_or_boolean_protocol_is_rejected(self):
        for version in (None, 0, 2, True, 1.0, "1"):
            with self.subTest(version=version), self.assertRaises(ValueError):
                read_request("ready", self.request(protocol=version))

    def test_missing_or_invalid_request_identity_is_rejected(self):
        for identity in (None, "", 1, "a" * 81):
            with self.subTest(identity=identity), self.assertRaises(ValueError):
                read_request("ready", self.request(requestId=identity))

    def test_additional_parameters_cannot_reach_host(self):
        with self.assertRaises(ValueError):
            read_request("open_input_check", self.request(commandId="unrelated-command"))


class SnapPaletteProtocolTests(unittest.TestCase):
    identity = "caf51e65-f35b-44fc-b748-56ee3e879ae6"

    def request(self, **updates):
        return json.dumps({"protocol": 1, "requestId": "snap-ui-1", **updates})

    def test_begin_merges_only_snap_defaults_and_boolean_edit_mode(self):
        request = read_request("snap_begin", self.request(settings={"width_mm": 10}, editing=True))
        self.assertIsInstance(request.settings, SnapFitSettings)
        self.assertEqual(request.settings.width_mm, 10)
        self.assertEqual(request.settings.reach_mm, 16)
        self.assertTrue(request.editing)
        for editing in (0, 1, "true", None):
            with self.subTest(editing=editing), self.assertRaises(ValueError):
                read_request("snap_begin", self.request(settings={}, editing=editing))
        for supplied in ({"length_mm": 40}, {"commandId": "other"}, None, []):
            with self.subTest(supplied=supplied), self.assertRaises(ValueError):
                read_request("snap_begin", self.request(settings=supplied, editing=False))

    def test_live_actions_require_complete_atomic_snap_settings(self):
        settings = SnapFitSettings(width_mm=12, snap_count=3).to_dict()
        for action in ("snap_update", "snap_preview", "snap_commit"):
            with self.subTest(action=action):
                request = read_request(action, self.request(settings=settings, sessionId=self.identity, revision=9))
                self.assertEqual(request.settings.to_dict(), settings)
                self.assertEqual((request.session_id, request.revision), (self.identity, 9))
                for missing in settings:
                    incomplete = {key: value for key, value in settings.items() if key != missing}
                    with self.subTest(missing=missing), self.assertRaisesRegex(ValueError, "exactly"):
                        read_request(action, self.request(settings=incomplete, sessionId=self.identity, revision=9))
                with self.assertRaises(ValueError):
                    read_request(action, self.request(settings=HingeSettings().to_dict(), sessionId=self.identity, revision=9))

    def test_revision_and_settings_type_validation_precedes_native_operations(self):
        settings = SnapFitSettings().to_dict()
        for revision in (-1, 1_000_000_001, True, 1.0, "1", None):
            with self.subTest(revision=revision), self.assertRaises(ValueError):
                read_request("snap_preview", self.request(settings=settings, sessionId=self.identity, revision=revision))
        for name, value in (("snap_count", 1.0), ("snap_count", True), ("width_mm", "8"),
                            ("width_mm", math.inf), ("clearance_mm", math.nan), ("thickness_mm", 0)):
            with self.subTest(name=name, value=value), self.assertRaises(ValueError):
                read_request("snap_preview", self.request(settings={**settings, name: value}, sessionId=self.identity, revision=0))

    def test_only_canonical_current_session_identifiers_are_accepted(self):
        for identity in (None, "", 1, "other-command", self.identity.upper(), self.identity.replace("-", "")):
            with self.subTest(identity=identity), self.assertRaises(ValueError):
                read_request("snap_cancel", self.request(sessionId=identity))
        self.assertEqual(read_request("snap_cancel", self.request(sessionId=self.identity)).session_id, self.identity)

    def test_focus_targets_are_explicit_geometry_slots(self):
        for target in ("face_a", "face_b", "axis_edge", "edit_target"):
            self.assertEqual(read_request("snap_focus", self.request(sessionId=self.identity, target=target)).target, target)
        for target in ("body", "delete", [], None, 1):
            with self.subTest(target=target), self.assertRaises(ValueError):
                read_request("snap_focus", self.request(sessionId=self.identity, target=target))

    def test_status_cancel_and_focus_reject_extra_host_instructions(self):
        for action, fields in (("snap_status", {}), ("snap_cancel", {"sessionId": self.identity}),
                               ("snap_focus", {"sessionId": self.identity, "target": "face_a"})):
            with self.subTest(action=action):
                self.assertEqual(read_request(action, self.request(**fields)).request_id, "snap-ui-1")
                for injected in ({"entityToken": "untrusted"}, {"path": "other.py"}, {"settings": {}}):
                    with self.assertRaises(ValueError):
                        read_request(action, self.request(**fields, **injected))
        for action in ("snap_create", "snap_edit", "snap_delete", "snap_run_script"):
            with self.subTest(action=action), self.assertRaises(ValueError):
                read_request(action, self.request())


if __name__ == "__main__":
    unittest.main()

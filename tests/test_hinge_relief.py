"""Movement-relief planning and fake-host safety contracts, never kernel proof."""

from dataclasses import FrozenInstanceError, replace
import json
import math
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from Partelier.partelier.tools.hinge import fusion, relief, support
from Partelier.partelier.tools.hinge.planner import build_hinge_plan
from Partelier.partelier.tools.hinge.settings import HingeSettings


class RotationReliefSettingsTests(unittest.TestCase):
    def test_default_is_radial_and_distinct_from_diametral_bore_clearance(self):
        settings = HingeSettings()
        self.assertEqual(settings.rotation_clearance_mm, .3)
        changed = replace(settings, rotation_clearance_mm=.8)
        self.assertEqual(changed.diametral_clearance_mm, settings.diametral_clearance_mm)
        self.assertEqual(HingeSettings.from_dict(changed.to_dict()), changed)
        with self.assertRaises(FrozenInstanceError):
            changed.rotation_clearance_mm = .2

    def test_zero_is_a_valid_legacy_no_relief_setting_and_current_schema_is_strict(self):
        settings = HingeSettings(rotation_clearance_mm=0)
        self.assertEqual(settings.rotation_clearance_mm, 0.0)
        self.assertIsNone(relief.plan_rotation_relief(settings))
        self.assertEqual(HingeSettings.from_dict(settings.to_dict()), settings)
        missing = settings.to_dict()
        missing.pop("rotation_clearance_mm")
        with self.assertRaisesRegex(ValueError, "exactly"):
            HingeSettings.from_dict(missing)
        with self.assertRaisesRegex(ValueError, "exactly"):
            HingeSettings.from_dict({**settings.to_dict(), "rotation_clearance": .3})

    def test_negative_nonfinite_nonnumeric_and_unrepresentable_clearance_are_rejected(self):
        for value in (-.1, True, False, None, ".3", math.inf, -math.inf, math.nan,
                      10 ** 1000):
            with self.subTest(value=repr(value)), self.assertRaises(ValueError):
                HingeSettings(rotation_clearance_mm=value)
        with self.assertRaisesRegex(ValueError, "distinct finite"):
            HingeSettings(rotation_clearance_mm=1e-16)
        with self.assertRaisesRegex(ValueError, "distinct finite"):
            HingeSettings(barrel_diameter_mm=1e308, rotation_clearance_mm=1.6e308)
        with self.assertRaisesRegex(ValueError, "distinct finite"):
            HingeSettings(length_mm=1.7e308, rotation_clearance_mm=1e308)

    def test_plan_expands_radially_and_past_both_ends_for_all_housings_and_outputs(self):
        for mode in ("attached", "separate"):
            for profile in ("round", "square"):
                settings = HingeSettings(output_mode=mode, knuckle_profile=profile,
                                         rotation_clearance_mm=.7)
                plan = relief.plan_rotation_relief(settings)
                self.assertEqual(plan.housing_radius_mm, 4)
                self.assertEqual(plan.cutter_radius_mm, 4.7)
                self.assertEqual(plan.start_mm, -20.7)
                self.assertEqual(plan.end_mm, 20.7)
                self.assertEqual(plan.clearance_mm, .7)
                self.assertTrue(all(math.isfinite(value) for value in (
                    plan.start_mm, plan.end_mm, plan.cutter_radius_mm)))
                self.assertGreater(plan.cutter_radius_mm, plan.housing_radius_mm)
                self.assertGreater(plan.end_mm, settings.length_mm / 2)
                self.assertLess(plan.start_mm, -settings.length_mm / 2)

    def test_plan_scales_with_mm_inputs_without_changing_nonlength_settings(self):
        original = HingeSettings()
        for scale in (.01, .1, 10, 1000):
            scaled = HingeSettings(**{
                key: value * scale if key.endswith("_mm") else value
                for key, value in original.to_dict().items()})
            plan = relief.plan_rotation_relief(scaled)
            self.assertAlmostEqual(plan.cutter_radius_mm / scale, 4.3)
            self.assertAlmostEqual(plan.start_mm / scale, -20.3)
            self.assertAlmostEqual(plan.end_mm / scale, 20.3)

    def test_legacy_recipes_keep_zero_relief_and_original_support_style(self):
        current = HingeSettings()
        base = {
            "version": 8, "tool": fusion.TOOL_ID,
            "feature_id": "de431a33-e909-4d18-9f1f-7518678982a4",
            "settings": current.to_dict(),
            "sources": {name: name for name in
                        ("face_a", "face_b", "axis_edge", "body_a", "body_b")},
            "results": {name: "a" * 64 for name in ("A", "B", "pin")},
            "base_feature": "owned base",
        }
        versions = {
            1: fusion.LEGACY_SETTINGS_FIELDS,
            2: fusion.VERSION_TWO_SETTINGS_FIELDS,
            3: fusion.VERSION_THREE_SETTINGS_FIELDS,
            4: fusion.VERSION_FOUR_SETTINGS_FIELDS,
            5: fusion.VERSION_FIVE_SETTINGS_FIELDS,
            6: fusion.VERSION_SIX_SETTINGS_FIELDS,
            7: fusion.VERSION_SEVEN_SETTINGS_FIELDS,
        }
        for version, keys in versions.items():
            recipe = {**base, "version": version,
                      "settings": {key: current.to_dict()[key] for key in keys}}
            encoded = json.dumps(recipe, sort_keys=True)
            raw, restored = fusion._read_recipe(encoded)
            self.assertEqual(restored.rotation_clearance_mm, 0)
            self.assertEqual(restored.web_profile, "flat" if version < 7 else "tangent")
            self.assertEqual(json.dumps(raw, sort_keys=True), encoded)
        self.assertEqual(fusion._read_recipe(json.dumps(base))[1], current)


class SeparateTaperHoleLipTests(unittest.TestCase):
    def test_all_housing_finishes_keep_raised_support_inside_each_flat_hole_lip(self):
        for housing in ("round", "square"):
            for finish in ("sharp", "chamfer", "fillet"):
                dimensions = {"output_mode": "separate", "knuckle_profile": housing,
                              "web_profile": "tangent", "screw_holes": True,
                              "chamfer_edges": finish == "chamfer",
                              "fillet_edges": finish == "fillet",
                              "fillet_radius_mm": .4}
                with self.subTest(housing=housing, finish=finish):
                    settings = HingeSettings(**dimensions)
                    plan = build_hinge_plan(settings)
                    size = (.4 if finish == "fillet" else
                            settings.chamfer_size_mm if finish == "chamfer" else 0)
                    plates = {plate.owner: plate for plate in plan.plates}
                    for web in plan.webs:
                        shape = support.plan_tangent_support(
                            web, plan.barrel_radius_mm,
                            knuckle_profile=housing, attached=False)
                        extent = max(abs(x) for x, _ in shape.polygon_xz_mm)
                        self.assertLessEqual(extent, settings.leaf_reach_mm)
                        self.assertEqual(min(z for _, z in shape.polygon_xz_mm), 0)
                        plate = plates[web.owner]
                        plate_inner = min(abs(plate.x_min_mm), abs(plate.x_max_mm))
                        self.assertGreater(extent, plate_inner)
                        for hole in plan.mounting_holes:
                            if hole.owner == web.owner:
                                inward_lip = abs(hole.x_mm) - hole.diameter_mm / 2 - size
                                self.assertLess(extent, inward_lip)

    def test_flat_web_option_retains_the_earlier_nominal_reach(self):
        tapered = build_hinge_plan(HingeSettings(output_mode="separate",
                                                screw_holes=True, web_profile="tangent"))
        flat = build_hinge_plan(HingeSettings(output_mode="separate",
                                             screw_holes=True, web_profile="flat"))
        self.assertLess(abs(tapered.webs[0].x_min_mm), abs(flat.webs[0].x_min_mm))
        self.assertEqual(tapered.mounting_holes, flat.mounting_holes)
        self.assertEqual(tapered.plates, flat.plates)


class Body:
    def __init__(self, volume=10.0, *, temporary=True, kind="copy"):
        self.volume = volume
        self.isTemporary = temporary
        self.isValid = True
        self.isSolid = True
        self.lumps = SimpleNamespace(count=1)
        self.kind = kind


class Manager:
    """Deterministic volume/failure fixture; this is not a geometry engine."""

    def __init__(self):
        self.calls = []
        self.copies = []
        self.fail_copy = False
        self.fail_cut = False
        self.fail_marker = False
        self.split_cut = False
        self.invalid_cut = False
        self.remove_volume = 2.0
        self.after_volume = None
        self.marker_volume = None

    def copy(self, body):
        self.copies.append(body)
        if self.fail_copy:
            return None
        return Body(body.volume)

    def booleanOperation(self, target, tool, operation):
        self.calls.append((target, tool, operation))
        if operation != "difference":
            raise AssertionError("Relief should use temporary differences only.")
        if tool.kind == "cutter":
            if self.fail_cut:
                return False
            target.volume = (self.after_volume if self.after_volume is not None
                             else target.volume - self.remove_volume)
            if self.split_cut:
                target.lumps = SimpleNamespace(count=2)
            if self.invalid_cut:
                target.isValid = False
        else:
            if self.fail_marker:
                return False
            target.volume = (self.marker_volume if self.marker_volume is not None
                             else target.volume - tool.volume)
        return True


class RotationReliefAdapterTests(unittest.TestCase):
    def setUp(self):
        self.settings = HingeSettings()
        self.frame = fusion.HingeFrame((12, -3, 9), (0, 1, 0), (0, 0, 1), (1, 0, 0))
        self.manager = Manager()
        self.measure = Mock(return_value=SimpleNamespace(value=.03))
        app = SimpleNamespace(measureManager=SimpleNamespace(
            measureMinimumDistance=self.measure))
        self.core = SimpleNamespace(Application=SimpleNamespace(get=lambda: app))
        self.api_patch = patch.object(fusion, "_api", return_value=(
            self.core, SimpleNamespace(BooleanTypes=SimpleNamespace(
                DifferenceBooleanType="difference"))))
        self.api = self.api_patch.start()
        self.addCleanup(self.api_patch.stop)
        self.cylinder_patch = patch.object(
            fusion, "_cylinder",
            side_effect=lambda manager, frame, start, end, radius, z: Body(
                kind="cutter" if radius > self.settings.barrel_diameter_mm / 2 else "nominal"))
        self.cylinder = self.cylinder_patch.start()
        self.addCleanup(self.cylinder_patch.stop)

    def cut(self, bodies=None, settings=None):
        return relief.cut_rotation_relief(
            self.manager, self.frame,
            bodies if bodies is not None else {"A": Body()},
            settings or self.settings)

    def test_cuts_only_supplied_temporary_copies_and_leaves_originals_unchanged(self):
        original = Body(10, temporary=False, kind="source")
        copied = self.manager.copy(original)
        markers = self.cut({"A": copied})
        self.assertEqual(original.volume, 10)
        self.assertFalse(original.isTemporary)
        self.assertEqual(copied.volume, 8)
        self.assertEqual(len(markers), 1)
        role, removal = markers[0]
        self.assertEqual(role, "clearance")
        self.assertIsNot(removal, original)
        self.assertIsNot(removal, copied)
        self.assertEqual(removal.volume, 2)
        self.assertTrue(removal.isTemporary)
        self.assertTrue(all(target.isTemporary for target, _, _ in self.manager.calls))
        self.measure.assert_called_once()
        self.assertIs(self.measure.call_args.args[0], copied)

    def test_cutter_uses_mm_envelope_and_nominal_housing_is_measured_separately(self):
        self.cut()
        first, second = self.cylinder.call_args_list
        self.assertEqual(first.args, (self.manager, self.frame, -20.3, 20.3, 4.3, 4))
        self.assertEqual(second.args, (self.manager, self.frame, -20, 20, 4, 4))

    def test_zero_legacy_setting_is_noop_without_body_reads_or_api_calls(self):
        source = Body(10, temporary=False)
        self.assertEqual(self.cut({"A": source},
                                  replace(self.settings, rotation_clearance_mm=0)), ())
        self.api.assert_not_called()
        self.cylinder.assert_not_called()
        self.assertEqual(self.manager.calls, [])
        self.assertEqual(self.manager.copies, [])
        self.assertEqual(source.volume, 10)

    def test_persisted_bodies_are_rejected_before_any_boolean_or_copy(self):
        source = Body(10, temporary=False)
        with self.assertRaisesRegex(fusion.HingeGeometryError, "temporary copies only"):
            self.cut({"A": source})
        self.assertEqual(source.volume, 10)
        self.assertEqual(self.manager.calls, [])
        self.assertEqual(self.manager.copies, [])

    def test_already_clear_separate_leaf_may_remain_unchanged_without_marker(self):
        self.manager.remove_volume = 0
        leaf = Body()
        result = self.cut({"B": leaf}, replace(self.settings, output_mode="separate"))
        self.assertEqual(result, ())
        self.assertEqual(leaf.volume, 10)
        self.assertEqual(len(self.manager.calls), 1)
        self.measure.assert_called_once()

    def test_invalid_copy_boolean_failure_split_or_erased_source_are_rejected(self):
        for flag in ("fail_copy", "fail_cut", "split_cut", "invalid_cut"):
            with self.subTest(flag=flag):
                self.manager = Manager()
                setattr(self.manager, flag, True)
                with self.assertRaises(fusion.HingeGeometryError):
                    self.cut()
        for volume in (0, -1, math.nan, math.inf, 11):
            with self.subTest(after_volume=volume):
                self.manager = Manager()
                self.manager.after_volume = volume
                with self.assertRaisesRegex(fusion.HingeGeometryError, "volume"):
                    self.cut()

    def test_bad_initial_volumes_are_rejected_before_cutting(self):
        for volume in (0, -1, math.nan, math.inf):
            with self.subTest(volume=volume):
                self.manager = Manager()
                with self.assertRaisesRegex(fusion.HingeGeometryError, "positive finite"):
                    self.cut({"A": Body(volume)})
                self.assertEqual(self.manager.calls, [])

    def test_unchanged_volume_is_not_accepted_when_requested_gap_is_missing(self):
        self.manager.remove_volume = 0
        self.measure.return_value = SimpleNamespace(value=0)
        with self.assertRaisesRegex(fusion.HingeGeometryError, "requested.*gap"):
            self.cut()

    def test_missing_nonfinite_or_insufficient_measurements_are_rejected(self):
        for measured in (None, SimpleNamespace(value=math.nan),
                         SimpleNamespace(value=math.inf), SimpleNamespace(value=-.01),
                         SimpleNamespace(value=.02)):
            with self.subTest(measured=measured):
                self.manager = Manager()
                self.measure.return_value = measured
                with self.assertRaisesRegex(fusion.HingeGeometryError, "requested.*gap"):
                    self.cut()

    def test_measurement_failure_is_wrapped_with_original_cause(self):
        cause = RuntimeError("Native measurement unavailable")
        self.measure.side_effect = cause
        with self.assertRaisesRegex(fusion.HingeGeometryError, "could not verify") as raised:
            self.cut()
        self.assertIs(raised.exception.__cause__, cause)

    def test_failed_or_nonpositive_removal_markers_are_rejected(self):
        self.manager.fail_marker = True
        with self.assertRaisesRegex(fusion.HingeGeometryError, "display"):
            self.cut()
        for volume in (0, -1, math.nan):
            with self.subTest(marker_volume=volume):
                self.manager = Manager()
                self.manager.marker_volume = volume
                with self.assertRaisesRegex(fusion.HingeGeometryError, "removal is invalid"):
                    self.cut()

    def test_each_changed_copy_gets_its_own_marker_and_model_objects_stay_untouched(self):
        source_a, source_b = Body(10, temporary=False), Body(20, temporary=False)
        copies = {"A": self.manager.copy(source_a), "B": self.manager.copy(source_b)}
        markers = self.cut(copies)
        self.assertEqual(len(markers), 2)
        self.assertEqual([role for role, _ in markers], ["clearance", "clearance"])
        self.assertTrue(all(body.volume == 2 for _, body in markers))
        self.assertEqual((source_a.volume, source_b.volume), (10, 20))
        self.assertEqual(self.measure.call_count, 2)


if __name__ == "__main__":
    unittest.main()

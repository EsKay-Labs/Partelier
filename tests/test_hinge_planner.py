"""Geometry invariants and recipe contracts, runnable without Autodesk Fusion."""

from dataclasses import FrozenInstanceError, fields, replace
import json
import math
import unittest

from Partelier.partelier.tools.hinge import HingeSettings, build_hinge_plan


class HingeSettingsTests(unittest.TestCase):
    def test_defaults_have_a_positive_barrel_wall_and_diametral_clearance(self):
        plan = build_hinge_plan(HingeSettings())
        self.assertAlmostEqual(plan.bore_radius_mm, 1.65)
        self.assertAlmostEqual(2 * plan.bore_radius_mm - plan.settings.pin_diameter_mm, 0.3)
        self.assertGreater(plan.barrel_radius_mm - plan.bore_radius_mm, 0)

    def test_every_length_rejects_nonfinite_nonpositive_and_nonnumeric_input(self):
        for field in fields(HingeSettings):
            if not field.name.endswith("_mm") or field.name in {"start_margin_mm", "end_margin_mm", "rotation_clearance_mm"}:
                continue
            for value in (0, -0.1, math.inf, -math.inf, math.nan, True, "4", None, 10 ** 1000):
                with self.subTest(field=field.name, value=repr(value)), self.assertRaises(ValueError):
                    HingeSettings(**{field.name: value})

    def test_hinge_count_is_a_bounded_integer(self):
        self.assertEqual(HingeSettings().hinge_count, 1)
        for value in (1, 2, 20):
            self.assertEqual(HingeSettings(hinge_count=value).hinge_count, value)
        for value in (0, -1, 21, 1.0, True, "2", None):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, "Hinge count"):
                HingeSettings(hinge_count=value)

    def test_layout_margins_are_nonnegative_finite_mm(self):
        for name in ("start_margin_mm", "end_margin_mm"):
            self.assertEqual(getattr(HingeSettings(), name), 0.0)
            for value in (0, 0.1, 8):
                self.assertEqual(getattr(HingeSettings(**{name: value}), name), float(value))
            for value in (-0.1, math.inf, -math.inf, math.nan, True, "4", None, 10 ** 1000):
                with self.subTest(name=name, value=repr(value)), self.assertRaisesRegex(ValueError, "nonnegative"):
                    HingeSettings(**{name: value})

    def test_layout_settings_round_trip_and_are_required_in_recipes(self):
        settings = HingeSettings(hinge_count=3, start_margin_mm=5, end_margin_mm=9)
        recipe = json.loads(json.dumps(settings.to_dict()))
        self.assertEqual(HingeSettings.from_dict(recipe), settings)
        for name in ("hinge_count", "start_margin_mm", "end_margin_mm"):
            incomplete = dict(recipe)
            del incomplete[name]
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, "exactly"):
                HingeSettings.from_dict(incomplete)

    def test_knuckle_count_bounds_work_and_keep_owner_a_at_both_ends(self):
        for value in (0, 1, 2, 4, 16, 17, 5.0, True, "5", None):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, "odd integer"):
                HingeSettings(knuckle_count=value)
        for count in range(3, 16, 2):
            plan = build_hinge_plan(HingeSettings(knuckle_count=count))
            self.assertEqual(len(plan.knuckles), count)
            self.assertEqual(plan.knuckles[0].owner, "A")
            self.assertEqual(plan.knuckles[-1].owner, "A")

    def test_include_pin_is_a_boolean(self):
        for value in (0, 1, "true", None):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, "Include pin"):
                HingeSettings(include_pin=value)
        self.assertFalse(HingeSettings(include_pin=False).include_pin)

    def test_split_seam_defaults_to_off_and_requires_a_boolean(self):
        settings = HingeSettings()
        self.assertFalse(settings.split_seam)
        self.assertEqual(settings.seam_clearance_mm, 0.3)
        for value in (0, 1, "true", None):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, "Split seam"):
                HingeSettings(split_seam=value)
        self.assertTrue(HingeSettings(split_seam=True).split_seam)

    def test_split_clearance_leaves_room_for_attachment(self):
        for clearance in (24, 24.1, 100):
            with self.subTest(clearance=clearance), self.assertRaisesRegex(ValueError, "twice the leaf reach"):
                HingeSettings(split_seam=True, seam_clearance_mm=clearance)
        self.assertEqual(HingeSettings(split_seam=True, seam_clearance_mm=23.9).seam_clearance_mm, 23.9)
        # The unused setting does not constrain the pre-existing separated-body workflow.
        self.assertEqual(HingeSettings(split_seam=False, seam_clearance_mm=100).seam_clearance_mm, 100)
        # Axis offset remains a positive input even though split placement ignores it.
        with self.assertRaisesRegex(ValueError, "Axis offset"):
            HingeSettings(split_seam=True, axis_offset_mm=0)

    def test_seam_clearance_round_trips_and_current_recipe_fields_are_required(self):
        settings = HingeSettings(split_seam=True, seam_clearance_mm=0.45)
        values = json.loads(json.dumps(settings.to_dict()))
        self.assertEqual(HingeSettings.from_dict(values), settings)
        for field in ("split_seam", "seam_clearance_mm"):
            incomplete = dict(values)
            del incomplete[field]
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, "exactly"):
                HingeSettings.from_dict(incomplete)

    def test_bore_and_web_cannot_consume_the_barrel(self):
        invalid = (
            {"pin_diameter_mm": 7.7},
            {"diametral_clearance_mm": 5.0},
            {"leaf_thickness_mm": 2.35},
            {"leaf_thickness_mm": 3.0},
            {"leaf_thickness_mm": 0.1},
            {"leaf_reach_mm": 4.0},
        )
        for values in invalid:
            with self.subTest(values=values), self.assertRaises(ValueError):
                HingeSettings(**values)

    def test_gaps_cannot_consume_the_length(self):
        for length in (1.2, 1.0):
            with self.subTest(length=length), self.assertRaisesRegex(ValueError, "total axial gaps"):
                HingeSettings(length_mm=length)

    def test_finite_inputs_that_overflow_or_erase_gaps_are_rejected(self):
        for values in (
            {"length_mm": 1e308, "pin_overhang_mm": 1.7e308},
            {"length_mm": 1e308},
            {"axial_gap_mm": 1e308},
            {"pin_diameter_mm": 1e308, "diametral_clearance_mm": 1e308},
            {"pin_diameter_mm": 10 ** 308, "diametral_clearance_mm": 10 ** 308},
            {"diametral_clearance_mm": 5e-324},
        ):
            with self.subTest(values=values), self.assertRaises(ValueError):
                HingeSettings(**values)

    def test_recipe_round_trips_through_json_and_is_strict(self):
        original = HingeSettings(knuckle_count=7, include_pin=False)
        recipe = json.loads(json.dumps(original.to_dict()))
        self.assertEqual(HingeSettings.from_dict(recipe), original)
        for invalid in (None, [], {}, {**recipe, "unexpected": 1}):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                HingeSettings.from_dict(invalid)
        del recipe["axis_offset_mm"]
        with self.assertRaises(ValueError):
            HingeSettings.from_dict(recipe)

    def test_settings_are_immutable(self):
        settings = HingeSettings()
        with self.assertRaises(FrozenInstanceError):
            settings.length_mm = 50


class HingePlanTests(unittest.TestCase):
    def test_knuckles_fill_length_with_exactly_the_requested_separation(self):
        for count in range(3, 16, 2):
            for length, gap in ((40.0, 0.3), (11.2, 0.07), (600.0, 2.5)):
                settings = HingeSettings(length_mm=length, knuckle_count=count, axial_gap_mm=gap)
                plan = build_hinge_plan(settings)
                self.assertEqual(plan.knuckles[0].start_mm, -length / 2)
                self.assertEqual(plan.knuckles[-1].end_mm, length / 2)
                self.assertAlmostEqual(sum(k.length_mm for k in plan.knuckles) + gap * (count - 1), length)
                for index, knuckle in enumerate(plan.knuckles):
                    self.assertGreater(knuckle.length_mm, 0)
                    self.assertAlmostEqual(knuckle.length_mm, plan.knuckles[0].length_mm)
                    if index:
                        previous = plan.knuckles[index - 1]
                        self.assertNotEqual(knuckle.owner, previous.owner)
                        self.assertAlmostEqual(knuckle.start_mm - previous.end_mm, gap)

    def test_webs_attach_to_their_knuckles_and_leave_the_bore_open(self):
        plan = build_hinge_plan(HingeSettings())
        for knuckle, web in zip(plan.knuckles, plan.webs):
            self.assertEqual(web.owner, knuckle.owner)
            self.assertEqual((web.y_min_mm, web.y_max_mm), (knuckle.start_mm, knuckle.end_mm))
            self.assertLess(web.x_min_mm, web.x_max_mm)
            self.assertLess(web.z_min_mm, 0)
            self.assertGreater(web.z_max_mm, 0)
            self.assertLess(web.z_max_mm, plan.barrel_radius_mm - plan.bore_radius_mm)
            if web.owner == "A":
                self.assertLess(web.x_max_mm, 0)
                closest_x = web.x_max_mm
            else:
                self.assertGreater(web.x_min_mm, 0)
                closest_x = web.x_min_mm
            # A web must overlap the outside cylinder, not merely touch it.
            radius_squared = closest_x ** 2 + (web.z_max_mm - plan.barrel_radius_mm) ** 2
            self.assertLess(radius_squared, plan.barrel_radius_mm ** 2)

    def test_separate_filleted_support_uses_a_hole_safe_neck_without_changing_dimensions(self):
        settings = HingeSettings(output_mode="separate", screw_holes=True,
                                 web_profile="tangent", fillet_edges=True)
        plan = build_hinge_plan(settings)
        inner = plan.barrel_radius_mm + settings.leaf_barrel_clearance_mm
        overlap = abs(plan.webs[0].x_min_mm) - inner
        self.assertGreater(overlap, 2 * settings.fillet_radius_mm)
        for web in plan.webs:
            reach = abs(web.x_min_mm) if web.owner == "A" else web.x_max_mm
            hole = next(hole for hole in plan.mounting_holes if hole.owner == web.owner)
            lip = abs(hole.x_mm) - hole.diameter_mm / 2 - settings.fillet_radius_mm
            self.assertLess(reach, lip)
        self.assertEqual(plan.settings, settings)
        self.assertEqual(plan.plates[0].x_min_mm, -settings.leaf_reach_mm)
        self.assertEqual(plan.plates[0].z_max_mm, settings.leaf_thickness_mm)

    def test_pin_extends_beyond_both_ends(self):
        settings = HingeSettings(pin_overhang_mm=1.7)
        plan = build_hinge_plan(settings)
        self.assertAlmostEqual(-settings.length_mm / 2 - plan.pin_start_mm, 1.7)
        self.assertAlmostEqual(plan.pin_end_mm - settings.length_mm / 2, 1.7)

    def test_dimensions_scale_without_a_printer_specific_minimum(self):
        original = HingeSettings()
        for scale in (0.01, 100.0):
            values = original.to_dict()
            values.update({name: value * scale for name, value in values.items() if name.endswith("_mm")})
            plan = build_hinge_plan(HingeSettings.from_dict(values))
            self.assertAlmostEqual(plan.barrel_radius_mm, 4 * scale)
            self.assertAlmostEqual(plan.pin_end_mm, 22 * scale)
            self.assertEqual(len(plan.knuckles), 5)

    def test_split_mode_keeps_the_same_pure_hinge_shape(self):
        normal = build_hinge_plan(HingeSettings())
        split = build_hinge_plan(HingeSettings(split_seam=True, seam_clearance_mm=0.45))
        for field in ("knuckles", "webs", "barrel_radius_mm", "bore_radius_mm", "pin_start_mm", "pin_end_mm"):
            with self.subTest(field=field):
                self.assertEqual(getattr(normal, field), getattr(split, field))
        self.assertTrue(split.settings.split_seam)
        self.assertEqual(split.settings.seam_clearance_mm, 0.45)

    def test_repetition_changes_placement_settings_without_changing_unit_geometry(self):
        single = build_hinge_plan(HingeSettings())
        repeated = build_hinge_plan(HingeSettings(hinge_count=3, start_margin_mm=6, end_margin_mm=9))
        for name in ("knuckles", "webs", "barrel_radius_mm", "bore_radius_mm", "pin_start_mm", "pin_end_mm"):
            with self.subTest(name=name):
                self.assertEqual(getattr(single, name), getattr(repeated, name))
        self.assertEqual(repeated.settings.length_mm, 40)
        self.assertEqual(repeated.settings.hinge_count, 3)

    def test_planner_has_no_state_and_returns_immutable_results(self):
        settings = HingeSettings()
        first = build_hinge_plan(settings)
        second = build_hinge_plan(settings)
        self.assertEqual(first, second)
        self.assertIsInstance(first.knuckles, tuple)
        self.assertIsInstance(first.webs, tuple)
        with self.assertRaises(FrozenInstanceError):
            first.knuckles[0].owner = "B"
        changed = build_hinge_plan(replace(settings, length_mm=50))
        self.assertNotEqual(first, changed)
        self.assertEqual(first.settings.length_mm, 40)

    def test_raw_settings_are_not_silently_accepted(self):
        with self.assertRaisesRegex(ValueError, "HingeSettings"):
            build_hinge_plan(HingeSettings().to_dict())


if __name__ == "__main__":
    unittest.main()

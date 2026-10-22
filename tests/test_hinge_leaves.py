"""Separate mounting leaves and through-hole bounds, without Autodesk APIs."""

from dataclasses import FrozenInstanceError, replace
import json
import math
import unittest

from Partelier.partelier.tools.hinge.planner import build_hinge_plan
from Partelier.partelier.tools.hinge.settings import HingeSettings


class SeparateLeafSettingsTests(unittest.TestCase):
    def test_defaults_preserve_attached_output(self):
        settings = HingeSettings()
        self.assertEqual(settings.output_mode, "attached")
        self.assertEqual(settings.leaf_profile, "rectangular")
        self.assertEqual(settings.leaf_barrel_clearance_mm, 0.3)
        self.assertFalse(settings.screw_holes)
        self.assertEqual(settings.screw_diameter_mm, 3.2)
        self.assertEqual(settings.screw_end_margin_mm, 6.0)

    def test_modes_and_profiles_use_exact_supported_strings(self):
        for field, accepted in (("output_mode", ("attached", "separate")),
                                ("leaf_profile", ("rectangular", "rounded"))):
            for value in accepted:
                self.assertEqual(getattr(HingeSettings(**{field: value}), field), value)
            for value in (None, True, 1, "", "other", accepted[0].upper(), [], {}):
                with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                    HingeSettings(**{field: value})

    def test_screw_toggle_is_always_strictly_boolean(self):
        for value in (0, 1, "true", None):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, "Screw holes"):
                HingeSettings(screw_holes=value)

    def test_separate_leaf_must_have_positive_plate_and_web_overlap(self):
        for reach in (4.2, 4.3):
            with self.subTest(reach=reach), self.assertRaisesRegex(ValueError, "Separate leaf reach"):
                HingeSettings(output_mode="separate", leaf_reach_mm=reach)
        self.assertEqual(HingeSettings(output_mode="separate", leaf_reach_mm=4.4).leaf_reach_mm, 4.4)

    def test_holes_require_positive_side_material(self):
        for diameter in (4, 4.1, 100):
            with self.subTest(diameter=diameter), self.assertRaisesRegex(ValueError, "both sides"):
                HingeSettings(output_mode="separate", leaf_barrel_clearance_mm=0.5,
                              leaf_reach_mm=8.5, screw_holes=True, screw_diameter_mm=diameter)
        HingeSettings(output_mode="separate", leaf_barrel_clearance_mm=0.5,
                      leaf_reach_mm=8.5, screw_holes=True, screw_diameter_mm=3.9)

    def test_holes_require_positive_end_and_between_hole_material(self):
        for margin in (1, 2, 18, 19, 40):
            with self.subTest(margin=margin), self.assertRaisesRegex(ValueError, "Screw end margin"):
                HingeSettings(output_mode="separate", screw_holes=True,
                              screw_diameter_mm=4, screw_end_margin_mm=margin)
        for margin in (2.1, 17.9):
            HingeSettings(output_mode="separate", screw_holes=True,
                          screw_diameter_mm=4, screw_end_margin_mm=margin)

    def test_inactive_leaf_and_screw_dimensions_do_not_constrain_attached_geometry(self):
        original = build_hinge_plan(HingeSettings())
        inactive = build_hinge_plan(HingeSettings(
            leaf_profile="rounded", leaf_barrel_clearance_mm=1000,
            screw_holes=True, screw_diameter_mm=1000, screw_end_margin_mm=1000,
        ))
        for name in ("knuckles", "webs", "barrel_radius_mm", "bore_radius_mm", "pin_start_mm", "pin_end_mm"):
            self.assertEqual(getattr(original, name), getattr(inactive, name))
        self.assertEqual(inactive.plates, ())
        self.assertEqual(inactive.mounting_holes, ())

    def test_separate_auto_centred_seam_ignores_inactive_attached_clearance(self):
        settings = HingeSettings(output_mode="separate", split_seam=True, seam_clearance_mm=1000)
        self.assertTrue(settings.split_seam)
        self.assertEqual(settings.seam_clearance_mm, 1000)
        normal = build_hinge_plan(HingeSettings(output_mode="separate"))
        inactive = build_hinge_plan(settings)
        self.assertEqual(normal.plates, inactive.plates)
        self.assertEqual(normal.webs, inactive.webs)
        with self.assertRaisesRegex(ValueError, "twice the leaf reach"):
            HingeSettings(output_mode="attached", split_seam=True, seam_clearance_mm=1000)

    def test_v4_leaf_fields_round_trip_and_are_required_in_complete_recipes(self):
        settings = HingeSettings(output_mode="separate", leaf_profile="rounded", screw_holes=True)
        values = json.loads(json.dumps(settings.to_dict()))
        self.assertEqual(HingeSettings.from_dict(values), settings)
        for name in ("output_mode", "leaf_profile", "leaf_barrel_clearance_mm", "screw_holes",
                     "screw_diameter_mm", "screw_end_margin_mm"):
            incomplete = dict(values)
            del incomplete[name]
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, "exactly"):
                HingeSettings.from_dict(incomplete)


class SeparateLeafPlanTests(unittest.TestCase):
    def test_separate_plates_span_each_unit_and_stay_outside_every_barrel(self):
        settings = HingeSettings(output_mode="separate")
        plan = build_hinge_plan(settings)
        self.assertEqual([plate.owner for plate in plan.plates], ["A", "B"])
        inner = plan.barrel_radius_mm + settings.leaf_barrel_clearance_mm
        for plate in plan.plates:
            self.assertEqual((plate.y_min_mm, plate.y_max_mm), (-20, 20))
            self.assertEqual((plate.z_min_mm, plate.z_max_mm), (0, 2))
            self.assertEqual(plate.corner_radius_mm, 0)
            if plate.owner == "A":
                self.assertEqual((plate.x_min_mm, plate.x_max_mm), (-12, -inner))
            else:
                self.assertEqual((plate.x_min_mm, plate.x_max_mm), (inner, 12))
            # Every point of the plate has |X| >= R + the explicit leaf clearance.
            self.assertGreaterEqual(min(abs(plate.x_min_mm), abs(plate.x_max_mm)), inner)
        self.assertEqual(plan.mounting_holes, ())

    def test_short_webs_join_own_plate_and_barrel_without_filling_free_corners(self):
        settings = HingeSettings(output_mode="separate", leaf_profile="rounded")
        plan = build_hinge_plan(settings)
        plates = {plate.owner: plate for plate in plan.plates}
        for web in plan.webs:
            plate = plates[web.owner]
            self.assertEqual((web.z_min_mm, web.z_max_mm), (0, settings.leaf_thickness_mm))
            self.assertGreater(min(web.x_max_mm, plate.x_max_mm) - max(web.x_min_mm, plate.x_min_mm), 0)
            self.assertGreater(min(web.y_max_mm, plate.y_max_mm) - max(web.y_min_mm, plate.y_min_mm), 0)
            if web.owner == "A":
                self.assertGreater(web.x_min_mm, plate.x_min_mm + plate.corner_radius_mm)
                closest_x = web.x_max_mm
            else:
                self.assertLess(web.x_max_mm, plate.x_max_mm - plate.corner_radius_mm)
                closest_x = web.x_min_mm
            self.assertLess(closest_x ** 2 + (web.z_max_mm - plan.barrel_radius_mm) ** 2,
                            plan.barrel_radius_mm ** 2)

    def test_rounded_profile_derives_a_bounded_outer_corner_radius(self):
        settings = HingeSettings(output_mode="separate", leaf_profile="rounded")
        plan = build_hinge_plan(settings)
        for plate in plan.plates:
            width = plate.x_max_mm - plate.x_min_mm
            self.assertEqual(plate.corner_radius_mm, min(width / 4, settings.length_mm / 8,
                                                       settings.leaf_thickness_mm / 2))
            self.assertGreater(plate.corner_radius_mm, 0)
            self.assertLess(plate.corner_radius_mm, width / 2)

    def test_four_through_holes_use_mid_width_and_requested_end_setback(self):
        settings = HingeSettings(output_mode="separate", screw_holes=True)
        plan = build_hinge_plan(settings)
        self.assertEqual(len(plan.mounting_holes), 4)
        for plate in plan.plates:
            holes = [hole for hole in plan.mounting_holes if hole.owner == plate.owner]
            self.assertEqual(len(holes), 2)
            self.assertEqual([hole.y_mm for hole in holes], [-14, 14])
            for hole in holes:
                self.assertAlmostEqual(hole.x_mm, (plate.x_min_mm + plate.x_max_mm) / 2)
                self.assertEqual(hole.diameter_mm, 3.2)

    def test_hole_disks_remain_inside_straight_edges_and_rounded_free_corners(self):
        cases = (
            HingeSettings(output_mode="separate", leaf_profile="rounded", screw_holes=True),
            HingeSettings(output_mode="separate", leaf_profile="rounded", screw_holes=True,
                          length_mm=20, leaf_reach_mm=10, screw_end_margin_mm=4),
            HingeSettings(output_mode="separate", leaf_profile="rounded", screw_holes=True,
                          leaf_barrel_clearance_mm=0.15, leaf_reach_mm=7.5),
        )
        for settings in cases:
            plan = build_hinge_plan(settings)
            for plate in plan.plates:
                for hole in (h for h in plan.mounting_holes if h.owner == plate.owner):
                    radius = hole.diameter_mm / 2
                    self.assertGreater(hole.x_mm - radius, plate.x_min_mm)
                    self.assertLess(hole.x_mm + radius, plate.x_max_mm)
                    self.assertGreater(hole.y_mm - radius, plate.y_min_mm)
                    self.assertLess(hole.y_mm + radius, plate.y_max_mm)
                    corner_r = plate.corner_radius_mm
                    sign = -1 if plate.owner == "A" else 1
                    outer = plate.x_min_mm if sign == -1 else plate.x_max_mm
                    corner_x = outer - sign * corner_r
                    for end_sign in (-1, 1):
                        corner_y = end_sign * (settings.length_mm / 2 - corner_r)
                        for step in range(65):
                            angle = step * math.pi / 128
                            boundary_x = corner_x + sign * corner_r * math.cos(angle)
                            boundary_y = corner_y + end_sign * corner_r * math.sin(angle)
                            distance = math.hypot(boundary_x - hole.x_mm, boundary_y - hole.y_mm)
                            self.assertGreater(distance, radius)

    def test_count_and_layout_margins_do_not_change_separate_unit_shape(self):
        settings = HingeSettings(output_mode="separate", screw_holes=True, leaf_profile="rounded")
        original = build_hinge_plan(settings)
        repeated = build_hinge_plan(replace(settings, hinge_count=3, start_margin_mm=5, end_margin_mm=8))
        self.assertEqual(original.plates, repeated.plates)
        self.assertEqual(original.mounting_holes, repeated.mounting_holes)
        self.assertEqual(original.webs, repeated.webs)

    def test_leaf_records_are_immutable_and_attachment_overlap_is_inactive(self):
        settings = HingeSettings(output_mode="separate", screw_holes=True)
        plan = build_hinge_plan(settings)
        with self.assertRaises(FrozenInstanceError):
            plan.plates[0].x_min_mm = 0
        with self.assertRaises(FrozenInstanceError):
            plan.mounting_holes[0].diameter_mm = 5
        changed = build_hinge_plan(replace(settings, attachment_overlap_mm=9))
        self.assertEqual(plan.webs, changed.webs)
        self.assertEqual(plan.plates, changed.plates)

    def test_separate_geometry_scales_with_dimensions(self):
        original = HingeSettings(output_mode="separate", screw_holes=True, leaf_profile="rounded")
        baseline = build_hinge_plan(original)
        for scale in (0.01, 100):
            values = original.to_dict()
            values.update({name: value * scale for name, value in values.items() if name.endswith("_mm")})
            scaled = build_hinge_plan(HingeSettings.from_dict(values))
            for base, current in zip(baseline.plates, scaled.plates):
                self.assertAlmostEqual(current.corner_radius_mm, base.corner_radius_mm * scale)
                self.assertAlmostEqual(current.x_max_mm, base.x_max_mm * scale)
            for base, current in zip(baseline.mounting_holes, scaled.mounting_holes):
                self.assertAlmostEqual(current.x_mm, base.x_mm * scale)
                self.assertAlmostEqual(current.y_mm, base.y_mm * scale)
                self.assertAlmostEqual(current.diameter_mm, base.diameter_mm * scale)


if __name__ == "__main__":
    unittest.main()

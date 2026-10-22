"""Dimension and placement checks for a geometry-only exterior clasp plan."""

from dataclasses import FrozenInstanceError
import math
import unittest

from Partelier.partelier.tools.snap_fit.planner import build_snap_fit_plan
from Partelier.partelier.tools.snap_fit.settings import SnapFitSettings


def box_volume(bounds):
    return ((bounds.x_max_mm - bounds.x_min_mm)
            * (bounds.y_max_mm - bounds.y_min_mm)
            * (bounds.z_max_mm - bounds.z_min_mm))


def polygon_area(points):
    return abs(sum(a[0] * b[1] - b[0] * a[1]
                   for a, b in zip(points, points[1:] + points[:1]))) / 2.0


class SnapFitPlannerTests(unittest.TestCase):
    def test_single_default_is_centered_and_deterministic(self):
        settings = SnapFitSettings()
        plan = build_snap_fit_plan(settings, 60)
        self.assertEqual(plan, build_snap_fit_plan(settings, 60))
        self.assertIs(plan.settings, settings)
        self.assertEqual(plan.span_mm, 60.0)
        self.assertEqual(len(plan.units), 1)
        self.assertEqual(plan.units[0].center_y_mm, 0)

    def test_root_joins_selected_body_below_rim_and_overlaps_beam(self):
        unit = build_snap_fit_plan(SnapFitSettings(), 60).units[0]
        self.assertEqual((unit.root.x_min_mm, unit.root.x_max_mm), (-.5, 1.8))
        self.assertEqual((unit.root.z_min_mm, unit.root.z_max_mm), (-4, 0))
        self.assertEqual((unit.beam.x_min_mm, unit.beam.x_max_mm), (.3, 1.8))
        self.assertEqual((unit.beam.z_min_mm, unit.beam.z_max_mm), (-4, 16))
        self.assertGreater(min(unit.root.x_max_mm, unit.beam.x_max_mm)
                           - max(unit.root.x_min_mm, unit.beam.x_min_mm), 0)
        self.assertGreater(min(unit.root.z_max_mm, unit.beam.z_max_mm)
                           - max(unit.root.z_min_mm, unit.beam.z_min_mm), 0)

    def test_hook_has_exact_engagement_shoulder_lead_in_and_positive_beam_overlap(self):
        settings = SnapFitSettings()
        unit = build_snap_fit_plan(settings, 60).units[0]
        self.assertEqual(unit.hook.points_xz_mm,
                         ((-1, 13), (1.8, 13), (1.8, 16), (.3, 16)))
        self.assertGreater(polygon_area(unit.hook.points_xz_mm), 0)
        self.assertGreater(unit.beam.x_max_mm - settings.clearance_mm, 0)
        self.assertEqual((unit.hook.y_min_mm, unit.hook.y_max_mm), (-4, 4))

    def test_receiving_pocket_contains_hook_with_clearance_on_every_cut_boundary(self):
        settings = SnapFitSettings()
        unit = build_snap_fit_plan(settings, 60).units[0]
        pocket = unit.receiver
        hook = unit.hook
        self.assertAlmostEqual(pocket.x_min_mm, -1.3)
        self.assertAlmostEqual(pocket.x_max_mm, 2.1)
        self.assertAlmostEqual(pocket.z_min_mm, 12.7)
        self.assertAlmostEqual(pocket.z_max_mm, 16.3)
        self.assertAlmostEqual(hook.y_min_mm - pocket.y_min_mm, settings.clearance_mm)
        self.assertAlmostEqual(pocket.y_max_mm - hook.y_max_mm, settings.clearance_mm)
        for x, z in hook.points_xz_mm:
            self.assertLess(pocket.x_min_mm, x)
            self.assertLess(x, pocket.x_max_mm)
            self.assertLess(pocket.z_min_mm, z)
            self.assertLess(z, pocket.z_max_mm)
        self.assertGreater(pocket.z_min_mm, 0)

    def test_every_generated_box_has_positive_volume(self):
        plan = build_snap_fit_plan(SnapFitSettings(snap_count=4), 100)
        for index, unit in enumerate(plan.units):
            for name in ("root", "beam", "receiver"):
                with self.subTest(index=index, name=name):
                    self.assertGreater(box_volume(getattr(unit, name)), 0)

    def test_asymmetric_margins_shift_one_center_instead_of_changing_dimensions(self):
        settings = SnapFitSettings(start_margin_mm=11, end_margin_mm=3)
        unit = build_snap_fit_plan(settings, 60).units[0]
        self.assertAlmostEqual(unit.center_y_mm, 4)
        self.assertAlmostEqual(unit.beam.y_max_mm - unit.beam.y_min_mm, 8)
        self.assertAlmostEqual(unit.receiver.y_max_mm - unit.receiver.y_min_mm, 8.6)

    def test_repeat_centers_are_equal_with_receiver_edge_margins(self):
        settings = SnapFitSettings(snap_count=4, start_margin_mm=7, end_margin_mm=9)
        plan = build_snap_fit_plan(settings, 100)
        units = plan.units
        self.assertAlmostEqual(units[0].receiver.y_min_mm, -50 + 7)
        self.assertAlmostEqual(units[-1].receiver.y_max_mm, 50 - 9)
        differences = [b.center_y_mm - a.center_y_mm for a, b in zip(units, units[1:])]
        for difference in differences[1:]:
            self.assertAlmostEqual(difference, differences[0])
        for a, b in zip(units, units[1:]):
            self.assertGreater(b.receiver.y_min_mm, a.receiver.y_max_mm)

    def test_symmetric_pair_matches_reflection_about_rim_midpoint(self):
        units = build_snap_fit_plan(SnapFitSettings(snap_count=2), 60).units
        self.assertAlmostEqual(units[0].center_y_mm, -units[1].center_y_mm)
        self.assertAlmostEqual(units[0].hook.y_min_mm, -units[1].hook.y_max_mm)

    def test_count_limit_twenty_is_not_silently_reduced(self):
        plan = build_snap_fit_plan(SnapFitSettings(snap_count=20), 300)
        self.assertEqual(len(plan.units), 20)

    def test_overlapping_or_touching_neighbor_receivers_are_refused(self):
        settings = SnapFitSettings(width_mm=8, clearance_mm=.5, snap_count=2,
                                   start_margin_mm=0, end_margin_mm=0)
        for span in (9, 17, 18):
            with self.subTest(span=span), self.assertRaisesRegex(ValueError, "positive gap"):
                build_snap_fit_plan(settings, span)
        self.assertEqual(len(build_snap_fit_plan(settings, 18.01).units), 2)

    def test_single_exact_fit_is_allowed_without_neighbor_collision(self):
        settings = SnapFitSettings(width_mm=8, clearance_mm=.5,
                                   start_margin_mm=0, end_margin_mm=0)
        unit = build_snap_fit_plan(settings, 9).units[0]
        self.assertEqual((unit.receiver.y_min_mm, unit.receiver.y_max_mm), (-4.5, 4.5))

    def test_short_rim_cannot_silently_reduce_width_or_margins(self):
        with self.assertRaisesRegex(ValueError, "too short"):
            build_snap_fit_plan(SnapFitSettings(), 18)
        self.assertEqual(SnapFitSettings().width_mm, 8)

    def test_nonsettings_and_invalid_span_are_refused(self):
        for settings in ({}, None, 5, "settings"):
            with self.subTest(settings=settings), self.assertRaisesRegex(ValueError, "SnapFitSettings"):
                build_snap_fit_plan(settings, 60)
        for span in (0, -1, math.inf, math.nan, True, "60", None, 10 ** 1000):
            with self.subTest(span=repr(span)[:30]), self.assertRaises(ValueError):
                build_snap_fit_plan(SnapFitSettings(), span)

    def test_huge_placement_that_erases_local_width_is_refused(self):
        settings = SnapFitSettings(snap_count=2)
        with self.assertRaisesRegex(ValueError, "distinct finite"):
            build_snap_fit_plan(settings, 1e308)

    def test_settings_and_plan_are_immutable(self):
        plan = build_snap_fit_plan(SnapFitSettings(), 60)
        with self.assertRaises(FrozenInstanceError):
            plan.units = ()
        with self.assertRaises(FrozenInstanceError):
            plan.units[0].beam.z_max_mm = 10

    def test_dimension_changes_keep_other_requested_dimensions(self):
        settings = SnapFitSettings(width_mm=10, thickness_mm=2, reach_mm=20,
                                   clearance_mm=.4, hook_depth_mm=1.5, lead_in_mm=4,
                                   root_length_mm=5, attachment_overlap_mm=.8)
        unit = build_snap_fit_plan(settings, 60).units[0]
        self.assertAlmostEqual(unit.beam.x_max_mm - unit.beam.x_min_mm, 2)
        self.assertEqual(unit.beam.z_max_mm, 20)
        self.assertEqual(unit.hook.points_xz_mm[0], (-1.5, 16))
        self.assertEqual(unit.root.x_min_mm, -.8)
        self.assertEqual(unit.root.z_min_mm, -5)


if __name__ == "__main__":
    unittest.main()

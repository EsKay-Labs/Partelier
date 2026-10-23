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
        settings = SnapFitSettings(chamfer_edges=False, print_support=False)
        unit = build_snap_fit_plan(settings, 60).units[0]
        pocket = unit.arms[0].receiver_bounds
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
        self.assertAlmostEqual(unit.arms[0].receiver_bounds.y_max_mm - unit.arms[0].receiver_bounds.y_min_mm, 8.6)

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
        settings = SnapFitSettings(width_mm=8, clearance_mm=.5, snap_count=2, chamfer_edges=False,
                                   start_margin_mm=0, end_margin_mm=0)
        for span in (9, 17, 18):
            with self.subTest(span=span), self.assertRaisesRegex(ValueError, "positive gap"):
                build_snap_fit_plan(settings, span)
        self.assertEqual(len(build_snap_fit_plan(settings, 18.01).units), 2)

    def test_single_exact_fit_is_allowed_without_neighbor_collision(self):
        settings = SnapFitSettings(width_mm=8, clearance_mm=.5, chamfer_edges=False,
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


    def test_tapered_beam_has_constant_width_and_sixty_five_percent_tip_thickness(self):
        settings = SnapFitSettings(snap_style="tapered")
        unit = build_snap_fit_plan(settings, 60).units[0]
        arm = unit.arms[0]
        tip = max(x for x, z in arm.beam.points_xz_mm if z == settings.reach_mm)
        self.assertAlmostEqual(tip - settings.clearance_mm, .65 * settings.thickness_mm)
        self.assertEqual(arm.beam.y_max_mm - arm.beam.y_min_mm, settings.width_mm)
        self.assertIn((settings.clearance_mm + settings.thickness_mm, 0), arm.beam.points_xz_mm)
        self.assertAlmostEqual(arm.hook.points_xz_mm[2][0], tip)
        self.assertEqual(arm.hook.points_xz_mm[0][0], -settings.hook_depth_mm)

    def test_twin_arms_and_two_recesses_have_a_positive_middle_web(self):
        settings = SnapFitSettings(snap_style="twin")
        unit = build_snap_fit_plan(settings, 60).units[0]
        left, right = unit.arms
        gap = max(settings.thickness_mm, 4 * settings.clearance_mm + .2)
        self.assertAlmostEqual(right.beam.y_min_mm - left.beam.y_max_mm, gap)
        self.assertAlmostEqual(left.beam.y_max_mm - left.beam.y_min_mm, (settings.width_mm - gap) / 2)
        self.assertGreater(right.receiver.y_min_mm - left.receiver.y_max_mm, 0)
        self.assertGreater(right.receiver_cover.y_min_mm - left.receiver_cover.y_max_mm, 0)
        self.assertEqual(unit.root.y_max_mm - unit.root.y_min_mm, settings.width_mm)

    def test_print_ramps_have_exact_45_degree_run_rise_and_preserve_retaining_shoulder(self):
        settings = SnapFitSettings()
        unit = build_snap_fit_plan(settings, 60).units[0]
        support = unit.root_support
        self.assertGreater(polygon_area(support.points_xz_mm), 0)
        first, second = support.points_xz_mm[:2]
        self.assertAlmostEqual(second[0] - first[0], second[1] - first[1])
        self.assertLess(unit.root_cover.z_min_mm, unit.root.z_min_mm)
        roof = unit.arms[0].receiver.points_xz_mm
        self.assertAlmostEqual(roof[2][1] - roof[3][1], roof[2][0] - roof[3][0])
        shoulder = settings.reach_mm - settings.lead_in_mm
        self.assertEqual(unit.arms[0].hook.points_xz_mm[0], (-settings.hook_depth_mm, shoulder))
        self.assertEqual(roof[0][1], shoulder - settings.clearance_mm)

    def test_print_support_off_restores_rectangular_pocket_and_original_root_coverage(self):
        settings = SnapFitSettings(print_support=False, chamfer_edges=False)
        unit = build_snap_fit_plan(settings, 60).units[0]
        self.assertIsNone(unit.root_support)
        self.assertEqual(unit.root_cover.z_min_mm, -settings.root_length_mm)
        roof = unit.arms[0].receiver.points_xz_mm
        self.assertEqual(roof[2][1], roof[3][1])
        self.assertEqual(unit.arms[0].receiver_cover.z_max_mm, settings.reach_mm + 2 * settings.clearance_mm)

    def test_finished_receiver_envelopes_preserve_requested_margins_and_neighbor_gaps(self):
        settings = SnapFitSettings(snap_count=3, start_margin_mm=6, end_margin_mm=9)
        units = build_snap_fit_plan(settings, 90).units
        first_cut_edge = min(arm.receiver.y_min_mm for arm in units[0].arms)
        last_cut_edge = max(arm.receiver.y_max_mm for arm in units[-1].arms)
        self.assertAlmostEqual(first_cut_edge, -45 + settings.start_margin_mm)
        self.assertAlmostEqual(last_cut_edge, 45 - settings.end_margin_mm)
        for first, last in zip(units, units[1:]):
            first_end = max(arm.receiver.y_max_mm for arm in first.arms)
            last_start = min(arm.receiver.y_min_mm for arm in last.arms)
            self.assertGreater(last_start, first_end)
        with self.assertRaisesRegex(ValueError, "positive gap"):
            build_snap_fit_plan(SnapFitSettings(snap_count=2, start_margin_mm=0, end_margin_mm=0), 17.2)


if __name__ == "__main__":
    unittest.main()

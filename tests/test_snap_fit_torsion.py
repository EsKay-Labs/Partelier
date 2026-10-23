"""Torsion-bar latch planning and temporary-solid API boundaries."""

from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from Partelier.partelier.tools.snap_fit.settings import SnapFitSettings
from Partelier.partelier.tools.snap_fit.planner import build_snap_fit_plan
from Partelier.partelier.tools.snap_fit.torsion import adapt_unit, add_torsion_bodies, TorsionUnit
from Partelier.partelier.tools.hinge import fusion as hinge


def fixture(**updates):
    base = SnapFitSettings(chamfer_edges=False, print_support=False)
    values = base.to_dict()
    values.update(torsion_radius_mm=.8, snap_family="torsion")
    values.update(updates)
    settings = SimpleNamespace(**values)
    unit = build_snap_fit_plan(base, 60).units[0]
    return settings, unit


def body():
    return SimpleNamespace(isValid=True, isSolid=True, lumps=SimpleNamespace(count=1))


class SnapFitTorsionTests(unittest.TestCase):
    def test_two_posts_support_a_y_axis_bar_above_the_root(self):
        settings, raw = fixture()
        unit = adapt_unit(raw, settings)
        self.assertIsInstance(unit, TorsionUnit)
        geometry = unit.torsion_geometry
        self.assertAlmostEqual(geometry.axis_x_mm, 1.1)
        self.assertAlmostEqual(geometry.axis_z_mm, 1.1)
        self.assertAlmostEqual(geometry.radius_mm, .8)
        self.assertAlmostEqual(geometry.start_y_mm, -3.2)
        self.assertAlmostEqual(geometry.end_y_mm, 3.2)
        self.assertEqual(len(geometry.posts), 2)
        self.assertGreater(geometry.axis_z_mm - geometry.radius_mm, unit.root.z_max_mm)
        for post in geometry.posts:
            self.assertLess(post.z_min_mm, unit.root.z_max_mm)
            self.assertGreater(post.z_max_mm, geometry.axis_z_mm)
            self.assertGreater(post.x_max_mm, unit.root.x_min_mm)
            self.assertLess(post.x_min_mm, unit.root.x_max_mm)

    def test_central_lever_joins_only_the_bar_and_has_two_real_post_clearances(self):
        settings, raw = fixture()
        unit = adapt_unit(raw, settings)
        self.assertEqual(len(unit.arms), 1)
        arm = unit.arms[0]
        geometry = unit.torsion_geometry
        self.assertAlmostEqual(arm.beam.y_max_mm - arm.beam.y_min_mm, settings.width_mm / 3)
        self.assertAlmostEqual(min(z for x, z in arm.beam.points_xz_mm), geometry.axis_z_mm)
        self.assertGreater(min(z for x, z in arm.beam.points_xz_mm), unit.root.z_max_mm)
        self.assertGreater(arm.beam.y_min_mm - geometry.posts[0].y_max_mm, settings.clearance_mm)
        self.assertGreater(geometry.posts[1].y_min_mm - arm.beam.y_max_mm, settings.clearance_mm)
        self.assertGreater(geometry.axis_z_mm + geometry.radius_mm,
                           min(z for x, z in arm.beam.points_xz_mm))

    def test_hook_and_single_matching_receiver_follow_the_center_lever(self):
        settings, raw = fixture()
        unit = adapt_unit(raw, settings)
        arm = unit.arms[0]
        self.assertEqual(arm.hook.y_min_mm, arm.beam.y_min_mm)
        self.assertEqual(arm.hook.y_max_mm, arm.beam.y_max_mm)
        self.assertAlmostEqual(arm.receiver.y_min_mm, arm.hook.y_min_mm - settings.clearance_mm)
        self.assertAlmostEqual(arm.receiver.y_max_mm, arm.hook.y_max_mm + settings.clearance_mm)
        self.assertEqual(arm.hook.points_xz_mm[0], (-settings.hook_depth_mm, settings.reach_mm - settings.lead_in_mm))
        self.assertLess(arm.receiver_cover.y_min_mm, arm.receiver.y_min_mm)
        self.assertGreater(arm.receiver_cover.y_max_mm, arm.receiver.y_max_mm)

    def test_root_and_print_ramp_follow_full_post_depth_without_a_step(self):
        base = SnapFitSettings(print_support=True, chamfer_edges=False)
        values = base.to_dict()
        values.update(torsion_radius_mm=.8, snap_family="torsion")
        raw = build_snap_fit_plan(base, 60).units[0]
        unit = adapt_unit(raw, SimpleNamespace(**values))
        self.assertAlmostEqual(unit.root.x_max_mm, 1.9)
        self.assertEqual(unit.root.z_max_mm, raw.root.z_max_mm)
        self.assertEqual(unit.root.z_min_mm, raw.root.z_min_mm)
        self.assertTrue(all(post.x_max_mm == unit.root.x_max_mm for post in unit.torsion_geometry.posts))
        self.assertAlmostEqual(unit.root_cover.z_min_mm, -6.4)
        self.assertAlmostEqual(max(x for x,z in unit.root_support.points_xz_mm), unit.root.x_max_mm)
        self.assertIsNotNone(unit.root_support)

    def test_thicker_arms_keep_posts_and_fixed_root_in_the_same_plane(self):
        base = SnapFitSettings(snap_family="torsion", torsion_radius_mm=.4)
        raw = build_snap_fit_plan(base, 60).units[0]
        unit = adapt_unit(raw, base)
        self.assertTrue(all(post.x_max_mm == unit.root.x_max_mm for post in unit.torsion_geometry.posts))

    def test_existing_hook_style_does_not_make_extra_torsion_levers(self):
        for style in ("standard", "tapered", "twin"):
            base = SnapFitSettings(snap_style=style, chamfer_edges=False)
            values = base.to_dict()
            values.update(torsion_radius_mm=.8, snap_family="torsion")
            raw = build_snap_fit_plan(base, 60).units[0]
            with self.subTest(style=style):
                unit = adapt_unit(raw, SimpleNamespace(**values))
                self.assertEqual(len(unit.arms), 1)
                tip_outer = max(x for x, z in unit.arms[0].beam.points_xz_mm if z == base.reach_mm)
                self.assertAlmostEqual(tip_outer - base.clearance_mm, base.thickness_mm)

    def test_radius_post_and_lever_interference_are_refused_without_adjusting_settings(self):
        for radius in (0, -1, True, float("inf"), float("nan"), "0.8", 10 ** 1000):
            settings, raw = fixture(torsion_radius_mm=radius)
            with self.subTest(radius=repr(radius)[:20]), self.assertRaises(ValueError):
                adapt_unit(raw, settings)
        settings, raw = fixture(torsion_radius_mm=1.5)
        with self.assertRaisesRegex(ValueError, "between the lever"):
            adapt_unit(raw, settings)
        self.assertEqual(settings.torsion_radius_mm, 1.5)

    def test_bar_must_leave_room_below_the_hook_shoulder(self):
        settings, raw = fixture(reach_mm=4, lead_in_mm=3)
        with self.assertRaisesRegex(ValueError, "shoulder stays above"):
            adapt_unit(raw, settings)

    def test_bad_or_missing_unit_plan_is_refused(self):
        settings, raw = fixture()
        with self.assertRaisesRegex(ValueError, "complete snap-fit"):
            adapt_unit(None, settings)
        with self.assertRaisesRegex(ValueError, "torsion unit plan"):
            add_torsion_bodies(None, None, raw, settings)

    def test_temporary_posts_precede_bar_and_native_units_convert_once(self):
        settings, raw = fixture()
        unit = adapt_unit(raw, settings)
        posts = (body(), body())
        bar = body()
        manager = SimpleNamespace(createCylinderOrCone=Mock(return_value=bar))
        frame = hinge.HingeFrame((10, 20, 30), (1, 0, 0), (0, 1, 0), (0, 0, 1))
        def native_point(frame, x, y, z):
            return tuple(value / 10 for value in frame.point_mm(x, y, z))
        with patch.object(hinge, "_box", side_effect=posts) as boxes, patch.object(
                hinge, "_point", side_effect=native_point):
            result = add_torsion_bodies(manager, frame, unit, settings)
        self.assertEqual(result, posts + (bar,))
        self.assertEqual(boxes.call_count, 2)
        start, radius_one, end, radius_two = manager.createCylinderOrCone.call_args.args
        for actual, expected in zip(start, (1.11, 1.68, 3.11)):
            self.assertAlmostEqual(actual, expected)
        for actual, expected in zip(end, (1.11, 2.32, 3.11)):
            self.assertAlmostEqual(actual, expected)
        self.assertAlmostEqual(radius_one, .08)
        self.assertAlmostEqual(radius_two, .08)

    def test_failed_native_bar_construction_raises_instead_of_partial_result(self):
        settings, raw = fixture()
        unit = adapt_unit(raw, settings)
        manager = SimpleNamespace(createCylinderOrCone=Mock(return_value=None))
        with patch.object(hinge, "_box", side_effect=(body(), body())), patch.object(
                hinge, "_point", return_value=object()), self.assertRaisesRegex(ValueError, "torsion bar"):
            add_torsion_bodies(manager, None, unit, settings)


if __name__ == "__main__":
    unittest.main()

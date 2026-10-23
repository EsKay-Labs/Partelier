"""Bounded bevel size, exposed-edge policy and protected catch/root regions."""

import unittest

from Partelier.partelier.tools.snap_fit.finish import (apply_chamfers,
    plan_detail_chamfers, plan_receiver_chamfers)
from Partelier.partelier.tools.snap_fit.planner import build_snap_fit_plan
from Partelier.partelier.tools.snap_fit.settings import SnapFitSettings


def contains(cut, point):
    delta = tuple(value - origin for value, origin in zip(point, cut.center_mm))
    for axis, size in ((cut.edge_axis, cut.length_mm), (cut.tangent_axis, cut.width_mm),
                       (cut.normal_axis, cut.depth_mm)):
        if abs(sum(a * b for a, b in zip(delta, axis))) >= size / 2:
            return False
    return True


class SnapFitFinishTests(unittest.TestCase):
    def test_requested_45_degree_beam_bevel_removes_point_at_point_nine_size_but_not_one_point_one(self):
        for style in ("standard", "tapered", "twin"):
            settings = SnapFitSettings(snap_style=style)
            unit = build_snap_fit_plan(settings, 60).units[0]
            cuts = plan_detail_chamfers(unit, settings)
            for arm in unit.arms:
                z = settings.reach_mm / 3
                outer = settings.clearance_mm + settings.thickness_mm * (1 - .35 * z / settings.reach_mm if style == "tapered" else 1)
                for factor, expected in ((.45, True), (.55, False)):
                    point = (outer - factor * settings.chamfer_size_mm,
                             arm.beam.y_max_mm - factor * settings.chamfer_size_mm, z)
                    with self.subTest(style=style, factor=factor):
                        self.assertEqual(any(contains(cut, point) for cut in cuts), expected)

    def test_receiver_entry_has_requested_bevel_and_preserves_flat_lower_catch_lip(self):
        settings = SnapFitSettings()
        arm = build_snap_fit_plan(settings, 60).units[0].arms[0]
        cuts = plan_receiver_chamfers(arm, settings)
        z = settings.reach_mm - settings.lead_in_mm / 2
        for factor, expected in ((.45, True), (.55, False)):
            point = (-factor * settings.chamfer_size_mm,
                     arm.receiver.y_max_mm + factor * settings.chamfer_size_mm, z)
            self.assertEqual(any(contains(cut, point) for cut in cuts), expected)
        protected = (-.05, arm.receiver.y_max_mm + .05, arm.receiver_bounds.z_min_mm + .05)
        self.assertFalse(any(contains(cut, protected) for cut in cuts))

    def test_negative_x_hook_land_and_root_joint_are_outside_every_finish_tool(self):
        for style in ("standard", "tapered", "twin"):
            settings = SnapFitSettings(snap_style=style)
            unit = build_snap_fit_plan(settings, 60).units[0]
            cuts = plan_detail_chamfers(unit, settings)
            for arm in unit.arms:
                shoulder = settings.reach_mm - settings.lead_in_mm
                catch = (-settings.hook_depth_mm / 2, arm.hook.y_max_mm - .05, shoulder + .02)
                root_joint = (settings.clearance_mm, arm.hook.y_max_mm - .05, -.05)
                with self.subTest(style=style):
                    self.assertFalse(any(contains(cut, catch) for cut in cuts))
                    self.assertFalse(any(contains(cut, root_joint) for cut in cuts))

    def test_chamfer_off_has_no_cutters_or_native_work(self):
        settings = SnapFitSettings(chamfer_edges=False)
        unit = build_snap_fit_plan(settings, 60).units[0]
        self.assertEqual(plan_detail_chamfers(unit, settings), ())
        self.assertEqual(plan_receiver_chamfers(unit.arms[0], settings), ())
        body = object()
        self.assertIs(apply_chamfers(None, None, body, ()), body)


if __name__ == "__main__":
    unittest.main()

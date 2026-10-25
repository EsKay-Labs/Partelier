"""Detent engagement, clearance envelope and support roof geometry."""

from dataclasses import replace
import math
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from Partelier.partelier.tools.snap_fit import ball_detent
from Partelier.partelier.tools.snap_fit.planner import build_snap_fit_plan
from Partelier.partelier.tools.snap_fit.settings import SnapFitSettings
from Partelier.partelier.tools.hinge import fusion as hinge


class BallDetentTests(unittest.TestCase):
    def unit(self, **values):
        settings = SnapFitSettings(snap_family="ball_detent", **values)
        raw = build_snap_fit_plan(settings, 80).units[0]
        return settings, ball_detent.adapt_unit(raw, settings)

    def test_engagement_is_exact_and_spherical_socket_has_radial_clearance(self):
        settings, unit = self.unit()
        ball = unit.ball_geometry
        self.assertAlmostEqual(ball.center_mm[0]-ball.radius_mm, -settings.hook_depth_mm)
        self.assertAlmostEqual(ball.center_mm[2]+ball.radius_mm, settings.reach_mm)
        self.assertAlmostEqual(ball.socket_radius_mm-ball.radius_mm, settings.clearance_mm)
        self.assertGreater(ball.center_mm[0]+ball.radius_mm, settings.clearance_mm)
        self.assertEqual(unit.root, build_snap_fit_plan(settings, 80).units[0].root)

    def test_support_plane_encloses_upper_sphere_and_has_45_degree_slope(self):
        settings, unit = self.unit()
        x, _, z = unit.ball_geometry.center_mm
        radius = unit.ball_geometry.socket_radius_mm
        intercept = z + math.sqrt(2)*radius-x
        for index in range(101):
            sample_x = x-radius+2*radius*index/100
            sphere_top = z+math.sqrt(max(0, radius**2-(sample_x-x)**2))
            self.assertGreaterEqual(sample_x+intercept+1e-10, sphere_top)
        self.assertAlmostEqual((1+intercept)-(0+intercept), 1)
        self.assertGreaterEqual(unit.ball_geometry.receiver_cover.z_max_mm, intercept)

    def test_disabled_support_uses_spherical_top_envelope(self):
        settings, unit = self.unit(print_support=False)
        ball = unit.ball_geometry
        self.assertAlmostEqual(ball.receiver_cover.z_max_mm,
                               ball.center_mm[2]+ball.socket_radius_mm+settings.clearance_mm)

    def test_sphere_creation_converts_millimetres_once(self):
        _, unit = self.unit()
        manager = SimpleNamespace(createSphere=Mock(return_value="nose"))
        with patch.object(hinge, "_point", side_effect=lambda frame,*point: tuple(v/10 for v in point)), patch.object(hinge, "_require_body"):
            self.assertEqual(ball_detent.nose_body(manager, None, unit), "nose")
        manager.createSphere.assert_called_once_with((.1, 0, 1.4), .2)

    def test_invalid_ball_geometry_and_hook_variant_are_refused(self):
        for values in ({"ball_radius_mm": .4}, {"ball_radius_mm": 8},
                       {"snap_style": "twin"}, {"hook_depth_mm": 4}):
            with self.subTest(values=values), self.assertRaises(ValueError):
                SnapFitSettings(snap_family="ball_detent", **values)

    def test_multiple_detents_retain_requested_centres(self):
        settings = SnapFitSettings(snap_family="ball_detent", snap_count=3)
        units = tuple(ball_detent.adapt_unit(unit, settings)
                      for unit in build_snap_fit_plan(settings, 100).units)
        centres = [unit.ball_geometry.center_mm[1] for unit in units]
        self.assertAlmostEqual(centres[1]-centres[0], centres[2]-centres[1])
        self.assertEqual(centres[1], 0)

    def test_local_free_space_covers_nose_deflection_without_requiring_an_exterior_body(self):
        for radius,width,engagement in ((1.25,6,.45),(3,2,1),(2,12,.5)):
            settings,unit=self.unit(ball_radius_mm=radius,width_mm=width,hook_depth_mm=engagement,chamfer_edges=False)
            bounds=ball_detent.free_space(unit,settings)
            ball=unit.ball_geometry
            self.assertEqual(bounds.x_min_mm,0)
            self.assertGreaterEqual(bounds.x_max_mm,ball.center_mm[0]+radius+engagement+settings.clearance_mm)
            self.assertGreaterEqual(bounds.x_max_mm,unit.beam.x_max_mm+engagement+settings.clearance_mm)
            self.assertLessEqual(bounds.y_min_mm,unit.center_y_mm-max(width/2,radius)-settings.clearance_mm)
            self.assertGreaterEqual(bounds.y_max_mm,unit.center_y_mm+max(width/2,radius)+settings.clearance_mm)
            self.assertEqual(bounds.z_min_mm,0);self.assertEqual(bounds.z_max_mm,settings.reach_mm+settings.clearance_mm)

    def test_local_space_refuses_either_obstructing_body_or_unproven_boolean(self):
        from Partelier.partelier.tools.snap_fit import fusion
        settings,unit=self.unit();manager,frame,a,b,envelope=(object() for _ in range(5))
        for failure in (None,0,1):
            calls=[None,None]
            if failure is not None:calls[failure]=fusion.SnapFitGeometryError('collision or failed boolean')
            with patch.object(hinge,'_box',return_value=envelope),patch.object(fusion,'_no_positive_overlap',side_effect=calls) as check:
                if failure is None:
                    fusion._detent_clearance(manager,frame,unit,settings,a,b)
                    self.assertEqual([call.args[2] for call in check.call_args_list],[a,b])
                else:
                    with self.assertRaisesRegex(ValueError,'empty space'):fusion._detent_clearance(manager,frame,unit,settings,a,b)
                    self.assertIs(check.call_args_list[-1].args[2],(a,b)[failure])


if __name__ == "__main__":
    unittest.main()

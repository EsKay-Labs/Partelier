"""CAD groove layout, full-height modes and conservative motif support bounds."""
from dataclasses import replace
import math
import unittest

from Partelier.partelier.tools.knurl.settings import KnurlSettings, STYLES
from Partelier.partelier.tools.knurl import planner


class KnurlPlanTests(unittest.TestCase):
    def test_rounded_diamond_uses_paired_repeats_and_preserves_requested_radius(self):
        settings=KnurlSettings(mode='emboss',grip_fillet_mm=.15)
        plan=planner.plan(settings,8,8)
        self.assertEqual(plan.repeats%2,0)
        self.assertAlmostEqual(plan.repeats*plan.effective_pitch_mm,2*math.pi*8.6)
        self.assertEqual(settings.grip_fillet_mm,.15)

    def test_exact_typed_settings_and_full_height_defaults(self):
        settings=KnurlSettings()
        self.assertEqual((settings.style,settings.pitch_mm,settings.depth_mm,settings.border_mm),('diamond',6.,.6,0.))
        self.assertEqual((settings.mode,settings.top_finish,settings.bottom_finish),('engrave','none','none'))
        self.assertEqual(len(settings.to_dict()),13)
        self.assertEqual(KnurlSettings.from_dict(settings.to_dict()),settings)
        for values in ({'depth_mm':True},{'angle_deg':float('nan')},{'pitch_mm':float('inf')},
                       {'border_mm':10**1000},{'groove_fillet_mm':-1},{'groove_fillet_mm':True},{'groove_fillet_mm':2.1},{'grip_fillet_mm':-1},{'grip_fillet_mm':True},{'grip_fillet_mm':2.1},{'style':'unknown'},{'mode':'add'},
                       {'bottom_finish':'chamferish'},{'top_size_mm':0}):
            with self.subTest(values=values),self.assertRaises(ValueError):replace(settings,**values)
        for key in settings.to_dict():
            value=settings.to_dict();value.pop(key)
            with self.assertRaises(ValueError):KnurlSettings.from_dict(value)

    def test_every_style_has_a_bounded_full_height_plan(self):
        for style in STYLES:
            for mode in ('engrave','emboss'):
                with self.subTest(style=style,mode=mode):
                    p=planner.plan(KnurlSettings(style=style,mode=mode),15,20)
                    self.assertLessEqual(p.cutter_count,planner.MAX_CUTTERS)
                    self.assertLessEqual(p.max_overhang_deg,45.)
                    self.assertGreaterEqual(p.repeats,3)
                    self.assertLessEqual(p.repeats,planner.MAX_REPEATS)
                    self.assertAlmostEqual(p.repeats*p.effective_pitch_mm,2*math.pi*p.outer_radius_mm)

    def test_outward_relief_preserves_the_nominal_core(self):
        inward=planner.plan(KnurlSettings(),15,20)
        outward=planner.plan(KnurlSettings(mode='emboss'),15,20)
        self.assertEqual(inward.outer_radius_mm,15)
        self.assertEqual(inward.root_radius_mm,14.4)
        self.assertEqual(outward.root_radius_mm,15)
        self.assertEqual(outward.outer_radius_mm,15.6)

    def test_zero_border_has_no_mandatory_fade_or_plain_bands(self):
        p=planner.plan(KnurlSettings(border_mm=0),8,2)
        self.assertGreater(p.cutter_count,0)
        self.assertFalse(hasattr(p,'levels_mm'))
        with self.assertRaisesRegex(ValueError,'Border'):
            planner.plan(KnurlSettings(border_mm=1),8,2)

    def test_spacing_changes_whole_number_repeats(self):
        a=planner.plan(KnurlSettings(),15,20)
        b=planner.plan(KnurlSettings(pitch_mm=9),15,20)
        self.assertLess(b.repeats,a.repeats)
        self.assertGreater(b.effective_pitch_mm,a.effective_pitch_mm)

    def test_straight_and_rounded_axial_grooves_have_no_axial_overhang(self):
        for style in ('straight','flutes','scallops'):
            self.assertEqual(planner.plan(KnurlSettings(style=style),15,20).max_overhang_deg,0)

    def test_spherical_dimple_bound_keeps_downward_normals_within_45(self):
        s=KnurlSettings(style='dimples');p=planner.plan(s,15,20)
        q=(p.half_width_mm**2+s.depth_mm**2)/(2*s.depth_mm)
        # All groove points lie inside outer_radius. Therefore the horizontal
        # distance from the sphere centre is >=q-d, and |nz|<=sqrt(q²-(q-d)²).
        bound=math.sqrt(q*q-(q-s.depth_mm)**2)/(q-s.depth_mm)
        self.assertLessEqual(bound,1)
        self.assertAlmostEqual(math.tan(math.radians(p.max_overhang_deg)),bound)

    def test_actual_smooth_wave_normals_stay_inside_control_hull_bound(self):
        from Partelier.partelier.tools.knurl import wave_profile as w
        settings=KnurlSettings(style='waves',angle_deg=45)
        p=planner.plan(settings,15,20)
        paths=[w.spans(point,-.1,20.1,p.effective_pitch_mm,45,p.outer_radius_mm)[0]
               for point in w.profile(p.outer_radius_mm,p.root_radius_mm,p.half_width_mm,settings.depth_mm)]
        bound=math.tan(math.radians(p.max_overhang_deg))
        def evaluate(points,t):
            n=len(points)-1
            return tuple(sum(math.comb(n,i)*t**i*(1-t)**(n-i)*v[k] for i,v in enumerate(points)) for k in range(3))
        for i in range(3):
            for one,two in zip(paths[i],paths[(i+1)%3]):
                for t in (0.,.1,.25,.5,.75,.9,1.):
                    a,b=evaluate(one,t),evaluate(two,t)
                    edge=tuple(y-x for x,y in zip(a,b))
                    for u in (0.,.3,.7,1.):
                        points=tuple(tuple((1-u)*x+u*y for x,y in zip(a,b)) for a,b in zip(one,two))
                        derivatives=tuple(tuple(3*(y-x) for x,y in zip(a,b)) for a,b in zip(points,points[1:]))
                        v=evaluate(derivatives,t)
                        normal=(edge[1]*v[2]-edge[2]*v[1],edge[2]*v[0]-edge[0]*v[2],edge[0]*v[1]-edge[1]*v[0])
                        slope=abs(normal[2])/math.hypot(normal[0],normal[1])
                        self.assertLessEqual(slope,bound+1e-10)
        self.assertLessEqual(bound,1.)

    def test_wave_bezier_sections_have_matching_position_and_tangent(self):
        from Partelier.partelier.tools.knurl import wave_profile as w
        sections,levels=w.spans((15.,.8),-.1,20.1,6.,30.,15.)
        for index,(one,two) in enumerate(zip(sections,sections[1:])):
            self.assertEqual(one[-1],two[0])
            left=levels[index+1]-levels[index];right=levels[index+2]-levels[index+1]
            for k in range(3):
                self.assertAlmostEqual(3*(one[-1][k]-one[-2][k])/left,3*(two[1][k]-two[0][k])/right)

    def test_excessive_overhang_refused_without_silently_changing_depth(self):
        for style in ('diamond','helical','chevron','waves','rings','pyramids','dimples'):
            s=KnurlSettings(style=style,depth_mm=3,pitch_mm=3,angle_deg=45)
            with self.subTest(style=style),self.assertRaises(ValueError):planner.plan(s,15,20)
            self.assertEqual(s.depth_mm,3)

    def test_extreme_repeat_and_dimple_counts_are_bounded(self):
        with self.assertRaisesRegex(ValueError,'dense'):
            planner.plan(KnurlSettings(pitch_mm=2),100,200)
        with self.assertRaisesRegex(ValueError,'dense'):
            planner.plan(KnurlSettings(style='dimples'),15,200)

    def test_collapsed_core_and_nonfinite_cylinder_refused(self):
        with self.assertRaisesRegex(ValueError,'core'):
            planner.plan(KnurlSettings(depth_mm=1),2,8)
        for radius,height in ((float('nan'),10),(8,True),(10**1000,10)):
            with self.assertRaises(ValueError):planner.plan(KnurlSettings(),radius,height)

    def test_pure_plan_cache_is_bounded_and_contains_no_native_entities(self):
        a=planner.plan(KnurlSettings(),8,8)
        b=planner.plan(KnurlSettings.from_dict(KnurlSettings().to_dict()),8,8)
        self.assertIs(a,b)
        self.assertEqual(planner._plan.cache_info().maxsize,8)
        self.assertFalse(hasattr(a,'points_mm'))


if __name__=='__main__':unittest.main()

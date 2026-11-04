"""Physical dimensions, handedness/lead and conservative thread budgets."""
from dataclasses import replace
import math
import unittest
from Partelier.partelier.tools.threads.settings import ThreadSettings, METRIC, preset
from Partelier.partelier.tools.threads import planner

class ThreadPlanTests(unittest.TestCase):
    def test_default_is_printable_radial_clearance_with_coarse_pitch(self):
        s=ThreadSettings();p=planner.plan(s)
        self.assertEqual((s.profile,s.diameter_mm,s.pitch_mm,s.clearance_mm),('printable_v',24,3,.25))
        self.assertAlmostEqual(p.major_radius_mm-p.minor_radius_mm,1.05)
        self.assertAlmostEqual(p.female_major_radius_mm-p.major_radius_mm,.25)
        self.assertAlmostEqual(p.female_minor_radius_mm-p.minor_radius_mm,.25)
        self.assertEqual(p.lead_mm,3)
        self.assertEqual(p.turns,4)
        a,b=p.profile[:2]
        self.assertAlmostEqual(b[0]-a[0],b[1]-a[1])

    def test_snapshot_is_exact_and_typed(self):
        s=ThreadSettings();self.assertEqual(len(s.to_dict()),13)
        self.assertEqual(ThreadSettings.from_dict(s.to_dict()),s)
        for patch in ({'diameter_mm':True},{'starts':1.0},{'clearance_mm':float('nan')},
                      {'pitch_mm':float('inf')},{'length_mm':10**1000},{'mode':'both'},{'profile':'iso'}):
            with self.subTest(patch=patch),self.assertRaises(ValueError):replace(s,**patch)
        for key in s.to_dict():
            value=s.to_dict();value.pop(key)
            with self.assertRaises(ValueError):ThreadSettings.from_dict(value)
        with self.assertRaises(ValueError):ThreadSettings.from_dict({**s.to_dict(),'future':1})

    def test_multi_start_changes_lead_not_pitch(self):
        for starts in (1,2,3):
            for hand in ('right','left'):
                s=replace(ThreadSettings(),starts=starts,handedness=hand);p=planner.plan(s)
                self.assertEqual(p.lead_mm,3*starts)
                self.assertAlmostEqual(p.turns,4/starts)
                self.assertEqual(p.profile,planner.plan(ThreadSettings()).profile)

    def test_clearance_is_applied_to_standalone_part_and_only_once_in_pairs(self):
        s=ThreadSettings()
        self.assertEqual(planner.allowance(s),-.25)
        self.assertEqual(planner.allowance(replace(s,mode='internal'),True),.25)
        for mode in ('pair','coupon'):
            setting=replace(s,mode=mode)
            self.assertEqual(planner.allowance(setting),0)
            self.assertEqual(planner.allowance(setting,True),.25)
            self.assertAlmostEqual(planner.allowance(setting,True)-planner.allowance(setting),s.clearance_mm)
        self.assertEqual(planner.allowance(replace(s,clearance_mm=0)),0)
        with self.assertRaises(ValueError):replace(s,diameter_mm=6,clearance_mm=1)
        with self.assertRaises(ValueError):replace(s,diameter_mm=6,clearance_mm=.5,lead_in_mm=2.1)

    def test_metric_coarse_profiles_preserve_nominal_crest_root_and_sixty_degrees(self):
        for name,(diameter,pitch) in METRIC.items():
            with self.subTest(name=name):
                s=preset(name);p=planner.plan(s);H=math.sqrt(3)*pitch/2
                self.assertEqual(s.profile,'metric');self.assertEqual(p.major_radius_mm,diameter/2)
                self.assertAlmostEqual(p.minor_radius_mm,diameter/2-17*H/24)
                tangent,crest=p.profile[6:8]
                self.assertAlmostEqual((crest[0]-tangent[0])/(crest[1]-tangent[1]),math.sqrt(3))
                self.assertLess(abs(p.profile[0][0]-p.minor_radius_mm),.001)
                self.assertGreater(p.profile[0][1],-pitch/2)

    def test_rounded_crest_remains_inside_printable_envelope(self):
        s=replace(ThreadSettings(),profile='rounded');p=planner.plan(s)
        self.assertEqual(len(p.profile),12)
        self.assertEqual(p.profile[0],planner.section(ThreadSettings())[0])
        self.assertEqual(p.profile[-1],planner.section(ThreadSettings())[-1])
        self.assertTrue(all(p.minor_radius_mm<=r<=p.major_radius_mm for r,z in p.profile))
        for a,b in zip(p.profile,tuple((r,-z) for r,z in reversed(p.profile))):
            self.assertAlmostEqual(a[0],b[0]);self.assertAlmostEqual(a[1],b[1])

    def test_printing_bounds_refuse_collapsed_or_excessive_threads(self):
        s=ThreadSettings()
        for patch in ({'depth_mm':2},{'diameter_mm':6,'depth_mm':2},
                      {'lead_in_mm':5,'length_mm':6},{'length_mm':80,'pitch_mm':.5},
                      {'pitch_mm':12,'length_mm':2},{'mode':'coupon','clearance_mm':.05}):
            with self.subTest(patch=patch),self.assertRaises(ValueError):replace(s,**patch)

    def test_profile_loop_is_simple_ccw_and_keeps_adjacent_turns_separate(self):
        for profile in ('printable_v','metric','rounded'):
            s=replace(ThreadSettings(),profile=profile);points=planner.section(s)
            area=sum(a[0]*b[1]-b[0]*a[1] for a,b in zip(points,points[1:]+points[:1]))/2
            self.assertGreater(area,0)
            self.assertLess(max(z for _,z in points)-min(z for _,z in points),s.pitch_mm)

    def test_printable_profiles_helical_flanks_stay_within_forty_five_degrees(self):
        # Outward normal of a ruled helical side: horizontal magnitude is
        # sqrt((r*dz)^2+(lead*dr/(2pi))^2); vertical magnitude is abs(r*dr).
        # Exclude the buried root closure. This is an axis-upright geometry
        # bound, not a promise for horizontal threads or printing performance.
        for profile in ('printable_v','rounded'):
            for starts in (1,2,3):
                s=replace(ThreadSettings(),profile=profile,starts=starts)
                p=planner.plan(s)
                for a,b in zip(p.profile,p.profile[1:]):
                    radius=(a[0]+b[0])/2;dr=b[0]-a[0];dz=b[1]-a[1]
                    horizontal=math.hypot(radius*dz,p.lead_mm*dr/(2*math.pi))
                    self.assertLessEqual(abs(radius*dr),horizontal+1e-9)

    def test_coupon_ladder_bounds_remain_within_settings(self):
        with self.assertRaises(ValueError):replace(ThreadSettings(),mode='coupon',clearance_mm=.95)
        with self.assertRaises(ValueError):replace(ThreadSettings(),mode='coupon',wall_mm=1.2)
        with self.assertRaises(ValueError):replace(ThreadSettings(),diameter_mm=6,lead_in_mm=3)
        s=replace(ThreadSettings(),mode='coupon')
        for allowance in (s.clearance_mm-s.coupon_clearance_step_mm,s.clearance_mm,s.clearance_mm+s.coupon_clearance_step_mm):
            replace(s,mode='internal',clearance_mm=allowance)

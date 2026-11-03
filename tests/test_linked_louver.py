"""Analytic linkage pitch and bounded motion envelopes."""
import unittest,math
from types import SimpleNamespace
from Partelier.partelier.tools.mechanisms import linked_louver as l

def sample(**kwargs):
    values=dict(length_mm=80.,width_mm=100.,height_mm=18.,wall_mm=2.,clearance_mm=.3,pin_diameter_mm=3.,count=5,angle_deg=30.,output_mode='separate',assembly_layout='assembled');values.update(kwargs);return SimpleNamespace(**values)
class LinkedLouverTests(unittest.TestCase):
    def test_preset_has_clearance_for_all_vane_angles(self):
        s=sample();d=l.validate(s)
        self.assertAlmostEqual(math.hypot(d.chord,2*d.radius)+s.clearance_mm,d.pitch)
        self.assertLess(math.hypot(d.crank+2*d.radius,2*d.radius)+s.clearance_mm,d.pitch)
    def test_link_keeps_exact_pitch_at_every_pose(self):
        s=sample();d=l.validate(s)
        for angle in range(61):
            points=l.centers_at(s,angle)
            for i in range(1,len(points)):
                self.assertAlmostEqual(points[i][0]-points[i-1][0],d.pitch)
                self.assertAlmostEqual(points[i][1],points[0][1])
            for y,(cy,cz) in zip(d.centers,points):self.assertAlmostEqual(math.hypot(cy-y,cz-s.height_mm/2),d.crank)
    def test_unusable_envelopes_refused(self):
        for values in ({'width_mm':40.},{'height_mm':8.},{'length_mm':12.},{'count':9},{'angle_deg':75.},{'output_mode':'attached'},{'assembly_layout':'other'}):
            with self.subTest(values=values),self.assertRaises(ValueError):l.validate(sample(**values))
if __name__=='__main__':unittest.main()

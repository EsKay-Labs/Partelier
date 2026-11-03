import math,unittest
from types import SimpleNamespace
from Partelier.partelier.tools.mechanisms import parallel_lift as p

def sample(**changes):
    v=dict(length_mm=30.,width_mm=50.,height_mm=16.,wall_mm=2.,clearance_mm=.3,pin_diameter_mm=3.,angle_deg=30.,output_mode='separate',assembly_layout='assembled');v.update(changes);return SimpleNamespace(**v)
class LiftTests(unittest.TestCase):
    def test_preset_and_exact_four_bar(self):
        s=sample();p.validate(s)
        for angle in range(61):
            A,B=p.pivots(s,angle)
            self.assertAlmostEqual(math.dist(B[0],B[1]),s.width_mm)
            self.assertAlmostEqual(B[0][1],B[1][1])
            for a,b in zip(A,B):self.assertAlmostEqual(math.dist(a,b),s.length_mm)
    def test_collision_and_thin_eye_inputs_refused(self):
        for change in ({'width_mm':30.},{'length_mm':10.},{'height_mm':4.},{'angle_deg':70.},{'output_mode':'attached'}):
            with self.subTest(change=change),self.assertRaises(ValueError):p.validate(sample(**change))
if __name__=='__main__':unittest.main()

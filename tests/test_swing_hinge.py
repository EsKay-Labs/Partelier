import math
import unittest
from dataclasses import replace
from Partelier.partelier.tools.mechanisms.settings import preset
from Partelier.partelier.tools.mechanisms.swing_hinge import pivots,dimensions

class SwingHingeTests(unittest.TestCase):
    def test_closed_loop_and_true_rotating_plate(self):
        s=preset('swing_hinge');a,b,c,d,*_=dimensions(s)
        closed=pivots(s,0);closed_angle=math.atan2(closed[2][1]-closed[1][1],closed[2][0]-closed[1][0])
        for opening in (i/4 for i in range(361)):
            A,B,C,D=pivots(s,opening)
            for P,Q,length in ((A,B,a),(B,C,b),(C,D,c),(D,A,d)):
                self.assertAlmostEqual(math.dist(P,Q),length,places=9)
            angle=math.atan2(C[1]-B[1],C[0]-B[0])
            self.assertAlmostEqual(math.degrees(closed_angle-angle),opening,places=9)
        self.assertGreater(math.dist(closed[1],pivots(s,90)[1]),20)
    def test_rejects_unreachable_or_degenerate_assembly(self):
        s=preset('swing_hinge')
        for patch in ({'width_mm':100},{'length_mm':12},{'height_mm':3},{'angle_deg':91},{'output_mode':'attached'}):
            with self.subTest(patch=patch),self.assertRaises(ValueError):replace(s,**patch)
    def test_custom_uniform_scale_preserves_path(self):
        s=preset('swing_hinge');large=replace(s,length_mm=60,width_mm=80)
        for angle in (0,30,60,90):
            for small,big in zip(pivots(s,angle),pivots(large,angle)):
                for one,two in zip(small,big):self.assertAlmostEqual(2*one,two,places=9)

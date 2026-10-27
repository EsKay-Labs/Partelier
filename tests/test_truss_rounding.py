"""Tangent arc radius, exact removed areas, fit bounds and truss connectivity."""

import math
import unittest
from Partelier.partelier.tools.truss import planner,rounding


class TrussFilletTests(unittest.TestCase):
    def test_three_four_five_triangle_has_exact_inradius_and_arc_area(self):
        polygon=((0,0),(4,0),(0,3));radius=.4
        hole=rounding.window(polygon,radius)
        self.assertAlmostEqual(hole.maximum_radius_mm,1)
        self.assertAlmostEqual(hole.area_mm2,6-radius**2*(6-math.pi))
        self.assertEqual(hole.interior_point,(1,1))

    def test_every_arc_is_exact_and_tangent_to_both_original_edges(self):
        for style in planner.STYLES:
            for axis in ('long','short'):
                layout=planner.plan((-60,60,-20,20),style,6,2,3,axis,.5)
                for polygon,hole in zip(layout.holes,layout.rounded_holes):
                    for index,corner in enumerate(hole.corners):
                        for point in (corner.start,corner.middle,corner.end):
                            self.assertAlmostEqual(math.dist(point,corner.center),.5)
                            for a,b in zip(polygon,polygon[1:]+polygon[:1]):
                                self.assertGreaterEqual((b[0]-a[0])*(point[1]-a[1])-(b[1]-a[1])*(point[0]-a[0]),-1e-8)
                        for end,other in ((corner.start,polygon[index-1]),(corner.end,polygon[(index+1)%3])):
                            edge=tuple(a-b for a,b in zip(other,polygon[index]))
                            radial=tuple(a-b for a,b in zip(end,corner.center))
                            self.assertAlmostEqual(sum(a*b for a,b in zip(edge,radial)),0)
                    self.assertAlmostEqual(sum(c.turn_rad for c in hole.corners),2*math.pi)

    def test_zero_preserves_original_geometry_and_rounding_only_adds_junction_material(self):
        for style in planner.STYLES:
            sharp=planner.plan((0,120,0,40),style,6,2,3)
            self.assertEqual(sharp.rounded_holes,())
            small=planner.plan((0,120,0,40),style,6,2,3,fillet_mm=.4)
            larger=planner.plan((0,120,0,40),style,6,2,3,fillet_mm=.8)
            self.assertEqual(sharp.outer,small.outer);self.assertEqual(sharp.members,larger.members)
            self.assertEqual(sharp.holes,larger.holes)
            self.assertLess(sharp.material_area_mm2,small.material_area_mm2)
            self.assertLess(small.material_area_mm2,larger.material_area_mm2)
            self.assertAlmostEqual(larger.material_area_mm2+larger.open_area_mm2,4800)

    def test_radius_near_incircle_retains_a_positive_straight_portion_and_void(self):
        polygon=((0,0),(4,0),(0,3));hole=rounding.window(polygon,.99)
        self.assertGreater(hole.area_mm2,math.pi*.99**2)
        for i,corner in enumerate(hole.corners):self.assertGreater(math.dist(corner.end,hole.corners[(i+1)%3].start),1e-4)
        for radius in (1,1.01,1000):
            with self.assertRaisesRegex(ValueError,'too large'):rounding.window(polygon,radius)

    def test_early_refusal_for_collapsed_arcs_invalid_types_and_clockwise_windows(self):
        polygon=((0,0),(4,0),(0,3))
        for radius in (-1,0,True,math.nan,math.inf,'1',1e-12):
            with self.subTest(radius=radius),self.assertRaises(ValueError):rounding.window(polygon,radius)
        for polygon in (((0,0),(0,3),(4,0)),((0,0),(1,1),(2,2)),((0,0),(3,0),(3,3),(0,3))):
            with self.assertRaises(ValueError):rounding.window(polygon,.2)
        with self.assertRaisesRegex(ValueError,'too large'):planner.plan((0,120,0,40),'truss_pratt',6,2,3,fillet_mm=50)

    def test_planning_is_translation_invariant_and_bounded_at_128_windows(self):
        polygon=((0,0),(4,0),(0,3));shift=(100000,-100000)
        plain=rounding.window(polygon,.4)
        moved=rounding.window(tuple(tuple(v+d for v,d in zip(p,shift)) for p in polygon),.4)
        self.assertAlmostEqual(plain.area_mm2,moved.area_mm2)
        for one,two in zip(plain.corners,moved.corners):
            for p,q in zip(one.center,two.center):self.assertAlmostEqual(abs(q-p),100000)
        layout=planner.plan((0,1000,0,100),'truss_pratt',64,1,3,fillet_mm=.5)
        self.assertEqual(len(layout.rounded_holes),128)
        self.assertEqual(sum(len(h.corners) for h in layout.rounded_holes),384)


if __name__=='__main__':unittest.main()

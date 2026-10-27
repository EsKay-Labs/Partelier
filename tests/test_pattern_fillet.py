"""Shared per-cell tangent geometry, explicit overrides and bounded trim curves."""

import math
import unittest
from dataclasses import replace
from Partelier.partelier.tools.patterns import fillet,clipping,tiles
from Partelier.partelier.tools.patterns.settings import PatternSettings
from Partelier.partelier.tools.patterns.planner import build_layout


class PatternFilletTests(unittest.TestCase):
    def test_square_radius_is_exact_and_area_adds_four_circular_segments(self):
        square=((-5,-5),(5,-5),(5,5),(-5,5));value=fillet.profile(square,1)
        self.assertAlmostEqual(value.area_mm2,100-4+math.pi)
        self.assertAlmostEqual(value.maximum_radius_mm,5)
        for corner in value.corners:
            self.assertAlmostEqual(corner.turn_rad,math.pi/2)
            for p in (corner.start,corner.middle,corner.end):self.assertAlmostEqual(math.dist(p,corner.center),1)
        self.assertEqual(value.interior_point,(0,0))

    def test_every_polygon_family_and_warren_gets_strict_arcs_inside_original_cell(self):
        for name in tiles.TILED_PATTERNS:
            profiles=tiles.profiles(name,10,2,sharp=True)
            for center,polygon in profiles[2]:
                value=fillet.profile(polygon,.3)
                self.assertGreater(value.area_mm2,0);self.assertLess(value.area_mm2,clipping.area(polygon))
                for c in value.corners:
                    for point in (c.start,c.middle,c.end):
                        self.assertAlmostEqual(math.dist(point,c.center),.3)
                        self.assertTrue(all((b[0]-a[0])*(point[1]-a[1])-(b[1]-a[1])*(point[0]-a[0])>=-1e-8 for a,b in zip(polygon,polygon[1:]+polygon[:1])))

    def test_clip_strokes_have_a_proved_sag_limit_and_bounded_point_count(self):
        value=fillet.profile(((-5,-5),(5,-5),(5,5),(-5,5)),1)
        polygon=fillet.stroke(value)
        self.assertLessEqual(len(polygon),128)
        self.assertLess(clipping.area(polygon),value.area_mm2)
        for a,b in zip(polygon,polygon[1:]+polygon[:1]):
            if any(abs(math.dist(a,c.center)-1)<1e-9 and abs(math.dist(b,c.center)-1)<1e-9 for c in value.corners):
                sag=1-math.sqrt(max(0,1-(math.dist(a,b)/2)**2))
                self.assertLessEqual(sag,.01+1e-10)
        with self.assertRaisesRegex(ValueError,'bounded'):fillet.stroke(value,tolerance_mm=1e-8,max_points=12)

    def test_explicit_radius_replaces_builtin_rounded_variant_instead_of_rounding_facets(self):
        for name,corner_count in (('rounded_triangle',3),('rounded_hexagon',6)):
            default=tiles.profiles(name,10,2)[2]
            explicit=tiles.profiles(name,10,2,sharp=True)[2]
            self.assertGreater(len(default[0][1]),corner_count)
            self.assertEqual(len(explicit[0][1]),corner_count)
            settings=PatternSettings(pattern=name,pattern_fillet_mm=.3,pitch_mm=12,web_mm=2,layout_mode='fill')
            layout=build_layout(settings,(0,80,0,60))
            self.assertTrue(layout.cells)
            self.assertTrue(all(len(c.original_polygon_mm or c.polygon_mm)==corner_count for c in layout.cells))

    def test_invalid_or_oversized_radius_never_clamps_and_crossing_contours_fail(self):
        square=((-1,-1),(1,-1),(1,1),(-1,1))
        for r in (0,-1,True,math.nan,math.inf,1,2):
            with self.subTest(r=r),self.assertRaises(ValueError):fillet.profile(square,r)
        star=tuple((math.cos(i*4*math.pi/5),math.sin(i*4*math.pi/5)) for i in range(5))
        with self.assertRaises(ValueError):fillet.profile(star,.1)


if __name__=='__main__':unittest.main()

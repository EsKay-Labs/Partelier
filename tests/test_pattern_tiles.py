"""Polygon-family topology, physical gaps, wrapping and bounded planning."""

from dataclasses import replace
import itertools
import math
import unittest

from Partelier.partelier.tools.patterns import clipping
from Partelier.partelier.tools.patterns.tiles import TILED_PATTERNS, motif, profiles, shifted, dimensions
from Partelier.partelier.tools.patterns.settings import PatternSettings
from Partelier.partelier.tools.patterns.planner import build_layout, build_cells
from test_pattern_fit_layout import opening_distance


class PolygonTileTests(unittest.TestCase):
    def settings(self,pattern,**values):
        return PatternSettings(pattern=pattern,**values)

    def test_periodic_templates_have_no_overlaps_and_tile_the_claimed_area(self):
        for name in TILED_PATTERNS:
            value=motif(name)
            with self.subTest(pattern=name):
                ratio=sum(clipping.area(p) for p in value.polygons)/(value.width*value.height)
                if name not in ('pentagon','octagon'):self.assertAlmostEqual(ratio,1)
                for i,one in enumerate(value.polygons):
                    for dx,dy in itertools.product((-value.width,0,value.width),(-value.height,0,value.height)):
                        for j,two in enumerate(value.polygons):
                            if dx==dy==0 and i==j:continue
                            two=shifted(two,dx,dy);intersection=one
                            for a,b in zip(two,two[1:]+two[:1]):
                                intersection=clipping.halfplane(intersection,a,b)
                                if not intersection:break
                            self.assertLess(clipping.area(intersection),1e-7)

    def test_every_inset_and_rounded_profile_remains_strictly_convex(self):
        for name in TILED_PATTERNS:
            for size,gap in ((5,1.5),(12.5,5),(20,2)):
                with self.subTest(pattern=name,size=size,gap=gap):
                    result=profiles(name,size,gap);self.assertTrue(result)
                    for center,polygon in result[2]:
                        self.assertGreater(clipping.area(polygon),0)
                        for i,a in enumerate(polygon):
                            b,c=polygon[(i+1)%len(polygon)],polygon[(i+2)%len(polygon)]
                            self.assertGreater((b[0]-a[0])*(c[1]-b[1])-(b[1]-a[1])*(c[0]-b[0]),-1e-8)
                        if name.startswith('rounded'):self.assertGreater(len(polygon),10)

    def test_actual_perpendicular_gaps_survive_spreading_and_rotation(self):
        for name in TILED_PATTERNS:
            settings=self.settings(name,layout_mode='balanced',pitch_mm=8,web_mm=2,rotation_deg=17)
            layout=build_layout(settings,(0,80,0,60),max_cells=32)
            with self.subTest(pattern=name):
                self.assertTrue(layout.cells);self.assertLessEqual(layout.cell_count,32)
                for one,two in itertools.combinations(layout.cells,2):
                    if math.dist(one.center_mm,two.center_mm)>one.radius_mm+two.radius_mm+2.1:continue
                    self.assertGreaterEqual(opening_distance(one,two),2-1e-6)

    def test_mixed_patterns_have_distinct_polygon_sizes_and_orientations(self):
        for name in ('trihex','octagon_square','cairo','rhombille'):
            shapes=profiles(name,12.5,5)[2]
            signatures={(len(p),round(max(x for x,y in p)-min(x for x,y in p),5),
                         round(max(y for x,y in p)-min(y for x,y in p),5)) for center,p in shapes}
            self.assertGreater(len(signatures),1,name)

    def test_rounded_variants_are_contained_in_the_sharp_polygons(self):
        for rounded,sharp in (('rounded_triangle','triangle'),):
            one=profiles(sharp,12.5,5)[2];two=profiles(rounded,12.5,5)[2]
            for (ca,pa),(cb,pb) in zip(one,two):
                a=shifted(pa,*ca);b=shifted(pb,*cb)
                self.assertLess(clipping.area(b),clipping.area(a))
                for x,y in b:
                    for p,q in zip(a,a[1:]+a[:1]):
                        self.assertGreaterEqual((q[0]-p[0])*(y-p[1])-(q[1]-p[1])*(x-p[0]),-1e-7)

    def test_auto_size_locks_and_geometry_budgets_apply_to_every_family(self):
        for name in TILED_PATTERNS:
            for locked in (False,True):
                settings=self.settings(name,layout_mode='auto',size_locked=locked,pitch_mm=11,web_mm=2)
                calls=[]
                def accept(cell):calls.append(cell);return 1
                layout=build_layout(settings,(0,150,0,100),accept=accept)
                with self.subTest(pattern=name,locked=locked):
                    self.assertTrue(layout.cells);self.assertLessEqual(layout.cell_count,64)
                    self.assertLessEqual(layout.proposals_evaluated,16)
                    self.assertLessEqual(layout.acceptance_checks,128)
                    self.assertEqual(len(calls),len(set(calls)))
                    if locked:self.assertEqual(layout.cell_size_mm,9)

    def test_density_controls_change_every_family_on_a_large_face(self):
        for name in TILED_PATTERNS:
            layouts=[build_layout(self.settings(name,layout_mode='auto',density=d),(0,300,0,170))
                     for d in ('sparse','balanced','dense')]
            with self.subTest(pattern=name):
                self.assertTrue(all(l.cells for l in layouts))
                self.assertLess(layouts[0].cell_count,layouts[1].cell_count)
                self.assertLess(layouts[1].cell_count,layouts[2].cell_count)

    def test_wrap_repeats_close_without_duplicate_or_missing_cells(self):
        for name in TILED_PATTERNS:
            settings=self.settings(name,layout_mode='auto',web_mm=1.2)
            layout=build_layout(settings,(0,100,0,32),100)
            with self.subTest(pattern=name):
                self.assertTrue(layout.cells)
                self.assertAlmostEqual(round(100/layout.repeat_u_mm)*layout.repeat_u_mm,100)
                self.assertEqual(len(layout.cells),len(set(layout.cells)))

    def test_fixed_and_fill_modes_preserve_the_requested_reference_dimension(self):
        for name,mode,edge in itertools.product(TILED_PATTERNS,('fixed','fill','balanced'),('clip','whole')):
            settings=self.settings(name,layout_mode=mode,edge_mode=edge)
            layout=build_layout(settings,(0,100,0,70))
            with self.subTest(pattern=name,mode=mode,edge=edge):
                self.assertTrue(layout.cells);self.assertEqual(layout.cell_size_mm,12.5)
                self.assertEqual(build_cells(settings,(0,100,0,70)),layout.cells)

    def test_invalid_wrap_rotation_and_empty_regions_are_bounded_refusals(self):
        with self.assertRaisesRegex(ValueError,'180'):
            build_layout(self.settings('cairo',rotation_deg=17),(0,100,0,32),100)
        layout=build_layout(self.settings('triangle',border_mm=100),(0,20,0,20))
        self.assertFalse(layout.cells)

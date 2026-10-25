"""Dense grid phase equivalence, independent material witnesses and hard bounds."""

from dataclasses import replace
import math
import itertools
import random
import unittest
from types import SimpleNamespace as N
from unittest.mock import patch

from Partelier.partelier.tools.patterns.dense_grid import plan,MAX_OPENINGS
from Partelier.partelier.tools.patterns.planner import build_layout
from Partelier.partelier.tools.patterns.settings import PatternSettings


def inside(point,polygon):
    crosses=[(b[0]-a[0])*(point[1]-a[1])-(b[1]-a[1])*(point[0]-a[0]) for a,b in zip(polygon,polygon[1:]+polygon[:1])]
    return min(crosses)>=-1e-9 or max(crosses)<=1e-9


class DenseGridTests(unittest.TestCase):
    def settings(self,**values):
        return PatternSettings(**{'pattern':'grille_cross','layout_mode':'fill','pitch_mm':7,'web_mm':2,'border_mm':3,**values})

    def test_same_opening_phase_and_clipped_profiles_as_existing_small_grid(self):
        for angle,offset in itertools.product((0,15,45,90,180,-30),(0,2,-12)):
            with self.subTest(angle=angle,offset=offset):
                settings=self.settings(rotation_deg=angle,offset_u_mm=offset,offset_v_mm=-offset)
                dense=plan(settings,(-40,40,-30,30))
                old=build_layout(settings,(-40,40,-30,30))
                self.assertEqual(len(dense.layout.cells),len(old.cells))
                for one,two in zip(dense.layout.cells,old.cells):
                    self.assertLess(math.dist(one.center_mm,two.center_mm),1e-7)
                    for point in one.polygon_mm:self.assertLess(min(math.dist(point,q) for q in two.polygon_mm),1e-7)
                    for point in two.polygon_mm:self.assertLess(min(math.dist(point,q) for q in one.polygon_mm),1e-7)
                self.assertEqual(dense.layout.cell_size_mm,5)

    def test_bands_are_exact_complement_of_openings_at_independent_points(self):
        rng=random.Random(812)
        for angle in (0,23,45,90):
            grid=plan(self.settings(rotation_deg=angle,offset_v_mm=1.3),(-40,40,-30,30))
            polygons=[tuple((u+cell.center_mm[0],v+cell.center_mm[1]) for u,v in cell.polygon_mm) for cell in grid.layout.cells]
            for _ in range(500):
                point=(rng.uniform(-37,37),rng.uniform(-27,27))
                opening=any(inside(point,p) for p in polygons)
                rib=any(inside(point,p) for p in grid.bands)
                self.assertNotEqual(opening,rib,(angle,point))

    def test_large_grid_preserves_five_mm_openings_and_two_mm_ribs(self):
        grid=plan(self.settings(border_mm=7),(0,400,0,400))
        self.assertGreater(grid.layout.cell_count,2000)
        self.assertLessEqual(grid.layout.cell_count,MAX_OPENINGS)
        self.assertLess(len(grid.bands),150)
        self.assertEqual(grid.layout.effective_pitch_mm,7)
        self.assertEqual(grid.layout.cell_size_mm,5)

    def test_extreme_requests_refuse_before_unbounded_allocation(self):
        for settings,bounds in ((self.settings(pitch_mm=.1,web_mm=.01),(0,400,0,400)),
                                (self.settings(),(0,10000,0,100)),
                                (self.settings(border_mm=0),(0,400,0,400)),
                                (self.settings(edge_mode='whole'),(0,400,0,400))):
            with self.subTest(settings=settings,bounds=bounds),self.assertRaises(ValueError):plan(settings,bounds)

    def test_trim_guard_keeps_requested_pitch_and_reserves_the_existing_border_margin(self):
        settings=self.settings(rotation_deg=23,offset_v_mm=1.2)
        plain=plan(settings,(-40,40,-30,30))
        guarded=plan(settings,(-40,40,-30,30),trim_margin_mm=.002)
        self.assertEqual(guarded.layout.effective_pitch_mm,7)
        self.assertEqual(guarded.layout.cell_size_mm,5)
        self.assertLess(guarded.opening_area_mm2,plain.opening_area_mm2)
        for cell in guarded.layout.cells:
            for u,v in cell.polygon_mm:
                self.assertGreaterEqual(u+cell.center_mm[0],-36.998-1e-7)
                self.assertLessEqual(u+cell.center_mm[0],36.998+1e-7)
                self.assertGreaterEqual(v+cell.center_mm[1],-26.998-1e-7)
                self.assertLessEqual(v+cell.center_mm[1],26.998+1e-7)

    def test_small_rim_faces_return_empty_layouts(self):
        grid=plan(self.settings(border_mm=7),(0,120,0,3),trim_margin_mm=.002)
        self.assertEqual(grid.layout.cell_count,0)
        self.assertFalse(grid.bands)

    def test_opening_count_has_its_own_bound_even_with_few_rib_tools(self):
        with self.assertRaisesRegex(ValueError,'4096 openings'):
            plan(self.settings(border_mm=7),(0,470,0,470))

    def test_native_budget_refuses_before_any_body_construction(self):
        from Partelier.partelier.tools.patterns import dense_grid,fusion,grilles
        native=N(TemporaryBRepManager=N(get=lambda:object()))
        with patch.object(dense_grid,'MAX_NATIVE_OPENINGS',200),patch.object(fusion,'_api',return_value=(None,native)),patch.object(grilles,'prepare_louver_face'),patch.object(fusion,'SurfaceMap',return_value=N(bounds=(0,400,0,400))),patch.object(fusion,'_copy') as copy:
            with self.assertRaisesRegex(ValueError,'exceeds 200 openings'):
                dense_grid.prepare(None,(object(),),self.settings(border_mm=7),None,(),{},0)
        copy.assert_not_called()

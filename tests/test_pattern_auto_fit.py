"""Visual-layout behavior and work bounds, independent of Fusion."""

from dataclasses import replace
import itertools
import math
import unittest

from Partelier.partelier.tools.patterns.settings import PatternSettings
from Partelier.partelier.tools.patterns.planner import build_layout, _fit_grid
from Partelier.partelier.tools.patterns.auto_fit import MAX_AUTO_PROPOSALS, AUTO_SHORTLIST, DENSITIES
from test_pattern_fit_layout import opening_distance


class AutoFitTests(unittest.TestCase):
    def settings(self, **values):
        return PatternSettings(**{'layout_mode':'auto','web_mm':5,'border_mm':2,**values})

    def test_densities_change_size_and_count_for_all_current_shapes(self):
        for shape in ('hexagon','circle','diamond','square','slot'):
            for edge in ('clip','whole'):
                layouts=[build_layout(self.settings(pattern=shape,edge_mode=edge,density=density),(0,200,0,160))
                         for density in DENSITIES]
                with self.subTest(shape=shape,edge=edge):
                    self.assertTrue(all(layout.cells for layout in layouts))
                    self.assertLess(layouts[0].cell_count,layouts[1].cell_count)
                    self.assertLess(layouts[1].cell_count,layouts[2].cell_count)
                    self.assertGreater(layouts[0].cell_size_mm,layouts[1].cell_size_mm)
                    self.assertGreater(layouts[1].cell_size_mm,layouts[2].cell_size_mm)

    def test_surface_size_changes_the_proposal_without_using_the_seed_size(self):
        settings=self.settings()
        small=build_layout(settings,(0,100,0,80))
        large=build_layout(settings,(0,300,0,240))
        self.assertGreater(large.cell_size_mm,small.cell_size_mm)
        other=build_layout(replace(settings,pitch_mm=1000),(0,300,0,240))
        self.assertEqual(large.cells,other.cells)
        self.assertEqual(large.cell_size_mm,other.cell_size_mm)

    def test_explicit_size_survives_density_and_face_changes(self):
        for density,bounds in itertools.product(DENSITIES,((0,200,0,160),(0,300,0,170))):
            for size in (5,10,20):
                settings=self.settings(density=density,size_locked=True,pitch_mm=size+5)
                layout=build_layout(settings,bounds)
                with self.subTest(density=density,bounds=bounds,size=size):
                    self.assertTrue(layout.cells)
                    self.assertEqual(layout.cell_size_mm,size)
                    self.assertAlmostEqual(max(max(x for x,y in c.polygon_mm)-min(x for x,y in c.polygon_mm)
                                               for c in layout.cells),size)
                    self.assertLessEqual(layout.cell_count,DENSITIES[density][1])

    def test_minimum_gap_border_and_work_budget_for_every_shape(self):
        for shape in ('hexagon','circle','diamond','square','slot'):
            settings=self.settings(pattern=shape)
            layout=build_layout(settings,(0,150,0,90),max_cells=40)
            self.assertTrue(layout.cells)
            self.assertLessEqual(layout.cell_count,40)
            self.assertLessEqual(layout.proposals_evaluated,MAX_AUTO_PROPOSALS)
            for one,two in itertools.combinations(layout.cells,2):
                self.assertGreaterEqual(opening_distance(one,two),settings.web_mm-1e-7)
            for cell in layout.cells:
                for x,y in cell.polygon_mm:
                    self.assertTrue(2-1e-7<=cell.center_mm[0]+x<=148+1e-7)
                    self.assertTrue(2-1e-7<=cell.center_mm[1]+y<=88+1e-7)

    def test_exact_surface_queries_are_shortlisted_and_cached(self):
        calls=[]
        def accept(cell):calls.append(cell);return .6 if cell.center_mm[0]<100 else 0
        layout=build_layout(self.settings(),(0,200,0,160),max_cells=40,accept=accept)
        self.assertTrue(layout.cells)
        self.assertEqual(layout.acceptance_checks,len(calls))
        self.assertEqual(len(calls),len(set(calls)))
        self.assertLessEqual(len(calls),AUTO_SHORTLIST*40)
        self.assertTrue(all(cell.center_mm[0]<100 for cell in layout.cells))

    def test_wrap_closes_and_bounds_opening_curvature_even_on_tall_cylinders(self):
        for height in (50,300):
            for density in DENSITIES:
                settings=self.settings(web_mm=2,density=density)
                layout=build_layout(settings,(0,100,0,height),100)
                with self.subTest(height=height,density=density):
                    self.assertTrue(layout.cells)
                    self.assertAlmostEqual(round(100/layout.pitch_mm)*layout.pitch_mm,100)
                    self.assertLessEqual(layout.cell_size_mm,10.5+1e-7)
                    self.assertLessEqual(layout.cell_count,DENSITIES[density][1])

    def test_symmetric_square_grid_balances_opposite_margins(self):
        layout=build_layout(self.settings(pattern='square'),(0,120,0,80))
        points=[(cell.center_mm[0]+x,cell.center_mm[1]+y) for cell in layout.cells for x,y in cell.polygon_mm]
        self.assertAlmostEqual(min(x for x,y in points),120-max(x for x,y in points))
        self.assertAlmostEqual(min(y for x,y in points),80-max(y for x,y in points))

    def test_offsets_remain_explicit_and_result_is_deterministic(self):
        settings=self.settings()
        bounds=(0,150,0,100)
        self.assertEqual(build_layout(settings,bounds),build_layout(settings,bounds))
        shifted=build_layout(replace(settings,offset_u_mm=1.1,offset_v_mm=2.3),bounds)
        self.assertNotEqual(build_layout(settings,bounds).cells,shifted.cells)

    def test_tiny_faces_and_fully_rejected_regions_allocate_no_extra_work(self):
        calls=[]
        tiny=build_layout(self.settings(border_mm=10),(0,15,0,15),accept=lambda c:calls.append(c))
        self.assertFalse(tiny.cells);self.assertEqual(calls,[])
        empty=build_layout(self.settings(),(0,100,0,80),accept=lambda c:False)
        self.assertFalse(empty.cells)
        self.assertLessEqual(empty.acceptance_checks,AUTO_SHORTLIST*64)

    def test_automatic_openings_do_not_collapse_to_pinholes(self):
        for density in DENSITIES:
            layout=build_layout(self.settings(density=density),(0,100,0,30))
            self.assertTrue(layout.cells)
            self.assertGreaterEqual(layout.cell_size_mm,5-1e-7)

    def test_new_fields_are_strictly_typed(self):
        for values in ({'size_locked':1},{'size_locked':'false'},{'density':'maximum'}):
            with self.assertRaises(ValueError):self.settings(**values)

    def test_fast_interior_path_retains_exact_boundary_polygons(self):
        for shape,period in itertools.product(('hexagon','circle','diamond','square','slot'),(None,100)):
            settings=self.settings(pattern=shape,pitch_mm=11,web_mm=2,offset_u_mm=1.3,offset_v_mm=-.7)
            bounds=(0,100,0,65)
            slow,pitch=_fit_grid(settings,bounds,12.5,period,0,preserve_size=True,spread=True)
            fast,actual=_fit_grid(settings,bounds,12.5,period,0,preserve_size=True,spread=True,fast_clip=True)
            with self.subTest(shape=shape,period=period):
                self.assertEqual(actual,pitch);self.assertEqual(len(fast),len(slow))
                for one,two in zip(slow,fast):
                    self.assertEqual(len(one.polygon_mm),len(two.polygon_mm))
                    for a,b in zip(one.polygon_mm,two.polygon_mm):
                        self.assertAlmostEqual(one.center_mm[0]+a[0],two.center_mm[0]+b[0])
                        self.assertAlmostEqual(one.center_mm[1]+a[1],two.center_mm[1]+b[1])

    def test_fast_path_retains_the_degenerate_fragment_guard(self):
        settings=self.settings(size_locked=True,pitch_mm=5.00001)
        for fast in (False,True):
            cells,_=_fit_grid(settings,(0,20,0,20),10,None,0,preserve_size=True,spread=True,fast_clip=fast)
            self.assertFalse(cells)

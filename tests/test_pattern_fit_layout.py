"""Whole-cell balanced fit, bounded native acceptance and legacy geometry."""

from dataclasses import replace
import hashlib
import json
import math
from types import SimpleNamespace
import unittest

from Partelier.partelier.tools.patterns.settings import PatternSettings
from Partelier.partelier.tools.patterns.planner import (
    build_cells, build_layout, allocate_face_budgets, FIT_SHORTLIST,
)


def envelope(cells):
    points = [(cell.center_mm[0]+du, cell.center_mm[1]+dv)
              for cell in cells for du,dv in cell.polygon_mm]
    return (min(u for u,v in points),max(u for u,v in points),
            min(v for u,v in points),max(v for u,v in points))


def point_segment(point, first, second):
    delta = (second[0]-first[0], second[1]-first[1])
    length = delta[0]**2+delta[1]**2
    ratio = max(0,min(1,((point[0]-first[0])*delta[0]+(point[1]-first[1])*delta[1])/length))
    return math.hypot(point[0]-first[0]-ratio*delta[0], point[1]-first[1]-ratio*delta[1])


def opening_distance(one, two):
    first = tuple((one.center_mm[0]+u,one.center_mm[1]+v) for u,v in one.polygon_mm)
    second = tuple((two.center_mm[0]+u,two.center_mm[1]+v) for u,v in two.polygon_mm)
    return min(point_segment(point,a,b) for polygon,other in ((first,second),(second,first))
               for point in polygon for a,b in zip(other,other[1:]+other[:1]))


class PatternFitLayoutTests(unittest.TestCase):
    def settings(self, **values):
        return PatternSettings(layout_mode='fit', **values)

    def assert_complete_and_balanced(self, layout, bounds, border):
        self.assertTrue(layout.cells)
        low_u,high_u,low_v,high_v = envelope(layout.cells)
        self.assertGreaterEqual(low_u,bounds[0]+border-1e-7)
        self.assertLessEqual(high_u,bounds[1]-border+1e-7)
        self.assertGreaterEqual(low_v,bounds[2]+border-1e-7)
        self.assertLessEqual(high_v,bounds[3]-border+1e-7)
        self.assertAlmostEqual(low_u-bounds[0],bounds[1]-high_u,places=7)
        self.assertAlmostEqual(low_v-bounds[2],bounds[3]-high_v,places=7)

    def test_actual_reported_face_fills_both_axes_with_small_uniform_pitch_change(self):
        settings = self.settings(pitch_mm=40,web_mm=10,border_mm=3)
        before = settings.to_dict()
        layout = build_layout(settings,(0,300,0,169.85))
        self.assert_complete_and_balanced(layout,(0,300,0,169.85),3)
        self.assertLess(abs(layout.effective_pitch_mm/40-1),.15)
        low_u,high_u,low_v,high_v = envelope(layout.cells)
        self.assertGreater((high_u-low_u)/294,.98)
        self.assertGreater((high_v-low_v)/163.85,.98)
        self.assertGreaterEqual(layout.cell_count,26)
        self.assertEqual(layout.requested_pitch_mm,40)
        self.assertEqual(settings.to_dict(),before,'resolved dimensions must not rewrite the request')
        self.assertEqual(layout.pitch_mm,layout.effective_pitch_mm)
        self.assertEqual(build_cells(settings,(0,300,0,169.85)),layout.cells)

    def test_all_shapes_have_complete_centered_cells_at_nonzero_chart_origin(self):
        for pattern in ('hexagon','circle','diamond','square','slot'):
            with self.subTest(pattern=pattern):
                settings=self.settings(pattern=pattern)
                layout=build_layout(settings,(103,157,-71,-32))
                self.assert_complete_and_balanced(layout,(103,157,-71,-32),settings.border_mm)
                self.assertEqual(len({cell.polygon_mm for cell in layout.cells}),1,
                                 'every cell on a face must use one uniform shape')

    def test_rotated_layout_centers_the_actual_pruned_envelope(self):
        for pattern,angle in (('hexagon',27),('square',45),('slot',71)):
            with self.subTest(pattern=pattern,angle=angle):
                settings=self.settings(pattern=pattern,rotation_deg=angle)
                layout=build_layout(settings,(-17,39,11,56))
                self.assert_complete_and_balanced(layout,(-17,39,11,56),settings.border_mm)

    def test_hex_rows_are_individually_centered_and_keep_one_coherent_lattice(self):
        layout=build_layout(self.settings(pitch_mm=40,web_mm=10,border_mm=3),(0,300,0,169.85))
        rows={}
        for cell in layout.cells:rows.setdefault(round(cell.center_mm[1],8),[]).append(cell.center_mm[0])
        counts=[]
        for row in rows.values():
            row.sort();counts.append(len(row))
            self.assertAlmostEqual((row[0]+row[-1])/2,150,places=7)
            for a,b in zip(row,row[1:]):self.assertAlmostEqual(b-a,layout.pitch_mm,places=7)
        self.assertEqual(max(counts)-min(counts),1)
        heights=sorted(rows)
        for a,b in zip(heights,heights[1:]):
            self.assertAlmostEqual(b-a,layout.pitch_mm*math.sqrt(3)/2,places=7)

    def test_minimum_planar_web_is_retained_for_every_neighbor_and_shape(self):
        for pattern in ('hexagon','circle','diamond','square','slot'):
            with self.subTest(pattern=pattern):
                settings=self.settings(pattern=pattern,web_mm=2)
                layout=build_layout(settings,(-16,16,-12,12))
                for index,one in enumerate(layout.cells):
                    for two in layout.cells[index+1:]:
                        self.assertGreaterEqual(opening_distance(one,two),settings.web_mm-1e-7)

    def test_dense_face_adapts_pitch_before_hitting_the_native_cell_limit(self):
        settings=self.settings()
        layout=build_layout(settings,(0,300,0,169.85))
        self.assertGreater(layout.pitch_mm,settings.pitch_mm)
        self.assertLessEqual(layout.cell_count,200)
        self.assertGreater(layout.cell_count,160)
        self.assert_complete_and_balanced(layout,(0,300,0,169.85),settings.border_mm)
        limited=build_layout(settings,(0,300,0,169.85),max_cells=50)
        self.assertLessEqual(limited.cell_count,50)
        self.assertGreater(limited.pitch_mm,layout.pitch_mm)

    def test_narrow_face_can_fit_a_smaller_uniform_cell_without_changing_web(self):
        settings=self.settings(pitch_mm=8,border_mm=0)
        layout=build_layout(settings,(0,100,0,4))
        self.assertLess(layout.pitch_mm,settings.pitch_mm)
        self.assertGreater(layout.pitch_mm,settings.web_mm)
        self.assert_complete_and_balanced(layout,(0,100,0,4),0)
        self.assertLessEqual(layout.cell_count,200)

    def test_native_acceptance_only_evaluates_three_pure_ranked_proposals(self):
        settings=self.settings()
        calls=[]
        def accept(cell):calls.append(cell);return cell.center_mm[0]>=150
        layout=build_layout(settings,(0,300,0,169.85),max_cells=200,accept=accept)
        self.assertTrue(layout.cells)
        self.assertTrue(all(cell.center_mm[0]>=150 for cell in layout.cells))
        self.assertLessEqual(len(calls),FIT_SHORTLIST*200)
        self.assertEqual(len(calls),len({(cell.center_mm,cell.polygon_mm) for cell in calls}),
                         'identical acceptance probes should be reused')

    def test_no_complete_cells_returns_empty_layout_for_small_rim_faces(self):
        settings=self.settings(border_mm=3)
        calls=[]
        layout=build_layout(settings,(0,4,0,100),accept=lambda cell:calls.append(cell) or True)
        self.assertEqual(layout.cells,())
        self.assertEqual(calls,[])
        rejected=build_layout(self.settings(),(0,60,0,40),accept=lambda cell:False)
        self.assertEqual(rejected.cells,())

    def test_manual_offsets_remain_explicit_phase_controls(self):
        settings=self.settings(pattern='square')
        default=build_layout(settings,(0,60,0,40))
        shifted=build_layout(replace(settings,offset_u_mm=1.3,offset_v_mm=-2.1),(0,60,0,40))
        self.assertNotEqual(default.cells,shifted.cells)
        self.assertEqual(settings.offset_u_mm,0)
        for cell in shifted.cells:
            self.assertTrue(all(2-1e-7<=cell.center_mm[0]+u<=58+1e-7 and
                                2-1e-7<=cell.center_mm[1]+v<=38+1e-7 for u,v in cell.polygon_mm))

    def test_periodic_pitch_closes_every_row_and_staggers_with_uniform_spacing(self):
        period=2*math.pi*16
        layout=build_layout(self.settings(web_mm=2),(0,period,0,32),period)
        rows={}
        for cell in layout.cells:rows.setdefault(round(cell.center_mm[1],8),[]).append(cell.center_mm[0])
        count=round(period/layout.pitch_mm)
        self.assertGreaterEqual(count,3)
        self.assertAlmostEqual(count*layout.pitch_mm,period,places=8)
        for row in rows.values():
            row.sort();self.assertEqual(len(row),count)
            gaps=[b-a for a,b in zip(row,row[1:])]+[row[0]+period-row[-1]]
            for gap in gaps:self.assertAlmostEqual(gap,layout.pitch_mm,places=7)
        heights=sorted(rows)
        for a,b in zip(heights,heights[1:]):self.assertAlmostEqual(b-a,layout.pitch_mm*math.sqrt(3)/2,places=7)
        self.assertAlmostEqual(min(heights)-min(point[1] for point in layout.cells[0].polygon_mm),
                               32-max(heights)+max(point[1] for point in layout.cells[0].polygon_mm),places=7)

    def test_periodic_world_chords_pass_the_existing_physical_web_guard(self):
        from Partelier.partelier.tools.patterns.fusion import _check_webs
        for radius,pitch,web,height in ((16,8,2,32),(16,8,1.2,32),(30,12,2,32),(100,40,10,170)):
            with self.subTest(radius=radius,pitch=pitch,web=web):
                period=2*math.pi*radius
                layout=build_layout(self.settings(pitch_mm=pitch,web_mm=web),(0,period,0,height),period)
                def point(u,v):return(radius*math.cos(u/radius),radius*math.sin(u/radius),v)
                mapped=[SimpleNamespace(center=SimpleNamespace(point_mm=point(*cell.center_mm)),
                    world_polygon=tuple(point(cell.center_mm[0]+u,cell.center_mm[1]+v) for u,v in cell.polygon_mm),
                    radius_mm=cell.radius_mm) for cell in layout.cells]
                _check_webs(mapped,web)

    def test_invalid_fit_budgets_bounds_and_periods_are_refused(self):
        for budget in (0,201,True,1.5):
            with self.subTest(budget=budget),self.assertRaises(ValueError):
                build_layout(self.settings(),(0,40,0,40),max_cells=budget)
        for bounds in ((0,0,0,40),(0,float('inf'),0,40),(0,40,0)):
            with self.subTest(bounds=bounds),self.assertRaises(ValueError):build_layout(self.settings(),bounds)
        for period in (0,-1,True,float('nan')):
            with self.subTest(period=period),self.assertRaises(ValueError):
                build_layout(self.settings(),(0,100,0,40),period)
        with self.assertRaises(ValueError):build_layout(self.settings(),(0,100,0,40),99)
        with self.assertRaises(ValueError):build_layout(self.settings(rotation_deg=17),(0,100,0,40),100)

    def test_face_budget_allocation_is_deterministic_and_globally_bounded(self):
        for areas in ((100,), (1,1), (100,100,100), (1,1000000,1), tuple(range(1,101))):
            with self.subTest(faces=len(areas)):
                budgets=allocate_face_budgets(areas)
                self.assertEqual(budgets,allocate_face_budgets(areas))
                self.assertEqual(len(budgets),len(areas))
                self.assertTrue(all(1<=value<=200 for value in budgets))
                self.assertLessEqual(sum(budgets),400)
        self.assertEqual(allocate_face_budgets((100,100,100)),(134,133,133))
        for areas in ((),(0,1),(float('nan'),1),(True,1)):
            with self.subTest(areas=areas),self.assertRaises(ValueError):allocate_face_budgets(areas)

    def test_fixed_layout_keeps_three_pre_change_golden_geometries_bit_exact(self):
        fixtures=(
            ({},(-16,16,-12,12),None,16,'8e423101dc479f222b95ba5da07b1cc059f729c1c466f2d7d3e00f3a9677cf38'),
            ({'rotation_deg':27,'offset_u_mm':1.3,'offset_v_mm':-2.1},(3,58,-12,31),None,44,
             '505e0e6da04edb68d36b17a207a8ced88546f3ee5bebfd53354dafab8057914f'),
            ({'pattern':'circle','offset_u_mm':1.7},(-30,70,2,34),100,60,
             '7cf7297f2e33a308627c43598b63c4593effca0bfccdf2a4d4d695eab9449ef2'))
        for values,bounds,period,count,digest in fixtures:
            settings=PatternSettings(pitch_mm=8,web_mm=1.2,layout_mode='fixed',**values)
            cells=build_cells(settings,bounds,period)
            actual=hashlib.sha256(json.dumps([(cell.center_mm,cell.polygon_mm) for cell in cells],
                                             separators=(',',':')).encode()).hexdigest()
            self.assertEqual(len(cells),count)
            self.assertEqual(actual,digest)
            self.assertEqual(build_layout(settings,bounds,period).cells,cells)

    def test_fixed_native_acceptance_preserves_order_without_new_budget_clipping(self):
        settings=PatternSettings(layout_mode='fixed')
        legacy=build_cells(settings,(0,60,0,40))
        expected=tuple(cell for cell in legacy if cell.center_mm[0]>=30)
        calls=[]
        def accept(cell):calls.append(cell);return cell.center_mm[0]>=30
        layout=build_layout(settings,(0,60,0,40),max_cells=1,accept=accept)
        self.assertEqual(layout.cells,expected)
        self.assertEqual(tuple(calls),legacy)
        self.assertGreater(len(layout.cells),1,'existing recipes retain manual geometry, even above a new fit budget')
        self.assertEqual(layout.pitch_mm,settings.pitch_mm)


if __name__=='__main__':
    unittest.main()

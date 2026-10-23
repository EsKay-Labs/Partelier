"""Partial cells, finite trim capsules and area-preserving convex pieces."""

from dataclasses import replace
import itertools
import math
import unittest

from Partelier.partelier.tools.patterns import clipping
from Partelier.partelier.tools.patterns.planner import build_layout, _polygon
from Partelier.partelier.tools.patterns.settings import PatternSettings
from test_pattern_fit_layout import opening_distance


class PatternClippingTests(unittest.TestCase):
    def test_rectangle_clips_a_half_cell_exactly_without_moving_the_edge(self):
        square=((-5,-5),(5,-5),(5,5),(-5,5))
        clipped=clipping.rectangle(square,(0,20,-20,20))
        self.assertAlmostEqual(clipping.area(clipped),50)
        self.assertEqual(min(x for x,y in clipped),0)

    def test_convex_difference_preserves_area_and_does_not_overlap_pieces(self):
        square=((-10,-10),(10,-10),(10,10),(-10,10))
        hole=((-2,-2),(2,-2),(2,2),(-2,2))
        pieces=clipping.difference(square,hole)
        self.assertAlmostEqual(sum(clipping.area(p) for p in pieces),384)
        for one,two in itertools.combinations(pieces,2):
            intersection=one
            for a,b in zip(two,two[1:]+two[:1]):intersection=clipping.halfplane(intersection,a,b)
            self.assertFalse(intersection)

    def test_finite_boundary_does_not_cut_distant_columns(self):
        polygon=((-5,-20),(5,-20),(5,-10),(-5,-10))
        pieces=clipping.subtract_boundaries(polygon,(((0,1),(0,5),0),),2)
        self.assertEqual(pieces,(polygon,))

    def test_capsule_contains_requested_radius_even_between_angular_vertices(self):
        capsule=clipping.capsule((0,0),(10,0),2)
        for x in (0,3,10):
            for index in range(72):
                a=math.tau*index/72;p=(x+2*math.cos(a),2*math.sin(a))
                self.assertTrue(all((b[0]-a[0])*(p[1]-a[1])-(b[1]-a[1])*(p[0]-a[0])>=-1e-8
                                    for a,b in zip(capsule,capsule[1:]+capsule[:1])))

    def test_merging_convex_parts_removes_seams_but_keeps_holes_and_gaps(self):
        one=((0,0),(10,0),(10,10));two=((0,0),(10,10),(0,10))
        merged=clipping.merge_convex((one,two))
        self.assertEqual(len(merged),1)
        self.assertAlmostEqual(clipping.area(merged[0]),100)
        separated=((11,0),(21,0),(21,10),(11,10))
        self.assertEqual(len(clipping.merge_convex((merged[0],separated))),2)
        square=((-10,-10),(10,-10),(10,10),(-10,10));hole=((-2,-2),(2,-2),(2,2),(-2,2))
        parts=clipping.merge_convex(clipping.difference(square,hole))
        self.assertAlmostEqual(sum(clipping.area(p) for p in parts),384)
        self.assertGreater(len(parts),1)

    def test_closed_convex_hole_offset_keeps_a_border_without_capsule_fragment_growth(self):
        hole=tuple((3.5*math.cos(i*math.tau/64),3.5*math.sin(i*math.tau/64)) for i in range(64))
        expanded=clipping.offset_convex(hole,-2.005)
        self.assertTrue(all(math.hypot(x,y)>5.5 for x,y in expanded))
        cell=((-8,-4),(8,-4),(8,4),(-8,4))
        parts=clipping.merge_convex(clipping.difference(cell,expanded))
        self.assertTrue(parts)
        self.assertLess(len(parts),64)
        for polygon in parts:
            for x,y in polygon:self.assertGreater(math.hypot(x,y),5.49)

    def test_all_shapes_and_layouts_can_retain_partial_cells_at_border(self):
        for shape in ('hexagon','circle','diamond','square','slot'):
            for mode in ('balanced','fit','fill','fixed'):
                with self.subTest(shape=shape,mode=mode):
                    settings=PatternSettings(pattern=shape,layout_mode=mode,pitch_mm=12,web_mm=5,border_mm=2,offset_u_mm=2,offset_v_mm=2)
                    layout=build_layout(settings,(0,43,0,37))
                    self.assertTrue(layout.cells)
                    effective=replace(settings,pitch_mm=layout.pitch_mm) if mode=='fit' else settings
                    full_area=clipping.area(_polygon(effective))
                    self.assertTrue(any(clipping.area(cell.polygon_mm)<full_area*.99 for cell in layout.cells))
                    for cell in layout.cells:
                        for x,y in cell.polygon_mm:
                            self.assertTrue(2-1e-7<=cell.center_mm[0]+x<=41+1e-7)
                            self.assertTrue(2-1e-7<=cell.center_mm[1]+y<=35+1e-7)
                    for one,two in itertools.combinations(layout.cells,2):
                        self.assertGreaterEqual(opening_distance(one,two),5-1e-7)

    def test_clipping_keeps_more_boundary_cells_than_the_legacy_whole_cell_mode(self):
        settings=PatternSettings(layout_mode='fill',pitch_mm=12,web_mm=5)
        clipped=build_layout(settings,(0,43,0,37))
        whole=build_layout(replace(settings,edge_mode='whole'),(0,43,0,37))
        self.assertGreater(clipped.cell_count,whole.cell_count)

    def test_whole_and_clipped_modes_round_trip_and_unknown_edge_mode_refuses(self):
        for mode in ('clip','whole'):
            value=PatternSettings(edge_mode=mode)
            self.assertEqual(PatternSettings.from_dict(value.to_dict()),value)
        with self.assertRaises(ValueError):PatternSettings(edge_mode='unsupported')

"""Analytic full cells and rounded-before-trim edge fragments without Fusion."""

from dataclasses import replace
import math
from types import SimpleNamespace as N
import unittest
from unittest.mock import Mock,patch

from Partelier.partelier.tools.patterns import clipping,fillet,fusion
from Partelier.partelier.tools.patterns.planner import Cell,Layout,_clipped_grid,_polygon,same_polygon
from Partelier.partelier.tools.patterns.settings import PatternSettings
from Partelier.partelier.tools.patterns.tiles import profiles
from Partelier.partelier.tools.patterns.tiled_layout import _grid
from Partelier.partelier.tools.patterns.surfaces import SurfaceSample


SQUARE=((-4.,-4.),(4.,-4.),(4.,4.),(-4.,4.))


def world(cell):return tuple((cell.center_mm[0]+x,cell.center_mm[1]+y) for x,y in cell.polygon_mm)


def recentered(polygon):
    center=tuple(sum(p[i] for p in polygon)/len(polygon) for i in (0,1))
    return Cell(center,tuple((x-center[0],y-center[1]) for x,y in polygon))


class Chart:
    bounds=(-30,30,-30,30)
    period_u_mm=None
    def __init__(self,clip=None):self.clip=clip;self.clip_calls=[];self.samples=[]
    def sample(self,u,v):
        self.samples.append((u,v));return SurfaceSample((u,v,0),(0,0,1),(1,0,0),(0,1,0))
    def accepts(self,*args):return True
    def clipped_cells(self,cell,border):
        self.clip_calls.append(cell)
        return self.clip(cell) if self.clip else (cell,)


class FilletMappingTests(unittest.TestCase):
    def settings(self,**values):return PatternSettings(**{'pattern':'square','pitch_mm':10,'web_mm':2,'border_mm':0,'pattern_fillet_mm':1,**values})

    def mapped(self,cells,settings=None,chart=None):
        settings=settings or self.settings();chart=chart or Chart()
        def layout(*args,**kwargs):
            for cell in cells:kwargs['accept'](cell)
            return Layout(tuple(cells),10,10,settings.layout_mode)
        with patch.object(fusion,'SurfaceMap',return_value=chart),patch.object(fusion,'build_layout',side_effect=layout):
            return fusion._mapped_cells((N(area=100),),settings,_return_layouts=True),chart

    def test_complete_cell_keeps_exact_profile_when_trim_only_recentres_its_identical_outline(self):
        offset=tuple((x+1,y) for x,y in SQUARE)
        cell=Cell((2,3),offset,offset)
        def rebuild(value):
            polygon=world(value);return (recentered(polygon[2:]+polygon[:2]),)
        (mapped,layouts),chart=self.mapped((cell,),chart=Chart(rebuild))
        self.assertEqual(len(mapped),1);self.assertEqual(layouts[0].cell_count,1)
        self.assertIsNotNone(mapped[0].rounded_profile)
        self.assertEqual(len(mapped[0].rounded_profile.corners),4)
        self.assertEqual(len(chart.clip_calls),1,'an unchanged contour must not be stroked/retrimmed')
        self.assertEqual(mapped[0].rounded_profile.radius_mm,1)

    def test_partial_edge_uses_full_original_before_trim_so_tiny_fragments_do_not_limit_radius(self):
        full=Cell((0,0),SQUARE)
        strip=((3.5,-4.),(4.,-4.),(4.,4.),(3.5,4.))
        part=recentered(strip)
        part=replace(part,original_polygon_mm=tuple((x-part.center_mm[0],y-part.center_mm[1]) for x,y in SQUARE))
        def trim(value):
            cut=clipping.halfplane(world(value),(3.5,5),(3.5,-5))
            return (recentered(cut),) if cut else ()
        (mapped,layouts),chart=self.mapped((part,),chart=Chart(trim))
        self.assertEqual(len(mapped),1);self.assertIsNone(mapped[0].rounded_profile)
        self.assertEqual(len(chart.clip_calls),2)
        expected=fillet.stroke(fillet.profile(SQUARE,1))
        expected=clipping.halfplane(expected,(3.5,5),(3.5,-5))
        self.assertAlmostEqual(clipping.area(mapped[0].polygon),clipping.area(expected))
        self.assertEqual(layouts[0].cell_count,1)

    def test_trim_decomposition_has_one_cell_key_and_no_rounding_web_at_internal_seam(self):
        def split(value):
            polygon=world(value)
            return tuple(recentered(part) for part in (
                clipping.halfplane(polygon,(0,-10),(0,10)),
                clipping.halfplane(polygon,(0,10),(0,-10))) if part)
        (mapped,layouts),chart=self.mapped((Cell((0,0),SQUARE),),chart=Chart(split))
        self.assertEqual(len(mapped),2);self.assertEqual(layouts[0].cell_count,1)
        self.assertEqual([cell.cell_key for cell in mapped],[(0,0),(0,0)])
        self.assertTrue(all(cell.rounded_profile is None for cell in mapped))
        expected=fillet.stroke(fillet.profile(SQUARE,1))
        self.assertAlmostEqual(sum(clipping.area(cell.polygon) for cell in mapped),clipping.area(expected))
        self.assertEqual(len(chart.clip_calls),2)

    def test_circle_and_slot_keep_the_existing_profile_and_do_not_invoke_corner_fillets(self):
        for name in ('circle','slot'):
            settings=self.settings(pattern=name);cell=Cell((0,0),_polygon(settings))
            with self.subTest(pattern=name),patch.object(fillet,'profile',side_effect=AssertionError('No-op shapes must not be re-rounded')):
                (mapped,_),chart=self.mapped((cell,),settings)
                self.assertIsNone(mapped[0].rounded_profile);self.assertEqual(len(chart.clip_calls),1)

    def test_rounded_polygon_variants_use_the_requested_radius_on_the_sharp_template(self):
        for name,corners in (('rounded_triangle',3),('rounded_hexagon',6)):
            settings=self.settings(pattern=name,pattern_fillet_mm=.4)
            polygon=_polygon(settings)
            self.assertEqual(len(polygon),corners)
            (mapped,_),_=self.mapped((Cell((0,0),polygon),),settings)
            self.assertEqual(len(mapped[0].rounded_profile.corners),corners)
            self.assertEqual(mapped[0].rounded_profile.radius_mm,.4)

    def test_rounded_asymmetric_opening_has_a_real_interior_first_ray_witness(self):
        # This skinny triangle's old vertex centroid is outside the nearly
        # incircular rounded opening, although it lies inside the sharp triangle.
        polygon=((0.,0.),(20.,0.),(0.,2.))
        center=tuple(sum(p[i] for p in polygon)/3 for i in (0,1))
        local=tuple((x-center[0],y-center[1]) for x,y in polygon)
        radius=2*clipping.area(polygon)/sum(math.dist(a,b) for a,b in zip(polygon,polygon[1:]+polygon[:1]))*.95
        (mapped,_),_=self.mapped((Cell(center,local),),self.settings(pattern='warren',pattern_fillet_mm=radius))
        cell=mapped[0];profile=cell.rounded_profile
        self.assertFalse(fusion._inside_rounded(profile,(0,0)))
        sample=cell.samples[0];delta=fusion._sub(sample.point_mm,cell.center.point_mm)
        projected=(fusion._dot(delta,cell.center.tangent_u),fusion._dot(delta,fusion.hinge._cross(cell.center.tangent_u,cell.center.normal)))
        self.assertTrue(fusion._inside_rounded(profile,projected))
        self.assertNotEqual(sample.point_mm,cell.center.point_mm)

    def test_interior_witness_respects_mirrored_and_skew_surface_chart_directions(self):
        polygon=((0.,0.),(20.,0.),(0.,2.));center=tuple(sum(p[i] for p in polygon)/3 for i in (0,1))
        local=tuple((x-center[0],y-center[1]) for x,y in polygon)
        radius=2*clipping.area(polygon)/sum(math.dist(a,b) for a,b in zip(polygon,polygon[1:]+polygon[:1]))*.9
        for mirrored,skew in ((True,0),(False,.2),(True,.2)):
            chart=Chart()
            def sample(u,v):
                return SurfaceSample((u+skew*v,(-1 if mirrored else 1)*v,0),(0,0,1),(1,0,0),(0,1,0))
            chart.sample=sample
            (mapped,_),_=self.mapped((Cell(center,local),),self.settings(pattern='warren',pattern_fillet_mm=radius),chart)
            cell=mapped[0];delta=fusion._sub(cell.samples[0].point_mm,cell.center.point_mm)
            projected=(delta[0],-delta[1])
            self.assertTrue(fusion._inside_rounded(cell.rounded_profile,projected))

    def test_metadata_only_records_actual_clipping_and_loop_comparison_ignores_start_vertex(self):
        self.assertTrue(same_polygon(SQUARE,SQUARE[2:]+SQUARE[:2]))
        self.assertTrue(same_polygon(SQUARE,tuple(reversed(SQUARE))))
        self.assertFalse(same_polygon(SQUARE,((-3,-4),(4,-4),(4,4),(-4,4))))
        settings=self.settings(layout_mode='fill')
        cells,_=_clipped_grid(settings,(-15,15,-15,15),10,None,0)
        self.assertTrue(any(c.original_polygon_mm is not None for c in cells))
        self.assertTrue(any(c.original_polygon_mm is None for c in cells))
        for cell in cells:
            if cell.original_polygon_mm is not None:self.assertFalse(same_polygon(cell.original_polygon_mm,cell.polygon_mm))
        tiles,_,_=_grid(self.settings(pattern='warren'),(-15,15,-15,15),None,8,1,(0,0),profiles('warren',8,2))
        self.assertTrue(any(c.original_polygon_mm is not None for c in tiles))
        self.assertTrue(any(c.original_polygon_mm is None for c in tiles))

    def test_web_broad_phase_skips_separated_detailed_contours_but_refuses_a_near_gap(self):
        def mapped(x,key=None):
            return N(center=N(point_mm=(x,0,0)),radius_mm=10,cell_key=key,
                     world_polygon=tuple((x+u,v,0) for u,v in ((-1,-1),(1,-1),(1,1),(-1,1))))
        with patch.object(fusion,'_segment_distance',wraps=fusion._segment_distance) as measured:
            fusion._check_webs((mapped(0),mapped(6)),2)
            measured.assert_not_called()
        with self.assertRaisesRegex(ValueError,'reduces the requested web'):
            fusion._check_webs((mapped(0),mapped(3.5)),2)
        # Two fragments of the same original opening share decomposition edges.
        fusion._check_webs((mapped(0,(0,1)),mapped(.5,(0,1))),2)


if __name__=='__main__':unittest.main()

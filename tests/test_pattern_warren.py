"""Surface Warren bands, physical chord widths and coherent wrap repeats."""

from dataclasses import replace
import itertools
import math
import unittest

from Partelier.partelier.tools.patterns import clipping
from Partelier.partelier.tools.patterns.tiles import motif,profiles,shifted
from Partelier.partelier.tools.patterns.settings import PatternSettings
from Partelier.partelier.tools.patterns.planner import Cell,build_layout


def world(cell):return tuple((cell.center_mm[0]+x,cell.center_mm[1]+y) for x,y in cell.polygon_mm)


def intersection_area(one,two):
    polygon=one
    for a,b in zip(two,two[1:]+two[:1]):
        polygon=clipping.halfplane(polygon,a,b)
        if not polygon:break
    return clipping.area(polygon)


def distance(one,two):
    def point_segment(point,a,b):
        dx,dy=b[0]-a[0],b[1]-a[1]
        ratio=max(0,min(1,((point[0]-a[0])*dx+(point[1]-a[1])*dy)/(dx*dx+dy*dy)))
        return math.hypot(point[0]-a[0]-ratio*dx,point[1]-a[1]-ratio*dy)
    return min(point_segment(p,a,b) for points,other in ((one,two),(two,one))
               for p in points for a,b in zip(other,other[1:]+other[:1]))


class WarrenPatternTests(unittest.TestCase):
    def settings(self,**values):
        return PatternSettings(**{'pattern':'warren','pitch_mm':11,'web_mm':1,'border_mm':2,'layout_mode':'fill',**values})

    def test_warren_has_horizontal_chords_alternating_45_degree_diagonals_and_no_posts(self):
        value=motif('warren')
        self.assertEqual((value.width,value.height,len(value.polygons)),(1,1,4))
        self.assertAlmostEqual(sum(clipping.area(p) for p in value.polygons),1)
        signatures=[]
        for polygon in value.polygons:
            self.assertEqual(len(polygon),3)
            width=max(x for x,y in polygon)-min(x for x,y in polygon)
            height=max(y for x,y in polygon)-min(y for x,y in polygon)
            self.assertAlmostEqual(width/height,2)
            slopes=[]
            for a,b in zip(polygon,polygon[1:]+polygon[:1]):
                self.assertGreater(abs(b[0]-a[0]),1e-8,'Warren bands must not add vertical posts')
                slopes.append(round((b[1]-a[1])/(b[0]-a[0]),8))
            self.assertEqual(sorted(slopes),[-1,0,1]);signatures.append(polygon)
        self.assertNotEqual(value.polygons,motif('triangle').polygons)

    def test_inset_profiles_keep_requested_width_and_perpendicular_gap_at_every_chord_and_diagonal(self):
        size,gap=12,1.5
        unit_u,unit_v,shapes=profiles('warren',size,gap)
        for center,polygon in shapes:
            self.assertAlmostEqual(max(x for x,y in polygon)-min(x for x,y in polygon),size)
            self.assertAlmostEqual((max(y for x,y in polygon)-min(y for x,y in polygon))*2,size)
        openings=[shifted(p,*c) for c,p in shapes]
        smallest=math.inf
        for i,one in enumerate(openings):
            for dx,dy in itertools.product((-unit_u,0,unit_u),(-unit_v,0,unit_v)):
                for j,polygon in enumerate(openings):
                    if i==j and dx==dy==0:continue
                    two=shifted(polygon,dx,dy)
                    self.assertLess(intersection_area(one,two),1e-7)
                    separation=distance(one,two);self.assertGreaterEqual(separation,gap-1e-7)
                    smallest=min(smallest,separation)
        self.assertAlmostEqual(smallest,gap)

    def test_full_cylinder_repeat_closes_the_seam_without_duplicates_or_a_vertical_post_column(self):
        period=96;settings=self.settings()
        layout=build_layout(settings,(0,period,0,36),period)
        self.assertTrue(layout.cells);self.assertEqual(len(layout.cells),len(set(layout.cells)))
        self.assertAlmostEqual(round(period/layout.repeat_u_mm)*layout.repeat_u_mm,period)
        seam_checks=0
        for one,two in itertools.combinations(layout.cells,2):
            for displacement in (0,-period,period):
                other=Cell((two.center_mm[0]+displacement,two.center_mm[1]),two.polygon_mm)
                if math.dist(one.center_mm,other.center_mm)>one.radius_mm+other.radius_mm+settings.web_mm+.01:continue
                a,b=world(one),world(other)
                self.assertLess(intersection_area(a,b),1e-6)
                self.assertGreaterEqual(distance(a,b),settings.web_mm-1e-6)
                if displacement:seam_checks+=1
        self.assertGreater(seam_checks,0)
        # Both rotationally supported directions retain exact complete repeats.
        turned=build_layout(replace(settings,rotation_deg=180),(0,period,0,36),period)
        self.assertAlmostEqual(round(period/turned.repeat_u_mm)*turned.repeat_u_mm,period)
        with self.assertRaisesRegex(ValueError,'180'):
            build_layout(replace(settings,rotation_deg=45),(0,period,0,36),period)

    def test_clip_and_whole_edges_respect_border_and_whole_cells_keep_full_triangles(self):
        bounds=(0,80,0,45);settings=self.settings(pitch_mm=15,web_mm=2,border_mm=3)
        clipped=build_layout(settings,bounds);whole=build_layout(replace(settings,edge_mode='whole'),bounds)
        self.assertTrue(clipped.cells);self.assertTrue(whole.cells)
        self.assertGreaterEqual(clipped.cell_count,whole.cell_count)
        self.assertTrue(any(len(c.polygon_mm)!=3 or clipping.area(c.polygon_mm)<169/4-1e-7 for c in clipped.cells))
        for cell in whole.cells:self.assertEqual(len(cell.polygon_mm),3)
        for cell in clipped.cells:
            for x,y in world(cell):
                self.assertGreaterEqual(x,3-1e-7);self.assertLessEqual(x,77+1e-7)
                self.assertGreaterEqual(y,3-1e-7);self.assertLessEqual(y,42+1e-7)

    def test_auto_fit_density_locked_size_and_acceptance_are_bounded(self):
        counts=[]
        for density in ('sparse','balanced','dense'):
            settings=self.settings(layout_mode='auto',density=density)
            layout=build_layout(settings,(0,180,0,80));counts.append(layout.cell_count)
            self.assertTrue(layout.cells);self.assertLessEqual(layout.proposals_evaluated,16)
            self.assertLessEqual(layout.cell_count,128)
        self.assertEqual(counts,sorted(set(counts)))
        settings=self.settings(layout_mode='auto',size_locked=True)
        accepted=[]
        layout=build_layout(settings,(0,180,0,80),accept=lambda cell:accepted.append(cell) or 1)
        self.assertEqual(layout.cell_size_mm,10)
        self.assertLessEqual(layout.acceptance_checks,128)
        self.assertEqual(len(accepted),len(set(accepted)))


if __name__=='__main__':unittest.main()

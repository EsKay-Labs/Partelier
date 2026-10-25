"""All bounded rectangular side combinations and their continuous print leads."""

import math
from types import SimpleNamespace
import unittest
from Partelier.partelier.tools.details import planner


FRAME=SimpleNamespace(origin_mm=(0.,0.,0.),x_axis=(1.,0.,0.),y_axis=(0.,1.,0.),z_axis=(0.,0.,1.))


class SelectedLipTests(unittest.TestCase):
    def test_every_mask_preserves_exact_side_membership_and_cyclic_adjacency(self):
        for mask in range(1,16):
            runs=planner.side_runs(mask)
            self.assertEqual(sorted(i for run in runs for i in run),[i for i in range(4) if mask&(1<<i)])
            for run in runs:
                self.assertTrue(all(b==(a+1)%4 for a,b in zip(run,run[1:])))
            if mask!=15:
                self.assertEqual(len(runs),2 if mask in (5,10) else 1)
        self.assertEqual(planner.side_runs(9),((3,0),))
        for mask in (0,16,True,1.0):
            with self.assertRaises(ValueError):planner.side_runs(mask)

    def test_joined_runs_have_exact_strip_area_without_internal_chamfer_boundaries(self):
        bounds=(0,60,0,40);inset=.8;width=1.2
        lengths=(60-2*inset,40-2*inset)*2
        for mask in range(1,15):
            polygons=planner.lip_polygons(bounds,inset,width,mask)
            expected=sum(width*(lengths[i]-width) for i in range(4) if mask&(1<<i))
            self.assertAlmostEqual(sum(planner.polygon_area(p) for p in polygons),expected)
            for run,polygon in zip(planner.side_runs(mask),polygons):
                self.assertEqual(len(polygon),2*(len(run)+1))
        with self.assertRaises(ValueError):planner.lip_polygons(bounds,inset,width,15)
        with self.assertRaises(ValueError):planner.lip_polygons((0,3,0,3),1,1,3)

    def test_every_run_has_uniform_normal_clearance_including_diagonal_ends(self):
        for mask in range(1,15):
            for polygon in planner.lip_polygons((0,60,0,40),.8,1.2,mask):
                for distance in (.2,-.25,0):
                    offset=planner.offset_polygon(polygon,distance)
                    for i,(one,two) in enumerate(zip(polygon,polygon[1:]+polygon[:1])):
                        dx,dz=two[0]-one[0],two[1]-one[1]
                        for point in (offset[i],offset[(i+1)%len(offset)]):
                            actual=(dx*(point[1]-one[1])-dz*(point[0]-one[0]))/math.hypot(dx,dz)
                            self.assertAlmostEqual(actual,distance)
                    a,b=planner.polygon_area(polygon),planner.polygon_area(offset)
                    if distance:self.assertTrue(b<a if distance>0 else b>a)
                    else:self.assertAlmostEqual(a,b)

    def test_continuous_concave_lofts_have_one_cap_and_closed_shared_edges(self):
        for mask in range(1,15):
            for polygon in planner.lip_polygons((0,60,0,40),.8,1.2,mask):
                top=planner.offset_polygon(polygon,.2)
                for upper,low,high in ((polygon,-.15,2.3),(top,2.3,2.5)):
                    points,faces,volume=planner.lip_loft(FRAME,polygon,upper,low,high)
                    self.assertEqual(len(points),2*len(polygon))
                    self.assertEqual(len(faces),len(polygon)+2)
                    self.assertGreater(volume,0)
                    edges={}
                    for face in faces:
                        self.assertEqual(len(face),1)
                        loop=face[0]
                        for a,b in zip(loop,loop[1:]+loop[:1]):edges.setdefault(tuple(sorted((a,b))),[]).append(a>b)
                    self.assertTrue(all(sorted(directions)==[False,True] for directions in edges.values()))
                    if upper==polygon:self.assertAlmostEqual(volume,planner.polygon_area(polygon)*(high-low))

    def test_collapsing_leads_and_invalid_lofts_are_refused(self):
        polygon=planner.lip_polygons((0,60,0,40),.8,1.2,3)[0]
        for distance in (.61,20,math.nan):
            with self.assertRaises(ValueError):planner.offset_polygon(polygon,distance)
        for low,high in ((2,2),(3,2),(0,math.inf)):
            with self.assertRaises(ValueError):planner.lip_loft(FRAME,polygon,polygon,low,high)
        top=list(polygon);top[0]=(top[0][0]+.1,top[0][1]+.2)
        with self.assertRaises(ValueError):planner.lip_loft(FRAME,polygon,top,0,1)


if __name__=='__main__':unittest.main()

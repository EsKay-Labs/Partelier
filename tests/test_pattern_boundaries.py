"""Finite trim boundaries, conservative curved strokes and central coverage."""

import math
from types import ModuleType, SimpleNamespace as N
import unittest
from unittest.mock import patch

from Partelier.partelier.tools.patterns import surfaces
from Partelier.partelier.tools.patterns.planner import build_cells
from Partelier.partelier.tools.patterns.settings import PatternSettings


def point(x,y,z=0):
    return N(x=x,y=y,z=z)


class Collection:
    def __init__(self,values):self.values=values;self.count=len(values)
    def item(self,index):return self.values[index]


class LineEvaluator:
    def __init__(self,one,two):
        self.one=one;self.two=two;self.extents_calls=0;self.point_calls=0
    def getParameterExtents(self):
        self.extents_calls+=1
        return True,2.0,5.0
    def getPointAtParameter(self,value):
        self.point_calls+=1
        t=(value-2)/3
        return True,point(*(a+t*(b-a) for a,b in zip(self.one,self.two)))
    def getStrokes(self,*args):raise AssertionError('Lines must use exact bounded endpoints.')


class ArcEvaluator:
    def __init__(self,start=math.pi/2,end=math.pi):
        self.start=start;self.end=end;self.stroke_calls=[]
    def getParameterExtents(self):return True,self.start,self.end
    def getStrokes(self,start,end,tolerance):
        self.stroke_calls.append((start,end,tolerance))
        count=max(1,math.ceil((end-start)/(2*math.acos(1-tolerance/.1))))
        return True,[point(.1*math.cos(start+(end-start)*i/count),
                           .1*math.sin(start+(end-start)*i/count)) for i in range(count+1)]


def edge(evaluator,kind='line'):
    return N(evaluator=evaluator,geometry=kind,isDegenerate=False,coEdges=Collection([]))


CORE=N(Line3D=N(cast=lambda geometry:geometry if geometry=='line' else None))


class FiniteBoundaryTests(unittest.TestCase):
    def test_short_vertical_edge_does_not_exclude_distant_column(self):
        boundary=surfaces._boundary_from_edge(edge(LineEvaluator((.5,0,0),(.5,.5,0))),CORE)
        self.assertAlmostEqual(boundary.distance_mm((5,-150,0)),150)
        self.assertTrue(boundary.clears((5,-150,0),20))
        self.assertFalse(boundary.clears((5,2,0),.1))
        self.assertEqual(boundary.tolerance_mm,0)

    def test_line_projection_clamps_to_both_finite_endpoints(self):
        boundary=surfaces._boundary_from_edge(edge(LineEvaluator((0,0,0),(0,1,0))),CORE)
        self.assertAlmostEqual(boundary.distance_mm((3,-4,0)),5)
        self.assertAlmostEqual(boundary.distance_mm((3,14,0)),5)
        self.assertAlmostEqual(boundary.distance_mm((3,5,0)),3)
        self.assertFalse(boundary.clears((3,-4,0),5.01))
        self.assertTrue(boundary.clears((3,-4,0),4.99))

    def test_trimmed_arc_never_uses_missing_circle_quadrants(self):
        evaluator=ArcEvaluator()
        boundary=surfaces._boundary_from_edge(edge(evaluator,'arc'),CORE)
        actual=math.sqrt(5)
        self.assertGreaterEqual(boundary.distance_mm((2,0,0)),actual-surfaces.TRIM_TOLERANCE_MM-1e-12)
        self.assertLessEqual(boundary.distance_mm((2,0,0)),actual)
        self.assertTrue(boundary.clears((2,0,0),2))
        self.assertFalse(boundary.clears((2,0,0),2.24))
        self.assertEqual(evaluator.stroke_calls,[(math.pi/2,math.pi,surfaces.TRIM_TOLERANCE_MM/10)])

    def test_closed_curved_boundary_retains_conservative_hole_margin(self):
        boundary=surfaces._boundary_from_edge(edge(ArcEvaluator(0,2*math.pi),'circle'),CORE)
        self.assertLessEqual(boundary.distance_mm((0,0,0)),1)
        self.assertGreater(boundary.distance_mm((0,0,0)),.989)
        self.assertTrue(boundary.clears((0,0,0),.98))
        self.assertFalse(boundary.clears((0,0,0),.999))

    def test_invalid_unbounded_or_unreadable_curves_are_refused(self):
        failures=(N(getParameterExtents=lambda:(False,0,1)),
                  N(getParameterExtents=lambda:(True,0,float('inf'))),
                  N(getParameterExtents=lambda:(True,2,1)),
                  N(getParameterExtents=lambda:(True,0,1),getStrokes=lambda *args:(False,[])))
        for evaluator in failures:
            with self.subTest(evaluator=evaluator),self.assertRaises(ValueError):
                surfaces._boundary_from_edge(edge(evaluator,'curve'),CORE)

    def test_non_finite_or_collapsed_line_and_unbounded_stroke_budget_are_refused(self):
        for evaluator in (LineEvaluator((0,0,0),(float('nan'),1,0)),LineEvaluator((0,0,0),(0,0,0))):
            with self.assertRaises(ValueError):surfaces._boundary_from_edge(edge(evaluator),CORE)
        with patch.object(surfaces,'MAX_BOUNDARY_POINTS',3),self.assertRaisesRegex(ValueError,'complex'):
            surfaces._boundary_from_edge(edge(ArcEvaluator(0,2*math.pi),'curve'),CORE)


PROFILE=((-50,-40),(50,-40),(50,0),(30,0),(30,5),(20,5),(20,0),(5,0),
         (5,5),(-5,5),(-5,0),(-20,0),(-20,5),(-30,5),(-30,0),(-50,0))


class PlaneEvaluator:
    def __init__(self,hole=False):self.hole=hole
    def getParameterAtPoint(self,p):return True,point(p.x,p.y)
    def getFirstDerivative(self,p):return True,point(1,0,0),point(0,1,0)
    def getNormalAtParameter(self,p):return True,point(0,0,1)
    def getPointAtParameter(self,p):return True,point(p.x,p.y)
    def getParamAnomaly(self):return True,[0],[0],[],[],[False,False]
    def parametricRange(self):return N(minPoint=point(-5,-4),maxPoint=point(5,.5))
    def isParameterOnFace(self,p):
        x,y=p.x*10,p.y*10
        inside=(-50<=x<=50 and -40<=y<=0 or
                any(a<=x<=b and 0<=y<=5 for a,b in ((-30,-20),(-5,5),(20,30))))
        return inside and not(self.hole and -5<x<5 and -25<y<-15)


class SurfaceBoundaryTests(unittest.TestCase):
    def chart(self,hole=False):
        core=ModuleType('adsk.core');adsk=ModuleType('adsk');adsk.core=core
        core.Point2D=N(create=lambda x,y:point(x,y))
        core.Point3D=N(create=lambda x,y,z:point(x,y,z))
        core.Plane=N(cast=lambda geometry:geometry if geometry=='plane' else None)
        core.Cylinder=N(cast=lambda geometry:None)
        core.Line3D=CORE.Line3D
        def forbidden():raise AssertionError('Finite trims must not call native support-curve measurements.')
        core.Application=N(get=forbidden)
        outlines=[PROFILE]
        if hole:outlines.append(((-5,-25),(5,-25),(5,-15),(-5,-15)))
        edges=[]
        for outline in outlines:
            for a,b in zip(outline,outline[1:]+outline[:1]):
                edges.append(edge(LineEvaluator((a[0]/10,a[1]/10,0),(b[0]/10,b[1]/10,0))))
        face=N(geometry='plane',evaluator=PlaneEvaluator(hole),pointOnFace=point(0,-3),edges=Collection(edges))
        modules=patch.dict('sys.modules',{'adsk':adsk,'adsk.core':core})
        modules.start();self.addCleanup(modules.stop)
        return surfaces.SurfaceMap(face),edges

    def test_tabs_leave_central_lower_panel_available_while_real_borders_remain(self):
        chart,_=self.chart()
        self.assertTrue(chart.accepts(0,10,4,2),'Point is20mm below short tabedges, not on their infinite extensions.')
        self.assertFalse(chart.accepts(48,10,1,2),'The actual outside edge still needs its border.')
        self.assertFalse(chart.accepts(10,28,1,2),'The real top notch boundary remains protected.')

    def test_true_inner_hole_boundaries_remain_protected(self):
        chart,_=self.chart(hole=True)
        self.assertFalse(chart.accepts(0,10,1,2))
        self.assertFalse(chart.accepts(7,10,1,2))
        self.assertTrue(chart.accepts(12,10,1,2))

    def test_partial_cells_clip_around_real_notches_and_holes_with_a_solid_border(self):
        chart,_=self.chart(hole=True)
        settings=PatternSettings(layout_mode='fill',pitch_mm=14,web_mm=5,border_mm=2)
        from Partelier.partelier.tools.patterns.planner import build_layout
        layout=build_layout(settings,chart.bounds)
        fragments=[part for cell in layout.cells for part in chart.clipped_cells(cell,2)]
        self.assertTrue(fragments)
        self.assertTrue(any(not chart.accepts(*part.center_mm,part.radius_mm,2) for part in fragments),
                        'Clipped polygons may safely occupy the old enclosing-disk exclusion region.')
        for part in fragments:
            for x,y in part.polygon_mm:
                sample=chart.sample(part.center_mm[0]+x,part.center_mm[1]+y)
                self.assertTrue(all(boundary.clears(sample.point_mm,2-1e-6) for boundary in chart._boundaries))

    def test_large_cell_over_several_notches_has_bounded_convex_fragments(self):
        chart,_=self.chart()
        from Partelier.partelier.tools.patterns.planner import build_layout
        settings=PatternSettings(layout_mode='fill',pitch_mm=42,web_mm=5,offset_u_mm=2,offset_v_mm=2)
        layout=build_layout(settings,chart.bounds)
        parts=[part for cell in layout.cells for part in chart.clipped_cells(cell,2)]
        self.assertTrue(parts)
        self.assertLess(len(parts),96)
        for part in parts:
            for x,y in part.polygon_mm:
                sample=chart.sample(part.center_mm[0]+x,part.center_mm[1]+y)
                self.assertTrue(all(boundary.clears(sample.point_mm,2-1e-6) for boundary in chart._boundaries))

    def test_planar_clearance_proof_avoids_redundant_ring_evaluations(self):
        chart,_=self.chart(hole=True)
        with patch.object(chart,'sample',wraps=chart.sample) as sample:
            self.assertTrue(chart.accepts(12,10,1,2))
            self.assertEqual(sample.call_count,1)
            self.assertFalse(chart.accepts(7,10,1,2),'The actual inner-hole border still excludes the disk.')
            self.assertEqual(sample.call_count,2)

    def test_nonplanar_charts_retain_ring_orientation_checks(self):
        chart,_=self.chart()
        chart.kind='general'
        with patch.object(chart,'sample',wraps=chart.sample) as sample:
            self.assertTrue(chart.accepts(0,10,4,2))
            self.assertEqual(sample.call_count,25)

    def test_boundaries_are_evaluated_once_per_chart(self):
        chart,edges=self.chart()
        before=[(item.evaluator.extents_calls,item.evaluator.point_calls) for item in edges]
        for _ in range(3):self.assertTrue(chart.accepts(0,10,4,2))
        self.assertEqual(before,[(item.evaluator.extents_calls,item.evaluator.point_calls) for item in edges])
        self.assertTrue(all(value==(1,2) for value in before))

    def test_pattern_cells_cover_middle_below_all_three_top_tabs(self):
        chart,_=self.chart()
        settings=PatternSettings(pitch_mm=8,web_mm=1.2,border_mm=2,layout_mode='fixed',edge_mode='whole')
        accepted=[chart.sample(*cell.center_mm).point_mm for cell in
            build_cells(settings,chart.bounds,period_u_mm=chart.period_u_mm)
            if chart.accepts(*cell.center_mm,cell.radius_mm,settings.border_mm)]
        self.assertGreater(len(accepted),30)
        self.assertGreater(sum(abs(x)<30 and y<-10 for x,y,z in accepted),20)
        self.assertTrue(any(x<0 for x,y,z in accepted))
        self.assertTrue(any(x>0 for x,y,z in accepted))


if __name__=='__main__':unittest.main()

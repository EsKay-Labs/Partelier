"""Physical chart layouts, seam closure, finite budgets and typed settings."""

from dataclasses import replace
import math
from types import SimpleNamespace as NS, ModuleType
import unittest
from unittest.mock import patch

from Partelier.partelier.tools.patterns.settings import PatternSettings
from Partelier.partelier.tools.patterns.planner import build_cells
from Partelier.partelier.tools.patterns.surfaces import SurfaceMap


class PatternSettingsTests(unittest.TestCase):
    def test_full_settings_round_trip_all_shapes_and_actions(self):
        for pattern in ('hexagon','circle','diamond','square','slot'):
            for mode in ('through','engrave','emboss'):
                value=PatternSettings(pattern=pattern,mode=mode,rotation_deg=-30,offset_u_mm=-2)
                self.assertEqual(PatternSettings.from_dict(value.to_dict()),value)
        self.assertEqual(len(PatternSettings().to_dict()),10)

    def test_invalid_dimensions_modes_and_partial_snapshots_are_refused(self):
        for values in ({'pitch_mm':0},{'web_mm':8},{'depth_mm':-1},{'border_mm':-1},
                       {'pitch_mm':True},{'rotation_deg':float('nan')},{'mode':'bad'},
                       {'selection_scope':'mesh'},{'offset_u_mm':float('inf')},
                       {'pitch_mm':10**1000}):
            with self.subTest(values=values),self.assertRaises(ValueError):PatternSettings(**values)
        with self.assertRaises(ValueError):PatternSettings.from_dict({'pitch_mm':8})


class PatternLayoutTests(unittest.TestCase):
    def test_hexagon_web_is_the_distance_between_adjacent_opening_flats(self):
        values=PatternSettings()
        cells=build_cells(values,(-24,24,-24,24))
        apothem=max(x for x,y in cells[0].polygon_mm)
        self.assertAlmostEqual(values.pitch_mm-2*apothem,values.web_mm)
        self.assertAlmostEqual(cells[0].radius_mm,(values.pitch_mm-values.web_mm)/math.sqrt(3))

    def test_cylinder_rows_close_without_duplicate_or_narrower_seam_spacing(self):
        values=PatternSettings(pitch_mm=8)
        cells=build_cells(values,(0,100,-20,20),100)
        rows={}
        for cell in cells:rows.setdefault(round(cell.center_mm[1],8),[]).append(cell.center_mm[0])
        for row in rows.values():
            row.sort();self.assertEqual(len(row),12);self.assertEqual(len(set(row)),12)
            steps=[b-a for a,b in zip(row,row[1:])]+[100-row[-1]+row[0]]
            self.assertTrue(all(step>=8-1e-7 for step in steps))
            self.assertAlmostEqual(min(steps),max(steps))

    def test_rotation_applies_to_centres_as_well_as_openings(self):
        values=PatternSettings(pattern='square',rotation_deg=30)
        cells=build_cells(values,(-25,25,-25,25))
        distances=[math.dist(cells[10].center_mm,other.center_mm) for other in cells if other!=cells[10]]
        self.assertAlmostEqual(min(distances),values.pitch_mm)
        self.assertTrue(all(-25<=c.center_mm[0]<25 and -25<=c.center_mm[1]<=25 for c in cells))

    def test_unsafe_wrap_rotation_and_unbounded_density_are_refused(self):
        with self.assertRaisesRegex(ValueError,'multiples'):
            build_cells(PatternSettings(rotation_deg=15),(0,100,0,40),100)
        with self.assertRaisesRegex(ValueError,'dense'):
            build_cells(PatternSettings(pitch_mm=.1,web_mm=.01),(0,100,0,100))
        with self.assertRaises(ValueError):build_cells(PatternSettings(),(0,float('inf'),0,10))

    def test_offsets_are_signed_and_periodic_not_empty_shifts(self):
        a=build_cells(PatternSettings(offset_u_mm=-2),(0,40,0,40))
        b=build_cells(PatternSettings(offset_u_mm=6),(0,40,0,40))
        self.assertEqual(a,b)


class Collection:
    def __init__(self,values):self.values=values;self.count=len(values)
    def item(self,index):return self.values[index]


def point(x,y,z=0):return NS(x=x,y=y,z=z)


class Evaluator:
    def __init__(self,kind):self.kind=kind
    def getParameterAtPoint(self,p):return True,point(math.pi,0) if self.kind=='cylinder' else point(0,0)
    def getFirstDerivative(self,p):
        if self.kind=='cylinder':return True,point(-2*math.sin(p.x),2*math.cos(p.x),0),point(0,0,1)
        return True,point(1,0,0),point(0,1,0)
    def parametricRange(self):
        return NS(minPoint=point(0,-2),maxPoint=point(2*math.pi,2)) if self.kind=='cylinder' else NS(minPoint=point(-2,-2),maxPoint=point(2,2))
    def getParamAnomaly(self):return True,[2*math.pi if self.kind=='cylinder' else 0],[],[],[],[False,False]
    def isParameterOnFace(self,p):return (-2<=p.y<=2 and (0<=p.x<=2*math.pi if self.kind=='cylinder' else -2<=p.x<=2))
    def getPointAtParameter(self,p):return (True,point(2*math.cos(p.x),2*math.sin(p.x),p.y)) if self.kind=='cylinder' else (True,point(p.x,p.y,0))
    def getNormalAtParameter(self,p):return (True,point(math.cos(p.x),math.sin(p.x),0)) if self.kind=='cylinder' else (True,point(0,0,1))


class SurfaceChartTests(unittest.TestCase):
    def chart(self,kind):
        core=ModuleType('adsk.core');adsk=ModuleType('adsk');adsk.core=core
        core.Point2D=NS(create=lambda x,y:point(x,y))
        core.Point3D=NS(create=point)
        core.Plane=NS(cast=lambda value:value if kind=='plane' else None)
        core.Cylinder=NS(cast=lambda value:value if kind.startswith('cylinder') else None)
        core.Application=NS(get=lambda:NS(measureManager=NS(measureMinimumDistance=lambda p,e:NS(value=abs(p.z-e.z)))))
        evaluator=Evaluator(kind)
        if kind=='cylinder_v':
            base=Evaluator('cylinder')
            class SwappedEvaluator:
                def getParameterAtPoint(self,p):return True,point(0,math.pi)
                def getParamAnomaly(self):return True,[0],[2*math.pi],[],[],[False,False]
                def parametricRange(self):return NS(minPoint=point(-2,0),maxPoint=point(2,2*math.pi))
                def getFirstDerivative(self,p):
                    ok,du,dv=base.getFirstDerivative(point(p.y,p.x));return ok,dv,du
                def isParameterOnFace(self,p):return base.isParameterOnFace(point(p.y,p.x))
                def getPointAtParameter(self,p):return base.getPointAtParameter(point(p.y,p.x))
                def getNormalAtParameter(self,p):return base.getNormalAtParameter(point(p.y,p.x))
            evaluator=SwappedEvaluator()
        face=NS(evaluator=evaluator,pointOnFace=point(0,0),geometry=object(),edges=Collection([]))
        seam=NS(isDegenerate=False,coEdges=Collection([NS(loop=NS(face=face)),NS(loop=NS(face=face))]))
        if kind.startswith('cylinder'):
            rims=[NS(z=z,isDegenerate=False,coEdges=Collection([])) for z in (-2,2)]
            face.edges=Collection(rims+[seam])
        modules=patch.dict('sys.modules',{'adsk':adsk,'adsk.core':core});modules.start();self.addCleanup(modules.stop)
        return SurfaceMap(face)

    def test_cylindrical_chart_is_arc_length_and_periodic_without_seam_border(self):
        chart=self.chart('cylinder');self.assertAlmostEqual(chart.period_u_mm,40*math.pi)
        a=chart.sample(0,0);b=chart.sample(chart.period_u_mm,0)
        self.assertLess(math.dist(a.point_mm,b.point_mm),1e-7)
        self.assertTrue(chart.accepts(chart.bounds[1]-.1,0,2,2))
        self.assertFalse(chart.accepts(0,18,2,2))
        self.assertEqual(len(chart._edges),2)

    def test_plane_chart_converts_native_centimetres_to_millimetres(self):
        chart=self.chart('plane')
        self.assertEqual(chart.bounds,(-20,20,-20,20))
        self.assertEqual(chart.sample(5,7).point_mm,(5,7,0))
        self.assertTrue(chart.accepts(0,0,3,2))
        self.assertFalse(chart.accepts(19,0,3,2))

    def test_native_periodic_v_is_normalized_to_the_same_arc_length_chart(self):
        original=self.chart('cylinder')
        swapped=self.chart('cylinder_v')
        self.assertEqual(original.bounds,swapped.bounds)
        self.assertAlmostEqual(original.period_u_mm,swapped.period_u_mm)
        for u,v in ((0,0),(5,7),(original.bounds[1]-.1,-5)):
            self.assertEqual(original.sample(u,v),swapped.sample(u,v))
            self.assertEqual(original.accepts(u,v,2,2),swapped.accepts(u,v,2,2))


if __name__=='__main__':unittest.main()

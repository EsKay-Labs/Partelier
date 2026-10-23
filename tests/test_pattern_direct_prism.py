"""Direct pattern-prism topology, rigid placement and failure guards."""

import math
from types import SimpleNamespace as N
import unittest
from unittest.mock import patch

from Partelier.partelier.tools.patterns import prism as direct
from Partelier.partelier.tools.patterns.planner import _polygon
from Partelier.partelier.tools.patterns.settings import PatternSettings


FRAME=N(origin_mm=(0,0,0),x_axis=(1,0,0),y_axis=(0,1,0),z_axis=(0,0,1))
OBLIQUE=N(origin_mm=(123.4,-56.7,89.01),
    x_axis=tuple(v/math.sqrt(14) for v in (1,2,3)),
    y_axis=tuple(v/math.sqrt(5) for v in (-2,1,0)),
    z_axis=tuple(v/math.sqrt(70) for v in (-3,-6,5)))
SQUARE=((-2,-1),(2,-1),(2,1),(-2,1))


def xyz(point):return point.x,point.y,point.z
def point(*values):return N(**dict(zip(('x','y','z'),values)))
def subtract(a,b):return tuple(one-two for one,two in zip(a,b))
def cross(a,b):return a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]


class Collection:
    def __init__(self,items=()):self.items=list(items)
    @property
    def count(self):return len(self.items)
    def item(self,index):return self.items[index]


class AddingCollection(Collection):
    def __init__(self,factory):super().__init__();self.factory=factory
    def add(self,*args):
        item=self.factory(*args);self.items.append(item);return item


class Definition:
    def __init__(self):
        self.vertices=[];self.edges=[];self.faces=[];self.create_calls=0
        self.doFullHealing=False;self.outcomeInfo=[]
        self.failure=None;self.volume_factor=1;self.void=False
        self.lumpDefinitions=AddingCollection(lambda:N(shellDefinitions=AddingCollection(self.shell)))
    def shell(self):return N(faceDefinitions=AddingCollection(self.face))
    def face(self,plane,reversed_normal):
        face=N(plane=plane,isParamReversed=reversed_normal,
               loopDefinitions=AddingCollection(lambda:N(bRepCoEdgeDefinitions=
                   AddingCollection(lambda edge,opposed:N(edge=edge,opposed=opposed)))))
        self.faces.append(face);return face
    def createVertexDefinition(self,position):
        vertex=N(position=position);self.vertices.append(vertex);return vertex
    def createEdgeDefinitionByCurve(self,one,two,curve):
        if self.failure=='edge':return None
        assert curve.start is one.position and curve.end is two.position
        edge=N(one=one,two=two,curve=curve);self.edges.append(edge);return edge
    def createBody(self):
        self.create_calls+=1
        if self.failure=='body':self.outcomeInfo=['fixed native failure'];return None
        reference=xyz(self.vertices[0].position)
        volume=0
        for face in self.faces:
            self.assert_loop(face)
            loop=face.loopDefinitions.item(0)
            points=[xyz(coedge.edge.two.position if coedge.opposed else coedge.edge.one.position)
                    for coedge in loop.bRepCoEdgeDefinitions.items]
            for i in range(1,len(points)-1):
                a,b,c=(subtract(p,reference) for p in (points[0],points[i],points[i+1]))
                volume+=sum(x*y for x,y in zip(a,cross(b,c)))/6
        assert volume>0,'Faces must wind outward before healing.'
        shell=N(isVoid=self.void)
        return N(isValid=True,isTemporary=True,isSolid=True,
                 lumps=Collection([N(shells=Collection([shell]))]),volume=volume*self.volume_factor)
    def assert_loop(self,face):
        assert face.isParamReversed is False
        assert face.loopDefinitions.count==1
        values=face.loopDefinitions.item(0).bRepCoEdgeDefinitions.items
        for a,b in zip(values,values[1:]+values[:1]):
            end=a.edge.one if a.opposed else a.edge.two
            start=b.edge.two if b.opposed else b.edge.one
            assert end is start,'Co-edge loops must share the exact vertex definitions.'


def api(definition):
    core=N(Point3D=N(create=point),Vector3D=N(create=point),
           Line3D=N(create=lambda one,two:N(start=one,end=two)),
           Plane=N(create=lambda origin,normal:N(origin=origin,normal=normal)))
    native=N(BRepBodyDefinition=N(create=lambda:definition))
    return core,native


class PrismPlanTests(unittest.TestCase):
    def test_all_real_pattern_footprints_close_with_opposed_shared_edges(self):
        for shape in ('hexagon','circle','diamond','square','slot'):
            polygon=_polygon(PatternSettings(pattern=shape,rotation_deg=17))
            plan=direct.plan_prism(FRAME,polygon,-3,.02)
            self.assertEqual(len(plan.points_mm),2*len(polygon))
            self.assertEqual(len(plan.face_loops),len(polygon)+2)
            self.assertAlmostEqual(plan.volume_mm3,plan.area_mm2*3.02)
            edges={}
            for face in plan.face_loops:
                for one,two in zip(face,face[1:]+face[:1]):
                    edges.setdefault(tuple(sorted((one,two))),[]).append(one>two)
            self.assertEqual(len(edges),3*len(polygon))
            self.assertTrue(all(sorted(v)==[False,True] for v in edges.values()))

    def test_oblique_translated_frame_preserves_volume_and_known_vertices(self):
        original=direct.plan_prism(FRAME,SQUARE,-.02,1.02)
        rotated=direct.plan_prism(OBLIQUE,SQUARE,-.02,1.02)
        self.assertEqual(original.volume_mm3,rotated.volume_mm3)
        for source,target in zip(original.points_mm,rotated.points_mm):
            expected=tuple(OBLIQUE.origin_mm[i]+source[0]*OBLIQUE.x_axis[i]
                +source[1]*OBLIQUE.y_axis[i]+source[2]*OBLIQUE.z_axis[i] for i in range(3))
            self.assertEqual(target,expected)

    def test_clockwise_concave_crossed_collinear_and_repeated_polygons_are_refused(self):
        star=tuple((math.cos(i*4*math.pi/5),math.sin(i*4*math.pi/5)) for i in range(5))
        invalid=(tuple(reversed(SQUARE)),((0,0),(2,0),(1,.2),(2,2),(0,2)),star,
                 ((0,0),(1,0),(2,0),(2,2),(0,2)),SQUARE+(SQUARE[0],),((0,0),(1,0)))
        for polygon in invalid:
            with self.subTest(polygon=polygon),self.assertRaises(ValueError):
                direct.plan_prism(FRAME,polygon,-1,1)

    def test_non_finite_inputs_bad_frames_and_collapsed_depth_are_refused(self):
        for low,high in ((1,1),(1,-1),(False,1),(0,float('nan')),(0,10**1000)):
            with self.assertRaises(ValueError):direct.plan_prism(FRAME,SQUARE,low,high)
        for frame in (N(origin_mm=(0,0,0),x_axis=(1,0,0),y_axis=(0,2,0),z_axis=(0,0,1)),
                      N(origin_mm=(0,0,0),x_axis=(1,0,0),y_axis=(0,1,0),z_axis=(0,0,-1)),
                      N(origin_mm=(0,0),x_axis=(1,0,0),y_axis=(0,1,0),z_axis=(0,0,1))):
            with self.assertRaises(ValueError):direct.plan_prism(frame,SQUARE,-1,1)


class DirectNativeDefinitionTests(unittest.TestCase):
    def test_real_footprints_use_one_native_creation_without_any_boolean_or_history_api(self):
        for shape in ('hexagon','circle','diamond','square','slot'):
            with self.subTest(shape=shape):
                polygon=_polygon(PatternSettings(pattern=shape))
                definition=Definition();diagnostics={}
                with patch.object(direct,'_api',lambda:api(definition)):
                    body=direct.prism(OBLIQUE,polygon,-3,.02,diagnostics=diagnostics)
                self.assertTrue(body.isTemporary)
                self.assertEqual(definition.create_calls,1)
                self.assertTrue(definition.doFullHealing)
                self.assertEqual(len(definition.vertices),2*len(polygon))
                self.assertEqual(len(definition.edges),3*len(polygon))
                self.assertEqual(len(definition.faces),len(polygon)+2)
                uses={id(edge):[] for edge in definition.edges}
                for face in definition.faces:
                    for coedge in face.loopDefinitions.item(0).bRepCoEdgeDefinitions.items:
                        uses[id(coedge.edge)].append(coedge.opposed)
                self.assertTrue(all(sorted(v)==[False,True] for v in uses.values()))
                self.assertEqual(diagnostics['backend'],'BRepBodyDefinition')
                self.assertEqual(diagnostics['create_calls'],1)
                self.assertEqual(diagnostics['outcome'],())

    def test_native_creation_failure_reports_diagnostics_without_fallback(self):
        definition=Definition();definition.failure='body'
        with patch.object(direct,'_api',lambda:api(definition)),self.assertRaisesRegex(ValueError,'fixed native failure'):
            direct.prism(FRAME,SQUARE,-1,1)
        self.assertEqual(definition.create_calls,1)

    def test_wrong_volume_and_reversed_void_shell_are_refused(self):
        for volume_factor,void in ((1.1,False),(1,True)):
            definition=Definition();definition.volume_factor=volume_factor;definition.void=void
            with patch.object(direct,'_api',lambda:api(definition)),self.assertRaises(ValueError):
                direct.prism(FRAME,SQUARE,-1,1)

    def test_invalid_polygon_never_reaches_native_api(self):
        with patch.object(direct,'_api',side_effect=AssertionError('No native call allowed.')):
            with self.assertRaises(ValueError):direct.prism(FRAME,tuple(reversed(SQUARE)),-1,1)

    def test_edge_definition_failure_never_attempts_body_creation(self):
        definition=Definition();definition.failure='edge'
        with patch.object(direct,'_api',lambda:api(definition)),self.assertRaisesRegex(ValueError,'shared prism edge'):
            direct.prism(FRAME,SQUARE,-1,1)
        self.assertEqual(definition.create_calls,0)


if __name__=='__main__':unittest.main()

"""Multi-loop cap winding, shared topology, invalid holes and SDK failure guards."""

import unittest
from types import SimpleNamespace as N
from unittest.mock import patch
from Partelier.partelier.tools.patterns import perforated_prism as direct
from Partelier.partelier.tools.patterns import prism
from Partelier.partelier.tools.patterns.dense_grid import plan as grid_plan
from Partelier.partelier.tools.patterns.settings import PatternSettings
from test_pattern_direct_prism import Definition,Collection,api,FRAME,xyz,subtract,cross


OUTER=((-10,-10),(10,-10),(10,10),(-10,10))
HOLES=(((-5,-5),(-1,-5),(-1,-1),(-5,-1)),((1,1),(6,1),(6,6),(1,6)))


class MultiDefinition(Definition):
    def createBody(self):
        self.create_calls+=1
        if self.failure=='body':return None
        reference=xyz(self.vertices[0].position);volume=0
        for face in self.faces:
            for loop in face.loopDefinitions.items:
                values=loop.bRepCoEdgeDefinitions.items
                for a,b in zip(values,values[1:]+values[:1]):
                    self_end=a.edge.one if a.opposed else a.edge.two
                    next_start=b.edge.two if b.opposed else b.edge.one
                    assert self_end is next_start
                points=[xyz(coedge.edge.two.position if coedge.opposed else coedge.edge.one.position) for coedge in values]
                for i in range(1,len(points)-1):
                    a,b,c=(subtract(p,reference) for p in (points[0],points[i],points[i+1]))
                    volume+=sum(x*y for x,y in zip(a,cross(b,c)))/6
        return N(isValid=True,isTemporary=True,isSolid=True,volume=volume*self.volume_factor,
                 lumps=Collection([N(shells=Collection([N(isVoid=False)]))]))


class PerforatedPrismTests(unittest.TestCase):
    def test_cap_holes_have_opposite_winding_and_all_edges_are_shared_twice(self):
        value=direct.plan(FRAME,OUTER,HOLES,-3,0)
        self.assertEqual([len(face) for face in value.faces[:2]],[3,3])
        self.assertAlmostEqual(value.volume_mm3,(400-16-25)*3)
        edges={}
        for face in value.faces:
            for loop in face:
                for a,b in zip(loop,loop[1:]+loop[:1]):edges.setdefault(tuple(sorted((a,b))),[]).append(a>b)
        self.assertTrue(all(sorted(v)==[False,True] for v in edges.values()))

    def test_one_fully_healed_sdk_body_contains_all_loops_with_correct_signed_volume(self):
        definition=MultiDefinition()
        with patch.object(prism,'_api',return_value=api(definition)):
            body=direct.create(FRAME,OUTER,HOLES,-3,0)
        self.assertEqual(definition.create_calls,1)
        self.assertTrue(definition.doFullHealing)
        self.assertEqual(definition.faces[0].loopDefinitions.count,3)
        self.assertAlmostEqual(body.volume,1.077)

    def test_touching_overlapping_and_exterior_holes_are_refused_before_sdk(self):
        for holes in ((HOLES[0],HOLES[0]),(HOLES[0],((-1,-5),(3,-5),(3,-1),(-1,-1))),
                      (((-10,-5),(-6,-5),(-6,-1),(-10,-1)),)):
            with self.subTest(holes=holes),self.assertRaises(ValueError):direct.plan(FRAME,OUTER,holes,-3,0)

    def test_native_body_failure_and_wrong_volume_are_refused(self):
        for failure,factor in (('body',1),(None,.99)):
            definition=MultiDefinition();definition.failure=failure;definition.volume_factor=factor
            with patch.object(prism,'_api',return_value=api(definition)),self.assertRaises(ValueError):
                direct.create(FRAME,OUTER,HOLES,-3,0)

    def test_large_topology_is_planned_without_any_sdk_calls(self):
        settings=PatternSettings(pattern='grille_cross',layout_mode='fill',pitch_mm=7,web_mm=2,border_mm=7)
        grid=grid_plan(settings,(0,400,0,400))
        holes=tuple(tuple((u+cell.center_mm[0],v+cell.center_mm[1]) for u,v in cell.polygon_mm) for cell in grid.layout.cells)
        with patch.object(prism,'_api') as sdk:value=direct.plan(FRAME,((0,0),(400,0),(400,400),(0,400)),holes,-3,0)
        sdk.assert_not_called()
        self.assertEqual(len(value.faces[0]),3026)
        self.assertAlmostEqual(value.volume_mm3,(160000-3025*25)*3)

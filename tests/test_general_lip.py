"""General native-offset guards; these fakes are not CAD acceptance evidence."""
import unittest
from types import SimpleNamespace as NS
from Partelier.partelier.tools.details import native_outline


class GeneralLipOffsetTests(unittest.TestCase):
    def fixture(self,areas):
        calls=[];deleted=[];children=[];sketch=NS(profiles=[])
        def add(inp):
            calls.append(inp)
            self.assertTrue(inp.isTopologyMatched)
            sketch.profiles=[NS(profileLoops=NS(count=1),areaProperties=lambda a=area:NS(area=a)) for area in areas[len(calls)-1]]
            child=NS(isConstruction=True,isValid=True,deleteMe=lambda:deleted.append('curve'));children.append(child)
            return NS(childCurves=[child],isValid=True,deleteMe=lambda:deleted.append('constraint'))
        sketch.geometricConstraints=NS(createOffsetInput=lambda curves,value:NS(curves=curves,value=value),addOffset2=add)
        core=NS(ValueInput=NS(createByReal=lambda value:value))
        return sketch,core,calls,deleted,children

    def test_outward_offset_is_removed_before_trying_inward(self):
        sketch,core,calls,deleted,children=self.fixture([[120],[80]])
        sign=native_outline._profile(sketch,('curve',),2,100,core)
        self.assertEqual(sign,-1);self.assertEqual([i.value for i in calls],[.2,-.2])
        self.assertEqual(deleted,['constraint','curve']);self.assertTrue(all(not c.isConstruction for c in children))

    def test_split_or_nonshrinking_offsets_are_refused_and_cleaned(self):
        for areas in ([[30,40],[50,20]],[[120],[130]],[[100],[100]]):
            sketch,core,calls,deleted,children=self.fixture(areas)
            with self.assertRaisesRegex(ValueError,'one inward offset'):native_outline._profile(sketch,('curve',),2,100,core)
            self.assertEqual(len(deleted),4)

    def test_inner_offset_keeps_the_confirmed_direction_and_topology(self):
        sketch,core,calls,deleted,children=self.fixture([[80,10]])
        self.assertEqual(native_outline._profile(sketch,('curve',),3,100,core,-1),-1)
        self.assertEqual(calls[0].value,-.3);self.assertEqual(deleted,[])

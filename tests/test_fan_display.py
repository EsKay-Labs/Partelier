import unittest
from types import SimpleNamespace as NS
from Partelier.partelier.tools.fans.display import material

class FanPreviewMaterialTests(unittest.TestCase):
    def test_material_colours_are_lit_opaque_and_non_emissive(self):
        core=NS(Color=NS(create=lambda *rgba:rgba),ColorProperty=NS(cast=lambda value:value))
        native=NS(CustomGraphicsBasicMaterialColorEffect=NS(create=lambda *values:values))
        for colour in ((160,160,160),(210,45,25)):
            props={'metal_f0':NS(value=NS(red=colour[0],green=colour[1],blue=colour[2]))}
            appearance=NS(appearanceProperties=NS(itemById=props.get))
            effect=material(appearance,core,native)
            self.assertEqual(effect[0],(*colour,255))
            self.assertEqual(effect[3],(0,0,0,255))
            self.assertEqual(effect[-1],1.)
            self.assertTrue(all(a<b for a,b in zip(effect[1][:3],effect[0][:3])))
        self.assertEqual(material(None,core,native)[0],(160,160,160,255))

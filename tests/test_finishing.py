"""Face-detail dimensions and exact footprint tests."""
import unittest,math
from dataclasses import replace
from Partelier.partelier.tools.finishing.settings import FinishingSettings,KINDS
from Partelier.partelier.tools.finishing import planner

class FinishingTests(unittest.TestCase):
    def test_roundtrips(self):
        for kind in KINDS:
            s=FinishingSettings(kind=kind);self.assertEqual(s,FinishingSettings.from_dict(s.to_dict()))
    def test_invalid_dimensions(self):
        for fields in ({'width_mm':10**400},{'width_mm':0},{'depth_mm':float('nan')},{'count':True},{'text':'<b>x</b>'},{'kind':'unknown'},{'offset_x_mm':float('inf')},{'kind':'keyhole','shaft_mm':12},{'kind':'scale','count':101}):
            with self.subTest(fields=fields),self.assertRaises(ValueError):FinishingSettings(**fields).validate()
    def test_addition_semantics(self):
        for kind in KINDS:
            for mode in ('engrave','emboss'):
                s=FinishingSettings(kind=kind,mode=mode)
                self.assertEqual(s.additive,kind=='stop' or kind in ('text','arrow','scale') and mode=='emboss')
    def test_scale_dimensions(self):
        s=FinishingSettings(kind='scale',count=11,major_every=5,length_mm=30,width_mm=8,stroke_mm=.5)
        polygons=planner.polygons(s);self.assertEqual(len(polygons),11)
        for i,p in enumerate(polygons):
            self.assertAlmostEqual(max(x for x,y in p)-min(x for x,y in p),.5)
            self.assertAlmostEqual(max(y for x,y in p),8 if i%5==0 else 4.4)
        self.assertAlmostEqual((polygons[-1][0][0]+.25)-(polygons[0][0][0]+.25),30)
    def test_transform(self):
        s=FinishingSettings(rotation_deg=90,offset_x_mm=2,offset_y_mm=3)
        x,y=planner.transformed(((1,0),),s)[0];self.assertAlmostEqual(x,2);self.assertAlmostEqual(y,4)
    def test_unknown_fields_refused(self):
        values=FinishingSettings().to_dict();values['unused']=1
        with self.assertRaises(ValueError):FinishingSettings.from_dict(values)
class FinishingRecipeTests(unittest.TestCase):
    def recipe(self):
        from uuid import uuid4
        return {'version':1,'id':str(uuid4()),'settings':FinishingSettings().to_dict(),'sources':{'faces':['face'],'bodies':['body']},'base':'base','combines':['combine'],'tools':['tool'],'tool_signatures':['a'*64],'results':['b'*64]}
    def test_exact_one_face_delta_record(self):
        import json
        from Partelier.partelier.tools.finishing.store import _parse
        value=self.recipe();record,s=_parse(json.dumps(value));self.assertEqual(s,FinishingSettings())
        for key in ('combines','tools','results'):
            invalid=self.recipe();invalid[key].append(invalid[key][0])
            with self.assertRaises(ValueError):_parse(json.dumps(invalid))
    def test_version_and_identity_validation(self):
        import json
        from Partelier.partelier.tools.finishing.store import _parse
        for change in ({'version':2},{'id':'invalid'}):
            with self.assertRaises(ValueError):_parse(json.dumps({**self.recipe(),**change}))
if __name__=='__main__':unittest.main()

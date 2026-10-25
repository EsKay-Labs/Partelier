"""Small detail field contracts, fit dimensions, ownership and protocol limits."""

from dataclasses import replace,FrozenInstanceError
import json,math,unittest,uuid
from Partelier.partelier.tools.details.settings import DetailSettings
from Partelier.partelier.tools.details import planner
from Partelier.partelier.palette_protocol import read_request


class DetailSettingsTests(unittest.TestCase):
    def test_all_three_helpers_round_trip_exactly_and_defaults_have_print_leads(self):
        for kind in ('lid','alignment','ribs'):
            s=DetailSettings(kind=kind);self.assertEqual(DetailSettings.from_dict(s.to_dict()),s)
            self.assertEqual(len(s.to_dict()),19)
        self.assertEqual(DetailSettings().lead_mm,.2)
        with self.assertRaises(FrozenInstanceError):DetailSettings().lip_height_mm=4

    def test_numeric_type_and_geometry_bounds_are_strict(self):
        cases=[{'kind':'pockets'},{'rib_style':'circle'},{'pin_count':True},{'pin_count':3},{'pin_count':2.0},
               {'rib_count':33},{'rib_count':0},{'rib_count':2.0},{'lip_height_mm':0},{'lead_mm':.6},
               {'kind':'alignment','lead_mm':2},{'lip_clearance_mm':2.01},{'pin_clearance_mm':-1}]
        cases.extend({name:value} for name in ('lip_width_mm','pin_height_mm','rib_width_mm') for value in (True,math.nan,math.inf,10**400,'3'))
        for values in cases:
            with self.subTest(values=values),self.assertRaises(ValueError):DetailSettings(**values)

    def test_no_partial_snapshots_or_unknown_settings(self):
        for values in ({},{**DetailSettings().to_dict(),'unknown':1}):
            with self.assertRaises(ValueError):DetailSettings.from_dict(values)


class DetailLayoutTests(unittest.TestCase):
    def test_pin_centres_are_diagonal_or_all_four_corners_with_diametral_clearance(self):
        s=DetailSettings(kind='alignment');two=planner.pins((-30,30,-20,20),s)
        self.assertEqual(len(two),2)
        self.assertAlmostEqual(two[0][0],-27.9);self.assertAlmostEqual(two[0][1],-17.9)
        four=planner.pins((-30,30,-20,20),replace(s,pin_count=4))
        self.assertEqual(len(set(four)),4)
        self.assertAlmostEqual((s.pin_diameter_mm+s.pin_clearance_mm),2.8)
        with self.assertRaises(ValueError):planner.pins((-3,3,-3,3),s)
        with self.assertRaises(ValueError):planner.pins((-30,30,-20,20),replace(s,pin_inset_mm=.1))

    def test_rib_rows_have_exact_equal_margins_and_uniform_spacing(self):
        positions=planner.rib_positions(60,2,3,5)
        self.assertEqual(positions,(6,30,54))
        self.assertEqual(positions[0]-1,5);self.assertEqual(60-positions[-1]-1,5)
        self.assertEqual(planner.rib_positions(60,2,1,5),(30,))
        for args in ((10,2,9,1),(10,2,2,6),(60,2,33,1),(60,2,True,1)):
            with self.subTest(args=args),self.assertRaises(ValueError):planner.rib_positions(*args)

    def test_socket_depth_preserves_clearance_after_gap_and_refuses_overlap(self):
        self.assertAlmostEqual(planner.socket_depth(4,.25,.3),4.05)
        self.assertAlmostEqual(planner.socket_depth(2.5,0,.3),2.8)
        for args in ((2.5,2.4,.3),(2.5,-1,.3)):
            with self.assertRaises(ValueError):planner.socket_depth(*args)

    def test_ring_offsets_keep_exact_perimeter_width_and_refuse_collapsed_region(self):
        self.assertEqual(planner.rectangle((0,20,0,10),1),((1,1),(19,1),(19,9),(1,9)))
        with self.assertRaises(ValueError):planner.rectangle((0,20,0,10),5)


class DetailProtocolTests(unittest.TestCase):
    def request(self,action,**extra):return read_request(action,json.dumps({'protocol':1,'requestId':'detail-test',**extra}))

    def test_begin_defaults_and_full_live_snapshots(self):
        result=self.request('detail_begin',editing=False,settings={'kind':'ribs'})
        self.assertEqual(result.settings.rib_count,3)
        sid=str(uuid.uuid4());values=DetailSettings(kind='alignment').to_dict()
        for action in ('detail_update','detail_preview','detail_commit'):
            self.assertEqual(self.request(action,sessionId=sid,revision=4,settings=values).settings.kind,'alignment')
            with self.assertRaises(ValueError):self.request(action,sessionId=sid,revision=4,settings={'kind':'alignment'})

    def test_focus_and_revision_are_tool_scoped(self):
        sid=str(uuid.uuid4())
        for target in ('face_a','face_b','edit_target'):self.request('detail_focus',sessionId=sid,target=target)
        for target in ('axis_edge','faces','body','add_face'):
            with self.assertRaises(ValueError):self.request('detail_focus',sessionId=sid,target=target)
        for revision in (True,-1,1.5):
            with self.assertRaises(ValueError):self.request('detail_update',sessionId=sid,revision=revision,settings=DetailSettings().to_dict())
        self.request('detail_status')

    def test_ownership_record_rejects_bad_references_and_geometry_hashes_before_host_access(self):
        from copy import deepcopy
        from Partelier.partelier.tools.details import store
        value={'version':1,'id':str(uuid.uuid4()),'settings':DetailSettings().to_dict(),
            'sources':{'faces':['fa','fb'],'bodies':['a','b']},'base':'base','combines':['join','cut'],
            'tools':['one','two'],'tool_signatures':['0'*64,'1'*64],'results':['2'*64,'3'*64]}
        self.assertEqual(store._parse(json.dumps(value))[0],value)
        changes=[('version',True),('id','other'),('base',None),('tools',['one']),('tool_signatures',[{},{}])]
        for key,wrong in changes:
            damaged={**value,key:wrong}
            with self.subTest(key=key),self.assertRaises(ValueError):store._parse(json.dumps(damaged))
        for wrong in ([[],[]],[None,'f'],['same','same']):
            damaged=deepcopy(value);damaged['sources']['faces']=wrong
            with self.subTest(faces=wrong),self.assertRaises(ValueError):store._parse(json.dumps(damaged))

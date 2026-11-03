import unittest
import math
import json, uuid
from dataclasses import replace
from Partelier.partelier.tools.mechanisms.settings import MechanismSettings, FAMILIES,preset
from Partelier.partelier.tools.mechanisms.planner import plan
from Partelier.partelier.tools.mechanisms import store
from Partelier.partelier.tools.mechanisms.motion import path
from Partelier.partelier.tools.patterns.prism import plan_prism
from types import SimpleNamespace


class MechanismTests(unittest.TestCase):
    def test_motion_paths_respect_stop_and_bayonet_entry(self):
        slider=MechanismSettings()
        poses=path(slider)
        self.assertEqual(poses[0].dy_mm,0)
        self.assertAlmostEqual(poses[-1].dy_mm+slider.length_mm*.55,
                               slider.length_mm-slider.wall_mm-slider.clearance_mm)
        free=path(replace(slider,end_stop=False))
        self.assertGreater(free[-1].dy_mm,poses[-1].dy_mm)
        bayonet=MechanismSettings(family='bayonet')
        poses=path(bayonet)
        self.assertEqual(poses[8].angle_deg,-bayonet.angle_deg)
        self.assertEqual(poses[8].dz_mm,0)
        self.assertTrue(all(p.angle_deg==-bayonet.angle_deg for p in poses if p.stage=='withdraw'))
        self.assertGreater(poses[-1].dz_mm,bayonet.height_mm)

    def test_pivot_and_hinge_paths_state_bounded_angles(self):
        poses=path(MechanismSettings(family='clevis'))
        self.assertEqual((poses[0].angle_deg,poses[-1].angle_deg),(-60,60))
        for family in ('barrel','concealed','pip_hinge'):
            poses=path(MechanismSettings(family=family))
            self.assertEqual((poses[0].angle_deg,poses[-1].angle_deg),(0,150))
            self.assertTrue(all(p.body_index==1 for p in poses))

    def test_saved_recipe_validates_family_body_count_and_ownership(self):
        for family in FAMILIES:
            settings=preset(family)
            value={'version':2,'tool':'mechanism','feature_id':str(uuid.uuid4()),'base_feature':'base',
                   'settings':settings.to_dict(),'references':{},'attachment':None,
                   'results':[{'body':str(i),'signature':'0'*64} for i in range(len(plan(settings).names))]}
            raw=json.dumps(value)
            self.assertEqual(store.parse(raw),(value,settings))
            for patch in ({'version':True},{'version':3},{'references':{'circle':'token'}},{'results':value['results'][:-1]},
                          {'results':[value['results'][0]]*len(value['results'])},{'tool':'fan'}):
                with self.assertRaises(ValueError):store.parse(json.dumps({**value,**patch}))

    def test_recipe_one_is_read_only_separate_output_migration(self):
        settings=MechanismSettings();old={k:v for k,v in settings.to_dict().items() if k not in ('output_mode','attachment_overlap_mm','placement_angle_deg','assembly_layout')}
        value={'version':1,'tool':'mechanism','feature_id':str(uuid.uuid4()),'base_feature':'base','settings':old,'references':{},
               'results':[{'body':str(i),'signature':'0'*64} for i in range(2)]}
        parsed,upgraded=store.parse(json.dumps(value))
        self.assertEqual(parsed,value);self.assertEqual(len(parsed['settings']),14)
        self.assertEqual(upgraded.output_mode,'separate');self.assertEqual(upgraded.attachment_overlap_mm,.5)
        with self.assertRaises(ValueError):store.parse(json.dumps({**value,'settings':settings.to_dict()}))

    def test_attached_recipe_requires_exact_join_ownership_and_references(self):
        s=MechanismSettings(output_mode='attached')
        value={'version':2,'tool':'mechanism','feature_id':str(uuid.uuid4()),'base_feature':'base','settings':s.to_dict(),
            'references':{'face_a':'faceA','face_b':'faceB'},'results':[{'body':b,'signature':'0'*64} for b in ('A','B')],
            'attachment':{'targets':['A','B'],'combines':['joinA','joinB'],'tools':['toolA','toolB'],'tool_signatures':['0'*64]*2}}
        self.assertEqual(store.parse(json.dumps(value))[1],s)
        for patch in ({'references':{}},{'attachment':None},{'attachment':{**value['attachment'],'targets':['B','A']}},
                      {'attachment':{**value['attachment'],'combines':['joinA','joinA']}}):
            with self.assertRaises(ValueError):store.parse(json.dumps({**value,**patch}))

    def test_all_families_have_independent_output_layout(self):
        for family in FAMILIES:
            with self.subTest(family=family):
                s=preset(family)
                self.assertEqual(MechanismSettings.from_dict(s.to_dict()),s)
                p=plan(s)
                self.assertEqual(len(p.names),8 if family in ('parallel_lift','swing_hinge') else s.count+3 if family=='linked_louver' else s.count+1 if family=='pip_louver' else 3 if family in ('clevis','barrel','concealed') else 2)

    def test_captive_louver_bed_slot_retains_pivot_and_swept_spacing(self):
        s=MechanismSettings(family='pip_louver')
        poses=path(s)
        self.assertEqual(len(poses),13*s.count)
        self.assertEqual({p.body_index for p in poses},set(range(1,s.count+1)))
        self.assertTrue(all(p.axis=='x' and p.center_z_mm==s.pin_diameter_mm/2 for p in poses))
        with self.assertRaises(ValueError):replace(s,clearance_mm=.5)
        with self.assertRaises(ValueError):replace(s,count=9)
        with self.assertRaises(ValueError):replace(s,height_mm=3)

    def test_invalid_scalars_and_unknown_keys(self):
        for value in (float('nan'),float('inf'),True,'3',10**1000):
            with self.assertRaises(ValueError):MechanismSettings(clearance_mm=value)
        for patch in ({'extra':1},{'wall_mm':False},{'count':3.0},{'end_stop':1}):
            with self.assertRaises(ValueError):MechanismSettings.from_dict({**MechanismSettings().to_dict(),**patch})

    def test_dovetail_neck_and_clearance(self):
        frame=SimpleNamespace(origin_mm=(0,0,0),x_axis=(1,0,0),y_axis=(0,1,0),z_axis=(0,0,1))
        for family in ('slider','dovetail'):
            p=plan(MechanismSettings(family=family))
            solid=plan_prism(frame,p.rail_profile,0,40)
            expanded=plan_prism(frame,p.clearance_profile,0,40)
            self.assertGreater(expanded.volume_mm3,solid.volume_mm3)
            self.assertGreater(p.clearance_profile[1][0],p.rail_profile[1][0])
        with self.assertRaises(ValueError):MechanismSettings(family='dovetail',width_mm=8)

    def test_knuckles_have_axial_gap_and_captive_ends(self):
        for count in (3,5,7,9):
            s=MechanismSettings(family='pip_hinge',count=count)
            p=plan(s)
            self.assertEqual(p.knuckles[0][0],0)
            self.assertEqual(p.knuckles[-1][0],0)
            for one,two in zip(p.knuckles,p.knuckles[1:]):self.assertAlmostEqual(two[1]-one[2],s.clearance_mm)
        with self.assertRaises(ValueError):MechanismSettings(family='pip_hinge',count=4)

    def test_bayonet_refuses_crossed_slots_and_no_hollow_center(self):
        with self.assertRaises(ValueError):MechanismSettings(family='bayonet',count=9,angle_deg=60)
        with self.assertRaises(ValueError):MechanismSettings(family='bayonet',diameter_mm=12,wall_mm=3)
        with self.assertRaises(ValueError):MechanismSettings(family='bayonet',height_mm=4)

    def test_clevis_refuses_missing_back_wall_or_bore_wall(self):
        with self.assertRaises(ValueError):MechanismSettings(family='clevis',length_mm=15)
        with self.assertRaises(ValueError):MechanismSettings(family='clevis',pin_diameter_mm=8)

    def test_dimensions_do_not_silently_shrink(self):
        s=MechanismSettings(family='dovetail',width_mm=23,clearance_mm=.65,angle_deg=20)
        p=plan(s)
        self.assertAlmostEqual(p.rail_profile[2][0]-p.rail_profile[3][0],23)
        self.assertEqual(s.clearance_mm,.65)
        one,two=p.rail_profile[1:3]
        dx,dz=two[0]-one[0],two[1]-one[1]
        for x,z in p.clearance_profile[1:3]:
            distance=abs(dx*(z-one[1])-dz*(x-one[0]))/math.hypot(dx,dz)
            self.assertAlmostEqual(distance,.65)


if __name__=='__main__':unittest.main()

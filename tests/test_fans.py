"""Geometry invariants and exact HTML settings contracts for original rotors."""
from dataclasses import replace
import json,math,unittest,uuid
from pathlib import Path
from Partelier.partelier.tools.fans.settings import FanSettings,preset,STYLES,PC_SIZES,PROPS
from Partelier.partelier.tools.fans.planner import plan,stroke,outline_chord
from Partelier.partelier.palette_protocol import read_request
from Partelier.partelier.tools.fans import store

class FanPlanningTests(unittest.TestCase):
 def test_ui_defaults_presets_and_help_match_the_python_contract(self):
  source=(Path(__file__).parents[1]/'Partelier/partelier/ui/fan-data.js').read_text(encoding='utf-8')
  data=json.loads(source.split('Object.freeze(',1)[1].rsplit(');',1)[0])
  self.assertEqual(data['defaults'],FanSettings().to_dict())
  self.assertEqual(set(data['labels']),set(data['help']))
  self.assertEqual(set(data['labels']),set(data['defaults']))
  for key,values in data['presets'].items():self.assertEqual(values,preset(*key.split(':')).to_dict())

 def test_all_dimensional_presets_leave_separate_blade_sectors(self):
  for style in STYLES:
   for size in PROPS if style.startswith('prop') else PC_SIZES:
    with self.subTest(style=style,size=size):
     s=preset(style,size);p=plan(s)
     self.assertEqual(len(p.sections),0 if style=="blower" else 9);self.assertGreater(p.minimum_sector_gap_deg,.5)
     self.assertEqual(s,FanSettings.from_dict(s.to_dict()))
     for section in p.sections:
      self.assertTrue(all(math.isfinite(v) for point in section.points_mm for v in point))
      self.assertLessEqual(max(math.hypot(x,y) for x,y,z in stroke(section,40)),section.radius_mm+1e-6)

 def test_custom_station_widths_and_angles_are_retained(self):
  s=replace(FanSettings(),root_chord_mm=15,mid_chord_mm=18,tip_chord_mm=12,root_angle_deg=42,mid_angle_deg=28,tip_angle_deg=11)
  p=plan(s)
  self.assertEqual([p.sections[i].chord_mm for i in (0,4,8)],[15,18,12])
  self.assertEqual([p.sections[i].angle_deg for i in (0,4,8)],[42,28,11])

 def test_constant_pitch_is_computed_at_each_actual_station(self):
  s=preset('prop3','prop6040')
  for section in plan(s).sections:
   self.assertAlmostEqual(math.tan(math.radians(section.angle_deg))*2*math.pi*section.axis_radius_mm,s.pitch_mm)

 def test_rotation_is_an_exact_mirror(self):
  a=plan(FanSettings());b=plan(replace(FanSettings(),rotation='cw'))
  for x,y in zip(a.sections,b.sections):
   for p,q in zip(x.points_mm,y.points_mm):self.assertEqual(p,(q[0],-q[1],q[2]))

 def test_invalid_numbers_or_missing_atomic_fields_are_rejected(self):
  for value in (True,float('nan'),float('inf'),'120',10**1000):
   with self.subTest(value=str(value)[:20]),self.assertRaises(ValueError):replace(FanSettings(),diameter_mm=value)
  values=FanSettings().to_dict();values.pop('root_fillet_mm')
  with self.assertRaises(ValueError):FanSettings.from_dict(values)
  for count in (True,3.5,1,17):
   with self.assertRaises(ValueError):replace(FanSettings(),blade_count=count)

 def test_collisions_and_frame_budget_are_refused_without_shrinking(self):
  with self.assertRaisesRegex(ValueError,'wide'):plan(replace(FanSettings(),blade_count=16,mid_chord_mm=60))
  with self.assertRaisesRegex(ValueError,'Frame depth'):plan(replace(FanSettings(),output='rotor_frame',frame_depth_mm=5))
  with self.assertRaisesRegex(ValueError,'Mounting holes'):replace(FanSettings(),output='rotor_frame',mount_pitch_mm=80)

 def test_custom_planform_changes_widths_but_refuses_pointed_ends(self):
  rectangle=((0,-2),(20,-2),(20,2),(0,2))
  self.assertEqual(outline_chord(rectangle,.5),(4,0,20))
  s=replace(FanSettings(),outline_mode='sketch')
  p=plan(s,rectangle)
  self.assertAlmostEqual(p.sections[0].chord_mm,4*(s.diameter_mm/2-(s.hub_diameter_mm/2-.8))/20)
  with self.assertRaises(ValueError):plan(s,((0,0),(20,-4),(20,4)))
  with self.assertRaises(ValueError):plan(s)

 def test_hub_coupon_has_no_blades(self):
  p=plan(replace(FanSettings(),output='hub_test'))
  self.assertEqual((p.sections,p.blade_count),((),0))

 def test_html_session_requires_full_typed_settings_and_current_identity(self):
  base={'protocol':1,'requestId':'fan-test','sessionId':str(uuid.uuid4()),'revision':1,'settings':FanSettings().to_dict()}
  self.assertIsInstance(read_request('fan_preview',json.dumps(base)).settings,FanSettings)
  for change in ({'revision':True},{'sessionId':'old'},{'settings':{'style':'axial'}}):
   with self.assertRaises(ValueError):read_request('fan_preview',json.dumps({**base,**change}))
  focus={k:v for k,v in base.items() if k not in ('revision','settings')}
  for target in ('circle','outline','edit_target'):self.assertEqual(read_request('fan_focus',json.dumps({**focus,'target':target})).target,target)
  with self.assertRaises(ValueError):read_request('fan_focus',json.dumps({**focus,'target':'face_a'}))

 def test_recipe_is_exact_versioned_and_maps_only_owned_outputs(self):
  value={'version':2,'tool':'fan','feature_id':str(uuid.uuid4()),'base_feature':'base','settings':FanSettings().to_dict(),'references':{},'results':[{'body':'rotor','signature':'a'*64}]}
  self.assertEqual(store.parse(json.dumps(value))[1],FanSettings())
  for changed in ({'version':True},{'version':3},{'tool':'hinge'},{'feature_id':'broken'},{'extra':0},{'references':{'face':'source'}},{'results':[{'body':'rotor','signature':'x'*64}]},{'results':[]}):
   with self.subTest(change=changed),self.assertRaises(ValueError):store.parse(json.dumps({**value,**changed}))
  triple={**value,'settings':replace(FanSettings(),output='rotor_guard').to_dict(),'results':[{'body':name,'signature':'a'*64} for name in ('rotor','frame','guard')]}
  self.assertEqual(len(store.parse(json.dumps(triple))[0]['results']),3)
  triple['results'][2]['body']='rotor'
  with self.assertRaisesRegex(ValueError,'duplicated'):store.parse(json.dumps(triple))

class BlowerTests(unittest.TestCase):
 def test_bounded_impeller_envelope_and_clearance(self):
  s=preset('blower','pc80');p=plan(s)
  self.assertEqual(p.sections,());self.assertEqual(p.blade_count,12)
  self.assertGreater(p.minimum_sector_gap_deg,1)
  self.assertEqual(p.z_min_mm,-s.hub_height_mm/2)
  self.assertEqual(p.z_max_mm,max(s.hub_height_mm/2,p.z_min_mm+s.blower_backplate_mm+s.blower_height_mm))
  for values in ({'output':'rotor_frame'},{'outline_mode':'sketch'},{'hub_diameter_mm':5,'shaft_diameter_mm':.8,'blade_count':16,'blower_vane_mm':6}):
   with self.assertRaises(ValueError):replace(s,**values)
 def test_old_recipe_remains_read_only_and_new_style_requires_new_recipe(self):
  settings=FanSettings().to_dict();old={k:v for k,v in settings.items() if not k.startswith('blower_')}
  value={'version':1,'tool':'fan','feature_id':str(uuid.uuid4()),'base_feature':'base','settings':old,'references':{},'results':[{'body':'rotor','signature':'a'*64}]}
  raw=json.dumps(value);parsed,read=store.parse(raw)
  self.assertEqual(parsed,value);self.assertEqual(read,FanSettings());self.assertEqual(len(parsed['settings']),40)
  with self.assertRaises(ValueError):store.parse(json.dumps({**value,'settings':settings}))
  with self.assertRaises(ValueError):store.parse(json.dumps({**value,'settings':{**old,'style':'blower'}}))

"""Standalone guard contracts, independent of native CAD availability."""
from dataclasses import replace
import json
import unittest
import uuid
from Partelier.partelier.tools.fans.settings import FanSettings, preset
from Partelier.partelier.tools.fans import planner, store

KINDS = ('spokes', 'rings', 'parallel', 'grid', 'honeycomb')


def recipe(settings, version=4):
    return dict(version=version, tool='fan', feature_id=str(uuid.uuid4()),
                base_feature='base', settings=settings, references={},
                results=[dict(body='guard', signature='a'*64)])


class FanGuardTests(unittest.TestCase):
    def test_all_five_guards_have_flat_bounded_plans_without_blades(self):
        for kind in KINDS:
            with self.subTest(kind=kind):
                s=replace(preset('axial','pc80'),output='guard',guard_type=kind)
                p=planner.plan(s)
                self.assertEqual(p.sections,())
                self.assertEqual(p.blade_count,0)
                self.assertEqual((p.z_min_mm,p.z_max_mm),(0,s.guard_thickness_mm))
                self.assertEqual(FanSettings.from_dict(s.to_dict()),s)

    def test_guard_ignores_irrelevant_rotor_collision_and_blade_budget(self):
        s=replace(preset('axial','pc80'),output='guard',guard_type='grid',
                  blade_count=16,root_chord_mm=100,mid_chord_mm=100,tip_chord_mm=100,
                  frame_depth_mm=5,outline_mode='sketch')
        self.assertEqual(planner.plan(s).sections,())

    def test_pitch_and_type_reject_untyped_and_nonfinite_values(self):
        for value in (True,'12',None,float('nan'),float('inf'),10**1000):
            with self.subTest(value=str(value)[:25]),self.assertRaises(ValueError):
                replace(FanSettings(),output='guard',guard_pitch_mm=value)
        for kind in ('hex', '', None, 0):
            with self.subTest(kind=kind),self.assertRaises(ValueError):
                replace(FanSettings(),output='guard',guard_type=kind)

    def test_guard_preserves_frame_and_mount_clearance_checks(self):
        s=replace(preset('axial','pc80'),output='guard')
        for changes in ({'frame_width_mm':70},{'mount_pitch_mm':40},{'mount_pitch_mm':79}):
            with self.subTest(changes=changes),self.assertRaises(ValueError):replace(s,**changes)

    def test_v4_requires_complete_52_fields_and_one_owned_body(self):
        s=replace(FanSettings(),output='guard',guard_type='honeycomb')
        self.assertEqual(len(s.to_dict()),52)
        raw=recipe(s.to_dict());self.assertEqual(store.parse(json.dumps(raw))[1],s)
        for key in ('guard_type','guard_pitch_mm'):
            broken=json.loads(json.dumps(raw));del broken['settings'][key]
            with self.assertRaises(ValueError):store.parse(json.dumps(broken))
        raw['results']*=2
        with self.assertRaises(ValueError):store.parse(json.dumps(raw))

    def test_exact_v3_recipe_is_upgraded_only_in_memory(self):
        s=FanSettings().to_dict();s.pop('guard_type');s.pop('guard_pitch_mm')
        old=recipe(s,3);parsed,current=store.parse(json.dumps(old))
        self.assertEqual(parsed,old)
        self.assertEqual(current.guard_type,'spokes')
        self.assertEqual(current.guard_pitch_mm,12)
        for change in ({'guard_type':'rings'},{'guard_pitch_mm':14},{'output':'guard'}):
            with self.subTest(change=change),self.assertRaises(ValueError):
                store.parse(json.dumps({**old,'settings':{**s,**change}}))

    def test_rotor_guard_keeps_three_distinct_owned_outputs(self):
        s=replace(FanSettings(),output='rotor_guard',guard_type='rings')
        value=recipe(s.to_dict());value['results']=[dict(body=name,signature='a'*64) for name in ('rotor','frame','guard')]
        self.assertEqual(store.parse(json.dumps(value))[1],s)
        value['results'][2]['body']='rotor'
        with self.assertRaises(ValueError):store.parse(json.dumps(value))

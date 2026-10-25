"""Planar truss topology, real perpendicular member widths and bounded work."""

from dataclasses import replace
import json
import math
from types import SimpleNamespace as N
import unittest
from Partelier.partelier.tools.truss import planner
from Partelier.partelier.tools.patterns import clipping,perforated_prism
from Partelier.partelier.tools.patterns.settings import PatternSettings


def inside(point,polygon):
    return all((b[0]-a[0])*(point[1]-a[1])-(b[1]-a[1])*(point[0]-a[0])>=-1e-8
               for a,b in zip(polygon,polygon[1:]+polygon[:1]))


class TrussGeometryTests(unittest.TestCase):
    def layout(self,style='truss_warren',bays=6,width=2,border=3,axis='long'):
        return planner.plan((-60,60,-20,20),style,bays,width,border,axis)

    def test_three_distinct_connected_layouts_with_expected_window_counts(self):
        layouts=[self.layout(style) for style in planner.STYLES]
        self.assertEqual([len(p.holes) for p in layouts],[7,12,12])
        self.assertEqual([len(p.members) for p in layouts],[6,11,11])
        for one,two in zip(layouts,layouts[1:]):self.assertNotEqual(one.holes,two.holes)
        for layout in layouts:
            self.assertGreater(layout.material_area_mm2,0)
            self.assertAlmostEqual(layout.open_area_mm2+layout.material_area_mm2,4800)
            for hole in layout.holes:
                self.assertGreater(clipping.area(hole),.01)
                for x,y in hole:
                    self.assertLessEqual(abs(x),57+1e-8);self.assertLessEqual(abs(y),17+1e-8)

    def test_width_is_measured_perpendicular_to_every_diagonal_and_post(self):
        for style in planner.STYLES:
            layout=self.layout(style)
            for a,b in layout.members:
                midpoint=tuple((x+y)/2 for x,y in zip(a,b));length=math.dist(a,b)
                normal=(-(b[1]-a[1])/length,(b[0]-a[0])/length)
                for sign in (-1,1):
                    solid=tuple(p+sign*.97*n for p,n in zip(midpoint,normal))
                    void=tuple(p+sign*1.03*n for p,n in zip(midpoint,normal))
                    self.assertFalse(any(inside(solid,hole) for hole in layout.holes),(style,a,b))
                    self.assertTrue(any(inside(void,hole) for hole in layout.holes),(style,a,b))

    def test_exact_closed_multi_loop_volume_and_uniform_frame_for_all_styles(self):
        frame=N(origin_mm=(0,0,0),x_axis=(1,0,0),y_axis=(0,0,1),z_axis=(0,-1,0))
        for style in planner.STYLES:
            for axis in ('long','short'):
                layout=self.layout(style,axis=axis)
                solid=perforated_prism.plan(frame,layout.outer,layout.holes,-3,0)
                self.assertAlmostEqual(solid.volume_mm3,layout.material_area_mm2*3)
                for x,y in ((-59,0),(59,0),(0,-19),(0,19)):
                    self.assertFalse(any(inside((x,y),hole) for hole in layout.holes))

    def test_long_short_directions_respond_to_the_face_not_fixed_world_axes(self):
        long=self.layout();short=self.layout(axis='short')
        self.assertEqual((long.axis,short.axis),('u','v'))
        turned=planner.plan((-20,20,-60,60),'truss_warren',6,2,3)
        self.assertEqual(turned.axis,'v')
        self.assertAlmostEqual(turned.open_area_mm2,long.open_area_mm2)
        self.assertNotEqual(long.holes,short.holes)

    def test_warren_odd_bays_are_supported_and_work_is_bounded_before_sdk(self):
        self.assertEqual(len(self.layout(bays=5).holes),6)
        large=planner.plan((0,1000,0,100),'truss_pratt',64,1,3)
        self.assertEqual(len(large.holes),128)
        for args in (('truss_warren',65,2,3,'long'),('truss_pratt',3,2,3,'long'),
                     ('truss_howe',True,2,3,'long'),('truss_warren',6,50,3,'long'),
                     ('truss_warren',6,2,30,'long'),('truss_warren',6,math.nan,3,'long')):
            with self.subTest(args=args),self.assertRaises(ValueError):self.layout(*args)

    def test_settings_reject_silent_modes_and_allow_member_width_independent_of_pitch(self):
        settings=PatternSettings(pattern='truss_warren',layout_mode='fill',web_mm=2,border_mm=3)
        self.assertEqual(PatternSettings.from_dict(settings.to_dict()),settings)
        for fields in ({'mode':'emboss'},{'selection_scope':'body'},{'truss_bays':2.5},{'truss_bays':True},
                       {'pattern':'truss_pratt','truss_bays':3},{'rotation_deg':45},{'border_mm':0},
                       {'mount_mode':'plain'},{'grille_profile':'raised'},{'truss_axis':'world_z'}):
            with self.subTest(fields=fields),self.assertRaises(ValueError):replace(settings,**fields)
        self.assertEqual(replace(settings,pitch_mm=1).web_mm,2)

    def test_legacy_version_nine_adds_only_truss_defaults_without_changing_or_writing_settings(self):
        from Partelier.partelier.tools.patterns import recipe
        settings=PatternSettings().to_dict();settings.pop('truss_bays');settings.pop('truss_axis')
        value={'version':9,'tool':'surface_pattern','feature_id':'owned','settings':settings,
               'sources':{'body':'body','faces':['face']}}
        raw=json.dumps(value);parsed,loaded=recipe._parse(raw,N(feature_id='owned'))
        self.assertEqual(parsed,value);self.assertEqual(loaded.truss_bays,6);self.assertEqual(loaded.truss_axis,'long')
        self.assertEqual(loaded.border_mm,settings['border_mm'])
        value['settings']['truss_bays']=6
        with self.assertRaises(ValueError):recipe._parse(json.dumps(value),N(feature_id='owned'))
        value['settings'].pop('truss_bays')
        value['settings'].update(pattern='truss_warren',layout_mode='fill')
        with self.assertRaisesRegex(ValueError,'legacy truss'):recipe._parse(json.dumps(value),N(feature_id='owned'))

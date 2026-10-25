"""Independent mounting dimensions, clearance, fit and exact legacy schemas."""

from dataclasses import replace
import json
from types import SimpleNamespace as N
import unittest
from Partelier.partelier.tools.patterns import mounting,recipe
from Partelier.partelier.tools.patterns.flat_plate import Plate
from Partelier.partelier.tools.patterns.settings import PatternSettings


class MountPlanTests(unittest.TestCase):
    def setUp(self):
        self.settings=PatternSettings(pattern='grille_parallel',layout_mode='fill',mount_mode='countersink')

    def plan(self,settings=None,thickness=3,bounds=(-30,30,-25,25)):
        return mounting.plan(settings or self.settings,bounds,thickness)

    def test_m4_has_separate_diametral_hole_allowance_and_head_percentage(self):
        value=self.plan()
        self.assertAlmostEqual(value.hole_diameter_mm,4.3)
        self.assertAlmostEqual(value.head_diameter_mm,9.856)
        self.assertAlmostEqual(value.countersink_depth_mm,2.778)
        self.assertAlmostEqual((value.head_diameter_mm-value.hole_diameter_mm)/2,value.countersink_depth_mm)
        changed=self.plan(replace(self.settings,mount_clearance_mm=.5))
        self.assertAlmostEqual(changed.head_diameter_mm,value.head_diameter_mm)
        self.assertAlmostEqual(changed.hole_diameter_mm,4.5)
        self.assertAlmostEqual(changed.countersink_depth_mm,2.678)

    def test_measured_head_overrides_catalogue_before_percentage(self):
        value=self.plan(replace(self.settings,mount_head_mm=8))
        self.assertAlmostEqual(value.head_diameter_mm,8.8)
        self.assertAlmostEqual(value.countersink_depth_mm,2.25)
        no_extra=self.plan(replace(self.settings,mount_head_mm=8,mount_head_extra_percent=0))
        self.assertEqual(no_extra.head_diameter_mm,8)

    def test_plain_holes_have_no_head_recess_and_allow_thin_plates(self):
        value=self.plan(replace(self.settings,mount_mode='plain'),thickness=.8)
        self.assertEqual(value.countersink_depth_mm,0)
        self.assertAlmostEqual(value.hole_diameter_mm,4.3)
        with self.assertRaisesRegex(ValueError,'2.98 mm'):self.plan(thickness=2.9)

    def test_four_corners_are_symmetric_inside_the_plate_with_frame_overlap(self):
        value=self.plan()
        self.assertEqual(len(value.centers_mm),4)
        self.assertEqual(sorted(value.centers_mm),sorted((-x,-z) for x,z in value.centers_mm))
        self.assertAlmostEqual(value.inset_mm-value.land_radius_mm,.5)
        self.assertGreaterEqual(self.settings.border_mm+value.land_radius_mm-value.inset_mm,1)
        for i,one in enumerate(value.centers_mm):
            for two in value.centers_mm[i+1:]:
                self.assertGreater(sum((a-b)**2 for a,b in zip(one,two))**.5,2*value.land_radius_mm)
        for (x,z),(lo,hi,bottom,top) in zip(value.centers_mm,value.land_bounds_mm):
            self.assertGreaterEqual(min(x-lo,hi-x,z-bottom,top-z)+1e-8,value.land_radius_mm)
            self.assertTrue(lo==-30 or hi==30)
            self.assertTrue(bottom==-25 or top==25)

    def test_manual_positions_and_all_presets_have_positive_complete_lands(self):
        for screw,nominal in (('M3',3),('M4',4),('M5',5),('M6',6)):
            value=self.plan(replace(self.settings,mount_screw=screw),thickness=6)
            self.assertAlmostEqual(value.hole_diameter_mm,nominal+.3)
            self.assertGreater(value.land_radius_mm,value.head_diameter_mm/2)
        value=self.plan(replace(self.settings,mount_inset_mm=8))
        self.assertEqual(value.inset_mm,8)

    def test_unsupported_geometry_is_refused_without_silently_changing_dimensions(self):
        cases=[(replace(self.settings,mount_inset_mm=2),(-30,30,-25,25)),
               (replace(self.settings,mount_inset_mm=21),(-30,30,-25,25)),
               (replace(self.settings,border_mm=.5),(-30,30,-25,25)),
               (replace(self.settings,mount_head_mm=3),(-30,30,-25,25)),
               (self.settings,(-10,10,-10,10))]
        for settings,bounds in cases:
            before=settings.to_dict()
            with self.subTest(settings=settings,bounds=bounds),self.assertRaises(ValueError):self.plan(settings,bounds=bounds)
            self.assertEqual(settings.to_dict(),before)

    def test_settings_refuse_invalid_snapshots_and_non_grille_mounting(self):
        for values in ({'mount_mode':'thread'},{'mount_screw':'M20'},{'mount_clearance_mm':True},
                       {'mount_head_mm':float('nan')},{'mount_inset_mm':-1},{'mount_head_extra_percent':31},
                       {'mount_clearance_mm':3},{'pattern':'hexagon'}):
            with self.subTest(values=values),self.assertRaises(ValueError):replace(self.settings,**values)
        self.assertEqual(PatternSettings.from_dict(self.settings.to_dict()),self.settings)

    def test_plate_coordinates_follow_face_frame_not_world_z(self):
        frame=N(origin_mm=(10,20,30),x_axis=(0,1,0),y_axis=(1,0,0),z_axis=(0,0,1))
        plate=Plate(None,None,None,frame,(),3,())
        self.assertEqual(plate.world(4,-2,1),(11,24,28))
        self.assertEqual(plate.local(plate.world(4,-2,0)),(4,-2))

    def test_mounting_does_not_change_the_internal_square_repeat_grid(self):
        from Partelier.partelier.tools.patterns.planner import build_layout
        settings=replace(self.settings,pattern='grille_cross',pitch_mm=7,web_mm=2)
        mounted=build_layout(settings,(-30,30,-25,25),max_cells=200)
        plain=build_layout(replace(settings,mount_mode='off'),(-30,30,-25,25),max_cells=200)
        self.assertEqual(mounted,plain)
        self.assertEqual(settings.mount_mode,'countersink')

    def test_version_six_reads_mounting_off_without_rewriting_its_profile(self):
        settings=replace(self.settings,grille_profile='chamfer').to_dict()
        old={key:value for key,value in settings.items() if not key.startswith('mount_')}
        value={'version':6,'tool':'surface_pattern','feature_id':'owned','settings':old,
               'sources':{'body':'body','faces':['face']}}
        raw=json.dumps(value)
        parsed,migrated=recipe._parse(raw,N(feature_id='owned'))
        self.assertEqual(parsed,value)
        self.assertEqual(migrated.grille_profile,'chamfer')
        self.assertEqual(migrated.mount_mode,'off')
        self.assertEqual(migrated.mount_head_extra_percent,10)
        value['settings']['mount_mode']='plain'
        with self.assertRaises(ValueError):recipe._parse(json.dumps(value),N(feature_id='owned'))

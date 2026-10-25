"""Closed material, exact volume and unsupported underside refusals."""

from types import SimpleNamespace as N
import json
import unittest
from unittest.mock import patch
from Partelier.partelier.tools.patterns import profile_loft,prism,clipping
from Partelier.partelier.tools.patterns.settings import PatternSettings
from test_pattern_direct_prism import FRAME,api
from test_perforated_prism import OUTER,HOLES,MultiDefinition


class ProfileGeometryTests(unittest.TestCase):
    def test_straight_profile_preserves_all_openings_and_exact_volume(self):
        plan=profile_loft.plan(FRAME,OUTER,HOLES,OUTER,HOLES,0,3)
        self.assertAlmostEqual(plan.volume_mm3,(400-16-25)*3)
        definition=MultiDefinition()
        with patch.object(prism,'_api',return_value=api(definition)):
            body=profile_loft.create(FRAME,OUTER,HOLES,OUTER,HOLES,0,3)
        self.assertAlmostEqual(body.volume,1.077)
        self.assertEqual(definition.create_calls,1)

    def test_45_degree_holes_keep_their_area_and_close_into_one_solid(self):
        upper=tuple(tuple((u+2,v) for u,v in hole) for hole in HOLES)
        plan=profile_loft.plan(FRAME,OUTER,HOLES,OUTER,upper,0,2)
        self.assertAlmostEqual(plan.volume_mm3,(400-16-25)*2)
        definition=MultiDefinition()
        with patch.object(prism,'_api',return_value=api(definition)):
            body=profile_loft.create(FRAME,OUTER,HOLES,OUTER,upper,0,2)
        self.assertAlmostEqual(body.volume,plan.volume_mm3/1000)

    def test_excessive_underside_and_loop_collisions_refuse_before_sdk(self):
        steep=tuple(tuple((u+3,v) for u,v in hole) for hole in HOLES)
        with patch.object(prism,'_api') as sdk:
            with self.assertRaisesRegex(ValueError,'45 degrees'):
                profile_loft.create(FRAME,OUTER,HOLES,OUTER,steep,0,2)
            with self.assertRaises(ValueError):
                profile_loft.create(FRAME,OUTER,HOLES,OUTER,(HOLES[0],HOLES[0]),0,2)
        sdk.assert_not_called()

    def test_chamfer_material_shrinks_upward_and_retains_positive_solid_volume(self):
        upper=tuple(clipping.offset_convex(hole,-.4) for hole in HOLES)
        plan=profile_loft.plan(FRAME,OUTER,HOLES,clipping.offset_convex(OUTER,.4),upper,2,2.4)
        self.assertGreater(plan.volume_mm3,0)
        self.assertLess(plan.volume_mm3,(400-16-25)*.4)
        definition=MultiDefinition()
        with patch.object(prism,'_api',return_value=api(definition)):
            body=profile_loft.create(FRAME,OUTER,HOLES,clipping.offset_convex(OUTER,.4),upper,2,2.4)
        self.assertAlmostEqual(body.volume,plan.volume_mm3/1000)

    def test_nonplanar_twisted_walls_refuse(self):
        hole=((-4,-4),(4,-4),(4,4),(-4,4))
        rotated=((-3,-5),(5,-3),(3,5),(-5,3))
        with self.assertRaisesRegex(ValueError,'non-planar'):
            profile_loft.plan(FRAME,OUTER,(hole,),OUTER,(rotated,),0,3)

    def test_print_direction_is_relative_to_plate_normal(self):
        turned=N(origin_mm=FRAME.origin_mm,x_axis=(0,1,0),y_axis=(0,0,1),z_axis=(1,0,0))
        upper=tuple(tuple((u+2,v) for u,v in hole) for hole in HOLES)
        self.assertAlmostEqual(profile_loft.plan(turned,OUTER,HOLES,OUTER,upper,0,2).volume_mm3,718)

    def test_settings_reject_unsupported_profiles_nonfinite_height_and_bounds(self):
        for values in ({'grille_profile':'round'},{'grille_height_mm':True},{'grille_height_mm':float('nan')},
                       {'grille_height_mm':0},{'grille_height_mm':21}):
            with self.subTest(values=values),self.assertRaises(ValueError):PatternSettings(**values)
        settings=PatternSettings(pattern='grille_louver',layout_mode='fill',grille_profile='chamfer')
        self.assertEqual(PatternSettings.from_dict(settings.to_dict()),settings)


class VersionFiveTests(unittest.TestCase):
    def test_old_recipe_gains_only_flat_profile_defaults_without_writes(self):
        from Partelier.partelier.tools.patterns import recipe
        from types import SimpleNamespace as N
        settings=PatternSettings(pattern='grille_cross',layout_mode='fill').to_dict()
        settings.pop('grille_profile');settings.pop('grille_height_mm')
        record=N(feature_id='test')
        value={'version':5,'tool':'surface_pattern','feature_id':'test','settings':settings,
               'sources':{'body':'body','faces':['face']}}
        saved,migrated=recipe._parse(json.dumps(value),record)
        self.assertEqual(saved,value)
        self.assertEqual(migrated.grille_profile,'flat')
        self.assertEqual(migrated.grille_height_mm,3)
        value['settings']['grille_profile']='raised'
        with self.assertRaises(ValueError):recipe._parse(json.dumps(value),record)

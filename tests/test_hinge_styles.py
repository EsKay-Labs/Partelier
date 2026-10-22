"""Pin-hinge profile, finish and legacy contracts; no native kernel claims."""

from dataclasses import replace
import json
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from Partelier.partelier.tools.hinge import fusion
from Partelier.partelier.tools.hinge.planner import build_hinge_plan
from Partelier.partelier.tools.hinge.settings import HingeSettings
from test_hinge_rounding import AnalyticManager, Body
from test_hinge_fusion import part_fixture


class StyleSettingsTests(unittest.TestCase):
    def test_defaults_and_strict_style_fields(self):
        current = HingeSettings()
        self.assertEqual(current.knuckle_profile, "round")
        self.assertFalse(current.fillet_edges)
        for profile in ("oval", "", None, True, 1):
            with self.subTest(profile=profile), self.assertRaises(ValueError):
                replace(current, knuckle_profile=profile)
        for value in (0, 1, "yes", None):
            with self.subTest(value=value), self.assertRaises(ValueError):
                replace(current, fillet_edges=value)
        for radius in (0, -1, True, float("nan"), float("inf")):
            with self.subTest(radius=radius), self.assertRaises(ValueError):
                replace(current, fillet_radius_mm=radius)
        with self.assertRaisesRegex(ValueError, "either chamfer or fillet"):
            HingeSettings(fillet_edges=True, chamfer_edges=True)

    def test_round_radius_preserves_barrel_wall_pin_web_and_hole_material(self):
        HingeSettings(fillet_edges=True)
        HingeSettings(fillet_edges=True, output_mode="separate", screw_holes=True)
        for dimensions in ({"fillet_radius_mm": 1.2}, {"pin_diameter_mm": 1},
                           {"leaf_thickness_mm": .7}, {"length_mm": 5},
                           {"output_mode": "separate", "leaf_reach_mm": 5},
                           {"output_mode": "separate", "screw_holes": True, "screw_diameter_mm": 6},
                           {"output_mode": "separate", "leaf_profile": "rounded"}):
            with self.subTest(dimensions=dimensions), self.assertRaises(ValueError):
                HingeSettings(fillet_edges=True, **dimensions)

    def test_square_housing_rejects_bore_or_web_that_cannot_fit_inscribed_section(self):
        with self.assertRaisesRegex(ValueError,"square housing"):
            HingeSettings(knuckle_profile="square",pin_diameter_mm=5.5)
        with self.assertRaisesRegex(ValueError,"contact height"):
            HingeSettings(knuckle_profile="square",leaf_thickness_mm=1)
        with self.assertRaisesRegex(ValueError,"wall thickness"):
            HingeSettings(knuckle_profile="square",fillet_edges=True)

    def test_profile_and_finish_keep_nominal_layout_and_bore(self):
        standard = build_hinge_plan(HingeSettings())
        for dimensions in ({"knuckle_profile": "square"}, {"fillet_edges": True}):
            candidate = build_hinge_plan(HingeSettings(**dimensions))
            self.assertEqual(candidate.knuckles, standard.knuckles)
            self.assertEqual(candidate.webs, standard.webs)
            self.assertEqual(candidate.bore_radius_mm, standard.bore_radius_mm)
            self.assertEqual(candidate.pin_start_mm, standard.pin_start_mm)
            self.assertEqual(candidate.pin_end_mm, standard.pin_end_mm)

    def test_five_preset_topologies_are_valid_and_serializable(self):
        for count, profile, chamfer, rounded in ((5,"round",False,False),
                (5,"round",False,True),(5,"square",True,False),
                (3,"round",False,True),(11,"round",True,False)):
            for mode in ("attached", "separate"):
                candidate = HingeSettings(knuckle_count=count, knuckle_profile=profile,
                    chamfer_edges=chamfer, fillet_edges=rounded, output_mode=mode)
                self.assertEqual(HingeSettings.from_dict(candidate.to_dict()), candidate)
                self.assertEqual(len(build_hinge_plan(candidate).knuckles), count)

    def test_rounding_scales_with_all_dimensions(self):
        original = HingeSettings(fillet_edges=True, output_mode="separate", screw_holes=True)
        for scale in (.01, .1, 10, 1000):
            scaled = HingeSettings(**{key: value*scale if key.endswith("_mm") else value
                                     for key,value in original.to_dict().items()})
            self.assertAlmostEqual(scaled.fillet_radius_mm/scale, .6)

    def test_current_recipe_round_trips_and_version_five_retains_original_finish(self):
        settings = HingeSettings(knuckle_profile="square", fillet_edges=True, fillet_radius_mm=.4)
        _,_,_,_,recipe = part_fixture(settings)
        self.assertEqual(recipe["version"], 8)
        self.assertEqual(fusion._read_recipe(json.dumps(recipe))[1], settings)
        legacy = {**recipe, "version": 5, "settings": HingeSettings(chamfer_edges=True).to_dict()}
        legacy["settings"].pop("web_profile")
        legacy["settings"].pop("rotation_clearance_mm")
        for key in fusion.STYLE_DEFAULTS: legacy["settings"].pop(key)
        original = json.dumps(legacy, sort_keys=True)
        raw, restored = fusion._read_recipe(json.dumps(legacy))
        self.assertEqual(json.dumps(raw, sort_keys=True), original)
        self.assertTrue(restored.chamfer_edges)
        self.assertFalse(restored.fillet_edges)
        self.assertEqual(restored.knuckle_profile, "round")
        legacy["settings"]["knuckle_profile"]="square"
        with self.assertRaisesRegex(ValueError,"version 5"):
            fusion._read_recipe(json.dumps(legacy))
        recipe["settings"].pop("fillet_radius_mm")
        with self.assertRaises(ValueError): fusion._read_recipe(json.dumps(recipe))


class StyleAdapterTests(unittest.TestCase):
    def setUp(self):
        self.frame=fusion.HingeFrame((0,0,0),(1,0,0),(0,1,0),(0,0,1))
        self.manager=AnalyticManager()
        self.api=(SimpleNamespace(
            Point3D=SimpleNamespace(create=lambda *args:args),
            Vector3D=SimpleNamespace(create=lambda *args:args),
            OrientedBoundingBox3D=SimpleNamespace(create=lambda *args:args)),
            SimpleNamespace(BooleanTypes=SimpleNamespace(UnionBooleanType="union",
                DifferenceBooleanType="difference",IntersectionBooleanType="intersection"),
                TemporaryBRepManager=SimpleNamespace(get=lambda:self.manager)))
        self.api_patch=patch.object(fusion,"_api",return_value=self.api)
        self.api_patch.start()
        self.addCleanup(self.api_patch.stop)

    def knuckle(self, settings):
        plan=build_hinge_plan(settings)
        attachment=fusion._box(self.manager,self.frame,plan.webs[0])
        return fusion._knuckle_body(self.manager,self.frame,plan,plan.knuckles[0],attachment),plan

    def test_linear_has_actual_square_corners_and_retains_circular_through_bore(self):
        round_body, plan=self.knuckle(HingeSettings())
        square_body,_=self.knuckle(HingeSettings(knuckle_profile="square"))
        midpoint=(plan.knuckles[0].start_mm+plan.knuckles[0].end_mm)/2
        corner=(.38,midpoint/10,.02)
        self.assertFalse(round_body.contains(corner))
        self.assertFalse(square_body.contains(corner))
        outer_side=(.38,midpoint/10,.4)
        self.assertTrue(round_body.contains(outer_side))
        self.assertFalse(square_body.contains(outer_side))
        half=plan.barrel_radius_mm/(2**.5)
        self.assertAlmostEqual((2*half*half)**.5,plan.barrel_radius_mm)
        self.assertTrue(square_body.contains((.27,midpoint/10,.14)))
        for body in (round_body,square_body):
            self.assertFalse(body.contains((0,midpoint/10,.4)))
            self.assertTrue(body.contains((0,midpoint/10,.65)))

    def test_soft_barrel_is_rounded_at_ends_and_bore_has_true_round_mouth(self):
        body,plan=self.knuckle(HingeSettings(fillet_edges=True))
        start=plan.knuckles[0].start_mm
        self.assertFalse(body.contains((.39,(start+.01)/10,.4)))
        self.assertTrue(body.contains((.39,(start+1)/10,.4)))
        self.assertFalse(body.contains((.2,(start+.001)/10,.4)))
        self.assertTrue(body.contains((.2,(start+1)/10,.4)))
        self.assertEqual(sum(name=="torus" for name,_ in self.manager.calls),4)

    def test_separate_and_attached_round_only_new_details_and_keep_source_objects(self):
        for mode in ("attached","separate"):
            with self.subTest(mode=mode):
                settings=HingeSettings(fillet_edges=True,output_mode=mode,screw_holes=mode=="separate",web_profile="flat",rotation_clearance_mm=0)
                a,b=Body(),Body()
                edge=object()
                self.manager.copy=Mock(side_effect=lambda body:Body())
                with patch.object(fusion,"_selection",return_value=(self.frame,(),edge)),patch.object(
                    fusion,"_coincident_face_edges",return_value=()),patch.object(
                    fusion,"_straight_endpoints",return_value=((0,-2.5,0),(0,2.5,0))),patch.object(
                    fusion,"rounded_box",side_effect=lambda *args:Body()) as boxes,patch.object(
                    fusion,"rounded_axis_body",side_effect=lambda *args:Body()) as pins,patch.object(
                    fusion,"round_bore_entry") as entries,patch.object(
                    fusion,"_knuckle_body",side_effect=lambda *args:Body()),patch.object(
                    fusion,"_drill_leaf") as holes,patch.object(fusion,"_boolean"),patch.object(
                    fusion,"_positive_attachment"),patch.object(fusion,"_require_separate"):
                    result=fusion.prepare_hinge(object(),SimpleNamespace(body=a),SimpleNamespace(body=b),edge,settings)
                self.assertEqual(boxes.call_count,settings.knuckle_count+(2 if mode=="separate" else 0))
                self.assertEqual(pins.call_count,1)
                self.assertEqual(entries.call_count,8 if mode=="separate" else 0)
                self.assertEqual(holes.call_count,4 if mode=="separate" else 0)
                for call in entries.call_args_list:
                    self.assertIsNot(call.args[2],a)
                    self.assertIsNot(call.args[2],b)
                    self.assertEqual(call.kwargs["axis"],"z")
                self.assertEqual((a.volume,b.volume),(100,100))
                self.assertEqual({role for role,_ in result.result_bodies},{"A","B","pin"})


if __name__=="__main__": unittest.main()

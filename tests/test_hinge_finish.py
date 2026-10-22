"""Geometric edge-finish contracts; native kernel verification is separate."""

from dataclasses import replace
import json
import math
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from Partelier.partelier.tools.hinge import fusion
from Partelier.partelier.tools.hinge.finish import box_chamfer_wedges
from Partelier.partelier.tools.hinge.planner import WebBounds, build_hinge_plan
from Partelier.partelier.tools.hinge.settings import HingeSettings


def dot(one, two):
    return sum(a*b for a,b in zip(one,two))


class FinishPlanTests(unittest.TestCase):
    def setUp(self):
        self.bounds = WebBounds("A", -12, -2, -20, 20, 0, 2)

    def test_all_twelve_edges_have_equal_distance_45_degree_cut_planes(self):
        size = .3
        cuts = box_chamfer_wedges(self.bounds, size)
        self.assertEqual(len(cuts), 12)
        for cut in cuts:
            self.assertAlmostEqual(dot(cut.normal_axis, cut.normal_axis), 1)
            self.assertAlmostEqual(dot(cut.edge_axis, cut.edge_axis), 1)
            self.assertAlmostEqual(dot(cut.tangent_axis, cut.tangent_axis), 1)
            self.assertAlmostEqual(dot(cut.edge_axis, cut.tangent_axis), 0)
            active = [i for i,n in enumerate(cut.normal_axis) if n]
            self.assertEqual(len(active), 2)
            self.assertAlmostEqual(abs(cut.normal_axis[active[0]]), abs(cut.normal_axis[active[1]]))
            minima=(-12,-20,0); maxima=(-2,20,2)
            edge=[(low+high)/2 for low,high in zip(minima,maxima)]
            for index in active:
                edge[index]=maxima[index] if cut.normal_axis[index]>0 else minima[index]
            inner_plane=dot(cut.center_mm,cut.normal_axis)-cut.depth_mm/2
            self.assertAlmostEqual(dot(edge,cut.normal_axis)-inner_plane,size/math.sqrt(2))
            for index in active:
                on_face=edge.copy(); on_face[index]-=math.copysign(size,cut.normal_axis[index])
                self.assertAlmostEqual(dot(on_face,cut.normal_axis),inner_plane)
                on_face[index]-=math.copysign(.01,cut.normal_axis[index])
                self.assertLess(dot(on_face,cut.normal_axis),inner_plane)

    def test_rounded_profiles_keep_curved_vertical_edges_and_finish_other_ten(self):
        for side in (-1,1):
            cuts=box_chamfer_wedges(self.bounds,.3,side)
            self.assertEqual(len(cuts),10)
            vertical=[c for c in cuts if c.edge_axis[2]]
            self.assertEqual(len(vertical),2)
            self.assertTrue(all(math.copysign(1,c.normal_axis[0])==-side for c in vertical))

    def test_degenerate_or_overlarge_box_finish_is_rejected(self):
        for size in (0,-1,1,float("nan"),float("inf"),True,".3"):
            with self.subTest(size=size),self.assertRaises(ValueError):
                box_chamfer_wedges(self.bounds,size)
        with self.assertRaises(ValueError):
            box_chamfer_wedges(replace(self.bounds,x_min_mm=100),.3)

    def test_finish_defaults_and_legacy_shape_are_unchanged(self):
        settings=HingeSettings()
        self.assertFalse(settings.chamfer_edges)
        self.assertEqual(settings.chamfer_size_mm,.3)
        finished=replace(settings,chamfer_edges=True)
        self.assertEqual(build_hinge_plan(settings).webs,build_hinge_plan(finished).webs)
        self.assertEqual(build_hinge_plan(settings).knuckles,build_hinge_plan(finished).knuckles)
        self.assertEqual(HingeSettings.from_dict(finished.to_dict()),finished)

    def test_boolean_and_size_are_strict_even_when_disabled(self):
        for value in (0,1,"yes",None):
            with self.subTest(value=value),self.assertRaises(ValueError):
                HingeSettings(chamfer_edges=value)
        for value in (0,-.1,float("nan"),float("inf"),True):
            with self.subTest(value=value),self.assertRaises(ValueError):
                HingeSettings(chamfer_size_mm=value)

    def test_finish_cannot_consume_wall_pin_or_web_contact(self):
        for values in ({"chamfer_size_mm":1.2},
                       {"pin_diameter_mm":.4,"chamfer_size_mm":.3},
                       {"leaf_thickness_mm":.6,"chamfer_size_mm":.3},
                       {"length_mm":2,"axial_gap_mm":.01,"chamfer_size_mm":.3}):
            with self.subTest(values=values),self.assertRaisesRegex(ValueError,"Chamfer"):
                HingeSettings(chamfer_edges=True,**values)

    def test_separate_plates_and_hole_mouths_retain_material(self):
        HingeSettings(output_mode="separate",leaf_profile="rounded",screw_holes=True,chamfer_edges=True)
        for values in ({"leaf_thickness_mm":.7,"chamfer_size_mm":.4},
                       {"leaf_reach_mm":4.8,"chamfer_size_mm":.3},
                       {"leaf_profile":"rounded","chamfer_size_mm":1},
                       {"screw_holes":True,"screw_diameter_mm":7,"chamfer_size_mm":.3},
                       {"screw_holes":True,"screw_end_margin_mm":2,"chamfer_size_mm":.3}):
            with self.subTest(values=values),self.assertRaises(ValueError):
                HingeSettings(output_mode="separate",chamfer_edges=True,**values)

    def test_finish_scales_without_changing_angles_or_nominal_fit(self):
        base=HingeSettings(output_mode="separate",leaf_profile="rounded",screw_holes=True,chamfer_edges=True)
        for scale in (.01, .1, 10,1000):
            values={k:v*scale if k.endswith("_mm") else v for k,v in base.to_dict().items()}
            scaled=HingeSettings(**values)
            self.assertAlmostEqual(scaled.chamfer_size_mm/scale,base.chamfer_size_mm)
            self.assertAlmostEqual(build_hinge_plan(scaled).bore_radius_mm/scale,1.65)

    def test_version_four_is_read_without_applying_finish_or_migrating(self):
        from test_hinge_fusion import part_fixture
        _,_,_,_,recipe=part_fixture()
        recipe["version"]=4
        for key in (*fusion.FINISH_DEFAULTS, *fusion.STYLE_DEFAULTS, *fusion.SUPPORT_DEFAULTS, *fusion.RELIEF_DEFAULTS):recipe["settings"].pop(key)
        original=json.dumps(recipe,sort_keys=True)
        raw,settings=fusion._read_recipe(json.dumps(recipe))
        self.assertEqual(json.dumps(raw,sort_keys=True),original)
        self.assertFalse(settings.chamfer_edges)
        recipe["settings"]["chamfer_edges"]=True
        with self.assertRaisesRegex(ValueError,"version 4"):
            fusion._read_recipe(json.dumps(recipe))


class Body:
    isValid=True
    isSolid=True
    lumps=SimpleNamespace(count=1)
    def __init__(self):self.volume=100


class FinishAdapterTests(unittest.TestCase):
    def setUp(self):
        self.frame=fusion.HingeFrame((10,20,30),(1,0,0),(0,1,0),(0,0,1))
        def boolean(target,tool,operation):
            target.volume += 1 if operation==1 else -.1
            return True
        self.manager=SimpleNamespace(createCylinderOrCone=Mock(side_effect=lambda *args:Body()),
                                     createBox=Mock(side_effect=lambda *args:Body()),
                                     booleanOperation=Mock(side_effect=boolean),copy=Mock())
        self.core=SimpleNamespace(
            Point3D=SimpleNamespace(create=lambda *args:args),
            Vector3D=SimpleNamespace(create=lambda *args:args),
            OrientedBoundingBox3D=SimpleNamespace(create=lambda *args:args))
        self.api=(self.core,SimpleNamespace(BooleanTypes=SimpleNamespace(
            UnionBooleanType=1,DifferenceBooleanType=2,IntersectionBooleanType=3),
            TemporaryBRepManager=SimpleNamespace(get=lambda:self.manager)))

    def test_cylindrical_middle_and_fit_diameter_survive_both_end_bevels(self):
        with patch.object(fusion,"_api",return_value=self.api):
            fusion._beveled_axis_body(self.manager,self.frame,-20,20,1.5,4,.3)
        calls=[call.args for call in self.manager.createCylinderOrCone.call_args_list]
        self.assertEqual(len(calls),3)
        self.assertAlmostEqual(calls[0][1],.15)
        self.assertAlmostEqual(calls[0][3],.15)
        self.assertAlmostEqual(calls[1][1],.12)
        self.assertAlmostEqual(calls[2][3],.12)
        self.assertAlmostEqual(calls[1][0][1],0)
        self.assertAlmostEqual(calls[2][2][1],4)

    def test_box_cutters_follow_translated_rotated_frames_and_mm_cm_boundary(self):
        bounds=WebBounds("A",-12,-2,-20,20,0,2)
        frame=fusion.HingeFrame((10,20,30),(0,1,0),(-1,0,0),(0,0,1))
        with patch.object(fusion,"_api",return_value=self.api):
            fusion._chamfer_box(self.manager,frame,Body(),bounds,.3)
        self.assertEqual(self.manager.createBox.call_count,12)
        cut=box_chamfer_wedges(bounds,.3)[0]
        actual=self.manager.createBox.call_args_list[0].args[0]
        expected=frame.point_mm(*cut.center_mm)
        for a,e in zip(actual[0],expected):self.assertAlmostEqual(a,e/10)
        self.assertAlmostEqual(actual[3],cut.length_mm/10)
        self.assertTrue(all(call.args[2]==2 for call in self.manager.booleanOperation.call_args_list))

    def test_rounded_leaf_finishes_curves_with_quarter_cones(self):
        plate=build_hinge_plan(HingeSettings(output_mode="separate",leaf_profile="rounded")).plates[0]
        with patch.object(fusion,"_api",return_value=self.api),patch.object(fusion,"_chamfer_box") as flat:
            fusion._finish_leaf_plate(self.manager,self.frame,Body(),plate,.3)
        self.assertEqual(flat.call_args.args[-1],-1)
        calls=[call.args for call in self.manager.createCylinderOrCone.call_args_list]
        self.assertEqual(len(calls),8)
        cones=[args for args in calls if args[1]!=args[3]]
        self.assertEqual(len(cones),4)
        self.assertTrue(all(min(args[1],args[3])>0 for args in cones))
        self.assertEqual(sum(call.args[2]==3 for call in self.manager.booleanOperation.call_args_list),4)

    def test_hole_entry_finish_keeps_bore_and_only_changes_generated_leaf(self):
        plan=build_hinge_plan(HingeSettings(output_mode="separate",screw_holes=True))
        target=Body()
        with patch.object(fusion,"_api",return_value=self.api):
            fusion._drill_leaf(self.manager,self.frame,target,plan.plates[0],plan.mounting_holes[0],.3)
        calls=[call.args for call in self.manager.createCylinderOrCone.call_args_list]
        self.assertEqual(len(calls),3)
        self.assertAlmostEqual(calls[0][1],.16)
        self.assertTrue(all(call.args[0] is target for call in self.manager.booleanOperation.call_args_list))
        self.assertLess(target.volume,100)

    def test_prepare_applies_finish_only_to_new_hinge_geometry_in_both_modes(self):
        for mode in ("attached", "separate"):
            with self.subTest(mode=mode):
                settings=HingeSettings(output_mode=mode,chamfer_edges=True,screw_holes=mode=="separate",web_profile="flat",rotation_clearance_mm=0)
                original_a,original_b=Body(),Body()
                face_a,face_b=SimpleNamespace(body=original_a),SimpleNamespace(body=original_b)
                edge=object(); design=object()
                self.manager.copy.side_effect=lambda source:Body()
                point=lambda y:(0,y,0)
                with patch.object(fusion,"_api",return_value=self.api),patch.object(
                        fusion,"_selection",return_value=(self.frame,("unchanged",),edge)),patch.object(
                        fusion,"_coincident_face_edges",return_value=()),patch.object(
                        fusion,"_straight_endpoints",return_value=(point(-2.5),point(2.5))),patch.object(
                        fusion,"_box",side_effect=lambda *args:Body()),patch.object(
                        fusion,"_leaf_plate",side_effect=lambda *args:Body()),patch.object(
                        fusion,"_finish_leaf_plate") as finish_leaf,patch.object(
                        fusion,"_chamfer_box") as finish_web,patch.object(
                        fusion,"_knuckle_body",side_effect=lambda *args:Body()),patch.object(
                        fusion,"_beveled_axis_body",side_effect=lambda *args:Body()) as finish_pin,patch.object(
                        fusion,"_drill_leaf") as drill,patch.object(
                        fusion,"_require_separate"),patch.object(fusion,"_positive_attachment"):
                    prepared=fusion.prepare_hinge(design,face_a,face_b,edge,settings)
                self.assertEqual(finish_web.call_count,settings.knuckle_count)
                self.assertEqual(finish_leaf.call_count,2 if mode=="separate" else 0)
                self.assertEqual(finish_pin.call_count,1)
                self.assertEqual(drill.call_count,4 if mode=="separate" else 0)
                self.assertTrue(all(call.args[-1]==.3 for call in drill.call_args_list))
                for call in finish_web.call_args_list+finish_leaf.call_args_list:
                    self.assertIsNot(call.args[2],original_a)
                    self.assertIsNot(call.args[2],original_b)
                self.assertEqual(original_a.volume,100)
                self.assertEqual(original_b.volume,100)
                self.assertEqual({role for role,_ in prepared.result_bodies},{"A","B","pin"})

    def test_successful_but_unchanged_kernel_cut_is_rejected(self):
        self.manager.booleanOperation.side_effect=None
        self.manager.booleanOperation.return_value=True
        with patch.object(fusion,"_api",return_value=self.api):
            with self.assertRaisesRegex(ValueError,"No positive chamfer volume"):
                fusion._remove_finish_tool(self.manager,Body(),Body(),"Finish failed.")

    def test_kernel_failure_does_not_silently_skip_a_requested_finish(self):
        self.manager.booleanOperation.return_value=False
        self.manager.booleanOperation.side_effect=None
        with patch.object(fusion,"_api",return_value=self.api):
            with self.assertRaisesRegex(ValueError,"chamfer"):
                fusion._beveled_axis_body(self.manager,self.frame,-20,20,1.5,4,.3)


if __name__=="__main__":unittest.main()

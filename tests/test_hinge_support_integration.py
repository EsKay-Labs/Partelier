"""Support routing and recipe compatibility, independent of the native kernel."""

from dataclasses import replace
import json
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from Partelier.partelier.tools.hinge import fusion
from Partelier.partelier.tools.hinge.planner import build_hinge_plan
from Partelier.partelier.tools.hinge.settings import HingeSettings
from test_hinge_fusion import part_fixture


class SupportIntegrationTests(unittest.TestCase):
    def test_every_alternating_knuckle_in_every_placement_uses_the_new_support(self):
        settings = HingeSettings(hinge_count=3, length_mm=10,
                                 start_margin_mm=5, end_margin_mm=5)
        frame = fusion.HingeFrame((0, 0, 0), (1, 0, 0), (0, 1, 0), (0, 0, 1))
        sources = tuple(SimpleNamespace(volume=100) for _ in range(2))
        def copy(source):
            return SimpleNamespace(isValid=True, isSolid=True,
                                   lumps=SimpleNamespace(count=1), source=source, volume=100)
        manager = SimpleNamespace(copy=copy)
        api = (None, SimpleNamespace(TemporaryBRepManager=SimpleNamespace(get=lambda: manager),
                                    BooleanTypes=SimpleNamespace(UnionBooleanType=1)))
        edge = object()
        with patch.object(fusion, "_api", return_value=api), patch.object(
                fusion, "_selection", return_value=(frame, (), edge)), patch.object(
                fusion, "_coincident_face_edges", return_value=()), patch.object(
                fusion, "_straight_endpoints", return_value=((0, -2.5, 0), (0, 2.5, 0))), patch.object(
                fusion, "make_tangent_support", side_effect=lambda *args: object()) as supports, patch.object(
                fusion, "_knuckle_body", side_effect=lambda *args: object()) as knuckles, patch.object(
                fusion, "cut_rotation_relief", return_value=()), patch.object(
                fusion, "_positive_attachment") as attachments, patch.object(
                fusion, "_cylinder", side_effect=lambda *args: object()), patch.object(
                fusion, "_boolean"), patch.object(fusion, "_require_separate"):
            prepared = fusion.prepare_hinge(object(), SimpleNamespace(body=sources[0]),
                                           SimpleNamespace(body=sources[1]), edge, settings)
        self.assertEqual(supports.call_count, 15)
        self.assertEqual(knuckles.call_count, 15)
        self.assertEqual(attachments.call_count, 15)
        self.assertEqual([call.args[2].owner for call in supports.call_args_list],
                         ["A", "B", "A", "B", "A"] * 3)
        self.assertEqual([call.args[1].origin_mm[1] for call in supports.call_args_list],
                         [-15] * 5 + [0] * 5 + [15] * 5)
        self.assertTrue(all(call.args[3].web_profile == "tangent" for call in supports.call_args_list))
        self.assertEqual({role for role, _ in prepared.result_bodies},
                         {"A", "B", "pin_1", "pin_2", "pin_3"})
        self.assertEqual([body.volume for body in sources], [100, 100])

    def test_explicit_flat_keeps_the_existing_attachment_and_finish(self):
        frame = object()
        for changes in ({"web_profile": "flat"},):
            settings = HingeSettings(**changes)
            web = build_hinge_plan(settings).webs[0]
            result = object()
            with self.subTest(changes=changes), patch.object(fusion, "make_tangent_support") as taper, patch.object(
                    fusion, "_box", return_value=result) as box:
                self.assertIs(fusion._attachment_body(object(), frame, web, settings), result)
                taper.assert_not_called()
                box.assert_called_once()
        for finish in ("chamfer", "fillet"):
            settings = HingeSettings(web_profile="flat", chamfer_edges=finish == "chamfer",
                                     fillet_edges=finish == "fillet")
            web = build_hinge_plan(settings).webs[0]
            result = object()
            with self.subTest(finish=finish), patch.object(fusion, "make_tangent_support") as taper, patch.object(
                    fusion, "_box", return_value=result), patch.object(
                    fusion, "rounded_box", return_value=result) as rounding, patch.object(
                    fusion, "_chamfer_box") as chamfer:
                self.assertIs(fusion._attachment_body(object(), frame, web, settings), result)
                taper.assert_not_called()
                self.assertEqual(rounding.call_count, int(finish == "fillet"))
                self.assertEqual(chamfer.call_count, int(finish == "chamfer"))

    def test_every_profile_and_output_routes_taper_and_preserves_legacy_seven_on_read(self):
        for mode in ("attached", "separate"):
            for housing in ("round", "square"):
                settings = HingeSettings(output_mode=mode, knuckle_profile=housing)
                web = build_hinge_plan(settings).webs[0]
                target = object()
                with self.subTest(mode=mode, housing=housing), patch.object(
                        fusion, "make_tangent_support", return_value=target) as taper, patch.object(
                        fusion, "_box") as flat:
                    self.assertIs(fusion._attachment_body(object(), object(), web, settings), target)
                    taper.assert_called_once()
                    flat.assert_not_called()
        _, _, _, _, recipe = part_fixture(HingeSettings())
        recipe["version"] = 7
        recipe["settings"].pop("rotation_clearance_mm")
        before = json.dumps(recipe, sort_keys=True)
        raw, restored = fusion._read_recipe(json.dumps(recipe))
        self.assertEqual(json.dumps(raw, sort_keys=True), before)
        self.assertEqual(restored.web_profile, "tangent")
        self.assertEqual(restored.rotation_clearance_mm, 0)

    def test_version_six_keeps_flat_geometry_and_requires_its_exact_original_schema(self):
        _, _, _, _, current = part_fixture(HingeSettings(fillet_edges=True))
        legacy = {**current, "version": 6, "settings": dict(current["settings"])}
        legacy["settings"].pop("web_profile")
        legacy["settings"].pop("rotation_clearance_mm")
        before = json.dumps(legacy, sort_keys=True)
        raw, settings = fusion._read_recipe(json.dumps(legacy))
        self.assertEqual(json.dumps(raw, sort_keys=True), before)
        self.assertEqual(settings.web_profile, "flat")
        self.assertTrue(settings.fillet_edges)
        self.assertEqual(replace(settings, web_profile="tangent", rotation_clearance_mm=.3), HingeSettings(fillet_edges=True))
        for change in ("extra", "missing"):
            changed = {**legacy, "settings": dict(legacy["settings"])}
            if change == "extra":
                changed["settings"]["web_profile"] = "tangent"
            else:
                changed["settings"].pop("fillet_radius_mm")
            with self.subTest(change=change), self.assertRaisesRegex(ValueError, "version 6"):
                fusion._read_recipe(json.dumps(changed))
        current["settings"].pop("web_profile")
        with self.assertRaises(ValueError):
            fusion._read_recipe(json.dumps(current))


if __name__ == "__main__":
    unittest.main()

"""Compound finishing order and final-output routing, without native CAD claims."""

from contextlib import ExitStack
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from Partelier.partelier.tools.hinge import fusion
from Partelier.partelier.tools.hinge.settings import HingeSettings


class Body:
    isValid = True
    isSolid = True
    lumps = SimpleNamespace(count=1)

    def __init__(self, label, *, final=False, origin=None):
        self.label = label
        self.parts = {label}
        self.cuts = []
        self.volume = 100
        self.final = final
        self.origin = origin


class Manager:
    def __init__(self):
        self.operations = []

    def copy(self, body):
        copy = Body("copy", final=body.final, origin=body)
        copy.parts = set(body.parts)
        copy.cuts = list(body.cuts)
        copy.volume = body.volume
        return copy

    def booleanOperation(self, target, tool, operation):
        self.operations.append((operation, target, tool))
        if operation == "union":
            target.parts.update(tool.parts)
            target.cuts.extend(tool.cuts)
        elif operation == "difference":
            target.cuts.append(tool.label)
            target.volume -= .1
        else:
            raise AssertionError("Unexpected native operation: " + str(operation))
        return True


class PreparationHarness:
    def __init__(self, case, settings):
        self.case = case
        self.settings = settings
        self.design = object()
        self.edge = object()
        self.frame = fusion.HingeFrame((10, 20, 30), (1, 0, 0), (0, 1, 0), (0, 0, 1))
        self.source_a, self.source_b = Body("source A"), Body("source B")
        self.face_a = SimpleNamespace(body=self.source_a)
        self.face_b = SimpleNamespace(body=self.source_b)
        self.manager = Manager()
        self.api = (None, SimpleNamespace(
            TemporaryBRepManager=SimpleNamespace(get=lambda: self.manager),
            BooleanTypes=SimpleNamespace(UnionBooleanType="union", DifferenceBooleanType="difference")))
        self.attachments = []
        self.drilled = []
        self.raw_inputs = None
        self.final_outputs = None
        self.callback_plan = None
        self.callback_layout = None
        self.clearance_markers = []
        self.separation_calls = []
        self.events = []

    def support(self, manager, frame, web, construction):
        self.case.assertFalse(construction.chamfer_edges)
        self.case.assertFalse(construction.fillet_edges)
        self.attachments.append((web, construction))
        return Body("web " + web.owner)

    def cylinder(self, manager, frame, start, end, radius, center_z):
        bore = (self.settings.pin_diameter_mm + self.settings.diametral_clearance_mm) / 2
        return Body("bore" if abs(radius - bore) < 1e-12 else "axis cylinder")

    def drill(self, manager, frame, body, plate, hole, *extra):
        self.case.assertEqual(extra, (), "Raw screw holes must not receive primitive mouth chamfers.")
        body.cuts.append("screw hole")
        self.drilled.append((body, hole))
        self.events.append("hole")

    def relief(self, manager, frame, results, settings):
        marker = Body("clearance")
        self.clearance_markers.append(marker)
        return (("clearance", marker),)

    def separate(self, manager, one, two, label):
        if self.settings.chamfer_edges or self.settings.fillet_edges:
            self.case.assertTrue(one.final and two.final,
                                 "Separation must validate finished outputs, never the raw solids.")
        self.separation_calls.append((one, two))
        self.events.append("separation")

    def finish(self, design, manager, frame, settings, raw_inputs, *, plan, layout):
        self.events.append("finish")
        self.case.assertIs(design, self.design)
        self.case.assertIs(manager, self.manager)
        self.case.assertIs(frame, self.frame)
        self.case.assertIs(settings, self.settings)
        self.case.assertIs(plan.settings, settings)
        self.case.assertEqual(len(layout.placements), settings.hinge_count)
        self.raw_inputs = raw_inputs
        self.callback_plan = plan
        self.callback_layout = layout
        for role, body in raw_inputs:
            self.case.assertFalse(body.final)
            if role.startswith("pin"):
                self.case.assertEqual(body.parts, {"axis cylinder"})
                self.case.assertEqual(body.cuts, [])
                continue
            owner = role.split("_", 1)[0]
            knuckles = sum(knuckle.owner == owner for knuckle in plan.knuckles)
            if settings.output_mode == "attached":
                knuckles *= settings.hinge_count
            holes = 2 if settings.output_mode == "separate" and settings.screw_holes else 0
            self.case.assertEqual(body.cuts.count("bore"), knuckles,
                                 "All pin bores must exist before compound finishing.")
            self.case.assertEqual(body.cuts.count("screw hole"), holes,
                                 "All screw holes must exist before compound finishing.")
            self.case.assertIn("web " + owner, body.parts)
        self.final_outputs = tuple((role, Body("finished " + role, final=True))
                                   for role, body in reversed(raw_inputs))
        return self.final_outputs

    def run(self, *, finisher=None):
        forbidden = ("rounded_box", "rounded_axis_body", "_beveled_axis_body",
                     "_chamfer_box", "_finish_leaf_plate", "round_bore_entry",
                     "_axis_frustum", "_remove_finish_tool")
        with ExitStack() as stack:
            patches = {
                "_api": dict(return_value=self.api),
                "_selection": dict(return_value=(self.frame, ("source signature",), self.edge)),
                "_coincident_face_edges": dict(return_value=()),
                "_straight_endpoints": dict(return_value=((0, -10, 0), (0, 10, 0))),
                "make_tangent_support": dict(side_effect=self.support),
                "_leaf_plate": dict(side_effect=lambda manager, frame, plate: Body("plate " + plate.owner)),
                "_box": dict(side_effect=lambda *args: Body("square housing")),
                "_cylinder": dict(side_effect=self.cylinder),
                "_positive_attachment": {},
                "_drill_leaf": dict(side_effect=self.drill),
                "cut_rotation_relief": dict(side_effect=self.relief),
                "_require_separate": dict(side_effect=self.separate),
            }
            for name, options in patches.items():
                stack.enter_context(patch.object(fusion, name, **options))
            for name in forbidden:
                stack.enter_context(patch.object(fusion, name, side_effect=AssertionError(
                    "A primitive finish ran before the compound finisher: " + name)))
            attachment = stack.enter_context(patch.object(fusion, "_attachment_body", wraps=fusion._attachment_body))
            knuckle = stack.enter_context(patch.object(fusion, "_knuckle_body", wraps=fusion._knuckle_body))
            prepared = fusion.prepare_hinge(self.design, self.face_a, self.face_b, self.edge,
                                            self.settings, edge_finisher=finisher or self.finish)
            for call in attachment.call_args_list:
                self.case.assertFalse(call.args[3].chamfer_edges or call.args[3].fillet_edges)
            for call in knuckle.call_args_list:
                self.case.assertFalse(call.args[2].settings.chamfer_edges or call.args[2].settings.fillet_edges)
        return prepared


class CompoundPreparationTests(unittest.TestCase):
    def settings(self, mode, profile, finish):
        return HingeSettings(output_mode=mode, knuckle_profile=profile, hinge_count=2,
                             length_mm=20, screw_holes=mode == "separate",
                             chamfer_edges=finish == "chamfer", fillet_edges=finish == "fillet",
                             fillet_radius_mm=.4)

    def test_joined_bored_raw_geometry_reaches_one_finisher_with_original_contract(self):
        for mode in ("attached", "separate"):
            for profile in ("round", "square"):
                for finish in ("chamfer", "fillet"):
                    with self.subTest(mode=mode, profile=profile, finish=finish):
                        settings = self.settings(mode, profile, finish)
                        harness = PreparationHarness(self, settings)
                        prepared = harness.run()
                        roles = {role for role, body in harness.raw_inputs}
                        expected = ({"A", "B"} if mode == "attached" else {"A_1", "B_1", "A_2", "B_2"})
                        self.assertEqual(roles, expected | {"pin_1", "pin_2"})
                        self.assertIs(prepared.settings, settings)
                        self.assertIs(prepared.plan, harness.callback_plan)
                        self.assertIs(prepared.layout, harness.callback_layout)
                        self.assertIs(prepared.result_bodies, harness.final_outputs)
                        self.assertEqual(harness.events.count("finish"), 1)
                        self.assertTrue(all(event == "separation" for event in
                                            harness.events[harness.events.index("finish") + 1:]))
                        self.assertEqual(len(harness.drilled), 8 if mode == "separate" else 0)
                        self.assertEqual(harness.source_a.parts, {"source A"})
                        self.assertEqual(harness.source_b.parts, {"source B"})
                        self.assertEqual(harness.source_a.cuts + harness.source_b.cuts, [])

    def test_preview_geometry_and_separation_use_final_bodies_not_raw_knuckles(self):
        for mode in ("attached", "separate"):
            with self.subTest(mode=mode):
                harness = PreparationHarness(self, self.settings(mode, "round", "fillet"))
                prepared = harness.run()
                finals = dict(harness.final_outputs)
                self.assertIs(prepared.preview_bodies, prepared.result_bodies)
                for role, body in prepared.preview_bodies:
                    self.assertTrue(body.final)
                    self.assertIs(body, finals[role])
                self.assertNotIn("clearance", {role for role, _ in prepared.preview_bodies})
                final_ids = {id(body) for body in finals.values()}
                self.assertEqual(len(harness.separation_calls), len(final_ids) * (len(final_ids) - 1) // 2)
                self.assertTrue(all(id(one) in final_ids and id(two) in final_ids
                                    for one, two in harness.separation_calls))
                if mode == "attached":
                    isolated = [(target, tool) for operation, target, tool in harness.manager.operations
                                if operation == "difference" and target.final]
                    self.assertEqual(isolated, [], "Full-result preview needs no addition-isolation booleans.")

    def test_sharp_settings_do_not_invoke_the_supplied_compound_finisher(self):
        harness = PreparationHarness(self, HingeSettings())
        forbidden = Mock(side_effect=AssertionError("Sharp geometry must not invoke a finish transaction."))
        prepared = harness.run(finisher=forbidden)
        forbidden.assert_not_called()
        self.assertFalse(prepared.settings.chamfer_edges or prepared.settings.fillet_edges)
        self.assertTrue(all(not body.final for role, body in prepared.result_bodies))
        self.assertEqual({role for role, body in prepared.result_bodies}, {"A", "B", "pin"})

    def test_finisher_failure_prevents_result_and_final_separation(self):
        harness = PreparationHarness(self, self.settings("separate", "square", "chamfer"))
        failed = Mock(side_effect=ValueError("Native compound finish failed."))
        with self.assertRaisesRegex(ValueError, "Native compound finish failed"):
            harness.run(finisher=failed)
        failed.assert_called_once()
        self.assertEqual(harness.separation_calls, [])
        self.assertEqual(harness.source_a.cuts + harness.source_b.cuts, [])


if __name__ == "__main__":
    unittest.main()

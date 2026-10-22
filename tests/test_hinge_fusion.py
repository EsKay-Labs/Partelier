"""Multi-hinge and Part Design ownership contracts; no native CAD assertions."""

import json
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from Partelier.partelier.tools.hinge import fusion, inplace
from Partelier.partelier.tools.hinge.settings import HingeSettings
from Partelier.partelier.tools.hinge.planner import build_hinge_plan


FEATURE_ID = "de431a33-e909-4d18-9f1f-7518678982a4"


class Collection:
    def __init__(self, values=()):
        self.values = list(values)

    @property
    def count(self):
        return len(self.values)

    def item(self, index):
        return self.values[index]


class Attributes:
    def __init__(self):
        self.values = {}
        self.writes = []

    def itemByName(self, group, name):
        return self.values.get((group, name))

    def add(self, group, name, value):
        tag = SimpleNamespace(value=value)
        self.values[(group, name)] = tag
        self.writes.append((group, name, value))
        return tag


def body(root, token):
    return SimpleNamespace(kind="body", isValid=True, isSolid=True,
                           isTemporary=False, isLightBulbOn=True,
                           lumps=SimpleNamespace(count=1), parentComponent=root,
                           assemblyContext=None, entityToken=token, attributes=Attributes())


def api():
    def cast(kind):
        return SimpleNamespace(cast=lambda value: value if getattr(value, "kind", None) == kind else None)

    core = SimpleNamespace(Matrix3D=SimpleNamespace(create=lambda: object()))
    adapter = SimpleNamespace(
        DesignTypes=SimpleNamespace(ParametricDesignType=1),
        DesignIntentTypes=SimpleNamespace(PartDesignIntentType=1),
        BRepBody=cast("body"), BaseFeature=cast("feature"), BRepFace=cast("face"),
        BRepEdge=cast("edge"), Component=cast("component"), Occurrence=cast("occurrence"))
    return core, adapter


def part_fixture(settings=None):
    settings = settings or HingeSettings(include_pin=False)
    root = SimpleNamespace(kind="component", isValid=True, name="User part", attributes=Attributes(),
                           occurrences=SimpleNamespace(addNewComponent=Mock()), deleteMe=Mock())
    source_a, source_b = body(root, "source A"), body(root, "source B")
    face_a = SimpleNamespace(kind="face", isValid=True, entityToken="face A", body=source_a)
    face_b = SimpleNamespace(kind="face", isValid=True, entityToken="face B", body=source_b)
    edge = SimpleNamespace(kind="edge", isValid=True, entityToken="axis")
    halves = ([f"{owner}_{index + 1}" for index in range(settings.hinge_count) for owner in ("A", "B")]
              if settings.output_mode == "separate" and settings.hinge_count > 1 else ["A", "B"])
    roles = halves + (["pin"] if settings.include_pin and settings.hinge_count == 1 else [
        f"pin_{index + 1}" for index in range(settings.hinge_count) if settings.include_pin])
    results = [body(root, "result " + role) for role in roles]
    base = SimpleNamespace(kind="feature", isValid=True, parentComponent=root,
                           entityToken="owned base", attributes=Attributes(), bodies=Collection(results),
                           startEdit=Mock(return_value=True), finishEdit=Mock(return_value=True),
                           deleteMe=Mock(return_value=True), timelineObject=SimpleNamespace(index=5, isDeletable=True))
    base_features = Collection((base,))
    base_features.add = Mock(return_value=base)
    root.features = SimpleNamespace(baseFeatures=base_features, count=100)
    root.bRepBodies = Collection((source_a, source_b, *results))
    editing_bodies = [body(root, "editing source " + str(index)) for index in range(len(results))]
    root.bRepBodies.add = Mock(side_effect=editing_bodies)
    def start_edit():
        base.bodies = Collection(editing_bodies)
        return True
    def finish_edit():
        base.bodies = Collection(results)
        return True
    base.startEdit.side_effect = start_edit
    base.finishEdit.side_effect = finish_edit
    entities = {entity.entityToken: entity for entity in (source_a, source_b, face_a, face_b, edge, base)}
    design = SimpleNamespace(isValid=True, designType=1, designIntent=1, rootComponent=root,
                             activeComponent=root, timeline=SimpleNamespace(count=6, markerPosition=6),
                             findEntityByToken=lambda token: [entities[token]] if token in entities else [])
    prepared = SimpleNamespace(face_a=face_a, face_b=face_b, axis_edge=edge, settings=settings,
                               result_bodies=tuple((role, object()) for role in roles))
    recipe = {"version": fusion.RECIPE_VERSION, "tool": fusion.TOOL_ID, "feature_id": FEATURE_ID,
              "settings": settings.to_dict(), "sources": {"face_a": "face A", "face_b": "face B",
              "axis_edge": "axis", "body_a": "source A", "body_b": "source B"},
              "results": {role: "a" * 64 for role in roles}, "base_feature": "owned base"}
    return design, prepared, base, results, recipe


def own_result(base, results, recipe):
    base.attributes.add(fusion.ATTRIBUTE_GROUP, fusion.OWNER_NAME, recipe["feature_id"])
    base.attributes.add(fusion.ATTRIBUTE_GROUP, fusion.RECIPE_NAME, json.dumps(recipe))
    for role, result in zip(recipe["results"], results):
        result.attributes.add(fusion.ATTRIBUTE_GROUP, fusion.OWNER_NAME, json.dumps({
            "feature_id": recipe["feature_id"], "role": role}))


class HingePersistenceTests(unittest.TestCase):
    def test_preview_uses_existing_body_appearances_and_fully_opaque_graphics(self):
        graphics = []
        def add_graphic(body):
            graphic = SimpleNamespace(body=body, setOpacity=Mock(return_value=True))
            graphics.append(graphic)
            return graphic
        group = SimpleNamespace(addBRepBody=add_graphic, isValid=True, deleteMe=Mock())
        root = SimpleNamespace(customGraphicsGroups=SimpleNamespace(add=lambda: group),
                               material=SimpleNamespace(appearance="Fusion default material"))
        source_a = SimpleNamespace(appearance="Body A appearance")
        source_b = SimpleNamespace(appearance="Body B appearance")
        prepared = SimpleNamespace(design=SimpleNamespace(rootComponent=root), result_bodies=tuple(
            (role, object()) for role in ("A_1", "B_1", "pin_1")),
            settings=HingeSettings(), face_a=SimpleNamespace(body=source_a),
            face_b=SimpleNamespace(body=source_b), preview_bodies=(("clearance", object()),))
        factory = Mock(side_effect=lambda appearance: ("Fusion appearance", appearance))
        adapter_api = (None, SimpleNamespace(CustomGraphicsAppearanceColorEffect=SimpleNamespace(create=factory)))
        with patch.object(fusion, "_api", return_value=adapter_api), patch.object(fusion, "_assert_fresh"), patch.object(fusion,"_preview_outlines"):
            self.assertIs(fusion.preview_hinge(prepared), group)
        self.assertEqual([graphic.color[1] for graphic in graphics],
                         ["Body A appearance", "Body B appearance", "Fusion default material"])
        for graphic in graphics:
            graphic.setOpacity.assert_called_once_with(1.0, True)
            self.assertFalse(graphic.isSelectable)
        self.assertEqual(source_a.appearance, "Body A appearance")
        self.assertEqual(source_b.appearance, "Body B appearance")
        group.deleteMe.assert_not_called()

    def test_edit_preview_resolves_persistent_body_appearance_without_reading_old_faces(self):
        root = SimpleNamespace(material=SimpleNamespace(appearance="Fusion default material"))
        prepared = SimpleNamespace(design=SimpleNamespace(rootComponent=root), settings=HingeSettings(),
                                   history_anchor=object(), source_tokens={"body_a":"A", "body_b":"B"})
        a=SimpleNamespace(appearance="A material");b=SimpleNamespace(appearance="B material")
        with patch.object(fusion, "_resolve_one", side_effect=[a,b]) as resolve:
            appearances=fusion._preview_appearances(prepared)
        self.assertEqual(appearances,{"A":"A material","B":"B material","pin":"Fusion default material"})
        self.assertEqual([call.args[1] for call in resolve.call_args_list],["A","B"])

    def test_generated_separate_leaves_and_pins_use_the_component_material(self):
        root=SimpleNamespace(material=SimpleNamespace(appearance="Fusion default material"))
        prepared=SimpleNamespace(design=SimpleNamespace(rootComponent=root),settings=HingeSettings(output_mode="separate"))
        self.assertEqual(set(fusion._preview_appearances(prepared).values()),{"Fusion default material"})

    def test_outline_batch_keeps_trimmed_edges_separate_and_skips_seams_and_degenerate_edges(self):
        point=lambda x,y:SimpleNamespace(x=x,y=y,z=0)
        def edge(points,degenerate=False,faces=2):
            return SimpleNamespace(isDegenerate=degenerate,faces=SimpleNamespace(count=faces),evaluator=SimpleNamespace(
                getParameterExtents=Mock(return_value=(True,2.0,5.0)),getStrokes=Mock(return_value=(True,points))))
        one=edge([point(0,0),point(1,0),point(1,1)])
        two=edge([point(5,5),point(6,5)])
        seam=edge([],faces=1);degenerate=edge([],degenerate=True)
        body=SimpleNamespace(edges=Collection((one,two,seam,degenerate)))
        lines=SimpleNamespace();group=SimpleNamespace(addLines=Mock(return_value=lines))
        core=SimpleNamespace(Application=SimpleNamespace(get=lambda:SimpleNamespace(activeViewport=SimpleNamespace(visualStyle=1))),
                             VisualStyles=SimpleNamespace(ShadedVisualStyle=0),Color=SimpleNamespace(create=lambda *rgba:rgba))
        api=SimpleNamespace(CustomGraphicsCoordinates=SimpleNamespace(create=lambda values:values),
                            CustomGraphicsSolidColorEffect=SimpleNamespace(create=lambda color:color))
        fusion._preview_outlines(group,body,core,api)
        group.addLines.assert_called_once_with([0,0,0,1,0,0,1,1,0,5,5,0,6,5,0],[0,1,1,2,3,4],False)
        self.assertEqual(lines.color,(0,0,0,255))
        self.assertEqual(lines.weight,1.0)
        self.assertFalse(lines.isSelectable)
        for boundary in (one,two):
            boundary.evaluator.getStrokes.assert_called_once_with(2.0,5.0,fusion.PREVIEW_EDGE_TOLERANCE_CM)
        seam.evaluator.getParameterExtents.assert_not_called()
        degenerate.evaluator.getParameterExtents.assert_not_called()

    def test_plain_shaded_display_does_not_add_outlines(self):
        core=SimpleNamespace(Application=SimpleNamespace(get=lambda:SimpleNamespace(activeViewport=SimpleNamespace(visualStyle=0))),
                             VisualStyles=SimpleNamespace(ShadedVisualStyle=0))
        group=SimpleNamespace(addLines=Mock())
        fusion._preview_outlines(group,object(),core,object())
        group.addLines.assert_not_called()

    def test_separate_multi_leaf_roles_persist_and_can_be_read_from_a_root_leaf(self):
        settings = HingeSettings(output_mode="separate", leaf_profile="rounded", hinge_count=2,
                                 length_mm=20, screw_holes=True)
        design, prepared, base, results, _ = part_fixture(settings)
        with patch.object(fusion, "_api", return_value=api()), patch.object(
                fusion, "_assert_fresh"), patch.object(fusion, "_body_signature", return_value="a" * 64):
            fusion._create(design, prepared, FEATURE_ID)
            target = fusion.read_edit_target(design, results[2])
        self.assertEqual(target.settings, settings)
        self.assertEqual(set(target.recipe["results"]), {"A_1", "B_1", "A_2", "B_2", "pin_1", "pin_2"})
        self.assertIs(target.anchor, base)
        self.assertEqual([item.name for item in results[:4]], ["Hinge 1 leaf A", "Hinge 1 leaf B",
                                                             "Hinge 2 leaf A", "Hinge 2 leaf B"])
        self.assertEqual(design.rootComponent.attributes.writes, [])

    def test_rounded_leaf_constructs_only_free_outer_corners(self):
        plan = build_hinge_plan(HingeSettings(output_mode="separate", leaf_profile="rounded"))
        adapter_api = (None, SimpleNamespace(BooleanTypes=SimpleNamespace(UnionBooleanType=1)))
        for plate in plan.plates:
            main, middle, corner = object(), object(), object()
            with self.subTest(owner=plate.owner), patch.object(fusion, "_api", return_value=adapter_api), patch.object(
                    fusion, "_box", side_effect=(main, middle)) as boxes, patch.object(
                    fusion, "_vertical_cylinder", return_value=corner) as cylinders, patch.object(
                    fusion, "_boolean") as boolean:
                result = fusion._leaf_plate(object(), object(), plate)
            self.assertIs(result, main)
            radius = plate.corner_radius_mm
            inner = boxes.call_args_list[0].args[2]
            mid = boxes.call_args_list[1].args[2]
            if plate.owner == "A":
                self.assertEqual(inner.x_min_mm, plate.x_min_mm + radius)
                self.assertEqual(inner.x_max_mm, plate.x_max_mm)
                expected_x = plate.x_min_mm + radius
            else:
                self.assertEqual(inner.x_min_mm, plate.x_min_mm)
                self.assertEqual(inner.x_max_mm, plate.x_max_mm - radius)
                expected_x = plate.x_max_mm - radius
            self.assertEqual((mid.x_min_mm, mid.x_max_mm), (plate.x_min_mm, plate.x_max_mm))
            self.assertEqual((mid.y_min_mm, mid.y_max_mm), (plate.y_min_mm + radius, plate.y_max_mm - radius))
            self.assertEqual(cylinders.call_count, 2)
            self.assertEqual([call.args[2] for call in cylinders.call_args_list], [expected_x, expected_x])
            self.assertEqual([call.args[3] for call in cylinders.call_args_list],
                             [plate.y_min_mm + radius, plate.y_max_mm - radius])
            self.assertEqual(boolean.call_count, 3)

    def test_rectangular_leaf_has_no_rounded_corner_tools(self):
        plate = build_hinge_plan(HingeSettings(output_mode="separate")).plates[0]
        result = object()
        with patch.object(fusion, "_box", return_value=result) as box, patch.object(
                fusion, "_vertical_cylinder") as corner:
            self.assertIs(fusion._leaf_plate(object(), object(), plate), result)
        box.assert_called_once()
        corner.assert_not_called()

    def test_screw_hole_removes_positive_material_from_only_the_supplied_generated_leaf(self):
        plan = build_hinge_plan(HingeSettings(output_mode="separate", screw_holes=True))
        plate, hole = plan.plates[0], plan.mounting_holes[0]
        for outcome in ("success", "no material", "split"):
            leaf = SimpleNamespace(isValid=True, isSolid=True, lumps=SimpleNamespace(count=1), volume=10)
            tool = object()
            def boolean(target, cutter, operation):
                self.assertIs(target, leaf)
                self.assertIs(cutter, tool)
                self.assertEqual(operation, 2)
                if outcome != "no material":
                    target.volume = 9
                if outcome == "split":
                    target.lumps.count = 2
                return True
            manager = SimpleNamespace(booleanOperation=boolean)
            adapter_api = (None, SimpleNamespace(BooleanTypes=SimpleNamespace(DifferenceBooleanType=2)))
            with self.subTest(outcome=outcome), patch.object(fusion, "_api", return_value=adapter_api), patch.object(
                    fusion, "_vertical_cylinder", return_value=tool) as cutter:
                if outcome == "success":
                    fusion._drill_leaf(manager, object(), leaf, plate, hole)
                else:
                    with self.assertRaises(fusion.HingeGeometryError):
                        fusion._drill_leaf(manager, object(), leaf, plate, hole)
            self.assertEqual(cutter.call_args.args[2:], (hole.x_mm, hole.y_mm, plate.z_min_mm - 0.1,
                                                       plate.z_max_mm + 0.1, hole.diameter_mm / 2))

    def test_base_feature_result_roles_follow_editable_source_indices_not_add_order(self):
        design, prepared, base, results, _ = part_fixture(HingeSettings(hinge_count=2))
        editable = [body(design.rootComponent, "editable " + str(index)) for index in range(len(results))]
        order = (1, 3, 0, 2)
        design.rootComponent.bRepBodies.add.side_effect = editable
        def start_edit():
            base.bodies = Collection(editable[index] for index in order)
            return True
        def finish_edit():
            base.bodies = Collection(results[index] for index in order)
            return True
        base.startEdit.side_effect = start_edit
        base.finishEdit.side_effect = finish_edit
        with patch.object(fusion, "_api", return_value=api()), patch.object(
                fusion, "_assert_fresh"), patch.object(fusion, "_body_signature", return_value="a" * 64):
            fusion._create(design, prepared, FEATURE_ID)
        for role, result in zip(("A", "B", "pin_1", "pin_2"), results):
            tag = result.attributes.itemByName(fusion.ATTRIBUTE_GROUP, fusion.OWNER_NAME)
            self.assertEqual(json.loads(tag.value)["role"], role)
        self.assertTrue(all(not item.attributes.writes for item in editable))

    def test_part_create_owns_only_root_base_feature_and_names_each_pin(self):
        settings = HingeSettings(hinge_count=3, length_mm=10, start_margin_mm=5, end_margin_mm=7)
        design, prepared, base, results, _ = part_fixture(settings)
        with patch.object(fusion, "_api", return_value=api()), patch.object(
                fusion, "_assert_fresh"), patch.object(fusion, "_body_signature", return_value="a" * 64):
            anchor = fusion._create(design, prepared, FEATURE_ID)
        self.assertIs(anchor, base)
        design.rootComponent.occurrences.addNewComponent.assert_not_called()
        self.assertEqual(design.designIntent, 1)
        self.assertEqual(design.rootComponent.name, "User part")
        self.assertEqual(design.rootComponent.attributes.writes, [])
        self.assertEqual([item.name for item in results], ["Hinge half A", "Hinge half B",
                                                          "Separate pin 1", "Separate pin 2", "Separate pin 3"])
        raw = base.attributes.itemByName(fusion.ATTRIBUTE_GROUP, fusion.RECIPE_NAME).value
        recipe, decoded = fusion._read_recipe(raw)
        self.assertEqual(recipe["version"], 8)
        self.assertEqual(decoded, settings)
        self.assertEqual(set(recipe["results"]), {"A", "B", "pin_1", "pin_2", "pin_3"})
        base.deleteMe.assert_not_called()

    def test_part_create_failure_exits_edit_and_deletes_only_new_feature(self):
        design, prepared, base, _, _ = part_fixture()
        design.rootComponent.bRepBodies.add.side_effect = RuntimeError("injected persist failure")
        with patch.object(fusion, "_api", return_value=api()), patch.object(fusion, "_assert_fresh"):
            with self.assertRaisesRegex(RuntimeError, "injected persist"):
                fusion._create(design, prepared, FEATURE_ID)
        base.finishEdit.assert_called_once()
        base.deleteMe.assert_called_once()
        design.rootComponent.deleteMe.assert_not_called()
        design.rootComponent.occurrences.addNewComponent.assert_not_called()
        self.assertEqual(design.rootComponent.attributes.writes, [])

    def test_part_cleanup_failure_is_reported(self):
        design, prepared, base, _, _ = part_fixture()
        design.rootComponent.bRepBodies.add.side_effect = RuntimeError("injected persist failure")
        base.deleteMe.return_value = False
        with patch.object(fusion, "_api", return_value=api()), patch.object(fusion, "_assert_fresh"):
            with self.assertRaisesRegex(fusion.HingeGeometryError, "Cleanup incomplete.*Undo"):
                fusion._create(design, prepared, FEATURE_ID)
        design.rootComponent.deleteMe.assert_not_called()

    def test_root_body_edit_resolves_feature_without_claiming_unrelated_root_content(self):
        design, prepared, base, results, recipe = part_fixture(HingeSettings(hinge_count=2, include_pin=False))
        own_result(base, results, recipe)
        unrelated = body(design.rootComponent, "unrelated root body")
        design.rootComponent.bRepBodies.values.append(unrelated)
        with patch.object(fusion, "_api", return_value=api()), patch.object(
                fusion, "_body_signature", return_value="a" * 64):
            target = fusion.read_edit_target(design, results[0])
            internal = fusion.read_edit_target(design, base)
        self.assertIs(target.anchor, base)
        self.assertIs(internal.anchor, base)
        self.assertIs(target.component, design.rootComponent)
        self.assertIsNone(target.occurrence)
        self.assertEqual(target.settings, prepared.settings)
        self.assertEqual(design.rootComponent.attributes.writes, [])
        self.assertEqual(unrelated.attributes.writes, [])
        base.deleteMe.assert_not_called()

    def test_root_component_resolves_only_its_one_owned_hinge_without_claiming_root(self):
        design, prepared, base, results, recipe = part_fixture()
        own_result(base, results, recipe)
        with patch.object(fusion, "_api", return_value=api()), patch.object(fusion, "_body_signature", return_value="a" * 64):
            target = fusion.read_edit_target(design, design.rootComponent)
        self.assertIs(target.anchor, base)
        self.assertEqual(target.settings, prepared.settings)
        self.assertEqual(design.rootComponent.attributes.writes, [])
        design.rootComponent.deleteMe.assert_not_called()

    def test_root_component_with_zero_or_multiple_hinges_requires_specific_body(self):
        for count in (0, 2):
            design, _, base, results, recipe = part_fixture()
            if count:
                own_result(base, results, recipe)
                second = SimpleNamespace(attributes=Attributes())
                second.attributes.add(fusion.ATTRIBUTE_GROUP, fusion.RECIPE_NAME, "{}")
                design.rootComponent.features.baseFeatures.values.append(second)
            with patch.object(fusion, "_api", return_value=api()):
                with self.assertRaisesRegex(fusion.HingeGeometryError, "no editable|multiple hinges"):
                    fusion.read_edit_target(design, design.rootComponent)
            base.deleteMe.assert_not_called()
            design.rootComponent.deleteMe.assert_not_called()

    def test_picked_result_face_or_edge_resolves_to_its_owned_body(self):
        design, _, base, results, recipe = part_fixture()
        own_result(base, results, recipe)
        with patch.object(fusion, "_api", return_value=api()), patch.object(fusion, "_body_signature", return_value="a" * 64):
            for kind in ("face", "edge"):
                selected = SimpleNamespace(kind=kind, isValid=True, body=results[0])
                target = fusion.read_edit_target(design, selected)
                self.assertIs(target.anchor, base)

    def test_root_edit_refuses_changed_results_downstream_history_and_unsafe_delete(self):
        for failure in ("signature", "rolled-back marker", "dependent feature", "added body"):
            design, _, base, results, recipe = part_fixture()
            own_result(base, results, recipe)
            if failure == "rolled-back marker":
                design.timeline.count = 7
                design.timeline.markerPosition = 6
            elif failure == "dependent feature":
                base.timelineObject.isDeletable = False
            elif failure == "added body":
                base.bodies.values.append(body(design.rootComponent, "unowned added result"))
            with self.subTest(failure=failure), patch.object(fusion, "_api", return_value=api()), patch.object(
                    fusion, "_body_signature", return_value=("b" if failure == "signature" else "a") * 64):
                with self.assertRaises(fusion.HingeGeometryError):
                    fusion.read_edit_target(design, results[0])
            base.deleteMe.assert_not_called()
            design.rootComponent.deleteMe.assert_not_called()

    def test_root_edit_refuses_unowned_body_and_duplicate_feature_owners(self):
        for duplicate in (False, True):
            design, _, base, results, recipe = part_fixture()
            own_result(base, results, recipe)
            if duplicate:
                other = SimpleNamespace(attributes=base.attributes)
                design.rootComponent.features.baseFeatures.values.append(other)
                selected = results[0]
            else:
                selected = body(design.rootComponent, "source body")
            with self.subTest(duplicate=duplicate), patch.object(fusion, "_api", return_value=api()):
                with self.assertRaisesRegex(fusion.HingeGeometryError, "ownership|unique owned"):
                    fusion.read_edit_target(design, selected)
            base.deleteMe.assert_not_called()

    def test_legacy_attached_rebuild_migrates_originals_before_retiring_copy(self):
        design, prepared, base, _, recipe = part_fixture()
        target = SimpleNamespace(component=design.rootComponent, occurrence=None, anchor=base,
                                 settings=prepared.settings, recipe=recipe, feature_id=FEATURE_ID,
                                 face_a=prepared.face_a, face_b=prepared.face_b, axis_edge=prepared.axis_edge)
        replacement = SimpleNamespace(isValid=True, deleteMe=Mock(return_value=True))
        with patch.object(fusion, "read_edit_target", return_value=target) as read, patch.object(
                inplace, "create", return_value=replacement):
            result = fusion.rebuild_hinge(design, target, prepared)
        read.assert_called_once_with(design, base)
        self.assertIs(result, replacement)
        base.deleteMe.assert_called_once()
        replacement.deleteMe.assert_not_called()
        design.rootComponent.deleteMe.assert_not_called()

    def test_root_rebuild_cleans_new_feature_when_retirement_fails(self):
        design, prepared, base, _, recipe = part_fixture(HingeSettings(output_mode="separate", include_pin=False))
        base.deleteMe.return_value = False
        target = SimpleNamespace(component=design.rootComponent, occurrence=None, anchor=base,
                                 settings=prepared.settings, recipe=recipe, feature_id=FEATURE_ID,
                                 face_a=prepared.face_a, face_b=prepared.face_b, axis_edge=prepared.axis_edge)
        replacement = SimpleNamespace(isValid=True, deleteMe=Mock(return_value=True))
        with patch.object(fusion, "_api", return_value=api()), patch.object(
                fusion, "read_edit_target", return_value=target), patch.object(
                fusion, "_create", return_value=replacement):
            with self.assertRaisesRegex(fusion.HingeGeometryError, "prior hinge was retained"):
                fusion.rebuild_hinge(design, target, prepared)
        replacement.deleteMe.assert_called_once()
        design.rootComponent.deleteMe.assert_not_called()

    def test_v5_roles_follow_hinge_and_pin_count_and_legacy_versions_add_only_defaults(self):
        _, _, _, _, recipe = part_fixture(HingeSettings(hinge_count=2))
        decoded, settings = fusion._read_recipe(json.dumps(recipe))
        self.assertEqual(settings.hinge_count, 2)
        self.assertEqual(decoded, recipe)
        for bad_roles in ({"A", "B", "pin"}, {"A", "B", "pin_1"}, {"A", "B", "pin_1", "pin_2", "pin_3"}):
            changed = {**recipe, "results": {role: "a" * 64 for role in bad_roles}}
            with self.subTest(bad_roles=bad_roles), self.assertRaisesRegex(fusion.HingeGeometryError, "ownership"):
                fusion._read_recipe(json.dumps(changed))
        for version in (1, 2, 3, 4, 5, 6, 7):
            _, _, _, _, legacy = part_fixture(HingeSettings(include_pin=False))
            legacy["version"] = version
            legacy["settings"].pop("rotation_clearance_mm")
            if version < 7:
                legacy["settings"].pop("web_profile")
            if version < 6:
                for name in fusion.STYLE_DEFAULTS:
                    legacy["settings"].pop(name)
            if version < 5:
                for name in fusion.FINISH_DEFAULTS:
                    legacy["settings"].pop(name)
            if version < 4:
                for name in fusion.LEAF_DEFAULTS:
                    legacy["settings"].pop(name)
            if version < 3:
                for name in fusion.LAYOUT_DEFAULTS:
                    legacy["settings"].pop(name)
            if version == 1:
                legacy["settings"].pop("split_seam")
                legacy["settings"].pop("seam_clearance_mm")
            original = json.dumps(legacy, sort_keys=True)
            raw, defaults = fusion._read_recipe(json.dumps(legacy))
            self.assertEqual(json.dumps(raw, sort_keys=True), original)
            self.assertEqual(defaults.web_profile, "flat" if version < 7 else "tangent")
            self.assertEqual(defaults.rotation_clearance_mm, 0)
            self.assertEqual(defaults.hinge_count, 1)
            self.assertEqual(defaults.start_margin_mm, 0)
            self.assertEqual(defaults.end_margin_mm, 0)
            self.assertEqual(defaults.output_mode, "attached")
            self.assertFalse(defaults.chamfer_edges)
            self.assertEqual(defaults.chamfer_size_mm, 0.3)


if __name__ == "__main__":
    unittest.main()

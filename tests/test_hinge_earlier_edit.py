"""Earlier root hinge independence; fake hosts do not prove Fusion deletion."""

from copy import deepcopy
import json
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from Partelier.partelier.tools.hinge import fusion, inplace
from test_hinge_fusion import Attributes, Collection, api, body, own_result, part_fixture


SECOND_ID = "07bb03dc-1095-48ec-985a-a5a0208c73e9"


class EarlierRootHingeTests(unittest.TestCase):
    def fixture(self, namespace=None):
        design, prepared, first, first_bodies, recipe = part_fixture()
        prepared.axis_edge.body = prepared.face_a.body
        own_result(first, first_bodies, recipe)
        first.timelineObject.index = 4
        design.timeline.count = design.timeline.markerPosition = 7
        second = SimpleNamespace(kind="feature", isValid=True, parentComponent=design.rootComponent,
                                 entityToken="second base", attributes=Attributes(),
                                 timelineObject=SimpleNamespace(index=6, isDeletable=True), deleteMe=Mock(return_value=True))
        second_bodies = [body(design.rootComponent, "second " + role) for role in recipe["results"]]
        second.bodies = Collection(second_bodies)
        other = deepcopy(recipe)
        other["feature_id"] = SECOND_ID
        other["base_feature"] = second.entityToken
        group = namespace or fusion.ATTRIBUTE_GROUP
        second.attributes.add(group, fusion.OWNER_NAME, SECOND_ID)
        second.attributes.add(group, fusion.RECIPE_NAME, json.dumps(other))
        for role, result in zip(other["results"], second_bodies):
            result.attributes.add(group, fusion.OWNER_NAME, json.dumps({"feature_id": SECOND_ID, "role": role}))
        design.rootComponent.features.baseFeatures.values.append(second)
        design.rootComponent.bRepBodies.values.extend(second_bodies)
        original_resolve = design.findEntityByToken
        extra = {second.entityToken: second, **{result.entityToken: result for result in first_bodies}}
        design.findEntityByToken = lambda token: [extra[token]] if token in extra else original_resolve(token)
        return design, prepared, first, first_bodies, second, second_bodies, other, extra

    def test_earlier_part_root_hinge_can_be_read_without_moving_timeline(self):
        design, _, first, first_bodies, second, _, _, _ = self.fixture()
        with patch.object(fusion, "_api", return_value=api()), patch.object(fusion, "_body_signature", return_value="a" * 64):
            target = fusion.read_edit_target(design, first_bodies[0])
        self.assertIs(target.anchor, first)
        self.assertEqual(design.timeline.markerPosition, 7)
        first.deleteMe.assert_not_called()
        second.deleteMe.assert_not_called()

    def test_two_same_original_source_recipes_are_independent_in_both_namespaces(self):
        for namespace in (fusion.ATTRIBUTE_GROUP, fusion.LEGACY_ATTRIBUTE_GROUP):
            design, _, first, _, second, second_bodies, _, _ = self.fixture(namespace)
            before = (second.attributes.values.copy(), tuple(item.attributes.values.copy() for item in second_bodies))
            with self.subTest(namespace=namespace), patch.object(fusion, "_api", return_value=api()):
                fusion._guard_root_recipe_dependencies(design, first)
            self.assertEqual(before, (second.attributes.values, tuple(item.attributes.values for item in second_bodies)))
            first.deleteMe.assert_not_called()
            second.deleteMe.assert_not_called()

    def test_rebuild_of_earlier_independent_part_retires_only_first_owner(self):
        design, prepared, first, first_bodies, second, second_bodies, _, _ = self.fixture()
        before = (second.attributes.values.copy(), tuple(second_bodies))
        replacement = SimpleNamespace(isValid=True, deleteMe=Mock())
        with patch.object(fusion, "_api", return_value=api()), patch.object(fusion, "_body_signature", return_value="a" * 64):
            target = fusion.read_edit_target(design, first_bodies[0])
            with patch.object(inplace, "create", return_value=replacement) as create:
                self.assertIs(fusion.rebuild_hinge(design, target, prepared), replacement)
        create.assert_called_once()
        first.deleteMe.assert_called_once()
        second.deleteMe.assert_not_called()
        self.assertEqual(before, (second.attributes.values, tuple(second_bodies)))

    def test_hybrid_and_occurrence_outputs_keep_last_timeline_gate(self):
        design, _, first, first_bodies, _, _, _, _ = self.fixture()
        design.designIntent = 2
        with patch.object(fusion, "_api", return_value=api()), patch.object(fusion, "_body_signature", return_value="a" * 64):
            with self.assertRaisesRegex(fusion.HingeGeometryError, "last in the timeline"):
                fusion.read_edit_target(design, first_bodies[0])
        with self.assertRaisesRegex(fusion.HingeGeometryError, "last in the timeline"):
            fusion._guard_feature_timeline(design, first)

    def test_native_dependency_or_non_end_marker_still_blocks_earlier_part_edit(self):
        for failure in ("dependency", "marker"):
            design, _, first, first_bodies, _, _, _, _ = self.fixture()
            if failure == "dependency":
                first.timelineObject.isDeletable = False
            else:
                design.timeline.markerPosition -= 1
            with self.subTest(failure=failure), patch.object(fusion, "_api", return_value=api()):
                with self.assertRaises(fusion.HingeGeometryError):
                    fusion.read_edit_target(design, first_bodies[0])
            first.deleteMe.assert_not_called()

    def test_logical_source_dependency_blocks_before_any_create_or_delete(self):
        design, prepared, first, first_bodies, second, _, other, extra = self.fixture()
        other["sources"]["body_a"] = "alternate token for first result"
        face = SimpleNamespace(kind="face", isValid=True, body=first_bodies[0])
        edge = SimpleNamespace(kind="edge", isValid=True, body=first_bodies[0])
        extra.update({"alternate token for first result": first_bodies[0], "dependent face": face, "dependent edge": edge})
        other["sources"].update(face_a="dependent face", axis_edge="dependent edge")
        second.attributes.add(fusion.ATTRIBUTE_GROUP, fusion.RECIPE_NAME, json.dumps(other))
        with patch.object(fusion, "_api", return_value=api()), patch.object(fusion, "_body_signature", return_value="a" * 64):
            target = fusion.read_edit_target(design, first_bodies[0])
            with patch.object(inplace, "create") as create:
                with self.assertRaisesRegex(fusion.HingeGeometryError, "depends on this hinge's generated bodies"):
                    fusion.rebuild_hinge(design, target, prepared)
        create.assert_not_called()
        first.deleteMe.assert_not_called()
        second.deleteMe.assert_not_called()

    def test_damaged_unsupported_conflicting_or_inconsistent_other_recipe_refused(self):
        for failure in ("json", "version", "conflicting", "missing owner", "face", "edge"):
            design, _, first, first_bodies, second, _, other, extra = self.fixture()
            raw = json.dumps(other)
            if failure == "json":
                raw = "{"
            elif failure == "version":
                other["version"] = 99
                raw = json.dumps(other)
            elif failure == "conflicting":
                second.attributes.add(fusion.LEGACY_ATTRIBUTE_GROUP, fusion.OWNER_NAME, SECOND_ID)
            elif failure == "missing owner":
                del second.attributes.values[(fusion.ATTRIBUTE_GROUP, fusion.OWNER_NAME)]
            else:
                key = "face_a" if failure == "face" else "axis_edge"
                extra["bad source"] = SimpleNamespace(kind="face" if failure == "face" else "edge",
                                                       isValid=True, body=first_bodies[0])
                other["sources"][key] = "bad source"
                raw = json.dumps(other)
            second.attributes.add(fusion.ATTRIBUTE_GROUP, fusion.RECIPE_NAME, raw)
            with self.subTest(failure=failure), patch.object(fusion, "_api", return_value=api()):
                with self.assertRaises(fusion.HingeGeometryError):
                    fusion._guard_root_recipe_dependencies(design, first)
            first.deleteMe.assert_not_called()
            second.deleteMe.assert_not_called()

    def test_ambiguous_other_source_token_is_not_guessed(self):
        design, _, first, _, second, _, other, _ = self.fixture()
        resolve = design.findEntityByToken
        token = other["sources"]["body_a"]
        design.findEntityByToken = lambda value: resolve(value) * 2 if value == token else resolve(value)
        with patch.object(fusion, "_api", return_value=api()):
            with self.assertRaisesRegex(fusion.HingeGeometryError, "missing or split"):
                fusion._guard_root_recipe_dependencies(design, first)
        first.deleteMe.assert_not_called()
        second.deleteMe.assert_not_called()


if __name__ == "__main__":
    unittest.main()

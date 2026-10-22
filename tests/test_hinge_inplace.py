"""In-place native API protocols; fake booleans are not CAD kernel validation."""

from copy import deepcopy
import hashlib
import json
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from Partelier.partelier.tools.hinge import fusion, inplace
from Partelier.partelier.tools.hinge.settings import HingeSettings
from test_hinge_fusion import Attributes, FEATURE_ID


class Collection:
    def __init__(self, values=()):
        self.values = list(values)

    @property
    def count(self):
        return len(self.values)

    def item(self, index):
        return self.values[index]

    def add(self, value):
        self.values.append(value)
        return True


class Entity:
    def __init__(self, host, kind, name):
        self.host = host
        self.kind = kind
        self.name = name
        self.entityToken = name + ":" + str(len(host.entities))
        self.isValid = True
        self.healthState = 0
        self.errorOrWarningMessage = ""
        self.attributes = Attributes()
        self.parentComponent = host.root
        self.deleteMe = Mock(side_effect=self._delete)
        host.entities[self.entityToken] = self

    def _delete(self):
        self.host.events.append(("delete", self))
        self.isValid = False
        return True


class Body(Entity):
    def __init__(self, host, name, volume=1, maximum=1):
        super().__init__(host, "body", name)
        self.isSolid = True
        self.isTemporary = False
        self.assemblyContext = None
        self.isLightBulbOn = True
        self.lumps = SimpleNamespace(count=1)
        self.set_shape(volume, maximum)

    def set_shape(self, volume, maximum):
        self.volume = volume
        self.boundingBox = SimpleNamespace(
            minPoint=SimpleNamespace(x=0, y=0, z=0),
            maxPoint=SimpleNamespace(x=maximum, y=maximum, z=maximum))

    def copy_shape(self, other):
        self.set_shape(other.volume, other.boundingBox.maxPoint.x)


class BaseFeature(Entity):
    def __init__(self, host):
        super().__init__(host, "feature", "owned tools")
        self.sources = []
        self.results = []
        self.editing = False
        self.fail_update = None
        self.timelineObject = host.timeline_node(self)
        self.startEdit = Mock(side_effect=self._start)
        self.finishEdit = Mock(side_effect=self._finish)
        self.updateBody = Mock(side_effect=self._update)

    @property
    def bodies(self):
        return Collection(self.host.order_sources(self.sources) if self.editing else self.results)

    def _start(self):
        self.host.events.append(("start", self))
        self.editing = True
        return True

    def _finish(self):
        self.host.events.append(("finish", self))
        old = self.results[:]
        self.sources = [source for source in self.sources if source.isValid]
        self.results = []
        for source in self.host.order_sources(self.sources):
            result = getattr(source, "result", None)
            if result is None:
                result = source.result = Body(self.host, source.name)
            result.copy_shape(source)
            self.results.append(result)
            if result.entityToken not in self.host.consumed and result not in self.host.root.bRepBodies.values:
                self.host.root.bRepBodies.add(result)
        for result in old:
            if result not in self.results and result in self.host.root.bRepBodies.values:
                self.host.root.bRepBodies.values.remove(result)
        self.editing = False
        return True

    def _update(self, source, desired):
        self.host.events.append(("update", source))
        if len(self.updateBody.call_args_list) == self.fail_update:
            return False
        source.copy_shape(desired)
        return True


class Timeline:
    def __init__(self, host):
        self.host = host
        self.nodes = []
        self._marker = 0

    @property
    def count(self):
        return len(self.nodes)

    @property
    def markerPosition(self):
        return self._marker

    @markerPosition.setter
    def markerPosition(self, value):
        self.host.events.append(("marker", value))
        self._marker = value
        if value == self.count:
            for spec in self.host.combine_inputs:
                if spec.operation == 2:
                    spec.targetBody.copy_shape(spec.toolBodies.item(0))
            for body, delta in self.host.downstream_edits:
                body.volume += delta


class Host:
    """Records target references, consumed tools, editable sources and ordering."""
    def __init__(self):
        self.entities = {}
        self.events = []
        self.consumed = set()
        self.combine_inputs = []
        self.downstream_edits = []
        self.combine_features = []
        self.fail_combine = None
        self.consume = True
        self.reverse_tools = False
        self.root = SimpleNamespace()
        self.timeline = Timeline(self)
        self.root.bRepBodies = Collection()
        self.body_adds = []
        self.root.bRepBodies.add = self.add_body
        bases = Collection()
        bases.add = self.add_base
        self.root.features = SimpleNamespace(baseFeatures=bases, combineFeatures=SimpleNamespace(
            createInput=self.combine_input, add=self.add_combine))
        self.design = SimpleNamespace(isValid=True, designType=1, rootComponent=self.root,
                                      timeline=self.timeline, findEntityByToken=self.resolve)
        self.originals = [Body(self, "existing A"), Body(self, "existing B")]
        self.originals[1].isLightBulbOn = False
        self.root.bRepBodies.values.extend(self.originals)
        self.faces = [Entity(self, "face", "face " + role) for role in ("A", "B")]
        for face, body in zip(self.faces, self.originals):
            face.body = body
        self.edge = Entity(self, "edge", "axis")
        self.edge.body = self.originals[0]
        cast = lambda kind: SimpleNamespace(cast=lambda entity: entity if getattr(entity, "kind", None) == kind else None)
        self.api = (SimpleNamespace(ObjectCollection=SimpleNamespace(create=Collection)), SimpleNamespace(
            BaseFeature=cast("feature"), BRepBody=cast("body"), BRepFace=cast("face"),
            BRepEdge=cast("edge"), CombineFeature=cast("combine"),
            FeatureOperations=SimpleNamespace(JoinFeatureOperation=1, IntersectFeatureOperation=2),
            FeatureHealthStates=SimpleNamespace(HealthyFeatureHealthState=0),
            DesignTypes=SimpleNamespace(ParametricDesignType=1),
            TemporaryBRepManager=SimpleNamespace(get=lambda: object())))

    def order_sources(self, values):
        return list(reversed(values)) if self.reverse_tools else list(values)

    def resolve(self, token):
        entity = self.entities.get(token)
        return [entity] if entity is not None and entity.isValid else []

    def timeline_node(self, feature):
        node = SimpleNamespace(index=self.timeline.count, isDeletable=True)
        def roll(before):
            self.events.append(("roll", before))
            self.timeline._marker = node.index + (0 if before else 1)
            return True
        node.rollTo = Mock(side_effect=roll)
        self.timeline.nodes.append(feature)
        self.timeline._marker = self.timeline.count
        return node

    def add_base(self):
        base = BaseFeature(self)
        self.root.features.baseFeatures.values.append(base)
        return base

    def add_body(self, desired, base=None):
        if base is None:
            self.root.bRepBodies.values.append(desired)
            return True
        self.body_adds.append((desired, base))
        source = Body(self, "editable tool")
        source.copy_shape(desired)
        base.sources.append(source)
        return source

    def combine_input(self, target, tools):
        return SimpleNamespace(targetBody=target, toolBodies=tools)

    def add_combine(self, spec):
        self.combine_inputs.append(spec)
        if len(self.combine_inputs) == self.fail_combine:
            raise RuntimeError("injected Combine failure")
        feature = Entity(self, "combine", "combine " + str(len(self.combine_inputs)))
        feature.timelineObject = self.timeline_node(feature)
        for name in ("targetBody", "toolBodies", "operation", "isKeepToolBodies", "isNewComponent"):
            setattr(feature, name, getattr(spec, name))
        self.combine_features.append(feature)
        if spec.operation == 2:
            tool = spec.toolBodies.item(0)
            spec.targetBody.copy_shape(tool)
            if self.consume:
                self.consumed.add(tool.entityToken)
                self.root.bRepBodies.values.remove(tool)
        return feature

    def prepared(self, settings=None, shape=3):
        settings = settings or HingeSettings(include_pin=False)
        roles = ["A", "B"] + (["pin"] if settings.include_pin and settings.hinge_count == 1 else
            ["pin_" + str(index + 1) for index in range(settings.hinge_count) if settings.include_pin])
        desired = tuple((role, Body(self, "transient " + role, shape + index, shape))
                        for index, role in enumerate(roles))
        return SimpleNamespace(design=self.design, face_a=self.faces[0], face_b=self.faces[1],
                               axis_edge=self.edge, settings=settings, result_bodies=desired,
                               history_anchor=None, source_signature=("sources",),
                               source_tokens={"face_a": self.faces[0].entityToken,
                                              "face_b": self.faces[1].entityToken,
                                              "axis_edge": self.edge.entityToken,
                                              "body_a": self.originals[0].entityToken,
                                              "body_b": self.originals[1].entityToken})


def fingerprint(body):
    return hashlib.sha256(str((body.volume, body.boundingBox.maxPoint.x)).encode()).hexdigest()


class NativeInplaceProtocolTests(unittest.TestCase):
    def setUp(self):
        self.host = Host()
        for name, value in (("_api", self.host.api), ("_body_signature", None), ("_assert_fresh", None), ("_selection", None)):
            mocked = patch.object(fusion, name, return_value=value)
            result = mocked.start()
            self.addCleanup(mocked.stop)
            if name == "_body_signature":
                result.side_effect = fingerprint

    def create(self, settings=None):
        prepared = self.host.prepared(settings)
        base = inplace.create(self.host.design, prepared, FEATURE_ID)
        return base, prepared

    def test_component_face_and_edge_picks_resolve_the_same_owned_inplace_hinge(self):
        base, prepared = self.create()
        self.host.root.kind = "component"
        self.host.api[1].Component = SimpleNamespace(cast=lambda value: value if getattr(value, "kind", None) == "component" else None)
        for entity in (self.host.root, *self.host.faces, self.host.edge):
            target = fusion.read_edit_target(self.host.design, entity)
            self.assertIs(target.anchor, base)
            self.assertEqual(target.settings, prepared.settings)
        self.assertFalse(any(event[0] == "delete" for event in self.host.events))

    def test_create_consumes_full_tools_into_exact_existing_targets(self):
        base, prepared = self.create()
        self.assertEqual(self.host.root.bRepBodies.values, self.host.originals)
        self.assertEqual([body.name for body in self.host.originals], ["existing A", "existing B"])
        self.assertEqual([body.isLightBulbOn for body in self.host.originals], [True, False])
        self.assertEqual([spec.targetBody for spec in self.host.combine_inputs],
                         [self.host.originals[0]] * 2 + [self.host.originals[1]] * 2)
        self.assertEqual([spec.operation for spec in self.host.combine_inputs], [1, 2, 1, 2])
        self.assertEqual([spec.isKeepToolBodies for spec in self.host.combine_inputs], [True, False, True, False])
        self.assertTrue(all(spec.isNewComponent is False for spec in self.host.combine_inputs))
        self.assertIs(self.host.combine_inputs[0].toolBodies.item(0), self.host.combine_inputs[1].toolBodies.item(0))
        self.assertIs(self.host.combine_inputs[2].toolBodies.item(0), self.host.combine_inputs[3].toolBodies.item(0))
        self.assertEqual([desired for desired, _ in self.host.body_adds], [body for _, body in prepared.result_bodies])
        self.assertTrue(all(desired not in self.host.originals for desired, _ in self.host.body_adds))
        self.assertFalse(base.editing)
        for body in self.host.originals:
            body.deleteMe.assert_not_called()

    def test_only_actual_separate_pins_increase_end_body_count(self):
        base, prepared = self.create(HingeSettings(hinge_count=2, length_mm=10))
        self.assertEqual(self.host.root.bRepBodies.count, 4)
        recipe, settings = inplace.read_recipe(base.attributes.itemByName(fusion.ATTRIBUTE_GROUP, fusion.RECIPE_NAME).value)
        self.assertEqual(set(recipe["results"]), {"A", "B", "pin_1", "pin_2"})
        self.assertEqual(recipe["tool_roles"], ["A", "B", "pin_1", "pin_2"])
        self.assertIs(inplace.result_bodies(self.host.design, recipe)["A"], self.host.originals[0])
        self.assertEqual(settings, prepared.settings)
        self.assertEqual(len(self.host.combine_features), 4)

    def test_reordered_native_tool_indices_preserve_roles_during_create_and_rebuild(self):
        self.host.reverse_tools = True
        settings = HingeSettings(hinge_count=2, length_mm=10)
        base, _ = self.create(settings)
        target = self.target(base)
        self.assertEqual(target.recipe["tool_roles"], ["pin_2", "pin_1", "B", "A"])
        self.assertEqual([body.volume for body in self.host.originals], [3, 4])
        prepared = self.host.prepared(settings, shape=7)
        prepared.history_anchor = base
        inplace.rebuild(self.host.design, target, prepared)
        self.assertEqual([body.volume for body in self.host.originals], [7, 8])
        outputs = inplace.result_bodies(self.host.design, self.target(base).recipe)
        self.assertEqual(outputs["pin_1"].volume, 9)
        self.assertEqual(outputs["pin_2"].volume, 10)
        self.assertEqual(self.host.root.bRepBodies.count, 4)

    def test_existing_owned_or_nonroot_targets_fail_before_model_mutation(self):
        for failure in ("owner", "legacy owner", "proxy", "component"):
            with self.subTest(failure=failure):
                host = Host()
                body = host.originals[0]
                if failure in ("owner", "legacy owner"):
                    group = fusion.ATTRIBUTE_GROUP if failure == "owner" else fusion.LEGACY_ATTRIBUTE_GROUP
                    body.attributes.add(group, fusion.OWNER_NAME, "already owned")
                elif failure == "proxy":
                    body.assemblyContext = object()
                else:
                    body.parentComponent = object()
                with self.assertRaises(fusion.HingeGeometryError):
                    inplace.create(host.design, host.prepared(), FEATURE_ID)
                self.assertEqual(host.timeline.count, 0)
                self.assertEqual(host.body_adds, [])
                body.deleteMe.assert_not_called()

    def test_native_failure_cleans_only_new_owned_history_in_reverse_order(self):
        self.host.fail_combine = 3
        with self.assertRaisesRegex(RuntimeError, "injected Combine"):
            self.create()
        deleted = [entity for action, entity in self.host.events if action == "delete"]
        base = self.host.root.features.baseFeatures.item(0)
        self.assertEqual(deleted, list(reversed(self.host.combine_features)) + [base])
        for original in self.host.originals:
            original.deleteMe.assert_not_called()
        self.assertTrue(all(not body.attributes.writes for body in self.host.originals))

    def test_unconsumed_tools_are_rejected_before_result_metadata_is_recorded(self):
        self.host.consume = False
        with self.assertRaisesRegex(fusion.HingeGeometryError, "duplicate bodies"):
            self.create()
        self.assertTrue(all(not body.attributes.writes for body in self.host.originals))
        self.assertTrue(all(body.isValid for body in self.host.originals))

    def target(self, base):
        return inplace._read_target(self.host.design, base)

    def test_rebuild_updates_same_editable_tools_without_new_bodies_or_features(self):
        base, _ = self.create()
        target = self.target(base)
        before_bodies = tuple(self.host.root.bRepBodies.values)
        before_tools = tuple(base.sources)
        before_combines = tuple(self.host.combine_features)
        add_count = len(self.host.body_adds)
        prepared = self.host.prepared(shape=5)
        prepared.history_anchor = base
        result = inplace.rebuild(self.host.design, target, prepared)
        self.assertIs(result, base)
        self.assertEqual(tuple(self.host.root.bRepBodies.values), before_bodies)
        self.assertEqual(tuple(base.sources), before_tools)
        self.assertEqual(tuple(self.host.combine_features), before_combines)
        self.assertEqual(len(self.host.body_adds), add_count)
        self.assertEqual([call.args[0] for call in base.updateBody.call_args_list], list(before_tools))
        self.assertEqual([call.args[1] for call in base.updateBody.call_args_list], [body for _, body in prepared.result_bodies])
        self.assertEqual([body.name for body in self.host.originals], ["existing A", "existing B"])
        self.assertEqual([body.isLightBulbOn for body in self.host.originals], [True, False])
        self.assertEqual(self.host.timeline.markerPosition, self.host.timeline.count)
        self.assertEqual([body.volume for body in self.host.originals], [5, 6])
        self.assertEqual(self.target(base).settings, prepared.settings)
        base.deleteMe.assert_not_called()
        for feature in before_combines:
            feature.deleteMe.assert_not_called()

    def test_failed_update_finishes_base_before_restoring_history_and_never_deletes_targets(self):
        base, _ = self.create()
        target = self.target(base)
        prepared = self.host.prepared(shape=6)
        prepared.history_anchor = base
        base.fail_update = 2
        self.host.events.clear()
        with self.assertRaisesRegex(fusion.HingeGeometryError, "could not update"):
            inplace.rebuild(self.host.design, target, prepared)
        finish = self.host.events.index(("finish", base))
        started = self.host.events.index(("start", base))
        restored = next(index for index, event in enumerate(self.host.events)
                        if index > started and event == ("marker", self.host.timeline.count))
        self.assertLess(finish, restored)
        self.assertFalse(base.editing)
        self.assertEqual(self.host.timeline.markerPosition, self.host.timeline.count)
        base.deleteMe.assert_not_called()
        for body in self.host.originals:
            body.deleteMe.assert_not_called()
        # The caller's failed Fusion command, not this fake, rolls back updated shapes.

    def test_changing_pin_count_with_later_history_fails_before_updating_tools(self):
        base, _ = self.create()
        target = self.target(base)
        later = Entity(self.host, "feature", "unrelated later feature")
        later.timelineObject = self.host.timeline_node(later)
        prepared = self.host.prepared(HingeSettings(include_pin=True))
        prepared.history_anchor = base
        with self.assertRaisesRegex(fusion.HingeGeometryError, "pin count.*last"):
            inplace.rebuild(self.host.design, target, prepared)
        base.updateBody.assert_not_called()
        later.deleteMe.assert_not_called()

    def test_prepared_alternate_sources_are_refused_before_tool_updates(self):
        base, _ = self.create()
        target = self.target(base)
        prepared = self.host.prepared(shape=6)
        prepared.history_anchor = base
        alternate = Entity(self.host, "face", "other source face")
        alternate.body = self.host.originals[0]
        prepared.source_tokens["face_a"] = alternate.entityToken
        with self.assertRaisesRegex(fusion.HingeGeometryError, "saved source selections"):
            inplace.rebuild(self.host.design, target, prepared)
        base.updateBody.assert_not_called()
        self.assertEqual(self.host.timeline.markerPosition, self.host.timeline.count)

    def test_edit_prepares_at_original_history_but_finishes_after_marker_restore(self):
        base, _ = self.create()
        target = self.target(base)
        settings = HingeSettings(include_pin=False, chamfer_edges=True)
        desired = self.host.prepared(settings).result_bodies
        prepared = fusion.PreparedHinge(self.host.design, *self.host.faces, self.host.edge,
            settings, object(), object(), desired, desired, ("sources",),
            {"temporary_geometry_ms": 1})
        def finishing(*args, **keywords):
            self.assertEqual(self.host.timeline.markerPosition, self.host.timeline.count)
            return args[4]
        finisher = Mock(side_effect=finishing)
        def preparing(design, face_a, face_b, edge, actual, **keywords):
            self.assertEqual(self.host.timeline.markerPosition, base.timelineObject.index)
            self.assertTrue(keywords["_historical"])
            self.assertIs(actual, settings)
            self.assertEqual((face_a, face_b, edge), (*self.host.faces, self.host.edge))
            self.assertEqual(keywords["edge_finisher"](design, object(), object(), actual, desired), desired)
            finisher.assert_not_called()
            return prepared
        with patch.object(fusion, "prepare_hinge", side_effect=preparing), patch.object(fusion, "_require_separate") as separate:
            result = inplace.prepare_edit(self.host.design, target, settings, edge_finisher=finisher)
        self.assertIs(result.history_anchor, base)
        self.assertEqual(result.source_tokens, target.recipe["sources"])
        self.assertIsNot(result.source_tokens, target.recipe["sources"])
        self.assertEqual(result.result_bodies, desired)
        finisher.assert_called_once()
        separate.assert_called_once()
        self.assertEqual(self.host.timeline.markerPosition, self.host.timeline.count)

    def test_historical_source_freshness_error_restores_marker(self):
        base, _ = self.create()
        target = self.target(base)
        prepared = self.host.prepared()
        prepared.history_anchor = base
        fusion._selection.return_value = (None, ("changed source",), self.host.edge)
        with self.assertRaisesRegex(fusion.HingeGeometryError, "pre-hinge source geometry changed"):
            inplace.assert_fresh(self.host.design, prepared)
        self.assertEqual(self.host.timeline.markerPosition, self.host.timeline.count)
        base.updateBody.assert_not_called()

    def test_history_scope_restores_exact_marker_when_source_work_raises(self):
        base, _ = self.create()
        before = self.host.timeline.markerPosition
        with self.assertRaisesRegex(RuntimeError, "source inspection"):
            with inplace.historical_scope(self.host.design, base):
                self.assertEqual(self.host.timeline.markerPosition, base.timelineObject.index)
                raise RuntimeError("source inspection failed")
        self.assertEqual(self.host.timeline.markerPosition, before)
        base.deleteMe.assert_not_called()

    def test_refused_history_roll_never_enters_source_work(self):
        base, _ = self.create()
        before = self.host.timeline.markerPosition
        base.timelineObject.rollTo.side_effect = None
        base.timelineObject.rollTo.return_value = False
        with self.assertRaisesRegex(fusion.HingeGeometryError, "could not inspect"):
            with inplace.historical_scope(self.host.design, base):
                self.fail("A refused history roll must not inspect source topology")
        self.assertEqual(self.host.timeline.markerPosition, before)

    def test_tampered_tool_order_is_rejected_before_entering_base_edit(self):
        base, _ = self.create()
        recipe, _ = inplace.read_recipe(base.attributes.itemByName(fusion.ATTRIBUTE_GROUP, fusion.RECIPE_NAME).value)
        base.results.reverse()
        base.startEdit.reset_mock()
        with self.assertRaisesRegex(fusion.HingeGeometryError, "role mapping"):
            inplace._editable_tools(self.host.design, base, recipe)
        base.startEdit.assert_not_called()
        base.updateBody.assert_not_called()

    def test_changed_combine_definitions_or_unhealthy_history_block_rebuild(self):
        base, _ = self.create()
        target = self.target(base)
        prepared = self.host.prepared(shape=6)
        prepared.history_anchor = base
        feature = self.host.combine_features[0]
        for name, changed in (("targetBody", self.host.originals[1]),
                              ("toolBodies", Collection([self.host.originals[0]])),
                              ("operation", 2), ("isKeepToolBodies", False),
                              ("isNewComponent", True), ("healthState", 1)):
            previous = getattr(feature, name)
            setattr(feature, name, changed)
            base.startEdit.reset_mock()
            with self.subTest(name=name), self.assertRaises(fusion.HingeGeometryError):
                inplace.rebuild(self.host.design, target, prepared)
            self.assertEqual(self.host.timeline.markerPosition, self.host.timeline.count)
            base.startEdit.assert_not_called()
            base.updateBody.assert_not_called()
            setattr(feature, name, previous)

    def test_edited_final_target_is_preserved_and_not_rebuilt(self):
        base, _ = self.create()
        target = self.target(base)
        prepared = self.host.prepared(shape=6)
        prepared.history_anchor = base
        # Model a persistent downstream edit which survives history recomputation.
        self.host.downstream_edits.append((self.host.originals[0], 1))
        self.host.originals[0].volume += 1
        with self.assertRaisesRegex(fusion.HingeGeometryError, "edited after creation"):
            inplace.rebuild(self.host.design, target, prepared)
        base.updateBody.assert_not_called()
        base.deleteMe.assert_not_called()
        self.host.originals[0].deleteMe.assert_not_called()

    def test_strict_recipe_rejects_damaged_or_incompatible_inplace_contract(self):
        base, _ = self.create()
        recipe, _ = inplace.read_recipe(base.attributes.itemByName(fusion.ATTRIBUTE_GROUP, fusion.RECIPE_NAME).value)
        changes = []
        for key, value in (("version", True), ("version", 10), ("persistence", "copied"),
                           ("tool_roles", ["B", "unexpected"]), ("tool_roles", ["A", "A"]),
                           ("feature_id", "invalid"), ("external_path", "outside")):
            candidate = deepcopy(recipe)
            candidate[key] = value
            changes.append(candidate)
        candidate = deepcopy(recipe)
        candidate["settings"]["output_mode"] = "separate"
        changes.append(candidate)
        for key in ("sources", "combines", "tool_tokens", "results"):
            candidate = deepcopy(recipe)
            candidate[key].pop(next(iter(candidate[key])))
            changes.append(candidate)
        for candidate in changes:
            with self.subTest(candidate=candidate), self.assertRaises(fusion.HingeGeometryError):
                inplace.read_recipe(json.dumps(candidate))
        self.assertEqual(inplace.read_recipe(json.dumps(recipe))[0], recipe)


if __name__ == "__main__":
    unittest.main()

"""Single-target pattern history protocols; native CAD validation is separate."""

from copy import deepcopy
import json
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from Partelier.partelier.tools.patterns import store as module
from test_hinge_fusion import FEATURE_ID
from test_hinge_inplace import Body, Entity, Host, Collection, fingerprint


class PatternStoreTests(unittest.TestCase):
    def setUp(self):
        self.host = Host()
        self.host.root.isValid = True
        self.store = module.PatternStore("PartelierPattern", "surface_pattern")
        self.target = self.host.originals[0]
        api = patch.object(module, "_api", return_value=self.host.api)
        api.start()
        self.addCleanup(api.stop)
        signature = patch.object(module, "_signature", side_effect=fingerprint)
        signature.start()
        self.addCleanup(signature.stop)

    def final(self, shape=3):
        body = Body(self.host, "detached pattern", shape, shape)
        body.isTemporary = True
        return body

    def create(self):
        base = self.store.create(self.host.design, self.target, self.final(), FEATURE_ID)
        return base, self.store.read(self.host.design, base)

    def assert_user_bodies_preserved(self):
        self.assertEqual(self.host.root.bRepBodies.values, self.host.originals)
        self.assertEqual([body.name for body in self.host.originals], ["existing A", "existing B"])
        self.assertEqual([body.isLightBulbOn for body in self.host.originals], [True, False])
        for body in self.host.originals:
            body.deleteMe.assert_not_called()
        self.assertEqual(self.host.originals[1].volume, 1)
        self.assertEqual(self.host.originals[1].attributes.writes, [])

    def test_create_uses_one_tool_and_two_combines_without_dummy_or_duplicate_bodies(self):
        base, record = self.create()
        self.assertIs(record.anchor, base)
        self.assertIs(record.target, self.target)
        self.assertEqual(record.feature_id, FEATURE_ID)
        self.assertEqual(len(base.sources), 1)
        self.assertEqual(len(self.host.body_adds), 1)
        self.assertEqual(self.host.timeline.count, 3)
        self.assertEqual([spec.targetBody for spec in self.host.combine_inputs], [self.target, self.target])
        self.assertEqual([spec.operation for spec in self.host.combine_inputs], [1, 2])
        self.assertEqual([spec.isKeepToolBodies for spec in self.host.combine_inputs], [True, False])
        self.assertTrue(all(not spec.isNewComponent for spec in self.host.combine_inputs))
        self.assertEqual(self.target.volume, 3)
        self.assert_user_bodies_preserved()

    def test_body_face_edge_base_and_unique_root_select_the_same_result(self):
        base, record = self.create()
        for selected in (self.target, self.host.faces[0], self.host.edge, base, self.host.root):
            with self.subTest(selected=getattr(selected, "name", "root")):
                read = self.store.read(self.host.design, selected)
                self.assertIs(read.anchor, base)
                self.assertIs(read.target, self.target)
                self.assertEqual(read.recipe, record.recipe)
                self.assertEqual(self.host.timeline.markerPosition, 3)

    def test_update_reuses_exact_same_single_tool_sources_features_and_target(self):
        base, record = self.create()
        before_sources = tuple(base.sources)
        before_combines = tuple(self.host.combine_features)
        before_adds = len(self.host.body_adds)
        self.store._attribute(base, "recipe", "tool-specific face settings")
        final = self.final(7)
        self.assertIs(self.store.update(self.host.design, record, final), base)
        self.assertEqual(tuple(base.sources), before_sources)
        self.assertEqual(tuple(self.host.combine_features), before_combines)
        self.assertEqual(len(self.host.body_adds), before_adds)
        self.assertEqual(self.host.timeline.count, 3)
        self.assertEqual(self.target.volume, 7)
        base.updateBody.assert_called_once_with(before_sources[0], final)
        self.assertEqual(base.attributes.itemByName(self.store.group, "recipe").value, "tool-specific face settings")
        self.assert_user_bodies_preserved()
        for feature in (*before_combines, base):
            feature.deleteMe.assert_not_called()

    def test_input_scope_yields_one_body_and_restores_marker_on_error(self):
        base, record = self.create()
        marker = self.host.timeline.markerPosition
        with self.assertRaisesRegex(RuntimeError, "inspection"):
            with self.store.input_scope(self.host.design, record) as original:
                self.assertIs(original, self.target)
                self.assertEqual(self.host.timeline.markerPosition, base.timelineObject.index)
                raise RuntimeError("inspection failed")
        self.assertEqual(self.host.timeline.markerPosition, marker)
        base.updateBody.assert_not_called()

    def test_read_restores_the_timeline_once_after_all_definition_checks(self):
        base, record = self.create()
        self.host.events.clear()
        current = self.store.read(self.host.design, base)
        self.assertEqual(current.feature_id, record.feature_id)
        self.assertEqual([event for event in self.host.events if event[0] == 'marker'],
                         [('marker', self.host.timeline.count)])
        self.assert_user_bodies_preserved()

    def test_failed_second_combine_inspection_restores_history_without_editing(self):
        base, record = self.create()
        feature = self.host.combine_features[1]
        feature.timelineObject.rollTo.side_effect = None
        feature.timelineObject.rollTo.return_value = False
        base.startEdit.reset_mock()
        with self.assertRaisesRegex(ValueError, 'inspect'):
            self.store.read(self.host.design, base)
        self.assertEqual(self.host.timeline.markerPosition, self.host.timeline.count)
        base.startEdit.assert_not_called()
        self.assert_user_bodies_preserved()

    def test_refused_history_roll_does_not_enter_source_work(self):
        base, record = self.create()
        base.timelineObject.rollTo.side_effect = None
        base.timelineObject.rollTo.return_value = False
        with self.assertRaisesRegex(ValueError, "inspect"):
            with self.store.input_scope(self.host.design, record):
                self.fail("Refused history must not inspect input")
        self.assertEqual(self.host.timeline.markerPosition, 3)

    def test_earlier_pattern_rebuild_preserves_later_independent_history(self):
        base, record = self.create()
        later = Entity(self.host, "feature", "later unrelated feature")
        later.timelineObject = self.host.timeline_node(later)
        self.store.update(self.host.design, record, self.final(8))
        self.assertEqual(self.host.timeline.count, 4)
        self.assertEqual(self.host.timeline.markerPosition, 4)
        later.deleteMe.assert_not_called()
        self.assert_user_bodies_preserved()

    def test_changed_target_fingerprint_and_stale_record_refuse_before_tool_edit(self):
        base, record = self.create()
        self.target.volume += 1
        base.startEdit.reset_mock()
        with self.assertRaisesRegex(ValueError, "edited after creation"):
            self.store.update(self.host.design, record, self.final(8))
        base.startEdit.assert_not_called()
        self.target.volume -= 1
        self.store.update(self.host.design, record, self.final(6))
        base.startEdit.reset_mock()
        with self.assertRaisesRegex(ValueError, "changed.*Reopen"):
            self.store.update(self.host.design, record, self.final(8))
        base.startEdit.assert_not_called()

    def test_changed_combine_definition_or_health_is_rejected_before_writes(self):
        base, record = self.create()
        feature = self.host.combine_features[0]
        for key, value in (("targetBody", self.host.originals[1]),
                           ("toolBodies", Collection((self.target,))),
                           ("operation", 2), ("isKeepToolBodies", False),
                           ("isNewComponent", True), ("healthState", 1)):
            original = getattr(feature, key)
            setattr(feature, key, value)
            base.startEdit.reset_mock()
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.store.update(self.host.design, record, self.final(9))
            base.startEdit.assert_not_called()
            self.assertEqual(self.host.timeline.markerPosition, self.host.timeline.count)
            setattr(feature, key, original)

    def test_noncontiguous_owned_features_are_rejected(self):
        base, record = self.create()
        self.host.combine_features[1].timelineObject.index += 1
        base.startEdit.reset_mock()
        with self.assertRaisesRegex(ValueError, "inserted inside"):
            self.store.update(self.host.design, record, self.final(8))
        base.startEdit.assert_not_called()

    def test_changed_editable_single_tool_refuses_before_start_edit(self):
        base, record = self.create()
        other = Body(self.host, "foreign tool")
        base.results[:] = [other]
        base.startEdit.reset_mock()
        with self.assertRaisesRegex(ValueError, "editable pattern tool"):
            self.store.update(self.host.design, record, self.final(8))
        base.startEdit.assert_not_called()

    def test_unowned_selections_and_damaged_ownership_do_not_fall_back_to_all_bodies(self):
        base, record = self.create()
        for selected in (None, object(), self.host.originals[1], self.host.faces[1]):
            with self.subTest(selected=selected), self.assertRaises(ValueError):
                self.store.read(self.host.design, selected)
        self.store._attribute(self.target, module.OWNER_NAME, "damaged")
        with self.assertRaisesRegex(ValueError, "missing or ambiguous"):
            self.store.read(self.host.design, self.target)
        with self.assertRaisesRegex(ValueError, "edited after creation"):
            self.store.read(self.host.design, base)
        base.updateBody.assert_not_called()

    def test_root_with_two_owned_patterns_is_ambiguous_but_body_selection_is_exact(self):
        first, record = self.create()
        second = self.store.create(self.host.design, self.host.originals[1], self.final(4))
        with self.assertRaisesRegex(ValueError, "ambiguous"):
            self.store.read(self.host.design, self.host.root)
        self.assertIs(self.store.read(self.host.design, self.target).anchor, first)
        self.assertIs(self.store.read(self.host.design, self.host.originals[1]).anchor, second)

    def test_duplicate_owned_anchor_is_rejected_as_ambiguous(self):
        base, record = self.create()
        other = self.host.add_base()
        for name in (module.RECORD_NAME, module.OWNER_NAME):
            tag = base.attributes.itemByName(self.store.group, name)
            self.store._attribute(other, name, tag.value)
        for selected in (base, self.target, self.host.root):
            with self.subTest(selected=selected), self.assertRaisesRegex(ValueError, "ambiguous"):
                self.store.read(self.host.design, selected)

    def test_strict_record_schema_rejects_extra_missing_nonunique_and_invalid_references(self):
        base, record = self.create()
        bad = []
        for key, value in (("version", True), ("version", 2), ("tool", "another"),
                           ("feature_id", "not-uuid"), ("result", "z"*64), ("extra", "no")):
            candidate = deepcopy(record.recipe)
            candidate[key] = value
            bad.append(candidate)
        for key in module.RECORD_KEYS:
            candidate = deepcopy(record.recipe)
            del candidate[key]
            bad.append(candidate)
        candidate = deepcopy(record.recipe)
        candidate["tool_token"] = candidate["target"]
        bad.append(candidate)
        for candidate in bad:
            with self.subTest(candidate=candidate), self.assertRaises(ValueError):
                self.store._parse(json.dumps(candidate))
        for raw in (None, "{", "[]", " "*131073):
            with self.assertRaises(ValueError):
                self.store._parse(raw)
        base.updateBody.assert_not_called()

    def test_invalid_design_proxy_subcomponent_or_persistent_final_refuse_before_create(self):
        for fault in ("direct", "marker", "proxy", "subcomponent", "persistent final"):
            with self.subTest(fault=fault):
                host = Host()
                target = host.originals[0]
                final = Body(host, "final", 3)
                final.isTemporary = True
                if fault == "direct":
                    host.design.designType = 0
                elif fault == "marker":
                    host.timeline._marker = 1
                elif fault == "proxy":
                    target.assemblyContext = object()
                elif fault == "subcomponent":
                    target.parentComponent = object()
                else:
                    final.isTemporary = False
                with self.assertRaises(ValueError):
                    self.store.create(host.design, target, final)
                self.assertEqual(host.timeline.count, 0)
                self.assertEqual(host.body_adds, [])

    def test_duplicate_create_on_owned_body_is_refused_without_new_history(self):
        self.create()
        count = self.host.timeline.count
        with self.assertRaisesRegex(ValueError, "already belongs"):
            self.store.create(self.host.design, self.target, self.final(8))
        self.assertEqual(self.host.timeline.count, count)

    def test_create_failure_cleans_only_new_owned_features_in_reverse_order(self):
        self.host.fail_combine = 2
        with self.assertRaisesRegex(RuntimeError, "injected Combine"):
            self.store.create(self.host.design, self.target, self.final(), FEATURE_ID)
        deleted = [entity for action, entity in self.host.events if action == "delete"]
        self.assertEqual(deleted, list(reversed(self.host.combine_features))
                         + [self.host.root.features.baseFeatures.item(0)])
        for body in self.host.originals:
            body.deleteMe.assert_not_called()
            self.assertEqual(body.attributes.writes, [])

    def test_unconsumed_tool_is_refused_before_target_metadata_is_stamped(self):
        self.host.consume = False
        with self.assertRaisesRegex(ValueError, "duplicate bodies"):
            self.store.create(self.host.design, self.target, self.final(), FEATURE_ID)
        self.assertEqual(self.target.attributes.writes, [])
        for body in self.host.originals:
            body.deleteMe.assert_not_called()

    def test_failed_update_finishes_edit_before_restoring_history_and_never_deletes(self):
        base, record = self.create()
        base.fail_update = 1
        self.host.events.clear()
        with self.assertRaisesRegex(ValueError, "could not update"):
            self.store.update(self.host.design, record, self.final(8))
        self.assertFalse(base.editing)
        start = self.host.events.index(("start", base))
        finish = self.host.events.index(("finish", base))
        restored = next(index for index, event in enumerate(self.host.events)
                        if index > start and event == ("marker", self.host.timeline.count))
        self.assertLess(finish, restored)
        for feature in (*self.host.originals, *self.host.combine_features, base):
            feature.deleteMe.assert_not_called()
        # Native transaction rollback, not this fake, restores intermediate shapes.


if __name__ == "__main__":
    unittest.main()

"""Native persistence protocol checks, independent of real CAD kernel geometry."""

from copy import deepcopy
import json
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from Partelier.partelier.tools import solid_pair
from test_hinge_fusion import FEATURE_ID
from test_hinge_inplace import Body, Entity, Host, Collection, fingerprint


class SolidPairStoreTests(unittest.TestCase):
    def setUp(self):
        self.host = Host()
        self.host.root.isValid = True
        self.store = solid_pair.SolidPairStore("PartelierSnapFit", "snap_fit")
        api = patch.object(solid_pair, "_api", return_value=self.host.api)
        api.start()
        self.addCleanup(api.stop)
        signature = patch.object(solid_pair, "_signature", side_effect=fingerprint)
        signature.start()
        self.addCleanup(signature.stop)

    def finals(self, shape=3):
        return tuple(Body(self.host, "detached " + role, shape + index, shape)
                     for index, role in enumerate(("A", "B")))

    def create(self):
        finals = self.finals()
        base = self.store.create(self.host.design, tuple(self.host.originals), finals, FEATURE_ID)
        return base, self.store.read(self.host.design, base)

    def assert_originals_preserved(self):
        self.assertEqual(self.host.root.bRepBodies.values, self.host.originals)
        self.assertEqual([body.name for body in self.host.originals], ["existing A", "existing B"])
        self.assertEqual([body.isLightBulbOn for body in self.host.originals], [True, False])
        for body in self.host.originals:
            body.deleteMe.assert_not_called()

    def test_create_preserves_identity_names_visibility_and_consumes_all_tools(self):
        base, record = self.create()
        self.assert_originals_preserved()
        self.assertEqual(record.targets, tuple(self.host.originals))
        self.assertIs(record.anchor, base)
        self.assertEqual(record.feature_id, FEATURE_ID)
        self.assertEqual([spec.targetBody for spec in self.host.combine_inputs],
                         [self.host.originals[0]] * 2 + [self.host.originals[1]] * 2)
        self.assertEqual([spec.operation for spec in self.host.combine_inputs], [1, 2, 1, 2])
        self.assertEqual([spec.isKeepToolBodies for spec in self.host.combine_inputs], [True, False, True, False])
        self.assertTrue(all(spec.isNewComponent is False for spec in self.host.combine_inputs))
        self.assertEqual(len(base.sources), 2)
        self.assertEqual(self.host.timeline.count, 5)
        self.assertEqual([body.volume for body in self.host.originals], [3, 4])

    def test_read_body_face_edge_and_unique_root_resolve_same_owned_anchor(self):
        base, record = self.create()
        for selected in [*self.host.originals, *self.host.faces, self.host.edge, self.host.root]:
            with self.subTest(selected=getattr(selected, "name", "root")):
                result = self.store.read(self.host.design, selected)
                self.assertIs(result.anchor, base)
                self.assertEqual(result.recipe, record.recipe)
                self.assertEqual(self.host.timeline.markerPosition, self.host.timeline.count)

    def test_unsupported_selection_and_unowned_body_do_not_change_geometry(self):
        self.create()
        unowned = Body(self.host, "unowned")
        for selected in (None, unowned, object()):
            with self.subTest(selected=selected), self.assertRaises(ValueError):
                self.store.read(self.host.design, selected)
        self.assert_originals_preserved()

    def test_update_reuses_same_feature_sources_combines_and_targets(self):
        base, record = self.create()
        before_sources = tuple(base.sources)
        before_combines = tuple(self.host.combine_features)
        before_adds = len(self.host.body_adds)
        self.store._attribute(base, "recipe", "tool-specific recipe")
        finals = self.finals(5)
        result = self.store.update(self.host.design, record, finals)
        self.assertIs(result, base)
        self.assertEqual(tuple(base.sources), before_sources)
        self.assertEqual(tuple(self.host.combine_features), before_combines)
        self.assertEqual(len(self.host.body_adds), before_adds)
        self.assertEqual(self.host.timeline.count, 5)
        self.assertEqual([body.volume for body in self.host.originals], [5, 6])
        self.assertEqual([call.args[0] for call in base.updateBody.call_args_list], list(before_sources))
        self.assertEqual([call.args[1] for call in base.updateBody.call_args_list], list(finals))
        self.assert_originals_preserved()
        self.assertEqual(base.attributes.itemByName(self.store.attribute_group, "recipe").value,
                         "tool-specific recipe")
        for feature in (*before_combines, base):
            feature.deleteMe.assert_not_called()
        self.assertNotEqual(self.store.read(self.host.design, base).recipe, record.recipe)

    def test_tool_source_order_is_mapped_even_when_fusion_returns_reverse_order(self):
        self.host.reverse_tools = True
        base, record = self.create()
        self.assertEqual(record.recipe["tool_roles"], ["B", "A"])
        self.store.update(self.host.design, record, self.finals(7))
        self.assertEqual([body.volume for body in self.host.originals], [7, 8])
        self.assert_originals_preserved()

    def test_input_scope_rolls_before_base_and_restores_exact_marker_on_error(self):
        base, record = self.create()
        marker = self.host.timeline.markerPosition
        with self.assertRaisesRegex(RuntimeError, "inspection"):
            with self.store.input_scope(self.host.design, record) as targets:
                self.assertEqual(self.host.timeline.markerPosition, base.timelineObject.index)
                self.assertEqual(targets, tuple(self.host.originals))
                raise RuntimeError("inspection failed")
        self.assertEqual(self.host.timeline.markerPosition, marker)
        base.updateBody.assert_not_called()
        self.assert_originals_preserved()

    def test_refused_history_roll_never_enters_user_source_work(self):
        base, record = self.create()
        base.timelineObject.rollTo.side_effect = None
        base.timelineObject.rollTo.return_value = False
        with self.assertRaisesRegex(ValueError, "inspect"):
            with self.store.input_scope(self.host.design, record):
                self.fail("Refused roll must never inspect sources")
        self.assertEqual(self.host.timeline.markerPosition, self.host.timeline.count)

    def test_downstream_independent_history_is_preserved_during_early_update(self):
        base, record = self.create()
        later = Entity(self.host, "feature", "later unrelated feature")
        later.timelineObject = self.host.timeline_node(later)
        self.store.update(self.host.design, record, self.finals(8))
        self.assertEqual(self.host.timeline.count, 6)
        self.assertEqual(self.host.timeline.markerPosition, 6)
        later.deleteMe.assert_not_called()
        self.assert_originals_preserved()

    def test_changed_target_fingerprint_refuses_before_any_tool_edit(self):
        base, record = self.create()
        self.host.originals[0].volume += 1
        base.startEdit.reset_mock()
        with self.assertRaisesRegex(ValueError, "edited after creation"):
            self.store.update(self.host.design, record, self.finals(8))
        base.startEdit.assert_not_called()
        base.updateBody.assert_not_called()
        self.host.originals[0].deleteMe.assert_not_called()

    def test_stale_record_after_rebuild_requires_reopen(self):
        base, record = self.create()
        self.store.update(self.host.design, record, self.finals(5))
        base.updateBody.reset_mock()
        with self.assertRaisesRegex(ValueError, "changed.*Reopen"):
            self.store.update(self.host.design, record, self.finals(8))
        base.updateBody.assert_not_called()

    def test_changed_combine_definition_and_health_are_rejected_before_writes(self):
        base, record = self.create()
        feature = self.host.combine_features[0]
        for name, value in (("targetBody", self.host.originals[1]),
                            ("toolBodies", Collection([self.host.originals[0]])),
                            ("operation", 2), ("isKeepToolBodies", False),
                            ("isNewComponent", True), ("healthState", 1)):
            previous = getattr(feature, name)
            setattr(feature, name, value)
            base.startEdit.reset_mock()
            with self.subTest(name=name), self.assertRaises(ValueError):
                self.store.update(self.host.design, record, self.finals(8))
            base.startEdit.assert_not_called()
            base.updateBody.assert_not_called()
            self.assertEqual(self.host.timeline.markerPosition, self.host.timeline.count)
            setattr(feature, name, previous)

    def test_damaged_editable_role_order_refuses_before_start_edit(self):
        base, record = self.create()
        base.results.reverse()
        base.startEdit.reset_mock()
        with self.assertRaisesRegex(ValueError, "role mapping"):
            self.store.update(self.host.design, record, self.finals(8))
        base.startEdit.assert_not_called()
        base.updateBody.assert_not_called()

    def test_duplicate_owned_anchor_refuses_ambiguous_selection(self):
        base, record = self.create()
        other = self.host.add_base()
        for name in (solid_pair.PAIR_NAME, solid_pair.OWNER_NAME):
            attribute = base.attributes.itemByName(self.store.attribute_group, name)
            self.store._attribute(other, name, attribute.value)
        for selected in (self.host.root, self.host.originals[0], base):
            with self.subTest(selected=getattr(selected, "name", "root")), self.assertRaisesRegex(ValueError, "ambiguous"):
                self.store.read(self.host.design, selected)
        base.updateBody.assert_not_called()

    def test_changed_result_ownership_does_not_fall_back_to_entire_root(self):
        base, record = self.create()
        self.store._attribute(self.host.originals[0], solid_pair.OWNER_NAME, "damaged")
        with self.assertRaisesRegex(ValueError, "missing or ambiguous"):
            self.store.read(self.host.design, self.host.originals[0])
        with self.assertRaisesRegex(ValueError, "edited after creation"):
            self.store.read(self.host.design, base)
        base.updateBody.assert_not_called()

    def test_strict_pair_schema_rejects_unsupported_damaged_and_duplicate_references(self):
        base, record = self.create()
        cases = []
        for key, value in (("version", True), ("version", 2), ("tool", "other"),
                           ("feature_id", "no"), ("tool_roles", ["A", "A"]),
                           ("tool_roles", ["B", []]), ("extra", "unsupported")):
            candidate = deepcopy(record.recipe)
            candidate[key] = value
            cases.append(candidate)
        for key in ("targets", "combines", "tool_tokens", "results"):
            candidate = deepcopy(record.recipe)
            candidate[key].pop(next(iter(candidate[key])))
            cases.append(candidate)
        for key in ("targets", "tool_tokens"):
            candidate = deepcopy(record.recipe)
            candidate[key]["B"] = candidate[key]["A"]
            cases.append(candidate)
        candidate = deepcopy(record.recipe)
        candidate["results"]["A"] = "z" * 64
        cases.append(candidate)
        for index, candidate in enumerate(cases):
            with self.subTest(index=index), self.assertRaises(ValueError):
                self.store._parse(json.dumps(candidate))
        for raw in (None, "{", " " * 131073, "[]"):
            with self.subTest(raw=str(raw)[:10]), self.assertRaises(ValueError):
                self.store._parse(raw)
        base.updateBody.assert_not_called()

    def test_nonparametric_history_mid_marker_proxy_and_subcomponent_refuse_before_create(self):
        for failure in ("direct", "marker", "proxy", "subcomponent", "same target", "same final"):
            with self.subTest(failure=failure):
                host = Host()
                finals = (Body(host, "detached A", 3), Body(host, "detached B", 4))
                targets = tuple(host.originals)
                if failure == "direct":
                    host.design.designType = 0
                elif failure == "marker":
                    host.timeline._marker = 1
                elif failure == "proxy":
                    targets[0].assemblyContext = object()
                elif failure == "subcomponent":
                    targets[0].parentComponent = object()
                elif failure == "same target":
                    targets = (targets[0], targets[0])
                else:
                    finals = (finals[0], finals[0])
                with self.assertRaises(ValueError):
                    self.store.create(host.design, targets, finals, FEATURE_ID)
                self.assertEqual(host.timeline.count, 0)
                self.assertEqual(host.body_adds, [])

    def test_duplicate_same_tool_ownership_refuses_new_create(self):
        base, record = self.create()
        before = self.host.timeline.count
        with self.assertRaisesRegex(ValueError, "already belongs"):
            self.store.create(self.host.design, tuple(self.host.originals), self.finals(8))
        self.assertEqual(self.host.timeline.count, before)

    def test_create_failure_deletes_only_new_owned_history_in_reverse_order(self):
        self.host.fail_combine = 3
        with self.assertRaisesRegex(RuntimeError, "injected Combine"):
            self.store.create(self.host.design, tuple(self.host.originals), self.finals(), FEATURE_ID)
        deleted = [entity for action, entity in self.host.events if action == "delete"]
        self.assertEqual(deleted, list(reversed(self.host.combine_features))
                         + [self.host.root.features.baseFeatures.item(0)])
        for body in self.host.originals:
            body.deleteMe.assert_not_called()
            self.assertEqual(body.attributes.writes, [])

    def test_unconsumed_tools_rejected_before_stamping_target_metadata(self):
        self.host.consume = False
        with self.assertRaisesRegex(ValueError, "duplicate bodies"):
            self.store.create(self.host.design, tuple(self.host.originals), self.finals(), FEATURE_ID)
        for body in self.host.originals:
            body.deleteMe.assert_not_called()
            self.assertEqual(body.attributes.writes, [])

    def test_failed_update_finishes_edit_before_marker_restore_and_never_deletes(self):
        base, record = self.create()
        base.fail_update = 2
        self.host.events.clear()
        with self.assertRaisesRegex(ValueError, "could not update"):
            self.store.update(self.host.design, record, self.finals(8))
        start = self.host.events.index(("start", base))
        finish = self.host.events.index(("finish", base))
        restored = next(index for index, event in enumerate(self.host.events)
                        if index > start and event == ("marker", self.host.timeline.count))
        self.assertLess(finish, restored)
        self.assertFalse(base.editing)
        self.assertEqual(self.host.timeline.markerPosition, self.host.timeline.count)
        for entity in (*self.host.originals, *self.host.combine_features, base):
            entity.deleteMe.assert_not_called()
        # Real Fusion command rollback, not this fake, restores intermediate shapes.


if __name__ == "__main__":
    unittest.main()

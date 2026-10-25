"""Cut-record ownership protocols; the fake host does not model CAD material."""

from types import SimpleNamespace as N
import unittest
from unittest.mock import patch

import test_pattern_store as fixtures


class CutStoreTests(unittest.TestCase):
    final=fixtures.PatternStoreTests.final
    assert_user_bodies_preserved=fixtures.PatternStoreTests.assert_user_bodies_preserved

    def setUp(self):
        fixtures.PatternStoreTests.setUp(self)
        signature=patch.object(fixtures.module,'_cut_signature',side_effect=fixtures.module._signature)
        signature.start();self.addCleanup(signature.stop)
        self.host.api[1].FeatureOperations.CutFeatureOperation=3
        add=self.host.add_combine
        def fake_cut(spec):
            # Abstract shape IDs use the fake host's existing copy operation.
            cut=spec.operation==3
            if cut:spec.operation=2
            feature=add(spec)
            if cut:feature.operation=3
            return feature
        self.host.root.features.combineFeatures.add=fake_cut

    def create(self):
        tool=self.final();tool.lumps=N(count=3)
        base=self.store.create(self.host.design,self.target,self.final(),cut_tool=tool)
        return base,self.store.read(self.host.design,base)

    def test_cut_preserves_target_and_has_one_consuming_native_operation(self):
        base,record=self.create()
        self.assertEqual(record.recipe['version'],2)
        self.assertEqual(set(record.recipe['combines']),{'cut'})
        self.assertEqual(self.host.timeline.count,2)
        self.assertEqual(self.host.combine_features[0].operation,3)
        self.assertFalse(self.host.combine_features[0].isKeepToolBodies)
        self.assert_user_bodies_preserved()

    def test_cut_rebuild_keeps_base_target_history_and_recipe_identity(self):
        base,record=self.create()
        self.store.update(self.host.design,record,self.final(8),cut_tool=self.final(8))
        current=self.store.read(self.host.design,self.target)
        self.assertEqual(current.feature_id,record.feature_id)
        self.assertEqual(self.host.timeline.count,2)
        self.assertEqual(self.target.volume,8)
        self.assert_user_bodies_preserved()

    def test_wrong_cut_definition_refuses_before_source_edit(self):
        base,record=self.create()
        self.host.combine_features[0].operation=1;base.startEdit.reset_mock()
        with self.assertRaises(ValueError):self.store.update(self.host.design,record,self.final(8),cut_tool=self.final(8))
        base.startEdit.assert_not_called()

    def test_missing_cut_tool_refuses_before_source_edit(self):
        base,record=self.create();base.startEdit.reset_mock()
        with self.assertRaises(ValueError):self.store.update(self.host.design,record,self.final(8))
        base.startEdit.assert_not_called()

    def test_cut_input_inspection_retains_the_active_tool_feature(self):
        base,record=self.create()
        base.timelineObject.rollTo.reset_mock()
        cut=self.host.combine_features[0]
        with self.store.input_scope(self.host.design,record) as original:
            self.assertIs(original,self.target)
            self.assertEqual(self.host.timeline.markerPosition,cut.timelineObject.index)
        base.timelineObject.rollTo.assert_not_called()
        self.assertEqual(self.host.timeline.markerPosition,self.host.timeline.count)

    def test_raised_conversion_refuses_later_history_before_any_owned_deletion(self):
        base,record=self.create()
        later=fixtures.Entity(self.host,'feature','later unrelated')
        later.timelineObject=self.host.timeline_node(later)
        cut=self.host.combine_features[0];base.startEdit.reset_mock()
        with self.assertRaisesRegex(ValueError,'end of the timeline'):
            self.store.promote(self.host.design,record,self.final(8))
        cut.deleteMe.assert_not_called();later.deleteMe.assert_not_called();base.startEdit.assert_not_called()
        self.assert_user_bodies_preserved()

    def test_raised_conversion_refuses_tampered_cut_before_deletion(self):
        base,record=self.create()
        cut=self.host.combine_features[0];cut.operation=1
        with self.assertRaises(ValueError):self.store.promote(self.host.design,record,self.final(8))
        cut.deleteMe.assert_not_called()

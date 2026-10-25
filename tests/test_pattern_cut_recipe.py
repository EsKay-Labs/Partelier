"""Owned cutter isolation and historical-source ordering for grille Cut records."""

from dataclasses import replace
from types import SimpleNamespace as N
import unittest
from unittest.mock import Mock,patch

import test_pattern_recipe as fixtures
from Partelier.partelier.tools.patterns.settings import PatternSettings


class CutRecipeTests(unittest.TestCase):
    write_recipe=fixtures.PatternRecipeTests.write_recipe
    read=fixtures.PatternRecipeTests.read
    edited=fixtures.PatternRecipeTests.edited

    def setUp(self):
        fixtures.PatternRecipeTests.setUp(self)
        self.settings=PatternSettings(pattern='grille_cross',layout_mode='fill')
        self.body.volume=100
        self.prepared=replace(self.prepared,settings=self.settings,result_body=N(volume=90,isTemporary=True))
        self.saved['settings']=self.settings.to_dict();self.write_recipe(self.saved)
        self.cutter=N(volume=10,isTemporary=True,isValid=True,isSolid=True,lumps=N(count=3))
        self.manager=N(copy=Mock(return_value=self.cutter),booleanOperation=Mock(return_value=True))
        self.fusion._api=lambda:(None,N(TemporaryBRepManager=N(get=lambda:self.manager),BooleanTypes=N(DifferenceBooleanType='difference')))

    def test_cut_material_is_an_owned_copy_with_exact_removed_volume(self):
        self.assertIs(self.module._cut_tool(self.prepared),self.cutter)
        self.manager.copy.assert_called_once_with(self.body)
        self.manager.booleanOperation.assert_called_once_with(self.cutter,self.prepared.result_body,'difference')
        self.assertEqual(self.body.volume,100)

    def test_failed_invalid_or_mismatched_cutters_are_refused(self):
        for values in ({'volume':9},{'volume':float('nan')},{'isSolid':False},{'isValid':False}):
            saved={key:getattr(self.cutter,key) for key in values}
            for key,value in values.items():setattr(self.cutter,key,value)
            with self.subTest(values=values),self.assertRaises(ValueError):self.module._cut_tool(self.prepared)
            for key,value in saved.items():setattr(self.cutter,key,value)
        self.manager.booleanOperation.return_value=False
        with self.assertRaises(ValueError):self.module._cut_tool(self.prepared)

    def test_new_grilles_pass_only_the_isolated_cut_tool_to_persistence(self):
        self.store.create.side_effect=lambda *args,**kwargs:self.anchor
        self.module.create_pattern(self.design,self.prepared)
        self.store.create.assert_called_once_with(self.design,self.body,self.prepared.result_body,cut_tool=self.cutter)

    def test_cut_rebuild_captures_original_material_inside_history_before_writes(self):
        self.record.recipe={'version':2}
        target,prepared=self.edited()
        def capture(value):
            self.assertTrue(self.design.historical)
            return self.cutter
        def update(*args,**kwargs):
            self.assertFalse(self.design.historical)
            return self.anchor
        self.store.update.side_effect=update
        with patch.object(self.module,'_cut_tool',side_effect=capture) as cut:
            self.module.rebuild_pattern(self.design,target,prepared)
        cut.assert_called_once_with(prepared)
        self.store.update.assert_called_once_with(self.design,self.record,prepared.result_body,cut_tool=self.cutter)

    def test_raised_create_uses_complete_shape_without_cutting_away_added_material(self):
        prepared=replace(self.prepared,settings=replace(self.settings,grille_profile='raised'))
        self.module.create_pattern(self.design,prepared)
        self.store.create.assert_called_once_with(self.design,self.body,prepared.result_body)
        self.manager.copy.assert_not_called()

    def test_cut_to_raised_validates_historical_sources_then_promotes_after_restoring(self):
        self.record.recipe={'version':2}
        target,prepared=self.edited(replace(self.settings,grille_profile='chamfer'))
        def promote(*args):
            self.assertFalse(self.design.historical)
            return self.anchor
        self.store.promote=Mock(side_effect=promote)
        self.module.rebuild_pattern(self.design,target,prepared)
        self.store.promote.assert_called_once_with(self.design,self.record,prepared.result_body)
        self.store.update.assert_not_called()
        self.manager.copy.assert_not_called()

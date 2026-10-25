"""Small details reference sequencing and Esc reset without a CAD kernel."""

import importlib.util
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace as NS, MethodType
import unittest
from unittest.mock import Mock, patch


class DetailSelectionTests(unittest.TestCase):
    def setUp(self):
        core=ModuleType('adsk.core');native=ModuleType('adsk.fusion');adsk=ModuleType('adsk')
        self.ui=NS(selectEntity=Mock());core.Application=NS(get=lambda:NS(userInterface=self.ui))
        adsk.core=core;adsk.fusion=native
        prefix='Partelier.partelier.tools'
        lifecycle=ModuleType(prefix+'.patterns.command');lifecycle.PatternCommands=object;lifecycle._Session=object
        runner=ModuleType(prefix+'.hinge.native_preview');runner.NativePreviewRunner=object
        adapter=ModuleType(prefix+'.details.fusion');store=ModuleType(prefix+'.details.store')
        name=prefix+'.details._selection_test'
        spec=importlib.util.spec_from_file_location(name,Path(__file__).parents[1]/'Partelier/partelier/tools/details/command.py')
        self.module=importlib.util.module_from_spec(spec)
        from Partelier.partelier.tools import patterns,details
        with patch.dict(sys.modules,{'adsk':adsk,'adsk.core':core,'adsk.fusion':native,lifecycle.__name__:lifecycle,runner.__name__:runner,adapter.__name__:adapter,store.__name__:store}),patch.object(patterns,'command',lifecycle,create=True),patch.object(details,'fusion',adapter,create=True),patch.object(details,'store',store,create=True):
            spec.loader.exec_module(self.module)
        self.states=[]
        self.owner=NS(runner=NS(cancel=Mock()))
        self.owner.publish=lambda s:self.states.append((s.picking_target,s.faces,s.phase,s.revision))
        for name in ('pick','_pick_one','reset'):
            setattr(self.owner,name,MethodType(getattr(self.module.DetailCommands,name),self.owner))
        self.session=NS(editing=False,ensure_design=Mock(),clear_preview=Mock(),settings=NS(kind='lid'),
                        faces=(None,None),phase='selecting',message='',picking_target=None,revision=0,edit_target=None)
        self.session.validate=lambda:setattr(self.session,'phase','ready' if all(self.session.faces) else 'selecting')
        self.a=NS(isValid=True);self.b=NS(isValid=True)

    def test_face_a_auto_advances_to_b_and_publishes_each_active_step(self):
        self.ui.selectEntity.side_effect=[NS(entity=self.a),NS(entity=self.b)]
        self.owner.pick(self.session,'face_a')
        self.assertEqual(self.session.faces,(self.a,self.b));self.assertEqual(self.session.phase,'ready')
        self.assertEqual([state[0] for state in self.states],['face_a','face_b',None])
        self.assertEqual(self.states[1][1],(self.a,None))
        self.assertEqual(self.ui.selectEntity.call_count,2)

    def test_escape_on_second_face_resets_all_supports_and_retires_preview_revision(self):
        self.ui.selectEntity.side_effect=[NS(entity=self.a),RuntimeError('Esc')]
        self.owner.pick(self.session,'face_a')
        self.assertEqual(self.session.faces,(None,None));self.assertEqual(self.session.phase,'selecting')
        self.assertEqual(self.session.revision,1);self.assertIsNone(self.session.picking_target)
        self.assertIn('Selection reset',self.session.message)
        self.owner.runner.cancel.assert_called_once_with(self.session)

    def test_repick_b_does_not_ask_for_a_and_reset_keeps_dimensions(self):
        self.session.faces=(self.a,self.b);settings=self.session.settings
        replacement=NS(isValid=True);self.ui.selectEntity.return_value=NS(entity=replacement)
        self.owner.pick(self.session,'face_b')
        self.assertEqual(self.session.faces,(self.a,replacement));self.assertEqual(self.ui.selectEntity.call_count,1)
        self.owner.reset(self.session)
        self.assertIs(self.session.settings,settings);self.assertEqual(self.session.faces,(None,None))

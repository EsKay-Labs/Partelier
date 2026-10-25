"""The native validation entry point owns only disposable documents."""

import importlib.util
from pathlib import Path
from types import ModuleType,SimpleNamespace as N
import unittest
from unittest.mock import Mock,patch


class Empty:
    count=0
    def item(self,index):raise IndexError(index)


class IsolationTests(unittest.TestCase):
    def setUp(self):
        self.camera=object()
        self.app=N(activeViewport=N(camera=self.camera))
        def document(label):
            design=N(label=label,designType='parametric',activeComponent=object(),rootComponent=N(bRepBodies=Empty()))
            doc=N(label=label,isValid=True,design=design)
            def activate():self.app.activeDocument=doc;self.app.activeProduct=design;return True
            def close(save):
                if label=='caller':raise AssertionError('Never close the caller document')
                self.assertFalse(save);doc.isValid=False;return True
            doc.activate=Mock(side_effect=activate);doc.close=Mock(side_effect=close)
            return doc
        self.caller=document('caller');self.owned=document('owned');self.caller.activate()
        self.app.documents=N(add=Mock(side_effect=lambda kind:self.owned.activate() and self.owned))
        adsk,core,native=(ModuleType(name) for name in ('adsk','adsk.core','adsk.fusion'))
        adsk.core=core;adsk.fusion=native
        core.Application=N(get=lambda:self.app);core.DocumentTypes=N(FusionDesignDocumentType='design')
        for name in ('CustomEventHandler','CommandEventHandler','CommandCreatedEventHandler'):setattr(core,name,object)
        native.Design=N(cast=lambda value:value);native.DesignTypes=N(ParametricDesignType='parametric')
        path=Path(__file__).parents[1]/'tools/fusion/PatternProbe/PatternProbe.py'
        spec=importlib.util.spec_from_file_location('_pattern_probe_isolation',path)
        self.module=importlib.util.module_from_spec(spec)
        with patch.dict('sys.modules',{'adsk':adsk,'adsk.core':core,'adsk.fusion':native}):spec.loader.exec_module(self.module)
        self.module.snapshot=lambda design:{'label':design.label}

    def test_native_work_starts_in_a_fresh_document_and_retains_the_caller(self):
        def start(context):self.assertIs(self.app.activeProduct,self.owned.design)
        self.module._run_owned=Mock(side_effect=start)
        self.module.run({'request':'small'})
        self.module._run_owned.assert_called_once_with({'request':'small'})
        self.assertIs(self.module.STATE['caller']['document'],self.caller)
        self.assertIs(self.module.STATE['validation_document'],self.owned)
        self.caller.close.assert_not_called()

    def test_setup_failure_discards_only_the_owned_document_and_restores_caller(self):
        self.module._run_owned=Mock(side_effect=RuntimeError('registration failed'))
        with self.assertRaisesRegex(RuntimeError,'registration failed'):self.module.run({})
        self.owned.close.assert_called_once_with(False)
        self.caller.close.assert_not_called()
        self.assertIs(self.app.activeDocument,self.caller)
        self.assertIs(self.app.activeViewport.camera,self.camera)

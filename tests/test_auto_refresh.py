import sys,unittest
from pathlib import Path
from types import SimpleNamespace,ModuleType
from unittest.mock import patch
from Partelier.partelier import refresh_context
from Partelier.partelier import auto_refresh
from Partelier.partelier.auto_refresh import _tokens,_hash,AutomaticUpdates
from Partelier.partelier.palette_protocol import read_request
import json

class AutomaticUpdateContracts(unittest.TestCase):
    def test_failed_baseline_save_aborts_automatic_batch_but_not_optional_enrollment(self):
        design=object();anchor=SimpleNamespace(attributes=SimpleNamespace(add=lambda *args:None))
        record={'anchor':anchor};native=ModuleType('adsk.fusion');native.Design=SimpleNamespace(cast=lambda value:value)
        adsk=ModuleType('adsk');adsk.fusion=native
        with patch.dict(sys.modules,{'adsk':adsk,'adsk.fusion':native}),patch.object(auto_refresh.operations,'records',return_value=[record]),patch.object(auto_refresh,'baseline',return_value={}),patch('Partelier.partelier.diagnostics.emit'):
            auto_refresh.capture(design,anchor)
            with self.assertRaisesRegex(ValueError,'save update baseline'):
                auto_refresh.capture(design,anchor,strict=True)

    def test_failure_latch_requires_explicit_reenable(self):
        design=SimpleNamespace(isValid=True,rootComponent=SimpleNamespace(attributes=SimpleNamespace(itemByName=lambda *args:None)))
        adsk=ModuleType('adsk');adsk.core=ModuleType('adsk.core');adsk.fusion=ModuleType('adsk.fusion')
        adsk.core.Application=SimpleNamespace(get=lambda:SimpleNamespace(activeProduct=design))
        adsk.fusion.Design=SimpleNamespace(cast=lambda value:value)
        service=AutomaticUpdates(None)
        with patch.dict(sys.modules,{'adsk':adsk,'adsk.core':adsk.core,'adsk.fusion':adsk.fusion}):
            self.assertTrue(service.enabled())
            service.failed_designs.append(design)
            self.assertFalse(service.enabled())
            service.cancel_palette()
            self.assertFalse(service.enabled())
            service.reset_failure(design)
            self.assertTrue(service.enabled())

    def test_sketch_only_edits_invalidate_the_cheap_revision_gate(self):
        body=SimpleNamespace(revisionId='body-1');sketch=SimpleNamespace(revisionId='sketch-1')
        design=SimpleNamespace(timeline=SimpleNamespace(count=3),rootComponent=SimpleNamespace(bRepBodies=[body],sketches=[sketch]))
        adsk=ModuleType('adsk');adsk.core=ModuleType('adsk.core');adsk.fusion=ModuleType('adsk.fusion')
        adsk.core.Application=SimpleNamespace(get=lambda:SimpleNamespace(activeProduct=design))
        adsk.fusion.Design=SimpleNamespace(cast=lambda value:value)
        service=AutomaticUpdates(None)
        with patch.dict(sys.modules,{'adsk':adsk,'adsk.core':adsk.core,'adsk.fusion':adsk.fusion}):
            before=service.revisions()
            self.assertEqual(before,service.revisions())
            sketch.revisionId='sketch-2'
            self.assertNotEqual(before,service.revisions())
            self.assertEqual(body.revisionId,'body-1')

    def test_scope_restores_even_on_failure_and_never_authorizes_another_anchor(self):
        design=SimpleNamespace(timeline=SimpleNamespace(count=20,markerPosition=20));anchor=object()
        with self.assertRaisesRegex(ValueError,'failure'):
            with refresh_context.scope(design,anchor,9):
                self.assertEqual(refresh_context.end(design),9)
                self.assertTrue(refresh_context.authorized(design,anchor))
                self.assertFalse(refresh_context.authorized(design,object()))
                with self.assertRaisesRegex(ValueError,'already'):
                    with refresh_context.scope(design,anchor,4):pass
                raise ValueError('failure')
        self.assertEqual(design.timeline.markerPosition,20)
        self.assertEqual(refresh_context.end(design),20)
        self.assertFalse(refresh_context.authorized(design,anchor))

    def test_only_actual_reference_values_are_collected(self):
        self.assertEqual(list(_tokens({'faces':['a','b'],'body':'c','flag':True})),['a','b','c'])
        self.assertEqual(_hash({'a':1,'b':2}),_hash({'b':2,'a':1}))

    def test_switch_requires_an_exact_boolean_payload(self):
        base={'protocol':1,'requestId':'update-test'}
        for value in (True,False):self.assertIs(read_request('auto_update_toggle',json.dumps({**base,'enabled':value})).enabled,value)
        for value in ('true',0,None,[]):
            with self.assertRaises(ValueError):read_request('auto_update_toggle',json.dumps({**base,'enabled':value}))
        with self.assertRaises(ValueError):read_request('auto_update_status',json.dumps({**base,'enabled':True}))

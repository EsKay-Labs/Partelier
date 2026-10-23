"""Diagnostic events must preserve the real rollback driver ordering/results."""

import importlib.util
from pathlib import Path
import sys
from types import ModuleType,SimpleNamespace
import unittest
from unittest.mock import Mock,patch
import uuid


ROOT=Path(__file__).resolve().parents[1]/'Partelier'/'partelier'


class Event:
    def __init__(self):self.handlers=[]
    def add(self,handler):self.handlers.append(handler);return True
    def remove(self,handler):
        if handler in self.handlers:self.handlers.remove(handler)
        return True
    def fire(self,args):
        for handler in tuple(self.handlers):handler.notify(args)


class PatternTraceTests(unittest.TestCase):
    def setUp(self):
        self.events=[];self.order=[];self.queue=[]
        self.ui=SimpleNamespace(activeCommand='SelectCommand')
        self.app=SimpleNamespace(userInterface=self.ui,log=Mock())
        def fire(identity,information):self.queue.append(information);return False
        self.app.fireCustomEvent=fire
        core=ModuleType('adsk.core')
        core.Application=SimpleNamespace(get=lambda:self.app)
        for name in ('CommandCreatedEventHandler','CommandEventHandler','CustomEventHandler'):
            setattr(core,name,type(name,(),{}))
        adsk=ModuleType('adsk');adsk.core=core
        self.prefix='_pattern_trace_'+uuid.uuid4().hex
        modules={'adsk':adsk,'adsk.core':core}
        for suffix,path in (('',ROOT),('.tools',ROOT/'tools'),('.tools.patterns',ROOT/'tools/patterns'),('.tools.hinge',ROOT/'tools/hinge')):
            package=ModuleType(self.prefix+suffix);package.__path__=[str(path)];modules[package.__name__]=package
        diagnostics=ModuleType(self.prefix+'.diagnostics')
        diagnostics.emit=lambda event,**fields:self.events.append((event,fields))
        modules[diagnostics.__name__]=diagnostics
        self.patch=patch.dict(sys.modules,modules);self.patch.start();self.addCleanup(self.patch.stop)
        self.addCleanup(lambda:[sys.modules.pop(name,None) for name in tuple(sys.modules) if name.startswith(self.prefix)])
        name=self.prefix+'.tools.patterns.preview'
        spec=importlib.util.spec_from_file_location(name,ROOT/'tools/patterns/preview.py')
        self.module=importlib.util.module_from_spec(spec);sys.modules[name]=self.module;spec.loader.exec_module(self.module)
        self.runner=self.module.PatternPreviewRunner()
        test=self
        class Command:
            def __init__(self):
                self.executePreview=Event();self.execute=Event();self.destroy=Event();self.isValid=True
            def doExecutePreview(self):
                test.order.append('preview');self.executePreview.fire(SimpleNamespace(isValidResult=True));return True
            def doExecute(self,confirmed):
                test.order.extend(('rollback','execute'));self.execute.fire(SimpleNamespace())
                test.ui.activeCommand='SelectCommand';self.isValid=False
                test.order.append('destroy');self.destroy.fire(SimpleNamespace());return True
        class Definition:
            isValid=True
            commandCreated=Event()
            def execute(self):
                test.ui.activeCommand=test.runner._command_id
                test.runner.created(Command());return True
            def deleteMe(self):self.isValid=False;return True
        def start(runner):runner._definition=Definition()
        self.start_patch=patch.object(self.module.NativePreviewRunner,'_start',start)
        self.start_patch.start();self.addCleanup(self.start_patch.stop);self.addCleanup(self.runner.stop)

    def drain(self):
        while self.queue:self.runner.drive(self.queue.pop(0))

    def names(self):return [event for event,fields in self.events]

    def test_log_order_follows_queued_compute_rollback_destroy_and_completed_callback(self):
        completed=Mock();failed=Mock();prepared=object()
        self.runner.request(object(),lambda:prepared,completed,failed)
        self.assertNotIn('pattern.runner.compute.begin',self.names())
        self.assertIn('pattern.runner.driver.queued',self.names())
        self.drain()
        self.assertEqual(self.order,['preview','rollback','execute','destroy'])
        completed.assert_called_once_with(prepared);failed.assert_not_called()
        names=self.names()
        for before,after in (('driver.queued','drive.begin'),('compute.begin','compute.end'),
                             ('compute.end','destroy.begin'),('destroy.begin','callback.completed.begin'),
                             ('callback.completed.end','destroy.end')):
            self.assertLess(names.index('pattern.runner.'+before),names.index('pattern.runner.'+after))
        callback=next(fields for event,fields in self.events if event=='pattern.runner.callback.completed.begin')
        self.assertEqual(callback['serial'],1)
        self.assertIsNone(callback['current_serial'],'finished request serial cannot depend on cleared current state')
        self.assertEqual(callback['active_command'],'SelectCommand')
        self.assertFalse(self.runner.busy)

    def test_compute_error_is_delivered_unchanged_after_destroy_and_traced(self):
        error=RuntimeError('native compute failed');completed=Mock();failed=Mock()
        def compute():raise error
        self.runner.request(object(),compute,completed,failed);self.drain()
        completed.assert_not_called();failed.assert_called_once_with(error)
        end=next(fields for event,fields in self.events if event=='pattern.runner.compute.end')
        self.assertEqual(end['error_type'],'RuntimeError')
        self.assertEqual(end['error'],'native compute failed')
        self.assertLess(self.names().index('pattern.runner.destroy.begin'),self.names().index('pattern.runner.callback.failed.begin'))
        self.assertEqual(self.order,['preview','rollback','execute','destroy'])

    def test_callback_exception_is_traced_then_reaches_existing_base_error_handler(self):
        def completed(value):raise RuntimeError('draw callback failed')
        self.runner.request(object(),lambda:object(),completed,Mock());self.drain()
        self.assertIn('pattern.runner.callback.completed.error',self.names())
        self.assertIn('pattern.runner.internal.error',self.names())
        self.app.log.assert_called()
        self.assertFalse(self.runner.busy)

    def test_failed_log_sink_cannot_change_compute_or_cleanup(self):
        self.module.emit=Mock(side_effect=OSError('log disk unavailable'))
        completed=Mock();failed=Mock();prepared=object()
        self.runner.request(object(),lambda:prepared,completed,failed);self.drain()
        completed.assert_called_once_with(prepared);failed.assert_not_called()
        self.assertEqual(self.order,['preview','rollback','execute','destroy'])
        self.assertFalse(self.runner.busy)

    def test_superseded_request_keeps_original_latest_only_behavior(self):
        old_compute=Mock();old_done=Mock();new_compute=Mock(return_value='new');new_done=Mock();failed=Mock()
        self.runner.request(object(),old_compute,old_done,failed)
        self.runner.request(object(),new_compute,new_done,failed)
        self.drain()
        old_compute.assert_not_called();old_done.assert_not_called()
        new_compute.assert_called_once_with();new_done.assert_called_once_with('new');failed.assert_not_called()
        callback=next(fields for event,fields in self.events if event=='pattern.runner.callback.completed.begin')
        self.assertEqual(callback['serial'],2)
        self.assertFalse(self.runner.busy)


if __name__=='__main__':unittest.main()

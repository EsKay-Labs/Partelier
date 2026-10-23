"""Diagnostics stay bounded, correlated, thread-safe and harmless on I/O failure."""

import importlib.util
import json
from pathlib import Path
import tempfile
import threading
import unittest

from Partelier.partelier.palette_protocol import read_request


class DiagnosticTests(unittest.TestCase):
    def setUp(self):
        self.directory=tempfile.TemporaryDirectory();self.addCleanup(self.directory.cleanup)
        self.path=Path(self.directory.name)/'logs/partelier.jsonl'
        source=Path(__file__).parents[1]/'Partelier/partelier/diagnostics.py'
        spec=importlib.util.spec_from_file_location('_isolated_diagnostic_test',source)
        self.logger=importlib.util.module_from_spec(spec);spec.loader.exec_module(self.logger)

    def records(self):return [json.loads(line) for line in self.path.read_text(encoding='utf-8').splitlines()]

    def test_disabled_import_does_not_create_a_file(self):
        self.assertFalse(self.logger.emit('ignored'))
        self.assertFalse(self.path.exists())

    def test_run_sequence_and_request_identifiers_survive_unicode_and_errors(self):
        self.logger.start('test',path=self.path)
        self.assertTrue(self.logger.emit('request.begin',request_id='ui-7',session_id='s',revision=4,detail='επιλογή'))
        self.assertTrue(self.logger.emit('request.error',error='failed',bad_number=float('nan'),object_value=object()))
        rows=self.records()
        self.assertEqual([row['sequence'] for row in rows],[1,2,3])
        self.assertEqual(len({row['run_id'] for row in rows}),1)
        self.assertEqual(rows[1]['data']['detail'],'επιλογή')
        self.assertEqual(rows[2]['data']['bad_number'],'nan')
        self.assertEqual(rows[2]['data']['object_value'],'object')
        self.assertTrue(rows[0]['utc'].endswith('+00:00'))

    def test_rotation_keeps_three_backups_and_complete_json_lines(self):
        self.logger.MAX_BYTES=700
        self.logger.start('test',path=self.path)
        for index in range(20):self.assertTrue(self.logger.emit('test',index=index))
        files=list(self.path.parent.glob('partelier.jsonl*'))
        self.assertEqual(len(files),4)
        for file in files:
            self.assertLessEqual(file.stat().st_size,700)
            self.assertTrue(all(json.loads(line) for line in file.read_text().splitlines()))

    def test_unwritable_destination_cannot_interrupt_the_caller(self):
        parent=Path(self.directory.name)/'blocking-file';parent.write_text('occupied')
        self.logger.start('test',path=parent/'partelier.jsonl')
        self.assertFalse(self.logger.emit('test'))

    def test_concurrent_writers_preserve_whole_lines_and_unique_sequence(self):
        self.logger.start('test',path=self.path)
        threads=[threading.Thread(target=lambda:[self.logger.emit('thread',index=i) for i in range(12)]) for _ in range(3)]
        for thread in threads:thread.start()
        for thread in threads:thread.join()
        rows=self.records();self.assertEqual(len(rows),37)
        self.assertEqual([row['sequence'] for row in rows],list(range(1,38)))

    def request(self,entries,**extra):
        return json.dumps({'protocol':1,'requestId':'trace-1','entries':entries,**extra})

    def test_ui_trace_has_a_separate_strict_bounded_read_only_contract(self):
        entry={'event':'request.send','at':123,'context':{'action':'pattern_begin','busy':True,'revision':0}}
        value=read_request('diagnostic_log',self.request([entry]))
        self.assertEqual(value.request_id,'trace-1');self.assertEqual(value.diagnostics,(entry,))
        self.assertIsNone(value.settings);self.assertIsNone(value.session_id)
        for entries in ([],[entry]*11,[dict(entry,code='execute')],
                        [dict(entry,at=True)],[dict(entry,at=float('inf'))],
                        [dict(entry,event='not allowed!')],[dict(entry,context={'x':[]})],
                        [dict(entry,context={'x':'x'*513})]):
            with self.subTest(entries=str(entries)[:80]),self.assertRaises(ValueError):
                read_request('diagnostic_log',self.request(entries))
        with self.assertRaises(ValueError):read_request('diagnostic_log',self.request([entry],path='elsewhere'))
        with self.assertRaises(ValueError):read_request('diagnostic_log','x'*16385)

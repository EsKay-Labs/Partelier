"""Knob grip ownership and protocol boundaries, outside Fusion."""
import json
import unittest
import uuid
from types import SimpleNamespace as NS
from unittest.mock import patch

from Partelier.partelier import operations, auto_refresh
from Partelier.partelier.palette_protocol import read_request
from Partelier.partelier.tools.knurl.settings import KnurlSettings
from Partelier.partelier.tools.knurl import store


def recipe():
    return {'version':1,'id':str(uuid.uuid4()),'settings':KnurlSettings().to_dict(),
            'sources':{'faces':['face'],'bodies':['body']},'base':'base',
            'combines':['combine'],'tools':['tool'],
            'tool_signatures':['a'*64],'results':['b'*64]}


class KnurlWorkflowTests(unittest.TestCase):
    def test_knurling_has_its_own_saved_section_and_owned_history(self):
        value=recipe()
        tag=NS(value=json.dumps(value))
        anchor=NS(isValid=True,attributes=NS(itemByName=lambda group,name:tag if (group,name)==(store.GROUP,'record') else None))
        tag.parent=anchor
        design=NS(findAttributes=lambda group,name:[tag] if (group,name)==(store.GROUP,'record') else [])
        rows=operations.snapshot(design)
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]['id'],value['id'])
        self.assertEqual(rows[0]['alias'],'knurling')
        self.assertEqual(rows[0]['tool'],'knurling')
        self.assertFalse(rows[0]['canDelete'])
        self.assertEqual(json.loads(tag.value),value,'Listing must not migrate or rewrite ownership.')

    def test_automatic_refresh_reuses_guarded_saved_edit_path(self):
        design,anchor,prepared=object(),object(),object()
        record=NS(settings=KnurlSettings())
        with patch.object(store,'read',return_value=record) as read,patch.object(store,'prepare_edit',return_value=prepared) as prepare,patch.object(store,'apply') as apply:
            auto_refresh._rebuild(design,{'tool':'knurling','anchor':anchor})
        read.assert_called_once_with(design,anchor)
        prepare.assert_called_once_with(design,record,record.settings)
        apply.assert_called_once_with(prepared)

    def test_one_source_one_tool_one_cut_contract(self):
        value=recipe()
        self.assertEqual(store._parse(json.dumps(value)),(value,KnurlSettings()))
        for key in ('combines','tools','tool_signatures','results'):
            for count in (0,2):
                bad=recipe();bad[key]*=count
                with self.subTest(key=key,count=count),self.assertRaises(ValueError):
                    store._parse(json.dumps(bad))
        for key in ('faces','bodies'):
            bad=recipe();bad['sources'][key].append('second')
            with self.assertRaises(ValueError):store._parse(json.dumps(bad))

    def test_rejects_damaged_ownership_and_unsupported_schema(self):
        for patch in ({'version':True},{'version':2},{'extra':True},{'base':''},
                      {'id':'invalid'},{'results':['x'*64]},{'tools':[None]}):
            value=recipe();value.update(patch)
            with self.subTest(patch=patch),self.assertRaises(ValueError):
                store._parse(json.dumps(value))

    def test_active_settings_are_complete_atomic_snapshots(self):
        request={'protocol':1,'requestId':'test','sessionId':str(uuid.uuid4()),
                 'revision':2,'settings':KnurlSettings().to_dict()}
        for action in ('knurling_update','knurling_preview','knurling_commit'):
            self.assertEqual(read_request(action,json.dumps(request)).settings,KnurlSettings())
            bad={**request,'settings':{k:v for k,v in request['settings'].items() if k!='depth_mm'}}
            with self.assertRaises(ValueError):read_request(action,json.dumps(bad))

    def test_begin_defaults_and_only_supported_selection_targets(self):
        payload={'protocol':1,'requestId':'test','editing':False,'settings':{'style':'flutes'}}
        self.assertEqual(read_request('knurling_begin',json.dumps(payload)).settings.style,'flutes')
        base={'protocol':1,'requestId':'test','sessionId':str(uuid.uuid4())}
        for target in ('face_a','edit_target'):
            self.assertEqual(read_request('knurling_focus',json.dumps({**base,'target':target})).target,target)
        for target in ('face_b','faces','body'):
            with self.assertRaises(ValueError):read_request('knurling_focus',json.dumps({**base,'target':target}))
        for action in ('knurling_reset','knurling_cancel'):
            self.assertEqual(read_request(action,json.dumps(base)).session_id,base['sessionId'])

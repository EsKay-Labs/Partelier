"""Thread ownership and UI message contracts, without requiring Fusion."""
from dataclasses import replace
import json
import unittest
import uuid
from Partelier.partelier.tools.threads.settings import ThreadSettings
from Partelier.partelier.tools.threads import store
from Partelier.partelier.palette_protocol import read_request


def recipe(mode):
    s=replace(ThreadSettings(),mode=mode)
    count=0 if mode=='coupon' else 2 if mode=='pair' else 1
    n=4 if mode=='coupon' else count
    return {'version':1,'id':str(uuid.uuid4()),'settings':s.to_dict(),
        'sources':{'faces':['face'+str(i) for i in range(count)],'bodies':['body'+str(i) for i in range(count)]},
        'base':'base','combines':['combine'+str(i) for i in range(count)],
        'tools':['tool'+str(i) for i in range(n)],'tool_signatures':['a'*64]*n,'results':['b'*64]*n}


class ThreadOwnershipTests(unittest.TestCase):
    def test_coupon_rebuild_refreshes_generated_clearance_labels_only(self):
        old=replace(ThreadSettings(),mode='coupon')
        for index,clearance in enumerate((.15,.25,.35),1):
            generated=f'Partelier · Thread coupon · radial clearance {clearance:g} mm'
            updated=f'Partelier · Thread coupon · radial clearance {clearance+.1:g} mm'
            self.assertEqual(store._coupon_body_name(generated,old,index,updated),updated)
            self.assertEqual(store._coupon_body_name('My fit sample',old,index,updated),'My fit sample')
        self.assertEqual(store._coupon_body_name('Custom male grip',old,0,'Partelier · Thread coupon · male'),'Custom male grip')

    def test_four_modes_have_exact_owned_body_and_history_counts(self):
        for mode in ('external','internal','pair','coupon'):
            with self.subTest(mode=mode):
                raw=recipe(mode);parsed,s=store._parse(json.dumps(raw))
                self.assertEqual(parsed,raw);self.assertEqual(s.mode,mode)
                for field in ('tools','tool_signatures','results'):
                    bad=json.loads(json.dumps(raw));bad[field].pop()
                    with self.assertRaises(ValueError):store._parse(json.dumps(bad))

    def test_coupon_cannot_claim_source_bodies_or_combines(self):
        for field in ('combines','sources'):
            raw=recipe('coupon')
            raw[field]=['combine'] if field=='combines' else {'faces':['face'],'bodies':['body']}
            with self.assertRaises(ValueError):store._parse(json.dumps(raw))

    def test_record_rejects_unowned_fields_tokens_and_duplicates(self):
        for change in ({'version':True},{'version':2},{'extra':True},{'base':None},{'tools':['same','same']}):
            raw=recipe('pair');raw.update(change)
            with self.subTest(change=change),self.assertRaises(ValueError):store._parse(json.dumps(raw))

    def test_pair_requires_two_distinct_sources(self):
        raw=recipe('pair');raw['sources']['bodies']=['body','body']
        with self.assertRaises(ValueError):store._parse(json.dumps(raw))

    def test_active_thread_updates_require_complete_atomic_settings(self):
        request={'protocol':1,'requestId':'test','sessionId':str(uuid.uuid4()),'revision':2,'settings':ThreadSettings().to_dict()}
        parsed=read_request('thread_update',json.dumps(request));self.assertEqual(parsed.settings,ThreadSettings())
        del request['settings']['clearance_mm']
        with self.assertRaises(ValueError):read_request('thread_update',json.dumps(request))

    def test_thread_begin_focus_and_cancel_protocol(self):
        begin=read_request('thread_begin',json.dumps({'protocol':1,'requestId':'test','editing':False,'settings':{'mode':'coupon'}}))
        self.assertEqual(begin.settings.mode,'coupon')
        base={'protocol':1,'requestId':'test','sessionId':str(uuid.uuid4())}
        for target in ('face_a','face_b','edit_target'):
            self.assertEqual(read_request('thread_focus',json.dumps({**base,'target':target})).target,target)
        with self.assertRaises(ValueError):read_request('thread_focus',json.dumps({**base,'target':'faces'}))
        self.assertEqual(read_request('thread_cancel',json.dumps(base)).session_id,base['sessionId'])

"""Strict bridge contracts for the two newly integrated tool sessions."""
import json
import unittest
import uuid
from Partelier.partelier.palette_protocol import read_request
from Partelier.partelier.tools.mechanisms.settings import MechanismSettings
from Partelier.partelier.tools.finishing.settings import FinishingSettings


class NewToolProtocolTests(unittest.TestCase):
    tools=(('mechanism',MechanismSettings),('finishing',FinishingSettings))

    def begin(self,settings=None):
        return {'protocol':1,'requestId':'new-tool-begin','settings':{} if settings is None else settings,'editing':False}

    def active(self,cls):
        return {'protocol':1,'requestId':'new-tool-update','sessionId':str(uuid.uuid4()),'revision':4,'settings':cls().to_dict()}

    def test_begin_fills_typed_defaults_but_does_not_accept_unknown_fields(self):
        for tool,cls in self.tools:
            with self.subTest(tool=tool):
                expected=cls();expected.validate()
                parsed=read_request(tool+'_begin',json.dumps(self.begin()))
                self.assertIsInstance(parsed.settings,cls);self.assertEqual(parsed.settings.to_dict(),expected.to_dict())
                self.assertFalse(parsed.editing)
                changed=read_request(tool+'_begin',json.dumps(self.begin({'width_mm':24})))
                self.assertEqual(changed.settings.width_mm,24)
                for settings in ({'unknown':0},None,[],False):
                    raw={**self.begin(),'settings':settings}
                    with self.assertRaises(ValueError):read_request(tool+'_begin',json.dumps(raw))

    def test_active_updates_preview_and_commit_require_full_atomic_settings(self):
        for tool,cls in self.tools:
            for suffix in ('update','preview','commit'):
                with self.subTest(tool=tool,action=suffix):
                    raw=self.active(cls);parsed=read_request(tool+'_'+suffix,json.dumps(raw))
                    self.assertEqual(parsed.settings.to_dict(),raw['settings']);self.assertEqual(parsed.revision,4)
                    for settings in ({},{'width_mm':24},{**raw['settings'],'unknown':0}):
                        with self.assertRaises(ValueError):read_request(tool+'_'+suffix,json.dumps({**raw,'settings':settings}))

    def test_settings_reject_wrong_types_nonfinite_and_out_of_bounds_dimensions(self):
        for tool,cls in self.tools:
            for value in (True,None,'12',float('nan'),float('inf'),-2,10**1000):
                with self.subTest(tool=tool,value=str(value)[:20]):
                    with self.assertRaises(ValueError):read_request(tool+'_begin',json.dumps(self.begin({'width_mm':value})))
            for value in (True,2.5,0,1000):
                with self.subTest(tool=tool,count=value),self.assertRaises(ValueError):
                    read_request(tool+'_begin',json.dumps(self.begin({'count':value})))

    def test_boolean_edit_flag_and_schema_are_exact(self):
        for tool,cls in self.tools:
            for change in ({'editing':1},{'editing':'false'},{'protocol':True},{'requestId':''},{'extra':'no'}):
                with self.subTest(tool=tool,change=change),self.assertRaises(ValueError):
                    read_request(tool+'_begin',json.dumps({**self.begin(),**change}))
            for missing in ('editing','settings','requestId','protocol'):
                raw=self.begin();del raw[missing]
                with self.assertRaises(ValueError):read_request(tool+'_begin',json.dumps(raw))

    def test_revision_and_session_identity_are_strict(self):
        for tool,cls in self.tools:
            raw=self.active(cls);raw['sessionId']='caf51e65-f35b-44fc-b748-56ee3e879ae6'
            for change in ({'revision':True},{'revision':-1},{'revision':1.2},{'revision':1000000001},{'sessionId':None},{'sessionId':'old'},{'sessionId':raw['sessionId'].upper()}):
                with self.subTest(tool=tool,change=change),self.assertRaises(ValueError):
                    read_request(tool+'_update',json.dumps({**raw,**change}))

    def test_only_supported_selection_roles_are_forwarded(self):
        for tool,cls in self.tools:
            raw={'protocol':1,'requestId':'focus','sessionId':str(uuid.uuid4())}
            allowed=('edit_target',) if tool=='mechanism' else ('face','edit_target')
            for target in allowed:self.assertEqual(read_request(tool+'_focus',json.dumps({**raw,'target':target})).target,target)
            for target in ('body','face_a','outline',None,[]):
                with self.subTest(tool=tool,target=target),self.assertRaises(ValueError):read_request(tool+'_focus',json.dumps({**raw,'target':target}))

    def test_status_is_settings_free_and_cancel_reset_need_only_identity(self):
        for tool,cls in self.tools:
            base={'protocol':1,'requestId':'status'}
            self.assertIsNone(read_request(tool+'_status',json.dumps(base)).settings)
            with self.assertRaises(ValueError):read_request(tool+'_status',json.dumps({**base,'settings':cls().to_dict()}))
            for action in ('cancel','reset'):
                raw={**base,'sessionId':str(uuid.uuid4())};read_request(tool+'_'+action,json.dumps(raw))
                with self.assertRaises(ValueError):read_request(tool+'_'+action,json.dumps({**raw,'revision':0}))

    def test_malformed_and_oversized_payloads_are_refused(self):
        for tool,cls in self.tools:
            for raw in ('{','[]','null','x'*4097):
                with self.subTest(tool=tool,raw=raw[:12]),self.assertRaises(ValueError):read_request(tool+'_begin',raw)
            with self.assertRaises(ValueError):read_request(tool+'_unsupported',json.dumps(self.begin()))

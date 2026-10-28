"""Operation discovery, exact native history ownership and protocol contracts."""

import json
from types import SimpleNamespace as NS
import unittest
import uuid

from Partelier.partelier import operations as op
from Partelier.partelier.palette_protocol import read_request


class Attributes:
    def __init__(self, parent):self.parent=parent;self.values={}
    def itemByName(self,group,name):return self.values.get((group,name))
    def add(self,group,name,value):
        tag=NS(parent=self.parent,groupName=group,name=name,value=value)
        self.values[group,name]=tag;return tag


class Collection:
    def __init__(self,values=()):self.values=list(values)
    @property
    def count(self):return len(self.values)
    def item(self,index):return self.values[index]


class HistoryTests(unittest.TestCase):
    def setUp(self):
        self.identity=str(uuid.uuid4());self.deletions=[];self.entities={}
        self.features=[]
        for index,name in enumerate(('source','tools','lip','groove')):
            feature=NS(entityToken=name,name=name,isValid=True,timelineObject=NS(index=index,parentGroup=None))
            feature.attributes=Attributes(feature)
            def delete(feature=feature):
                self.deletions.append(feature.name);feature.isValid=False;self.features.remove(feature)
                self.design.timeline.count-=1;self.design.timeline.markerPosition-=1
                return True
            feature.deleteMe=delete
            self.features.append(feature);self.entities[name]=feature
        self.anchor=self.features[1]
        self.anchor.attributes.add(op.RECIPES[0][0],'record',json.dumps({'id':self.identity,'settings':{'kind':'lid'}}))
        self.design=NS(timeline=NS(count=4,markerPosition=4,timelineGroups=Collection()),rootComponent=NS())
        self.design.findAttributes=lambda g,n:[tag for f in self.entities.values() if f.isValid for (group,name),tag in f.attributes.values.items() if (g,n)==(group,name)]
        self.design.findEntityByToken=lambda token:[self.entities[token]] if token in self.entities and self.entities[token].isValid else []
        self.meta={'id':self.identity,'tool':'detail','name':'Lid lip & groove · test','features':['tools','lip','groove']}
        self.stamp()

    def stamp(self):
        self.anchor.attributes.add(op.GROUP,'operation',json.dumps(self.meta))
        for feature in self.features[1:]:feature.attributes.add(op.GROUP,'owner',json.dumps({'id':self.identity}))

    def test_listing_reads_small_recipes_without_geometry_access(self):
        self.assertEqual(op.snapshot(self.design),[{'id':self.identity,'tool':'detail','alias':'lid','name':self.meta['name'],'canDelete':True}])
        self.assertEqual(self.deletions,[])

    def test_one_owned_feature_gets_edit_delete_metadata_without_native_group(self):
        self.features=self.features[:2];self.design.timeline.count=2;self.design.timeline.markerPosition=2
        self.design.timeline.item=lambda i:NS(entity=self.features[i])
        self.anchor.attributes.values.pop((op.GROUP,'operation'))
        op.capture(self.design,self.anchor,'detail',{'kind':'lid'},1)
        record=op.resolve(self.design,self.identity)
        self.assertEqual(record['meta']['features'],['tools'])
        self.assertTrue(op.snapshot(self.design)[0]['canDelete'])
        op.delete(self.design,self.identity)
        self.assertEqual(self.deletions,['tools'])

    def test_native_suffix_deletes_in_reverse_and_keeps_sources(self):
        op.delete(self.design,self.identity)
        self.assertEqual(self.deletions,['groove','lip','tools'])
        self.assertTrue(self.entities['source'].isValid)
        self.assertFalse(op.snapshot(self.design))

    def test_unrelated_later_feature_blocks_all_deletion(self):
        self.design.timeline.count=5;self.design.timeline.markerPosition=5
        with self.assertRaisesRegex(ValueError,'later features'):op.delete(self.design,self.identity)
        self.assertEqual(self.deletions,[])

    def test_source_body_or_other_operation_cannot_become_delete_member(self):
        for wrong in ('source','missing'):
            self.meta['features']=['tools',wrong,'groove'];self.stamp()
            with self.assertRaises(ValueError):op.delete(self.design,self.identity)
            self.assertEqual(self.deletions,[])
        self.meta['features']=['tools','lip','groove'];self.stamp()
        self.entities['lip'].attributes.add(op.GROUP,'owner',json.dumps({'id':str(uuid.uuid4())}))
        with self.assertRaisesRegex(ValueError,'does not own'):op.delete(self.design,self.identity)

    def test_duplicate_references_and_rolled_timeline_are_refused(self):
        self.meta['features']=['tools','tools','groove'];self.stamp()
        with self.assertRaisesRegex(ValueError,'duplicate'):op.delete(self.design,self.identity)
        self.meta['features']=['tools','lip','groove'];self.stamp();self.design.timeline.markerPosition=3
        with self.assertRaisesRegex(ValueError,'timeline to the end'):op.delete(self.design,self.identity)
        self.assertEqual(self.deletions,[])

    def test_legacy_records_remain_visible_without_metadata_mutation(self):
        self.anchor.attributes.values.pop((op.GROUP,'operation'))
        before=dict(self.anchor.attributes.values)
        self.assertFalse(op.snapshot(self.design)[0]['canDelete'])
        self.assertEqual(before,self.anchor.attributes.values)
        with self.assertRaisesRegex(ValueError,'older operation'):op.delete(self.design,self.identity)

    def test_expands_only_groups_containing_owned_operation_recipes(self):
        own=Collection([NS(entity=self.anchor)]);own.isCollapsed=True
        component_child=Collection([NS(entity=self.entities['lip'])]);component_child.isCollapsed=True
        other=Collection([NS(entity=self.entities['source'])]);other.isCollapsed=True
        self.design.timeline.timelineGroups=Collection([own,component_child,other]);op.expand(self.design)
        self.assertFalse(own.isCollapsed);self.assertFalse(component_child.isCollapsed);self.assertTrue(other.isCollapsed)

    def test_damaged_identity_does_not_expose_an_edit_or_delete_target(self):
        for wrong in (None,'bad',True):
            with self.assertRaises(ValueError):op.resolve(self.design,wrong)
        self.anchor.attributes.add(op.GROUP,'operation',json.dumps({**self.meta,'id':str(uuid.uuid4())}))
        self.assertEqual(op.snapshot(self.design),[])


class ProtocolTests(unittest.TestCase):
    def request(self,action,**values):return read_request(action,json.dumps({'protocol':1,'requestId':'operation-test',**values}))

    def test_operation_id_is_explicit_and_typed(self):
        identity=str(uuid.uuid4())
        for action in ('operation_edit','operation_delete'):
            self.assertEqual(self.request(action,operationId=identity).operation_id,identity)
            for wrong in (None,True,'bad',identity.upper()):
                with self.assertRaises(ValueError):self.request(action,operationId=wrong)
            with self.assertRaises(ValueError):self.request(action)
            with self.assertRaises(ValueError):self.request(action,operationId=identity,body='source')
        self.request('operations_list')
        with self.assertRaises(ValueError):self.request('operations_list',operationId=identity)

    def test_all_reset_actions_are_session_scoped_without_dimension_overrides(self):
        identity=str(uuid.uuid4())
        for action in ('hinge_reset','snap_reset','pattern_reset','detail_reset'):
            self.assertEqual(self.request(action,sessionId=identity).session_id,identity)
            with self.assertRaises(ValueError):self.request(action)
            with self.assertRaises(ValueError):self.request(action,sessionId=identity,settings={})

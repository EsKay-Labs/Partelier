"""One owned extra BaseFeature/body for all flat-colour islands.

Caller owns a rollback-capable native command. Only explicitly recorded bodies
are read/updated/removed; changing output mode may remove only the last feature.
"""

import json

from . import inlay
from .store import _api, _token, _resolve, _signature, _items, _history, _healthy


TAG='flat_colour'


def _raw(anchor,group):
    tag=anchor.attributes.itemByName(group,TAG)
    if tag is None:return None
    try:
        value=json.loads(tag.value)
    except (TypeError,ValueError) as error:
        raise ValueError('The flat colour ownership record is damaged.') from error
    if (not isinstance(value,dict) or set(value)!={'version','feature','body','signature','feature_id'}
            or type(value['version']) is not int or value['version']!=1
            or not all(isinstance(value[key],str) and 0<len(value[key])<=16384
                       for key in ('feature','body','signature','feature_id'))):
        raise ValueError('The flat colour ownership record is unsupported.')
    return value


def read(design,store,record):
    value=_raw(record.anchor,store.group)
    if value is None:return None
    if value['feature_id']!=record.feature_id:
        raise ValueError('The colour body belongs to another pattern.')
    _,native=_api()
    feature=_resolve(design,value['feature']);body=_resolve(design,value['body'])
    if (native.BaseFeature.cast(feature) is None or feature.parentComponent!=design.rootComponent
            or not store._owned(feature,record.feature_id,'colour_feature')
            or not store._owned(body,record.feature_id,'colour')
            or body.parentComponent!=design.rootComponent or body.assemblyContext is not None
            or _signature(inlay.solid(body,temporary=False))!=value['signature']):
        raise ValueError('The colour body was edited outside Partelier. Preserve those edits before rebuilding.')
    if feature.timelineObject.index!=record.anchor.timelineObject.index+3:
        raise ValueError('Features were inserted inside the flat colour history.')
    owned=tuple(item for item in _items(design.rootComponent.features.baseFeatures)
                if store._owned(item,record.feature_id,'colour_feature'))
    if owned!=(feature,):raise ValueError('Flat colour history ownership is ambiguous.')
    _healthy(feature)
    with _history(design,feature,before=False):
        if _items(feature.bodies)!=(body,):
            raise ValueError('The flat colour feature has unexpected bodies.')
    return feature,body


def _save(store,record,feature,body):
    store._stamp(feature,record.feature_id,'colour_feature')
    store._stamp(body,record.feature_id,'colour')
    store._attribute(body,TAG,_token(record.anchor))
    store._attribute(record.anchor,TAG,json.dumps({'version':1,'feature':_token(feature),
        'body':_token(body),'signature':_signature(body),'feature_id':record.feature_id},separators=(',',':')))


def apply(design,store,record,desired,previous=None):
    """Create/update a constant single colour body, or remove a last owned one."""
    if desired is None:
        if previous is not None:
            feature,_=previous
            if feature.timelineObject.index!=design.timeline.count-1:
                raise ValueError('Move/remove later features before changing Flat colour to another mode.')
            if feature.deleteMe() is False:raise ValueError('Fusion could not remove the owned colour feature.')
            tag=record.anchor.attributes.itemByName(store.group,TAG)
            if tag is None or tag.deleteMe() is False:raise ValueError('Could not retire the colour ownership record.')
        return
    inlay.solid(desired,temporary=True)
    root=design.rootComponent
    if previous is None:
        # The four-feature block must remain contiguous, including conversions.
        if record.anchor.timelineObject.index+3!=design.timeline.count:
            raise ValueError('Flat colour conversion requires the pattern at the end of the timeline.')
        feature=root.features.baseFeatures.add()
        if feature is None:raise ValueError('Fusion could not allocate the colour feature.')
    else:
        feature,_=previous
    editing=False
    with _history(design,feature,before=False):
        try:
            if feature.startEdit() is False:raise ValueError('Fusion could not edit the colour feature.')
            editing=True
            if previous is None:
                if root.bRepBodies.add(desired,feature) is None:
                    raise ValueError('Fusion could not store the flat colour islands.')
            else:
                bodies=_items(feature.bodies)
                if len(bodies)!=1 or feature.updateBody(bodies[0],desired) is False:
                    raise ValueError('Fusion could not update the flat colour islands.')
            if feature.finishEdit() is False:raise ValueError('Fusion could not finish the colour feature.')
            editing=False
            bodies=_items(feature.bodies)
            if len(bodies)!=1:
                raise ValueError('Fusion split the colour islands into unexpected bodies.')
            body=inlay.solid(bodies[0],temporary=False)
            if body.lumps.count!=desired.lumps.count or not inlay.agrees(float(body.volume),float(desired.volume)):
                raise ValueError('Stored colour islands do not match the preview.')
        finally:
            if editing:feature.finishEdit()
    if previous is not None and body!=previous[1]:
        raise ValueError('Fusion replaced the colour body identity during Rebuild.')
    feature.name='Partelier flat colour'
    body.name='Partelier Pattern colour'
    body.isLightBulbOn=True
    _healthy(feature)
    _save(store,record,feature,body)


def selection_anchor(selected,group):
    """Redirect an explicitly tagged colour body selection to its pattern."""
    _,native=_api()
    body=native.BRepBody.cast(selected)
    if body is None:
        for kind in (native.BRepFace,native.BRepEdge):
            part=kind.cast(selected)
            if part is not None:body=part.body;break
    if body is None:return selected
    tag=body.attributes.itemByName(group,TAG)
    if tag is None:return selected
    design=body.parentComponent.parentDesign
    anchor=_resolve(design,tag.value)
    record_value=_raw(anchor,group)
    if record_value is None or _resolve(design,record_value['body'])!=body:
        raise ValueError('The selected colour body is not the recorded pattern output.')
    return anchor

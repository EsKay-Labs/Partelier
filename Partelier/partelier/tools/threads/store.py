"""Owned additive/cutting delta history, allowing different threads to stack.

The caller owns the native transaction. Edit is guarded at the timeline end;
there is no replacement result body, hidden backup, or copied complete shape.
"""

from ... import refresh_context
from contextlib import contextmanager
from dataclasses import dataclass,replace
import json
import uuid
from .settings import ThreadSettings
from . import fusion as a
from ..solid_pair import _api,_items,_resolve,_body,_healthy,_history,_token


GROUP='sktech_partelier_threads_61dba590'


@dataclass(frozen=True)
class Record:
    anchor: object
    settings: ThreadSettings
    recipe: dict
    targets: tuple


def _json(value):return json.dumps(value,separators=(',',':'))


def _write(entity,name,value):
    if entity.attributes.add(GROUP,name,_json(value)) is None:raise ValueError('Fusion could not save the thread ownership.')


def _parse(raw):
    if not isinstance(raw,str) or len(raw)>131072:raise ValueError('The thread record is missing or too large.')
    try:value=json.loads(raw)
    except (ValueError,TypeError) as error:raise ValueError('The thread record is damaged.') from error
    keys={'version','id','settings','sources','base','combines','tools','tool_signatures','results'}
    if not isinstance(value,dict) or set(value)!=keys or type(value['version']) is not int or value['version']!=1:
        raise ValueError('The thread record has an unsupported structure.')
    try:
        if str(uuid.UUID(value['id']))!=value['id']:raise ValueError()
    except (ValueError,TypeError,AttributeError) as error:raise ValueError('The thread identity is damaged.') from error
    settings=ThreadSettings.from_dict(value['settings']);count=0 if settings.mode=='coupon' else 2 if settings.mode=='pair' else 1
    tool_count=4 if settings.mode=='coupon' else count
    sources=value['sources']
    if (not isinstance(sources,dict) or set(sources)!={'faces','bodies'} or not isinstance(sources['faces'],list)
            or len(sources['faces'])!=count or not isinstance(sources['bodies'],list) or len(sources['bodies'])!=count
            or not all(isinstance(t,str) for t in (*sources['faces'],*sources['bodies']))
            or len(set(sources['faces']))!=count or len(set(sources['bodies']))!=count):raise ValueError('The thread sources are damaged.')
    if (not isinstance(value['combines'],list) or len(value['combines'])!=count or any(not isinstance(value[key],list) or len(value[key])!=tool_count for key in ('tools','tool_signatures','results'))):
        raise ValueError('The thread native-tool mapping is damaged.')
    tokens=[value['base'],*value['combines'],*value['tools'],*sources['faces'],*sources['bodies']]
    if any(not isinstance(t,str) or not 0<len(t)<=16384 for t in tokens):raise ValueError('The thread references are damaged.')
    if len(set(value['combines']))!=count or len(set(value['tools']))!=tool_count:raise ValueError('Thread history references are duplicated.')
    for signature in (*value['tool_signatures'],*value['results']):
        if not isinstance(signature,str) or len(signature)!=64 or any(c not in '0123456789abcdef' for c in signature):
            raise ValueError('The thread geometry signature is damaged.')
    return value,settings


def _owned(entity,identity,anchor):
    tag=entity.attributes.itemByName(GROUP,'owner')
    return tag is not None and tag.value==_json({'id':identity,'base':anchor})


def _read(design,anchor,kind=None):
    if design.timeline.markerPosition!=refresh_context.end(design):raise ValueError('Move the timeline to the end before editing a thread.')
    tag=anchor.attributes.itemByName(GROUP,'record')
    if tag is None:raise ValueError('Select a created Printed thread or its timeline feature.')
    value,settings=_parse(tag.value)
    if kind is not None and settings.mode!=kind:raise ValueError('Select a thread belonging to the current tool.')
    core,native=_api()
    if native.BaseFeature.cast(anchor) is None or _resolve(design,value['base'])!=anchor:raise ValueError('The thread BaseFeature is missing.')
    features=tuple(_resolve(design,t) for t in value['combines']);indices=[anchor.timelineObject.index]
    for feature in (anchor,*features):
        if feature.parentComponent!=design.rootComponent or not _owned(feature,value['id'],value['base']):
            raise ValueError('The thread no longer owns its native history.')
        _healthy(feature)
    indices.extend(f.timelineObject.index for f in features)
    if indices!=list(range(indices[0],indices[0]+len(indices))) or indices[-1]+1!=refresh_context.end(design):
        raise ValueError('Edit this thread at the end of the timeline. Preserve or move later features before Rebuild.')
    targets=tuple(_body(_resolve(design,t),design.rootComponent) for t in (value['tools'] if settings.mode=='coupon' else value['sources']['bodies']))
    if [json.loads(_json(a.h._body_signature(b))) for b in targets]!=value['results'] and not refresh_context.authorized(design,anchor):
        raise ValueError('The thread result was modified. Preserve those edits before Rebuild.')
    with _history(design,anchor,before=False):
        tools=_items(anchor.bodies)
        if len(tools)!=(4 if settings.mode=='coupon' else len(features)) or any(tool!=_resolve(design,token) for tool,token in zip(tools,value['tools'])):
            raise ValueError('The owned thread tools were changed outside Partelier.')
        if [json.loads(_json(a.h._body_signature(t))) for t in tools]!=value['tool_signatures']:
            raise ValueError('The thread tool geometry was modified outside Partelier.')
        for i,feature in enumerate(features):
            if not feature.timelineObject.rollTo(True):raise ValueError('Fusion could not inspect the thread Combine input.')
            target=_resolve(design,value['sources']['bodies'][i]);tool=_resolve(design,value['tools'][i])
            if (native.CombineFeature.cast(feature) is None or feature.targetBody!=target or _items(feature.toolBodies)!=(tool,)
                    or feature.operation!=(native.FeatureOperations.CutFeatureOperation)
                    or feature.isKeepToolBodies or feature.isNewComponent):
                raise ValueError('The owned thread Combine definition was changed outside Partelier.')
    return Record(anchor,settings,value,targets)


def read(design,selected,kind=None):
    from ... import operations
    operations.expand(design)
    core,native=_api();anchor=selected
    if getattr(selected,'attributes',None) is not None:
        tag=selected.attributes.itemByName(GROUP,'owner')
        if tag is not None:
            try:anchor=_resolve(design,json.loads(tag.value)['base'])
            except (ValueError,KeyError,TypeError):raise ValueError('The selected thread ownership is damaged.')
    face=native.BRepFace.cast(selected)
    if face is not None:
        creator=getattr(face,'createdByFeature',None)
        if creator is not None and creator.attributes.itemByName(GROUP,'owner') is not None:return read(design,creator,kind)
        selected=face.body
    body=native.BRepBody.cast(selected)
    if body is not None:
        matches=[]
        for base in _items(design.rootComponent.features.baseFeatures):
            tag=base.attributes.itemByName(GROUP,'record')
            if tag is None:continue
            value,settings=_parse(tag.value)
            if (kind is None or settings.mode==kind) and any(_resolve(design,t)==body for t in (value['tools'] if settings.mode=='coupon' else value['sources']['bodies'])):matches.append(base)
        if not matches:raise ValueError('The selected body has no saved thread of this type.')
        if len(matches)!=1:raise ValueError('Select the generated face or its timeline feature; this body has multiple matching threads.')
        anchor=matches[0]
    return _read(design,anchor,kind)


@contextmanager
def input_scope(design,record):
    with _history(design,record.anchor):yield


def prepare_edit(design,record,settings):
    current=_read(design,record.anchor,settings.mode)
    if settings.mode!=current.settings.mode:raise ValueError('Keep the saved thread output mode during Edit.')
    if current.recipe!=record.recipe:raise ValueError('The saved thread changed. Reopen Edit.')
    with input_scope(design,record):
        faces=tuple(_resolve(design,t) for t in record.recipe['sources']['faces'])
        prepared=a.prepare(design,faces,settings)
    return replace(prepared,record=record)


def validate(prepared):
    if prepared.record is None:
        if prepared.design.timeline.markerPosition!=prepared.design.timeline.count:raise ValueError('Move the timeline to the end before Create.')
        a.validate(prepared);return
    current=_read(prepared.design,prepared.record.anchor,prepared.settings.mode)
    if current.recipe!=prepared.record.recipe:raise ValueError('The saved thread changed. Reopen Edit.')
    with input_scope(prepared.design,prepared.record):a.validate(prepared)


def _save(design,base,prepared,features,identity,tool_tokens):
    value={'version':1,'id':identity,'settings':prepared.settings.to_dict(),'sources':prepared.tokens,
        'base':_token(base),'combines':[_token(f) for f in features],'tools':list(tool_tokens),
        'tool_signatures':[a.h._body_signature(t) for t in (prepared.results if prepared.settings.mode=='coupon' else prepared.tools)],
        'results':[a.h._body_signature(b) for b in (tuple(base.bodies) if prepared.settings.mode=='coupon' else prepared.targets)]}
    _parse(_json(value));_write(base,'record',value)
    for feature in (base,*features):_write(feature,'owner',{'id':identity,'base':value['base']})


def apply(prepared):
    validate(prepared)
    if prepared.settings.mode=='coupon':return _apply_coupon(prepared)
    design=prepared.design;core,native=_api();root=design.rootComponent
    tokens=tuple(b.entityToken for b in prepared.targets);names=tuple(b.name for b in prepared.targets)
    visible=tuple(b.isLightBulbOn for b in prepared.targets);count=root.bRepBodies.count
    record=prepared.record;features=[];editing=False;base=None
    if record is None:
        base=root.features.baseFeatures.add();identity=str(uuid.uuid4())
        base.name='Partelier · '+prepared.settings.mode.title()
        try:
            if not base.startEdit():raise ValueError('Fusion could not open thread tools.')
            editing=True
            for tool in prepared.tools:
                if root.bRepBodies.add(tool,base) is None:raise ValueError('Fusion could not persist the thread tool.')
            if not base.finishEdit():raise ValueError('Fusion could not finish thread tools.')
            editing=False;tools=_items(base.bodies);tool_tokens=tuple(t.entityToken for t in tools)
            for i,(target,tool) in enumerate(zip(prepared.targets,tools)):
                collection=core.ObjectCollection.create();collection.add(tool)
                inputs=root.features.combineFeatures.createInput(target,collection)
                inputs.operation=native.FeatureOperations.CutFeatureOperation
                inputs.isKeepToolBodies=False
                feature=root.features.combineFeatures.add(inputs)
                if feature is None:raise ValueError('Fusion could not apply the thread.')
                features.append(feature);_healthy(feature)
                feature.name='Partelier · '+prepared.settings.mode.title()+' · '+target.name
        except Exception:
            if editing:base.finishEdit()
            for feature in reversed(features):
                if feature.isValid:feature.deleteMe()
            if base is not None and base.isValid:base.deleteMe()
            raise
    else:
        base=record.anchor;identity=record.recipe['id'];features=[_resolve(design,t) for t in record.recipe['combines']]
        with _history(design,base,before=False):
            try:
                if not base.startEdit():raise ValueError('Fusion could not edit the thread tools.')
                editing=True;sources=tuple(base.sourceBodies)
                if len(sources)!=len(prepared.tools):raise ValueError('The thread tool count changed.')
                for source,tool in zip(sources,prepared.tools):
                    if not base.updateBody(source,tool):raise ValueError('Fusion could not update the thread tool.')
                if not base.finishEdit():raise ValueError('Fusion could not finish the rebuilt thread.')
                editing=False;tools=_items(base.bodies);tool_tokens=tuple(t.entityToken for t in tools)
            finally:
                if editing:base.finishEdit()
        operation=native.FeatureOperations.CutFeatureOperation
        for feature in features:
            if feature.operation!=operation:
                with _history(design,feature):feature.operation=operation
            _healthy(feature)
    if root.bRepBodies.count!=count:raise ValueError('The thread left duplicate source/result bodies.')
    for i,body in enumerate(prepared.targets):
        if _resolve(design,tokens[i])!=body or body.name!=names[i]:raise ValueError('Fusion replaced or renamed a selected body.')
        if a.h._body_signature(body)!=a.h._body_signature(prepared.results[i]):raise ValueError('The persisted thread differs from the reviewed preview.')
        body.isLightBulbOn=visible[i]
    # The tools have been consumed; keep their persistent tokens captured above,
    # and use the detached planned shapes for geometry signatures.
    _save(design,base,prepared,features,identity,tool_tokens)
    return base


def _coupon_body_name(previous,old_settings,index,new_name):
    """Refresh generated clearance labels while preserving deliberate renames."""
    if index==0:expected='Partelier · Thread coupon · male'
    else:
        clearance=old_settings.clearance_mm+(index-2)*old_settings.coupon_clearance_step_mm
        expected=f'Partelier · Thread coupon · radial clearance {clearance:g} mm'
    return new_name if previous==expected else previous


def _apply_coupon(p):
    design=p.design;root=design.rootComponent;record=p.record
    base=record.anchor if record else root.features.baseFeatures.add()
    identity=record.recipe['id'] if record else str(uuid.uuid4());editing=False
    before=tuple(record.targets) if record else ()
    names=tuple(b.name for b in before);visible=tuple(b.isLightBulbOn for b in before)
    try:
        if not base.startEdit():raise ValueError('Could not create the thread calibration set.')
        editing=True;sources=tuple(base.sourceBodies)
        if record and len(sources)!=4:raise ValueError('The saved calibration bodies changed.')
        for i,body in enumerate(p.results):
            if i<len(sources):
                if not base.updateBody(sources[i],body):raise ValueError('Could not rebuild the calibration body.')
            elif root.bRepBodies.add(body,base) is None:raise ValueError('Could not save the calibration body.')
        if not base.finishEdit():raise ValueError('Could not finish the calibration set.')
        editing=False;bodies=tuple(base.bodies)
        if len(bodies)!=4 or before and bodies!=before:raise ValueError('Calibration body identities changed.')
        for i,body in enumerate(bodies):
            new_name='Partelier · '+p.names[i]
            body.name=_coupon_body_name(names[i],record.settings,i,new_name) if names else new_name
            if visible:body.isLightBulbOn=visible[i]
            _write(body,'owner',{'id':identity,'base':base.entityToken})
        base.name='Partelier · Thread fit coupon'
        _save(design,base,p,(),identity,tuple(b.entityToken for b in bodies))
        return base
    finally:
        if editing:base.finishEdit()

"""Owned additive/cutting delta history, allowing different details to stack.

The caller owns the native transaction. Edit is guarded at the timeline end;
there is no replacement result body, hidden backup, or copied complete shape.
"""

from contextlib import contextmanager
from dataclasses import dataclass,replace
import json
import uuid
from .settings import DetailSettings
from . import fusion as a
from ..solid_pair import _api,_items,_resolve,_body,_healthy,_history,_token


GROUP='sktech_partelier_small_details_3cc4981e'


@dataclass(frozen=True)
class Record:
    anchor: object
    settings: DetailSettings
    recipe: dict
    targets: tuple


def _json(value):return json.dumps(value,separators=(',',':'))


def _write(entity,name,value):
    if entity.attributes.add(GROUP,name,_json(value)) is None:raise ValueError('Fusion could not save the detail ownership.')


def _parse(raw):
    if not isinstance(raw,str) or len(raw)>131072:raise ValueError('The detail record is missing or too large.')
    try:value=json.loads(raw)
    except (ValueError,TypeError) as error:raise ValueError('The detail record is damaged.') from error
    keys={'version','id','settings','sources','base','combines','tools','tool_signatures','results'}
    if not isinstance(value,dict) or set(value)!=keys or type(value['version']) is not int or value['version']!=1:
        raise ValueError('The detail record has an unsupported structure.')
    try:
        if str(uuid.UUID(value['id']))!=value['id']:raise ValueError()
    except (ValueError,TypeError,AttributeError) as error:raise ValueError('The detail identity is damaged.') from error
    settings=DetailSettings.from_dict(value['settings']);count=1 if settings.kind=='ribs' else 2
    sources=value['sources']
    if (not isinstance(sources,dict) or set(sources)!={'faces','bodies'} or not isinstance(sources['faces'],list)
            or len(sources['faces'])!=2 or not isinstance(sources['bodies'],list) or len(sources['bodies'])!=count
            or not all(isinstance(t,str) for t in (*sources['faces'],*sources['bodies']))
            or len(set(sources['faces']))!=2 or len(set(sources['bodies']))!=count):raise ValueError('The detail sources are damaged.')
    if any(not isinstance(value[key],list) or len(value[key])!=count for key in ('combines','tools','tool_signatures','results')):
        raise ValueError('The detail native-tool mapping is damaged.')
    tokens=[value['base'],*value['combines'],*value['tools'],*sources['faces'],*sources['bodies']]
    if any(not isinstance(t,str) or not 0<len(t)<=16384 for t in tokens):raise ValueError('The detail references are damaged.')
    for signature in (*value['tool_signatures'],*value['results']):
        if not isinstance(signature,str) or len(signature)!=64 or any(c not in '0123456789abcdef' for c in signature):
            raise ValueError('The detail geometry signature is damaged.')
    return value,settings


def _owned(entity,identity,anchor):
    tag=entity.attributes.itemByName(GROUP,'owner')
    return tag is not None and tag.value==_json({'id':identity,'base':anchor})


def _read(design,anchor,kind=None):
    if design.timeline.markerPosition!=design.timeline.count:raise ValueError('Move the timeline to the end before editing a detail.')
    tag=anchor.attributes.itemByName(GROUP,'record')
    if tag is None:raise ValueError('Select a created Small detail or its timeline feature.')
    value,settings=_parse(tag.value)
    if kind is not None and settings.kind!=kind:raise ValueError('Select a detail belonging to the current tool.')
    core,native=_api()
    if native.BaseFeature.cast(anchor) is None or _resolve(design,value['base'])!=anchor:raise ValueError('The detail BaseFeature is missing.')
    features=tuple(_resolve(design,t) for t in value['combines']);indices=[anchor.timelineObject.index]
    for feature in (anchor,*features):
        if feature.parentComponent!=design.rootComponent or not _owned(feature,value['id'],value['base']):
            raise ValueError('The detail no longer owns its native history.')
        _healthy(feature)
    indices.extend(f.timelineObject.index for f in features)
    if indices!=list(range(indices[0],indices[0]+len(indices))) or indices[-1]+1!=design.timeline.count:
        raise ValueError('Edit this detail at the end of the timeline. Preserve or move later features before Rebuild.')
    targets=tuple(_body(_resolve(design,t),design.rootComponent) for t in value['sources']['bodies'])
    if [json.loads(_json(a.h._body_signature(b))) for b in targets]!=value['results']:
        raise ValueError('The detail result was modified. Preserve those edits before Rebuild.')
    with _history(design,anchor,before=False):
        tools=_items(anchor.bodies)
        if len(tools)!=len(features) or any(tool!=_resolve(design,token) for tool,token in zip(tools,value['tools'])):
            raise ValueError('The owned detail tools were changed outside Partelier.')
        if [json.loads(_json(a.h._body_signature(t))) for t in tools]!=value['tool_signatures']:
            raise ValueError('The detail tool geometry was modified outside Partelier.')
        for i,feature in enumerate(features):
            if not feature.timelineObject.rollTo(True):raise ValueError('Fusion could not inspect the detail Combine input.')
            target=_resolve(design,value['sources']['bodies'][i]);tool=_resolve(design,value['tools'][i])
            if (native.CombineFeature.cast(feature) is None or feature.targetBody!=target or _items(feature.toolBodies)!=(tool,)
                    or feature.operation!=(native.FeatureOperations.JoinFeatureOperation if i==0 else native.FeatureOperations.CutFeatureOperation)
                    or feature.isKeepToolBodies or feature.isNewComponent):
                raise ValueError('The owned detail Combine definition was changed outside Partelier.')
    return Record(anchor,settings,value,targets)


def read(design,selected,kind):
    from ... import operations
    operations.expand(design)
    core,native=_api();anchor=selected
    if getattr(selected,'attributes',None) is not None:
        tag=selected.attributes.itemByName(GROUP,'owner')
        if tag is not None:
            try:anchor=_resolve(design,json.loads(tag.value)['base'])
            except (ValueError,KeyError,TypeError):raise ValueError('The selected detail ownership is damaged.')
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
            if settings.kind==kind and any(_resolve(design,t)==body for t in value['sources']['bodies']):matches.append(base)
        if not matches:raise ValueError('The selected body has no saved detail of this type.')
        if len(matches)!=1:raise ValueError('Select the generated face or its timeline feature; this body has multiple matching details.')
        anchor=matches[0]
    return _read(design,anchor,kind)


@contextmanager
def input_scope(design,record):
    with _history(design,record.anchor):yield


def prepare_edit(design,record,settings):
    current=_read(design,record.anchor,settings.kind)
    if current.recipe!=record.recipe:raise ValueError('The saved detail changed. Reopen Edit.')
    with input_scope(design,record):
        faces=tuple(_resolve(design,t) for t in record.recipe['sources']['faces'])
        prepared=a.prepare(design,faces,settings)
    return replace(prepared,record=record)


def validate(prepared):
    if prepared.record is None:
        if prepared.design.timeline.markerPosition!=prepared.design.timeline.count:raise ValueError('Move the timeline to the end before Create.')
        a.validate(prepared);return
    current=_read(prepared.design,prepared.record.anchor,prepared.settings.kind)
    if current.recipe!=prepared.record.recipe:raise ValueError('The saved detail changed. Reopen Edit.')
    with input_scope(prepared.design,prepared.record):a.validate(prepared)


def _save(design,base,prepared,features,identity,tool_tokens):
    value={'version':1,'id':identity,'settings':prepared.settings.to_dict(),'sources':prepared.tokens,
        'base':_token(base),'combines':[_token(f) for f in features],'tools':list(tool_tokens),
        'tool_signatures':[a.h._body_signature(t) for t in prepared.tools],
        'results':[a.h._body_signature(b) for b in prepared.targets]}
    _parse(_json(value));_write(base,'record',value)
    for feature in (base,*features):_write(feature,'owner',{'id':identity,'base':value['base']})


def apply(prepared):
    validate(prepared);design=prepared.design;core,native=_api();root=design.rootComponent
    tokens=tuple(b.entityToken for b in prepared.targets);names=tuple(b.name for b in prepared.targets)
    visible=tuple(b.isLightBulbOn for b in prepared.targets);count=root.bRepBodies.count
    record=prepared.record;features=[];editing=False;base=None
    if record is None:
        base=root.features.baseFeatures.add();identity=str(uuid.uuid4())
        base.name='Partelier · '+{'lid':'Lid lip & groove','alignment':'Alignment pins','ribs':'Ribs & gussets'}[prepared.settings.kind]
        try:
            if not base.startEdit():raise ValueError('Fusion could not open detail tools.')
            editing=True
            for tool in prepared.tools:
                if root.bRepBodies.add(tool,base) is None:raise ValueError('Fusion could not persist the detail tool.')
            if not base.finishEdit():raise ValueError('Fusion could not finish detail tools.')
            editing=False;tools=_items(base.bodies);tool_tokens=tuple(t.entityToken for t in tools)
            for i,(target,tool) in enumerate(zip(prepared.targets,tools)):
                collection=core.ObjectCollection.create();collection.add(tool)
                inputs=root.features.combineFeatures.createInput(target,collection)
                inputs.operation=native.FeatureOperations.JoinFeatureOperation if i==0 else native.FeatureOperations.CutFeatureOperation
                inputs.isKeepToolBodies=False
                feature=root.features.combineFeatures.add(inputs)
                if feature is None:raise ValueError('Fusion could not apply the detail.')
                features.append(feature);_healthy(feature)
                feature.name='Partelier · '+({'lid':('Lip','Groove'),'alignment':('Pins','Pin holes'),'ribs':('Ribs',)}[prepared.settings.kind][i])+' · '+target.name
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
                if not base.startEdit():raise ValueError('Fusion could not edit the detail tools.')
                editing=True;sources=_items(base.bodies)
                if len(sources)!=len(prepared.tools):raise ValueError('The detail tool count changed.')
                for source,tool in zip(sources,prepared.tools):
                    if not base.updateBody(source,tool):raise ValueError('Fusion could not update the detail tool.')
                if not base.finishEdit():raise ValueError('Fusion could not finish the rebuilt detail.')
                editing=False;tools=_items(base.bodies);tool_tokens=tuple(t.entityToken for t in tools)
            finally:
                if editing:base.finishEdit()
        for feature in features:_healthy(feature)
    if root.bRepBodies.count!=count:raise ValueError('The detail left duplicate source/result bodies.')
    for i,body in enumerate(prepared.targets):
        if _resolve(design,tokens[i])!=body or body.name!=names[i]:raise ValueError('Fusion replaced or renamed a selected body.')
        if a.h._body_signature(body)!=a.h._body_signature(prepared.results[i]):raise ValueError('The persisted detail differs from the reviewed preview.')
        body.isLightBulbOn=visible[i]
    # The tools have been consumed; keep their persistent tokens captured above,
    # and use the detached planned shapes for geometry signatures.
    _save(design,base,prepared,features,identity,tool_tokens)
    return base

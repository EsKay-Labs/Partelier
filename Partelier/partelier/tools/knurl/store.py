"""Owned cutting/additive delta history for cylindrical knob grips.

The caller owns the native transaction. Edit is guarded at the timeline end;
there is no replacement result body, hidden backup, or copied complete shape.
"""

from ... import refresh_context
from contextlib import contextmanager
from dataclasses import dataclass,replace
import json
import uuid
from .settings import KnurlSettings, LEGACY_FIELDS
from . import fusion as a
from ..solid_pair import _api,_items,_resolve,_body,_healthy,_history,_token


GROUP='sktech_partelier_knurling_b23c9a71'


@dataclass(frozen=True)
class Record:
    anchor: object
    settings: KnurlSettings
    recipe: dict
    targets: tuple


def _json(value):return json.dumps(value,separators=(',',':'))


def _write(entity,name,value):
    if entity.attributes.add(GROUP,name,_json(value)) is None:raise ValueError('Fusion could not save the knurling ownership.')


def _parse(raw):
    if not isinstance(raw,str) or len(raw)>131072:raise ValueError('The knurling record is missing or too large.')
    try:value=json.loads(raw)
    except (ValueError,TypeError) as error:raise ValueError('The knurling record is damaged.') from error
    keys={'version','id','settings','sources','base','combines','tools','tool_signatures','results'}
    if not isinstance(value,dict) or type(value.get('version')) is not int or value['version'] not in (1,2,3):
        raise ValueError('The knurling record has an unsupported structure.')
    if set(value)!=(keys if value['version']==1 else keys|{'operations'}):
        raise ValueError('The knurling record has an unsupported structure.')
    try:
        if str(uuid.UUID(value['id']))!=value['id']:raise ValueError()
    except (ValueError,TypeError,AttributeError) as error:raise ValueError('The knurling identity is damaged.') from error
    supplied=value['settings']
    if value['version']==1:
        if not isinstance(supplied,dict) or set(supplied)!=LEGACY_FIELDS:
            raise ValueError('Legacy knurling settings must contain exactly their six original fields.')
        settings=KnurlSettings(**supplied)
        tool_count=1
    else:
        if value['version']==2:
            expected=set(KnurlSettings().to_dict())-{'grip_fillet_mm'}
            if not isinstance(supplied,dict) or set(supplied)!=expected:raise ValueError('Legacy knurling settings must contain exactly their eleven original fields.')
            settings=KnurlSettings(**supplied)
        else:settings=KnurlSettings.from_dict(supplied)
        ops=value['operations']
        if not isinstance(ops,list) or tuple(ops) not in (('cut',),('join',),('cut','join'),('join','cut')):
            raise ValueError('The knurling native operations are damaged.')
        tool_count=len(ops)
    count=1
    sources=value['sources']
    if (not isinstance(sources,dict) or set(sources)!={'faces','bodies'} or not isinstance(sources['faces'],list)
            or len(sources['faces'])!=count or not isinstance(sources['bodies'],list) or len(sources['bodies'])!=count
            or not all(isinstance(t,str) for t in (*sources['faces'],*sources['bodies']))
            or len(set(sources['faces']))!=count or len(set(sources['bodies']))!=count):raise ValueError('The knurling sources are damaged.')
    if (not isinstance(value['combines'],list) or len(value['combines'])!=tool_count or any(not isinstance(value[key],list) or len(value[key])!=tool_count for key in ('tools','tool_signatures')) or not isinstance(value['results'],list) or len(value['results'])!=1):
        raise ValueError('The knurling native-tool mapping is damaged.')
    tokens=[value['base'],*value['combines'],*value['tools'],*sources['faces'],*sources['bodies']]
    if any(not isinstance(t,str) or not 0<len(t)<=16384 for t in tokens):raise ValueError('The knurling references are damaged.')
    if len(set(value['combines']))!=tool_count or len(set(value['tools']))!=tool_count:raise ValueError('Knurling history references are duplicated.')
    for signature in (*value['tool_signatures'],*value['results']):
        if not isinstance(signature,str) or len(signature)!=64 or any(c not in '0123456789abcdef' for c in signature):
            raise ValueError('The knurling geometry signature is damaged.')
    return value,settings


def _owned(entity,identity,anchor):
    tag=entity.attributes.itemByName(GROUP,'owner')
    return tag is not None and tag.value==_json({'id':identity,'base':anchor})


def _read(design,anchor,kind=None):
    if design.timeline.markerPosition!=refresh_context.end(design):raise ValueError('Move the timeline to the end before editing a knurling.')
    tag=anchor.attributes.itemByName(GROUP,'record')
    if tag is None:raise ValueError('Select a created Printed knurling or its timeline feature.')
    value,settings=_parse(tag.value)
    core,native=_api()
    if native.BaseFeature.cast(anchor) is None or _resolve(design,value['base'])!=anchor:raise ValueError('The knurling BaseFeature is missing.')
    features=tuple(_resolve(design,t) for t in value['combines']);indices=[anchor.timelineObject.index]
    for feature in (anchor,*features):
        if feature.parentComponent!=design.rootComponent or not _owned(feature,value['id'],value['base']):
            raise ValueError('The knurling no longer owns its native history.')
        _healthy(feature)
    indices.extend(f.timelineObject.index for f in features)
    if indices!=list(range(indices[0],indices[0]+len(indices))) or indices[-1]+1!=refresh_context.end(design):
        raise ValueError('Edit this knurling at the end of the timeline. Preserve or move later features before Rebuild.')
    targets=tuple(_body(_resolve(design,t),design.rootComponent) for t in value['sources']['bodies'])
    if [json.loads(_json(a.h._body_signature(b))) for b in targets]!=value['results'] and not refresh_context.authorized(design,anchor):
        raise ValueError('The knurling result was modified. Preserve those edits before Rebuild.')
    with _history(design,anchor,before=False):
        tools=_items(anchor.bodies)
        if len(tools)!=len(features) or any(tool!=_resolve(design,token) for tool,token in zip(tools,value['tools'])):
            raise ValueError('The owned knurling tools were changed outside Partelier.')
        if [json.loads(_json(a.h._body_signature(t))) for t in tools]!=value['tool_signatures']:
            raise ValueError('The knurling tool geometry was modified outside Partelier.')
        for i,feature in enumerate(features):
            if not feature.timelineObject.rollTo(True):raise ValueError('Fusion could not inspect the knurling Combine input.')
            target=_resolve(design,value['sources']['bodies'][0]);tool=_resolve(design,value['tools'][i])
            if (native.CombineFeature.cast(feature) is None or feature.targetBody!=target or _items(feature.toolBodies)!=(tool,)
                    or feature.operation!=_native_operation(native,_operations(value)[i])
                    or feature.isKeepToolBodies or feature.isNewComponent):
                raise ValueError('The owned knurling Combine definition was changed outside Partelier.')
    return Record(anchor,settings,value,targets)


def read(design,selected,kind=None):
    from ... import operations
    operations.expand(design)
    core,native=_api();anchor=selected
    if getattr(selected,'attributes',None) is not None:
        tag=selected.attributes.itemByName(GROUP,'owner')
        if tag is not None:
            try:anchor=_resolve(design,json.loads(tag.value)['base'])
            except (ValueError,KeyError,TypeError):raise ValueError('The selected knurling ownership is damaged.')
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
            if any(_resolve(design,t)==body for t in value['sources']['bodies']):matches.append(base)
        if not matches:raise ValueError('The selected body has no saved knurling of this type.')
        if len(matches)!=1:raise ValueError('Select the generated face or its timeline feature; this body has multiple matching knurling.')
        anchor=matches[0]
    return _read(design,anchor,kind)


@contextmanager
def input_scope(design,record):
    with _history(design,record.anchor):yield


def prepare_edit(design,record,settings):
    current=_read(design,record.anchor)
    if current.recipe!=record.recipe:raise ValueError('The saved knurling changed. Reopen Edit.')
    with input_scope(design,record):
        faces=tuple(_resolve(design,t) for t in record.recipe['sources']['faces'])
        prepared=a.prepare(design,faces,settings)
    return replace(prepared,record=record)


def validate(prepared):
    if prepared.record is None:
        if prepared.design.timeline.markerPosition!=prepared.design.timeline.count:raise ValueError('Move the timeline to the end before Create.')
        a.validate(prepared);return
    current=_read(prepared.design,prepared.record.anchor)
    if current.recipe!=prepared.record.recipe:raise ValueError('The saved knurling changed. Reopen Edit.')
    with input_scope(prepared.design,prepared.record):a.validate(prepared)


def _save(design,base,prepared,features,identity,tool_tokens):
    value={'version':3,'id':identity,'settings':prepared.settings.to_dict(),'sources':prepared.tokens,'operations':list(prepared.operations),
        'base':_token(base),'combines':[_token(f) for f in features],'tools':list(tool_tokens),
        'tool_signatures':[a.h._body_signature(t) for t in prepared.tools],
        'results':[a.h._body_signature(b) for b in prepared.targets]}
    _parse(_json(value));_write(base,'record',value)
    for feature in (base,*features):_write(feature,'owner',{'id':identity,'base':value['base']})


def _operations(recipe):
    return tuple(recipe['operations']) if recipe['version']>=2 else ('cut',)


def _native_operation(native, operation):
    if operation=='cut':return native.FeatureOperations.CutFeatureOperation
    if operation=='join':return native.FeatureOperations.JoinFeatureOperation
    raise ValueError('Unsupported knurling native operation.')


def _add_combines(root, target, tools, operations):
    core,native=_api();features=[]
    try:
        for tool,operation in zip(tools,operations):
            collection=core.ObjectCollection.create();collection.add(tool)
            inputs=root.features.combineFeatures.createInput(target,collection)
            inputs.operation=_native_operation(native,operation)
            inputs.isKeepToolBodies=False;inputs.isNewComponent=False
            feature=root.features.combineFeatures.add(inputs)
            if feature is None:raise ValueError('Fusion could not apply the knurling '+operation+'.')
            features.append(feature);_healthy(feature)
            feature.name='Partelier · Knurling · '+operation.title()+' · '+target.name
        return features
    except Exception:
        for feature in reversed(features):
            if feature.isValid:feature.deleteMe()
        raise


def _edit_tools(root, base, bodies, allow_resize):
    editing=False
    try:
        if not base.startEdit():raise ValueError('Fusion could not edit knurling tools.')
        editing=True;sources=tuple(base.sourceBodies)
        if not allow_resize and len(sources)!=len(bodies):raise ValueError('The knurling tool count changed.')
        for source in reversed(sources[len(bodies):]):
            if source.deleteMe() is False:raise ValueError('Fusion could not remove an obsolete owned knurling tool.')
        for i,body in enumerate(bodies):
            if i<len(sources):
                if not base.updateBody(sources[i],body):raise ValueError('Fusion could not update the knurling tool.')
            elif root.bRepBodies.add(body,base) is None:raise ValueError('Fusion could not add the knurling tool.')
        if not base.finishEdit():raise ValueError('Fusion could not finish the knurling tools.')
        editing=False
    finally:
        if editing:base.finishEdit()
    tools=_items(base.bodies)
    if len(tools)!=len(bodies):raise ValueError('Fusion did not retain the exact knurling tool mapping.')
    return tools


def apply(prepared):
    validate(prepared)
    if len(prepared.targets)!=1 or len(prepared.results)!=1:
        raise ValueError('Knurling must preserve exactly one source body.')
    ops=tuple(prepared.operations)
    if ops not in (('cut',),('join',),('cut','join'),('join','cut')) or len(prepared.tools)!=len(ops):
        raise ValueError('The knurling cutting/additive tools are incomplete.')
    design=prepared.design;core,native=_api();root=design.rootComponent
    target=prepared.targets[0];token=target.entityToken;name=target.name
    visible=target.isLightBulbOn;count=root.bRepBodies.count
    record=prepared.record;features=[];base=None
    if record is None:
        base=root.features.baseFeatures.add();identity=str(uuid.uuid4())
        base.name='Partelier · Knurling'
        try:
            tools=_edit_tools(root,base,prepared.tools,True)
            tool_tokens=tuple(t.entityToken for t in tools)
            features=_add_combines(root,target,tools,ops)
        except Exception:
            for feature in reversed(features):
                if feature.isValid:feature.deleteMe()
            if base is not None and base.isValid:base.deleteMe()
            raise
    else:
        base=record.anchor;identity=record.recipe['id']
        features=[_resolve(design,t) for t in record.recipe['combines']]
        if _operations(record.recipe)==ops:
            # Stable operation graph: update all tool inputs together; do not
            # create replacement target bodies or extra native history.
            with _history(design,base,before=False):
                tools=_edit_tools(root,base,prepared.tools,False)
                tool_tokens=tuple(t.entityToken for t in tools)
            for feature in features:_healthy(feature)
        else:
            # A mode/finish conversion can add or remove a Cut/Join. The exact
            # owned suffix was validated above; the caller's native command
            # rolls the complete transaction back if any following step fails.
            owned=(base,*features);groups=[]
            for feature in owned:
                group=feature.timelineObject.parentGroup
                if group is not None and group not in groups:groups.append(group)
            for group in groups:
                children=tuple(item.entity for item in _items(group))
                if any(entity not in owned for entity in children):
                    raise ValueError('The knurling shares a timeline group with user features. Separate that group before changing relief mode.')
            for group in groups:
                group.isCollapsed=True
                if group.deleteMe(False) is False:raise ValueError('Fusion could not update the knurling timeline group.')
            for feature in reversed(features):
                if feature.deleteMe() is False:raise ValueError('Fusion could not remove an obsolete owned knurling operation.')
            features=[]
            if design.timeline.markerPosition!=design.timeline.count:
                design.timeline.markerPosition=design.timeline.count
            tools=_edit_tools(root,base,prepared.tools,True)
            tool_tokens=tuple(t.entityToken for t in tools)
            target=_body(_resolve(design,token),root)
            features=_add_combines(root,target,tools,ops)
    if root.bRepBodies.count!=count:raise ValueError('The knurling left duplicate source/result bodies.')
    if _resolve(design,token)!=target or target!=prepared.targets[0] or target.name!=name:
        raise ValueError('Fusion replaced or renamed the selected body.')
    if a.h._body_signature(target)!=a.h._body_signature(prepared.results[0]):
        raise ValueError('The persisted knurling differs from the reviewed preview.')
    target.isLightBulbOn=visible
    _save(design,base,prepared,features,identity,tool_tokens)
    return base

"""One owned BaseFeature and exact independent body ownership for fan results."""

from dataclasses import dataclass
import json,uuid
from .settings import FanSettings
from . import references
from ..patterns.store import _api,_resolve,_body,_healthy
from ..hinge.fusion import _body_signature

GROUP='sktech_partelier_fans_e46bf1a9'


@dataclass(frozen=True)
class Record:
    anchor:object
    settings:object
    recipe:dict
    bodies:tuple


def _json(value):return json.dumps(value,separators=(',',':'))


def parse(raw):
    if not isinstance(raw,str) or len(raw)>131072:raise ValueError('Fan recipe is missing or too large.')
    try:value=json.loads(raw)
    except (ValueError,TypeError) as error:raise ValueError('Fan recipe is damaged.') from error
    keys={'version','tool','feature_id','base_feature','settings','references','results'}
    if not isinstance(value,dict) or set(value)!=keys or type(value['version']) is not int or value['version']!=1 or value['tool']!='fan':raise ValueError('Unsupported fan recipe.')
    try:
        if not isinstance(value['feature_id'],str) or str(uuid.UUID(value['feature_id']))!=value['feature_id']:raise ValueError()
    except (ValueError,TypeError,AttributeError):raise ValueError('Fan identity is damaged.')
    settings=FanSettings.from_dict(value['settings'])
    refs=value['references']
    if not isinstance(refs,dict) or not set(refs)<={'circle','outline'}:raise ValueError('Fan reference data is damaged.')
    results=value['results']
    count=3 if settings.output=='rotor_guard' else 2 if settings.output=='rotor_frame' else 1
    if not isinstance(results,list) or len(results)!=count:raise ValueError('Fan output mapping is damaged.')
    tokens=[value['base_feature'],*refs.values()]
    for item in results:
        if not isinstance(item,dict) or set(item)!={'body','signature'} or not isinstance(item['signature'],str) or len(item['signature'])!=64 or any(c not in '0123456789abcdef' for c in item['signature']):raise ValueError('Fan body record is damaged.')
        tokens.append(item['body'])
    if any(not isinstance(token,str) or not 0<len(token)<=16384 for token in tokens):raise ValueError('Fan body references are damaged.')
    if len({item['body'] for item in results})!=len(results):raise ValueError('Fan body references are duplicated.')
    return value,settings


def read(design,entity):
    from ... import operations
    core,native=_api();operations.expand(design)
    if design.timeline.markerPosition!=design.timeline.count:raise ValueError('Move the timeline to the end before editing a fan.')
    if getattr(entity,'attributes',None) is None:raise ValueError('Choose a saved fan feature.')
    if entity.attributes.itemByName(GROUP,'recipe') is None:
        parent=getattr(entity,'body',entity);tag=parent.attributes.itemByName(GROUP,'owner')
        if tag is None:raise ValueError('Select a Partelier fan body or its saved feature.')
        owner=json.loads(tag.value);entity=_resolve(design,owner['base'])
    tag=entity.attributes.itemByName(GROUP,'recipe')
    if tag is None:raise ValueError('Select a saved fan result.')
    recipe,settings=parse(tag.value)
    if native.BaseFeature.cast(entity) is None or _resolve(design,recipe['base_feature'])!=entity:raise ValueError('The fan BaseFeature is missing.')
    if entity.timelineObject.index!=design.timeline.count-1:raise ValueError('This fan has later features. Move/review those before rebuilding it.')
    bodies=tuple(_resolve(design,item['body']) for item in recipe['results'])
    if tuple(entity.bodies)!=bodies:raise ValueError('The fan output bodies changed outside Partelier.')
    for body,item in zip(bodies,recipe['results']):
        _body(body,design.rootComponent)
        owner=body.attributes.itemByName(GROUP,'owner')
        data=json.loads(owner.value) if owner else {}
        if set(data)!={'id','base'} or data['id']!=recipe['feature_id'] or _resolve(design,data['base'])!=entity or _body_signature(body)!=item['signature']:
            raise ValueError('A fan output was changed outside Partelier. Undo that change or create a new fan.')
    return Record(entity,settings,recipe,bodies)


def validate(prepared):
    if prepared.design!=_api()[0].Application.get().activeProduct:raise ValueError('Return to the fan design before Create.')
    _,_,signature=references.resolve(prepared.design,prepared.references,prepared.settings)
    if prepared.reference_signature and signature!=prepared.reference_signature:raise ValueError('The fan reference changed. Refresh the preview.')
    if prepared.record is not None and read(prepared.design,prepared.record.anchor).recipe!=prepared.record.recipe:raise ValueError('The saved fan changed. Reopen Edit.')


def apply(prepared):
    validate(prepared);design=prepared.design;root=design.rootComponent;editing=False
    old=read(design,prepared.record.anchor) if prepared.record else None
    base=old.anchor if old else root.features.baseFeatures.add();identity=old.recipe['feature_id'] if old else str(uuid.uuid4())
    names=[body.name for body in old.bodies] if old else []
    visible=[body.isLightBulbOn for body in old.bodies] if old else []
    try:
        if base.startEdit() is False:raise ValueError('Could not edit the fan BaseFeature.')
        editing=True;sources=tuple(base.sourceBodies)
        for i,body in enumerate(prepared.bodies):
            if i<len(sources):
                if base.updateBody(sources[i],body) is False:raise ValueError('Could not replace the owned fan geometry.')
            elif root.bRepBodies.add(body,base) is None:raise ValueError('Could not save the fan output.')
        for body in reversed(sources[len(prepared.bodies):]):
            if body.deleteMe() is False:raise ValueError('Could not remove the old optional fan output.')
        if base.finishEdit() is False:raise ValueError('Could not finish the fan operation.')
        editing=False;bodies=tuple(base.bodies)
        if len(bodies)!=len(prepared.bodies):raise ValueError('Fan output count changed unexpectedly.')
        result=[]
        for i,(body,name) in enumerate(zip(bodies,prepared.names)):
            body.name=names[i] if i<len(names) else 'Partelier · '+name
            if i<len(visible):body.isLightBulbOn=visible[i]
            if body.attributes.add(GROUP,'owner',_json({'id':identity,'base':base.entityToken})) is None:raise ValueError('Could not save fan body ownership.')
            result.append({'body':body.entityToken,'signature':_body_signature(body)})
        value={'version':1,'tool':'fan','feature_id':identity,'base_feature':base.entityToken,'settings':prepared.settings.to_dict(),
            'references':prepared.references,'results':result}
        if base.attributes.add(GROUP,'recipe',_json(value)) is None:raise ValueError('Could not save the fan dimensions.')
        base.name='Partelier · Fans & Propellers'
        return base
    finally:
        if editing:base.finishEdit()

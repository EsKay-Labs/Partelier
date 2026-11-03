"""One owned BaseFeature and exact independent body ownership for mechanism results."""

from dataclasses import dataclass
import json,uuid
from .settings import MechanismSettings

from ..patterns.store import _api,_resolve,_body,_healthy
from ..hinge.fusion import _body_signature

GROUP='sktech_partelier_mechanisms_23d8c71a'


@dataclass(frozen=True)
class Record:
    anchor:object
    settings:object
    recipe:dict
    bodies:tuple


def _json(value):return json.dumps(value,separators=(',',':'))


def parse(raw):
    if not isinstance(raw,str) or len(raw)>131072:raise ValueError('Mechanism recipe is missing or too large.')
    try:value=json.loads(raw)
    except (ValueError,TypeError) as error:raise ValueError('Mechanism recipe is damaged.') from error
    keys={'version','tool','feature_id','base_feature','settings','references','results'}
    if not isinstance(value,dict) or set(value)!=keys or type(value['version']) is not int or value['version']!=1 or value['tool']!='mechanism':raise ValueError('Unsupported mechanism recipe.')
    try:
        if not isinstance(value['feature_id'],str) or str(uuid.UUID(value['feature_id']))!=value['feature_id']:raise ValueError()
    except (ValueError,TypeError,AttributeError):raise ValueError('Mechanism identity is damaged.')
    settings=MechanismSettings.from_dict(value['settings'])
    refs=value['references']
    if not isinstance(refs,dict) or bool(refs):raise ValueError('Mechanism reference data is damaged.')
    results=value['results']
    from .planner import plan
    count=len(plan(settings).names)
    if not isinstance(results,list) or len(results)!=count:raise ValueError('Mechanism output mapping is damaged.')
    tokens=[value['base_feature'],*refs.values()]
    for item in results:
        if not isinstance(item,dict) or set(item)!={'body','signature'} or not isinstance(item['signature'],str) or len(item['signature'])!=64 or any(c not in '0123456789abcdef' for c in item['signature']):raise ValueError('Mechanism body record is damaged.')
        tokens.append(item['body'])
    if any(not isinstance(token,str) or not 0<len(token)<=16384 for token in tokens):raise ValueError('Mechanism body references are damaged.')
    if len({item['body'] for item in results})!=len(results):raise ValueError('Mechanism body references are duplicated.')
    return value,settings


def read(design,entity):
    from ... import operations
    core,native=_api();operations.expand(design)
    if design.timeline.markerPosition!=design.timeline.count:raise ValueError('Move the timeline to the end before editing a mechanism.')
    if getattr(entity,'attributes',None) is None:raise ValueError('Choose a saved mechanism feature.')
    if entity.attributes.itemByName(GROUP,'recipe') is None:
        parent=getattr(entity,'body',entity);tag=parent.attributes.itemByName(GROUP,'owner')
        if tag is None:raise ValueError('Select a Partelier mechanism body or its saved feature.')
        owner=json.loads(tag.value);entity=_resolve(design,owner['base'])
    tag=entity.attributes.itemByName(GROUP,'recipe')
    if tag is None:raise ValueError('Select a saved mechanism result.')
    recipe,settings=parse(tag.value)
    if native.BaseFeature.cast(entity) is None or _resolve(design,recipe['base_feature'])!=entity:raise ValueError('The mechanism BaseFeature is missing.')
    if entity.timelineObject.index!=design.timeline.count-1:raise ValueError('This mechanism has later features. Move/review those before rebuilding it.')
    bodies=tuple(_resolve(design,item['body']) for item in recipe['results'])
    if tuple(entity.bodies)!=bodies:raise ValueError('The mechanism output bodies changed outside Partelier.')
    for body,item in zip(bodies,recipe['results']):
        _body(body,design.rootComponent)
        owner=body.attributes.itemByName(GROUP,'owner')
        data=json.loads(owner.value) if owner else {}
        if set(data)!={'id','base'} or data['id']!=recipe['feature_id'] or _resolve(design,data['base'])!=entity or _body_signature(body)!=item['signature']:
            raise ValueError('A mechanism output was changed outside Partelier. Undo that change or create a new mechanism.')
    return Record(entity,settings,recipe,bodies)


def validate(prepared):
    if prepared.design!=_api()[0].Application.get().activeProduct:raise ValueError('Return to the mechanism design before Create.')
    if prepared.record is not None and read(prepared.design,prepared.record.anchor).recipe!=prepared.record.recipe:raise ValueError('The saved mechanism changed. Reopen Edit.')


def apply(prepared):
    validate(prepared);design=prepared.design;root=design.rootComponent;editing=False
    old=read(design,prepared.record.anchor) if prepared.record else None
    base=old.anchor if old else root.features.baseFeatures.add();identity=old.recipe['feature_id'] if old else str(uuid.uuid4())
    names=[body.name for body in old.bodies] if old else []
    visible=[body.isLightBulbOn for body in old.bodies] if old else []
    try:
        if base.startEdit() is False:raise ValueError('Could not edit the mechanism BaseFeature.')
        editing=True;sources=tuple(base.sourceBodies)
        for i,body in enumerate(prepared.bodies):
            if i<len(sources):
                if base.updateBody(sources[i],body) is False:raise ValueError('Could not replace the owned mechanism geometry.')
            elif root.bRepBodies.add(body,base) is None:raise ValueError('Could not save the mechanism output.')
        for body in reversed(sources[len(prepared.bodies):]):
            if body.deleteMe() is False:raise ValueError('Could not remove the old optional mechanism output.')
        if base.finishEdit() is False:raise ValueError('Could not finish the mechanism operation.')
        editing=False;bodies=tuple(base.bodies)
        if len(bodies)!=len(prepared.bodies):raise ValueError('Mechanism output count changed unexpectedly.')
        result=[]
        for i,(body,name) in enumerate(zip(bodies,prepared.names)):
            body.name=names[i] if i<len(names) else 'Partelier · '+name
            if i<len(visible):body.isLightBulbOn=visible[i]
            if body.attributes.add(GROUP,'owner',_json({'id':identity,'base':base.entityToken})) is None:raise ValueError('Could not save mechanism body ownership.')
            result.append({'body':body.entityToken,'signature':_body_signature(body)})
        value={'version':1,'tool':'mechanism','feature_id':identity,'base_feature':base.entityToken,'settings':prepared.settings.to_dict(),
            'references':prepared.references,'results':result}
        if base.attributes.add(GROUP,'recipe',_json(value)) is None:raise ValueError('Could not save the mechanism dimensions.')
        base.name='Partelier · '+prepared.settings.family.replace('_',' ').title()
        return base
    finally:
        if editing:base.finishEdit()

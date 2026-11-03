"""Two consumed Join tools retain the selected source identities; optional pin stays separate."""
from dataclasses import replace
import uuid
from ..solid_pair import _api,_resolve,_history,_healthy,_body
from ..hinge.fusion import _body_signature
from . import attachment
from ... import refresh_context


def read(design,anchor,recipe,settings):
    from .store import Record,GROUP,_json
    core,native=_api();meta=recipe['attachment']
    features=tuple(_resolve(design,t) for t in meta['combines'])
    indices=[f.timelineObject.index for f in (anchor,*features)]
    if indices!=list(range(indices[0],indices[0]+3)) or indices[-1]+1!=refresh_context.end(design):
        raise ValueError('Move/review later features before editing this attached mechanism.')
    for feature in (anchor,*features):
        _healthy(feature)
        owner=feature.attributes.itemByName(GROUP,'owner')
        if owner is None or owner.value!=_json({'id':recipe['feature_id'],'base':recipe['base_feature']}):
            raise ValueError('The mechanism no longer owns its native history.')
    targets=tuple(_body(_resolve(design,t),design.rootComponent) for t in meta['targets'])
    bodies=tuple(_resolve(design,item['body']) for item in recipe['results'])
    if bodies[:2]!=targets:raise ValueError('The attached target mapping changed.')
    if not refresh_context.authorized(design,anchor) and any(_body_signature(body)!=item['signature'] for body,item in zip(bodies,recipe['results'])):
        raise ValueError('An attached result was changed outside Partelier. Preserve those edits before Rebuild.')
    with _history(design,anchor,before=False):
        tools=tuple(anchor.bodies)
        if len(tools)!=len(meta['tools']) or any(tool!=_resolve(design,token) for tool,token in zip(tools,meta['tools'])):
            raise ValueError('The owned attachment tools changed.')
        if [_body_signature(t) for t in tools]!=meta['tool_signatures']:raise ValueError('The attachment tool geometry changed.')
        for i,feature in enumerate(features):
            if not feature.timelineObject.rollTo(True):raise ValueError('Could not inspect attachment history.')
            if (native.CombineFeature.cast(feature) is None or feature.targetBody!=_resolve(design,meta['targets'][i])
                    or tuple(feature.toolBodies)!=(_resolve(design,meta['tools'][i]),)
                    or feature.operation!=native.FeatureOperations.JoinFeatureOperation or feature.isKeepToolBodies or feature.isNewComponent):
                raise ValueError('A mechanism Join was changed outside Partelier.')
    return Record(anchor,settings,recipe,bodies,targets)


def prepare_edit(design,record,settings):
    from . import store
    current=store.read(design,record.anchor)
    if current.recipe!=record.recipe:raise ValueError('The saved mechanism changed. Reopen Edit.')
    if settings.output_mode!='attached' or settings.family!=record.settings.family:
        raise ValueError('Saved attached mechanisms keep their family and output mode. Create another feature to change them.')
    with _history(design,record.anchor):
        prepared=attachment.prepare(design,settings,None,record.recipe['references'])
    return replace(prepared,record=record)


def validate(prepared):
    from . import store
    if prepared.record:
        current=store.read(prepared.design,prepared.record.anchor)
        if current.recipe!=prepared.record.recipe:raise ValueError('The saved mechanism changed. Reopen Edit.')
        with _history(prepared.design,prepared.record.anchor):attachment.validate(prepared)
    else:attachment.validate(prepared)


def apply(prepared):
    from .store import GROUP,_json,parse
    validate(prepared);design=prepared.design;root=design.rootComponent;core,native=_api()
    record=prepared.record;old_count=root.bRepBodies.count;tokens=[b.entityToken for b in prepared.targets]
    names=[b.name for b in prepared.targets];visible=[b.isLightBulbOn for b in prepared.targets]
    identity=record.recipe['feature_id'] if record else str(uuid.uuid4())
    base=record.anchor if record else root.features.baseFeatures.add();features=[];editing=False
    if record is None:
        try:
            if not base.startEdit():raise ValueError('Could not open the attachment tools.')
            editing=True
            for tool in prepared.tools:
                if root.bRepBodies.add(tool,base) is None:raise ValueError('Could not persist an attachment tool.')
            if not base.finishEdit():raise ValueError('Could not finish the attachment tools.')
            editing=False;tools=tuple(base.bodies);tool_tokens=[t.entityToken for t in tools]
            for target,tool in zip(prepared.targets,tools[:2]):
                collection=core.ObjectCollection.create();collection.add(tool)
                inputs=root.features.combineFeatures.createInput(target,collection)
                inputs.operation=native.FeatureOperations.JoinFeatureOperation;inputs.isKeepToolBodies=False
                feature=root.features.combineFeatures.add(inputs)
                if feature is None:raise ValueError('Could not join the mechanism to its selected body.')
                _healthy(feature);features.append(feature);feature.name='Partelier · Mechanism attachment · '+target.name
        except Exception:
            if editing:base.finishEdit();editing=False
            for feature in reversed(features):
                if feature.isValid:feature.deleteMe()
            if base.isValid:base.deleteMe()
            raise
    else:
        features=[_resolve(design,t) for t in record.recipe['attachment']['combines']]
        with _history(design,base,before=False):
            try:
                if not base.startEdit():raise ValueError('Could not edit the attachment tools.')
                editing=True;sources=tuple(base.sourceBodies)
                if len(sources)!=len(prepared.tools):raise ValueError('The attachment tool count changed.')
                for source,tool in zip(sources,prepared.tools):
                    if not base.updateBody(source,tool):raise ValueError('Could not update an owned attachment tool.')
                if not base.finishEdit():raise ValueError('Could not finish the attached mechanism rebuild.')
                editing=False;tool_tokens=[t.entityToken for t in base.bodies]
            finally:
                if editing:base.finishEdit()
        for feature in features:_healthy(feature)
    extra=tuple(_resolve(design,t) for t in tool_tokens[2:]);results=prepared.targets+extra
    expected=old_count+(len(extra) if record is None else 0)
    if root.bRepBodies.count!=expected:raise ValueError('Attachment left unexpected duplicate bodies.')
    for i,(body,planned) in enumerate(zip(results,prepared.bodies)):
        if _body_signature(body)!=_body_signature(planned):raise ValueError('The persisted attachment differs from its reviewed preview.')
        if i<2:
            if _resolve(design,tokens[i])!=body or body.name!=names[i]:raise ValueError('Attachment replaced or renamed a source body.')
            body.isLightBulbOn=visible[i]
        elif record is None:body.name='Partelier · '+prepared.names[i]
    value={'version':2,'tool':'mechanism','feature_id':identity,'base_feature':base.entityToken,
           'settings':prepared.settings.to_dict(),'references':prepared.references,
           'results':[{'body':b.entityToken,'signature':_body_signature(b)} for b in results],
           'attachment':{'targets':tokens,'combines':[f.entityToken for f in features],'tools':tool_tokens,
                         'tool_signatures':[_body_signature(t) for t in prepared.tools]}}
    parse(_json(value))
    if base.attributes.add(GROUP,'recipe',_json(value)) is None:raise ValueError('Could not save the attached mechanism recipe.')
    for entity in (base,*features,*extra):
        if entity.attributes.add(GROUP,'owner',_json({'id':identity,'base':base.entityToken})) is None:raise ValueError('Could not save attachment ownership.')
    base.name='Partelier · '+prepared.settings.family.replace('_',' ').title()+' · Attached'
    return base

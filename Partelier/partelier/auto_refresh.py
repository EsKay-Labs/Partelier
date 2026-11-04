"""Automatic source-driven rebuilds, within one rollback-capable native command.

No timer, worker or per-frame scan. Only completed external modeling commands
queue a check. Owned geometry and native definitions must match the saved baseline.
"""
import hashlib
import importlib
import json
from . import operations, refresh_context

GROUP = 'sktech_partelier_auto_update_172cbc09'
COMMAND = 'sktech_partelier_auto_update_command_172cbc09'
EVENT = 'sktech_partelier_auto_update_event_172cbc09'

def _hash(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()

def _resolve(design, token):
    found = design.findEntityByToken(token)
    if len(found) != 1 or not found[0].isValid:
        raise ValueError('A source reference is missing or split. Reselect it in Edit.')
    return found[0]

def _tokens(value):
    if isinstance(value,dict):
        for item in value.values():yield from _tokens(item)
    elif isinstance(value,(tuple,list)):
        for item in value:yield from _tokens(item)
    elif isinstance(value,str):yield value

def _sources(design, record):
    from .tools.hinge.fusion import _body_signature
    from .tools.fans import references
    recipe=record['recipe'];values=[]
    refs=recipe.get('sources',recipe.get('references',{}))
    if record['tool']=='mechanism':refs=recipe.get('references',{})
    for token in dict.fromkeys(_tokens(refs)):
        entity=_resolve(design,token)
        body=getattr(entity,'body',None)
        if body is None and hasattr(entity,'isSolid'):body=entity
        if body is not None:values.append(_body_signature(body))
        elif hasattr(entity,'profileLoops'):values.append(references.outline(entity))
        else:raise ValueError('This reference type cannot be automatically updated.')
    return _hash(values) if values else None

def _owned(design, record, features):
    from .tools.hinge.fusion import _body_signature
    marker=design.timeline.markerPosition;values=[]
    try:
        base=record['anchor']
        if not base.timelineObject.rollTo(False):raise ValueError('Cannot inspect the owned tools.')
        values.append([_body_signature(b) for b in base.bodies])
        for feature in features[1:]:
            if not feature.timelineObject.rollTo(True):raise ValueError('Cannot inspect the owned history.')
            if hasattr(feature,'targetBody'):
                values.append([len(tuple(feature.toolBodies)),int(feature.operation),bool(feature.isKeepToolBodies),bool(feature.isNewComponent)])
            else:raise ValueError('Automatic update does not support this additional feature type.')
        values.append(record['recipe'])
        return _hash(values)
    finally:design.timeline.markerPosition=marker

def baseline(design, record, *, source_only=False):
    features=operations._members(design,record)
    indices=[f.timelineObject.index for f in features]
    if indices!=list(range(indices[0],indices[-1]+1)):
        raise ValueError('Features were inserted inside this operation.')
    marker=design.timeline.markerPosition
    try:
        if not record['anchor'].timelineObject.rollTo(True):raise ValueError('Cannot inspect the source history.')
        source=_sources(design,record)
    finally:design.timeline.markerPosition=marker
    return {'version':1,'source':source,'owned':None if source_only or source is None else _owned(design,record,features),'end':indices[-1]+1}

def capture(design, anchor, *, strict=False):
    """Enroll explicit commits best-effort; automatic batch renewal must succeed."""
    try:
        import adsk.fusion as native
        if native.Design.cast(design) is None:return
        record=next(r for r in operations.records(design) if r['anchor']==anchor)
        value=baseline(design,record)
        if anchor.attributes.add(GROUP,'baseline',json.dumps(value)) is None:raise ValueError('Cannot save update baseline.')
    except (ImportError,AttributeError):
        if strict:raise
        return # Host-independent lifecycle test doubles have no native geometry.
    except Exception as error:
        if strict:raise
        from .diagnostics import emit
        emit('auto_update.baseline_unavailable',error=str(error))

def _rebuild(design, record):
    tool=record['tool'];anchor=record['anchor']
    if tool in ('detail','finishing'):
        module=importlib.import_module('.tools.'+('details' if tool=='detail' else tool)+'.store',__package__)
        target=module.read(design,anchor,record['recipe']['settings']['kind'])
        module.apply(module.prepare_edit(design,target,target.settings))
    elif tool=='thread':
        from .tools.threads import store
        target=store.read(design,anchor)
        store.apply(store.prepare_edit(design,target,target.settings))
    elif tool=='pattern':
        from .tools.patterns import recipe as module
        target=module.read_edit_target(design,anchor)
        module.rebuild_pattern(design,target,module.prepare_edit_pattern(design,target,target.settings))
    elif tool in ('hinge','snap'):
        module=importlib.import_module('.tools.'+('snap_fit' if tool=='snap' else tool)+'.fusion',__package__)
        name='snap_fit' if tool=='snap' else 'hinge';target=module.read_edit_target(design,anchor)
        kwargs={}
        if tool=='hinge' and (target.settings.chamfer_edges or target.settings.fillet_edges):
            from .tools.hinge.native_finish import finish_native_results
            kwargs['edge_finisher']=finish_native_results
        prepared=getattr(module,'prepare_edit_'+name)(design,target,target.settings,**kwargs)
        getattr(module,'rebuild_'+name)(design,target,prepared)
    elif tool=='fan':
        from dataclasses import replace
        from .tools.fans import store,fusion,references
        target=store.read(design,anchor);settings=target.settings;refs=target.recipe['references']
        if 'circle' in refs:
            _,diameter=references.circle(_resolve(design,refs['circle']))
            settings=replace(settings,diameter_mm=diameter-2*settings.tip_gap_mm,size_preset='custom')
        placement,outline,signature=references.resolve(design,refs,settings)
        prepared=fusion.prepare(design,settings,placement,refs,outline,target,{})
        store.apply(replace(prepared,reference_signature=signature))
    elif tool=='mechanism':
        from .tools.mechanisms import store,fusion
        target=store.read(design,anchor)
        prepared=store.prepare_edit(design,target,target.settings)
        store.apply(prepared)
    else:raise ValueError('This tool does not support automatic rebuilding.')

def refresh(design):
    """Caller MUST own a native transaction: any failure rolls the whole batch back."""
    if design.timeline.markerPosition!=design.timeline.count:raise ValueError('Move the timeline to the end before automatic updating.')
    operations.expand(design);records=operations.records(design)
    records.sort(key=lambda r:r['anchor'].timelineObject.index)
    updated=[]
    for record in records:
        tag=record['anchor'].attributes.itemByName(GROUP,'baseline')
        if tag is None:continue # Old features require one deliberate Rebuild to enroll.
        saved=json.loads(tag.value)
        if set(saved)!={'version','source','owned','end'} or saved['version']!=1:raise ValueError('Update baseline is damaged.')
        if saved['source'] is None:continue
        current=baseline(design,record,source_only=True)
        if current['source']==saved['source']:continue
        current['owned']=_owned(design,record,operations._members(design,record))
        if current['owned']!=saved['owned']:raise ValueError(record['name']+': generated geometry or its definition was edited. Automatic update stopped.')
        with refresh_context.scope(design,record['anchor'],current['end']):
            _rebuild(design,record)
            capture(design,record['anchor'],strict=True)
        updated.append(record['name'])
    if updated:
        from .tools.solid_pair import _healthy
        for index in range(design.timeline.count):
            entity=design.timeline.item(index).entity
            if entity is not None and hasattr(entity,'healthState'):_healthy(entity)
    return updated

class AutomaticUpdates:
    def __init__(self,library):
        self.library=library;self.events=[];self.handlers=[];self.definition=None;self.pending=False;self.busy=False;self.message='';self.observed=None;self.failed_designs=[]

    def start(self):
        import adsk.core as core
        app=core.Application.get();ui=app.userInterface;owner=self
        if not hasattr(ui,'commandTerminated'):return
        class Execute(core.CommandEventHandler):
            def notify(self,args):
                import adsk.fusion as native
                design=native.Design.cast(app.activeProduct)
                try:
                    if not owner.enabled():raise ValueError('Automatic updates are paused. Re-enable them in Saved after resolving the conflict.')
                    names=refresh(design);owner.message=('Updated '+str(len(names))+' feature(s).') if names else ''
                except Exception as error:
                    if design not in owner.failed_designs:owner.failed_designs.append(design)
                    args.executeFailed=True;args.executeFailedMessage=str(error)
                    owner.message='Automatic update stopped: '+str(error)+' Re-enable updates in Saved after resolving the conflict.'
        class Destroy(core.CommandEventHandler):
            def notify(self,args):
                owner.busy=False;owner.handlers.clear()
                owner.observed=owner.revisions()
                owner.library._operations_changed(owner.message)
        class Created(core.CommandCreatedEventHandler):
            def notify(self,args):
                owner.busy=True;command=args.command;command.isExecutedWhenPreEmpted=False;command.isAutoExecute=True;command.isOKButtonVisible=False
                for event,handler in ((command.execute,Execute()),(command.destroy,Destroy())):event.add(handler);owner.handlers.append(handler)
        class Driver(core.CustomEventHandler):
            def notify(self,args):
                owner.pending=False
                if not owner.idle() or not owner.enabled():return
                revision=owner.revisions()
                if revision is not None and revision==owner.observed:return
                owner.definition.execute()
        class Ended(core.ApplicationCommandEventHandler):
            def notify(self,args):
                key=args.commandId.lower()
                if owner.busy or owner.pending or 'partelier' in key or any(word in key for word in ('select','orbit','pan','zoom','undo','redo','view','python','mcp')):return
                if owner.enabled():owner.pending=True;app.fireCustomEvent(EVENT)
        self.definition=ui.commandDefinitions.itemById(COMMAND) or ui.commandDefinitions.addButtonDefinition(COMMAND,'Partelier: Update dependent features','Rebuild unchanged owned features from changed sources.')
        custom=app.registerCustomEvent(EVENT)
        for event,handler in ((self.definition.commandCreated,Created()),(custom,Driver()),(ui.commandTerminated,Ended())):event.add(handler);self.events.append((event,handler))

    def revisions(self):
        import adsk.core as core,adsk.fusion as native
        design=native.Design.cast(core.Application.get().activeProduct)
        if design is None:return None
        root=design.rootComponent
        return (design,design.timeline.count,tuple((body,body.revisionId) for body in root.bRepBodies),
                tuple((sketch,sketch.revisionId) for sketch in root.sketches))

    def enabled(self):
        import adsk.core as core,adsk.fusion as native
        design=native.Design.cast(core.Application.get().activeProduct)
        if design is None or design in self.failed_designs:return False
        tag=design.rootComponent.attributes.itemByName(GROUP,'enabled')
        return tag is None or tag.value=='true'

    def reset_failure(self,design):
        self.failed_designs=[item for item in self.failed_designs if item!=design and item.isValid]
        self.observed=None
        self.message=''

    def idle(self):
        import adsk.core as core
        if self.busy or self.library._palette_closed or core.Application.get().userInterface.activeCommand not in ('','SelectCommand'):return False
        for name in ('hinge','snap','pattern','detail','fan','mechanism','finishing','thread'):
            manager=getattr(self.library,'_'+name+'_commands',None)
            if manager:
                state=manager.palette_state()
                if getattr(manager,'busy',False) or state.get('sessionId') and state.get('phase') not in ('idle','created','cancelled'):return False
        return True

    def cancel_palette(self):
        self.pending=False

    def stop(self):
        import adsk.core as core
        for event,handler in self.events:event.remove(handler)
        self.events.clear()
        if self.definition and self.definition.isValid:self.definition.deleteMe()
        if self.definition:core.Application.get().unregisterCustomEvent(EVENT)
        self.definition=None;self.pending=False

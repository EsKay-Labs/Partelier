"""Staged source-edit test against the loaded automatic-refresh service.

Call setup/change/status/verify/finish separately so native command events run.
Use setup_rollback instead of setup for a real owned-cutter conflict: the first
operation rebuilds, then the second guard refuses and the native batch rolls back.
No UI input automation and no direct calls to auto_refresh.refresh are used.
"""
import importlib,json,sys,types
from pathlib import Path

ROOT=Path(r'C:\Users\SKTech\Desktop\Programming_Projects\Apps\Fusion360\Partelier')
STATE='_partelier_auto_update_session_fixture'
COMMAND='sktech_source_fixture_change'

def run(context):
 import adsk.core as core,adsk.fusion as native
 c=context or {};stage=c.get('stage','status');app=core.Application.get();ui=app.userInterface
 modules=[(k,m) for k,m in tuple(sys.modules.items()) if k.endswith('partelier.addin')]
 if len(modules)!=1:raise ValueError('Load exactly one Partelier instance.')
 key,addin=modules[0];prefix=key.rsplit('.',1)[0];service=addin._automatic_updates
 operations=importlib.import_module(prefix+'.operations');auto=importlib.import_module(prefix+'.auto_refresh')
 def snapshot(design):
  return None if design is None else (design.timeline.count,design.timeline.markerPosition,tuple((b,b.name,b.isLightBulbOn) for b in design.rootComponent.bRepBodies))
 def save(state,result):
  state.report['stages'].append(result);folder=ROOT/'output'/'overnight';folder.mkdir(exist_ok=True,parents=True)
  (folder/('auto-update-rollback-session.json' if getattr(state,'rollback',False) else 'auto-update-session.json')).write_text(json.dumps(state.report,indent=2),encoding='utf-8');app.log(json.dumps(result));return result
 if stage in ('setup','setup_rollback'):
  if STATE in sys.modules:raise ValueError('Finish the previous automatic-update fixture first.')
  if ui.activeCommand not in ('','SelectCommand'):raise ValueError('Finish the active native command.')
  for name in ('hinge','snap','pattern','detail','fan','mechanism','finishing'):
   manager=getattr(addin,'_'+name+'_commands',None)
   if manager and (getattr(manager,'busy',False) or manager.palette_state().get('sessionId')):raise ValueError('Finish or Cancel the active Partelier session.')
  state=types.ModuleType(STATE);sys.modules[STATE]=state;state.caller=app.activeDocument;state.original=native.Design.cast(app.activeProduct)
  state.rollback=stage=='setup_rollback';state.trace=[];state.original_rebuild=None
  state.before=snapshot(state.original);state.camera=app.activeViewport.camera;state.handlers=[];state.definition=None
  state.external_done=False;state.external_terminated=False;state.external_error=None;state.report={'production_service':True,'direct_refresh_called':False,'stages':[]}
  state.doc=app.documents.add(core.DocumentTypes.FusionDesignDocumentType);state.design=native.Design.cast(app.activeProduct);root=state.design.rootComponent
  sketch=root.sketches.add(root.xYConstructionPlane);sketch.sketchCurves.sketchLines.addTwoPointRectangle(core.Point3D.create(-4,-3,0),core.Point3D.create(4,3,0))
  state.extrude=root.features.extrudeFeatures.addSimple(sketch.profiles.item(0),core.ValueInput.createByReal(.4),native.FeatureOperations.NewBodyFeatureOperation)
  state.body=state.extrude.bodies.item(0);state.body.name='Auto-update fixture plate';state.source=state.body.entityToken
  settings=importlib.import_module(prefix+'.tools.finishing.settings').FinishingSettings
  fusion=importlib.import_module(prefix+'.tools.finishing.fusion');store=importlib.import_module(prefix+'.tools.finishing.store')
  state.identities=[];state.original_tools={};state.saved_settings={}
  for kind in ('notch','arrow'):
   face=max((f for f in state.body.faces if core.Plane.cast(f.geometry) is not None and f.evaluator.getNormalAtPoint(f.pointOnFace)[1].z>.99),key=lambda f:f.area)
   s=settings(kind=kind,width_mm=12 if kind=='notch' else 8,length_mm=20,depth_mm=1 if kind=='notch' else .6)
   prepared=fusion.prepare(state.design,(face,),s);start=state.design.timeline.count;anchor=store.apply(prepared)
   operations.capture(state.design,anchor,'finishing',s.to_dict(),start)
   record=next(r for r in operations.records(state.design) if r['anchor']==anchor)
   tag=anchor.attributes.itemByName(auto.GROUP,'baseline')
   if tag is None:raise ValueError('Explicit operation creation did not enroll its source baseline.')
   state.identities.append(record['id']);state.original_tools[record['id']]=record['recipe']['tool_signatures'];state.saved_settings[record['id']]=record['recipe']['settings']
  if state.rollback:
   # Genuine native edit to the second operation's owned cutter, without
   # reenrolling its baseline. Move only 0.1 mm sideways, retaining valid cuts.
   record=operations.resolve(state.design,state.identities[1]);anchor=record['anchor']
   manager=native.TemporaryBRepManager.get();marker=state.design.timeline.markerPosition;editing=False
   try:
    assert anchor.timelineObject.rollTo(False)
    assert anchor.startEdit();editing=True
    source=tuple(anchor.sourceBodies)[0];changed=manager.copy(source)
    transform=core.Matrix3D.create();transform.translation=core.Vector3D.create(.01,0,0)
    assert manager.transform(changed,transform)
    assert anchor.updateBody(source,changed)
    assert anchor.finishEdit();editing=False
   finally:
    if editing:anchor.finishEdit()
    state.design.timeline.markerPosition=marker
   original=json.loads(anchor.attributes.itemByName(auto.GROUP,'baseline').value)
   assert auto.baseline(state.design,record)['owned']!=original['owned'],'Native cutter mutation did not trigger the ownership guard.'
   state.saved_baselines={identity:operations.resolve(state.design,identity)['anchor'].attributes.itemByName(auto.GROUP,'baseline').value for identity in state.identities}
   state.saved_recipes={identity:json.dumps(operations.resolve(state.design,identity)['recipe'],sort_keys=True) for identity in state.identities}
   state.original_rebuild=auto._rebuild
   def observe_rebuild(design,record):
    # Observation only: delegate unchanged to the actual production rebuild.
    result=state.original_rebuild(design,record)
    if design==state.design and record['id'] in state.identities:
     fresh=operations.resolve(design,record['id'])
     state.trace.append({'id':record['id'],'returned':True,'tool_changed':fresh['recipe']['tool_signatures']!=state.original_tools[record['id']]})
    return result
   state.observer=observe_rebuild;auto._rebuild=observe_rebuild
  state.native_before=snapshot(state.design);state.initial_volume=state.body.volume
  result={'stage':stage,'ok':True,'operations':len(state.identities),'history':state.design.timeline.count,'source_body_count':root.bRepBodies.count,'baseline_saved':True}
  return save(state,result)
 state=sys.modules[STATE]
 if stage=='activate':state.doc.activate();return save(state,{'stage':stage,'ok':True})
 if stage in ('change','verify') and app.activeDocument!=state.doc:raise ValueError('Activate the owned scratch document in a separate call.')
 if stage=='change':
  if service.busy or service.pending or ui.activeCommand not in ('','SelectCommand'):raise ValueError('Wait for the native command queue.')
  if addin._tool_library._palette_closed:raise ValueError('Open the Partelier palette so the production automatic-update service is enabled.')
  state.expected_height_mm=float(c.get('height_mm',6.));assert 4<state.expected_height_mm<=10
  state.external_done=False;state.external_terminated=False;state.external_error=None
  if state.definition is None:
   class Execute(core.CommandEventHandler):
    def notify(self,args):
     try:
      if app.activeDocument!=state.doc:raise ValueError('The source-edit fixture lost its document.')
      state.extrude.extentOne.distance.value=state.expected_height_mm/10
      if state.rollback:
       signature=importlib.import_module(prefix+'.tools.hinge.fusion')._body_signature
       state.after_external_signature=signature(state.body)
       state.after_external_snapshot=snapshot(state.design)
      state.external_done=True
     except Exception as error:args.executeFailed=True;args.executeFailedMessage=str(error);state.external_error=str(error)
   class Destroy(core.CommandEventHandler):
    def notify(self,args):state.external_terminated=True
   class Created(core.CommandCreatedEventHandler):
    def notify(self,args):
     command=args.command;command.isExecutedWhenPreEmpted=False;command.isAutoExecute=True;command.isOKButtonVisible=False
     for event,handler in ((command.execute,Execute()),(command.destroy,Destroy())):
      if event.add(handler) is False:raise ValueError('Could not register source-edit fixture event.')
      state.handlers.append(handler)
   state.definition=ui.commandDefinitions.itemById(COMMAND)
   if state.definition is not None:raise ValueError('Source fixture command id already exists.')
   state.definition=ui.commandDefinitions.addButtonDefinition(COMMAND,'Source fixture thickness','Change only the owned source plate thickness.')
   state.created=Created();state.definition.commandCreated.add(state.created)
  if state.definition.execute() is False:raise ValueError('Could not queue the external source edit.')
  return save(state,{'stage':stage,'queued':True,'command_id':COMMAND,'height_mm':state.expected_height_mm})
 if stage=='status':
  return save(state,{'stage':stage,'external_done':state.external_done,'external_terminated':state.external_terminated,'external_error':state.external_error,'auto_busy':service.busy,'auto_pending':service.pending,'message':service.message,'owned_document_active':app.activeDocument==state.doc})
 if stage=='verify':
  assert state.external_done and state.external_terminated and state.external_error is None
  assert not service.busy and not service.pending, 'Automatic update is still queued.'
  assert state.design.timeline.count==state.native_before[0] and state.design.timeline.markerPosition==state.native_before[1], 'Update added history or moved the timeline.'
  assert snapshot(state.design)[2]==state.native_before[2], 'Update changed body identities, names or visibility.'
  assert state.design.findEntityByToken(state.source)[0]==state.body
  assert abs(state.body.boundingBox.maxPoint.z*10-state.expected_height_mm)<1e-5
  if state.rollback:
   signature=importlib.import_module(prefix+'.tools.hinge.fusion')._body_signature
   assert state.trace==[{'id':state.identities[0],'returned':True,'tool_changed':True}], 'First production rebuild did not complete before second guard refusal: '+repr(state.trace)
   assert 'generated geometry or its definition was edited' in service.message,service.message
   assert signature(state.body)==state.after_external_signature,'Native batch failed to restore the pre-refresh solid.'
   assert snapshot(state.design)==state.after_external_snapshot,'Native batch changed history/body state.'
   assert abs(state.extrude.extentOne.distance.value*10-state.expected_height_mm)<1e-5,'Rollback undid the upstream source edit.'
   for identity in state.identities:
    record=operations.resolve(state.design,identity)
    assert json.dumps(record['recipe'],sort_keys=True)==state.saved_recipes[identity],'Recipe changes survived failed batch.'
    assert record['anchor'].attributes.itemByName(auto.GROUP,'baseline').value==state.saved_baselines[identity],'Baseline changes survived failed batch.'
   assert snapshot(state.original)==state.before,'Caller changed during failed update.'
   return save(state,{'stage':stage,'ok':True,'first_rebuild_completed':True,'first_tool_changed_before_failure':True,'second_owned_tool_conflict':True,'native_batch_rolled_back':True,'recipes_and_baselines_restored':True,'upstream_edit_preserved':True,'caller_unchanged':True,'message':service.message,'trace':state.trace})
  refreshed=[]
  for identity in state.identities:
   record=operations.resolve(state.design,identity);tag=record['anchor'].attributes.itemByName(auto.GROUP,'baseline');saved=json.loads(tag.value)
   current=auto.baseline(state.design,record,source_only=True)
   assert saved['source']==current['source'],'Saved source baseline is stale.'
   assert record['recipe']['tool_signatures']!=state.original_tools[identity], 'A cutter did not move to the changed top face.'
   assert record['recipe']['settings']==state.saved_settings[identity], 'Automatic refresh changed requested dimensions.'
   refreshed.append(record['name'])
  assert 'Updated 2 feature(s).'==service.message, service.message
  return save(state,{'stage':stage,'ok':True,'automatically_refreshed':refreshed,'history_unchanged':True,'same_source_body':True,'settings_preserved':True,'top_mm':state.expected_height_mm})
 if stage=='finish':
  if service.busy or service.pending:raise ValueError('Wait for automatic refresh before closing its fixture.')
  if state.definition and state.definition.isValid:
   state.definition.commandCreated.remove(state.created);state.definition.deleteMe()
  if state.original_rebuild is not None:
   assert auto._rebuild is state.observer,'Fixture rebuild observer was replaced.'
   auto._rebuild=state.original_rebuild;state.original_rebuild=None
  state.handlers.clear();state.doc.close(False)
  if state.caller and state.caller.isValid:state.caller.activate();app.activeViewport.camera=state.camera
  assert snapshot(state.original)==state.before,'The caller document changed.'
  result=save(state,{'stage':stage,'ok':True,'caller_unchanged':True});del sys.modules[STATE];return result
 raise ValueError('Choose setup/setup_rollback/change/status/verify/finish.')

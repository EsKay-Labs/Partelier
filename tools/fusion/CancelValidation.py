"""Exercise real modal pick cancellation through the production palette route.

One tool per invocation, two selections in a disposable empty document. No
pointer/keyboard automation and no CAD geometry generation.
"""
def run(context):
 import adsk.core as c,adsk.fusion as f
 import sys,json,uuid,traceback
 from pathlib import Path
 app=c.Application.get();ui=app.userInterface;tool=(context or {}).get('tool','knurling')
 addin=next(m for k,m in tuple(sys.modules.items()) if k.endswith('partelier.addin'))
 library=addin._tool_library;owner=getattr(addin,'_'+tool+'_commands')
 assert ui.activeCommand in ('','SelectCommand')
 for name in ('hinge','snap','pattern','detail','fan','mechanism','finishing','thread','knurling'):
  manager=getattr(addin,'_'+name+'_commands')
  library._require_idle_other_tool(manager,name)
 caller=app.activeDocument;camera=app.activeViewport.camera
 original=f.Design.cast(app.activeProduct)
 before=(original.timeline.count,original.timeline.markerPosition,tuple((b.entityToken,b.name,b.isLightBulbOn,b.volume) for b in original.rootComponent.bRepBodies)) if original else None
 selected=tuple(ui.activeSelections.item(i).entity for i in range(ui.activeSelections.count))
 callback=getattr(owner,'_state_callback',None) if tool in ('hinge','snap') else owner.callback
 was_closed=library._palette_closed
 event_id='partelier_cancel_fixture_'+uuid.uuid4().hex;event=app.registerCustomEvent(event_id)
 report={'success':False,'tool':tool,'cycles':[]};doc=None;pending=None;cycle=None
 class Cancel(c.CustomEventHandler):
  def notify(self,args):
   nonlocal pending
   identity=pending;pending=None
   if identity is None:return
   try:
    cycle['reply']=json.loads(library.handle_message(tool+'_cancel',json.dumps({'protocol':1,'requestId':'fixture-cancel','sessionId':identity})))
   except Exception:
    cycle['cancel_error']=traceback.format_exc()
    owner.cancel_palette()
 handler=Cancel();assert event.add(handler) is not False
 def state(snapshot):
  nonlocal pending
  if callback:callback(snapshot)
  if snapshot.get('sessionId') and snapshot.get('pickingTarget') and not cycle.get('armed'):
   cycle['armed']=True;cycle['session']=snapshot['sessionId'];pending=snapshot['sessionId']
   app.fireCustomEvent(event.eventId,'cancel')
 try:
  doc=app.documents.add(c.DocumentTypes.FusionDesignDocumentType);design=f.Design.cast(app.activeProduct)
  design.designType=f.DesignTypes.ParametricDesignType;ui.activeSelections.clear()
  library._palette_closed=False;owner.set_state_callback(state)
  for index in range(2):
   cycle={'index':index};report['cycles'].append(cycle)
   try:library.handle_message(tool+'_begin',json.dumps({'protocol':1,'requestId':'fixture-begin','settings':{},'editing':True}))
   except Exception as error:cycle['picker_return']=str(error)
   snapshot=owner.palette_state()
   assert cycle.get('armed') and 'reply' in cycle and cycle['reply']['ok'],cycle
   assert snapshot['phase']=='cancelled' and not snapshot.get('sessionId'),snapshot
   assert not getattr(owner,'busy',False) and not getattr(owner,'_palette_action_busy',False)
   assert design.timeline.count==0 and design.rootComponent.bRepBodies.count==0
   cycle['cancelled_unlocked_no_geometry']=True
  assert report['cycles'][0]['session']!=report['cycles'][1]['session']
  report['success']=True
 except Exception:report['error']=traceback.format_exc()
 finally:
  owner.cancel_palette();owner.set_state_callback(callback);library._palette_closed=was_closed
  event.remove(handler);app.unregisterCustomEvent(event_id)
  if doc and doc.isValid:doc.close(False)
  if caller and caller.isValid:caller.activate();app.activeViewport.camera=camera
  ui.activeSelections.clear()
  for entity in selected:
   if entity.isValid:ui.activeSelections.add(entity)
  after=(original.timeline.count,original.timeline.markerPosition,tuple((b.entityToken,b.name,b.isLightBulbOn,b.volume) for b in original.rootComponent.bRepBodies)) if original else None
  report['caller_unchanged']=before==after and app.activeDocument==caller
  path=Path('C:/Users/SKTech/Desktop/Programming_Projects/Apps/Fusion360/Partelier/output/cancel');path.mkdir(exist_ok=True)
  (path/(tool+'.json')).write_text(json.dumps(report,indent=2),encoding='utf-8')
 print(json.dumps(report))

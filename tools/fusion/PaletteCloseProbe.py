"""Native Close/Cancel check, queued outside the Fusion MCP outer transaction.

The registered Close callback is invoked programmatically; this is not manual
pointer evidence for Fusion's X button. Only the disposable document is edited.
"""

import copy
from dataclasses import replace
import importlib
import json
from pathlib import Path
import sys
import traceback
from types import ModuleType
import uuid

import adsk.core as core
import adsk.fusion as native


def _snapshot(design):
    if design is None:return None
    history=(design.timeline.count,design.timeline.markerPosition) if design.designType==native.DesignTypes.ParametricDesignType else None
    return history,[(body.entityToken,body.name,body.isLightBulbOn,round(body.volume,9)) for body in design.rootComponent.bRepBodies]


def run(context):
    context=context or {};app=core.Application.get()
    addin=next(value for key,value in tuple(sys.modules.items()) if key.endswith('partelier.addin'))
    library=addin._tool_library;manager=addin._pattern_commands
    for field in ('_hinge_commands','_snap_commands','_pattern_commands','_detail_commands'):
        state=getattr(addin,field).palette_state()
        if state.get('sessionId') and state.get('phase') not in ('idle','created','cancelled'):
            raise ValueError('Cancel the active user preview before this disposable native test.')
    if app.userInterface.activeCommand not in ('','SelectCommand'):raise ValueError('Finish the current Fusion command first.')
    package=addin.__package__;adapter=importlib.import_module(package+'.tools.patterns.fusion')
    recipe=importlib.import_module(package+'.tools.patterns.recipe');config=importlib.import_module(package+'.tools.patterns.settings')
    operations=importlib.import_module(package+'.operations')
    keeper=ModuleType('_partelier_close_probe_'+uuid.uuid4().hex);sys.modules[keeper.__name__]=keeper
    keeper.caller=app.activeDocument;keeper.original=native.Design.cast(app.activeProduct);keeper.before=_snapshot(keeper.original)
    keeper.camera=app.activeViewport.camera;keeper.old_callback=manager.callback;keeper.old_last=copy.deepcopy(manager.last)
    keeper.old_error=library._report_error;keeper.queue=manager.runner._queue;keeper.destroyed=manager.runner.destroyed
    keeper.owned=None;keeper.design=None;keeper.stage='setup';keeper.report={'version':'0.25.1','success':False,'fusion_version':app.version,'callback_invoked_programmatically':True}
    root=Path(__file__).resolve().parents[2]
    output=Path(context.get('report_path',str(root/'output/close-cancel/native.json')))
    event_id='partelier_close_check_'+uuid.uuid4().hex;keeper.event_id=event_id
    def cleanup():
        manager.runner._queue=keeper.queue;manager.runner.destroyed=keeper.destroyed;manager.callback=keeper.old_callback;library._report_error=keeper.old_error
        if manager._session:manager.cancel_palette()
        manager.last=keeper.old_last
        if keeper.owned is not None and keeper.owned.isValid:keeper.owned.close(False)
        if keeper.caller and keeper.caller.isValid:keeper.caller.activate();app.activeViewport.camera=keeper.camera
        keeper.report['caller_unchanged']=_snapshot(keeper.original)==keeper.before
        library.show()
        app.unregisterCustomEvent(event_id)
        output.parent.mkdir(parents=True,exist_ok=True);output.write_text(json.dumps(keeper.report,indent=2),encoding='utf-8')
        sys.modules.pop(keeper.__name__,None)
    def pause_html():
        library.show();library._palette.incomingFromHTML.remove(library._html_handler)
    def close_palette():
        keeper.old_html=library._html_handler;keeper.old_close=library._close_handler
        library._palette.isVisible=False
        keeper.old_close.notify(None)
        assert library._palette is None and library._palette_closed
    class Handler(core.CustomEventHandler):
        def notify(self,args):
            try:
                design=keeper.design
                if keeper.stage=='setup':
                    setup()
                elif keeper.stage=='start_preview':
                    assert app.activeDocument==keeper.owned
                    manager.begin_palette(keeper.settings.to_dict(),editing=True,selected_entity=keeper.anchor)
                    manager.callback=observed;keeper.stage='waiting'
                    session=manager._session;changed=replace(keeper.settings,pitch_mm=11)
                    manager.palette_action('pattern_preview',session.session_id,revision=1,settings_dict=changed.to_dict())
                elif keeper.stage=='abort':
                    cleanup()
                elif keeper.stage=='ready_close':
                    session=manager._session
                    assert session and session.phase=='preview' and session.preview.isValid
                    assert not keeper.body.isLightBulbOn
                    close_palette()
                    assert session.closed and session.phase=='cancelled' and manager._session is None
                    assert _snapshot(design)==keeper.saved and design.rootComponent.customGraphicsGroups.count==0
                    assert len(operations.snapshot(design))==1
                    keeper.report.update(ready_preview_removed=True,visibility_restored=True,created_feature_preserved=True)
                    pause_html()
                    from types import SimpleNamespace
                    stale=SimpleNamespace(action='pattern_begin',data='{}')
                    keeper.old_html.notify(stale);assert not json.loads(stale.returnData)['ok']
                    keeper.old_close.notify(None);assert library._palette is not None
                    keeper.report['old_page_and_close_rejected_after_reopen']=True
                    manager.callback=keeper.old_callback
                    target=recipe.read_edit_target(design,keeper.body)
                    manager.begin_palette(target.settings.to_dict(),editing=True,selected_entity=target.anchor)
                    session=manager._session;held=[]
                    manager.runner._queue=held.append
                    manager.palette_action('pattern_preview',session.session_id,revision=session.revision,settings_dict=session.settings.to_dict())
                    request=manager.runner._current;assert request is not None and not request.computed
                    def drained(value):
                        keeper.destroyed(value)
                        if keeper.stage=='wait_drained':keeper.stage='finish';app.fireCustomEvent(event_id)
                    manager.runner.destroyed=drained;keeper.stage='wait_drained'
                    close_palette();manager.runner._queue=keeper.queue
                    for information in held:manager.runner.drive(information)
                    assert request.cancelled and not request.computed and request.prepared is None
                    assert manager._session is None and _snapshot(design)==keeper.saved
                    assert design.rootComponent.customGraphicsGroups.count==0
                    keeper.report.update(queued_preview_not_computed=True,late_driver_did_not_draw=True)
                elif keeper.stage=='finish':
                    assert not manager.busy and manager._pending is None
                    assert len(operations.snapshot(design))==1 and _snapshot(design)==keeper.saved
                    keeper.report.update(success=True,tool_registered_after_close=manager._registration[0].isValid)
                    cleanup()
            except Exception:
                keeper.report['error']=traceback.format_exc();cleanup()
    def setup():
        pause_html();keeper.owned=app.documents.add(core.DocumentTypes.FusionDesignDocumentType)
        design=native.Design.cast(app.activeProduct);keeper.design=design;design.designType=native.DesignTypes.ParametricDesignType
        body= native.TemporaryBRepManager.get().createBox(core.OrientedBoundingBox3D.create(core.Point3D.create(0,0,.15),core.Vector3D.create(1,0,0),core.Vector3D.create(0,1,0),6,5,.3))
        feature=design.rootComponent.features.baseFeatures.add();assert feature.startEdit()
        design.rootComponent.bRepBodies.add(body,feature);assert feature.finishEdit();body=feature.bodies.item(0);body.name='Close test source';keeper.body=body
        face=next(face for face in body.faces if abs(face.pointOnFace.z-.3)<1e-7)
        settings=config.PatternSettings(pattern='grille_parallel',layout_mode='fill',pitch_mm=9,web_mm=2,border_mm=7)
        start=design.timeline.count;prepared=adapter.prepare_pattern(design,(face,),settings)
        anchor=recipe.create_pattern(design,prepared);operations.capture(design,anchor,'pattern',settings.to_dict(),start)
        keeper.saved=_snapshot(design)
        keeper.settings=settings;keeper.anchor=anchor
        keeper.stage='start_preview';app.fireCustomEvent(event_id)
    def observed(state):
        keeper.old_callback(state)
        if keeper.stage=='waiting':
            if state['phase']=='preview':keeper.stage='ready_close';app.fireCustomEvent(event_id)
            elif state['phase'] in ('error','cancelled'):
                keeper.report['error']='Preview ended before the Close check: '+state.get('message','')
                keeper.stage='abort';app.fireCustomEvent(event_id)
    keeper.cleanup=cleanup
    try:
        library._report_error=lambda message:keeper.report.setdefault('ui_errors',[]).append(message)
        keeper.handler=Handler();keeper.event=app.registerCustomEvent(event_id);assert keeper.event.add(keeper.handler)
        app.fireCustomEvent(event_id)
        print(json.dumps({'queued_outside_MCP_transaction':True,'report_path':str(output)}))
    except Exception:
        keeper.report['error']=traceback.format_exc();cleanup();raise

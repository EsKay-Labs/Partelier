"""Staged native command tests. Call stages separately so Fusion can dispatch events."""
import importlib, json, sys, types
from pathlib import Path

ROOT=Path(r'C:\Users\SKTech\Desktop\Programming_Projects\Apps\Fusion360\Partelier')
STATE='_partelier_overnight_session_test'


def run(context):
    import adsk.core as core
    import adsk.fusion as native
    c=context or {};stage=c.get('stage','status');tool=c.get('tool','mechanism')
    app=core.Application.get()
    loaded=[m for name,m in tuple(sys.modules.items()) if name.endswith('partelier.addin')]
    if len(loaded)!=1:raise ValueError('Load exactly one live Partelier add-in before the production session test.')
    addin=loaded[0]
    def snapshot(design):
        return (design.timeline.count,design.timeline.markerPosition,tuple((b,b.name,b.isLightBulbOn) for b in design.rootComponent.bRepBodies))
    if stage=='setup':
        if STATE in sys.modules:raise ValueError('Finish the previous owned session fixture first.')
        for name in ('_hinge_commands','_snap_commands','_pattern_commands','_detail_commands','_fan_commands','_mechanism_commands','_finishing_commands'):
            manager=getattr(addin,name,None)
            if manager and (getattr(manager,'busy',False) or manager.palette_state().get('sessionId')):raise ValueError('A Partelier session is active.')
        state=types.ModuleType(STATE);state.caller=app.activeDocument;state.original=native.Design.cast(app.activeProduct)
        state.before=snapshot(state.original) if state.original else None;state.camera=app.activeViewport.camera
        state.report={'production_managers':True,'programmatic_selections':True,'stages':[]};sys.modules[STATE]=state
        state.doc=app.documents.add(core.DocumentTypes.FusionDesignDocumentType);state.design=native.Design.cast(app.activeProduct)
        root=state.design.rootComponent;manager=native.TemporaryBRepManager.get()
        box=manager.createBox(core.OrientedBoundingBox3D.create(core.Point3D.create(0,0,.3),core.Vector3D.create(1,0,0),core.Vector3D.create(0,1,0),8,6,.6))
        base=root.features.baseFeatures.add();assert base.startEdit();root.bRepBodies.add(box,base);assert base.finishEdit()
        state.source=tuple(base.bodies)[0];state.source.name='Owned session test plate'
        state.face=next(face for face in state.source.faces if core.Plane.cast(face.geometry) and face.evaluator.getNormalAtPoint(face.pointOnFace)[1].z>.99)
        result={'stage':stage,'ok':True}
    else:
        state=sys.modules[STATE]
        manager=getattr(addin,'_'+tool+'_commands')
        if stage not in ('finish','status') and app.activeDocument!=state.doc:
            raise ValueError('Owned scratch document is not active; activate it in a separate call before starting asynchronous preview.')
        if stage in ('begin','begin_cancel'):
            assert manager._session is None and not manager.busy
            state.baseline=snapshot(state.design);state.tool=tool
            settings_module=importlib.import_module(manager.__class__.__module__.rsplit('.',1)[0]+'.settings')
            cls=getattr(settings_module,'MechanismSettings' if tool=='mechanism' else 'FinishingSettings')
            state.settings=(cls(kind='arrow') if tool=='finishing' and stage=='begin_cancel' else cls()).to_dict()
            state.face=max((face for face in state.source.faces if core.Plane.cast(face.geometry) and face.evaluator.getNormalAtPoint(face.pointOnFace)[1].z>.99),key=lambda face:face.area)
            manager.begin_palette(state.settings,selected_entity=state.face if tool=='finishing' else None)
            session=manager._session;state.session=session
            manager.palette_action(tool+'_preview',session.session_id,session.revision,state.settings)
            result={'stage':stage,'tool':tool,'queued':True,'state':manager.palette_state()}
        elif stage=='commit':
            session=state.session
            assert session.preview_current and session.phase=='preview',manager.palette_state()
            current=snapshot(state.design)
            assert current[:2]==state.baseline[:2] and tuple(x[:2] for x in current[2])==tuple(x[:2] for x in state.baseline[2]),'Preview changed native geometry/history'
            manager.palette_action(tool+'_commit',session.session_id,session.revision,state.settings)
            result={'stage':stage,'tool':tool,'queued':True}
        elif stage=='verify':
            status=manager.palette_state()
            assert status['phase']=='created',status
            assert state.design.timeline.count>state.baseline[0]
            assert state.source.isValid and state.source.name=='Owned session test plate'
            expected=len(state.baseline[2])+(2 if tool=='mechanism' else 0)
            assert state.design.rootComponent.bRepBodies.count==expected
            result={'stage':stage,'tool':tool,'ok':True,'bodies':expected,'history':state.design.timeline.count}
        elif stage=='cancel':
            session=state.session
            assert session.preview_current and session.phase=='preview',manager.palette_state()
            manager.palette_action(tool+'_cancel',session.session_id)
            assert snapshot(state.design)==state.baseline,'Cancel failed to restore native source/history'
            result={'stage':stage,'tool':tool,'ok':True,'state':manager.palette_state()}
        elif stage=='status':
            result={'stage':stage,'tool':tool,'state':manager.palette_state(),'active_owned_document':app.activeDocument==state.doc}
        elif stage=='finish':
            for name in ('_mechanism_commands','_finishing_commands'):
                owner=getattr(addin,name)
                if owner._session:owner.cancel_palette()
            state.doc.close(False)
            if state.caller and state.caller.isValid:state.caller.activate();app.activeViewport.camera=state.camera
            assert (snapshot(state.original) if state.original else None)==state.before
            result={'stage':stage,'ok':True,'caller_unchanged':True}
        else:raise ValueError('Unknown native test stage.')
    state.report['stages'].append(result)
    (ROOT/'output'/'overnight'/'production-sessions.json').write_text(json.dumps(state.report,indent=2),encoding='utf-8')
    if stage=='finish':del sys.modules[STATE]
    app.log(json.dumps(result))
    return result

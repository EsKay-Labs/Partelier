"""Real registered knurling commands, staged so Fusion dispatches events normally."""
def run(context):
    import adsk.core as c,adsk.fusion as f
    import importlib,sys,types,json,gc
    from pathlib import Path
    from dataclasses import replace
    options=context or {};stage=options.get('stage','status')
    key='_partelier_knurling_session_validation'
    app=c.Application.get()
    modules=[m for name,m in tuple(sys.modules.items()) if name.endswith('partelier.addin')]
    assert len(modules)==1
    addin=modules[0];owner=addin._knurling_commands
    package=owner.__class__.__module__.rsplit('.',1)[0]
    S=importlib.import_module(package+'.settings');T=importlib.import_module(package+'.store')
    H=importlib.import_module(package.rsplit('.',1)[0]+'.hinge.fusion')
    O=importlib.import_module(addin.__package__+'.operations')
    def snapshot(design):
        if design is None:return None
        return (design.timeline.count,design.timeline.markerPosition,
            tuple((b,b.name,b.isLightBulbOn,H._body_signature(b)) for b in design.rootComponent.bRepBodies))
    if stage=='setup':
        assert key not in sys.modules
        assert app.userInterface.activeCommand in ('','SelectCommand')
        for name in ('hinge','snap','pattern','detail','fan','mechanism','finishing','thread','knurling'):
            manager=getattr(addin,'_'+name+'_commands',None)
            assert not manager or not (getattr(manager,'busy',False) or getattr(manager,'_session',None)),'A Partelier session is active.'
        state=types.ModuleType(key);state.caller=app.activeDocument;state.original=f.Design.cast(app.activeProduct)
        state.camera=app.activeViewport.camera;state.before=snapshot(state.original)
        state.doc=app.documents.add(c.DocumentTypes.FusionDesignDocumentType)
        state.design=f.Design.cast(app.activeProduct);state.design.designType=f.DesignTypes.ParametricDesignType
        root=state.design.rootComponent;manager=f.TemporaryBRepManager.get()
        body=manager.createCylinderOrCone(c.Point3D.create(),1.2,c.Point3D.create(0,0,.8),1.2)
        base=root.features.baseFeatures.add();assert base.startEdit();root.bRepBodies.add(body,base);assert base.finishEdit()
        state.source=tuple(base.bodies)[0];state.source.name='Knurl session source'
        state.face=next(face for face in state.source.faces if c.Cylinder.cast(face.geometry))
        state.settings=S.KnurlSettings(mode='emboss',top_finish='fillet',bottom_finish='fillet')
        state.report={'success':False,'native_registered_commands':True,'programmatic_selection':True,'stages':[]}
        sys.modules[key]=state;result={'stage':stage,'ok':True}
    else:
        state=sys.modules[key]
        assert app.activeDocument==state.doc,'Return to owned fixture document before continuing.'
        if stage=='bad-preview':
            state.baseline=snapshot(state.design)
            bad=replace(state.settings,pitch_mm=2,depth_mm=3)
            owner.begin_palette(bad.to_dict(),selected_entity=state.face)
            session=owner._session
            assert session.snapshot()['selections']['surface']['selected']
            owner.palette_action('knurling_preview',session.session_id,session.revision,session.settings.to_dict())
            result={'stage':stage,'queued':True}
        elif stage=='recover':
            session=owner._session
            assert session.phase=='error' and session.snapshot()['selections']['surface']['selected'],owner.palette_state()
            assert snapshot(state.design)==state.baseline
            owner.palette_action('knurling_preview',session.session_id,session.revision+1,state.settings.to_dict())
            result={'stage':stage,'same_reference_recovered':True}
        elif stage=='begin':
            state.baseline=snapshot(state.design)
            owner.begin_palette(state.settings.to_dict(),selected_entity=state.face)
            session=owner._session;assert session is not None
            owner.palette_action('knurling_preview',session.session_id,session.revision,session.settings.to_dict())
            result={'stage':stage,'queued':True}
        elif stage=='status':
            result={'stage':stage,'state':owner.palette_state(),'busy':owner.busy}
        elif stage=='cancel':
            session=owner._session;assert session.preview_current,owner.palette_state()
            owner.palette_action('knurling_cancel',session.session_id)
            assert snapshot(state.design)==state.baseline and state.design.rootComponent.customGraphicsGroups.count==0
            result={'stage':stage,'source_and_visibility_restored':True}
        elif stage=='commit':
            session=owner._session;assert session.preview_current,owner.palette_state()
            current=snapshot(state.design)
            assert current[:2]==state.baseline[:2]
            assert tuple((x[0],x[1],x[3]) for x in current[2])==tuple((x[0],x[1],x[3]) for x in state.baseline[2])
            owner.palette_action('knurling_commit',session.session_id,session.revision,session.settings.to_dict())
            result={'stage':stage,'queued':True}
        elif stage=='verify':
            assert owner.palette_state()['phase']=='created',owner.palette_state()
            assert state.source.isValid and state.design.rootComponent.bRepBodies.count==1
            records=[r for r in O.records(state.design) if r['tool']=='knurling'];assert len(records)==1
            state.anchor=records[0]['anchor'];state.identity=records[0]['id']
            state.saved=snapshot(state.design)
            result={'stage':stage,'saved_feature':True,'same_source_body':True}
        elif stage=='edit':
            assert not owner._session and not owner.busy
            state.baseline=snapshot(state.design)
            owner.begin_palette(state.settings.to_dict(),editing=True,selected_entity=state.anchor)
            session=owner._session;settings=replace(session.settings,depth_mm=.5,mode='engrave')
            owner.palette_action('knurling_preview',session.session_id,session.revision+1,settings.to_dict())
            result={'stage':stage,'queued':True}
        elif stage=='finish':
            assert not owner._session and not owner.busy
            O.delete(state.design,state.identity)
            assert state.design.rootComponent.bRepBodies.count==1 and state.design.timeline.count==1
            assert H._body_signature(state.source)==state.before_source_signature
            result={'stage':stage,'caller_unchanged':True}
            state.report['success']=True
        else:raise ValueError('Unsupported knurling validation stage.')
    if stage=='setup':state.before_source_signature=H._body_signature(state.source)
    state.report['stages'].append(result)
    path=Path('C:/Users/SKTech/Desktop/Programming_Projects/Apps/Fusion360/Partelier/output/knurl/production-session.json')
    if stage=='finish':
        caller,camera,original,before,doc=state.caller,state.camera,state.original,state.before,state.doc
        report=state.report
        state.__dict__.clear();sys.modules.pop(key,None);gc.collect()
        doc.close(False);doc=None;gc.collect()
        if caller is not None and caller.isValid:caller.activate();app.activeViewport.camera=camera
        assert snapshot(original)==before
        path.write_text(json.dumps(report,indent=2),encoding='utf8')
    else:path.write_text(json.dumps(state.report,indent=2),encoding='utf8')
    print(json.dumps(result))

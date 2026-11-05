"""Bounded single-knob lifecycle in a disposable document per invocation."""

def _case(prefix, options):
    import adsk.core as c, adsk.fusion as f
    import importlib, time
    from dataclasses import replace
    S=importlib.import_module(prefix+'.tools.knurl.settings')
    F=importlib.import_module(prefix+'.tools.knurl.fusion')
    T=importlib.import_module(prefix+'.tools.knurl.store')
    P=importlib.import_module(prefix+'.tools.knurl.planner')
    O=importlib.import_module(prefix+'.operations')
    H=importlib.import_module(prefix+'.tools.hinge.fusion')
    app=c.Application.get();d=f.Design.cast(app.activeProduct)
    d.designType=f.DesignTypes.ParametricDesignType;root=d.rootComponent
    manager=f.TemporaryBRepManager.get()
    s=S.KnurlSettings(style=options['style'],pitch_mm=options.get('pitch_mm',6))
    radius=options.get('radius_mm',8);height=options.get('height_mm',8)
    body=manager.createCylinderOrCone(c.Point3D.create(0,0,0),radius/10,c.Point3D.create(0,0,height/10),radius/10)
    if options.get('nearby_material'):
        foot=manager.createCylinderOrCone(c.Point3D.create(0,0,-.02),(radius+1)/10,c.Point3D.create(0,0,.005),(radius+1)/10)
        post=manager.createCylinderOrCone(c.Point3D.create((radius+.05)/10,0,-.01),.0025,c.Point3D.create((radius+.05)/10,0,height/10),.0025)
        assert manager.booleanOperation(body,foot,f.BooleanTypes.UnionBooleanType)
        assert manager.booleanOperation(body,post,f.BooleanTypes.UnionBooleanType)
    if options.get('bore_radius_mm'):
        bore=manager.createCylinderOrCone(c.Point3D.create(0,0,-.1),options['bore_radius_mm']/10,c.Point3D.create(0,0,height/10+.1),options['bore_radius_mm']/10)
        assert manager.booleanOperation(body,bore,f.BooleanTypes.DifferenceBooleanType)
    base=root.features.baseFeatures.add();assert base.startEdit()
    assert root.bRepBodies.add(body,base);assert base.finishEdit()
    source=base.bodies.item(0);source.name='Knurl test source'
    face=next(face for face in source.faces if c.Cylinder.cast(face.geometry) and abs(face.geometry.radius-radius/10)<1e-8)
    baseline=(root.bRepBodies.count,d.timeline.count);signature=H._body_signature(source)
    if options.get('expect_refusal'):
        try:F.prepare(d,(face,),s)
        except ValueError as error:
            assert ('outside this cylinder' if options.get('nearby_material') else 'continuous wall') in str(error),str(error)
            assert (root.bRepBodies.count,d.timeline.count)==baseline and H._body_signature(source)==signature
            return {'checks':{('nearby_material_refused_without_mutation' if options.get('nearby_material') else 'thin_wall_refused_without_mutation'):True},'message':str(error)}
        raise AssertionError('Thin wall was accepted.')
    started=time.perf_counter();p=F.prepare(d,(face,),s)
    report={'settings':s.to_dict(),'prepare_ms':(time.perf_counter()-started)*1000,'checks':{},'timings':p.timings}
    assert (root.bRepBodies.count,d.timeline.count)==baseline
    assert p.results[0].isSolid and p.results[0].lumps.count==1 and 0<p.results[0].volume<source.volume
    report['checks']['solid_result_no_preview_history']=True
    cached=F.cache(p);group=None
    try:
        group=F.draw(cached);assert group and group.isValid
        report['triangles']=sum(m.triangle_count for m in cached.meshes)
    finally:
        if group is not None and group.isValid:group.deleteMe()
        group=None
    assert root.customGraphicsGroups.count==0 and H._body_signature(source)==signature
    report['checks']['opaque_preview_cleanup_source_unchanged']=True
    started=time.perf_counter();anchor=T.apply(p);O.capture(d,anchor,'knurling',s.to_dict(),baseline[1])
    report['create_ms']=(time.perf_counter()-started)*1000
    if options.get('image'):
        camera=app.activeViewport.camera
        camera.viewOrientation=c.ViewOrientations.IsoTopRightViewOrientation
        camera.isFitView=True;app.activeViewport.camera=camera
        app.activeViewport.refresh()
        assert app.activeViewport.saveAsImageFile(options['image'],900,700)
    record=T.read(d,anchor);history=d.timeline.count;bodies=tuple(root.bRepBodies)
    assert root.bRepBodies.count==baseline[0]
    revised=replace(s,depth_mm=.5)
    prepared=T.prepare_edit(d,record,revised);T.apply(prepared)
    O.capture(d,anchor,'knurling',revised.to_dict(),baseline[1],editing=True)
    record=T.read(d,anchor)
    assert record.settings==revised and tuple(root.bRepBodies)==bodies and d.timeline.count==history
    report['checks']['create_same_body_rebuild_same_history']=True
    O.delete(d,record.recipe['id'])
    assert (root.bRepBodies.count,d.timeline.count)==baseline and H._body_signature(source)==signature
    report['checks']['delete_restores_source']=True
    return report

def run(context):
    import adsk.core as c
    import gc,importlib.util,json,sys,traceback,uuid
    from pathlib import Path
    options=context if isinstance(context,dict) else {}
    options={'style':options.get('style','diamond'),'pitch_mm':options.get('pitch_mm',6),'radius_mm':options.get('radius_mm',8),'height_mm':options.get('height_mm',8),'image':options.get('image'),'bore_radius_mm':options.get('bore_radius_mm'),'expect_refusal':options.get('expect_refusal',False),'nearby_material':options.get('nearby_material',False)}
    root=Path('C:/Users/SKTech/Desktop/Programming_Projects/Apps/Fusion360/Partelier')
    path=root/'output/knurl'/(options['style']+'-'+str(options['radius_mm'])+'-'+str(options['height_mm'])+('-bore'+str(options['bore_radius_mm']) if options['bore_radius_mm'] else '')+('-nearby' if options['nearby_material'] else '')+'.json')
    path.parent.mkdir(parents=True,exist_ok=True)
    app=c.Application.get();caller=app.activeDocument;camera=app.activeViewport.camera;doc=None
    prefix='_partelier_knurl_validation_'+uuid.uuid4().hex
    report={'success':False,**options}
    try:
        assert app.userInterface.activeCommand in ('','SelectCommand'),'Fusion has an active command.'
        for key,module in tuple(sys.modules.items()):
            if key.endswith('partelier.addin'):
                for field in ('_hinge_commands','_snap_commands','_pattern_commands','_detail_commands','_fan_commands','_mechanism_commands','_finishing_commands','_thread_commands','_knurling_commands'):
                    manager=getattr(module,field,None)
                    assert not manager or not (getattr(manager,'_session',None) or getattr(manager,'busy',False)),'Partelier session active.'
        package=root/'Partelier/partelier'
        spec=importlib.util.spec_from_file_location(prefix,package/'__init__.py',submodule_search_locations=[str(package)])
        module=importlib.util.module_from_spec(spec);sys.modules[prefix]=module;spec.loader.exec_module(module)
        doc=app.documents.add(c.DocumentTypes.FusionDesignDocumentType)
        report.update(_case(prefix,options));report['success']=True
    except Exception:report['error']=traceback.format_exc()
    finally:
        module=manager=spec=None
        for key in tuple(sys.modules):
            if key==prefix or key.startswith(prefix+'.'):sys.modules.pop(key,None)
        gc.collect()
        if doc is not None and doc.isValid:doc.close(False)
        doc=None;gc.collect()
        if caller is not None and caller.isValid:caller.activate();app.activeViewport.camera=camera
        report['caller_restored']=app.activeDocument==caller
        path.write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report))

"""One bounded thread lifecycle in a disposable document per invocation."""

def _case(prefix,options):
    import adsk.core as c,adsk.fusion as f
    import importlib,time
    from dataclasses import replace
    S=importlib.import_module(prefix+'.tools.threads.settings')
    F=importlib.import_module(prefix+'.tools.threads.fusion')
    T=importlib.import_module(prefix+'.tools.threads.store')
    G=importlib.import_module(prefix+'.tools.threads.geometry')
    P=importlib.import_module(prefix+'.tools.threads.planner')
    O=importlib.import_module(prefix+'.operations')
    H=importlib.import_module(prefix+'.tools.hinge.fusion')
    app=c.Application.get();d=f.Design.cast(app.activeProduct)
    d.designType=f.DesignTypes.ParametricDesignType;root=d.rootComponent
    manager=f.TemporaryBRepManager.get()
    s=S.ThreadSettings(profile=options['profile'],mode=options['mode'],length_mm=options.get('length_mm',6),
        starts=options.get('starts',1),handedness=options.get('handedness','right'))
    def cylinder(radius,x=0):
        return manager.createCylinderOrCone(c.Point3D.create(x/10,0,0),radius/10,
            c.Point3D.create(x/10,0,(s.length_mm+2)/10),radius/10)
    bore=min(10.5,P.plan(s).female_minor_radius_mm-.1)
    sources=[];faces=[];base=None
    if s.mode!='coupon':
        base=root.features.baseFeatures.add();assert base.startEdit()
        if s.mode in ('external','pair'):
            sources.append(root.bRepBodies.add(cylinder(12),base))
        if s.mode in ('internal','pair'):
            x=40 if s.mode=='pair' else 0
            body=cylinder(17,x)
            assert manager.booleanOperation(body,cylinder(bore,x),f.BooleanTypes.DifferenceBooleanType)
            sources.append(root.bRepBodies.add(body,base))
        assert base.finishEdit();sources=tuple(base.bodies)
        for i,body in enumerate(sources):
            internal=s.mode=='internal' or s.mode=='pair' and i==1
            face=next(face for face in body.faces if c.Cylinder.cast(face.geometry)
                and abs(face.geometry.radius-(bore/10 if internal else 1.2))<1e-6)
            faces.append(face);body.name='Thread test source '+str(i+1)
    baseline=(root.bRepBodies.count,d.timeline.count)
    signatures=tuple(H._body_signature(b) for b in sources)
    started=time.perf_counter();p=F.prepare(d,tuple(faces),s)
    report={'settings':s.to_dict(),'prepare_ms':(time.perf_counter()-started)*1000,'checks':{}}
    assert (root.bRepBodies.count,d.timeline.count)==baseline
    assert all(b.isSolid and b.lumps.count==1 and b.volume>0 for b in p.results)
    assert len(p.results)==(4 if s.mode=='coupon' else len(sources))
    if sources:assert all(result.volume<source.volume for result,source in zip(p.results,sources))
    report['checks']['solid_results_no_preview_history']=True
    cached=F.cache(p);group=None
    try:
        group=F.draw(cached);assert group and group.isValid
        report['triangles']=sum(m.triangle_count for m in cached.meshes)
    finally:
        if group is not None and group.isValid:group.deleteMe()
        group=None
    assert root.customGraphicsGroups.count==0
    assert tuple(H._body_signature(b) for b in sources)==signatures
    report['checks']['shaded_preview_cleanup_source_unchanged']=True
    anchor=T.apply(p);O.capture(d,anchor,'thread',s.to_dict(),baseline[1])
    record=T.read(d,anchor);history=d.timeline.count
    bodies=tuple(root.bRepBodies)
    assert root.bRepBodies.count==baseline[0]+(4 if s.mode=='coupon' else 0)
    revised=replace(s,length_mm=s.length_mm-1,clearance_mm=.3)
    prepared=T.prepare_edit(d,record,revised);T.apply(prepared)
    O.capture(d,anchor,'thread',revised.to_dict(),baseline[1],editing=True)
    record=T.read(d,anchor)
    assert record.settings==revised and tuple(root.bRepBodies)==bodies and d.timeline.count==history
    report['checks']['create_same_body_rebuild_same_history']=True
    O.delete(d,record.recipe.get('id',record.recipe.get('feature_id')))
    assert (root.bRepBodies.count,d.timeline.count)==baseline
    assert tuple(H._body_signature(b) for b in sources)==signatures
    report['checks']['delete_restores_source']=True
    # A female envelope includes its matching male at the nominal assembled pose.
    male=G.build(s,internal=False);female=G.build(s,internal=True)
    expected=male.volume;intersection=manager.copy(male)
    assert manager.booleanOperation(intersection,female,f.BooleanTypes.IntersectionBooleanType)
    assert abs(intersection.volume-expected)<max(1e-7,expected*1e-5)
    report['checks']['female_contains_matching_male']=True
    return report


def run(context):
    import adsk.core as c
    import gc,importlib.util,json,sys,traceback,uuid
    from pathlib import Path
    options=context if isinstance(context,dict) else {}
    options={'profile':options.get('profile','printable_v'),'mode':options.get('mode','external'),
        'starts':options.get('starts',1),'handedness':options.get('handedness','right'),
        'length_mm':options.get('length_mm',6)}
    root=Path('C:/Users/SKTech/Desktop/Programming_Projects/Apps/Fusion360/Partelier')
    path=root/'output/threads'/('-'.join(map(str,options.values()))+'.json')
    path.parent.mkdir(parents=True,exist_ok=True)
    app=c.Application.get();caller=app.activeDocument;camera=app.activeViewport.camera;doc=None
    prefix='_partelier_thread_validation_'+uuid.uuid4().hex
    report={'success':False,**options}
    try:
        assert app.userInterface.activeCommand in ('','SelectCommand'),'Fusion has an active command.'
        for key,module in tuple(sys.modules.items()):
            if key.endswith('partelier.addin'):
                for field in ('_hinge_commands','_snap_commands','_pattern_commands','_detail_commands','_fan_commands','_mechanism_commands','_finishing_commands','_thread_commands'):
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

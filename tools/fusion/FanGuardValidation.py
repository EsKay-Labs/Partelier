"""ONE bounded guard per invocation. No multi-design thumbnails or user-doc edits.

run({'guard_type':'spokes'}) or rings/parallel/grid/honeycomb.
Optional separate run({'guard_type':'spokes','output':'rotor_guard'}).
Every child/native/graphics wrapper lives in _case and is released before close.
"""

def _case(prefix, options):
    import adsk.core as c, adsk.fusion as f
    import importlib,time
    from dataclasses import replace
    from unittest.mock import patch
    S=importlib.import_module(prefix+'.tools.fans.settings')
    F=importlib.import_module(prefix+'.tools.fans.fusion')
    T=importlib.import_module(prefix+'.tools.fans.store')
    O=importlib.import_module(prefix+'.operations')
    d=f.Design.cast(c.Application.get().activeProduct)
    d.designType=f.DesignTypes.ParametricDesignType
    root=d.rootComponent;manager=f.TemporaryBRepManager.get()
    s=replace(S.preset('axial','pc80'),output=options['output'],guard_type=options['guard_type'],root_fillet_mm=0)
    report={'checks':{},'settings':s.to_dict()};geometry_cache={}
    started=time.perf_counter()
    if s.output=='guard':
        # A guard must never build a rotor, including temporary blade lofts.
        with patch.object(F,'_blade',side_effect=AssertionError('Guard invoked blade loft')),patch.object(F,'_blower',side_effect=AssertionError('Guard invoked blower')),patch.object(F,'_bore',side_effect=AssertionError('Guard invoked shaft bore')):
            prepared=F.prepare(d,s,geometry_cache=geometry_cache)
    else:prepared=F.prepare(d,s,geometry_cache=geometry_cache)
    report['prepare_ms']=(time.perf_counter()-started)*1000
    report['timings']=dict(prepared.timings)
    expected=1 if s.output=='guard' else 3
    assert len(prepared.bodies)==expected
    assert all(b.isSolid and b.lumps.count==1 for b in prepared.bodies)
    assert root.bRepBodies.count==0 and d.timeline.count==0
    guard=prepared.bodies[-1];bounds=guard.boundingBox
    assert abs((bounds.maxPoint.x-bounds.minPoint.x)*10-s.frame_width_mm)<1e-4
    assert abs((bounds.maxPoint.y-bounds.minPoint.y)*10-s.frame_width_mm)<1e-4
    assert abs((bounds.maxPoint.z-bounds.minPoint.z)*10-s.guard_thickness_mm)<1e-4
    if s.output=='guard':assert abs(bounds.minPoint.z)<1e-7
    for x in (-s.mount_pitch_mm/2,s.mount_pitch_mm/2):
        for y in (-s.mount_pitch_mm/2,s.mount_pitch_mm/2):
            bore=F._cylinder(manager,c,s.mount_hole_mm/2-.05,bounds.minPoint.z*10-.1,bounds.maxPoint.z*10+.1,(x,y))
            probe=manager.copy(guard)
            intersects=manager.booleanOperation(probe,bore,f.BooleanTypes.IntersectionBooleanType)
            assert not intersects or not probe.isValid or not probe.isSolid or probe.volume<1e-8,'Mount hole blocked.'
    report['checks']['one_connected_guard_flat_mount_holes']=True
    cached=F.cache(prepared);group=None
    try:
        group=F.draw(cached);assert group is not None and group.isValid
        assert root.customGraphicsGroups.count==1
        for index in range(group.count):
            item=group.item(index)
            if f.CustomGraphicsMesh.cast(item):assert f.CustomGraphicsBasicMaterialColorEffect.cast(item.color) is not None,'Preview is not lit material.'
        item=None
        report['triangles']=sum(mesh.triangle_count for mesh in cached.meshes)
    finally:
        item=None
        if group is not None and group.isValid:group.deleteMe()
        group=None
    assert root.customGraphicsGroups.count==0 and root.bRepBodies.count==0 and d.timeline.count==0
    report['checks']['phong_preview_cleanup']=True
    anchor=T.apply(prepared);O.capture(d,anchor,'fan',s.to_dict(),0)
    record=T.read(d,anchor);original=record.bodies;history=d.timeline.count
    assert record.recipe['version']==4 and len(original)==expected
    revised=replace(s,guard_thickness_mm=3,guard_pitch_mm=14)
    rebuilt=F.prepare(d,revised,record=record,geometry_cache=geometry_cache)
    T.apply(rebuilt);O.capture(d,anchor,'fan',revised.to_dict(),0,editing=True)
    after=T.read(d,anchor)
    assert after.bodies==original and after.settings==revised and d.timeline.count==history
    result=after.bodies[-1].boundingBox
    assert abs((result.maxPoint.z-result.minPoint.z)*10-3)<1e-4
    report['checks']['same_body_edit_same_history']=True
    O.delete(d,after.recipe['feature_id'])
    assert root.bRepBodies.count==0 and d.timeline.count==0 and root.customGraphicsGroups.count==0
    report['checks']['owned_delete']=True
    geometry_cache.clear()
    return report


def run(context):
    import adsk.core as c
    import gc,importlib.util,json,sys,traceback,uuid
    from pathlib import Path
    options=context if isinstance(context,dict) else {}
    kind=options.get('guard_type','spokes');output=options.get('output','guard')
    if kind not in ('spokes','rings','parallel','grid','honeycomb') or output not in ('guard','rotor_guard'):
        raise ValueError('Choose exactly one supported guard type and output.')
    options={'guard_type':kind,'output':output}
    root=Path('C:/Users/SKTech/Desktop/Programming_Projects/Apps/Fusion360/Partelier')
    path=root/'output/guards'/((kind if output=='guard' else 'combo-'+kind)+'.json')
    path.parent.mkdir(parents=True,exist_ok=True)
    app=c.Application.get();caller=app.activeDocument;camera=app.activeViewport.camera;doc=None
    prefix='_partelier_guard_validation_'+uuid.uuid4().hex
    report={'success':False,**options}
    try:
        assert app.userInterface.activeCommand in ('','SelectCommand'),'Fusion has an active command.'
        for key,module in tuple(sys.modules.items()):
            if key.endswith('partelier.addin'):
                for field in ('_hinge_commands','_snap_commands','_pattern_commands','_detail_commands','_fan_commands','_mechanism_commands','_finishing_commands'):
                    manager=getattr(module,field,None)
                    assert not manager or not (getattr(manager,'_session',None) or getattr(manager,'busy',False)),'Partelier session active.'
        package=root/'Partelier/partelier'
        spec=importlib.util.spec_from_file_location(prefix,package/'__init__.py',submodule_search_locations=[str(package)])
        module=importlib.util.module_from_spec(spec);sys.modules[prefix]=module;spec.loader.exec_module(module)
        doc=app.documents.add(c.DocumentTypes.FusionDesignDocumentType)
        report.update(_case(prefix,options));report['success']=True
    except Exception:report['error']=traceback.format_exc()
    finally:
        # _case frame has returned/unwound. Clear imported callbacks/caches before
        # closing: no graphics entities, BReps, faces or mesh wrappers survive.
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

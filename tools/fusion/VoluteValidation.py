"""Isolated volute fixture: detached geometry, openings, ownership and editing."""
def run(context):
    import adsk.core as c,adsk.fusion as f
    import importlib,importlib.util,json,sys,time,traceback,uuid
    from pathlib import Path
    from dataclasses import replace
    root=Path('C:/Users/SKTech/Desktop/Programming_Projects/Apps/Fusion360/Partelier')
    app=c.Application.get();caller=app.activeDocument;camera=app.activeViewport.camera;doc=None
    prefix='_partelier_volute_'+uuid.uuid4().hex;report={'success':False,'checks':{}}
    path=root/'output/fans/volute-validation.json';path.parent.mkdir(parents=True,exist_ok=True)
    try:
        assert app.userInterface.activeCommand in ('','SelectCommand')
        for key,module in tuple(sys.modules.items()):
            if key.endswith('partelier.addin'):
                for field in ('_hinge_commands','_snap_commands','_pattern_commands','_detail_commands','_fan_commands','_mechanism_commands','_finishing_commands'):
                    manager=getattr(module,field,None)
                    assert not manager or not (getattr(manager,'_session',None) or getattr(manager,'busy',False)), 'Partelier session is active.'
        package=root/'Partelier/partelier';spec=importlib.util.spec_from_file_location(prefix,package/'__init__.py',submodule_search_locations=[str(package)])
        module=importlib.util.module_from_spec(spec);sys.modules[prefix]=module;spec.loader.exec_module(module)
        S=importlib.import_module(prefix+'.tools.fans.settings');F=importlib.import_module(prefix+'.tools.fans.fusion')
        T=importlib.import_module(prefix+'.tools.fans.store');V=importlib.import_module(prefix+'.tools.fans.volute');O=importlib.import_module(prefix+'.operations')
        doc=app.documents.add(c.DocumentTypes.FusionDesignDocumentType);d=f.Design.cast(app.activeProduct);d.designType=f.DesignTypes.ParametricDesignType
        manager=f.TemporaryBRepManager.get();cache={};s=replace(S.preset('blower','pc60'),output='blower_housing');started=time.perf_counter()
        prepared=F.prepare(d,s,geometry_cache=cache);report['prepare_ms']=(time.perf_counter()-started)*1000;report['timings']=prepared.timings
        assert len(prepared.bodies)==3 and all(b.isSolid and b.lumps.count==1 for b in prepared.bodies)
        assert d.rootComponent.bRepBodies.count==0 and d.timeline.count==0
        def empty_intersection(one,two):
            probe=manager.copy(one);ok=manager.booleanOperation(probe,two,f.BooleanTypes.IntersectionBooleanType)
            assert not ok or not probe.isValid or not probe.isSolid or probe.volume<1e-8,'Unexpected material overlap.'
        for i in range(3):
            for j in range(i):empty_intersection(prepared.bodies[i],prepared.bodies[j])
        p=V.plan(s,prepared.plan.z_min_mm,prepared.plan.z_max_mm);rotor,housing,lid=prepared.bodies
        empty_intersection(lid,F._cylinder(manager,c,p.inlet_radius-.05,p.lid_low-.1,p.lid_high+.1))
        empty_intersection(housing,F._cylinder(manager,c,s.volute_motor_mm/2-.05,p.floor_low-.1,p.cavity_low+.1))
        outlet=F._box(manager,c,p.exit_x-p.throat_x-.2,.4,p.cavity_high-p.cavity_low-.2,((p.exit_x+p.throat_x)/2,p.exit_y,(p.cavity_high+p.cavity_low)/2))
        empty_intersection(housing,outlet)
        for center in p.bosses:
            empty_intersection(housing,F._cylinder(manager,c,s.mount_hole_mm/2-.05,p.floor_low-.1,p.cavity_high+.1,center))
            empty_intersection(lid,F._cylinder(manager,c,s.mount_hole_mm/2-.05,p.lid_low-.1,p.lid_high+.1,center))
        report['checks']['nonoverlap_inlet_outlet_motor_mounts']=True
        cached=F.cache(prepared);group=F.draw(cached);assert group.isValid;group.deleteMe()
        report['triangles']=sum(m.triangle_count for m in cached.meshes)
        assert d.rootComponent.bRepBodies.count==0 and d.timeline.count==0
        anchor=T.apply(prepared);O.capture(d,anchor,'fan',s.to_dict(),0);record=T.read(d,anchor);bodies=record.bodies
        assert len(bodies)==3 and record.recipe['version']==3
        revised=replace(s,volute_growth_mm=8,volute_mounts=False,volute_outlet_mm=18)
        updated=F.prepare(d,revised,record=record,geometry_cache=cache);assert updated.timings.get('rotor_cache_hit')
        T.apply(updated);read=T.read(d,anchor);assert read.bodies==bodies and read.settings==revised
        report['checks']['same_body_housing_edit_and_cached_rotor']=True
        only=replace(revised,output='rotor');T.apply(F.prepare(d,only,record=read,geometry_cache=cache));read=T.read(d,anchor)
        assert read.bodies==(bodies[0],)
        O.delete(d,read.recipe['feature_id']);assert d.timeline.count==0 and d.rootComponent.bRepBodies.count==0
        report['checks']['optional_bodies_removed_and_delete']=True
        report['success']=True
    except Exception:report['error']=traceback.format_exc()
    finally:
        if doc and doc.isValid:doc.close(False)
        if caller and caller.isValid:caller.activate();app.activeViewport.camera=camera
        report['caller_restored']=app.activeDocument==caller
        path.write_text(json.dumps(report,indent=2),encoding='utf-8')
        for key in list(sys.modules):
            if key==prefix or key.startswith(prefix+'.'):sys.modules.pop(key,None)
    print(json.dumps(report))

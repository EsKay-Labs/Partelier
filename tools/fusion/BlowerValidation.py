"""Run only through Fusion on an idle host; all geometry belongs to a scratch document."""
def run(context):
    import adsk.core as c, adsk.fusion as f
    import importlib, importlib.util, json, sys, time, traceback, uuid
    from pathlib import Path
    from dataclasses import replace
    root=Path('C:/Users/SKTech/Desktop/Programming_Projects/Apps/Fusion360/Partelier')
    app=c.Application.get();caller=app.activeDocument;camera=app.activeViewport.camera;doc=None
    prefix='_partelier_blower_validation_'+uuid.uuid4().hex
    report={'success':False,'cases':[]};path=root/'output/fans/blower-validation.json'
    path.parent.mkdir(parents=True,exist_ok=True)
    try:
        assert app.userInterface.activeCommand in ('','SelectCommand'),'Leave Fusion idle.'
        for key,module in tuple(sys.modules.items()):
            if key.endswith('partelier.addin'):
                for field in ('_hinge_commands','_snap_commands','_pattern_commands','_detail_commands','_fan_commands'):
                    manager=getattr(module,field,None)
                    assert not manager or not (getattr(manager,'_session',None) or getattr(manager,'busy',False)), 'An existing Partelier session is active.'
        package=root/'Partelier/partelier'
        spec=importlib.util.spec_from_file_location(prefix,package/'__init__.py',submodule_search_locations=[str(package)])
        module=importlib.util.module_from_spec(spec);sys.modules[prefix]=module;spec.loader.exec_module(module)
        S=importlib.import_module(prefix+'.tools.fans.settings');F=importlib.import_module(prefix+'.tools.fans.fusion')
        T=importlib.import_module(prefix+'.tools.fans.store');O=importlib.import_module(prefix+'.operations')
        doc=app.documents.add(c.DocumentTypes.FusionDesignDocumentType)
        design=f.Design.cast(app.activeProduct);design.designType=f.DesignTypes.ParametricDesignType
        settings=S.preset('blower','pc60');cache={};started=time.perf_counter()
        prepared=F.prepare(design,settings,geometry_cache=cache)
        assert len(prepared.bodies)==1 and prepared.bodies[0].isSolid
        assert design.timeline.count==0 and design.rootComponent.bRepBodies.count==0
        bounds=prepared.bodies[0].boundingBox
        assert abs((bounds.maxPoint.x-bounds.minPoint.x)*10-settings.diameter_mm)<1e-5
        assert abs(bounds.minPoint.z*10+settings.hub_height_mm/2)<1e-5
        report['cases'].append({'name':'prepare','ms':(time.perf_counter()-started)*1000,'faces':prepared.bodies[0].faces.count})
        mesh=F.cache(prepared);group=F.draw(mesh);assert group.isValid;group.deleteMe()
        assert design.timeline.count==0 and design.rootComponent.bRepBodies.count==0
        start=design.timeline.count;anchor=T.apply(prepared);O.capture(design,anchor,'fan',settings.to_dict(),start)
        record=T.read(design,anchor);body=record.bodies[0];body.name='Blower validation';body.isLightBulbOn=False
        revised=replace(settings,shaft_diameter_mm=2.2)
        second=F.prepare(design,revised,record=record,geometry_cache=cache)
        assert second.timings.get('rotor_cache_hit')
        T.apply(second);read=T.read(design,anchor)
        assert read.bodies[0]==body and body.name=='Blower validation' and not body.isLightBulbOn
        assert read.recipe['version']==2 and read.settings==revised
        report['cases'].append({'name':'edit_shaft_cache','passed':True})
        third=replace(revised,blower_height_mm=revised.blower_height_mm+2,blower_vane_mm=1)
        T.apply(F.prepare(design,third,record=read,geometry_cache=cache));read=T.read(design,anchor)
        assert read.settings==third and read.bodies[0]==body
        O.delete(design,read.recipe['feature_id'])
        assert design.rootComponent.bRepBodies.count==0 and design.timeline.count==0
        report['cases'].append({'name':'edit_vanes_delete','passed':True})
        report['success']=True
    except Exception:
        report['error']=traceback.format_exc()
    finally:
        if doc and doc.isValid:doc.close(False)
        if caller and caller.isValid:caller.activate();app.activeViewport.camera=camera
        report['caller_restored']=app.activeDocument==caller
        path.write_text(json.dumps(report,indent=2),encoding='utf-8')
        for key in list(sys.modules):
            if key==prefix or key.startswith(prefix+'.'):sys.modules.pop(key,None)
    print(json.dumps(report))

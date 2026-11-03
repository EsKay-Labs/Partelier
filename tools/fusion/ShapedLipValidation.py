"""Isolated native fixtures for circular and convex-polygon continuous lips."""
def run(context):
    import adsk.core as c,adsk.fusion as f
    import importlib,importlib.util,json,math,sys,time,traceback,uuid
    from pathlib import Path
    from dataclasses import replace
    root=Path('C:/Users/SKTech/Desktop/Programming_Projects/Apps/Fusion360/Partelier')
    app=c.Application.get();caller=app.activeDocument;camera=app.activeViewport.camera;doc=None
    prefix='_partelier_shaped_lip_'+uuid.uuid4().hex;report={'success':False,'cases':[]}
    path=root/'output/details/shaped-lip-validation.json';path.parent.mkdir(parents=True,exist_ok=True)
    try:
        assert app.userInterface.activeCommand in ('','SelectCommand')
        for key,module in tuple(sys.modules.items()):
            if key.endswith('partelier.addin'):
                for field in ('_hinge_commands','_snap_commands','_pattern_commands','_detail_commands','_fan_commands'):
                    manager=getattr(module,field,None)
                    assert not manager or not (getattr(manager,'_session',None) or getattr(manager,'busy',False)),'Finish the active Partelier session first.'
        package=root/'Partelier/partelier';spec=importlib.util.spec_from_file_location(prefix,package/'__init__.py',submodule_search_locations=[str(package)])
        module=importlib.util.module_from_spec(spec);sys.modules[prefix]=module;spec.loader.exec_module(module)
        S=importlib.import_module(prefix+'.tools.details.settings');F=importlib.import_module(prefix+'.tools.details.fusion')
        T=importlib.import_module(prefix+'.tools.details.store');O=importlib.import_module(prefix+'.operations')
        doc=app.documents.add(c.DocumentTypes.FusionDesignDocumentType);d=f.Design.cast(app.activeProduct);d.designType=f.DesignTypes.ParametricDesignType
        manager=f.TemporaryBRepManager.get()
        for kind in ('circle','polygon'):
            frame=F.h.HingeFrame((0,0,0),(1,0,0),(0,0,1),(0,-1,0))
            if kind=='circle':
                raw=(F._cylinder(frame,(0,0),-5,0,20),F._cylinder(frame,(0,0),.5,6,20))
            else:
                polygon=tuple((25*math.cos(i*math.pi/3),25*math.sin(i*math.pi/3)) for i in range(6))
                raw=(F.prism.prism(frame,polygon,-5,0),F.prism.prism(frame,polygon,.5,6))
            base=d.rootComponent.features.baseFeatures.add();assert base.startEdit()
            for body in raw:assert d.rootComponent.bRepBodies.add(body,base)
            assert base.finishEdit();bodies=tuple(base.bodies);assert len(bodies)==2
            faces=tuple(next(face for face in body.faces if c.Plane.cast(face.geometry) and abs(face.pointOnFace.z*10-z)<1e-5 and F._normal(face)[2]*sign>.99) for body,z,sign in zip(bodies,(0,.5),(1,-1)))
            baseline=(d.timeline.count,d.rootComponent.bRepBodies.count);volumes=tuple(body.volume for body in bodies)
            settings=S.DetailSettings();started=time.perf_counter();prepared=F.prepare(d,faces,settings)
            assert prepared.timings['outline_kind']==kind
            assert (d.timeline.count,d.rootComponent.bRepBodies.count)==baseline
            assert all(body.isSolid and body.lumps.count==1 for body in prepared.results)
            # Reject a groove that does not retain enough lid floor.
            try:F.prepare(d,faces,replace(settings,lip_height_mm=6))
            except ValueError:pass
            else:raise AssertionError('Thin lid floor was not protected.')
            start=d.timeline.count;anchor=T.apply(prepared);O.capture(d,anchor,'detail',settings.to_dict(),start)
            record=T.read(d,anchor,'lid');assert record.targets==bodies
            revised=replace(settings,lip_height_mm=3,lip_width_mm=1.4)
            T.apply(T.prepare_edit(d,record,revised));updated=T.read(d,anchor,'lid')
            assert updated.targets==bodies and updated.settings==revised
            O.delete(d,updated.recipe['id'])
            assert tuple(b.volume for b in bodies)==volumes
            assert d.rootComponent.bRepBodies.count==baseline[1]
            report['cases'].append({'outline':kind,'create_edit_delete':True,'floor_guard':True,'ms':(time.perf_counter()-started)*1000})
            assert base.deleteMe()
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

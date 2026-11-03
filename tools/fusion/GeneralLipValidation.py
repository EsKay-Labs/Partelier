"""Native concave and spline lip fixtures; all work is in disposable documents."""
def run(context):
    import adsk.core as c,adsk.fusion as f
    import importlib,importlib.util,json,sys,time,traceback,uuid
    from pathlib import Path
    from dataclasses import replace
    root=Path('C:/Users/SKTech/Desktop/Programming_Projects/Apps/Fusion360/Partelier');path=root/'output/details/general-lip-validation.json';path.parent.mkdir(parents=True,exist_ok=True)
    app=c.Application.get();caller=app.activeDocument;camera=app.activeViewport.camera;doc=None;report={'success':False,'cases':[]}
    prefix='_partelier_general_lip_'+uuid.uuid4().hex
    try:
        assert app.userInterface.activeCommand in ('','SelectCommand')
        for key,module in tuple(sys.modules.items()):
            if key.endswith('partelier.addin'):
                for field in ('_hinge_commands','_snap_commands','_pattern_commands','_detail_commands','_fan_commands','_mechanism_commands','_finishing_commands'):
                    manager=getattr(module,field,None)
                    assert not manager or not (getattr(manager,'_session',None) or getattr(manager,'busy',False)), 'Partelier session active.'
        package=root/'Partelier/partelier';spec=importlib.util.spec_from_file_location(prefix,package/'__init__.py',submodule_search_locations=[str(package)])
        module=importlib.util.module_from_spec(spec);sys.modules[prefix]=module;spec.loader.exec_module(module)
        S=importlib.import_module(prefix+'.tools.details.settings');F=importlib.import_module(prefix+'.tools.details.fusion');T=importlib.import_module(prefix+'.tools.details.store');O=importlib.import_module(prefix+'.operations')
        for kind in ('concave','spline'):
            case={'kind':kind};report['cases'].append(case)
            doc=app.documents.add(c.DocumentTypes.FusionDesignDocumentType);d=f.Design.cast(app.activeProduct);d.designType=f.DesignTypes.ParametricDesignType;r=d.rootComponent
            sketch=r.sketches.add(r.xYConstructionPlane)
            if kind=='concave':
                points=((-3,-2),(3,-2),(3,0),(.5,0),(.5,2),(-3,2))
                for a,b in zip(points,points[1:]+points[:1]):sketch.sketchCurves.sketchLines.addByTwoPoints(c.Point3D.create(*a,0),c.Point3D.create(*b,0))
            else:
                points=c.ObjectCollection.create()
                for x,y in ((-3,0),(-2,-1.8),(0,-2),(2,-1.5),(3,0),(1.8,2),(0,2.3),(-2,1.8)):
                    points.add(c.Point3D.create(x,y,0))
                curve=sketch.sketchCurves.sketchFittedSplines.add(points);curve.isClosed=True
            assert sketch.profiles.count==1,'Source fixture did not close.'
            bodies=[]
            for low,high in ((-.5,0),(.05,.6)):
                inp=r.features.extrudeFeatures.createInput(sketch.profiles.item(0),f.FeatureOperations.NewBodyFeatureOperation)
                inp.startExtent=f.OffsetStartDefinition.create(c.ValueInput.createByReal(low))
                assert inp.setOneSideExtent(f.DistanceExtentDefinition.create(c.ValueInput.createByReal(high-low)),f.ExtentDirections.PositiveExtentDirection)
                bodies.append(r.features.extrudeFeatures.add(inp).bodies.item(0))
            bodies=tuple(bodies);faces=tuple(next(face for face in body.faces if c.Plane.cast(face.geometry) and abs(face.pointOnFace.z-z)<1e-6 and F._normal(face)[2]*sign>.99) for body,z,sign in zip(bodies,(0,.05),(1,-1)))
            baseline=(r.bRepBodies.count,r.sketches.count,d.timeline.count);volumes=tuple(body.volume for body in bodies)
            started=time.perf_counter();s=S.DetailSettings();prepared=F.prepare(d,faces,s);case['prepare_ms']=(time.perf_counter()-started)*1000
            assert prepared.timings['outline_kind']=='native_offset';assert (r.bRepBodies.count,r.sketches.count,d.timeline.count)==baseline
            case['cleanup']=True;case['native_offset']=True
            start=d.timeline.count;anchor=T.apply(prepared);O.capture(d,anchor,'detail',s.to_dict(),start)
            record=T.read(d,anchor,'lid');revised=replace(s,lip_height_mm=3)
            T.apply(T.prepare_edit(d,record,revised));read=T.read(d,anchor,'lid');assert read.targets==bodies
            O.delete(d,read.recipe['id']);assert all(abs(body.volume-old)<1e-8 for body,old in zip(bodies,volumes))
            case['same_body_create_edit_delete']=True
            try:F.prepare(d,faces,replace(s,lip_height_mm=7))
            except ValueError:pass
            else:raise AssertionError('Floor protection was lost.')
            assert (r.bRepBodies.count,r.sketches.count,d.timeline.count)==baseline
            case['failed_prepare_cleanup']=True
            doc.close(False);doc=None
        report['success']=True
    except Exception:report['error']=traceback.format_exc()
    finally:
        if doc and doc.isValid:doc.close(False)
        if caller and caller.isValid:caller.activate();app.activeViewport.camera=camera
        report['caller_restored']=app.activeDocument==caller;path.write_text(json.dumps(report,indent=2),encoding='utf-8')
        for key in list(sys.modules):
            if key==prefix or key.startswith(prefix+'.'):sys.modules.pop(key,None)
    print(json.dumps(report))

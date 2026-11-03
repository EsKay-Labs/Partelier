"""Actual upstream edits through automatic pattern, grille, fan and lip rebuilds."""
def run(context):
    import adsk.core as c,adsk.fusion as f
    import importlib,importlib.util,json,sys,time,traceback,uuid
    from pathlib import Path
    from dataclasses import replace
    root=Path('C:/Users/SKTech/Desktop/Programming_Projects/Apps/Fusion360/Partelier');path=root/'output/auto-update/families.json';path.parent.mkdir(parents=True,exist_ok=True)
    app=c.Application.get();caller=app.activeDocument;camera=app.activeViewport.camera;doc=None;report={'success':False,'cases':[]}
    prefix='_partelier_auto_families_'+uuid.uuid4().hex
    try:
        assert app.userInterface.activeCommand in ('','SelectCommand')
        for key,module in tuple(sys.modules.items()):
            if key.endswith('partelier.addin'):
                for field in ('_hinge_commands','_snap_commands','_pattern_commands','_detail_commands','_fan_commands','_mechanism_commands','_finishing_commands'):
                    manager=getattr(module,field,None)
                    assert not manager or not (getattr(manager,'_session',None) or getattr(manager,'busy',False)), 'Partelier session active.'
        package=root/'Partelier/partelier';spec=importlib.util.spec_from_file_location(prefix,package/'__init__.py',submodule_search_locations=[str(package)])
        module=importlib.util.module_from_spec(spec);sys.modules[prefix]=module;spec.loader.exec_module(module)
        def mod(name):return importlib.import_module(prefix+'.'+name)
        O=mod('operations');A=mod('auto_refresh');P=mod('tools.patterns.fusion');PS=mod('tools.patterns.settings');PR=mod('tools.patterns.recipe')
        F=mod('tools.fans.fusion');FS=mod('tools.fans.settings');FT=mod('tools.fans.store');FR=mod('tools.fans.references')
        D=mod('tools.details.fusion');DS=mod('tools.details.settings');DT=mod('tools.details.store')
        def rect(d):
            sk=d.rootComponent.sketches.add(d.rootComponent.xYConstructionPlane)
            sk.sketchCurves.sketchLines.addTwoPointRectangle(c.Point3D.create(-2.5,-2,0),c.Point3D.create(2.5,2,0))
            return sk
        def extrude(d,sk,low,high):
            inp=d.rootComponent.features.extrudeFeatures.createInput(sk.profiles.item(0),f.FeatureOperations.NewBodyFeatureOperation)
            inp.startExtent=f.OffsetStartDefinition.create(c.ValueInput.createByReal(low))
            assert inp.setOneSideExtent(f.DistanceExtentDefinition.create(c.ValueInput.createByReal(high-low)),f.ExtentDirections.PositiveExtentDirection)
            return d.rootComponent.features.extrudeFeatures.add(inp)
        def cap(body,z,sign):return next(face for face in body.faces if c.Plane.cast(face.geometry) and abs(face.pointOnFace.z-z)<1e-6 and D._normal(face)[2]*sign>.99)
        for kind in ('pattern','grille','fan_circle','fan_sketch','lip'):
            case={'kind':kind,'success':False};report['cases'].append(case)
            try:
                doc=app.documents.add(c.DocumentTypes.FusionDesignDocumentType);d=f.Design.cast(app.activeProduct);d.designType=f.DesignTypes.ParametricDesignType;r=d.rootComponent
                if kind in ('pattern','grille'):
                    sketch=rect(d);source=extrude(d,sketch,0,.3);body=source.bodies.item(0);body.name='Original plate'
                    settings=PS.PatternSettings(pattern='circle',pitch_mm=15,web_mm=5,border_mm=5,layout_mode='fixed',edge_mode='whole') if kind=='pattern' else PS.PatternSettings(pattern='grille_parallel',pitch_mm=10,web_mm=3,border_mm=5,layout_mode='fill')
                    prepared=P.prepare_pattern(d,(cap(body,.3,1),),settings);start=d.timeline.count;anchor=PR.create_pattern(d,prepared);O.capture(d,anchor,'pattern',settings.to_dict(),start)
                    assert anchor.attributes.itemByName(A.GROUP,'baseline') is not None,'Missing source baseline.'
                    saved=json.loads(anchor.attributes.itemByName(A.GROUP,'baseline').value);history=d.timeline.count;count=r.bRepBodies.count
                    assert A.refresh(d)==[]
                    source.extentOne.distance.value=.4;d.computeAll();started=time.perf_counter();updated=A.refresh(d);case['refresh_ms']=(time.perf_counter()-started)*1000
                    assert len(updated)==1 and d.timeline.count==history and r.bRepBodies.count==count
                    assert body.isValid and body.name=='Original plate' and abs(body.boundingBox.maxPoint.z-.4)<1e-6
                    assert json.loads(anchor.attributes.itemByName(A.GROUP,'baseline').value)['source']!=saved['source']
                    assert A.refresh(d)==[];case['updates']=updated
                elif kind=='fan_circle':
                    sketch=r.sketches.add(r.xYConstructionPlane);circle=sketch.sketchCurves.sketchCircles.addByCenterRadius(c.Point3D.create(0,0,0),3)
                    source=extrude(d,sketch,0,.2);reference_body=source.bodies.item(0);reference_body.name='Opening reference'
                    edge=next(e for e in reference_body.edges if c.Circle3D.cast(e.geometry) and abs(c.Circle3D.cast(e.geometry).center.z-.2)<1e-6)
                    settings=replace(FS.preset('blower','pc60'),diameter_mm=58.8,size_preset='custom');refs={'circle':edge.entityToken}
                    placement,outline,signature=FR.resolve(d,refs,settings);prepared=replace(F.prepare(d,settings,placement,refs,outline),reference_signature=signature)
                    start=d.timeline.count;anchor=FT.apply(prepared);O.capture(d,anchor,'fan',settings.to_dict(),start);record=FT.read(d,anchor);rotor=record.bodies[0];rotor.name='Original rotor'
                    history=d.timeline.count;count=r.bRepBodies.count;assert anchor.attributes.itemByName(A.GROUP,'baseline') is not None
                    assert A.refresh(d)==[];circle.radius=3.5;d.computeAll();started=time.perf_counter();updated=A.refresh(d);case['refresh_ms']=(time.perf_counter()-started)*1000
                    read=FT.read(d,anchor);assert len(updated)==1 and read.bodies[0]==rotor and read.settings.diameter_mm==68.8
                    assert abs((rotor.boundingBox.maxPoint.x-rotor.boundingBox.minPoint.x)*10-68.8)<1e-5
                    assert d.timeline.count==history and r.bRepBodies.count==count and reference_body.isValid and reference_body.name=='Opening reference' and rotor.name=='Original rotor'
                    assert A.refresh(d)==[];case['updates']=updated
                elif kind=='fan_sketch':
                    sketch=r.sketches.add(r.xYConstructionPlane)
                    lines=sketch.sketchCurves.sketchLines.addTwoPointRectangle(c.Point3D.create(0,-.2,0),c.Point3D.create(2,.2,0))
                    vertical=next(line for line in lines if abs(line.startSketchPoint.geometry.x-line.endSketchPoint.geometry.x)<1e-8)
                    dimension=sketch.sketchDimensions.addDistanceDimension(vertical.startSketchPoint,vertical.endSketchPoint,
                        f.DimensionOrientations.VerticalDimensionOrientation,c.Point3D.create(-.5,0,0))
                    settings=replace(FS.FanSettings(),outline_mode='sketch');refs={'outline':sketch.profiles.item(0).entityToken}
                    placement,outline,signature=FR.resolve(d,refs,settings)
                    prepared=replace(F.prepare(d,settings,placement,refs,outline),reference_signature=signature)
                    start=d.timeline.count;anchor=FT.apply(prepared);O.capture(d,anchor,'fan',settings.to_dict(),start)
                    rotor=FT.read(d,anchor).bodies[0];volume=rotor.volume;body_revision=rotor.revisionId
                    history=d.timeline.count;gate=A.AutomaticUpdates(None);before=gate.revisions()
                    dimension.parameter.value=.5
                    assert rotor.revisionId==body_revision,'Fixture unexpectedly changed the generated body before refresh.'
                    assert gate.revisions()!=before,'A sketch-only edit was missed by the revision gate.'
                    started=time.perf_counter();updated=A.refresh(d);case['refresh_ms']=(time.perf_counter()-started)*1000
                    assert len(updated)==1 and FT.read(d,anchor).bodies[0]==rotor and rotor.volume>volume
                    assert d.timeline.count==history and r.bRepBodies.count==1 and A.refresh(d)==[]
                    case['updates']=updated;case['sketch_only_revision_detected']=True
                else:
                    sketch=rect(d);base=extrude(d,sketch,-.5,0);lid=extrude(d,sketch,.05,.6);one,two=base.bodies.item(0),lid.bodies.item(0)
                    one.name='Original base';two.name='Original lid';settings=DS.DetailSettings();prepared=D.prepare(d,(cap(one,0,1),cap(two,.05,-1)),settings)
                    start=d.timeline.count;anchor=DT.apply(prepared);O.capture(d,anchor,'detail',settings.to_dict(),start)
                    history=d.timeline.count;count=r.bRepBodies.count;assert anchor.attributes.itemByName(A.GROUP,'baseline') is not None;assert A.refresh(d)==[]
                    base.extentOne.distance.value=.53;d.computeAll();started=time.perf_counter();updated=A.refresh(d);case['refresh_ms']=(time.perf_counter()-started)*1000
                    assert len(updated)==1 and DT.read(d,anchor,'lid').targets==(one,two)
                    assert abs(one.boundingBox.maxPoint.z-.28)<1e-6
                    assert d.timeline.count==history and r.bRepBodies.count==count and one.name=='Original base' and two.name=='Original lid'
                    assert A.refresh(d)==[];case['updates']=updated
                assert d.timeline.markerPosition==d.timeline.count
                case['success']=True;case['same_bodies_history_and_idempotence']=True
            except Exception:case['error']=traceback.format_exc()
            finally:
                if doc and doc.isValid:doc.close(False)
                doc=None
        report['success']=all(case['success'] for case in report['cases'])
    except Exception:report['error']=traceback.format_exc()
    finally:
        if doc and doc.isValid:doc.close(False)
        if caller and caller.isValid:caller.activate();app.activeViewport.camera=camera
        report['caller_restored']=app.activeDocument==caller;path.write_text(json.dumps(report,indent=2),encoding='utf-8')
        for key in list(sys.modules):
            if key==prefix or key.startswith(prefix+'.'):sys.modules.pop(key,None)
    print(json.dumps(report))

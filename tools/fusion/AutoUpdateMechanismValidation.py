"""Real upstream extrusion edits through hinge, snap and attached-pair adapters."""
def run(context):
    import adsk.core as c,adsk.fusion as f
    import importlib,importlib.util,json,sys,time,traceback,uuid
    from pathlib import Path
    root=Path(r'C:\Users\SKTech\Desktop\Programming_Projects\Apps\Fusion360\Partelier')
    app=c.Application.get();caller=app.activeDocument;camera=app.activeViewport.camera;doc=None
    report={'success':False,'cases':[]};prefix='_partelier_auto_mechanisms_'+uuid.uuid4().hex
    try:
        assert app.userInterface.activeCommand in ('','SelectCommand')
        package=root/'Partelier'/'partelier';spec=importlib.util.spec_from_file_location(prefix,package/'__init__.py',submodule_search_locations=[str(package)])
        module=importlib.util.module_from_spec(spec);sys.modules[prefix]=module;spec.loader.exec_module(module)
        def mod(name):return importlib.import_module(prefix+'.'+name)
        O=mod('operations');A=mod('auto_refresh');H=mod('tools.hinge.fusion');HS=mod('tools.hinge.settings')
        S=mod('tools.snap_fit.fusion');SS=mod('tools.snap_fit.settings');M=mod('tools.mechanisms.fusion')
        MS=mod('tools.mechanisms.settings');MT=mod('tools.mechanisms.store')
        def extrude(design,x0,x1,y0,y1,z0,z1):
            r=design.rootComponent;sk=r.sketches.add(r.xYConstructionPlane)
            sk.sketchCurves.sketchLines.addTwoPointRectangle(c.Point3D.create(x0,y0,0),c.Point3D.create(x1,y1,0))
            inp=r.features.extrudeFeatures.createInput(sk.profiles.item(0),f.FeatureOperations.NewBodyFeatureOperation)
            inp.startExtent=f.OffsetStartDefinition.create(c.ValueInput.createByReal(z0))
            assert inp.setOneSideExtent(f.DistanceExtentDefinition.create(c.ValueInput.createByReal(z1-z0)),f.ExtentDirections.PositiveExtentDirection)
            return r.features.extrudeFeatures.add(inp)
        def face(body,axis,sign,coordinate):
            return next(q for q in body.faces if c.Plane.cast(q.geometry) and abs(q.pointOnFace.asArray()[axis]-coordinate)<1e-6
                        and q.evaluator.getNormalAtPoint(q.pointOnFace)[1].asArray()[axis]*sign>.99)
        def edge_at(face,axis,coordinate):
            return next(edge for edge in face.edges if c.Line3D.cast(edge.geometry) and all(abs(p.asArray()[axis]-coordinate)<1e-6 for p in (edge.startVertex.geometry,edge.endVertex.geometry)))
        for kind in ('hinge_sharp','hinge_fillet','snap_hook','attached_slider'):
            case={'kind':kind,'success':False};report['cases'].append(case)
            try:
                doc=app.documents.add(c.DocumentTypes.FusionDesignDocumentType);d=f.Design.cast(app.activeProduct);r=d.rootComponent
                if kind.startswith('hinge'):
                    ex_a=extrude(d,-2.4,-.4,-2.5,2.5,-.4,0);ex_b=extrude(d,.4,2.4,-2.5,2.5,-.4,0)
                    one,two=ex_a.bodies.item(0),ex_b.bodies.item(0);fa,fb=face(one,2,1,0),face(two,2,1,0);axis=edge_at(fa,0,-.4)
                    settings=HS.HingeSettings(fillet_edges=kind=='hinge_fillet',fillet_radius_mm=.3)
                    kwargs={}
                    if kind=='hinge_fillet':kwargs['edge_finisher']=mod('tools.hinge.native_finish').finish_native_results
                    p=H.prepare_hinge(d,fa,fb,axis,settings,**kwargs);start=d.timeline.count;anchor=H.create_hinge(d,p)
                    tool='hinge'
                elif kind=='snap_hook':
                    ex_a=extrude(d,-.3,0,-3,3,-2.4,0);ex_b=extrude(d,-.3,0,-3,3,0,2.4)
                    one,two=ex_a.bodies.item(0),ex_b.bodies.item(0);fa,fb=face(one,0,1,0),face(two,0,1,0);axis=edge_at(fa,2,0)
                    settings=SS.SnapFitSettings(chamfer_edges=False,print_support=False)
                    p=S.prepare_snap_fit(d,fa,fb,axis,settings);start=d.timeline.count;anchor=S.create_snap_fit(d,p);tool='snap'
                else:
                    settings=MS.MechanismSettings(output_mode='attached');gap=(2*settings.wall_mm+settings.height_mm+settings.clearance_mm-2*settings.attachment_overlap_mm)/10
                    ex_a=extrude(d,-4,4,-4,4,-.5,0);ex_b=extrude(d,-4,4,-1.9,.1,gap,gap+.5)
                    one,two=ex_a.bodies.item(0),ex_b.bodies.item(0);fa,fb=face(one,2,1,0),face(two,2,-1,gap)
                    axis=next(edge for edge in fa.edges if c.Line3D.cast(edge.geometry) and edge.endVertex.geometry.x-edge.startVertex.geometry.x>.1)
                    refs={'face_a':fa.entityToken,'face_b':fb.entityToken,'axis_edge':axis.entityToken}
                    p=M.prepare(d,settings,references=refs);start=d.timeline.count;anchor=MT.apply(p);tool='mechanism'
                one.name='Original A';two.name='Original B'
                O.capture(d,anchor,tool,settings.to_dict(),start)
                tag=anchor.attributes.itemByName(A.GROUP,'baseline');assert tag is not None,'Missing automatic source baseline'
                saved=json.loads(tag.value);assert saved['source'] and saved['owned']
                tokens=(one.entityToken,two.entityToken);count=r.bRepBodies.count;history=d.timeline.count
                assert A.refresh(d)==[],'Unchanged inputs were rebuilt'
                if kind.startswith('hinge'):
                    ex_a.extentOne.distance.value=.5;ex_b.extentOne.distance.value=.5
                elif kind=='snap_hook':ex_b.extentOne.distance.value=2.5
                else:ex_a.extentOne.distance.value=.55
                d.computeAll();started=time.perf_counter();updated=A.refresh(d);case['refresh_ms']=(time.perf_counter()-started)*1000
                assert len(updated)==1,(kind,updated)
                assert d.timeline.count==history and r.bRepBodies.count==count
                assert all(d.findEntityByToken(t)[0]==b for t,b in zip(tokens,(one,two)))
                assert one.name=='Original A' and two.name=='Original B'
                baseline=json.loads(anchor.attributes.itemByName(A.GROUP,'baseline').value)
                assert baseline['source']!=saved['source'] and baseline['owned']!=saved['owned']
                if kind=='snap_hook':assert abs(two.boundingBox.maxPoint.z-2.5)<1e-6
                if tool=='mechanism':assert MT.read(d,anchor).targets==(one,two)
                assert A.refresh(d)==[],'Repeated update was not idempotent'
                case.update(success=True,updates=updated,retained_targets=True,unchanged_history=True,idempotent=True)
            except Exception:case['error']=traceback.format_exc()
            finally:
                if doc is not None and doc.isValid:doc.close(False)
                doc=None
        report['success']=all(case['success'] for case in report['cases'])
    finally:
        if doc is not None and doc.isValid:doc.close(False)
        if caller is not None and caller.isValid:caller.activate();app.activeViewport.camera=camera
        report['caller_restored']=app.activeDocument==caller
        path=root/'output'/'auto-update'/'mechanisms.json';path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(report,indent=2),encoding='utf-8')
        for key in list(sys.modules):
            if key==prefix or key.startswith(prefix+'.'):sys.modules.pop(key,None)
    print(json.dumps(report))

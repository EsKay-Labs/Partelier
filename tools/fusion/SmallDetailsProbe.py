"""Fresh disposable fixtures for Small details, called through opt-in Fusion MCP."""

from dataclasses import replace
import hashlib,importlib,importlib.util,json
from pathlib import Path
import sys,time,uuid
import adsk.core as core
import adsk.fusion as native


def snapshot(design):
    return None if design is None else (design.timeline.count,design.timeline.markerPosition,
        [(b.entityToken,b.name,b.isLightBulbOn,round(b.volume,9),b.faces.count,b.edges.count) for b in design.rootComponent.bRepBodies])


def witnesses(adapter,faces,settings,targets,frame_info=None):
    count=0
    if settings.kind=='ribs':
        centers=adapter.planner.rib_positions(60,settings.rib_width_mm,settings.rib_count,settings.rib_margin_mm)
        for c in centers:
            y=-30+c;x=settings.rib_height_a_mm/4;z=settings.rib_height_b_mm/4
            assert adapter.a._containment(targets[0],(x,y,z));count+=1
            for offset,solid in ((settings.rib_width_mm/2-.03,True),(settings.rib_width_mm/2+.03,False)):
                assert adapter.a._containment(targets[0],(x,y+offset,z))==solid;count+=1
            assert adapter.a._containment(targets[0],(.8*settings.rib_height_a_mm,y,.8*settings.rib_height_b_mm))==(settings.rib_style=='full');count+=1
        return count
    frame,bounds,gap,depth=frame_info or adapter._mating(faces,settings)
    def material(body,x,z,height):return adapter.a._containment(body,adapter.world(frame,x,z,height))
    if settings.kind=='lid':
        lo,hi,bottom,top=bounds;b=settings.lip_inset_mm;w=settings.lip_width_mm;c=settings.lip_clearance_mm
        for x,z,dx,dz in ((lo+b+w/2,0,-1,0),(hi-b-w/2,0,1,0),(0,bottom+b+w/2,0,-1),(0,top-b-w/2,0,1)):
            assert material(targets[0],x,z,settings.lip_height_mm/2)
            assert not material(targets[1],x,z,gap+depth/2)
            assert material(targets[1],x,z,gap+depth+settings.socket_floor_mm/2)
            for sign in (-1,1):assert material(targets[1],x+sign*dx*(w/2+c+.05),z+sign*dz*(w/2+c+.05),gap+depth/2)
            count+=5
    else:
        radius=settings.pin_diameter_mm/2;hole=radius+settings.pin_clearance_mm/2
        points=adapter.planner.pins(bounds,settings)
        for x,z in points:
            assert material(targets[0],x+radius-.03,z,settings.pin_height_mm/2)
            assert not material(targets[0],x+radius+.03,z,settings.pin_height_mm/2)
            assert not material(targets[1],x+hole-.03,z,gap+depth/2)
            assert material(targets[1],x+hole+.03,z,gap+depth/2)
            assert material(targets[1],x,z,gap+depth+settings.socket_floor_mm/2);count+=5
    return count


def run(context):
    context=context or {};root=Path(__file__).resolve().parents[2];package=root/'Partelier/partelier'
    name='_partelier_detail_probe_'+uuid.uuid4().hex
    spec=importlib.util.spec_from_file_location(name,package/'__init__.py',submodule_search_locations=[str(package)])
    module=importlib.util.module_from_spec(spec);sys.modules[name]=module;spec.loader.exec_module(module)
    settings_module,adapter,store=tuple(importlib.import_module(name+'.tools.details.'+leaf) for leaf in ('settings','fusion','store'))
    app=core.Application.get();caller=app.activeDocument;original=native.Design.cast(app.activeProduct);before=snapshot(original)
    camera=app.activeViewport.camera;component=original.activeComponent if original else None;owned=None
    report={'version':'0.18.0','fusion_version':app.version,'context':context,'success':False}
    try:
        if app.userInterface.activeCommand not in ('','SelectCommand'):raise RuntimeError('Finish the active command first.')
        owned=app.documents.add(core.DocumentTypes.FusionDesignDocumentType);design=native.Design.cast(app.activeProduct)
        if design.designType!=native.DesignTypes.ParametricDesignType:design.designType=native.DesignTypes.ParametricDesignType
        root_component=design.rootComponent;manager=native.TemporaryBRepManager.get()
        def box(x0,x1,y0,y1,z0,z1):return manager.createBox(core.OrientedBoundingBox3D.create(
            core.Point3D.create((x0+x1)/20,(y0+y1)/20,(z0+z1)/20),core.Vector3D.create(1,0,0),core.Vector3D.create(0,1,0),(x1-x0)/10,(y1-y0)/10,(z1-z0)/10))
        def persist(shape,label):
            base=root_component.features.baseFeatures.add();assert base.startEdit();body=root_component.bRepBodies.add(shape,base)
            assert base.finishEdit();body=base.bodies.item(0);body.name=label;return body
        kind=context.get('kind','lid');values={k:v for k,v in context.items() if k in settings_module.DetailSettings().to_dict()}
        if kind=='ribs':
            shape=box(-3,40,-30,30,-3,0);assert manager.booleanOperation(shape,box(-3,0,-30,30,0,30),native.BooleanTypes.UnionBooleanType)
            A=persist(shape,'Detail support');B=A
            faces=(next(f for f in A.faces if abs(f.pointOnFace.x)<1e-7 and adapter._normal(f)[0]>.99),
                next(f for f in A.faces if abs(f.pointOnFace.z)<1e-7 and adapter._normal(f)[2]>.99))
        else:
            shape=box(-30,30,-20,20,-5,0)
            wall=context.get('wall_mm',4)
            assert manager.booleanOperation(shape,box(-30+wall,30-wall,-20+wall,20-wall,-4,1),native.BooleanTypes.DifferenceBooleanType)
            A=persist(shape,'Detail base');B=persist(box(-30,30,-20,20,.25,6.25),'Detail lid')
            faces=(next(f for f in A.faces if abs(f.pointOnFace.z)<1e-7 and adapter._normal(f)[2]>.99),
                next(f for f in B.faces if abs(f.pointOnFace.z-.025)<1e-7 and adapter._normal(f)[2]<-.99))
        clean=snapshot(design)
        try:
            settings=settings_module.DetailSettings(**values)
            if context.get('stack'):
                lip=adapter.prepare(design,faces,settings_module.DetailSettings(kind='lid'));lip_anchor=store.apply(lip)
                def same_plane(body,z,normal):
                    choices=[f for f in body.faces if abs(f.pointOnFace.z-z)<1e-7 and adapter._normal(f)[2]*normal>.99]
                    return max(choices,key=lambda f:(adapter._frame(f)[1][1]-adapter._frame(f)[1][0])*(adapter._frame(f)[1][3]-adapter._frame(f)[1][2]))
                faces=(same_plane(A,0,1),same_plane(B,.025,-1))
                try:store.read(design,lip_anchor,'lid')
                except ValueError:raise
                clean=snapshot(design)
            start=time.perf_counter();prepared=adapter.prepare(design,faces,settings)
        except ValueError as error:
            if not context.get('expect_refusal') or context['expect_refusal'].lower() not in str(error).lower():raise
            assert snapshot(design)==clean
            report.update(success=True,expected_refusal=str(error),model_unchanged_before_cleanup=True);return report
        if context.get('expect_refusal'):raise AssertionError('Unsupported detail was accepted')
        report['prepare_ms']=(time.perf_counter()-start)*1000;report['timings']=prepared.timings
        report['material_witnesses']=witnesses(adapter,faces,settings,prepared.results)
        assert snapshot(design)==clean
        if context.get('preview'):
            graphics=root_component.customGraphicsGroups.count;prepared=adapter.cache(prepared);group=adapter.draw(prepared)
            assert group.isValid and group.deleteMe();assert snapshot(design)==clean and root_component.customGraphicsGroups.count==graphics
            report['preview_cleanup']=True
        count=root_component.bRepBodies.count;history=design.timeline.count;tokens=[b.entityToken for b in prepared.targets]
        start=time.perf_counter();anchor=store.apply(prepared);report['create_ms']=(time.perf_counter()-start)*1000
        assert root_component.bRepBodies.count==count and design.timeline.count==history+1+len(prepared.targets)
        record=store.read(design,A,settings.kind);assert record.settings==settings
        if context.get('stack'):
            try:store.read(design,lip_anchor,'lid')
            except ValueError as error:assert 'end of the timeline' in str(error)
            else:raise AssertionError('Earlier detail Edit did not guard later features')
            report['stacked_delta_tools_and_earlier_edit_guard']=True
        changed=replace(settings,lip_height_mm=3) if kind=='lid' else replace(settings,pin_height_mm=4.4,pin_count=4) if kind=='alignment' else replace(settings,rib_height_a_mm=14,rib_count=4)
        start=time.perf_counter();rebuilt=store.prepare_edit(design,record,changed);store.apply(rebuilt)
        report['edit_rebuild_ms']=(time.perf_counter()-start)*1000
        assert root_component.bRepBodies.count==count and design.timeline.count==history+1+len(prepared.targets)
        assert all(design.findEntityByToken(t)[0]==b for t,b in zip(tokens,prepared.targets))
        assert store.read(design,anchor,settings.kind).settings==changed
        # Resolve original faces in their guarded history to inspect the same
        # physical coordinates while sampling the final persistent bodies.
        with store.input_scope(design,store.read(design,anchor,settings.kind)):
            saved_faces=tuple(design.findEntityByToken(t)[0] for t in rebuilt.tokens['faces'])
            frame_info=adapter._mating(saved_faces,changed) if kind!='ribs' else None
        report['rebuilt_material_witnesses']=witnesses(adapter,saved_faces if kind!='ribs' else faces,changed,prepared.targets,frame_info)
        if context.get('registration'):
            commands=importlib.import_module(name+'.tools.details.command')
            if app.userInterface.commandDefinitions.itemById(commands.COMMIT_ID) is not None:
                report['native_registration_cleanup']='skipped_existing_owner'
            else:
                stable=snapshot(design);manager_commands=commands.DetailCommands()
                try:
                    manager_commands.start();manager_commands.runner._start()
                    assert app.userInterface.commandDefinitions.itemById(commands.COMMIT_ID) is not None
                finally:manager_commands.stop()
                assert app.userInterface.commandDefinitions.itemById(commands.COMMIT_ID) is None
                assert snapshot(design)==stable;report['native_registration_cleanup']=True
        picture=context.get('screenshot')
        if picture:
            view=app.activeViewport.camera;view.viewOrientation=core.ViewOrientations.IsoTopRightViewOrientation;view.isFitView=True
            app.activeViewport.camera=view;assert app.activeViewport.saveAsImageFile(str(picture),1000,700)
        if context.get('views') and kind!='ribs':
            folder=Path(context['views']);visibleA,visibleB=A.isLightBulbOn,B.isLightBulbOn
            try:
                A.isLightBulbOn=True;B.isLightBulbOn=False
                view=app.activeViewport.camera;view.viewOrientation=core.ViewOrientations.IsoTopRightViewOrientation;view.isFitView=True
                app.activeViewport.camera=view;assert app.activeViewport.saveAsImageFile(str(folder/(kind+'-base.png')),1000,700)
                A.isLightBulbOn=False;B.isLightBulbOn=True
                view=app.activeViewport.camera;view.eye=core.Point3D.create(10,-10,-12);view.target=core.Point3D.create(0,0,.3);view.upVector=core.Vector3D.create(0,0,1);view.isFitView=True
                app.activeViewport.camera=view;assert app.activeViewport.saveAsImageFile(str(folder/(kind+'-receiver.png')),1000,700)
            finally:A.isLightBulbOn=visibleA;B.isLightBulbOn=visibleB
        report.update(success=True,same_targets=True,owned_features=1+len(prepared.targets))
    finally:
        if owned is not None and owned.isValid:owned.close(False)
        if caller is not None and caller.isValid:caller.activate();app.activeViewport.camera=camera
        report['caller_document_unchanged']=app.activeDocument==caller and snapshot(original)==before and (original is None or original.activeComponent==component)
        report['discarded_without_saving']=owned is None or not owned.isValid
        report['source_sha256']={p.relative_to(root).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in package.rglob('*.py')}
        if context.get('report_path'):Path(context['report_path']).write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
        for key in tuple(sys.modules):
            if key==name or key.startswith(name+'.'):sys.modules.pop(key,None)
    assert report['caller_document_unchanged'] and report['discarded_without_saving']
    print(json.dumps({k:v for k,v in report.items() if k!='source_sha256'}));return report

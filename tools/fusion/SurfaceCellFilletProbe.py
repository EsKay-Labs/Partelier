"""One disposable case for mapped Warren/perimeter fillets; no caller edits."""

from dataclasses import replace
import importlib,importlib.util,json,math,sys,time,uuid
from pathlib import Path
import adsk.core as core
import adsk.fusion as native


def snapshot(design):
    if design is None:return None
    timeline=(design.timeline.count,design.timeline.markerPosition) if design.designType==native.DesignTypes.ParametricDesignType else None
    return timeline,[(b.entityToken,b.name,b.isLightBulbOn,round(b.volume,9)) for b in design.rootComponent.bRepBodies]


def run(context):
    context=context or {};root=Path(__file__).resolve().parents[2];package=root/'Partelier/partelier';name='_partelier_cell_fillet_'+uuid.uuid4().hex
    spec=importlib.util.spec_from_file_location(name,package/'__init__.py',submodule_search_locations=[str(package)])
    module=importlib.util.module_from_spec(spec);sys.modules[name]=module;spec.loader.exec_module(module)
    a,s,recipe=[importlib.import_module(name+'.tools.patterns.'+leaf) for leaf in ('fusion','settings','recipe')]
    app=core.Application.get();caller=app.activeDocument;original=native.Design.cast(app.activeProduct)
    before=snapshot(original);camera=app.activeViewport.camera;owned=None
    report={'release':'0.23.0','fusion_version':app.version,'context':context,'success':False}
    try:
        if app.userInterface.activeCommand not in ('','SelectCommand'):raise ValueError('Finish the active command before this disposable test.')
        for key,value in tuple(sys.modules.items()):
            if key.endswith('partelier.addin'):
                for field in ('_hinge_commands','_snap_commands','_pattern_commands','_detail_commands'):
                    manager=getattr(value,field,None);state=manager.palette_state() if manager else {}
                    if state.get('sessionId') and state.get('phase') not in ('idle','created','cancelled'):
                        raise ValueError('Cancel the active Partelier task before this disposable test.')
        owned=app.documents.add(core.DocumentTypes.FusionDesignDocumentType);design=native.Design.cast(app.activeProduct)
        if design.designType!=native.DesignTypes.ParametricDesignType:design.designType=native.DesignTypes.ParametricDesignType
        comp=design.rootComponent;manager=native.TemporaryBRepManager.get();kind=context.get('kind','cylinder')
        if kind=='plane':
            shape=manager.createBox(core.OrientedBoundingBox3D.create(core.Point3D.create(0,0,-.15),core.Vector3D.create(1,0,0),core.Vector3D.create(0,1,0),6,4,.3))
        else:
            shape=manager.createCylinderOrCone(core.Point3D.create(0,0,0),2.5,core.Point3D.create(0,0,4),2.5)
            inner=manager.createCylinderOrCone(core.Point3D.create(0,0,-.1),2.2,core.Point3D.create(0,0,4.1),2.2)
            assert manager.booleanOperation(shape,inner,native.BooleanTypes.DifferenceBooleanType)
        base=comp.features.baseFeatures.add();assert base.startEdit();comp.bRepBodies.add(shape,base);assert base.finishEdit()
        body=base.bodies.item(0);body.name='Surface cell fixture'
        if kind=='plane':face=next(f for f in body.faces if core.Plane.cast(f.geometry) is not None and abs(f.pointOnFace.z)<1e-7 and a.hinge._plane_normal(f)[2]>.99)
        else:face=next(f for f in body.faces if core.Cylinder.cast(f.geometry) is not None and abs(core.Cylinder.cast(f.geometry).radius-2.5)<1e-7)
        values=s.PatternSettings(pattern=context.get('pattern','warren'),mode=context.get('mode','through'),
            pitch_mm=context.get('pitch_mm',12),web_mm=2,border_mm=3,depth_mm=.5,
            pattern_fillet_mm=context.get('radius_mm',.5),edge_mode=context.get('edge_mode','whole'),layout_mode=context.get('layout_mode','auto'),density='sparse',size_locked=True)
        clean=snapshot(design);start=time.perf_counter()
        try:prepared=a.prepare_pattern(design,(face,),values)
        except ValueError as error:
            if not context.get('expect_refusal') or context['expect_refusal'] not in str(error):raise
            assert snapshot(design)==clean;report.update(success=True,expected_refusal=str(error));return report
        if context.get('expect_refusal'):raise AssertionError('Unsupported fillet accepted')
        report.update(prepare_ms=round((time.perf_counter()-start)*1000,2),timings=prepared.timings,cells=prepared.cell_count)
        assert snapshot(design)==clean
        if values.pattern in ('circle','slot'):
            sharp=a.prepare_pattern(design,(face,),replace(values,pattern_fillet_mm=0))
            assert abs(sharp.result_body.volume-prepared.result_body.volume)<1e-9
            report['already_smooth_unchanged']=True
        mapped=a._mapped_cells((face,),values);witnesses=0
        for cell in mapped:
            if witnesses>=12:break
            # Rounded full-cell interior is robust even for asymmetric windows.
            p=cell.rounded_profile.interior_point if cell.rounded_profile is not None else (0,0)
            frame=a.hinge.HingeFrame(cell.center.point_mm,cell.center.tangent_u,cell.center.normal,a.hinge._cross(cell.center.tangent_u,cell.center.normal))
            point=tuple(o+p[0]*u+p[1]*z for o,u,z in zip(frame.origin_mm,frame.x_axis,frame.z_axis))
            if kind=='cylinder':
                length=math.hypot(point[0],point[1]);point=(point[0]*25/length,point[1]*25/length,point[2]);normal=(point[0]/25,point[1]/25,0)
            else:normal=(0,0,1)
            offset=values.depth_mm/2 if values.mode=='emboss' else -1.5 if values.mode=='through' else -values.depth_mm/2
            witness=tuple(x+offset*n for x,n in zip(point,normal))
            expected=values.mode=='emboss'
            assert a._containment(prepared.result_body,witness)==expected,(values.mode,point,witness)
            if values.mode=='inlay':assert a._containment(prepared.colour_body,witness)
            witnesses+=1
        if values.pattern_fillet_mm and values.pattern not in ('circle','slot'):
            cylinders=[core.Cylinder.cast(f.geometry) for f in prepared.result_body.faces if core.Cylinder.cast(f.geometry) is not None]
            report['exact_radius_faces']=sum(abs(c.radius*10-values.pattern_fillet_mm)<1e-5 for c in cylinders)
            if any(c.rounded_profile is not None for c in mapped):assert report['exact_radius_faces']>0
        prepared=a.display_export.prepare(prepared);groups=comp.customGraphicsGroups.count
        group=a.preview_pattern(prepared);assert group.isValid and group.deleteMe()
        assert comp.customGraphicsGroups.count==groups and snapshot(design)==clean
        count=comp.bRepBodies.count;history=design.timeline.count;token=body.entityToken
        start=time.perf_counter();recipe.create_pattern(design,prepared);loaded=recipe.read_edit_target(design,body)
        assert loaded.settings==values and loaded.recipe['version']==12;feature=loaded.record.feature_id
        actual_count=count+(1 if values.mode=='inlay' else 0);actual_history=design.timeline.count
        assert comp.bRepBodies.count==actual_count and actual_history>=history+2
        changed=replace(values,pattern_fillet_mm=.7 if values.pattern_fillet_mm<1 else .3)
        candidate=recipe.prepare_edit_pattern(design,loaded,changed);recipe.rebuild_pattern(design,loaded,candidate)
        revised=recipe.read_edit_target(design,body)
        assert revised.settings==changed and revised.record.feature_id==feature
        assert body.entityToken==token and body.name=='Surface cell fixture' and body.isLightBulbOn
        assert comp.bRepBodies.count==actual_count and design.timeline.count==actual_history
        report.update(create_rebuild_ms=round((time.perf_counter()-start)*1000,2),witnesses=witnesses,same_body_and_history=True,preview_cleanup=True)
        if context.get('screenshot'):
            view=app.activeViewport.camera;view.viewOrientation=core.ViewOrientations.IsoTopRightViewOrientation;view.isFitView=True;app.activeViewport.camera=view
            assert app.activeViewport.saveAsImageFile(context['screenshot'],1000,650)
        report['success']=True
    finally:
        if owned is not None and owned.isValid:owned.close(False)
        if caller is not None and caller.isValid:caller.activate();app.activeViewport.camera=camera
        report['caller_unchanged']=snapshot(original)==before
        for key in tuple(sys.modules):
            if key==name or key.startswith(name+'.'):sys.modules.pop(key,None)
        if not report['caller_unchanged']:raise AssertionError('Caller model changed')
    return report

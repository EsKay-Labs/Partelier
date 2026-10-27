"""Isolated MCP validation of planar trusses; never edits the caller's model."""

from dataclasses import replace
import hashlib
import importlib
import importlib.util
import json
import math
from pathlib import Path
import sys
import time
import uuid
import adsk.core as core
import adsk.fusion as native


def snapshot(design):
    if design is None:return None
    return {'timeline':design.timeline.count,'marker':design.timeline.markerPosition,
        'bodies':[(b.entityToken,b.name,b.isLightBulbOn,round(b.volume,9),b.faces.count,b.edges.count) for b in design.rootComponent.bRepBodies]}


def witnesses(adapter,plate,body,layout,width):
    count=0
    for hole in layout.holes:
        center=tuple(sum(p[i] for p in hole)/len(hole) for i in (0,1))
        assert not adapter._containment(body,plate.world(*center,-plate.thickness_mm/2));count+=1
    for a,b in layout.members:
        midpoint=tuple((x+y)/2 for x,y in zip(a,b));length=math.dist(a,b)
        normal=(-(b[1]-a[1])/length,(b[0]-a[0])/length)
        for sign in (-1,1):
            for distance,solid in ((width/2-.03,True),(width/2+.03,False)):
                p=tuple(x+sign*distance*n for x,n in zip(midpoint,normal))
                assert adapter._containment(body,plate.world(*p,-plate.thickness_mm/2))==solid,(a,b,p,solid)
                count+=1
    return count


def run(context):
    context=context or {};root=Path(__file__).resolve().parents[2];package=root/'Partelier/partelier'
    name='_partelier_truss_probe_'+uuid.uuid4().hex
    spec=importlib.util.spec_from_file_location(name,package/'__init__.py',submodule_search_locations=[str(package)])
    module=importlib.util.module_from_spec(spec);sys.modules[name]=module;spec.loader.exec_module(module)
    adapter,settings_module,recipe,flat_plate=tuple(importlib.import_module(name+'.tools.patterns.'+leaf) for leaf in ('fusion','settings','recipe','flat_plate'))
    planner=importlib.import_module(name+'.tools.truss.planner')
    app=core.Application.get();caller=app.activeDocument;original=native.Design.cast(app.activeProduct)
    before=snapshot(original);camera=app.activeViewport.camera;component=original.activeComponent if original else None
    report={'version':'0.17.0','fusion_version':app.version,'context':context,'success':False};owned=None
    try:
        if app.userInterface.activeCommand not in ('','SelectCommand'):raise RuntimeError('Finish the active command before this probe.')
        owned=app.documents.add(core.DocumentTypes.FusionDesignDocumentType);design=native.Design.cast(app.activeProduct)
        if design.designType!=native.DesignTypes.ParametricDesignType:design.designType=native.DesignTypes.ParametricDesignType
        manager=native.TemporaryBRepManager.get();w=context.get('width_mm',120);d=context.get('depth_mm',40);t=context.get('thickness_mm',3)
        shape=manager.createBox(core.OrientedBoundingBox3D.create(core.Point3D.create(0,0,t/20),core.Vector3D.create(1,0,0),core.Vector3D.create(0,1,0),w/10,d/10,t/10))
        angle=math.radians(context.get('incline_deg',0));normal=(0,-math.sin(angle),math.cos(angle))
        if angle:
            transform=core.Matrix3D.create();assert transform.setToRotation(angle,core.Vector3D.create(1,0,0),core.Point3D.create(0,0,0))
            assert manager.transform(shape,transform)
        if context.get('stepped_back'):
            step=manager.createBox(core.OrientedBoundingBox3D.create(core.Point3D.create(w/40,0,-.04),core.Vector3D.create(1,0,0),core.Vector3D.create(0,1,0),w/40,d/20,.1))
            assert manager.booleanOperation(shape,step,native.BooleanTypes.UnionBooleanType)
        base=design.rootComponent.features.baseFeatures.add();assert base.startEdit()
        body=design.rootComponent.bRepBodies.add(shape,base);assert base.finishEdit();body=base.bodies.item(0)
        body.name='Planar truss fixture';token=body.entityToken;visible=body.isLightBulbOn
        face=next(f for f in body.faces if abs(f.area-w*d/100)<1e-6 and f.evaluator.getNormalAtPoint(f.pointOnFace)[0]
            and sum(a*b for a,b in zip(normal,(f.evaluator.getNormalAtPoint(f.pointOnFace)[1].x,f.evaluator.getNormalAtPoint(f.pointOnFace)[1].y,f.evaluator.getNormalAtPoint(f.pointOnFace)[1].z)))>.999)
        clean=snapshot(design)
        try:
            settings=settings_module.PatternSettings(pattern=context.get('style','truss_warren'),layout_mode='fill',
                web_mm=context.get('member_mm',2),border_mm=context.get('frame_mm',3),
                truss_bays=context.get('bays',6),truss_axis=context.get('axis','long'))
            selected=(face,next(f for f in body.faces if f!=face)) if context.get('two_faces') else (face,)
            start=time.perf_counter();prepared=adapter.prepare_pattern(design,selected,settings)
        except ValueError as error:
            if not context.get('expect_refusal') or context['expect_refusal'].lower() not in str(error).lower():raise
            assert snapshot(design)==clean
            report.update(success=True,expected_refusal=str(error),model_unchanged_before_cleanup=True);return report
        if context.get('expect_refusal'):raise AssertionError('Unsupported truss was accepted')
        report.update(prepare_ms=(time.perf_counter()-start)*1000,timings=prepared.timings,windows=prepared.cell_count)
        plate=flat_plate.inspect(design,(face,),settings,body)
        bounds=tuple(v for axis in (0,1) for v in (min(p[axis] for p in plate.outer),max(p[axis] for p in plate.outer)))
        layout=planner.plan(bounds,settings.pattern,settings.truss_bays,settings.web_mm,settings.border_mm,settings.truss_axis)
        report['window_and_perpendicular_width_witnesses']=witnesses(adapter,plate,prepared.result_body,layout,settings.web_mm)
        assert snapshot(design)==clean and prepared.result_body.lumps.count==1
        if context.get('preview'):
            groups=design.rootComponent.customGraphicsGroups.count;prepared=adapter.display_export.prepare(prepared)
            group=adapter.preview_pattern(prepared);assert group.isValid and group.deleteMe()
            assert snapshot(design)==clean and design.rootComponent.customGraphicsGroups.count==groups
            report.update(preview_draw_cleanup=True,preview_triangles=prepared.display_mesh.triangle_count)
        history=design.timeline.count;start=time.perf_counter();recipe.create_pattern(design,prepared)
        report['create_ms']=(time.perf_counter()-start)*1000
        target=recipe.read_edit_target(design,body);feature_id=target.record.feature_id
        assert target.settings==settings and target.record.recipe['version']==2 and target.recipe['version']==12
        assert design.timeline.count==history+2 and design.rootComponent.bRepBodies.count==1
        changes=[replace(settings,truss_bays=settings.truss_bays+2)] if settings.truss_bays<64 else [replace(settings,web_mm=settings.web_mm+.1)]
        if context.get('edit_cycle'):
            changes=[replace(settings,pattern=style,truss_bays=8,web_mm=2.4,truss_axis=axis)
                     for style,axis in (('truss_pratt','long'),('truss_howe','long'),('truss_warren','short'),('truss_warren','long'))]
        report['edits']=[]
        for changed in changes:
            start=time.perf_counter();target=recipe.read_edit_target(design,body)
            rebuilt=recipe.prepare_edit_pattern(design,target,changed);recipe.rebuild_pattern(design,target,rebuilt)
            assert design.timeline.count==history+2 and design.rootComponent.bRepBodies.count==1
            target=recipe.read_edit_target(design,body)
            assert target.settings==changed and target.record.feature_id==feature_id
            assert design.findEntityByToken(token)[0]==body and body.name=='Planar truss fixture' and body.isLightBulbOn==visible
            revised=planner.plan(bounds,changed.pattern,changed.truss_bays,changed.web_mm,changed.border_mm,changed.truss_axis)
            checks=witnesses(adapter,plate,body,revised,changed.web_mm)
            report['edits'].append({'style':changed.pattern,'axis':changed.truss_axis,'bays':changed.truss_bays,'witnesses':checks,'elapsed_ms':(time.perf_counter()-start)*1000})
        picture=context.get('screenshot')
        if picture:
            view=app.activeViewport.camera;view.viewOrientation=core.ViewOrientations.IsoTopRightViewOrientation;view.isFitView=True
            app.activeViewport.camera=view;assert app.activeViewport.saveAsImageFile(str(picture),1000,650)
        report.update(success=True,same_body=True,owned_features=2,flat_back=True)
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

"""Disposable inside/outside enclosure detent geometry and in-place history."""

from dataclasses import replace
import importlib,importlib.util,json,math,sys,time,uuid
from pathlib import Path
import adsk.core as core
import adsk.fusion as native


def snapshot(design):
    if design is None:return None
    history=(design.timeline.count,design.timeline.markerPosition) if design.designType==native.DesignTypes.ParametricDesignType else None
    return (history,[(b.entityToken,b.name,b.isLightBulbOn,round(b.volume,9)) for b in design.rootComponent.bRepBodies])


def run(context):
    root=Path(__file__).resolve().parents[2];name='_partelier_pushfit_'+uuid.uuid4().hex;package=root/'Partelier/partelier'
    spec=importlib.util.spec_from_file_location(name,package/'__init__.py',submodule_search_locations=[str(package)])
    module=importlib.util.module_from_spec(spec);sys.modules[name]=module;spec.loader.exec_module(module)
    adapter,settings,ball=[importlib.import_module(name+'.tools.snap_fit.'+leaf) for leaf in ('fusion','settings','ball_detent')]
    app=core.Application.get();caller=app.activeDocument;original=native.Design.cast(app.activeProduct)
    before=snapshot(original);camera=app.activeViewport.camera;owned=None
    report={'version':'0.21.1','fusion_version':app.version,'cases':[],'success':False}
    try:
        if app.userInterface.activeCommand not in ('','SelectCommand'):raise ValueError('Finish the current Fusion command first.')
        for key,value in tuple(sys.modules.items()):
            if key.endswith('partelier.addin'):
                for field in ('_hinge_commands','_snap_commands','_pattern_commands','_detail_commands'):
                    manager=getattr(value,field,None);state=manager.palette_state() if manager else {}
                    if state.get('sessionId') and state.get('phase') not in ('idle','created','cancelled'):
                        raise ValueError('Cancel the current Partelier preview before this disposable test.')
        owned=app.documents.add(core.DocumentTypes.FusionDesignDocumentType);design=native.Design.cast(app.activeProduct)
        if design.designType!=native.DesignTypes.ParametricDesignType:design.designType=native.DesignTypes.ParametricDesignType
        comp=design.rootComponent;manager=native.TemporaryBRepManager.get()
        def box(x0,x1,y0,y1,z0,z1):return manager.createBox(core.OrientedBoundingBox3D.create(
            core.Point3D.create((x0+x1)/20,(y0+y1)/20,(z0+z1)/20),core.Vector3D.create(1,0,0),core.Vector3D.create(0,1,0),(x1-x0)/10,(y1-y0)/10,(z1-z0)/10))
        def persist(shape,label):
            base=comp.features.baseFeatures.add();assert base.startEdit();comp.bRepBodies.add(shape,base);assert base.finishEdit()
            body=base.bodies.item(0);body.name=label;return body
        def fixture(inside=True,rotated=False,narrow=False,thin=False):
            far=5.5 if narrow else 40;wall=.3 if thin else 3
            A=box(-wall,far,-30,30,-24,0);B=box(-wall,far,-30,30,.3,20.3)
            assert manager.booleanOperation(A,box(0,far-3,-27,27,-21,1),native.BooleanTypes.DifferenceBooleanType)
            assert manager.booleanOperation(B,box(0,far-3,-27,27,-1,17.3),native.BooleanTypes.DifferenceBooleanType)
            matrix=core.Matrix3D.create()
            if rotated:assert matrix.setToRotation(.73,core.Vector3D.create(1,1,1),core.Point3D.create(0,0,0))
            assert manager.transform(A,matrix) and manager.transform(B,matrix)
            A,B=persist(A,'Push-fit base'),persist(B,'Push-fit lid')
            inverse=matrix.copy();assert inverse.invert()
            def local(point):
                result=point.copy();assert result.transformBy(inverse);return (result.x*10,result.y*10,result.z*10)
            direction=core.Vector3D.create(1 if inside else -1,0,0);assert direction.transformBy(matrix)
            normal=(direction.x,direction.y,direction.z);plane=0 if inside else -wall
            def face(body):return next(f for f in body.faces if core.Plane.cast(f.geometry) is not None
                and abs(local(f.pointOnFace)[0]-plane)<1e-5 and adapter.hinge._dot(adapter.hinge._plane_normal(f),normal)>.999)
            faces=(face(A),face(B))
            edge=next(e for e in faces[0].edges if core.Line3D.cast(e.geometry) is not None
                and all(abs(local(v.geometry)[2])<1e-5 for v in (e.startVertex,e.endVertex)))
            return (A,B),faces,edge
        preset=settings.SnapFitSettings(snap_family='ball_detent',width_mm=6,thickness_mm=1.2,reach_mm=12,
            clearance_mm=.25,hook_depth_mm=.45,lead_in_mm=3,snap_count=2,start_margin_mm=5,end_margin_mm=5,
            root_length_mm=3,attachment_overlap_mm=.5,ball_radius_mm=1.25,chamfer_edges=True,chamfer_size_mm=.2,print_support=True)
        def witnesses(prepared):
            result=dict(prepared.result_bodies);count=0
            def point(x,y,z):return adapter.hinge._point(prepared.frame,x,y,z)
            def solid(body,x,y,z):return body.pointContainment(point(x,y,z))!=native.PointContainment.PointOutsidePointContainment
            for unit in prepared.plan.units:
                x,y,z=unit.ball_geometry.center_mm;r=unit.ball_geometry.radius_mm;c=prepared.settings.clearance_mm
                for dx,dz in ((-r+.04,0),(-r*.75,r*.45),(-r*.75,-r*.45)):
                    assert solid(result['A'],x+dx,y,z+dz)
                    assert not solid(result['B'],x+dx,y,z+dz);count+=2
                assert solid(result['B'],-prepared.settings.hook_depth_mm-c-.1,y,z);count+=1
                assert solid(result['A'],c+prepared.settings.thickness_mm/2,y,prepared.settings.reach_mm/2);count+=1
            return count
        for inside,rotated in ((True,False),(False,False),(True,True),(False,True)):
            targets,faces,edge=fixture(inside,rotated);clean=snapshot(design);started=time.perf_counter()
            prepared=adapter.prepare_snap_fit(design,*faces,edge,preset);checks=witnesses(prepared)
            assert snapshot(design)==clean
            if inside:
                # The global exterior-plane rule must reject this actual box;
                # successful preparation therefore exercises the new local guard.
                try:adapter._halfspaces(manager,prepared.frame,*targets)
                except ValueError:pass
                else:raise AssertionError('Internal fixture did not cross selected wall plane')
            graphics=comp.customGraphicsGroups.count;group=adapter.preview_snap_fit(prepared)
            assert group.isValid and group.deleteMe() and comp.customGraphicsGroups.count==graphics
            assert snapshot(design)==clean
            tokens=tuple(b.entityToken for b in targets);count=comp.bRepBodies.count;history=design.timeline.count
            anchor=adapter.create_snap_fit(design,prepared);target=adapter.read_edit_target(design,anchor)
            ids=dict(target.record.recipe['combines']);created_history=design.timeline.count
            changed=replace(preset,snap_count=3,hook_depth_mm=.55,ball_radius_mm=1.4)
            rebuilt=adapter.prepare_edit_snap_fit(design,target,changed);checks+=witnesses(rebuilt)
            adapter.rebuild_snap_fit(design,target,rebuilt);loaded=adapter.read_edit_target(design,anchor)
            assert loaded.settings==changed and dict(loaded.record.recipe['combines'])==ids
            assert tuple(b.entityToken for b in targets)==tokens and comp.bRepBodies.count==count and design.timeline.count==created_history
            report['cases'].append({'location':'inside' if inside else 'outside','rotated':rotated,
                'material_witnesses':checks,'create_rebuild_ms':round((time.perf_counter()-started)*1000,2),
                'same_bodies':True,'same_native_history':True,'preview_cleanup':True})
        for values,label in (({'narrow':True},'blocked_flex_space'),({'thin':True},'thin_root')):
            targets,faces,edge=fixture(**values);clean=snapshot(design)
            try:adapter.prepare_snap_fit(design,*faces,edge,preset)
            except ValueError as error:
                if label=='blocked_flex_space':assert 'empty space' in str(error)
                else:assert 'root' in str(error)
                report['cases'].append({'refused':label,'message':str(error)})
            else:raise AssertionError('Invalid push-fit accepted: '+label)
            assert snapshot(design)==clean
        report['success']=True
    finally:
        if owned is not None and owned.isValid:owned.close(False)
        if caller is not None and caller.isValid:caller.activate();app.activeViewport.camera=camera
        report['caller_unchanged']=snapshot(original)==before
        for key in tuple(sys.modules):
            if key==name or key.startswith(name+'.'):sys.modules.pop(key,None)
        if not report['caller_unchanged']:raise AssertionError('Caller model changed')
    return report

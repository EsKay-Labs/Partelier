"""Disposable exact-radius truss checks through the opt-in Fusion MCP add-in."""

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
    root=Path(__file__).resolve().parents[2];package=root/'Partelier/partelier';name='_partelier_truss_fillet_'+uuid.uuid4().hex
    spec=importlib.util.spec_from_file_location(name,package/'__init__.py',submodule_search_locations=[str(package)])
    module=importlib.util.module_from_spec(spec);sys.modules[name]=module;spec.loader.exec_module(module)
    a,settings,recipe,flat=[importlib.import_module(name+'.tools.patterns.'+leaf) for leaf in ('fusion','settings','recipe','flat_plate')]
    planner=importlib.import_module(name+'.tools.truss.planner')
    app=core.Application.get();caller=app.activeDocument;original=native.Design.cast(app.activeProduct)
    before=snapshot(original);camera=app.activeViewport.camera;owned=None
    report={'version':'0.22.0','fusion_version':app.version,'cases':[],'edits':[],'success':False}
    try:
        if app.userInterface.activeCommand not in ('','SelectCommand'):raise ValueError('Finish the active Fusion command first.')
        for key,value in tuple(sys.modules.items()):
            if key.endswith('partelier.addin'):
                for field in ('_hinge_commands','_snap_commands','_pattern_commands','_detail_commands'):
                    manager=getattr(value,field,None);state=manager.palette_state() if manager else {}
                    if state.get('sessionId') and state.get('phase') not in ('idle','created','cancelled'):
                        raise ValueError('Cancel the active Partelier preview before this disposable test.')
        owned=app.documents.add(core.DocumentTypes.FusionDesignDocumentType);design=native.Design.cast(app.activeProduct)
        if design.designType!=native.DesignTypes.ParametricDesignType:design.designType=native.DesignTypes.ParametricDesignType
        comp=design.rootComponent;manager=native.TemporaryBRepManager.get()
        def fixture(width=120,height=40,angle=0):
            shape=manager.createBox(core.OrientedBoundingBox3D.create(core.Point3D.create(0,0,.15),core.Vector3D.create(1,0,0),core.Vector3D.create(0,1,0),width/10,height/10,.3))
            if angle:
                matrix=core.Matrix3D.create();assert matrix.setToRotation(angle,core.Vector3D.create(1,0,0),core.Point3D.create(0,0,0))
                assert manager.transform(shape,matrix)
            base=comp.features.baseFeatures.add();assert base.startEdit();comp.bRepBodies.add(shape,base);assert base.finishEdit()
            body=base.bodies.item(0);body.name='Rounded truss plate'
            normal=(0,-math.sin(angle),math.cos(angle))
            face=next(f for f in body.faces if abs(f.area-width*height/100)<1e-6 and
                sum(x*y for x,y in zip(a.hinge._plane_normal(f),normal))>.999)
            return body,face
        def inspect(prepared,plate,layout):
            body=prepared.result_body;radius=prepared.settings.truss_fillet_mm;count=0
            if radius:
                cylinders=[core.Cylinder.cast(f.geometry) for f in body.faces if core.Cylinder.cast(f.geometry) is not None]
                assert len(cylinders)==3*len(layout.holes)
                assert all(abs(c.radius*10-radius)<1e-6 for c in cylinders)
                arcs=[core.Arc3D.cast(e.geometry) for e in body.edges if core.Arc3D.cast(e.geometry) is not None]
                assert len(arcs)==6*len(layout.holes) and all(abs(c.radius*10-radius)<1e-6 for c in arcs)
                for polygon,hole in zip(layout.holes,layout.rounded_holes):
                    assert not a._containment(body,plate.world(*hole.interior_point,-1.5));count+=1
                    for vertex,corner in zip(polygon,hole.corners):
                        direction=tuple((c-m)/radius for c,m in zip(corner.center,corner.middle))
                        epsilon=min(.015,math.dist(vertex,corner.middle)/5,radius/5)
                        for sign,material in ((-1,True),(1,False)):
                            point=tuple(m+sign*epsilon*d for m,d in zip(corner.middle,direction))
                            assert a._containment(body,plate.world(*point,-1.5))==material;count+=1
            else:
                assert all(core.Cylinder.cast(f.geometry) is None for f in body.faces)
            assert abs(body.volume-layout.material_area_mm2*3/1000)<1e-7
            return count
        body,face=fixture();defaults=settings.PatternSettings(pattern='truss_warren',layout_mode='fill',web_mm=2,border_mm=3)
        plate=flat.inspect(design,(face,),defaults,body)
        bounds=tuple(v for axis in (0,1) for v in (min(p[axis] for p in plate.outer),max(p[axis] for p in plate.outer)))
        clean=snapshot(design)
        for style in planner.STYLES:
            for axis in ('long','short'):
                values=replace(defaults,pattern=style,truss_axis=axis,truss_fillet_mm=.8 if axis=='long' else .3)
                start=time.perf_counter();prepared=a.prepare_pattern(design,(face,),values)
                layout=planner.plan(bounds,style,6,2,3,axis,values.truss_fillet_mm)
                checks=inspect(prepared,plate,layout);assert snapshot(design)==clean
                report['cases'].append({'style':style,'axis':axis,'radius_mm':values.truss_fillet_mm,
                    'prepare_and_verify_ms':round((time.perf_counter()-start)*1000,2),'arc_faces':3*len(layout.holes),'material_witnesses':checks})
        values=replace(defaults,truss_fillet_mm=.8);prepared=a.display_export.prepare(a.prepare_pattern(design,(face,),values))
        graphics=comp.customGraphicsGroups.count;group=a.preview_pattern(prepared)
        assert group.isValid and group.deleteMe() and comp.customGraphicsGroups.count==graphics and snapshot(design)==clean
        count=comp.bRepBodies.count;history=design.timeline.count;token=body.entityToken
        recipe.create_pattern(design,prepared);target=recipe.read_edit_target(design,body);feature=target.record.feature_id
        assert target.settings==values and target.recipe['version']==11 and design.timeline.count==history+2
        for style,radius in (('truss_pratt',.8),('truss_howe',1.2),('truss_warren',0),('truss_warren',1.0)):
            target=recipe.read_edit_target(design,body);changed=replace(target.settings,pattern=style,truss_fillet_mm=radius)
            candidate=recipe.prepare_edit_pattern(design,target,changed)
            checks=inspect(candidate,plate,planner.plan(bounds,style,6,2,3,'long',radius))
            recipe.rebuild_pattern(design,target,candidate);loaded=recipe.read_edit_target(design,body)
            assert loaded.settings==changed and loaded.record.feature_id==feature
            assert body.entityToken==token and comp.bRepBodies.count==count and design.timeline.count==history+2
            report['edits'].append({'style':style,'radius_mm':radius,'material_witnesses':checks})
        # Exact recipe10 sharp settings load without writing and upgrade on Rebuild.
        target=recipe.read_edit_target(design,body);zero=replace(target.settings,truss_fillet_mm=0)
        recipe.rebuild_pattern(design,target,recipe.prepare_edit_pattern(design,target,zero))
        target=recipe.read_edit_target(design,body);old=dict(target.recipe);old['version']=10
        old['settings']=dict(old['settings']);del old['settings']['truss_fillet_mm']
        raw=json.dumps(old,separators=(',',':'));assert target.anchor.attributes.add(recipe.GROUP,'recipe',raw)
        loaded=recipe.read_edit_target(design,body);assert loaded.settings.truss_fillet_mm==0
        assert loaded.anchor.attributes.itemByName(recipe.GROUP,'recipe').value==raw
        revised=replace(loaded.settings,truss_fillet_mm=.8)
        recipe.rebuild_pattern(design,loaded,recipe.prepare_edit_pattern(design,loaded,revised))
        assert recipe.read_edit_target(design,body).recipe['version']==11
        clean=snapshot(design)
        target=recipe.read_edit_target(design,body)
        try:recipe.prepare_edit_pattern(design,target,replace(target.settings,truss_fillet_mm=100))
        except ValueError as error:assert 'too large' in str(error);report['oversize_refusal']=str(error)
        else:raise AssertionError('Oversized junction fillet accepted')
        assert snapshot(design)==clean
        if (context or {}).get('screenshot'):
            camera2=app.activeViewport.camera;camera2.viewOrientation=core.ViewOrientations.IsoTopRightViewOrientation;camera2.isFitView=True
            app.activeViewport.camera=camera2;assert app.activeViewport.saveAsImageFile(context['screenshot'],1000,650)
        # Large and inclined cases are separate source plates, never extra result copies.
        for width,height,bays,angle in ((1000,100,64,0),(120,40,6,math.pi/3)):
            other,surface=fixture(width,height,angle);values=replace(defaults,pattern='truss_pratt',truss_bays=bays,web_mm=1,truss_fillet_mm=.5)
            before_case=snapshot(design);start=time.perf_counter();prepared=a.prepare_pattern(design,(surface,),values)
            chart=flat.inspect(design,(surface,),values,other)
            bounds2=tuple(v for axis in (0,1) for v in (min(p[axis] for p in chart.outer),max(p[axis] for p in chart.outer)))
            layout=planner.plan(bounds2,values.pattern,bays,1,3,'long',.5)
            checks=inspect(prepared,chart,layout);assert snapshot(design)==before_case
            report['cases'].append({'style':values.pattern,'bays':bays,'inclined':bool(angle),'radius_mm':.5,
                'prepare_and_verify_ms':round((time.perf_counter()-start)*1000,2),'arc_faces':3*len(layout.holes),'material_witnesses':checks})
        report.update(success=True,same_body_and_history=True,preview_cleanup=True,legacy_read_only_then_rebuild=True)
    finally:
        if owned is not None and owned.isValid:owned.close(False)
        if caller is not None and caller.isValid:caller.activate();app.activeViewport.camera=camera
        report['caller_unchanged']=snapshot(original)==before
        for key in tuple(sys.modules):
            if key==name or key.startswith(name+'.'):sys.modules.pop(key,None)
        if not report['caller_unchanged']:raise AssertionError('Caller model changed')
    return report

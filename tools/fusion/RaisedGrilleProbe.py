"""Small isolated checks callable through the opt-in Fusion MCP execute tool.

Each call owns and discards a fresh unsaved document. No user geometry is edited.
The MCP caller must keep the runtime stable until the call has returned.
"""

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
    return {'timeline':design.timeline.count if design.designType==native.DesignTypes.ParametricDesignType else None,'marker':design.timeline.markerPosition if design.designType==native.DesignTypes.ParametricDesignType else None,
        'bodies':[(b.entityToken,b.name,b.isLightBulbOn,round(b.volume,9),b.faces.count,b.edges.count)
                  for b in design.rootComponent.bRepBodies]}


def mounting_witnesses(adapter,body,settings,width,depth,thickness,timings):
    """Independent radial samples at the back bore and half-depth cone."""
    inset=timings['mount_inset_mm'];radius=timings['mount_hole_diameter_mm']/2
    sink=timings['mount_countersink_depth_mm'];head=timings['mount_head_diameter_mm']/2
    for x in (-width/2+inset,width/2-inset):
        for y in (-depth/2+inset,depth/2-inset):
            assert not adapter._containment(body,(x+radius-.04,y,.08))
            assert adapter._containment(body,(x+radius+.04,y,.08))
            if sink:
                at=thickness-sink/2;edge=(radius+head)/2
                assert not adapter._containment(body,(x+edge-.04,y,at))
                assert adapter._containment(body,(x+edge+.04,y,at))
                # The seat lies on the original face even below raised fins.
                assert not adapter._containment(body,(x,y,thickness+.05))


def louver_angles(body,settings,thickness):
    """Read actual analytic wall normals, independently of planner diagnostics."""
    angles=[]
    raised=settings.grille_profile!='flat'
    cap=(settings.grille_chamfer_mm or min(.6,settings.grille_height_mm/2,settings.web_mm/4,settings.border_mm/4)) if settings.grille_profile=='chamfer' else 0
    for face in body.faces:
        if face.geometry.surfaceType!=core.SurfaceTypes.PlaneSurfaceType:continue
        bounds=face.boundingBox
        # At zero tilt the fin wall heals into the original through opening.
        # It may start below the selected face; it must extend ABOVE that face
        # and end below the cap, distinguishing it from the external ramp.
        if raised and (bounds.maxPoint.z<=thickness/10+1e-7 or
                bounds.maxPoint.z>(thickness+settings.grille_height_mm-cap)/10+1e-7):continue
        ok,normal=face.evaluator.getNormalAtPoint(face.pointOnFace);assert ok
        angle=math.degrees(math.asin(min(1,abs(normal.z))))
        if angle>89.999 or bounds.maxPoint.z-bounds.minPoint.z<1e-5:continue
        angles.append(angle)
    assert angles,'No analytic grille walls were measured'
    expected=settings.louver_angle_deg
    assert any(abs(angle-expected)<1e-4 for angle in angles),(expected,angles)
    # Clipped ends project the shear onto the frame's own wall direction;
    # their tilt can be smaller than the main fin wall, never greater.
    assert all(angle<=expected+1e-4 for angle in angles),(expected,angles)
    return sorted(set(round(angle,5) for angle in angles))


def bevel_angles(body,settings,thickness):
    """Measure cap planes; mounting relief can also expose full-height walls."""
    top=(thickness+settings.grille_height_mm)/10;angles=[];mounting_walls=0
    size=settings.grille_chamfer_mm or min(.6,settings.grille_height_mm/2,settings.web_mm/4,settings.border_mm/4)
    for face in body.faces:
        if face.geometry.surfaceType!=core.SurfaceTypes.PlaneSurfaceType:continue
        bounds=face.boundingBox
        if abs(bounds.maxPoint.z-top)>1e-7 or bounds.maxPoint.z-bounds.minPoint.z<1e-5:continue
        ok,normal=face.evaluator.getNormalAtPoint(face.pointOnFace);assert ok
        angle=math.degrees(math.asin(min(1,abs(normal.z))))
        if settings.mount_mode!='off' and angle<1e-5 and bounds.minPoint.z<top-size/10-1e-7:
            mounting_walls+=1;continue
        assert abs(angle-45)<1e-4,(angle,bounds.minPoint.z,bounds.maxPoint.z)
        angles.append(angle)
    assert len(angles)>=4,'No bevel planes measured'
    return {'measured_planes':len(angles),'min_deg':min(angles),'max_deg':max(angles),'full_height_mounting_walls':mounting_walls}


def frame_ramp_witnesses(adapter,body,settings,width,depth,thickness,timings):
    """Probe both sides of the perimeter at three elevations, not just its cap."""
    base=timings['frame_base_inset_mm'];height=settings.grille_height_mm;checked=0
    for fraction in (.1,.5,.9):
        level=height*fraction;inset=base+level
        for axis,extent in ((0,width),(1,depth)):
            for sign in (-1,1):
                for delta,expected in ((-.03,False),(.03,True)):
                    point=[0.,0.,thickness+level];point[axis]=sign*(extent/2-inset-delta)
                    assert bool(adapter._containment(body,tuple(point)))==expected,(point,expected)
                    checked+=1
    full_height=0
    for face in body.faces:
        if face.geometry.surfaceType!=core.SurfaceTypes.PlaneSurfaceType:continue
        bounds=face.boundingBox
        if abs(bounds.minPoint.z-thickness/10)>1e-7 or abs(bounds.maxPoint.z-(thickness+height)/10)>1e-7:continue
        ok,normal=face.evaluator.getNormalAtPoint(face.pointOnFace);assert ok
        angle=math.degrees(math.asin(min(1,abs(normal.z))))
        if abs(angle-45)<1e-4:full_height+=1
    assert full_height>=4,full_height
    return {'inside_outside_samples':checked,'full_height_slope_faces':full_height,'height_mm':height,
        'base_inset_mm':base,'top_inset_mm':timings['frame_top_inset_mm']}


def border_witnesses(adapter,body,settings,width,depth,thickness,timings):
    """Independent solid witnesses at all four inner border limits, at 3 depths."""
    border=timings['mount_border_mm'];radius=timings['mount_head_diameter_mm']/2
    inset=timings['mount_inset_mm']
    centers=[(x,y) for x in (-width/2+inset,width/2-inset) for y in (-depth/2+inset,depth/2-inset)]
    points=[]
    for index in range(25):
        x=-width/2+.1+(width-.2)*index/24;y=-depth/2+.1+(depth-.2)*index/24
        points.extend(((x,-depth/2+border-.1),(x,depth/2-border+.1),(-width/2+border-.1,y),(width/2-border+.1,y)))
    count=0
    for x,y in points:
        if any(math.hypot(x-cx,y-cy)<=radius+.1 for cx,cy in centers):continue
        for z in (.08,thickness/2,thickness-.08):
            assert adapter._containment(body,(x,y,z)),(x,y,z,border)
            count+=1
    assert count>=20
    assert border>=settings.border_mm and border+1e-8>=inset+radius+1.2
    return count


def directional_witnesses(adapter,prepared,face,settings,thickness):
    """Interior aperture samples follow each bank's own physical shear."""
    from importlib import import_module
    flow=import_module(adapter.__package__+'.grille_styles').flow_uv
    chart=adapter.SurfaceMap(face);checked=0
    raised=settings.grille_profile!='flat';height=settings.grille_height_mm
    for cell in prepared.layouts[0].cells:
        direction=flow(settings,cell.center_mm,chart.bounds)
        for level in ((-thickness/2,height/2) if raised else (-thickness/2,)):
            shift=0 if level<0 and raised else abs(level)*math.tan(math.radians(settings.louver_angle_deg))
            uv=tuple(a+shift*b for a,b in zip(cell.center_mm,direction))
            if not (chart.bounds[0]+settings.border_mm+.01<uv[0]<chart.bounds[1]-settings.border_mm-.01
                    and chart.bounds[2]+settings.border_mm+.01<uv[1]<chart.bounds[3]-settings.border_mm-.01):continue
            sample=chart.sample(*uv);point=adapter._add(sample.point_mm,sample.normal,level)
            assert not adapter._containment(prepared.result_body,point),(settings.pattern,cell.center_mm,level,point)
            checked+=1
    assert checked>=2
    return checked


def run(context):
    context=context or {}
    root=Path(__file__).resolve().parents[2]
    name='_partelier_raised_probe_'+uuid.uuid4().hex
    package=root/'Partelier/partelier'
    spec=importlib.util.spec_from_file_location(name,package/'__init__.py',submodule_search_locations=[str(package)])
    module=importlib.util.module_from_spec(spec);sys.modules[name]=module;spec.loader.exec_module(module)
    adapter,settings_module,recipe=tuple(importlib.import_module(name+'.tools.patterns.'+leaf) for leaf in ('fusion','settings','recipe'))
    app=core.Application.get();caller=app.activeDocument;original=native.Design.cast(app.activeProduct)
    before=snapshot(original);camera=app.activeViewport.camera
    original_component=original.activeComponent if original else None
    report={'version':json.loads((root/'Partelier/Partelier.manifest').read_text(encoding='utf-8'))['version'],
        'fusion_version':app.version,'context':context,'success':False}
    owned=None
    try:
        if app.userInterface.activeCommand not in ('','SelectCommand'):
            raise RuntimeError('Finish the active Fusion command before running this probe.')
        owned=app.documents.add(core.DocumentTypes.FusionDesignDocumentType)
        design=native.Design.cast(app.activeProduct)
        if design.designType!=native.DesignTypes.ParametricDesignType:
            design.designType=native.DesignTypes.ParametricDesignType
        manager=native.TemporaryBRepManager.get()
        width=float(context.get('width_mm',60));depth=float(context.get('depth_mm',50));thickness=float(context.get('thickness_mm',3))
        shape=manager.createBox(core.OrientedBoundingBox3D.create(core.Point3D.create(0,0,thickness/20),
            core.Vector3D.create(1,0,0),core.Vector3D.create(0,1,0),width/10,depth/10,thickness/10))
        if context.get('stepped_back'):
            step=manager.createBox(core.OrientedBoundingBox3D.create(core.Point3D.create(width/40,0,-.04),
                core.Vector3D.create(1,0,0),core.Vector3D.create(0,1,0),width/40,depth/20,.1))
            assert manager.booleanOperation(shape,step,native.BooleanTypes.UnionBooleanType)
        base=design.rootComponent.features.baseFeatures.add();assert base.startEdit()
        body=design.rootComponent.bRepBodies.add(shape,base);assert base.finishEdit()
        body=base.bodies.item(0);body.name='Raised grille fixture'
        original_volume=float(body.volume)
        token=body.entityToken
        face=next(f for f in body.faces if abs(f.pointOnFace.z-thickness/10)<1e-7)
        settings=settings_module.PatternSettings(pattern=context.get('pattern','grille_parallel'),layout_mode='fill',
            pitch_mm=7,web_mm=2,border_mm=context.get('border_mm',7),rotation_deg=context.get('rotation_deg',0),
            grille_profile=context.get('profile','raised'),grille_height_mm=context.get('height_mm',3),
            louver_angle_deg=context.get('louver_angle_deg',45))
        settings=replace(settings,pattern_fillet_mm=context.get('pattern_fillet_mm',0),grille_chamfer_mm=context.get('grille_chamfer_mm',0))
        settings=replace(settings,**{key:value for key,value in context.items() if key.startswith('mount_') and key in settings.to_dict()})
        if context.get('expect_refusal'):
            clean=snapshot(design)
            try:adapter.prepare_pattern(design,(face,),settings)
            except ValueError as error:
                assert context['expect_refusal'].lower() in str(error).lower(),str(error)
                assert snapshot(design)==clean
                report.update(success=True,expected_refusal=str(error),model_unchanged_before_cleanup=True)
                return report
            raise AssertionError('Unsupported geometry was accepted')
        prior=None
        if context.get('promote'):
            flat=replace(settings,grille_profile='flat')
            initial=adapter.prepare_pattern(design,(face,),flat)
            recipe.create_pattern(design,initial)
            prior=recipe.read_edit_target(design,body)
            assert prior.record.recipe['version']==2
            original_base=prior.anchor
            original_cut=design.findEntityByToken(prior.record.recipe['combines']['cut'])[0]
        start=time.perf_counter()
        prepared=recipe.prepare_edit_pattern(design,prior,settings) if prior else adapter.prepare_pattern(design,(face,),settings)
        report['prepare_ms']=(time.perf_counter()-start)*1000
        report['openings']=prepared.cell_count;report['timings']=prepared.timings
        if settings.grille_profile=='chamfer':report['analytic_bevel_angles']=bevel_angles(prepared.result_body,settings,thickness)
        if settings.grille_profile=='chamfer':report['frame_ramp_witnesses']=frame_ramp_witnesses(adapter,prepared.result_body,settings,width,depth,thickness,prepared.timings)
        if settings.pattern in ('grille_louver','grille_deflection','grille_diffuser'):
            report['analytic_wall_angles']=louver_angles(prepared.result_body,settings,thickness)
        assert body==design.findEntityByToken(token)[0] and design.rootComponent.bRepBodies.count==1
        assert abs(prepared.result_body.boundingBox.minPoint.z)<1e-7
        raised=settings.grille_profile!='flat'
        top_height=thickness+(settings.grille_height_mm if raised else 0)
        assert abs(prepared.result_body.boundingBox.maxPoint.z-top_height/10)<1e-7
        # Saved face references are historical during Edit; witnesses retained
        # by preparation already carry world coordinates after restoring history.
        for sample in prepared.accepted_samples[:3]:
            point=adapter._add(sample['point_mm'],sample['normal'],-thickness/2)
            if settings.mount_mode=='off' and settings.pattern not in ('grille_deflection','grille_diffuser'):assert not adapter._containment(prepared.result_body,point)
        if settings.pattern in ('grille_deflection','grille_diffuser'):
            report['directional_aperture_witnesses']=directional_witnesses(adapter,prepared,face,settings,thickness)
        if settings.mount_mode!='off':
            mounting_witnesses(adapter,prepared.result_body,settings,width,depth,thickness,prepared.timings)
            report['mount_bore_and_seat_witnesses']=4
            report['solid_border_witnesses']=border_witnesses(adapter,prepared.result_body,settings,width,depth,thickness,prepared.timings)
            assert prepared.timings['mount_border_restores']==0
        report['through_opening_witnesses']=min(3,len(prepared.accepted_samples)) if settings.mount_mode=='off' else 0
        if context.get('preview'):
            clean=snapshot(design);graphics=design.rootComponent.customGraphicsGroups.count
            prepared=adapter.display_export.prepare(prepared)
            group=adapter.preview_pattern(prepared)
            assert group.isValid
            assert group.deleteMe()
            assert snapshot(design)==clean and design.rootComponent.customGraphicsGroups.count==graphics
            report.update(cached_preview_draw_cleanup=True,preview_triangles=prepared.display_mesh.triangle_count)
        history=design.timeline.count
        start=time.perf_counter()
        anchor=recipe.rebuild_pattern(design,prior,prepared) if prior else recipe.create_pattern(design,prepared)
        if context.get('history'):
            operation_history=importlib.import_module(name+'.operations')
            operation_history.capture(design,anchor,'pattern',settings.to_dict(),history,editing=prior is not None)
        report['create_ms']=(time.perf_counter()-start)*1000
        assert design.rootComponent.bRepBodies.count==1 and design.findEntityByToken(token)[0]==body
        features=1 if prior else 3 if raised else 2
        assert design.timeline.count==history+features
        target=recipe.read_edit_target(design,body)
        assert target.settings==settings and target.record.recipe['version']==(1 if raised or prior else 2)
        if context.get('legacy_mount'):
            unchanged=snapshot(design)
            legacy=json.loads(target.anchor.attributes.itemByName(recipe.GROUP,'recipe').value);legacy['settings']={k:v for k,v in legacy['settings'].items() if not k.startswith('truss_') and k not in ('pattern_fillet_mm','grille_chamfer_mm')};legacy['version']=8
            raw=json.dumps(legacy,separators=(',',':'));assert target.anchor.attributes.add(recipe.GROUP,'recipe',raw)
            target=recipe.read_edit_target(design,body)
            assert target.recipe==legacy and target.settings==settings and snapshot(design)==unchanged
            assert 'minimum border' in recipe.edit_notice(target)
            report['legacy_mount_read_without_model_changes']=True
        if context.get('legacy_raised'):
            unchanged=snapshot(design)
            saved=target.anchor.attributes.itemByName(recipe.GROUP,'recipe').value
            legacy=json.loads(saved);legacy['settings']={k:v for k,v in legacy['settings'].items() if not k.startswith('truss_') and k not in ('pattern_fillet_mm','grille_chamfer_mm')};legacy['version']=7;legacy['settings']['louver_angle_deg']=0
            raw=json.dumps(legacy,separators=(',',':'))
            assert target.anchor.attributes.add(recipe.GROUP,'recipe',raw)
            target=recipe.read_edit_target(design,body)
            assert target.settings.louver_angle_deg==45 and target.recipe==legacy
            assert snapshot(design)==unchanged
            assert target.anchor.attributes.itemByName(recipe.GROUP,'recipe').value==raw
            report['legacy_dormant_angle_restored_to_actual_45_without_model_changes']=True
        if prior:
            assert target.anchor==original_base and target.record.feature_id==prior.record.feature_id
            assert not original_cut.isValid
            report['flat_to_raised_same_owned_history']=True
        settings=replace(settings,grille_height_mm=settings.grille_height_mm+.4)
        start=time.perf_counter();changed=recipe.prepare_edit_pattern(design,target,settings)
        recipe.rebuild_pattern(design,target,changed)
        report['edit_rebuild_ms']=(time.perf_counter()-start)*1000
        assert design.rootComponent.bRepBodies.count==1 and design.findEntityByToken(token)[0]==body
        assert design.timeline.count==history+features and body.name=='Raised grille fixture'
        assert recipe.read_edit_target(design,body).settings==settings
        if settings.grille_profile=='chamfer':report['rebuilt_bevel_angles']=bevel_angles(body,settings,thickness)
        if settings.grille_profile=='chamfer':report['rebuilt_frame_ramp_witnesses']=frame_ramp_witnesses(adapter,body,settings,width,depth,thickness,changed.timings)
        assert abs(body.boundingBox.minPoint.z)<1e-7
        assert abs(body.boundingBox.maxPoint.z-(thickness+(settings.grille_height_mm if raised else 0))/10)<1e-7
        if settings.mount_mode!='off':
            mounting_witnesses(adapter,body,settings,width,depth,thickness,changed.timings)
            border_witnesses(adapter,body,settings,width,depth,thickness,changed.timings)
        if context.get('mount_screw_cycle'):
            unchanged_volume=float(body.volume);report['mount_screw_cycle']=[]
            for screw,mode in (('M3','plain'),('M6','plain'),('M4','countersink')):
                target=recipe.read_edit_target(design,body);revised=replace(settings,mount_screw=screw,mount_mode=mode)
                staged=recipe.prepare_edit_pattern(design,target,revised);recipe.rebuild_pattern(design,target,staged)
                assert design.rootComponent.bRepBodies.count==1 and design.timeline.count==history+features
                assert design.findEntityByToken(token)[0]==body and recipe.read_edit_target(design,body).settings==revised
                mounting_witnesses(adapter,body,revised,width,depth,thickness,staged.timings)
                border_witnesses(adapter,body,revised,width,depth,thickness,staged.timings)
                report['mount_screw_cycle'].append({'screw':screw,'border_mm':staged.timings['mount_border_mm']})
            assert abs(body.volume-unchanged_volume)<1e-8
        if context.get('tilt_edit_cycle'):
            report['tilt_edit_cycle']=[]
            for tilt in (0,20,45):
                target=recipe.read_edit_target(design,body)
                revised=replace(settings,louver_angle_deg=tilt)
                staged=recipe.prepare_edit_pattern(design,target,revised)
                recipe.rebuild_pattern(design,target,staged)
                assert design.rootComponent.bRepBodies.count==1 and design.timeline.count==history+features
                assert design.findEntityByToken(token)[0]==body and body.name=='Raised grille fixture'
                assert recipe.read_edit_target(design,body).settings==revised
                measured=louver_angles(body,revised,thickness)
                if revised.mount_mode!='off':mounting_witnesses(adapter,body,revised,width,depth,thickness,staged.timings)
                report['tilt_edit_cycle'].append({'requested':tilt,'measured_wall_angles':measured,
                    'bevel_angles':bevel_angles(body,revised,thickness) if revised.grille_profile=='chamfer' else None})
        if context.get('chamfer_edit_cycle'):
            report['chamfer_edit_cycle']=[]
            for size in (.25,.7,0):
                target=recipe.read_edit_target(design,body);revised=replace(settings,grille_chamfer_mm=size)
                staged=recipe.prepare_edit_pattern(design,target,revised);recipe.rebuild_pattern(design,target,staged)
                assert design.rootComponent.bRepBodies.count==1 and design.timeline.count==history+features
                assert design.findEntityByToken(token)[0]==body and recipe.read_edit_target(design,body).settings==revised
                report['chamfer_edit_cycle'].append({'requested_mm':size,'actual_mm':staged.timings['chamfer_size_mm'],
                    'bevel_angles':bevel_angles(body,revised,thickness)})
        if context.get('inset_edit_cycle'):
            report['inset_edit_cycle']=[]
            for inset in (6.628,8.25,0):
                target=recipe.read_edit_target(design,body);revised=replace(settings,mount_inset_mm=inset)
                staged=recipe.prepare_edit_pattern(design,target,revised);recipe.rebuild_pattern(design,target,staged)
                assert design.rootComponent.bRepBodies.count==1 and design.timeline.count==history+features
                assert design.findEntityByToken(token)[0]==body and recipe.read_edit_target(design,body).settings==revised
                mounting_witnesses(adapter,body,revised,width,depth,thickness,staged.timings)
                border_witnesses(adapter,body,revised,width,depth,thickness,staged.timings)
                report['inset_edit_cycle'].append({'requested_mm':inset,'actual_mm':staged.timings['mount_inset_mm'],
                    'border_mm':staged.timings['mount_border_mm']})
        if context.get('mount_edit_cycle'):
            unchanged_volume=float(body.volume)
            for mode in ('plain','countersink','off'):
                target=recipe.read_edit_target(design,body)
                revised=replace(settings,mount_mode=mode)
                staged=recipe.prepare_edit_pattern(design,target,revised)
                recipe.rebuild_pattern(design,target,staged)
                if mode!='off':mounting_witnesses(adapter,body,revised,width,depth,thickness,staged.timings)
                assert design.rootComponent.bRepBodies.count==1 and design.timeline.count==history+features
            assert abs(body.volume-unchanged_volume)<1e-8
            report['mount_edit_cycle']=['off','plain','countersink','off']
        if context.get('conversion'):
            # Return to flat and then convert a separately created Cut record.
            target=recipe.read_edit_target(design,body)
            flat=replace(settings,grille_profile='flat',pattern='grille_parallel')
            recipe.rebuild_pattern(design,target,recipe.prepare_edit_pattern(design,target,flat))
            assert abs(body.boundingBox.maxPoint.z-thickness/10)<1e-7
            report['raised_to_flat']=True
        app.activeViewport.fit()
        picture=context.get('screenshot')
        if picture:
            camera_fixture=app.activeViewport.camera;camera_fixture.viewOrientation=core.ViewOrientations.IsoTopRightViewOrientation
            camera_fixture.isFitView=True;app.activeViewport.camera=camera_fixture
            assert app.activeViewport.saveAsImageFile(str(picture),900,650)
        if context.get('history'):
            operation_history.capture(design,anchor,'pattern',recipe.read_edit_target(design,body).settings.to_dict(),design.timeline.count,editing=True)
            saved=operation_history.snapshot(design);assert len(saved)==1 and saved[0]['alias']=='grilles'
            operation_history.delete(design,saved[0]['id'])
            assert not operation_history.snapshot(design) and body.isValid and design.findEntityByToken(token)[0]==body
            assert design.rootComponent.bRepBodies.count==1 and abs(body.volume-original_volume)<1e-9
            report.update(named_group_edit_delete=True,delete_restored_source=True)
        report.update(success=True,same_body=True,flat_back=True,owned_features=3 if raised or prior else 2)
    finally:
        if owned is not None and owned.isValid:owned.close(False)
        if caller is not None and caller.isValid:caller.activate();app.activeViewport.camera=camera
        report['caller_document_unchanged']=app.activeDocument==caller and snapshot(original)==before and (original is None or original.activeComponent==original_component)
        report['discarded_without_saving']=owned is None or not owned.isValid
        report['source_sha256']={p.relative_to(root).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
            for p in package.rglob('*.py')}
        output=context.get('report_path')
        if output:Path(output).write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
        for key in tuple(sys.modules):
            if key==name or key.startswith(name+'.'):sys.modules.pop(key,None)
    assert report['caller_document_unchanged'] and report['discarded_without_saving']
    print(json.dumps({key:value for key,value in report.items() if key!='source_sha256'}))
    return report

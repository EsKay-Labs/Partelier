"""Small isolated checks callable through the opt-in Fusion MCP execute tool.

Each call owns and discards a fresh unsaved document. No user geometry is edited.
The MCP caller must keep the runtime stable until the call has returned.
"""

from dataclasses import replace
import hashlib
import importlib
import importlib.util
import json
from pathlib import Path
import sys
import time
import uuid
import adsk.core as core
import adsk.fusion as native


def snapshot(design):
    if design is None:return None
    return {'timeline':design.timeline.count,'marker':design.timeline.markerPosition,
        'bodies':[(b.entityToken,b.name,b.isLightBulbOn,round(b.volume,9),b.faces.count,b.edges.count)
                  for b in design.rootComponent.bRepBodies]}


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
    report={'version':'0.15.0','fusion_version':app.version,'context':context,'success':False}
    owned=None
    try:
        if app.userInterface.activeCommand not in ('','SelectCommand'):
            raise RuntimeError('Finish the active Fusion command before running this probe.')
        owned=app.documents.add(core.DocumentTypes.FusionDesignDocumentType)
        design=native.Design.cast(app.activeProduct)
        if design.designType!=native.DesignTypes.ParametricDesignType:
            design.designType=native.DesignTypes.ParametricDesignType
        manager=native.TemporaryBRepManager.get()
        width=float(context.get('width_mm',60));depth=float(context.get('depth_mm',50));thickness=3.
        shape=manager.createBox(core.OrientedBoundingBox3D.create(core.Point3D.create(0,0,thickness/20),
            core.Vector3D.create(1,0,0),core.Vector3D.create(0,1,0),width/10,depth/10,thickness/10))
        if context.get('stepped_back'):
            step=manager.createBox(core.OrientedBoundingBox3D.create(core.Point3D.create(width/40,0,-.04),
                core.Vector3D.create(1,0,0),core.Vector3D.create(0,1,0),width/40,depth/20,.1))
            assert manager.booleanOperation(shape,step,native.BooleanTypes.UnionBooleanType)
        base=design.rootComponent.features.baseFeatures.add();assert base.startEdit()
        body=design.rootComponent.bRepBodies.add(shape,base);assert base.finishEdit()
        body=base.bodies.item(0);body.name='Raised grille fixture'
        token=body.entityToken
        face=next(f for f in body.faces if abs(f.pointOnFace.z-thickness/10)<1e-7)
        settings=settings_module.PatternSettings(pattern=context.get('pattern','grille_parallel'),layout_mode='fill',
            pitch_mm=7,web_mm=2,border_mm=7,rotation_deg=context.get('rotation_deg',0),
            grille_profile=context.get('profile','raised'),grille_height_mm=context.get('height_mm',3))
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
        assert body==design.findEntityByToken(token)[0] and design.rootComponent.bRepBodies.count==1
        assert abs(prepared.result_body.boundingBox.minPoint.z)<1e-7
        assert abs(prepared.result_body.boundingBox.maxPoint.z-(thickness+settings.grille_height_mm)/10)<1e-7
        # Saved face references are historical during Edit; witnesses retained
        # by preparation already carry world coordinates after restoring history.
        for sample in prepared.accepted_samples[:3]:
            assert not adapter._containment(prepared.result_body,adapter._add(sample['point_mm'],sample['normal'],-thickness/2))
        report['through_opening_witnesses']=min(3,len(prepared.layouts[0].cells))
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
        report['create_ms']=(time.perf_counter()-start)*1000
        assert design.rootComponent.bRepBodies.count==1 and design.findEntityByToken(token)[0]==body
        features=1 if prior else 3
        assert design.timeline.count==history+features
        target=recipe.read_edit_target(design,body)
        assert target.settings==settings and target.record.recipe['version']==1
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
        assert abs(body.boundingBox.minPoint.z)<1e-7
        assert abs(body.boundingBox.maxPoint.z-(thickness+settings.grille_height_mm)/10)<1e-7
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
        report.update(success=True,same_body=True,flat_back=True,owned_features=3)
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

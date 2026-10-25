"""Small disposable native check for named history; never edits caller geometry."""

import importlib.util
import importlib
import json
from dataclasses import replace
from pathlib import Path
import sys
import uuid
import adsk.core as core
import adsk.fusion as native


def state(design):
    return (design.timeline.count, design.timeline.markerPosition,
            [(b.entityToken,b.name,b.isLightBulbOn,round(b.volume,9)) for b in design.rootComponent.bRepBodies])


def run(context):
    root=Path(__file__).resolve().parents[2]
    name='_partelier_history_probe_'+uuid.uuid4().hex
    package=root/'Partelier/partelier'
    spec=importlib.util.spec_from_file_location(name,package/'__init__.py',submodule_search_locations=[str(package)])
    module=importlib.util.module_from_spec(spec);sys.modules[name]=module;spec.loader.exec_module(module)
    operations=importlib.import_module(name+'.operations')
    adapter=importlib.import_module(name+'.tools.details.fusion')
    store=importlib.import_module(name+'.tools.details.store')
    settings_module=importlib.import_module(name+'.tools.details.settings')
    app=core.Application.get();caller=app.activeDocument;original=native.Design.cast(app.activeProduct)
    before=state(original) if original else None
    camera=app.activeViewport.camera;owned=None
    report={'success':False,'version':'0.19.0','fusion_version':app.version}
    try:
        if app.userInterface.activeCommand not in ('','SelectCommand'):
            raise ValueError('Finish the current Fusion command before this disposable check.')
        for key,value in tuple(sys.modules.items()):
            if key.endswith('partelier.addin'):
                for field in ('_hinge_commands','_snap_commands','_pattern_commands','_detail_commands'):
                    manager=getattr(value,field,None)
                    snapshot=manager.palette_state() if manager else {}
                    if snapshot.get('sessionId') and snapshot.get('phase') not in ('idle','created','cancelled'):
                        raise ValueError('Cancel the active Partelier preview before this disposable check.')
        owned=app.documents.add(core.DocumentTypes.FusionDesignDocumentType)
        design=native.Design.cast(app.activeProduct);design.designType=native.DesignTypes.ParametricDesignType
        comp=design.rootComponent;manager=native.TemporaryBRepManager.get()
        def box(x0,x1,y0,y1,z0,z1):
            return manager.createBox(core.OrientedBoundingBox3D.create(core.Point3D.create((x0+x1)/20,(y0+y1)/20,(z0+z1)/20),
                core.Vector3D.create(1,0,0),core.Vector3D.create(0,1,0),(x1-x0)/10,(y1-y0)/10,(z1-z0)/10))
        def persist(shape,label):
            feature=comp.features.baseFeatures.add();assert feature.startEdit();comp.bRepBodies.add(shape,feature)
            assert feature.finishEdit();body=feature.bodies.item(0);body.name=label;return body
        if (context or {}).get('case','lid')!='lid':
            report.update(other_case(design,name,operations,adapter,box,persist,context['case']))
            report['success']=True
            return report
        shape=box(-30,30,-20,20,-5,0)
        assert manager.booleanOperation(shape,box(-26,26,-16,16,-4,1),native.BooleanTypes.DifferenceBooleanType)
        a=persist(shape,'History base');b=persist(box(-30,30,-20,20,.25,6.25),'History lid')
        clean=state(design)
        faces=(next(f for f in a.faces if abs(f.pointOnFace.z)<1e-7 and adapter._normal(f)[2]>.99),
               next(f for f in b.faces if abs(f.pointOnFace.z-.025)<1e-7 and adapter._normal(f)[2]<-.99))
        settings=settings_module.DetailSettings()
        prepared=adapter.prepare(design,faces,settings)
        start=design.timeline.count;anchor=store.apply(prepared)
        operations.capture(design,anchor,'detail',settings.to_dict(),start)
        listing=operations.snapshot(design);assert len(listing)==1 and listing[0]['alias']=='lid' and listing[0]['canDelete']
        identity=listing[0]['id'];group=design.timeline.timelineGroups.item(0)
        assert group.count==3
        names=[group.item(i).entity.name for i in range(group.count)]
        assert 'Lip · History base' in names[1] and 'Groove · History lid' in names[2]
        report['separate_features']=names;report['group_name']=group.name
        assert len(operations._members(design,operations.resolve(design,identity)))==3
        group.isCollapsed=True
        assert len(operations.snapshot(design))==1
        record=store.read(design,anchor,'lid');assert not group.isCollapsed
        changed=replace(settings,lip_height_mm=3)
        edited=store.prepare_edit(design,record,changed);store.apply(edited)
        operations.capture(design,anchor,'detail',changed.to_dict(),design.timeline.count,editing=True)
        assert len(operations.snapshot(design))==1 and design.timeline.timelineGroups.count==1
        assert store.read(design,anchor,'lid').settings==changed
        report['collapsed_group_edit_rebuild']=True
        extra=comp.features.baseFeatures.add();extra.name='Unrelated later feature'
        try:operations.delete(design,identity)
        except ValueError as error:assert 'later features' in str(error)
        else:raise AssertionError('Deletion accepted a later unrelated feature')
        assert extra.isValid and a.isValid and b.isValid
        assert extra.deleteMe()
        operations.delete(design,identity)
        assert not operations.snapshot(design)
        assert a.isValid and b.isValid and state(design)==clean
        report['exact_operation_delete_and_source_preservation']=True
        report['later_feature_delete_refused']=True
        report['success']=True
    finally:
        if owned is not None:owned.close(False)
        if caller is not None and caller.isValid:caller.activate();app.activeViewport.camera=camera
        report['caller_unchanged']=(state(original)==before if original else True)
        for key in list(sys.modules):
            if key==name or key.startswith(name+'.'):sys.modules.pop(key,None)
        output=Path((context or {}).get('report_path',str(root/'output/selection-history/native.json')))
        output.parent.mkdir(parents=True,exist_ok=True)
        output.write_text(json.dumps(report,indent=2),encoding='utf-8')
        print(json.dumps(report))


def other_case(design,name,operations,detail_adapter,box,persist,case):
    comp=design.rootComponent
    if case in ('hinge','hinge_separate','snap'):
        adapter=importlib.import_module(name+'.tools.'+('hinge' if case.startswith('hinge') else 'snap_fit')+'.fusion')
        config=importlib.import_module(name+'.tools.'+('hinge' if case.startswith('hinge') else 'snap_fit')+'.settings')
        if case.startswith('hinge'):
            a=persist(box(-24,-4,-25,25,-4,0),'Hinge A');b=persist(box(4,24,-25,25,-4,0),'Hinge B')
            faces=tuple(next(f for f in body.faces if abs(f.pointOnFace.z)<1e-7 and detail_adapter._normal(f)[2]>.99) for body in (a,b))
            edge=next(e for e in faces[0].edges if abs(e.startVertex.geometry.x+.4)<1e-7 and abs(e.endVertex.geometry.x+.4)<1e-7)
            settings=config.HingeSettings(output_mode='separate' if case=='hinge_separate' else 'attached',chamfer_edges=False,fillet_edges=False,rotation_clearance_mm=0,web_profile='flat')
            prepared=adapter.prepare_hinge(design,*faces,edge,settings)
            create=lambda:adapter.create_hinge(design,prepared)
            read=lambda anchor:adapter.read_edit_target(design,anchor)
            changed=replace(settings,length_mm=36)
            rebuild=lambda target:adapter.rebuild_hinge(design,target,adapter.prepare_edit_hinge(design,target,changed))
        else:
            a=persist(box(-3,0,-30,30,-24,0),'Snap A');b=persist(box(-3,0,-30,30,0,24),'Snap B')
            faces=tuple(next(f for f in body.faces if abs(f.pointOnFace.x)<1e-7 and detail_adapter._normal(f)[0]>.99) for body in (a,b))
            edge=next(e for e in faces[0].edges if abs(e.startVertex.geometry.z)<1e-7 and abs(e.endVertex.geometry.z)<1e-7)
            settings=config.SnapFitSettings(chamfer_edges=False)
            prepared=adapter.prepare_snap_fit(design,*faces,edge,settings)
            create=lambda:adapter.create_snap_fit(design,prepared)
            read=lambda anchor:adapter.read_edit_target(design,anchor)
            changed=replace(settings,width_mm=9)
            rebuild=lambda target:adapter.rebuild_snap_fit(design,target,adapter.prepare_edit_snap_fit(design,target,changed))
        tool='hinge' if case.startswith('hinge') else case
    elif case in ('alignment','ribs','legacy_lid'):
        adapter=detail_adapter;store=importlib.import_module(name+'.tools.details.store')
        config=importlib.import_module(name+'.tools.details.settings')
        if case in ('alignment','legacy_lid'):
            manager=native.TemporaryBRepManager.get();shape=box(-30,30,-20,20,-5,0)
            assert manager.booleanOperation(shape,box(-26,26,-16,16,-4,1),native.BooleanTypes.DifferenceBooleanType)
            a=persist(shape,'Pin base');b=persist(box(-30,30,-20,20,.25,6.25),'Pin lid')
            faces=(next(f for f in a.faces if abs(f.pointOnFace.z)<1e-7 and adapter._normal(f)[2]>.99),next(f for f in b.faces if abs(f.pointOnFace.z-.025)<1e-7 and adapter._normal(f)[2]<-.99))
        else:
            manager=native.TemporaryBRepManager.get();shape=box(-3,40,-30,30,-3,0)
            assert manager.booleanOperation(shape,box(-3,0,-30,30,0,30),native.BooleanTypes.UnionBooleanType)
            a=b=persist(shape,'Rib support')
            faces=(next(f for f in a.faces if abs(f.pointOnFace.x)<1e-7 and adapter._normal(f)[0]>.99),next(f for f in a.faces if abs(f.pointOnFace.z)<1e-7 and adapter._normal(f)[2]>.99))
        settings=config.DetailSettings(kind='lid' if case=='legacy_lid' else case);prepared=adapter.prepare(design,faces,settings)
        create=lambda:store.apply(prepared);read=lambda anchor:store.read(design,anchor,settings.kind)
        changed=replace(settings,lip_height_mm=3) if case=='legacy_lid' else replace(settings,pin_count=4) if case=='alignment' else replace(settings,rib_count=4)
        rebuild=lambda target:store.apply(store.prepare_edit(design,target,changed))
        tool='detail'
    else:
        adapter=importlib.import_module(name+'.tools.patterns.fusion');recipe=importlib.import_module(name+'.tools.patterns.recipe');config=importlib.import_module(name+'.tools.patterns.settings')
        a=b=persist(box(-30,30,-20,20,-3,0),'Pattern plate')
        faces=(next(f for f in a.faces if abs(f.pointOnFace.z)<1e-7 and detail_adapter._normal(f)[2]>.99),)
        settings=config.PatternSettings(pattern='grille_cross' if case in ('grilles','grille_promotion') else 'truss_warren' if case=='truss' else 'circle',layout_mode='fill',pitch_mm=15,web_mm=2,border_mm=5,truss_bays=4)
        prepared=adapter.prepare_pattern(design,faces,settings)
        create=lambda:recipe.create_pattern(design,prepared);read=lambda anchor:recipe.read_edit_target(design,anchor)
        changed=replace(settings,grille_profile='raised',grille_height_mm=2) if case=='grille_promotion' else replace(settings,mode='inlay',depth_mm=1) if case=='colour_conversion' else replace(settings,web_mm=2.5)
        rebuild=lambda target:recipe.rebuild_pattern(design,target,recipe.prepare_edit_pattern(design,target,changed))
        tool='pattern'
    clean=state(design);start=design.timeline.count;anchor=create()
    if case!='legacy_lid':operations.capture(design,anchor,tool,settings.to_dict(),start)
    listing=operations.snapshot(design);assert len(listing)==1 and listing[0]['canDelete']==(case!='legacy_lid')
    identity=listing[0]['id'];group=design.timeline.timelineGroups.item(0) if case!='legacy_lid' else None
    if group is not None:group.isCollapsed=True
    target=read(anchor)
    if group is not None:assert not group.isCollapsed
    anchor=rebuild(target);operations.capture(design,anchor,tool,changed.to_dict(),design.timeline.count,editing=True)
    assert len(operations.snapshot(design))==1
    assert read(anchor).settings==changed
    if case=='colour_conversion':
        target=read(anchor);anchor=recipe.rebuild_pattern(design,target,recipe.prepare_edit_pattern(design,target,settings))
        operations.capture(design,anchor,tool,settings.to_dict(),design.timeline.count,editing=True)
        assert read(anchor).settings==settings
    count=len(operations._members(design,operations.resolve(design,identity)))
    operations.delete(design,identity)
    assert not operations.snapshot(design) and state(design)==clean and a.isValid and b.isValid
    return {'case':case,'group_edit_delete':True,'owned_native_features':count,'source_bodies_preserved':True}

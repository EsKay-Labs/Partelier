"""Disposable native geometry/picking regression for selected rectangular lips."""

from dataclasses import replace
import importlib,importlib.util,json,sys,time,uuid
from pathlib import Path
from types import SimpleNamespace
import adsk.core as core
import adsk.fusion as native


def snapshot(design):
    if design is None:return None
    timeline=(design.timeline.count,design.timeline.markerPosition) if design.designType==native.DesignTypes.ParametricDesignType else None
    return (timeline,[(b.entityToken,b.name,b.isLightBulbOn,round(b.volume,9)) for b in design.rootComponent.bRepBodies])


def run(context):
    root=Path(__file__).resolve().parents[2];name='_partelier_sides_probe_'+uuid.uuid4().hex
    package=root/'Partelier/partelier'
    spec=importlib.util.spec_from_file_location(name,package/'__init__.py',submodule_search_locations=[str(package)])
    module=importlib.util.module_from_spec(spec);sys.modules[name]=module;spec.loader.exec_module(module)
    settings,adapter,store,command,selection=[importlib.import_module(name+'.tools.details.'+leaf)
        for leaf in ('settings','fusion','store','command','side_selection')]
    app=core.Application.get();caller=app.activeDocument;original=native.Design.cast(app.activeProduct)
    before=snapshot(original);camera=app.activeViewport.camera;owned=None;session=None;owner=None
    report={'version':'0.21.0','fusion_version':app.version,'success':False,'cases':[]}
    try:
        if app.userInterface.activeCommand not in ('','SelectCommand'):raise ValueError('Finish the active command first.')
        for key,value in tuple(sys.modules.items()):
            if key.endswith('partelier.addin'):
                for field in ('_hinge_commands','_snap_commands','_pattern_commands','_detail_commands'):
                    manager=getattr(value,field,None);state=manager.palette_state() if manager else {}
                    if state.get('sessionId') and state.get('phase') not in ('idle','created','cancelled'):
                        raise ValueError('Cancel the active Partelier preview before this disposable check.')
        owned=app.documents.add(core.DocumentTypes.FusionDesignDocumentType);design=native.Design.cast(app.activeProduct)
        if design.designType!=native.DesignTypes.ParametricDesignType:design.designType=native.DesignTypes.ParametricDesignType
        root_component=design.rootComponent;manager=native.TemporaryBRepManager.get()
        def box(x0,x1,y0,y1,z0,z1):return manager.createBox(core.OrientedBoundingBox3D.create(
            core.Point3D.create((x0+x1)/20,(y0+y1)/20,(z0+z1)/20),core.Vector3D.create(1,0,0),core.Vector3D.create(0,1,0),(x1-x0)/10,(y1-y0)/10,(z1-z0)/10))
        def persist(shape,label):
            base=root_component.features.baseFeatures.add();assert base.startEdit()
            root_component.bRepBodies.add(shape,base);assert base.finishEdit()
            body=base.bodies.item(0);body.name=label;return body
        shape=box(-30,30,-20,20,-5,0)
        assert manager.booleanOperation(shape,box(-26,26,-16,16,-4,1),native.BooleanTypes.DifferenceBooleanType)
        A=persist(shape,'Selected lip base');B=persist(box(-30,30,-20,20,.25,6.25),'Selected lip lid')
        faces=(next(f for f in A.faces if abs(f.pointOnFace.z)<1e-7 and adapter._normal(f)[2]>.99),
            next(f for f in B.faces if abs(f.pointOnFace.z-.025)<1e-7 and adapter._normal(f)[2]<-.99))
        frame,bounds,gap,depth=adapter._mating(faces,settings.DetailSettings());clean=snapshot(design)
        centers=lambda inset:tuple(((a[0]+b[0])/2,(a[1]+b[1])/2) for a,b in zip(
            adapter.planner.rectangle(bounds,inset),adapter.planner.rectangle(bounds,inset)[1:]+adapter.planner.rectangle(bounds,inset)[:1]))
        witnesses=0
        for lead in (0,.2):
            for mask in range(1,16):
                values=settings.DetailSettings(lip_layout='selected',lip_sides=mask,lead_mm=lead)
                start=time.perf_counter();prepared=adapter.prepare(design,faces,values)
                for i,(x,z) in enumerate(centers(values.lip_inset_mm+values.lip_width_mm/2)):
                    assert adapter.a._containment(prepared.results[0],adapter.world(frame,x,z,1))==bool(mask&(1<<i))
                    assert adapter.a._containment(prepared.results[1],adapter.world(frame,x,z,1))!=bool(mask&(1<<i));witnesses+=2
                assert snapshot(design)==clean
                report['cases'].append({'mask':mask,'lead_mm':lead,'prepare_ms':round((time.perf_counter()-start)*1000,2)})
        owner=command.DetailCommands();session=command._Session(owner,design,settings.DetailSettings(lip_layout='selected'),False)
        owner._session=session;session.faces=faces
        session.validate();assert session.phase=='selecting' and not session.snapshot()['selections']['surface']['selected']
        session.start_sides();picker=session.side_picker
        if not picker.ready:core.doEvents()
        assert picker.ready
        edges={picker.index(e):e for e in A.edges if picker.index(e) is not None}
        aliases={picker.index(e):e for e in B.edges if picker.index(e) is not None}
        assert len(edges)==4 and len(aliases)==4
        picker.changed([SimpleNamespace(entity=edges[0])]);picker.paint()
        assert picker.mask==1 and not session.snapshot()['previewCurrent']
        picker.changed([SimpleNamespace(entity=aliases[1])]);picker.paint()
        assert picker.mask==3 and len(picker.session.faces)==2
        picker.changed([SimpleNamespace(entity=aliases[0])]);picker.paint();assert picker.mask==3
        picker.changed([SimpleNamespace(entity=faces[0])]);picker.paint()
        assert picker.error and picker.mask==3 and not session.snapshot()['canFinishSides']
        picker.clear();picker.paint();assert not session.snapshot()['canFinishSides']
        try:session.finish_sides()
        except ValueError:pass
        else:raise AssertionError('Empty selected lip accepted')
        picker.changed([SimpleNamespace(entity=edges[0]),SimpleNamespace(entity=edges[1])]);picker.paint()
        session.finish_sides();assert session.settings.lip_sides==3 and session.phase=='ready' and session.side_picker is None
        session.start_sides();picker=session.side_picker
        if not picker.ready:core.doEvents()
        owner.reset(session);picker.paint();assert picker.mask==0 and session.faces==faces
        report['additive_side_picker']={'done_required':True,'normal_replacement_accumulates':True,'lid_alias_deduplicated':True,'clear_and_empty_done':True}
        session.close();session=None;owner.stop();owner=None
        assert not picker.bound and picker.seed_event_id is None and snapshot(design)==clean
        count=root_component.bRepBodies.count;tokens=(A.entityToken,B.entityToken);history=design.timeline.count
        prepared=adapter.cache(adapter.prepare(design,faces,settings.DetailSettings(lip_layout='selected',lip_sides=3)))
        group=adapter.draw(prepared);assert group.isValid and group.deleteMe();assert snapshot(design)==clean
        anchor=store.apply(prepared);feature_tokens=[anchor.entityToken]
        record=store.read(design,anchor,'lid');assert record.recipe['version']==2
        feature_tokens+=record.recipe['combines'];assert design.timeline.count==history+3
        for mask in (5,7,15,1):
            record=store.read(design,anchor,'lid')
            rebuilt=store.prepare_edit(design,record,replace(record.settings,lip_sides=mask))
            store.apply(rebuilt)
            current=store.read(design,anchor,'lid')
            assert current.settings.lip_sides==mask and [anchor.entityToken,*current.recipe['combines']]==feature_tokens
            assert (A.entityToken,B.entityToken)==tokens and root_component.bRepBodies.count==count and design.timeline.count==history+3
        # Saved selected-side masks seed an Edit picker using current valid edges.
        session=command._Session(command.DetailCommands(),design,settings.DetailSettings(),True);owner=session.owner;owner._session=session
        session.select_target(anchor);session.start_sides();picker=session.side_picker
        if not picker.ready:core.doEvents()
        assert picker.ready and picker.mask==1
        session.finish_sides();session.close();session=None;owner.stop();owner=None
        report.update(success=True,material_witnesses=witnesses,preview_cleanup=True,create_rebuild_masks=[3,5,7,15,1],
            preserved_body_identity=True,preserved_history=True,edit_side_seed=True)
    finally:
        if session is not None:session.close()
        if owner is not None:owner.stop()
        if owned is not None and owned.isValid:owned.close(False)
        if caller is not None and caller.isValid:caller.activate();app.activeViewport.camera=camera
        report['caller_unchanged']=snapshot(original)==before
        for key in tuple(sys.modules):
            if key==name or key.startswith(name+'.'):sys.modules.pop(key,None)
        if not report['caller_unchanged']:raise AssertionError('Caller model changed')
    return report

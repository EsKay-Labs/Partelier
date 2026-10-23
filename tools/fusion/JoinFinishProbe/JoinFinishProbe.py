"""Native hinge probe: only owned fixtures and rollback-only model changes."""
import importlib
import importlib.util
import json
from pathlib import Path
import sys
import time
import traceback
import uuid
from dataclasses import replace
from types import SimpleNamespace
from math import cos, pi, sin, sqrt
import adsk.core
import adsk.fusion

HANDLERS=[]
STATE={}
EVENT="sktech_partelier_join_finish_probe_event"
COMMAND="sktech_partelier_join_finish_probe_command"
DIAGNOSTIC_FAILURES_ONLY=False
LIVE_STATE_ONLY=False
SELECTION_STATE_ONLY=False
INPLACE_ONLY=True

def live_product_state(root,design):
    """Inspect already-loaded product state only; never import/reload/mutate it."""
    expected=(root/"Partelier"/"partelier"/"addin.py").resolve()
    modules=[]
    def request_state(request):
        if request is None:return None
        return {key:getattr(request,key,None) for key in ("serial","cancelled","computed","executed")}
    for name,module in tuple(sys.modules.items()):
        location=getattr(module,"__file__",None)
        if not location:continue
        try:matches=Path(location).resolve()==expected
        except Exception:continue
        if not matches:continue
        owner=getattr(module,"_hinge_commands",None)
        entry={"module":name,"path":str(location),"manager":owner is not None}
        if owner is not None:
            entry.update(opening=owner._opening,palette_action_busy=owner._palette_action_busy,
                         pending_commit=owner._palette_pending is not None,sessions=[])
            runner=owner._native_preview
            entry["runner"]=None if runner is None else {"busy":runner.busy,"stopped":runner._stopped,"current":request_state(runner._current),"pending":request_state(runner._pending),"has_command":runner._command is not None}
            for session in owner._sessions:
                entry["sessions"].append({"id":session.session_id,"editing":session.editing,"phase":session.phase,"revision":session.revision,"generation":session.generation,"preview_generation":session.preview_generation,"native_generation":session._native_preview_generation,"closed":session.closed,"message":session.message,"error":session.preview_error,"edit_target_loaded":session.edit_target_loaded,"settings":session.palette_settings.to_dict(),"selections":{key:{"valid":bool(entity.isValid),"name":getattr(entity,"name",None),"type":getattr(entity,"objectType",None)} for key,entity in session.selection_entities.items()}})
        modules.append(entry)
    return {"active_command":adsk.core.Application.get().userInterface.activeCommand,
            "active_selections":[{"type":getattr(selection.entity,"objectType",None),"name":getattr(selection.entity,"name",None)} for selection in adsk.core.Application.get().userInterface.activeSelections],
            "loaded_products":modules,"bodies":[{"name":body.name,"visible":body.isVisible,"light_bulb":body.isLightBulbOn} for body in design.rootComponent.bRepBodies]}

def snap_selection_state(root, design):
    """Read the currently loaded snap session and bounded selections only."""
    def xyz(point):return [round(float(value)*10,7) for value in (point.x,point.y,point.z)]
    def segment(edge):
      if edge.startVertex is None or edge.endVertex is None:return None
      return [xyz(edge.startVertex.geometry),xyz(edge.endVertex.geometry)]
    def describe(entity):
      data={"type":entity.objectType,"valid":bool(entity.isValid)}
      if not entity.isValid:return data
      data["token"]=entity.entityToken
      body=getattr(entity,"body",None)
      if body is not None:data["body"]={"name":body.name,"bounds_mm":[xyz(body.boundingBox.minPoint),xyz(body.boundingBox.maxPoint)]}
      face=adsk.fusion.BRepFace.cast(entity)
      edge=adsk.fusion.BRepEdge.cast(entity)
      if face is not None:
        data["point_mm"]=xyz(face.pointOnFace)
        plane=adsk.core.Plane.cast(face.geometry)
        if plane is not None:
          sign=-1 if face.isParamReversed else 1
          data["normal"]=[sign*value for value in (plane.normal.x,plane.normal.y,plane.normal.z)]
        data["boundaries_mm"]=[segment(item) for item in face.edges if adsk.core.Line3D.cast(item.geometry) is not None]
      if edge is not None:data["endpoints_mm"]=segment(edge)
      return data
    expected=(root/"Partelier"/"partelier"/"addin.py").resolve()
    sessions=[]
    for name,module in tuple(sys.modules.items()):
      location=getattr(module,"__file__",None)
      if not location:continue
      try:matches=Path(location).resolve()==expected
      except Exception:continue
      if not matches:continue
      owner=getattr(module,"_snap_commands",None)
      session=getattr(owner,"_session",None) if owner is not None else None
      if session is not None:
        sessions.append({"module":name,"phase":session.phase,"message":session.message,"settings":session.settings.to_dict(),
                         "selections":{key:describe(entity) for key,entity in session.selections.items()}})
    return {"sessions":sessions,"active_selections":[describe(selection.entity) for selection in adsk.core.Application.get().userInterface.activeSelections]}

def snapshot(design):
    return {"timeline": design.timeline.count, "marker":design.timeline.markerPosition,
            "bodies":[{"name":b.name,"volume":b.volume,"faces":b.faces.count,"edges":b.edges.count,
                       "visible":b.isVisible} for b in design.rootComponent.bRepBodies]}

def load(root):
    name="_partelier_join_probe_"+uuid.uuid4().hex
    STATE["package_name"]=name
    STATE.setdefault("package_names",[]).append(name)
    path=root/"Partelier"/"partelier"
    spec=importlib.util.spec_from_file_location(name,path/"__init__.py",submodule_search_locations=[str(path)])
    module=importlib.util.module_from_spec(spec);sys.modules[name]=module;spec.loader.exec_module(module)
    return tuple(importlib.import_module(name+".tools.hinge."+n) for n in ("fusion","planner","settings","native_finish"))

def queue_probe_event(information=""):
    result=adsk.core.Application.get().fireCustomEvent(EVENT,information)
    STATE.get("report",{}).setdefault("probe_event_queue_returns",[]).append({"information":information,"result":result})
    return result

def cancellation_requested():
    callback=STATE.get("context",{}).get("cancel_requested")
    try:requested=bool(STATE.get("cancelled") or (callback is not None and callback()))
    except Exception:requested=True
    if requested:
      STATE["cancelled"]=True
      STATE.get("report",{})["cancelled"]=True
    return requested

def cancel():
    """Main-thread cooperative stop; only owned native commands are closed."""
    STATE["cancelled"]=True
    STATE.get("report",{})["cancelled"]=True
    runner=STATE.get("runtime_runner")
    if runner is not None:runner.stop()
    sequence_owner=STATE.get("sequence_owner")
    if sequence_owner is not None:sequence_owner.stop()
    app=adsk.core.Application.get()
    command=STATE.get("command")
    if command is not None and not STATE.get("own_command_destroyed"):
      if app.userInterface.activeCommand==COMMAND:
        app.userInterface.terminateActiveCommand()
      if not STATE.get("own_command_destroyed"):return
    finish_report()

def install_finish_diagnostics(finish, report):
    """Capture failed native inputs in this development probe, never in runtime."""
    original=finish._apply_stage
    def apply(root,body,edges,role,stage,settings,core,fusion,owned):
        diagnostic={"role":role,"stage":stage,"selected":[],"case":STATE.get("diagnostic_case",{})}
        try:
            frame=STATE["diagnostic_frame"]
            coordinates=lambda point:[round(v,8) for v in finish._local_mm(point,frame)]
            selected_vertices=[]
            for edge in edges:
                points=finish._samples(edge)
                selected_vertices.extend((coordinates(points[0]),coordinates(points[-1])))
            for edge in edges:
                points=finish._samples(edge)
                entry={"curve":edge.geometry.objectType,"points":[coordinates(p) for p in (points[0],points[2],points[-1])],"faces":[]}
                for face in edge.faces:
                    ok,normal=face.evaluator.getNormalAtPoint(points[2])
                    entry["faces"].append({"surface":face.geometry.objectType,"normal":list(finish._xyz(normal)) if ok else None})
                entry["selected_endpoint_degrees"]=[sum(all(abs(a-b)<.00001 for a,b in zip(vertex,other)) for other in selected_vertices) for vertex in (coordinates(points[0]),coordinates(points[-1]))]
                diagnostic["selected"].append(entry)
            if stage.startswith("caps"):
                plane=finish._cap_plane(edges[0],frame)
                diagnostic["other_same_plane"]=[]
                for edge in body.edges:
                    if any(edge==chosen for chosen in edges):continue
                    try:
                        if abs(finish._cap_plane(edge,frame)-plane)>.0001:continue
                        points=finish._samples(edge)
                        classification=finish.classify_edge(edge,body,core,fusion,settings.fillet_radius_mm if settings.fillet_edges else settings.chamfer_size_mm)
                        diagnostic["other_same_plane"].append({"curve":edge.geometry.objectType,"points":[coordinates(p) for p in (points[0],points[2],points[-1])],"classification":classification})
                    except Exception:pass
        except Exception:
            diagnostic["diagnostic_error"]=traceback.format_exc()
        try:
            output=original(root,body,edges,role,stage,settings,core,fusion,owned)
            if role=="A" and STATE.get("tangent_probe") is not None:
                point=STATE["tangent_probe"]
                inside=output.pointContainment(point)!=fusion.PointContainment.PointOutsidePointContainment
                STATE["diagnostic_item"].setdefault("tangent_stage_trace",[]).append({"stage":stage,"inside":inside,"selected_edges":len(edges)})
            return output
        except Exception:
            report.setdefault("finish_failure_inputs",[]).append(diagnostic)
            raise
    finish._apply_stage=apply

def session_commit_check(design,anchor,adapter):
    """Actual command session on owned fixture only, inside outer rollback."""
    module=importlib.import_module(adapter.__package__+".command")
    owner=module.HingeCommands();session=module._Session(owner,None,True)
    session.palette_mode=True;session.session_id="validation-commit";owner._sessions.append(session)
    session.open(settings=adapter.read_edit_target(design,anchor).settings)
    session.selection_entities["edit_target"]=anchor;session.changed("edit_target")
    session.palette_settings=replace(session.palette_settings,length_mm=session.palette_settings.length_mm*.9)
    session.command=STATE["command"];session.commit_requested=True
    source_flags=[(body,body.isLightBulbOn) for body in adapter.source_bodies(SimpleNamespace(settings=session.palette_settings,face_a=adapter.read_edit_target(design,anchor).face_a,face_b=adapter.read_edit_target(design,anchor).face_b))]
    original=module.rebuild_hinge;replacement=[anchor]
    def rebuild(*arguments):
        result=original(*arguments);replacement[0]=result;return result
    module.rebuild_hinge=rebuild
    try:
        args=SimpleNamespace(executeFailed=False)
        session.execute(args)
        if args.executeFailed:raise RuntimeError(getattr(args,"executeFailedMessage","Session commit failed"))
        if any(body.isLightBulbOn for body,_ in source_flags):raise RuntimeError("Successful attached Session commit left its original backups visible.")
        current=adapter.read_edit_target(design,replacement[0])
        if current.settings!=session.palette_settings:raise RuntimeError("Session rebuild did not store the edited dimensions.")
        return replacement[0],{"hidden_source_count":len(source_flags),"edited_length_mm":current.settings.length_mm,"success":True}
    finally:
        module.rebuild_hinge=original
        session.close();owner.stop()
        for body,value in source_flags:
            if body.isValid:body.isLightBulbOn=value
        # The caller still owns the replacement even if a later assertion fails.
        STATE["session_commit_fixture"]=replacement[0]

def independent_root_edit_check(design,anchor,prepared,adapter):
    """Edit an earlier independent owned fixture; refuse a logical dependent."""
    if not adapter._is_part_design(design):
        return anchor,{"skipped":"Earlier component/occurrence editing remains unsupported."}
    later=None;current=anchor
    try:
        later=adapter.create_hinge(design,prepared)
        attribute=later.attributes.itemByName(adapter.ATTRIBUTE_GROUP,adapter.RECIPE_NAME)
        original=attribute.value;recipe=json.loads(original)
        forged=json.loads(original)
        forged["sources"]["body_a"]=adapter._token(current.bodies.item(0))
        before=(design.rootComponent.bRepBodies.count,design.timeline.count)
        before_target=adapter.read_edit_target(design,current)
        try:
            adapter._attribute(later,adapter.RECIPE_NAME,json.dumps(forged,separators=(",",":")))
            try:adapter.rebuild_hinge(design,before_target,prepared)
            except adapter.HingeGeometryError as error:
                if "depend" not in str(error).lower():raise
            else:raise RuntimeError("An earlier hinge with a logical recipe dependent was accepted for replacement.")
            if before!=(design.rootComponent.bRepBodies.count,design.timeline.count):raise RuntimeError("Logical-dependency refusal changed geometry/history.")
        finally:
            adapter._attribute(later,adapter.RECIPE_NAME,original)
        target=adapter.read_edit_target(design,current)
        edited=replace(target.settings,length_mm=target.settings.length_mm*.95)
        candidate=adapter.prepare_hinge(design,target.face_a,target.face_b,target.axis_edge,edited,edge_finisher=STATE["finish"].finish_native_results)
        current=adapter.rebuild_hinge(design,target,candidate)
        unchanged_later=adapter.read_edit_target(design,later)
        if unchanged_later.recipe!=recipe:raise RuntimeError("Editing the earlier fixture changed the later hinge recipe.")
        if before!=(design.rootComponent.bRepBodies.count,design.timeline.count):raise RuntimeError("Editing the earlier fixture accumulated result bodies/features.")
        if adapter.read_edit_target(design,current).settings!=edited:raise RuntimeError("Earlier fixture rebuild did not store its edited dimensions.")
        return current,{"success":True,"logical_dependency_refused":True,"later_recipe_and_geometry_unchanged":True,"body_and_timeline_counts_unchanged":True}
    finally:
        STATE["independent_fixture"]=current
        if later is not None and later.isValid and not later.deleteMe():raise RuntimeError("Could not remove the owned later-hinge fixture.")

def inplace_fixture(design):
    """Own both test targets; never run an in-place operation on the user's solids."""
    root=design.rootComponent
    manager=adsk.fusion.TemporaryBRepManager.get()
    feature=root.features.baseFeatures.add()
    feature.name="Partelier disposable in-place sources"
    feature.startEdit()
    for x in (-12,12):
        bounds=adsk.core.OrientedBoundingBox3D.create(
            adsk.core.Point3D.create(x/10,0,-.2),
            adsk.core.Vector3D.create(1,0,0),adsk.core.Vector3D.create(0,1,0),2.4,10,.4)
        root.bRepBodies.add(manager.createBox(bounds),feature)
    feature.finishEdit()
    bodies=tuple(feature.bodies)
    bodies=tuple(sorted(bodies,key=lambda body:body.boundingBox.minPoint.x))
    for body,name in zip(bodies,("Owned source A","Owned source B")):body.name=name
    faces=[]
    for body in bodies:
        faces.append(next(face for face in body.faces
            if adsk.core.Plane.cast(face.geometry) is not None
            and abs(face.boundingBox.minPoint.z)<1e-7 and abs(face.boundingBox.maxPoint.z)<1e-7))
    edge=next(edge for edge in faces[0].edges
        if abs(edge.startVertex.geometry.x)<1e-7 and abs(edge.endVertex.geometry.x)<1e-7)
    return feature,bodies,tuple(faces),edge


def inplace_algebra_check():
    """Join and intersect owned targets, then update consumed tools in history."""
    design=STATE["design"];root=design.rootComponent;adapter=STATE["adapter"]
    before_count=root.bRepBodies.count
    fixture,targets,faces,edge=inplace_fixture(design)
    tokens=[body.entityToken for body in targets]
    names=[body.name for body in targets]
    settings=STATE["settings_module"].HingeSettings(split_seam=True,hinge_count=2,length_mm=35,start_margin_mm=10,end_margin_mm=10)
    prepared=adapter.prepare_hinge(design,*faces,edge,settings)
    tools=root.features.baseFeatures.add();tools.startEdit()
    roles=[]
    for role,body in prepared.result_bodies:
        root.bRepBodies.add(body,tools);roles.append(role)
    tools.finishEdit();mapped=dict(zip(roles,tuple(tools.bodies)))
    operations=[]
    for role,target in zip(("A","B"),targets):
        for operation,keep in ((adsk.fusion.FeatureOperations.JoinFeatureOperation,True),(adsk.fusion.FeatureOperations.IntersectFeatureOperation,False)):
            collection=adsk.core.ObjectCollection.create();collection.add(mapped[role])
            definition=root.features.combineFeatures.createInput(target,collection)
            definition.operation=operation;definition.isKeepToolBodies=keep;definition.isNewComponent=False
            operation_feature=root.features.combineFeatures.add(definition)
            operations.append(operation_feature)
    for role,target,token,name in zip(("A","B"),targets,tokens,names):
        if not target.isValid or design.findEntityByToken(token)[0]!=target:raise RuntimeError("Combine replaced target identity.")
        if target.name!=name:raise RuntimeError("Combine renamed the user's body.")
        if abs(target.volume-dict(prepared.result_bodies)[role].volume)>1e-7:raise RuntimeError("Combine did not produce the expected full hinge.")
    if root.bRepBodies.count!=before_count+2+settings.hinge_count:raise RuntimeError("Consumed tools remain as extra bodies.")
    # The tool bodies must remain editable even though the final history consumed them.
    tools.timelineObject.rollTo(True)
    if not tools.startEdit():raise RuntimeError("Could not edit consumed tools.")
    sources=tuple(tools.bodies)
    if len(sources)!=len(roles):raise RuntimeError("Consumed tool source count changed.")
    for role,source in zip(roles,sources):
        if not tools.updateBody(source,dict(prepared.result_bodies)[role]):raise RuntimeError("Consumed tool updateBody failed.")
    if not tools.finishEdit():raise RuntimeError("Could not finish consumed-tool update.")
    design.timeline.moveToEnd()
    for role,target,token in zip(("A","B"),targets,tokens):
        if not target.isValid or design.findEntityByToken(token)[0]!=target:raise RuntimeError("Tool update replaced target identity.")
        if abs(target.volume-dict(prepared.result_bodies)[role].volume)>1e-7:raise RuntimeError("Tool update broke native recomputation.")
    STATE["report"]["cases"].append({"mode":"inplace-native-algebra","success":True,"original_target_identity_preserved":True,"original_names_preserved":True,"final_body_count":root.bRepBodies.count-before_count,"expected_body_count":2+settings.hinge_count,"consumed_tools_updated":True})
    STATE.setdefault("detached",[]).extend(body for _,body in prepared.result_bodies)
    STATE["report"]["success"]=True

def inplace_product_checks():
    """Exercise production Create/Edit/Rebuild on owned native-root targets only."""
    design=STATE["design"];root=design.rootComponent;adapter=STATE["adapter"]
    finish=STATE["finish"].finish_native_results
    module=STATE["settings_module"]
    for treatment in ("sharp","chamfer","fillet","square"):
        item={"mode":"inplace-production","finish":treatment,"success":False,"steps":[]}
        STATE["report"]["cases"].append(item)
        try:
            baseline=root.bRepBodies.count
            fixture,targets,faces,edge=inplace_fixture(design)
            tokens=[body.entityToken for body in targets]
            names=[body.name for body in targets]
            settings=module.HingeSettings(split_seam=True,hinge_count=2,length_mm=35,start_margin_mm=10,end_margin_mm=10,
                chamfer_edges=treatment=="chamfer",fillet_edges=treatment=="fillet",fillet_radius_mm=.2,
                knuckle_profile="square" if treatment=="square" else "round")
            prepared=adapter.prepare_hinge(design,*faces,edge,settings,edge_finisher=finish)
            anchor=adapter.create_hinge(design,prepared);item["steps"].append("create")
            if root.bRepBodies.count!=baseline+4:raise RuntimeError("Attached Create duplicated sources.")
            for body,token,name in zip(targets,tokens,names):
                if design.findEntityByToken(token)[0]!=body or body.name!=name:raise RuntimeError("Create changed source body identity/name.")
            target=adapter.read_edit_target(design,targets[0]);item["steps"].append("read-from-original-body")
            recipe=target.recipe
            history_before=design.timeline.count
            for index,changes in enumerate((dict(length_mm=32,knuckle_count=3),dict(include_pin=False),dict(hinge_count=3,length_mm=20,include_pin=True),dict(hinge_count=1,length_mm=45))):
                edited=replace(target.settings,**changes)
                before=snapshot(design)
                candidate=adapter.prepare_edit_hinge(design,target,edited,edge_finisher=finish)
                if snapshot(design)!=before:raise RuntimeError("Edit preview changed persisted geometry/history/visibility.")
                adapter.validate_preview_sources(design,adapter.capture_preview_sources(candidate))
                graphics=adapter.preview_hinge(candidate)
                if not graphics.deleteMe():raise RuntimeError("Could not remove temporary preview graphics.")
                old_anchor=anchor
                anchor=adapter.rebuild_hinge(design,target,candidate)
                if anchor!=old_anchor or design.timeline.count!=history_before:raise RuntimeError("Rebuild accumulated feature history.")
                target=adapter.read_edit_target(design,targets[1])
                if target.settings!=edited:raise RuntimeError("Rebuild saved different settings.")
                expected=baseline+2+(edited.hinge_count if edited.include_pin else 0)
                if root.bRepBodies.count!=expected:raise RuntimeError("Rebuild accumulated duplicate bodies or pins.")
                for body,token,name in zip(targets,tokens,names):
                    if design.findEntityByToken(token)[0]!=body or body.name!=name or not body.isLightBulbOn:raise RuntimeError("Rebuild replaced/renamed/hidden original body.")
                item["steps"].append("rebuild-"+str(index+1))
            STATE.setdefault("detached",[]).extend(body for _,body in candidate.result_bodies)
            item.update(success=True,same_targets=True,only_optional_pins_added=True,history_count_unchanged=True,preview_unchanged=True)
        except Exception:
            item["error"]=traceback.format_exc()
    item={"mode":"legacy-attached-migration","success":False,"steps":[]}
    STATE["report"]["cases"].append(item)
    try:
        baseline=root.bRepBodies.count
        fixture,targets,faces,edge=inplace_fixture(design)
        tokens=[body.entityToken for body in targets]
        settings=module.HingeSettings(split_seam=True,hinge_count=2,length_mm=35,start_margin_mm=10,end_margin_mm=10)
        prepared=adapter.prepare_hinge(design,*faces,edge,settings)
        legacy=adapter._create(design,prepared,str(uuid.uuid4()))
        for body in targets:body.isLightBulbOn=False
        target=adapter.read_edit_target(design,legacy)
        candidate=adapter.prepare_edit_hinge(design,target,replace(settings,length_mm=32))
        migrated=adapter.rebuild_hinge(design,target,candidate)
        if legacy.isValid:raise RuntimeError("Legacy copied result was not removed.")
        result=adapter.read_edit_target(design,targets[0])
        if result.recipe["version"]!=9 or result.anchor!=migrated:raise RuntimeError("Legacy migration did not produce in-place recipe.")
        if root.bRepBodies.count!=baseline+4:raise RuntimeError("Legacy migration retained duplicate result/source bodies.")
        for body,token in zip(targets,tokens):
            if design.findEntityByToken(token)[0]!=body or not body.isLightBulbOn:raise RuntimeError("Migration failed to show the integrated originals.")
        item.update(success=True,same_original_targets=True,old_copies_removed=True,integrated_originals_visible=True)
    except Exception:item["error"]=traceback.format_exc()
    STATE["report"]["success"]=all(item["success"] for item in STATE["report"]["cases"])

def inplace_session_check():
    """Production command sessions; no interactive picker or CEF input automation."""
    adapter=STATE["adapter"];design=STATE["design"];root=design.rootComponent
    module=importlib.import_module(adapter.__package__+".command")
    owner=module.HingeCommands();sessions=[]
    item={"mode":"inplace-command-sessions","success":False,"steps":[]}
    STATE["report"]["cases"].append(item)
    def open_session(editing,settings,entities):
        session=module._Session(owner,None,editing);session.palette_mode=True
        session.session_id=str(uuid.uuid4());owner._sessions.append(session)
        sessions.append(session);session.open(settings)
        session.selection_entities.update(entities)
        session.changed("edit_target" if editing else "axis_edge")
        session.command=STATE["command"];session.commit_requested=True
        return session
    def preview(session):
        candidate,_=session._prepare(native_transaction=True)
        session._display_preview(candidate,time.perf_counter())
        if session.phase!="preview" or not session.preview_visibility.pending_count:raise RuntimeError("Session failed to display and lease current preview.")
    def commit(session):
        args=SimpleNamespace(executeFailed=False)
        session.execute(args)
        if args.executeFailed:raise RuntimeError(getattr(args,"executeFailedMessage","Session commit failed."))
        session.close()
    try:
        baseline=root.bRepBodies.count
        fixture,targets,faces,edge=inplace_fixture(design)
        tokens=[body.entityToken for body in targets]
        settings=STATE["settings_module"].HingeSettings(split_seam=True,hinge_count=2,length_mm=35,start_margin_mm=10,end_margin_mm=10,chamfer_edges=True)
        new=open_session(False,settings,dict(face_a=faces[0],face_b=faces[1],axis_edge=edge))
        before=snapshot(design);preview(new)
        commit(new);item["steps"].append("new-preview-create")
        if root.bRepBodies.count!=baseline+4 or any(not body.isLightBulbOn for body in targets):raise RuntimeError("Session Create hid or duplicated original targets.")
        edit=open_session(True,settings,dict(edit_target=targets[0]))
        preview(edit)
        edit.palette_settings=replace(settings,length_mm=30,knuckle_count=3)
        edit.generation+=1;preview(edit);commit(edit)
        target=adapter.read_edit_target(design,targets[0])
        if target.settings!=edit.palette_settings:raise RuntimeError("Session Rebuild ignored edited settings.")
        item["steps"].append("edit-update-preview-rebuild")
        before=snapshot(design);recipe=dict(target.recipe)
        cancelled=open_session(True,target.settings,dict(edit_target=targets[1]))
        cancelled.palette_settings=replace(target.settings,length_mm=28)
        cancelled.generation+=1;preview(cancelled);cancelled.close()
        if snapshot(design)!=before or adapter.read_edit_target(design,targets[1]).recipe!=recipe:raise RuntimeError("Edit Cancel changed model, history, visibility or recipe.")
        item["steps"].append("edit-preview-cancel-restored")
        for body,token in zip(targets,tokens):
            if design.findEntityByToken(token)[0]!=body:raise RuntimeError("Session lifecycle replaced target identities.")
        owner.stop()
        item.update(success=True,same_original_targets=True,cancel_restored=True)
    except Exception:item["error"]=traceback.format_exc()
    finally:
        for session in sessions:session.close()
        owner.stop()
    STATE["report"]["success"]=all(case["success"] for case in STATE["report"]["cases"])

def cases(*, skip_saved=False):
    app=adsk.core.Application.get(); report=STATE["report"]; design=STATE["design"]
    if cancellation_requested():return
    adapter,planner,settings_module,finish=(STATE[key] for key in ("adapter","planner","settings_module","finish"))
    install_finish_diagnostics(finish,report)
    manager=adsk.fusion.TemporaryBRepManager.get()
    frames=(adapter.HingeFrame((0,0,0),(1,0,0),(0,1,0),(0,0,1)),
            adapter.HingeFrame((17,-9,31),(0,0,-1),(1,0,0),(0,-1,0)))
    for mode,leaf_profile,limit_web in (("attached","rectangular",None),("separate","rectangular",None),("separate","rounded",None),
                                         ("attached","rectangular","flat"),("separate","rectangular","flat"),("separate","rectangular","tangent")):
      for profile in ("round","square"):
       for web_profile in ("tangent","flat"):
        for treatment in ("chamfer","fillet"):
         for frame_index, frame in enumerate(frames):
          if limit_web and (profile!="round" or treatment!="fillet" or web_profile!=limit_web):continue
          # Rounded leaf outline plus all-corner fillet is explicitly invalid.
          if leaf_profile=="rounded" and treatment=="fillet":continue
          if DIAGNOSTIC_FAILURES_ONLY:
            report["diagnostic_only"]=True
            if frame_index!=0 or profile!="round" or not (treatment=="fillet" or (mode=="separate" and web_profile=="tangent")):continue
          if cancellation_requested():return
          STATE["diagnostic_frame"]=frame
          started=time.perf_counter();item={"mode":mode,"leaf_profile":leaf_profile,"housing":profile,"web":web_profile,"finish":treatment,"frame_index":frame_index,"success":False}
          if limit_web:item.update(case_kind="finish_limit",requested_fillet_mm=.6)
          try:
            STATE["diagnostic_case"]={key:item[key] for key in ("mode","leaf_profile","housing","web","finish","frame_index")}
            settings=settings_module.HingeSettings(output_mode=mode,leaf_profile=leaf_profile,knuckle_profile=profile,web_profile=web_profile,
                 chamfer_edges=treatment=="chamfer",fillet_edges=treatment=="fillet",
                 fillet_radius_mm=.6 if limit_web else (.4 if profile=="square" else (.2 if web_profile=="flat" or mode=="separate" else .6)),screw_holes=mode=="separate")
            item["finish_size_mm"]=settings.fillet_radius_mm if treatment=="fillet" else settings.chamfer_size_mm
            plan=planner.build_hinge_plan(settings)
            raw=replace(settings,chamfer_edges=False,fillet_edges=False)
            raw_plan=replace(plan,settings=raw)
            bodies={}
            if mode=="attached":
              for owner,lo,hi in (("A",-25,-.15),("B",.15,25)):
                bodies[owner]=adapter._box(manager,frame,planner.WebBounds(owner,lo,hi,-25,25,-4,0))
            else:
              bodies={plate.owner:adapter._leaf_plate(manager,frame,plate) for plate in plan.plates}
            adapter.cut_rotation_relief(manager,frame,bodies,settings)
            for knuckle,web in zip(plan.knuckles,plan.webs):
                support=adapter._attachment_body(manager,frame,web,raw)
                body=adapter._knuckle_body(manager,frame,raw_plan,knuckle,support)
                adapter._boolean(manager,bodies[web.owner],body,adsk.fusion.BooleanTypes.UnionBooleanType,"raw join")
            if mode=="separate":
              plates={p.owner:p for p in plan.plates}
              for hole in plan.mounting_holes:
                adapter._drill_leaf(manager,frame,bodies[hole.owner],plates[hole.owner],hole)
            bodies["pin"]=adapter._cylinder(manager,frame,plan.pin_start_mm,plan.pin_end_mm,
                                            settings.pin_diameter_mm/2,plan.barrel_radius_mm)
            STATE["diagnostic_item"]=item;STATE["tangent_probe"]=None
            if profile=="round" and web_profile=="tangent":
                support_module=importlib.import_module(adapter.__package__+".support")
                taper=support_module.plan_tangent_support(plan.webs[0],plan.barrel_radius_mm,attached=mode=="attached")
                tx,tz=taper.tangent_xz_mm;radius=plan.barrel_radius_mm
                nx,nz=tx/radius,(tz-radius)/radius
                size=settings.fillet_radius_mm if treatment=="fillet" else settings.chamfer_size_mm
                depth=min(.05,size/4)
                offset=size-sqrt(size*size-(size-depth)**2) if treatment=="fillet" else size-depth
                x=tx-.3;z=(radius*nz+radius-offset-nx*x)/nz
                point=adapter._point(frame,x,plan.knuckles[0].start_mm+depth,z-.005)
                STATE["tangent_probe"]=point
                item["tangent_raw_inside"]=bodies["A"].pointContainment(point)!=adsk.fusion.PointContainment.PointOutsidePointContainment
            result=finish.finish_native_results(design,manager,frame,settings,tuple(bodies.items()),plan=plan)
            if STATE["tangent_probe"] is not None:
                item["tangent_detached_inside"]=result[0][1].pointContainment(STATE["tangent_probe"])!=adsk.fusion.PointContainment.PointOutsidePointContainment
            for index,(role,body) in enumerate(result):
                for other_role,other in result[index+1:]:
                    adapter._require_separate(manager,body,other,"finished "+role+"/"+other_role)
            STATE.setdefault("detached",[]).extend(body for _,body in result)
            if mode=="separate":
                owners=dict(result)
                for hole in plan.mounting_holes:
                    for radial,expected in ((0,False),(hole.diameter_mm/2-.01,False),(hole.diameter_mm/2+.01,True)):
                        point=adapter._point(frame,hole.x_mm+radial,hole.y_mm,settings.leaf_thickness_mm/2)
                        inside=owners[hole.owner].pointContainment(point)!=adsk.fusion.PointContainment.PointOutsidePointContainment
                        if inside!=expected:raise RuntimeError("A finished screw hole is obstructed or its middle diameter changed.")
                item["screw_hole_witnesses"]=len(plan.mounting_holes)
                mouth_witnesses=0
                size=settings.fillet_radius_mm if treatment=="fillet" else settings.chamfer_size_mm
                for hole in plan.mounting_holes:
                  for surface,zsign in ((0,1),(settings.leaf_thickness_mm,-1)):
                    for depth in (.05,size/2,size*.9):
                      inset=(size-sqrt(size*size-(size-depth)**2)
                             if treatment=="fillet" else size-depth)
                      for angular_index in range(16):
                        angle=2*pi*angular_index/16
                        for delta,expected in ((-.005,False),(.005,True)):
                          radial=hole.diameter_mm/2+inset+delta
                          point=adapter._point(frame,hole.x_mm+radial*cos(angle),hole.y_mm+radial*sin(angle),surface+zsign*depth)
                          inside=owners[hole.owner].pointContainment(point)!=adsk.fusion.PointContainment.PointOutsidePointContainment
                          if inside!=expected:raise RuntimeError("A screw-hole entry does not match the requested finish: "+repr({"owner":hole.owner,"surface":surface,"depth":depth,"angle":angular_index,"delta":delta}))
                          mouth_witnesses+=1
                item["screw_mouth_witnesses"]=mouth_witnesses
            bore_checks=0
            for knuckle in plan.knuckles:
                middle=(knuckle.start_mm+knuckle.end_mm)/2
                for radial,expected in ((plan.bore_radius_mm-.01,False),(plan.bore_radius_mm+.01,True)):
                    point=adapter._point(frame,radial,middle,plan.barrel_radius_mm)
                    inside=dict(result)[knuckle.owner].pointContainment(point)!=adsk.fusion.PointContainment.PointOutsidePointContainment
                    if inside!=expected:raise RuntimeError("The finished middle bore diameter changed.")
                    bore_checks+=1
            for radial,expected in ((settings.pin_diameter_mm/2-.01,True),(settings.pin_diameter_mm/2+.01,False)):
                point=adapter._point(frame,radial,0,plan.barrel_radius_mm)
                inside=dict(result)["pin"].pointContainment(point)!=adsk.fusion.PointContainment.PointOutsidePointContainment
                if inside!=expected:raise RuntimeError("The finished middle pin diameter changed.")
            item["bore_witnesses"]=bore_checks
            item["pin_witnesses"]=2
            checks=[]
            size=settings.fillet_radius_mm if treatment=="fillet" else settings.chamfer_size_mm
            depth=min(.05,size/4)
            offset=size-sqrt(size*size-(size-depth)**2) if treatment=="fillet" else size-depth
            def boundary_pair(x,z,delta_axis,label):
                for delta,expected in ((-.005,True),(.005,False)):
                    coordinates=[x,plan.knuckles[0].start_mm+depth,z]
                    coordinates[delta_axis]+=delta
                    inside=result[0][1].pointContainment(adapter._point(frame,*coordinates))!=adsk.fusion.PointContainment.PointOutsidePointContainment
                    if inside!=expected:raise RuntimeError(label+" does not match the requested cap finish.")
                checks.append(label)
            # Standard equal-distance chamfer/constant-radius fillet formulas
            # apply at edge interiors, away from native corner patch choices.
            if web_profile=="flat":
                boundary_pair(-8,settings.leaf_thickness_mm-offset,2,"flat-web-cap-offset")
                middle=(plan.knuckles[0].start_mm+plan.knuckles[0].end_mm)/2
                if mode=="attached":
                    toe=adapter._point(frame,-settings.leaf_reach_mm+.001,middle,.05)
                    if result[0][1].pointContainment(toe)==adsk.fusion.PointContainment.PointOutsidePointContainment:
                        raise RuntimeError("The embedded source-root edge was incorrectly trimmed.")
                    checks.append("embedded-root-preserved")
            housing_side=(plan.barrel_radius_mm if profile=="round" else plan.barrel_radius_mm/sqrt(2))-offset
            boundary_pair(housing_side,plan.barrel_radius_mm,0,"outer-housing-cap-offset")
            if web_profile=="tangent" and profile=="round":
                support_module=importlib.import_module(adapter.__package__+".support")
                taper=support_module.plan_tangent_support(plan.webs[0],plan.barrel_radius_mm,
                                                           attached=mode=="attached")
                tx,tz=taper.tangent_xz_mm;radius=plan.barrel_radius_mm
                nx,nz=tx/radius,(tz-radius)/radius
                size=settings.fillet_radius_mm if treatment=="fillet" else settings.chamfer_size_mm
                depth=min(.05,size/4)
                offset=size-sqrt(size*size-(size-depth)**2) if treatment=="fillet" else size-depth
                # Shared tangent of the joined offset outline at this cap depth.
                x=tx-.3;z=(radius*nz+radius-offset-nx*x)/nz
                for delta,expected in ((-.005,True),(.005,False)):
                    point=adapter._point(frame,x,plan.knuckles[0].start_mm+depth,z+delta)
                    inside=result[0][1].pointContainment(point)!=adsk.fusion.PointContainment.PointOutsidePointContainment
                    if inside!=expected:
                        def occupied(height):
                            p=adapter._point(frame,x,plan.knuckles[0].start_mm+depth,height)
                            return result[0][1].pointContainment(p)!=adsk.fusion.PointContainment.PointOutsidePointContainment
                        heights=[2*radius*i/256 for i in range(257) if occupied(2*radius*i/256)]
                        actual=None
                        if heights:
                            low=max(heights);high=min(2*radius,low+2*radius/256)
                            for _ in range(24):
                                middle=(low+high)/2
                                if occupied(middle):low=middle
                                else:high=middle
                            actual=(low+high)/2
                        item["tangent_failure"]={"x_mm":x,"cap_depth_mm":depth,"expected_top_mm":z,"actual_top_mm":actual,"delta_mm":delta,"expected_inside":expected,"observed_inside":inside}
                        raise RuntimeError("Joined tangent top contour is discontinuous.")
                # Inspect both sides of every radial divider, each half and cap.
                # Roof u<=0 and barrel u>0 have independent exact offset formulas.
                seam_witnesses=0
                for knuckle,web in zip(plan.knuckles,plan.webs):
                    sign=1 if knuckle.owner=="A" else -1
                    support_plan=support_module.plan_tangent_support(web,radius,attached=mode=="attached")
                    canonical_tx=sign*support_plan.tangent_xz_mm[0]
                    tangent_z=support_plan.tangent_xz_mm[1]
                    normal_x,normal_z=canonical_tx/radius,(tangent_z-radius)/radius
                    for cap,ysign in ((knuckle.start_mm,1),(knuckle.end_mm,-1)):
                      for cap_depth in (.05,size/2,size*.9):
                        inset=(size-sqrt(size*size-(size-cap_depth)**2)
                               if treatment=="fillet" else size-cap_depth)
                        y=cap+ysign*cap_depth
                        for u in (-2*size,-size,-.3,-.02,0,.02,.3,size):
                          if u<=0:
                            px=canonical_tx+u*normal_z-inset*normal_x
                            pz=tangent_z-u*normal_x-inset*normal_z
                            ox,oz=normal_x,normal_z
                          else:
                            angle=u/radius
                            ox=normal_x*cos(angle)+normal_z*sin(angle)
                            oz=normal_z*cos(angle)-normal_x*sin(angle)
                            px=(radius-inset)*ox
                            pz=radius+(radius-inset)*oz
                          for delta,expected in ((-.005,True),(.005,False)):
                            point=adapter._point(frame,sign*(px+delta*ox),y,pz+delta*oz)
                            inside=dict(result)[knuckle.owner].pointContainment(point)!=adsk.fusion.PointContainment.PointOutsidePointContainment
                            if inside!=expected:
                              raise RuntimeError("Shared tangent/cylinder cap mismatch: "+repr({"owner":knuckle.owner,"cap":cap,"depth":cap_depth,"u":u,"delta":delta,"expected":expected,"observed":inside}))
                            seam_witnesses+=1
                item["seam_witnesses"]=seam_witnesses
                checks.append("continuous-shared-tangent")
            item["junction_checks"]=checks
            item["volumes_mm3"]={role:b.volume*1000 for role,b in result}
            STATE["runtime_inputs"]=(manager,frame,settings,tuple(bodies.items()),plan)
            item["success"]=True
            if limit_web:item["outcome"]="accepted-with-contour-checks"
          except Exception as error:
            item["error"]=traceback.format_exc()
            reason=str(error)
            if (limit_web and isinstance(error,adapter.HingeGeometryError)
                    and ("Fusion could not finish joined " in reason or "Fusion's joined fillet is discontinuous" in reason)
                    and "cleanup failed" not in reason.lower()):
                item.update(success=True,outcome="explicit-refusal",refusal_reason=reason)
                item.pop("error")
          item["elapsed_ms"]=(time.perf_counter()-started)*1000
          report["cases"].append(item)
    if skip_saved:
        report["success"]=all(item["success"] for item in report["cases"])
        return
    for anchor in STATE.get("active_anchors",[]):
        if cancellation_requested():return
        item={"mode":"saved_recipe","success":False}
        fixture=None
        try:
            target=adapter.read_edit_target(design,anchor)
            prepared=adapter.prepare_hinge(design,target.face_a,target.face_b,target.axis_edge,
                                           target.settings,edge_finisher=finish.finish_native_results)
            STATE.setdefault("detached",[]).extend(body for _,body in prepared.result_bodies)
            STATE["runtime_target"]=target
            item["settings"]=target.settings.to_dict()
            item["placement_count"]=len(prepared.layout.placements)
            item["prepare_timings_ms"]=prepared.timings
            fixture=adapter.create_hinge(design,prepared)
            copied_target=adapter.read_edit_target(design,fixture)
            rebuilt=adapter.rebuild_hinge(design,copied_target,prepared)
            fixture=rebuilt
            reread=adapter.read_edit_target(design,rebuilt)
            if reread.settings!=prepared.settings:raise RuntimeError("Rebuild changed the hinge settings.")
            item["workflow"]=["prepare","temporary-create","read-edit","temporary-rebuild","read-rebuilt"]
            fixture,commit_result=session_commit_check(design,fixture,adapter)
            item["session_commit_visibility"]=commit_result
            item["workflow"].append("session-rebuild-edited-settings-hidden-backups")
            fixture,independent=independent_root_edit_check(design,fixture,prepared,adapter)
            item["independent_root_edit"]=independent
            item["workflow"].append("earlier-independent-root-rebuild-and-logical-dependency-refusal")
            item["success"]=True
        except Exception:
            item["error"]=traceback.format_exc()
        finally:
            fixture=STATE.pop("independent_fixture",None) or STATE.pop("session_commit_fixture",None) or fixture
            if fixture is not None and fixture.isValid:
                if not fixture.deleteMe():
                    item["success"]=False;item["cleanup_error"]="Could not remove the owned workflow fixture."
        report["cases"].append(item)
    report["success"]=all(i["success"] for i in report["cases"])

class Preview(adsk.core.CommandEventHandler):
 def notify(self,args):
    args.isValidResult=False
    if cancellation_requested():return
    try:
      if INPLACE_ONLY:
        cases(skip_saved=True)
        inplace_algebra_check()
        inplace_product_checks()
        inplace_session_check()
      else:cases()
    except Exception:STATE["report"]["error"]=traceback.format_exc()
class Execute(adsk.core.CommandEventHandler):
 def notify(self,args):STATE["report"]["noop_execute"]=True
class Created(adsk.core.CommandCreatedEventHandler):
 def notify(self,args):
    cmd=args.command;STATE["command"]=cmd
    cmd.isAutoExecute=False;cmd.isExecutedWhenPreEmpted=False;cmd.isRepeatable=False
    for event,handler in ((cmd.executePreview,Preview()),(cmd.execute,Execute()),(cmd.destroy,Destroyed())):
      event.add(handler);HANDLERS.append(handler)
    if cancellation_requested():
      cmd.isAutoExecute=True;return
    queue_probe_event()
def runtime_preview_check():
    if cancellation_requested():cancel();return
    app=adsk.core.Application.get();report=STATE["report"]
    adapter,finish=STATE["adapter"],STATE["finish"]
    module=importlib.import_module(adapter.__package__+".native_preview")
    module.PREVIEW_COMMAND_ID+="_validation"
    module.PREVIEW_EVENT_ID+="_validation"
    errors=[];STATE["runtime_errors"]=errors
    runner=module.NativePreviewRunner(errors.append);STATE["runtime_runner"]=runner
    def compute():
        if cancellation_requested():raise RuntimeError("Validation cancelled before preview compute.")
        target=STATE.get("runtime_target")
        if target is not None:
            return adapter.prepare_hinge(STATE["design"],target.face_a,target.face_b,target.axis_edge,
                                         target.settings,edge_finisher=finish.finish_native_results)
        manager,frame,settings,bodies,plan=STATE["runtime_inputs"]
        return finish.finish_native_results(STATE["design"],manager,frame,settings,bodies,plan=plan)
    def completed(prepared):
        if cancellation_requested():cancel();return
        try:
            bodies=prepared.result_bodies if hasattr(prepared,"result_bodies") else prepared
            if not all(b.isValid and b.isTemporary and b.isSolid and b.lumps.count==1 for _,b in bodies):
                raise RuntimeError("Production preview returned invalid detached geometry.")
            if hasattr(prepared,"preview_bodies"):
                group=adapter.preview_hinge(prepared)
                if not group.isValid or not group.deleteMe():raise RuntimeError("Preview graphics cleanup failed.")
                report["runtime_preview_graphics_created_and_removed"]=True
            report["runtime_preview_transaction_passed"]=True
        except Exception:
            report["runtime_preview_error"]=traceback.format_exc()
            report["runtime_preview_transaction_passed"]=False
        queue_probe_event("runtime-finish")
    def failed(error):
        if cancellation_requested():cancel();return
        report["runtime_preview_transaction_passed"]=False
        report["runtime_preview_error"]=str(error)
        queue_probe_event("runtime-finish")
    runner.request("validation",compute,completed,failed)

def session_preview_start():
    if cancellation_requested():cancel();return
    adapter=STATE["adapter"];target=STATE.get("runtime_target")
    if target is None:
        STATE["report"]["session_sequence_skipped"]="No saved recipe source was available."
        finish_report();return
    module=importlib.import_module(adapter.__package__+".command")
    owner=module.HingeCommands();STATE["sequence_owner"]=owner
    sequence={"steps":[],"step":0,"queued":None,"target":target,"base":target.settings}
    STATE["sequence"]=sequence
    def publish(snapshot):
        if snapshot.get("phase")=="error":
            STATE["report"]["session_sequence_error"]=snapshot.get("message")
            queue_probe_event("session-cleanup")
        elif snapshot.get("phase")=="preview" and sequence.get("cancelling"):
            # Fusion may deliver preview completion before palette_action returns.
            # This is a completed-before-Cancel case, not a queued cancellation.
            STATE["report"]["session_cancel_completed_early"]=True
        elif snapshot.get("phase")=="preview" and sequence["queued"]!=sequence["step"]:
            sequence["queued"]=sequence["step"]
            sequence["steps"].append({"step":sequence["step"],"editing":snapshot["editing"],"revision":snapshot["revision"],"knuckles":snapshot["settings"]["knuckle_count"],"length_mm":snapshot["settings"]["length_mm"],"preview_current":snapshot["previewCurrent"]})
            queue_probe_event("session-next")
    owner.set_state_callback(publish)
    def open_session(editing):
        session=module._Session(owner,None,editing);session.palette_mode=True
        session.session_id=str(uuid.uuid4());owner._sessions.append(session);session.open(sequence["base"])
        if editing:
            session.selection_entities["edit_target"]=target.anchor or target.component;session.changed("edit_target")
        else:
            session.selection_entities.update(face_a=target.face_a,face_b=target.face_b,axis_edge=target.axis_edge)
            session.changed("axis_edge")
        sequence["session"]=session
        return session
    sequence["open"]=open_session
    session=open_session(True)
    owner.palette_action("hinge_preview",session.session_id,revision=0,settings_dict=session.palette_settings.to_dict())


def session_preview_next():
    sequence=STATE["sequence"];owner=STATE["sequence_owner"];session=sequence["session"]
    step=sequence["step"]
    if not session.preview or not session.preview.isValid:raise RuntimeError("Session did not retain its full-body preview.")
    if not session.preview_visibility.pending_count:raise RuntimeError("Session did not lease its old/source body visibility.")
    if step==0:
        settings=replace(session.palette_settings,knuckle_count=3 if session.palette_settings.knuckle_count!=3 else 5)
    elif step==1:
        settings=replace(session.palette_settings,length_mm=sequence["base"].length_mm*.9)
    elif step==2:
        owner.palette_action("hinge_cancel",session.session_id)
        if session.preview_visibility.pending_count:raise RuntimeError("Edit Cancel did not restore visibility.")
        session=sequence["open"](False);settings=session.palette_settings
    elif step==3:
        settings=replace(session.palette_settings,knuckle_count=3 if session.palette_settings.knuckle_count!=3 else 5)
    else:
        settings=replace(session.palette_settings,length_mm=sequence["base"].length_mm*.85)
        sequence["cancelling"]=True
        sequence["step"]+=1
        owner.palette_action("hinge_preview",session.session_id,revision=session.revision+1,settings_dict=settings.to_dict())
        owner.palette_action("hinge_cancel",session.session_id)
        queue_probe_event("session-cancel-check")
        return
    sequence["step"]+=1
    owner.palette_action("hinge_preview",session.session_id,revision=session.revision+1,settings_dict=settings.to_dict())


def session_preview_cleanup():
    owner=STATE.get("sequence_owner")
    if owner is not None:owner.stop()
    sequence=STATE.get("sequence",{})
    report=STATE["report"]
    report["session_sequence_steps"]=sequence.get("steps",[])
    report["session_sequence_passed"]=bool(len(sequence.get("steps",[]))==5 and not report.get("session_sequence_error"))
    finish_report()

class Drive(adsk.core.CustomEventHandler):
 def notify(self,args):
    if cancellation_requested():cancel();return
    try:
      if args.additionalInfo=="runtime-start":
          runtime_preview_check();return
      if args.additionalInfo=="runtime-finish":
          STATE["runtime_runner"].stop()
          STATE["report"]["runtime_preview_errors"]=STATE.get("runtime_errors",[])
          queue_probe_event("session-start");return
      if args.additionalInfo=="session-start":session_preview_start();return
      if args.additionalInfo=="session-next":session_preview_next();return
      if args.additionalInfo=="session-cleanup":session_preview_cleanup();return
      if args.additionalInfo=="session-cancel-check":
          owner=STATE["sequence_owner"]
          if owner._native_preview is not None and owner._native_preview.busy:
              retries=STATE.get("sequence_cancel_retries",0)+1;STATE["sequence_cancel_retries"]=retries
              if retries>4:raise RuntimeError("Cancelled session's native command did not finish.")
              queue_probe_event("session-cancel-check");return
          STATE["report"]["session_cancel_drained"]=True
          session_preview_cleanup();return
      preview_return=STATE["command"].doExecutePreview()
      STATE["report"]["probe_preview_return"]=preview_return
      execute_return=STATE["command"].doExecute(True)
      STATE["report"]["probe_execute_return"]=execute_return
    except Exception:
      STATE["report"]["drive_error"]=traceback.format_exc()
      if STATE.get("sequence_owner") is not None:
          STATE["report"]["session_sequence_error"]=STATE["report"]["drive_error"]
          session_preview_cleanup()
      else:finish_report()
class Destroyed(adsk.core.CommandEventHandler):
 def notify(self,args):
    STATE["own_command_destroyed"]=True
    finish_report()

def finish_report():
    if STATE.get("reported"):return
    cancelled=cancellation_requested()
    if not INPLACE_ONLY and STATE.get("own_command_destroyed") and not STATE.get("runtime_requested") and not cancelled:
      STATE["runtime_requested"]=True
      queue_probe_event("runtime-start")
      return
    STATE["reported"]=True
    report=STATE["report"];report["after"]=snapshot(STATE["design"])
    try:
      report["detached_bodies_survived_rollback"]=bool(STATE.get("detached")) and all(
          body.isValid and body.isTemporary and body.isSolid and body.lumps.count==1 and body.volume>0
          for body in STATE.get("detached",[]))
    except Exception:
      report["detached_bodies_survived_rollback"]=False
    report["original_topology_references_valid"]=all(entity.isValid for entity in STATE.get("original_topology",[]))
    report["unchanged"]=report["after"]==report["before"] and report["original_topology_references_valid"]
    report["success"]=bool(not report.get("diagnostic_only") and not cancelled and report.get("success") and report["unchanged"] and report.get("noop_execute") and report["detached_bodies_survived_rollback"] and (INPLACE_ONLY or (report.get("runtime_preview_transaction_passed") and not report.get("runtime_preview_errors") and report.get("session_sequence_passed") and report.get("session_cancel_drained"))))
    p=Path(STATE.get("context",{}).get("report_path") or STATE["root"]/"output"/"native"/"join-finish-probe.json");p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(report,indent=2),encoding="utf-8")
    app=adsk.core.Application.get();app.log("Partelier joined finish probe: "+str(report["success"])+" -> "+str(p))
    context=STATE.get("context",{})
    app.unregisterCustomEvent(EVENT)
    definition=STATE.get("definition")
    created=STATE.get("created")
    if definition is not None and created is not None:
      definition.commandCreated.remove(created)
    if not context.get("quiet"):
      app.userInterface.messageBox("Joined finish checks "+("passed" if report["success"] else "failed")+".\nModel unchanged: "+str(report["unchanged"])+"\n"+str(p),"Partelier compound finish check")
    prefix=STATE.get("package_name")
    if prefix:
      for module_name in tuple(sys.modules):
        if module_name==prefix or module_name.startswith(prefix+"."):sys.modules.pop(module_name,None)
    callback=context.get("on_complete")
    if callback is not None:callback(report)
    if not context.get("no_auto_terminate"):adsk.autoTerminate(True)

def preview_appearance_check(adapter,target):
    """Render exact copies of current outputs, restore all scene flags afterward."""
    design=STATE["design"];app=adsk.core.Application.get()
    initial_appearance_count=design.appearances.count
    initial_graphics_count=design.rootComponent.customGraphicsGroups.count
    lease_module=importlib.import_module(adapter.__package__+".visibility")
    inplace=importlib.import_module(adapter.__package__+".inplace")
    raw=adapter.prepare_edit_hinge(design,target,replace(target.settings,chamfer_edges=False,fillet_edges=False))
    outputs=inplace.result_bodies(design,target.recipe)
    manager=adsk.fusion.TemporaryBRepManager.get()
    results=tuple((role,manager.copy(body)) for role,body in outputs.items())
    prepared=replace(raw,settings=target.settings,result_bodies=results,preview_bodies=results)
    expected=adapter._preview_appearances(prepared)
    report_path=Path(STATE["context"]["report_path"])
    before_image=report_path.with_name(report_path.stem+"-preview-before.png")
    after_image=report_path.with_name(report_path.stem+"-preview-after.png")
    if not app.activeViewport.saveAsImageFile(str(before_image),1200,900):raise RuntimeError("Could not capture previous preview.")
    old_groups=[];group=None;lease=lease_module.BodyVisibilityLease()
    expected_addin=(STATE["root"]/"Partelier"/"partelier"/"addin.py").resolve()
    for module in tuple(sys.modules.values()):
      location=getattr(module,"__file__",None)
      if not location:continue
      try:matches=Path(location).resolve()==expected_addin
      except Exception:continue
      owner=getattr(module,"_hinge_commands",None) if matches else None
      if owner is not None:
        for session in owner._sessions:
          for candidate in [session.preview]+list(session.retained_preview_groups):
            if candidate is not None and candidate.isValid and not any(candidate==old for old,_ in old_groups):
              old_groups.append((candidate,candidate.isVisible))
    try:
      draw_started=time.perf_counter()
      group=adapter.preview_hinge(prepared)
      draw_ms=(time.perf_counter()-draw_started)*1000
      lease.hide(adapter.preview_hide_bodies(prepared,target))
      for candidate,_ in old_groups:candidate.isVisible=False
      inspected=[]
      STATE["report"]["preview_color_debug"]=inspected
      app.activeViewport.refresh()
      app.activeViewport.saveAsImageFile(str(after_image),1200,900)
      bodies=[adsk.fusion.CustomGraphicsBRepBody.cast(group.item(index)) for index in range(group.count)]
      bodies=[graphic for graphic in bodies if graphic is not None]
      for (role,_),graphic in zip(results,bodies):
        effect=adsk.fusion.CustomGraphicsAppearanceColorEffect.cast(graphic.color)
        inspected.append({"role":role,"actual_type":graphic.color.objectType,"expected_appearance":expected[role.split("_",1)[0]].name,"expected_id":expected[role.split("_",1)[0]].id,"actual_appearance":None if effect is None else effect.appearance.name,"actual_id":None if effect is None else effect.appearance.id,"equal":effect is not None and effect.appearance==expected[role.split("_",1)[0]]})
        if effect is None or effect.appearance.id!=expected[role.split("_",1)[0]].id:
          raise RuntimeError("Preview did not retain the existing Fusion appearance.")
        opacity=graphic.getOpacity()
        if not opacity[0] or abs(opacity[1]-1.0)>1e-9 or not opacity[2]:raise RuntimeError("Preview was not fully opaque.")
        inspected.append({"role":role,"appearance":effect.appearance.name,"effect":effect.objectType,"opacity":opacity[1],"override":opacity[2]})
      app.activeViewport.refresh()
      if not app.activeViewport.saveAsImageFile(str(after_image),1200,900):raise RuntimeError("Could not capture the Fusion appearance preview.")
      return {"success":True,"graphics":inspected,"draw_ms":draw_ms,"outline_batches":group.count-len(bodies),"appearance_count_before":initial_appearance_count,"appearance_count_after":design.appearances.count,"before_image":str(before_image),"after_image":str(after_image)}
    finally:
      if group is not None and group.isValid:group.deleteMe()
      lease.restore()
      for candidate,visible in old_groups:
        if candidate.isValid:candidate.isVisible=visible
      app.activeViewport.refresh()
      if design.appearances.count!=initial_appearance_count:raise RuntimeError("Preview added a persistent appearance.")
      if design.rootComponent.customGraphicsGroups.count!=initial_graphics_count:raise RuntimeError("Preview left an owned graphics group behind.")


def run(context):
    app=adsk.core.Application.get();design=adsk.fusion.Design.cast(app.activeProduct)
    STATE.clear();STATE.update(root=Path(__file__).resolve().parents[3],design=design,
                                context=context if isinstance(context,dict) else {})
    if design is None:raise ValueError("Open a Fusion Design and leave it idle before validation.")
    STATE["original_topology"]=[entity for body in design.rootComponent.bRepBodies
                                  for collection in (body.faces,body.edges) for entity in collection]
    STATE["report"]={"fusion_version":app.version,"before":snapshot(design),"cases":[],"success":False}
    STATE["report"]["live_product"]=live_product_state(STATE["root"],design)
    if SELECTION_STATE_ONLY:
      report=STATE["report"]
      report.update(diagnostic_only=True,read_only=True,selections=snap_selection_state(STATE["root"],design))
      for entry in report["selections"]["sessions"]:
        try:
          hinge_adapter,_,_,_=load(STATE["root"])
          snap=importlib.import_module(hinge_adapter.__package__.rsplit(".",1)[0]+".snap_fit.fusion")
          settings_module=importlib.import_module(snap.__package__+".settings")
          entities=[]
          for key in ("face_a","face_b","axis_edge"):
            resolved=design.findEntityByToken(entry["selections"][key]["token"])
            if len(resolved)!=1:raise RuntimeError("Selection no longer resolves uniquely.")
            entities.append(resolved[0])
          prepared=snap.prepare_snap_fit(design,*entities,settings_module.SnapFitSettings.from_dict(entry["settings"]))
          entry["candidate"]={"success":True,"canonical_edge_body":prepared.axis_edge.body.name,
                               "timings":prepared.timings,"solids":[{"role":role,"volume":body.volume,"lumps":body.lumps.count} for role,body in prepared.result_bodies]}
        except Exception:entry["candidate"]={"success":False,"error":traceback.format_exc()}
      report["saved_snap_previews"]=[]
      try:
        hinge_adapter,_,_,_=load(STATE["root"])
        snap=importlib.import_module(hinge_adapter.__package__.rsplit(".",1)[0]+".snap_fit.fusion")
        anchors=[feature for feature in design.rootComponent.features.baseFeatures
                 if feature.attributes.itemByName(snap.ATTRIBUTE_GROUP,snap.RECIPE_NAME) is not None]
        for anchor in anchors[:4]:
          item={"styles":[]}
          report["saved_snap_previews"].append(item)
          target=snap.read_edit_target(design,anchor)
          item.update(recipe_version=target.recipe["version"],loaded_style=target.settings.snap_style,
                      loaded_chamfer=target.settings.chamfer_edges,loaded_support=target.settings.print_support)
          for style in ("standard","tapered","twin"):
            values=replace(target.settings,snap_style=style,chamfer_edges=True,chamfer_size_mm=.3,print_support=True)
            try:
              prepared=snap.prepare_edit_snap_fit(design,target,values)
              item["styles"].append({"style":style,"success":True,"timings":prepared.timings,
                    "solids":[{"role":role,"volume":body.volume,"lumps":body.lumps.count} for role,body in prepared.result_bodies]})
            except Exception:item["styles"].append({"style":style,"success":False,"error":traceback.format_exc()})
      except Exception:report["saved_snap_preview_error"]=traceback.format_exc()
      report["after"]=snapshot(design)
      report["unchanged"]=report["before"]==report["after"]
      report["success"]=report["unchanged"]
      Path(STATE["context"]["report_path"]).write_text(json.dumps(report,indent=2),encoding="utf-8")
      for prefix in STATE.get("package_names",[]):
        for module_name in tuple(sys.modules):
          if module_name==prefix or module_name.startswith(prefix+"."):sys.modules.pop(module_name,None)
      STATE["context"]["on_complete"](report)
      return
    if LIVE_STATE_ONLY:
      report=STATE["report"];report.update(success=True,diagnostic_only=True,read_only=True)
      try:
        adapter,_,_,_=load(STATE["root"])
        target=adapter.read_edit_target(design,design.rootComponent)
        report["root_edit_selection"]={"success":True,"recipe_version":target.recipe["version"],"feature_id":target.feature_id,"settings":target.settings.to_dict()}
        module=importlib.import_module(adapter.__package__+".command")
        owner=module.HingeCommands();session=module._Session(owner,None,True)
        session.palette_mode=True;session.session_id="validation-root-selection"
        owner._sessions.append(session)
        try:
          session.open(module.HingeSettings())
          session.selection_entities["edit_target"]=design.rootComponent
          session.changed("edit_target")
          if not session.edit_target_loaded or session.phase!="ready" or session.palette_settings!=target.settings:
            raise RuntimeError("Actual Edit session did not load the selected Part's saved dimensions: "+session.message)
          report["root_edit_selection"]["session_dimensions_loaded"]=True
          report["root_edit_selection"]["session_phase"]=session.phase
        finally:session.close();owner.stop()
        report["preview_appearance"]=preview_appearance_check(adapter,target)
      except Exception:report["root_edit_selection"]={"success":False,"error":traceback.format_exc()}
      report["after"]=snapshot(design)
      report["unchanged"]=report["before"]==report["after"]
      report["success"]=bool(report["unchanged"] and report.get("root_edit_selection",{}).get("success") and report.get("preview_appearance",{}).get("success"))
      path=Path(STATE["context"]["report_path"])
      path.write_text(json.dumps(report,indent=2),encoding="utf-8")
      prefix=STATE.get("package_name")
      if prefix:
        for module_name in tuple(sys.modules):
          if module_name==prefix or module_name.startswith(prefix+"."):sys.modules.pop(module_name,None)
      STATE["context"]["on_complete"](report)
      return
    recipes=[]
    STATE["active_anchors"]=[]
    for feature in design.rootComponent.features.baseFeatures:
      attr=feature.attributes.itemByName("sktech_partelier_hinge_8c319ce2","recipe")
      if attr:
        recipes.append(json.loads(attr.value))
        STATE["active_anchors"].append(feature)
    STATE["report"]["active_recipes"]=recipes
    adapter,planner,settings_module,finish=load(STATE["root"])
    STATE.update(adapter=adapter,planner=planner,settings_module=settings_module,finish=finish)
    event=app.registerCustomEvent(EVENT);driver=Drive();event.add(driver);HANDLERS.append(driver)
    definition=app.userInterface.commandDefinitions.itemById(COMMAND)
    if definition is None:definition=app.userInterface.commandDefinitions.addButtonDefinition(COMMAND,"Partelier compound finish probe","Check native finish rollback")
    created=Created();definition.commandCreated.add(created);HANDLERS.append(created)
    STATE.update(definition=definition,created=created)
    if not STATE["context"].get("no_auto_terminate"):adsk.autoTerminate(False)
    if not definition.execute():raise RuntimeError("Fusion could not start the joined finish check.")

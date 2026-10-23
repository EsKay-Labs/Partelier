"""Fixed development-only snap-fit checks on owned rollback-only fixtures.

This script has no arbitrary input/path/eval surface. The bridge chooses this
fixed file, and the callback context controls reporting/cancellation only. Every
persistent geometry test runs in executePreview with isValidResult=False; the
following execute handler is deliberately empty. The user's model is compared
again only after the command is destroyed and its preview has rolled back.
"""

from dataclasses import replace
import importlib
import importlib.util
import json
from pathlib import Path
import sys
import traceback
import uuid
from types import SimpleNamespace

import adsk.core
import adsk.fusion


EVENT = "sktech_partelier_snap_fit_probe_event_804512bd"
COMMAND = "sktech_partelier_snap_fit_probe_command_804512bd"
STATE = {}
HANDLERS = []


def _items(collection):
    return tuple(collection.item(index) for index in range(collection.count))


def snapshot(design):
    root = design.rootComponent
    return {
        "timeline": design.timeline.count,
        "marker": design.timeline.markerPosition,
        "appearances": design.appearances.count,
        "bodies": [{"name": body.name, "volume": round(float(body.volume), 9),
                    "faces": body.faces.count, "edges": body.edges.count,
                    "visible": body.isVisible, "light_bulb": body.isLightBulbOn}
                   for body in _items(root.bRepBodies)],
        "graphics": [{"visible": group.isVisible} for group in _items(root.customGraphicsGroups)],
    }


def load(root):
    name = "_partelier_snap_probe_" + uuid.uuid4().hex
    STATE["package_name"] = name
    path = root / "Partelier" / "partelier"
    spec = importlib.util.spec_from_file_location(name, path / "__init__.py",
                                                 submodule_search_locations=[str(path)])
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return tuple(importlib.import_module(name + ".tools.snap_fit." + leaf)
                 for leaf in ("fusion", "settings"))


def cancellation_requested():
    callback = STATE.get("context", {}).get("cancel_requested")
    try:
        requested = bool(STATE.get("cancelled") or (callback is not None and callback()))
    except Exception:
        requested = True
    if requested:
        STATE["cancelled"] = True
        STATE.get("report", {})["cancelled"] = True
    return requested


def queue_probe_event():
    # Some Fusion releases return False even when the custom event is delivered.
    result = adsk.core.Application.get().fireCustomEvent(EVENT)
    STATE["report"]["queue_return"] = result


def fixture(design, *, span=60.0, thickness=3.0, upper=24.0, gap=0.0, lipped=False):
    """Create exactly two owned wall boxes with an outward X=0 face and Z=0 seam."""
    root = design.rootComponent
    manager = adsk.fusion.TemporaryBRepManager.get()
    feature = root.features.baseFeatures.add()
    feature.name = "Partelier disposable snap-fit sources"
    if not feature.startEdit():
        raise RuntimeError("Could not edit the disposable source fixture.")
    try:
        temporary = []
        for low_z, high_z in ((-24.0, 0.0), (gap, upper)):
            bounds = adsk.core.OrientedBoundingBox3D.create(
                adsk.core.Point3D.create(-thickness / 20.0, 0, (low_z + high_z) / 20.0),
                adsk.core.Vector3D.create(1, 0, 0), adsk.core.Vector3D.create(0, 1, 0),
                thickness / 10.0, span / 10.0, (high_z - low_z) / 10.0)
            body = manager.createBox(bounds)
            if body is None:
                raise RuntimeError("Could not construct the disposable wall fixture.")
            temporary.append(body)
        if lipped:
            adapter=STATE["adapter"]
            frame=adapter.hinge.HingeFrame((0,0,0),(1,0,0),(0,1,0),(0,0,1))
            def box(values):return adapter.hinge._box(manager,frame,adapter.BoxBounds(*values))
            def boolean(target,tool,operation):
                if not manager.booleanOperation(target,tool,operation):
                    raise RuntimeError("Could not construct the internal lip fixture.")
            operations=adsk.fusion.BooleanTypes
            boolean(temporary[0],box((-3,-2,-3,3,-.2,4)),operations.UnionBooleanType)
            boolean(temporary[1],box((-3.2,-1.7,-3.3,3.3,gap-.1,4.3)),operations.DifferenceBooleanType)
            boolean(temporary[1],box((-3,-2,10,16,-4,gap+.2)),operations.UnionBooleanType)
            boolean(temporary[0],box((-3.2,-1.7,9.7,16.3,-4.3,.1)),operations.DifferenceBooleanType)
        for body in temporary:
            if root.bRepBodies.add(body,feature) is None:
                raise RuntimeError("Could not persist the disposable wall fixture.")
    finally:
        if not feature.finishEdit():
            raise RuntimeError("Could not finish the disposable wall fixture.")
    bodies = tuple(sorted(_items(feature.bodies), key=lambda body: body.boundingBox.minPoint.z))
    if len(bodies) != 2:
        raise RuntimeError("Disposable snap-fit fixture did not contain exactly two bodies.")
    for body, role in zip(bodies, ("A", "B")):
        body.name = "Owned snap-fit source " + role
    bodies[1].isLightBulbOn = False
    faces = tuple(next(face for face in _items(body.faces)
                       if adsk.core.Plane.cast(face.geometry) is not None
                       and abs(face.boundingBox.minPoint.x) < 1e-7
                       and abs(face.boundingBox.maxPoint.x) < 1e-7) for body in bodies)
    edge = next(edge for edge in _items(faces[0].edges)
                if abs(edge.startVertex.geometry.z) < 1e-7
                and abs(edge.endVertex.geometry.z) < 1e-7)
    return feature, bodies, faces, edge


def _inside(body, x, y, z):
    state = body.pointContainment(adsk.core.Point3D.create(x / 10.0, y / 10.0, z / 10.0))
    inside = adsk.fusion.PointContainment.PointInsidePointContainment
    outside = adsk.fusion.PointContainment.PointOutsidePointContainment
    if state not in (inside, outside):
        raise RuntimeError("A clearance witness landed on an unexpected boundary.")
    return state == inside


def inspect_preview(prepared):
    """Witness beam, gap, latch/pocket and receiver back wall for every unit."""
    bodies = dict(prepared.result_bodies)
    if set(bodies) != {"A", "B"} or len(prepared.result_bodies) != 2:
        raise RuntimeError("Preview did not return exactly the two final body roles.")
    if not all(body.isValid and body.isTemporary and body.isSolid and body.lumps.count == 1
               and body.volume > 0 for body in bodies.values()):
        raise RuntimeError("Preview returned invalid or persistent geometry.")
    settings = prepared.settings
    shoulder = settings.reach_mm - settings.lead_in_mm
    outer = settings.clearance_mm + settings.thickness_mm
    witnesses = []
    for unit in prepared.plan.units:
        y = unit.center_y_mm
        # Fixture/frame orientation along Y can reverse; symmetric walls cover both.
        samples = [
            ("beam", (settings.clearance_mm + settings.thickness_mm / 2, y, shoulder / 2), True, False),
            ("beam_gap", (settings.clearance_mm / 2, y, shoulder / 2), False, False),
            ("hook", (-settings.hook_depth_mm / 2, y, shoulder + settings.clearance_mm / 2), True, False),
            ("pocket_side", (-settings.hook_depth_mm / 2,
                             y + settings.width_mm / 2 + settings.clearance_mm / 2,
                             shoulder + settings.clearance_mm / 2), False, False),
            ("back_wall", (-settings.hook_depth_mm - settings.clearance_mm - .2,
                            y, shoulder + settings.clearance_mm / 2), False, True),
            ("beam_outer_gap", (outer + settings.clearance_mm / 2,
                                 y, shoulder + settings.clearance_mm / 2), False, False),
        ]
        for label, point, expected_a, expected_b in samples:
            global_point = prepared.frame.point_mm(*point)
            actual = (_inside(bodies["A"], *global_point), _inside(bodies["B"], *global_point))
            if actual != (expected_a, expected_b):
                raise RuntimeError("Snap-fit witness " + label + " has incorrect material/clearance: " + str(actual))
            witnesses.append({"label": label, "point_mm": point, "inside_a": actual[0], "inside_b": actual[1]})
    if len(prepared.plan.units) != settings.snap_count:
        raise RuntimeError("The plan did not produce the requested clasp count.")
    STATE.setdefault("detached", []).extend(bodies.values())
    return witnesses


def _resolve_one(design, token):
    values = design.findEntityByToken(token)
    if values is None or len(values) != 1:
        raise RuntimeError("A native body reference was lost or split.")
    return values[0]


def _identity_check(design, targets, tokens, names, flags, count):
    if design.rootComponent.bRepBodies.count != count:
        raise RuntimeError("Native snap-fit persistence left duplicate or unconsumed bodies.")
    for body, token, name, flag in zip(targets, tokens, names, flags):
        if (not body.isValid or _resolve_one(design, token) != body or body.name != name
                or body.isLightBulbOn != flag):
            raise RuntimeError("Native persistence changed the selected body identity, name or visibility.")


def gap_cases():
    """Gap picking and lips that cross the exterior seam, with in-place rebuild."""
    design=STATE["design"]
    adapter=STATE["adapter"]
    settings=STATE["settings_module"].SnapFitSettings()
    for lipped in (False,True):
        _,targets,faces,edge_a=fixture(design,gap=.3,lipped=lipped)
        edge_b=next(edge for edge in _items(faces[1].edges)
                    if abs(edge.startVertex.geometry.z-.03)<1e-7 and abs(edge.endVertex.geometry.z-.03)<1e-7)
        before=snapshot(design)
        a=adapter.prepare_snap_fit(design,*faces,edge_a,settings)
        b=adapter.prepare_snap_fit(design,*faces,edge_b,settings)
        if b.axis_edge!=edge_a or b.source_signature!=a.source_signature:
            raise RuntimeError("A pick across the gap did not canonicalize to the same base rim.")
        if snapshot(design)!=before:
            raise RuntimeError("Gap preview modified the source bodies.")
        witnesses=inspect_preview(b)
        count=design.rootComponent.bRepBodies.count
        tokens=tuple(body.entityToken for body in targets)
        names=tuple(body.name for body in targets)
        flags=tuple(body.isLightBulbOn for body in targets)
        anchor=adapter.create_snap_fit(design,b)
        _identity_check(design,targets,tokens,names,flags,count)
        target=adapter.read_edit_target(design,anchor)
        settings2=replace(settings,width_mm=7)
        rebuilt=adapter.prepare_edit_snap_fit(design,target,settings2)
        if adapter.rebuild_snap_fit(design,target,rebuilt)!=anchor:
            raise RuntimeError("Gap rebuild replaced its feature.")
        _identity_check(design,targets,tokens,names,flags,count)
        STATE["report"]["cases"].append({"name":"internal_lips_gap_create_rebuild" if lipped else "lid_edge_gap_create_rebuild",
             "success":True,"gap_mm":.3,"witnesses":witnesses})


def cases():
    design = STATE["design"]
    adapter, settings_module = STATE["adapter"], STATE["settings_module"]
    settings = settings_module.SnapFitSettings()
    report = STATE["report"]
    _, targets, faces, edge = fixture(design)
    count = design.rootComponent.bRepBodies.count
    tokens = tuple(body.entityToken for body in targets)
    names = tuple(body.name for body in targets)
    flags = tuple(body.isLightBulbOn for body in targets)
    initial_volumes = tuple(float(body.volume) for body in targets)
    prepared = adapter.prepare_snap_fit(design, *faces, edge, settings)
    report["cases"].append({"name": "default_preview", "success": True,
                             "witnesses": inspect_preview(prepared)})
    if tuple(float(body.volume) for body in targets) != initial_volumes:
        raise RuntimeError("Preview preparation modified its source solids.")
    triple = adapter.prepare_snap_fit(design, *faces, edge, replace(settings, snap_count=3))
    report["cases"].append({"name": "three_clasp_preview", "success": True,
                             "witnesses": inspect_preview(triple)})
    anchor = adapter.create_snap_fit(design, prepared)
    _identity_check(design, targets, tokens, names, flags, count)
    record = adapter.read_edit_target(design, anchor)
    if record.settings != settings:
        raise RuntimeError("Create did not store the complete snap-fit settings.")
    for selected in targets:
        if adapter.read_edit_target(design, selected).anchor != anchor:
            raise RuntimeError("Edit selection did not recover the owned snap-fit feature.")
    owned_count = sum(feature.attributes.itemByName(adapter.ATTRIBUTE_GROUP, "pair") is not None
                      for feature in _items(design.rootComponent.features.baseFeatures))
    try:
        root_target = adapter.read_edit_target(design, design.rootComponent)
    except ValueError:
        if owned_count == 1:
            raise
    else:
        if owned_count != 1 or root_target.anchor != anchor:
            raise RuntimeError("Part selection did not require exactly one owned snap-fit.")
    combine_count = design.rootComponent.features.combineFeatures.count
    combine_tokens = dict(record.record.recipe["combines"])
    report["cases"].append({"name": "create_in_place", "success": True,
                             "body_count": count, "feature_id": record.record.feature_id})
    # A later independent fixture exercises rebuilding an earlier owned feature.
    fixture(design, span=40.0)
    count = design.rootComponent.bRepBodies.count
    changed = replace(settings, snap_count=3, width_mm=6.0, reach_mm=14.0)
    rebuilt = adapter.prepare_edit_snap_fit(design, record, changed)
    witnesses = inspect_preview(rebuilt)
    updated = adapter.rebuild_snap_fit(design, record, rebuilt)
    if updated != anchor:
        raise RuntimeError("Rebuild replaced the owned BaseFeature.")
    _identity_check(design, targets, tokens, names, flags, count)
    fresh = adapter.read_edit_target(design, anchor)
    if (fresh.settings != changed or fresh.record.recipe["combines"] != combine_tokens
            or design.rootComponent.features.combineFeatures.count != combine_count):
        raise RuntimeError("Rebuild changed native Combine references or failed to save new dimensions.")
    report["cases"].append({"name": "rebuild_same_history", "success": True,
                             "witnesses": witnesses, "native_combines": 4})
    for name, dimensions in (("short_rim_refused", {"span": 12.0}),
                             ("thin_wall_refused", {"thickness": 1.0}),
                             ("short_receiver_refused", {"upper": 12.0})):
        _, _, invalid_faces, invalid_edge = fixture(design, **dimensions)
        before = snapshot(design)
        try:
            adapter.prepare_snap_fit(design, *invalid_faces, invalid_edge, settings)
        except ValueError as error:
            if snapshot(design) != before:
                raise RuntimeError("A refused selection modified the document.") from error
            report["cases"].append({"name": name, "success": True,
                                     "expected_refusal": True, "message": str(error)})
        else:
            raise RuntimeError("Unsupported fixture was accepted: " + name)
    gap_cases()
    session_checks()
    report["geometry_checks_passed"] = True


def session_checks():
    """Production logical sessions; persistence remains in the OUTER rollback."""
    design = STATE["design"]
    adapter, settings_module = STATE["adapter"], STATE["settings_module"]
    module = importlib.import_module(adapter.__package__ + ".command")
    owner = module.SnapCommands()
    STATE["session_owner"] = owner
    states = []
    owner.set_state_callback(lambda value: states.append(
        {key: value.get(key) for key in ("phase", "editing", "revision", "previewCurrent")}))
    _, targets, faces, edge = fixture(design)
    settings = settings_module.SnapFitSettings()
    tokens = tuple(body.entityToken for body in targets)
    names = tuple(body.name for body in targets)
    flags = tuple(body.isLightBulbOn for body in targets)
    count = design.rootComponent.bRepBodies.count
    initial = snapshot(design)
    graphics_count = design.rootComponent.customGraphicsGroups.count

    def new_session(editing=False, anchor=None, values=settings):
        session = module._Session(owner, design, values, editing)
        owner._session = session
        if editing:
            session.set_selection("edit_target", anchor)
        else:
            for key, entity in zip(module.SELECTIONS, (*faces, edge)):
                session.set_selection(key, entity)
        return session

    try:
        session = new_session()
        owner.palette_action("snap_preview", session.session_id, revision=0,
                             settings_dict=settings.to_dict())
        if not session.preview_current or any(body.isLightBulbOn for body in targets):
            raise RuntimeError("Production session did not draw its preview and hide source solids.")
        updated_settings = replace(settings, width_mm=6.0)
        owner.palette_action("snap_preview", session.session_id, revision=1,
                             settings_dict=updated_settings.to_dict())
        if not session.preview_current or session.revision != 1:
            raise RuntimeError("Production session did not refresh its edited preview.")
        owner.palette_action("snap_cancel", session.session_id)
        if snapshot(design) != initial or owner._session is not None:
            raise RuntimeError("Production session Cancel changed source geometry or visibility.")
        STATE["report"]["cases"].append({"name": "session_preview_update_cancel", "success": True})
        session = new_session(values=updated_settings)
        session.show_preview()
        args = SimpleNamespace(executeFailed=False)
        session.execute(args)
        if args.executeFailed or session.phase != "created":
            raise RuntimeError("Production session Create failed: " + getattr(args, "executeFailedMessage", session.message))
        session.close()
        _identity_check(design, targets, tokens, names, flags, count)
        target = adapter.read_edit_target(design, targets[0])
        anchor = target.anchor
        if target.settings != updated_settings:
            raise RuntimeError("Production session Create lost its edited dimensions.")
        session = new_session(editing=True, anchor=targets[0])
        if session.edit_target is None or session.settings != updated_settings:
            raise RuntimeError("Production Edit session did not load the body's saved dimensions.")
        changed = replace(updated_settings, snap_count=2)
        owner.palette_action("snap_preview", session.session_id, revision=1, settings_dict=changed.to_dict())
        args = SimpleNamespace(executeFailed=False)
        session.execute(args)
        if args.executeFailed or session.phase != "created":
            raise RuntimeError("Production session Rebuild failed: " + getattr(args, "executeFailedMessage", session.message))
        session.close()
        _identity_check(design, targets, tokens, names, flags, count)
        final = adapter.read_edit_target(design, anchor)
        if final.anchor != anchor or final.settings != changed:
            raise RuntimeError("Production session Rebuild changed its feature or lost saved dimensions.")
        if design.rootComponent.customGraphicsGroups.count != graphics_count:
            raise RuntimeError("Production session workflow left preview graphics behind.")
        STATE["report"]["cases"].append({"name": "session_create_edit_rebuild", "success": True,
                                         "settings": final.settings.to_dict()})
        STATE["report"]["session_states"] = states
    finally:
        owner.stop()
        STATE.pop("session_owner", None)


class Preview(adsk.core.CommandEventHandler):
    def notify(self, args):
        args.isValidResult = False
        if cancellation_requested():
            return
        try:
            cases()
        except Exception:
            STATE["report"]["error"] = traceback.format_exc()


class Execute(adsk.core.CommandEventHandler):
    def notify(self, args):
        STATE["report"]["noop_execute"] = True


class Created(adsk.core.CommandCreatedEventHandler):
    def notify(self, args):
        command = args.command
        STATE["command"] = command
        command.isAutoExecute = False
        command.isExecutedWhenPreEmpted = False
        command.isRepeatable = False
        for event, handler in ((command.destroy, Destroyed()), (command.executePreview, Preview()),
                               (command.execute, Execute())):
            if event.add(handler) is False:
                STATE["report"]["error"] = "Could not bind the owned probe command."
                command.isAutoExecute = True
                return
            HANDLERS.append(handler)
        queue_probe_event()


class Drive(adsk.core.CustomEventHandler):
    def notify(self, args):
        if cancellation_requested():
            cancel()
            return
        try:
            command = STATE["command"]
            STATE["report"]["preview_return"] = command.doExecutePreview()
            STATE["report"]["execute_return"] = command.doExecute(True)
        except Exception:
            STATE["report"]["drive_error"] = traceback.format_exc()
            cancel()


class Destroyed(adsk.core.CommandEventHandler):
    def notify(self, args):
        STATE["destroyed"] = True
        finish_report()


def cancel():
    """Cooperative cancellation closes only this script's owned command."""
    STATE["cancelled"] = True
    STATE.get("report", {})["cancelled"] = True
    owner = STATE.get("session_owner")
    if owner is not None:
        owner.stop()
    command = STATE.get("command")
    if command is not None and not STATE.get("destroyed"):
        app = adsk.core.Application.get()
        if app.userInterface.activeCommand == COMMAND:
            app.userInterface.terminateActiveCommand()
        if not STATE.get("destroyed"):
            return
    finish_report()


def finish_report():
    if STATE.get("reported"):
        return
    STATE["reported"] = True
    report = STATE["report"]
    report["after"] = snapshot(STATE["design"])
    references = STATE["original_references"]
    report["original_references_valid"] = all(entity.isValid for entity in references)
    detached = STATE.get("detached", ())
    report["detached_survived_rollback"] = bool(detached) and all(
        body.isValid and body.isTemporary and body.isSolid and body.lumps.count == 1 for body in detached)
    report["unchanged"] = report["after"] == report["before"] and report["original_references_valid"]
    report["success"] = bool(report.get("geometry_checks_passed") and report.get("noop_execute")
                             and STATE.get("destroyed") and report["unchanged"]
                             and report["detached_survived_rollback"] and not cancellation_requested()
                             and not report.get("error") and not report.get("drive_error"))
    context = STATE["context"]
    path = Path(context.get("report_path") or STATE["root"] / "output/native/snap-fit-probe.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    app = adsk.core.Application.get()
    app.log("Partelier snap-fit probe: " + str(report["success"]) + " -> " + str(path))
    app.unregisterCustomEvent(EVENT)
    definition = STATE.get("definition")
    created = STATE.get("created")
    if definition is not None and created is not None:
        definition.commandCreated.remove(created)
    if definition is not None and definition.isValid:
        definition.deleteMe()
    prefix = STATE.get("package_name")
    if prefix:
        for name in tuple(sys.modules):
            if name == prefix or name.startswith(prefix + "."):
                sys.modules.pop(name, None)
    callback = context.get("on_complete")
    if callback is not None:
        callback(report)
    if not context.get("no_auto_terminate"):
        adsk.autoTerminate(True)


def run(context):
    app = adsk.core.Application.get()
    design = adsk.fusion.Design.cast(app.activeProduct)
    if design is None or design.designType != adsk.fusion.DesignTypes.ParametricDesignType:
        raise ValueError("Open a parametric Fusion Design before snap-fit validation.")
    if design.timeline.markerPosition != design.timeline.count:
        raise ValueError("Move the history marker to the end before snap-fit validation.")
    STATE.clear()
    STATE.update(root=Path(__file__).resolve().parents[3], design=design,
                 context=context if isinstance(context, dict) else {})
    STATE["original_references"] = [entity for body in _items(design.rootComponent.bRepBodies)
                                    for entity in (body, *_items(body.faces), *_items(body.edges))]
    STATE["report"] = {"scenario": "snap_fit", "fusion_version": app.version,
                       "before": snapshot(design), "cases": [], "success": False}
    STATE["adapter"], STATE["settings_module"] = load(STATE["root"])
    event = app.registerCustomEvent(EVENT)
    if event is None:
        raise RuntimeError("Could not register the fixed snap-fit probe event.")
    driver = Drive()
    if event.add(driver) is False:
        app.unregisterCustomEvent(EVENT)
        raise RuntimeError("Could not bind the fixed snap-fit probe event.")
    HANDLERS.append(driver)
    definition = app.userInterface.commandDefinitions.itemById(COMMAND)
    if definition is not None:
        app.unregisterCustomEvent(EVENT)
        raise RuntimeError("The owned snap-fit probe command already exists; stop its previous run first.")
    definition = app.userInterface.commandDefinitions.addButtonDefinition(
        COMMAND, "Partelier snap-fit probe", "Run fixed rollback-only snap-fit checks")
    created = Created()
    if definition.commandCreated.add(created) is False:
        app.unregisterCustomEvent(EVENT)
        definition.deleteMe()
        raise RuntimeError("Could not bind the fixed snap-fit command.")
    HANDLERS.append(created)
    STATE.update(definition=definition, created=created)
    if not STATE["context"].get("no_auto_terminate"):
        adsk.autoTerminate(False)
    if not definition.execute():
        raise RuntimeError("Fusion could not start the fixed snap-fit probe.")

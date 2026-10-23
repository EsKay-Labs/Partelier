"""Fixed development-only snap-fit checks on owned rollback-only fixtures.

This script has no arbitrary input/path/eval surface. The bridge chooses this
fixed file, and the callback context controls reporting/cancellation only. Every
persistent geometry test runs in executePreview with isValidResult=False; the
following execute handler is deliberately empty. The user's model is compared
again only after the command is destroyed and its preview has rolled back.
"""

from dataclasses import replace
import hashlib
import importlib
import importlib.util
import json
import math
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


def _local_point(frame, point):
    return STATE["adapter"].hinge._local_mm(frame, point)


def _rounded(values):
    rounded = tuple(round(float(value), 7) for value in values)
    return tuple(0.0 if value == 0 else value for value in rounded)


def _face_geometry(face, frame):
    """Whole trimmed fixture surface, independent of result face ordering."""
    plane = adsk.core.Plane.cast(face.geometry)
    if plane is None:
        raise RuntimeError("A fixed polyhedral fixture unexpectedly acquired a curved face.")
    normal = (float(plane.normal.x), float(plane.normal.y), float(plane.normal.z))
    if face.isParamReversed:
        normal = tuple(-value for value in normal)
    local_normal = tuple(sum(a * b for a, b in zip(normal, axis))
                         for axis in (frame.x_axis, frame.y_axis, frame.z_axis))
    vertices = sorted(_rounded(_local_point(frame, vertex.geometry)) for vertex in _items(face.vertices))
    edges = []
    for edge in _items(face.edges):
        endpoints = sorted((_rounded(_local_point(frame, edge.startVertex.geometry)),
                            _rounded(_local_point(frame, edge.endVertex.geometry))))
        edges.append((edge.geometry.objectType, round(float(edge.length) * 10, 7), endpoints))
    return {"normal": _rounded(local_normal), "area_mm2": round(float(face.area) * 100, 7),
            "vertices_mm": vertices, "edges": sorted(edges), "loops": face.loops.count}


def _geometry_hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def protected_geometry(prepared):
    """Require exact inner-beam/catch trims and the entire receiver unchanged."""
    bodies = dict(prepared.result_bodies)
    settings = prepared.settings
    shoulder = settings.reach_mm - settings.lead_in_mm
    faces_a = [(face, _face_geometry(face, prepared.frame)) for face in _items(bodies["A"].faces)]
    protected = []
    for unit_index, unit in enumerate(prepared.plan.units):
        for arm_index, arm in enumerate(unit.arms):
            for role in ("inner_beam", "catch"):
                matching = []
                for _, geometry in faces_a:
                    vertices = geometry["vertices_mm"]
                    normal = geometry["normal"]
                    if not vertices or any(point[1] < arm.beam.y_min_mm - 1e-6
                                           or point[1] > arm.beam.y_max_mm + 1e-6 for point in vertices):
                        continue
                    if role == "inner_beam":
                        selected = (normal[0] < -.999999 and abs(normal[1]) < 1e-6 and abs(normal[2]) < 1e-6
                                    and all(abs(point[0] - settings.clearance_mm) < 1e-6
                                            and -1e-6 <= point[2] <= shoulder + 1e-6 for point in vertices))
                    else:
                        selected = (normal[2] < -.999999 and abs(normal[0]) < 1e-6 and abs(normal[1]) < 1e-6
                                    and all(abs(point[2] - shoulder) < 1e-6
                                            and -settings.hook_depth_mm - 1e-6 <= point[0] <= settings.clearance_mm + 1e-6
                                            for point in vertices))
                    if selected:
                        matching.append(geometry)
                if len(matching) != 1:
                    raise RuntimeError("A protected " + role + " surface is missing, split or moved.")
                protected.append({"unit": unit_index, "arm": arm_index, "surface": role,
                                  "sha256": _geometry_hash(matching[0]), "area_mm2": matching[0]["area_mm2"]})
    receiver = sorted((_face_geometry(face, prepared.frame) for face in _items(bodies["B"].faces)),
                      key=lambda value: json.dumps(value, sort_keys=True))
    return {"A_protected": protected,
            "B_whole": _geometry_hash({"volume_cm3": round(float(bodies["B"].volume), 9), "faces": receiver})}


def inspect_corner_finish(prepared):
    settings = prepared.settings
    if not settings.chamfer_edges or settings.snap_family not in {"hook", "torsion"}:
        return []
    bodies = dict(prepared.result_bodies)
    size = settings.chamfer_size_mm
    checks = []
    for unit in prepared.plan.units:
        for arm in unit.arms:
            back = settings.clearance_mm-(settings.clearance_mm+settings.hook_depth_mm)*.05*size/settings.lead_in_mm
            for side, y in ((-1, arm.beam.y_min_mm), (1, arm.beam.y_max_mm)):
                point = (back, y-side*.1*size, settings.reach_mm-.1*size)
                if _inside(bodies['A'], *prepared.frame.point_mm(*point)):
                    raise RuntimeError('A free-tip triangular end cap remains at a bevel/nose junction.')
                checks.append({'label':'tip_cap_removed', 'point_mm':point, 'inside_a':False})
        if settings.snap_style == 'twin':
            outer = settings.clearance_mm+settings.thickness_mm
            for side, y in ((1, unit.arms[0].beam.y_max_mm), (-1, unit.arms[1].beam.y_min_mm)):
                for factor, expected in ((.3,False),(.6,True)):
                    point = (outer-factor*size, y-side*factor*size, -factor*size)
                    actual = _inside(bodies['A'], *prepared.frame.point_mm(*point))
                    if actual != expected:
                        raise RuntimeError('The inside fork foot has a flat end cap or excessive corner removal.')
                    checks.append({'label':'fork_foot_connection', 'point_mm':point, 'inside_a':actual})
    for face in _items(bodies['A'].faces):
        if face.vertices.count != 3 or adsk.core.Plane.cast(face.geometry) is None:
            continue
        geometry = _face_geometry(face, prepared.frame)
        if (geometry['normal'][0] > .999999
                and all(abs(point[0]-settings.clearance_mm)<1e-6
                        and point[2]>settings.reach_mm-2*size for point in geometry['vertices_mm'])):
            raise RuntimeError('A planar triangular tip-cap face remains.')
    return checks


def inspect_preview(prepared):
    """Probe actual catches, twin gaps, chamfers and 45-degree support surfaces."""
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

    def outer_at(z):
        factor = 1.0 - .35 * max(0.0, z) / settings.reach_mm if settings.snap_style == "tapered" else 1.0
        return settings.clearance_mm + settings.thickness_mm * factor

    def witness(label, point, expected_a, expected_b):
        global_point = prepared.frame.point_mm(*point)
        actual = (_inside(bodies["A"], *global_point), _inside(bodies["B"], *global_point))
        if actual != (expected_a, expected_b):
            raise RuntimeError("Snap-fit witness " + label + " has incorrect material/clearance: " + str(actual))
        witnesses.append({"label": label, "point_mm": point, "inside_a": actual[0], "inside_b": actual[1]})

    for unit in prepared.plan.units:
        expected_arms = 2 if settings.snap_style == "twin" else 1
        if len(unit.arms) != expected_arms:
            raise RuntimeError("The requested snap style did not create its expected arm count.")
        for index, arm in enumerate(unit.arms):
            y = (arm.hook.y_min_mm + arm.hook.y_max_mm) / 2
            beam_z = shoulder / 2
            prefix = "arm_" + str(index + 1) + "_"
            samples = [
                ("beam", ((settings.clearance_mm + outer_at(beam_z)) / 2, y, beam_z), True, False),
                ("beam_gap", (settings.clearance_mm / 2, y, beam_z), False, False),
                ("hook", (-settings.hook_depth_mm / 2, y, shoulder + settings.clearance_mm / 2), True, False),
                ("pocket_side", (-settings.hook_depth_mm / 2,
                                 arm.hook.y_max_mm + settings.clearance_mm / 2,
                                 shoulder + settings.clearance_mm / 2), False, False),
                ("back_wall", (-settings.hook_depth_mm - settings.clearance_mm - .2,
                                y, shoulder + settings.clearance_mm / 2), False, True),
                ("beam_outer_gap", (outer_at(shoulder + settings.clearance_mm / 2) + settings.clearance_mm / 2,
                                     y, shoulder + settings.clearance_mm / 2), False, False),
                ("receiver_roof", (-settings.hook_depth_mm / 2, y,
                                    settings.reach_mm + settings.clearance_mm + .2),
                 False, not settings.print_support),
            ]
            for label, point, expected_a, expected_b in samples:
                witness(prefix + label, point, expected_a, expected_b)
            # Whole protected surfaces must retain material at their boundaries,
            # including locations where the former partial inside bevel was cut.
            epsilon = min(.03, settings.clearance_mm / 10)
            for side, near_y in (("low", arm.beam.y_min_mm + epsilon),
                                 ("high", arm.beam.y_max_mm - epsilon)):
                for z in (.2, shoulder / 2, shoulder - .1):
                    witness(prefix + "protected_inner_" + side,
                            (settings.clearance_mm + epsilon, near_y, z), True, False)
                catch_x = (settings.clearance_mm - settings.hook_depth_mm) / 2
                witness(prefix + "protected_catch_material_" + side,
                        (catch_x, near_y, shoulder + epsilon), True, False)
                witness(prefix + "protected_catch_clearance_" + side,
                        (catch_x, near_y, shoulder - epsilon), False, False)
            # Sample the COMPLETE outer edge, through former primitive joins and
            # the hook junction. This does not read the production edge classifier.
            outer_zs = (.2, settings.reach_mm / 3, shoulder - .1,
                        shoulder, shoulder + .1, settings.reach_mm - 2 * settings.chamfer_size_mm)
            for side, edge_y in ((-1, arm.beam.y_min_mm), (1, arm.beam.y_max_mm)):
                for z in outer_zs:
                    inset = settings.chamfer_size_mm * .45 if settings.chamfer_edges else .05
                    witness(prefix + "complete_outer_side",
                            (outer_at(z) - inset, edge_y - side * inset, z),
                            not settings.chamfer_edges, False)
                    if settings.chamfer_edges:
                        retained = settings.chamfer_size_mm * .55
                        witness(prefix + "complete_outer_requested_size",
                                (outer_at(z) - retained, edge_y - side * retained, z), True, False)
            # The outside free tip is another complete convex edge; its inner
            # retaining shoulder remains covered by the protected surface check.
            inset = settings.chamfer_size_mm * .45 if settings.chamfer_edges else .05
            witness(prefix + "free_outer_tip",
                    (outer_at(settings.reach_mm) - inset, y, settings.reach_mm - inset),
                    not settings.chamfer_edges, False)
            if settings.chamfer_edges:
                retained = settings.chamfer_size_mm * .55
                witness(prefix + "free_outer_tip_requested_size",
                        (outer_at(settings.reach_mm) - retained, y, settings.reach_mm - retained), True, False)
            # Receiver entrance edges are intentionally sharp in BOTH modes.
            entry_z = (shoulder + settings.reach_mm) / 2
            witness(prefix + "receiver_entry_unchanged",
                    (-.05, arm.receiver.y_max_mm + .05, entry_z), False, True)
            if settings.snap_style == "tapered":
                # This material would remain in a straight beam at the same point.
                z = shoulder / 2
                x = (outer_at(z) + outer) / 2
                witness(prefix + "taper_narrowing", (x, y, z), False, False)
        for side, edge_y in ((-1, unit.root.y_min_mm), (1, unit.root.y_max_mm)):
            for z in (-settings.root_length_mm / 2, -.2, -.05, 0.0, .05):
                inset = settings.chamfer_size_mm * .45 if settings.chamfer_edges else .05
                witness("root_join_complete_outer_side",
                        (outer_at(z) - inset, edge_y - side * inset, z), not settings.chamfer_edges, False)
                if settings.chamfer_edges:
                    retained = settings.chamfer_size_mm * .55
                    witness("root_join_requested_size",
                            (outer_at(z) - retained, edge_y - side * retained, z), True, False)
        witness("root_support_45deg", (outer / 2, unit.center_y_mm,
                                        -settings.root_length_mm - outer / 4),
                settings.print_support, False)
        if settings.snap_style == "twin":
            witness("twin_middle_gap", (settings.clearance_mm + settings.thickness_mm / 2,
                                        unit.center_y_mm, shoulder / 2), False, False)
            witness("twin_receiver_middle_web", (-settings.hook_depth_mm / 2,
                                                unit.center_y_mm, shoulder + settings.clearance_mm / 2),
                    False, True)
    if len(prepared.plan.units) != settings.snap_count:
        raise RuntimeError("The plan did not produce the requested clasp count.")
    witnesses.extend(inspect_corner_finish(prepared))
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


def style_matrix(faces, edge):
    """Fixed style/finish/support combinations; every case has physical witnesses."""
    adapter = STATE["adapter"]
    settings_type = STATE["settings_module"].SnapFitSettings
    design = STATE["design"]
    sharp_baselines = {}
    for style in ("standard", "tapered", "twin"):
        for chamfer in (False, True):
            for support in (False, True):
                if cancellation_requested():
                    raise RuntimeError("Snap-fit validation cancelled before the next geometry case.")
                settings = settings_type(snap_style=style, chamfer_edges=chamfer,
                                         chamfer_size_mm=.3, print_support=support)
                before = snapshot(design)
                prepared = adapter.prepare_snap_fit(design, *faces, edge, settings)
                witnesses = inspect_preview(prepared)
                volumes = {role: float(body.volume) for role, body in prepared.result_bodies}
                protected = protected_geometry(prepared)
                if not chamfer:
                    sharp_baselines[(style, support)] = {"volumes": volumes, "protected": protected}
                else:
                    previous = sharp_baselines[(style, support)]
                    if not volumes["A"] < previous["volumes"]["A"] - 1e-8:
                        raise RuntimeError("The requested outer chamfer did not remove material from its exact sharp baseline.")
                    if protected != previous["protected"]:
                        raise RuntimeError("Chamfers changed the protected inner beam, catch or receiver geometry.")
                if snapshot(design) != before:
                    raise RuntimeError("A style/finish preview changed source geometry or scene flags.")
                STATE["report"]["cases"].append({
                    "name": "matrix_" + style + ("_chamfer" if chamfer else "_sharp")
                            + ("_print_support_on" if support else "_print_support_off"),
                    "snap_style": style, "chamfer_edges": chamfer, "print_support": support,
                    "success": True, "witnesses": witnesses,
                    "result_volumes_cm3": volumes, "protected_geometry": protected,
                })


def legacy_migration_case(version=1):
    """Owned historical schema fixtures load read-only; explicit Rebuild saves v3."""
    design, adapter = STATE["design"], STATE["adapter"]
    settings = STATE["settings_module"].SnapFitSettings(
        snap_style="standard" if version == 1 else "tapered",
        chamfer_edges=version == 2, print_support=version == 2)
    _, targets, faces, edge = fixture(design)
    count = design.rootComponent.bRepBodies.count
    tokens = tuple(body.entityToken for body in targets)
    names = tuple(body.name for body in targets)
    flags = tuple(body.isLightBulbOn for body in targets)
    prepared = adapter.prepare_snap_fit(design, *faces, edge, settings)
    inspect_preview(prepared)
    anchor = adapter.create_snap_fit(design, prepared)
    _identity_check(design, targets, tokens, names, flags, count)
    attribute = anchor.attributes.itemByName(adapter.ATTRIBUTE_GROUP, adapter.RECIPE_NAME)
    legacy = json.loads(attribute.value)
    legacy["version"] = version
    for key in adapter.FAMILY_DEFAULTS:
        del legacy["settings"][key]
    if version == 1:
        for key in adapter.LEGACY_STYLE_DEFAULTS:
            del legacy["settings"][key]
    if len(legacy["settings"]) != (11 if version == 1 else 15):
        raise RuntimeError("The historical settings fixture has an incorrect schema.")
    raw = json.dumps(legacy, separators=(",", ":"))
    if anchor.attributes.add(adapter.ATTRIBUTE_GROUP, adapter.RECIPE_NAME, raw) is None:
        raise RuntimeError("Could not establish the owned historical recipe fixture.")
    before = snapshot(design)
    loaded = adapter.read_edit_target(design, targets[0])
    if loaded.settings != settings:
        raise RuntimeError("Reading a historical recipe changed its saved geometry dimensions.")
    if (snapshot(design) != before
            or anchor.attributes.itemByName(adapter.ATTRIBUTE_GROUP, adapter.RECIPE_NAME).value != raw):
        raise RuntimeError("Reading historical settings modified geometry or persisted a migration.")
    combines = dict(loaded.record.recipe["combines"])
    changed = replace(settings, snap_style="tapered" if version == 1 else "standard",
                       chamfer_edges=True, print_support=True)
    updated = adapter.prepare_edit_snap_fit(design, loaded, changed)
    witnesses = inspect_preview(updated)
    if adapter.rebuild_snap_fit(design, loaded, updated) != anchor:
        raise RuntimeError("Historical Rebuild replaced its native BaseFeature.")
    _identity_check(design, targets, tokens, names, flags, count)
    final = adapter.read_edit_target(design, anchor)
    saved = json.loads(anchor.attributes.itemByName(adapter.ATTRIBUTE_GROUP, adapter.RECIPE_NAME).value)
    if (saved["version"] != adapter.RECIPE_VERSION or final.settings != changed
            or final.record.recipe["combines"] != combines):
        raise RuntimeError("Explicit historical Rebuild did not save current dimensions in the same history.")
    STATE["report"]["cases"].append({"name": "legacy_v"+str(version)+"_read_then_explicit_v3_rebuild",
        "success": True, "historical_read_unchanged": True, "witnesses": witnesses})


def annular_fixture(design, *, inner_b=10.3, outer_b=12.0):
    """Owned concentric hollow neck/socket, both extending below the upper rim."""
    root = design.rootComponent
    manager = adsk.fusion.TemporaryBRepManager.get()
    feature = root.features.baseFeatures.add()
    feature.name = "Partelier disposable annular sources"
    if not feature.startEdit():
        raise RuntimeError("Could not edit the annular fixture.")
    try:
        for inner, outer in ((9.0, 10.0), (inner_b, outer_b)):
            low, high = adsk.core.Point3D.create(0, 0, -1), adsk.core.Point3D.create(0, 0, 0)
            body = manager.createCylinderOrCone(low, outer/10, high, outer/10)
            core = manager.createCylinderOrCone(low, inner/10, high, inner/10)
            if (body is None or core is None or not manager.booleanOperation(
                    body, core, adsk.fusion.BooleanTypes.DifferenceBooleanType)):
                raise RuntimeError("Could not construct the hollow annular fixture.")
            if root.bRepBodies.add(body, feature) is None:
                raise RuntimeError("Could not persist an owned annular fixture body.")
    finally:
        if not feature.finishEdit():
            raise RuntimeError("Could not finish the annular fixture.")
    bodies = tuple(sorted(_items(feature.bodies), key=lambda body: body.boundingBox.maxPoint.x))
    if len(bodies) != 2:
        raise RuntimeError("The annular fixture must contain exactly two bodies.")
    faces = []
    for body, radius, role in zip(bodies, (10.0, inner_b), ("A", "B")):
        body.name = "Owned annular source " + role
        faces.append(next(face for face in _items(body.faces)
                          if (cylinder := adsk.core.Cylinder.cast(face.geometry)) is not None
                          and abs(cylinder.radius-radius/10) < 1e-7))
    bodies[1].isLightBulbOn = False
    edge = next(edge for edge in _items(faces[0].edges)
                if (circle := adsk.core.Circle3D.cast(edge.geometry)) is not None
                and abs(circle.center.z) < 1e-7)
    return feature, bodies, tuple(faces), edge


def inspect_family_preview(prepared):
    bodies = dict(prepared.result_bodies)
    if set(bodies) != {"A", "B"} or not all(body.isValid and body.isTemporary and body.isSolid
            and body.lumps.count == 1 and body.volume > 0 for body in bodies.values()):
        raise RuntimeError("A snap family did not return two valid detached solids.")
    settings = prepared.settings
    result = []
    def witness(label, point, a, b):
        actual = tuple(_inside(bodies[role], *prepared.frame.point_mm(*point)) for role in ("A", "B"))
        if actual != (a, b):
            raise RuntimeError(settings.snap_family + " witness " + label + " has wrong material: " + str(actual))
        result.append({"label": label, "point_mm": point, "inside_a": a, "inside_b": b})
    if settings.snap_family == "annular":
        plan = prepared.plan
        for angle in (0, math.pi/2, math.pi, 3*math.pi/2):
            def radial(label, radius, z, a, b):
                witness(label, (radius*math.cos(angle), radius*math.sin(angle), z), a, b)
            radial("ring_bead", plan.bead_peak_radius_mm-.1, plan.center_z_mm, True, False)
            bead_width = plan.bead_end_z_mm-plan.bead_start_z_mm
            bead_height = plan.bead_peak_radius_mm-plan.radius_a_mm
            radial("ring_requested_width_lower", plan.radius_a_mm+.1*bead_height,
                   plan.bead_start_z_mm+.1*bead_width, True, False)
            radial("ring_requested_width_upper", plan.radius_a_mm+.1*bead_height,
                   plan.bead_end_z_mm-.1*bead_width, True, False)
            radial("ring_fit_gap", plan.bead_peak_radius_mm+settings.clearance_mm/2,
                   plan.center_z_mm, False, False)
            radial("ring_back_wall", plan.groove_radius_mm+.15, plan.center_z_mm, False, True)
            radial("ring_base_neck", plan.radius_a_mm-.25, -8, True, False)
            radial("ring_radial_gap", (plan.radius_a_mm+plan.radius_b_mm)/2, -8, False, False)
            radial("ring_roof", (plan.radius_b_mm+plan.groove_radius_mm)/2,
                   plan.groove_end_z_mm+.1, False, not settings.print_support)
    else:
        for unit in prepared.plan.units:
            manager = adsk.fusion.TemporaryBRepManager.get()
            if settings.snap_family == "ball_detent":
                module = importlib.import_module(STATE["adapter"].__package__ + ".ball_detent")
                round_core = module.nose_body(manager, prepared.frame, unit)
            else:
                module = importlib.import_module(STATE["adapter"].__package__ + ".torsion")
                round_core = module.bar_body(manager, prepared.frame, unit)
            expected_volume = float(round_core.volume)
            STATE["adapter"]._boolean(manager, round_core, bodies["A"],
                adsk.fusion.BooleanTypes.IntersectionBooleanType,
                "Could not verify the complete protected round core.")
            if abs(round_core.volume-expected_volume) > max(1e-10, expected_volume*1e-8):
                raise RuntimeError("Cosmetic finishing removed material from the functional round core.")
            result.append({"label":"complete_round_core_preserved",
                           "expected_volume_cm3":expected_volume,
                           "actual_volume_cm3":float(round_core.volume)})
            if settings.snap_family == "ball_detent":
                geometry = unit.ball_geometry
                x, y, z = geometry.center_mm
                radius, socket = geometry.radius_mm, geometry.socket_radius_mm
                witness("rounded_nose", (x-radius+.1, y, z), True, False)
                witness("rounded_fit_gap", (x-radius-settings.clearance_mm/2, y, z), False, False)
                witness("rounded_back_wall", (x-socket-.2, y, z), False, True)
                witness("rounded_side", (x-.8*radius, y+.3*radius, z+.2*radius), True, False)
                roof_x = -.05
                sphere_top = z + math.sqrt(socket*socket-(roof_x-x)**2)
                ramp_top = z + math.sqrt(2)*socket-x+roof_x
                witness("rounded_roof", (roof_x, y, (sphere_top+ramp_top)/2), False, not settings.print_support)
            elif settings.snap_family == "torsion":
                geometry = unit.torsion_geometry
                arm = unit.arms[0]
                free_y = (arm.beam.y_max_mm+geometry.posts[1].y_min_mm)/2
                witness("torsion_free_bar", (geometry.axis_x_mm, free_y, geometry.axis_z_mm), True, False)
                witness("torsion_under_bar_gap", (geometry.axis_x_mm, free_y,
                         (geometry.axis_z_mm-geometry.radius_mm)/2), False, False)
                witness("torsion_central_lever", (settings.clearance_mm+settings.thickness_mm/2,
                         unit.center_y_mm, settings.reach_mm/2), True, False)
                witness("torsion_no_root_bridge", (settings.clearance_mm+settings.thickness_mm-.05,
                         unit.center_y_mm, geometry.axis_z_mm*.4), False, False)
                for post in geometry.posts:
                    witness("torsion_fixed_post", ((post.x_min_mm+post.x_max_mm)/2,
                            (post.y_min_mm+post.y_max_mm)/2, .1), True, False)
                shoulder = settings.reach_mm-settings.lead_in_mm
                witness("torsion_catch", (-settings.hook_depth_mm/2, unit.center_y_mm,
                                          shoulder+settings.clearance_mm/2), True, False)
                witness("torsion_receiver_gap", (-settings.hook_depth_mm/2,
                         arm.hook.y_max_mm+settings.clearance_mm/2,
                         shoulder+settings.clearance_mm/2), False, False)
            else:
                raise RuntimeError("Unsupported family in the fixed native probe.")
    result.extend(inspect_corner_finish(prepared))
    STATE.setdefault("detached", []).extend(bodies.values())
    return result


def family_cases():
    design, adapter = STATE["design"], STATE["adapter"]
    settings_type = STATE["settings_module"].SnapFitSettings
    for family in ("ball_detent", "torsion", "annular"):
        create_fixture = annular_fixture if family == "annular" else fixture
        _, targets, faces, edge = create_fixture(design)
        baselines = {}
        for support in (False, True):
            for chamfer in ((False,) if family == "annular" else (False, True)):
                settings = settings_type(snap_family=family, snap_style="standard",
                                          chamfer_edges=chamfer, print_support=support)
                before = snapshot(design)
                prepared = adapter.prepare_snap_fit(design, *faces, edge, settings)
                witnesses = inspect_family_preview(prepared)
                if snapshot(design) != before:
                    raise RuntimeError("A new family preview modified the model.")
                body_map = dict(prepared.result_bodies)
                signature_b = adapter.hinge._body_signature(body_map["B"])
                if chamfer:
                    if signature_b != baselines[support]:
                        raise RuntimeError("A family chamfer modified its receiving contact geometry.")
                else:
                    baselines[support] = signature_b
                STATE["report"]["cases"].append({"name": "family_"+family+("_chamfer" if chamfer else "_sharp")
                    +("_ramps" if support else "_no_ramps"), "success": True, "witnesses": witnesses,
                    "chamfer_edges": chamfer, "print_support": support})
        settings = settings_type(snap_family=family, chamfer_edges=family!="annular", print_support=True)
        prepared = adapter.prepare_snap_fit(design, *faces, edge, settings)
        tokens = tuple(body.entityToken for body in targets)
        names = tuple(body.name for body in targets)
        flags = tuple(body.isLightBulbOn for body in targets)
        count = design.rootComponent.bRepBodies.count
        anchor = adapter.create_snap_fit(design, prepared)
        _identity_check(design, targets, tokens, names, flags, count)
        loaded = adapter.read_edit_target(design, targets[0])
        if loaded.settings != settings or adapter.read_edit_target(design, targets[1]).anchor != anchor:
            raise RuntimeError("Family Edit did not recover all stored dimensions from either target.")
        combines = dict(loaded.record.recipe["combines"])
        if family == "ball_detent":
            changed = replace(settings, ball_radius_mm=2.2, reach_mm=17)
        elif family == "torsion":
            changed = replace(settings, torsion_radius_mm=.85, width_mm=9, reach_mm=17)
        else:
            changed = replace(settings, annular_bead_width_mm=2.2, annular_bead_height_mm=.6, annular_offset_mm=3.5)
        candidate = adapter.prepare_edit_snap_fit(design, loaded, changed)
        witnesses = inspect_family_preview(candidate)
        if adapter.rebuild_snap_fit(design, loaded, candidate) != anchor:
            raise RuntimeError("Family Rebuild replaced its owned history feature.")
        _identity_check(design, targets, tokens, names, flags, count)
        fresh = adapter.read_edit_target(design, anchor)
        if fresh.settings != changed or fresh.record.recipe["combines"] != combines:
            raise RuntimeError("Family Rebuild did not preserve native references and dimensions.")
        STATE["report"]["cases"].append({"name":"family_"+family+"_create_edit_rebuild",
            "success":True,"witnesses":witnesses,"same_bodies":True,"same_combines":True})


def extra_family_checks():
    design, adapter = STATE["design"], STATE["adapter"]
    settings_type = STATE["settings_module"].SnapFitSettings
    refusals = (
        ("ball_detent_thin_receiver_refused", lambda: fixture(design, thickness=1),
         settings_type(snap_family="ball_detent")),
        ("torsion_post_lever_interference_refused", lambda: fixture(design),
         settings_type(snap_family="torsion", width_mm=4)),
        ("annular_bead_cannot_engage_refused", lambda: annular_fixture(design, inner_b=10.7),
         settings_type(snap_family="annular", chamfer_edges=False)),
    )
    for name, source, settings in refusals:
        _, _, faces, edge = source()
        before = snapshot(design)
        try:
            adapter.prepare_snap_fit(design, *faces, edge, settings)
        except ValueError as error:
            if snapshot(design) != before:
                raise RuntimeError("A refused family modified its source geometry.") from error
            STATE["report"]["cases"].append({"name": name, "success": True,
                "expected_refusal": True, "message": str(error)})
        else:
            raise RuntimeError("An unsupported family fixture was accepted: "+name)
    _, targets, faces, edge = fixture(design)
    initial = settings_type(chamfer_edges=False, print_support=False)
    prepared = adapter.prepare_snap_fit(design, *faces, edge, initial)
    anchor = adapter.create_snap_fit(design, prepared)
    loaded = adapter.read_edit_target(design, anchor)
    tokens = tuple(body.entityToken for body in targets)
    names = tuple(body.name for body in targets)
    flags = tuple(body.isLightBulbOn for body in targets)
    count = design.rootComponent.bRepBodies.count
    combines = dict(loaded.record.recipe["combines"])
    for family in ("ball_detent", "torsion", "hook"):
        changed = replace(initial, snap_family=family, chamfer_edges=True, print_support=True)
        candidate = adapter.prepare_edit_snap_fit(design, loaded, changed)
        witnesses = inspect_preview(candidate) if family == "hook" else inspect_family_preview(candidate)
        if adapter.rebuild_snap_fit(design, loaded, candidate) != anchor:
            raise RuntimeError("Changing a planar family replaced its existing feature.")
        _identity_check(design, targets, tokens, names, flags, count)
        loaded = adapter.read_edit_target(design, anchor)
        if loaded.settings != changed or loaded.record.recipe["combines"] != combines:
            raise RuntimeError("Changing a planar family lost saved dimensions or native references.")
        STATE["report"]["cases"].append({"name": "planar_edit_change_to_"+family,
            "success": True, "same_bodies": True, "same_combines": True, "witnesses": witnesses})
    _, _, faces, edge = fixture(design)
    large = settings_type(snap_style="twin", width_mm=12, thickness_mm=1.6,
                          hook_depth_mm=2, clearance_mm=.1, chamfer_size_mm=.75)
    sharp = adapter.prepare_snap_fit(design, *faces, edge, replace(large, chamfer_edges=False))
    finished = adapter.prepare_snap_fit(design, *faces, edge, large)
    if protected_geometry(sharp) != protected_geometry(finished):
        raise RuntimeError("A large exterior chamfer changed the protected twin gap, catch or receiver.")
    if finished.settings.chamfer_size_mm != .75:
        raise RuntimeError("The requested large twin chamfer was silently reduced.")
    STATE["report"]["cases"].append({"name":"large_twin_outer_chamfer_preserves_contacts",
        "success": True, "requested_chamfer_mm": .75, "witnesses": inspect_preview(finished)})


def capture_family_visuals(prepared):
    """Capture exact detached A/B shapes, then restore the user's entire view."""
    app = adsk.core.Application.get()
    viewport = app.activeViewport
    design = STATE['design']
    adapter = STATE['adapter']
    root = design.rootComponent
    old_camera = viewport.camera
    def camera_state(camera):
        return (camera.cameraType,
                *(round(getattr(point, axis), 7) for point in (camera.eye, camera.target, camera.upVector)
                  for axis in ("x", "y", "z")),
                tuple(round(value, 7) if isinstance(value, float) else value for value in camera.getExtents()))
    original_camera_state = camera_state(old_camera)
    bodies = [(body, body.isLightBulbOn) for body in _items(root.bRepBodies)]
    groups = [(group, group.isVisible) for group in _items(root.customGraphicsGroups)]
    appearance_count = design.appearances.count
    initial_graphics = root.customGraphicsGroups.count
    paths = []
    graphic = None
    family = prepared.settings.snap_family
    report_file = Path(STATE['context']['report_path'])
    appearances = {role: source.appearance or source.material.appearance or root.material.appearance
                   for role, source in zip(('A','B'), (prepared.face_a.body, prepared.face_b.body))}
    try:
        for body, _ in bodies:
            body.isLightBulbOn = False
        for group, _ in groups:
            group.isVisible = False
        camera = viewport.camera
        camera.cameraType = adsk.core.CameraTypes.OrthographicCameraType
        camera.isFitView = False
        camera.isSmoothTransition = False
        if family == 'annular':
            camera.target = adapter.hinge._point(prepared.frame, 0, 0, -3)
            camera.eye = adapter.hinge._point(prepared.frame, 28, -35, 32)
            extent = 3.2
        else:
            camera.target = adapter.hinge._point(prepared.frame, 0, 0, 7)
            camera.eye = adapter.hinge._point(prepared.frame, 35, -24, 21)
            extent = 2.8
        camera.upVector = adsk.core.Vector3D.create(*prepared.frame.z_axis)
        if camera.setExtents(extent, extent) is False:
            raise RuntimeError('Could not set the diagnostic camera extents.')
        viewport.camera = camera
        for role, body in prepared.result_bodies:
            graphic = adapter.hinge.draw_solid_preview(design, ((role, body),), appearances)
            viewport.refresh()
            path = report_file.with_name(report_file.stem+'-'+family+'-'+role+'.png')
            if not viewport.saveAsImageFile(str(path), 1200, 900):
                raise RuntimeError('Could not capture the detached '+family+' '+role+' shape.')
            paths.append({'role':role, 'path':str(path)})
            if graphic.deleteMe() is False:
                raise RuntimeError('Could not remove diagnostic graphics.')
            graphic = None
    finally:
        if graphic is not None and graphic.isValid:
            graphic.deleteMe()
        for body, visible in bodies:
            if body.isValid:
                body.isLightBulbOn = visible
        for group, visible in groups:
            if group.isValid:
                group.isVisible = visible
        viewport.camera = old_camera
        viewport.refresh()
        if design.appearances.count != appearance_count or root.customGraphicsGroups.count != initial_graphics:
            raise RuntimeError('Diagnostic capture left a persistent appearance or graphics group.')
        if camera_state(viewport.camera) != original_camera_state:
            raise RuntimeError('Diagnostic capture did not restore the original camera.')
    return {'family':family, 'images':paths, 'view_restored':True}


def family_visual_cases():
    adapter, settings_module = STATE['adapter'], STATE['settings_module']
    design = STATE['design']
    captures = []
    for family in ('hook','ball_detent','torsion','annular'):
        values = settings_module.SnapFitSettings(snap_family=family, snap_style='twin' if family=='hook' else 'standard', chamfer_edges=family!='annular')
        if family == 'annular':
            _, _, faces, edge = annular_fixture(design)
        else:
            _, _, faces, edge = fixture(design, span=60, thickness=4, upper=30)
        prepared = adapter.prepare_snap_fit(design, *faces, edge, values)
        if family == 'hook':
            details=[]
            finish=importlib.import_module(adapter.__package__+'.finish')
            for face in _items(dict(prepared.result_bodies)['A'].faces):
                if face.vertices.count != 3 or adsk.core.Plane.cast(face.geometry) is None:
                    continue
                details.append({'normal':finish._local_normal(prepared.frame, adapter.hinge._plane_normal(face)),
                                'area_mm2':face.area*100,
                                'vertices_mm':[finish._local_point(prepared.frame, adapter.hinge._xyz(vertex.geometry)) for vertex in _items(face.vertices)]})
            STATE['report']['tip_triangle_diagnostic']=details
        captures.append(capture_family_visuals(prepared))
    STATE['report']['family_visuals'] = captures



def corner_regression_cases():
    design, adapter = STATE['design'], STATE['adapter']
    defaults = STATE['settings_module'].SnapFitSettings()
    configs = [
        {"snap_style":style,"clearance_mm":.01,"hook_depth_mm":2,"lead_in_mm":1,"chamfer_size_mm":.4}
        for style in ('standard','tapered','twin')]
    configs += [{"snap_style":style,"clearance_mm":.6} for style in ('standard','twin')]
    configs += [{"snap_style":"twin","snap_count":3,"width_mm":6,"reach_mm":14},
                {"snap_family":"torsion"},
                {"snap_family":"torsion","clearance_mm":.01,"hook_depth_mm":2,"lead_in_mm":1,"chamfer_size_mm":.4}]
    for index, changes in enumerate(configs):
        _, _, faces, edge = fixture(design, span=90, thickness=4, upper=30)
        values = replace(defaults, **changes)
        prepared = adapter.prepare_snap_fit(design, *faces, edge, values)
        checks = inspect_family_preview(prepared) if values.snap_family=='torsion' else inspect_preview(prepared)
        STATE['report']['cases'].append({'name':'corner_regression_'+str(index+1),'success':True,
            'settings':values.to_dict(),'witnesses':checks})


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
    style_matrix(faces, edge)
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
    changes = (
        replace(settings, snap_count=3, width_mm=6.0, reach_mm=14.0,
                snap_style="tapered", chamfer_edges=True, print_support=True),
        replace(settings, snap_style="twin", chamfer_edges=True, print_support=False),
        replace(settings, snap_style="standard", chamfer_edges=False, print_support=False),
    )
    for changed in changes:
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
        STATE["report"]["cases"].append({"name": "rebuild_same_history_" + changed.snap_style,
            "success": True, "witnesses": witnesses, "native_combines": 4,
            "chamfer_edges": changed.chamfer_edges, "print_support": changed.print_support})
        record = fresh
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
    _, _, invalid_faces, invalid_edge = fixture(design)
    before = snapshot(design)
    try:
        invalid = replace(settings, chamfer_edges=True, chamfer_size_mm=settings.thickness_mm)
        adapter.prepare_snap_fit(design, *invalid_faces, invalid_edge, invalid)
    except ValueError as error:
        if snapshot(design) != before:
            raise RuntimeError("An oversized chamfer refusal modified the model.") from error
        report["cases"].append({"name": "oversized_chamfer_explicit_refusal", "success": True,
                                 "expected_refusal": True, "message": str(error)})
    else:
        raise RuntimeError("An oversized chamfer was accepted or silently reduced.")
    legacy_migration_case()
    legacy_migration_case(2)
    gap_cases()
    family_cases()
    extra_family_checks()
    session_checks()
    corner_regression_cases()
    family_visual_cases()
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
        changed = replace(updated_settings, snap_count=2, snap_style="tapered",
                          chamfer_edges=False, print_support=False)
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

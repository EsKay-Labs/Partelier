"""Fixed Patterns CAD checks on owned fixtures in a rollback-only command.

No arbitrary geometry, paths, code or user selections enter this probe. Scratch
Offset/Thicken features, final persistence and Rebuild are checked against exact
source snapshots, then Fusion rolls the entire command back before reporting.
"""

from dataclasses import replace
import hashlib
import importlib
import importlib.util
import json
import math
import time
from pathlib import Path
import sys
import traceback
import uuid

import adsk.core
import adsk.fusion


EVENT = "sktech_partelier_pattern_probe_event_67744d4a"
COMMAND = "sktech_partelier_pattern_probe_command_67744d4a"
STATE = {}
HANDLERS = []


def _items(collection):
    return tuple(collection.item(index) for index in range(collection.count))


def _xyz(point):
    return tuple(round(float(value), 8) for value in (point.x, point.y, point.z))


def _signature(body):
    return STATE["adapter"].hinge._body_signature(body)


def snapshot(design):
    root = design.rootComponent
    def body_data(body):
        bounds = body.boundingBox
        return {"name": body.name, "volume": round(float(body.volume), 9),
                "faces": body.faces.count, "edges": body.edges.count,
                "bounds": [_xyz(bounds.minPoint), _xyz(bounds.maxPoint)],
                "vertices": sorted(_xyz(vertex.geometry) for vertex in _items(body.vertices)),
                "visible": body.isVisible, "light_bulb": body.isLightBulbOn,
                "attribute_sha256": hashlib.sha256(json.dumps(sorted(
                    (attribute.groupName, attribute.name, attribute.value)
                    for attribute in _items(body.attributes)), separators=(",", ":")).encode()).hexdigest()}
    return {"timeline": design.timeline.count, "marker": design.timeline.markerPosition,
            "appearances": design.appearances.count,
            "bodies": [body_data(body) for body in _items(root.bRepBodies)],
            "graphics": [{"visible": group.isVisible} for group in _items(root.customGraphicsGroups)]}


def load(root):
    name = "_partelier_pattern_probe_" + uuid.uuid4().hex
    STATE["package_name"] = name
    path = root / "Partelier" / "partelier"
    spec = importlib.util.spec_from_file_location(name, path / "__init__.py",
                                                 submodule_search_locations=[str(path)])
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return tuple(importlib.import_module(name + ".tools.patterns." + leaf)
                 for leaf in ("fusion", "settings", "recipe"))


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


def queue_probe_event(information="geometry"):
    STATE["report"]["queue_return"] = adsk.core.Application.get().fireCustomEvent(EVENT, information)


def _inside(body, point_mm):
    point = adsk.core.Point3D.create(*(value / 10 for value in point_mm))
    state = body.pointContainment(point)
    inside = adsk.fusion.PointContainment.PointInsidePointContainment
    outside = adsk.fusion.PointContainment.PointOutsidePointContainment
    if state not in (inside, outside):
        raise RuntimeError("An independent material witness landed on an unexpected boundary.")
    return state == inside


def _add(point, normal, distance):
    return tuple(one + distance * two for one, two in zip(point, normal))


def _same_reference(design, body, token):
    found = design.findEntityByToken(token)
    return body.isValid and found is not None and len(found) == 1 and found[0] == body


def _temporary(body):
    if (body is None or not body.isValid or not body.isTemporary or not body.isSolid
            or body.lumps.count != 1 or body.volume <= 0):
        raise RuntimeError("The fixed fixture/result is not one valid temporary solid.")
    return body


def _persist(design, temporary, label):
    root = design.rootComponent
    feature = root.features.baseFeatures.add()
    feature.name = "Partelier disposable pattern " + label
    if not feature.startEdit():
        raise RuntimeError("Could not edit the disposable pattern source.")
    try:
        if root.bRepBodies.add(_temporary(temporary), feature) is None:
            raise RuntimeError("Could not persist the disposable pattern source.")
    finally:
        if not feature.finishEdit():
            raise RuntimeError("Could not finish the disposable pattern source.")
    bodies = _items(feature.bodies)
    if len(bodies) != 1:
        raise RuntimeError("The disposable pattern fixture did not contain exactly one body.")
    body = bodies[0]
    body.name = "Owned pattern " + label
    body.isLightBulbOn = False
    return feature, body


def _box(manager, xmin, xmax, ymin, ymax, zmin, zmax):
    bounds = adsk.core.OrientedBoundingBox3D.create(
        adsk.core.Point3D.create((xmin+xmax)/20, (ymin+ymax)/20, (zmin+zmax)/20),
        adsk.core.Vector3D.create(1, 0, 0), adsk.core.Vector3D.create(0, 1, 0),
        (xmax-xmin)/10, (ymax-ymin)/10, (zmax-zmin)/10)
    return _temporary(manager.createBox(bounds))


def _boolean(manager, target, cutter):
    if not manager.booleanOperation(target, cutter, adsk.fusion.BooleanTypes.DifferenceBooleanType):
        raise RuntimeError("Could not construct the hollow disposable fixture.")
    return _temporary(target)


def fixture(design, kind):
    root = design.rootComponent
    manager = adsk.fusion.TemporaryBRepManager.get()
    if kind in ("plane","plane_hole"):
        temporary=_box(manager,-16,16,-12,12,-3,0)
        if kind=='plane_hole':
            drill=manager.createCylinderOrCone(adsk.core.Point3D.create(0,0,-.4),.35,
                                               adsk.core.Point3D.create(0,0,.1),.35)
            temporary=_boolean(manager,temporary,drill)
        feature, body = _persist(design, temporary, kind)
        faces = tuple(face for face in _items(body.faces)
                      if adsk.core.Plane.cast(face.geometry) is not None
                      and abs(face.boundingBox.minPoint.z) < 1e-7
                      and abs(face.boundingBox.maxPoint.z) < 1e-7)
    elif kind in ("cylinder", "cylinder_wrap"):
        start, end = adsk.core.Point3D.create(0, 0, 0), adsk.core.Point3D.create(0, 0, 3.2)
        temporary = manager.createCylinderOrCone(start, 1.6, end, 1.6)
        inner = manager.createCylinderOrCone(adsk.core.Point3D.create(0, 0, -.1), 1.3,
                                             adsk.core.Point3D.create(0, 0, 3.3), 1.3)
        feature, body = _persist(design, _boolean(manager, temporary, inner), kind)
        outer = next(face for face in _items(body.faces)
                     if adsk.core.Cylinder.cast(face.geometry) is not None
                     and abs(adsk.core.Cylinder.cast(face.geometry).radius-1.6) < 1e-7)
        if kind == "cylinder_wrap":
            faces = (outer,)
        else:
            selected = adsk.core.ObjectCollection.create()
            selected.add(outer)
            spec = root.features.splitFaceFeatures.createInput(selected, root.xZConstructionPlane, True)
            split = root.features.splitFaceFeatures.add(spec)
            if split is None or not split.isValid:
                raise RuntimeError("Could not split the cylinder fixture into independently selected half faces.")
            faces = tuple(face for face in _items(body.faces)
                          if adsk.core.Cylinder.cast(face.geometry) is not None
                          and abs(adsk.core.Cylinder.cast(face.geometry).radius-1.6) < 1e-7
                          and face.pointOnFace.y > 1e-5)
    elif kind == "cone":
        start, end = adsk.core.Point3D.create(0, 0, 0), adsk.core.Point3D.create(0, 0, 3.2)
        temporary = manager.createCylinderOrCone(start, 1.6, end, 1.8)
        # Extend the inner cone beyond both rims so the shell is truly open.
        inner = manager.createCylinderOrCone(adsk.core.Point3D.create(0, 0, -.1), 1.29375,
                                             adsk.core.Point3D.create(0, 0, 3.3), 1.50625)
        feature, body = _persist(design, _boolean(manager, temporary, inner), kind)
        selected = []
        for face in _items(body.faces):
            if adsk.core.Cone.cast(face.geometry) is not None:
                ok, normal = face.evaluator.getNormalAtPoint(face.pointOnFace)
                if ok and normal.x*face.pointOnFace.x+normal.y*face.pointOnFace.y > 0:
                    selected.append(face)
        faces = tuple(selected)
    elif kind == "hex":
        adapter = STATE["adapter"]
        support = importlib.import_module(STATE["package_name"] + ".tools.hinge.support")
        frame = adapter.hinge.HingeFrame((0, 0, 0), (1, 0, 0), (0, 0, -1), (0, 1, 0))
        def prism(radius):
            polygon = tuple((radius*math.cos(index*math.pi/3), radius*math.sin(index*math.pi/3))
                            for index in range(6))
            return support._prism(manager, frame, polygon, -32, 0)
        temporary = _boolean(manager, prism(16), prism(16-3/math.cos(math.pi/6)))
        feature, body = _persist(design, temporary, kind)
        faces = []
        for face in _items(body.faces):
            plane = adsk.core.Plane.cast(face.geometry)
            if plane is not None:
                ok, normal = face.evaluator.getNormalAtPoint(face.pointOnFace)
                if ok and normal.x > .85 and sum(a*b for a,b in zip(_xyz(face.pointOnFace), _xyz(normal))) > 1.3:
                    faces.append(face)
        faces = tuple(faces)
    elif kind == "notched_panel":
        temporary=_box(manager,-150,150,-3,0,0,170)
        for low,high in ((-25,-15),(-5,5),(15,25)):
            temporary=_boolean(manager,temporary,_box(manager,low,high,-4,1,155,168))
        feature,body=_persist(design,temporary,kind)
        faces=tuple(face for face in _items(body.faces)
            if adsk.core.Plane.cast(face.geometry) is not None
            and abs(face.boundingBox.minPoint.y)<1e-7
            and abs(face.boundingBox.maxPoint.y)<1e-7 and face.area*100>49000)
    elif kind == "sphere":
        origin = adsk.core.Point3D.create(0, 0, 0)
        temporary = _boolean(manager, manager.createSphere(origin, 1.6), manager.createSphere(origin, 1.3))
        feature, body = _persist(design, temporary, kind)
        faces = tuple(face for face in _items(body.faces)
                      if adsk.core.Sphere.cast(face.geometry) is not None
                      and abs(adsk.core.Sphere.cast(face.geometry).radius-1.6) < 1e-7)
    else:
        raise RuntimeError("Unknown fixed pattern fixture.")
    expected = 2 if kind == "hex" else 1
    if len(faces) != expected:
        raise RuntimeError("Disposable " + kind + " fixture has unexpected selected-face count " + str(len(faces)))
    return feature, body, tuple(faces)


def inspect(prepared, kind):
    result, source, settings = prepared.result_body, prepared.body, prepared.settings
    _temporary(result)
    if prepared.cell_count <= 0 or not prepared.accepted_samples:
        raise RuntimeError("The pattern did not apply any cells with independent witnesses.")
    indices = {sample["face_index"] for sample in prepared.accepted_samples}
    if indices != set(range(len(prepared.faces))):
        raise RuntimeError("At least one selected face was silently left without a pattern.")
    delta = float(result.volume)-float(source.volume)
    if (settings.mode == "emboss" and delta <= 0) or (settings.mode != "emboss" and delta >= 0):
        raise RuntimeError("The pattern changed volume in the wrong direction.")
    witnesses = []
    for sample in prepared.accepted_samples:
        point, normal = sample["point_mm"], sample["normal"]
        inward = _add(point, normal, -.5)
        if not _inside(source, inward):
            raise RuntimeError("A fixture normal does not point out of the independently known source wall.")
        checks = []
        if settings.mode == "through":
            for distance in (-.5, -2.7):
                candidate = _add(point, normal, distance)
                checks.append((_inside(source, candidate) and not _inside(result, candidate), "first_wall_open"))
            if sample["first_exit_mm"] is None or not 2.9 < sample["first_exit_mm"] < 3.2:
                raise RuntimeError("The first-wall ray did not measure the fixture's known 3 mm wall.")
        elif settings.mode == "engrave":
            shallow = _add(point, normal, -.5*settings.depth_mm)
            deep = _add(point, normal, -1.5*settings.depth_mm)
            checks.extend(((not _inside(result, shallow), "groove_depth_removed"),
                           (_inside(source, deep) and _inside(result, deep), "groove_floor_retained")))
        else:
            shallow = _add(point, normal, .5*settings.depth_mm)
            beyond = _add(point, normal, 1.25*settings.depth_mm)
            checks.extend(((_inside(result, shallow) and not _inside(source, shallow), "emboss_height_added"),
                           (not _inside(result, beyond), "emboss_height_bounded")))
        if kind == "cylinder":
            opposite = (-14.5*normal[0], -14.5*normal[1], point[2])
            checks.append((_inside(source, opposite) and _inside(result, opposite), "opposite_unselected_wall_intact"))
        if not all(passed for passed, _ in checks):
            raise RuntimeError("A material/depth witness failed: " + str(checks))
        witnesses.append({"face": sample["face_index"], "point_mm": point, "checks": [label for _, label in checks],
                          "first_exit_mm": sample["first_exit_mm"], "next_entry_mm": sample["next_entry_mm"]})
    borders = {"plane": (15, 0, -1.5), "cylinder": (0, 14.5, 1), "cylinder_wrap": (0, 14.5, 1), "hex": (14.5, 0, 16)}
    border = borders.get(kind)
    if border is not None and (not _inside(source, border) or not _inside(result, border)):
        raise RuntimeError("The requested edge border or selected-face ridge was cut.")
    return {"cells": prepared.cell_count, "selected_faces": len(prepared.faces),
            "volume_delta_mm3": delta*1000, "witnesses": witnesses,
            "border_or_ridge_intact": border is not None, "timings": prepared.timings}


def inspect_wrap(prepared):
    details = inspect(prepared, "cylinder_wrap")
    adapter, settings = STATE["adapter"], prepared.settings
    chart = adapter.SurfaceMap(prepared.faces[0])
    if chart.period_u_mm is None or abs(chart.period_u_mm-2*math.pi*16) > 1e-5:
        raise RuntimeError("The full cylinder was not recognized as its exact periodic arc-length chart.")
    mapped = adapter._mapped_cells(prepared.faces, settings)
    if len(mapped) != prepared.cell_count:
        raise RuntimeError("The periodic accepted-cell layout changed during preparation.")
    seam = []
    for cell in adapter.build_cells(settings, chart.bounds, period_u_mm=chart.period_u_mm):
        u, v = cell.center_mm
        if (abs(u-chart.bounds[0]) < 1e-7
                and chart.accepts(u, v, cell.radius_mm, settings.border_mm)):
            sample = chart.sample(u, v)
            if any(sum((a-b)**2 for a,b in zip(candidate.center.point_mm, sample.point_mm)) < 1e-10
                   for candidate in mapped):
                seam.append(sample)
    if not seam:
        raise RuntimeError("No actual accepted periodic cell crosses the cylindrical seam.")
    # Every physical center around the circumference must be present, not just
    # the first few samples returned as lightweight application diagnostics.
    for cell in mapped:
        point, normal = cell.center.point_mm, cell.center.normal
        distance = .5*settings.depth_mm if settings.mode == "emboss" else -.5
        state = _inside(prepared.result_body, _add(point, normal, distance))
        if state != (settings.mode == "emboss"):
            raise RuntimeError("An actual full-wrap cell center did not change the selected cylinder.")
    sample = seam[0]
    for degrees in (-1, 0, 1):
        angle = math.radians(degrees)
        x, y = sample.normal[:2]
        normal = (x*math.cos(angle)-y*math.sin(angle), x*math.sin(angle)+y*math.cos(angle), 0)
        point = (16*normal[0], 16*normal[1], sample.point_mm[2])
        depth = .5*settings.depth_mm if settings.mode == "emboss" else -1.5 if settings.mode == "through" else -.5*settings.depth_mm
        if _inside(prepared.result_body, _add(point, normal, depth)) != (settings.mode == "emboss"):
            raise RuntimeError("A real pattern cell stopped at the cylindrical parameter seam.")
    details.update(period_mm=chart.period_u_mm, full_wrap_centers_checked=len(mapped),
                   crossing_seam_cells=len(seam), seam_sides_checked=3)
    return details


def capture_pattern(prepared, label):
    """Render the exact detached CAD result, then restore the user's full view."""
    app = adsk.core.Application.get()
    viewport = app.activeViewport
    design = prepared.design
    root = design.rootComponent
    before = snapshot(design)
    camera = viewport.camera
    original_camera = _camera_signature(camera)
    bodies = [(body, body.isLightBulbOn) for body in _items(root.bRepBodies)]
    groups = [(group, group.isVisible) for group in _items(root.customGraphicsGroups)]
    group = None
    report_path = Path(STATE["context"].get("report_path") or STATE["root"] / "output/native/pattern-probe.json")
    path = report_path.with_name(report_path.stem+"-"+label+".png")
    try:
        for body, _ in bodies:
            body.isLightBulbOn = False
        for graphic, _ in groups:
            graphic.isVisible = False
        view = viewport.camera
        view.cameraType = adsk.core.CameraTypes.OrthographicCameraType
        view.isFitView = False
        view.isSmoothTransition = False
        z = 0 if label.startswith("sphere") else 16
        view.target = adsk.core.Point3D.create(0, 0, z/10)
        view.eye = adsk.core.Point3D.create(5.5, -6, (z+40)/10)
        view.upVector = adsk.core.Vector3D.create(0, 0, 1)
        if view.setExtents(6, 6) is False:
            raise RuntimeError("Could not frame the owned pattern visual.")
        if label=='balanced-notched-panel':
            view.target=adsk.core.Point3D.create(0,-.15,8.5)
            view.eye=adsk.core.Point3D.create(0,35,8.5)
            view.upVector=adsk.core.Vector3D.create(0,0,1)
            view.setExtents(34,25.5)
        viewport.camera = view
        group = STATE["adapter"].preview_pattern(prepared)
        viewport.refresh()
        if viewport.saveAsImageFile(str(path), 1200, 900) is False:
            raise RuntimeError("Could not save the exact pattern CAD visual.")
    finally:
        cleanup_errors = []
        if group is not None and group.isValid:
            try:
                if group.deleteMe() is False:
                    cleanup_errors.append("owned graphics removal refused")
            except Exception as error:
                cleanup_errors.append(str(error))
        for body, visible in bodies:
            if body.isValid:
                body.isLightBulbOn = visible
        for graphic, visible in groups:
            if graphic.isValid:
                graphic.isVisible = visible
        viewport.camera = camera
        viewport.refresh()
        if (cleanup_errors or snapshot(design) != before
                or _camera_signature(viewport.camera) != original_camera):
            raise RuntimeError("CAD visual capture did not restore the exact camera/source/graphics state.")
    STATE["report"].setdefault("visuals", []).append({"name": label, "path": str(path),
        "actual_temporary_brep": True, "view_restored": True})


def prepare_checked(design, faces, settings):
    before = snapshot(design)
    refs = tuple(entity for face in faces for entity in (face, face.body))
    prepared = STATE["adapter"].prepare_pattern(design, faces, settings)
    if snapshot(design) != before or not all(entity.isValid for entity in refs):
        raise RuntimeError("Preparing a pattern left scratch history/body/appearance changes or invalidated its sources.")
    STATE.setdefault("detached", []).append(prepared.result_body)
    if prepared.colour_body is not None:
        STATE.setdefault("detached_colours",[]).append((prepared.colour_body,prepared.colour_body.lumps.count,float(prepared.colour_body.volume)))
    STATE["recipe"].validate_preview_sources(prepared)
    return prepared


def _progress(label,phase):
    """Small atomic checkpoints; diagnostic I/O must never interrupt CAD."""
    try:
        path=Path(STATE['context']['report_path']).with_suffix('.progress.json')
        temporary=path.with_suffix('.progress.tmp')
        temporary.write_text(json.dumps({'case':label,'phase':phase,'completed_cases':len(STATE['report']['cases']),
            'updated_at':time.time()},sort_keys=True),encoding='utf-8')
        temporary.replace(path)
    except Exception:pass


def _case(label, function, *, optional=False):
    _progress(label,"running")
    if cancellation_requested():
        raise RuntimeError("Pattern validation cancelled.")
    try:
        details = function()
        STATE["report"]["cases"].append({"name": label, "passed": True, **(details or {})})
        _progress(label,"complete")
    except ValueError as error:
        _progress(label,"refused")
        message = str(error)
        bounded = ("singular", "smaller", "surface", "curvature", "distort", "regular", "offset", "thicken", "depth band", "fit", "cells")
        if not optional or not any(word in message.lower() for word in bounded):
            raise
        STATE["report"]["cases"].append({"name": label, "passed": True, "bounded_refusal": message})


def _fixed_settings(**values):
    return STATE['settings_module'].PatternSettings(**{'pitch_mm':8,'web_mm':1.2,'layout_mode':'fixed','edge_mode':'whole','border_mm':2,**values})


def run_direct_prism_proof(design,direct,adapter,settings_class):
    import time
    import adsk.core as core
    import adsk.fusion as native
    root=design.rootComponent
    before=(root.bRepBodies.count,design.timeline.count,design.timeline.markerPosition,
            root.customGraphicsGroups.count,design.appearances.count)
    manager=native.TemporaryBRepManager.get()
    frames=(adapter.hinge.HingeFrame((0,0,0),(1,0,0),(0,1,0),(0,0,1)),
            adapter.hinge.HingeFrame((123.4,-56.7,89.01),
                tuple(value/math.sqrt(14) for value in (1,2,3)),
                tuple(value/math.sqrt(5) for value in (-2,1,0)),
                tuple(value/math.sqrt(70) for value in (-3,-6,5))))
    # The old symbol is imported directly here only as a proof baseline.
    # No production monkeypatching or default backend replacement occurs.
    clipped_prism=sys.modules[adapter.hinge.__package__+'.support']._prism
    cases=[]
    for shape in ('hexagon','circle','diamond','square','slot'):
        values=settings_class(pattern=shape,layout_mode='fixed',edge_mode='whole',pitch_mm=8,web_mm=1.2,border_mm=2,rotation_deg=17)
        polygon=adapter.build_cells(values,(-10,10,-10,10))[0].polygon_mm
        for frame_index,frame in enumerate(frames):
            for low,high in ((-3,.02),(-.02,1.02)):
                diagnostics={}
                started=time.perf_counter()
                new=direct.prism(frame,polygon,low,high,diagnostics=diagnostics)
                new_ms=(time.perf_counter()-started)*1000
                started=time.perf_counter()
                old=clipped_prism(manager,frame,polygon,low,high)
                old_ms=(time.perf_counter()-started)*1000
                plan=direct.plan_prism(frame,polygon,low,high)
                count=len(polygon)
                if (new.faces.count,new.edges.count,new.vertices.count)!=(count+2,3*count,2*count):
                    raise RuntimeError('Direct prism native topology differs from its closed shared-edge construction.')
                def mm(point):return tuple(value*10 for value in (point.x,point.y,point.z))
                for axis in range(3):
                    if (abs(mm(new.boundingBox.minPoint)[axis]-min(p[axis] for p in plan.points_mm))>1e-5
                            or abs(mm(new.boundingBox.maxPoint)[axis]-max(p[axis] for p in plan.points_mm))>1e-5):
                        raise RuntimeError('Direct prism bounds differ from its exact transformed vertices.')
                intersection=manager.copy(new)
                if not manager.booleanOperation(intersection,old,native.BooleanTypes.IntersectionBooleanType):
                    raise RuntimeError('The new and old exact prisms could not be intersected for proof.')
                expected=plan.volume_mm3/1000
                tolerance=max(1e-10,expected*1e-6)
                if any(abs(float(body.volume)-expected)>tolerance for body in (new,old,intersection)):
                    raise RuntimeError('Direct and clipped prisms are not equal by common material volume.')
                center=core.Point3D.create(*(value/10 for value in plan.center_mm))
                inside=native.PointContainment.PointInsidePointContainment
                if new.pointContainment(center)!=inside or old.pointContainment(center)!=inside:
                    raise RuntimeError('A direct or clipped prism has reversed or missing interior material.')
                # Every native planar face normal must point away from the known interior.
                for index in range(new.faces.count):
                    face=new.faces.item(index)
                    okay,normal=face.evaluator.getNormalAtPoint(face.pointOnFace)
                    point=mm(face.pointOnFace)
                    delta=tuple(a-b for a,b in zip(point,plan.center_mm))
                    if not okay or sum(a*b for a,b in zip((normal.x,normal.y,normal.z),delta))<=1e-7:
                        raise RuntimeError('A direct prism face does not have an outward native normal.')
                outside=native.PointContainment.PointOutsidePointContainment
                cx=sum(x for x,z in polygon)/count
                cz=sum(z for x,z in polygon)/count
                for y in (low-.1,high+.1):
                    point=core.Point3D.create(*(value/10 for value in frame.point_mm(cx,y,cz)))
                    if new.pointContainment(point)!=outside or old.pointContainment(point)!=outside:
                        raise RuntimeError('Direct prism depth endpoints changed.')
                STATE.setdefault('detached', []).append(new)
                cases.append({'shape':shape,'frame':frame_index,'interval_mm':(low,high),
                    'new_ms':new_ms,'clipped_ms':old_ms,'speed_ratio':old_ms/max(new_ms,1e-9),
                    'intersection_error_mm3':abs(float(intersection.volume)*1000-plan.volume_mm3),
                    'diagnostics':diagnostics})
    after=(root.bRepBodies.count,design.timeline.count,design.timeline.markerPosition,
           root.customGraphicsGroups.count,design.appearances.count)
    if after!=before:
        raise RuntimeError('Temporary direct-prism proof changed native document state.')
    return {'cases':cases,'case_count':len(cases),'document_unchanged':True,
            'clipped_total_ms':sum(case['clipped_ms'] for case in cases),
            'direct_total_ms':sum(case['new_ms'] for case in cases)}


def _performance_cases(design):
    import time
    adapter=STATE['adapter']
    direct=importlib.import_module(adapter.__package__+'.prism')
    _case('direct_prism_twenty_native_equivalences',lambda:run_direct_prism_proof(
        design,direct,adapter,STATE['settings_module'].PatternSettings))
    _,body,faces=fixture(design,'notched_panel')
    def batch_equivalence():
        settings=STATE['settings_module'].PatternSettings(pitch_mm=8,web_mm=1.2,border_mm=2,layout_mode='fit',edge_mode='whole')
        fast=prepare_checked(design,faces,settings)
        if not fast.timings['batch_used']:
            raise RuntimeError('The dense native Through fixture did not exercise the batch path.')
        original=adapter.try_through_difference
        try:
            adapter.try_through_difference=lambda *args,**kwargs:None
            sequential=prepare_checked(design,faces,settings)
        finally:adapter.try_through_difference=original
        if sequential.timings['batch_used'] or fast.cell_count!=sequential.cell_count:
            raise RuntimeError('The forced exact fallback changed the selected layout.')
        manager=adsk.fusion.TemporaryBRepManager.get()
        common=manager.copy(fast.result_body)
        if not manager.booleanOperation(common,sequential.result_body,adsk.fusion.BooleanTypes.IntersectionBooleanType):
            raise RuntimeError('Batch and sequential pattern material could not be compared.')
        volume=float(sequential.result_body.volume)
        if any(abs(float(candidate.volume)-volume)>max(1e-8,volume*1e-8)
               for candidate in (common,fast.result_body)):
            raise RuntimeError('Batch and exact fallback differ by material volume.')
        for field in ('minPoint','maxPoint'):
            if any(abs(a-b)>1e-6 for a,b in zip(_xyz(getattr(fast.result_body.boundingBox,field)),
                                               _xyz(getattr(sequential.result_body.boundingBox,field)))):
                raise RuntimeError('Batch and sequential pattern bounds differ.')
        chart=adapter.SurfaceMap(faces[0])
        for cell in fast.layouts[0].cells:
            sample=chart.sample(*cell.center_mm)
            point=_add(sample.point_mm,sample.normal,-1.5)
            if not _inside(body,point) or any(_inside(candidate,point) for candidate in (fast.result_body,sequential.result_body)):
                raise RuntimeError('Batch or fallback lost an actual cell opening.')
        before=snapshot(design);group=None
        started=time.perf_counter()
        try:
            group=adapter.preview_pattern(fast)
            adsk.core.Application.get().activeViewport.refresh()
            draw_ms=(time.perf_counter()-started)*1000
        finally:
            if group is not None and group.isValid:group.deleteMe()
        if snapshot(design)!=before:
            raise RuntimeError('Dense drawing benchmark changed source geometry/display state.')
        return {'cells':fast.cell_count,'batch_timings':fast.timings,'sequential_timings':sequential.timings,
                'same_complete_material':True,'all_cell_material_witnesses':fast.cell_count,
                'forced_fallback_exact':True,'graphics_draw_and_refresh_ms':draw_ms}
    _case('dense_batch_matches_exact_fallback',batch_equivalence)


def _fit_cases(design):
    adapter=STATE['adapter']
    Settings=STATE['settings_module'].PatternSettings
    _,panel,faces=fixture(design,'notched_panel')
    def panel_result(layout_mode):
        settings=Settings(layout_mode=layout_mode,pitch_mm=40,web_mm=10,border_mm=3,edge_mode='whole')
        prepared=prepare_checked(design,faces,settings)
        chart=adapter.SurfaceMap(faces[0])
        samples=[chart.sample(*cell.center_mm) for cell in prepared.layouts[0].cells]
        groups=[[],[],[]]
        for sample in samples:
            x,_,z=sample.point_mm
            if z<130:
                if x< -60:groups[0].append(sample)
                elif abs(x)<45:groups[1].append(sample)
                elif x>60:groups[2].append(sample)
        if not all(groups) or prepared.cell_count<20:
            raise RuntimeError('Short top-slot edges still exclude the available middle of the panel.')
        for group in groups:
            sample=group[0]
            point=_add(sample.point_mm,sample.normal,-1.5)
            if not _inside(panel,point) or _inside(prepared.result_body,point):
                raise RuntimeError('An accepted left/middle/right panel cell did not cut actual material.')
        for x in (-14.5,5.5,25.5):
            point=(x,-1.5,160)
            if not _inside(panel,point) or not _inside(prepared.result_body,point):
                raise RuntimeError('The real border of an existing top slot was lost.')
        detail={'cells':prepared.cell_count,'middle_cells_below_slots':len(groups[1]),
                'existing_trim_borders_retained':True,'selected_faces':1,
                'target_pitch_mm':settings.pitch_mm,
                'effective_pitch_mm':prepared.layouts[0].effective_pitch_mm}
        if layout_mode=='fit':
            points=[chart.sample(cell.center_mm[0]+u,cell.center_mm[1]+v).point_mm
                    for cell in prepared.layouts[0].cells for u,v in cell.polygon_mm]
            left=min(p[0] for p in points)+150;right=150-max(p[0] for p in points)
            bottom=min(p[2] for p in points);top=170-max(p[2] for p in points)
            if min(left,right,bottom,top)<3-.01 or abs(left-right)>.05 or abs(bottom-top)>.05:
                raise RuntimeError('Automatic panel layout did not balance opposite real margins.')
            detail['opposite_margins_mm']=[left,right,bottom,top]
            capture_pattern(prepared,'balanced-notched-panel')
        return detail
    _case('finite_trims_keep_middle_columns',lambda:panel_result('fixed'))
    _case('automatic_balanced_notched_panel',lambda:panel_result('fit'))
    _,body,plane_faces=fixture(design,'plane')
    def automatic_density():
        settings=Settings(pitch_mm=1,web_mm=.2,layout_mode='fit',edge_mode='whole')
        prepared=prepare_checked(design,plane_faces,settings)
        if not 0<prepared.cell_count<=200 or prepared.layouts[0].effective_pitch_mm<=1 or settings.pitch_mm!=1:
            raise RuntimeError('Automatic spacing failed to fit a dense target within its budget.')
        history,count=design.timeline.count,design.rootComponent.bRepBodies.count
        anchor=STATE['recipe'].create_pattern(design,prepared)
        target=STATE['recipe'].read_edit_target(design,body)
        changed=replace(settings,pitch_mm=3)
        updated=STATE['recipe'].prepare_edit_pattern(design,target,changed)
        if STATE['recipe'].rebuild_pattern(design,target,updated)!=anchor:
            raise RuntimeError('Automatic Rebuild replaced the owned feature.')
        current=STATE['recipe'].read_edit_target(design,body)
        if (current.settings!=changed or current.record.target!=body
                or design.timeline.count!=history+3 or design.rootComponent.bRepBodies.count!=count
                or _signature(body)!=_signature(updated.result_body)):
            raise RuntimeError('Automatic Create/Rebuild lost settings, identity or its exact full result.')
        return {'cells':prepared.cell_count,'target_pitch_mm':1,
                'effective_pitch_mm':prepared.layouts[0].effective_pitch_mm,'settings_unchanged':True,
                'automatic_create_rebuild_same_body':True}
    _case('automatic_dense_target_without_refusal',automatic_density)
    _,body,wrap_faces=fixture(design,'cylinder_wrap')
    for mode in ('through','engrave','emboss'):
        def wrapped(mode=mode):
            settings=Settings(mode=mode,pitch_mm=8,web_mm=2,layout_mode='fit',edge_mode='whole')
            prepared=prepare_checked(design,wrap_faces,settings)
            detail=inspect(prepared,'cylinder_wrap')
            chart=adapter.SurfaceMap(wrap_faces[0]);layout=prepared.layouts[0]
            rows={}
            for cell in layout.cells:
                u,v=cell.center_mm;rows.setdefault(round(v,7),[]).append(u)
                sample=chart.sample(u,v)
                distance=.5 if mode=='emboss' else -.5
                if _inside(prepared.result_body,_add(sample.point_mm,sample.normal,distance))!=(mode=='emboss'):
                    raise RuntimeError('An automatic wrapped cell did not change real material.')
            for row in rows.values():
                row.sort()
                gaps=[b-a for a,b in zip(row,row[1:])]+[chart.period_u_mm-row[-1]+row[0]]
                if max(gaps)-min(gaps)>1e-5:
                    raise RuntimeError('Automatic cylinder spacing has an oversized seam gap.')
            if mode=='through':capture_pattern(prepared,'automatic-cylinder-wrap')
            detail['effective_pitch_mm']=layout.effective_pitch_mm
            detail['periodic_closure_uniform']=True
            return detail
        _case('automatic_full_wrap_'+mode,wrapped)


def _fill_cases(design):
    def Settings(**values):
        return STATE['settings_module'].PatternSettings(**{'border_mm':2,**values})
    adapter=STATE['adapter'];recipe=STATE['recipe']
    for shape in ('hexagon','circle','diamond','square','slot'):
        def planar(shape=shape):
            _,body,faces=fixture(design,'plane')
            settings=Settings(pattern=shape,pitch_mm=6.5,web_mm=1.5,layout_mode='fill',edge_mode='whole')
            prepared=prepare_checked(design,faces,settings)
            if prepared.cell_count<4:raise RuntimeError('Fill face did not populate the plane.')
            polygon=prepared.layouts[0].cells[0].polygon_mm
            width=max(x for x,y in polygon)-min(x for x,y in polygon)
            if abs(width-5)>1e-7:raise RuntimeError('Fill face changed the requested cell size.')
            detail=inspect(prepared,'plane');detail['requested_size_mm']=5;detail['minimum_gap_mm']=1.5
            if shape=='hexagon':
                history,count=design.timeline.count,design.rootComponent.bRepBodies.count
                anchor=recipe.create_pattern(design,prepared)
                target=recipe.read_edit_target(design,body)
                changed=replace(settings,pitch_mm=7.5)
                updated=recipe.prepare_edit_pattern(design,target,changed)
                if recipe.rebuild_pattern(design,target,updated)!=anchor:
                    raise RuntimeError('Fill Rebuild replaced its owned anchor.')
                current=recipe.read_edit_target(design,body)
                if (current.settings!=changed or current.record.target!=body
                        or design.timeline.count!=history+3 or design.rootComponent.bRepBodies.count!=count
                        or _signature(body)!=_signature(updated.result_body)):
                    raise RuntimeError('Fill Create/Edit/Rebuild lost settings, body identity or exact result.')
                detail['fill_create_edit_rebuild_same_body']=True
            return detail
        _case('fill_fixed_size_plane_'+shape,planar)
    for mode in ('through','engrave','emboss'):
        def wrapped(mode=mode):
            _,body,faces=fixture(design,'cylinder_wrap')
            settings=Settings(layout_mode='fill',edge_mode='whole',mode=mode,pitch_mm=8,web_mm=2,depth_mm=.5)
            prepared=prepare_checked(design,faces,settings)
            polygon=prepared.layouts[0].cells[0].polygon_mm
            if abs(max(x for x,y in polygon)-min(x for x,y in polygon)-6)>1e-7:
                raise RuntimeError('Full wrap changed the requested fixed cell size.')
            detail=inspect(prepared,'cylinder_wrap');detail['requested_size_mm']=6
            detail['effective_u_pitch_mm']=prepared.layouts[0].effective_pitch_mm
            return detail
        _case('fill_fixed_size_wrap_'+mode,wrapped)
    def balanced():
        _,body,faces=fixture(design,'notched_panel')
        settings=Settings(layout_mode='balanced',pitch_mm=17.5,web_mm=5)
        prepared=prepare_checked(design,faces,settings)
        if not 0<prepared.cell_count<=48:raise RuntimeError('Balanced default exceeded its soft cell budget.')
        return {'cells':prepared.cell_count,'layout_mode':settings.layout_mode,'soft_limit_per_face':48}
    _case('balanced_default_sparse_panel',balanced)


def _clip_cases(design):
    Settings=STATE['settings_module'].PatternSettings
    adapter=STATE['adapter'];recipe=STATE['recipe']
    clipping=importlib.import_module(adapter.__package__+'.clipping')
    planner=importlib.import_module(adapter.__package__+'.planner')
    for shape in ('hexagon','circle','diamond','square','slot'):
        for mode in ('through','engrave','emboss'):
            def planar(shape=shape,mode=mode):
                _,body,faces=fixture(design,'plane')
                settings=Settings(pattern=shape,mode=mode,layout_mode='fill',pitch_mm=11.5,
                                  web_mm=5,depth_mm=.5,offset_u_mm=2,offset_v_mm=2)
                prepared=prepare_checked(design,faces,settings)
                full_area=clipping.area(planner._polygon(settings))
                partial=sum(clipping.area(cell.polygon_mm)<full_area*.99 for cell in prepared.layouts[0].cells)
                if not partial:raise RuntimeError('The fixture did not retain partial boundary cells.')
                detail=inspect(prepared,'plane');detail['partial_cells']=partial;detail['edge_mode']='clip'
                if shape=='hexagon' and mode=='through':
                    history,count=design.timeline.count,design.rootComponent.bRepBodies.count
                    anchor=recipe.create_pattern(design,prepared)
                    target=recipe.read_edit_target(design,body)
                    changed=replace(settings,web_mm=6,pitch_mm=12.5)
                    updated=recipe.prepare_edit_pattern(design,target,changed)
                    recipe.rebuild_pattern(design,target,updated)
                    current=recipe.read_edit_target(design,body)
                    if (current.anchor!=anchor or current.settings!=changed or current.record.target!=body
                            or design.timeline.count!=history+3 or design.rootComponent.bRepBodies.count!=count):
                        raise RuntimeError('Clipped-cell Rebuild lost identity, settings or owned history.')
                    detail['clipped_create_edit_rebuild_same_body']=True
                return detail
            _case('clipped_plane_'+shape+'_'+mode,planar)
    for mode in ('through','engrave','emboss'):
        def wrapped(mode=mode):
            _,body,faces=fixture(design,'cylinder_wrap')
            settings=Settings(layout_mode='fill',mode=mode,pitch_mm=11,web_mm=5,depth_mm=.5,offset_v_mm=2)
            prepared=prepare_checked(design,faces,settings)
            detail=inspect(prepared,'cylinder_wrap');detail['edge_mode']='clip'
            capture_pattern(prepared,'clipped-wrap-'+mode)
            return detail
        _case('clipped_wrap_'+mode,wrapped)
    def faceted():
        _,body,faces=fixture(design,'hex')
        settings=Settings(layout_mode='fill',mode='engrave',pitch_mm=11,web_mm=5,border_mm=4,depth_mm=.5)
        prepared=prepare_checked(design,faces,settings)
        return {'cells':prepared.cell_count,'selected_faces':len(faces),'edge_mode':'clip','minimum_gap_mm':5}
    _case('clipped_faceted_hex_body',faceted)
    for kind in ('plane_hole','notched_panel'):
        def trimmed(kind=kind):
            _,body,faces=fixture(design,kind)
            settings=Settings(layout_mode='fill',pitch_mm=12 if kind=='plane_hole' else 42,
                              web_mm=5,border_mm=2,offset_u_mm=2,offset_v_mm=2)
            prepared=prepare_checked(design,faces,settings)
            detail={'cells':prepared.cell_count,'edge_mode':'clip','finite_trim_border_retained':True}
            mapped=adapter._mapped_cells(faces,settings)
            chart=adapter.SurfaceMap(faces[0])
            for cell in mapped:
                for sample in cell.samples:
                    if any(not boundary.clears(sample.point_mm,2-1e-6) for boundary in chart._boundaries):
                        raise RuntimeError('Clipped cell crossed the requested border around a real trim.')
            capture_pattern(prepared,'clipped-'+kind)
            return detail
        _case('clipped_real_trim_'+kind,trimmed)


def _auto_cases(design):
    Settings=STATE['settings_module'].PatternSettings
    planner=importlib.import_module(STATE['adapter'].__package__+'.auto_fit')
    counts=[]
    for density in ('sparse','balanced','dense'):
        def panel(density=density):
            _,body,faces=fixture(design,'notched_panel')
            settings=Settings(layout_mode='auto',density=density,web_mm=5,border_mm=2)
            prepared=prepare_checked(design,faces,settings)
            layout=prepared.layouts[0]
            if not 0<layout.cell_count<=planner.DENSITIES[density][1]:raise RuntimeError('Auto density work bound failed.')
            if layout.proposals_evaluated>16 or layout.acceptance_checks>2*planner.DENSITIES[density][1]:
                raise RuntimeError('Auto planning exceeded its explicit work budget.')
            counts.append(layout.cell_count)
            return {'cells':prepared.cell_count,'size_mm':layout.cell_size_mm,'density':density,
                    'proposals':layout.proposals_evaluated,'acceptance_checks':layout.acceptance_checks,'timings':prepared.timings}
        _case('auto_notched_panel_'+density,panel)
    def ordered():
        if len(counts)!=3 or not counts[0]<counts[1]<counts[2]:raise RuntimeError('Native density choices did not change the cell count.')
        return {'density_counts':counts}
    _case('auto_density_order',ordered)
    for shape in ('hexagon','circle','diamond','square','slot'):
        def planar(shape=shape):
            _,body,faces=fixture(design,'plane')
            settings=Settings(layout_mode='auto',pattern=shape,web_mm=1.2,border_mm=2,depth_mm=.5,mode='engrave')
            prepared=prepare_checked(design,faces,settings)
            detail=inspect(prepared,'plane');detail['size_mm']=prepared.layouts[0].cell_size_mm
            return detail
        _case('auto_plane_'+shape,planar)
    for mode in ('through','engrave','emboss'):
        def wrapped(mode=mode):
            _,body,faces=fixture(design,'cylinder_wrap')
            settings=Settings(layout_mode='auto',web_mm=2,border_mm=2,depth_mm=.5,mode=mode)
            prepared=prepare_checked(design,faces,settings)
            layout=prepared.layouts[0]
            period=STATE['adapter'].SurfaceMap(faces[0]).period_u_mm
            if abs(round(period/layout.pitch_mm)*layout.pitch_mm-period)>1e-7:raise RuntimeError('Auto wrap did not close.')
            detail=inspect(prepared,'cylinder_wrap');detail['size_mm']=layout.cell_size_mm
            return detail
        _case('auto_wrap_'+mode,wrapped)


def _variety_cases(design):
    Settings=STATE['settings_module'].PatternSettings
    adapter=STATE['adapter'];recipe=STATE['recipe']
    names=importlib.import_module(adapter.__package__+'.tiles').TILED_PATTERNS
    for name in names:
        for mode in ('through','engrave','emboss'):
            def planar(name=name,mode=mode):
                _,body,faces=fixture(design,'plane')
                settings=Settings(pattern=name,layout_mode='fill',pitch_mm=6.5,web_mm=1.5,border_mm=2,depth_mm=.5,mode=mode)
                prepared=prepare_checked(design,faces,settings)
                detail=inspect(prepared,'plane');detail['reference_size_mm']=prepared.layouts[0].cell_size_mm
                if mode=='through':capture_pattern(prepared,'variety-'+name)
                return detail
            _case('variety_'+name+'_'+mode,planar)
        def wrapped(name=name):
            _,body,faces=fixture(design,'cylinder_wrap')
            settings=Settings(pattern=name,layout_mode='auto',web_mm=1.2,border_mm=2,depth_mm=.5,mode='engrave')
            prepared=prepare_checked(design,faces,settings)
            layout=prepared.layouts[0];period=adapter.SurfaceMap(faces[0]).period_u_mm
            if abs(round(period/layout.repeat_u_mm)*layout.repeat_u_mm-period)>1e-7:raise RuntimeError('Polygon unit did not close around the wrap.')
            if layout.proposals_evaluated>16 or layout.acceptance_checks>128:raise RuntimeError('Polygon planning exceeded its work bounds.')
            detail=inspect(prepared,'cylinder_wrap');detail['reference_size_mm']=layout.cell_size_mm
            detail['repeat_u_mm']=layout.repeat_u_mm
            return detail
        _case('variety_'+name+'_wrap',wrapped)
    def editing():
        _,body,faces=fixture(design,'plane')
        before=(design.rootComponent.bRepBodies.count,design.timeline.count)
        settings=Settings(pattern='cairo',layout_mode='fill',pitch_mm=6.5,web_mm=1.5,mode='engrave',depth_mm=.5)
        prepared=prepare_checked(design,faces,settings)
        anchor=recipe.create_pattern(design,prepared)
        for name in ('rounded_triangle','trihex','octagon_square','rhombille'):
            target=recipe.read_edit_target(design,body)
            changed=replace(settings,pattern=name)
            updated=recipe.prepare_edit_pattern(design,target,changed)
            if recipe.rebuild_pattern(design,target,updated)!=anchor:raise RuntimeError('Changing polygon family replaced the owned anchor.')
            current=recipe.read_edit_target(design,body)
            if (current.settings.pattern!=name or current.record.target!=body
                    or design.rootComponent.bRepBodies.count!=before[0] or design.timeline.count!=before[1]+3):
                raise RuntimeError('Polygon Edit/Rebuild lost settings, target identity or owned history.')
        return {'family_rebuilds':4,'same_body':True,'owned_features':3}
    _case('variety_cross_family_edit_rebuild',editing)


def _flat_grille_cases(design):
    from pathlib import Path
    import xml.etree.ElementTree as ET
    import zipfile
    Settings=STATE['settings_module'].PatternSettings
    adapter=STATE['adapter'];recipe=STATE['recipe']
    colour_store=importlib.import_module(adapter.__package__+'.colour_store')
    exporter=importlib.import_module(adapter.__package__+'.colour_export')
    for kind,shape in (('plane','hexagon'),('plane','rounded_triangle'),('plane_hole','circle'),('cylinder_wrap','hexagon'),('hex','diamond')):
        def flat(kind=kind,shape=shape):
            _,body,faces=fixture(design,kind)
            settings=Settings(pattern=shape,mode='inlay',layout_mode='auto',web_mm=1.2,border_mm=2,depth_mm=.6)
            prepared=prepare_checked(design,faces,settings)
            colour=prepared.colour_body
            if colour is None or abs(prepared.result_body.volume+colour.volume-body.volume)>1e-7:
                raise RuntimeError('Flat colour did not partition exactly the original volume.')
            for sample in prepared.accepted_samples:
                point=_add(sample['point_mm'],sample['normal'],-.3)
                if not _inside(colour,point) or _inside(prepared.result_body,point):
                    raise RuntimeError('Colour/base material assignment failed at an independent depth witness.')
                if _inside(colour,_add(sample['point_mm'],sample['normal'],.01)):
                    raise RuntimeError('Flat colour protruded beyond the original surface.')
            return {'cells':prepared.cell_count,'colour_lumps':colour.lumps.count,'volume_conserved':True,'flush_witnesses':len(prepared.accepted_samples),'timings':prepared.timings}
        _case('flat_colour_'+kind+'_'+shape,flat)
    def persistence():
        _,body,faces=fixture(design,'plane')
        before=(design.rootComponent.bRepBodies.count,design.timeline.count)
        token=body.entityToken
        settings=Settings(mode='inlay',layout_mode='fill',pitch_mm=8,web_mm=2,border_mm=2,depth_mm=.6)
        prepared=prepare_checked(design,faces,settings)
        display=adapter.display_export.prepare(prepared)
        graphics=design.rootComponent.customGraphicsGroups.count
        for cycle in range(3):
            group=adapter.preview_pattern(display)
            if group is None or not group.isValid:raise RuntimeError('Flat colour cached preview did not draw.')
            if group.deleteMe() is False:raise RuntimeError('Flat colour preview cleanup refused.')
            if design.rootComponent.customGraphicsGroups.count!=graphics:raise RuntimeError('Flat colour graphics leaked.')
        anchor=recipe.create_pattern(design,prepared)
        target=recipe.read_edit_target(design,body)
        _,colour=colour_store.read(design,recipe.STORE,target.record)
        colour_token=colour.entityToken
        if recipe.read_edit_target(design,colour).anchor!=anchor:raise RuntimeError('Selecting the colour body did not load its recipe.')
        for shape in ('circle','triangle','hexagon'):
            target=recipe.read_edit_target(design,colour)
            updated=recipe.prepare_edit_pattern(design,target,replace(settings,pattern=shape,pitch_mm=9))
            if recipe.rebuild_pattern(design,target,updated)!=anchor:raise RuntimeError('Flat colour anchor changed.')
            target=recipe.read_edit_target(design,body)
            _,current=colour_store.read(design,recipe.STORE,target.record)
            if (not _same_reference(design,body,token) or not _same_reference(design,current,colour_token)
                    or (design.rootComponent.bRepBodies.count,design.timeline.count)!=(before[0]+1,before[1]+4)):
                raise RuntimeError('Flat colour Rebuild duplicated or replaced owned geometry/history.')
        path=Path(STATE['context']['report_path']).with_name(Path(STATE['context']['report_path']).stem+'-flat-colour.3mf')
        details=exporter.export(design,target,path)
        with zipfile.ZipFile(path) as archive:
            root=ET.fromstring(archive.read('3D/3dmodel.model'))
        ns={'m':exporter.NS}
        if len(root.findall('.//m:mesh',ns))!=2 or len(root.findall('.//m:component',ns))!=2:
            raise RuntimeError('Flat colour 3MF lost its two aligned material parts.')
        # Mode changes explicitly retire/create only the last owned extra feature.
        target=recipe.read_edit_target(design,body)
        changed=recipe.prepare_edit_pattern(design,target,replace(settings,mode='engrave'))
        recipe.rebuild_pattern(design,target,changed)
        if (design.rootComponent.bRepBodies.count,design.timeline.count)!=(before[0],before[1]+3):
            raise RuntimeError('Leaving Flat colour retained an extra body or feature.')
        target=recipe.read_edit_target(design,body)
        changed=recipe.prepare_edit_pattern(design,target,settings)
        recipe.rebuild_pattern(design,target,changed)
        return {'same_target':True,'same_colour_on_rebuild':True,'owned_features':4,'extra_bodies':1,'rebuilds':3,'cached_two_colour_preview':True,'mode_conversions':2,'export':str(path),**details}
    _case('flat_colour_create_edit_rebuild_export',persistence)
    for shape,rotation,tilt in (('grille_parallel',0,45),('grille_parallel',30,45),('grille_cross',0,45),('grille_louver',0,0),('grille_louver',0,30),('grille_louver',0,45),('grille_louver',0,60)):
        def grille(shape=shape,rotation=rotation,tilt=tilt):
            _,body,faces=fixture(design,'plane')
            settings=Settings(pattern=shape,mode='through',layout_mode='fill',pitch_mm=7,web_mm=2,border_mm=2,rotation_deg=rotation,louver_angle_deg=tilt)
            prepared=prepare_checked(design,faces,settings)
            if prepared.result_body.volume>=body.volume or prepared.result_body.lumps.count!=1:
                raise RuntimeError('Grille did not leave a connected perforated body.')
            if not _inside(prepared.result_body,(15,0,-1.5)):
                raise RuntimeError('Grille cut its outer frame.')
            if shape=='grille_louver' and tilt>0:
                expected=math.sin(math.radians(tilt))
                normals=[abs(plane.normal.z) for face in _items(prepared.result_body.faces)
                         if (plane:=adsk.core.Plane.cast(face.geometry)) is not None]
                if not any(abs(value-expected)<1e-5 for value in normals):
                    raise RuntimeError('The requested louver tilt did not produce real inclined walls.')
            before=(design.rootComponent.bRepBodies.count,design.timeline.count)
            anchor=recipe.create_pattern(design,prepared)
            target=recipe.read_edit_target(design,body)
            changed=recipe.prepare_edit_pattern(design,target,replace(settings,pitch_mm=8))
            recipe.rebuild_pattern(design,target,changed)
            if (design.rootComponent.bRepBodies.count,design.timeline.count)!=(before[0],before[1]+3):
                raise RuntimeError('Grille Rebuild duplicated its body or history.')
            return {'openings':prepared.cell_count,'tilt_deg':tilt,'rotation_deg':rotation,'same_body':True,'owned_features':3,'timings':prepared.timings}
        _case('grille_'+shape+'_'+str(rotation)+'_'+str(tilt),grille)


def cases(*, include_polygon_regressions=False):
    design = STATE["design"]
    Settings = _fixed_settings
    recipe = STATE["recipe"]
    _flat_grille_cases(design)
    _clip_cases(design)
    _auto_cases(design)
    # Current release changes material partitioning, persistence and grilles.
    # The expensive unchanged 0.12 polygon-family matrix remains callable for
    # motif/mapping changes, rather than repeating it on each focused run.
    STATE["report"]["scope"]="flat colour, grilles and shared pattern regressions"
    STATE["report"]["polygon_regressions_included"]=include_polygon_regressions
    if include_polygon_regressions:_variety_cases(design)
    fixtures = {}
    for kind in ("plane", "cylinder", "hex"):
        fixtures[kind] = fixture(design, kind)
        _, body, faces = fixtures[kind]
        original = _signature(body)
        for mode in ("through", "engrave", "emboss"):
            settings = Settings(mode=mode, pitch_mm=8, web_mm=2, depth_mm=1, border_mm=2)
            def one(faces=faces, settings=settings, kind=kind):
                return inspect(prepare_checked(design, faces, settings), kind)
            _case(kind + "_" + mode, one)
            if _signature(body) != original:
                raise RuntimeError("Temporary pattern preparation changed its original fixture body.")
    def density_recovery():
        _, body, faces = fixtures["plane"]
        before = snapshot(design)
        settings = Settings(pitch_mm=1, web_mm=.2)
        planner = importlib.import_module(STATE["package_name"]+".tools.patterns.planner")
        try:
            STATE["adapter"].prepare_pattern(design, faces, settings)
        except planner.PatternDensityError as error:
            hint = error.suggested_pitch_mm
            if (hint is None or hint<=settings.pitch_mm or '1 face selected' not in str(error)
                    or 'estimate' not in str(error) or 'select fewer' in str(error)):
                raise RuntimeError("The one-face density refusal lacks actionable, honest guidance.")
        else:
            raise RuntimeError("A dense single face bypassed its cell budget.")
        recovered = replace(settings, pitch_mm=hint)
        cells = STATE["adapter"]._mapped_cells(faces, recovered)
        if not 0<len(cells)<=200 or settings.pitch_mm!=1 or snapshot(design)!=before:
            raise RuntimeError("The density hint did not recover a bounded layout without changing sources/settings.")
        return {"one_selected_face": True, "current_pitch_mm":1,
                "suggested_pitch_mm":hint, "recovered_cells":len(cells),
                "source_and_settings_unchanged":True, "guidance_is_estimate":True}
    _case("single_face_density_guidance_and_recovery",density_recovery)
    _, wrap_body, wrap_faces = fixture(design, "cylinder_wrap")
    for mode in ("through", "engrave", "emboss"):
        def wrapped(mode=mode):
            settings = Settings(mode=mode, pitch_mm=8, web_mm=2, depth_mm=1, border_mm=2)
            prepared = prepare_checked(design, wrap_faces, settings)
            details = inspect_wrap(prepared)
            if mode in ("through", "emboss"):
                capture_pattern(prepared, "full-wrap-"+mode)
            return details
        _case("full_cylinder_wrap_"+mode, wrapped)
    def cone_case():
        _, cone_body, cone_faces = fixture(design, "cone")
        settings = Settings(pattern="circle", mode="engrave", pitch_mm=6, web_mm=2, depth_mm=1, border_mm=2)
        prepared = prepare_checked(design, cone_faces, settings)
        chart = STATE["adapter"].SurfaceMap(cone_faces[0])
        if chart.kind != "general":
            raise RuntimeError("The nonplanar conical test did not exercise the general surface chart.")
        details = inspect(prepared, "cone")
        details.update(surface_kind=chart.kind, positive_general_surface=True)
        capture_pattern(prepared, "cone-engrave")
        return details
    _case("cone_general_surface_engrave", cone_case)
    _, plane, faces = fixtures["plane"]
    for pattern in ("circle", "diamond", "square", "slot"):
        def one(pattern=pattern):
            settings = Settings(pattern=pattern, mode="engrave", pitch_mm=8, web_mm=2)
            return inspect(prepare_checked(design, faces, settings), "plane")
        _case("plane_pattern_" + pattern, one)
    def preview():
        prepared = prepare_checked(design, faces, Settings(mode="engrave", web_mm=2))
        before = snapshot(design)
        group = STATE["adapter"].preview_pattern(prepared)
        try:
            if group is None or not group.isValid or design.rootComponent.customGraphicsGroups.count != len(before["graphics"])+1:
                raise RuntimeError("The pattern preview did not create exactly one owned graphics group.")
            if STATE["adapter"].preview_hide_bodies(prepared) != (plane,):
                raise RuntimeError("The pattern preview visibility lease targets another body.")
        finally:
            if group is not None and group.isValid:
                group.deleteMe()
        if snapshot(design) != before:
            raise RuntimeError("Closing the pattern preview did not restore its exact graphics/source state.")
        return {"opaque_full_result": True, "graphics_cleanup": True}
    _case("preview_graphics_cleanup", preview)
    def persistence():
        before_count, before_timeline = design.rootComponent.bRepBodies.count, design.timeline.count
        token, name, visible = plane.entityToken, plane.name, plane.isLightBulbOn
        prepared = prepare_checked(design, faces, Settings(mode="through", web_mm=2))
        anchor = recipe.create_pattern(design, prepared)
        if (design.rootComponent.bRepBodies.count != before_count or design.timeline.count != before_timeline+3
                or not _same_reference(design, plane, token) or plane.name != name or plane.isLightBulbOn != visible):
            raise RuntimeError("Create replaced the target, changed its identity/state, or added extra solids/history.")
        for selected in (plane, plane.faces.item(0), plane.edges.item(0), anchor):
            target = recipe.read_edit_target(design, selected)
            if target.anchor != anchor or target.record.target != plane:
                raise RuntimeError("A pattern result selection did not resolve to the same owned feature.")
        target = recipe.read_edit_target(design, plane)
        history_refs = dict(target.record.recipe["combines"])
        source_signature = prepared.source_signature
        legacy=json.loads(anchor.attributes.itemByName(recipe.GROUP,'recipe').value)
        legacy['version']=1;legacy['settings'].pop('layout_mode');legacy['settings'].pop('edge_mode')
        legacy['settings'].pop('density');legacy['settings'].pop('size_locked');legacy['settings'].pop('louver_angle_deg')
        legacy_raw=json.dumps(legacy,separators=(',',':'))
        anchor.attributes.add(recipe.GROUP,'recipe',legacy_raw)
        legacy_target=recipe.read_edit_target(design,plane)
        if (legacy_target.settings.layout_mode!='fixed'
                or anchor.attributes.itemByName(recipe.GROUP,'recipe').value!=legacy_raw):
            raise RuntimeError('Reading a legacy recipe changed its spacing mode or saved metadata.')
        for mode in ("engrave", "emboss", "through"):
            target = recipe.read_edit_target(design, plane)
            settings = replace(target.settings, mode=mode, pattern="circle", depth_mm=.8)
            model_before = snapshot(design)
            updated = recipe.prepare_edit_pattern(design, target, settings)
            STATE.setdefault("detached", []).append(updated.result_body)
            if snapshot(design) != model_before or updated.source_signature != source_signature:
                raise RuntimeError("Edit did not prepare from the exact original sources without changing the model.")
            recipe.validate_preview_sources(updated)
            if recipe.rebuild_pattern(design, target, updated) != anchor:
                raise RuntimeError("Rebuild replaced its original feature.")
            current = recipe.read_edit_target(design, plane)
            if (current.settings != settings or current.record.recipe["combines"] != history_refs
                    or design.timeline.count != before_timeline+3
                    or design.rootComponent.bRepBodies.count != before_count
                    or not _same_reference(design, plane, token) or plane.name != name or plane.isLightBulbOn != visible):
                raise RuntimeError("Rebuild added geometry/history, lost settings, or changed the target identity/state.")
            if _signature(plane) != _signature(updated.result_body):
                raise RuntimeError("Rebuild did not persist the exact full preview shape.")
        if json.loads(anchor.attributes.itemByName(recipe.GROUP,'recipe').value)['version']!=5:
            raise RuntimeError('The explicit legacy rebuild did not migrate its recipe.')
        return {"same_body": True, "extra_bodies": 0, "owned_features": 3, "rebuild_modes": 3,
                "face_edge_body_feature_edit": True, "original_source_signature": source_signature,
                'legacy_read_unchanged_then_migrated_on_rebuild':True}
    _case("same_body_create_edit_rebuild", persistence)
    def sphere_case():
        _, body, sphere_faces = fixture(design, "sphere")
        settings = Settings(mode="engrave", pitch_mm=6, web_mm=2, border_mm=2)
        prepared = prepare_checked(design, sphere_faces, settings)
        if STATE["adapter"].SurfaceMap(sphere_faces[0]).kind != "general":
            raise RuntimeError("The sphere did not exercise the general surface chart.")
        details = inspect(prepared, "sphere")
        details.update(surface_kind="general", positive_general_surface=True)
        capture_pattern(prepared, "sphere-engrave")
        return details
    _case("sphere_general_surface_engrave", sphere_case)
    _fit_cases(design)
    _fill_cases(design)
    _performance_cases(design)
    STATE["report"]["geometry_checks_passed"] = all(case["passed"] for case in STATE["report"]["cases"])



# Production async runner integration: executed only AFTER the fixture matrix
# has been rolled back and the original document has passed its exact snapshot.
COMMIT_COMMAND = "sktech_partelier_pattern_probe_commit_67744d4a"


def _camera_signature(camera):
    return (camera.cameraType, _xyz(camera.eye), _xyz(camera.target), _xyz(camera.upVector),
            tuple(round(value, 7) if isinstance(value, float) else value for value in camera.getExtents()))


def _runtime_fail(error):
    STATE["report"]["runtime_error"] = str(error) + "\n" + traceback.format_exc()
    queue_probe_event("runtime:finish")


def _runtime_completed(prepared):
    try:
        if STATE.get("runtime_finishing"):
            return
        design = STATE["runtime_design"]
        STATE["runtime_completed"].append("newest")
        if STATE["runtime_computed"] != ["newest"]:
            raise RuntimeError("The superseded native preview computed or published its stale settings.")
        if snapshot(design) != STATE["runtime_before"]:
            raise RuntimeError("The real preview completion callback ran before native rollback or left scratch state.")
        STATE["recipe"].validate_preview_sources(prepared)
        details = inspect(prepared, "plane")
        if prepared.settings.mode != "emboss" or prepared.settings.depth_mm != .8:
            raise RuntimeError("The production runner published the superseded settings.")
        group = STATE["adapter"].preview_pattern(prepared)
        try:
            if group is None or not group.isValid:
                raise RuntimeError("The post-rollback result could not draw its real full-solid preview.")
        finally:
            if group is not None and group.isValid:
                group.deleteMe()
        if snapshot(design) != STATE["runtime_before"]:
            raise RuntimeError("The post-rollback preview did not restore its exact graphics/source state.")
        STATE["cached_prepared"] = prepared
        STATE["report"]["cases"].append({"name": "production_async_supersede_postrollback_preview",
            "passed": True, "computed": STATE["runtime_computed"],
            "completed": STATE["runtime_completed"], "source_refs_fresh_after_destroy": True,
            "exact_scratch_rollback": True, **details})
        queue_probe_event("runtime:commit")
    except Exception as error:
        _runtime_fail(error)


def _runtime_start():
    app = adsk.core.Application.get()
    if app.activeDocument != STATE["original_document"]:
        raise RuntimeError("The original document changed before the owned async validation started.")
    if snapshot(STATE["design"]) != STATE["report"]["before"]:
        raise RuntimeError("The fixture matrix has not completely rolled back before the async stage.")
    document = app.documents.add(adsk.core.DocumentTypes.FusionDesignDocumentType)
    if document is None or document == STATE["original_document"]:
        raise RuntimeError("Fusion could not create an independent disposable validation document.")
    STATE["runtime_document"] = document
    design = adsk.fusion.Design.cast(app.activeProduct)
    if design is None or design.parentDocument != document:
        raise RuntimeError("The disposable document did not become its own Fusion Design.")
    STATE["runtime_design"] = design
    if design.designType != adsk.fusion.DesignTypes.ParametricDesignType:
        design.designType = adsk.fusion.DesignTypes.ParametricDesignType
    _, body, faces = fixture(design, "plane")
    STATE.update(runtime_body=body, runtime_faces=faces, runtime_before=snapshot(design),
                 runtime_computed=[], runtime_completed=[])
    module = importlib.import_module(STATE["package_name"] + ".tools.patterns.preview")
    runner = module.PatternPreviewRunner(lambda message: STATE["report"].setdefault("runtime_logs", []).append(message))
    # Use actual production implementation with identities owned by this probe,
    # so a separately running Partelier palette cannot share our handlers.
    runner._command_id = "sktech_partelier_pattern_probe_compute_67744d4a"
    runner._requested_event_id = "sktech_partelier_pattern_probe_compute_event_67744d4a"
    runner._event_id = runner._requested_event_id
    STATE["runtime_runner"] = runner
    Settings = _fixed_settings
    def compute(label, settings):
        def operation():
            STATE["runtime_computed"].append(label)
            return STATE["adapter"].prepare_pattern(design, faces, settings)
        return operation
    def stale_completed(value):
        _runtime_fail(RuntimeError("The cancelled preview completion callback was delivered."))
    runner.request(object(), compute("superseded", Settings(mode="engrave", web_mm=2)),
                   stale_completed, _runtime_fail)
    runner.request(object(), compute("newest", Settings(mode="emboss", web_mm=2, depth_mm=.8)),
                   _runtime_completed, _runtime_fail)


class RuntimeCommitPreview(adsk.core.CommandEventHandler):
    def notify(self, args):
        args.isValidResult = False
        try:
            if cancellation_requested():
                return
            design, body = STATE["runtime_design"], STATE["runtime_body"]
            prepared = STATE["cached_prepared"]
            STATE["recipe"].validate_preview_sources(prepared)
            count, history = design.rootComponent.bRepBodies.count, design.timeline.count
            token, name, visible = body.entityToken, body.name, body.isLightBulbOn
            anchor = STATE["recipe"].create_pattern(design, prepared)
            target = STATE["recipe"].read_edit_target(design, body)
            if (target.anchor != anchor or target.record.target != body or target.settings != prepared.settings
                    or design.rootComponent.bRepBodies.count != count or design.timeline.count != history+3
                    or not _same_reference(design, body, token) or body.name != name
                    or body.isLightBulbOn != visible or _signature(body) != _signature(prepared.result_body)):
                raise RuntimeError("The cached post-rollback preview did not create the exact same-body pattern.")
            STATE["report"]["cached_create_passed"] = True
        except Exception:
            STATE["report"]["runtime_error"] = traceback.format_exc()


class RuntimeCommitExecute(adsk.core.CommandEventHandler):
    def notify(self, args):
        STATE["runtime_commit_noop"] = True


class RuntimeCommitDestroyed(adsk.core.CommandEventHandler):
    def notify(self, args):
        STATE["runtime_commit_destroyed"] = True
        if STATE.get("runtime_finishing"):
            return
        try:
            design = STATE["runtime_design"]
            body = STATE["runtime_body"]
            if (snapshot(design) != STATE["runtime_before"]
                    or body.attributes.itemByName(STATE["recipe"].GROUP, "solid_owner") is not None
                    or not STATE.get("runtime_commit_noop") or not STATE["report"].get("cached_create_passed")):
                raise RuntimeError("The cached-result native command did not fully roll back its persistence.")
            STATE["report"]["cases"].append({"name": "production_cached_result_create_rollback", "passed": True,
                "cache_survived_previous_transaction": True, "same_body": True,
                "rollback_history_and_bodies_unchanged": True})
        except Exception:
            STATE["report"]["runtime_error"] = traceback.format_exc()
        queue_probe_event("runtime:finish")


class RuntimeCommitCreated(adsk.core.CommandCreatedEventHandler):
    def notify(self, args):
        command = args.command
        STATE["runtime_commit_command"] = command
        command.isAutoExecute = False
        command.isExecutedWhenPreEmpted = False
        command.isRepeatable = False
        for event, handler in ((command.destroy, RuntimeCommitDestroyed()),
                               (command.executePreview, RuntimeCommitPreview()),
                               (command.execute, RuntimeCommitExecute())):
            if event.add(handler) is False:
                STATE["report"]["runtime_error"] = "Could not bind an owned cached-result validation handler."
                command.isAutoExecute = True
                return
            HANDLERS.append(handler)
        queue_probe_event("runtime:commit_drive")


def _runtime_commit():
    definitions = adsk.core.Application.get().userInterface.commandDefinitions
    if definitions.itemById(COMMIT_COMMAND) is not None:
        raise RuntimeError("The cached-result probe command identity is already in use.")
    definition = definitions.addButtonDefinition(COMMIT_COMMAND, "Partelier cached pattern probe",
                                                  "Validate a cached result in a rollback-only transaction")
    created = RuntimeCommitCreated()
    STATE.update(runtime_commit_definition=definition, runtime_commit_created=created)
    if definition.commandCreated.add(created) is False:
        raise RuntimeError("Could not bind the owned cached-result validation command.")
    HANDLERS.append(created)
    if definition.execute() is False:
        raise RuntimeError("Could not start the cached-result validation transaction.")


def _runtime_cleanup():
    if STATE.get("runtime_cleanup_done") or STATE.get("runtime_cleaning"):
        return
    STATE["runtime_finishing"] = True
    STATE["runtime_cleaning"] = True
    app = adsk.core.Application.get()
    errors = []
    def attempt(label, operation):
        try:
            operation()
        except Exception as error:
            errors.append(label+": "+str(error))
    try:
        runner = STATE.get("runtime_runner")
        if runner is not None:
            attempt("stop owned preview runner", runner.stop)
        command = STATE.get("runtime_commit_command")
        if command is not None and not STATE.get("runtime_commit_destroyed"):
            def terminate_owned_commit():
                if app.userInterface.activeCommand == COMMIT_COMMAND:
                    app.userInterface.terminateActiveCommand()
            attempt("close owned commit command", terminate_owned_commit)
        definition = STATE.get("runtime_commit_definition")
        created = STATE.get("runtime_commit_created")
        if definition is not None and definition.isValid:
            if created is not None:
                attempt("detach owned commit handler", lambda: definition.commandCreated.remove(created))
            def delete_definition():
                if definition.isValid and definition.deleteMe() is False:
                    raise RuntimeError("definition deletion refused")
            attempt("delete owned commit definition", delete_definition)
        document = STATE.get("runtime_document")
        original = STATE["original_document"]
        if document is not None:
            def discard_owned_document():
                if document == original:
                    raise RuntimeError("Refusing to close the user's original document")
                if document.isValid and document.close(False) is False:
                    raise RuntimeError("disposable document close refused")
            attempt("discard only owned scratch document", discard_owned_document)
        def restore_original():
            if not original.isValid or original.activate() is False:
                raise RuntimeError("original document activation refused")
        attempt("restore original active document", restore_original)
        if app.activeDocument == original:
            def restore_camera():
                app.activeViewport.camera = STATE["original_camera"]
                app.activeViewport.refresh()
                if _camera_signature(app.activeViewport.camera) != STATE["original_camera_signature"]:
                    raise RuntimeError("original camera did not restore exactly")
            attempt("restore original camera", restore_camera)
        else:
            errors.append("original document is not active; camera was not applied to another document")
        def verify_original():
            if (app.activeDocument != original
                    or STATE["design"].activeComponent != STATE["original_active_component"]
                    or snapshot(STATE["design"]) != STATE["report"]["before"]):
                raise RuntimeError("original document/component/model state changed")
        attempt("verify original document state", verify_original)
        if errors:
            raise RuntimeError("; ".join(errors))
        STATE["runtime_cleanup_done"] = True
        if not STATE["report"].get("runtime_error") and not cancellation_requested():
            STATE["report"]["cases"].append({"name": "production_disposable_document_cleanup", "passed": True,
                "discarded_without_saving": True, "original_document_active": True,
                "original_component_and_model_unchanged": True, "original_camera_restored": True})
            STATE["report"]["production_async_passed"] = True
    finally:
        STATE["runtime_cleaning"] = False


def _drive_runtime(information):
    try:
        if cancellation_requested():
            _runtime_cleanup()
            finish_report()
        elif information == "runtime:start":
            _runtime_start()
        elif information == "runtime:commit":
            _runtime_commit()
        elif information == "runtime:commit_drive":
            command = STATE["runtime_commit_command"]
            if command.doExecutePreview() is False or command.doExecute(True) is False:
                raise RuntimeError("Fusion refused the owned cached-result rollback command.")
        elif information == "runtime:finish":
            _runtime_cleanup()
            finish_report()
    except Exception:
        STATE["report"]["runtime_error"] = traceback.format_exc()
        try:
            _runtime_cleanup()
        except Exception:
            STATE["report"]["runtime_cleanup_error"] = traceback.format_exc()
        finish_report()


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
                STATE["report"]["error"] = "Could not bind the owned pattern probe command."
                command.isAutoExecute = True
                return
            HANDLERS.append(handler)
        queue_probe_event()


class Drive(adsk.core.CustomEventHandler):
    def notify(self, args):
        if args.additionalInfo.startswith("runtime:"):
            _drive_runtime(args.additionalInfo)
            return
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
        if (STATE["report"].get("geometry_checks_passed")
                and not STATE["report"].get("error") and not cancellation_requested()):
            try:
                if snapshot(STATE["design"]) != STATE["report"]["before"]:
                    raise RuntimeError("The original fixture transaction did not fully roll back.")
                queue_probe_event("runtime:start")
                return
            except Exception:
                STATE["report"]["runtime_error"] = traceback.format_exc()
        finish_report()


def cancel():
    STATE["cancelled"] = True
    STATE.get("report", {})["cancelled"] = True
    command = STATE.get("command")
    if command is not None and not STATE.get("destroyed"):
        app = adsk.core.Application.get()
        if app.userInterface.activeCommand == COMMAND:
            app.userInterface.terminateActiveCommand()
        if not STATE.get("destroyed"):
            return
    if STATE.get("runtime_document") is not None:
        try:
            _runtime_cleanup()
        except Exception:
            STATE["report"]["runtime_cleanup_error"] = traceback.format_exc()
    finish_report()


def finish_report():
    if STATE.get("reported"):
        return
    STATE["reported"] = True
    report = STATE["report"]
    report["after"] = snapshot(STATE["design"])
    report["original_references_valid"] = all(entity.isValid for entity in STATE["original_references"])
    detached = STATE.get("detached", ())
    report["detached_survived_rollback"] = bool(detached) and all(
        body.isValid and body.isTemporary and body.isSolid and body.lumps.count == 1 for body in detached)
    colours=STATE.get("detached_colours",())
    report["colour_survived_rollback"]=bool(colours) and all(body.isValid and body.isTemporary and body.isSolid
        and body.lumps.count==lumps and abs(float(body.volume)-volume)<1e-8 for body,lumps,volume in colours)
    report["unchanged"] = report["after"] == report["before"] and report["original_references_valid"]
    report["success"] = bool(report.get("geometry_checks_passed") and report.get("noop_execute")
                             and STATE.get("destroyed") and report["unchanged"]
                             and report["detached_survived_rollback"] and report["colour_survived_rollback"] and not cancellation_requested()
                             and report.get("production_async_passed")
                             and not report.get("error") and not report.get("drive_error")
                             and not report.get("runtime_error") and not report.get("runtime_cleanup_error"))
    context = STATE["context"]
    path = Path(context.get("report_path") or STATE["root"] / "output/native/pattern-probe.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    app = adsk.core.Application.get()
    app.log("Partelier pattern probe: " + str(report["success"]) + " -> " + str(path))
    app.unregisterCustomEvent(EVENT)
    definition, created = STATE.get("definition"), STATE.get("created")
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
        raise ValueError("Open a parametric Fusion Design before pattern validation.")
    if design.timeline.markerPosition != design.timeline.count:
        raise ValueError("Move the history marker to the end before pattern validation.")
    STATE.clear()
    STATE.update(root=Path(__file__).resolve().parents[3], design=design,
                 context=context if isinstance(context, dict) else {},
                 original_document=app.activeDocument, original_active_component=design.activeComponent,
                 original_camera=app.activeViewport.camera)
    STATE["original_camera_signature"] = _camera_signature(STATE["original_camera"])
    STATE["original_references"] = [entity for body in _items(design.rootComponent.bRepBodies)
                                    for entity in (body, *_items(body.faces), *_items(body.edges))]
    STATE["report"] = {"scenario": "patterns", "fusion_version": app.version,
                       "before": snapshot(design), "cases": [], "success": False}
    STATE["adapter"], STATE["settings_module"], STATE["recipe"] = load(STATE["root"])
    event = app.registerCustomEvent(EVENT)
    if event is None:
        raise RuntimeError("Could not register the fixed pattern probe event.")
    driver = Drive()
    if event.add(driver) is False:
        app.unregisterCustomEvent(EVENT)
        raise RuntimeError("Could not bind the fixed pattern probe event.")
    HANDLERS.append(driver)
    definition = app.userInterface.commandDefinitions.itemById(COMMAND)
    if definition is not None:
        app.unregisterCustomEvent(EVENT)
        raise RuntimeError("The owned pattern probe command already exists; stop its previous run first.")
    definition = app.userInterface.commandDefinitions.addButtonDefinition(
        COMMAND, "Partelier pattern probe", "Run fixed rollback-only pattern checks")
    created = Created()
    if definition.commandCreated.add(created) is False:
        app.unregisterCustomEvent(EVENT)
        definition.deleteMe()
        raise RuntimeError("Could not bind the fixed pattern probe command.")
    HANDLERS.append(created)
    STATE.update(definition=definition, created=created)
    if not STATE["context"].get("no_auto_terminate"):
        adsk.autoTerminate(False)
    if not definition.execute():
        raise RuntimeError("Fusion could not start the fixed pattern probe.")

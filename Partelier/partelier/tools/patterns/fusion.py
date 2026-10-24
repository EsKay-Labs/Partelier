"""Temporary conformal patterns on native faces, inside caller-owned commands.

Native Offset/Thicken features are used only to obtain exact surface-depth
bands, copied to temporary BRep and removed in finally. Through tools are bounded
to the first wall using parallel ray witnesses and a single-lump intersection.
The caller owns command rollback, persistence, and preview visibility leases.
"""

from dataclasses import dataclass
import math
import threading
import time

from ..hinge import fusion as hinge
from ..hinge.support import _prism
from .planner import MAX_CELLS, MAX_FACE_CELLS, build_cells, build_layout, density_error
from .surfaces import SurfaceMap
from .prism import prism as _direct_prism
from .batch import try_through_difference
from . import display_export
from . import clipping
from ...diagnostics import emit


MAX_TOTAL_CELLS = MAX_CELLS
EPSILON_MM = .001
EMBED_MM = .02
MIN_NORMAL_DOT = .90


@dataclass(frozen=True)
class PreparedPattern:
    design: object
    faces: tuple
    body: object
    settings: object
    result_body: object
    source_signature: tuple
    timings: dict
    cell_count: int
    source_tokens: dict
    record: object = None
    saved_recipe: object = None
    accepted_samples: tuple = ()
    layouts: tuple = ()
    display_mesh: object = None
    colour_body: object = None
    colour_mesh: object = None


@dataclass(frozen=True)
class _MappedCell:
    face_index: int
    center: object
    samples: tuple
    polygon: tuple
    world_polygon: tuple
    radius_mm: float
    sag_mm: float
    cell_key: object = None


def _trace_geometry(event,**fields):
    try:
        emit("pattern.geometry."+event,**fields)
    except Exception:
        pass


def _trace_error(error):
    try:
        return str(error)
    except Exception:
        return "<unprintable error>"


def _api():
    return hinge._api()


def _dot(a, b):
    return sum(one * two for one, two in zip(a, b))


def _sub(a, b):
    return tuple(one - two for one, two in zip(a, b))


def _add(a, direction, amount):
    return tuple(one + amount * two for one, two in zip(a, direction))


def _length(value):
    return math.sqrt(_dot(value, value))


def _point(mm):
    core, _ = _api()
    return core.Point3D.create(*(value / 10 for value in mm))


def _solid(body, message):
    if (body is None or not body.isValid or not body.isSolid or body.lumps.count != 1
            or not math.isfinite(float(body.volume)) or body.volume <= 0):
        raise ValueError(message)
    return body


def _copy(manager, body):
    return _solid(manager.copy(body), "Fusion could not copy the pattern solid.")


def _boolean(manager, target, tool, operation, message):
    if not manager.booleanOperation(target, tool, operation):
        raise ValueError(message)
    return _solid(target, message)


def _selection(design, faces, historical=False):
    if threading.current_thread() is not threading.main_thread():
        raise ValueError("Run the pattern tool on Fusion's main thread.")
    _, native = _api()
    if design is None or not design.isValid or design.designType != native.DesignTypes.ParametricDesignType:
        raise ValueError("Open a parametric Fusion Design with history enabled.")
    root = design.rootComponent
    if design.activeComponent != root:
        raise ValueError("Activate the root component before creating a pattern.")
    if not historical and design.timeline.markerPosition != design.timeline.count:
        raise ValueError("Move the history marker to the end before creating a pattern.")
    if not isinstance(faces, (tuple, list)) or not faces:
        raise ValueError("Select one or more faces on the same solid body.")
    unique = []
    body = None
    for face in faces:
        if native.BRepFace.cast(face) is None or not face.isValid or face.assemblyContext is not None:
            raise ValueError("Select native faces in the root component.")
        current = _solid(face.body, "Patterns require one valid source solid.")
        if (current.isTemporary or current.assemblyContext is not None or current.parentComponent != root):
            raise ValueError("Select native faces on a root-component body.")
        if body is not None and current != body:
            raise ValueError("All selected pattern faces must belong to the same body.")
        body = current
        if not any(face == previous for previous in unique):
            unique.append(face)
            if len(unique) > 100:
                raise ValueError("Select at most 100 pattern faces. Use selected faces to limit this body's pattern scope.")
    return tuple(unique), body


def _signature(body, faces):
    return (hinge._body_signature(body), tuple((round(float(face.area), 8), face.geometry.objectType,
            tuple(round(value, 8) for value in hinge._xyz(face.pointOnFace))) for face in faces))


def _tokens(body, faces):
    values = {"body": hinge._token(body), "faces": [hinge._token(face) for face in faces]}
    if len(set(values["faces"])) != len(values["faces"]) or values["body"] in values["faces"]:
        raise ValueError("Fusion did not provide unique references for the selected faces.")
    return values


def _validate_sources_impl(prepared, *, _historical=False):
    """Read-only source freshness; Edit invokes this before its saved feature."""
    faces, body = _selection(prepared.design, prepared.faces, _historical)
    references = prepared.source_tokens
    if not isinstance(references, dict) or set(references) != {"body", "faces"}:
        raise ValueError("The pattern source references changed. Refresh its preview.")
    current = hinge._resolve_one(prepared.design, references["body"], "Pattern source")
    resolved = tuple(hinge._resolve_one(prepared.design, token, "Pattern face") for token in references["faces"])
    if current != body or resolved != faces or _signature(body, faces) != prepared.source_signature:
        raise ValueError("The pattern source geometry changed. Refresh or reselect its faces.")


def validate_sources(prepared, *, _historical=False):
    _trace_geometry("source_validate.begin",historical=_historical)
    try:
        result=_validate_sources_impl(prepared,_historical=_historical)
    except Exception as error:
        _trace_geometry("source_validate.error",error_type=type(error).__name__,error=_trace_error(error))
        raise
    _trace_geometry("source_validate.end",historical=_historical)
    return result


def _face_budgets(areas):
    """Share the bounded automatic work budget; keep small faces selectable."""
    count=len(areas)
    if count<=2:return (MAX_FACE_CELLS,)*count
    if count>MAX_TOTAL_CELLS:raise ValueError("Select fewer faces for automatic spacing.")
    result=[1]*count
    remaining=MAX_TOTAL_CELLS-count
    active=set(range(count))
    weights=[max(float(area),1e-9) for area in areas]
    while remaining and active:
        total=sum(weights[index] for index in active)
        quotas={index:remaining*weights[index]/total for index in active}
        saturated=[index for index in active if quotas[index]>=MAX_FACE_CELLS-result[index]]
        if saturated:
            for index in saturated:
                amount=MAX_FACE_CELLS-result[index]
                result[index]+=amount;remaining-=amount;active.remove(index)
            continue
        for index in sorted(active):
            amount=min(remaining,int(quotas[index]))
            result[index]+=amount;remaining-=amount
        for index in sorted(active,key=lambda i:(-(quotas[i]-int(quotas[i])),i)):
            if not remaining:break
            if result[index]<MAX_FACE_CELLS:result[index]+=1;remaining-=1
        break
    return tuple(result)


def _mapped_cells(faces, settings, *, _return_layouts=False):
    """Skip charts with no complete cells; refuse an empty overall result.

    This lets whole-body selection retain small rim faces unchanged. An invalid
    chart, excessive curvature or reduced web still refuses the whole request.
    """
    mapped = []
    layouts=[]
    budgets=_face_budgets([face.area for face in faces]) if settings.layout_mode!='fixed' else (MAX_FACE_CELLS,)*len(faces)
    for index, face in enumerate(faces):
        if settings.pattern.startswith("grille_"):
            core,_=_api()
            if core.Plane.cast(face.geometry) is None:
                raise ValueError("Grilles currently require planar faces. Use Patterns for curved surfaces.")
        chart = SurfaceMap(face)
        accepted = 0
        fragments={}
        def accept(cell):
            if settings.edge_mode=='whole':return chart.accepts(*cell.center_mm,cell.radius_mm,settings.border_mm)
            fragments[cell]=chart.clipped_cells(cell,settings.border_mm)
            if settings.layout_mode=='auto':
                return sum(clipping.area(part.polygon_mm) for part in fragments[cell])/max(1e-12,clipping.area(cell.polygon_mm))
            return bool(fragments[cell])
        layout=build_layout(settings,chart.bounds,period_u_mm=chart.period_u_mm,max_cells=budgets[index],
            accept=accept)
        layouts.append(layout)
        pieces=[]
        for ordinal,cell in enumerate(layout.cells):
            parts=fragments[cell] if settings.edge_mode=='clip' else (cell,)
            pieces.extend((part,(index,ordinal) if settings.edge_mode=='clip' else None) for part in parts)
        for cell,cell_key in pieces:
            u, v = cell.center_mm
            center = chart.sample(u, v)
            boundary = tuple(chart.sample(u + du, v + dv) for du, dv in cell.polygon_mm)
            midpoints = tuple(chart.sample(u + (a[0] + b[0]) / 2, v + (a[1] + b[1]) / 2)
                              for a, b in zip(cell.polygon_mm, cell.polygon_mm[1:] + cell.polygon_mm[:1]))
            samples = (center,) + boundary + midpoints
            if any(_dot(center.normal, sample.normal) < MIN_NORMAL_DOT for sample in samples):
                raise ValueError("A pattern cell crosses too much curvature. Reduce pitch or select a smaller regular surface region.")
            x_axis = center.tangent_u
            z_axis = hinge._cross(x_axis, center.normal)
            polygon = tuple((_dot(_sub(point.point_mm, center.point_mm), x_axis),
                             _dot(_sub(point.point_mm, center.point_mm), z_axis)) for point in boundary)
            area = sum(a[0] * b[1] - b[0] * a[1] for a, b in zip(polygon, polygon[1:] + polygon[:1]))
            if area < 0:
                polygon = tuple(reversed(polygon))
            radius = max(math.hypot(x, z) for x, z in polygon)
            sag = max(abs(_dot(_sub(sample.point_mm, center.point_mm), center.normal)) for sample in samples)
            mapped.append(_MappedCell(index, center, samples, polygon,
                                      tuple(sample.point_mm for sample in boundary), radius, sag,cell_key))
            accepted += 1
            if len(mapped)>1200:
                raise ValueError('Too many clipped pattern fragments. Increase cell size or select a simpler region.')
            if layout.cell_count>MAX_FACE_CELLS or sum(item.cell_count for item in layouts)>MAX_TOTAL_CELLS:
                raise density_error(settings, [float(source.area)*100 for source in faces],
                                    face_index=index, face_cells=accepted, total_cells=len(mapped))
    if not mapped:
        raise ValueError("No pattern cells fit inside the selected faces and border. Reduce cell size or border.")
    _check_webs(mapped, settings.web_mm)
    return (tuple(mapped),tuple(layouts)) if _return_layouts else tuple(mapped)


def _segment_distance(a, b, c, d):
    """Closest distance of finite 3D segments, including parallel endpoints."""
    u, v, w = _sub(b, a), _sub(d, c), _sub(a, c)
    aa, bb, cc, dd, ee = _dot(u, u), _dot(u, v), _dot(v, v), _dot(u, w), _dot(v, w)
    if min(aa, cc) <= 1e-14:
        raise ValueError("A projected pattern edge collapsed. Reduce pitch or change the selected region.")
    denominator = aa * cc - bb * bb
    s = max(0.0, min(1.0, (bb * ee - cc * dd) / denominator)) if denominator > 1e-14 else 0.0
    t = (bb * s + ee) / cc
    if t < 0:
        t, s = 0.0, max(0.0, min(1.0, -dd / aa))
    elif t > 1:
        t, s = 1.0, max(0.0, min(1.0, (bb - dd) / aa))
    return _length(_sub(_add(a, u, s), _add(c, v, t)))


def _check_webs(cells, web):
    for index, one in enumerate(cells):
        for two in cells[index + 1:]:
            if one.cell_key is not None and one.cell_key==two.cell_key:continue
            if _length(_sub(one.center.point_mm, two.center.point_mm)) > one.radius_mm + two.radius_mm + web + .02:
                continue
            minimum = min(_segment_distance(a, b, c, d)
                          for a, b in zip(one.world_polygon, one.world_polygon[1:] + one.world_polygon[:1])
                          for c, d in zip(two.world_polygon, two.world_polygon[1:] + two.world_polygon[:1]))
            if minimum < web - .01:
                raise ValueError("Surface distortion reduces the requested web between neighboring cells. Increase pitch/web or choose a smaller surface region.")


def _containment(body, point_mm):
    _, native = _api()
    state = body.pointContainment(_point(point_mm))
    if state == native.PointContainment.PointInsidePointContainment:
        return True
    if state == native.PointContainment.PointOutsidePointContainment:
        return False
    raise ValueError("A pattern wall witness lies on an ambiguous boundary. Change pitch or placement.")


def _ray_target_hits(design, body, origin_mm, direction):
    core, native = _api()
    points = core.ObjectCollection.create()
    found = design.rootComponent.findBRepUsingRay(_point(origin_mm), core.Vector3D.create(*direction),
        native.BRepEntityTypes.BRepFaceEntityType, hinge.POSITION_TOLERANCE_CM, False, points)
    if found is None or found.count != points.count:
        raise ValueError("Fusion could not measure the first pattern wall along its normal.")
    hits = []
    for face, point in zip(hinge._items(found), hinge._items(points)):
        if native.BRepFace.cast(face) is None or face.body != body:
            continue
        mm = tuple(value * 10 for value in hinge._xyz(point))
        distance = _dot(_sub(mm, origin_mm), direction)
        if distance > EPSILON_MM / 10:
            hits.append((distance, mm))
    return tuple(sorted(hits, key=lambda value: value[0]))


def _wall(design, body, point_mm, outward):
    direction = tuple(-value for value in outward)
    origin = _add(point_mm, direction, EPSILON_MM)
    if not _containment(body, origin):
        raise ValueError("The selected normal does not enter a stable source wall. Choose an exterior face away from thin edges.")
    hits = _ray_target_hits(design, body, origin, direction)
    if not hits:
        raise ValueError("Fusion could not find the first exit through the selected wall.")
    exit_distance, exit_point = hits[0]
    if (not _containment(body, _add(exit_point, outward, EPSILON_MM))
            or _containment(body, _add(exit_point, direction, EPSILON_MM))):
        raise ValueError("The first pattern wall exit is ambiguous; no deep cut was attempted.")
    beyond = _add(exit_point, direction, EPSILON_MM)
    next_hits = _ray_target_hits(design, body, beyond, direction)
    next_entry = math.inf
    if next_hits:
        _, entry = next_hits[0]
        if (_containment(body, _add(entry, outward, EPSILON_MM))
                or not _containment(body, _add(entry, direction, EPSILON_MM))):
            raise ValueError("The next body wall is ambiguous. Select a simpler region or reduce pitch.")
        next_entry = _dot(_sub(entry, point_mm), direction)
    return exit_distance + EPSILON_MM, next_entry


def _cell_depth(design, body, cell, settings):
    normal = cell.center.normal
    firsts, entries = [], []
    wall_distances = [] if settings.pattern=='grille_louver' else None
    center_wall = None
    for sample in cell.samples:
        distance, entry = _wall(design, body, sample.point_mm, normal)
        if wall_distances is not None:wall_distances.append(distance)
        sag = -_dot(_sub(sample.point_mm, cell.center.point_mm), normal)
        firsts.append(sag + distance)
        entries.append(sag + entry)
        if center_wall is None:
            center_wall = (distance, entry)
        if settings.mode in {"engrave", "inlay"}:
            # Plane samples have exactly the same normal: the first query
            # already measured this identical ray and its first material exit.
            local_distance = distance
            if sample.normal != normal:
                local_distance, _ = _wall(design, body, sample.point_mm, sample.normal)
            if settings.depth_mm >= local_distance - EPSILON_MM * 4:
                raise ValueError("Engrave depth reaches the first wall exit. Reduce depth or choose Through.")
    if wall_distances is not None and max(wall_distances)-min(wall_distances)>.02:
        raise ValueError('Louvers require a constant-thickness plate. Select another face.')
    margin = max(.01, EPSILON_MM * 10)
    depth = max(firsts) + margin
    if depth >= min(entries) - margin:
        raise ValueError("The first wall cannot be isolated from another wall at this cell. Reduce pitch or choose another face.")
    return depth, center_wall


def _prism_for_cell(manager, cell, inward, outward):
    frame = hinge.HingeFrame(cell.center.point_mm, cell.center.tangent_u,
                             cell.center.normal, hinge._cross(cell.center.tangent_u, cell.center.normal))
    try:
        return _solid(_direct_prism(frame, cell.polygon, -inward, outward),
                      "The projected pattern cell did not form one solid.")
    except ValueError as error:
        raise ValueError("The pattern cell could not be mapped to this surface. " + str(error)) from error


def _healthy(feature):
    _, native = _api()
    if feature.healthState != native.FeatureHealthStates.HealthyFeatureHealthState:
        raise ValueError("Fusion could not construct a clean conformal depth band. " + feature.errorOrWarningMessage)


def _band(design, face, sample, settings):
    """Copy one exact Offset/Thicken band and remove every owned history node."""
    core, native = _api()
    root = design.rootComponent
    manager = native.TemporaryBRepManager.get()
    before = (root.bRepBodies.count, design.timeline.count, design.timeline.markerPosition)
    original_bodies = hinge._items(root.bRepBodies)
    owned = []
    try:
        inputs = core.ObjectCollection.create()
        inputs.add(face)
        # Thicken accepts independent sheet faces, never faces of the source
        # solid. A zero-distance Offset supplies that sheet for engraving;
        # emboss starts slightly inside the source to retain a positive join.
        distance = -EMBED_MM if settings.mode == "emboss" else 0.0
        offset_input = root.features.offsetFeatures.createInput(inputs,
            core.ValueInput.createByReal(distance / 10), native.FeatureOperations.NewBodyFeatureOperation, False)
        if offset_input is None:
            raise ValueError("Fusion could not define the independent pattern surface.")
        _trace_geometry("band.offset.begin",mode=settings.mode,distance_mm=distance)
        offset = root.features.offsetFeatures.add(offset_input)
        if offset is None or not offset.isValid:
            raise ValueError("Fusion could not copy the selected face into a pattern surface.")
        owned.append(offset)
        _healthy(offset)
        _trace_geometry("band.offset.end",mode=settings.mode)
        # Feature.bodies also contains affected input solids. Only CREATED
        # faces on one newly owned sheet may be passed to Thicken.
        created_faces = hinge._items(offset.faces)
        sheet_faces = tuple(candidate for candidate in created_faces
            if candidate.isValid and candidate.body.isValid and not candidate.body.isSolid
            and not any(candidate.body == original for original in original_bodies))
        sheets = []
        for candidate in sheet_faces:
            if not any(candidate.body == previous for previous in sheets):
                sheets.append(candidate.body)
        if not sheet_faces or len(sheets) != 1:
            details = ["solid=" + str(bool(body.isSolid))
                + "/source=" + str(body == face.body)
                for body in hinge._items(offset.bodies) if body.isValid]
            raise ValueError("Fusion did not produce one independent pattern sheet: "
                + str(len(created_faces)) + " created face(s), bodies " + str(details) + ".")
        inputs = core.ObjectCollection.create()
        for offset_face in sheet_faces:
            inputs.add(offset_face)
        thickness = settings.depth_mm + EMBED_MM if settings.mode == "emboss" else -settings.depth_mm
        spec = root.features.thickenFeatures.createInput(inputs, core.ValueInput.createByReal(thickness / 10),
            False, native.FeatureOperations.NewBodyFeatureOperation, False)
        if spec is None:
            raise ValueError("Fusion could not define the exact surface-depth band.")
        _trace_geometry("band.thicken.begin",mode=settings.mode,thickness_mm=thickness)
        feature = root.features.thickenFeatures.add(spec)
        if feature is None or not feature.isValid:
            raise ValueError("Fusion could not thicken this face at the requested depth. Reduce depth or split the face.")
        owned.append(feature)
        _healthy(feature)
        _trace_geometry("band.thicken.end",mode=settings.mode)
        bodies = tuple(body for body in hinge._items(root.bRepBodies)
            if body.isValid and body.isSolid
            and not any(body == original for original in original_bodies))
        if len(bodies) != 1:
            raise ValueError("Fusion did not produce one independent solid depth band. Select a smaller regular face region.")
        band = _copy(manager, bodies[0])
        direction = sample.normal
        expected = settings.depth_mm / 2 if settings.mode == "emboss" else -settings.depth_mm / 2
        if not _containment(band, _add(sample.point_mm, direction, expected)):
            raise ValueError("Fusion's surface-depth band has an unexpected orientation. Reselect a regular face.")
        outside = -(EMBED_MM + .01) if settings.mode == "emboss" else settings.depth_mm / 2
        if _containment(band, _add(sample.point_mm, direction, outside)):
            raise ValueError("The conformal band extends to the wrong side of the selected face.")
        if settings.mode == "emboss" and not _containment(band, _add(sample.point_mm, direction, -EMBED_MM / 2)):
            raise ValueError("The emboss depth band does not include its attachment overlap.")
        return band
    finally:
        _trace_geometry("band.cleanup.begin",owned_features=len(owned))
        cleanup_errors = []
        for feature in reversed(owned):
            try:
                if feature.isValid and feature.deleteMe() is False:
                    cleanup_errors.append("feature deletion refused")
            except Exception as error:
                cleanup_errors.append(str(error))
        try:
            design.timeline.markerPosition = before[2]
        except Exception as error:
            cleanup_errors.append(str(error))
        if (root.bRepBodies.count, design.timeline.count, design.timeline.markerPosition) != before:
            cleanup_errors.append("temporary history/body counts did not restore")
        _trace_geometry("band.cleanup.end",errors=cleanup_errors)
        if cleanup_errors:
            raise RuntimeError("Could not clean the temporary depth band; roll back this command. " + "; ".join(cleanup_errors))


def _prepare_pattern_impl(design, faces, settings, *, _historical=False):
    """Prepare the full result, inside the caller's owned native transaction."""
    settings.validate()
    started = time.perf_counter()
    faces, body = _selection(design, faces, _historical)
    _trace_geometry("source_read.begin",face_count=len(faces))
    signature, tokens = _signature(body, faces), _tokens(body, faces)
    _trace_geometry("source_read.end",face_count=len(faces))
    _trace_geometry("mapping.begin",face_count=len(faces),layout_mode=settings.layout_mode)
    mapped, layouts = _mapped_cells(faces, settings, _return_layouts=True)
    planned = time.perf_counter()
    _trace_geometry("mapping.end",cell_count=len(mapped),
        layouts=[{"face":index,"cells":len(layout.cells),"pitch_mm":layout.effective_pitch_mm}
                 for index,layout in enumerate(layouts)],elapsed_ms=(planned-started)*1000)
    _, native = _api()
    manager = native.TemporaryBRepManager.get()
    if manager is None:
        raise ValueError("Fusion's temporary geometry manager is unavailable.")
    _trace_geometry("source_copy.begin")
    result = _copy(manager, body)
    _trace_geometry("source_copy.end")
    bands = {}
    louver_faces={}
    if settings.pattern=='grille_louver':
        from .grilles import prepare_louver_face
        for index in sorted({cell.face_index for cell in mapped}):
            louver_faces[index]=prepare_louver_face(faces[index],settings)
    if settings.mode != "through":
        for index, face in enumerate(faces):
            first = next((cell for cell in mapped if cell.face_index == index), None)
            if first is not None:
                _trace_geometry("band.begin",face_index=index,mode=settings.mode)
                bands[index] = _band(design, face, first.center, settings)
                _trace_geometry("band.end",face_index=index,mode=settings.mode)
        if _signature(body, faces) != signature:
            raise ValueError("Temporary depth-band creation changed the source. Roll back the command.")
    diagnostics = []
    recorded = {}
    through_tools = []
    colour_tools = []
    details = dict(wall_checks_ms=0.0, tool_construction_ms=0.0,
                   tool_clip_ms=0.0, result_application_ms=0.0, batch_used=False)
    if louver_faces:details['louver_face_setups']=len(louver_faces)
    _trace_geometry("tools.begin",cell_count=len(mapped),mode=settings.mode)
    for cell_index,cell in enumerate(mapped,1):
        center_wall = None
        if settings.mode in {"through", "engrave", "inlay"}:
            stage = time.perf_counter()
            _trace_geometry("tool.wall.begin",cell=cell_index,total=len(mapped),face_index=cell.face_index)
            through_depth, center_wall = _cell_depth(design, body, cell, settings)
            details['wall_checks_ms'] += (time.perf_counter()-stage)*1000
        stage = time.perf_counter()
        _trace_geometry("tool.prism.begin",cell=cell_index,total=len(mapped),face_index=cell.face_index)
        if settings.mode == "through":
            if settings.pattern=="grille_louver":
                from .grilles import louver_cutter
                cutter=louver_cutter(cell,settings,through_depth,louver_faces[cell.face_index])
            else:
                cutter = _prism_for_cell(manager, cell, through_depth,
                                          max(.02, cell.sag_mm + .02))
            details['tool_construction_ms'] += (time.perf_counter()-stage)*1000
            stage = time.perf_counter()
            _trace_geometry("tool.clip.begin",cell=cell_index,total=len(mapped),mode=settings.mode)
            _boolean(manager, cutter, body, native.BooleanTypes.IntersectionBooleanType,
                     "A through cell crossed disconnected walls or could not isolate its first wall. Reduce pitch.")
            details['tool_clip_ms'] += (time.perf_counter()-stage)*1000
            operation = native.BooleanTypes.DifferenceBooleanType
            through_tools.append(cutter)
        else:
            inward = settings.depth_mm + cell.sag_mm + cell.radius_mm + .02 if settings.mode in {"engrave", "inlay"} else EMBED_MM + cell.sag_mm + cell.radius_mm
            outward = cell.sag_mm + cell.radius_mm + settings.depth_mm + .02
            cutter = _prism_for_cell(manager, cell, inward, outward)
            details['tool_construction_ms'] += (time.perf_counter()-stage)*1000
            stage = time.perf_counter()
            _trace_geometry("tool.clip.begin",cell=cell_index,total=len(mapped),mode=settings.mode)
            _boolean(manager, cutter, bands[cell.face_index], native.BooleanTypes.IntersectionBooleanType,
                     "A cell could not isolate one conformal depth region. Reduce pitch or select another surface.")
            details['tool_clip_ms'] += (time.perf_counter()-stage)*1000
            operation = (native.BooleanTypes.UnionBooleanType if settings.mode == "emboss"
                         else native.BooleanTypes.DifferenceBooleanType)
        if settings.mode == 'inlay':
            # The band ends exactly on the source face; intersect with the
            # original solid so separate selected faces cannot add exterior material.
            _boolean(manager,cutter,body,native.BooleanTypes.IntersectionBooleanType,
                     'A flat colour region did not intersect the original wall.')
            colour_tools.append(cutter)
        if settings.mode not in {'through','inlay'}:
            stage = time.perf_counter()
            _trace_geometry("tool.apply.begin",cell=cell_index,total=len(mapped),mode=settings.mode)
            before_volume = float(result.volume)
            _boolean(manager, result, cutter, operation,
                     "The pattern split or removed the source solid. Increase web/border or reduce depth.")
            delta = float(result.volume) - before_volume
            if (settings.mode == "emboss" and delta <= 1e-10) or (settings.mode != "emboss" and delta >= -1e-10):
                raise ValueError("A pattern cell did not change material. Remove overlapping selections or adjust its placement.")
            details['result_application_ms'] += (time.perf_counter()-stage)*1000
        if recorded.get(cell.face_index, 0) < 3:
            diagnostics.append({"point_mm": cell.center.point_mm, "normal": cell.center.normal,
                "face_index": cell.face_index, "through_depth_mm": through_depth if settings.mode == "through" else None,
                "first_exit_mm": center_wall[0] if center_wall else None,
                "next_entry_mm": center_wall[1] if center_wall and math.isfinite(center_wall[1]) else None})
            recorded[cell.face_index] = recorded.get(cell.face_index, 0) + 1
        if cell_index == 1 or cell_index%25 == 0 or cell_index == len(mapped):
            _trace_geometry("tools.progress",completed=cell_index,total=len(mapped),mode=settings.mode)
    _trace_geometry("tools.end",cell_count=len(mapped),mode=settings.mode)
    if through_tools:
        stage = time.perf_counter()
        _trace_geometry("batch.begin",tool_count=len(through_tools))
        batch = try_through_difference(manager, body, through_tools, native.BooleanTypes)
        _trace_geometry("batch.end",tool_count=len(through_tools),used=batch is not None)
        if batch is not None:
            result = batch.body
            details.update(batch.timings)
            details['batch_used'] = True
        else:
            # A refused aggregate may have mutated its own copies. Resume the
            # exact per-cell path only from the original source/pristine tools.
            _trace_geometry("fallback.begin",tool_count=len(through_tools))
            result = _copy(manager, body)
            for tool_index,cutter in enumerate(through_tools,1):
                _trace_geometry("fallback.apply.begin",cell=tool_index,total=len(through_tools))
                before_volume = float(result.volume)
                _boolean(manager, result, cutter, native.BooleanTypes.DifferenceBooleanType,
                         "The pattern split or removed the source solid. Increase web/border or reduce depth.")
                if float(result.volume)-before_volume >= -1e-10:
                    raise ValueError("A pattern cell did not change material. Remove overlapping selections or adjust its placement.")
                if tool_index == 1 or tool_index%25 == 0 or tool_index == len(through_tools):
                    _trace_geometry("fallback.progress",completed=tool_index,total=len(through_tools))
            _trace_geometry("fallback.end",tool_count=len(through_tools))
        details['result_application_ms'] = (time.perf_counter()-stage)*1000
    colour = None
    if colour_tools:
        from .inlay import partition
        result,colour = partition(manager,body,colour_tools,native.BooleanTypes)
    prepared = PreparedPattern(design, faces, body, settings, result, signature,
        {"source_and_plan_ms": (planned - started) * 1000,
         "temporary_geometry_ms": (time.perf_counter() - planned) * 1000,
         "total_ms": (time.perf_counter() - started) * 1000, **details}, sum(layout.cell_count for layout in layouts), tokens,
         accepted_samples=tuple(diagnostics), layouts=layouts, colour_body=colour)
    _trace_geometry("final_validate.begin",cell_count=len(mapped))
    validate_sources(prepared, _historical=_historical)
    _trace_geometry("final_validate.end",cell_count=len(mapped))
    return prepared


def prepare_pattern(design, faces, settings, *, _historical=False):
    _trace_geometry("prepare.begin",face_count=len(faces) if isinstance(faces,(tuple,list)) else None,
        mode=getattr(settings,"mode",None),pattern=getattr(settings,"pattern",None),
        pitch_mm=getattr(settings,"pitch_mm",None),layout_mode=getattr(settings,"layout_mode",None),historical=_historical)
    try:
        prepared=_prepare_pattern_impl(design,faces,settings,_historical=_historical)
    except Exception as error:
        _trace_geometry("prepare.error",error_type=type(error).__name__,error=_trace_error(error))
        raise
    _trace_geometry("prepare.end",cell_count=prepared.cell_count,timings=prepared.timings)
    return prepared


def preview_hide_bodies(prepared):
    from . import colour_store
    from .recipe import STORE
    previous=colour_store.read(prepared.design,STORE,prepared.record) if prepared.record is not None else None
    return (prepared.body,previous[1]) if previous is not None else (prepared.body,)


def preview_pattern(prepared):
    """Draw one full opaque result; the calling session owns source visibility."""
    if prepared.record is None:
        validate_sources(prepared)
    root = prepared.design.rootComponent
    appearance = prepared.body.appearance or prepared.body.material.appearance or root.material.appearance
    if appearance is None:
        raise ValueError("Fusion could not read the source appearance for the pattern preview.")
    _trace_geometry("draw.begin",cell_count=prepared.cell_count)
    try:
        if prepared.display_mesh is None:
            group=hinge.draw_solid_preview(prepared.design, (("A", prepared.result_body),), {"A": appearance})
        else:
            group=display_export.draw(prepared.design,prepared.result_body,appearance,prepared.display_mesh)
    except Exception as error:
        _trace_geometry("draw.error",error_type=type(error).__name__,error=_trace_error(error))
        raise
    if prepared.colour_body is not None:
        try:
            if prepared.colour_mesh is None:raise ValueError("Flat colour preview mesh is missing. Refresh the preview.")
            display_export.draw(prepared.design,prepared.colour_body,appearance,prepared.colour_mesh,colour=(38,125,225),group=group)
        except Exception:
            if group.isValid:group.deleteMe()
            raise
    _trace_geometry("draw.end",cell_count=prepared.cell_count)
    return group

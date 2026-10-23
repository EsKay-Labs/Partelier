"""Fusion adapter for one exterior cantilever clasp across a straight seam.

Preparation and preview only use detached temporary solids. Create/Rebuild must
run inside the caller's Fusion command transaction and that caller must abort
on any failure. SolidPairStore integrates the exact prepared shapes into the
same two selected root bodies, preserving their identities and names.
"""

from dataclasses import dataclass, replace
import json
import math
import threading
import time

from ..hinge import fusion as hinge
from ..hinge.support import _prism
from ..hinge.visibility import validated_bodies
from ..solid_pair import SolidPairStore
from .planner import BoxBounds, build_snap_fit_plan
from .settings import SnapFitSettings
from .finish import apply_chamfers, plan_detail_chamfers, plan_receiver_chamfers


ATTRIBUTE_GROUP = "sktech_partelier_snap_fit_389f7bf1"
TOOL_ID = "snap_fit"
RECIPE_NAME = "recipe"
RECIPE_VERSION = 2
LEGACY_SETTINGS_FIELDS = frozenset({
    "width_mm", "thickness_mm", "reach_mm", "clearance_mm", "hook_depth_mm",
    "lead_in_mm", "snap_count", "start_margin_mm", "end_margin_mm", "root_length_mm",
    "attachment_overlap_mm",
})
LEGACY_STYLE_DEFAULTS = {"snap_style": "standard", "chamfer_edges": False,
                         "chamfer_size_mm": .3, "print_support": False}
SOURCE_KEYS = frozenset({"face_a", "face_b", "axis_edge", "body_a", "body_b"})
RECIPE_KEYS = frozenset({"version", "tool", "feature_id", "settings", "sources"})
STORE = SolidPairStore(ATTRIBUTE_GROUP, TOOL_ID)
POSITION_TOLERANCE_CM = hinge.POSITION_TOLERANCE_CM
POSITION_TOLERANCE_MM = POSITION_TOLERANCE_CM * 10.0
ANGLE_TOLERANCE = hinge.ANGLE_TOLERANCE


class SnapFitGeometryError(ValueError):
    """An actionable source, geometry, persistence, or ownership error."""


@dataclass(frozen=True)
class PreparedSnapFit:
    design: object
    face_a: object
    face_b: object
    axis_edge: object
    settings: SnapFitSettings
    plan: object
    frame: object
    result_bodies: tuple
    source_signature: tuple
    timings: dict
    source_tokens: dict
    history_anchor: object = None
    record: object = None
    saved_recipe: object = None


@dataclass(frozen=True)
class PreviewSources:
    design: object
    face_a: object
    face_b: object
    axis_edge: object
    settings: SnapFitSettings
    source_signature: tuple
    source_tokens: dict
    history_anchor: object = None
    record: object = None
    saved_recipe: object = None


@dataclass(frozen=True)
class EditTarget:
    anchor: object
    record: object
    settings: SnapFitSettings
    recipe: dict
    face_a: object
    face_b: object
    axis_edge: object
    feature_id: str


def _api():
    import adsk.core
    import adsk.fusion
    return adsk.core, adsk.fusion


def _main_thread():
    if threading.current_thread() is not threading.main_thread():
        raise SnapFitGeometryError("Run the snap-fit tool on Fusion's main thread.")


def _token(entity):
    value = entity.entityToken
    if not isinstance(value, str) or not 0 < len(value) <= 16384:
        raise SnapFitGeometryError("Fusion did not provide a persistent snap-fit source reference.")
    return value


def _resolve(design, token):
    found = design.findEntityByToken(token)
    if found is None or len(found) != 1 or not hinge._valid(found[0]):
        raise SnapFitGeometryError("A saved snap-fit source is missing or split. Reselect the geometry.")
    return found[0]


def _source_tokens(face_a, face_b, edge):
    return {"face_a": _token(face_a), "face_b": _token(face_b), "axis_edge": _token(edge),
            "body_a": _token(face_a.body), "body_b": _token(face_b.body)}


def _sources(design, tokens, targets=None):
    _, fusion = _api()
    values = {key: _resolve(design, token) for key, token in tokens.items()}
    a = fusion.BRepFace.cast(values["face_a"])
    b = fusion.BRepFace.cast(values["face_b"])
    edge = fusion.BRepEdge.cast(values["axis_edge"])
    if (a is None or b is None or edge is None
            or a.body != values["body_a"] or b.body != values["body_b"]
            or (targets is not None and (a.body, b.body) != tuple(targets))):
        raise SnapFitGeometryError("The saved snap-fit faces no longer match their original bodies.")
    return a, b, edge


def _canonical_rim(face_a, face_b, selected):
    """Accept either facing rim across a gap; always persist A's real edge.

    Matching needs the same complete projected span, coplanar outside walls,
    and all face vertices on their respective sides of the seam. A distant,
    partial, diagonal, unrelated or ambiguous edge cannot choose a new origin.
    """
    try:
        return hinge._canonical_axis_edge(face_a, face_b, selected)
    except hinge.HingeGeometryError:
        pass
    if (selected.assemblyContext is not None or selected.body != face_b.body
            or not any(selected == edge for edge in hinge._items(face_b.edges))):
        raise SnapFitGeometryError("Pick the facing rim on wall A or B. The edge must bound the selected wall, not another face or body.")
    chosen = hinge._straight_endpoints(selected)
    if chosen is None:
        raise SnapFitGeometryError("Pick a complete straight rim on the selected outside wall.")
    normal = hinge._plane_normal(face_a)
    if hinge._dot(normal, hinge._plane_normal(face_b)) < 1 - ANGLE_TOLERANCE:
        raise SnapFitGeometryError("The outside wall faces must have matching outward normals.")
    plane_point = hinge._xyz(face_a.pointOnFace)
    if any(abs(hinge._dot(hinge._subtract(point, plane_point), normal)) > POSITION_TOLERANCE_CM
           for point in chosen):
        raise SnapFitGeometryError("Pick the rim in the same plane as the selected outside walls.")
    matches = []
    for edge in hinge._items(face_a.edges):
        points = hinge._straight_endpoints(edge)
        if points is None:
            continue
        axis = hinge._unit(hinge._subtract(points[1], points[0]))
        direction = hinge._unit(hinge._subtract(chosen[1], chosen[0]))
        if abs(hinge._dot(axis, direction)) < 1 - ANGLE_TOLERANCE:
            continue
        span_a = sorted(hinge._dot(point, axis) for point in points)
        span_b = sorted(hinge._dot(point, axis) for point in chosen)
        if any(abs(one-two) > POSITION_TOLERANCE_CM for one,two in zip(span_a,span_b)):
            continue
        across = hinge._unit(hinge._cross(normal, axis))
        origin = tuple((one+two)/2 for one,two in zip(*points))
        toward = hinge._dot(hinge._subtract(hinge._xyz(face_b.pointOnFace),origin),across)
        if abs(toward) <= POSITION_TOLERANCE_CM:
            continue
        if toward < 0:
            across = tuple(-value for value in across)
        gap = hinge._dot(hinge._subtract(chosen[0],origin),across)
        if gap < -POSITION_TOLERANCE_CM:
            continue
        # Only the facing boundaries qualify, not the far edge of either wall.
        if any(hinge._dot(hinge._subtract(hinge._xyz(vertex.geometry),origin),across)
               > POSITION_TOLERANCE_CM for vertex in hinge._items(face_a.vertices)):
            continue
        if any(hinge._dot(hinge._subtract(hinge._xyz(vertex.geometry),chosen[0]),across)
               < -POSITION_TOLERANCE_CM for vertex in hinge._items(face_b.vertices)):
            continue
        matches.append(edge)
    if len(matches) != 1:
        raise SnapFitGeometryError("The two facing rims must have the same complete span. Pick A's rim directly; offset, partial or ambiguous rim matches are not supported.")
    return matches[0]


def _selection(design, face_a, face_b, edge, *, historical=False):
    _main_thread()
    _, fusion = _api()
    if not hinge._valid(design) or design.designType != fusion.DesignTypes.ParametricDesignType:
        raise SnapFitGeometryError("Use a parametric Design document with history enabled.")
    root = design.rootComponent
    if design.activeComponent != root:
        raise SnapFitGeometryError("Activate the root component before making a snap-fit.")
    if not historical and design.timeline.markerPosition != design.timeline.count:
        raise SnapFitGeometryError("Move the history marker to the end before making a snap-fit.")
    faces = (fusion.BRepFace.cast(face_a), fusion.BRepFace.cast(face_b))
    edge = fusion.BRepEdge.cast(edge)
    if not all(hinge._valid(face) for face in faces) or not hinge._valid(edge):
        raise SnapFitGeometryError("Select two planar outside wall faces and a straight rim edge on face A.")
    face_a, face_b = faces
    for face in faces:
        body = face.body
        if (face.assemblyContext is not None or body.assemblyContext is not None
                or body.parentComponent != root or body.isTemporary
                or not body.isSolid or body.lumps.count != 1
                or not math.isfinite(float(body.volume)) or body.volume <= 0):
            raise SnapFitGeometryError("Select faces on two solid native bodies in the root component.")
    if face_a.body == face_b.body:
        raise SnapFitGeometryError("Select faces on two different solid bodies.")
    try:
        edge = _canonical_rim(face_a, face_b, edge)
        endpoints = hinge._straight_endpoints(edge)
        x_axis = hinge._plane_normal(face_a)
        b_normal = hinge._plane_normal(face_b)
    except hinge.HingeGeometryError as error:
        raise SnapFitGeometryError(str(error)) from error
    if endpoints is None:
        raise SnapFitGeometryError("Select a straight finite rim edge on face A.")
    if hinge._dot(x_axis, b_normal) < 1 - ANGLE_TOLERANCE:
        raise SnapFitGeometryError("The outside wall faces must have matching outward normals.")
    delta_plane = hinge._subtract(hinge._xyz(face_b.pointOnFace), hinge._xyz(face_a.pointOnFace))
    if abs(hinge._dot(delta_plane, x_axis)) > POSITION_TOLERANCE_CM:
        raise SnapFitGeometryError("The selected outside wall faces must lie in the same plane.")
    start, end = endpoints
    y_axis = hinge._unit(hinge._subtract(end, start))
    if abs(hinge._dot(x_axis, y_axis)) > ANGLE_TOLERANCE:
        raise SnapFitGeometryError("The rim edge must lie in the selected outside wall plane.")
    midpoint = tuple(a / 2.0 + b / 2.0 for a, b in zip(start, end))
    z_axis = hinge._unit(hinge._cross(x_axis, y_axis))
    toward_b = hinge._dot(hinge._subtract(hinge._xyz(face_b.pointOnFace), midpoint), z_axis)
    if abs(toward_b) <= POSITION_TOLERANCE_CM:
        raise SnapFitGeometryError("Face B must lie clearly across the rim from face A.")
    if toward_b < 0:
        y_axis = tuple(-value for value in y_axis)
        z_axis = tuple(-value for value in z_axis)
    toward_a = hinge._dot(hinge._subtract(hinge._xyz(face_a.pointOnFace), midpoint), z_axis)
    if toward_a >= -POSITION_TOLERANCE_CM:
        raise SnapFitGeometryError("Choose A's rim between the lower hook wall A and upper receiving wall B.")
    frame = hinge.HingeFrame(tuple(value * 10 for value in midpoint), x_axis, y_axis, z_axis)
    length_mm = math.sqrt(hinge._dot(hinge._subtract(end, start), hinge._subtract(end, start))) * 10
    if not math.isfinite(length_mm) or length_mm <= POSITION_TOLERANCE_MM:
        raise SnapFitGeometryError("The selected rim has no usable finite length.")
    signature = (hinge._body_signature(face_a.body), hinge._body_signature(face_b.body),
                 tuple(round(value, 8) for value in start + end),
                 tuple(round(value, 8) for value in x_axis),
                 round(float(face_a.area), 8), round(float(face_b.area), 8))
    return face_a, face_b, edge, frame, signature, length_mm


def _solid(body, message):
    if (body is None or not hinge._valid(body) or not body.isSolid or body.lumps.count != 1
            or not math.isfinite(float(body.volume)) or body.volume <= 0):
        raise SnapFitGeometryError(message)
    return body


def _copy(manager, body):
    return _solid(manager.copy(body), "Fusion could not copy a snap-fit source or checking solid.")


def _boolean(manager, target, tool, operation, message):
    if not manager.booleanOperation(target, tool, operation):
        raise SnapFitGeometryError(message)
    return _solid(target, message)


def _local_bounds(manager, frame, body):
    """Transform a detached solid, so rotated world boxes cannot distort limits."""
    core, _ = _api()
    matrix = core.Matrix3D.create()
    if matrix.setWithCoordinateSystem(core.Point3D.create(*(value / 10 for value in frame.origin_mm)),
                                      core.Vector3D.create(*frame.x_axis),
                                      core.Vector3D.create(*frame.y_axis),
                                      core.Vector3D.create(*frame.z_axis)) is False or not matrix.invert():
        raise SnapFitGeometryError("Fusion could not inspect the local snap-fit attachment region.")
    local = _copy(manager, body)
    if not manager.transform(local, matrix):
        raise SnapFitGeometryError("Fusion could not orient the attachment-region check.")
    bounds = local.boundingBox
    minimum = tuple(value * 10 for value in hinge._xyz(bounds.minPoint))
    maximum = tuple(value * 10 for value in hinge._xyz(bounds.maxPoint))
    if not all(math.isfinite(value) for value in minimum + maximum):
        raise SnapFitGeometryError("The selected solid has invalid local bounds.")
    return minimum, maximum


def _halfspaces(manager, frame, a, b):
    a_min, a_max = _local_bounds(manager, frame, a)
    b_min, b_max = _local_bounds(manager, frame, b)
    if a_max[0] > POSITION_TOLERANCE_MM or b_max[0] > POSITION_TOLERANCE_MM:
        raise SnapFitGeometryError("Both selected walls must keep all their material behind the outside wall plane.")
    # Internal tongue/groove lips may cross the exterior seam. Exact root/
    # recess coverage and a checked difference of the final pair establish fit;
    # a whole-body Z box would incorrectly refuse such ordinary lid geometry.


def _coverage(manager, frame, source, bounds, message):
    _, fusion = _api()
    check = hinge._box(manager, frame, bounds)
    expected = float(check.volume)
    _boolean(manager, check, source, fusion.BooleanTypes.IntersectionBooleanType, message)
    if abs(float(check.volume) - expected) > max(1e-9, expected * 1e-7):
        raise SnapFitGeometryError(message)


def _no_positive_overlap(manager, a, b):
    """Prove no material is lost by subtracting B from a detached copy of A.

    An empty intersection may report a failed boolean, which is ambiguous.
    Difference must succeed and preserve the complete volume; kernel failures
    are refused. This supports touching seams and interlocking source lips.
    """
    _, fusion = _api()
    witness = _copy(manager, a)
    before = float(witness.volume)
    if not manager.booleanOperation(witness, b, fusion.BooleanTypes.DifferenceBooleanType):
        raise SnapFitGeometryError("Fusion could not verify snap-fit clearance. No geometry was changed.")
    if not hinge._valid(witness) or not witness.isSolid:
        raise SnapFitGeometryError("The snap-fit halves overlap. Adjust the rim, walls or clearances.")
    after = float(witness.volume)
    if not math.isfinite(after) or abs(before-after) > max(1e-9, before*1e-8):
        raise SnapFitGeometryError("The snap-fit halves overlap. Check the selected rim, walls and clearances.")


def prepare_snap_fit(design, face_a, face_b, axis_edge, settings, *, _historical=False):
    """Read bounded sources, then construct two exact temporary final solids."""
    _main_thread()
    if not isinstance(settings, SnapFitSettings):
        raise SnapFitGeometryError("Use validated snap-fit settings.")
    settings.validate()
    started = time.perf_counter()
    face_a, face_b, axis_edge, frame, signature, span = _selection(
        design, face_a, face_b, axis_edge, historical=_historical)
    tokens = _source_tokens(face_a, face_b, axis_edge)
    read_done = time.perf_counter()
    plan = build_snap_fit_plan(settings, span)
    planned = time.perf_counter()
    _, fusion = _api()
    manager = fusion.TemporaryBRepManager.get()
    if manager is None:
        raise SnapFitGeometryError("Fusion's temporary solid manager is unavailable.")
    _halfspaces(manager, frame, face_a.body, face_b.body)
    results = {"A": _copy(manager, face_a.body), "B": _copy(manager, face_b.body)}
    for unit in plan.units:
        _coverage(manager, frame, face_a.body, unit.root_cover,
                  "Face A must contain the full root width, length and attachment overlap. Move the rim or reduce those dimensions.")
        root = hinge._box(manager, frame, unit.root)
        if unit.root_support is not None:
            support = unit.root_support
            _boolean(manager, root, _prism(manager, frame, support.points_xz_mm,
                                           support.y_min_mm, support.y_max_mm),
                     fusion.BooleanTypes.UnionBooleanType,
                     "The 45-degree root ramp did not join its root into one solid.")
        for arm in unit.arms:
            _coverage(manager, frame, face_b.body, arm.receiver_cover,
                      "Face B must contain the full blind recess and roof plus remaining wall. Increase wall thickness/height or reduce reach, hook depth or clearance.")
            beam = _prism(manager, frame, arm.beam.points_xz_mm, arm.beam.y_min_mm, arm.beam.y_max_mm)
            hook = _prism(manager, frame, arm.hook.points_xz_mm, arm.hook.y_min_mm, arm.hook.y_max_mm)
            _no_positive_overlap(manager, hook, face_a.body)
            for part in (beam, hook):
                _boolean(manager, root, part, fusion.BooleanTypes.UnionBooleanType,
                         "The cantilever root, beam and hook did not join into one solid.")
        apply_chamfers(manager, frame, root, plan_detail_chamfers(unit, settings))
        _boolean(manager, results["A"], root, fusion.BooleanTypes.UnionBooleanType,
                 "The snap-fit root did not join into body A.")
        for arm in unit.arms:
            pocket = arm.receiver
            _boolean(manager, results["B"], _prism(manager, frame, pocket.points_xz_mm,
                                                   pocket.y_min_mm, pocket.y_max_mm),
                     fusion.BooleanTypes.DifferenceBooleanType,
                     "The receiving recess removed or split body B. Reduce its dimensions.")
            apply_chamfers(manager, frame, results["B"], plan_receiver_chamfers(arm, settings))
    _no_positive_overlap(manager, results["A"], results["B"])
    ended = time.perf_counter()
    return PreparedSnapFit(design, face_a, face_b, axis_edge, settings, plan, frame,
                           tuple(results.items()), signature,
                           {"source_read_ms": (read_done - started) * 1000,
                            "planning_ms": (planned - read_done) * 1000,
                            "temporary_geometry_ms": (ended - planned) * 1000}, tokens)


def _parse_recipe(raw, record):
    if not isinstance(raw, str) or len(raw) > 131072:
        raise SnapFitGeometryError("The saved snap-fit recipe is missing or too large.")
    try:
        recipe = json.loads(raw)
    except (ValueError, TypeError) as error:
        raise SnapFitGeometryError("The saved snap-fit recipe is damaged.") from error
    if (not isinstance(recipe, dict) or set(recipe) != RECIPE_KEYS
            or type(recipe["version"]) is not int or recipe["version"] not in (1, RECIPE_VERSION)
            or recipe["tool"] != TOOL_ID or recipe["feature_id"] != record.feature_id
            or not isinstance(recipe["sources"], dict) or set(recipe["sources"]) != SOURCE_KEYS
            or not all(isinstance(value, str) and 0 < len(value) <= 16384
                       for value in recipe["sources"].values())
            or len(set(recipe["sources"].values())) != len(SOURCE_KEYS)):
        raise SnapFitGeometryError("The saved snap-fit recipe has an unsupported or damaged structure.")
    try:
        values = recipe["settings"]
        if recipe["version"] == 1:
            if not isinstance(values, dict) or set(values) != LEGACY_SETTINGS_FIELDS:
                raise ValueError("Version 1 must contain exactly its original eleven dimension fields.")
            values = {**values, **LEGACY_STYLE_DEFAULTS}
        settings = SnapFitSettings.from_dict(values)
    except (ValueError, TypeError) as error:
        raise SnapFitGeometryError("The saved snap-fit settings are damaged: " + str(error)) from error
    return recipe, settings


def _read_recipe(anchor, record):
    tag = anchor.attributes.itemByName(ATTRIBUTE_GROUP, RECIPE_NAME)
    if tag is None:
        raise SnapFitGeometryError("The saved snap-fit recipe is missing.")
    return _parse_recipe(tag.value, record)


def read_edit_target(design, selected_entity):
    _main_thread()
    record = STORE.read(design, selected_entity)
    recipe, settings = _read_recipe(record.anchor, record)
    with STORE.input_scope(design, record) as targets:
        face_a, face_b, edge = _sources(design, recipe["sources"], targets)
    return EditTarget(record.anchor, record, settings, recipe, face_a, face_b, edge, record.feature_id)


def prepare_edit_snap_fit(design, target, settings):
    _main_thread()
    if not isinstance(target, EditTarget):
        raise SnapFitGeometryError("Reopen Edit to load this snap-fit.")
    if _read_recipe(target.anchor, target.record)[0] != target.recipe:
        raise SnapFitGeometryError("The saved snap-fit settings changed. Reopen Edit.")
    with STORE.input_scope(design, target.record) as targets:
        faces = _sources(design, target.recipe["sources"], targets)
        prepared = prepare_snap_fit(design, *faces, settings, _historical=True)
    return replace(prepared, history_anchor=target.anchor, record=target.record,
                   source_tokens=dict(target.recipe["sources"]), saved_recipe=dict(target.recipe))


def _assert_fresh(design, prepared):
    _main_thread()
    if design != prepared.design:
        raise SnapFitGeometryError("The active design changed. Reselect the snap-fit sources.")
    if prepared.record is None:
        values = _selection(design, prepared.face_a, prepared.face_b, prepared.axis_edge)
    else:
        if _read_recipe(prepared.history_anchor, prepared.record)[0] != prepared.saved_recipe:
            raise SnapFitGeometryError("The saved snap-fit settings changed. Reopen Edit.")
        with STORE.input_scope(design, prepared.record) as targets:
            faces = _sources(design, prepared.source_tokens, targets)
            values = _selection(design, *faces, historical=True)
    if ((prepared.record is None and values[2] != prepared.axis_edge)
            or values[4] != prepared.source_signature):
        raise SnapFitGeometryError("The source geometry changed. Refresh the snap-fit preview.")


def capture_preview_sources(prepared):
    return PreviewSources(prepared.design, prepared.face_a, prepared.face_b, prepared.axis_edge,
                          prepared.settings, prepared.source_signature, dict(prepared.source_tokens),
                          prepared.history_anchor, prepared.record, prepared.saved_recipe)


def validate_preview_sources(design, sources):
    """Read-only freshness check, with no temporary geometry regeneration."""
    _assert_fresh(design, sources)


def _targets(prepared):
    bodies = tuple(_resolve(prepared.design, prepared.source_tokens["body_" + role]) for role in ("a", "b"))
    return validated_bodies(bodies)


def preview_hide_bodies(prepared, target=None):
    _main_thread()
    if target is not None and (prepared.record is None or target.record != prepared.record):
        raise SnapFitGeometryError("The preview no longer belongs to the selected snap-fit. Reopen Edit.")
    return _targets(prepared)


def preview_snap_fit(prepared):
    _assert_fresh(prepared.design, prepared)
    fallback = prepared.design.rootComponent.material.appearance
    appearances = {}
    for role, body in zip(("A", "B"), _targets(prepared)):
        appearances[role] = body.appearance or body.material.appearance or fallback
    if any(value is None for value in appearances.values()):
        raise SnapFitGeometryError("Fusion could not read the source appearances for the snap-fit preview.")
    return hinge.draw_solid_preview(prepared.design, prepared.result_bodies, appearances)


def _finals(prepared):
    if tuple(role for role, _ in prepared.result_bodies) != ("A", "B"):
        raise SnapFitGeometryError("The prepared snap-fit must have exactly two owned final shapes.")
    return tuple(_solid(body, "A generated snap-fit result is not one solid.")
                 for _, body in prepared.result_bodies)


def _save_recipe(anchor, record, settings, sources):
    recipe = {"version": RECIPE_VERSION, "tool": TOOL_ID, "feature_id": record.feature_id,
              "settings": settings.to_dict(), "sources": dict(sources)}
    raw = json.dumps(recipe, separators=(",", ":"))
    # Validate the exact snapshot before its only tool-specific attribute write.
    _parse_recipe(raw, record)
    if anchor.attributes.add(ATTRIBUTE_GROUP, RECIPE_NAME, raw) is None:
        raise SnapFitGeometryError("Fusion could not save the snap-fit dimensions. The command must roll back.")


def create_snap_fit(design, prepared):
    """Caller owns/aborts the native transaction; selected bodies stay in place."""
    _assert_fresh(design, prepared)
    if prepared.record is not None:
        raise SnapFitGeometryError("Use Rebuild for an existing snap-fit.")
    anchor = STORE.create(design, _targets(prepared), _finals(prepared))
    record = STORE.read(design, anchor)
    _save_recipe(anchor, record, prepared.settings, prepared.source_tokens)
    return anchor


def rebuild_snap_fit(design, target, prepared):
    """Update the existing two native tool shapes without accumulating bodies."""
    _assert_fresh(design, prepared)
    if (not isinstance(target, EditTarget) or prepared.record != target.record
            or prepared.history_anchor != target.anchor
            or prepared.source_tokens != target.recipe["sources"]):
        raise SnapFitGeometryError("The prepared result no longer matches the saved snap-fit. Reopen Edit.")
    anchor = STORE.update(design, target.record, _finals(prepared))
    current = STORE.read(design, anchor)
    _save_recipe(anchor, current, prepared.settings, prepared.source_tokens)
    return anchor

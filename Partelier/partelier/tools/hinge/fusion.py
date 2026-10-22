"""Fusion adapter for the deliberately bounded, separate-pin hinge.

All model access stays on Fusion's main thread. Preparation uses transient BRep
only; preview owns a custom-graphics group. Attached persistence modifies the selected root bodies using native Combines;
separate output uses an owned BaseFeature in the Part root or Hybrid component. This module imports adsk lazily so its contracts can be
checked outside Fusion. Native geometry behaviour still requires host checks.
"""

from dataclasses import dataclass, replace
import hashlib
import json
import math
import threading
import time
import uuid

from .planner import WebBounds, build_hinge_plan
from .layout import build_hinge_layout
from .settings import HingeSettings
from .seam import plan_seam_clearance
from .finish import box_chamfer_wedges
from .rounding import rounded_box, rounded_axis_body, round_bore_entry
from .support import make_tangent_support
from .relief import cut_rotation_relief
from .visibility import validated_bodies


ATTRIBUTE_GROUP = "sktech_partelier_hinge_8c319ce2"
# Read pre-rename results without mutating their saved ownership on inspection.
LEGACY_ATTRIBUTE_GROUP = "sktech_veyra_hinge_8c319ce2"
RECIPE_NAME = "recipe"
OWNER_NAME = "owner"
RECIPE_VERSION = 8
LEGACY_SETTINGS_FIELDS = frozenset({
    "length_mm", "knuckle_count", "barrel_diameter_mm", "pin_diameter_mm",
    "diametral_clearance_mm", "axial_gap_mm", "leaf_reach_mm", "leaf_thickness_mm",
    "attachment_overlap_mm", "pin_overhang_mm", "axis_offset_mm", "include_pin",
})
VERSION_TWO_SETTINGS_FIELDS = LEGACY_SETTINGS_FIELDS | {"split_seam", "seam_clearance_mm"}
LAYOUT_DEFAULTS = {"hinge_count": 1, "start_margin_mm": 0.0, "end_margin_mm": 0.0}
VERSION_THREE_SETTINGS_FIELDS = VERSION_TWO_SETTINGS_FIELDS | LAYOUT_DEFAULTS.keys()
LEAF_DEFAULTS = {"output_mode": "attached", "leaf_profile": "rectangular",
                 "leaf_barrel_clearance_mm": 0.3, "screw_holes": False,
                 "screw_diameter_mm": 3.2, "screw_end_margin_mm": 6.0}
VERSION_FOUR_SETTINGS_FIELDS = VERSION_THREE_SETTINGS_FIELDS | LEAF_DEFAULTS.keys()
FINISH_DEFAULTS = {"chamfer_edges": False, "chamfer_size_mm": 0.3}
VERSION_FIVE_SETTINGS_FIELDS = VERSION_FOUR_SETTINGS_FIELDS | FINISH_DEFAULTS.keys()
STYLE_DEFAULTS = {"knuckle_profile": "round", "fillet_edges": False, "fillet_radius_mm": 0.6}
VERSION_SIX_SETTINGS_FIELDS = VERSION_FIVE_SETTINGS_FIELDS | STYLE_DEFAULTS.keys()
SUPPORT_DEFAULTS = {"web_profile": "flat"}
VERSION_SEVEN_SETTINGS_FIELDS = VERSION_SIX_SETTINGS_FIELDS | SUPPORT_DEFAULTS.keys()
RELIEF_DEFAULTS = {"rotation_clearance_mm": 0.0}
TOOL_ID = "pin_hinge"
POSITION_TOLERANCE_CM = 0.00001
PREVIEW_EDGE_TOLERANCE_CM = 0.0005  # 0.005 mm, display strokes only.
ANGLE_TOLERANCE = 0.000001


class HingeGeometryError(ValueError):
    """An actionable selection, geometry, ownership or persistence error."""


@dataclass(frozen=True)
class HingeFrame:
    """World-space origin in mm and three unit direction tuples."""

    origin_mm: tuple
    x_axis: tuple
    y_axis: tuple
    z_axis: tuple

    def point_mm(self, x, y, z):
        return tuple(
            self.origin_mm[index] + x * self.x_axis[index]
            + y * self.y_axis[index] + z * self.z_axis[index]
            for index in range(3)
        )


@dataclass(frozen=True)
class PreparedHinge:
    design: object
    face_a: object
    face_b: object
    axis_edge: object
    settings: HingeSettings
    plan: object
    frame: HingeFrame
    result_bodies: tuple
    preview_bodies: tuple
    source_signature: tuple
    timings: dict
    layout: object = None
    history_anchor: object = None
    source_tokens: object = None


@dataclass(frozen=True)
class PreviewSources:
    """Only source references/signature; never retain generated temporary solids."""

    design: object
    face_a: object
    face_b: object
    axis_edge: object
    settings: HingeSettings
    source_signature: tuple
    history_anchor: object = None
    source_tokens: object = None


def capture_preview_sources(prepared):
    return PreviewSources(prepared.design, prepared.face_a, prepared.face_b,
                          prepared.axis_edge, prepared.settings, prepared.source_signature,
                          getattr(prepared, "history_anchor", None), getattr(prepared, "source_tokens", None))


def validate_preview_sources(design, sources):
    """Read-only source freshness check after a host command; no geometry rebuild."""
    _require_main_thread()
    _assert_fresh(design, sources)


@dataclass(frozen=True)
class EditTarget:
    component: object
    occurrence: object
    settings: HingeSettings
    face_a: object
    face_b: object
    axis_edge: object
    feature_id: str
    recipe: dict
    anchor: object = None


def _api():
    import adsk.core
    import adsk.fusion

    return adsk.core, adsk.fusion


def _require_main_thread():
    if threading.current_thread() is not threading.main_thread():
        raise HingeGeometryError("Run the hinge command on Fusion's main thread.")


def _xyz(value):
    return (float(value.x), float(value.y), float(value.z))


def _subtract(one, two):
    return tuple(a - b for a, b in zip(one, two))


def _dot(one, two):
    return sum(a * b for a, b in zip(one, two))


def _cross(one, two):
    return (one[1] * two[2] - one[2] * two[1],
            one[2] * two[0] - one[0] * two[2],
            one[0] * two[1] - one[1] * two[0])


def _unit(value):
    length = math.sqrt(_dot(value, value))
    if not math.isfinite(length) or length <= POSITION_TOLERANCE_CM:
        raise HingeGeometryError("The selected edge has no usable direction.")
    return tuple(coordinate / length for coordinate in value)


def _items(collection):
    return tuple(collection.item(index) for index in range(collection.count))


def _valid(entity):
    return entity is not None and entity.isValid


def _plane_normal(face):
    core, _ = _api()
    plane = core.Plane.cast(face.geometry)
    if plane is None:
        raise HingeGeometryError("Select planar faces; curved faces are not supported yet.")
    normal = _xyz(plane.normal)
    if face.isParamReversed:
        normal = tuple(-value for value in normal)
    return _unit(normal)



def _straight_endpoints(edge):
    """Return the bounded line segment, never an unbounded support line."""
    core, _ = _api()
    if (not _valid(edge) or core.Line3D.cast(edge.geometry) is None
            or not edge.startVertex or not edge.endVertex):
        return None
    endpoints = (_xyz(edge.startVertex.geometry), _xyz(edge.endVertex.geometry))
    if not all(math.isfinite(value) for endpoint in endpoints for value in endpoint):
        return None
    delta = _subtract(endpoints[1], endpoints[0])
    if _dot(delta, delta) <= POSITION_TOLERANCE_CM ** 2:
        return None
    return endpoints


def _same_segment(one, two):
    def near(first, second):
        delta = _subtract(first, second)
        return _dot(delta, delta) <= POSITION_TOLERANCE_CM ** 2

    return ((near(one[0], two[0]) and near(one[1], two[1]))
            or (near(one[0], two[1]) and near(one[1], two[0])))


def _coincident_face_edges(face, reference):
    """Find complete native boundary matches, not partial collinear segments."""
    endpoints = _straight_endpoints(reference)
    if endpoints is None:
        return ()
    matches = []
    for candidate in _items(face.edges):
        if candidate.assemblyContext is not None or candidate.body != face.body:
            continue
        bounds = _straight_endpoints(candidate)
        if bounds is not None and _same_segment(endpoints, bounds):
            matches.append(candidate)
    return tuple(matches)


def _canonical_axis_edge(face_a, face_b, selected):
    """Resolve coincident picks to A's topology before saving source identity.

    Split touching solids have distinct, overlapping boundary edges. Fusion may
    return B's edge for the same visible line. Only a complete coincident segment
    from the two selected native bodies can stand in for A's boundary; unrelated
    bodies, offset/partial collinear segments and ambiguous matches are refused.
    """
    if (selected.assemblyContext is not None
            or selected.body not in (face_a.body, face_b.body)):
        raise HingeGeometryError(
            "Select the shared boundary of face A, or its coincident edge on body B.")
    endpoints = _straight_endpoints(selected)
    if endpoints is None:
        raise HingeGeometryError("Select a straight, finite boundary edge on face A.")
    matches = []
    for candidate in _items(face_a.edges):
        if (candidate.assemblyContext is not None or candidate.body != face_a.body):
            continue
        bounds = _straight_endpoints(candidate)
        if bounds is not None and _same_segment(endpoints, bounds):
            matches.append(candidate)
    if not matches:
        raise HingeGeometryError(
            "The reference must match a complete straight boundary edge of face A. "
            "Select that edge directly, or the coincident edge on body B.")
    if len(matches) != 1:
        raise HingeGeometryError(
            "The reference matches multiple edges of face A. Choose an unambiguous boundary.")
    return matches[0]


def _selection(design, face_a, face_b, edge, settings, *, historical=False):
    core, fusion = _api()
    if not _valid(design) or design.designType != fusion.DesignTypes.ParametricDesignType:
        raise HingeGeometryError("Use a Fusion Design with Capture Design History enabled.")
    root = design.rootComponent
    if design.activeComponent != root:
        raise HingeGeometryError("Activate the root component before making a hinge.")
    if not historical and design.timeline.markerPosition != design.timeline.count:
        raise HingeGeometryError("Move the timeline marker to the end before making a hinge.")
    faces = (fusion.BRepFace.cast(face_a), fusion.BRepFace.cast(face_b))
    edge = fusion.BRepEdge.cast(edge)
    if not all(_valid(face) for face in faces) or not _valid(edge):
        raise HingeGeometryError("Select two valid planar faces and one straight edge on face A.")
    face_a, face_b = faces
    for face in faces:
        body = face.body
        if face.assemblyContext is not None or body.assemblyContext is not None:
            raise HingeGeometryError("Select native bodies in the root component, not occurrences.")
        if body.parentComponent != root or not body.isSolid or body.lumps.count != 1:
            raise HingeGeometryError("Each selected face must belong to one solid root-component body.")
    if face_a.body == face_b.body:
        raise HingeGeometryError("Select faces on two different solid bodies.")
    edge = _canonical_axis_edge(face_a, face_b, edge)
    start, end = _straight_endpoints(edge)
    edge_length_cm = math.sqrt(_dot(_subtract(end, start), _subtract(end, start)))
    if settings.length_mm / 10 > edge_length_cm + POSITION_TOLERANCE_CM:
        raise HingeGeometryError("Hinge length must fit within the selected straight edge.")
    z_axis = _plane_normal(face_a)
    if _dot(z_axis, _plane_normal(face_b)) < 1 - ANGLE_TOLERANCE:
        raise HingeGeometryError("Select faces with matching outward normals.")
    plane_delta = _subtract(_xyz(face_b.pointOnFace), _xyz(face_a.pointOnFace))
    if abs(_dot(plane_delta, z_axis)) > POSITION_TOLERANCE_CM:
        raise HingeGeometryError("The selected faces must lie in the same plane.")
    y_axis = _unit(_subtract(end, start))
    if abs(_dot(y_axis, z_axis)) > ANGLE_TOLERANCE:
        raise HingeGeometryError("The reference edge must lie in the selected face plane.")
    midpoint = tuple((a + b) / 2 for a, b in zip(start, end))
    x_axis = _unit(_cross(y_axis, z_axis))
    toward_b = _dot(_subtract(_xyz(face_b.pointOnFace), midpoint), x_axis)
    if abs(toward_b) <= POSITION_TOLERANCE_CM:
        raise HingeGeometryError("Face B must be clearly across the reference edge from face A.")
    if toward_b < 0:
        x_axis = tuple(-value for value in x_axis)
        y_axis = tuple(-value for value in y_axis)
    # The edge midpoint is in cm; this is the entry boundary to a pure mm frame.
    effective_offset_mm = 0.0 if settings.split_seam else settings.axis_offset_mm
    origin_mm = tuple(midpoint[index] * 10 + x_axis[index] * effective_offset_mm
                      for index in range(3))
    frame = HingeFrame(origin_mm, x_axis, y_axis, z_axis)
    signature = (_body_signature(face_a.body), _body_signature(face_b.body),
                 tuple(round(value, 8) for value in start + end),
                 tuple(round(value, 8) for value in z_axis),
                 round(float(face_a.area), 8), round(float(face_b.area), 8))
    return frame, signature, edge


def _body_signature(body):
    """Conservative edit guard; not a general geometric-equivalence proof."""
    bounds = body.boundingBox
    vertices = sorted(tuple(round(value, 8) for value in _xyz(vertex.geometry))
                      for vertex in _items(body.vertices))
    data = (body.faces.count, body.edges.count, body.lumps.count,
            round(float(body.volume), 8),
            tuple(round(value, 8) for value in _xyz(bounds.minPoint)),
            tuple(round(value, 8) for value in _xyz(bounds.maxPoint)),
            vertices)
    return hashlib.sha256(json.dumps(data, separators=(",", ":")).encode("utf-8")).hexdigest()


def _point(frame, x, y, z):
    core, _ = _api()
    # The single exit boundary from planner mm to Fusion cm.
    return core.Point3D.create(*(value / 10 for value in frame.point_mm(x, y, z)))


def _box(manager, frame, web):
    core, _ = _api()
    center = _point(frame, (web.x_min_mm + web.x_max_mm) / 2,
                    (web.y_min_mm + web.y_max_mm) / 2,
                    (web.z_min_mm + web.z_max_mm) / 2)
    bounds = core.OrientedBoundingBox3D.create(
        center, core.Vector3D.create(*frame.x_axis), core.Vector3D.create(*frame.y_axis),
        (web.x_max_mm - web.x_min_mm) / 10,
        (web.y_max_mm - web.y_min_mm) / 10,
        (web.z_max_mm - web.z_min_mm) / 10)
    return _require_body(manager.createBox(bounds), "Could not construct a hinge attachment or seam clearance box.")



def _local_mm(frame, point):
    delta = tuple(value * 10 - origin for value, origin in zip(_xyz(point), frame.origin_mm))
    return tuple(_dot(delta, axis) for axis in (frame.x_axis, frame.y_axis, frame.z_axis))


def _mating_face(top_face, edge, frame, normal_sign):
    """Find one bounded flat interface adjacent to the selected front/top edge."""
    matches = []
    for candidate in _items(edge.faces):
        if candidate == top_face or candidate.body != top_face.body:
            continue
        try:
            normal = _plane_normal(candidate)
        except HingeGeometryError:
            continue
        if _dot(normal, frame.x_axis) * normal_sign >= 1 - ANGLE_TOLERANCE:
            matches.append(candidate)
    if len(matches) != 1:
        raise HingeGeometryError(
            "Split seam requires opposite flat mating faces behind the shared edge. "
            "Choose the two outside faces on the same plane.")
    face = matches[0]
    if face.loops.count != 1 or face.edges.count != 4:
        raise HingeGeometryError(
            "Split seam currently supports matching rectangular mating faces without holes.")
    corners = []
    for boundary in _items(face.edges):
        endpoints = _straight_endpoints(boundary)
        if endpoints is None:
            raise HingeGeometryError("Split seam requires four straight mating-face edges.")
        for endpoint in endpoints:
            delta_mm = tuple(value * 10 - origin for value, origin in zip(endpoint, frame.origin_mm))
            local = tuple(_dot(delta_mm, axis) for axis in (frame.x_axis, frame.y_axis, frame.z_axis))
            if not any(_dot(_subtract(local, other), _subtract(local, other))
                       <= (POSITION_TOLERANCE_CM * 10) ** 2 for other in corners):
                corners.append(local)
    return tuple(corners)


def _require_split_half_space(body, frame, role):
    """Bound this first seam mode to polyhedral solids wholly on their side.

    For planar faces bounded by straight segments, all geometry is bounded by
    the vertices. Curved/re-entrant solids require a separate proven test; do
    not silently cut them with a rectangular clearance tool.
    """
    core, _ = _api()
    if any(core.Plane.cast(face.geometry) is None for face in _items(body.faces)):
        raise HingeGeometryError(
            "Split seam currently supports bodies with flat faces and straight edges. "
            "Use separated bodies for curved or filleted sources.")
    if any(_straight_endpoints(edge) is None for edge in _items(body.edges)):
        raise HingeGeometryError("Split seam currently supports straight-edged source bodies.")
    positions = tuple(_local_mm(frame, vertex.geometry)[0] for vertex in _items(body.vertices))
    tolerance = POSITION_TOLERANCE_CM * 10
    if (not positions or any(not math.isfinite(value) for value in positions)
            or (role == "A" and max(positions) > tolerance)
            or (role == "B" and min(positions) < -tolerance)):
        raise HingeGeometryError(
            "Each split body must stay on its own side of the selected seam. "
            "No arbitrary source trimming is supported.")


def _split_clearance_bounds(face_a, face_b, edge_a, frame, settings):
    endpoints = _straight_endpoints(edge_a)
    matches = _coincident_face_edges(face_b, edge_a)
    if len(matches) != 1:
        raise HingeGeometryError(
            "Split seam requires one complete coincident boundary edge on both selected faces.")
    corners_a = _mating_face(face_a, edge_a, frame, 1)
    corners_b = _mating_face(face_b, matches[0], frame, -1)
    _require_split_half_space(face_a.body, frame, "A")
    _require_split_half_space(face_b.body, frame, "B")
    delta = _subtract(endpoints[1], endpoints[0])
    edge_length_mm = math.sqrt(_dot(delta, delta)) * 10
    try:
        return plan_seam_clearance(corners_a, corners_b, settings.seam_clearance_mm,
                                   edge_length_mm, POSITION_TOLERANCE_CM * 10)
    except ValueError as error:
        raise HingeGeometryError(str(error)) from error


def _cut_split_copies(manager, results, frame, bounds):
    """Cut only already-copied temporary bodies; source handles never enter here."""
    _, fusion = _api()
    cutter = _box(manager, frame, bounds)
    for role in ("A", "B"):
        before_volume = float(results[role].volume)
        _boolean(manager, results[role], cutter, fusion.BooleanTypes.DifferenceBooleanType,
                 "The seam clearance would remove or split a hinge source copy. Reduce its clearance.")
        after_volume = float(results[role].volume)
        if not math.isfinite(after_volume) or not 0 < after_volume < before_volume:
            raise HingeGeometryError(
                "The seam clearance did not remove positive material from both source copies.")
    return cutter


def _cylinder(manager, frame, start, end, radius, height):
    body = manager.createCylinderOrCone(_point(frame, 0, start, height), radius / 10,
                                       _point(frame, 0, end, height), radius / 10)
    return _require_body(body, "Could not construct a hinge barrel or pin.")


def _vertical_cylinder(manager, frame, x, y, z_min, z_max, radius):
    body = manager.createCylinderOrCone(_point(frame, x, y, z_min), radius / 10,
                                       _point(frame, x, y, z_max), radius / 10)
    return _require_body(body, "Could not construct a leaf corner or screw-hole tool.")


def _axis_frustum(manager, frame, start, end, first_radius, last_radius, height):
    body = manager.createCylinderOrCone(_point(frame, 0, start, height), first_radius / 10,
                                       _point(frame, 0, end, height), last_radius / 10)
    return _require_body(body, "Could not construct a chamfered barrel or pin end.")


def _vertical_frustum(manager, frame, x, y, start, end, first_radius, last_radius):
    body = manager.createCylinderOrCone(_point(frame, x, y, start), first_radius / 10,
                                       _point(frame, x, y, end), last_radius / 10)
    return _require_body(body, "Could not construct a chamfered hole or leaf corner.")


def _beveled_axis_body(manager, frame, start, end, radius, height, size):
    """Keep the cylindrical middle/fit diameter; bevel both external ends."""
    _, fusion = _api()
    target = _cylinder(manager, frame, start + size, end - size, radius, height)
    for low, high, first, last in ((start, start + size, radius - size, radius),
                                   (end - size, end, radius, radius - size)):
        cap = _axis_frustum(manager, frame, low, high, first, last, height)
        _boolean(manager, target, cap, fusion.BooleanTypes.UnionBooleanType,
                 "Could not join a chamfered cylindrical end. Reduce chamfer size.")
    return target


def _world_direction(frame, direction):
    return tuple(sum(direction[axis] * basis[index] for axis, basis in enumerate(
        (frame.x_axis, frame.y_axis, frame.z_axis))) for index in range(3))


def _remove_finish_tool(manager, target, tool, message):
    """Requested edge finish must remove material, not merely return success."""
    _, fusion = _api()
    before = float(target.volume)
    _boolean(manager, target, tool, fusion.BooleanTypes.DifferenceBooleanType, message)
    after = float(target.volume)
    if not math.isfinite(after) or not 0 < after < before:
        raise HingeGeometryError(message + " No positive chamfer volume was removed.")
    return target


def _chamfer_box(manager, frame, body, bounds, size, rounded_outer=None):
    core, fusion = _api()
    for cut in box_chamfer_wedges(bounds, size, rounded_outer):
        oriented = core.OrientedBoundingBox3D.create(
            _point(frame, *cut.center_mm),
            core.Vector3D.create(*_world_direction(frame, cut.edge_axis)),
            core.Vector3D.create(*_world_direction(frame, cut.tangent_axis)),
            cut.length_mm / 10, cut.width_mm / 10, cut.depth_mm / 10,
        )
        if oriented is None:
            raise HingeGeometryError("Could not orient an edge-finish tool.")
        cutter = _require_body(manager.createBox(oriented), "Could not construct an edge-finish tool.")
        _remove_finish_tool(manager, body, cutter,
                            "The edge chamfer would split or remove a generated part. Reduce chamfer size.")
    return body


def _chamfer_round_leaf_corners(manager, frame, body, plate, size):
    """Trim quarter-conical caps, preserving the genuinely curved free outline."""
    _, fusion = _api()
    radius = plate.corner_radius_mm
    x = plate.x_min_mm + radius if plate.owner == "A" else plate.x_max_mm - radius
    margin = min(size / 10, (radius - size) / 2)
    for y, y_sign in ((plate.y_min_mm + radius, -1), (plate.y_max_mm - radius, 1)):
        for bottom in (True, False):
            if bottom:
                low, high = plate.z_min_mm - margin, plate.z_min_mm + size
                first, last = radius - size - margin, radius
            else:
                low, high = plate.z_max_mm - size, plate.z_max_mm + margin
                first, last = radius, radius - size - margin
            ring = _vertical_cylinder(manager, frame, x, y, low, high, radius + margin)
            cone = _vertical_frustum(manager, frame, x, y, low, high, first, last)
            _boolean(manager, ring, cone, fusion.BooleanTypes.DifferenceBooleanType,
                     "Could not construct a rounded corner chamfer.")
            x_low, x_high = ((x - radius - margin, x) if plate.owner == "A" else (x, x + radius + margin))
            y_low, y_high = ((y - radius - margin, y) if y_sign == -1 else (y, y + radius + margin))
            quadrant = _box(manager, frame, replace(plate, x_min_mm=x_low, x_max_mm=x_high,
                                                   y_min_mm=y_low, y_max_mm=y_high,
                                                   z_min_mm=low, z_max_mm=high))
            _boolean(manager, ring, quadrant, fusion.BooleanTypes.IntersectionBooleanType,
                     "Could not isolate the free leaf corner chamfer.")
            _remove_finish_tool(manager, body, ring,
                                "The rounded leaf chamfer would split or remove the leaf.")
    return body


def _finish_leaf_plate(manager, frame, body, plate, size):
    rounded = (-1 if plate.owner == "A" else 1) if plate.corner_radius_mm else None
    _chamfer_box(manager, frame, body, plate, size, rounded)
    if rounded is not None:
        _chamfer_round_leaf_corners(manager, frame, body, plate, size)
    return body


def _leaf_plate(manager, frame, plate):
    """Construct the real leaf outline, with only the two free corners rounded."""
    radius = plate.corner_radius_mm
    if radius == 0:
        return _box(manager, frame, plate)
    _, fusion = _api()
    inner = replace(plate, x_min_mm=plate.x_min_mm + radius) if plate.owner == "A" else replace(
        plate, x_max_mm=plate.x_max_mm - radius)
    target = _box(manager, frame, inner)
    middle = _box(manager, frame, replace(plate, y_min_mm=plate.y_min_mm + radius,
                                           y_max_mm=plate.y_max_mm - radius))
    _boolean(manager, target, middle, fusion.BooleanTypes.UnionBooleanType,
             "Could not join the rounded leaf plate sections.")
    x = plate.x_min_mm + radius if plate.owner == "A" else plate.x_max_mm - radius
    for y in (plate.y_min_mm + radius, plate.y_max_mm - radius):
        corner = _vertical_cylinder(manager, frame, x, y, plate.z_min_mm, plate.z_max_mm, radius)
        _boolean(manager, target, corner, fusion.BooleanTypes.UnionBooleanType,
                 "Could not join a rounded leaf corner.")
    return target


def _drill_leaf(manager, frame, target, plate, hole, finish_size=0):
    _, fusion = _api()
    tool = _vertical_cylinder(manager, frame, hole.x_mm, hole.y_mm,
                              plate.z_min_mm - 0.1, plate.z_max_mm + 0.1, hole.diameter_mm / 2)
    before = float(target.volume)
    _boolean(manager, target, tool, fusion.BooleanTypes.DifferenceBooleanType,
             "The screw hole would remove or split a generated leaf. Reduce its diameter.")
    if finish_size:
        for low, high, first, last in (
                (plate.z_min_mm - 0.1, plate.z_min_mm + finish_size,
                 hole.diameter_mm / 2 + finish_size + 0.1, hole.diameter_mm / 2),
                (plate.z_max_mm - finish_size, plate.z_max_mm + 0.1,
                 hole.diameter_mm / 2, hole.diameter_mm / 2 + finish_size + 0.1)):
            entry = _vertical_frustum(manager, frame, hole.x_mm, hole.y_mm, low, high, first, last)
            _remove_finish_tool(manager, target, entry,
                                "The screw entry chamfer would split the leaf. Reduce chamfer size.")
    after = float(target.volume)
    if not math.isfinite(after) or not 0 < after < before:
        raise HingeGeometryError("The screw-hole tool did not remove positive material from its leaf.")


def _attachment_body(manager, frame, web, settings):
    """Use the reference support on every housing/output mode, mirrored by owner."""
    if settings.web_profile == "tangent":
        return make_tangent_support(manager, frame, web, settings)
    body = (rounded_box(manager, frame, web, settings.fillet_radius_mm)
            if settings.fillet_edges else _box(manager, frame, web))
    if settings.chamfer_edges:
        _chamfer_box(manager, frame, body, web, settings.chamfer_size_mm)
    return body


def _knuckle_body(manager, frame, plan, knuckle, attachment):
    _, fusion = _api()
    size = plan.settings.chamfer_size_mm if plan.settings.chamfer_edges else 0
    radius = plan.barrel_radius_mm
    rounded = plan.settings.fillet_edges
    fillet = plan.settings.fillet_radius_mm
    if plan.settings.knuckle_profile == "square":
        # Inscribe the square in the same radial envelope as the round barrel.
        # Its corners must not expand the existing opposite-leaf keep-out.
        half_side = radius / math.sqrt(2)
        bounds = WebBounds(knuckle.owner, -half_side, half_side, knuckle.start_mm,
                           knuckle.end_mm, radius - half_side, radius + half_side)
        barrel = rounded_box(manager, frame, bounds, fillet) if rounded else _box(manager, frame, bounds)
        if size:
            _chamfer_box(manager, frame, barrel, bounds, size)
    elif rounded:
        barrel = rounded_axis_body(manager, frame, knuckle.start_mm, knuckle.end_mm,
                                   radius, radius, fillet)
    else:
        barrel = (_beveled_axis_body(manager, frame, knuckle.start_mm, knuckle.end_mm,
                                    radius, radius, size) if size else
                  _cylinder(manager, frame, knuckle.start_mm, knuckle.end_mm, radius, radius))
    _boolean(manager, barrel, attachment, fusion.BooleanTypes.UnionBooleanType,
             "The barrel and its attachment web do not form one solid.")
    bore = _cylinder(manager, frame, knuckle.start_mm - 0.1, knuckle.end_mm + 0.1,
                     plan.bore_radius_mm, plan.barrel_radius_mm)
    _boolean(manager, barrel, bore, fusion.BooleanTypes.DifferenceBooleanType,
             "Could not cut the pin bore through a hinge knuckle.")
    if size:
        for low, high, first, last in (
                (knuckle.start_mm - 0.1, knuckle.start_mm + size,
                 plan.bore_radius_mm + size + 0.1, plan.bore_radius_mm),
                (knuckle.end_mm - size, knuckle.end_mm + 0.1,
                 plan.bore_radius_mm, plan.bore_radius_mm + size + 0.1)):
            entry = _axis_frustum(manager, frame, low, high, first, last, plan.barrel_radius_mm)
            _remove_finish_tool(manager, barrel, entry,
                                "Could not finish the bore entry. Reduce chamfer size.")
    if rounded:
        for position, inward in ((knuckle.start_mm, 1), (knuckle.end_mm, -1)):
            round_bore_entry(manager, frame, barrel, plan.bore_radius_mm,
                             position, inward, radius, fillet)
    return barrel


def _require_body(body, message):
    if body is None or not body.isValid or not body.isSolid or body.lumps.count != 1:
        raise HingeGeometryError(message)
    return body


def _boolean(manager, target, tool, operation, message):
    if not manager.booleanOperation(target, tool, operation):
        raise HingeGeometryError(message)
    return _require_body(target, message)


def _positive_attachment(manager, web, source):
    _, fusion = _api()
    overlap = manager.copy(web)
    if overlap is None or not manager.booleanOperation(
            overlap, source, fusion.BooleanTypes.IntersectionBooleanType):
        raise HingeGeometryError("An attachment web misses its source body. Adjust reach or axis offset.")
    if not overlap.isValid or not overlap.isSolid or overlap.volume <= 0:
        raise HingeGeometryError("An attachment web only touches its source. Increase attachment overlap.")


def _require_separate(manager, one, two, label):
    """Require both no positive intersection and a measured positive gap.

    Empty intersections can be reported as a failed boolean by the kernel. A
    positive minimum distance independently establishes separation in that case;
    failed/ambiguous measurements are rejected instead of treated as clearance.
    This checks only the generated position, not a rotation sweep.
    """
    core, fusion = _api()
    overlap = manager.copy(one)
    if overlap is None:
        raise HingeGeometryError("Could not check the separation of " + label + ".")
    intersection = manager.booleanOperation(overlap, two, fusion.BooleanTypes.IntersectionBooleanType)
    if intersection and overlap.isValid and overlap.isSolid and overlap.volume > 0:
        raise HingeGeometryError(label + " overlap. Adjust the faces, offset, reach or clearances.")
    try:
        measurement = core.Application.get().measureManager.measureMinimumDistance(one, two)
        gap = float(measurement.value) if measurement is not None else float("nan")
    except Exception as error:
        raise HingeGeometryError("Fusion could not verify separation of " + label + ".") from error
    if not math.isfinite(gap) or gap <= POSITION_TOLERANCE_CM:
        raise HingeGeometryError(label + " touch or separation is ambiguous. Use a positive gap.")


def prepare_hinge(design, face_a, face_b, axis_edge, settings, *, edge_finisher=None, _historical=False):
    """Validate sources and construct exact temporary output without model writes."""
    _require_main_thread()
    if not isinstance(settings, HingeSettings):
        raise HingeGeometryError("Use validated hinge settings.")
    settings.validate()
    started = time.perf_counter()
    frame, signature, axis_edge = _selection(design, face_a, face_b, axis_edge, settings, historical=_historical)
    if not settings.split_seam and _coincident_face_edges(face_b, axis_edge):
        # A touching split needs a centered axis and a gap, rather than the
        # offset intended for already-separated sources. Derive the effective
        # immutable recipe before any temporary cuts. The full seam validator
        # below still refuses ambiguous or unsupported touching geometry.
        settings = replace(settings, split_seam=True)
        frame, signature, axis_edge = _selection(design, face_a, face_b, axis_edge, settings, historical=_historical)
    separate = settings.output_mode == "separate"
    compound_finish = edge_finisher is not None and (settings.chamfer_edges or settings.fillet_edges)
    construction = replace(settings, chamfer_edges=False, fillet_edges=False) if compound_finish else settings
    seam_bounds = (_split_clearance_bounds(face_a, face_b, axis_edge, frame, settings)
                   if settings.split_seam and not separate else None)
    read_done = time.perf_counter()
    plan = build_hinge_plan(settings)
    construction_plan = replace(plan, settings=construction)
    endpoints = _straight_endpoints(axis_edge)
    edge_delta = _subtract(endpoints[1], endpoints[0])
    layout = build_hinge_layout(settings, math.sqrt(_dot(edge_delta, edge_delta)) * 10)
    plan_done = time.perf_counter()
    _, fusion = _api()
    manager = fusion.TemporaryBRepManager.get()
    if manager is None:
        raise HingeGeometryError("Fusion's temporary geometry manager is unavailable.")
    results = {}
    attachment_sources = {}
    if not separate:
        sources = {"A": face_a.body, "B": face_b.body}
        results = {role: _require_body(manager.copy(body), "Could not copy the selected source body.")
                   for role, body in sources.items()}
        if seam_bounds is not None:
            _cut_split_copies(manager, results, frame, seam_bounds)
        for placement in layout.placements:
            relief_frame = replace(frame, origin_mm=frame.point_mm(0, placement.center_mm, 0))
            cut_rotation_relief(manager, relief_frame, results, settings)
        # Keep an unmodified transient attachment reference after the optional cut.
        attachment_sources = {role: _require_body(manager.copy(body), "Could not copy the attachment reference.")
                              for role, body in results.items()}
    for placement in layout.placements:
        unit_frame = replace(frame, origin_mm=frame.point_mm(0, placement.center_mm, 0))
        unit = ({plate.owner: (rounded_box(manager, unit_frame, plate, settings.fillet_radius_mm)
                               if construction.fillet_edges else _leaf_plate(manager, unit_frame, plate))
                 for plate in plan.plates} if separate else results)
        if separate and construction.chamfer_edges:
            for plate in plan.plates:
                _finish_leaf_plate(manager, unit_frame, unit[plate.owner], plate, settings.chamfer_size_mm)
        if separate:
            cut_rotation_relief(manager, unit_frame, unit, settings)
        for knuckle, web in zip(plan.knuckles, plan.webs):
            attachment = _attachment_body(manager, unit_frame, web, construction)
            if not separate:
                _positive_attachment(manager, attachment, attachment_sources[knuckle.owner])
            barrel = _knuckle_body(manager, unit_frame, construction_plan, knuckle, attachment)
            _boolean(manager, unit[knuckle.owner], barrel, fusion.BooleanTypes.UnionBooleanType,
                     "A knuckle did not join its generated leaf into one solid." if separate else
                     "An attachment did not join its source body into one solid.")
        if separate:
            plates = {plate.owner: plate for plate in plan.plates}
            for hole in plan.mounting_holes:
                if construction.chamfer_edges:
                    _drill_leaf(manager, unit_frame, unit[hole.owner], plates[hole.owner], hole,
                                settings.chamfer_size_mm)
                else:
                    _drill_leaf(manager, unit_frame, unit[hole.owner], plates[hole.owner], hole)
                if construction.fillet_edges:
                    plate = plates[hole.owner]
                    for position, inward in ((plate.z_min_mm, 1), (plate.z_max_mm, -1)):
                        round_bore_entry(manager, unit_frame, unit[hole.owner], hole.diameter_mm / 2,
                                         position, inward, 0, settings.fillet_radius_mm,
                                         axis="z", x=hole.x_mm, y=hole.y_mm)
            for owner, leaf in unit.items():
                role = owner if settings.hinge_count == 1 else f"{owner}_{placement.index + 1}"
                results[role] = leaf
    if settings.include_pin:
        for placement in layout.placements:
            unit_frame = replace(frame, origin_mm=frame.point_mm(0, placement.center_mm, 0))
            if construction.fillet_edges:
                pin = rounded_axis_body(manager, unit_frame, plan.pin_start_mm, plan.pin_end_mm,
                                        settings.pin_diameter_mm / 2, plan.barrel_radius_mm,
                                        settings.fillet_radius_mm)
            else:
                pin = (_beveled_axis_body(manager, unit_frame, plan.pin_start_mm, plan.pin_end_mm,
                                         settings.pin_diameter_mm / 2, plan.barrel_radius_mm,
                                         settings.chamfer_size_mm) if construction.chamfer_edges else
                       _cylinder(manager, unit_frame, plan.pin_start_mm, plan.pin_end_mm,
                                 settings.pin_diameter_mm / 2, plan.barrel_radius_mm))
            role = "pin" if settings.hinge_count == 1 else f"pin_{placement.index + 1}"
            results[role] = pin
    result_items = tuple(results.items())
    if compound_finish:
        result_items = edge_finisher(design, manager, frame, settings, result_items,
                                     plan=plan, layout=layout)
    for index, (role, body) in enumerate(result_items):
        for other_role, other_body in result_items[index + 1:]:
            label = ("The two hinge halves" if (role, other_role) == ("A", "B") else
                     f"The generated hinge bodies {role} and {other_role}")
            _require_separate(manager, body, other_body, label)
    ended = time.perf_counter()
    return PreparedHinge(design, face_a, face_b, axis_edge, settings, plan, frame,
                         result_items, result_items, signature,
                         {"source_read_ms": (read_done - started) * 1000,
                          "planning_ms": (plan_done - read_done) * 1000,
                          "temporary_geometry_ms": (ended - plan_done) * 1000}, layout)


def prepare_edit_hinge(design, target, settings, *, edge_finisher=None):
    """Prepare saved selections in their original source history context."""
    from . import inplace
    if inplace.is_recipe(target.recipe):
        return inplace.prepare_edit(design, target, settings, edge_finisher=edge_finisher)
    return prepare_hinge(design, target.face_a, target.face_b, target.axis_edge, settings,
                         edge_finisher=edge_finisher)


def source_bodies(prepared):
    """Explicit attached sources for presentation/commit; geometry stays intact."""
    _require_main_thread()
    if prepared.settings.output_mode != "attached":
        return ()
    if getattr(prepared, "history_anchor", None) is not None:
        from . import inplace
        return validated_bodies(inplace._source_bodies(prepared.design, {"sources": prepared.source_tokens}))
    return validated_bodies((prepared.face_a.body, prepared.face_b.body))


def preview_hide_bodies(prepared, target=None):
    """Return sources and the exact previously validated owned Edit output."""
    _require_main_thread()
    bodies = source_bodies(prepared)
    if target is None:
        return bodies
    from . import inplace
    if inplace.is_recipe(getattr(target, "recipe", None)):
        return validated_bodies(bodies + tuple(inplace.result_bodies(prepared.design, target.recipe).values()))
    anchor = getattr(target, "anchor", None)
    owned = getattr(anchor, "bodies", None) if anchor is not None else None
    if owned is None:
        component = target.component
        if component == prepared.design.rootComponent:
            raise HingeGeometryError("Edit preview needs its owned base feature, not the whole root component.")
        owned = component.bRepBodies
    return validated_bodies(bodies + _items(owned))


def _preview_appearances(prepared):
    """Read existing design appearances; never add/copy materials for a preview."""
    root = prepared.design.rootComponent
    default = root.material.appearance
    appearances = {"A": default, "B": default, "pin": default}
    if prepared.settings.output_mode == "attached":
        if getattr(prepared, "history_anchor", None) is not None:
            bodies = tuple(_resolve_one(prepared.design, prepared.source_tokens["body_" + owner.lower()],
                                        "The preview target " + owner) for owner in ("A", "B"))
        else:
            bodies = (prepared.face_a.body, prepared.face_b.body)
        for owner, body in zip(("A", "B"), bodies):
            appearances[owner] = body.appearance or body.material.appearance or default
    if any(appearance is None for appearance in appearances.values()):
        raise HingeGeometryError("Fusion could not read the model appearance for the hinge preview.")
    return appearances


def _preview_outlines(group, body, core, fusion):
    """Draw trimmed visible edges as one batch; avoid appearance-tinted outlines."""
    viewport = core.Application.get().activeViewport
    if viewport.visualStyle == core.VisualStyles.ShadedVisualStyle:
        return
    coordinates = []
    indices = []
    for edge in _items(body.edges):
        # A periodic surface's seam is not a physical sharp edge.
        if edge.isDegenerate or edge.faces.count < 2:
            continue
        success, start, end = edge.evaluator.getParameterExtents()
        if not success:
            raise HingeGeometryError("Fusion could not read a preview edge boundary.")
        success, points = edge.evaluator.getStrokes(start, end, PREVIEW_EDGE_TOLERANCE_CM)
        if not success or len(points) < 2:
            raise HingeGeometryError("Fusion could not draw a bounded preview edge.")
        offset = len(coordinates) // 3
        for point in points:
            coordinates.extend(_xyz(point))
        for index in range(len(points) - 1):
            indices.extend((offset + index, offset + index + 1))
    if not indices:
        return
    geometry = fusion.CustomGraphicsCoordinates.create(coordinates)
    lines = group.addLines(geometry, indices, False)
    if lines is None:
        raise HingeGeometryError("Fusion could not draw the hinge preview outlines.")
    lines.color = fusion.CustomGraphicsSolidColorEffect.create(core.Color.create(0, 0, 0, 255))
    lines.weight = 1.0
    lines.depthPriority = 1
    lines.isSelectable = False


def preview_hinge(prepared):
    """Draw the complete result candidate; the session owns source visibility."""
    _require_main_thread()
    core, fusion = _api()
    _assert_fresh(prepared.design, prepared)
    group = prepared.design.rootComponent.customGraphicsGroups.add()
    if group is None:
        raise HingeGeometryError("Could not create the hinge preview.")
    try:
        appearances = _preview_appearances(prepared)
        for role, body in prepared.result_bodies:
            graphic = group.addBRepBody(body)
            if graphic is None:
                raise HingeGeometryError("Could not draw the hinge preview.")
            family = role.split("_", 1)[0]
            material = fusion.CustomGraphicsAppearanceColorEffect.create(appearances[family])
            if material is None:
                raise HingeGeometryError("Could not define the hinge preview material.")
            graphic.color = material
            if graphic.setOpacity(1.0, True) is False:
                raise HingeGeometryError("Fusion could not make the hinge preview fully opaque.")
            graphic.isSelectable = False
            _preview_outlines(group, body, core, fusion)
        return group
    except Exception:
        if group.isValid:
            group.deleteMe()
        raise


def _assert_fresh(design, prepared):
    if getattr(prepared, "history_anchor", None) is not None:
        from . import inplace
        return inplace.assert_fresh(design, prepared)
    if design != prepared.design:
        raise HingeGeometryError("The active design changed. Reselect the hinge sources.")
    _, signature, axis_edge = _selection(design, prepared.face_a, prepared.face_b,
                              prepared.axis_edge, prepared.settings)
    if axis_edge != prepared.axis_edge or signature != prepared.source_signature:
        raise HingeGeometryError("The source geometry changed. Refresh the hinge preview.")


def _attribute(entity, name, value):
    if entity.attributes.add(ATTRIBUTE_GROUP, name, value) is None:
        raise HingeGeometryError("Could not save ownership for the generated hinge.")


def _token(entity):
    value = entity.entityToken
    if not isinstance(value, str) or not value:
        raise HingeGeometryError("Fusion did not provide a persistent reference for a hinge source.")
    return value


def _is_part_design(design):
    """Part Design documents prohibit creating child components."""
    _, fusion = _api()
    intent_types = getattr(fusion, "DesignIntentTypes", None)
    part_intent = getattr(intent_types, "PartDesignIntentType", None)
    return part_intent is not None and getattr(design, "designIntent", None) == part_intent


def _result_roles(settings):
    roles = ({f"{owner}_{index + 1}" for owner in ("A", "B") for index in range(settings.hinge_count)}
             if settings.output_mode == "separate" and settings.hinge_count > 1 else {"A", "B"})
    if settings.include_pin:
        roles.update(("pin",) if settings.hinge_count == 1 else (
            f"pin_{index + 1}" for index in range(settings.hinge_count)))
    return roles


def _result_name(role):
    if role in ("A", "B"):
        return "Hinge half " + role
    if role.startswith(("A_", "B_")):
        owner, index = role.split("_", 1)
        return f"Hinge {index} leaf {owner}"
    return "Separate pin" if role == "pin" else "Separate pin " + role.removeprefix("pin_")


def _create(design, prepared, feature_id):
    core, _ = _api()
    _assert_fresh(design, prepared)
    # Resolve every source reference before the first persistent model operation.
    sources = {"face_a": _token(prepared.face_a), "face_b": _token(prepared.face_b),
               "axis_edge": _token(prepared.axis_edge),
               "body_a": _token(prepared.face_a.body), "body_b": _token(prepared.face_b.body)}
    occurrence = None
    base_feature = None
    part_design = _is_part_design(design)
    editing = False
    try:
        if part_design:
            component = design.rootComponent
        else:
            occurrence = design.rootComponent.occurrences.addNewComponent(core.Matrix3D.create())
            if occurrence is None:
                raise HingeGeometryError("Could not create a component for the hinge results.")
            component = occurrence.component
            component.name = "Partelier Pin Hinge " + feature_id[:8]
        base_feature = component.features.baseFeatures.add()
        if base_feature is None or not base_feature.startEdit():
            raise HingeGeometryError("Could not start the hinge result base feature.")
        editing = True
        base_feature.name = "Partelier hinge geometry " + feature_id[:8]
        added_sources = []
        for role, transient in prepared.result_bodies:
            body = component.bRepBodies.add(transient, base_feature)
            _require_body(body, "Fusion could not persist a hinge result body.")
            added_sources.append((role, body))
        source_bodies = _items(base_feature.bodies)
        if len(source_bodies) != len(added_sources):
            raise HingeGeometryError("Fusion returned an unexpected number of editable hinge source bodies.")
        source_roles = [None] * len(source_bodies)
        for role, added in added_sources:
            indices = [index for index, source in enumerate(source_bodies) if source == added]
            if len(indices) != 1 or source_roles[indices[0]] is not None:
                raise HingeGeometryError("Fusion could not map an editable hinge body to its result index.")
            source_roles[indices[0]] = role
        if not base_feature.finishEdit():
            raise HingeGeometryError("Fusion could not finish the hinge result base feature.")
        editing = False
        # BaseFeature creates different result objects on finishEdit. Never use
        # the source body handles returned while editing for persistent ownership.
        bodies = _items(base_feature.bodies)
        if len(bodies) != len(prepared.result_bodies):
            raise HingeGeometryError("Fusion returned an unexpected number of hinge result bodies.")
        signatures = {}
        for role, body in zip(source_roles, bodies):
            _require_body(body, "A persisted hinge result is not one valid solid.")
            body.name = _result_name(role)
            _attribute(body, OWNER_NAME, json.dumps({"feature_id": feature_id, "role": role}))
            signatures[role] = _body_signature(body)
        recipe = {"version": RECIPE_VERSION, "tool": TOOL_ID, "feature_id": feature_id,
                  "settings": prepared.settings.to_dict(), "sources": sources,
                  "results": signatures, "base_feature": _token(base_feature)}
        _attribute(base_feature, OWNER_NAME, feature_id)
        anchor = base_feature if part_design else component
        _attribute(anchor, RECIPE_NAME, json.dumps(recipe, separators=(",", ":")))
        return anchor
    except Exception as error:
        cleanup_errors = []
        if editing and base_feature is not None and base_feature.isValid:
            try:
                if not base_feature.finishEdit():
                    cleanup_errors.append("could not exit the new base feature")
            except Exception:
                cleanup_errors.append("could not exit the new base feature")
        if occurrence is not None and occurrence.isValid:
            try:
                if not occurrence.deleteMe():
                    cleanup_errors.append("could not delete the new result component")
            except Exception:
                cleanup_errors.append("could not delete the new result component")
        elif part_design and base_feature is not None and base_feature.isValid:
            try:
                if not base_feature.deleteMe():
                    cleanup_errors.append("could not delete the new hinge base feature")
            except Exception:
                cleanup_errors.append("could not delete the new hinge base feature")
        if cleanup_errors:
            raise HingeGeometryError(str(error) + ". Cleanup incomplete: "
                                     + "; ".join(cleanup_errors) + ". Undo the command.") from error
        raise


def create_hinge(design, prepared):
    """Attach directly to selected bodies, or create explicitly separate leaves."""
    _require_main_thread()
    if prepared.settings.output_mode == "attached":
        from . import inplace
        return inplace.create(design, prepared)
    return _create(design, prepared, str(uuid.uuid4()))


def _read_recipe(raw):
    if not isinstance(raw, str) or len(raw) > 65536:
        raise HingeGeometryError("The selected hinge recipe is missing or too large.")
    try:
        recipe = json.loads(raw)
    except (ValueError, TypeError) as error:
        raise HingeGeometryError("The selected hinge recipe is damaged.") from error
    expected = {"version", "tool", "feature_id", "settings", "sources", "results", "base_feature"}
    if not isinstance(recipe, dict) or set(recipe) != expected:
        raise HingeGeometryError("The selected hinge recipe has an unsupported structure.")
    if type(recipe["version"]) is not int or recipe["version"] not in (1, 2, 3, 4, 5, 6, 7, RECIPE_VERSION):
        raise HingeGeometryError("This hinge recipe version is unsupported.")
    if recipe["tool"] != TOOL_ID:
        raise HingeGeometryError("Select a Partelier pin hinge result.")
    try:
        if str(uuid.UUID(recipe["feature_id"])) != recipe["feature_id"]:
            raise ValueError()
    except (ValueError, TypeError, AttributeError) as error:
        raise HingeGeometryError("The hinge ownership identity is invalid.") from error
    raw_settings = recipe["settings"]
    legacy_fields = {
        1: LEGACY_SETTINGS_FIELDS,
        2: VERSION_TWO_SETTINGS_FIELDS,
        3: VERSION_THREE_SETTINGS_FIELDS,
        4: VERSION_FOUR_SETTINGS_FIELDS,
        5: VERSION_FIVE_SETTINGS_FIELDS,
        6: VERSION_SIX_SETTINGS_FIELDS,
        7: VERSION_SEVEN_SETTINGS_FIELDS,
    }
    version = recipe["version"]
    if version in legacy_fields:
        if not isinstance(raw_settings, dict) or set(raw_settings) != legacy_fields[version]:
            raise HingeGeometryError(f"The version {version} hinge settings have an unsupported structure.")
        # Expand only in memory; saved v1-v6 geometry keeps its original flat
        # attachment until the user explicitly chooses the new tapered shape.
        defaults = dict(RELIEF_DEFAULTS)
        if version < 7:
            defaults.update(SUPPORT_DEFAULTS)
        if version < 6:
            defaults.update(STYLE_DEFAULTS)
        if version < 5:
            defaults.update(FINISH_DEFAULTS)
        if version < 4:
            defaults.update(LEAF_DEFAULTS)
        if version < 3:
            defaults.update(LAYOUT_DEFAULTS)
        if version < 2:
            defaults.update(split_seam=False, seam_clearance_mm=0.3)
        settings = HingeSettings.from_dict({**raw_settings, **defaults})
    else:
        settings = HingeSettings.from_dict(raw_settings)
    source_keys = {"face_a", "face_b", "axis_edge", "body_a", "body_b"}
    if not isinstance(recipe["sources"], dict) or set(recipe["sources"]) != source_keys:
        raise HingeGeometryError("The hinge source references are invalid.")
    for value in (*recipe["sources"].values(), recipe["base_feature"]):
        if not isinstance(value, str) or not value or len(value) > 8192:
            raise HingeGeometryError("The hinge source references are invalid.")
    roles = _result_roles(settings)
    if not isinstance(recipe["results"], dict) or set(recipe["results"]) != roles:
        raise HingeGeometryError("The hinge result ownership is incomplete.")
    for value in recipe["results"].values():
        if not isinstance(value, str) or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
            raise HingeGeometryError("The hinge result signatures are invalid.")
    return recipe, settings


def _resolve_one(design, token, label):
    entities = design.findEntityByToken(token)
    if entities is None or len(entities) != 1 or not _valid(entities[0]):
        raise HingeGeometryError(label + " is missing or split. Reselect sources in a new hinge.")
    return entities[0]


def _result_component(entity):
    _, fusion = _api()
    component = fusion.Component.cast(entity)
    occurrence = fusion.Occurrence.cast(entity)
    body = fusion.BRepBody.cast(entity)
    if component is not None:
        return component
    if occurrence is not None:
        return occurrence.component
    if body is not None:
        return body.parentComponent
    raise HingeGeometryError("Select a generated hinge component or one of its bodies.")


def _owned_occurrence(design, component):
    root = design.rootComponent
    all_occurrences = root.allOccurrencesByComponent(component)
    occurrences = root.occurrencesByComponent(component)
    if all_occurrences.count != 1 or occurrences.count != 1:
        raise HingeGeometryError("Edit supports one unmoved hinge occurrence directly under the root.")
    occurrence = occurrences.item(0)
    matrix = occurrence.transform2
    identity = (1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1)
    if any(abs(value - expected) > 1e-8 for value, expected in zip(matrix.asArray(), identity)):
        raise HingeGeometryError("The hinge result was moved. Edit supports its original placement only.")
    return occurrence


def _guard_feature_timeline(design, feature, *, allow_later=False):
    timeline = feature.timelineObject
    if timeline is None or timeline.index < 0 or timeline.index >= design.timeline.count:
        raise HingeGeometryError("Edit requires a valid, ungrouped hinge timeline feature.")
    if not allow_later and timeline.index != design.timeline.count - 1:
        raise HingeGeometryError("Edit requires the hinge to be last in the timeline, without later features.")
    if not hasattr(timeline, "isDeletable"):
        raise HingeGeometryError("Update Fusion to a version with the September 2026 API for safe Edit/Rebuild.")
    if not timeline.isDeletable:
        raise HingeGeometryError("The hinge has dependencies that prevent safe replacement.")
    if design.timeline.markerPosition != design.timeline.count:
        raise HingeGeometryError("Move the timeline marker to the end before editing a hinge.")


def _guard_owned_bodies(bodies, recipe, attribute_group):
    if len(bodies) != len(recipe["results"]):
        raise HingeGeometryError("The hinge result bodies were changed. Create a new hinge to preserve them.")
    roles = set()
    for body in bodies:
        tag = body.attributes.itemByName(attribute_group, OWNER_NAME)
        try:
            owner = json.loads(tag.value) if tag is not None else {}
        except (TypeError, ValueError) as error:
            raise HingeGeometryError("A hinge body ownership tag is damaged.") from error
        role = owner.get("role") if isinstance(owner, dict) else None
        if (not isinstance(owner, dict) or set(owner) != {"feature_id", "role"}
                or owner["feature_id"] != recipe["feature_id"]
                or not isinstance(role, str) or role not in recipe["results"] or role in roles
                or _body_signature(body) != recipe["results"][role]):
            raise HingeGeometryError("The generated bodies were edited. Create a new hinge to preserve those changes.")
        roles.add(role)


def _guard_owned_result(design, component, recipe, attribute_group=ATTRIBUTE_GROUP):
    """Refuse destructive replacement if downstream/unowned content may exist."""
    if not _valid(component) or component == design.rootComponent:
        raise HingeGeometryError("Select a valid generated hinge component.")
    occurrence = _owned_occurrence(design, component)
    for name in ("occurrences", "sketches", "meshBodies", "constructionPlanes", "constructionAxes",
                 "constructionPoints", "canvases", "decals", "joints", "asBuiltJoints", "jointOrigins"):
        if getattr(component, name).count:
            raise HingeGeometryError("The hinge component contains added content. Keep it and create a new hinge.")
    if component.features.count != 1:
        raise HingeGeometryError("The hinge result has additional features. Create a new hinge to preserve them.")
    feature = _resolve_one(design, recipe["base_feature"], "The owned base feature")
    owned = feature.attributes.itemByName(attribute_group, OWNER_NAME)
    if feature.parentComponent != component or owned is None or owned.value != recipe["feature_id"]:
        raise HingeGeometryError("The selected result does not own its recorded base feature.")
    _guard_feature_timeline(design, feature)
    _guard_owned_bodies(_items(component.bRepBodies), recipe, attribute_group)
    return occurrence


def _recipe_attribute(component):
    """Choose one complete ownership namespace; never mix old and new tags."""
    matches = []
    for group in (ATTRIBUTE_GROUP, LEGACY_ATTRIBUTE_GROUP):
        attribute = component.attributes.itemByName(group, RECIPE_NAME)
        if attribute is not None:
            matches.append((group, attribute))
    if len(matches) > 1:
        raise HingeGeometryError("The selected hinge has conflicting ownership recipes. Keep it and create a new hinge.")
    return matches[0] if matches else (ATTRIBUTE_GROUP, None)


def _root_feature_for_body(design, body):
    """Resolve a root result by its owner, never by claiming the root itself."""
    tags = [(group, body.attributes.itemByName(group, OWNER_NAME))
            for group in (ATTRIBUTE_GROUP, LEGACY_ATTRIBUTE_GROUP)]
    tags = [(group, tag) for group, tag in tags if tag is not None]
    if len(tags) != 1:
        raise HingeGeometryError("Select one generated Partelier hinge body with unambiguous ownership.")
    group, tag = tags[0]
    try:
        owner = json.loads(tag.value)
    except (ValueError, TypeError) as error:
        raise HingeGeometryError("The selected hinge body ownership is damaged.") from error
    if (not isinstance(owner, dict) or set(owner) != {"feature_id", "role"}
            or not isinstance(owner["feature_id"], str) or not isinstance(owner["role"], str)):
        raise HingeGeometryError("The selected hinge body ownership is damaged.")
    matches = []
    for feature in _items(design.rootComponent.features.baseFeatures):
        owned = feature.attributes.itemByName(group, OWNER_NAME)
        if owned is not None and owned.value == owner["feature_id"]:
            matches.append(feature)
    if len(matches) != 1:
        raise HingeGeometryError("The selected hinge body has no unique owned base feature.")
    return matches[0]


def _guard_root_result(design, feature, recipe, attribute_group, selected_body=None):
    """Own only the recorded root BaseFeature; unrelated root content is allowed."""
    root = design.rootComponent
    if not _valid(feature) or feature.parentComponent != root:
        raise HingeGeometryError("Select a valid generated hinge base feature in the root component.")
    resolved = _resolve_one(design, recipe["base_feature"], "The owned base feature")
    owned = feature.attributes.itemByName(attribute_group, OWNER_NAME)
    if resolved != feature or owned is None or owned.value != recipe["feature_id"]:
        raise HingeGeometryError("The selected result does not own its recorded base feature.")
    # Here the checked feature is the exact retirement owner. Hybrid output
    # retires an occurrence instead and deliberately keeps its last-item gate.
    _guard_feature_timeline(design, feature, allow_later=_is_part_design(design))
    bodies = _items(feature.bodies)
    if any(body.parentComponent != root or body.assemblyContext is not None for body in bodies):
        raise HingeGeometryError("The hinge result bodies are no longer native root bodies.")
    _guard_owned_bodies(bodies, recipe, attribute_group)
    if selected_body is not None and selected_body not in bodies:
        raise HingeGeometryError("The selected body is not a result of its recorded hinge base feature.")


def read_edit_target(design, selected_entity):
    """Read one owned result and resolve every source uniquely through Fusion."""
    _require_main_thread()
    _, fusion = _api()
    if not _valid(design) or design.designType != fusion.DesignTypes.ParametricDesignType:
        raise HingeGeometryError("Use a Fusion Design with Capture Design History enabled.")
    # Part Design picking can return the enclosing Part instead of a body.
    # Resolve only one explicit owned recipe; never claim every body in root.
    for type_name in ("BRepFace", "BRepEdge"):
        entity_type = getattr(fusion, type_name, None)
        boundary = entity_type.cast(selected_entity) if entity_type is not None else None
        if boundary is not None:
            selected_entity = boundary.body
            break
    component_type = getattr(fusion, "Component", None)
    selected_component = component_type.cast(selected_entity) if component_type is not None else None
    if selected_component is not None and selected_component == design.rootComponent:
        candidates = []
        for feature in _items(selected_component.features.baseFeatures):
            _, recipe = _recipe_attribute(feature)
            if recipe is not None:
                candidates.append(feature)
        if not candidates:
            raise HingeGeometryError("The selected Part contains no editable Partelier hinges. Pick a hinge body or pin.")
        if len(candidates) != 1:
            raise HingeGeometryError("The selected Part contains multiple hinges. Pick one hinge body or pin.")
        selected_entity = candidates[0]
    from . import inplace
    attached = inplace.read_if_inplace(design, selected_entity)
    if attached is not None:
        return attached
    body_type = getattr(fusion, "BRepBody", None)
    feature_type = getattr(fusion, "BaseFeature", None)
    body = body_type.cast(selected_entity) if body_type is not None else None
    feature = feature_type.cast(selected_entity) if feature_type is not None else None
    if body is not None and body.parentComponent == design.rootComponent:
        if body.assemblyContext is not None:
            raise HingeGeometryError("Select a native generated hinge body in the root component.")
        feature = _root_feature_for_body(design, body)
    root_result = feature is not None and feature.parentComponent == design.rootComponent
    component = design.rootComponent if root_result else _result_component(selected_entity)
    anchor = feature if root_result else component
    attribute_group, attribute = _recipe_attribute(anchor)
    if attribute is None:
        raise HingeGeometryError("Select a Partelier pin hinge result with an editable recipe.")
    recipe, settings = _read_recipe(attribute.value)
    if root_result:
        _guard_root_result(design, feature, recipe, attribute_group, body)
        occurrence = None
    else:
        occurrence = _guard_owned_result(design, component, recipe, attribute_group)
    sources = {name: _resolve_one(design, token, "Source " + name.replace("_", " "))
               for name, token in recipe["sources"].items()}
    face_a, face_b = fusion.BRepFace.cast(sources["face_a"]), fusion.BRepFace.cast(sources["face_b"])
    axis_edge = fusion.BRepEdge.cast(sources["axis_edge"])
    if (face_a is None or face_b is None or axis_edge is None
            or face_a.body != sources["body_a"] or face_b.body != sources["body_b"]):
        raise HingeGeometryError("The saved hinge sources no longer match their original bodies.")
    return EditTarget(component, occurrence, settings, face_a, face_b, axis_edge,
                      recipe["feature_id"], recipe, anchor)


def _guard_root_recipe_dependencies(design, retiring):
    """Attribute recipes are logical dependencies, invisible to isDeletable.

    Inspect only owned root BaseFeatures. No history movement, body creation or
    model mutation is used to establish independence before replacement.
    """
    root = design.rootComponent
    retiring_bodies = _items(retiring.bodies)
    retiring_ids = {tag.value for group in (ATTRIBUTE_GROUP, LEGACY_ATTRIBUTE_GROUP)
                    for tag in (retiring.attributes.itemByName(group, OWNER_NAME),) if tag is not None}
    for feature in _items(root.features.baseFeatures):
        if feature == retiring:
            continue
        tags = [(group, feature.attributes.itemByName(group, OWNER_NAME),
                 feature.attributes.itemByName(group, RECIPE_NAME))
                for group in (ATTRIBUTE_GROUP, LEGACY_ATTRIBUTE_GROUP)]
        tags = [(group, owner, recipe) for group, owner, recipe in tags
                if owner is not None or recipe is not None]
        if not tags:
            continue
        try:
            if len(tags) != 1 or tags[0][1] is None or tags[0][2] is None:
                raise HingeGeometryError("An owned root hinge has incomplete or conflicting recipe ownership.")
            _, owner, attribute = tags[0]
            from . import inplace
            raw_recipe = json.loads(attribute.value)
            if inplace.is_recipe(raw_recipe):
                other = inplace._read_target(design, feature)
                if other.feature_id in retiring_ids:
                    raise HingeGeometryError("Another root hinge has the same ownership identity; replacement is unsafe.")
                if any(source == body for source in inplace._source_bodies(design, other.recipe) for body in retiring_bodies):
                    raise HingeGeometryError("Another attached hinge depends on this hinge's generated bodies.")
                continue
            recipe, _ = _read_recipe(attribute.value)
            if recipe["feature_id"] in retiring_ids:
                raise HingeGeometryError("Another root hinge has the same ownership identity; replacement is unsafe.")
            if owner.value != recipe["feature_id"]:
                raise HingeGeometryError("Another root hinge's ownership does not match its recipe.")
            anchor = _resolve_one(design, recipe["base_feature"], "Another hinge base feature")
            if anchor != feature or not _valid(feature) or feature.parentComponent != root:
                raise HingeGeometryError("Another root hinge no longer owns its recorded base feature.")
            sources = {name: _resolve_one(design, token, "Other hinge source " + name)
                       for name, token in recipe["sources"].items()}
            _, fusion = _api()
            body_a = fusion.BRepBody.cast(sources["body_a"])
            body_b = fusion.BRepBody.cast(sources["body_b"])
            face_a = fusion.BRepFace.cast(sources["face_a"])
            face_b = fusion.BRepFace.cast(sources["face_b"])
            edge = fusion.BRepEdge.cast(sources["axis_edge"])
            references = (body_a, body_b, getattr(face_a, "body", None),
                          getattr(face_b, "body", None), getattr(edge, "body", None))
            if any(source is not None and source == body for source in references for body in retiring_bodies):
                raise HingeGeometryError("Another hinge depends on this hinge's generated bodies. Rebuild is blocked to preserve its sources.")
            if (body_a is None or body_b is None or face_a is None or face_b is None or edge is None
                    or body_a == body_b or not body_a.isSolid or not body_b.isSolid
                    or face_a.body != body_a or face_b.body != body_b
                    or edge.body not in (body_a, body_b)):
                raise HingeGeometryError("Another root hinge has inconsistent source references.")
            if any(body.parentComponent != root or body.assemblyContext is not None
                   for body in (body_a, body_b)):
                raise HingeGeometryError("Another root hinge has unsupported source body references.")
        except Exception as error:
            raise HingeGeometryError("Could not safely replace this hinge: " + str(error)) from error


def rebuild_hinge(design, target, prepared):
    """Build the replacement before retiring the previous valid, owned result."""
    _require_main_thread()
    from . import inplace
    if inplace.is_recipe(target.recipe):
        return inplace.rebuild(design, target, prepared)
    current = read_edit_target(design, getattr(target, "anchor", None) or target.component)
    if current.feature_id != target.feature_id or current.recipe != target.recipe:
        raise HingeGeometryError("The selected hinge changed. Reopen Edit/Rebuild.")
    if (prepared.face_a != current.face_a or prepared.face_b != current.face_b
            or prepared.axis_edge != current.axis_edge):
        raise HingeGeometryError("Edit/Rebuild uses the saved source selections. Create a new hinge to reselect.")
    if current.occurrence is None:
        _guard_root_recipe_dependencies(design, current.anchor)
    if prepared.settings.output_mode == "attached":
        # Deliberate migration: the originals hidden by older copy-based output
        # become the actual integrated targets. Retire only the exact old owner.
        integrated_sources = source_bodies(prepared)
        replacement = inplace.create(design, prepared, feature_id=target.feature_id)
        previous = current.occurrence if current.occurrence is not None else current.anchor
        if not previous.deleteMe():
            raise HingeGeometryError("Fusion could not retire the previous copied hinge. The command must be rolled back.")
        for body in integrated_sources:
            body.isLightBulbOn = True
        return replacement
    replacement = _create(design, prepared, target.feature_id)
    try:
        previous = current.occurrence if current.occurrence is not None else current.anchor
        if not previous.deleteMe():
            raise HingeGeometryError("Fusion could not retire the prior hinge result.")
    except Exception as error:
        try:
            replacement_owner = replacement if _is_part_design(design) else _owned_occurrence(design, replacement)
            cleaned = not replacement_owner.isValid or replacement_owner.deleteMe()
        except Exception:
            cleaned = False
        if not cleaned:
            raise HingeGeometryError("Replacement failed and cleanup was incomplete. Undo this command.") from error
        raise HingeGeometryError("Replacement failed; the prior hinge was retained. " + str(error)) from error
    return replacement

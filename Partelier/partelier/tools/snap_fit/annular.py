"""One concentric annular bead and mating blind groove, using detached solids.

All lengths in plans are millimetres. Native points/radii are converted once at
primitive creation. The common adapter owns selection history and persistence;
this module only validates cylindrical references and builds a temporary pair.
"""

from dataclasses import dataclass
import math


@dataclass(frozen=True)
class AnnularPlan:
    settings: object
    radius_a_mm: float
    radius_b_mm: float
    radial_gap_mm: float
    bead_inner_radius_mm: float
    bead_peak_radius_mm: float
    groove_inner_radius_mm: float
    groove_radius_mm: float
    bead_start_z_mm: float
    bead_end_z_mm: float
    center_z_mm: float
    groove_start_z_mm: float
    groove_end_z_mm: float
    roof_end_z_mm: float
    units: tuple = ()


def _adapter():
    from . import fusion
    return fusion


def _positive(value, label):
    try:
        valid = not isinstance(value, bool) and isinstance(value, (int, float)) and math.isfinite(value) and value > 0
    except OverflowError:
        valid = False
    if not valid:
        raise ValueError(label + " must be finite and greater than zero.")
    return float(value)


def _xyz(point):
    values = (float(point.x), float(point.y), float(point.z))
    if not all(math.isfinite(value) for value in values):
        raise ValueError("The cylindrical reference contains invalid coordinates.")
    return values


def _subtract(one, two):
    return tuple(a - b for a, b in zip(one, two))


def _dot(one, two):
    return sum(a * b for a, b in zip(one, two))


def _cross(one, two):
    return (one[1] * two[2] - one[2] * two[1], one[2] * two[0] - one[0] * two[2],
            one[0] * two[1] - one[1] * two[0])


def _unit(values):
    length = math.sqrt(_dot(values, values))
    if not math.isfinite(length) or length <= 1e-12:
        raise ValueError("A cylindrical reference has no usable direction.")
    return tuple(value / length for value in values)


def _radial(point, origin, axis):
    delta = _subtract(point, origin)
    axial = _dot(delta, axis)
    return tuple(value - axial * direction for value, direction in zip(delta, axis))


def _cylinder(face, outward):
    sf = _adapter()
    core, _ = sf._api()
    cylinder = core.Cylinder.cast(face.geometry)
    if cylinder is None:
        raise ValueError("Annular snaps require an outer cylindrical face A and inner cylindrical face B.")
    origin, axis = _xyz(cylinder.origin), _unit(_xyz(cylinder.axis))
    radius = _positive(cylinder.radius, "Cylinder radius")
    radial = _unit(_radial(_xyz(face.pointOnFace), origin, axis))
    success, normal = face.evaluator.getNormalAtPoint(face.pointOnFace)
    if not success:
        raise ValueError("Fusion could not read the cylindrical face orientation.")
    sign = _dot(_unit(_xyz(normal)), radial)
    desired = 1 if outward else -1
    if desired * sign < 1 - sf.ANGLE_TOLERANCE:
        raise ValueError("Select the outside of neck A and the inside of socket B.")
    return origin, axis, radius


def _cylinders(face_a, face_b):
    sf = _adapter()
    one, two = _cylinder(face_a, True), _cylinder(face_b, False)
    if abs(_dot(one[1], two[1])) < 1 - sf.ANGLE_TOLERANCE:
        raise ValueError("The annular neck and socket axes must be parallel and coaxial.")
    distance = math.sqrt(_dot(_cross(_subtract(two[0], one[0]), one[1]),
                              _cross(_subtract(two[0], one[0]), one[1])))
    if distance > sf.POSITION_TOLERANCE_CM:
        raise ValueError("The annular neck and socket axes must be coaxial.")
    if not two[2] > one[2] + sf.POSITION_TOLERANCE_CM:
        raise ValueError("Socket B must have a larger inner radius than neck A, leaving a positive radial gap.")
    return one, two


def selection(design, face_a, face_b, edge):
    """Return the common six-value selection contract for a complete annular rim."""
    sf = _adapter()
    sf._main_thread()
    core, native = sf._api()
    if (native.BRepFace.cast(face_a) is None or native.BRepFace.cast(face_b) is None
            or native.BRepEdge.cast(edge) is None):
        raise ValueError("Select two cylindrical faces and a complete circular rim on face A.")
    for face in (face_a, face_b):
        sf._solid(face.body, "Annular snap sources must be valid solid bodies.")
        if (not face.isValid or face.assemblyContext is not None
                or face.body.assemblyContext is not None or face.body.isTemporary
                or face.body.parentComponent != design.rootComponent):
            raise ValueError("Select native cylindrical faces on root-component bodies.")
    if face_a.body == face_b.body:
        raise ValueError("The annular neck and socket must be different bodies.")
    if (not edge.isValid or edge.body != face_a.body
            or not any(candidate == edge for candidate in sf.hinge._items(face_a.edges))):
        raise ValueError("Select a complete circular rim belonging to cylindrical face A.")
    one, two = _cylinders(face_a, face_b)
    circle = core.Circle3D.cast(edge.geometry)
    if circle is None:
        raise ValueError("The annular rim must be a complete circle, not an arc or straight edge.")
    center, normal = _xyz(circle.center), _unit(_xyz(circle.normal))
    circle_radius = _positive(circle.radius, "Circular rim radius")
    _positive(face_a.area, "Cylindrical face A area")
    _positive(face_b.area, "Cylindrical face B area")
    if (not math.isfinite(float(edge.length)) or float(edge.length) <= 0
            or abs(circle_radius - one[2]) > sf.POSITION_TOLERANCE_CM
            or abs(float(edge.length) - 2 * math.pi * one[2]) > max(sf.POSITION_TOLERANCE_CM, one[2] * 1e-7)
            or abs(_dot(normal, one[1])) < 1 - sf.ANGLE_TOLERANCE
            or math.sqrt(_dot(_radial(center, one[0], one[1]), _radial(center, one[0], one[1]))) > sf.POSITION_TOLERANCE_CM):
        raise ValueError("The circular rim does not match the complete cylindrical neck A.")
    axial = _dot(_subtract(_xyz(face_a.pointOnFace), center), one[1])
    if abs(axial) <= sf.POSITION_TOLERANCE_CM:
        raise ValueError("Choose an end rim with the neck A extending away from it.")
    z_axis = one[1] if axial < 0 else tuple(-value for value in one[1])
    x_axis = _unit(_radial(_xyz(face_a.pointOnFace), center, z_axis))
    y_axis = _unit(_cross(z_axis, x_axis))
    frame = sf.hinge.HingeFrame(tuple(value * 10 for value in center), x_axis, y_axis, z_axis)
    signature = (sf.hinge._body_signature(face_a.body), sf.hinge._body_signature(face_b.body),
                 tuple(round(value, 8) for value in center + z_axis + x_axis),
                 round(one[2], 8), round(two[2], 8),
                 round(float(face_a.area), 8), round(float(face_b.area), 8), round(float(edge.length), 8))
    return face_a, face_b, edge, frame, signature, 2 * math.pi * one[2] * 10


def _plan(frame, face_a, face_b, settings):
    settings.validate()
    if getattr(settings, "snap_family", None) != "annular":
        raise ValueError("Use the annular snap family for cylindrical necks and sockets.")
    if type(settings.snap_count) is not int or settings.snap_count != 1:
        raise ValueError("An annular snap uses one continuous ring. Set snap count to 1.")
    if type(settings.chamfer_edges) is not bool or settings.chamfer_edges:
        raise ValueError("Turn general chamfers off for the annular bead and groove profile.")
    if type(settings.print_support) is not bool:
        raise ValueError("Print support must be true or false.")
    one, two = _cylinders(face_a, face_b)
    frame_origin = tuple(value / 10 for value in frame.origin_mm)
    radial = _radial(frame_origin, one[0], one[1])
    if (abs(_dot(one[1], frame.z_axis)) < 1 - _adapter().ANGLE_TOLERANCE
            or math.sqrt(_dot(radial, radial)) > _adapter().POSITION_TOLERANCE_CM):
        raise ValueError("The annular frame no longer matches the selected cylinder axis.")
    a, b = one[2] * 10, two[2] * 10
    width = _positive(settings.annular_bead_width_mm, "Annular bead width")
    height = _positive(settings.annular_bead_height_mm, "Annular bead height")
    offset = _positive(settings.annular_offset_mm, "Annular bead offset")
    clearance = _positive(settings.clearance_mm, "Clearance")
    overlap = _positive(settings.attachment_overlap_mm, "Attachment overlap")
    inner, peak = a - overlap, a + height
    groove_inner, groove = a, peak + clearance
    center = -offset
    bead_low, bead_high = center - width / 2, center + width / 2
    low, high = bead_low - clearance, bead_high + clearance
    roof = high + groove - groove_inner if settings.print_support else high
    values = (a, b, inner, peak, groove_inner, groove, center, bead_low, bead_high, low, high, roof,
              groove + clearance, low - clearance, roof + clearance)
    if (not all(math.isfinite(value) for value in values) or not 0 < inner < a < b < peak < groove
            or not bead_low < center < bead_high or not low < bead_low < bead_high < high
            or roof < high):
        raise ValueError("The annular bead must exceed the radial gap and leave valid root, groove and clearance dimensions.")
    return AnnularPlan(settings, a, b, b - a, inner, peak, groove_inner, groove,
                       bead_low, bead_high, center, low, high, roof)


def _frustum(manager, frame, low, radius_low, high, radius_high):
    sf = _adapter()
    core, _ = sf._api()
    if not low < high or min(radius_low, radius_high) <= 0:
        raise ValueError("The annular cylinder or cone dimensions collapsed.")
    start = core.Point3D.create(*(value / 10 for value in frame.point_mm(0, 0, low)))
    end = core.Point3D.create(*(value / 10 for value in frame.point_mm(0, 0, high)))
    return sf._solid(manager.createCylinderOrCone(start, radius_low / 10, end, radius_high / 10),
                     "Fusion could not construct an annular cylinder or cone.")


def _shell(manager, frame, inner, outer, low, high):
    sf = _adapter()
    _, native = sf._api()
    if not 0 < inner < outer:
        raise ValueError("The annular shell must have distinct positive radii.")
    body = _frustum(manager, frame, low, outer, high, outer)
    core = _frustum(manager, frame, low, inner, high, inner)
    return sf._boolean(manager, body, core, native.BooleanTypes.DifferenceBooleanType,
                       "Fusion could not form an annular shell.")


def _coverage(manager, source, witness, message):
    sf = _adapter()
    _, native = sf._api()
    expected = float(witness.volume)
    sf._boolean(manager, witness, source, native.BooleanTypes.IntersectionBooleanType, message)
    if abs(float(witness.volume) - expected) > max(1e-9, expected * 1e-7):
        raise ValueError(message)


def prepare_geometry(manager, frame, face_a, face_b, settings):
    """Return a plan and two temporary final solids; never mutate either source."""
    sf = _adapter()
    sf._main_thread()
    plan = _plan(frame, face_a, face_b, settings)
    _, native = sf._api()
    operations = native.BooleanTypes
    sf._no_positive_overlap(manager, face_a.body, face_b.body)
    a_root = _shell(manager, frame, plan.bead_inner_radius_mm, plan.radius_a_mm,
                    plan.bead_start_z_mm, plan.bead_end_z_mm)
    _coverage(manager, face_a.body, a_root,
              "Neck A must contain the full annular root width and attachment overlap around the entire ring.")
    c = settings.clearance_mm
    b_shell = _shell(manager, frame, plan.radius_b_mm, plan.groove_radius_mm + c,
                     plan.groove_start_z_mm - c, plan.roof_end_z_mm + c)
    _coverage(manager, face_b.body, b_shell,
              "Socket B must contain the full groove, roof and remaining wall/floor around the entire ring. Increase its wall or axial extent.")
    # Width describes the exposed triangular profile at the neck surface.
    # The inner subtraction leaves a full-width embedded root independently
    # of attachment overlap, so changing overlap cannot reshape the bead.
    bead = _frustum(manager, frame, plan.bead_start_z_mm, plan.radius_a_mm,
                    plan.center_z_mm, plan.bead_peak_radius_mm)
    upper = _frustum(manager, frame, plan.center_z_mm, plan.bead_peak_radius_mm,
                     plan.bead_end_z_mm, plan.radius_a_mm)
    sf._boolean(manager, bead, upper, operations.UnionBooleanType,
                "The two annular bead halves did not join into one solid.")
    inner = _frustum(manager, frame, plan.bead_start_z_mm, plan.bead_inner_radius_mm,
                     plan.bead_end_z_mm, plan.bead_inner_radius_mm)
    sf._boolean(manager, bead, inner, operations.DifferenceBooleanType,
                "Fusion could not form the hollow annular bead.")
    result_a, result_b = sf._copy(manager, face_a.body), sf._copy(manager, face_b.body)
    sf._boolean(manager, result_a, bead, operations.UnionBooleanType,
                "The annular bead did not join the selected neck A.")
    groove = _shell(manager, frame, plan.groove_inner_radius_mm, plan.groove_radius_mm,
                    plan.groove_start_z_mm, plan.groove_end_z_mm)
    sf._boolean(manager, result_b, groove, operations.DifferenceBooleanType,
                "The annular groove removed or split socket B. Increase its wall thickness.")
    if settings.print_support:
        roof = _frustum(manager, frame, plan.groove_end_z_mm, plan.groove_radius_mm,
                        plan.roof_end_z_mm, plan.groove_inner_radius_mm)
        core = _frustum(manager, frame, plan.groove_end_z_mm, plan.groove_inner_radius_mm,
                        plan.roof_end_z_mm, plan.groove_inner_radius_mm)
        sf._boolean(manager, roof, core, operations.DifferenceBooleanType,
                    "Fusion could not form the 45-degree annular groove roof.")
        sf._boolean(manager, result_b, roof, operations.DifferenceBooleanType,
                    "The annular roof removed or split socket B. Increase its wall or axial extent.")
    sf._no_positive_overlap(manager, result_a, result_b)
    return plan, (("A", result_a), ("B", result_b))

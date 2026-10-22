"""Exact transient round edges from analytic Fusion BRep primitives.

Lengths are millimetres in the hinge frame. Only newly generated temporary
solids are accepted; these helpers never create a document, sketch or feature.
The construction rounds convex primitive edges, not concave web/barrel joins.
Native kernel behaviour still needs verification inside Fusion.
"""

import itertools
import math
from numbers import Real
from types import SimpleNamespace


def _adapter():
    # Lazy import permits fusion.py to integrate these helpers without a cycle.
    from . import fusion
    return fusion


def _finite(*values):
    if any(isinstance(value, bool) or not isinstance(value, Real)
           or not math.isfinite(value) for value in values):
        raise _adapter().HingeGeometryError("Round dimensions must be finite numbers in mm.")


def _frame(frame):
    adapter = _adapter()
    try:
        origin = tuple(frame.origin_mm)
        axes = tuple(tuple(axis) for axis in (frame.x_axis, frame.y_axis, frame.z_axis))
        if len(origin) != 3 or any(len(axis) != 3 for axis in axes):
            raise ValueError()
        _finite(*origin, *(value for axis in axes for value in axis))
        if any(abs(adapter._dot(axis, axis) - 1) > 1e-6 for axis in axes):
            raise ValueError()
        if any(abs(adapter._dot(axes[a], axes[b])) > 1e-6
               for a, b in ((0, 1), (0, 2), (1, 2))):
            raise ValueError()
        if adapter._dot(adapter._cross(axes[0], axes[1]), axes[2]) < 1 - 1e-6:
            raise ValueError()
    except (AttributeError, TypeError, ValueError) as error:
        raise adapter.HingeGeometryError("Round geometry needs a finite, orthonormal hinge frame.") from error


def _temporary(body, message):
    adapter = _adapter()
    adapter._require_body(body, message)
    if getattr(body, "isTemporary", False) is not True:
        raise adapter.HingeGeometryError("Round geometry may modify temporary generated bodies only.")
    return body


def _cylinder(manager, frame, start, end, radius):
    adapter = _adapter()
    return _temporary(manager.createCylinderOrCone(
        adapter._point(frame, *start), radius / 10,
        adapter._point(frame, *end), radius / 10),
        "Could not construct a round-edge cylinder.")


def _torus(manager, frame, center, axis, major, minor):
    adapter = _adapter()
    core, _ = adapter._api()
    return _temporary(manager.createTorus(
        adapter._point(frame, *center), core.Vector3D.create(*axis),
        major / 10, minor / 10), "Could not construct a round-edge torus.")


def _join(manager, target, tool):
    adapter = _adapter()
    _, fusion = adapter._api()
    adapter._boolean(manager, target, tool, fusion.BooleanTypes.UnionBooleanType,
                     "Could not join the rounded sections into one solid. Reduce round size.")
    return target


def rounded_box(manager, frame, bounds, radius):
    """Return an envelope-preserving box with twelve equal round edge radii.

    This is the exact Minkowski sum of the inset box with a radius sphere:
    three intersecting face slabs, twelve edge cylinders and eight spheres.
    In particular, the corners are spherical rather than intersecting bevels.
    """
    adapter = _adapter()
    adapter._require_main_thread()
    _frame(frame)
    try:
        low = (bounds.x_min_mm, bounds.y_min_mm, bounds.z_min_mm)
        high = (bounds.x_max_mm, bounds.y_max_mm, bounds.z_max_mm)
    except AttributeError as error:
        raise adapter.HingeGeometryError("Round box bounds need all three axis ranges.") from error
    _finite(radius, *low, *high)
    if radius <= 0 or any(upper - lower <= 2 * radius for lower, upper in zip(low, high)):
        raise adapter.HingeGeometryError("Round size must be positive and less than half each box dimension.")
    inner_low = tuple(value + radius for value in low)
    inner_high = tuple(value - radius for value in high)
    _finite(*(upper - lower for lower, upper in zip(low, high)), *inner_low, *inner_high)
    if any(not lower < inset_low < inset_high < upper for lower, inset_low, inset_high, upper
           in zip(low, inner_low, inner_high, high)):
        raise adapter.HingeGeometryError("Round size must produce distinct inset box coordinates.")
    target = None
    for axis in range(3):
        slab_low = tuple(low[index] if index == axis else inner_low[index] for index in range(3))
        slab_high = tuple(high[index] if index == axis else inner_high[index] for index in range(3))
        slab_bounds = SimpleNamespace(**{
            name + "_min_mm": slab_low[index] for index, name in enumerate("xyz")}, **{
            name + "_max_mm": slab_high[index] for index, name in enumerate("xyz")})
        slab = _temporary(adapter._box(manager, frame, slab_bounds),
                          "Could not construct a rounded box slab.")
        target = slab if target is None else _join(manager, target, slab)
    for axis in range(3):
        other_axes = [index for index in range(3) if index != axis]
        for choices in itertools.product((0, 1), repeat=2):
            start = list(inner_low)
            end = list(inner_low)
            end[axis] = inner_high[axis]
            for index, choice in zip(other_axes, choices):
                start[index] = end[index] = (inner_low, inner_high)[choice][index]
            _join(manager, target, _cylinder(manager, frame, start, end, radius))
    for choices in itertools.product((0, 1), repeat=3):
        center = tuple((inner_low, inner_high)[choice][index]
                       for index, choice in enumerate(choices))
        sphere = _temporary(manager.createSphere(adapter._point(frame, *center), radius / 10),
                            "Could not construct a spherical rounded box corner.")
        _join(manager, target, sphere)
    return target


def rounded_axis_body(manager, frame, start, end, radius, height, fillet):
    """Return a Y-axis cylinder with true circular round ends, within its envelope.

    The straight middle keeps the nominal fit diameter. A full-length inset
    core and two full tori produce tangential quarter-circle end transitions.
    """
    adapter = _adapter()
    adapter._require_main_thread()
    _frame(frame)
    _finite(start, end, radius, height, fillet)
    if fillet <= 0 or end - start <= 2 * fillet or radius <= 2 * fillet:
        raise adapter.HingeGeometryError(
            "Round size must be positive, below half the cylinder radius and below half its length.")
    _finite(end - start, start + fillet, end - fillet)
    if not start < start + fillet < end - fillet < end or not 0 < radius - fillet < radius:
        raise adapter.HingeGeometryError("Round size must produce distinct cylinder end transitions.")
    target = _cylinder(manager, frame, (0, start + fillet, height),
                       (0, end - fillet, height), radius)
    _join(manager, target, _cylinder(manager, frame, (0, start, height),
                                    (0, end, height), radius - fillet))
    for position in (start + fillet, end - fillet):
        _join(manager, target, _torus(manager, frame, (0, position, height),
                                     frame.y_axis, radius - fillet, fillet))
    return target


def round_bore_entry(manager, frame, target, bore_radius, position, inward_sign,
                     height, fillet, axis="y", x=0, y=0):
    """Round one mouth of an existing straight bore on a temporary solid.

    Y is the barrel/pin axis at local X=0, Z=height. For a Z screw hole,
    position is the mouth's Z coordinate and x/y locate the hole; height is
    unused. inward_sign is +1 or -1 into the solid from that mouth.
    The cutter is a short cylinder minus a torus, giving a concave circular
    transition from bore_radius+fillet at the mouth to bore_radius inside.
    """
    adapter = _adapter()
    adapter._require_main_thread()
    _frame(frame)
    _finite(bore_radius, position, height, fillet, x, y)
    if (axis not in ("y", "z") or type(inward_sign) is not int
            or inward_sign not in (-1, 1) or bore_radius <= 0 or fillet <= 0):
        raise adapter.HingeGeometryError("Use a positive bore/round size, Y or Z axis and an inward sign of +1 or -1.")
    _temporary(target, "The bore round needs one valid generated solid.")
    before = float(target.volume)
    if not math.isfinite(before) or before <= 0:
        raise adapter.HingeGeometryError("The bore round needs a positive temporary solid volume.")
    margin = min(fillet / 4, .1)
    outer = position - inward_sign * margin
    inner = position + inward_sign * fillet
    _finite(outer, inner, bore_radius + fillet)
    if (outer == position or inner == position or bore_radius + fillet <= bore_radius):
        raise adapter.HingeGeometryError("Round size must produce distinct bore-entry coordinates.")
    point = ((lambda value: (0, value, height)) if axis == "y"
             else (lambda value: (x, y, value)))
    cutter = _cylinder(manager, frame, point(outer), point(inner), bore_radius + fillet)
    ring = _torus(manager, frame, point(inner),
                   frame.y_axis if axis == "y" else frame.z_axis,
                   bore_radius + fillet, fillet)
    _, fusion = adapter._api()
    adapter._boolean(manager, cutter, ring, fusion.BooleanTypes.DifferenceBooleanType,
                     "Could not construct a circular bore-entry round tool.")
    adapter._boolean(manager, target, cutter, fusion.BooleanTypes.DifferenceBooleanType,
                     "The bore-entry round would split or remove a generated part. Reduce round size.")
    after = float(target.volume)
    if not math.isfinite(after) or not 0 < after < before:
        raise adapter.HingeGeometryError("The bore-entry round did not remove positive material.")
    return target

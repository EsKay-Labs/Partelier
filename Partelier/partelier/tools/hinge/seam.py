"""Pure bounds for an explicit clearance cut between planar split bodies.

This checks a deliberately limited rectangular mating interface. The host must
verify topology, outward normals and source half-spaces before using the plan.
"""

from dataclasses import dataclass
import math


@dataclass(frozen=True)
class SeamCutBounds:
    x_min_mm: float
    x_max_mm: float
    y_min_mm: float
    y_max_mm: float
    z_min_mm: float
    z_max_mm: float


def _rectangle(corners, edge_length_mm, tolerance_mm):
    if len(corners) != 4:
        raise ValueError("Split seam requires rectangular mating faces with four corners.")
    if any(len(point) != 3 or any(not math.isfinite(value) for value in point)
           for point in corners):
        raise ValueError("The split seam contains invalid coordinates.")
    y_min, y_max = min(p[1] for p in corners), max(p[1] for p in corners)
    z_min, z_max = min(p[2] for p in corners), max(p[2] for p in corners)
    if (y_max - y_min <= tolerance_mm or z_max - z_min <= tolerance_mm
            or abs(z_max) > tolerance_mm
            or abs(y_min + edge_length_mm / 2) > tolerance_mm
            or abs(y_max - edge_length_mm / 2) > tolerance_mm):
        raise ValueError(
            "The split mating face must extend behind the selected face and span its full edge.")
    found = set()
    for x, y, z in corners:
        if abs(x) > tolerance_mm:
            raise ValueError("The mating faces must lie on the selected split plane.")
        y_side = 0 if abs(y - y_min) <= tolerance_mm else 1 if abs(y - y_max) <= tolerance_mm else None
        z_side = 0 if abs(z - z_min) <= tolerance_mm else 1 if abs(z - z_max) <= tolerance_mm else None
        if y_side is None or z_side is None or (y_side, z_side) in found:
            raise ValueError("Split seam requires rectangular mating faces with four distinct corners.")
        found.add((y_side, z_side))
    return y_min, y_max, z_min, z_max


def plan_seam_clearance(corners_a, corners_b, clearance_mm, edge_length_mm,
                        tolerance_mm=0.0001):
    """Return one full-interface slab, never a cut limited to hinge length.

    Local X points from A to B, Y follows the selected edge and Z points out of
    the selected faces. The seam is X=0; the rectangular mating faces extend
    inward in negative Z. The added Y/Z margin only avoids coplanar cutter ends.
    """
    for value in (clearance_mm, edge_length_mm, tolerance_mm):
        if (isinstance(value, bool) or not isinstance(value, (int, float))
                or not math.isfinite(value) or value <= 0):
            raise ValueError("Seam clearance, reference length and tolerance must be finite positive mm values.")
    if clearance_mm <= 2 * tolerance_mm:
        raise ValueError("Seam clearance is too small to establish a positive geometric gap.")
    bounds_a = _rectangle(corners_a, edge_length_mm, tolerance_mm)
    bounds_b = _rectangle(corners_b, edge_length_mm, tolerance_mm)
    if any(abs(a - b) > tolerance_mm for a, b in zip(bounds_a, bounds_b)):
        raise ValueError("Split seam requires matching rectangular mating faces on A and B.")
    margin = tolerance_mm * 10
    half_gap = clearance_mm / 2
    return SeamCutBounds(
        -half_gap, half_gap,
        min(bounds_a[0], bounds_b[0]) - margin,
        max(bounds_a[1], bounds_b[1]) + margin,
        min(bounds_a[2], bounds_b[2]) - margin,
        max(bounds_a[3], bounds_b[3]) + margin,
    )

"""Pure placement of one or more equal hinges along a selected straight edge.

Hinge length describes each body span; margins exclude pin overhang. Multiple
hinges use exact outer margins and equal inter-hinge gaps. One hinge is centred
inside the remaining interval and treats the two margins as minimums.
"""

from dataclasses import dataclass
import math

from .settings import HingeSettings


@dataclass(frozen=True)
class HingePlacement:
    """One zero-based placement along the edge's centred local Y axis."""

    index: int
    center_mm: float
    start_mm: float
    end_mm: float


@dataclass(frozen=True)
class HingeLayout:
    placements: tuple[HingePlacement, ...]
    edge_length_mm: float
    gap_mm: float


def _edge_length(value):
    try:
        valid = (not isinstance(value, bool) and isinstance(value, (int, float))
                 and math.isfinite(value) and value > 0)
    except OverflowError:
        valid = False
    if not valid:
        raise ValueError("Reference edge length must be a finite number greater than zero (mm).")
    return float(value)


def build_hinge_layout(settings, edge_length_mm):
    """Place validated equal hinge units, rejecting impossible or collapsed fits.

    A few floating-point ulps permit ordinary decimal boundary fits such as
    84.3 = 2*40 + 4.3. This is arithmetic roundoff, not a CAD clearance tolerance.
    Every produced interval and inter-unit gap must still be distinct.
    """
    if not isinstance(settings, HingeSettings):
        raise ValueError("Build the hinge layout from HingeSettings.")
    settings.validate()
    edge_length = _edge_length(edge_length_mm)
    half_edge = edge_length / 2.0
    left = -half_edge + settings.start_margin_mm
    right = half_edge - settings.end_margin_mm
    available = right - left
    if (not all(math.isfinite(value) for value in (left, right, available))
            or not right > left or half_edge <= 0):
        raise ValueError("Start and end margins leave no usable edge. Reduce the margins.")
    length = settings.length_mm
    count = settings.hinge_count
    roundoff = 8 * max(math.ulp(edge_length), math.ulp(length))
    if count == 1:
        if available + roundoff < length:
            raise ValueError("The hinge does not fit between the margins. Reduce hinge length or margins.")
        center = left / 2.0 + right / 2.0
        start, end = center - length / 2.0, center + length / 2.0
        if not end > start or start < left - roundoff or end > right + roundoff:
            raise ValueError("Hinge placement collapses at this numeric scale. Adjust length or margins.")
        return HingeLayout((HingePlacement(0, center, start, end),), edge_length, 0.0)

    occupied = count * length
    minimum_gap = settings.axial_gap_mm
    if settings.include_pin:
        minimum_gap += 2.0 * settings.pin_overhang_mm
    gap = (available - occupied) / (count - 1)
    if (not math.isfinite(occupied) or not math.isfinite(minimum_gap)
            or not math.isfinite(gap) or gap <= 0 or gap + roundoff < minimum_gap):
        raise ValueError(
            "The requested hinges do not fit. Reduce count, length, margins or pin overhang; "
            "each inter-hinge gap must accommodate both pin ends and an axial gap."
            if settings.include_pin else
            "The requested hinges do not fit. Reduce count, length or margins to leave axial gaps."
        ) from None
    # Preserve the requested minimum even when decimal subtraction rounds down.
    gap = max(gap, minimum_gap)
    stride = length + gap
    placements = []
    previous_end = None
    for index in range(count):
        start = left if index == 0 else left + index * stride
        end = right if index == count - 1 else start + length
        center = start / 2.0 + end / 2.0
        if (not all(math.isfinite(value) for value in (start, end, center))
                or not end > start or abs((end - start) - length) > roundoff
                or start < left - roundoff or end > right + roundoff
                or (previous_end is not None and (
                    not start > previous_end or start - previous_end + roundoff < minimum_gap))):
            raise ValueError("Hinge intervals or gaps collapse at this numeric scale. Adjust dimensions.")
        placements.append(HingePlacement(index, center, start, end))
        previous_end = end
    return HingeLayout(tuple(placements), edge_length, gap)

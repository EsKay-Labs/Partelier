"""Pure 45-degree edge-finish constraints and bounded box cutters (mm)."""

from dataclasses import dataclass
from itertools import product
import math


@dataclass(frozen=True)
class ChamferWedge:
    center_mm: tuple
    edge_axis: tuple
    tangent_axis: tuple
    normal_axis: tuple
    length_mm: float
    width_mm: float
    depth_mm: float


def validate_edge_finish(settings):
    if type(settings.chamfer_edges) is not bool:
        raise ValueError("Chamfer edges must be true or false.")
    if type(settings.fillet_edges) is not bool:
        raise ValueError("Fillet edges must be true or false.")
    if settings.chamfer_edges and settings.fillet_edges:
        raise ValueError("Choose either chamfer or fillet edge treatment.")
    if not (settings.chamfer_edges or settings.fillet_edges):
        return
    rounded = settings.fillet_edges
    label = "Fillet radius" if rounded else "Chamfer size"
    size = settings.fillet_radius_mm if rounded else settings.chamfer_size_mm
    radius = settings.barrel_diameter_mm / 2
    bore = (settings.pin_diameter_mm + settings.diametral_clearance_mm) / 2
    span = (settings.length_mm - (settings.knuckle_count - 1) * settings.axial_gap_mm) / settings.knuckle_count
    wall_radius = radius / math.sqrt(2) if settings.knuckle_profile == "square" else radius
    if not size < (wall_radius - bore) / 2:
        raise ValueError(f"{label} must be smaller than half the housing wall thickness.")
    if not size < span / 2:
        raise ValueError(f"{label} must be smaller than half each knuckle length.")
    contact_x = radius / 2 + size
    contact_height = (radius - wall_radius + max(0, contact_x - (wall_radius - size))
                      if settings.knuckle_profile == "square" else
                      radius * (1 - math.sqrt(max(0, 1 - (contact_x / radius) ** 2))))
    if not settings.leaf_thickness_mm > contact_height:
        raise ValueError(f"{label} removes the web-to-barrel contact. Reduce it or increase leaf thickness.")
    pin_limit = settings.pin_diameter_mm / (4 if rounded else 2)
    if settings.include_pin and not size < pin_limit:
        raise ValueError(f"{label} must be smaller than {'half the pin radius' if rounded else 'the pin radius'}.")
    separate = settings.output_mode == "separate"
    if separate:
        inner = radius + settings.leaf_barrel_clearance_mm
        width = settings.leaf_reach_mm - inner
        web_width = inner + min(width / 2, settings.leaf_thickness_mm) - radius / 2
        web_height = settings.leaf_thickness_mm
        if not size < min(width, settings.length_mm, settings.leaf_thickness_mm) / 2:
            raise ValueError(f"{label} must be smaller than half the leaf width, length and thickness.")
        if rounded and settings.leaf_profile == "rounded":
            raise ValueError("Fillet treatment rounds all leaf corners. Choose the flat leaf outline for this treatment.")
        if settings.leaf_profile == "rounded":
            corner = min(width / 4, settings.length_mm / 8, settings.leaf_thickness_mm / 2)
            if not size < corner:
                raise ValueError(f"{label} must be smaller than the rounded leaf corner radius.")
        if settings.screw_holes:
            lip_radius = settings.screw_diameter_mm / 2 + size
            half_spacing = settings.length_mm / 2 - settings.screw_end_margin_mm
            if not (lip_radius + size < min(width / 2, settings.screw_end_margin_mm)
                    and lip_radius < half_spacing):
                raise ValueError("Finished screw-hole entries must leave material at the leaf edges and between holes.")
    else:
        web_width = settings.leaf_reach_mm - radius / 2
        web_height = settings.leaf_thickness_mm + settings.attachment_overlap_mm
    if not size < min(web_width, span, web_height) / 2:
        raise ValueError(f"{label} must be smaller than half the attachment web dimensions.")


def box_chamfer_wedges(bounds, size, rounded_outer=None):
    """Plan twelve local cutters, or ten when two outer corners are rounded.

    Each cut's inner plane meets the adjacent faces at equal distance `size`
    from their sharp edge. The cutters are bounded to that edge's immediate
    vicinity; they are never applied to original or copied source geometry.
    rounded_outer=-1/+1 skips the two vertical outer X edges of a rounded leaf.
    """
    minima = (bounds.x_min_mm, bounds.y_min_mm, bounds.z_min_mm)
    maxima = (bounds.x_max_mm, bounds.y_max_mm, bounds.z_max_mm)
    lengths = tuple(high - low for low, high in zip(minima, maxima))
    if (isinstance(size, bool) or not isinstance(size, (int, float))
            or not math.isfinite(size) or not 0 < size < min(lengths) / 2
            or not all(math.isfinite(value) for value in minima + maxima)):
        raise ValueError("Chamfer requires finite box bounds and a size below half every dimension.")
    if rounded_outer not in (None, -1, 1):
        raise ValueError("Rounded outer side must be negative X, positive X, or absent.")
    cuts = []
    diagonal = math.sqrt(2)
    for along in range(3):
        across = [index for index in range(3) if index != along]
        edge_axis = tuple(1.0 if index == along else 0.0 for index in range(3))
        for signs in product((-1, 1), repeat=2):
            if along == 2 and rounded_outer is not None and signs[0] == rounded_outer:
                continue
            corner = [low / 2 + high / 2 for low, high in zip(minima, maxima)]
            normal = [0.0, 0.0, 0.0]
            for index, sign in zip(across, signs):
                corner[index] = minima[index] if sign == -1 else maxima[index]
                normal[index] = sign / diagonal
            # Tangent = normal cross edge; edge cross tangent = outward normal.
            tangent = (normal[1] * edge_axis[2] - normal[2] * edge_axis[1],
                       normal[2] * edge_axis[0] - normal[0] * edge_axis[2],
                       normal[0] * edge_axis[1] - normal[1] * edge_axis[0])
            center = tuple(value + direction * (2 * size - size / diagonal)
                           for value, direction in zip(corner, normal))
            dimensions = (lengths[along] + 2 * size, 4 * size, 4 * size)
            if (not all(math.isfinite(value) and value > 0 for value in dimensions)
                    or not all(math.isfinite(value) for value in center)):
                raise ValueError("Chamfer cutter dimensions overflow at this scale.")
            cuts.append(ChamferWedge(center, edge_axis, tangent, tuple(normal), *dimensions))
    return tuple(cuts)

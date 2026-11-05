"""Periodic cylindrical cut relief with explicit facet and overhang bounds.

The cylinder's axis is the print axis. Every side triangle is checked in both
axial directions, so either flat end can face the bed. The check concerns the
generated relief, not unsupported geometry elsewhere in the user's body.
"""
from dataclasses import dataclass
from functools import lru_cache
import math
from .settings import ANGLED_STYLES

MAX_FACES = 2500
MAX_SAG_MM = .04
FADE_SLOPE = .8


@dataclass(frozen=True)
class Plan:
    points_mm: tuple
    face_loops: tuple
    volume_mm3: float
    repeats: int
    effective_pitch_mm: float
    max_overhang_deg: float
    columns: int
    levels_mm: tuple
    radial_approximation_mm: float


def _triangle(value):
    return 1. - abs(2. * (value % 1.) - 1.)


def relief(style, u, z, pitch, angle_deg, height):
    """Unit-depth radial relief at one unwrapped coordinate; periodic in u."""
    slope = math.tan(math.radians(angle_deg)) / pitch
    v = z / pitch
    if style == 'straight':
        return _triangle(u)
    if style == 'flutes':
        return .5 - .5 * math.cos(2. * math.pi * u)
    if style == 'scallops':
        return math.sqrt(max(0., 1. - (2. * (u % 1.) - 1.) ** 2))
    if style == 'helical':
        return _triangle(u - z * slope)
    if style == 'chevron':
        return _triangle(u - abs(z - height / 2.) * slope)
    if style == 'waves':
        # The maximum lateral lean equals tan(angle), not the wave amplitude.
        return _triangle(u - slope * pitch / math.pi * math.sin(math.pi * z / pitch))
    if style == 'diamond':
        return max(_triangle(u + z * slope), _triangle(u - z * slope))
    if style == 'pyramids':
        return max(_triangle(u), _triangle(v))
    if style == 'rings':
        return _triangle(v)
    if style == 'dimples':
        du, dv = (u % 1.) - .5, (v % 1.) - .5
        return max(0., 1. - (du * du + dv * dv) / .42 ** 2)
    raise ValueError('Unsupported grip style.')


def _sub(a, b):
    return tuple(x - y for x, y in zip(a, b))


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _dot(a, b):
    return sum(x * y for x, y in zip(a, b))


def _finite_dimension(value, name, low, high):
    try:
        valid = type(value) in (int, float) and math.isfinite(value) and low <= value <= high
    except OverflowError:
        valid = False
    if not valid:
        raise ValueError(f'The cylinder {name} must be {low:g}–{high:g} mm.')


def plan(settings, radius_mm, height_mm):
    settings.validate()
    _finite_dimension(radius_mm, 'radius', 2., 150.)
    _finite_dimension(height_mm, 'height', 2., 200.)
    return _plan(settings, radius_mm, height_mm)


@lru_cache(maxsize=8)
def _plan(settings, radius_mm, height_mm):
    # Cache only immutable pure values, never native entities or preview objects.
    s = settings
    if radius_mm - s.depth_mm < 1.2:
        raise ValueError('Reduce Depth: the grip must retain at least a 1.2 mm core radius.')
    usable = height_mm - 2. * s.border_mm
    fade = s.depth_mm / FADE_SLOPE
    if usable < 2. * fade + .5:
        raise ValueError('Reduce Border or Depth, or select a taller cylinder for both supported end transitions.')
    circumference = 2. * math.pi * radius_mm
    repeats = max(3, round(circumference / s.pitch_mm))
    pitch = circumference / repeats
    # Match complete repeats exactly; never leave a partial motif at the seam.
    minimum_columns = math.ceil(math.pi / math.acos(radius_mm / (radius_mm + MAX_SAG_MM)))
    samples = 8 if s.style in ('flutes', 'scallops') else 4
    # Quarter phases include both crossed-ridge intersections and groove roots.
    # Arbitrary five/six-sample motifs make their sharp creases zigzag.
    samples = max(samples, 4 * math.ceil(minimum_columns / repeats / 4))
    columns = repeats * samples
    factor = 1. / math.cos(math.pi / columns)
    approximation = radius_mm * (factor - 1.)
    # A min-envelope with linear fades retains the maximum of constituent
    # Lipschitz bounds, unlike multiplying texture by a fade (summed slopes).
    if s.style in ('straight', 'flutes', 'scallops'):
        derivative = 0.
        axial_step = usable
    elif s.style in ANGLED_STYLES:
        derivative = 2. * math.tan(math.radians(s.angle_deg)) / pitch
        # Waves retain their own axial frequency even at a very small lean.
        # Sampling only at half-wave zeros would erase the central waveform.
        axial_step = pitch / 4. if s.style == 'waves' else pitch / max(samples * math.tan(math.radians(s.angle_deg)), 1.)
    elif s.style == 'dimples':
        derivative = 2. / (.42 * pitch)
        axial_step = pitch / 4.
    else:
        derivative = 2. / pitch
        axial_step = pitch / 4.
    if s.depth_mm * derivative * factor > .98:
        raise ValueError('This Depth/Spacing/Angle exceeds the 45° upright-print slope. Reduce Depth or Angle, or increase Spacing.')
    low, high = s.border_mm, height_mm - s.border_mm
    steps = max(1, math.ceil(usable / axial_step))
    if columns * (steps + 4) + 2 > MAX_FACES + 2 * columns:
        raise ValueError('This grip is too dense for a responsive preview. Increase Spacing or select a shorter cylinder (2,500 face limit).')
    levels = {0., low, low + fade, high - fade, high, height_mm}
    # Preserve motif extrema instead of stretching the sample spacing across
    # the available height; the last partial row ends at the upper fade.
    levels.update(low + axial_step * i for i in range(1, steps) if low + axial_step * i < high)
    if s.style == 'chevron':
        levels.add(height_mm / 2.)
    levels = tuple(sorted(levels))
    # Near-equal rings can produce degenerate native edges; merge only numerical
    # duplicates, never change an intended geometric spacing.
    levels = tuple(z for i, z in enumerate(levels) if i == 0 or z - levels[i - 1] > 1e-8)
    if columns * (len(levels) - 1) + 2 > MAX_FACES:
        raise ValueError('This grip is too dense for a responsive preview. Increase Spacing or select a shorter cylinder (2,500 face limit).')
    def radius_at(u, z):
        edge_depth = max(0., min(z - low, high - z) * FADE_SLOPE)
        depth = min(s.depth_mm * relief(s.style, u, z - low, pitch, s.angle_deg, usable), edge_depth)
        return (radius_mm - depth) * factor

    points = []
    for z in levels:
        for j in range(columns):
            # Rotate the complete phase-aligned tessellation. Shifting just
            # field samples would lose sharp creases at non-quarter phases.
            theta = 2. * math.pi * j / columns - math.radians(s.phase_deg)
            u = j * repeats / columns
            # Circumscribed zero-depth rings preserve a truly round source
            # collar after the retained envelope is intersected with the source.
            r = radius_at(u, z)
            points.append((r * math.cos(theta), r * math.sin(theta), z))
    faces = [tuple(reversed(range(columns))), tuple((len(levels) - 1) * columns + j for j in range(columns))]
    max_slope = 0.
    for i in range(len(levels) - 1):
        for j in range(columns):
            a = i * columns + j
            b = i * columns + (j + 1) % columns
            c = (i + 1) * columns + (j + 1) % columns
            d = (i + 1) * columns + j
            # Follow the actual valley/ridge diagonal of this unwrapped cell.
            # One fixed triangulation cuts across half of the diamond creases.
            mid = radius_at((j + .5) * repeats / columns, (levels[i] + levels[i + 1]) / 2.)
            radial = {k: math.hypot(points[k][0], points[k][1]) for k in (a, b, c, d)}
            ac_error = abs(mid - (radial[a] + radial[c]) / 2.)
            bd_error = abs(mid - (radial[b] + radial[d]) / 2.)
            triangles = ((a, b, c), (a, c, d)) if ac_error <= bd_error + 1e-10 else ((a, b, d), (b, c, d))
            for face in triangles:
                p, q, r = (points[k] for k in face)
                normal = _cross(_sub(q, p), _sub(r, p))
                horizontal = math.hypot(normal[0], normal[1])
                if horizontal < 1e-10:
                    raise ValueError('The grip contains a degenerate side facet.')
                slope = abs(normal[2]) / horizontal
                max_slope = max(max_slope, slope)
                if slope > 1. + 1e-8:
                    raise ValueError('A grip facet exceeds 45° for upright printing. Reduce Depth or Angle, or increase Spacing.')
            normal = _cross(_sub(points[b], points[a]), _sub(points[c], points[a]))
            coplanar = abs(_dot(normal, _sub(points[d], points[a]))) <= 1e-8 * math.sqrt(_dot(normal, normal))
            faces.extend(((a, b, c, d),) if coplanar else triangles)
    if len(faces) > MAX_FACES:
        raise ValueError('This grip is too dense for a responsive preview. Increase Spacing or select a shorter cylinder (2,500 face limit).')
    # Explicit manifold orientation and signed volume, independently of Fusion.
    edges = {}
    for face in faces:
        for a, b in zip(face, face[1:] + face[:1]):
            edges.setdefault(tuple(sorted((a, b))), []).append(a > b)
    if any(sorted(uses) != [False, True] for uses in edges.values()):
        raise ValueError('The grip envelope is not closed.')
    origin = points[0]
    volume = math.fsum(_dot(_sub(points[face[0]], origin), _cross(_sub(points[face[k]], origin), _sub(points[face[k + 1]], origin))) / 6.
                      for face in faces for k in range(1, len(face) - 1))
    if not math.isfinite(volume) or volume <= 0:
        raise ValueError('The grip envelope has invalid volume.')
    return Plan(tuple(points), tuple(faces), volume, repeats, pitch,
                math.degrees(math.atan(max_slope)), columns, levels, approximation)

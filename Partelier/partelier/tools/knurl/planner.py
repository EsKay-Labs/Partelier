"""Bounded exact-CAD groove layout and conservative upright-print bounds."""
from dataclasses import dataclass
from functools import lru_cache
import math

MAX_REPEATS = 64
MAX_CUTTERS = 128


@dataclass(frozen=True)
class Plan:
    repeats: int
    effective_pitch_mm: float
    outer_radius_mm: float
    root_radius_mm: float
    half_width_mm: float
    row_centres_mm: tuple
    cutter_count: int
    max_overhang_deg: float


def plan(settings, radius_mm, height_mm):
    settings.validate()
    for value, low, high, name in ((radius_mm, 2., 150., 'radius'), (height_mm, 2., 200., 'height')):
        try:valid = type(value) in (int, float) and math.isfinite(value) and low <= value <= high
        except OverflowError:valid = False
        if not valid:raise ValueError(f'The cylinder {name} must be {low:g}–{high:g} mm.')
    return _plan(settings, radius_mm, height_mm)


@lru_cache(maxsize=8)
def _plan(s, radius, height):
    if height - 2*s.border_mm < .5:
        raise ValueError('Reduce Border or select a taller cylinder.')
    outer = radius + (s.depth_mm if s.mode == 'emboss' else 0.)
    root = outer - s.depth_mm
    if root < 1.2:raise ValueError('Reduce Depth: retain at least a 1.2 mm core radius.')
    repeats = max(3, round(2*math.pi*outer/s.pitch_mm))
    if s.style=='diamond' and (s.grip_fillet_mm or s.groove_fillet_mm):
        repeats=max(4,2*round(repeats/2))
    if repeats > MAX_REPEATS:
        raise ValueError('This grip is too dense. Increase Spacing (maximum 64 repeats).')
    pitch = 2*math.pi*outer/repeats
    half = pitch*.25
    rows = tuple(i*pitch for i in range(math.ceil(height/pitch)+1))
    angled = s.style in ('diamond','helical','chevron','waves')
    slope = s.depth_mm/half * math.tan(math.radians(s.angle_deg)) if angled else 0.
    if s.style=='diamond' and s.groove_fillet_mm:
        slope=(s.depth_mm+.001)/half*math.tan(math.radians(s.angle_deg))
    if s.style == 'waves':
        from .wave_profile import maximum_slope
        slope=maximum_slope(outer,root,half,s.depth_mm,height,pitch,s.angle_deg)
    count = repeats*(2 if s.style in ('diamond','chevron') and s.angle_deg else 1)
    if s.style in ('rings','pyramids'):
        slope = s.depth_mm/half
        count = len(rows)+(repeats if s.style=='pyramids' else 0)
    elif s.style == 'dimples':
        # Spherical cap depth d and halfwidth w: q=(w²+d²)/(2d).
        # At the outer cylinder, q-d is a lower radial normal bound.
        half = pitch*.35
        sphere = (half*half+s.depth_mm*s.depth_mm)/(2*s.depth_mm)
        if sphere <= s.depth_mm:
            raise ValueError('Increase Spacing or reduce Depth for the dimple profile.')
        slope = half/(sphere-s.depth_mm)
        count = repeats*len(rows)
    if count > MAX_CUTTERS:
        raise ValueError('This grip is too dense for a responsive preview. Increase Spacing or use a shorter face (maximum 128 grooves).')
    if slope > 1.+1e-8:
        raise ValueError('This Depth/Spacing/Angle exceeds the 45° upright-print slope. Reduce Depth or Angle, or increase Spacing.')
    return Plan(repeats,pitch,outer,root,half,rows,count,math.degrees(math.atan(slope)))

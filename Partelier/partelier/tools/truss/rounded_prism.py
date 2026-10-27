"""Truss adapter for the shared exact multi-loop rounded-prism builder."""

from ..patterns.fillet import Profile
from ..patterns.rounded_prism import create as create_rounded


def create(frame,layout,low,high):
    profiles=tuple(Profile(polygon,hole.corners,hole.radius_mm,hole.area_mm2,
        hole.maximum_radius_mm,hole.interior_point) for polygon,hole in zip(layout.holes,layout.rounded_holes))
    return create_rounded(frame,layout.outer,profiles,low,high)

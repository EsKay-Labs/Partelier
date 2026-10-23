"""Rounded detent on a flexible beam, with a matching bounded socket."""

from dataclasses import dataclass, replace
import math

from .planner import BoxBounds, SnapFitUnit


@dataclass(frozen=True)
class BallGeometry:
    center_mm: tuple
    radius_mm: float
    socket_radius_mm: float
    receiver_cover: BoxBounds


@dataclass(frozen=True)
class BallUnit(SnapFitUnit):
    ball_geometry: object = None


def adapt_unit(unit, settings):
    r, c = settings.ball_radius_mm, settings.clearance_mm
    center = (r - settings.hook_depth_mm, unit.center_y_mm, settings.reach_mm - r)
    socket = r + c
    xmin = center[0] - socket
    top = (center[2] + math.sqrt(2) * socket - center[0]
           if settings.print_support else center[2] + socket)
    cover = BoxBounds(xmin-c, 0, center[1]-socket-c, center[1]+socket+c,
                      center[2]-socket-c, top+c)
    geometry = BallGeometry(center, r, socket, cover)
    return BallUnit(unit.center_y_mm, unit.root, unit.beam, unit.hook,
                    unit.receiver, unit.arms, unit.root_support, unit.root_cover, geometry)


def nose_body(manager, frame, unit):
    from ..hinge import fusion as adapter
    ball = unit.ball_geometry
    body = manager.createSphere(adapter._point(frame, *ball.center_mm), ball.radius_mm / 10)
    adapter._require_body(body, "Fusion could not create the rounded detent.")
    return body


def receiver_body(manager, frame, unit, settings):
    from ..hinge import fusion as adapter
    from ..hinge.support import _prism
    _, fusion = adapter._api()
    ball = unit.ball_geometry
    x, y, z = ball.center_mm
    radius = ball.socket_radius_mm
    body = manager.createSphere(adapter._point(frame, x, y, z), radius / 10)
    adapter._require_body(body, "Fusion could not create the detent socket.")
    if settings.print_support:
        low, high = x-radius, x+radius
        intercept = z + math.sqrt(2) * radius - x
        roof = _prism(manager, frame, ((low, z), (high, z),
                                      (high, high+intercept), (low, low+intercept)),
                      y-radius, y+radius)
        adapter._boolean(manager, body, roof, fusion.BooleanTypes.UnionBooleanType,
                         "The 45-degree detent roof did not join its socket.")
    return body

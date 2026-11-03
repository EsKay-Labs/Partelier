"""Small deterministic layouts, separated from the Fusion adapter."""
from dataclasses import dataclass
import math


@dataclass(frozen=True)
class Plan:
    family: str
    names: tuple
    rail_profile: tuple = ()
    clearance_profile: tuple = ()
    knuckles: tuple = ()


def plan(settings):
    settings.validate()
    s=settings;w=s.width_mm;h=s.height_mm;t=s.wall_mm;g=s.clearance_mm
    if s.family in ('slider','dovetail'):
        inset=h*math.tan(math.radians(s.angle_deg)) if s.family=='dovetail' else 0
        profile=((-w/2+inset,t), (w/2-inset,t),(w/2,t+h),(-w/2,t+h))
        # Offset sloped sides by the requested perpendicular clearance.
        side=g/math.cos(math.radians(s.angle_deg)) if inset else g
        clearance=((-w/2+inset-side+g*inset/h,t-g),(w/2-inset+side-g*inset/h,t-g),
                   (w/2+side+g*inset/h,t+h+g),(-w/2-side-g*inset/h,t+h+g))
        return Plan(s.family,('Guide rail','Sliding carriage'),profile,clearance)
    if s.family=='bayonet': return Plan(s.family,('Bayonet male','Bayonet sleeve'))
    if s.family=='clevis': return Plan(s.family,('Clevis fork','Clevis tongue','Clevis pin'))
    if s.family=='pip_louver':return Plan(s.family,('Captive louver frame',)+tuple(f'Captive vane {i+1}' for i in range(s.count)))
    if s.family=='linked_louver':return Plan(s.family,('Split frame back','Split frame front')+tuple(f'Linked vane {i+1}' for i in range(s.count))+('Common crank link',))
    if s.family=='swing_hinge':
        from .swing_hinge import NAMES
        return Plan(s.family,NAMES)
    if s.family=='parallel_lift':return Plan(s.family,('Fixed lift plate','Parallel moving plate','Lift arm A','Lift arm B','Fixed spacer A','Fixed spacer B','Moving spacer A','Moving spacer B'))
    span=s.length_mm/s.count
    knuckles=tuple((i%2,i*span+g/2,(i+1)*span-g/2) for i in range(s.count))
    names=('Captive hinge A','Captive hinge B') if s.family=='pip_hinge' else ('Hinge A','Hinge B','Hinge pin')
    return Plan(s.family,names,knuckles=knuckles)

"""Bounded scroll housing: millimetre planning and detached native solids."""
from dataclasses import dataclass
import math


@dataclass(frozen=True)
class VolutePlan:
    inner:tuple
    outer:tuple
    throat_x:float
    exit_x:float
    exit_y:float
    wall:float
    cavity_low:float
    cavity_high:float
    floor_low:float
    lid_low:float
    lid_high:float
    inlet_radius:float
    bosses:tuple
    boss_radius:float
    segments:int


def plan(settings,rotor_low,rotor_high):
    settings.validate()
    if settings.style!='blower' or settings.output!='blower_housing':raise ValueError('Select a blower with volute housing.')
    wall=settings.volute_wall_mm;inner_radius=settings.diameter_mm/2+settings.tip_gap_mm
    maximum=inner_radius+settings.volute_growth_mm+wall
    # Target 0.02 mm chord sag; the 256-segment cap stays below 0.03 mm.
    # The radial inflation
    # conservatively preserves minimum rotor clearance even between vertices.
    count=max(64,min(256,math.ceil(math.pi/math.acos(1-.02/maximum))))
    factor=1/math.cos(math.pi/count)
    r0=inner_radius*factor;r1=r0+settings.volute_growth_mm
    def outline(add):
        return tuple(((r0+settings.volute_growth_mm*i/count+add)*math.cos(2*math.pi*i/count),(r0+settings.volute_growth_mm*i/count+add)*math.sin(2*math.pi*i/count)) for i in range(count+1))
    inner,outer=outline(0),outline(wall)
    cavity_low=rotor_low-settings.axial_clearance_mm;cavity_high=rotor_high+settings.axial_clearance_mm
    boss_radius=settings.mount_hole_mm/2+wall
    bosses=tuple(((r0+settings.volute_growth_mm*angle/(2*math.pi)+wall+boss_radius-wall/2)*math.cos(angle),(r0+settings.volute_growth_mm*angle/(2*math.pi)+wall+boss_radius-wall/2)*math.sin(angle)) for angle in (math.pi/4,3*math.pi/4,5*math.pi/4,7*math.pi/4)) if settings.volute_mounts else ()
    lid_low=cavity_high+settings.volute_lid_gap_mm
    return VolutePlan(inner,outer,r0,r1,-r1-settings.volute_outlet_mm,wall,cavity_low,cavity_high,cavity_low-wall,lid_low,lid_low+wall,(settings.volute_inlet_mm or settings.hub_diameter_mm+2*wall)/2,bosses,boss_radius,count)


def prism_plan(polygon,low,high):
    """Simple CCW non-convex polygon prism, with explicit shared closed topology."""
    from ..patterns.perforated_prism import Plan
    polygon=tuple(polygon);n=len(polygon)
    if not 3<=n<=257 or not high>low or any(not math.isfinite(v) for p in polygon for v in p):raise ValueError('Invalid scroll contour.')
    area=math.fsum(a[0]*b[1]-a[1]*b[0] for a,b in zip(polygon,polygon[1:]+polygon[:1]))/2
    if area<=0:raise ValueError('Scroll contour is reversed.')
    points=tuple((x,y,low) for x,y in polygon)+tuple((x,y,high) for x,y in polygon)
    faces=((tuple(reversed(range(n))),),(tuple(range(n,2*n)),))+tuple(((i,(i+1)%n,(i+1)%n+n,i+n),) for i in range(n))
    return Plan(points,faces,area*(high-low))


def build(manager,settings,rotor_plan,core,native):
    from . import fusion as fan
    from ..patterns import perforated_prism
    p=plan(settings,rotor_plan.z_min_mm,rotor_plan.z_max_mm)
    def prism(poly,low,high):return perforated_prism.create_plan(prism_plan(poly,low,high))
    def box(x1,x2,y1,y2,low,high):return fan._box(manager,core,x2-x1,y2-y1,high-low,((x1+x2)/2,(y1+y2)/2,(low+high)/2))
    def union(a,b):fan._boolean(manager,a,b,native.BooleanTypes.UnionBooleanType,'Could not join the scroll outlet or mounting boss.')
    def cut(a,b):fan._boolean(manager,a,b,native.BooleanTypes.DifferenceBooleanType,'A volute opening disconnected its housing. Review the dimensions.')
    def outer(low,high):
        body=prism(p.outer,low,high)
        union(body,box(p.throat_x-p.wall,p.exit_x+p.wall,p.exit_y,p.wall,low,high))
        for center in p.bosses:union(body,fan._cylinder(manager,core,p.boss_radius,low,high,center))
        return body
    housing=outer(p.floor_low,p.cavity_high)
    cavity=prism(p.inner,p.cavity_low,p.cavity_high+.1)
    union(cavity,box(p.throat_x,p.exit_x,p.exit_y-1,.1,p.cavity_low,p.cavity_high+.1))
    cut(housing,cavity)
    cut(housing,fan._cylinder(manager,core,settings.volute_motor_mm/2,p.floor_low-.1,p.cavity_low+.1))
    lid=outer(p.lid_low,p.lid_high)
    cut(lid,fan._cylinder(manager,core,p.inlet_radius,p.lid_low-.1,p.lid_high+.1))
    for center in p.bosses:
        cut(housing,fan._cylinder(manager,core,settings.mount_hole_mm/2,p.floor_low-.1,p.cavity_high+.1,center))
        cut(lid,fan._cylinder(manager,core,settings.mount_hole_mm/2,p.lid_low-.1,p.lid_high+.1,center))
    return housing,lid,p

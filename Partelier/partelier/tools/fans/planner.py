"""Bounded smooth section control polygons for one blade, in millimetres."""

from dataclasses import dataclass
import math

K=.5522847498307936
UNIT=((-1,0),(-1,K),(-K,1),(0,1),(K,1),(1,K),(1,0),(1,-K),(K,-1),(0,-1),(-K,-1),(-1,-K),(-1,0))
KNOTS=(0,0,0,0,1,1,1,2,2,2,3,3,3,4,4,4,4)


@dataclass(frozen=True)
class Section:
    radius_mm:float
    axis_radius_mm:float
    sweep_deg:float
    chord_mm:float
    angle_deg:float
    points_mm:tuple


@dataclass(frozen=True)
class Plan:
    sections:tuple
    blade_count:int
    z_min_mm:float
    z_max_mm:float
    minimum_sector_gap_deg:float


def blend(root,middle,tip,u):
    # Two cubic smoothstep intervals retain all three user stations exactly.
    t=u*2 if u<=.5 else (u-.5)*2;t=t*t*(3-2*t)
    return root+(middle-root)*t if u<=.5 else middle+(tip-middle)*t


def bezier_values(points):
    values=[points[0],points[-1]]
    a=-points[0]+3*points[1]-3*points[2]+points[3]
    b=2*(points[0]-2*points[1]+points[2]);c=points[1]-points[0]
    roots=[]
    if abs(a)<1e-12:
        if abs(b)>1e-12:roots=[-c/b]
    elif b*b-4*a*c>=0:
        disc=math.sqrt(max(0,b*b-4*a*c));roots=[(-b-disc)/(2*a),(-b+disc)/(2*a)]
    for t in roots:
        if 0<t<1:values.append((1-t)**3*points[0]+3*(1-t)**2*t*points[1]+3*(1-t)*t*t*points[2]+t**3*points[3])
    return values


def extrema(control,index):
    values=[value for start in (0,3,6,9) for value in bezier_values([p[index] for p in control[start:start+4]])]
    return min(values),max(values)


def _contour(chord,thickness,camber,angle):
    beta=math.radians(angle);co,si=math.cos(beta),math.sin(beta)
    points=[]
    for index,(x,z) in enumerate(UNIT):
        # Equal camber on each middle endpoint and its two handles preserves
        # G1 continuity across the four cubic arcs (pointwise warping does not).
        lift=camber*chord if index in (2,3,4,8,9,10) else 0.
        y=x*chord/2;z=z*thickness/2+lift
        points.append((y*co-z*si,y*si+z*co))
    return tuple(points)


def outline_chord(points,u):
    if len(points)<4 or len(points)>256:raise ValueError('Use one simple closed sketch outline with 4–256 sampled points.')
    xs=[p[0] for p in points];left,right=min(xs),max(xs)
    if right-left<1:raise ValueError('Sketch outline must span at least 1 mm horizontally.')
    x=left+u*(right-left);crossings=[]
    for a,b in zip(points,points[1:]+points[:1]):
        if abs(a[0]-b[0])<1e-9:
            if abs(x-a[0])<1e-7:crossings.extend((a[1],b[1]))
        elif min(a[0],b[0])-1e-8<=x<=max(a[0],b[0])+1e-8:
            crossings.append(a[1]+(b[1]-a[1])*(x-a[0])/(b[0]-a[0]))
    values=[]
    for value in sorted(crossings):
        if not values or abs(value-values[-1])>1e-5:values.append(value)
    if len(values)!=2 or values[1]-values[0]<.01:raise ValueError('Sketch outline needs one chord at every span, with finite-width root and tip ends.')
    return values[1]-values[0],(values[0]+values[1])/2,right-left


def plan(settings,outline=()):
    settings.validate()
    if settings.output=='hub_test':return Plan((),0,-settings.hub_height_mm/2,settings.hub_height_mm/2,360)
    if settings.outline_mode=='sketch' and not outline:raise ValueError('Pick one closed blade outline sketch profile, or choose Generated outline.')
    root=settings.hub_diameter_mm/2-.8;tip=settings.diameter_mm/2
    if root<=1:raise ValueError('Increase Hub diameter to attach the blades.')
    hand=1 if settings.rotation=='ccw' else -1
    sections=[];minimum=360;low=-settings.hub_height_mm/2;high=-low
    for i in range(9):
        u=i/8;limit=root+(tip-root)*u
        chord=blend(settings.root_chord_mm,settings.mid_chord_mm,settings.tip_chord_mm,u)
        offset=0.
        if settings.outline_mode=='sketch':
            width,center,span=outline_chord(tuple(outline),u)
            scale=(tip-root)/span*settings.outline_scale_percent/100
            chord=width*scale;offset=center*scale
        thickness=settings.root_thickness_mm+(settings.tip_thickness_mm-settings.root_thickness_mm)*u
        if chord<thickness*1.67:raise ValueError('The sketch/section chord is too narrow for Blade thickness. Increase its width or reduce thickness.')
        twist=blend(settings.root_angle_deg,settings.mid_angle_deg,settings.tip_angle_deg,u)
        def shape(radius):
            beta=math.degrees(math.atan2(settings.pitch_mm,2*math.pi*radius)) if settings.pitch_mode=='pitch' else twist
            contour=_contour(chord,thickness,settings.camber_percent/100,beta)
            ylo,yhi=extrema(contour,0);needed=max(abs(ylo+offset),abs(yhi+offset))
            return beta,contour,math.hypot(radius,needed)
        a,b=max(.05,root*.01),limit
        if shape(a)[2]>=limit:raise ValueError('Root chord is too wide for the hub. Increase Hub diameter or reduce Root chord / sketch width.')
        for _ in range(40):
            mid=(a+b)/2
            if shape(mid)[2]>limit:b=mid
            else:a=mid
        radius=(a+b)/2;beta,contour,_=shape(radius)
        if beta>80:raise ValueError('Pitch creates a root angle above 80°. Reduce Pitch or enlarge the hub.')
        if i==0 and radius<=(settings.shaft_diameter_mm+settings.shaft_clearance_mm)/2+.5:
            raise ValueError('Blade root reaches the shaft hole. Enlarge Hub or reduce Root chord.')
        theta=math.radians(hand*settings.sweep_deg*u*u);co,si=math.cos(theta),math.sin(theta)
        control=tuple((radius*co-hand*(y+offset)*si,radius*si+hand*(y+offset)*co,z) for y,z in contour)
        zlo,zhi=extrema(contour,1);low=min(low,zlo);high=max(high,zhi)
        ylo,yhi=extrema(contour,0)
        gap=360/settings.blade_count-math.degrees(math.atan2(yhi+offset,radius)-math.atan2(ylo+offset,radius))
        if limit>settings.hub_diameter_mm/2+settings.root_fillet_mm:
            minimum=min(minimum,gap)
            if gap<.5:raise ValueError('Blades are too wide for this count. Reduce chord/count or enlarge the hub/rotor.')
        sections.append(Section(limit,radius,math.degrees(theta),chord,beta,control))
    if settings.style=='ring':
        low=min(low,-settings.ring_height_mm/2);high=max(high,settings.ring_height_mm/2)
    if settings.output in ('rotor_frame','rotor_guard') and high-low+2*settings.axial_clearance_mm>settings.frame_depth_mm:
        raise ValueError(f'Blade envelope needs at least {high-low+2*settings.axial_clearance_mm:.1f} mm Frame depth including axial clearance. Increase depth or reduce twist/chord.')
    return Plan(tuple(sections),settings.blade_count,low,high,minimum)


def stroke(section,steps=12):
    result=[];p=section.points_mm
    for start in (0,3,6,9):
        a,b,c,d=p[start:start+4]
        for i in range(steps):
            t=i/steps
            result.append(tuple((1-t)**3*x+3*(1-t)**2*t*y+3*(1-t)*t*t*z+t**3*w for x,y,z,w in zip(a,b,c,d)))
    return tuple(result)

"""Exact tangent arcs inside convex truss windows; millimetres, no CAD imports."""

from dataclasses import dataclass
import math


@dataclass(frozen=True)
class Corner:
    start: tuple
    end: tuple
    middle: tuple
    center: tuple
    turn_rad: float


@dataclass(frozen=True)
class RoundedWindow:
    corners: tuple
    radius_mm: float
    area_mm2: float
    maximum_radius_mm: float
    interior_point: tuple


def window(polygon,radius):
    """Round every convex corner with an exact radius, never silently clamp."""
    polygon=tuple(tuple(p) for p in polygon)
    if (len(polygon)!=3 or any(len(p)!=2 for p in polygon)
            or any(isinstance(v,bool) or not isinstance(v,(float,int)) or not math.isfinite(v) for p in polygon for v in p)
            or isinstance(radius,bool) or not isinstance(radius,(float,int)) or not math.isfinite(radius) or radius<=0):
        raise ValueError('A truss junction fillet needs a positive finite radius and a triangular window.')
    reference=polygon[0]
    area=math.fsum((a[0]-reference[0])*(b[1]-reference[1])-(a[1]-reference[1])*(b[0]-reference[0])
        for a,b in zip(polygon,polygon[1:]+polygon[:1]))/2
    if area<=1e-10:raise ValueError('The truss window must have a positive counterclockwise area.')
    lengths=tuple(math.dist(a,b) for a,b in zip(polygon,polygon[1:]+polygon[:1]))
    values=[]
    for index,point in enumerate(polygon):
        previous,following=polygon[index-1],polygon[(index+1)%len(polygon)]
        before,after=lengths[index-1],lengths[index]
        if min(before,after)<1e-5:raise ValueError('A truss window edge has collapsed.')
        u=tuple((a-b)/before for a,b in zip(previous,point));v=tuple((a-b)/after for a,b in zip(following,point))
        cross=-(u[0]*v[1]-u[1]*v[0]);dot=math.fsum(a*b for a,b in zip(u,v))
        if cross<=1e-12:raise ValueError('Only convex triangular truss windows support junction fillets.')
        angle=math.atan2(cross,dot);half=angle/2;cot=1/math.tan(half)
        values.append((point,u,v,half,cot))
    maximum=min(lengths[i]/(values[i][4]+values[(i+1)%len(values)][4]) for i in range(len(values)))
    # Require distinct tangent points and straight portions for robust BRep loops.
    if radius>=maximum or any(lengths[i]-radius*(values[i][4]+values[(i+1)%len(values)][4])<1e-4 for i in range(len(values))):
        raise ValueError(f'Junction fillet is too large for the truss windows. Use less than {maximum:.4g} mm, reduce Bays or increase the plate size. Your radius was not changed.')
    corners=[];removed=[]
    for point,u,v,half,cot in values:
        distance=radius*cot
        start=tuple(p+d*distance for p,d in zip(point,u));end=tuple(p+d*distance for p,d in zip(point,v))
        bisector=tuple(a+b for a,b in zip(u,v));length=math.hypot(*bisector)
        direction=tuple(value/length for value in bisector)
        center=tuple(p+d*radius/math.sin(half) for p,d in zip(point,direction))
        middle=tuple(c-d*radius for c,d in zip(center,direction))
        if min(math.dist(start,end),math.dist(start,middle),math.dist(middle,end))<1e-5:
            raise ValueError('Junction fillet is too small to create distinct arc points. Increase the radius, or use 0 for sharp corners.')
        turn=math.pi-2*half
        corners.append(Corner(start,end,middle,center,turn));removed.append(radius*radius*(cot-turn/2))
    rounded_area=area-math.fsum(removed)
    if not 0<rounded_area<area:raise ValueError('The rounded truss window has an invalid area.')
    perimeter=math.fsum(lengths)
    interior=tuple(math.fsum(p[axis]*lengths[(i+1)%3] for i,p in enumerate(polygon))/perimeter for axis in (0,1))
    return RoundedWindow(tuple(corners),float(radius),rounded_area,maximum,interior)

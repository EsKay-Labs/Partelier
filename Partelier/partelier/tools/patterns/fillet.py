"""Exact bounded convex-cell corner arcs; chart millimetres, no CAD imports."""

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
class Profile:
    polygon_mm: tuple
    corners: tuple
    radius_mm: float
    area_mm2: float
    maximum_radius_mm: float
    interior_point: tuple


def profile(polygon,radius):
    """Round every convex corner with an exact radius, never silently clamp."""
    polygon=tuple(tuple(p) for p in polygon)
    if (not 3<=len(polygon)<=128 or any(len(p)!=2 for p in polygon)
            or any(isinstance(v,bool) or not isinstance(v,(float,int)) or not math.isfinite(v) for p in polygon for v in p)
            or isinstance(radius,bool) or not isinstance(radius,(float,int)) or not math.isfinite(radius) or radius<=0):
        raise ValueError('Cell fillet needs a positive finite radius and a convex polygon with 3–128 corners.')
    reference=polygon[0]
    area=math.fsum((a[0]-reference[0])*(b[1]-reference[1])-(a[1]-reference[1])*(b[0]-reference[0])
        for a,b in zip(polygon,polygon[1:]+polygon[:1]))/2
    if area<=1e-10:raise ValueError('The cell contour must have a positive counterclockwise area.')
    lengths=tuple(math.dist(a,b) for a,b in zip(polygon,polygon[1:]+polygon[:1]))
    for i,(a,b) in enumerate(zip(polygon,polygon[1:]+polygon[:1])):
        for j,p in enumerate(polygon):
            if j in (i,(i+1)%len(polygon)):continue
            if (b[0]-a[0])*(p[1]-a[1])-(b[1]-a[1])*(p[0]-a[0])<=1e-10:
                raise ValueError('Cell fillets need a strictly convex contour without crossing or flat corners.')
    values=[]
    for index,point in enumerate(polygon):
        previous,following=polygon[index-1],polygon[(index+1)%len(polygon)]
        before,after=lengths[index-1],lengths[index]
        if min(before,after)<1e-5:raise ValueError('A cell edge has collapsed.')
        u=tuple((a-b)/before for a,b in zip(previous,point));v=tuple((a-b)/after for a,b in zip(following,point))
        cross=-(u[0]*v[1]-u[1]*v[0]);dot=math.fsum(a*b for a,b in zip(u,v))
        if cross<=1e-12:raise ValueError('Only convex cell contours support perimeter fillets.')
        angle=math.atan2(cross,dot);half=angle/2;cot=1/math.tan(half)
        values.append((point,u,v,half,cot))
    maximum=min(lengths[i]/(values[i][4]+values[(i+1)%len(values)][4]) for i in range(len(values)))
    # Require distinct tangent points and straight portions for robust BRep loops.
    if radius>=maximum or any(lengths[i]-radius*(values[i][4]+values[(i+1)%len(values)][4])<1e-4 for i in range(len(values))):
        raise ValueError(f'Cell fillet is too large. Use less than {maximum:.4g} mm or increase Cell size. Your radius was not changed.')
    corners=[];removed=[]
    for point,u,v,half,cot in values:
        distance=radius*cot
        start=tuple(p+d*distance for p,d in zip(point,u));end=tuple(p+d*distance for p,d in zip(point,v))
        bisector=tuple(a+b for a,b in zip(u,v));length=math.hypot(*bisector)
        direction=tuple(value/length for value in bisector)
        center=tuple(p+d*radius/math.sin(half) for p,d in zip(point,direction))
        middle=tuple(c-d*radius for c,d in zip(center,direction))
        if min(math.dist(start,end),math.dist(start,middle),math.dist(middle,end))<1e-5:
            raise ValueError('Cell fillet is too small to create distinct arc points. Increase the radius, or use 0 for sharp corners.')
        turn=math.pi-2*half
        corners.append(Corner(start,end,middle,center,turn));removed.append(radius*radius*(cot-turn/2))
    rounded_area=area-math.fsum(removed)
    if not 0<rounded_area<area:raise ValueError('The rounded cell has an invalid area.')
    # Every tangent endpoint lies on the convex rounded contour. Their mean is
    # an interior witness even for asymmetric contours near the fit limit.
    points=tuple(p for corner in corners for p in (corner.start,corner.end))
    interior=tuple(math.fsum(p[axis] for p in points)/len(points) for axis in (0,1))
    return Profile(polygon,tuple(corners),float(radius),rounded_area,maximum,interior)


def stroke(value,tolerance_mm=.01,max_points=128):
    """Inscribed chords with a proved sag bound; only for trims/sheared lofts."""
    if not 0<tolerance_mm<1 or type(max_points) is not int or not 6<=max_points<=128:
        raise ValueError('Use a bounded curve tolerance and at most 128 cell points.')
    step=2*math.acos(max(-1.,min(1.,1-tolerance_mm/value.radius_mm)))
    counts=tuple(max(1,math.ceil(c.turn_rad/step)) for c in value.corners)
    if sum(n+1 for n in counts)>max_points:
        raise ValueError('This fillet exceeds the bounded curve detail for clipped/raised cells. Reduce radius or use a smaller, simpler region.')
    points=[]
    for corner,count in zip(value.corners,counts):
        angle=math.atan2(corner.start[1]-corner.center[1],corner.start[0]-corner.center[0])
        for i in range(count+1):
            t=angle+corner.turn_rad*i/count
            points.append((corner.center[0]+value.radius_mm*math.cos(t),corner.center[1]+value.radius_mm*math.sin(t)))
    return tuple(points)

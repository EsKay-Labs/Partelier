"""Bounded convex polygon clipping in physical chart millimetres."""

import math

EPSILON = 1e-9
MAX_FRAGMENTS = 96


def area(polygon):
    return abs(sum(a[0]*b[1]-b[0]*a[1] for a,b in zip(polygon,polygon[1:]+polygon[:1])))/2


def clean(polygon):
    points=[]
    for point in polygon:
        if not points or math.dist(points[-1],point)>1e-5:
            points.append(tuple(point))
    if len(points)>1 and math.dist(points[0],points[-1])<=1e-5:points.pop()
    changed=True
    while len(points)>=3 and changed:
        changed=False
        for index,point in enumerate(points):
            a,b=points[index-1],points[(index+1)%len(points)]
            cross=(point[0]-a[0])*(b[1]-point[1])-(point[1]-a[1])*(b[0]-point[0])
            if abs(cross)<=1e-8*max(1,math.dist(a,b)):
                points.pop(index);changed=True;break
    result=tuple(points)
    return result if len(result)>=3 and area(result)>1e-6 else ()


def halfplane(polygon,a,b,*,inside=True):
    """Keep the left (or right) closed side of the directed finite line."""
    if not polygon:return ()
    def signed(p):return ((b[0]-a[0])*(p[1]-a[1])-(b[1]-a[1])*(p[0]-a[0]))*(1 if inside else -1)
    result=[]
    previous=polygon[-1];before=signed(previous)
    for point in polygon:
        after=signed(point)
        if (before>=0)!=(after>=0):
            fraction=before/(before-after)
            result.append(tuple(x+fraction*(y-x) for x,y in zip(previous,point)))
        if after>=0:result.append(point)
        previous,before=point,after
    return clean(result)


def rectangle(polygon,bounds,periodic=False):
    low_u,high_u,low_v,high_v=bounds
    edges=[((high_u,low_v),(low_u,low_v)),((low_u,high_v),(high_u,high_v))]
    # Clockwise lines above keep the exterior; reverse to keep the rectangle.
    edges=[(b,a) for a,b in edges]
    if not periodic:edges += [((low_u,high_v),(low_u,low_v)),((high_u,low_v),(high_u,high_v))]
    for a,b in edges:
        polygon=halfplane(polygon,a,b)
        if not polygon:break
    return polygon


def difference(polygon,obstacle):
    """Disjoint convex pieces of polygon minus one convex CCW obstacle."""
    remaining=polygon;result=[]
    for a,b in zip(obstacle,obstacle[1:]+obstacle[:1]):
        if not remaining:break
        outside=halfplane(remaining,a,b,inside=False)
        if outside:result.append(outside)
        remaining=halfplane(remaining,a,b)
    return tuple(result)


def capsule(a,b,radius):
    """Circumscribed capsule: never erodes less than the requested border."""
    angle=math.atan2(b[1]-a[1],b[0]-a[0])
    count=16
    radius=radius/math.cos(math.pi/(2*count))
    return tuple((origin[0]+radius*math.cos(theta),origin[1]+radius*math.sin(theta))
                 for origin,start in ((b,angle-math.pi/2),(a,angle+math.pi/2))
                 for theta in (start+math.pi*i/count for i in range(count+1)))


def bounds(polygon):
    return tuple((min(p[axis] for p in polygon),max(p[axis] for p in polygon)) for axis in (0,1))


def overlaps(one,two):
    return all(a[0]<b[1]-EPSILON and b[0]<a[1]-EPSILON for a,b in zip(one,two))


def convex_hull(points):
    points=sorted(set(points))
    def cross(a,b,c):return (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])
    lower=[];upper=[]
    for point in points:
        while len(lower)>=2 and cross(lower[-2],lower[-1],point)<=1e-10:lower.pop()
        lower.append(point)
    for point in reversed(points):
        while len(upper)>=2 and cross(upper[-2],upper[-1],point)<=1e-10:upper.pop()
        upper.append(point)
    return clean(lower[:-1]+upper[:-1])


def merge_convex(pieces):
    """Remove decomposition seams only when their union remains convex.

    An area equality plus touching bounds rules out filling a finite void.
    Existing clipped vertices define the hull; no coordinates are rounded.
    """
    pieces=list(pieces);changed=True
    while changed:
        changed=False
        for i,one in enumerate(pieces):
            a=bounds(one)
            for j in range(i+1,len(pieces)):
                two=pieces[j];b=bounds(two)
                if any(x[1]<y[0]-1e-8 or y[1]<x[0]-1e-8 for x,y in zip(a,b)):continue
                hull=convex_hull(one+two)
                if hull and abs(area(hull)-area(one)-area(two))<=1e-8:
                    pieces[i]=hull;pieces.pop(j);changed=True;break
            if changed:break
    return tuple(pieces)


def offset_convex(polygon,distance):
    """Inward positive / outward negative offset of a convex CCW loop."""
    if len(polygon)>512:raise ValueError('Too much detail in a closed pattern trim.')
    polygon=clean(polygon)
    if not polygon:return ()
    signed=sum(a[0]*b[1]-a[1]*b[0] for a,b in zip(polygon,polygon[1:]+polygon[:1]))
    if signed<0:polygon=tuple(reversed(polygon))
    lines=[]
    for a,b in zip(polygon,polygon[1:]+polygon[:1]):
        length=math.dist(a,b);normal=(-(b[1]-a[1])/length,(b[0]-a[0])/length)
        if any(normal[0]*(p[0]-a[0])+normal[1]*(p[1]-a[1]) < -1e-7 for p in polygon):
            raise ValueError('A closed trim is not convex.')
        lines.append((normal,normal[0]*a[0]+normal[1]*a[1]+distance))
    result=[]
    for i,(n,c) in enumerate(lines):
        before,d=lines[i-1];det=before[0]*n[1]-before[1]*n[0]
        if abs(det)<1e-12:raise ValueError('A closed trim offset is singular.')
        result.append(((d*n[1]-c*before[1])/det,(before[0]*c-n[0]*d)/det))
    if any(n[0]*p[0]+n[1]*p[1]<c-1e-7 for p in result for n,c in lines):return ()
    return clean(result)


def subtract_boundaries(polygon,segments,border):
    """Subtract only nearby finite edge capsules; fragments retain convexity."""
    pieces=(polygon,)
    original=bounds(polygon)
    for a,b,tolerance in segments:
        radius=max(.005,border+tolerance+.002)
        box=((min(a[0],b[0])-radius*1.01,max(a[0],b[0])+radius*1.01),
             (min(a[1],b[1])-radius*1.01,max(a[1],b[1])+radius*1.01))
        if not overlaps(original,box):continue
        obstacle=capsule(a,b,radius)
        parts=[]
        for piece in pieces:
            parts.extend(difference(piece,obstacle) if overlaps(bounds(piece),box) else (piece,))
        pieces=merge_convex(parts) if len(parts)>4 else tuple(parts)
        if len(pieces)>MAX_FRAGMENTS:
            raise ValueError('Too much boundary detail in one pattern cell. Reduce cell size or select a simpler face region.')
        if not pieces:break
    return pieces

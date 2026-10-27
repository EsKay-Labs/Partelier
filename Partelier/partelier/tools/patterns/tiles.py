"""Convex periodic motifs, with an actual perpendicular half-gap per edge.

Templates are analytic geometry, independent of Fusion. Cairo uses an integer
coordinate deformation of the square-lattice pentagonal construction discussed
by M. Zucker, Bridges 2023, pp. 215-216 (see docs/surface-patterns.md).
"""

from dataclasses import dataclass
from functools import lru_cache
import math

from . import clipping


TILED_PATTERNS = ('triangle','rounded_triangle','pentagon','octagon',
                  'trihex','octagon_square','cairo','rhombille','rounded_hexagon','elongated_hexagon','warren')


@dataclass(frozen=True)
class Motif:
    width: float
    height: float
    polygons: tuple
    reference: int = 0
    rounded: bool = False


def rotate(polygon, angle):
    c,s=math.cos(angle),math.sin(angle)
    return tuple((x*c-y*s,x*s+y*c) for x,y in polygon)


def shifted(polygon, x, y):
    return tuple((u+x,v+y) for u,v in polygon)


def _regular(count, phase=math.pi/2):
    return tuple((math.cos(phase+i*2*math.pi/count),math.sin(phase+i*2*math.pi/count)) for i in range(count))


@lru_cache(maxsize=16)
def motif(pattern):
    h=math.sqrt(3)/2
    if pattern in ('triangle','rounded_triangle','warren'):
        # Warren bands have alternating +/-45-degree diagonals between straight
        # horizontal chords. Their 2:1 windows intentionally differ from the
        # equilateral triangle mosaic while sharing its closed periodic topology.
        if pattern=='warren':h=.5
        polygons=(((0,0),(1,0),(.5,h)),((.5,h),(1,0),(1.5,h)),
                  ((.5,h),(1.5,h),(1,2*h)),((0,2*h),(.5,h),(1,2*h)))
        value=Motif(1,2*h,polygons,rounded=pattern=='rounded_triangle')
    elif pattern=='pentagon':
        value=Motif(2,2,(_regular(5),))
    elif pattern in ('octagon','octagon_square'):
        a=(1+math.sqrt(2))/2
        octagon=((a,.5),(.5,a),(-.5,a),(-a,.5),(-a,-.5),(-.5,-a),(.5,-a),(a,-.5))
        square=shifted(((0,-1/math.sqrt(2)),(1/math.sqrt(2),0),(0,1/math.sqrt(2)),(-1/math.sqrt(2),0)),a,a)
        value=Motif(2*a,2*a,(octagon,) if pattern=='octagon' else (octagon,square),0 if pattern=='octagon' else 1)
    elif pattern=='trihex':
        hexagon=_regular(6,0)
        polygons=(hexagon,shifted(hexagon,1,2*h),
                  ((1,0),(1.5,h),(.5,h)),((0,2*h),(-.5,h),(.5,h)),
                  ((0,2*h),(.5,3*h),(-.5,3*h)),((1,4*h),(.5,3*h),(1.5,3*h)))
        value=Motif(2,4*h,polygons,2)
    elif pattern=='cairo':
        # Eight congruent convex pentagons fill the 12 x 12 repeat rectangle.
        pentagon=((-5,-3),(-1,-3),(0,0),(-3,1),(-6,0))
        polygons=tuple(shifted(rotate(pentagon,k*math.pi/2),x,y)
                       for x,y in ((0,0),(6,6)) for k in range(4))
        value=Motif(12,12,polygons)
    elif pattern in ('rhombille','rounded_hexagon','elongated_hexagon'):
        hexagon=_regular(6,math.pi/6)
        centers=((0,0),(math.sqrt(3)/2,1.5))
        polygons=tuple(shifted(hexagon,x,y) for x,y in centers)
        if pattern=='rhombille':
            polygons=tuple(shifted(((0,0),hexagon[k],hexagon[(k+1)%6],hexagon[(k+2)%6]),x,y)
                           for x,y in centers for k in (0,2,4))
        stretch=1.6 if pattern=='elongated_hexagon' else 1
        polygons=tuple(tuple((x*stretch,y) for x,y in p) for p in polygons)
        value=Motif(math.sqrt(3)*stretch,3,polygons,rounded=pattern=='rounded_hexagon')
    else:
        raise ValueError('Choose a supported polygon family.')
    # Put every tile center inside one repeat rectangle; avoid duplicated seams.
    polygons=[]
    for polygon in value.polygons:
        cx=sum(x for x,y in polygon)/len(polygon);cy=sum(y for x,y in polygon)/len(polygon)
        dx=(cx+value.width/2)%value.width-value.width/2-cx
        dy=(cy+value.height/2)%value.height-value.height/2-cy
        polygons.append(shifted(polygon,dx,dy))
    return Motif(value.width,value.height,tuple(polygons),value.reference,value.rounded)


def inset(polygon, distance):
    """Intersect adjacent offset supporting lines; reject collapsed tiles."""
    lines=[]
    for a,b in zip(polygon,polygon[1:]+polygon[:1]):
        dx,dy=b[0]-a[0],b[1]-a[1];length=math.hypot(dx,dy)
        nx,ny=-dy/length,dx/length
        lines.append((nx,ny,nx*a[0]+ny*a[1]+distance))
    result=[]
    for index,(nx,ny,c) in enumerate(lines):
        px,py,d=lines[index-1];det=px*ny-py*nx
        if abs(det)<1e-12:return ()
        point=((d*ny-py*c)/det,(px*c-d*nx)/det)
        if any(x*point[0]+y*point[1]<v-1e-7 for x,y,v in lines):return ()
        result.append(point)
    return clipping.clean(tuple(result))


def rounded(polygon, radius):
    """Inscribed tangent corner arcs, six bounded segments per corner."""
    result=[]
    for i,point in enumerate(polygon):
        before,after=polygon[i-1],polygon[(i+1)%len(polygon)]
        one=(before[0]-point[0],before[1]-point[1]);two=(after[0]-point[0],after[1]-point[1])
        l1,l2=math.hypot(*one),math.hypot(*two)
        one=(one[0]/l1,one[1]/l1);two=(two[0]/l2,two[1]/l2)
        theta=math.acos(max(-1,min(1,one[0]*two[0]+one[1]*two[1])))
        r=min(radius,min(l1,l2)*.24*math.tan(theta/2))
        distance=r/math.tan(theta/2)
        a=(point[0]+one[0]*distance,point[1]+one[1]*distance)
        # For a CCW boundary, the incoming edge is -one, so its inward normal
        # is (one.y,-one.x).
        center=(a[0]+one[1]*r,a[1]-one[0]*r)
        angle=math.atan2(a[1]-center[1],a[0]-center[0])
        for j in range(7):
            t=angle+(math.pi-theta)*j/6
            result.append((center[0]+r*math.cos(t),center[1]+r*math.sin(t)))
    return clipping.clean(tuple(result))


@lru_cache(maxsize=16)
def dimensions(pattern):
    value=motif(pattern);reference=value.polygons[value.reference]
    width=max(x for x,y in reference)-min(x for x,y in reference)
    smaller=inset(reference,.01)
    shrink=(width-(max(x for x,y in smaller)-min(x for x,y in smaller)))/.02
    return width,shrink


def profiles(pattern, size, gap, *, sharp=False):
    value=motif(pattern);width,shrink=dimensions(pattern)
    scale=(size+gap*shrink)/width
    result=[]
    for polygon in value.polygons:
        scaled=tuple((x*scale,y*scale) for x,y in polygon)
        inner=inset(scaled,gap/2)
        if not inner:return ()
        if value.rounded and not sharp:inner=rounded(inner,size*.12)
        if not inner:return ()
        cx=sum(x for x,y in inner)/len(inner);cy=sum(y for x,y in inner)/len(inner)
        result.append(((cx,cy),tuple((x-cx,y-cy) for x,y in inner)))
    return value.width*scale,value.height*scale,tuple(result)

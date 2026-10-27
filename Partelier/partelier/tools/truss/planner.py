"""Connected parallel-chord layouts, represented by disjoint convex windows.

Original implementation in millimetres; no StructForge source is imported.
Member widths are perpendicular to their centre lines, not horizontal offsets.
This is geometry planning, not a structural analysis or a strength rating.
"""

from dataclasses import dataclass
import math
from ..patterns import clipping


STYLES=('truss_warren','truss_pratt','truss_howe')
MAX_BAYS=64


@dataclass(frozen=True)
class Plan:
    outer: tuple
    holes: tuple
    members: tuple
    axis: str
    bay_span_mm: float
    open_area_mm2: float
    material_area_mm2: float
    rounded_holes: tuple = ()


def _ccw(polygon):
    polygon=tuple(polygon)
    return polygon if sum(a[0]*b[1]-b[0]*a[1] for a,b in zip(polygon,polygon[1:]+polygon[:1]))>0 else tuple(reversed(polygon))


def _window(triangle,inner,width):
    polygon=_ccw(triangle)
    for a,b in zip(polygon,polygon[1:]+polygon[:1]):
        # Chords/end posts are supplied by the original solid perimeter. Only
        # interior edges need half a member width removed on either side.
        boundary=any(abs(a[axis]-edge)<1e-8 and abs(b[axis]-edge)<1e-8
                     for axis,edges in ((0,inner[:2]),(1,inner[2:])) for edge in edges)
        if boundary:continue
        length=math.dist(a,b);d=width/2
        shift=(-(b[1]-a[1])*d/length,(b[0]-a[0])*d/length)
        polygon=clipping.halfplane(polygon,tuple(x+s for x,s in zip(a,shift)),tuple(x+s for x,s in zip(b,shift)))
        if not polygon:break
    if not polygon or 2*clipping.area(polygon)/sum(math.dist(a,b) for a,b in zip(polygon,polygon[1:]+polygon[:1]))<.1:
        raise ValueError('The truss windows are too small. Reduce Bays/Member width/Frame width, or use a larger plate.')
    return polygon


def plan(bounds,style,bays,member_mm,frame_mm,axis='long',fillet_mm=0):
    if style not in STYLES or axis not in ('long','short'):
        raise ValueError('Choose Warren, Pratt or Howe and a long/short span direction.')
    if type(bays) is not int or not 2<=bays<=MAX_BAYS:
        raise ValueError('Truss Bays must be a whole number from 2 to 64.')
    if style!='truss_warren' and bays%2:
        raise ValueError('Pratt and Howe need an even number of Bays for a symmetric centre.')
    values=(*bounds,member_mm,frame_mm,fillet_mm)
    if len(bounds)!=4 or any(isinstance(v,bool) or not isinstance(v,(float,int)) or not math.isfinite(v) for v in values):
        raise ValueError('Truss dimensions must be finite numbers.')
    lo,hi,bottom,top=bounds
    if hi<=lo or top<=bottom or not .4<=member_mm<=100 or not .5<=frame_mm<=1000 or not 0<=fillet_mm<=1000:
        raise ValueError('Use Member width 0.4–100 mm and Frame width 0.5–1000 mm on a positive rectangular region.')
    outer=((lo,bottom),(hi,bottom),(hi,top),(lo,top))
    use_u=(hi-lo>=top-bottom)==(axis=='long')
    if not use_u:lo,hi,bottom,top=bottom,top,lo,hi
    lo+=frame_mm;hi-=frame_mm;bottom+=frame_mm;top-=frame_mm
    if hi-lo<=.2 or top-bottom<=.2:
        raise ValueError('Frame width leaves no truss region. Reduce Frame width or use a larger plate.')
    inner=(lo,hi,bottom,top);step=(hi-lo)/bays
    triangles=[];members=[]
    if style=='truss_warren':
        nodes=tuple((lo+i*step,bottom if i%2==0 else top) for i in range(bays+1))
        members.extend(zip(nodes,nodes[1:]))
        triangles.append((nodes[0],nodes[1],(lo,top)))
        triangles.extend((nodes[i-1],nodes[i],nodes[i+1]) for i in range(1,bays))
        triangles.append((nodes[-2],nodes[-1],(hi,top if bays%2==0 else bottom)))
    else:
        for i in range(bays):
            x=lo+i*step;right=lo+(i+1)*step
            bl,br,tr,tl=(x,bottom),(right,bottom),(right,top),(x,top)
            descending=(i<bays/2)==(style=='truss_pratt')
            triangles.extend(((bl,br,tl),(br,tr,tl)) if descending else ((bl,br,tr),(bl,tr,tl)))
            members.append((tl,br) if descending else (bl,tr))
            if i:members.append((bl,tl))
    # Triangles partition the complete inner rectangle before erosion. Refuse
    # a planning defect rather than filling an accidental gap with material.
    if abs(math.fsum(clipping.area(t) for t in triangles)-(hi-lo)*(top-bottom))>max(1e-7,(hi-lo)*(top-bottom)*1e-10):
        raise ValueError('The truss subdivision did not cover its frame.')
    holes=tuple(_window(triangle,inner,member_mm) for triangle in triangles)
    def mapped(point):return point if use_u else (point[1],point[0])
    holes=tuple(_ccw(mapped(point) for point in hole) for hole in holes)
    members=tuple(tuple(mapped(point) for point in line) for line in members)
    if fillet_mm:
        from .rounding import window
        rounded=tuple(window(hole,fillet_mm) for hole in holes)
    else:rounded=()
    opened=math.fsum(hole.area_mm2 for hole in rounded) if rounded else math.fsum(clipping.area(hole) for hole in holes)
    return Plan(outer,holes,members,'u' if use_u else 'v',step,opened,clipping.area(outer)-opened,rounded)

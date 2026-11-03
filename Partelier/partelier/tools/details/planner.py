"""Bounded rectangle-ring, matching-pin and evenly spaced rib dimensions."""

import math


def rectangle(bounds,inset=0):
    lo,hi,bottom,top=bounds;lo+=inset;hi-=inset;bottom+=inset;top-=inset
    if hi-lo<=.2 or top-bottom<=.2:raise ValueError('The inset/width leaves no closed rectangular region.')
    return ((lo,bottom),(hi,bottom),(hi,top),(lo,top))


def side_runs(mask):
    """Consecutive rectangular side indices; the closed ring is a separate case."""
    if type(mask) is not int or not 1<=mask<=15:raise ValueError('Choose one to four lip sides.')
    if mask==15:return ((0,1,2,3),)
    runs=[]
    for side in range(4):
        if mask&(1<<side) and not mask&(1<<((side-1)%4)):
            run=[];current=side
            while mask&(1<<current):
                run.append(current);current=(current+1)%4
            runs.append(tuple(run))
    return tuple(runs)


def lip_polygons(bounds,inset,width,mask):
    """One continuous footprint for each open run, with mitered corner ends."""
    if mask==15:raise ValueError('Use the closed ring for all four lip sides.')
    outer,inner=rectangle(bounds,inset),rectangle(bounds,inset+width)
    polygons=[]
    for run in side_runs(mask):
        corners=(*run,(run[-1]+1)%4)
        polygon=tuple(outer[i] for i in corners)+tuple(inner[i] for i in reversed(corners))
        _validate_polygon(polygon);polygons.append(polygon)
    return tuple(polygons)


def polygon_area(polygon):
    return math.fsum(a[0]*b[1]-a[1]*b[0] for a,b in zip(polygon,polygon[1:]+polygon[:1]))/2


def _cross2(a,b):return a[0]*b[1]-a[1]*b[0]


def _validate_polygon(polygon):
    if not 3<=len(polygon)<=10 or any(not math.isfinite(v) for p in polygon for v in p):
        raise ValueError('The selected lip contour is invalid.')
    if polygon_area(polygon)<=1e-8:raise ValueError('The selected lip contour has collapsed.')
    edges=tuple(zip(polygon,polygon[1:]+polygon[:1]))
    for i,(a,b) in enumerate(edges):
        if math.dist(a,b)<1e-5:raise ValueError('The lip contour has a collapsed edge. Reduce Lead-in or clearance.')
        for j,(c,d) in enumerate(edges):
            if j<=i or j in ((i+1)%len(edges),(i-1)%len(edges)):continue
            ab=(b[0]-a[0],b[1]-a[1]);cd=(d[0]-c[0],d[1]-c[1]);ac=(c[0]-a[0],c[1]-a[1])
            denominator=_cross2(ab,cd)
            if abs(denominator)<1e-10:continue
            one,two=_cross2(ac,cd)/denominator,_cross2(ac,ab)/denominator
            if -1e-8<=one<=1+1e-8 and -1e-8<=two<=1+1e-8:
                raise ValueError('The lip contour crosses itself. Reduce Lead-in or clearance.')


def offset_polygon(polygon,distance):
    """Parallel inward offset of an open rectangular lip run, preserving corners."""
    polygon=tuple(polygon);_validate_polygon(polygon)
    if not math.isfinite(distance):raise ValueError('The lip offset must be finite.')
    lines=[]
    for a,b in zip(polygon,polygon[1:]+polygon[:1]):
        dx,dz=b[0]-a[0],b[1]-a[1];length=math.hypot(dx,dz)
        lines.append(((a[0]-dz*distance/length,a[1]+dx*distance/length),(dx/length,dz/length)))
    output=[]
    for i,(point,direction) in enumerate(lines):
        previous,vector=lines[i-1];cross=_cross2(vector,direction)
        if abs(cross)<1e-9:raise ValueError('The lip offset has a flat corner.')
        delta=(point[0]-previous[0],point[1]-previous[1]);t=_cross2(delta,direction)/cross
        output.append((previous[0]+t*vector[0],previous[1]+t*vector[1]))
    output=tuple(output);_validate_polygon(output)
    # Parallel offsets must preserve every edge direction and positive length.
    for (a,b),(c,d) in zip(zip(polygon,polygon[1:]+polygon[:1]),zip(output,output[1:]+output[:1])):
        if (b[0]-a[0])*(d[0]-c[0])+(b[1]-a[1])*(d[1]-c[1])<=0:
            raise ValueError('Lead-in or clearance collapses the selected lip. Reduce it or increase Lip width.')
    return output


def lip_loft(frame,polygon,top,low,high):
    """Closed planar topology for a <=10-corner lip run, including L/U contours.

    This deliberately does not extend the shared strictly convex pattern planner.
    Matching parallel edges give planar side faces; a signed-volume check proves
    their winding against the exact prismoidal volume before entering Fusion.
    """
    polygon,top=tuple(polygon),tuple(top);_validate_polygon(polygon);_validate_polygon(top)
    if len(polygon)!=len(top) or not math.isfinite(low+high) or high<=low:
        raise ValueError('The selected lip loft has invalid matching sections.')
    axes=(frame.x_axis,frame.y_axis,frame.z_axis);origin=frame.origin_mm
    if (any(len(axis)!=3 or not all(math.isfinite(v) for v in axis) for axis in axes)
            or any(abs(sum(v*v for v in axis)-1)>1e-7 for axis in axes)
            or any(abs(sum(a*b for a,b in zip(axes[i],axes[j])))>1e-7 for i,j in ((0,1),(1,2),(0,2)))):
        raise ValueError('The lip needs an orthonormal frame.')
    def world(point,height):
        return tuple(o+point[0]*x+height*y+point[1]*z for o,x,y,z in zip(origin,*axes))
    count=len(polygon);points=tuple(world(p,low) for p in polygon)+tuple(world(p,high) for p in top)
    faces=(tuple(range(count)),tuple(reversed(range(count,2*count))))+tuple(
        (i,count+i,count+(i+1)%count,(i+1)%count) for i in range(count))
    def sub(a,b):return tuple(x-y for x,y in zip(a,b))
    def cross(a,b):return (a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0])
    def dot(a,b):return sum(x*y for x,y in zip(a,b))
    for face in faces[2:]:
        a,b,c=(points[i] for i in face[:3]);normal=cross(sub(b,a),sub(c,a));length=math.sqrt(dot(normal,normal))
        if length<1e-9 or any(abs(dot(normal,sub(points[i],a)))>length*1e-7 for i in face):
            raise ValueError('The selected lip loft needs planar sides.')
    reference=points[0]
    signed=math.fsum(dot(sub(points[face[0]],reference),cross(sub(points[face[i]],reference),sub(points[face[i+1]],reference)))/6
        for face in faces for i in range(1,len(face)-1))
    middle=tuple(tuple((a+b)/2 for a,b in zip(one,two)) for one,two in zip(polygon,top))
    expected=(polygon_area(polygon)+4*polygon_area(middle)+polygon_area(top))*(high-low)/6
    if not math.isfinite(signed) or signed<=0 or abs(signed-expected)>max(1e-8,expected*1e-7):
        raise ValueError('The selected lip has inconsistent winding or volume.')
    return points,tuple((face,) for face in faces),expected


def pins(bounds,settings):
    radius=(settings.pin_diameter_mm+settings.pin_clearance_mm)/2+settings.lead_mm
    inset=settings.pin_inset_mm or radius+.5
    if inset<radius+.1:raise ValueError(f'Pin centres need at least {radius+.1:.2f} mm inset. Use 0 for Auto.')
    lo,hi,bottom,top=bounds
    if min(hi-lo,top-bottom)<=2*inset+2*radius+.2:raise ValueError('The selected face is too small for separated pins and receiving holes.')
    points=((lo+inset,bottom+inset),(hi-inset,top-inset))
    if settings.pin_count==4:points+=((lo+inset,top-inset),(hi-inset,bottom+inset))
    return points


def rib_positions(length,width,count,margin):
    if (not all(math.isfinite(v) for v in (length,width,margin)) or length<=0 or width<=0 or margin<0
            or type(count) is not int or not 1<=count<=32):raise ValueError('Use finite rib dimensions and 1â€“32 ribs.')
    available=length-2*margin-width
    if available<0:raise ValueError('End margins and rib width exceed the common support edge.')
    if count==1:return (length/2,)
    step=available/(count-1)
    if step<width+.2:raise ValueError('Ribs overlap. Reduce count/width/end margins or choose a longer edge.')
    return tuple(margin+width/2+i*step for i in range(count))


def socket_depth(height,gap,axial):
    if gap< -1e-4:raise ValueError('The selected mating faces overlap. Choose faces facing each other across a nonnegative gap.')
    if height-gap<.2:raise ValueError(f'Height must exceed the {gap:.2f} mm face gap by at least 0.2 mm.')
    return height-max(0,gap)+axial


def convex_outline(points):
    """Exact 3–10 corner strictly convex contour; reject concavity and flat corners."""
    polygon=tuple(tuple(p) for p in points)
    if any(len(p)!=2 for p in polygon):raise ValueError('Use a planar polygon outline.')
    if polygon_area(polygon)<0:polygon=tuple(reversed(polygon))
    _validate_polygon(polygon)
    for i,b in enumerate(polygon):
        a,c=polygon[i-1],polygon[(i+1)%len(polygon)]
        if _cross2((b[0]-a[0],b[1]-a[1]),(c[0]-b[0],c[1]-b[1]))<=1e-7:
            raise ValueError('Continuous polygon lips require 3–10 strictly convex straight sides; concave/flat corners are not supported.')
    return polygon


def lip_contours(polygon,inset,width,clearance,lead):
    """Shared exact parallel outlines for a convex lip, lead-in and receiving ring."""
    polygon=convex_outline(polygon)
    if not all(math.isfinite(v) for v in (inset,width,clearance,lead)) or inset<clearance+.1 or width<=2*lead or min(clearance,lead)<0:
        raise ValueError('Lip dimensions leave no complete contour or receiving margin.')
    return tuple(offset_polygon(polygon,d) for d in (inset,inset+width,inset-clearance,inset+width+clearance,inset+lead,inset+width-lead))


def circle_lip_radii(radius,inset,width,clearance,lead):
    if not all(math.isfinite(v) for v in (radius,inset,width,clearance,lead)) or inset<clearance+.1 or width<=2*lead or min(clearance,lead)<0:
        raise ValueError('Circular lip dimensions leave no complete ring or receiving margin.')
    values=tuple(radius-d for d in (inset,inset+width,inset-clearance,inset+width+clearance,inset+lead,inset+width-lead))
    if min(values)<=.1:raise ValueError('Lip width/inset/clearance collapses the circular opening. Reduce them or select a larger face.')
    return values

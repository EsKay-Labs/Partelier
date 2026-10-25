"""Bounded planar profile segments with explicit bed-relative overhang proof.

Only matching convex loops with planar sides are supported. End and midpoint
sections are checked before any native geometry; the lowest cap sits on an
already supported grille section, never in free air.
"""

import math
from . import perforated_prism as direct
from . import prism


def plan(frame,outer,holes,top_outer,top_holes,low,high):
    holes=tuple(holes);top_holes=tuple(top_holes)
    if not 1<=len(holes)<=200 or len(holes)!=len(top_holes):
        raise ValueError('Raised profiles support up to 200 openings. Increase Opening width or Rib width.')
    lower=direct.plan(frame,outer,holes,low,high)
    upper=direct.plan(frame,top_outer,top_holes,low,high)
    loops=(tuple(outer),)+tuple(tuple(p) for p in holes)
    tops=(tuple(top_outer),)+tuple(tuple(p) for p in top_holes)
    if any(len(a)!=len(b) for a,b in zip(loops,tops)):
        raise ValueError('The profile collapsed an opening corner. Increase Rib width or Border.')
    middle=tuple(tuple(tuple((x+y)/2 for x,y in zip(a,b)) for a,b in zip(one,two)) for one,two in zip(loops,tops))
    midpoint=direct.plan(frame,middle[0],middle[1:],low,high)
    points=[];offset=0
    for loop in loops:
        count=len(loop)
        points.extend(lower.points_mm[offset:offset+count])
        points.extend(upper.points_mm[offset+count:offset+2*count])
        offset+=2*count
    points=tuple(points)
    for face in lower.faces[2:]:
        indices=face[0]
        a,b,c=(points[i] for i in indices[:3])
        normal=prism._cross(prism._sub(b,a),prism._sub(c,a))
        length=math.sqrt(prism._dot(normal,normal))
        if length<1e-10 or any(abs(prism._dot(normal,prism._sub(points[i],a)))>length*1e-7 for i in indices):
            raise ValueError('This grille profile needs non-planar sides. Change Direction or profile.')
        vertical=prism._dot(normal,frame.y_axis)
        horizontal=math.sqrt(max(0,length*length-vertical*vertical))
        if vertical < -horizontal-1e-7*length:
            raise ValueError('The grille underside exceeds 45 degrees for back-to-bed printing.')
    reference=points[0]
    volume=math.fsum(prism._dot(prism._sub(points[loop[0]],reference),
        prism._cross(prism._sub(points[loop[i]],reference),prism._sub(points[loop[i+1]],reference)))/6
        for face in lower.faces for loop in face for i in range(1,len(loop)-1))
    expected=(lower.volume_mm3+4*midpoint.volume_mm3+upper.volume_mm3)/6
    if not math.isfinite(volume) or volume<=0 or abs(volume-expected)>max(1e-8,expected*1e-7):
        raise ValueError('The grille profile has inconsistent closed volume.')
    return direct.Plan(points,lower.faces,volume)


def create(frame,outer,holes,top_outer,top_holes,low,high):
    return direct.create_plan(plan(frame,outer,holes,top_outer,top_holes,low,high))

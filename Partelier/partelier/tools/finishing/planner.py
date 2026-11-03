"""Bounded original footprints; no Fusion dependencies."""
import math

def rectangle(x0,x1,y0,y1):return ((x0,y0),(x1,y0),(x1,y1),(x0,y1))
def polygons(s):
    s.validate();w,l,t=s.width_mm,s.length_mm,s.stroke_mm
    if s.kind=='stop':return (rectangle(-w/2,w/2,-l/2,l/2),)
    if s.kind=='arrow':
        # Two convex polygons overlap into one arrow, avoiding concave prism input.
        return (rectangle(-l/2,l/6,-t/2,t/2),((0,-w/2),(l/2,0),(0,w/2)))
    if s.kind=='scale':return tuple(rectangle(-l/2+i*l/(s.count-1)-t/2,-l/2+i*l/(s.count-1)+t/2,0,w if i%s.major_every==0 else w*.55) for i in range(s.count))
    return ()

def transformed(points,s):
    c=math.cos(math.radians(s.rotation_deg));q=math.sin(math.radians(s.rotation_deg))
    return tuple((s.offset_x_mm+c*x-q*y,s.offset_y_mm+q*x+c*y) for x,y in points)

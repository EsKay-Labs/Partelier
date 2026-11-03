"""Flat, connected fan guards with bounded geometry and protected mounting rim."""
import math

def hexagons(s):
    radius=s.diameter_mm/2+s.tip_gap_mm;pitch=s.guard_pitch_mm
    cell=(pitch-s.guard_spoke_mm)/math.sqrt(3);step=pitch*math.sqrt(3)/2
    bound=math.ceil((radius+cell)/step);polygons=[]
    if (2*bound+1)**2>2500:raise ValueError('Guard is too dense. Increase Guard spacing.')
    for row in range(-bound,bound+1):
        for column in range(-bound,bound+1):
            x=(column+(row%2)/2)*pitch;y=row*step
            if math.hypot(x,y)>radius+cell:continue
            points=tuple((x+cell*math.cos(math.pi/6+i*math.pi/3),y+cell*math.sin(math.pi/6+i*math.pi/3)) for i in range(6))
            # The central hex encloses the origin; otherwise nearest segment
            # decides intersection with the circular aperture, including halves.
            nearest=0 if x==0 and y==0 else float('inf')
            for a,b in zip(points,points[1:]+points[:1]):
                vx,vy=b[0]-a[0],b[1]-a[1];t=max(0,min(1,-(a[0]*vx+a[1]*vy)/(vx*vx+vy*vy)))
                nearest=min(nearest,math.hypot(a[0]+t*vx,a[1]+t*vy))
            if nearest<radius-.01:polygons.append(points)
    if len(polygons)>180:raise ValueError('Honeycomb guard exceeds 180 openings. Increase Guard spacing.')
    return tuple(polygons)

def validate(s):
    opening=s.diameter_mm+2*s.tip_gap_mm
    if opening>s.frame_width_mm-4:raise ValueError('Guard must leave at least 2 mm outside the fan opening.')
    if opening/2+s.mount_hole_mm/2+1>=s.mount_pitch_mm/math.sqrt(2):raise ValueError('Mounting holes intersect the guard opening. Increase Mount pitch or reduce Fan diameter.')
    if s.mount_pitch_mm+s.mount_hole_mm+2>s.frame_width_mm:raise ValueError('Mounting holes need more space inside the guard rim.')
    if s.guard_type in ('spokes','rings') and s.hub_diameter_mm>=opening-2*s.guard_spoke_mm:
        raise ValueError('Guard centre must leave room for its openings.')
    if s.guard_type!='spokes':
        if s.guard_pitch_mm<=s.guard_spoke_mm+1:raise ValueError('Guard spacing must exceed Bar width by more than 1 mm.')
        if math.ceil(opening/s.guard_pitch_mm)>64:raise ValueError('Guard is too dense. Increase Guard spacing.')
    if s.guard_type=='rings' and s.hub_diameter_mm/2+s.guard_pitch_mm>=opening/2:
        raise ValueError('No ring fits. Reduce Guard spacing or Centre diameter.')
    if s.guard_type=='honeycomb':hexagons(s)

def build(manager,s,z,core,native):
    from dataclasses import replace
    from . import fusion as f
    from ..patterns import fusion as a
    from ..hinge.fusion import HingeFrame
    validate(s);t=s.guard_thickness_mm;low=z+s.axial_clearance_mm;high=low+t;mid=(low+high)/2
    R=s.diameter_mm/2+s.tip_gap_mm;width=s.frame_width_mm
    union=native.BooleanTypes.UnionBooleanType;cut=native.BooleanTypes.DifferenceBooleanType
    def boolean(body,tool,kind):f._boolean(manager,body,tool,kind,'Guard could not retain one connected solid.')
    if s.guard_type in ('spokes','rings'):
        result=f._guard(manager,replace(s,guard_type='spokes'),z,core,native)
        if s.guard_type=='rings':
            r=s.hub_diameter_mm/2+s.guard_pitch_mm
            while r<R:
                ring=f._cylinder(manager,core,r,low,high)
                boolean(ring,f._cylinder(manager,core,r-s.guard_spoke_mm,low-.1,high+.1),cut)
                boolean(result,ring,union);r+=s.guard_pitch_mm
        return result
    result=f._box(manager,core,width,width,t,(0,0,mid))
    aperture=f._cylinder(manager,core,R,low-.1,high+.1)
    if s.guard_type=='honeycomb':
        # A right-handed frame maps the footprint to XY and depth to Z.
        frame=HingeFrame((0,0,0),(1,0,0),(0,0,1),(0,-1,0))
        for points in hexagons(s):
            tool=a._direct_prism(frame,points,low-.05,high+.05)
            if any(math.hypot(x,y)>R for x,y in points):
                boolean(tool,manager.copy(aperture),native.BooleanTypes.IntersectionBooleanType)
            boolean(result,tool,cut)
    else:
        boolean(result,aperture,cut)
        n=math.floor(R/s.guard_pitch_mm)
        for i in range(-n,n+1):
            offset=i*s.guard_pitch_mm
            boolean(result,f._box(manager,core,width,s.guard_spoke_mm,t,(0,offset,mid)),union)
            if s.guard_type=='grid':boolean(result,f._box(manager,core,s.guard_spoke_mm,width,t,(offset,0,mid)),union)
    f._mount_holes(manager,result,s,low,high,core,native)
    return result

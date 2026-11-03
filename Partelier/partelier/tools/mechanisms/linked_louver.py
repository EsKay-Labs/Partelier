"""Parallel-crank louver assembly with separate flat printing layout.

Two split frame halves trap diamond journals. A common translating link has
holes coaxial with every vane crank eye. Assembly needs four frame fasteners
and one shoulder screw/pin per crank; those hardware fasteners are not printed
or simulated. No native joints or physical friction claims are implied.
"""
from dataclasses import dataclass,replace
from types import SimpleNamespace
import math,time

@dataclass(frozen=True)
class Dimensions:
    radius: float
    end_band: float
    pitch: float
    chord: float
    crank: float
    hole_radius: float
    centers: tuple

def dimensions(s):
    r=s.pin_diameter_mm/2+s.clearance_mm+s.wall_mm
    band=2*r+s.clearance_mm
    pitch=(s.width_mm-2*band)/s.count
    square=(pitch-s.clearance_mm)**2-4*r*r
    chord=math.sqrt(square) if square>0 else 0.
    return Dimensions(r,band,pitch,chord,r+s.clearance_mm,s.pin_diameter_mm/2+s.clearance_mm,
        tuple(-s.width_mm/2+band+(i+.5)*pitch for i in range(s.count)))

def validate(s):
    d=dimensions(s);t,g=s.wall_mm,s.clearance_mm
    if getattr(s,'output_mode','separate')!='separate':raise ValueError('Linked louvers are a separate assembly, not an attached two-body detail.')
    if not 0<=s.angle_deg<=60:raise ValueError('Linked louver angle must be between 0 and 60 degrees.')
    if s.length_mm<2*d.end_band+4*t:raise ValueError('Increase span to leave frame fastener bands and a clear vane opening.')
    if d.pitch<=0 or d.chord<2*t:raise ValueError('Increase frame width or reduce vane count, fastener diameter or wall thickness.')
    if math.hypot(d.crank+2*d.radius,2*d.radius)+g>=d.pitch:raise ValueError('Crank swept envelopes need more spacing. Increase width or reduce vane count.')
    if s.height_mm<d.pitch+g:raise ValueError('Frame depth must exceed vane pitch plus clearance for the full turning envelope.')
    if d.radius/math.sqrt(2)-d.hole_radius<.6:raise ValueError('Crank eyes need at least 0.6 mm material around their screw bore. Increase wall thickness.')
    if getattr(s,'assembly_layout','assembled') not in ('assembled','print'):raise ValueError('Choose assembled or flat print layout.')
    return d

def centers_at(s,angle_deg):
    d=validate(s);theta=math.radians(angle_deg)
    return tuple((y+d.crank*math.cos(theta),s.height_mm/2+d.crank*math.sin(theta)) for y in d.centers)

def build(s,core,native,manager):
    from ..patterns.prism import prism
    from ..patterns import fusion as a
    d=validate(s);l,w,h,t,g=s.length_mm,s.width_mm,s.height_mm,s.wall_mm,s.clearance_mm
    union=native.BooleanTypes.UnionBooleanType;cut=native.BooleanTypes.DifferenceBooleanType
    def boolean(b,tool,op):
        a._boolean(manager,b,tool,op,'Linked louver geometry failed. Review frame size and clearances.');return b
    def box(x0,x1,y0,y1,z0,z1):
        return manager.createBox(core.OrientedBoundingBox3D.create(core.Point3D.create((x0+x1)/20,(y0+y1)/20,(z0+z1)/20),core.Vector3D.create(1,0,0),core.Vector3D.create(0,1,0),(x1-x0)/10,(y1-y0)/10,(z1-z0)/10))
    def cyl_x(y,z,r,x0,x1):return manager.createCylinderOrCone(core.Point3D.create(x0/10,y/10,z/10),r/10,core.Point3D.create(x1/10,y/10,z/10),r/10)
    def cyl_z(x,y,r,z0,z1):return manager.createCylinderOrCone(core.Point3D.create(x/10,y/10,z0/10),r/10,core.Point3D.create(x/10,y/10,z1/10),r/10)
    yz=SimpleNamespace(origin_mm=(0,0,0),x_axis=(0,1,0),y_axis=(1,0,0),z_axis=(0,0,-1))
    def profile(points,x0,x1):
        p=tuple((y,-z) for y,z in points)
        if sum(one[0]*two[1]-two[0]*one[1] for one,two in zip(p,p[1:]+p[:1]))<0:p=tuple(reversed(p))
        return prism(yz,p,x0,x1)
    def diamond(y,z,r,x0,x1):return profile(((y-r,z),(y,z-r),(y+r,z),(y,z+r)),x0,x1)
    def tear(y,z,r,x0,x1):
        # Circumscribed polygon preserves the requested circular hardware envelope.
        rho=r/math.cos(math.radians(2.5))
        points=[(y+rho/math.sqrt(2),z+rho/math.sqrt(2)),(y,z+rho*math.sqrt(2))]
        points.extend((y+rho*math.cos(math.radians(angle)),z+rho*math.sin(math.radians(angle))) for angle in range(135,405,5))
        return profile(tuple(points),x0,x1)
    def move(body,dx,dy,dz):
        matrix=core.Matrix3D.create();matrix.translation=core.Vector3D.create(dx/10,dy/10,dz/10)
        if not manager.transform(body,matrix):raise ValueError('Could not place a linked louver part.')
    def rotate(body,angle,y,z):
        matrix=core.Matrix3D.create();matrix.setToRotation(math.radians(angle),core.Vector3D.create(1,0,0),core.Point3D.create(0,y/10,z/10))
        if not manager.transform(body,matrix):raise ValueError('Could not rotate a linked louver part.')
    z=h/2;inner=l/2-t;frames=[]
    for lo,hi in ((0,z),(z,h)):
        body=box(-l/2,l/2,-w/2,w/2,lo,hi)
        boolean(body,box(-inner,inner,-w/2+d.end_band,w/2-d.end_band,lo-.1,hi+.1),cut)
        for y in d.centers:boolean(body,cyl_x(y,z,d.radius+g,-l/2-.1,l/2+.1),cut)
        for x in (-l/2+d.end_band/2,l/2-d.end_band/2):
            for y in (-w/2+d.end_band/2,w/2-d.end_band/2):boolean(body,cyl_z(x,y,d.hole_radius,lo-.1,hi+.1),cut)
        frames.append(body)
    crank_x=l/2+s.pin_diameter_mm+t+2*g;link_x=crank_x+t+g;blades=[]
    theta=0 if s.assembly_layout=='print' else s.angle_deg
    for y in d.centers:
        blade=box(-inner+g,inner-g,y-d.chord/2,y+d.chord/2,z-d.radius,z+d.radius)
        boolean(blade,diamond(y,z,d.radius,-l/2+g,crank_x+t*.5),union)
        crank=diamond(y,z,d.radius,crank_x,crank_x+t)
        boolean(crank,box(crank_x,crank_x+t,y,y+d.crank,z-d.radius,z+d.radius),union)
        boolean(crank,diamond(y+d.crank,z,d.radius,crank_x,crank_x+t),union)
        boolean(crank,tear(y+d.crank,z,d.hole_radius,crank_x-.1,crank_x+t+.1),cut)
        boolean(blade,crank,union)
        rotate(blade,theta,y,z);blades.append(blade)
    pin_centers=centers_at(s,theta);link_z=pin_centers[0][1]
    link=box(link_x,link_x+t,pin_centers[0][0]-d.radius,pin_centers[-1][0]+d.radius,link_z-d.radius,link_z+d.radius)
    for y,pz in pin_centers:boolean(link,cyl_x(y,pz,d.hole_radius,link_x-.1,link_x+t+.1),cut)
    bodies=[*frames,*blades,link]
    names=['Split frame back','Split frame front']+[f'Linked vane {i+1}' for i in range(s.count)]+['Common crank link']
    if s.assembly_layout=='print':
        # Frame halves rest on their outer flat backs; pivot slots face upwards.
        rotate(frames[1],180,0,z);move(frames[1],l+10,0,0)
        blade_right=0.
        for i,body in enumerate(blades):
            bounds=body.boundingBox
            move(body,-bounds.minPoint.x*10,w/2+10+i*(d.chord+d.crank+2*d.radius+10)-bounds.minPoint.y*10,-bounds.minPoint.z*10)
            blade_right=max(blade_right,body.boundingBox.maxPoint.x*10)
        # The link prints broad face down, with vertical fastener bores.
        matrix=core.Matrix3D.create();matrix.setToRotation(math.pi/2,core.Vector3D.create(0,1,0),core.Point3D.create(0,0,0))
        if not manager.transform(link,matrix):raise ValueError('Could not lay the control link flat.')
        bounds=link.boundingBox;move(link,max(l+10,blade_right+10)-bounds.minPoint.x*10,w/2+10-bounds.minPoint.y*10,-bounds.minPoint.z*10)
    return tuple(bodies),tuple(names)

def motion(s,core,native,manager):
    """Finite simultaneous crank positions, pairwise solids and journal identity."""
    started=time.perf_counter();d=validate(s);checks=0
    for angle in range(0,61,10):
        sample=replace(s,angle_deg=float(angle),assembly_layout='assembled')
        bodies,_=build(sample,core,native,manager)
        centers=centers_at(sample,angle)
        for i in range(1,len(centers)):
            if abs(centers[i][0]-centers[i-1][0]-d.pitch)>1e-9 or abs(centers[i][1]-centers[0][1])>1e-9:raise ValueError('The common link does not preserve crank pitch.')
        for i,left in enumerate(bodies):
            for right in bodies[i+1:]:
                witness=manager.copy(left);original=float(witness.volume)
                if not manager.booleanOperation(witness,right,native.BooleanTypes.DifferenceBooleanType):raise ValueError('Could not verify the linked louver motion sample.')
                if not witness.isValid or not witness.isSolid or abs(float(witness.volume)-original)>max(1e-9,original*1e-8):raise ValueError(f'Linked louver collision at {angle} degrees.')
                checks+=1
    return {'sampled_angles_deg':list(range(0,61,10)),'pairwise_checks':checks,'continuous_sweep':False,'seconds':time.perf_counter()-started,'linkage':'parallel cranks with equal pitch','requires_assembly_fasteners':True}


def print_check(s,core,native,manager):
    """Check the generated flat layout and each face's underside witness."""
    flat=replace(s,assembly_layout='print');bodies,names=build(flat,core,native,manager);faces=0
    for body,name in zip(bodies,names):
        if abs(body.boundingBox.minPoint.z)>1e-7:raise ValueError(name+' does not touch the print bed.')
        for face in body.faces:
            if face.boundingBox.maxPoint.z<1e-7:continue
            ok,normal=face.evaluator.getNormalAtPoint(face.pointOnFace)
            if not ok or normal.z < -math.sqrt(.5)-1e-6:raise ValueError(name+' has an underside exceeding 45 degrees in the flat layout.')
            faces+=1
    return {'bodies':len(bodies),'underside_faces_checked':faces,'underside_limit_deg':45,'physical_print_tested':False}

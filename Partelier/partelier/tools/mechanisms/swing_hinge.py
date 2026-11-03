"""Unequal-arm four-bar swing: moving mounting plate rotates through 90 degrees.

Separate flat-print parts, external shoulder screws, no cabinetry collision claim.
Ratios of the two arms/coupler are fixed; arm length and ground spacing are custom.
"""
from dataclasses import replace
import math,time

NAMES=('Fixed swing plate','Rotating swing plate','Short swing arm','Long swing arm','Ground spacer A','Ground spacer D','Coupler spacer B','Coupler spacer C')

def dimensions(s):
    a=s.length_mm;return a,2*a/3,7*a/6,s.width_mm,s.pin_diameter_mm/2+s.clearance_mm+s.wall_mm,s.pin_diameter_mm/2+s.clearance_mm,s.pin_diameter_mm+s.wall_mm+2*s.clearance_mm

def _points(s,drive):
    a,b,c,d,*_=dimensions(s);q=math.radians(drive);B=(a*math.cos(q),a*math.sin(q));v=(d-B[0],-B[1]);e=math.hypot(*v)
    if not abs(b-c)+.1<e<b+c-.1:raise ValueError('Swing linkage reaches a toggle. Adjust arm length or fixed pivot spacing.')
    u=(b*b-c*c+e*e)/(2*e);h=math.sqrt(max(0,b*b-u*u));C=(B[0]+(u*v[0]-h*v[1])/e,B[1]+(u*v[1]+h*v[0])/e)
    return ((0.,0.),B,C,(d,0.)),math.degrees(math.atan2(C[1]-B[1],C[0]-B[0]))

def pivots(s,opening):
    _,closed=_points(s,25);_,opened=_points(s,95);target=closed-opening
    if not opened<=target<=closed:raise ValueError('These dimensions cannot provide the requested opening.')
    low,high=25.,95.
    for _ in range(48):
        mid=(low+high)/2;_,phi=_points(s,mid)
        if phi>target:low=mid
        else:high=mid
    return _points(s,(low+high)/2)[0]

def validate(s):
    a,b,c,d,r,hole,j=dimensions(s)
    if s.output_mode!='separate':raise ValueError('Offset four-bar hinge is a separate fastener assembly.')
    if not 0<=s.angle_deg<=90:raise ValueError('Hinge opening must be 0 to 90 degrees.')
    if s.height_mm<2*r:raise ValueError('Mounting plate width must retain the pivot eyes.')
    if b/3<=2*hole+s.wall_mm:raise ValueError('Increase arm length to separate the mounting and pivot holes.')
    if d/3<=2*hole+s.wall_mm:raise ValueError('Increase ground spacing to separate the mounting holes.')
    _,closed=_points(s,25);_,opened=_points(s,95)
    if closed-opened<90:raise ValueError('This arm length / ground spacing cannot produce a 90-degree swing.')
    previous=closed
    for drive in range(26,96):
        _,phi=_points(s,drive)
        if phi>=previous:raise ValueError('Linkage crosses an unsupported motion branch.')
        previous=phi
    return dimensions(s)

def build(s,core,native,manager):
    from ..patterns import fusion as adapter
    a,b,c,d,r,hole,j=validate(s);t=s.wall_mm;A,B,C,D=pivots(s,s.angle_deg)
    union=native.BooleanTypes.UnionBooleanType;cut=native.BooleanTypes.DifferenceBooleanType
    def box(x0,x1,y0,y1,z0,z1):return manager.createBox(core.OrientedBoundingBox3D.create(core.Point3D.create((x0+x1)/20,(y0+y1)/20,(z0+z1)/20),core.Vector3D.create(1,0,0),core.Vector3D.create(0,1,0),(x1-x0)/10,(y1-y0)/10,(z1-z0)/10))
    def cyl(y,z,radius,x0,x1):return manager.createCylinderOrCone(core.Point3D.create(x0/10,y/10,z/10),radius/10,core.Point3D.create(x1/10,y/10,z/10),radius/10)
    def boolean(body,tool,op):adapter._boolean(manager,body,tool,op,'Swing hinge geometry is invalid.');return body
    def link(P,Q,x,plate=False):
        length=math.dist(P,Q);half=s.height_mm/2 if plate else r
        body=box(x,x+t,-r if plate else 0,length+r if plate else length,-half,half)
        if not plate:
            for y in (0,length):boolean(body,cyl(y,0,r,x,x+t),union)
        for y in ((0,length,length/3,2*length/3) if plate else (0,length)):boolean(body,cyl(y,0,hole,x-.1,x+t+.1),cut)
        matrix=core.Matrix3D.create();matrix.setToRotation(math.atan2(Q[1]-P[1],Q[0]-P[0]),core.Vector3D.create(1,0,0),core.Point3D.create(0,0,0));matrix.translation=core.Vector3D.create(0,P[0]/10,P[1]/10)
        if not manager.transform(body,matrix):raise ValueError('Could not place swing link.')
        return body
    fixed=link(A,D,0,True);moving=link(B,C,2*t+2*j,True)
    short=link(A,B,t+j);long=link(D,C,3*t+3*j)
    collars=[]
    for P,x0,x1 in ((A,t,t+j),(D,t,3*t+3*j),(B,2*t+j,2*t+2*j),(C,3*t+2*j,3*t+3*j)):
        body=cyl(*P,r,x0,x1);boolean(body,cyl(*P,hole,x0-.1,x1+.1),cut);collars.append(body)
    bodies=(fixed,moving,short,long,*collars)
    if s.assembly_layout=='print':
        cursor=0.
        for body in bodies:
            matrix=core.Matrix3D.create();matrix.setToRotation(math.pi/2,core.Vector3D.create(0,1,0),core.Point3D.create(0,0,0))
            if not manager.transform(body,matrix):raise ValueError('Could not lay swing part flat.')
            bounds=body.boundingBox;shift=core.Matrix3D.create();shift.translation=core.Vector3D.create(cursor/10-bounds.minPoint.x,-bounds.minPoint.y,-bounds.minPoint.z)
            if not manager.transform(body,shift):raise ValueError('Could not place swing part on bed.')
            cursor=body.boundingBox.maxPoint.x*10+8
    return bodies,NAMES

def motion(s,core,native,manager):
    start=time.perf_counter();checks=0;angles=list(range(0,91,5));a,b,c,d,*_=validate(s);_,closed=_points(s,25)
    for angle in angles:
        sample=replace(s,angle_deg=angle,assembly_layout='assembled');A,B,C,D=pivots(sample,angle)
        for left,right,length in ((A,B,a),(B,C,b),(C,D,c),(D,A,d)):
            if abs(math.dist(left,right)-length)>1e-8:raise ValueError('Four-bar changed its link lengths.')
        actual=closed-math.degrees(math.atan2(C[1]-B[1],C[0]-B[0]))
        if abs(actual-angle)>1e-8:raise ValueError('Output plate did not reach the requested opening.')
        bodies,_=build(sample,core,native,manager)
        for i,left in enumerate(bodies):
            for right in bodies[i+1:]:
                witness=manager.copy(left);volume=witness.volume
                if not manager.booleanOperation(witness,right,native.BooleanTypes.DifferenceBooleanType):raise ValueError('Could not check swing interference.')
                if not witness.isValid or not witness.isSolid or abs(witness.volume-volume)>max(1e-9,volume*1e-8):raise ValueError(f'Swing hinge collision at {angle} degrees, pair {i}.')
                checks+=1
    return {'opening_angles_deg':angles,'pairwise_checks':checks,'output_rotation_deg':90,'continuous_sweep':False,'requires_external_fasteners':True,'seconds':time.perf_counter()-start}

def print_check(s,core,native,manager):
    bodies,_=build(replace(s,assembly_layout='print'),core,native,manager);faces=0
    for body in bodies:
        if abs(body.boundingBox.minPoint.z)>1e-7:raise ValueError('Swing part floats above print bed.')
        for face in body.faces:
            if face.boundingBox.maxPoint.z<1e-7:continue
            ok,normal=face.evaluator.getNormalAtPoint(face.pointOnFace)
            if not ok or normal.z < -math.sqrt(.5)-1e-6:raise ValueError('Swing part has an unsupported underside.')
            faces+=1
    return {'bodies':len(bodies),'underside_faces_checked':faces,'underside_limit_deg':45,'physical_print_tested':False}

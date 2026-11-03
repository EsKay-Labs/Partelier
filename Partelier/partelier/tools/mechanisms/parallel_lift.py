"""Equal-arm four-bar lift, with real pivot bores and four spacer collars.

The mounting plates remain parallel. This is not a swinging concealed hinge.
Four shoulder screws/pins connect the four pivot axes; those fasteners are
external hardware. Flat print layout puts every broad back onto the bed.
"""
from dataclasses import replace
import math,time

def dimensions(s):
    r=s.pin_diameter_mm/2+s.clearance_mm+s.wall_mm
    hole=s.pin_diameter_mm/2+s.clearance_mm
    spacer=s.pin_diameter_mm+s.wall_mm+2*s.clearance_mm
    return r,hole,spacer

def validate(s):
    r,hole,spacer=dimensions(s)
    if getattr(s,'output_mode','separate')!='separate':raise ValueError('Parallel-lift linkage is a separate assembly.')
    if not 0<=s.angle_deg<=60:raise ValueError('Parallel lift angle must be 0 to 60 degrees.')
    if s.length_mm<=4*r:raise ValueError('Increase arm length to separate its two pivot eyes.')
    if s.width_mm<=s.length_mm+2*r+2*s.clearance_mm:raise ValueError('Pivot spacing must exceed arm length plus both eye radii and clearance.')
    if s.height_mm<2*r:raise ValueError('Mounting plate height needs complete material around its pivot holes.')
    if s.width_mm/4<=2*hole+s.wall_mm:raise ValueError('Mounting holes need more distance from the pivot holes.')
    if getattr(s,'assembly_layout','assembled') not in ('assembled','print'):raise ValueError('Choose assembled or flat print layout.')
    return r,hole,spacer

def pivots(s,angle):
    dy=s.length_mm*math.cos(math.radians(angle));dz=s.length_mm*math.sin(math.radians(angle));z=s.height_mm/2
    a=((-s.width_mm/2,z),(s.width_mm/2,z))
    return a,tuple((y+dy,z+dz) for y,z in a)

def build(s,core,native,manager):
    from ..patterns import fusion as a
    r,hole,j=validate(s);t,g=s.wall_mm,s.clearance_mm;length,span,h=s.length_mm,s.width_mm,s.height_mm
    union=native.BooleanTypes.UnionBooleanType;cut=native.BooleanTypes.DifferenceBooleanType
    def box(x0,x1,y0,y1,z0,z1):return manager.createBox(core.OrientedBoundingBox3D.create(core.Point3D.create((x0+x1)/20,(y0+y1)/20,(z0+z1)/20),core.Vector3D.create(1,0,0),core.Vector3D.create(0,1,0),(x1-x0)/10,(y1-y0)/10,(z1-z0)/10))
    def cyl(y,z,radius,x0,x1):return manager.createCylinderOrCone(core.Point3D.create(x0/10,y/10,z/10),radius/10,core.Point3D.create(x1/10,y/10,z/10),radius/10)
    def boolean(body,tool,op):a._boolean(manager,body,tool,op,'Parallel-lift geometry is disconnected or invalid.');return body
    angle=0. if s.assembly_layout=='print' else s.angle_deg
    A,B=pivots(s,angle);dy=B[0][0]-A[0][0];dz=B[0][1]-A[0][1]
    fixed=box(0,t,-span/2-r,span/2+r,0,h)
    bx=2*t+2*j;moving=box(bx,bx+t,-span/2-r+dy,span/2+r+dy,dz,dz+h)
    for body,x0,pairs in ((fixed,0,A),(moving,bx,B)):
        for y,z in pairs:boolean(body,cyl(y,z,hole,x0-.1,x0+t+.1),cut)
        midpoint_y=(pairs[0][0]+pairs[1][0])/2;z=pairs[0][1]
        for y in (midpoint_y-span/4,midpoint_y+span/4):boolean(body,cyl(y,z,hole,x0-.1,x0+t+.1),cut)
    arms=[];x=t+j
    for ay,az in A:
        arm=box(x,x+t,ay,ay+length,az-r,az+r)
        for y in (ay,ay+length):boolean(arm,cyl(y,az,r,x,x+t),union);boolean(arm,cyl(y,az,hole,x-.1,x+t+.1),cut)
        matrix=core.Matrix3D.create();matrix.setToRotation(math.radians(angle),core.Vector3D.create(1,0,0),core.Point3D.create(0,ay/10,az/10))
        if not manager.transform(arm,matrix):raise ValueError('Could not position a lift arm.')
        arms.append(arm)
    collars=[]
    for points,x0,x1 in ((A,t,t+j),(B,2*t+j,2*t+2*j)):
        for y,z in points:
            collar=cyl(y,z,r,x0,x1);boolean(collar,cyl(y,z,hole,x0-.1,x1+.1),cut);collars.append(collar)
    bodies=[fixed,moving,*arms,*collars]
    names=['Fixed lift plate','Parallel moving plate','Lift arm A','Lift arm B','Fixed spacer A','Fixed spacer B','Moving spacer A','Moving spacer B']
    if s.assembly_layout=='print':
        cursor=0.
        for body in bodies:
            matrix=core.Matrix3D.create();matrix.setToRotation(math.pi/2,core.Vector3D.create(0,1,0),core.Point3D.create(0,0,0))
            if not manager.transform(body,matrix):raise ValueError('Could not lay a lift part flat.')
            bounds=body.boundingBox;shift=core.Matrix3D.create();shift.translation=core.Vector3D.create(cursor/10-bounds.minPoint.x,-bounds.minPoint.y,-bounds.minPoint.z)
            if not manager.transform(body,shift):raise ValueError('Could not place a lift part on the print bed.')
            cursor=body.boundingBox.maxPoint.x*10+8
    return tuple(bodies),tuple(names)

def motion(s,core,native,manager):
    start=time.perf_counter();validate(s);checks=0
    for angle in range(0,61,10):
        sample=replace(s,angle_deg=float(angle),assembly_layout='assembled');bodies,_=build(sample,core,native,manager);A,B=pivots(sample,angle)
        for one,two in zip(A,B):
            if abs(math.dist(one,two)-s.length_mm)>1e-9:raise ValueError('Lift arm length changed across the path.')
        if abs(B[1][0]-B[0][0]-s.width_mm)>1e-9 or abs(B[0][1]-B[1][1])>1e-9:raise ValueError('Lift plate lost parallel alignment.')
        for i,left in enumerate(bodies):
            for right in bodies[i+1:]:
                witness=manager.copy(left);volume=float(witness.volume)
                if not manager.booleanOperation(witness,right,native.BooleanTypes.DifferenceBooleanType):raise ValueError('Could not check lift linkage interference.')
                if not witness.isValid or not witness.isSolid or abs(witness.volume-volume)>max(1e-9,volume*1e-8):raise ValueError(f'Lift linkage collision at {angle} degrees.')
                checks+=1
    return {'sampled_angles_deg':list(range(0,61,10)),'pairwise_checks':checks,'continuous_sweep':False,'maximum_lift_mm':s.length_mm*math.sin(math.radians(60)),'parallel_plate':True,'requires_assembly_fasteners':True,'seconds':time.perf_counter()-start}

def print_check(s,core,native,manager):
    bodies,_=build(replace(s,assembly_layout='print'),core,native,manager);faces=0
    for body in bodies:
        if abs(body.boundingBox.minPoint.z)>1e-7:raise ValueError('A lift part floats above the print bed.')
        for face in body.faces:
            if face.boundingBox.maxPoint.z<1e-7:continue
            ok,normal=face.evaluator.getNormalAtPoint(face.pointOnFace)
            if not ok or normal.z < -math.sqrt(.5)-1e-6:raise ValueError('Lift layout has an unsupported underside.')
            faces+=1
    return {'bodies':len(bodies),'underside_faces_checked':faces,'underside_limit_deg':45,'physical_print_tested':False}

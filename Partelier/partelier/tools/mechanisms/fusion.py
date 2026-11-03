"""Temporary analytical mechanical pairs; no persistent preview geometry."""
from dataclasses import dataclass, replace
from types import SimpleNamespace
import math, time
from . import planner
from ..patterns import fusion as a, display_export
from ..patterns.prism import prism
from ..fans.fusion import _box, draw
from ...diagnostics import emit


@dataclass(frozen=True)
class Prepared:
    design: object
    settings: object
    bodies: tuple
    names: tuple
    plan: object
    references: dict
    timings: dict
    record: object = None
    meshes: tuple = ()
    targets: tuple = ()
    tools: tuple = ()
    source_signature: tuple = ()


def prepare(design,settings,record=None,references=None):
    if settings.output_mode=='attached':
        from . import attachment
        return attachment.prepare(design,settings,record,references or {})
    import adsk.core as core
    import adsk.fusion as native
    started=time.perf_counter();s=settings;p=planner.plan(s)
    m=native.TemporaryBRepManager.get();union=native.BooleanTypes.UnionBooleanType;cut=native.BooleanTypes.DifferenceBooleanType
    intersect=native.BooleanTypes.IntersectionBooleanType
    def boolean(body,tool,kind):
        a._boolean(m,body,tool,kind,'Mechanism dimensions produced disconnected or invalid geometry. Review wall/clearance/size.');return body
    def box(x0,x1,y0,y1,z0,z1):
        return _box(m,core,x1-x0,y1-y0,z1-z0,((x0+x1)/2,(y0+y1)/2,(z0+z1)/2))
    def cylinder(radius,lo,hi,center=(0.,0.)):
        return a._solid(m.createCylinderOrCone(core.Point3D.create(center[0]/10,center[1]/10,lo/10),radius/10,
            core.Point3D.create(center[0]/10,center[1]/10,hi/10),radius/10),'Could not construct mechanism cylinder.')
    frame=SimpleNamespace(origin_mm=(0.,0.,0.),x_axis=(1.,0.,0.),y_axis=(0.,1.,0.),z_axis=(0.,0.,1.))
    xy=SimpleNamespace(origin_mm=(0.,0.,0.),x_axis=(1.,0.,0.),y_axis=(0.,0.,-1.),z_axis=(0.,1.,0.))
    def sector(inner,outer,start,end,lo,hi):
        body=cylinder(outer,lo,hi)
        boolean(body,cylinder(inner,lo-.1,hi+.1),cut)
        radius=outer*3
        triangle=((0.,0.),(radius*math.cos(start),radius*math.sin(start)),(radius*math.cos(end),radius*math.sin(end)))
        return boolean(body,prism(xy,triangle,-hi,-lo),intersect)
    l,w,h,t,g=s.length_mm,s.width_mm,s.height_mm,s.wall_mm,s.clearance_mm
    if s.family in ('slider','dovetail'):
        rail=box(-w/2-2*t,w/2+2*t,0,l,0,t)
        boolean(rail,prism(frame,p.rail_profile,0,l),union)
        carlength=l*.55
        outer=w/2+2*t+g
        carriage=box(-outer,outer,g,carlength,t+g,t+h+g+t)
        boolean(carriage,prism(frame,p.clearance_profile,-.1,carlength+.1),cut)
        if s.end_stop:boolean(rail,box(-w/2-2*t,w/2+2*t,l-t,l,t-.1,t+h+t),union)
        bodies=[rail,carriage]
    elif s.family=='bayonet':
        r=s.diameter_mm/2;male=cylinder(r,0,h);boolean(male,cylinder(r-t,-.1,h+.1),cut)
        sleeve=cylinder(r+g+2*t,0,h);boolean(sleeve,cylinder(r+g,-.1,h+.1),cut)
        half=(t/2)/r;spread=g/r;rotation=math.radians(s.angle_deg);lo=h*.5-t/2;hi=lo+t
        for i in range(s.count):
            theta=2*math.pi*i/s.count
            boolean(male,sector(r-.2,r+t,theta-half,theta+half,lo,hi),union)
            boolean(sleeve,sector(r-.1,r+t+g,theta-rotation-half-spread,theta+half+spread,lo-g,hi+g),cut)
            boolean(sleeve,sector(r-.1,r+t+g,theta-rotation-half-spread,theta-rotation+half+spread,lo-g,h+.1),cut)
        bodies=[male,sleeve]
    elif s.family=='clevis':
        r=w/2;back=-r-g-t
        fork=box(-l/2,back,-r,r,0,h)
        for lo,hi in ((0,t),(h-t,h)):
            ear=box(-l/2,0,-r,r,lo,hi);boolean(ear,cylinder(r,lo,hi),union);boolean(fork,ear,union)
        boolean(fork,cylinder((s.pin_diameter_mm+2*g)/2,-.1,h+.1),cut)
        tongue=cylinder(r-g,t+g,h-t-g)
        boolean(tongue,box(0,l/2,-r+g,r-g,t+g,h-t-g),union)
        boolean(tongue,cylinder((s.pin_diameter_mm+2*g)/2,-.1,h+.1),cut)
        pin=cylinder(s.pin_diameter_mm/2,-t,h+t)
        bodies=[fork,tongue,pin]
    elif s.family=='linked_louver':
        from .linked_louver import build
        bodies,names=build(s,core,native,m);p=replace(p,names=tuple(names))
    elif s.family=='swing_hinge':
        from .swing_hinge import build
        bodies,names=build(s,core,native,m);p=replace(p,names=tuple(names))
    elif s.family=='parallel_lift':
        from .parallel_lift import build
        bodies,names=build(s,core,native,m);p=replace(p,names=tuple(names))
    elif s.family=='pip_louver':
        # Adapted from our own PipLouverCoupon: bed-open teardrop sockets and
        # diamond pivots. Vanes print upright, all bodies touching Z=0.
        r=s.pin_diameter_mm/2;rho=r+g;inner=l/2-t
        body=box(-l/2,l/2,-w/2,w/2,0,h)
        boolean(body,box(-inner,inner,-w/2+t,w/2-t,-.1,h+.1),cut)
        yz_frame=SimpleNamespace(origin_mm=(0,0,0),x_axis=(0,1,0),y_axis=(1,0,0),z_axis=(0,0,-1))
        def yz(points,x0,x1):
            polygon=tuple((y,-z) for y,z in points)
            if sum(a[0]*b[1]-b[0]*a[1] for a,b in zip(polygon,polygon[1:]+polygon[:1]))<0:polygon=tuple(reversed(polygon))
            return prism(yz_frame,polygon,x0,x1)
        blades=[];pitch=(w-2*t)/s.count
        for i in range(s.count):
            y=-w/2+t+(i+.5)*pitch
            roof=[(y+rho/math.sqrt(2),r+rho/math.sqrt(2)),(y,r+rho*math.sqrt(2))]
            roof.extend((y+rho*math.cos(math.radians(a)),r+rho*math.sin(math.radians(a))) for a in range(135,405,5))
            for sign in (-1,1):
                x0,x1=sorted((sign*(inner-.02),sign*(l/2-.5)))
                boolean(body,yz(tuple(roof),x0,x1),cut)
            blade=box(-inner+g,inner-g,y-t/4,y+t/4,0,2*r)
            diamond=((y,0),(y+r,r),(y,2*r),(y-r,r))
            for sign in (-1,1):
                x0,x1=sorted((sign*(inner-.5-g),sign*(l/2-.5-g)))
                boolean(blade,yz(diamond,x0,x1),union)
            blades.append(blade)
        bodies=[body,*blades]
    else:
        # Axial knuckles with two continuous mounting leaves. Recessed style uses
        # compact cylindrical mounting tails; it is a single-axis mechanism.
        r=h;bodies=[None,None];bore=s.pin_diameter_mm/2+g
        for side,lo,hi in p.knuckles:
            knuckle=cylinder(r,lo,hi)
            boolean(knuckle,cylinder(bore,lo-.1,hi+.1),cut)
            if side==0:leaf=box(-r-w,-r*.5,-t/2,t/2,lo,hi)
            else:leaf=box(r*.5,r+w,-t/2,t/2,lo,hi)
            boolean(knuckle,leaf,union)
            if bodies[side] is None:bodies[side]=knuckle
            else:
                # Join the common back spine before adding disjoint knuckles.
                boolean(bodies[side],knuckle,union)
            if bodies[side] is knuckle:
                x0,x1=(-r-w,-r-w+t) if side==0 else (r+w-t,r+w)
                boolean(bodies[side],box(x0,x1,-t/2,t/2,0,l),union)
        if s.family in ('barrel','concealed'):
            # Cylindrical mounting tails on barrel; recessed rectangular leaves
            # on concealed. Both remain supplied as separate installable pairs.
            if s.family=='barrel':
                for i,sign in enumerate((-1,1)):
                    tail=cylinder(t,0,l,(sign*(r+w-t),0))
                    boolean(bodies[i],tail,union)
            pin=cylinder(s.pin_diameter_mm/2,-t,l+t);bodies.append(pin)
        else:
            # Integral captive axle connected to A through its first and last
            # knuckles. B retains the explicit radial and axial clearances.
            pin=cylinder(s.pin_diameter_mm/2,0,l)
            for side,lo,hi in p.knuckles:
                if side==0:boolean(bodies[0],cylinder(bore+.2,lo,hi),union)
            boolean(bodies[0],pin,union)
    transform=core.Matrix3D.create()
    transform.setToRotation(math.radians(s.placement_angle_deg),core.Vector3D.create(0,0,1),core.Point3D.create(0,0,0))
    transform.translation=core.Vector3D.create(s.x_mm/10,s.y_mm/10,s.z_mm/10)
    for body in bodies:
        if not m.transform(body,transform):raise ValueError('Could not position mechanism.')
    # A failed empty intersection is ambiguous. Difference must succeed and
    # preserve volume, following the existing snap-fit clearance witness.
    for i,body in enumerate(bodies):
        if not body.isSolid or body.lumps.count != 1:raise ValueError('A mechanism part is not one connected solid.')
        for other in bodies[i+1:]:
            test=m.copy(body);before=float(body.volume)
            if not m.booleanOperation(test,m.copy(other),cut):raise ValueError('Fusion could not verify mechanism clearance.')
            a._solid(test,'The mechanism parts overlap. Review clearance and wall dimensions.')
            if abs(float(test.volume)-before)>max(1e-9,before*1e-8):
                raise ValueError('The mechanism parts overlap. Review clearance and wall dimensions.')
    return Prepared(design,s,tuple(bodies),p.names,p,{}, {'prepare_ms':(time.perf_counter()-started)*1000,'bodies':len(bodies)},record)


def cache(prepared):
    meshes=tuple(display_export.capture(prepared.design,body,coarse=True) for body in prepared.bodies)
    emit('mechanism.prepare',**prepared.timings)
    return replace(prepared,meshes=meshes)

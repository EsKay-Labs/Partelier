"""Detached delta tools and full previews for the three Small details helpers."""

from dataclasses import dataclass,replace
import math
import threading
import time
from . import planner
from ..hinge import fusion as h
from ..patterns import fusion as a,prism,perforated_prism,profile_loft,display_export,clipping


EMBED=.15


@dataclass(frozen=True)
class Prepared:
    design: object
    settings: object
    faces: tuple
    targets: tuple
    tools: tuple
    results: tuple
    source_signature: tuple
    tokens: dict
    timings: dict
    record: object = None
    meshes: tuple = ()


def _unit(vector):
    length=math.sqrt(sum(v*v for v in vector))
    if length<1e-9:raise ValueError('A reference direction has zero length.')
    return tuple(v/length for v in vector)


def _xyz(point):return tuple(v*10 for v in (point.x,point.y,point.z))


def _normal(face):
    ok,n=face.evaluator.getNormalAtPoint(face.pointOnFace)
    if not ok:raise ValueError('Fusion could not read the support face normal.')
    return _unit((n.x,n.y,n.z))


def _frame(face):
    core,native=h._api()
    if core.Plane.cast(face.geometry) is None:raise ValueError('Select planar support faces.')
    outer=next((loop for loop in h._items(face.loops) if loop.isOuter),None)
    if outer is None:raise ValueError('The face has no closed outer boundary.')
    edges=tuple(c.edge for c in h._items(outer.coEdges))
    if len(edges)!=4 or any(core.Line3D.cast(e.geometry) is None for e in edges):
        raise ValueError('Lid and alignment tools need rectangular outer face boundaries.')
    edge=max(edges,key=lambda e:e.length)
    points=[]
    for edge in edges:
        for vertex in (edge.startVertex,edge.endVertex):
            point=_xyz(vertex.geometry)
            if not any(math.dist(point,p)<1e-6 for p in points):points.append(point)
    if len(points)!=4:raise ValueError('Select a four-corner rectangular face.')
    origin=tuple(sum(p[i] for p in points)/4 for i in range(3))
    axis=_unit(a._sub(_xyz(edge.endVertex.geometry),_xyz(edge.startVertex.geometry)));normal=_normal(face)
    frame=h.HingeFrame(origin,axis,normal,h._cross(axis,normal))
    coords=tuple(_local(frame,p) for p in points)
    bounds=tuple(v for i in (0,1) for v in (min(p[i] for p in coords),max(p[i] for p in coords)))
    for x,z in coords:
        if min(abs(x-bounds[0]),abs(x-bounds[1]))>1e-4 or min(abs(z-bounds[2]),abs(z-bounds[3]))>1e-4:
            raise ValueError('The outer boundary must be a straight rectangle.')
    return frame,bounds


def _local(frame,point):
    delta=a._sub(point,frame.origin_mm)
    return (a._dot(delta,frame.x_axis),a._dot(delta,frame.z_axis))


def world(frame,x,z,height):
    return tuple(o+x*u+z*v+height*n for o,u,v,n in zip(frame.origin_mm,frame.x_axis,frame.z_axis,frame.y_axis))


def _tool(body):
    if body is None or not body.isValid or not body.isTemporary or not body.isSolid or body.lumps.count<1 or body.volume<=0:
        raise ValueError('Fusion could not build the detail tool.')
    return body


def _union(manager,tools):
    _,native=h._api();result=_tool(manager.copy(tools[0]))
    for tool in tools[1:]:
        if manager.booleanOperation(result,_tool(manager.copy(tool)),native.BooleanTypes.UnionBooleanType) is False:
            raise ValueError('Fusion could not collect the repeated detail tools.')
    return _tool(result)


def _material(manager,mask,body,message):
    _,native=h._api();actual=a._copy(manager,mask);expected=float(mask.volume)
    if (manager.booleanOperation(actual,body,native.BooleanTypes.IntersectionBooleanType) is False
            or not actual.isValid or not actual.isSolid or abs(float(actual.volume)-expected)>max(1e-8,expected*1e-6)):
        raise ValueError(message)


def _cylinder(frame,point,low,high,radius,last=None):
    core,native=h._api();manager=native.TemporaryBRepManager.get()
    one=core.Point3D.create(*(v/10 for v in world(frame,*point,low)))
    two=core.Point3D.create(*(v/10 for v in world(frame,*point,high)))
    return _tool(manager.createCylinderOrCone(one,radius/10,two,(radius if last is None else last)/10))


def _ring(frame,bounds,outset,inset,low,high):
    return perforated_prism.create(frame,planner.rectangle(bounds,outset),(planner.rectangle(bounds,inset),),low,high)


def _mating(faces,settings):
    frame,bounds=_frame(faces[0]);_frame(faces[1])
    if a._dot(frame.y_axis,_normal(faces[1]))>-.99999:
        raise ValueError('Select two parallel mating faces facing each other: the base rim and the lid inside face.')
    gap=a._dot(a._sub(_xyz(faces[1].pointOnFace),frame.origin_mm),frame.y_axis)
    height=settings.lip_height_mm if settings.kind=='lid' else settings.pin_height_mm
    return frame,bounds,max(0,gap),planner.socket_depth(height,gap,settings.axial_clearance_mm)


def _pair_tools(faces,settings,manager):
    frame,bounds,gap,depth=_mating(faces,settings)
    A,B=(face.body for face in faces);floor=settings.socket_floor_mm;lead=settings.lead_mm
    if settings.kind=='lid':
        inset,width,height=settings.lip_inset_mm,settings.lip_width_mm,settings.lip_height_mm
        c=settings.lip_clearance_mm
        if inset<c+.1:raise ValueError('Lip inset must leave at least 0.1 mm beyond the receiving groove clearance.')
        _material(manager,_ring(frame,bounds,inset,inset+width,-EMBED,0),A,'The complete lip root must be supported by face A. Reduce inset/width or choose a wider rim.')
        # The full receiving ring plus a protected floor must be original B
        # material. This checks every point, not a few rays through the lid.
        _material(manager,_ring(frame,bounds,inset-c,inset+width+c,gap,gap+depth+floor),B,
            'The lid needs room for the complete groove and protected floor. Reduce height/clearance or use a thicker/wider lid.')
        lip=_ring(frame,bounds,inset,inset+width,-EMBED,height-lead if lead else height)
        if lead:
            cap=profile_loft.create(frame,planner.rectangle(bounds,inset),(planner.rectangle(bounds,inset+width),),
                planner.rectangle(bounds,inset+lead),(planner.rectangle(bounds,inset+width-lead),),height-lead,height)
            lip=_union(manager,(lip,cap))
        cut=_ring(frame,bounds,inset-c,inset+width+c,gap-.02,gap+depth)
        return (lip,cut),{'gap_mm':gap,'socket_depth_mm':depth,'lip_perimeter':True}
    positions=planner.pins(bounds,settings);r=settings.pin_diameter_mm/2;hole=(settings.pin_diameter_mm+settings.pin_clearance_mm)/2
    pins=[];holes=[]
    for point in positions:
        _material(manager,_cylinder(frame,point,-EMBED,0,r),A,'Each pin root needs full material on face A. Adjust inset/diameter or choose a wider rim.')
        _material(manager,_cylinder(frame,point,gap,gap+depth+floor,hole+lead),B,
            'Each receiving hole needs complete material and a protected floor. Reduce height/inset/diameter or choose a thicker lid.')
        pin=_cylinder(frame,point,-EMBED,settings.pin_height_mm-lead if lead else settings.pin_height_mm,r)
        if lead:pin=_union(manager,(pin,_cylinder(frame,point,settings.pin_height_mm-lead,settings.pin_height_mm,r,r-lead)))
        pins.append(pin);cut=_cylinder(frame,point,gap-.02,gap+depth,hole)
        if lead:cut=_union(manager,(cut,_cylinder(frame,point,gap-.02,gap+lead,hole+lead+.02,hole)))
        holes.append(cut)
    return (_union(manager,pins),_union(manager,holes)),{'gap_mm':gap,'socket_depth_mm':depth,'pin_count':len(positions),'pin_positions_mm':positions}


def _rib_tools(faces,settings,manager):
    core,native=h._api();one,two=faces;nA,nB=(_normal(face) for face in faces)
    if core.Plane.cast(one.geometry) is None or core.Plane.cast(two.geometry) is None or abs(a._dot(nA,nB))>1e-5:
        raise ValueError('Ribs need two perpendicular planar faces on the same body.')
    common=tuple(e for e in h._items(one.edges) if any(e==other for other in h._items(two.edges)) and core.Line3D.cast(e.geometry) is not None)
    if len(common)!=1:raise ValueError('Choose two support faces sharing one complete straight corner edge.')
    edge=common[0];start,end=_xyz(edge.startVertex.geometry),_xyz(edge.endVertex.geometry);axis=_unit(a._sub(end,start))
    if a._dot(h._cross(nA,axis),nB)<0:start,end=end,start;axis=tuple(-v for v in axis)
    frame=h.HingeFrame(start,nA,axis,nB);length=math.dist(start,end)
    centers=planner.rib_positions(length,settings.rib_width_mm,settings.rib_count,settings.rib_margin_mm)
    x,z=settings.rib_height_a_mm,settings.rib_height_b_mm;width=settings.rib_width_mm
    polygon=((-EMBED,-EMBED),(x,-EMBED),(-EMBED,z)) if settings.rib_style=='triangle' else ((-EMBED,-EMBED),(x,-EMBED),(x,z),(-EMBED,z))
    tools=[]
    for center in centers:
        lo,hi=center-width/2,center+width/2
        leg_a=clipping.rectangle(polygon,(-EMBED,0,0,z))
        leg_b=clipping.rectangle(polygon,(0,x,-EMBED,0))
        _material(manager,prism.prism(frame,leg_a,lo,hi),one.body,
            'Face A does not support the complete rib leg. Choose an inside corner or reduce its height.')
        _material(manager,prism.prism(frame,leg_b,lo,hi),one.body,
            'Face B does not support the complete rib leg. Choose an inside corner or reduce its reach.')
        tools.append(prism.prism(frame,polygon,lo,hi))
    return (_union(manager,tools),),{'rib_count':len(centers),'rib_centers_mm':centers,'support_length_mm':length}


def selection(design,faces,settings):
    core,native=h._api()
    if threading.current_thread() is not threading.main_thread() or design is None or not design.isValid or design.activeComponent!=design.rootComponent:
        raise ValueError('Use the root component of a Fusion Design on its main thread.')
    if design.designType!=native.DesignTypes.ParametricDesignType:raise ValueError('Small details need history enabled.')
    if len(faces)!=2 or any(native.BRepFace.cast(f) is None or not f.isValid or f.assemblyContext is not None for f in faces):
        raise ValueError('Select two native planar faces.')
    bodies=tuple(f.body for f in faces)
    for body in bodies:
        a._solid(body,'Select solid source bodies.')
        if body.isTemporary or body.parentComponent!=design.rootComponent:raise ValueError('Select bodies in the root component.')
    if settings.kind=='ribs' and bodies[0]!=bodies[1]:raise ValueError('Ribs join two support faces of the same body.')
    if settings.kind!='ribs' and bodies[0]==bodies[1]:raise ValueError('Choose a base and lid on two separate bodies.')
    return bodies[:1] if settings.kind=='ribs' else bodies


def prepare(design,faces,settings):
    settings.validate();started=time.perf_counter();targets=selection(design,faces,settings)
    signature=tuple(h._body_signature(body) for body in targets)
    core,native=h._api();manager=native.TemporaryBRepManager.get()
    tools,info=_rib_tools(faces,settings,manager) if settings.kind=='ribs' else _pair_tools(faces,settings,manager)
    results=[]
    for i,(body,tool) in enumerate(zip(targets,tools)):
        result=a._copy(manager,body)
        a._boolean(manager,result,_tool(manager.copy(tool)),native.BooleanTypes.DifferenceBooleanType if i else native.BooleanTypes.UnionBooleanType,
            'The detail did not stay connected to its selected body. Check support, dimensions and clearance.')
        if abs(float(result.volume)-float(body.volume))<1e-9:raise ValueError('The detail makes no change to the selected body.')
        results.append(result)
    if len(results)==2:
        common=a._copy(manager,results[0]);ok=manager.booleanOperation(common,results[1],native.BooleanTypes.IntersectionBooleanType)
        if ok and common.isValid and common.isSolid and common.volume>1e-8:raise ValueError('The two finished parts overlap. Increase mating clearance or separate the original parts.')
    return Prepared(design,settings,tuple(faces),targets,tools,tuple(results),signature,
        {'faces':[f.entityToken for f in faces],'bodies':[b.entityToken for b in targets]},
        {**info,'prepare_ms':(time.perf_counter()-started)*1000})


def validate(prepared):
    targets=selection(prepared.design,prepared.faces,prepared.settings)
    if targets!=prepared.targets or tuple(h._body_signature(b) for b in targets)!=prepared.source_signature:
        raise ValueError('The source bodies changed. Refresh the preview before Create.')


def cache(prepared):
    return replace(prepared,meshes=tuple(display_export.capture(prepared.design,body) for body in prepared.results))


def draw(prepared):
    group=None
    try:
        if len(prepared.meshes)!=len(prepared.results):raise ValueError('The detail preview mesh is missing.')
        for body,result,mesh in zip(prepared.targets,prepared.results,prepared.meshes):
            appearance=body.appearance or body.material.appearance or prepared.design.rootComponent.material.appearance
            group=display_export.draw(prepared.design,result,appearance,mesh,group=group)
        return group
    except Exception:
        if group is not None and group.isValid:group.deleteMe()
        raise

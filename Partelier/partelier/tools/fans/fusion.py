"""One smooth native blade, radial copies and independent optional output bodies."""

from dataclasses import dataclass,replace
import math,time
from . import planner
from ..patterns import fusion as a,display_export
from ..hinge import fusion as h
from ...diagnostics import emit


@dataclass(frozen=True)
class Prepared:
    design:object
    settings:object
    bodies:tuple
    names:tuple
    plan:object
    placement:tuple
    references:dict
    timings:dict
    record:object=None
    meshes:tuple=()
    reference_signature:str=''


IDENTITY=((0.,0.,0.),(1.,0.,0.),(0.,1.,0.),(0.,0.,1.))


def _cylinder(manager,core,radius,low,high,center=(0,0),axis=(0,0,1)):
    point=tuple((*center,0.))
    one=core.Point3D.create(*( (p+v*low)/10 for p,v in zip(point,axis)))
    two=core.Point3D.create(*( (p+v*high)/10 for p,v in zip(point,axis)))
    return a._solid(manager.createCylinderOrCone(one,radius/10,two,radius/10),'Fusion could not build the fan cylinder.')


def _box(manager,core,width,depth,height,center=(0,0,0),x=(1,0,0),y=(0,1,0)):
    bounds=core.OrientedBoundingBox3D.create(core.Point3D.create(*(v/10 for v in center)),core.Vector3D.create(*x),core.Vector3D.create(*y),width/10,depth/10,height/10)
    return a._solid(manager.createBox(bounds),'Fusion could not build the fan frame.')


def _boolean(manager,one,two,kind,label):return a._boolean(manager,one,two,kind,label)


def _samples(edge):
    ok,lo,hi=edge.evaluator.getParameterExtents()
    if not ok:raise ValueError('Could not read a fan edge.')
    points=[]
    for t in (0,.2,.4,.6,.8,1):
        ok,point=edge.evaluator.getPointAtParameter(lo+(hi-lo)*t)
        if not ok:raise ValueError('Could not locate a fan edge.')
        points.append(point)
    return points


def _fillet(root,base,body,edges,size,core,native,label):
    if not edges:raise ValueError('Could not identify the '+label+' edges. Use radius 0 or review the dimensions.')
    collection=core.ObjectCollection.create()
    for edge in edges:collection.add(edge)
    inp=root.features.filletFeatures.createInput()
    if hasattr(inp,'targetBaseFeature'):inp.targetBaseFeature=base
    inp.edgeSetInputs.addConstantRadiusEdgeSet(collection,core.ValueInput.createByReal(size/10),False)
    try:feature=root.features.filletFeatures.add(inp)
    except RuntimeError as error:raise ValueError('The requested '+label+' does not fit. Reduce its radius. '+str(error)) from error
    if feature is None or not feature.isValid or not body.isValid or not body.isSolid or feature.healthState==native.FeatureHealthStates.ErrorFeatureHealthState:
        raise ValueError('The requested '+label+' could not be completed. Reduce its radius. '+(feature.errorOrWarningMessage if feature else 'No feature.'))
    # Within an edited BaseFeature, feature.bodies can also expose earlier
    # component solids. The edge set explicitly identifies this source body.
    return body


def _blade(design,base,plan,settings,core,native,manager):
    root=design.rootComponent;inp=root.features.loftFeatures.createInput(native.FeatureOperations.NewBodyFeatureOperation)
    inp.targetBaseFeature=base
    for section in plan.sections:
        curve=core.NurbsCurve3D.createNonRational([core.Point3D.create(*(v/10 for v in p)) for p in section.points_mm],3,list(planner.KNOTS),False)
        if curve is None:raise ValueError('Could not define the blade section curve.')
        wire=manager.createWireFromCurves([curve])[0]
        face=manager.createFaceFromPlanarWires([wire])
        if face is None:raise ValueError('Could not close a blade section.')
        managed=root.bRepBodies.add(face,base)
        if managed is None or inp.loftSections.add(managed.faces.item(0)) is None:raise ValueError('Could not register a blade section.')
    try:feature=root.features.loftFeatures.add(inp)
    except RuntimeError as error:raise ValueError('Blade loft failed. Reduce sweep/twist or review the sketch outline. '+str(error)) from error
    created=[body for body in base.sourceBodies if body.isSolid] if feature else []
    if len(created)!=1:raise ValueError('Blade loft did not produce one owned solid.')
    managed=created[0]
    if settings.edge_round_mm:
        tip=plan.sections[-1];theta=math.radians(tip.sweep_deg)
        edges=[edge for edge in managed.edges if all(abs(point.x*math.cos(theta)+point.y*math.sin(theta)-tip.axis_radius_mm/10)<1e-6 for point in _samples(edge))]
        managed=_fillet(root,base,managed,edges,settings.edge_round_mm,core,native,'Tip edge radius')
    result=a._copy(manager,managed)
    # The requested diameter is an exact radial envelope, including smooth
    # interpolation between stations. Trim just the single prototype blade.
    mask=_cylinder(manager,core,settings.diameter_mm/2,plan.z_min_mm-20,plan.z_max_mm+20)
    _boolean(manager,result,mask,native.BooleanTypes.IntersectionBooleanType,'The blade does not fit its radial envelope.')
    return result


def _root_edges(body,hub_radius,core):
    edges=[]
    for edge in body.edges:
        faces=tuple(edge.faces)
        if len(faces)!=2:continue
        def hub(face):
            cyl=core.Cylinder.cast(face.geometry);plane=core.Plane.cast(face.geometry)
            return bool(cyl and abs(cyl.radius-hub_radius/10)<1e-6 or plane and abs(plane.normal.z)>.999)
        if any(hub(face) for face in faces) and any(core.NurbsSurface.cast(face.geometry) for face in faces):
            points=_samples(edge)
            if max(math.hypot(p.x,p.y)*10 for p in points)<hub_radius+.01:edges.append(edge)
    return edges


def _bore(manager,body,settings,core,native):
    low,high=body.boundingBox.minPoint.z*10-.1,body.boundingBox.maxPoint.z*10+.1
    radius=(settings.shaft_diameter_mm+settings.shaft_clearance_mm)/2
    cutter=_cylinder(manager,core,radius,low,high)
    if settings.shaft_shape=='d':
        left=-radius+settings.shaft_flat_mm
        mask=_box(manager,core,2*radius-left,2*radius+.2,high-low,((left+2*radius)/2,0,(low+high)/2))
        _boolean(manager,cutter,mask,native.BooleanTypes.IntersectionBooleanType,'Could not build the D-shaft bore.')
    _boolean(manager,body,cutter,native.BooleanTypes.DifferenceBooleanType,'Shaft hole disconnected the hub.')
    if settings.set_screw_diameter_mm:
        theta=math.pi/settings.blade_count;axis=(math.cos(theta),math.sin(theta),0)
        tool=_cylinder(manager,core,settings.set_screw_diameter_mm/2,0,settings.hub_diameter_mm/2+.05,axis=axis)
        _boolean(manager,body,tool,native.BooleanTypes.DifferenceBooleanType,'Set screw hole disconnected the hub.')
    return body


def _mount_holes(manager,body,settings,low,high,core,native):
    for x in (-settings.mount_pitch_mm/2,settings.mount_pitch_mm/2):
        for y in (-settings.mount_pitch_mm/2,settings.mount_pitch_mm/2):
            _boolean(manager,body,_cylinder(manager,core,settings.mount_hole_mm/2,low-.1,high+.1,(x,y)),native.BooleanTypes.DifferenceBooleanType,'Mount holes do not fit the frame.')


def _frame(manager,settings,plan,core,native):
    # Frame is centred on the rotor envelope, keeping explicit axial clearance.
    mid=(plan.z_min_mm+plan.z_max_mm)/2;low=mid-settings.frame_depth_mm/2;high=mid+settings.frame_depth_mm/2
    result=_box(manager,core,settings.frame_width_mm,settings.frame_width_mm,high-low,(0,0,mid))
    hole=_cylinder(manager,core,settings.diameter_mm/2+settings.tip_gap_mm,low-.1,high+.1)
    _boolean(manager,result,hole,native.BooleanTypes.DifferenceBooleanType,'Rotor opening does not fit the frame.')
    _mount_holes(manager,result,settings,low,high,core,native)
    return result,high


def _guard(manager,settings,z,core,native):
    width=settings.frame_width_mm;thickness=settings.guard_thickness_mm;center=z+settings.axial_clearance_mm+thickness/2
    result=_box(manager,core,width,width,thickness,(0,0,center))
    hole_radius=settings.diameter_mm/2+settings.tip_gap_mm
    _boolean(manager,result,_cylinder(manager,core,hole_radius,center-thickness,center+thickness),native.BooleanTypes.DifferenceBooleanType,'Could not open the fan guard.')
    center_ring=_cylinder(manager,core,settings.hub_diameter_mm/2,center-thickness/2,center+thickness/2)
    for i in range(settings.guard_spokes):
        angle=2*math.pi*i/settings.guard_spokes;x=(math.cos(angle),math.sin(angle),0);y=(-x[1],x[0],0)
        spoke=_box(manager,core,hole_radius+2,settings.guard_spoke_mm,thickness,((hole_radius+2)/2*x[0],(hole_radius+2)/2*x[1],center),x,y)
        _boolean(manager,result,spoke,native.BooleanTypes.UnionBooleanType,'Could not join a guard spoke.')
    _boolean(manager,result,center_ring,native.BooleanTypes.UnionBooleanType,'Could not join the guard centre.')
    _mount_holes(manager,result,settings,center-thickness/2,center+thickness/2,core,native)
    return result


def _blower(manager,settings,core,native):
    """One connected flat-backed radial impeller, made only from temporary solids."""
    radius=settings.diameter_mm/2;root=settings.hub_diameter_mm/2-.5
    low=-settings.hub_height_mm/2;floor=low+settings.blower_backplate_mm
    top=floor+settings.blower_height_mm
    body=_cylinder(manager,core,radius,low,floor)
    hub=_cylinder(manager,core,settings.hub_diameter_mm/2,low,settings.hub_height_mm/2)
    _boolean(manager,body,hub,native.BooleanTypes.UnionBooleanType,'Could not join the blower hub to its backplate.')
    for i in range(settings.blade_count):
        angle=i*2*math.pi/settings.blade_count;x=(math.cos(angle),math.sin(angle),0);y=(-x[1],x[0],0)
        mid=(root+radius)/2
        vane=_box(manager,core,radius-root,settings.blower_vane_mm,top-floor+.1,(mid*x[0],mid*x[1],(top+floor-.1)/2),x,y)
        _boolean(manager,body,vane,native.BooleanTypes.UnionBooleanType,'Could not attach a radial vane.')
    # Clip the tips once, after the union, to retain the exact specified diameter.
    _boolean(manager,body,_cylinder(manager,core,radius,low-.1,max(top,settings.hub_height_mm/2)+.1),native.BooleanTypes.IntersectionBooleanType,'Could not trim the blower tips.')
    return body


def prepare(design,settings,placement=IDENTITY,references=None,outline=(),record=None,geometry_cache=None):
    h._require_main_thread();settings.validate();plan=planner.plan(settings,outline);core,native=a._api()
    root=design.rootComponent
    if design.activeComponent!=root or design.designType!=native.DesignTypes.ParametricDesignType or design.timeline.markerPosition!=design.timeline.count:
        raise ValueError('Use a parametric Design with the root active and the timeline at the end.')
    started=time.perf_counter();manager=native.TemporaryBRepManager.get();before=(root.bRepBodies.count,design.timeline.count)
    base=None;editing=False;stages={};stage=started
    try:
        hub=_cylinder(manager,core,settings.hub_diameter_mm/2,-settings.hub_height_mm/2,settings.hub_height_mm/2)
        if settings.style=='blower' and settings.output!='hub_test':
            key=('blower',settings.diameter_mm,settings.hub_diameter_mm,settings.hub_height_mm,settings.blade_count,settings.blower_height_mm,settings.blower_backplate_mm,settings.blower_vane_mm)
            if geometry_cache is not None and geometry_cache.get('key')==key:
                hub=a._copy(manager,geometry_cache['body']);stages['rotor_cache_hit']=True
            else:
                hub=_blower(manager,settings,core,native)
                if geometry_cache is not None:geometry_cache.clear();geometry_cache.update(key=key,body=a._copy(manager,hub))
            stages['radial_vanes_ms']=(time.perf_counter()-stage)*1000
        elif settings.output!='hub_test':
            excluded=('size_preset', 'shaft_diameter_mm', 'shaft_clearance_mm', 'shaft_shape', 'shaft_flat_mm', 'set_screw_diameter_mm', 'tip_gap_mm', 'frame_width_mm', 'frame_depth_mm', 'mount_pitch_mm', 'mount_hole_mm', 'axial_clearance_mm', 'guard_thickness_mm', 'guard_spoke_mm', 'guard_spokes', 'output')
            key=(tuple((k,v) for k,v in settings.to_dict().items() if k not in excluded),tuple(outline))
            hit=geometry_cache is not None and geometry_cache.get('key')==key
            if hit:
                hub=a._copy(manager,geometry_cache['body']);stages['rotor_cache_hit']=True
            else:
                base=root.features.baseFeatures.add();base.name='Partelier fan scratch'
                if base.startEdit() is False:raise ValueError('Could not open fan scratch geometry.')
                editing=True
                blade=_blade(design,base,plan,settings,core,native,manager)
                stages['blade_loft_ms']=(time.perf_counter()-stage)*1000;stage=time.perf_counter()
                prototype=a._copy(manager,hub)
                _boolean(manager,prototype,a._copy(manager,blade),native.BooleanTypes.UnionBooleanType,'Blade root does not meet the hub.')
                if settings.root_fillet_mm:
                    managed=root.bRepBodies.add(prototype,base)
                    managed=_fillet(root,base,managed,_root_edges(managed,settings.hub_diameter_mm/2,core),settings.root_fillet_mm,core,native,'Root fillet')
                    prototype=a._copy(manager,managed)
                stages['prototype_finish_ms']=(time.perf_counter()-stage)*1000;stage=time.perf_counter()
                _boolean(manager,prototype,a._copy(manager,hub),native.BooleanTypes.DifferenceBooleanType,'Could not isolate the finished prototype blade.')
                volume=lambda body: float(body.getPhysicalProperties(native.CalculationAccuracy.VeryHighCalculationAccuracy).volume)
                expected=volume(hub)+settings.blade_count*volume(prototype)
                stages['prototype_volume_ms']=(time.perf_counter()-stage)*1000;stage=time.perf_counter()
                for i in range(settings.blade_count):
                    copy=a._copy(manager,prototype);matrix=core.Matrix3D.create()
                    matrix.setToRotation(i*2*math.pi/settings.blade_count,core.Vector3D.create(0,0,1),core.Point3D.create(0,0,0))
                    if not manager.transform(copy,matrix):raise ValueError('Could not repeat the prototype blade.')
                    _boolean(manager,hub,copy,native.BooleanTypes.UnionBooleanType,'A blade did not join the hub.')
                stages['repeat_ms']=(time.perf_counter()-stage)*1000;stage=time.perf_counter()
                if abs(volume(hub)-expected)>max(2e-6,expected*2e-6):
                    raise ValueError('Blades or root fillets overlap outside the hub. Reduce chord/count/sweep/fillet or enlarge the hub.')
                stages['result_volume_ms']=(time.perf_counter()-stage)*1000
                if settings.style=='ring':
                    radius=settings.diameter_mm/2
                    ring=_cylinder(manager,core,radius,-settings.ring_height_mm/2,settings.ring_height_mm/2)
                    _boolean(manager,ring,_cylinder(manager,core,radius-settings.ring_width_mm,-settings.ring_height_mm/2-.1,settings.ring_height_mm/2+.1),native.BooleanTypes.DifferenceBooleanType,'Could not open the tip ring.')
                    _boolean(manager,hub,ring,native.BooleanTypes.UnionBooleanType,'Tip ring does not join all blade tips. Increase Ring width/height.')
                if geometry_cache is not None:
                    geometry_cache.clear();geometry_cache.update(key=key,body=a._copy(manager,hub))
        _bore(manager,hub,settings,core,native)
        plan=replace(plan,z_min_mm=hub.boundingBox.minPoint.z*10,z_max_mm=hub.boundingBox.maxPoint.z*10)
        if settings.output in ('rotor_frame','rotor_guard') and plan.z_max_mm-plan.z_min_mm+2*settings.axial_clearance_mm>settings.frame_depth_mm+1e-5:
            raise ValueError('The actual smooth blade envelope exceeds Frame depth. Increase Frame depth or reduce blade twist/chord.')
        bodies=[hub];names=['Hub fit test' if settings.output=='hub_test' else 'Radial blower impeller' if settings.style=='blower' else 'Fan rotor']
        if settings.output in ('rotor_frame','rotor_guard'):
            frame,front=_frame(manager,settings,plan,core,native);bodies.append(frame);names.append('Fan frame')
            if settings.output=='rotor_guard':bodies.append(_guard(manager,settings,front,core,native));names.append('Fan guard')
        if settings.output=='blower_housing':
            from . import volute
            stage=time.perf_counter();housing,lid,volute_plan=volute.build(manager,settings,plan,core,native)
            bodies.extend((housing,lid));names.extend(('Blower volute housing','Blower inlet lid'))
            stages['volute_ms']=(time.perf_counter()-stage)*1000;stages['volute_segments']=volute_plan.segments
        transform=core.Matrix3D.create();origin,x,y,z=placement
        transform.setWithCoordinateSystem(core.Point3D.create(*(v/10 for v in origin)),core.Vector3D.create(*x),core.Vector3D.create(*y),core.Vector3D.create(*z))
        for body in bodies:
            if not manager.transform(body,transform):raise ValueError('Could not place the fan on its reference.')
        return Prepared(design,settings,tuple(bodies),tuple(names),plan,placement,references or {},
            {**stages,'prepare_ms':(time.perf_counter()-started)*1000,'prototype_blades':0 if settings.output=='hub_test' else 1,
             'blade_count':plan.blade_count,'bodies':len(bodies),'sector_gap_deg':plan.minimum_sector_gap_deg},record)
    finally:
        if base is not None:
            if editing and base.finishEdit() is False:raise RuntimeError('Could not finish fan scratch geometry.')
            if base.isValid and base.deleteMe() is False:raise RuntimeError('Could not remove fan scratch geometry.')
        if (root.bRepBodies.count,design.timeline.count)!=before:raise RuntimeError('Fan preparation needs rollback: scratch geometry remains.')


def cache(prepared):
    started=time.perf_counter()
    meshes=tuple(display_export.capture(prepared.design,body,coarse=True) for body in prepared.bodies)
    timings={**prepared.timings,'display_capture_ms':(time.perf_counter()-started)*1000,'triangles':sum(mesh.triangle_count for mesh in meshes)}
    emit('fan.prepare',**timings)
    return replace(prepared,meshes=meshes,timings=timings)


def draw(prepared):
    from . import display
    core,native=a._api()
    group=None
    try:
        if len(prepared.meshes)!=len(prepared.bodies):raise ValueError('Fan display mesh is missing.')
        material=prepared.design.rootComponent.material
        appearance=material.appearance if material is not None else None
        for index,(body,mesh) in enumerate(zip(prepared.bodies,prepared.meshes)):
            source=prepared.record.bodies[index].appearance if prepared.record is not None and index<len(prepared.record.bodies) else appearance
            group=display_export.draw(prepared.design,body,source,mesh,group=group,effect=display.material(source,core,native))
        return group
    except Exception:
        if group is not None and group.isValid:group.deleteMe()
        raise

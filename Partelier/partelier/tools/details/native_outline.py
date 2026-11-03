"""Exact native offsets for bounded general planar outer loops.

All sketches/extrudes/chamfers belong to one disposable BaseFeature. No sampled
polygon substitutes for the supplied boundary. Unsupported native offsets fail.
"""
import math
from . import fusion as d


def _profile(sketch,curves,distance,source_area,core,sign=None):
    constraints=sketch.geometricConstraints
    for direction in ((1,-1) if sign is None else (sign,)):
        created=None;children=()
        try:
            inp=constraints.createOffsetInput(list(curves),core.ValueInput.createByReal(direction*distance/10))
            inp.isTopologyMatched=True
            created=constraints.addOffset2(inp)
            if created is None:raise ValueError('Fusion could not offset this boundary.')
            children=tuple(created.childCurves)
            if not 1<=len(children)<=128:raise ValueError('The offset exceeds 128 curves.')
            for curve in children:curve.isConstruction=False
            if sign is not None:return direction
            profiles=tuple(sketch.profiles)
            if len(profiles)==1 and profiles[0].profileLoops.count==1 and 0<profiles[0].areaProperties().area<source_area-1e-8:
                return direction
        except RuntimeError:
            if sign is not None:raise
        if created is not None and created.isValid:created.deleteMe()
        for curve in children:
            if curve.isValid:curve.deleteMe()
    raise ValueError('The boundary cannot retain one inward offset. Reduce inset/width or simplify tight corners.')


def _ring_profile(root,base,face,edges,outer,inner,core):
    sketch=root.sketches.addToBaseOrFormFeature(face,base,False)
    if sketch is None:raise ValueError('Could not create the temporary outline sketch.')
    sketch.isVisible=False;projected=[]
    for edge in edges:
        collection=sketch.project(edge)
        if collection is None:raise ValueError('Could not project the exact outer boundary.')
        projected.extend(tuple(collection))
    if not 1<=len(projected)<=64:raise ValueError('General lip boundaries support at most 64 source curves.')
    if sketch.profiles.count!=1 or sketch.profiles.item(0).profileLoops.count!=1:raise ValueError('The outer boundary must enclose one simple region.')
    area=sketch.profiles.item(0).areaProperties().area
    # Projected model edges can have distinct coincident sketch endpoints, so
    # findConnectedCurves need not recover their BRep-loop connectivity. Pass
    # the ordered outer co-edge projections directly to the native offsetter.
    curves=tuple(projected)
    for curve in sketch.sketchCurves:curve.isConstruction=True
    sign=_profile(sketch,curves,outer,area,core)
    _profile(sketch,curves,inner,area,core,sign)
    rings=tuple(profile for profile in sketch.profiles if profile.profileLoops.count==2)
    if sketch.profiles.count!=2 or len(rings)!=1:raise ValueError('The lip offset splits or intersects itself. Reduce inset/width or smooth the source boundary.')
    return sketch,rings[0]


def _extrude(root,base,sketch,profile,low,high,normal,core,native):
    old=tuple(base.sourceBodies)
    origin=sketch.sketchToModelSpace(core.Point3D.create(0,0,0));tip=sketch.sketchToModelSpace(core.Point3D.create(0,0,1))
    direction=1 if sum(v*n for v,n in zip((tip.x-origin.x,tip.y-origin.y,tip.z-origin.z),normal))>0 else -1
    inp=root.features.extrudeFeatures.createInput(profile,native.FeatureOperations.NewBodyFeatureOperation)
    inp.targetBaseFeature=base;inp.startExtent=native.OffsetStartDefinition.create(core.ValueInput.createByReal(direction*low/10))
    extent=native.DistanceExtentDefinition.create(core.ValueInput.createByReal((high-low)/10))
    if not inp.setOneSideExtent(extent,native.ExtentDirections.PositiveExtentDirection if direction>0 else native.ExtentDirections.NegativeExtentDirection):raise ValueError('Could not define the lip extrusion.')
    feature=root.features.extrudeFeatures.add(inp)
    if feature is None or feature.healthState==native.FeatureHealthStates.ErrorFeatureHealthState:raise ValueError('The native outline extrusion failed.')
    added=tuple(body for body in base.sourceBodies if body not in old and body.isSolid)
    if len(added)!=1:raise ValueError('The native offset must produce one solid ring.')
    return added[0]


def tools(faces,settings,manager):
    core,native=d.h._api();face,lid=faces;root=face.body.parentComponent
    if settings.lip_layout!='closed':raise ValueError('General outlines require Continuous perimeter; selected sides is rectangular only.')
    normal=d._normal(face)
    if core.Plane.cast(face.geometry) is None or core.Plane.cast(lid.geometry) is None or d.a._dot(normal,d._normal(lid))>-.99999:raise ValueError('Choose opposing planar base and lid faces.')
    outer=next((loop for loop in face.loops if loop.isOuter),None)
    edges=tuple(co.edge for co in outer.coEdges) if outer else ()
    if not 1<=len(edges)<=64:raise ValueError('The outer boundary needs 1–64 connected edges.')
    gap=d.a._dot(d.a._sub(d._xyz(lid.pointOnFace),d._xyz(face.pointOnFace)),normal)
    depth=d.planner.socket_depth(settings.lip_height_mm,gap,settings.axial_clearance_mm);gap=max(0,gap)
    inset,width,height,c,lead=settings.lip_inset_mm,settings.lip_width_mm,settings.lip_height_mm,settings.lip_clearance_mm,settings.lead_mm
    if inset<c+.1:raise ValueError('Lip inset must retain at least0.1 mm beyond receiving clearance.')
    design=root.parentDesign;before=(root.bRepBodies.count,root.sketches.count,design.timeline.count)
    base=None;editing=False
    try:
        base=root.features.baseFeatures.add();base.name='Partelier general lip scratch'
        if not base.startEdit():raise ValueError('Could not open outline scratch geometry.')
        editing=True
        sketch,profile=_ring_profile(root,base,face,edges,inset,inset+width,core)
        rootmask=_extrude(root,base,sketch,profile,-d.EMBED,0,normal,core,native)
        d._material(manager,d.a._copy(manager,rootmask),face.body,'The complete offset lip root needs original base material.')
        lip=_extrude(root,base,sketch,profile,-d.EMBED,height,normal,core,native)
        if lead:
            collection=core.ObjectCollection.create()
            for cap in lip.faces:
                if core.Plane.cast(cap.geometry) is not None and d.a._dot(d._normal(cap),normal)>.99999 and abs(d.a._dot(d.a._sub(d._xyz(cap.pointOnFace),d._xyz(face.pointOnFace)),normal)-height)<1e-4:
                    for edge in cap.edges:collection.add(edge)
            if collection.count<2:raise ValueError('Could not identify the complete top ring for its lead-in.')
            inp=root.features.chamferFeatures.createInput2();inp.targetBaseFeature=base
            if not inp.chamferEdgeSets.addEqualDistanceChamferEdgeSet(collection,core.ValueInput.createByReal(lead/10),False):raise ValueError('Could not define the exact lead-in.')
            finish=root.features.chamferFeatures.add(inp)
            if finish is None or finish.healthState==native.FeatureHealthStates.ErrorFeatureHealthState:raise ValueError('Lead-in does not fit this outline. Reduce Lead-in or smooth tight corners.')
        detached_lip=d.a._copy(manager,lip)
        groove_sketch,groove_profile=_ring_profile(root,base,face,edges,inset-c,inset+width+c,core)
        floor=_extrude(root,base,groove_sketch,groove_profile,gap,gap+depth+settings.socket_floor_mm,normal,core,native)
        d._material(manager,d.a._copy(manager,floor),lid.body,'The complete groove and protected floor must fit in the lid material.')
        cutter=_extrude(root,base,groove_sketch,groove_profile,gap-.02,gap+depth,normal,core,native)
        return (detached_lip,d.a._copy(manager,cutter)),{'gap_mm':gap,'socket_depth_mm':depth,'lip_perimeter':True,'outline_kind':'native_offset','outline_edges':len(edges)}
    except RuntimeError as error:
        raise ValueError('Fusion could not offset or finish this outline without changing its topology. Reduce inset/width/lead-in or simplify the boundary. '+str(error)) from error
    finally:
        if base is not None:
            if editing and not base.finishEdit():raise RuntimeError('Could not close general lip scratch geometry.')
            if base.isValid and not base.deleteMe():raise RuntimeError('Could not remove general lip scratch geometry.')
        if (root.bRepBodies.count,root.sketches.count,design.timeline.count)!=before:raise RuntimeError('General lip preparation left scratch geometry; rollback is required.')

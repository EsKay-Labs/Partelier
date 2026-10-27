"""Shared analytic convex-cell/plate prism; one healed body, no booleans."""

import math
from . import prism as simple,perforated_prism,clipping


def _create(frame,outer,holes,low,high,outer_profile=None):
    # The rounded openings are subsets of these proven disjoint convex windows.
    # Reuse the established frame/outer/separation checks before SDK allocation.
    if holes:perforated_prism.plan(frame,outer,tuple(h.polygon_mm for h in holes),low,high)
    else:simple.plan_prism(frame,outer,low,high)
    core,native=simple._api();require=simple._required
    definition=require(native.BRepBodyDefinition.create(),'Fusion could not define the rounded profile.')
    definition.doFullHealing=True
    shell=require(require(definition.lumpDefinitions.add(),'Fusion could not define the rounded profile lump.').shellDefinitions.add(),'Fusion could not define the rounded profile shell.')
    def point(p,height):
        return core.Point3D.create(*(float(o+p[0]*x+height*y+p[1]*z)/10
            for o,x,y,z in zip(frame.origin_mm,frame.x_axis,frame.y_axis,frame.z_axis)))
    axis=core.Vector3D.create(*frame.y_axis)
    def coedge(loop,edge,reverse=False):
        return require(loop.bRepCoEdgeDefinitions.add(edge,reverse),'Fusion could not define a rounded profile co-edge.')
    def face(surface,reverse=False):
        return require(shell.faceDefinitions.add(require(surface,'Fusion could not define a rounded profile surface.'),reverse),'Fusion could not define a rounded profile face.')
    def loop(target):return require(target.loopDefinitions.add(),'Fusion could not define a rounded profile loop.')
    lower=face(core.Plane.create(point(outer[0],low),core.Vector3D.create(*(-v for v in frame.y_axis))))
    upper=face(core.Plane.create(point(outer[0],high),axis))

    def boundary(segments,hole=False):
        # Segment: start/end and optional exact arc midpoint/center/radius.
        lows=tuple(point(segment[0],low) for segment in segments)
        highs=tuple(point(segment[0],high) for segment in segments)
        lv=tuple(require(definition.createVertexDefinition(p),'Fusion could not define a rounded profile vertex.') for p in lows)
        hv=tuple(require(definition.createVertexDefinition(p),'Fusion could not define a rounded profile vertex.') for p in highs)
        vertical=tuple(require(definition.createEdgeDefinitionByCurve(a,b,core.Line3D.create(one,two)),
            'Fusion could not define a rounded profile thickness edge.') for a,b,one,two in zip(lv,hv,lows,highs))
        ledges=[];hedges=[]
        for i,(start,end,middle,center,radius) in enumerate(segments):
            j=(i+1)%len(segments)
            if middle is None:
                lcurve=core.Line3D.create(lows[i],lows[j]);hcurve=core.Line3D.create(highs[i],highs[j])
            else:
                lcurve=core.Arc3D.createByThreePoints(lows[i],point(middle,low),lows[j])
                hcurve=core.Arc3D.createByThreePoints(highs[i],point(middle,high),highs[j])
            le=require(definition.createEdgeDefinitionByCurve(lv[i],lv[j],require(lcurve,'Fusion could not define the rounded profile arc.')),'Fusion could not define a lower rounded profile edge.')
            he=require(definition.createEdgeDefinitionByCurve(hv[i],hv[j],require(hcurve,'Fusion could not define the rounded profile arc.')),'Fusion could not define an upper rounded profile edge.')
            ledges.append(le);hedges.append(he)
            if center is not None:
                side=face(core.Cylinder.create(point(center,low),axis,radius/10),hole)
            else:
                # CCW profile outward is (dz,0,-dx); reverse for hole walls.
                dx,dz=end[0]-start[0],end[1]-start[1];length=math.hypot(dx,dz);sign=-1 if hole else 1
                normal=core.Vector3D.create(*(sign*(dz*x-dx*z)/length for x,z in zip(frame.x_axis,frame.z_axis)))
                side=face(core.Plane.create(lows[i],normal))
            side_loop=loop(side)
            # Shared lower/upper cap edges have opposite orientation on walls.
            if hole:
                coedge(side_loop,le);coedge(side_loop,vertical[j]);coedge(side_loop,he,True);coedge(side_loop,vertical[i],True)
            else:
                coedge(side_loop,vertical[i]);coedge(side_loop,he);coedge(side_loop,vertical[j],True);coedge(side_loop,le,True)
        lower_loop,upper_loop=loop(lower),loop(upper)
        for edge in (reversed(ledges) if hole else ledges):coedge(lower_loop,edge,hole)
        for edge in (hedges if hole else reversed(hedges)):coedge(upper_loop,edge,not hole)

    def curved(value):
        segments=[]
        for i,corner in enumerate(value.corners):
            segments.append((corner.start,corner.end,corner.middle,corner.center,value.radius_mm))
            segments.append((corner.end,value.corners[(i+1)%len(value.corners)].start,None,None,None))
        return tuple(segments)
    boundary(curved(outer_profile) if outer_profile is not None else
        tuple((a,b,None,None,None) for a,b in zip(outer,outer[1:]+outer[:1])))
    for window in holes:boundary(curved(window),True)
    result=definition.createBody();expected=((outer_profile.area_mm2 if outer_profile is not None else clipping.area(outer))-math.fsum(h.area_mm2 for h in holes))*(high-low)/1000
    if result is None or not result.isValid or not result.isTemporary or not result.isSolid or result.lumps.count!=1:
        raise ValueError('Fusion could not create the rounded profile. '+str(tuple(definition.outcomeInfo)))
    if result.lumps.item(0).shells.count!=1 or result.lumps.item(0).shells.item(0).isVoid:
        raise ValueError('The rounded profile has an unexpected or reversed shell.')
    if abs(float(result.volume)-expected)>max(1e-9,expected*1e-7):
        raise ValueError('The rounded profile volume differs from its exact arc plan.')
    return result


def create(frame,outer,profiles,low,high):
    return _create(frame,tuple(outer),tuple(profiles),low,high)


def prism(frame,value,low,high):
    return _create(frame,value.polygon_mm,(),low,high,value)

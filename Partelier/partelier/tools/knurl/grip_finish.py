"""One bounded native fillet of motif edges on a disposable owned solid."""
import math
from ..hinge import fusion as h
from ..fans.fusion import _fillet


def _sharp(edge, height, outer, groove=False):
    if edge.faces.count != 2:return False
    ok,low,high=edge.evaluator.getParameterExtents()
    if not ok:raise ValueError("Could not read a grip edge.")
    points=[]
    for fraction in (.00001,.2,.4,.6,.8,.99999):
        ok,point=edge.evaluator.getPointAtParameter(low+(high-low)*fraction)
        if not ok:raise ValueError("Could not sample a grip edge.")
        points.append(point)
    z = [point.z*10 for point in points]
    # End rims are controlled independently by Top/Bottom edge.
    if max(z)<.001 or min(z)>height-.001:return False
    # Separate exposed crests from the lower groove junctions.
    at_crest=min(math.hypot(point.x,point.y)*10 for point in points)>=outer-.005
    if at_crest==groove:return False
    midpoint=points[len(points)//2];normals=[]
    for face in edge.faces:
        if groove and face.geometry.objectType=='adsk::core::Torus':return False
        ok,normal=face.evaluator.getNormalAtPoint(midpoint)
        if not ok:raise ValueError('Could not classify a grip edge for filleting.')
        normals.append(normal)
    return normals[0].angleTo(normals[1])>math.radians(2.)


def apply(design, body, radius, height, outer, groove=False):
    if not radius:return body
    core,native=h._api();manager=native.TemporaryBRepManager.get()
    root=design.rootComponent;base=None;editing=False
    try:
        base=root.features.baseFeatures.add()
        if not base.startEdit():raise ValueError('Could not prepare the grip fillet.')
        editing=True
        source=root.bRepBodies.add(body,base)
        edges=[edge for edge in source.edges if _sharp(edge,height,outer,groove)]
        if not edges and groove:return manager.copy(body)
        if not edges:raise ValueError('This pattern has no sharp interior grip edges to fillet. Use radius 0.')
        if len(edges)>256:raise ValueError('Too many grip edges to fillet efficiently. Increase spacing.')
        _fillet(root,base,source,edges,radius,core,native,'groove root fillet' if groove else 'grip crest fillet')
        result=manager.copy(source)
        if result is None or not result.isSolid or result.lumps.count!=1:
            raise ValueError('The grip fillet would disconnect the knob. Reduce its radius.')
        if not base.finishEdit():raise ValueError('Could not finish the grip fillet.')
        editing=False
        return result
    finally:
        if base is not None and base.isValid:
            if editing:base.finishEdit()
            if base.deleteMe() is False:raise RuntimeError('Could not remove the temporary grip fillet.')

"""One exact rectangular uniform plate, including a full-material proof."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Plate:
    face: object
    body: object
    chart: object
    frame: object
    outer: tuple
    thickness_mm: float
    across: tuple

    def local(self,point):
        delta=tuple(p-o for p,o in zip(point,self.frame.origin_mm))
        return tuple(sum(a*b for a,b in zip(delta,axis)) for axis in (self.frame.x_axis,self.frame.z_axis))

    def world(self,x,z,height=0):
        return tuple(o+x*u+z*v+height*n for o,u,v,n in zip(self.frame.origin_mm,
            self.frame.x_axis,self.frame.z_axis,self.frame.y_axis))


def inspect(design,faces,settings,body):
    from . import fusion as a
    from .grilles import prepare_louver_face
    from .prism import prism
    if len(faces)!=1 or settings.selection_scope!='faces':
        raise ValueError('This grille option needs one rectangular plate face, with its flat back on the bed.')
    try:context=prepare_louver_face(faces[0],settings)
    except ValueError as error:
        raise ValueError('Select one rectangular planar plate face. '+str(error)) from error
    chart=a.SurfaceMap(faces[0]);lo,hi,bottom,top=chart.bounds
    origin=chart.sample((lo+hi)/2,(bottom+top)/2)
    frame=a.hinge.HingeFrame(origin.point_mm,origin.tangent_u,origin.normal,a.hinge._cross(origin.tangent_u,origin.normal))
    plate=Plate(faces[0],body,chart,frame,(),0,context.across)
    outer=tuple(plate.local(chart.sample(u,v).point_mm) for u,v in ((lo,bottom),(hi,bottom),(hi,top),(lo,top)))
    if sum(p[0]*q[1]-q[0]*p[1] for p,q in zip(outer,outer[1:]+outer[:1]))<0:outer=tuple(reversed(outer))
    thickness=a._wall(design,body,origin.point_mm,origin.normal)[0]
    _,native=a._api();manager=native.TemporaryBRepManager.get()
    mask=prism(frame,outer,-thickness,0);material=a._copy(manager,mask)
    a._boolean(manager,material,body,native.BooleanTypes.IntersectionBooleanType,'Select a solid flat-backed rectangular plate.')
    expected=float(mask.volume)
    if (abs(float(material.volume)-expected)>max(1e-8,expected*1e-7)
            or abs(float(body.volume)-expected)>max(1e-8,expected*1e-7)):
        raise ValueError('This grille option requires a rectangular plate of uniform thickness with a flat back.')
    return Plate(faces[0],body,chart,frame,outer,thickness,context.across)

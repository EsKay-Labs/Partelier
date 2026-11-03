"""Explicit sampled motion paths; no continuous sweep or physical-fit claim."""
from dataclasses import dataclass


@dataclass(frozen=True)
class Pose:
    stage: str
    body_index: int
    angle_deg: float = 0.
    dy_mm: float = 0.
    dz_mm: float = 0.
    axis: str = 'z'
    center_y_mm: float = 0.
    center_z_mm: float = 0.


def path(settings):
    settings.validate();s=settings
    if s.family in ('slider','dovetail'):
        travel=s.length_mm*.45-(s.wall_mm+s.clearance_mm if s.end_stop else 0)
        return tuple(Pose('slide',1,dy_mm=travel*i/8) for i in range(9))
    if s.family=='bayonet':
        turn=tuple(Pose('unlock',0,angle_deg=-s.angle_deg*i/8) for i in range(9))
        extract=tuple(Pose('withdraw',0,angle_deg=-s.angle_deg,dz_mm=(s.height_mm+s.clearance_mm)*i/8) for i in range(1,9))
        return turn+extract
    if s.family=='clevis':
        return tuple(Pose('pivot',1,angle_deg=-60+10*i) for i in range(13))
    if s.family=='pip_louver':
        pitch=(s.width_mm-2*s.wall_mm)/s.count
        return tuple(Pose(f'vane {i+1}',i+1,angle_deg=angle,axis='x',
                          center_y_mm=-s.width_mm/2+s.wall_mm+(i+.5)*pitch,center_z_mm=s.pin_diameter_mm/2)
                     for i in range(s.count) for angle in range(-90,91,15))
    return tuple(Pose('hinge',1,angle_deg=12.5*i) for i in range(13))


def validate(prepared):
    """Transform detached copies only; require unchanged subtraction volumes.

    This is an opt-in native validation step, not an orbit/preview computation.
    Discrete poses cannot prove absence of interference between sample points.
    """
    import math, time
    import adsk.core as core
    import adsk.fusion as native
    from ..patterns import fusion as a
    if prepared.settings.output_mode=='attached':raise ValueError('Attached movement depends on both source shapes; this fixture only certifies sampled separate-part motion.')
    if prepared.settings.family=='linked_louver':
        from .linked_louver import motion
        return motion(prepared.settings,core,native,native.TemporaryBRepManager.get())
    if prepared.settings.family=='swing_hinge':
        from .swing_hinge import motion
        return motion(prepared.settings,core,native,native.TemporaryBRepManager.get())
    if prepared.settings.family=='parallel_lift':
        from .parallel_lift import motion
        return motion(prepared.settings,core,native,native.TemporaryBRepManager.get())
    start=time.perf_counter();s=prepared.settings;poses=path(s)
    manager=native.TemporaryBRepManager.get()
    for pose in poses:
        moving=a._copy(manager,prepared.bodies[pose.body_index])
        transform=core.Matrix3D.create()
        pivot=core.Point3D.create(s.x_mm/10,(s.y_mm+pose.center_y_mm)/10,(s.z_mm+pose.center_z_mm)/10)
        axis=core.Vector3D.create(1,0,0) if pose.axis=='x' else core.Vector3D.create(0,0,1)
        transform.setToRotation(math.radians(pose.angle_deg),axis,pivot)
        offset=transform.translation
        offset.y+=pose.dy_mm/10;offset.z+=pose.dz_mm/10
        transform.translation=offset
        if not manager.transform(moving,transform):raise ValueError('Could not apply the sampled motion pose.')
        for i,fixed in enumerate(prepared.bodies):
            if i==pose.body_index:continue
            witness=a._copy(manager,moving);before=float(witness.volume)
            if not manager.booleanOperation(witness,a._copy(manager,fixed),native.BooleanTypes.DifferenceBooleanType):
                raise ValueError(f'Cannot verify {s.family} {pose.stage} at {pose.angle_deg:g} degrees.')
            a._solid(witness,'Motion sample removed the complete moving part.')
            if abs(float(witness.volume)-before)>max(1e-9,before*1e-8):
                raise ValueError(f'{s.family} collision during {pose.stage}: angle {pose.angle_deg:g}°, Y {pose.dy_mm:g} mm, Z {pose.dz_mm:g} mm.')
    underside=None
    if s.family=='pip_louver':
        # Every underside above the print bed is bounded by the existing
        # coupon's 45-degree proof; planar socket facets have constant normals.
        for body in prepared.bodies:
            if abs(body.boundingBox.minPoint.z*10-s.z_mm)>1e-6:raise ValueError('A louver part floats above the print bed.')
            for face in body.faces:
                if face.boundingBox.maxPoint.z*10<=s.z_mm+1e-6:continue
                ok,normal=face.evaluator.getNormalAtPoint(face.pointOnFace)
                if not ok or normal.z < -math.sqrt(.5)-1e-6:raise ValueError('Louver underside exceeds the 45-degree bound.')
        underside=45
    return {'poses':len(poses),'stages':sorted({pose.stage for pose in poses}),
            'angle_min_deg':min(pose.angle_deg for pose in poses),'angle_max_deg':max(pose.angle_deg for pose in poses),
            'travel_y_mm':max(pose.dy_mm for pose in poses),'travel_z_mm':max(pose.dz_mm for pose in poses),
            'seconds':time.perf_counter()-start,'continuous_sweep':False,'underside_limit_deg':underside}

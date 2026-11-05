"""Analytic end treatments and optional supported border transitions."""
import math
from ..hinge import fusion as h
from ..patterns import fusion as a
from ..fans import fusion as f


def finish_drop(kind, size, bottom=False):
    if kind == 'none':
        return 0.
    return size * (1.-1./math.sqrt(2.)) if bottom and kind == 'fillet' else size


def _cone(manager, core, r0, r1, low, high):
    return a._solid(manager.createCylinderOrCone(core.Point3D.create(0, 0, low/10), r0/10,
                    core.Point3D.create(0, 0, high/10), r1/10), 'Could not create the grip end transition.')


def _end_mask(manager, core, native, radius, height, kind, size, bottom):
    cut = native.BooleanTypes.IntersectionBooleanType
    union = native.BooleanTypes.UnionBooleanType
    if kind == 'chamfer':
        if bottom:
            mask = _cone(manager, core, radius-size, radius, 0, size)
            rest = f._cylinder(manager, core, radius, size, height)
        else:
            mask = _cone(manager, core, radius, radius-size, height-size, height)
            rest = f._cylinder(manager, core, radius, 0, height-size)
        a._boolean(manager, mask, rest, union, 'Could not join the chamfer mask.')
        return mask
    if size >= radius/2:
        raise ValueError('Use a fillet radius smaller than half the knob outer radius.')
    # The lower circular arc starts at 45 degrees, rather than the unsupported
    # horizontal tangent of a full lower quarter round. The upper arc is full.
    centre = size/math.sqrt(2.) if bottom else height-size
    mask = f._cylinder(manager, core, radius-size, 0, height)
    rest = f._cylinder(manager, core, radius, centre, height) if bottom else f._cylinder(manager, core, radius, 0, centre)
    a._boolean(manager, mask, rest, union, 'Could not join the fillet core.')
    torus = a._solid(manager.createTorus(core.Point3D.create(0, 0, 0),
                     core.Vector3D.create(0, 0, 1), (radius-size)/10, size/10),
                     'Could not construct the circular grip fillet.')
    position = core.Matrix3D.create()
    # Move the periodic surface seam away from the zero-phase groove crossings.
    # This changes only the CAD parameterization, never the round profile.
    position.setToRotation(math.radians(17.), core.Vector3D.create(0, 0, 1), core.Point3D.create())
    position.translation = core.Vector3D.create(0, 0, centre/10)
    if not manager.transform(torus, position):
        raise ValueError('Could not position the circular grip fillet.')
    a._boolean(manager, mask, torus, union, 'Could not join the circular grip fillet.')
    a._boolean(manager, mask, f._cylinder(manager, core, radius+.01, 0, height), cut,
               'Could not trim the grip fillet.')
    return mask


def apply(body, settings, radius, height):
    core, native = h._api()
    manager = native.TemporaryBRepManager.get()
    union, intersect = native.BooleanTypes.UnionBooleanType, native.BooleanTypes.IntersectionBooleanType
    s = settings
    outer = radius + (s.depth_mm if s.mode == 'emboss' else 0.)
    if s.top_size_mm*(s.top_finish != 'none') + s.bottom_size_mm*(s.bottom_finish != 'none') >= height:
        raise ValueError('Top and bottom finishes must fit within the cylinder height.')
    if s.border_mm:
        border, depth = s.border_mm, s.depth_mm
        if 2*(border+depth) >= height:
            raise ValueError('Reduce End borders or Depth to leave space for the grip and its 45° transitions.')
        if s.mode == 'emboss':
            mask = f._cylinder(manager, core, radius, 0, height)
            pieces = (_cone(manager, core, radius, outer, border, border+depth),
                      f._cylinder(manager, core, outer, border+depth, height-border-depth),
                      _cone(manager, core, outer, radius, height-border-depth, height-border))
            for piece in pieces:
                a._boolean(manager, mask, piece, union, 'Could not create the supported raised border.')
            a._boolean(manager, body, mask, intersect, 'Could not limit the raised grip at its borders.')
        else:
            pieces = (f._cylinder(manager, core, radius, 0, border),
                      _cone(manager, core, radius, radius-depth, border, border+depth),
                      _cone(manager, core, radius-depth, radius, height-border-depth, height-border),
                      f._cylinder(manager, core, radius, height-border, height))
            for piece in pieces:
                a._boolean(manager, body, piece, union, 'Could not preserve the smooth grip borders.')
    for bottom, kind, size in ((True, s.bottom_finish, s.bottom_size_mm), (False, s.top_finish, s.top_size_mm)):
        if kind == 'none':
            continue
        end_radius = radius if s.mode == 'emboss' and s.border_mm else outer
        if s.mode == 'emboss' and s.border_mm and size > s.border_mm:
            raise ValueError('Keep each end finish size within its smooth End border, or choose Full cylinder.')
        if end_radius-size <= .8:
            raise ValueError('Reduce the end finish size to retain the knob core.')
        mask = _end_mask(manager, core, native, end_radius, height, kind, size, bottom)
        if end_radius < outer:
            middle = f._cylinder(manager, core, outer, size, height) if bottom else f._cylinder(manager, core, outer, 0, height-size)
            a._boolean(manager, mask, middle, union, 'Could not preserve the raised grip between finished borders.')
        a._boolean(manager, body, mask, intersect, 'Could not apply the grip end finish.')
    return body

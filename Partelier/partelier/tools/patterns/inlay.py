"""Bounded exact material partition; the colour body may have disjoint lumps."""

import math


def solid(body, *, temporary=None):
    if (body is None or not body.isValid or not body.isSolid
            or not 1 <= body.lumps.count <= 1200
            or not math.isfinite(float(body.volume)) or body.volume <= 0
            or (temporary is not None and body.isTemporary != temporary)):
        raise ValueError('Flat colour requires bounded valid closed material regions.')
    return body


def agrees(actual, expected):
    return math.isfinite(actual) and abs(actual-expected) <= max(1e-8, abs(expected)*1e-7)


def partition(manager, source, pieces, boolean_types):
    """Return one connected base and one colour body, never mutating inputs.

    Pieces must already be clipped to the source and conformal inward band.
    Same-colour fragments may meet or overlap at a curved seam; their union
    counts that material once. The base/colour partition must still be exact.
    """
    pieces=tuple(pieces)
    if not 1 <= len(pieces) <= 1200:
        raise ValueError('Flat colour exceeds the clipped-region work budget.')
    for piece in pieces:solid(piece,temporary=True)
    layer=[solid(manager.copy(piece),temporary=True) for piece in pieces]
    while len(layer)>1:
        following=[]
        for index in range(0,len(layer),2):
            left=layer[index]
            if index+1 < len(layer):
                total=float(left.volume)+float(layer[index+1].volume)
                if manager.booleanOperation(left,layer[index+1],boolean_types.UnionBooleanType) is False:
                    raise ValueError('Fusion could not group the flat colour regions. Reduce the pattern density.')
                volume=float(solid(left).volume)
                if volume>total+max(1e-8,total*1e-7):
                    raise ValueError('Grouping flat colour fragments created unexpected material.')
            following.append(left)
        layer=following
    colour=layer[0]
    base=solid(manager.copy(source),temporary=True)
    if manager.booleanOperation(base,colour,boolean_types.DifferenceBooleanType) is False:
        raise ValueError('Fusion could not partition the flat colour material.')
    if solid(base).lumps.count!=1 or not agrees(float(base.volume)+float(colour.volume),float(source.volume)):
        raise ValueError('Flat colour must leave one connected base. Reduce depth or increase gap and border.')
    restored=solid(manager.copy(base),temporary=True)
    if (manager.booleanOperation(restored,colour,boolean_types.UnionBooleanType) is False
            or solid(restored).lumps.count!=1 or not agrees(float(restored.volume),float(source.volume))):
        raise ValueError('Flat colour did not restore the original closed exterior.')
    for one,two in ((restored.boundingBox.minPoint,source.boundingBox.minPoint),
                    (restored.boundingBox.maxPoint,source.boundingBox.maxPoint)):
        if any(abs(getattr(one,axis)-getattr(two,axis))>1e-6 for axis in 'xyz'):
            raise ValueError('Flat colour changed the exterior bounds.')
    return base,colour

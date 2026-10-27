"""Fixed grille families: bounded convex apertures and physical flow axes."""

import math

ANGLED = ('grille_louver', 'grille_deflection', 'grille_diffuser')
GRILLES = ('grille_parallel', 'grille_cross') + ANGLED
NEW_STYLES = ('grille_deflection', 'grille_diffuser')


def flow_uv(settings, point, bounds):
    """Direction of a fixed slat's shear, in the face's millimetre chart."""
    u = point[0] - (bounds[0] + bounds[1]) / 2
    v = point[1] - (bounds[2] + bounds[3]) / 2
    if settings.pattern == 'grille_diffuser':
        half_u, half_v = (bounds[1]-bounds[0])/2, (bounds[3]-bounds[2])/2
        return min(((half_u-u, (1., 0.)), (half_u+u, (-1., 0.)),
                    (half_v-v, (0., 1.)), (half_v+v, (0., -1.))), key=lambda item:item[0])[1]
    angle = math.radians(settings.rotation_deg)
    across = (-math.sin(angle), math.cos(angle))
    sign = -1 if settings.pattern == 'grille_deflection' and u*across[0]+v*across[1] < 0 else 1
    return tuple(sign*x for x in across)


def diffuser_layout(settings, bounds, max_cells, accept):
    """Four trapezoids per rectangular ring, separated by diagonal solid ribs."""
    from .planner import Cell, Layout, density_error
    from .clipping import area
    lo, hi, bottom, top = bounds
    center = ((lo+hi)/2, (bottom+top)/2)
    w, h = (hi-lo)/2-settings.border_mm, (top-bottom)/2-settings.border_mm
    pitch, opening = settings.pitch_mm, settings.pitch_mm-settings.web_mm
    q = settings.web_mm/math.sqrt(2)
    reserve = q+settings.web_mm/2
    rings = max(0, math.ceil((min(w,h)-reserve)/pitch))
    if 4*rings > max_cells:
        raise density_error(settings, [(hi-lo)*(top-bottom)], face_cells=4*rings)
    cells = []
    for index in range(rings):
        d = index*pitch
        width = min(opening, min(w,h)-d-reserve)
        if width <= 1e-6:
            continue
        a, b = w-d, h-d
        shapes = (
            ((-a+q,b),(-a+width+q,b-width),(a-width-q,b-width),(a-q,b)),
            ((a,b-q),(a-width,b-width-q),(a-width,-b+width+q),(a,-b+q)),
            ((a-q,-b),(a-width-q,-b+width),(-a+width+q,-b+width),(-a+q,-b)),
            ((-a,-b+q),(-a+width,-b+width+q),(-a+width,b-width-q),(-a,b-q)),
        )
        for polygon in shapes:
            signed = sum(p[0]*z[1]-z[0]*p[1] for p,z in zip(polygon,polygon[1:]+polygon[:1]))
            if signed < 0:
                polygon = tuple(reversed(polygon))
            if area(polygon) < 1e-6:
                continue
            midpoint = tuple(sum(p[i] for p in polygon)/4 for i in (0,1))
            cell = Cell(tuple(a+b for a,b in zip(center,midpoint)),
                        tuple(tuple(a-b for a,b in zip(p,midpoint)) for p in polygon))
            if accept is None or accept(cell):
                cells.append(cell)
    return Layout(tuple(cells), pitch, pitch, 'fill', opening, 1, 4*rings)

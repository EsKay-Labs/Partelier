"""One exact multi-loop solid; no feature or Boolean per truss member."""

import time
from .planner import plan


def prepare(design,faces,settings,body,signature,tokens,started,*,historical=False):
    from ..patterns import fusion as a,flat_plate,perforated_prism
    if len(faces)!=1 or settings.selection_scope!='faces':
        raise ValueError('Planar truss needs one rectangular face of a uniform solid plate.')
    try:plate=flat_plate.inspect(design,faces,settings,body)
    except ValueError as error:
        raise ValueError('Planar truss needs one straight rectangular planar face of a uniform solid plate, with a flat back.') from error
    bounds=tuple(v for axis in (0,1) for v in (min(p[axis] for p in plate.outer),max(p[axis] for p in plate.outer)))
    layout=plan(bounds,settings.pattern,settings.truss_bays,settings.web_mm,settings.border_mm,settings.truss_axis,settings.truss_fillet_mm)
    if layout.rounded_holes:
        from . import rounded_prism
        planned=time.perf_counter();result=rounded_prism.create(plate.frame,layout,-plate.thickness_mm,0)
    else:
        geometry=perforated_prism.plan(plate.frame,layout.outer,layout.holes,-plate.thickness_mm,0)
        planned=time.perf_counter();result=perforated_prism.create_plan(geometry)
    completed=time.perf_counter()
    expected=layout.material_area_mm2*plate.thickness_mm/1000
    if abs(float(result.volume)-expected)>max(1e-8,expected*1e-7):
        raise ValueError('The truss material differs from its planned connected members.')
    centers=(tuple(hole.interior_point for hole in layout.rounded_holes[:3]) if layout.rounded_holes else
        tuple(tuple(sum(p[i] for p in hole)/len(hole) for i in (0,1)) for hole in layout.holes[:3]))
    samples=tuple({'face_index':0,'point_mm':plate.world(*center),
        'normal':plate.frame.y_axis,'first_exit_mm':plate.thickness_mm,'next_entry_mm':None} for center in centers)
    prepared=a.PreparedPattern(design,faces,body,settings,result,signature,
        {'source_and_plan_ms':(planned-started)*1000,'temporary_geometry_ms':(completed-planned)*1000,
         'total_ms':(completed-started)*1000,'truss_body_creations':1,'truss_bays':settings.truss_bays,
         'truss_axis':layout.axis,'truss_bay_span_mm':layout.bay_span_mm,
         'truss_fillet_mm':settings.truss_fillet_mm,'truss_arc_faces':sum(len(hole.corners) for hole in layout.rounded_holes),
         'truss_open_area_percent':100*layout.open_area_mm2/(layout.open_area_mm2+layout.material_area_mm2)},
        len(layout.holes),tokens,accepted_samples=samples)
    a.validate_sources(prepared,_historical=historical)
    return prepared

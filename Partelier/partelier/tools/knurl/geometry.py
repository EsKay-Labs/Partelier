"""One transient bounded BRep envelope, without per-groove native features."""
from . import planner
from ..patterns import perforated_prism


def build(settings, radius_mm, height_mm):
    """Return the retained envelope in local Z=0..height, dimensions in mm.

    Subtract it from the original cylinder to obtain the cut tool. Zero-depth
    rings circumscribe the cylinder so smooth borders remain untouched. This is
    deliberately a bounded planar approximation. Circumscribing the nominal
    round collar adds <=0.04 mm radial excess at vertices; that bound does not
    describe interpolation error of the sampled groove waveform.
    """
    planned = planner.plan(settings, radius_mm, height_mm)
    geometry = perforated_prism.Plan(planned.points_mm,
        tuple((loop,) for loop in planned.face_loops), planned.volume_mm3)
    return perforated_prism.create_plan(geometry)

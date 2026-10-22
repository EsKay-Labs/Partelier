"""Circular movement relief on temporary source/leaf copies, never originals."""

from dataclasses import dataclass
import math


@dataclass(frozen=True)
class RotationRelief:
    start_mm: float
    end_mm: float
    housing_radius_mm: float
    clearance_mm: float
    cutter_radius_mm: float


def plan_rotation_relief(settings):
    settings.validate()
    gap = settings.rotation_clearance_mm
    if gap == 0:
        return None
    radius = settings.barrel_diameter_mm / 2
    return RotationRelief(-settings.length_mm / 2 - gap,
                          settings.length_mm / 2 + gap, radius, gap, radius + gap)


def cut_rotation_relief(manager, frame, bodies, settings):
    """Return removal markers after cutting only supplied temporary result copies.

    The radius covers the round housing and the rotational envelope of the
    inscribed square. Axial extension leaves room around the housing ends.
    Source connectivity and the actual gap to the nominal housing are checked.
    Unchanged separate plates already outside the envelope are accepted.
    """
    from . import fusion as adapter
    adapter._require_main_thread()
    plan = plan_rotation_relief(settings)
    if plan is None:
        return ()
    core, fusion = adapter._api()
    cutter = adapter._cylinder(manager, frame, plan.start_mm, plan.end_mm,
                               plan.cutter_radius_mm, plan.housing_radius_mm)
    nominal = adapter._cylinder(manager, frame, -settings.length_mm / 2,
                                settings.length_mm / 2,
                                plan.housing_radius_mm, plan.housing_radius_mm)
    markers = []
    for role, body in bodies.items():
        adapter._require_body(body, "Movement relief needs one connected source or leaf copy.")
        if getattr(body, "isTemporary", False) is not True:
            raise adapter.HingeGeometryError("Movement relief may cut temporary copies only.")
        before = float(body.volume)
        original = manager.copy(body)
        adapter._require_body(original, "Could not retain the temporary movement relief reference.")
        if not math.isfinite(before) or before <= 0:
            raise adapter.HingeGeometryError("Movement relief needs positive finite source volume.")
        adapter._boolean(manager, body, cutter, fusion.BooleanTypes.DifferenceBooleanType,
                         "Movement clearance would remove or split a source/leaf. Reduce it.")
        after = float(body.volume)
        if not math.isfinite(after) or not 0 < after <= before:
            raise adapter.HingeGeometryError("Movement relief returned invalid source/leaf volume.")
        try:
            measured = core.Application.get().measureManager.measureMinimumDistance(body, nominal)
            gap = float(measured.value) * 10 if measured is not None else float("nan")
        except Exception as error:
            raise adapter.HingeGeometryError("Fusion could not verify the body-to-housing movement gap.") from error
        if not math.isfinite(gap) or gap < plan.clearance_mm - adapter.POSITION_TOLERANCE_CM * 10:
            raise adapter.HingeGeometryError("Movement relief did not leave the requested body-to-housing gap.")
        if after < before:
            if not manager.booleanOperation(original, body, fusion.BooleanTypes.DifferenceBooleanType):
                raise adapter.HingeGeometryError("Could not display the movement relief removal.")
            if (not original.isValid or not original.isSolid
                    or not math.isfinite(original.volume) or not original.volume > 0):
                raise adapter.HingeGeometryError("The movement relief removal is invalid.")
            markers.append(("clearance", original))
    return tuple(markers)

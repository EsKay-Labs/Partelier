"""Temporary cylinder grip cuts, preserving the selected source body."""
from dataclasses import dataclass, replace
import time
from . import geometry, planner
from ..threads.fusion import cylinder, _transform
from ..hinge import fusion as h
from ..patterns import fusion as a, display_export
from ..fans import fusion as f, display
from ...diagnostics import emit


@dataclass(frozen=True)
class Prepared:
    design: object
    settings: object
    faces: tuple
    targets: tuple
    tools: tuple
    results: tuple
    source_signature: tuple
    tokens: dict
    timings: dict
    record: object = None
    meshes: tuple = ()


def fit(settings, face):
    frame = cylinder(face)
    if frame[-1]:
        raise ValueError('Select the outside cylindrical face of the knob.')
    # Keep a valid reference even when current dimensions are too dense. The
    # preview owns dimensional refusals, allowing corrections without repicking.
    return settings


def selection(design, faces, settings):
    _, native = h._api()
    h._require_main_thread()
    if design.activeComponent != design.rootComponent or design.designType != native.DesignTypes.ParametricDesignType:
        raise ValueError('Use the root component with history enabled.')
    if len(faces) != 1:
        raise ValueError('Select one complete outside cylindrical face of the knob.')
    face = faces[0]
    frame = cylinder(face)
    if frame[-1] or face.body.parentComponent != design.rootComponent:
        raise ValueError('Select an outside cylindrical face on a native root body.')
    a._solid(face.body, 'Choose a solid knob body.')
    return (face.body,)


def prepare(design, faces, settings):
    settings.validate()
    started = time.perf_counter()
    targets = selection(design, faces, settings)
    frame = cylinder(faces[0])
    radius, height = frame[-3:-1]
    plan = planner.plan(settings, radius, height)
    core, native = h._api()
    manager = native.TemporaryBRepManager.get()
    cut = native.BooleanTypes.DifferenceBooleanType
    target = targets[0]
    # Full annular witness catches thin walls and intersecting holes between
    # samples. The cut must leave at least 0.8 mm of continuous source material.
    inner = radius - settings.depth_mm - .8
    if inner <= 0:
        raise ValueError('Reduce texture depth; retain at least 0.8 mm of solid core.')
    shell = f._cylinder(manager, core, radius, .001, height-.001)
    a._boolean(manager, shell, f._cylinder(manager, core, inner, -.1, height+.1), cut,
               'Could not check the knob wall thickness.')
    _transform(manager, shell, frame)
    expected = shell.volume
    witness = manager.copy(shell)
    if (not manager.booleanOperation(witness, manager.copy(target), native.BooleanTypes.IntersectionBooleanType)
            or not witness.isValid or not witness.isSolid
            or abs(witness.volume-expected) > max(1e-8, expected*1e-6)):
        raise ValueError('This texture needs its depth plus 0.8 mm of continuous wall. Reduce Depth or thicken the knob.')
    retained = geometry.build(settings, radius, height)
    # The narrow outer carrier connects all grooves into one cutting solid.
    # It must not touch any OTHER source material beyond the selected cylinder.
    carrier = f._cylinder(manager, core, radius+.1, 0, height)
    a._boolean(manager, carrier, f._cylinder(manager, core, radius, -.01, height+.01), cut,
               'Could not check the grip carrier clearance.')
    _transform(manager, carrier, frame)
    untouched = manager.copy(target)
    if (not manager.booleanOperation(untouched, carrier, cut)
            or not untouched.isValid or not untouched.isSolid
            or abs(untouched.volume-target.volume) > max(1e-9, target.volume*1e-10)):
        raise ValueError('Other knob geometry lies immediately outside this cylinder. Choose an isolated cylindrical grip face.')
    tool = f._cylinder(manager, core, radius+.1, 0, height)
    a._boolean(manager, tool, retained, cut, 'Could not form the grip cutting shell.')
    _transform(manager, tool, frame)
    result = manager.copy(target)
    a._boolean(manager, result, manager.copy(tool), cut,
               'The grip would disconnect the knob. Reduce texture depth.')
    if abs(result.volume-target.volume) < 1e-9:
        raise ValueError('The texture does not intersect the knob.')
    timings = {'prepare_ms': (time.perf_counter()-started)*1000,
               'repeats': plan.repeats, 'effective_pitch_mm': plan.effective_pitch_mm,
               'max_overhang_deg': plan.max_overhang_deg,
               'planned_faces': len(plan.face_loops)}
    emit('knurling.prepare', style=settings.style, **timings)
    return Prepared(design, settings, tuple(faces), targets, (tool,), (result,),
                    (h._body_signature(target),),
                    {'faces': [faces[0].entityToken], 'bodies': [target.entityToken]},
                    timings)


def validate(prepared):
    if prepared.design != h._api()[0].Application.get().activeProduct:
        raise ValueError('Return to the knob design.')
    targets = selection(prepared.design, prepared.faces, prepared.settings)
    if targets != prepared.targets or tuple(h._body_signature(b) for b in targets) != prepared.source_signature:
        raise ValueError('The knob changed. Refresh the preview.')


def cache(prepared):
    return replace(prepared, meshes=tuple(display_export.capture(prepared.design, b, coarse=True) for b in prepared.results))


def draw(prepared):
    core, native = h._api()
    group = None
    try:
        if len(prepared.meshes) != len(prepared.results):
            raise ValueError('The grip preview mesh is missing.')
        for body, target, mesh in zip(prepared.results, prepared.targets, prepared.meshes):
            appearance = target.appearance
            group = display_export.draw(prepared.design, body, appearance, mesh,
                                        group=group, effect=display.material(appearance, core, native))
        return group
    except Exception:
        if group is not None and group.isValid:
            group.deleteMe()
        raise

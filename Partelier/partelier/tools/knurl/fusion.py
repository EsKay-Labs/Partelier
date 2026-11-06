"""Temporary cylinder grip cuts, preserving the selected source body."""
from dataclasses import dataclass, replace
import time
from . import geometry, planner, finishes, grip_finish
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
    operations: tuple
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
    outer = radius + (settings.depth_mm if settings.mode == 'emboss' else 0.)
    drop = max(finishes.finish_drop(settings.top_finish, settings.top_size_mm),
               finishes.finish_drop(settings.bottom_finish, settings.bottom_size_mm, True))
    end_radius = radius if settings.mode == 'emboss' and settings.border_mm else outer
    removal = max(settings.depth_mm if settings.mode == 'engrave' else 0., radius-end_radius+drop)
    inner = radius - removal - .8
    if inner <= 0:
        raise ValueError('Reduce texture depth or end finish size; retain at least 0.8 mm of solid core.')
    shell = f._cylinder(manager, core, radius, .001, height-.001)
    a._boolean(manager, shell, f._cylinder(manager, core, inner, -.1, height+.1), cut,
               'Could not check the knob wall thickness.')
    _transform(manager, shell, frame)
    expected = shell.volume
    witness = manager.copy(shell)
    if (not manager.booleanOperation(witness, manager.copy(target), native.BooleanTypes.IntersectionBooleanType)
            or not witness.isValid or not witness.isSolid
            or abs(witness.volume-expected) > max(1e-8, expected*1e-6)):
        raise ValueError('The grip and end finishes need 0.8 mm of continuous wall beneath their deepest cut. Reduce Depth/finish size or thicken the knob.')
    origin, axis = frame[0], frame[3]
    box = core.Application.get().measureManager.getOrientedBoundingBox(
        target, core.Vector3D.create(*axis), core.Vector3D.create(*frame[1]))
    center = (box.centerPoint.x, box.centerPoint.y, box.centerPoint.z)
    axial_center = sum((center[i]*10-origin[i])*axis[i] for i in range(3))
    axial = (axial_center-box.length*5, axial_center+box.length*5)
    cuts_upper_end = (settings.mode=='engrave' and not settings.border_mm or
                      settings.top_finish!='none' and (settings.mode=='engrave' or settings.border_mm or settings.top_size_mm>settings.depth_mm))
    if cuts_upper_end and max(axial) > height+.01:
        raise ValueError('The body continues above this cylindrical face. Use End borders without a top finish, or select the complete knob side before adding its end details.')
    if settings.mode == 'emboss' and not settings.border_mm:
        foot_radius = outer-finishes.finish_drop(settings.bottom_finish, settings.bottom_size_mm, True)
        if foot_radius > radius+.001:
            low = min(axial)
            if low < -.01:
                raise ValueError('Full-height raised grip must start at the knob base for upright printing. Use End borders or a bottom chamfer at least as large as the outward depth.')
    prefinished = settings.mode=='emboss' and not settings.border_mm and (settings.top_finish=='fillet' or settings.bottom_finish=='fillet')
    seed = finishes.apply(f._cylinder(manager,core,outer,0,height),settings,radius,height) if prefinished else None
    if settings.grip_fillet_mm and settings.style=='diamond':
        # Round beyond the final end planes, then crop. Crossed helix edges
        # meeting an end cap create unstable zero-length fillet corners in ASM.
        margin=outer
        retained=geometry.build(settings,radius,height+2*margin)
        retained=grip_finish.apply(design,retained,settings.grip_fillet_mm,height+2*margin,outer)
        translation=core.Matrix3D.create();translation.translation=core.Vector3D.create(0,0,-margin/10)
        if not manager.transform(retained,translation):raise ValueError('Could not position the rounded grip.')
        a._boolean(manager,retained,f._cylinder(manager,core,outer+.01,0,height),native.BooleanTypes.IntersectionBooleanType,'Could not trim the rounded grip.')
        if seed is not None:a._boolean(manager,retained,seed,native.BooleanTypes.IntersectionBooleanType,'Could not finish the rounded grip ends.')
    else:
        retained = geometry.build(settings, radius, height, seed=seed)
        retained = grip_finish.apply(design, retained, settings.grip_fillet_mm, height, outer)
    if not prefinished:
        retained = finishes.apply(retained, replace(settings,top_finish='none',bottom_finish='none') if settings.mode=='emboss' else settings, radius, height)
    # A connected carrier lies outside the selected cylinder. Refuse any nearby
    # source material there, both to prevent accidental cuts and unintended joins.
    carrier = f._cylinder(manager, core, outer+.1, 0, height)
    a._boolean(manager, carrier, f._cylinder(manager, core, radius, -.01, height+.01), cut,
               'Could not check the grip carrier clearance.')
    _transform(manager, carrier, frame)
    untouched = manager.copy(target)
    if (not manager.booleanOperation(untouched, carrier, cut)
            or not untouched.isValid or not untouched.isSolid
            or abs(untouched.volume-target.volume) > max(1e-9, target.volume*1e-10)):
        raise ValueError('Other knob geometry lies immediately outside this cylinder. Choose an isolated cylindrical grip face.')
    result = manager.copy(target)
    tools, operations = [], []
    def trim_result():
        nonlocal result
        tool = f._cylinder(manager, core, outer+.1, 0, height)
        cutting_envelope = finishes.apply(f._cylinder(manager, core, outer, 0, height), settings, radius, height) if settings.mode == 'emboss' else manager.copy(retained)
        a._boolean(manager, tool, cutting_envelope, cut, 'Could not form the grip cutting shell.')
        _transform(manager, tool, frame)
        before_cut = result.volume
        a._boolean(manager, result, manager.copy(tool), cut,
                   'The grip would disconnect the knob. Reduce texture depth or end finish size.')
        if abs(result.volume-before_cut) > max(1e-9, target.volume*1e-10):
            tools.append(tool); operations.append('cut')
    if prefinished:trim_result()
    if settings.mode == 'emboss':
        # Filleted full-height relief is cut from a finished simple seed. Other
        # relief joins before its end cuts, avoiding coincident toroidal joins.
        additive = manager.copy(retained)
        a._boolean(manager, additive, f._cylinder(manager, core, radius-.05, -.01, height+.01), cut,
                   'Could not connect the raised grip ridges.')
        _transform(manager, additive, frame)
        a._boolean(manager, result, manager.copy(additive), native.BooleanTypes.UnionBooleanType,
                   'Could not join the raised grip to the original knob.')
        tools.append(additive); operations.append('join')
    if not prefinished and (settings.mode == 'engrave' or settings.top_finish!='none' or settings.bottom_finish!='none'):trim_result()
    if not tools:
        raise ValueError('These settings do not change the selected knob.')
    timings = {'prepare_ms': (time.perf_counter()-started)*1000,
               'repeats': plan.repeats, 'effective_pitch_mm': plan.effective_pitch_mm,
               'max_overhang_deg': max(plan.max_overhang_deg, 45. if settings.border_mm or settings.bottom_finish!='none' else 0.),
               'motif_overhang_bound_deg': plan.max_overhang_deg,
               'planned_cutters': plan.cutter_count}
    emit('knurling.prepare', style=settings.style, mode=settings.mode, **timings)
    return Prepared(design, settings, tuple(faces), targets, tuple(tools), (result,),
                    (h._body_signature(target),),
                    {'faces': [faces[0].entityToken], 'bodies': [target.entityToken]},
                    timings, tuple(operations))



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

"""Cache display triangles through Fusion's standard STL exporter."""

from dataclasses import replace
from pathlib import Path
import tempfile
import time
import traceback

from ..hinge import fusion as hinge
from ...diagnostics import emit
from .display_mesh import MAX_TRIANGLES, read_binary_stl


def prepare(prepared):
    started=time.perf_counter()
    mesh=capture(prepared.design,prepared.result_body)
    colour=getattr(prepared,"colour_body",None)
    colour_mesh=capture(prepared.design,colour) if colour is not None else None
    return replace(prepared,display_mesh=mesh,colour_mesh=colour_mesh,
        timings={**prepared.timings,'display_capture_ms':(time.perf_counter()-started)*1000})


def capture(design,body,checkpoint=None,*,coarse=False):
    """Caller owns rollback. Export exactly one owned copy, then remove it."""
    hinge._require_main_thread()
    _,native=hinge._api()
    root=design.rootComponent
    before=(root.bRepBodies.count,design.timeline.count,design.timeline.markerPosition)
    def stage(name):
        emit('pattern.display_export.'+name)
        if checkpoint is not None:checkpoint(name)
    stage('feature.add')
    feature=root.features.baseFeatures.add()
    if feature is None:raise ValueError('Fusion could not allocate display scratch geometry.')
    editing=False;options=None;managed=None;exporter=None
    try:
        stage('feature.start_edit')
        if feature.startEdit() is False:raise ValueError('Fusion could not open display scratch geometry.')
        editing=True
        stage('body.add')
        if root.bRepBodies.add(body,feature) is None:raise ValueError('Fusion could not copy the preview solid.')
        stage('feature.finish_edit')
        if feature.finishEdit() is False:raise ValueError('Fusion could not finish display scratch geometry.')
        editing=False
        if feature.bodies.count!=1:raise ValueError('Display scratch geometry must contain exactly one solid.')
        managed=feature.bodies.item(0)
        if managed.isTemporary:raise ValueError('Display export requires a document-owned solid.')
        managed.isLightBulbOn=True
        with tempfile.TemporaryDirectory(prefix='partelier-display-') as folder:
            path=Path(folder)/'preview.stl'
            stage('options.create')
            exporter=design.exportManager
            options=exporter.createSTLExportOptions(managed,str(path))
            if options is None:raise ValueError('Fusion could not prepare the preview export.')
            stage('options.binary');options.isBinaryFormat=True
            stage('options.units');options.unitType=native.DistanceUnits.CentimeterDistanceUnits
            stage('options.utility');options.sendToPrintUtility=False
            stage('options.quality');options.meshRefinement=(native.MeshRefinementSettings.MeshRefinementLow if coarse else native.MeshRefinementSettings.MeshRefinementMedium)
            stage('export.execute')
            if exporter.execute(options) is False:raise ValueError('Fusion could not export preview triangles.')
            stage('export.finished')
            # Release export/body wrappers while their native owner still exists.
            options=None;managed=None;exporter=None
            if not path.is_file():raise ValueError('Fusion did not write the preview export.')
            if path.stat().st_size>84+50*MAX_TRIANGLES:
                raise ValueError('The preview export exceeds its display budget.')
            data=read_binary_stl(path.read_bytes())
            stage('arrays.ready')
            return data
    except Exception as error:
        message=str(error)
        emit('pattern.display_export.error',error=message,traceback=traceback.format_exc())
        # Native wrapper traceback frames may retain export options/body handles.
        # Keep diagnostic text, then release those frames before deleting owner.
        seen=set();current=error
        while current is not None and id(current) not in seen:
            seen.add(id(current));following=current.__context__ or current.__cause__
            current.__traceback__=None;current.__context__=None;current.__cause__=None
            current=following
        raise ValueError(message) from None
    finally:
        options=None;managed=None;exporter=None
        errors=[]
        if editing:
            try:
                if feature.finishEdit() is False:errors.append('finish scratch edit')
            except Exception as error:errors.append(str(error))
        stage('feature.delete')
        try:
            if feature.isValid and feature.deleteMe() is False:errors.append('remove scratch feature')
        except Exception as error:errors.append(str(error))
        if errors or (root.bRepBodies.count,design.timeline.count,design.timeline.markerPosition)!=before:
            raise RuntimeError('Display export needs rollback cleanup. '+', '.join(errors))


def draw(design,body,appearance,mesh,*,colour=None,group=None,effect=None):
    """Upload a cached opaque mesh and the existing bounded outline batch."""
    hinge._require_main_thread()
    core,native=hinge._api()
    if group is None:group=design.rootComponent.customGraphicsGroups.add()
    if group is None:raise ValueError('Fusion could not allocate preview graphics.')
    try:
        group.isChildrenSelectable=False;group.isSelectable=False
        graphic=group.addMesh(native.CustomGraphicsCoordinates.create(list(mesh.coordinates)),[],list(mesh.normals),[])
        if graphic is None:raise ValueError('Fusion could not upload the preview triangles.')
        material=effect if effect is not None else (native.CustomGraphicsAppearanceColorEffect.create(appearance) if colour is None
                  else native.CustomGraphicsSolidColorEffect.create(core.Color.create(*colour,255)))
        if material is None:raise ValueError('Fusion could not read the preview appearance.')
        graphic.color=material;graphic.isSelectable=False
        if graphic.setOpacity(1.,True) is False:raise ValueError('Fusion could not make the preview opaque.')
        hinge._preview_outlines(group,body,core,native)
        emit('pattern.display_export.draw',triangles=mesh.triangle_count)
        return group
    except Exception:
        if group.isValid:group.deleteMe()
        raise

"""Aligned two-part standard 3MF; no filament/profile or machine settings."""

import os
import math
from pathlib import Path
import tempfile
import xml.etree.ElementTree as ET
import zipfile

from .display_mesh import MAX_TRIANGLES,read_binary_stl


NS='http://schemas.microsoft.com/3dmanufacturing/core/2015/02'


def package(meshes):
    """Create a standard assembly with two named meshes, in millimetres.

    STL export buffers are centimetres. Shared coordinates are indexed without
    rounding, resampling or independently recentering the two material parts.
    """
    meshes=tuple(meshes)
    if len(meshes)!=2 or sum(mesh.triangle_count for mesh in meshes)>MAX_TRIANGLES:
        raise ValueError('Flat colour export requires two parts within the triangle budget.')
    ET.register_namespace('',NS)
    def element(parent,tag,**attributes):return ET.SubElement(parent,'{'+NS+'}'+tag,attributes)
    root=ET.Element('{'+NS+'}model',{'unit':'millimeter','{http://www.w3.org/XML/1998/namespace}lang':'en-US'})
    resources=element(root,'resources')
    for identity,name,mesh in zip((1,2),('Base','Pattern colour'),meshes):
        if (not mesh.triangle_count or len(mesh.coordinates)%9
                or not all(math.isfinite(value) for value in mesh.coordinates)):
            raise ValueError('Cannot export empty or invalid material triangles.')
        obj=element(resources,'object',id=str(identity),type='model',name=name)
        shape=element(obj,'mesh');vertices=element(shape,'vertices');triangles=element(shape,'triangles')
        indices={}
        for offset in range(0,len(mesh.coordinates),9):
            corners=[]
            for index in range(offset,offset+9,3):
                point=tuple(mesh.coordinates[index:index+3])
                if point not in indices:
                    indices[point]=len(indices)
                    element(vertices,'vertex',**dict(zip('xyz',(format(value*10,'.12g') for value in point))))
                corners.append(str(indices[point]))
            element(triangles,'triangle',v1=corners[0],v2=corners[1],v3=corners[2])
    obj=element(resources,'object',id='3',type='model',name='Partelier flat colour')
    components=element(obj,'components')
    for identity in (1,2):element(components,'component',objectid=str(identity))
    element(element(root,'build'),'item',objectid='3')
    return ET.tostring(root,encoding='utf-8',xml_declaration=True)


def write(path,meshes):
    """Atomic replacement only after a complete bounded package was produced."""
    model=package(meshes)
    path=Path(path)
    if path.suffix.lower()!='.3mf':raise ValueError('Choose a .3mf filename for flat colour export.')
    temporary=None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent,suffix='.3mf.tmp',delete=False) as file:
            temporary=Path(file.name)
        with zipfile.ZipFile(temporary,'w',compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr('[Content_Types].xml','<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="config" ContentType="application/xml"/><Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/></Types>')
            archive.writestr('_rels/.rels','<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Target="/3D/3dmodel.model" Id="rel0" Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/></Relationships>')
            archive.writestr('3D/3dmodel.model',model)
            # Optional slicer naming metadata; core geometry remains standard 3MF.
            archive.writestr('Metadata/model_settings.config','<?xml version="1.0" encoding="utf-8"?><config><object id="3"><metadata key="name" value="Partelier flat colour"/><part id="1" subtype="normal_part"><metadata key="name" value="Base"/></part><part id="2" subtype="normal_part"><metadata key="name" value="Pattern colour"/></part></object></config>')
        os.replace(temporary,path)
        temporary=None
    finally:
        if temporary is not None:temporary.unlink(missing_ok=True)


def export(design,target,path):
    """Read only recorded final bodies, using the stable official STL exporter."""
    from .recipe import STORE,read_edit_target
    from . import colour_store
    from .store import _api
    _,native=_api()
    target=read_edit_target(design,target.anchor)
    colour=colour_store.read(design,STORE,target.record)
    if colour is None or target.settings.mode!='inlay':
        raise ValueError('Select a created Flat colour pattern to export.')
    meshes=[]
    with tempfile.TemporaryDirectory(prefix='partelier-colour-') as folder:
        for index,body in enumerate((target.record.target,colour[1])):
            stl=Path(folder)/(str(index)+'.stl')
            options=design.exportManager.createSTLExportOptions(body,str(stl))
            if options is None:raise ValueError('Fusion could not prepare the material-part export.')
            visible=body.isLightBulbOn
            try:
                body.isLightBulbOn=True
                options.isOneFilePerBody=False
                options.isBinaryFormat=True
                options.unitType=native.DistanceUnits.CentimeterDistanceUnits
                options.sendToPrintUtility=False
                options.meshRefinement=native.MeshRefinementSettings.MeshRefinementHigh
                if design.exportManager.execute(options) is False:
                    raise ValueError('Fusion could not export a material part.')
            finally:
                options=None
                body.isLightBulbOn=visible
            if not stl.is_file() or stl.stat().st_size>84+50*MAX_TRIANGLES:
                sizes={item.name:item.stat().st_size for item in Path(folder).iterdir() if item.is_file()}
                raise ValueError('The material export is missing or exceeds its triangle budget: '+str(sizes))
            meshes.append(read_binary_stl(stl.read_bytes()))
    # Revalidate ownership after export before touching the requested destination.
    read_edit_target(design,target.anchor)
    write(path,meshes)
    return {'parts':2,'triangles':sum(mesh.triangle_count for mesh in meshes)}

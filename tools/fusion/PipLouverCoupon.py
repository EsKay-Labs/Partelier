"""Experimental bed-flat captive louver coupons; run only in a disposable design.

Not an app feature or a proven printing preset. All API work is on Fusion's main
thread. The script exports a clearance ladder and closes its owned document.
"""

import importlib
import json
import math
from pathlib import Path
import struct
import sys
import tempfile
import uuid
import xml.etree.ElementTree as ET
import zipfile

import adsk.core as core
import adsk.fusion as native


def _snapshot(design):
    if design is None:return None
    history=(design.timeline.count,design.timeline.markerPosition) if design.designType==native.DesignTypes.ParametricDesignType else None
    return history,[(b.entityToken,b.name,b.isLightBulbOn,round(b.volume,9)) for b in design.rootComponent.bRepBodies]


def _package(path,parts):
    """One millimetre assembly, with all nine parts left in printing position."""
    ns='http://schemas.microsoft.com/3dmanufacturing/core/2015/02';ET.register_namespace('',ns)
    def tag(name):return '{'+ns+'}'+name
    model=ET.Element(tag('model'),{'unit':'millimeter','{http://www.w3.org/XML/1998/namespace}lang':'en-US'})
    ET.SubElement(model,tag('metadata'),{'name':'Title'}).text='Partelier experimental PIP louver · 0.25 / 0.35 / 0.45 mm'
    resources=ET.SubElement(model,tag('resources'));merged=[]
    for index,(label,data) in enumerate(parts,1):
        obj=ET.SubElement(resources,tag('object'),{'id':str(index),'type':'model','name':label})
        mesh=ET.SubElement(obj,tag('mesh'));vertices=ET.SubElement(mesh,tag('vertices'));triangles=ET.SubElement(mesh,tag('triangles'))
        lookup={}
        for facet in struct.iter_unpack('<12fH',data[84:]):
            merged.append(struct.pack('<12fH',*facet))
            indices=[]
            for offset in (3,6,9):
                point=tuple(round(v,7) for v in facet[offset:offset+3])
                if point not in lookup:
                    lookup[point]=len(lookup);ET.SubElement(vertices,tag('vertex'),dict(zip(('x','y','z'),map(str,point))))
                indices.append(lookup[point])
            ET.SubElement(triangles,tag('triangle'),dict(zip(('v1','v2','v3'),map(str,indices))))
    assembly=ET.SubElement(resources,tag('object'),{'id':str(len(parts)+1),'type':'model','name':'PIP louver clearance ladder'})
    components=ET.SubElement(assembly,tag('components'))
    for index in range(1,len(parts)+1):ET.SubElement(components,tag('component'),{'objectid':str(index)})
    ET.SubElement(ET.SubElement(model,tag('build')),tag('item'),{'objectid':str(len(parts)+1)})
    content='<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/></Types>'
    rels='<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Target="/3D/3dmodel.model" Id="rel0" Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/></Relationships>'
    with zipfile.ZipFile(path,'w',zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('[Content_Types].xml',content);archive.writestr('_rels/.rels',rels)
        archive.writestr('3D/3dmodel.model',ET.tostring(model,encoding='utf-8',xml_declaration=True))
    path.with_suffix('.stl').write_bytes(b'Partelier experimental PIP louver'.ljust(80,b'\0')+struct.pack('<I',len(merged))+b''.join(merged))


def run(context):
    context=context or {};app=core.Application.get()
    addin=next(m for key,m in tuple(sys.modules.items()) if key.endswith('partelier.addin'))
    for name in ('_hinge_commands','_snap_commands','_pattern_commands','_detail_commands'):
        state=getattr(addin,name).palette_state()
        if state.get('sessionId') and state.get('phase') not in ('idle','created','cancelled'):
            raise ValueError('Cancel the current Partelier preview before making the separate print coupon.')
    if app.userInterface.activeCommand not in ('','SelectCommand'):raise ValueError('Finish the active Fusion command first.')
    # A fresh isolated package always uses the sources on disk.
    import importlib.util
    root=Path(__file__).resolve().parents[2];prefix='_pip_louver_trial_'+uuid.uuid4().hex
    package=root/'Partelier/partelier';spec=importlib.util.spec_from_file_location(prefix,package/'__init__.py',submodule_search_locations=[str(package)])
    module=importlib.util.module_from_spec(spec);sys.modules[prefix]=module;spec.loader.exec_module(module)
    prism=importlib.import_module(prefix+'.tools.patterns.prism').prism
    frame_type=importlib.import_module(prefix+'.tools.hinge.fusion').HingeFrame
    caller=app.activeDocument;original=native.Design.cast(app.activeProduct);before=_snapshot(original);camera=app.activeViewport.camera
    owned=None;report={'version':'0.25.0','experimental':True,'success':False,'physical_print_tested':False,'fusion_version':app.version,'coupons':[]}
    destination=Path(context.get('output_dir',str(root/'examples/print-tests/pip-louver')));destination.mkdir(parents=True,exist_ok=True)
    try:
        owned=app.documents.add(core.DocumentTypes.FusionDesignDocumentType);design=native.Design.cast(app.activeProduct)
        design.designType=native.DesignTypes.ParametricDesignType;comp=design.rootComponent;manager=native.TemporaryBRepManager.get()
        def box(x0,x1,y0,y1,z0,z1):
            return manager.createBox(core.OrientedBoundingBox3D.create(core.Point3D.create((x0+x1)/20,(y0+y1)/20,(z0+z1)/20),core.Vector3D.create(1,0,0),core.Vector3D.create(0,1,0),(x1-x0)/10,(y1-y0)/10,(z1-z0)/10))
        def boolean(body,tool,operation):
            if not manager.booleanOperation(body,tool,operation):raise ValueError('The experimental coupon Boolean failed.')
            return body
        def yz(polygon,x0,x1):
            points=tuple((y,-z) for y,z in polygon)
            if sum(a[0]*b[1]-b[0]*a[1] for a,b in zip(points,points[1:]+points[:1]))<0:points=tuple(reversed(points))
            return prism(frame_type((0,0,0),(0,1,0),(1,0,0),(0,0,-1)),points,x0,x1)
        bodies=[];r=2.5;height=r+math.sqrt(2)*(r+.45)+.8
        for index,gap in enumerate((.25,.35,.45)):
            offset=index*46.;rho=r+gap
            frame=box(offset-20,offset+20,-13,13,0,height)
            boolean(frame,box(offset-16,offset+16,-10.5,10.5,-1,height+1),native.BooleanTypes.DifferenceBooleanType)
            blades=[]
            for y in (-4.5,4.5):
                bore=[(y+rho/math.sqrt(2),r+rho/math.sqrt(2)),(y,r+rho*math.sqrt(2))]
                bore.extend((y+rho*math.cos(math.radians(a)),r+rho*math.sin(math.radians(a))) for a in range(135,405,5))
                for sign in (-1,1):
                    x0,x1=sorted((offset+sign*15.98,offset+sign*19.5))
                    boolean(frame,yz(tuple(bore),x0,x1),native.BooleanTypes.DifferenceBooleanType)
                blade=box(offset-16+gap,offset+16-gap,y-.6,y+.6,0,2*r)
                pin=((y,0),(y+r,r),(y,2*r),(y-r,r))
                for sign in (-1,1):
                    x0,x1=sorted((offset+sign*(15.5-gap),offset+sign*(19.5-gap)))
                    boolean(blade,yz(pin,x0,x1),native.BooleanTypes.UnionBooleanType)
                blades.append(blade)
            for mark in range(index+1):
                x=offset+(mark-index/2)*2
                boolean(frame,box(x-.35,x+.35,-13.1,-12.2,height-.7,height+.1),native.BooleanTypes.DifferenceBooleanType)
            # The socket opens narrowly at the bed, while the pivot's minimum
            # caliper remains larger: it is captive without a floating floor.
            slot=2*math.sqrt(rho*rho-r*r)
            assert slot<r*math.sqrt(2)
            checked=0
            for number,blade in enumerate(blades):
                for angle in range(-90,91,15):
                    rotated=manager.copy(blade);matrix=core.Matrix3D.create()
                    assert matrix.setToRotation(math.radians(angle),core.Vector3D.create(1,0,0),core.Point3D.create(offset/10,(-4.5 if number==0 else 4.5)/10,r/10))
                    assert manager.transform(rotated,matrix)
                    for other in (frame,blades[1-number]):
                        overlap=manager.copy(rotated)
                        assert manager.booleanOperation(overlap,other,native.BooleanTypes.IntersectionBooleanType)
                        assert not overlap.isSolid or overlap.volume<1e-9,(gap,angle,overlap.volume)
                        checked+=1
            for body in (frame,*blades):
                assert body.isSolid and body.lumps.count==1 and abs(body.boundingBox.minPoint.z)<1e-7
                for face in body.faces:
                    if face.boundingBox.maxPoint.z<1e-7:continue
                    ok,normal=face.evaluator.getNormalAtPoint(face.pointOnFace);assert ok
                    assert normal.z>=-math.sqrt(.5)-1e-6,('unsupported underside',normal.z)
            bodies.extend([(f'{index+1} · {gap:.2f} mm · Frame',frame)]+[(f'{index+1} · {gap:.2f} mm · Blade {i+1}',b) for i,b in enumerate(blades)])
            report['coupons'].append({'clearance_mm':gap,'bodies':3,'bed_slot_mm':slot,'minimum_pivot_caliper_mm':r*math.sqrt(2),'motion_degrees':[-90,90],'rotation_sample_step_deg':15,'sampled_intersection_checks':checked,'minimum_radial_gap_mm':gap-rho*(1-math.cos(math.radians(2.5))),'swept_blade_to_blade_gap_mm':9-2*math.hypot(r,.6),'underside_limit_deg':45})
        feature=comp.features.baseFeatures.add();assert feature.startEdit()
        for label,body in bodies:
            managed=comp.bRepBodies.add(body,feature);assert managed;managed.name=label
        assert feature.finishEdit();assert comp.bRepBodies.count==9
        parts=[]
        with tempfile.TemporaryDirectory(prefix='partelier-pip-') as folder:
            for index,body in enumerate(feature.bodies):
                path=Path(folder)/(str(index)+'.stl');options=design.exportManager.createSTLExportOptions(body,str(path))
                options.isBinaryFormat=True;options.unitType=native.DistanceUnits.MillimeterDistanceUnits;options.sendToPrintUtility=False
                options.meshRefinement=native.MeshRefinementSettings.MeshRefinementHigh
                assert design.exportManager.execute(options);options=None
                data=path.read_bytes();assert len(data)==84+50*struct.unpack_from('<I',data,80)[0]
                parts.append((body.name,data))
        _package(destination/'Partelier-PIP-louver-clearance.3mf',parts)
        view=app.activeViewport.camera;view.viewOrientation=core.ViewOrientations.IsoTopRightViewOrientation;view.isFitView=True;app.activeViewport.camera=view
        assert app.activeViewport.saveAsImageFile(str(destination/'preview.png'),1100,650)
        report.update(success=True,parts=9,print_file='Partelier-PIP-louver-clearance.3mf',stl_file='Partelier-PIP-louver-clearance.stl')
        return report
    finally:
        if owned is not None:owned.close(False)
        if caller is not None and caller.isValid:caller.activate();app.activeViewport.camera=camera
        report['caller_unchanged']=_snapshot(original)==before
        (destination/'validation.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
        for name in list(sys.modules):
            if name==prefix or name.startswith(prefix+'.'):sys.modules.pop(name,None)

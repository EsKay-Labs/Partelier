"""Isolated attachment fixtures: same source identities, no duplicated originals."""
import importlib,importlib.util,json,sys,time,traceback
from pathlib import Path


def run(context):
    import adsk.core as core
    import adsk.fusion as native
    from dataclasses import replace
    root=Path(r'C:\Users\SKTech\Desktop\Programming_Projects\Apps\Fusion360\Partelier')
    package=root/'Partelier'/'partelier';prefix='_partelier_attached_mechanism_validation'
    for key in list(sys.modules):
        if key==prefix or key.startswith(prefix+'.'):del sys.modules[key]
    spec=importlib.util.spec_from_file_location(prefix,package/'__init__.py',submodule_search_locations=[str(package)])
    module=importlib.util.module_from_spec(spec);sys.modules[prefix]=module;spec.loader.exec_module(module)
    settings_module=importlib.import_module(prefix+'.tools.mechanisms.settings')
    fusion=importlib.import_module(prefix+'.tools.mechanisms.fusion');store=importlib.import_module(prefix+'.tools.mechanisms.store')
    operations=importlib.import_module(prefix+'.operations');a=importlib.import_module(prefix+'.tools.patterns.fusion')
    boxfn=importlib.import_module(prefix+'.tools.fans.fusion')._box
    app=core.Application.get();caller=app.activeDocument;doc=None;report={'cases':[]}
    try:
        for family in ('slider','dovetail','clevis','barrel','concealed','pip_hinge','bayonet'):
            started=time.perf_counter();entry={'family':family}
            try:
                doc=app.documents.add(core.DocumentTypes.FusionDesignDocumentType);design=native.Design.cast(app.activeProduct);comp=design.rootComponent
                manager=native.TemporaryBRepManager.get();s=settings_module.MechanismSettings(family=family,output_mode='attached')
                if family=='bayonet':
                    def ring(inner,outer,z0,z1):
                        body=manager.createCylinderOrCone(core.Point3D.create(0,0,z0/10),outer/10,core.Point3D.create(0,0,z1/10),outer/10)
                        bore=manager.createCylinderOrCone(core.Point3D.create(0,0,(z0-.1)/10),inner/10,core.Point3D.create(0,0,(z1+.1)/10),inner/10)
                        a._boolean(manager,body,bore,native.BooleanTypes.DifferenceBooleanType,'Fixture ring failed.');return body
                    r=s.diameter_mm/2;gap=s.height_mm-2*s.attachment_overlap_mm
                    sources=[ring(r-s.wall_mm,r,-5,0),ring(r+s.wall_mm+s.clearance_mm+.2,r+s.clearance_mm+2*s.wall_mm,gap,gap+5)]
                    normals=((0,0,1),(0,0,-1));edge_axis=None
                elif family in ('slider','dovetail'):
                    gap=2*s.wall_mm+s.height_mm+s.clearance_mm-2*s.attachment_overlap_mm
                    # The moving support follows the carriage footprint and
                    # stays clear of the fixed rail end stop at far Y.
                    sources=[boxfn(manager,core,80,80,5,(0,0,-2.5)),boxfn(manager,core,80,20,5,(0,-9,gap+2.5))]
                    normals=((0,0,1),(0,0,-1));edge_axis=0
                else:
                    gap=(s.length_mm if family=='clevis' else 2*(s.height_mm+s.width_mm))-2*s.attachment_overlap_mm
                    sources=[boxfn(manager,core,5,80,80,(-2.5,0,0)),boxfn(manager,core,5,80,80,(gap+2.5,0,0))]
                    normals=((1,0,0),(-1,0,0));edge_axis=1
                base=comp.features.baseFeatures.add();assert base.startEdit()
                for body in sources:comp.bRepBodies.add(body,base)
                assert base.finishEdit();targets=tuple(base.bodies)
                for name,body in zip(('Original A','Original B'),targets):body.name=name
                faces=[]
                for body,direction in zip(targets,normals):
                    faces.append(next(face for face in body.faces if core.Plane.cast(face.geometry) and sum(x*y for x,y in zip(face.evaluator.getNormalAtPoint(face.pointOnFace)[1].asArray(),direction))>.999))
                refs={'face_a':faces[0].entityToken,'face_b':faces[1].entityToken}
                if edge_axis is not None:
                    edge=next(edge for edge in faces[0].edges if core.Line3D.cast(edge.geometry) and
                        edge.endVertex.geometry.asArray()[edge_axis]-edge.startVertex.geometry.asArray()[edge_axis]>.1)
                    refs['axis_edge']=edge.entityToken
                before=(design.timeline.count,comp.bRepBodies.count);tokens=[b.entityToken for b in targets];volumes=[b.volume for b in targets]
                p=fusion.prepare(design,s,references=refs)
                assert (design.timeline.count,comp.bRepBodies.count)==before
                cache=fusion.cache(p);group=fusion.draw(cache);assert group.isValid;group.deleteMe()
                start=design.timeline.count;anchor=store.apply(p);operations.capture(design,anchor,'mechanism',s.to_dict(),start)
                record=store.read(design,anchor)
                assert record.targets==targets and all(design.findEntityByToken(t)[0]==b for t,b in zip(tokens,targets))
                expected=2+len(p.tools)-2;assert comp.bRepBodies.count==expected
                assert [b.name for b in targets]==['Original A','Original B']
                edited=replace(s,clearance_mm=.4)
                prepared=store.prepare_edit(design,record,edited);start=design.timeline.count
                assert store.apply(prepared)==anchor
                operations.capture(design,anchor,'mechanism',edited.to_dict(),start,editing=True)
                assert store.read(design,anchor).settings==edited and comp.bRepBodies.count==expected
                identity=record.recipe['feature_id'];operations.delete(design,identity)
                assert comp.bRepBodies.count==2 and all(abs(b.volume-v)<1e-8 for b,v in zip(targets,volumes))
                assert all(design.findEntityByToken(t)[0]==b for t,b in zip(tokens,targets))
                entry.update(ok=True,source_identity_preserved=True,originals_restored_after_delete=True,final_bodies_before_delete=expected)
            except Exception:entry.update(ok=False,error=traceback.format_exc())
            finally:
                entry['seconds']=time.perf_counter()-started;report['cases'].append(entry)
                if doc is not None:doc.close(False);doc=None
        report['ok']=all(item['ok'] for item in report['cases'])
    finally:
        if doc is not None:doc.close(False)
        if caller is not None and caller.isValid:caller.activate()
        out=root/'output'/'overnight';out.mkdir(exist_ok=True,parents=True)
        (out/'attached-mechanisms-native.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    app.log(json.dumps(report))

"""Small cached-mesh, exact Saved Delete and additive support checks."""
def run(context):
 import adsk.core as c,adsk.fusion as n,sys,importlib,json,traceback
 from pathlib import Path
 from dataclasses import replace
 app=c.Application.get();caller=app.activeDocument
 assert app.userInterface.activeCommand in ('','SelectCommand')
 prefix=next(k.rsplit('.',1)[0] for k in sys.modules if k.endswith('partelier.addin'))
 for name in ('settings','planner','fusion','store'):
  full=prefix+'.tools.finishing.'+name
  if full in sys.modules:importlib.reload(sys.modules[full])
 settings=importlib.import_module(prefix+'.tools.finishing.settings');a=importlib.import_module(prefix+'.tools.finishing.fusion');store=importlib.import_module(prefix+'.tools.finishing.store')
 operations=importlib.import_module(prefix+'.operations')
 assert any(row[2]=='finishing' for row in operations.RECIPES), 'Load current operations before lifecycle validation.'
 report=[]
 for kind in ('text','keyhole','scale'):
  doc=None;group=None
  try:
   doc=app.documents.add(c.DocumentTypes.FusionDesignDocumentType);design=n.Design.cast(app.activeProduct);root=design.rootComponent
   sketch=root.sketches.add(root.xYConstructionPlane);sketch.sketchCurves.sketchLines.addTwoPointRectangle(c.Point3D.create(-5,-4,0),c.Point3D.create(5,4,0))
   ext=root.features.extrudeFeatures.addSimple(sketch.profiles.item(0),c.ValueInput.createByReal(.4),n.FeatureOperations.NewBodyFeatureOperation)
   body=ext.bodies.item(0);face=max(tuple(body.faces),key=lambda f:f.pointOnFace.z)
   s=settings.FinishingSettings(kind=kind,text='A1',depth_mm=1,width_mm=12,length_mm=20,mode='emboss')
   original=a.h._body_signature(body);before=(root.bRepBodies.count,design.timeline.count,body.isLightBulbOn)
   p=a.cache(a.prepare(design,(face,),s));group=a.draw(p);assert group.isValid;group.deleteMe();group=None
   assert (root.bRepBodies.count,design.timeline.count,body.isLightBulbOn)==before
   assert a.h._body_signature(body)==original
   if s.additive:
    refused=False
    try:a.prepare(design,(face,),replace(s,offset_x_mm=49))
    except ValueError:refused=True
    assert refused, 'Raised detail crossing boundary must be refused.'
   start=design.timeline.count;anchor=store.apply(p);operations.capture(design,anchor,'finishing',s.to_dict(),start)
   record=next(r for r in operations.records(design) if r['anchor']==anchor)
   assert record['meta'] and record['tool']=='finishing'
   operations.delete(design,record['id'])
   assert (root.bRepBodies.count,design.timeline.count,body.isLightBulbOn)==before
   assert a.h._body_signature(body)==original
   report.append({'kind':kind,'ok':True,'triangles':p.meshes[0].triangle_count,'delete_restored_source':True})
  except Exception:report.append({'kind':kind,'ok':False,'error':traceback.format_exc()})
  finally:
   if group and group.isValid:group.deleteMe()
   if doc:doc.close(False)
   if caller and caller.isValid:caller.activate()
 path=Path('C:/Users/SKTech/Desktop/Programming_Projects/Apps/Fusion360/Partelier/output/finishing-lifecycle.json');path.write_text(json.dumps(report,indent=2),encoding='utf-8')
 print(json.dumps(report))

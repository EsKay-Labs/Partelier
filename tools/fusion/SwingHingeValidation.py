def run(context):
 import adsk.core as c,adsk.fusion as n,sys,importlib,json,traceback
 from pathlib import Path
 app=c.Application.get();assert app.userInterface.activeCommand in ('','SelectCommand')
 prefix=next(k.rsplit('.',1)[0] for k in sys.modules if k.endswith('partelier.addin'))
 for name in ('swing_hinge','settings'):
  key=prefix+'.tools.mechanisms.'+name
  if key in sys.modules:importlib.reload(sys.modules[key])
 p=importlib.import_module(prefix+'.tools.mechanisms.swing_hinge');S=importlib.import_module(prefix+'.tools.mechanisms.settings').MechanismSettings
 report={'ok':False,'fusion_version':app.version}
 try:
  s=S(family='swing_hinge',length_mm=30,width_mm=40,height_mm=16,wall_mm=2,clearance_mm=.3,pin_diameter_mm=3,angle_deg=30,assembly_layout='assembled')
  m=n.TemporaryBRepManager.get();bodies,names=p.build(s,c,n,m)
  assert len(bodies)==8 and all(b.isTemporary and b.isSolid and b.lumps.count==1 for b in bodies)
  report['bodies']=list(names);report['motion']=p.motion(s,c,n,m);report['print_layout']=p.print_check(s,c,n,m);report['ok']=True
 except Exception:report['error']=traceback.format_exc()
 path=Path('C:/Users/SKTech/Desktop/Programming_Projects/Apps/Fusion360/Partelier/output/swing-hinge-native.json');path.write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps(report))

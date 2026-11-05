"use strict";
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const ui=path.join(__dirname,'..','Partelier','partelier','ui');
function fixture(){
 const ids=new Map(),timers=new Map(),requests=[];let timerId=0,host=null,serial=0,reset;
 class Element{
  constructor(tag='div'){this.tagName=tag;this.children=[];this.listeners={};this.dataset={};this.disabled=false;this.hidden=false;this.custom='';const classes=new Set();this.classList={add:x=>classes.add(x),toggle:(x,on)=>on?classes.add(x):classes.delete(x)};}
  set id(v){this._id=v;ids.set(v,this);}get id(){return this._id;}
  set value(v){this._value=String(v);}get value(){return this._value||'';}
  append(...items){for(const i of items){this.children.push(i);i.parentElement=this;}}
  replaceChildren(...items){this.children=[];this.append(...items);}
  addEventListener(name,fn){(this.listeners[name]||=[]).push(fn);}setAttribute(name,value){this[name]=value;}
  querySelectorAll(){return this.children.flatMap(c=>[...(c.name?[c]:[]),...c.querySelectorAll()]);}
  checkValidity(){return this.tagName==='form'?this.querySelectorAll().every(c=>c.checkValidity()):this.disabled||!this.custom;}
  setCustomValidity(v){this.custom=v;}showModal(){this.open=true;}close(){this.open=false;}focus(){}
 }
 for(const m of fs.readFileSync(path.join(ui,'palette.html'),'utf8').matchAll(/<([a-z]+)[^>]*\bid="([^"]+)"/g)){const e=new Element(m[1]);e.id=m[2];}
 const $=id=>{assert(ids.has(id),'Missing element '+id);return ids.get(id);};
 for(const group of ['basic','advanced','edges'])$('knurling-settings').append($('knurling-'+group+'-fields'));
 const clone=v=>JSON.parse(JSON.stringify(v));
 const window={PartelierSelectionUI:{register(name,handlers){assert.equal(name,'knurling');reset=handlers.reset;}},adsk:{async fusionSendData(action,raw){
  const r=JSON.parse(raw);requests.push({action,...r});
  if(action==='knurling_begin')host={sessionId:'knurling-'+(++serial),revision:0,phase:'ready',settings:r.settings,editing:r.editing,selections:{surface:{selected:true},face_a:{selected:true},face_b:{selected:false}},previewCurrent:false};
  if(action==='knurling_preview')host={...host,settings:r.settings,revision:r.revision,phase:'preview',previewCurrent:true};
  if(action==='knurling_reset')host={...host,phase:'ready',revision:host.revision+1,previewCurrent:false};
  if(action==='knurling_cancel'||action==='knurling_commit')host={...host,endedSessionId:host.sessionId,sessionId:null,phase:action==='knurling_cancel'?'cancelled':'created',previewCurrent:false};
  return JSON.stringify({ok:true,requestId:r.requestId,knurlingState:clone(host)});
 }}};
 const context=vm.createContext({window,document:{getElementById:$,createElement:tag=>new Element(tag)},console,setTimeout(fn,ms){if(ms===400){timers.set(++timerId,fn);return timerId;}return 0;},clearTimeout(id){timers.delete(id);}});
 for(const file of ['knurling-data.js','knurling-art.js','knurling.js'])vm.runInContext(fs.readFileSync(path.join(ui,file),'utf8'),context,{filename:file});
 window.PartelierKnurling.connect({capabilities:['knurling-palette','knurling-edit']});window.PartelierKnurling.select('knurling');
 const flush=async()=>{for(let i=0;i<6;i++)await new Promise(r=>setImmediate(r));};
 const settle=async()=>{const list=[...timers.values()];timers.clear();list.forEach(fn=>fn());await flush();};
 return {$,requests,settle,host:()=>host,window,reset:()=>reset(),
  async click(id){for(const fn of $(id).listeners.click||[])fn();await flush();},
  async coverage(value){$('knurling-coverage').value=value;for(const fn of $('knurling-coverage').listeners.change||[])fn();await flush();},
  async input(name,value){const input=$('knurling-'+name);input.value=value;for(const fn of $('knurling-settings').listeners.input)fn({target:input});await flush();},
  push(snapshot){return window.PartelierKnurling.handle('knurling_state',JSON.stringify(snapshot));},

 };
}
(async()=>{
 const f=fixture();assert.equal(f.$('knurling-create').disabled,true);
 assert.equal(f.$('knurling-style').value,'diamond');assert.equal(f.$('knurling-pitch_mm').value,'6');
 assert.equal(f.$('knurling-border_mm').value,'0');assert.equal(f.$('knurling-coverage').value,'full');assert.equal(f.$('knurling-border_mm').parentElement.hidden,true);
 await f.coverage('border');assert.equal(f.$('knurling-border_mm').value,'1');assert.equal(f.$('knurling-border_mm').parentElement.hidden,false);
 await f.input('border_mm',2.5);await f.coverage('full');assert.equal(f.$('knurling-border_mm').value,'0');await f.coverage('border');assert.equal(f.$('knurling-border_mm').value,'2.5');await f.coverage('full');
 await f.coverage('border');await f.input('border_mm',-1);assert.equal(f.$('knurling-border_mm').parentElement.hidden,false,'Invalid borders stay visible for correction');await f.coverage('full');
 await f.input('mode','emboss');assert.equal(f.$('knurling-depth_mm').parentElement.children[0].textContent,'Relief height (mm)');
 const modeHelp=f.$('knurling-mode').parentElement.children.find(e=>e.dataset.knurlingHelp);for(const fn of modeHelp.listeners.click)fn();assert.match(f.$('knurling-help-image').innerHTML,/Raised outward/);await f.click('knurling-help-close');
 await f.input('mode','engrave');assert.equal(f.$('knurling-depth_mm').parentElement.children[0].textContent,'Cut depth (mm)');
 assert.equal(f.$('knurling-top_size_mm').parentElement.hidden,true);assert.equal(f.$('knurling-bottom_size_mm').parentElement.hidden,true);
 await f.input('top_finish','chamfer');await f.input('top_size_mm',1.2);assert.equal(f.$('knurling-top_size_mm').parentElement.hidden,false);assert.equal(f.$('knurling-bottom_size_mm').parentElement.hidden,true);
 await f.input('bottom_finish','fillet');await f.input('bottom_size_mm',.8);assert.equal(f.$('knurling-bottom_size_mm').parentElement.hidden,false);assert.equal(f.$('knurling-top_size_mm').value,'1.2');
 const bottomHelp=f.$('knurling-bottom_finish').parentElement.children.find(e=>e.dataset.knurlingHelp);for(const fn of bottomHelp.listeners.click)fn();assert.match(f.$('knurling-help-description').textContent,/45°/);assert.match(f.$('knurling-help-image').innerHTML,/45° start/);await f.click('knurling-help-close');
 const help=f.$('knurling-style').parentElement.children.find(e=>e.dataset.knurlingHelp);
 const artworks=new Set();
 for(const [style,label] of f.window.PartelierKnurlingData.styles){
  await f.input('style',style);for(const fn of help.listeners.click)fn();
  assert.equal(f.$('knurling-help-dialog').open,true);assert.match(f.$('knurling-help-image').innerHTML,new RegExp(label));
  assert.match(f.$('knurling-help-description').textContent,/existing cylindrical knob/);
  artworks.add(f.$('knurling-help-image').innerHTML.replace(/knurl-art-(clip|shade)-[a-z]+-\d+/g,'asset'));
  await f.click('knurling-help-close');
 }
 assert.equal(artworks.size,10);assert.equal(f.requests.length,0,'Help before selection never computes native geometry');
 await f.input('style','rings');assert.equal(f.$('knurling-phase_deg').parentElement.hidden,true);
 await f.input('style','straight');assert.equal(f.$('knurling-phase_deg').parentElement.hidden,false);assert.equal(f.$('knurling-angle_deg').parentElement.hidden,true);
 await f.input('style','helical');assert.equal(f.$('knurling-angle_deg').parentElement.hidden,false);
 await f.click('knurling-new');await f.settle();assert.equal(f.$('knurling-create').disabled,false);assert.equal(f.$('tool-select').disabled,true);
 const preview=f.requests.find(r=>r.action==='knurling_preview');assert.equal(Object.keys(preview.settings).length,11);assert.equal(preview.settings.depth_mm,.6);assert.equal(preview.settings.border_mm,0);assert.equal(preview.settings.top_finish,'chamfer');assert.equal(preview.settings.top_size_mm,1.2);assert.equal(preview.settings.bottom_finish,'fillet');assert.equal(preview.settings.bottom_size_mm,.8);assert(!Object.hasOwn(preview.settings,'coverage'));
 await f.input('mode','emboss');await f.settle();assert.equal(f.host().settings.mode,'emboss');assert.equal(f.host().settings.top_finish,'chamfer');
 await f.input('depth_mm',.8);await f.settle();const latest=f.host();assert.equal(latest.settings.depth_mm,.8);
 f.push({...latest,revision:latest.revision-1,settings:{...latest.settings,depth_mm:.3}});assert.equal(f.$('knurling-depth_mm').value,'0.8');
 await f.click('knurling-cancel');f.push(latest);assert.equal(f.window.PartelierKnurling.isActive(),false);assert.equal(f.$('knurling-create').disabled,true);
 await f.click('knurling-new');await f.input('pitch_mm',8);await f.click('knurling-cancel');const count=f.requests.length;await f.settle();assert.equal(f.requests.length,count,'Cancel retires pending preview');
 await f.click('knurling-new');await f.settle();await f.click('knurling-create');assert.equal(f.window.PartelierKnurling.isActive(),false);
 // A native picker owns references until it returns; no premature preview.
 const g=fixture();await g.click('knurling-new');const partial={...g.host(),revision:1,phase:'selecting',pickingTarget:'face_a',selections:{surface:{selected:false},face_a:{selected:false}},previewCurrent:false};g.push(partial);await g.settle();assert.equal(g.requests.filter(r=>r.action==='knurling_preview').length,0);
 g.push({...partial,revision:2,phase:'ready',pickingTarget:null,selections:{surface:{selected:true},face_a:{selected:true}}});await g.settle();assert.equal(g.requests.filter(r=>r.action==='knurling_preview').length,1);
 await g.reset();assert.equal(g.requests.at(-1).action,'knurling_reset');
 console.log('Knurling UI: ten illustrated styles, eleven typed settings, inward/outward relief, full coverage/borders, independent edge finishes, no help computation, gated live preview, stale-state protection, Cancel/Create and Esc reset passed.');
})().catch(error=>{console.error(error);process.exitCode=1;});

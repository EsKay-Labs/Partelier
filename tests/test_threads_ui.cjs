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
 for(const group of ['basic','advanced','coupon'])$('thread-settings').append($('thread-'+group+'-fields'));
 const clone=v=>JSON.parse(JSON.stringify(v));
 const window={PartelierSelectionUI:{register(name,handlers){assert.equal(name,'thread');reset=handlers.reset;}},adsk:{async fusionSendData(action,raw){
  const r=JSON.parse(raw);requests.push({action,...r});
  if(action==='thread_begin')host={sessionId:'thread-'+(++serial),revision:0,phase:'ready',settings:r.settings,editing:r.editing,selections:{surface:{selected:true},face_a:{selected:true},face_b:{selected:r.settings.mode==='pair'}},previewCurrent:false};
  if(action==='thread_preview')host={...host,settings:r.settings,revision:r.revision,phase:'preview',previewCurrent:true};
  if(action==='thread_reset')host={...host,phase:'ready',revision:host.revision+1,previewCurrent:false};
  if(action==='thread_cancel'||action==='thread_commit')host={...host,endedSessionId:host.sessionId,sessionId:null,phase:action==='thread_cancel'?'cancelled':'created',previewCurrent:false};
  return JSON.stringify({ok:true,requestId:r.requestId,threadState:clone(host)});
 }}};
 const context=vm.createContext({window,document:{getElementById:$,createElement:tag=>new Element(tag)},console,setTimeout(fn,ms){if(ms===400){timers.set(++timerId,fn);return timerId;}return 0;},clearTimeout(id){timers.delete(id);}});
 for(const file of ['thread-data.js','thread-art.js','threads.js'])vm.runInContext(fs.readFileSync(path.join(ui,file),'utf8'),context,{filename:file});
 window.PartelierThreads.connect({capabilities:['thread-palette','thread-edit']});window.PartelierThreads.select('thread');
 const flush=async()=>{for(let i=0;i<6;i++)await new Promise(r=>setImmediate(r));};
 const settle=async()=>{const list=[...timers.values()];timers.clear();list.forEach(fn=>fn());await flush();};
 return {$,requests,settle,host:()=>host,window,reset:()=>reset(),
  async click(id){for(const fn of $(id).listeners.click||[])fn();await flush();},
  async input(name,value){const input=$('thread-'+name);input.value=value;for(const fn of $('thread-settings').listeners.input)fn({target:input});await flush();},
  push(snapshot){return window.PartelierThreads.handle('thread_state',JSON.stringify(snapshot));},
  async metric(size){$('thread-metric-preset').value=size;for(const fn of $('thread-metric-preset').listeners.change)fn();await flush();}
 };
}
(async()=>{
 const f=fixture();assert.equal(f.$('thread-create').disabled,true);
 assert.equal(f.$('thread-profile').value,'printable_v');assert.equal(f.$('thread-mode').value,'external');
 assert.equal(f.$('thread-pitch_mm').value,'3');assert.equal(f.$('thread-clearance_mm').parentElement.hidden,false);assert.match(f.$('thread-fit-note').textContent,/Male reduced by 0.25/);
 const help=f.$('thread-profile').parentElement.children.find(e=>e.dataset.threadHelp);
 for(const fn of help.listeners.click)fn();assert.equal(f.$('thread-help-dialog').open,true);assert.match(f.$('thread-help-image').innerHTML,/Printable V/);assert.equal(f.requests.length,0);
 await f.click('thread-help-close');await f.input('mode','pair');
 assert.equal(f.$('thread-pick-face_b').hidden,false);assert.equal(f.$('thread-clearance_mm').parentElement.hidden,false);assert.match(f.$('thread-fit-note').textContent,/Female enlarged by 0.25/);
 await f.click('thread-new');await f.settle();
 assert.equal(f.$('thread-create').disabled,false);assert.equal(f.$('thread-mode').disabled,true);assert.equal(f.$('tool-select').disabled,true);
 const preview=f.requests.find(r=>r.action==='thread_preview');assert.equal(Object.keys(preview.settings).length,13);assert.equal(preview.settings.clearance_mm,.25);
 await f.input('length_mm',15);await f.settle();const latest=f.host();assert.equal(latest.settings.length_mm,15);
 f.push({...latest,revision:latest.revision-1,settings:{...latest.settings,length_mm:10}});assert.equal(f.$('thread-length_mm').value,'15');
 await f.click('thread-cancel');f.push(latest);assert.equal(f.window.PartelierThreads.isActive(),false);assert.equal(f.$('thread-create').disabled,true);
 await f.input('mode','coupon');assert.equal(f.$('thread-length_mm').value,'6');assert.equal(f.$('thread-selection').hidden,true);assert.equal(f.$('thread-coupon-group').hidden,false);assert.match(f.$('thread-fit-note').textContent,/0.15 \/ 0.25 \/ 0.35/);
 await f.click('thread-new');await f.settle();await f.click('thread-create');assert.equal(f.window.PartelierThreads.isActive(),false);
 await f.input('depth_mm',.8);await f.input('profile','metric');assert.equal(f.$('thread-depth_mm').parentElement.hidden,true);assert.equal(f.$('thread-depth_mm').value,'0');await f.metric('M8');assert.equal(f.$('thread-diameter_mm').value,'8');assert.equal(f.$('thread-pitch_mm').value,'1.25');assert.equal(f.$('thread-depth_mm').value,'0');
 await f.input('pitch_mm',1.3);assert.equal(f.$('thread-metric-preset').value,'custom');
 await f.click('thread-new');await f.input('length_mm',7);await f.click('thread-cancel');const count=f.requests.length;await f.settle();assert.equal(f.requests.length,count,'Cancel retires pending preview');
 // Incomplete pair and active native picker must gate preview.
 const g=fixture();await g.input('mode','pair');await g.click('thread-new');const partial={...g.host(),revision:1,phase:'selecting',pickingTarget:'face_b',selections:{surface:{selected:false},face_a:{selected:true},face_b:{selected:false}},previewCurrent:false};g.push(partial);await g.settle();assert.equal(g.requests.filter(r=>r.action==='thread_preview').length,0);assert.equal(g.$('thread-create').disabled,true);
 const complete={...partial,revision:2,phase:'ready',pickingTarget:null,selections:{surface:{selected:true},face_a:{selected:true},face_b:{selected:true}}};g.push(complete);await g.settle();assert.equal(g.requests.filter(r=>r.action==='thread_preview').length,1);
 console.log('Thread UI: typed snapshots, defaults, metric presets, illustrated help, coupon values, pair gate, stale updates, Cancel and Create passed.');
})().catch(error=>{console.error(error);process.exitCode=1;});

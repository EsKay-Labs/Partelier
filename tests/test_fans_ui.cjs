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
 for(const group of ['basic','blade','hub','frame'])$('fan-settings').append($('fan-'+group+'-fields'));
 const clone=v=>JSON.parse(JSON.stringify(v));
 const window={PartelierSelectionUI:{register(name,handlers){assert.equal(name,'fan');reset=handlers.reset;}},adsk:{async fusionSendData(action,raw){
  const r=JSON.parse(raw);requests.push({action,...r});
  if(action==='fan_begin')host={sessionId:'fan-'+(++serial),revision:0,phase:'ready',settings:r.settings,editing:r.editing,selections:{surface:{selected:true}},previewCurrent:false};
  if(action==='fan_preview')host={...host,settings:r.settings,revision:r.revision,phase:'preview',previewCurrent:true};
  if(action==='fan_reset')host={...host,phase:'ready',revision:host.revision+1,previewCurrent:false};
  if(action==='fan_cancel'||action==='fan_commit')host={...host,endedSessionId:host.sessionId,sessionId:null,phase:action==='fan_cancel'?'cancelled':'created',previewCurrent:false};
  return JSON.stringify({ok:true,requestId:r.requestId,fanState:clone(host)});
 }}};
 const context=vm.createContext({window,document:{getElementById:$,createElement:tag=>new Element(tag)},console,setTimeout(fn,ms){if(ms===400){timers.set(++timerId,fn);return timerId;}return 0;},clearTimeout(id){timers.delete(id);}});
 for(const file of ['fan-data.js','fan-art.js','fans.js'])vm.runInContext(fs.readFileSync(path.join(ui,file),'utf8'),context,{filename:file});
 window.PartelierFans.connect({capabilities:['fan-palette','fan-edit']});window.PartelierFans.select('fan');
 const flush=async()=>{for(let i=0;i<6;i++)await new Promise(r=>setImmediate(r));};
 const settle=async()=>{const list=[...timers.values()];timers.clear();list.forEach(fn=>fn());await flush();};
 return {$,requests,settle,host:()=>host,window,reset:()=>reset(),
  async click(id){for(const fn of $(id).listeners.click||[])fn();await flush();},
  async input(name,value){const input=$('fan-'+name);input.value=value;for(const fn of $('fan-settings').listeners.input)fn({target:input});await flush();},
  push(snapshot){return window.PartelierFans.handle('fan_state',JSON.stringify(snapshot));}
 };
}
(async()=>{
 const f=fixture();assert.equal(f.$('fan-create').disabled,true);await f.click('fan-new');await f.settle();
 assert.equal(f.$('fan-create').disabled,false);assert.equal(f.$('tool-select').disabled,true);
 const snapshot=f.requests.find(r=>r.action==='fan_preview');assert.equal(Object.keys(snapshot.settings).length,43);
 assert.equal(snapshot.settings.style,'axial');assert.equal(snapshot.settings.diameter_mm,112.8);
 await f.input('style','prop3');await f.settle();assert.equal(f.host().settings.size_preset,'prop5030');assert.equal(f.host().settings.blade_count,3);
 assert.equal(f.$('fan-root_angle_deg').parentElement.hidden,true);assert.equal(f.$('fan-pitch_mm').parentElement.hidden,false);
 await f.input('diameter_mm',140);await f.settle();assert.equal(f.host().settings.size_preset,'custom');assert.equal(f.host().settings.diameter_mm,140);
 await f.input('shaft_diameter_mm','');assert.equal(f.$('fan-shaft_diameter_mm').value,'','typing must not replace an empty/partial number with zero');
 await f.input('shaft_diameter_mm',5);await f.settle();
 const valid=f.host();f.push({...valid,revision:valid.revision-1,settings:{...valid.settings,diameter_mm:99}});assert.equal(f.$('fan-diameter_mm').value,'140');
 await f.input('output','hub_test');await f.settle();assert.equal(f.$('fan-diameter_mm').parentElement.hidden,true);assert.equal(f.$('fan-hub_height_mm').parentElement.hidden,false);
 const help=f.$('fan-diameter_mm').parentElement.children.find(e=>e.dataset.fanHelp);for(const fn of help.listeners.click)fn();assert.equal(f.$('fan-help-dialog').open,true);assert.match(f.$('fan-help-image').innerHTML,/<svg/);
 await f.click('fan-cancel');f.push(valid);assert.equal(f.window.PartelierFans.isActive(),false);assert.equal(f.$('fan-create').disabled,true);
 await f.click('fan-new');await f.input('hub_diameter_mm',30);await f.click('fan-cancel');const count=f.requests.length;await f.settle();assert.equal(f.requests.length,count,'cancel retires queued preview');
 await f.click('fan-new');await f.settle();await f.click('fan-create');assert.equal(f.window.PartelierFans.isActive(),false);assert.equal(f.$('tool-select').disabled,false);
 await f.input('style','blower');await f.click('fan-new');await f.settle();assert.equal(f.host().settings.style,'blower');assert.equal(f.$('fan-blower_height_mm').parentElement.hidden,false);assert.equal(f.$('fan-root_chord_mm').parentElement.hidden,true);assert.equal(f.$('fan-pick-outline').disabled,true);assert.deepEqual(f.$('fan-output').children.map(o=>o.value),['rotor','hub_test']);await f.input('blower_height_mm',14);await f.settle();assert.equal(f.host().settings.blower_height_mm,14);await f.click('fan-cancel');
 console.log('Fans UI: full snapshots, preset/custom, contextual fields/help, stale sessions, queued Cancel and Create passed.');
})().catch(e=>{console.error(e);process.exitCode=1;});

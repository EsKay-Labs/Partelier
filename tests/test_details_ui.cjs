"use strict";
// Production Small details controller: side selection gates preview and keeps atomic settings.
const assert=require("node:assert/strict"),fs=require("node:fs"),path=require("node:path"),vm=require("node:vm");
const ui=path.join(__dirname,"..","Partelier","partelier","ui");
function fixture(){
 const ids=new Map(),timers=new Map(),requests=[];let timerId=0,host=null,serial=0;
 class Element{
  constructor(tag="div"){this.tagName=tag;this.children=[];this.listeners={};this.dataset={};this.disabled=false;this.hidden=false;this.open=false;this.custom="";const classes=new Set();this.classList={add:x=>classes.add(x),toggle:(x,on)=>on?classes.add(x):classes.delete(x)};}
  set id(value){this._id=value;ids.set(value,this);}get id(){return this._id;}
  set value(value){this._value=String(value);}get value(){return this._value||"";}
  append(...items){for(const item of items){this.children.push(item);item.parentElement=this;}}
  replaceChildren(...items){this.children=[];this.append(...items);}
  setAttribute(name,value){this[name]=value;}removeAttribute(name){delete this[name];}
  addEventListener(name,handler){(this.listeners[name]||=[]).push(handler);}
  querySelectorAll(){return this.children.flatMap(child=>[...(child.name?[child]:[]),...child.querySelectorAll()]);}
  querySelector(selector){if(selector===".geometry-state")return label;if(selector===".geometry-change")return change;return null;}
  setCustomValidity(value){this.custom=value;}
  checkValidity(){if(this.tagName==="form")return this.querySelectorAll().every(x=>x.checkValidity());return this.disabled||!this.custom;}
  focus(){}showModal(){}close(){}
 }
 const html=fs.readFileSync(path.join(ui,"palette.html"),"utf8");
 for(const match of html.matchAll(/<([a-z]+)[^>]*\bid="([^"]+)"/g)){const e=new Element(match[1]);e.id=match[2];}
 const $=id=>{assert(ids.has(id),`Missing element ${id}`);return ids.get(id);};
 $("detail-settings").append($("detail-fields"),$("detail-advanced-fields"));
 const card=new Element(),label=new Element(),change=new Element();
 const document={getElementById:$,createElement:tag=>new Element(tag),querySelector:()=>card};
 const clone=value=>JSON.parse(JSON.stringify(value));
 const window={PartelierIllustrations:{render:()=>"<svg/>"},adsk:{async fusionSendData(action,raw){
  const r=JSON.parse(raw);requests.push({action,...r});
  if(action==="detail_begin")host={sessionId:`detail-${++serial}`,revision:0,phase:"ready",editing:r.editing,settings:r.settings,selections:r.editing?{edit_target:{selected:true},surface:{selected:true}}:{face_a:{selected:true,label:"Base"},face_b:{selected:true,label:"Lid"},surface:{selected:true}},previewCurrent:false};
  if(["detail_update","detail_preview","detail_commit"].includes(action)){
   const changed=host.settings.lip_layout!==r.settings.lip_layout;host.settings=r.settings;host.revision=r.revision;
   if(changed&&r.settings.lip_layout==="selected")startSides();
   else{host.phase=action==="detail_preview"?"preview":"ready";host.previewCurrent=action==="detail_preview";}
  }
  if(action==="detail_finish_sides"){
   host.settings.lip_sides=3;host.revision++;host.pickingSides=false;host.pickingTarget=null;host.selections.lip_sides={selected:true,label:"2 sides"};host.selections.surface.selected=true;host.phase="ready";host.previewCurrent=false;
  }
  if(action==="detail_clear_sides"){host.canFinishSides=false;host.selections.lip_sides={selected:false,label:"0 sides"};}
  if(action==="detail_focus"&&r.target==="lip_sides")startSides();
  if(action==="detail_cancel"){host.phase="cancelled";host.endedSessionId=host.sessionId;host.sessionId=null;}
  return JSON.stringify({requestId:r.requestId,ok:true,detailState:clone(host)});
 }}};
 function startSides(){Object.assign(host,{phase:"picking_sides",pickingSides:true,pickingTarget:"lip_sides",canFinishSides:false,previewCurrent:false});host.selections.surface.selected=false;host.selections.lip_sides={selected:false,label:"0 sides"};}
 const context=vm.createContext({window,document,console,setTimeout(fn,ms){if(ms===160){const id=++timerId;timers.set(id,fn);return id;}return 0;},clearTimeout(id){timers.delete(id);}});
 for(const file of ["workspace-flow.js","details.js"])vm.runInContext(fs.readFileSync(path.join(ui,file),"utf8"),context,{filename:file});
 window.PartelierDetails.connect({capabilities:["detail-palette","detail-edit"]});window.PartelierDetails.select("lid");
 const flush=async()=>{for(let i=0;i<6;i++)await new Promise(resolve=>setImmediate(resolve));};
 const settle=async()=>{const pending=[...timers.values()];timers.clear();pending.forEach(fn=>fn());await flush();};
 const click=async id=>{for(const fn of $(id).listeners.click||[])fn();await flush();};
 return{$,card,requests,flush,settle,click,
  async input(name,value){const input=$("detail-"+name);input.value=value;for(const fn of $("detail-settings").listeners.input)fn({target:input});await flush();},
  select:kind=>window.PartelierDetails.select(kind),
  push:()=>window.PartelierDetails.handle("detail_state",JSON.stringify(host)),
  host:()=>host,
 };
}
(async()=>{
 const f=fixture();await f.click("begin-detail-button");await f.settle();
 assert.equal(f.$("create-detail-button").disabled,false);
 const previewCount=()=>f.requests.filter(r=>r.action==="detail_preview").length;
 const before=previewCount();await f.input("lip_layout","selected");await f.settle();
 assert.equal(f.requests.at(-1).action,"detail_update");assert.equal(previewCount(),before,"layout change waits for selected sides");
 assert.equal(f.card.open,true);assert.equal(f.$("detail-done-sides").disabled,true);
 assert.equal(f.$("detail-lip_height_mm").disabled,true);assert.equal(f.$("detail-pick-face_a").disabled,true);
 assert.equal(f.$("create-detail-button").disabled,true);
 f.host().canFinishSides=true;f.host().selections.lip_sides.label="2 sides";f.push();
 await f.click("detail-done-sides");await f.settle();
 assert.equal(previewCount(),before+1);assert.equal(f.$("create-detail-button").disabled,false);assert.equal(f.card.open,false);
 const request=f.requests.at(-1);assert.equal(request.settings.lip_sides,3);assert.equal(request.settings.lip_layout,"selected");assert.equal(Object.keys(request.settings).length,21);
 await f.click("detail-pick-lip_sides");assert.equal(f.card.open,true);assert.equal(f.$("detail-lip_width_mm").disabled,true);
 await f.click("detail-clear-sides");assert.equal(f.$("detail-done-sides").disabled,true);
 await f.click("cancel-detail-button");f.select("ribs");
 assert.equal(f.$("detail-rib_height_b_mm").parentElement.children[0].textContent,"Height · face A (mm)");
 assert.equal(f.$("detail-rib_height_a_mm").parentElement.children[0].textContent,"Width · face B (mm)");
 assert.equal(f.$("detail-rib_width_mm").parentElement.children[0].textContent,"Thickness (mm)");
 const css=fs.readFileSync(path.join(ui,"palette.css"),"utf8");
 assert(css.includes('[data-field="rib_height_b_mm"] { order: -8; }'));
 assert(css.includes('[data-field="rib_height_a_mm"] { order: -7; }'));
 console.log("Small details UI: selected-side Done gate,21-field snapshots,repick/clear and rib labels passed.");
})().catch(error=>{console.error(error);process.exitCode=1;});

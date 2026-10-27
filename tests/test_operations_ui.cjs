"use strict";
// Real saved-feature controller, isolated DOM/host contract. No Fusion geometry.
const assert=require("node:assert/strict"),fs=require("node:fs"),path=require("node:path"),vm=require("node:vm");
class Element{
 constructor(){this.children=[];this.listeners={};this.dataset={};this.hidden=false;this.disabled=false;this.value="hinge";const classes=new Set();this.classList={toggle:(name,on)=>on?classes.add(name):classes.delete(name),contains:name=>classes.has(name)};}
 append(...nodes){this.children.push(...nodes);}replaceChildren(...nodes){this.children=nodes;}
 setAttribute(name,value){this[name]=value;}addEventListener(name,fn){(this.listeners[name]||=[]).push(fn);}
 click(){return this.disabled?Promise.resolve():Promise.all((this.listeners.click||[]).map(fn=>fn()));}
 scrollIntoView(){}
}
const ids=new Map(),$=id=>{if(!ids.has(id))ids.set(id,new Element());return ids.get(id);};
const requests=[],timers=new Map();let timerId=0,active=false,holdList=false,releaseList,pendingDelete=false,deleteFailure=false,opened;
const feature=(id,alias,name,canDelete=true)=>({id,tool:alias==='lid'?'detail':'pattern',alias,name,canDelete});
let items=[feature('a','honeycomb','Surface pattern · Hexagon · a'),feature('b','perforation','Surface pattern · Circle · b'),feature('c','knurl','Surface texture · Diamond · c'),feature('d','truss','Planar truss · Warren · d'),feature('e','grilles','Grille · Cross · e'),feature('f','lid','Lid · f'),feature('g','truss','Older truss · g',false)];
const window={PartelierPatterns:{isActive:()=>active,isBusy:()=>false},PartelierOpenOperation:(response,alias)=>{opened={response,alias};active=true;window.PartelierOperations.select(alias);},adsk:{fusionSendData(action,raw){
 const r=JSON.parse(raw);requests.push({action,...r});let response={ok:true,protocol:1,requestId:r.requestId,operations:structuredClone(items)};
 if(action==='operation_edit')Object.assign(response,{operationAlias:items.find(x=>x.id===r.operationId).alias,patternState:{editing:true}});
 if(action==='operation_delete'){
  if(deleteFailure)response={...response,ok:false,message:'This operation has later features.'};
  else if(pendingDelete)response.operationPending=true;
  else{items=items.filter(x=>x.id!==r.operationId);response.operations=structuredClone(items);}
 }
 const result=JSON.stringify(response);
 if(action==='operations_list'&&holdList)return new Promise(resolve=>{releaseList=()=>resolve(result);});
 return Promise.resolve(result);
}}};
const sandbox={window,document:{getElementById:$,createElement:()=>new Element()},setTimeout:fn=>{const id=++timerId;timers.set(id,fn);return id;},clearTimeout:id=>timers.delete(id),queueMicrotask};
vm.runInNewContext(fs.readFileSync(path.join(__dirname,'../Partelier/partelier/ui/operations.js'),'utf8'),sandbox);
const api=window.PartelierOperations,flush=async()=>{for(let i=0;i<8;i++)await new Promise(setImmediate);};
const settle=async()=>{const queued=[...timers.values()];timers.clear();queued.forEach(fn=>fn());await flush();};
const rows=()=>$('section-features-list').children;
const find=id=>rows().find(row=>row.dataset.operationId===id);
const button=(row,text)=>row.children.flatMap(n=>n.children||[]).concat(row.children).find(n=>n.textContent===text);
const push=()=>api.handle('operations_state',JSON.stringify({items,message:'Feature deleted. Undo restores it.'}));
(async()=>{
 assert.equal(requests.length,0);assert($('section-features-refresh').disabled);
 api.connect();await flush();assert.equal(requests.length,1);assert.equal(rows().length,0);
 api.select('honeycomb');await settle();assert.deepEqual(rows().map(x=>x.dataset.operationId),['a','b','c']);
 for(const alias of ['perforation','knurl']){api.select(alias);await settle();assert.equal(rows().length,3);}
 api.select('truss');await settle();assert.deepEqual(rows().map(x=>x.dataset.operationId),['d','g']);assert(button(find('g'),'Delete…').disabled);
 await button(find('d'),'Edit').click();await flush();assert.equal(opened.alias,'truss');assert.equal(requests.at(-1).operationId,'d');assert(find('d').classList.contains('is-editing'));assert(button(find('g'),'Edit').disabled);
 api.handle('pattern_state',JSON.stringify({phase:'cancelled',sessionId:'retired-session'}));await settle();assert(find('d').classList.contains('is-editing'),'a retired terminal push cannot clear the current active edit');
 active=false;api.handle('pattern_state',JSON.stringify({phase:'cancelled'}));await settle();assert(!find('d').classList.contains('is-editing'));
 await button(find('d'),'Delete…').click();assert.equal(requests.at(-1).action,'operations_list');assert(button(find('d'),'Delete feature'));
 await button(find('d'),'Keep').click();assert(!button(find('d'),'Delete feature'));
 await button(find('d'),'Delete…').click();pendingDelete=true;await button(find('d'),'Delete feature').click();await flush();assert.equal(requests.at(-1).operationId,'d');assert(button(find('d'),'Edit').disabled);assert($('section-features-refresh').disabled);
 items=items.filter(x=>x.id!=='d');push();await flush();assert(!find('d'));assert(!$('section-features-refresh').disabled);
 // The host may finish deletion before its earlier pending acknowledgement arrives.
 api.select('grilles');await settle();
 const send=window.adsk.fusionSendData;window.adsk.fusionSendData=(action,raw)=>{if(action==='operation_delete'){const promise=send(action,raw);items=items.filter(x=>x.id!=='e');push();return promise;}return send(action,raw);};
 await button(find('e'),'Delete…').click();await button(find('e'),'Delete feature').click();await flush();assert.equal(rows().length,0);assert(!$('section-features-refresh').disabled);window.adsk.fusionSendData=send;
 // A delayed list must never resurrect a feature already removed by a native push.
 api.select('honeycomb');await settle();holdList=true;const refresh=api.refresh();await flush();items=items.filter(x=>x.id!=='a');push();releaseList();await refresh;assert.deepEqual(rows().map(x=>x.dataset.operationId),['b','c']);holdList=false;
 // Create/Rebuild pushes refresh metadata only, without geometry/picking requests.
 items.push(feature('h','truss','Planar truss · Howe · h'));api.handle('pattern_state',JSON.stringify({phase:'created'}));await settle();api.select('truss');await settle();assert(find('h'));
 deleteFailure=true;await button(find('h'),'Delete…').click();await button(find('h'),'Delete feature').click();await flush();assert(find('h'));assert($('section-features-message').textContent.includes('later features'));assert($('section-features-message').classList.contains('is-error'));
 assert(requests.every(x=>['operations_list','operation_edit','operation_delete'].includes(x.action)));
 assert.equal($('operations-list').children.length,items.length);
 console.log('Saved features: section filtering, exact Edit/Delete, cancellation, legacy, native pending/error and stale acknowledgement checks pass.');
})().catch(error=>{console.error(error);process.exitCode=1;});

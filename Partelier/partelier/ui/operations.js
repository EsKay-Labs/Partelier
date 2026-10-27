"use strict";

(()=>{
 const $=id=>document.getElementById(id);
 const section=alias=>["honeycomb","perforation","knurl"].includes(alias)?"surface":alias;
 let sequence=0,busy=false,deleting=false,connected=false,items=[],confirmation=null;
 let selected=$("tool-select").value,editingId=null,timer,rendered,listVersion=0,refreshQueued=false;
 const locked=()=>!!window.PartelierHingeActive||!!window.PartelierSnap?.isActive()||!!window.PartelierSnap?.isBusy()||!!window.PartelierPatterns?.isActive()||!!window.PartelierPatterns?.isBusy()||!!window.PartelierDetails?.isActive()||!!window.PartelierDetails?.isBusy();
 const unavailable=()=>busy||deleting||locked();
 function message(text,error=false){
  for(const id of ["operations-message","section-features-message"]){const node=$(id);node.textContent=text;node.classList.toggle("is-error",error);node.hidden=!text;}
 }
 function rowFor(item,location){
  const row=document.createElement("div");row.className="operation-row";row.dataset.operationId=item.id;
  row.classList.toggle("is-editing",editingId===item.id);
  const title=document.createElement("strong");title.textContent=item.name;
  const actions=document.createElement("div");actions.className="operation-actions";
  const edit=document.createElement("button");edit.type="button";edit.className="secondary-button";edit.textContent="Edit";
  edit.disabled=unavailable();edit.setAttribute("aria-label","Edit "+item.name);edit.addEventListener("click",()=>act("operation_edit",item.id));
  const remove=document.createElement("button");remove.type="button";remove.className="text-button operation-delete";remove.textContent="Delete…";
  remove.disabled=unavailable()||!item.canDelete;remove.setAttribute("aria-label","Delete "+item.name);
  remove.title=item.canDelete?"Delete this complete feature; later features may block deletion":"Older feature: rebuild it to adopt its history, or use the Fusion timeline";
  remove.addEventListener("click",()=>{if(unavailable())return;confirmation={id:item.id,location};render();});actions.append(edit,remove);
  row.append(title,actions);
  if(editingId===item.id){const label=document.createElement("span");label.className="operation-editing-label";label.textContent="Editing · change settings, then Rebuild or Cancel below.";row.append(label);}
  if(confirmation?.id===item.id&&confirmation.location===location){
   const note=document.createElement("p");note.textContent="Delete “"+item.name+"”? Source bodies stay. Later features can block deletion.";
   const yes=document.createElement("button");yes.type="button";yes.className="secondary-button";yes.textContent="Delete feature";yes.disabled=unavailable();yes.addEventListener("click",()=>act("operation_delete",item.id));
   const no=document.createElement("button");no.type="button";no.className="text-button";no.textContent="Keep";no.disabled=busy||deleting;no.addEventListener("click",()=>{confirmation=null;render();});row.append(note,yes,no);
  }
  return row;
 }
 function render(){
  if(editingId&&!locked())editingId=null;
  const key=JSON.stringify([items,confirmation,busy,deleting,locked(),selected,editingId,connected]);if(key===rendered)return;rendered=key;
  const scoped=items.filter(item=>section(item.alias)===section(selected));
  $("operations-count").textContent=String(items.length);$("section-features-count").textContent=String(scoped.length);
  for(const id of ["operations-refresh","section-features-refresh"])$(id).disabled=busy||deleting||!connected;
  $("operation-pick-model").disabled=unavailable();
  $("section-features-empty").hidden=scoped.length>0;
  $("section-features-empty").textContent=!connected?"Open Partelier in Fusion to see saved features.":"No saved features in this section yet.";
  $("operations-list").replaceChildren(...items.map(item=>rowFor(item,"all")));
  $("section-features-list").replaceChildren(...scoped.map(item=>rowFor(item,"section")));
 }
 async function request(action,payload={}){
  const requestId="operation-ui-"+(++sequence);
  const raw=await window.adsk.fusionSendData(action,JSON.stringify({protocol:1,requestId,...payload}));
  const response=typeof raw==="string"?JSON.parse(raw):raw;
  if(!response?.ok||response.protocol!==1||response.requestId!==requestId)throw Error(response?.message||"Could not read the saved features.");
  return response;
 }
 function scheduleRefresh(){clearTimeout(timer);timer=setTimeout(refresh,150);}
 function finished(){busy=false;render();if(refreshQueued){refreshQueued=false;scheduleRefresh();}}
 async function refresh(){
  if(busy||deleting){refreshQueued=true;return;}
  if(!connected||!window.adsk?.fusionSendData)return;
  busy=true;render();const version=listVersion;
  try{
   const response=await request("operations_list");
   // An asynchronous native push is newer than a delayed request acknowledgement.
   if(version===listVersion){items=response.operations||[];message(locked()&&!editingId?"Finish with Create / Rebuild or Cancel before choosing another saved feature.":"");}
  }catch(error){message(error.message,true);}
  finally{finished();}
 }
 async function act(action,identity){
  if(unavailable())return;
  busy=true;render();message(action==="operation_edit"?"Loading this feature…":"Deleting this feature…");const version=listVersion;
  try{
   const response=await request(action,{operationId:identity});confirmation=null;
   if(response.operations&&version===listVersion)items=response.operations;
   if(action==="operation_edit"){
    editingId=identity;
    window.PartelierOpenOperation?.(response,response.operationAlias);
    message("");$("operations-browser").open=false;$("tool-workspace").scrollTop=0;
   }else if(response.operationPending&&version===listVersion){deleting=true;message("Finishing deletion…");}
   else if(version===listVersion)message("Feature deleted. Undo restores it.");
  }catch(error){confirmation=null;message(error.message,true);}
  finally{finished();}
 }
 for(const id of ["operations-refresh","section-features-refresh"])$(id).addEventListener("click",refresh);
 $("saved-operations-button").addEventListener("click",()=>{const browser=$("operations-browser");browser.hidden=false;browser.open=!browser.open;if(browser.open)browser.scrollIntoView({block:"start"});});
 $("operation-pick-model").addEventListener("click",()=>{if(unavailable())return;$("operations-browser").open=false;window.PartelierPickFromModel?.();});
 $("operations-browser").addEventListener("toggle",()=>{const open=$("operations-browser").open;$("operations-browser").hidden=!open;$("saved-operations-button").setAttribute("aria-expanded",String(open));if(open)refresh();});
 window.PartelierOperations=Object.freeze({
  refresh,
  connect(){connected=true;refresh();},
  select(alias){if(selected===alias)return;selected=alias;confirmation=null;message("");render();if(connected)scheduleRefresh();},
  handle(action,raw){
   if(action==="operations_state"){
    const value=JSON.parse(raw);listVersion++;items=value.items||[];deleting=false;confirmation=null;
    if(!items.some(item=>item.id===editingId))editingId=null;
    message(value.message||"");render();if(refreshQueued&&!busy){refreshQueued=false;scheduleRefresh();}return true;
   }
   if(["hinge_state","snap_state","pattern_state","detail_state"].includes(action)){
    const value=JSON.parse(raw);
    if(["created","cancelled"].includes(value.phase)){confirmation=null;scheduleRefresh();}
    // The tool applies its pushed state after this handler returns.
    queueMicrotask(render);
   }
   return false;
  }
 });
 render();
})();

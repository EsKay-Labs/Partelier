"use strict";

(()=>{
 const $=id=>document.getElementById(id);
 let sequence=0,busy=false,items=[],confirmation=null,timer,rendered;
 const locked=()=>!!window.PartelierHingeActive||!!window.PartelierSnap?.isActive()||!!window.PartelierSnap?.isBusy()||!!window.PartelierPatterns?.isActive()||!!window.PartelierPatterns?.isBusy()||!!window.PartelierDetails?.isActive()||!!window.PartelierDetails?.isBusy();
 function message(text){$("operations-message").textContent=text;}
 function render(){
  const key=JSON.stringify([items,confirmation,busy,locked()]);if(key===rendered)return;rendered=key;
  $("operations-count").textContent=String(items.length);
  $("operations-refresh").disabled=busy;
  const rows=items.map(item=>{
   const row=document.createElement("div");row.className="operation-row";
   const title=document.createElement("strong");title.textContent=item.name;
   const actions=document.createElement("div");actions.className="operation-actions";
   const edit=document.createElement("button");edit.type="button";edit.className="secondary-button";edit.textContent="Edit";edit.disabled=busy||locked();edit.setAttribute("aria-label","Edit "+item.name);edit.addEventListener("click",()=>act("operation_edit",item.id));
   const remove=document.createElement("button");remove.type="button";remove.className="text-button";remove.textContent="Delete…";remove.disabled=busy||locked()||!item.canDelete;remove.title=item.canDelete?"Delete this complete operation":"Older operation: delete its features from the Fusion timeline";remove.addEventListener("click",()=>{confirmation=item.id;render();});actions.append(edit,remove);
   row.append(title,actions);
   if(confirmation===item.id){const note=document.createElement("p");note.textContent="Delete this complete operation and its matching features? The selected source bodies are kept. Later features may block deletion.";const yes=document.createElement("button");yes.type="button";yes.className="secondary-button";yes.textContent="Delete operation";yes.disabled=busy||locked();yes.addEventListener("click",()=>act("operation_delete",item.id));const no=document.createElement("button");no.type="button";no.className="text-button";no.textContent="Keep";no.disabled=busy;no.addEventListener("click",()=>{confirmation=null;render();});row.append(note,yes,no);}
   return row;
  });
  $("operations-list").replaceChildren(...rows);
 }
 async function request(action,payload={}){
  const requestId=`operation-ui-${++sequence}`;
  const raw=await window.adsk.fusionSendData(action,JSON.stringify({protocol:1,requestId,...payload}));
  const response=typeof raw==="string"?JSON.parse(raw):raw;
  if(!response?.ok||response.protocol!==1||response.requestId!==requestId)throw Error(response?.message||"Could not read the saved operations.");
  return response;
 }
 async function refresh(){
  if(busy)return;
  if(!window.adsk?.fusionSendData){message("Open Partelier in Fusion to see operations in this design.");return;}
  busy=true;render();
  try{const response=await request("operations_list");items=response.operations||[];message(locked()?"Create or Cancel the current preview before editing a saved operation.":items.length?"Choose an operation to load its dimensions.":"No saved Partelier operations in this design.");}
  catch(error){message(error.message);}
  finally{busy=false;render();}
 }
 async function act(action,identity){
  if(busy||locked())return;
  busy=true;render();message(action==="operation_edit"?"Loading this operation…":"Deleting the chosen operation…");
  try{
   const response=await request(action,{operationId:identity});confirmation=null;
   if(response.operations)items=response.operations;
   if(action==="operation_edit"){
    window.PartelierOpenOperation?.(response,response.operationAlias);
    message("Operation loaded. Change its dimensions, then Rebuild.");
    document.querySelector("#operations-browser").open=false;
    $("tool-workspace").scrollTop=0;
   }else if(response.operationPending){message("Finishing the native deletion…");}
   else message("Operation deleted. Undo restores it.");
  }catch(error){message(error.message);}
  finally{busy=false;render();}
 }
 $("operations-refresh").addEventListener("click",refresh);
 $("saved-operations-button").addEventListener("click",()=>{const browser=$("operations-browser");browser.hidden=false;browser.open=!browser.open;if(browser.open)browser.scrollIntoView({block:"start"});});
 $("operation-pick-model").addEventListener("click",()=>{if(locked()){message("Create or Cancel the current preview first.");return;}$("operations-browser").open=false;window.PartelierPickFromModel?.();});
 $("operations-browser").addEventListener("toggle",()=>{const open=$("operations-browser").open;$("operations-browser").hidden=!open;$("saved-operations-button").setAttribute("aria-expanded",String(open));if(open)refresh();});
 window.PartelierOperations=Object.freeze({
  refresh,
  handle(action,raw){
   if(action==="operations_state"){const value=JSON.parse(raw);items=value.items||[];message(value.message||"");render();return true;}
   if(["hinge_state","snap_state","pattern_state","detail_state"].includes(action)){
    const value=JSON.parse(raw);if(["created","cancelled"].includes(value.phase)){clearTimeout(timer);timer=setTimeout(refresh,350);}
    queueMicrotask(render);
   }
   return false;
  }
 });
 render();
})();

"use strict";

// Shared presentation only. Geometry and native selection stay in Python.
window.PartelierSelectionUI=(()=>{
 const resets=new Map();
 function decorate(button,index,target,snapshot,targets){
  const picked=snapshot?.selections?.[target];
  const next=snapshot?.pickingTarget||targets.find(name=>!snapshot?.selections?.[name]?.selected);
  button.dataset.step=String(index+1);button.dataset.reference=target;
  button.classList.add("selection-step");
  button.classList.toggle("is-next",target===next);
  button.classList.toggle("is-picking",target===snapshot?.pickingTarget);
  button.classList.toggle("is-selected",!!picked?.selected);
  if(target===next)button.setAttribute("aria-current","step");
  else button.removeAttribute("aria-current");
  if(target===snapshot?.pickingTarget)button.setAttribute("aria-label",(button.getAttribute("aria-label")||button.textContent)+" · Select this reference in Fusion now");
 }
 function resetControl(container,key,enabled){
  let button=document.getElementById(key+"-reset-selection");
  if(!button){button=document.createElement("button");button.id=key+"-reset-selection";button.type="button";button.className="text-button selection-reset";button.textContent="Reset selection · Esc";button.addEventListener("click",()=>resets.get(key)?.reset());container.after(button);}
  button.disabled=!enabled;button.hidden=!enabled;
 }
 document.addEventListener("keydown",event=>{
  if(event.key!=="Escape"||document.querySelector("dialog[open]")||event.defaultPrevented)return;
  const entry=[...resets.values()].find(item=>item.active()&&!item.busy());
  if(entry){event.preventDefault();entry.reset();}
 });
 // Wheels over number/select fields must scroll, not silently change dimensions.
 // Header/footer wheel gestures also reach the sole workspace scroll container.
 document.addEventListener("wheel",event=>{
  if(event.ctrlKey||event.metaKey||document.querySelector("dialog[open]")||event.defaultPrevented)return;
  const workspace=document.getElementById("tool-workspace");
  const target=event.target;
  if(!workspace||!target?.closest||workspace.scrollHeight<=workspace.clientHeight)return;
  if(target.closest(".workspace")&&!target.closest('input[type="number"],select'))return;
  const delta=event.deltaY*(event.deltaMode===1?18:event.deltaMode===2?workspace.clientHeight:1);
  if(!delta)return;
  event.preventDefault();workspace.scrollBy({top:delta,behavior:"instant"});
 },{passive:false});
 return Object.freeze({decorate,resetControl,register:(key,value)=>resets.set(key,value)});
})();

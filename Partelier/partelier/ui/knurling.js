"use strict";
(() => {
 const $=id=>document.getElementById(id),D=window.PartelierKnurlingData,defaults=D.defaults,clone=v=>JSON.parse(JSON.stringify(v));
 const choices={style:D.styles};
 const terminal=new Set(["idle","cancelled","created"]),retired=new Set();
 const state={selected:false,settings:clone(defaults),session:null,revision:0,connected:false,caps:new Set(),busy:false,expecting:false,error:false};
 let sequence=0,hostRevision=-1,pushVersion=0,timer,poll,previewFlight=false,queued=false,queue=Promise.resolve(),helpTrigger;
 const active=()=>!!state.session?.sessionId&&!terminal.has(state.session.phase),identity=()=>active()?state.session.sessionId:null;
 const other=()=>!!window.PartelierHingeActive||[window.PartelierSnap,window.PartelierPatterns,window.PartelierDetails,window.PartelierFans,window.PartelierMechanisms,window.PartelierFinishing,window.PartelierThreads].some(m=>m?.isActive()||m?.isBusy());
 const ready=()=>!!identity()&&!state.session?.pickingTarget&&!!state.session?.selections?.surface?.selected;
 const valid=()=>$("knurling-settings").checkValidity();
 const current=()=>active()&&state.session.phase==="preview"&&state.session.revision===state.revision&&state.session.previewCurrent&&!state.error;
 const message=(text,error=false)=>{$("knurling-message").textContent=text;$("knurling-message").classList.toggle("error",error);};
 function options(input,items){input.replaceChildren(...items.map(([value,text])=>{const o=document.createElement("option");o.value=value;o.textContent=text;return o;}));}
 function sync(){for(const input of $("knurling-settings").querySelectorAll("[name]"))input.value=state.settings[input.name];}
 function apply(snapshot){
  if(!snapshot||!Number.isInteger(snapshot.revision)||!snapshot.phase)return false;
  const old=state.session?.sessionId,id=snapshot.sessionId,ended=snapshot.endedSessionId;
  if(id&&retired.has(id)||ended&&active()&&ended!==old||active()&&id&&id!==old&&!state.expecting||id===old&&snapshot.revision<hostRevision)return false;
  if(old&&(id!==old||terminal.has(snapshot.phase)))retired.add(old);
  state.session=snapshot;hostRevision=snapshot.revision;
  if(snapshot.settings&&(snapshot.revision>=state.revision||state.expecting||id&&id!==old)){state.settings=clone(snapshot.settings);state.revision=snapshot.revision;sync();}
  state.error=snapshot.phase==="error";message(snapshot.message||"",state.error);render();
  if(["computing","opening"].includes(snapshot.phase))recover();
  return true;
 }
 function recover(){clearTimeout(poll);poll=setTimeout(async()=>{if(!active())return;if(state.busy){recover();return;}try{await send("knurling_status");}catch(error){message(error.message,true);recover();}},2000);}
 async function send(action,payload={}){
  const requestId=`knurling-ui-${++sequence}`,version=pushVersion;
  const raw=await window.adsk.fusionSendData(action,JSON.stringify({protocol:1,requestId,...payload}));
  let r;try{r=typeof raw==="string"?JSON.parse(raw):raw;}catch(_){throw Error("Invalid Fusion response.");}
  if(!r?.ok||r.requestId!==requestId)throw Error(r?.message||r?.error||"Fusion could not complete the knurling request.");
  if(r.knurlingState&&(!payload.sessionId||payload.sessionId===identity()||state.expecting)&&!(version!==pushVersion&&!state.expecting&&r.knurlingState.revision<=hostRevision))apply(r.knurlingState);
  return r;
 }
 function action(name,extra={}){if(!identity())throw Error("Start a knurling session first.");const p={sessionId:identity(),...extra};if(["knurling_update","knurling_preview","knurling_commit"].includes(name))Object.assign(p,{revision:state.revision,settings:clone(state.settings)});return send(name,p);}
 function run(work){queue=queue.then(async()=>{state.busy=true;render();try{await work();}catch(error){state.error=true;message(error.message,true);}finally{state.busy=false;render();if(queued){queued=false;schedule();}}});return queue;}
 const computingCurrent=()=>state.session?.phase==="computing"&&state.session.revision===state.revision;
 function schedule(){clearTimeout(timer);if(!ready()||!valid()||current()||computingCurrent()||state.session.phase==="opening")return;if(state.busy||previewFlight){queued=true;return;}timer=setTimeout(refresh,400);}
 async function refresh(){
  if(!ready()||!valid()||current()||computingCurrent())return;if(previewFlight){queued=true;return;}previewFlight=true;const rev=state.revision;
  try{await action("knurling_preview");}catch(error){state.error=true;message(error.message,true);render();}finally{previewFlight=false;if(queued||rev!==state.revision){queued=false;schedule();}}
 }
 function render(){
  const supported=state.connected&&state.caps.has("knurling-palette"),opening=state.session?.phase==="opening",computing=state.session?.phase==="computing";
  $("knurling-tool").hidden=!state.selected;$("knurling-action-dock").hidden=!state.selected;
  for(const input of $("knurling-settings").querySelectorAll("[name]")){
   const show=(input.name!=="angle_deg"||["diamond","helical","chevron","waves"].includes(state.settings.style))&&(input.name!=="phase_deg"||state.settings.style!=="rings");
   input.parentElement.hidden=!show;input.disabled=!show||state.busy||opening;
  }
  $("knurling-availability").hidden=supported;$("knurling-availability").textContent=state.connected?"Restart Partelier to enable Knurling.":"Open Partelier in Fusion to texture a knob.";
  $("knurling-new").hidden=active();$("knurling-edit").hidden=active();
  $("knurling-new").disabled=!supported||state.busy||other()||!valid();$("knurling-edit").disabled=!supported||!state.caps.has("knurling-edit")||active()||state.busy||other();
  const b=$("knurling-pick-face_a"),picked=state.session?.selections?.face_a?.selected;
  b.textContent=picked?"Outer cylinder · selected":"Outer cylinder · select";
  b.classList.toggle("is-selected",!!picked);b.classList.toggle("is-next",!picked);
  b.disabled=!supported||state.busy||opening||computing||other()||!!state.session?.editing;
  window.PartelierSelectionUI?.decorate?.(b,0,"face_a",state.session,["face_a"]);
  $("knurling-reset").disabled=!identity()||state.busy||opening;$("knurling-cancel").disabled=!identity()||state.busy||opening;
  $("knurling-create").disabled=!supported||!ready()||!current()||!valid()||state.busy;$("knurling-create").textContent=state.session?.editing?"Rebuild knurling":"Create knurling";
  $("knurling-retry").hidden=!ready()||current();$("knurling-retry").disabled=state.busy||opening||computing||!valid();
  $("knurling-status").textContent="Live preview · "+(!supported?"Fusion required":opening?"creating…":computing?"computing…":state.error?"needs attention":current()?"up to date":ready()?"waiting for update":"select outer cylinder");
  $("knurling-style-note").textContent=D.descriptions[state.settings.style];
  $("knurling-example").innerHTML=window.PartelierKnurlingArt.render(state.settings);
  $("tool-select").disabled=active()||state.busy||other();window.PartelierRefreshActions?.();
 }

 for(const [group,names] of Object.entries(D.groups))for(const name of names){
  const item=document.createElement("div");item.className="parameter-item has-parameter-help";if(name==="style")item.classList.add("full-width-parameter");
  const label=document.createElement("label");label.htmlFor="knurling-"+name;label.textContent=D.labels[name];
  const input=document.createElement(choices[name]?"select":"input");input.id="knurling-"+name;input.name=name;input.required=true;
  if(choices[name])options(input,choices[name]);else {input.type="number";input.step="any";[input.min,input.max]=D.bounds[name]||[0,1000];}
  const help=document.createElement("button");help.type="button";help.className="parameter-help";help.textContent="?";help.setAttribute("aria-label","Help: "+D.labels[name]);help.dataset.knurlingHelp=name;
  help.addEventListener("click",()=>{helpTrigger=help;$("knurling-help-title").textContent=D.labels[name];$("knurling-help-description").textContent=D.help[name]+(name==="style"?" "+D.descriptions[state.settings.style]:"");$("knurling-help-image").innerHTML=window.PartelierKnurlingArt.render(state.settings,name);$("knurling-help-dialog").showModal();});
  item.append(label,input,help);$("knurling-"+group+"-fields").append(item);
 }
 $("knurling-settings").addEventListener("submit",e=>e.preventDefault());
 function changed(){state.revision++;state.error=false;render();message(!valid()?"Check the dimensions.":active()?"Updating live preview…":"Choose settings, then start.",!valid());schedule();}
 $("knurling-settings").addEventListener("input",e=>{
  const input=e.target,name=input.name;if(!Object.hasOwn(defaults,name))return;
  state.settings[name]=typeof defaults[name]==="number"?Number(input.value):input.value;
  changed();
 });

 async function begin(editing){state.expecting=true;try{hostRevision=-1;await send("knurling_begin",{settings:clone(state.settings),editing});}finally{state.expecting=false;}schedule();}
 $("knurling-new").addEventListener("click",()=>run(()=>begin(false)));$("knurling-edit").addEventListener("click",()=>run(()=>begin(true)));
 for(const target of ["face_a"])$("knurling-pick-"+target).addEventListener("click",()=>run(async()=>{if(!identity()){await begin(false);return;}clearTimeout(timer);queued=false;await action("knurling_focus",{target});schedule();}));
 $("knurling-retry").addEventListener("click",refresh);$("knurling-create").addEventListener("click",()=>run(()=>action("knurling_commit")));
 const reset=()=>run(async()=>{clearTimeout(timer);queued=false;await action("knurling_reset");});
 $("knurling-reset").addEventListener("click",reset);$("knurling-cancel").addEventListener("click",()=>run(async()=>{clearTimeout(timer);clearTimeout(poll);queued=false;await action("knurling_cancel");}));
 $("knurling-help-close").addEventListener("click",()=>$("knurling-help-dialog").close());$("knurling-help-dialog").addEventListener("close",()=>helpTrigger?.focus());
 window.PartelierSelectionUI?.register("knurling",{active,busy:()=>state.busy,reset});
 window.PartelierKnurling=Object.freeze({matches:id=>id==="knurling",isActive:active,isBusy:()=>state.busy,
  select(id){state.selected=id==="knurling";render();},
  connect(response){state.connected=true;state.caps=new Set(response.capabilities||[]);if(!active()&&response.knurlingDefaults){state.settings=clone(response.knurlingDefaults);sync();}if(response.knurlingState)apply(response.knurlingState);render();if(ready()&&state.session.phase==="ready")schedule();return active()?"knurling":null;},
  handle(name,raw){if(name!=="knurling_state")return false;pushVersion++;const accepted=apply(JSON.parse(raw));if(accepted&&ready()&&state.session.phase==="ready")schedule();return true;}
 });
 sync();render();
})();

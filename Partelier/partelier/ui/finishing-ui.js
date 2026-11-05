"use strict";
(() => {
 const $=id=>document.getElementById(id),D=window.PartelierFinishingData,defaults=D.defaults,clone=v=>JSON.parse(JSON.stringify(v));
 const choices={edge_side:[["top","Top"],["bottom","Bottom"],["left","Left"],["right","Right"]],kind:[["notch","Finger notch"],["keyhole","Keyhole slot"],["stop","Motion stop"],["text","Text label"],["arrow","Direction arrow"],["scale","Scale marks"]],mode:[["engrave","Engraved"],["emboss","Raised"]]};
 const terminal=new Set(["idle","cancelled","created"]),retired=new Set();
 const state={selected:false,settings:clone(defaults),session:null,revision:0,connected:false,caps:new Set(),busy:false,expecting:false,error:false};
 let sequence=0,hostRevision=-1,pushVersion=0,timer,poll,previewFlight=false,queued=false,queue=Promise.resolve(),helpTrigger;
 const active=()=>!!state.session?.sessionId&&!terminal.has(state.session.phase),identity=()=>active()?state.session.sessionId:null;
 const other=()=>!!window.PartelierKnurling?.isActive()||!!window.PartelierKnurling?.isBusy()||!!window.PartelierThreads?.isActive()||!!window.PartelierThreads?.isBusy()||!!window.PartelierHingeActive||[window.PartelierSnap,window.PartelierPatterns,window.PartelierDetails,window.PartelierFans,window.PartelierMechanisms].some(m=>m?.isActive()||m?.isBusy());
 const ready=()=>!!identity()&&!state.session?.pickingTarget&&!!state.session?.selections?.surface?.selected;
 const valid=()=>$("finishing-settings").checkValidity();
 const current=()=>active()&&state.session.phase==="preview"&&state.session.revision===state.revision&&state.session.previewCurrent&&!state.error;
 const message=(text,error=false)=>{$("finishing-message").textContent=text;$("finishing-message").classList.toggle("error",error);};
 function options(input,items){input.replaceChildren(...items.map(([value,text])=>{const o=document.createElement("option");o.value=value;o.textContent=text;return o;}));}
 function sync(){for(const input of $("finishing-settings").querySelectorAll("[name]"))input.value=state.settings[input.name];}
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
 function recover(){clearTimeout(poll);poll=setTimeout(async()=>{if(!active())return;if(state.busy){recover();return;}try{await send("finishing_status");}catch(error){message(error.message,true);recover();}},2000);}
 async function send(action,payload={}){
  const requestId=`finishing-ui-${++sequence}`,version=pushVersion;
  const raw=await window.adsk.fusionSendData(action,JSON.stringify({protocol:1,requestId,...payload}));
  let r;try{r=typeof raw==="string"?JSON.parse(raw):raw;}catch(_){throw Error("Invalid Fusion response.");}
  if(!r?.ok||r.requestId!==requestId)throw Error(r?.message||r?.error||"Fusion could not complete the finishing request.");
  if(r.finishingState&&(!payload.sessionId||payload.sessionId===identity()||state.expecting)&&!(version!==pushVersion&&!state.expecting&&r.finishingState.revision<=hostRevision))apply(r.finishingState);
  return r;
 }
 function action(name,extra={}){if(!identity())throw Error("Start a finishing session first.");const p={sessionId:identity(),...extra};if(["finishing_update","finishing_preview","finishing_commit"].includes(name))Object.assign(p,{revision:state.revision,settings:clone(state.settings)});return send(name,p);}
 function run(work){queue=queue.then(async()=>{state.busy=true;render();try{await work();}catch(error){state.error=true;message(error.message,true);}finally{state.busy=false;render();if(queued){queued=false;schedule();}}});return queue;}
 const computingCurrent=()=>state.session?.phase==="computing"&&state.session.revision===state.revision;
 function schedule(){clearTimeout(timer);if(!ready()||!valid()||current()||computingCurrent()||state.session.phase==="opening")return;if(state.busy||previewFlight){queued=true;return;}timer=setTimeout(refresh,400);}
 async function refresh(){
  if(!ready()||!valid()||current()||computingCurrent())return;if(previewFlight){queued=true;return;}previewFlight=true;const rev=state.revision;
  try{await action("finishing_preview");}catch(error){state.error=true;message(error.message,true);render();}finally{previewFlight=false;if(queued||rev!==state.revision){queued=false;schedule();}}
 }
 function visible(name){const k=state.settings.kind; if(name==="edge_side")return k==="notch";if(name==="depth_mm")return k!=="stop";if(["kind","offset_x_mm","offset_y_mm"].includes(name))return true;if(name==="width_mm")return k!=="text";if(name==="length_mm")return !["notch","text"].includes(k);if(name==="height_mm")return ["text","stop"].includes(k);if(name==="shaft_mm")return k==="keyhole";if(["text","font"].includes(name))return k==="text";if(name==="mode")return ["text","arrow","scale"].includes(k);if(name==="stroke_mm")return ["arrow","scale"].includes(k);if(["count","major_every"].includes(name))return k==="scale";if(name==="rotation_deg")return k!=="notch";return true;}
 function render(){
  const k=state.settings.kind;
  $("finishing-width_mm").previousElementSibling.textContent=({notch:"Notch diameter (mm)",keyhole:"Head opening (mm)",stop:"Block width (mm)",arrow:"Arrow width (mm)",scale:"Major tick length (mm)"})[k]||D.labels.width_mm;
  $("finishing-height_mm").previousElementSibling.textContent=k==="text"?"Character height (mm)":"Stop height (mm)";
  $("finishing-length_mm").previousElementSibling.textContent=k==="keyhole"?"Total slot length (mm)":k==="scale"?"Scale span (mm)":"Length (mm)";
  const supported=state.connected&&state.caps.has("finishing-palette"),opening=state.session?.phase==="opening",computing=state.session?.phase==="computing";
  $("finishing-tool").hidden=!state.selected;$("finishing-action-dock").hidden=!state.selected;
  for(const input of $("finishing-settings").querySelectorAll("[name]")){const show=visible(input.name);input.parentElement.hidden=!show;input.disabled=!show||state.busy||opening||(input.name==="kind"&&state.session?.editing);}
  for(const group of ["placement","advanced"])$("finishing-"+group+"-group").hidden=!D.groups[group].some(visible);
  $("finishing-availability").hidden=supported;$("finishing-availability").textContent=state.connected?"Restart Partelier to enable Face details.":"Open Partelier in Fusion to apply details.";
  $("finishing-new").hidden=active();$("finishing-edit").hidden=active();$("finishing-new").disabled=!supported||state.busy||other()||!valid();$("finishing-edit").disabled=!supported||!state.caps.has("finishing-edit")||active()||state.busy||other();
  for(const role of ["face"]){const b=$("finishing-pick-"+role),picked=state.session?.selections?.[role]?.selected;b.classList.toggle("is-selected",!!picked);b.textContent="Select face"+(picked?" · ✓":"");b.disabled=!supported||state.busy||opening||computing||other()||!!state.session?.editing;}
  $("finishing-reset").disabled=!identity()||state.busy||opening;$("finishing-cancel").disabled=!identity()||state.busy||opening;
  $("finishing-create").disabled=!supported||!ready()||!current()||!valid()||state.busy;$("finishing-create").textContent=state.session?.editing?"Rebuild detail":"Create detail";
  $("finishing-retry").hidden=!ready()||current();$("finishing-retry").disabled=state.busy||opening||computing||!valid();
  $("finishing-status").textContent="Live preview · "+(!supported?"Fusion required":opening?"creating…":computing?"computing…":state.error?"needs attention":current()?"up to date":ready()?"waiting for update":"select a detail, then its face");
  $("finishing-example").innerHTML=window.PartelierFinishingArt.render(state.settings);
  $("tool-select").disabled=active()||state.busy||other();window.PartelierRefreshActions?.();
 }
 for(const [group,names] of Object.entries(D.groups))for(const name of names){
  const item=document.createElement("div");item.className="parameter-item has-parameter-help";
  const label=document.createElement("label");label.htmlFor="finishing-"+name;label.textContent=D.labels[name];
  const input=document.createElement(choices[name]?"select":"input");input.id="finishing-"+name;input.name=name;input.required=true;
  if(choices[name])options(input,choices[name]);else if(!["text","font"].includes(name)){input.type="number";input.step=["count","major_every"].includes(name)?"1":"any";[input.min,input.max]=D.bounds[name]||[0,1000];}
  const help=document.createElement("button");help.type="button";help.className="parameter-help";help.textContent="?";help.setAttribute("aria-label","Help: "+D.labels[name]);help.dataset.finishingHelp=name;
  help.addEventListener("click",()=>{helpTrigger=help;$("finishing-help-title").textContent=D.labels[name];$("finishing-help-description").textContent=D.help[name];$("finishing-help-image").innerHTML=window.PartelierFinishingArt.render(state.settings,name);$("finishing-help-dialog").showModal();});
  item.append(label,input,help);$("finishing-"+group+"-fields").append(item);
 }
 $("finishing-settings").addEventListener("submit",e=>e.preventDefault());
 $("finishing-settings").addEventListener("input",e=>{
  const input=e.target,name=input.name;if(!Object.hasOwn(defaults,name))return;
  state.settings[name]=typeof defaults[name]==="number"?Number(input.value):input.value;
  state.revision++;state.error=false;render();message(valid()?"Updating live preview…":"Check the dimensions.",!valid());schedule();
 });
 async function begin(editing){state.expecting=true;try{hostRevision=-1;await send("finishing_begin",{settings:clone(state.settings),editing});}finally{state.expecting=false;}schedule();}
 $("finishing-new").addEventListener("click",()=>run(()=>begin(false)));$("finishing-edit").addEventListener("click",()=>run(()=>begin(true)));
 for(const target of ["face"])$("finishing-pick-"+target).addEventListener("click",()=>run(async()=>{if(!identity()){await begin(false);return;}clearTimeout(timer);queued=false;await action("finishing_focus",{target});schedule();}));
 $("finishing-retry").addEventListener("click",refresh);$("finishing-create").addEventListener("click",()=>run(()=>action("finishing_commit")));
 const reset=()=>run(async()=>{clearTimeout(timer);queued=false;await action("finishing_reset");});
 $("finishing-reset").addEventListener("click",reset);$("finishing-cancel").addEventListener("click",()=>run(async()=>{clearTimeout(timer);clearTimeout(poll);queued=false;await action("finishing_cancel");}));
 $("finishing-help-close").addEventListener("click",()=>$("finishing-help-dialog").close());$("finishing-help-dialog").addEventListener("close",()=>helpTrigger?.focus());
 window.PartelierSelectionUI?.register("finishing",{active,busy:()=>state.busy,reset});
 window.PartelierFinishing=Object.freeze({matches:id=>id==="finishing",isActive:active,isBusy:()=>state.busy,
  select(id){state.selected=id==="finishing";render();},
  connect(response){state.connected=true;state.caps=new Set(response.capabilities||[]);if(response.finishingState)apply(response.finishingState);render();if(ready()&&state.session.phase==="ready")schedule();return active()?"finishing":null;},
  handle(name,raw){if(name!=="finishing_state")return false;pushVersion++;const accepted=apply(JSON.parse(raw));if(accepted&&ready()&&state.session.phase==="ready")schedule();return true;}
 });
 sync();render();
})();

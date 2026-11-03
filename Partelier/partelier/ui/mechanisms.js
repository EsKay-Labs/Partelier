"use strict";
(() => {
 const $=id=>document.getElementById(id),D=window.PartelierMechanismData,defaults=D.defaults,clone=v=>JSON.parse(JSON.stringify(v));
 const choices={family:[["slider","Straight sliding guide"],["dovetail","Dovetail sliding guide"],["bayonet","Bayonet closure"],["clevis","Clevis pivot"],["barrel","Barrel mounting hinge"],["concealed","Recessed single-axis hinge"],["pip_hinge","Captive hinge · print trial"],["pip_louver","Moving louvers · print trial"]],end_stop:[["true","Enabled"],["false","Disabled"]]};
 const terminal=new Set(["idle","cancelled","created"]),retired=new Set();
 const state={selected:false,settings:clone(defaults),session:null,revision:0,connected:false,caps:new Set(),busy:false,expecting:false,error:false};
 let sequence=0,hostRevision=-1,pushVersion=0,timer,poll,previewFlight=false,queued=false,queue=Promise.resolve(),helpTrigger;
 const active=()=>!!state.session?.sessionId&&!terminal.has(state.session.phase),identity=()=>active()?state.session.sessionId:null;
 const other=()=>!!window.PartelierHingeActive||[window.PartelierFans,window.PartelierSnap,window.PartelierPatterns,window.PartelierDetails,window.PartelierFinishing].some(m=>m?.isActive()||m?.isBusy());
 const ready=()=>!!identity()&&!state.session?.pickingTarget&&!!state.session?.selections?.surface?.selected;
 const valid=()=>$("mechanism-settings").checkValidity();
 const current=()=>active()&&state.session.phase==="preview"&&state.session.revision===state.revision&&state.session.previewCurrent&&!state.error;
 const message=(text,error=false)=>{$("mechanism-message").textContent=text;$("mechanism-message").classList.toggle("error",error);};
 function options(input,items){input.replaceChildren(...items.map(([value,text])=>{const o=document.createElement("option");o.value=value;o.textContent=text;return o;}));}
 function sync(){for(const input of $("mechanism-settings").querySelectorAll("[name]"))input.value=String(state.settings[input.name]);}
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
 function recover(){clearTimeout(poll);poll=setTimeout(async()=>{if(!active())return;if(state.busy){recover();return;}try{await send("mechanism_status");}catch(error){message(error.message,true);recover();}},2000);}
 async function send(action,payload={}){
  const requestId=`mechanism-ui-${++sequence}`,version=pushVersion;
  const raw=await window.adsk.fusionSendData(action,JSON.stringify({protocol:1,requestId,...payload}));
  let r;try{r=typeof raw==="string"?JSON.parse(raw):raw;}catch(_){throw Error("Invalid Fusion response.");}
  if(!r?.ok||r.requestId!==requestId)throw Error(r?.message||r?.error||"Fusion could not complete the mechanism request.");
  if(r.mechanismState&&(!payload.sessionId||payload.sessionId===identity()||state.expecting)&&!(version!==pushVersion&&!state.expecting&&r.mechanismState.revision<=hostRevision))apply(r.mechanismState);
  return r;
 }
 function action(name,extra={}){if(!identity())throw Error("Start a mechanism session first.");const p={sessionId:identity(),...extra};if(["mechanism_update","mechanism_preview","mechanism_commit"].includes(name))Object.assign(p,{revision:state.revision,settings:clone(state.settings)});return send(name,p);}
 function run(work){queue=queue.then(async()=>{state.busy=true;render();try{await work();}catch(error){state.error=true;message(error.message,true);}finally{state.busy=false;render();if(queued){queued=false;schedule();}}});return queue;}
 const computingCurrent=()=>state.session?.phase==="computing"&&state.session.revision===state.revision;
 function schedule(){clearTimeout(timer);if(!ready()||!valid()||current()||computingCurrent()||state.session.phase==="opening")return;if(state.busy||previewFlight){queued=true;return;}timer=setTimeout(refresh,400);}
 async function refresh(){
  if(!ready()||!valid()||current()||computingCurrent())return;if(previewFlight){queued=true;return;}previewFlight=true;const rev=state.revision;
  try{await action("mechanism_preview");}catch(error){state.error=true;message(error.message,true);render();}finally{previewFlight=false;if(queued||rev!==state.revision){queued=false;schedule();}}
 }
 function visible(name){
  const f=state.settings.family;
  if(name==="diameter_mm")return f==="bayonet";
  if(name==="pin_diameter_mm")return ["clevis","barrel","concealed","pip_hinge","pip_louver"].includes(f);
  if(name==="count")return !["slider","dovetail","clevis"].includes(f);
  if(name==="angle_deg")return ["dovetail","bayonet"].includes(f);
  if(name==="end_stop")return ["slider","dovetail"].includes(f);
  if(name==="length_mm"||name==="width_mm")return f!=="bayonet";
  return true;
 }
 function render(){
  const supported=state.connected&&state.caps.has("mechanism-palette"),opening=state.session?.phase==="opening",computing=state.session?.phase==="computing";
  const f=state.settings.family,hinge=["barrel","concealed","pip_hinge"].includes(f);
  for(const [name,label] of Object.entries({height_mm:hinge?"Barrel radius (mm)":f==="bayonet"?"Engagement height (mm)":"Height (mm)",width_mm:hinge?"Leaf reach (mm)":"Width (mm)",count:f==="bayonet"?"Lug count":f==="pip_louver"?"Vane count":"Knuckle count",pin_diameter_mm:f==="pip_louver"?"Pivot diameter (mm)":"Pin diameter (mm)",angle_deg:f==="bayonet"?"Locking turn (°)":"Dovetail angle (°)"}))$("mechanism-"+name).parentElement.querySelector("label").textContent=label;
  $("mechanism-tool").hidden=!state.selected;$("mechanism-action-dock").hidden=!state.selected;
  for(const input of $("mechanism-settings").querySelectorAll("[name]")){const show=visible(input.name);input.parentElement.hidden=!show;input.disabled=!show||state.busy||opening;}
  for(const group of ["placement"])$("mechanism-"+group+"-group").hidden=!D.groups[group].some(visible);
  $("mechanism-availability").hidden=supported;$("mechanism-availability").textContent=state.connected?"Restart Partelier to enable mechanical pairs.":"Open Partelier in Fusion to build the mating parts.";
  $("mechanism-new").hidden=active();$("mechanism-edit").hidden=active();$("mechanism-new").disabled=!supported||state.busy||other()||!valid();$("mechanism-edit").disabled=!supported||!state.caps.has("mechanism-edit")||active()||state.busy||other();
  $("mechanism-reset").disabled=!identity()||state.busy||opening;$("mechanism-cancel").disabled=!identity()||state.busy||opening;
  $("mechanism-create").disabled=!supported||!ready()||!current()||!valid()||state.busy;$("mechanism-create").textContent=state.session?.editing?"Rebuild mechanism":"Create mechanism";
  $("mechanism-retry").hidden=!ready()||current();$("mechanism-retry").disabled=state.busy||opening||computing||!valid();
  $("mechanism-status").textContent="Live preview · "+(!supported?"Fusion required":opening?"creating…":computing?"computing…":state.error?"needs attention":current()?"up to date":ready()?"waiting for update":"choose a family, then New mechanism");
  $("mechanism-example").innerHTML=window.PartelierMechanismArt.render(state.settings);
  $("tool-select").disabled=active()||state.busy||other();window.PartelierRefreshActions?.();
 }
 for(const [group,names] of Object.entries(D.groups))for(const name of names){
  const item=document.createElement("div");item.className="parameter-item has-parameter-help";
  if(name==="family")item.classList.add("full-width-parameter");
  const label=document.createElement("label");label.htmlFor="mechanism-"+name;label.textContent=D.labels[name];
  const input=document.createElement(choices[name]?"select":"input");input.id="mechanism-"+name;input.name=name;input.required=true;
  if(choices[name])options(input,choices[name]);else{input.type="number";input.step=name==="count"?"1":"any";[input.min,input.max]=D.bounds[name]||[0,1000];}
  const help=document.createElement("button");help.type="button";help.className="parameter-help";help.textContent="?";help.setAttribute("aria-label","Help: "+D.labels[name]);help.dataset.mechanismHelp=name;
  help.addEventListener("click",()=>{helpTrigger=help;$("mechanism-help-title").textContent=D.labels[name];$("mechanism-help-description").textContent=D.help[name];$("mechanism-help-image").innerHTML=window.PartelierMechanismArt.render(state.settings,name);$("mechanism-help-dialog").showModal();});
  item.append(label,input,help);$("mechanism-"+group+"-fields").append(item);
 }
 $("mechanism-settings").addEventListener("submit",e=>e.preventDefault());
 $("mechanism-settings").addEventListener("input",e=>{
  const input=e.target,name=input.name;if(!Object.hasOwn(defaults,name))return;
  state.settings[name]=typeof defaults[name]==="boolean"?input.value==="true":typeof defaults[name]==="number"?Number(input.value):input.value;
  if(name==="family")sync();
  state.revision++;state.error=false;render();message(valid()?"Updating live preview…":"Check the dimensions.",!valid());schedule();
 });
 async function begin(editing){state.expecting=true;try{hostRevision=-1;await send("mechanism_begin",{settings:clone(state.settings),editing});}finally{state.expecting=false;}schedule();}
 $("mechanism-new").addEventListener("click",()=>run(()=>begin(false)));$("mechanism-edit").addEventListener("click",()=>run(()=>begin(true)));
 $("mechanism-retry").addEventListener("click",refresh);$("mechanism-create").addEventListener("click",()=>run(()=>action("mechanism_commit")));
 const reset=()=>run(async()=>{clearTimeout(timer);queued=false;await action("mechanism_reset");});
 $("mechanism-reset").addEventListener("click",reset);$("mechanism-cancel").addEventListener("click",()=>run(async()=>{clearTimeout(timer);clearTimeout(poll);queued=false;await action("mechanism_cancel");}));
 $("mechanism-help-close").addEventListener("click",()=>$("mechanism-help-dialog").close());$("mechanism-help-dialog").addEventListener("close",()=>helpTrigger?.focus());
 window.PartelierSelectionUI?.register("mechanism",{active,busy:()=>state.busy,reset});
 window.PartelierMechanisms=Object.freeze({matches:id=>id==="mechanism",isActive:active,isBusy:()=>state.busy,
  select(id){state.selected=id==="mechanism";render();},
  connect(response){state.connected=true;state.caps=new Set(response.capabilities||[]);if(response.mechanismState)apply(response.mechanismState);render();if(ready()&&state.session.phase==="ready")schedule();return active()?"mechanism":null;},
  handle(name,raw){if(name!=="mechanism_state")return false;pushVersion++;const accepted=apply(JSON.parse(raw));if(accepted&&ready()&&state.session.phase==="ready")schedule();return true;}
 });
 sync();render();
})();

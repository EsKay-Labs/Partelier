"use strict";
(() => {
 const $=id=>document.getElementById(id),D=window.PartelierThreadData,defaults=D.defaults,clone=v=>JSON.parse(JSON.stringify(v));
 const choices={profile:[["printable_v","Printable V · recommended"],["rounded","Rounded · custom"],["metric","Metric · nominal 60°"]],mode:[["external","External · shaft"],["internal","Internal · bore"],["pair","Matched pair · two bodies"],["coupon","Fit coupon · one male + three nuts"]],handedness:[["right","Right-hand"],["left","Left-hand"]]};
 const terminal=new Set(["idle","cancelled","created"]),retired=new Set();
 const state={selected:false,settings:clone(defaults),session:null,revision:0,connected:false,caps:new Set(),busy:false,expecting:false,error:false};
 let sequence=0,hostRevision=-1,pushVersion=0,timer,poll,previewFlight=false,queued=false,queue=Promise.resolve(),helpTrigger;
 const active=()=>!!state.session?.sessionId&&!terminal.has(state.session.phase),identity=()=>active()?state.session.sessionId:null;
 const other=()=>!!window.PartelierHingeActive||[window.PartelierKnurling,window.PartelierSnap,window.PartelierPatterns,window.PartelierDetails,window.PartelierFans,window.PartelierMechanisms,window.PartelierFinishing].some(m=>m?.isActive()||m?.isBusy());
 const ready=()=>!!identity()&&!state.session?.pickingTarget&&!!state.session?.selections?.surface?.selected;
 const valid=()=>$("thread-settings").checkValidity();
 const current=()=>active()&&state.session.phase==="preview"&&state.session.revision===state.revision&&state.session.previewCurrent&&!state.error;
 const message=(text,error=false)=>{$("thread-message").textContent=text;$("thread-message").classList.toggle("error",error);};
 function options(input,items){input.replaceChildren(...items.map(([value,text])=>{const o=document.createElement("option");o.value=value;o.textContent=text;return o;}));}
 function sync(){for(const input of $("thread-settings").querySelectorAll("[name]"))input.value=state.settings[input.name];syncMetric();}
 function syncMetric(){const size=Object.entries(D.metric).find(([,v])=>v[0]===state.settings.diameter_mm&&v[1]===state.settings.pitch_mm);$("thread-metric-preset").value=state.settings.profile==="metric"&&size?size[0]:"custom";}
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
 function recover(){clearTimeout(poll);poll=setTimeout(async()=>{if(!active())return;if(state.busy){recover();return;}try{await send("thread_status");}catch(error){message(error.message,true);recover();}},2000);}
 async function send(action,payload={}){
  const requestId=`thread-ui-${++sequence}`,version=pushVersion;
  const raw=await window.adsk.fusionSendData(action,JSON.stringify({protocol:1,requestId,...payload}));
  let r;try{r=typeof raw==="string"?JSON.parse(raw):raw;}catch(_){throw Error("Invalid Fusion response.");}
  if(!r?.ok||r.requestId!==requestId)throw Error(r?.message||r?.error||"Fusion could not complete the thread request.");
  if(r.threadState&&(!payload.sessionId||payload.sessionId===identity()||state.expecting)&&!(version!==pushVersion&&!state.expecting&&r.threadState.revision<=hostRevision))apply(r.threadState);
  return r;
 }
 function action(name,extra={}){if(!identity())throw Error("Start a thread session first.");const p={sessionId:identity(),...extra};if(["thread_update","thread_preview","thread_commit"].includes(name))Object.assign(p,{revision:state.revision,settings:clone(state.settings)});return send(name,p);}
 function run(work){queue=queue.then(async()=>{state.busy=true;render();try{await work();}catch(error){state.error=true;message(error.message,true);}finally{state.busy=false;render();if(queued){queued=false;schedule();}}});return queue;}
 const computingCurrent=()=>state.session?.phase==="computing"&&state.session.revision===state.revision;
 function schedule(){clearTimeout(timer);if(!ready()||!valid()||current()||computingCurrent()||state.session.phase==="opening")return;if(state.busy||previewFlight){queued=true;return;}timer=setTimeout(refresh,400);}
 async function refresh(){
  if(!ready()||!valid()||current()||computingCurrent())return;if(previewFlight){queued=true;return;}previewFlight=true;const rev=state.revision;
  try{await action("thread_preview");}catch(error){state.error=true;message(error.message,true);render();}finally{previewFlight=false;if(queued||rev!==state.revision){queued=false;schedule();}}
 }
 function visible(name){const coupon=state.settings.mode==="coupon";if(["wall_mm","coupon_clearance_step_mm"].includes(name))return coupon;if(name==="offset_mm")return !coupon;if(name==="depth_mm")return state.settings.profile!=="metric";return true;}
 function render(){
  const supported=state.connected&&state.caps.has("thread-palette"),opening=state.session?.phase==="opening",computing=state.session?.phase==="computing",coupon=state.settings.mode==="coupon",pair=state.settings.mode==="pair";
  $("thread-tool").hidden=!state.selected;$("thread-action-dock").hidden=!state.selected;
  for(const input of $("thread-settings").querySelectorAll("[name]")){const show=visible(input.name);input.parentElement.hidden=!show;input.disabled=!show||state.busy||opening||(input.name==="mode"&&active());}
  $("thread-coupon-group").hidden=!coupon;$("thread-metric-row").hidden=state.settings.profile!=="metric";$("thread-metric-preset").disabled=state.busy||opening;
  $("thread-selection").hidden=coupon;$("thread-pick-face_b").hidden=!pair;
  $("thread-selection-note").textContent=pair?"Select the outer cylinder first, then the inner bore on the other body. Esc resets both.":state.settings.mode==="internal"?"Select the inside cylindrical wall of an existing hole. Esc resets selection.":"Select the outside cylindrical face of an existing shaft. Esc resets selection.";
  $("thread-availability").hidden=supported;$("thread-availability").textContent=state.connected?"Restart Partelier to enable Threads.":"Open Partelier in Fusion to create threads.";
  $("thread-new").hidden=active();$("thread-edit").hidden=active();$("thread-new").textContent=coupon?"New fit coupon":pair?"Select shaft → bore":"Select cylinder";
  $("thread-new").disabled=!supported||state.busy||other()||!valid();$("thread-edit").disabled=!supported||!state.caps.has("thread-edit")||active()||state.busy||other();
  const targets=pair?["face_a","face_b"]:["face_a"];
  for(const role of ["face_a","face_b"]){const b=$("thread-pick-"+role),selection=state.session?.selections?.[role],picked=selection?.selected;
   b.textContent=(role==="face_b"?"Inner bore":pair?"Outer shaft":state.settings.mode==="internal"?"Inner bore":"Outer shaft")+(picked?" · selected":" · select");
   b.classList.toggle("is-selected",!!picked);b.classList.toggle("is-next",role===(state.session?.pickingTarget||targets.find(x=>!state.session?.selections?.[x]?.selected)));
   b.disabled=!supported||state.busy||opening||computing||other()||!!state.session?.editing;
   window.PartelierSelectionUI?.decorate?.(b,targets.indexOf(role),role,state.session,targets);
  }
  $("thread-reset").hidden=coupon;$("thread-reset").disabled=!identity()||state.busy||opening;$("thread-cancel").disabled=!identity()||state.busy||opening;
  $("thread-create").disabled=!supported||!ready()||!current()||!valid()||state.busy;$("thread-create").textContent=state.session?.editing?"Rebuild thread":coupon?"Create fit coupon":"Create thread";
  $("thread-retry").hidden=!ready()||current();$("thread-retry").disabled=state.busy||opening||computing||!valid();
  $("thread-status").textContent="Live preview · "+(!supported?"Fusion required":opening?"creating…":computing?"computing…":state.error?"needs attention":current()?"up to date":ready()?"waiting for update":coupon?"choose settings, then New fit coupon":"select cylindrical faces");
  $("thread-fit-note").textContent=coupon?"One male + three nuts: "+[-1,0,1].map(i=>(state.settings.clearance_mm+i*state.settings.coupon_clearance_step_mm).toFixed(2)).join(" / ")+" mm per side. Nuts have 1 / 2 / 3 raised outer marks, respectively.":state.settings.mode==="external"?"Male reduced by "+state.settings.clearance_mm.toFixed(2)+" mm per side ("+(state.settings.clearance_mm*2).toFixed(2)+" mm diametral allowance).":"Female enlarged by "+state.settings.clearance_mm.toFixed(2)+" mm per side ("+(state.settings.clearance_mm*2).toFixed(2)+" mm diametral allowance).";
  $("thread-example").innerHTML=window.PartelierThreadArt.render(state.settings,coupon?"mode":"profile");
  $("tool-select").disabled=active()||state.busy||other();window.PartelierRefreshActions?.();
 }

 for(const [group,names] of Object.entries(D.groups))for(const name of names){
  const item=document.createElement("div");item.className="parameter-item has-parameter-help";if(["mode","profile"].includes(name))item.classList.add("full-width-parameter");
  const label=document.createElement("label");label.htmlFor="thread-"+name;label.textContent=D.labels[name];
  const input=document.createElement(choices[name]?"select":"input");input.id="thread-"+name;input.name=name;input.required=true;
  if(choices[name])options(input,choices[name]);else {input.type="number";input.step=name==="starts"?"1":"any";[input.min,input.max]=D.bounds[name]||[0,1000];}
  const help=document.createElement("button");help.type="button";help.className="parameter-help";help.textContent="?";help.setAttribute("aria-label","Help: "+D.labels[name]);help.dataset.threadHelp=name;
  help.addEventListener("click",()=>{helpTrigger=help;$("thread-help-title").textContent=D.labels[name];$("thread-help-description").textContent=D.help[name];$("thread-help-image").innerHTML=window.PartelierThreadArt.render(state.settings,name);$("thread-help-dialog").showModal();});
  item.append(label,input,help);$("thread-"+group+"-fields").append(item);
 }
 $("thread-settings").addEventListener("submit",e=>e.preventDefault());
 function changed(){state.revision++;state.error=false;render();message(!valid()?"Check the dimensions.":active()?"Updating live preview…":"Choose settings, then start.",!valid());schedule();}
 $("thread-settings").addEventListener("input",e=>{
  const input=e.target,name=input.name;if(!Object.hasOwn(defaults,name))return;
  state.settings[name]=typeof defaults[name]==="number"?Number(input.value):input.value;
  if(name==="profile"&&state.settings.profile==="metric"){state.settings.depth_mm=0;$("thread-depth_mm").value=0;}
  if(name==="mode"&&state.settings.mode==="coupon"){state.settings.length_mm=6;$("thread-length_mm").value=6;}
  syncMetric();changed();
 });
 options($("thread-metric-preset"),[["custom","Custom nominal size"],...Object.entries(D.metric).map(([key,v])=>[key,key+" × "+v[1]])]);
 $("thread-metric-preset").addEventListener("change",()=>{const values=D.metric[$("thread-metric-preset").value];if(!values)return;state.settings.profile="metric";state.settings.diameter_mm=values[0];state.settings.pitch_mm=values[1];state.settings.depth_mm=0;sync();changed();});

 async function begin(editing){state.expecting=true;try{hostRevision=-1;await send("thread_begin",{settings:clone(state.settings),editing});}finally{state.expecting=false;}schedule();}
 $("thread-new").addEventListener("click",()=>run(()=>begin(false)));$("thread-edit").addEventListener("click",()=>run(()=>begin(true)));
 for(const target of ["face_a","face_b"])$("thread-pick-"+target).addEventListener("click",()=>run(async()=>{if(!identity()){await begin(false);return;}clearTimeout(timer);queued=false;await action("thread_focus",{target});schedule();}));
 $("thread-retry").addEventListener("click",refresh);$("thread-create").addEventListener("click",()=>run(()=>action("thread_commit")));
 const reset=()=>run(async()=>{clearTimeout(timer);queued=false;await action("thread_reset");});
 $("thread-reset").addEventListener("click",reset);$("thread-cancel").addEventListener("click",()=>run(async()=>{clearTimeout(timer);clearTimeout(poll);queued=false;await action("thread_cancel");}));
 $("thread-help-close").addEventListener("click",()=>$("thread-help-dialog").close());$("thread-help-dialog").addEventListener("close",()=>helpTrigger?.focus());
 window.PartelierSelectionUI?.register("thread",{active,busy:()=>state.busy,reset});
 window.PartelierThreads=Object.freeze({matches:id=>id==="thread",isActive:active,isBusy:()=>state.busy,
  select(id){state.selected=id==="thread";render();},
  connect(response){state.connected=true;state.caps=new Set(response.capabilities||[]);if(!active()&&response.threadDefaults){state.settings=clone(response.threadDefaults);sync();}if(response.threadState)apply(response.threadState);render();if(ready()&&state.session.phase==="ready")schedule();return active()?"thread":null;},
  handle(name,raw){if(name!=="thread_state")return false;pushVersion++;const accepted=apply(JSON.parse(raw));if(accepted&&ready()&&state.session.phase==="ready")schedule();return true;}
 });
 sync();render();
})();

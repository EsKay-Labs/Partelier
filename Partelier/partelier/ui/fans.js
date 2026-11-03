"use strict";
(() => {
 const $=id=>document.getElementById(id),D=window.PartelierFanData,defaults=D.defaults,clone=v=>JSON.parse(JSON.stringify(v));
 const styles=[["axial","PC axial"],["wide","Wide blade"],["slim","Slim rotor"],["ring","Tip-ring rotor"],["prop2","2-blade propeller"],["prop3","3-blade propeller"],["prop4","4-blade propeller"],["blower","Radial blower impeller"]];
 const choices={style:styles,volute_mounts:[[true,"On · 4 bosses"],[false,"Off"]],output:[["blower_housing","Rotor + volute + lid"],["rotor","Rotor only"],["rotor_frame","Rotor + frame"],["rotor_guard","Rotor + frame + guard"],["hub_test","Hub fit coupon"]],shaft_shape:[["round","Round"],["d","D-shaft"]],pitch_mode:[["twist","Root / middle / tip angles"],["pitch","Constant geometric pitch"]],rotation:[["ccw","CCW · viewed from above"],["cw","CW · viewed from above"]],outline_mode:[["generated","Generated planform"],["sketch","Selected sketch profile"]]};
 const terminal=new Set(["idle","cancelled","created"]),retired=new Set();
 const state={selected:false,settings:clone(defaults),session:null,revision:0,connected:false,caps:new Set(),busy:false,expecting:false,error:false};
 let sequence=0,hostRevision=-1,pushVersion=0,timer,poll,previewFlight=false,queued=false,queue=Promise.resolve(),helpTrigger;
 const active=()=>!!state.session?.sessionId&&!terminal.has(state.session.phase),identity=()=>active()?state.session.sessionId:null;
 const other=()=>!!window.PartelierMechanisms?.isActive()||!!window.PartelierMechanisms?.isBusy()||!!window.PartelierFinishing?.isActive()||!!window.PartelierFinishing?.isBusy()||!!window.PartelierHingeActive||[window.PartelierSnap,window.PartelierPatterns,window.PartelierDetails].some(m=>m?.isActive()||m?.isBusy());
 const ready=()=>!!identity()&&!state.session?.pickingTarget&&!!state.session?.selections?.surface?.selected;
 const valid=()=>$("fan-settings").checkValidity();
 const current=()=>active()&&state.session.phase==="preview"&&state.session.revision===state.revision&&state.session.previewCurrent&&!state.error;
 const message=(text,error=false)=>{$("fan-message").textContent=text;$("fan-message").classList.toggle("error",error);};
 function options(input,items){input.replaceChildren(...items.map(([value,text])=>{const o=document.createElement("option");o.value=value;o.textContent=text;return o;}));}
 function sync(){
  options($("fan-output"),choices.output.filter(([key])=>state.settings.style==="blower"?["rotor","hub_test","blower_housing"].includes(key):key!=="blower_housing"));
  options($("fan-size_preset"),[["custom","Custom"],...Object.keys(state.settings.style.startsWith("prop")?D.propSizes:D.pcSizes).map(k=>[k,k.startsWith("pc")?k.slice(2)+" mm PC frame":({prop5030:'5 × 3 in',prop6040:'6 × 4 in',prop8040:'8 × 4 in',prop1045:'10 × 4.5 in'})[k]])]);
  for(const input of $("fan-settings").querySelectorAll("[name]"))input.value=state.settings[input.name];
 }
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
 function recover(){clearTimeout(poll);poll=setTimeout(async()=>{if(!active())return;if(state.busy){recover();return;}try{await send("fan_status");}catch(error){message(error.message,true);recover();}},2000);}
 async function send(action,payload={}){
  const requestId=`fan-ui-${++sequence}`,version=pushVersion;
  const raw=await window.adsk.fusionSendData(action,JSON.stringify({protocol:1,requestId,...payload}));
  let r;try{r=typeof raw==="string"?JSON.parse(raw):raw;}catch(_){throw Error("Invalid Fusion response.");}
  if(!r?.ok||r.requestId!==requestId)throw Error(r?.message||r?.error||"Fusion could not complete the fan request.");
  if(r.fanState&&(!payload.sessionId||payload.sessionId===identity()||state.expecting)&&!(version!==pushVersion&&!state.expecting&&r.fanState.revision<=hostRevision))apply(r.fanState);
  return r;
 }
 function action(name,extra={}){if(!identity())throw Error("Start a fan session first.");const p={sessionId:identity(),...extra};if(["fan_update","fan_preview","fan_commit"].includes(name))Object.assign(p,{revision:state.revision,settings:clone(state.settings)});return send(name,p);}
 function run(work){queue=queue.then(async()=>{state.busy=true;render();try{await work();}catch(error){state.error=true;message(error.message,true);}finally{state.busy=false;render();if(queued){queued=false;schedule();}}});return queue;}
 const computingCurrent=()=>state.session?.phase==="computing"&&state.session.revision===state.revision;
 function schedule(){clearTimeout(timer);if(!ready()||!valid()||current()||computingCurrent()||state.session.phase==="opening")return;if(state.busy||previewFlight){queued=true;return;}timer=setTimeout(refresh,400);}
 async function refresh(){
  if(!ready()||!valid()||current()||computingCurrent())return;if(previewFlight){queued=true;return;}previewFlight=true;const rev=state.revision;
  try{await action("fan_preview");}catch(error){state.error=true;message(error.message,true);render();}finally{previewFlight=false;if(queued||rev!==state.revision){queued=false;schedule();}}
 }
 function visible(name){
  const s=state.settings,coupon=s.output==="hub_test";
  if(name.startsWith("volute_"))return s.style==="blower"&&s.output==="blower_housing";
  if(s.style==="blower"&&D.groups.frame.includes(name))return name==="tip_gap_mm"?!coupon:s.output==="blower_housing"&&(["axial_clearance_mm"].includes(name)||name==="mount_hole_mm"&&s.volute_mounts);
  if(name.startsWith("blower_"))return s.style==="blower"&&!coupon;
  if(s.style==="blower"&&D.groups.blade.includes(name))return false;
  if(coupon&&D.groups.blade.includes(name))return false;
  if(coupon&&["diameter_mm","blade_count"].includes(name))return false;
  if(name.startsWith("ring_"))return s.style==="ring"&&!coupon;
  if(name==="pitch_mm")return s.pitch_mode==="pitch"&&!coupon;
  if(name.endsWith("angle_deg"))return s.pitch_mode==="twist"&&!coupon;
  if(name.endsWith("chord_mm"))return s.outline_mode==="generated"&&!coupon;
  if(name==="outline_scale_percent")return s.outline_mode==="sketch"&&!coupon;
  if(name==="shaft_flat_mm")return s.shaft_shape==="d";
  if(D.groups.frame.includes(name))return name==="tip_gap_mm"?!coupon:(s.output==="rotor_frame"||s.output==="rotor_guard")&&(!name.startsWith("guard_")||s.output==="rotor_guard");
  return true;
 }
 function render(){
  const supported=state.connected&&state.caps.has("fan-palette"),opening=state.session?.phase==="opening",computing=state.session?.phase==="computing";
  $("fan-tool").hidden=!state.selected;$("fan-action-dock").hidden=!state.selected;
  for(const input of $("fan-settings").querySelectorAll("[name]")){const show=visible(input.name);input.parentElement.hidden=!show;input.disabled=!show||state.busy||opening||(input.name==="diameter_mm"&&!!state.session?.selections?.circle?.selected);}
  for(const group of ["blade","hub","frame"])$("fan-"+group+"-group").hidden=!D.groups[group].some(visible);
  $("fan-availability").hidden=supported;$("fan-availability").textContent=state.connected?"Restart Partelier to enable Fans & Propellers.":"Open Partelier in Fusion to build the rotor.";
  $("fan-new").hidden=active();$("fan-edit").hidden=active();$("fan-new").disabled=!supported||state.busy||other()||!valid();$("fan-edit").disabled=!supported||!state.caps.has("fan-edit")||active()||state.busy||other();
  for(const role of ["circle","outline"]){const b=$("fan-pick-"+role),picked=state.session?.selections?.[role]?.selected;b.classList.toggle("is-selected",!!picked);b.textContent=(role==="circle"?"Fit circular opening":"Use sketch outline")+(picked?" · ✓":"");b.disabled=!supported||state.busy||opening||computing||other()||(role==="outline"&&state.settings.style==="blower");}
  $("fan-reset").disabled=!identity()||state.busy||opening;$("fan-cancel").disabled=!identity()||state.busy||opening;
  $("fan-create").disabled=!supported||!ready()||!current()||!valid()||state.busy;$("fan-create").textContent=state.session?.editing?"Rebuild fan":"Create fan";
  $("fan-retry").hidden=!ready()||current();$("fan-retry").disabled=state.busy||opening||computing||!valid();
  $("fan-status").textContent="Live preview · "+(!supported?"Fusion required":opening?"creating…":computing?"computing…":state.error?"needs attention":current()?"up to date":ready()?"waiting for update":"choose preset, then New fan");
  $("fan-example").innerHTML=window.PartelierFanArt.render(state.settings);
  $("tool-select").disabled=active()||state.busy||other();window.PartelierRefreshActions?.();
 }
 for(const [group,names] of Object.entries(D.groups))for(const name of names){
  const item=document.createElement("div");item.className="parameter-item has-parameter-help";
  const label=document.createElement("label");label.htmlFor="fan-"+name;label.textContent=D.labels[name];
  const input=document.createElement(choices[name]||name==="size_preset"?"select":"input");input.id="fan-"+name;input.name=name;input.required=true;
  if(choices[name])options(input,choices[name]);else if(name!=="size_preset"){input.type="number";input.step=["blade_count","guard_spokes"].includes(name)?"1":"any";[input.min,input.max]=D.bounds[name]||[0,1000];}
  const help=document.createElement("button");help.type="button";help.className="parameter-help";help.textContent="?";help.setAttribute("aria-label","Help: "+D.labels[name]);help.dataset.fanHelp=name;
  help.addEventListener("click",()=>{helpTrigger=help;$("fan-help-title").textContent=D.labels[name];$("fan-help-description").textContent=D.help[name];$("fan-help-image").innerHTML=window.PartelierFanArt.render(state.settings,name);$("fan-help-dialog").showModal();});
  item.append(label,input,help);$("fan-"+group+"-fields").append(item);
 }
 $("fan-settings").addEventListener("submit",e=>e.preventDefault());
 $("fan-settings").addEventListener("input",e=>{
  const input=e.target,name=input.name;if(!Object.hasOwn(defaults,name))return;
  state.settings[name]=typeof defaults[name]==="number"?Number(input.value):typeof defaults[name]==="boolean"?input.value==="true":input.value;
  if(name==="style"||name==="size_preset"){
   const prop=state.settings.style.startsWith("prop");let size=state.settings.size_preset;
   if(name==="style"&&size==="custom")size=prop?"prop5030":"pc120";
   if(size!=="custom"&&!Object.hasOwn(prop?D.propSizes:D.pcSizes,size))size=prop?"prop5030":"pc120";
   if(size!=="custom")state.settings=clone(D.presets[state.settings.style+":"+size]);
   sync();
  }else{state.settings.size_preset="custom";$("fan-size_preset").value="custom";}
  state.revision++;state.error=false;render();message(valid()?"Updating live preview…":"Check the dimensions.",!valid());schedule();
 });
 async function begin(editing){state.expecting=true;try{hostRevision=-1;await send("fan_begin",{settings:clone(state.settings),editing});}finally{state.expecting=false;}schedule();}
 $("fan-new").addEventListener("click",()=>run(()=>begin(false)));$("fan-edit").addEventListener("click",()=>run(()=>begin(true)));
 for(const target of ["circle","outline"])$("fan-pick-"+target).addEventListener("click",()=>run(async()=>{if(!identity())await begin(false);clearTimeout(timer);queued=false;await action("fan_focus",{target});schedule();}));
 $("fan-retry").addEventListener("click",refresh);$("fan-create").addEventListener("click",()=>run(()=>action("fan_commit")));
 const reset=()=>run(async()=>{clearTimeout(timer);queued=false;await action("fan_reset");});
 $("fan-reset").addEventListener("click",reset);$("fan-cancel").addEventListener("click",()=>run(async()=>{clearTimeout(timer);clearTimeout(poll);queued=false;await action("fan_cancel");}));
 $("fan-help-close").addEventListener("click",()=>$("fan-help-dialog").close());$("fan-help-dialog").addEventListener("close",()=>helpTrigger?.focus());
 window.PartelierSelectionUI?.register("fan",{active,busy:()=>state.busy,reset});
 window.PartelierFans=Object.freeze({matches:id=>id==="fan",isActive:active,isBusy:()=>state.busy,
  select(id){state.selected=id==="fan";render();},
  connect(response){state.connected=true;state.caps=new Set(response.capabilities||[]);if(response.fanState)apply(response.fanState);render();if(ready()&&state.session.phase==="ready")schedule();return active()?"fan":null;},
  handle(name,raw){if(name!=="fan_state")return false;pushVersion++;const accepted=apply(JSON.parse(raw));if(accepted&&ready()&&state.session.phase==="ready")schedule();return true;}
 });
 sync();render();
})();

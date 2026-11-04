"use strict";

// Small details share one typed session; the selected helper owns its geometry.
(() => {
 const $=id=>document.getElementById(id),terminal=new Set(["idle","created","cancelled"]),retired=new Set();
 const defaults={kind:"lid",lip_layout:"closed",lip_sides:15,lip_height_mm:2.5,lip_width_mm:1.2,lip_inset_mm:.8,lip_clearance_mm:.25,axial_clearance_mm:.3,lead_mm:.2,pin_diameter_mm:2.5,pin_height_mm:4,pin_clearance_mm:.3,pin_inset_mm:0,pin_count:2,socket_floor_mm:.5,rib_width_mm:2,rib_height_a_mm:12,rib_height_b_mm:12,rib_count:3,rib_margin_mm:5,rib_style:"triangle"};
 const titles={lid:"Lid lip & groove",alignment:"Alignment pins",ribs:"Ribs & gussets"};
 const fields={
  lip_layout:["Lip layout","Continuous perimeter: χείλος και αυλάκι σε ορθογώνιο, κύκλο ή κλειστό επίπεδο περίγραμμα με ευθείες/καμπύλες (έως 64 ακμές). Τα offsets πρέπει να παραμένουν ενιαία χωρίς να διασταυρώνονται. Selected sides (μόνο ορθογώνιο): επίλεξε τις πλευρές πάνω στο μοντέλο και πάτησε Done. Το χείλος και το ταιριαστό αυλάκι δημιουργούνται μόνο εκεί."],
  lip_height_mm:["Lip height (mm)","Ύψος του χείλους από το face A προς το καπάκι. Πρέπει να ξεπερνά το κενό ανάμεσα στα δύο faces τουλάχιστον κατά 0.2 mm."],
  lip_width_mm:["Lip width (mm)","Πλάτος του συνεχόμενου χείλους, κάθετα στο περίγραμμα. Η βάση του πρέπει να πατάει ολόκληρη στο υλικό του A."],
  lip_inset_mm:["Edge inset (mm)","Απόσταση από την εξωτερική περίμετρο του A μέχρι την εξωτερική πλευρά του χείλους. Πρέπει να χωρά και το περιθώριο του αυλακιού."],
  lip_clearance_mm:["Side clearance (mm)","Πλευρικό κενό σε κάθε πλευρά του χείλους μέσα στο αυλάκι. Δεν αλλάζει το μέγεθος της αρχικής περιμέτρου."],
  axial_clearance_mm:["End clearance (mm)","Επιπλέον βάθος στο αυλάκι ή στην οπή, πέρα από την άκρη του χείλους/πείρου, ώστε να μη βρίσκει στον πάτο."],
  lead_mm:["45° lead-in (mm)","Λοξότμηση στην άκρη του χείλους ή πείρου. Στους πείρους ανοίγει και την είσοδο της υποδοχής. 0 = χωρίς λοξότμηση."],
  pin_diameter_mm:["Pin diameter (mm)","Πραγματική διάμετρος των πείρων. Η οπή στο B είναι μεγαλύτερη κατά Hole allowance. Δεν δημιουργείται ξεχωριστό pin body."],
  pin_height_mm:["Pin height (mm)","Ύψος από το face A προς το B. Το κενό ανάμεσα στα faces αφαιρείται πριν υπολογιστεί το βάθος εμπλοκής."],
  pin_clearance_mm:["Hole allowance · Ø (mm)","Προστίθεται στη διάμετρο, όχι στην ακτίνα. Πείρος 2.5 mm + allowance 0.3 mm δημιουργεί οπή Ø2.8 mm."],
  pin_inset_mm:["Edge to centre · 0 = Auto", "Απόσταση των κέντρων από τις γωνίες του ορθογωνίου. Auto κρατά χώρο για την οπή, τη λοξότμηση εισόδου και 0.5 mm επιπλέον προς τα έξω. Η βάση χρειάζεται πλήρες υλικό."],
  pin_count:["Pins","Δύο πείροι σε απέναντι διαγώνιες γωνίες ή τέσσερις, ένας σε κάθε γωνία. Οι αντίστοιχες οπές δημιουργούνται μαζί στο B."],
  socket_floor_mm:["Keep floor (mm)","Ελάχιστο συμπαγές υλικό πίσω από την υποδοχή. Το εργαλείο αρνείται το preview αν το αυλάκι ή οι οπές βγαίνουν από την άλλη πλευρά."],
  rib_width_mm:["Thickness (mm)","Πάχος κάθε νεύρωσης κατά μήκος της κοινής ακμής. Οι νευρώσεις ενώνονται στο υπάρχον σώμα, χωρίς νέα τελικά bodies."],
  rib_height_a_mm:["Width · face B (mm)","Η προέκταση από τον τοίχο A πάνω στην επιφάνεια B. Το πλήρες σκέλος πρέπει να έχει υποστήριξη."],
  rib_height_b_mm:["Height · face A (mm)","Ύψος από την επιφάνεια B κατά μήκος του τοίχου A. Δεν επιτρέπεται νεύρωση που πατάει μόνο στην κορυφή της γωνίας."],
  rib_count:["Ribs","Πλήθος από 1 έως 32. Μία νεύρωση μπαίνει στο κέντρο. Οι υπόλοιπες ισομοιράζονται, με τα ίδια περιθώρια στις άκρες."],
  rib_margin_mm:["End margin (mm)","Απόσταση από κάθε άκρη της κοινής ακμής μέχρι την εξωτερική πλευρά της πρώτης/τελευταίας νεύρωσης. Για μία νεύρωση είναι ελάχιστο: η νεύρωση μένει στο κέντρο."],
  rib_style:["Rib style","Triangular gusset: τριγωνική ενίσχυση γωνίας. Full rib: ορθογώνια νεύρωση με το ίδιο πάχος, ύψος και προέκταση."]
 };
 const groups={lid:["lip_layout","lip_height_mm","lip_width_mm","lip_inset_mm","lip_clearance_mm","lead_mm","axial_clearance_mm","socket_floor_mm"],alignment:["pin_count","pin_diameter_mm","pin_height_mm","pin_clearance_mm","pin_inset_mm","lead_mm","axial_clearance_mm","socket_floor_mm"],ribs:["rib_style","rib_width_mm","rib_height_a_mm","rib_height_b_mm","rib_count","rib_margin_mm"]};
 const state={selected:false,alias:null,settings:{...defaults},session:null,revision:0,connected:false,caps:new Set(),busy:false,expecting:false,error:false};
 let sequence=0,hostRevision=-1,timer,poll,previewFlight=false,queued=false,queue=Promise.resolve(),helpTrigger,exampleKind;
 const active=()=>!!state.session?.sessionId&&!terminal.has(state.session.phase),identity=()=>active()?state.session.sessionId:null;
 const other=()=>!!window.PartelierThreads?.isActive()||!!window.PartelierThreads?.isBusy()||!!window.PartelierMechanisms?.isActive()||!!window.PartelierMechanisms?.isBusy()||!!window.PartelierFinishing?.isActive()||!!window.PartelierFinishing?.isBusy()||!!window.PartelierFans?.isActive()||!!window.PartelierFans?.isBusy()||!!window.PartelierHingeActive||!!window.PartelierSnap?.isActive()||!!window.PartelierSnap?.isBusy()||!!window.PartelierPatterns?.isActive()||!!window.PartelierPatterns?.isBusy();
 const ready=()=>!state.session?.pickingSides&&!state.session?.pickingTarget&&!!identity()&&!!state.session?.selections?.surface?.selected;
 const valid=()=>$("detail-settings").checkValidity();
 const current=()=>active()&&state.session.phase==="preview"&&state.session.revision===state.revision&&state.session.previewCurrent&&!state.error;
 const message=(text,error=false)=>{$("detail-message").textContent=text;$("detail-message").classList.toggle("error",error);};
 const clone=value=>JSON.parse(JSON.stringify(value));
 function sync(){for(const input of $("detail-settings").querySelectorAll("[name]")){input.value=state.settings[input.name];input.setCustomValidity("");}}
 function apply(snapshot){
  if(!snapshot||typeof snapshot!=="object"||!Number.isInteger(snapshot.revision)||!snapshot.phase)return false;
  const old=state.session?.sessionId,id=snapshot.sessionId,ended=snapshot.endedSessionId;
  if(id&&retired.has(id)||ended&&active()&&ended!==old)return false;
  if(active()&&id&&id!==old&&!state.expecting)return false;
  if(id===old&&snapshot.revision<hostRevision)return false;
  if(old&&(id!==old||terminal.has(snapshot.phase)))retired.add(old);
  state.session=snapshot;hostRevision=snapshot.revision;
  if(snapshot.settings&&(snapshot.revision>=state.revision||state.expecting||(id&&id!==old))){
   state.settings={...defaults,...snapshot.settings};state.revision=snapshot.revision;sync();
  }
  state.error=snapshot.phase==="error";
  message(snapshot.message||"",state.error);render();
  if(snapshot.phase==="computing"||snapshot.phase==="opening")recover();
  return true;
 }
 function recover(){
  clearTimeout(poll);poll=setTimeout(async()=>{
   if(!active()||state.busy)return;
   try{await send("detail_status");}catch(error){message(error.message,true);recover();}
  },2000);
 }
 async function send(action,payload={}){
  const requestId=`detail-ui-${++sequence}`,sentId=payload.sessionId;
  const raw=await window.adsk.fusionSendData(action,JSON.stringify({protocol:1,requestId,...payload}));
  let response;try{response=typeof raw==="string"?JSON.parse(raw):raw;}catch(_){throw Error("The Fusion response is invalid.");}
  if(!response?.ok)throw Error(response?.message||response?.error||"Fusion could not complete the detail request.");
  if(response.requestId!==requestId)throw Error("The detail acknowledgment belongs to another request.");
  if(response.detailState&&(!sentId||sentId===identity()||state.expecting))apply(response.detailState);
  return response;
 }
 function action(actionName,extra={}){
  if(!identity())throw Error("Start the detail session first.");
  const payload={sessionId:identity(),...extra};
  if(["detail_update","detail_preview","detail_commit"].includes(actionName))Object.assign(payload,{revision:state.revision,settings:clone(state.settings)});
  return send(actionName,payload);
 }
 function run(work){queue=queue.then(async()=>{state.busy=true;render();try{await work();}catch(error){state.error=true;message(error.message,true);}finally{state.busy=false;render();if(queued){queued=false;schedule();}}});return queue;}
 function schedule(){
  clearTimeout(timer);
  if(!ready()||!valid()||current()||state.session.phase==="opening")return;
  if(state.busy||previewFlight){queued=true;return;}
  timer=setTimeout(()=>{timer=undefined;refresh();},160);
 }
 async function refresh(){
  if(!ready()||!valid()||current())return;
  if(previewFlight){queued=true;return;}
  previewFlight=true;const revision=state.revision;
  try{await action("detail_preview");}catch(error){state.error=true;message(error.message,true);render();}
  finally{previewFlight=false;if(queued||revision!==state.revision){queued=false;schedule();}}
 }
 function render(){
  const kind=state.settings.kind,pickingSides=!!state.session?.pickingSides,opening=state.session?.phase==="opening",supported=state.connected&&state.caps.has("detail-palette");
  $("detail-tool").hidden=!state.selected;$("detail-action-dock").hidden=!state.selected;
  for(const input of $("detail-settings").querySelectorAll("[name]")){
   const show=groups[kind].includes(input.name);input.parentElement.hidden=!show;input.disabled=!show||opening||state.busy||pickingSides;
  }
  const lead=$("detail-lead_mm"),s=state.settings;
  lead.setCustomValidity(kind==="lid"&&(s.lead_mm*2>=s.lip_width_mm||s.lead_mm>=s.lip_height_mm)?"Lead-in must be smaller than half the lip width and its height.":kind==="alignment"&&(s.lead_mm>=s.pin_diameter_mm/2||s.lead_mm>=s.pin_height_mm)?"Lead-in must be smaller than the pin radius and height.":"");
  const labels=kind==="ribs"?[["face_a","Wall face A"],["face_b","Floor face B"]]:[["face_a","Base face A"],["face_b","Lid inside face B"]];
  const targets=state.session?.editing?[["edit_target","Existing detail"]]:labels;
  if(kind==="lid"&&state.settings.lip_layout==="selected")targets.push(["lip_sides","Lip sides"]);
  $("detail-selections").replaceChildren(...targets.map(([target,caption])=>{
   const button=document.createElement("button");button.type="button";button.id="detail-pick-"+target;button.className="selection-button";
   const picked=active()?state.session?.selections?.[target]:null;button.textContent=`${caption} · ${target==="lip_sides"&&pickingSides?(picked?.label||"Click edges in Fusion"):target===state.session?.pickingTarget?"Select in Fusion now":picked?.selected?"✓ "+(picked.label||"Selected"):"Click to select"}`;
   button.classList.toggle("is-selected",!!picked?.selected);button.disabled=!supported||state.busy||opening||pickingSides||(target==="lip_sides"&&!identity());
   window.PartelierSelectionUI?.decorate(button,targets.findIndex(([name])=>name===target),target,state.session,targets.map(([name])=>name));
   button.addEventListener("click",()=>run(async()=>{if(!identity())await begin(false);else await action("detail_focus",{target});schedule();}));return button;
  }));
  if(pickingSides){
   const controls=document.createElement("div");controls.className="detail-side-actions";
   for(const [id,caption,actionName] of [["detail-done-sides","Done · update preview","detail_finish_sides"],["detail-clear-sides","Clear sides","detail_clear_sides"]]){
    const button=document.createElement("button");button.id=id;button.type="button";button.textContent=caption;
    button.className=id==="detail-done-sides"?"create-button":"secondary-button";
    button.disabled=state.busy||(id==="detail-done-sides"&&!state.session.canFinishSides);
    button.addEventListener("click",()=>run(async()=>{await action(actionName);schedule();}));controls.append(button);
   }
   $("detail-selections").append(controls);
  }
  window.PartelierWorkspace?.update("detail",state.session);
  $("detail-selection-help").textContent=pickingSides?"Click the straight outer edges for the lip. Selections stay blue. Done starts preview; Clear or Esc starts the sides over.":state.session?.editing?(kind==="lid"&&state.settings.lip_layout==="selected"?"Saved sides loaded. Lip sides changes the selection; dimensions update the matching lip and groove.":"Saved operation loaded. Change dimensions, then Rebuild detail. Reset clears only this temporary selection."):kind==="ribs"?"1 · Inside wall A → 2 · Floor B. One body, inside corner 90°. Next step opens automatically. Esc resets selections.":(kind==="lid"&&state.settings.lip_layout==="selected"?"1 · Base rim A → 2 · Lid underside B → 3 · Lip sides → Done. Preview waits until Done.":"1 · Base rim A → 2 · Lid underside B. Two bodies, facing each other. Next step opens automatically. Esc resets selections.");
  window.PartelierSelectionUI?.resetControl($("detail-selections"),"detail",!!identity()&&!state.busy);
  $("detail-availability").hidden=supported;$("detail-availability").textContent=state.connected?"Stop and Run Partelier to enable Small details.":"Open Partelier in Fusion to select geometry.";
  $("begin-detail-button").hidden=active();$("begin-detail-button").disabled=!supported||!valid()||state.busy||active()||other();
  $("edit-detail-button").disabled=!supported||!state.caps.has("detail-edit")||state.busy||active()||other();
  $("cancel-detail-button").disabled=!identity()||state.busy||opening;
  $("create-detail-button").disabled=!supported||!ready()||!current()||!valid()||state.busy||opening;
  $("create-detail-button").textContent=state.session?.editing?"Rebuild detail":"Create detail";
  $("retry-detail-button").hidden=!ready()||current();$("retry-detail-button").disabled=!valid()||state.busy||opening;
  $("detail-status").textContent=`Live preview · ${pickingSides?"choose sides, then Done":!supported?"Fusion required":!valid()?"check inputs":opening?"creating":state.session?.phase==="computing"?"updating…":state.error?"needs attention":current()?"up to date":ready()?"waiting for update":"select supports"}`;
  if(exampleKind!==kind){$("detail-example").innerHTML=window.PartelierDetailExamples?.render(kind)||window.PartelierIllustrations.render(kind);exampleKind=kind;}
  $("tool-select").disabled=active()||state.busy||other();window.PartelierRefreshActions?.();
 }
 function helpArt(name){
  const s=state.settings,ribs=s.kind==="ribs",value=typeof s[name]==="number"?(Number.isFinite(s[name])?s[name]:"—"):s[name];
  const arrow=(x,y,u,v)=>`<path d="M${x} ${y}L${u} ${v}" stroke="#bd501c" stroke-width="2" marker-start="url(#detail-arrow)" marker-end="url(#detail-arrow)"/>`;
  let geometry,dimension;
  if(name==="lip_layout"){
   return `<svg viewBox="0 0 320 180" role="img" aria-label="Continuous lip and selected-side lip examples"><g fill="none" stroke="#355f8d" stroke-width="9"><rect x="26" y="28" width="104" height="96"/><path d="M190 124V28H294"/></g><g font-size="12" fill="#303d4e" text-anchor="middle"><text x="78" y="152">Continuous perimeter</text><text x="242" y="152">Selected sides · 2</text></g></svg>`;
  }
  if(ribs){
   const row=["rib_width_mm","rib_count","rib_margin_mm"].includes(name),n=Math.min(6,s.rib_count),step=228/Math.max(1,n-1);
   geometry=row?`<rect x="20" y="125" width="280" height="20" fill="#dbe7f8" stroke="#365f88"/>${Array.from({length:n},(_,i)=>`<rect x="${40+i*step}" y="55" width="12" height="90" fill="#7697be" stroke="#365f88"/>`).join("")}`:`<path d="M36 30H56V155H285V175H36Z" fill="#dbe7f8" stroke="#365f88"/><path d="${s.rib_style==="full"?"M56 155H214V55H56Z":"M56 155H214L56 55Z"}" fill="#7697be" stroke="#365f88"/>`;
   dimension=name==="rib_width_mm"?arrow(40,40,52,40):name==="rib_margin_mm"?arrow(20,160,40,160):name==="rib_count"?arrow(40,40,280,40):name==="rib_height_a_mm"?arrow(56,188,214,188):arrow(240,55,240,155);
  }else{
   geometry='<rect x="20" y="132" width="280" height="27" fill="#dbe7f8" stroke="#365f88"/><path d="M20 20H300V100H126V40H82V100H20Z" fill="#dbe7f8" stroke="#365f88"/><path d="M92 132V56L100 48H108L116 56V132Z" fill="#7697be" stroke="#365f88"/>';
   dimension=name==="lead_mm"?arrow(92,56,100,48):name==="socket_floor_mm"?arrow(160,20,160,40):name==="axial_clearance_mm"?arrow(104,40,104,48):name.includes("inset")?arrow(20,179,92,179):name.includes("clearance")?arrow(82,85,92,85):name.includes("width")||name.includes("diameter")?arrow(92,118,116,118):arrow(145,48,145,132);
   if(name==="pin_count")geometry+=Array.from({length:s.pin_count},(_,i)=>`<circle cx="${198+i%2*35}" cy="${126+Math.floor(i/2)*24}" r="6" fill="#267de1"/>`).join("");
  }
  return `<svg viewBox="0 0 320 225" role="img" aria-label="${fields[name][0]} section diagram" data-detail-help="${name}"><defs><marker id="detail-arrow" viewBox="0 0 6 6" refX="3" refY="3" markerWidth="4" markerHeight="4" orient="auto-start-reverse"><path d="M0 0L6 3L0 6" fill="none" stroke="#bd501c"/></marker></defs>${geometry}${dimension}<text x="160" y="214" text-anchor="middle" font-size="12" fill="#365f88">${fields[name][0]} · ${value}</text></svg>`;
 }
 for(const [name,[caption]] of Object.entries(fields)){
  const item=document.createElement("div");item.className="parameter-item has-parameter-help";item.dataset.field=name;if(["rib_style","lip_layout"].includes(name))item.classList.add("detail-style-choice");
  const label=document.createElement("label");label.htmlFor="detail-"+name;label.textContent=caption;
  const input=document.createElement(["pin_count","rib_style","lip_layout"].includes(name)?"select":"input");input.id="detail-"+name;input.name=name;input.required=true;
  if(input.tagName.toLowerCase()==="select")for(const [value,text] of name==="pin_count"?[[2,"2 diagonal corners"],[4,"4 corners"]]:name==="lip_layout"?[["closed","Continuous perimeter"],["selected","Selected sides"]]:[["triangle","Triangular gusset"],["full","Full rectangular rib"]]){
   const option=document.createElement("option");option.value=String(value);option.textContent=text;input.append(option);
  }else{input.type="number";input.min=["lip_height_mm","lip_width_mm","pin_diameter_mm","pin_height_mm","socket_floor_mm","rib_width_mm","rib_height_a_mm","rib_height_b_mm"].includes(name)?"0.2":"0";input.max=["lip_clearance_mm","pin_clearance_mm","axial_clearance_mm"].includes(name)?"2":"1000";input.step="any";if(name==="rib_count"){input.min="1";input.max="32";input.step="1";}}
  input.value=defaults[name];item.append(label,input);
  const help=document.createElement("button");help.type="button";help.id="detail-help-"+name;help.className="parameter-help";help.textContent="?";help.setAttribute("aria-label","Help: "+caption);
  help.addEventListener("click",()=>{helpTrigger=help;$("detail-help-title").textContent=caption;$("detail-help-description").textContent=fields[name][1];$("detail-help-image").innerHTML=helpArt(name);$("detail-help-dialog").showModal();});
  item.append(help);$(["lead_mm","axial_clearance_mm","socket_floor_mm","pin_inset_mm","rib_margin_mm"].includes(name)?"detail-advanced-fields":"detail-fields").append(item);
 }
 $("detail-settings").addEventListener("submit",e=>e.preventDefault());
 $("detail-settings").addEventListener("input",event=>{
  const input=event.target;if(!Object.hasOwn(defaults,input.name))return;
  state.settings[input.name]=["rib_style","lip_layout"].includes(input.name)?input.value:Number(input.value);
  state.revision++;state.error=false;render();
  if(input.name==="lip_layout"&&identity()){
   clearTimeout(timer);queued=false;run(async()=>{await action("detail_update");schedule();});return;
  }
  message(valid()?"Updating live preview…":"Check the highlighted dimensions. Showing the previous valid preview.",!valid());schedule();
 });
 async function begin(editing){state.expecting=true;try{hostRevision=-1;await send("detail_begin",{settings:editing?{...defaults,kind:state.settings.kind}:clone(state.settings),editing});}finally{state.expecting=false;}schedule();}
 $("begin-detail-button").addEventListener("click",()=>run(()=>begin(false)));
 $("edit-detail-button").addEventListener("click",()=>run(()=>begin(true)));
 $("retry-detail-button").addEventListener("click",()=>refresh());
 $("cancel-detail-button").addEventListener("click",()=>run(async()=>{clearTimeout(timer);queued=false;await action("detail_cancel");}));
 $("create-detail-button").addEventListener("click",()=>run(()=>action("detail_commit")));
 $("detail-help-close").addEventListener("click",()=>$("detail-help-dialog").close());
 $("detail-help-dialog").addEventListener("close",()=>helpTrigger?.focus());
 window.PartelierSelectionUI?.register('detail',{active,busy:()=>state.busy,reset:()=>run(async()=>{clearTimeout(timer);queued=false;await action('detail_reset');})});
 window.PartelierDetails=Object.freeze({
  matches:id=>Object.hasOwn(titles,id),isActive:active,isBusy:()=>state.busy,
  select(id){const selected=Object.hasOwn(titles,id);if(selected&&!active()&&state.alias!==id){state.settings={...defaults,kind:id};state.revision=0;sync();}state.selected=selected;state.alias=selected?id:null;render();},
  connect(response){state.connected=true;state.caps=new Set(response.capabilities||[]);if(response.detailState)apply(response.detailState);render();if(ready()&&state.session.phase==="ready")schedule();return active()?state.settings.kind:null;},
  handle(actionName,raw){if(actionName!=="detail_state")return false;const accepted=apply(JSON.parse(raw));if(accepted&&ready()&&state.session.phase==="ready")schedule();return true;}
 });
 render();
})();

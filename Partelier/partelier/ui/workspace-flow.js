"use strict";

// Presentation state only. The existing tool sessions still own all CAD actions.
window.PartelierWorkspace=(()=>{
 const previous=new Map(),terminal=new Set(["idle","created","cancelled"]);
 function update(family,snapshot){
  const card=document.querySelector(`[data-geometry="${family}"]`);if(!card)return;
  const active=!!snapshot?.sessionId&&!terminal.has(snapshot.phase);
  const targets=snapshot?.editing?["edit_target"]:family==="pattern"?["surface"]:family==="detail"?["face_a","face_b"]:["face_a","face_b","axis_edge"];
  if(family==="detail"&&snapshot?.settings?.kind==="lid"&&snapshot.settings.lip_layout==="selected")targets.push("lip_sides");
  const count=active?targets.filter(key=>snapshot?.selections?.[key]?.selected).length:0;
  const picking=active&&(!!snapshot.pickingTarget||!!snapshot.pickingFaces||!!snapshot.pickingSides);
  const complete=active&&count===targets.length&&!picking;
  const last=previous.get(family),identity=active?snapshot.sessionId:null;
  if(picking||(!complete&&last?.complete)||identity!==last?.identity)card.open=!complete;
  else if(complete&&!last?.complete)card.open=false;
  previous.set(family,{identity,complete});
  card.dataset.state=picking?"picking":complete?"complete":active?"selecting":"idle";
  const label=card.querySelector(".geometry-state"),change=card.querySelector(".geometry-change");
  if(label)label.textContent=complete?(snapshot.editing?"Saved result":family==="pattern"?snapshot.selections.surface.label||"Faces selected":family==="detail"?(snapshot.settings?.kind==="lid"&&snapshot.settings?.lip_layout==="selected"?snapshot.selections.lip_sides.label||"Lip sides selected":"2 faces selected"):"2 faces + edge"):picking?(snapshot.pickingSides?"Choose lip sides · Done when ready":snapshot.pickingFaces?"Choose faces · Done when ready":snapshot.pickingTarget==="face_b"?"Select face B":snapshot.pickingTarget==="axis_edge"?"Select reference edge":snapshot.pickingTarget==="edit_target"?"Select existing result":snapshot.pickingTarget==="body"?"Select body":"Select face A"):active?`${count} / ${targets.length} selected`:"Choose geometry";
  if(change)change.textContent=complete?"Change":"Select";
  const dock=document.getElementById(family==="detail"?"detail-action-dock":family+"-action-dock");
  if(dock)dock.dataset.phase=snapshot?.phase||"idle";
 }
 return Object.freeze({update});
})();

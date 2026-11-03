"use strict";
// Original explanatory diagrams; never presented as the Fusion CAD preview.
let fanGuardArtSequence=0;
window.PartelierFanArt = Object.freeze({
 guards:Object.freeze({
  spokes:{name:"Radial spokes",description:"Evenly spaced ribs connect a solid centre disk to the mounting rim. Adjust spoke count, rib width and centre diameter."},
  rings:{name:"Concentric rings",description:"Circular rings join supporting spokes and a centre disk. Pattern spacing changes the ring spacing; spoke count controls their radial supports."},
  parallel:{name:"Parallel bars",description:"Straight parallel ribs span the circular opening and join the mounting rim at both ends. Pattern spacing controls their centre-to-centre distance."},
  grid:{name:"Crossed grid",description:"Two perpendicular sets of ribs form square openings. Change pattern spacing and rib width to adjust the opening size."},
  honeycomb:{name:"Honeycomb",description:"Connected hexagonal ribs fill the circular opening and meet the mounting rim. Pattern spacing changes cell size; rib width controls the material between openings."}
 }),
 guard(s,field){
  const clipId=`fan-guard-aperture-${++fanGuardArtSequence}`;
  const type=this.guards[s.guard_type]?s.guard_type:"spokes",item=this.guards[type];let ribs="";
  const pitch=Math.max(12,Math.min(44,180*(s.guard_pitch_mm||12)/(s.diameter_mm||112.8))),width=Math.max(2,Math.min(8,180*(s.guard_spoke_mm||2)/(s.diameter_mm||112.8)));
  const count=Math.max(3,Math.min(12,s.guard_spokes||4)),centre=Math.max(8,Math.min(45,90*s.hub_diameter_mm/s.diameter_mm));
  if(type==="spokes"||type==="rings"){
   for(let i=0;i<count;i++)ribs+=`<path d="M150 112V22" transform="rotate(${i*360/count} 150 112)"/>`;
   if(type==="rings")for(let r=centre+pitch;r<90;r+=pitch)ribs+=`<circle cx="150" cy="112" r="${r}"/>`;
   ribs+=`<circle cx="150" cy="112" r="${centre}" fill="#9bb7d7" stroke="none"/>`;
  }else if(type==="parallel"||type==="grid"){
   for(let t=-90;t<=90;t+=pitch){ribs+=`<path d="M60 ${112+t}H240"/>`;if(type==="grid")ribs+=`<path d="M${150+t} 22V202"/>`;}
  }else{
   const r=pitch/Math.sqrt(3),h=Math.sqrt(3)*r;
   for(let col=-7;col<=7;col++)for(let row=-10;row<=10;row++){
    const x=150+col*1.5*r,y=112+(row+(col%2)/2)*h;
    ribs+=`<polygon points="${Array.from({length:6},(_,i)=>`${x+r*Math.cos(i*Math.PI/3)},${y+r*Math.sin(i*Math.PI/3)}`).join(" ")}"/>`;
   }
  }
  const holes=[[-1,-1],[-1,1],[1,-1],[1,1]].map(([x,y])=>`<circle cx="${150+x*96}" cy="${112+y*96}" r="4" fill="white" stroke="#375e88"/>`).join("");
  return `<svg viewBox="0 0 300 250" role="img" aria-label="${item.name} guard explanatory diagram"><defs><clipPath id="${clipId}"><circle cx="150" cy="112" r="90"/></clipPath></defs><rect x="42" y="4" width="216" height="216" rx="6" fill="#dce5ef" stroke="#375e88" stroke-width="2"/><circle cx="150" cy="112" r="90" fill="#f8fafc" stroke="#375e88"/><g clip-path="url(#${clipId})" fill="none" stroke="#7399c4" stroke-width="${width}" stroke-linejoin="round">${ribs}</g>${holes}<text x="150" y="242" text-anchor="middle" fill="#375e88" font-size="12">${item.name} · ${s.output==="guard"?"flat standalone guard":"guard above rotor"}</text></svg>`;
 },
 styles:Object.freeze({
  axial:{name:"PC axial",description:"Curved, twisted blades around a central hub. Start here for a conventional PC fan rotor."},
  wide:{name:"Wide blade",description:"Broader blades cover more of the opening. Compare the chord and spacing with the axial preset; airflow performance requires testing."},
  slim:{name:"Slim rotor",description:"A shallower rotor with reduced blade angles for restricted depth. Check the complete blade envelope before adding a frame."},
  ring:{name:"Tip-ring rotor",description:"An outer ring connects the blade tips. Ring thickness and height can be adjusted separately."},
  prop2:{name:"2-blade propeller",description:"Two opposing blades with geometric pitch. Choose an inch-size preset or custom diameter and pitch."},
  prop3:{name:"3-blade propeller",description:"Three evenly spaced pitched blades. Hub, shaft fit and blade sections remain adjustable."},
  prop4:{name:"4-blade propeller",description:"Four pitched blades around the hub. Check blade spacing when increasing chord or reducing hub diameter."},
  blower:{name:"Radial blower impeller",description:"Straight radial vanes on a flat backplate. Optionally add the scroll housing, tangential outlet and removable inlet lid."}
 }),
 photo(style){const item=this.styles[style]||this.styles.axial;const key=this.styles[style]?style:"axial";return `<figure class="fan-reference"><img src="assets/fans/${key}.png" width="640" height="480" alt="${item.name} preset rendered in Fusion"><figcaption>Actual Fusion model · example preset. Your dimensions and output options may differ.</figcaption></figure>`;},
 render(s,field="style"){
 if(s.output==="guard"||s.output==="rotor_guard"&&(field==="style"||field.startsWith("guard_")))return this.guard(s,field);
 if(s.style==="blower"){const vanes=Array.from({length:s.blade_count},(_,i)=>`<path d="M178 114H244" transform="rotate(${360*i/s.blade_count} 150 114)" stroke="#375e88" stroke-width="5"/>`).join("");return `<svg viewBox="0 0 300 250" role="img" aria-label="Straight radial blower impeller schematic">${s.output==="blower_housing"?'<path d="M249 120C260 30 175 4 108 24C25 48 15 141 65 188C115 237 240 222 250 135L250 225H215V134" fill="#dde6f0" stroke="#375e88" stroke-width="3"/>':""}<circle cx="150" cy="114" r="96" fill="#e3eaf3" stroke="#71869f"/>${vanes}<circle cx="150" cy="114" r="29" fill="#c7d5e5" stroke="#375e88"/><circle cx="150" cy="114" r="6" fill="white" stroke="#375e88"/><text x="150" y="245" text-anchor="middle" fill="#375e88" font-size="12">${s.output==="blower_housing"?"Impeller + scroll housing + inlet lid":"Radial impeller · flat backplate"}</text></svg>`;}
 const prop=s.style.startsWith("prop"),n=Math.min(16,s.blade_count),ring=s.style==="ring",frame=s.output.startsWith("rotor_");
 const blades=Array.from({length:n},(_,i)=>`<path transform="rotate(${360*i/n} 150 114)" d="M166 103C188 76 220 61 240 89Q252 109 224 116L170 129Z" fill="#9bb7d7" stroke="#375e88" stroke-width="1.5"/>`).join("");
 const side=/angle|pitch|thickness|camber|fillet|round|height|depth|clearance/.test(field);
 const body=side?`<path d="M35 136Q100 87 262 65L271 76Q130 103 42 146Z" fill="#9bb7d7" stroke="#375e88" stroke-width="2"/><path d="M30 158H280M48 153V174M264 153V174" fill="none" stroke="#8194a9"/><path d="M104 129L203 90" stroke="#d1642c" stroke-width="3"/><text x="150" y="36" text-anchor="middle" fill="#375e88" font-size="12">Blade section / side view · schematic</text>`:`${frame?'<rect x="29" y="8" width="242" height="212" rx="9" fill="#e3eaf3" stroke="#71869f"/><circle cx="150" cy="114" r="100" fill="#f8fafc" stroke="#71869f"/>':''}${ring?'<circle cx="150" cy="114" r="95" stroke="#375e88" stroke-width="7" fill="none"/>':''}${blades}<circle cx="150" cy="114" r="26" fill="#c7d5e5" stroke="#375e88" stroke-width="2"/><circle cx="150" cy="114" r="6" fill="white" stroke="#375e88"/><path d="M53 217H247" stroke="#d1642c" stroke-width="2"/><path d="M53 211V223M247 211V223" stroke="#d1642c"/><text x="150" y="237" text-anchor="middle" fill="#375e88" font-size="12">${prop?'Air propeller':'Fan rotor'} · Ø${s.diameter_mm} mm · ${n} blades</text>`;
 return `<svg viewBox="0 0 300 250" role="img" aria-label="${side?'Blade section':'Fan top view'} explanatory diagram">${body}</svg>`;
}});

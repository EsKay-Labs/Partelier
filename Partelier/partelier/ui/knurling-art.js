"use strict";
window.PartelierKnurlingArt=(()=>{
 let serial=0;
 const escape=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 function marks(style){
  let lines="";const line=(x,y,a,b)=>`<path d="M${x},${y}L${a},${b}"/>`;
  if(style==="diamond")for(let i=-140;i<180;i+=22)lines+=line(i,28,i+140,168)+line(i,168,i+140,28);
  else if(style==="pyramids")for(let y=38;y<160;y+=24)for(let x=25;x<150;x+=24)lines+=`<path d="M${x},${y}h24v24h-24z m0,0l24,24 m-24,0l24,-24"/>`;
  else if(style==="dimples")for(let y=40;y<162;y+=24)for(let x=26;x<155;x+=24)lines+=`<ellipse cx="${x}" cy="${y}" rx="8" ry="8"/>`;
  else if(style==="rings")for(let y=36;y<170;y+=14)lines+=line(20,y,160,y);
  else for(let x=-100;x<210;x+=18){
   if(style==="helical")lines+=line(x,28,x+70,168);
   else if(style==="chevron")lines+=`<path d="M${x},28l35,70l-35,70"/>`;
   else if(style==="waves")lines+=`<path d="M${x},28q26,18 0,35t0,35t0,35t0,35"/>`;
   else if(style==="scallops")lines+=`<path d="M${x},28v140m12,-140v140"/><path d="M${x+4},28v140" stroke-width="5" opacity=".2"/>`;
   else if(style==="flutes")lines+=`<path d="M${x},28v140m7,-140v140"/>`;
   else lines+=line(x,28,x,168);
  }
  return lines;
 }
 const panel=(caption,content)=>`<svg viewBox="0 0 350 220" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="${escape(caption)}"><rect width="350" height="220" rx="12" fill="#edf3f8"/><g font-family="sans-serif" font-size="12" fill="#223d57">${content}<text x="14" y="207" font-size="11">${escape(caption)}</text></g></svg>`;
 function direction(s){
  const raised=s.mode==="emboss",points=[];
  for(let i=0;i<=160;i++){const a=2*Math.PI*i/160,r=(raised?58:46)+6*Math.cos(a*10);points.push(`${100+r*Math.cos(a)},${105+r*Math.sin(a)}`);}
  return panel(raised?"Raised outward · beyond the original cylinder":"Cut inward · inside the original cylinder",`<path d="M${points.join("L")}Z" fill="#bed6ed" stroke="#267de1" stroke-width="2"/><circle cx="100" cy="105" r="52" fill="none" stroke="#63758a" stroke-width="2" stroke-dasharray="5 4"/><circle cx="100" cy="105" r="10" fill="#edf3f8" stroke="#63758a"/><text x="196" y="68">End view</text><path d="M196,91h27" stroke="#63758a" stroke-dasharray="5 4"/><text x="196" y="112">Original cylinder</text><path d="M196,133h27" stroke="#267de1" stroke-width="3"/><text x="196" y="154">${raised?"Added relief":"Finished surface"}</text><text x="196" y="177">${raised?"Outside diameter grows":"Outside diameter retained"}</text>`);
 }
 function finish(s,topic){
  const bottom=topic.startsWith("bottom"),kind=s[bottom?"bottom_finish":"top_finish"]||"none",title=(bottom?"Bottom":"Top")+" · "+(kind==="fillet"?(bottom?"fillet with 45° start":"quarter-round fillet"):kind);
  let contour;
  if(bottom)contour=kind==="chamfer"?"M56,42H145V126L107,164H56Z":kind==="fillet"?"M56,42H145V126A54,54 0 0 1 129.18,164H56Z":"M56,42H145V164H56Z";
  else contour=kind==="chamfer"?"M56,42H107L145,80V164H56Z":kind==="fillet"?"M56,42H107A38,38 0 0 1 145,80V164H56Z":"M56,42H145V164H56Z";
  const note=bottom&&kind==="fillet"?`<path d="M129,164l25,-25" stroke="#267de1" stroke-width="2" stroke-dasharray="4 3"/><text x="200" y="90">45° start</text><text x="200" y="112">True circular arc</text><text x="200" y="137">Size = arc radius</text>`:kind==="fillet"?`<text x="200" y="90">Full quarter-round</text><text x="200" y="116">Size = radius</text>`:kind==="chamfer"?`<text x="200" y="90">45° bevel</text><text x="200" y="116">Equal rise and run</text>`:`<text x="200" y="90">Original edge</text><text x="200" y="116">No edge finish</text>`;
  return panel(title+" · section illustration",`<path d="M56,42H145V164H56Z" fill="none" stroke="#8496a7" stroke-dasharray="5 4"/><path d="${contour}" fill="#bed6ed" stroke="#45617b" stroke-width="2"/>${note}<path d="M40,177h125" stroke="#7b8c9c" stroke-width="4"/><text x="200" y="166">Knob side section</text>`);
 }
 function coverage(s){
  const full=!(s.border_mm>0),top=full?43:61,bottom=full?166:148;
  let stripes="";for(let x=40;x<158;x+=14)stripes+=`<path d="M${x},${top}V${bottom}"/>`;
  return panel(full?"Full cylinder · pattern reaches both ends":"End borders · smooth bands at both ends",`<rect x="32" y="43" width="140" height="123" fill="#dce7f1" stroke="#45617b"/><g stroke="#267de1" stroke-width="3">${stripes}</g><path d="M32,43H172M32,166H172" stroke="#45617b" stroke-width="2"/><text x="196" y="76">${full?"No empty bands":"Optional end bands"}</text><text x="196" y="100">${full?"Border = 0 mm":"Equal width at each end"}</text><text x="196" y="135">Edge finishes are</text><text x="196" y="154">separate controls</text>`);
 }
 function render(s={},topic="style"){
  if(["mode","depth_mm"].includes(topic))return direction(s);
  if(topic.startsWith("top_")||topic.startsWith("bottom_"))return finish(s,topic);
  if(topic==="border_mm")return coverage(s);
  const id=++serial,D=window.PartelierKnurlingData,style=D.styles.some(x=>x[0]===s.style)?s.style:"diamond",label=D.styles.find(x=>x[0]===style)[1];
  const caption=topic==="pitch_mm"?"Whole repeats close the circumference":topic==="phase_deg"?"Rotate around the cylinder axis":topic==="angle_deg"?"Pattern direction ≠ print overhang":label+" · "+(s.mode==="emboss"?"raised outward":"cut inward")+" · illustration";
  return `<svg viewBox="0 0 350 220" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="${escape(caption)}"><defs><clipPath id="knurl-art-clip-${style}-${id}"><path d="M20,28h140v140H20z"/></clipPath><linearGradient id="knurl-art-shade-${style}-${id}"><stop stop-color="#d1dfeb"/><stop offset=".45" stop-color="#edf4fa"/><stop offset="1" stop-color="#adc0d4"/></linearGradient></defs><rect width="350" height="220" rx="12" fill="#edf3f8"/><g transform="translate(14 8)"><path d="M20,25Q90,5 160,25v145q-70,22 -140,0z" fill="url(#knurl-art-shade-${style}-${id})" stroke="#45617b"/><g clip-path="url(#knurl-art-clip-${style}-${id})" fill="none" stroke="#456f98" stroke-width="2">${marks(style)}</g><ellipse cx="90" cy="25" rx="70" ry="13" fill="#e3edf6" stroke="#45617b"/><ellipse cx="90" cy="25" rx="10" ry="3" fill="#7791aa"/><path d="M20,169q70,20 140,0" fill="none" stroke="#45617b" stroke-width="${s.border_mm>0?5:1}"/></g><g fill="#223d57" font-family="sans-serif" font-size="12"><text x="204" y="51">Print upright</text><path d="M233,142v-63m-6,7l6,-8l6,8" fill="none" stroke="#267de1" stroke-width="3"/><text x="204" y="164">Knob axis ↑</text><path d="M196,179h130" stroke="#7b8c9c" stroke-width="4"/><text x="204" y="196">Bed</text><text x="14" y="214" font-size="11">${escape(caption)}</text></g></svg>`;
 }
 return Object.freeze({render});
})();

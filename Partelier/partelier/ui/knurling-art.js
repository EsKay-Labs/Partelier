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
 function render(s={},topic="style"){
  const id=++serial,D=window.PartelierKnurlingData,style=D.styles.some(x=>x[0]===s.style)?s.style:"diamond",label=D.styles.find(x=>x[0]===style)[1];
  const caption=topic==="depth_mm"?"Relief stays inside the original diameter":topic==="border_mm"?"Smooth end bands + gradual transitions":topic==="pitch_mm"?"Whole repeats close the circumference":topic==="phase_deg"?"Rotate around the cylinder axis":topic==="angle_deg"?"Pattern direction ≠ print overhang":label+" · illustrative pattern";
  return `<svg viewBox="0 0 350 220" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="${escape(caption)}"><defs><clipPath id="knurl-art-clip-${style}-${id}"><path d="M20,28h140v140H20z"/></clipPath><linearGradient id="knurl-art-shade-${style}-${id}"><stop stop-color="#d1dfeb"/><stop offset=".45" stop-color="#edf4fa"/><stop offset="1" stop-color="#adc0d4"/></linearGradient></defs><rect width="350" height="220" rx="12" fill="#edf3f8"/><g transform="translate(14 8)"><path d="M20,25Q90,5 160,25v145q-70,22 -140,0z" fill="url(#knurl-art-shade-${style}-${id})" stroke="#45617b"/><g clip-path="url(#knurl-art-clip-${style}-${id})" fill="none" stroke="#456f98" stroke-width="2">${marks(style)}</g><ellipse cx="90" cy="25" rx="70" ry="13" fill="#e3edf6" stroke="#45617b"/><ellipse cx="90" cy="25" rx="10" ry="3" fill="#7791aa"/><path d="M20,169q70,20 140,0" fill="none" stroke="#45617b" stroke-width="5"/></g><g fill="#223d57" font-family="sans-serif" font-size="12"><text x="204" y="51">Print upright</text><path d="M233,142v-63m-6,7l6,-8l6,8" fill="none" stroke="#267de1" stroke-width="3"/><text x="204" y="164">Knob axis ↑</text><path d="M196,179h130" stroke="#7b8c9c" stroke-width="4"/><text x="204" y="196">Bed</text><text x="14" y="214" font-size="11">${escape(caption)}</text></g></svg>`;
 }
 return Object.freeze({render});
})();

"use strict";
window.PartelierMechanismData=Object.freeze({
 defaults:{family:"slider",length_mm:40,width_mm:18,height_mm:8,wall_mm:2,clearance_mm:.3,diameter_mm:32,pin_diameter_mm:3,count:3,angle_deg:30,end_stop:true,x_mm:0,y_mm:0,z_mm:0},
 groups:{basic:["family","length_mm","width_mm","height_mm","diameter_mm","wall_mm","clearance_mm","pin_diameter_mm","count","angle_deg","end_stop"],placement:["x_mm","y_mm","z_mm"]},
 labels:{family:"Mechanism",length_mm:"Length (mm)",width_mm:"Width / leaf reach (mm)",height_mm:"Height / barrel radius (mm)",wall_mm:"Wall thickness (mm)",clearance_mm:"Mating clearance (mm)",diameter_mm:"Male diameter (mm)",pin_diameter_mm:"Pin diameter (mm)",count:"Lugs / knuckles",angle_deg:"Dovetail / turn angle (°)",end_stop:"Rail end stop",x_mm:"X offset (mm)",y_mm:"Y offset (mm)",z_mm:"Z offset (mm)"},
 bounds:{length_mm:[12,300],width_mm:[6,150],height_mm:[3,100],wall_mm:[.8,10],clearance_mm:[.1,2],diameter_mm:[12,150],pin_diameter_mm:[1,30],count:[2,9],angle_deg:[10,60],x_mm:[-10000,10000],y_mm:[-10000,10000],z_mm:[-10000,10000]},
 help:{family:"Creates separate matching parts at the document origin. No selected body is modified. Sliding guides run along Y; pivot and hinge axes follow Z. Install or combine the generated parts deliberately after checking fit. Captive hinge is a print trial, not a validated support-free mechanism.",
 length_mm:"Rail travel envelope, clevis length, or total hinge axial length. The sliding carriage is 55% of the rail length, leaving travel space. End stop occupies one wall thickness at the far end.",
 width_mm:"Full rail width; full clevis ear width; hinge leaf reach beyond the barrel. For a dovetail, increasing width retains more material at its narrow root.",
 height_mm:"Rail rise above its base; bayonet engagement height; full clevis height; OUTSIDE RADIUS of hinge knuckles. This value is not a hinge diameter.",
 wall_mm:"Rail base/carriage roof, coupling wall and lug size, fork ear thickness or hinge leaf thickness. Thin or conflicting dimensions are refused.",
 clearance_mm:"Per-side mating clearance. Pin hole diameter is pin diameter + twice this value. Knuckle end separation uses this axial gap. Test a small print with your material before producing the final assembly.",
 diameter_mm:"Outside diameter of the male bayonet tube before its lugs. The female sleeve reserves mating clearance, lug depth and its outer wall.",
 pin_diameter_mm:"Diameter of the generated separate pin, or integral axle for the captive hinge. Receiving holes add the mating clearance on each side.",
 count:"Equally spaced bayonet lugs, alternating hinge knuckles, or moving louver vanes. Captive hinges require an odd count (3, 5, 7 or 9) so A retains the axle at both ends. Louvers need enough frame width for each vane's complete rotating envelope.",
 angle_deg:"Dovetail wall angle measured from vertical, or the bayonet twist between entry slots and the displayed engaged position. This is not a universal print overhang control.",
 end_stop:"Adds a solid stop to the far end of the rail. The carriage can slide on from the opposite open end. It does not latch or prevent removal from that open end.",
 x_mm:"Translate all mating parts together along document X. No source geometry is changed.",y_mm:"Translate all mating parts together along document Y.",z_mm:"Translate all mating parts together along document Z."}
});
window.PartelierMechanismArt=Object.freeze({render(s){
 const f=s.family;let paths;
 if(["slider","dovetail"].includes(f))paths='<path d="M45 135V100H80L95 60H165L180 100H215V135Z" fill="#90b7df"/><path d="M65 85V40H195V85H180L166 57H94L80 85Z" fill="#d6dce4"/><path d="M100 150H160m-60-5v10m60-10v10" stroke="#245fa0"/>';
 else if(f==="bayonet")paths='<circle cx="130" cy="90" r="60" fill="#d6dce4"/><circle cx="130" cy="90" r="44" fill="#90b7df"/><circle cx="130" cy="90" r="32" fill="white"/><path d="M122 45h16V28h-16zm-40 64-8 14 15 8 8-14zm92 0 8 14-15 8-8-14z" fill="#245fa0"/>';
 else if(f==="pip_louver")paths='<path d="M25 25H235V155H25ZM45 45V135H215V45Z" fill="#d6dce4" fill-rule="evenodd"/><path d="M43 55H217M43 90H217M43 125H217" stroke="#245fa0" stroke-width="8"/><path d="M73 45v20m90 15v20M73 115v20" stroke="#90b7df" stroke-width="4"/>';
 else if(f==="clevis")paths='<path d="M40 35H145V65H75V115H145V145H40Z" fill="#90b7df"/><path d="M95 75H220V105H95Z" fill="#d6dce4"/><path d="M125 20V160" stroke="#245fa0" stroke-width="10"/>';
 else paths='<path d="M35 45H115V135H35Z" fill="#90b7df"/><path d="M145 45H225V135H145Z" fill="#d6dce4"/><path d="M112 35h36v32h-36zm0 72h36v32h-36z" fill="#90b7df"/><path d="M112 71h36v32h-36z" fill="#d6dce4"/><path d="M130 20V155" stroke="#245fa0" stroke-width="5"/>';
 return '<svg viewBox="0 0 260 180" role="img" aria-label="Mechanism concept; mating parts shown in two colours"><g stroke="#405367" stroke-width="2" stroke-linejoin="round">'+paths+'</g></svg>';
}});

"use strict";
window.PartelierKnurlingData={
 defaults:{style:"diamond",pitch_mm:6,depth_mm:.6,border_mm:1,angle_deg:30,phase_deg:0},
 styles:[["diamond","Diamond"],["straight","Straight V grooves"],["helical","Helical"],["chevron","Chevron"],["waves","Waves"],["flutes","Rounded flutes"],["scallops","Scallops"],["dimples","Dimples"],["pyramids","Pyramids"],["rings","Rings"]],
 labels:{style:"Grip style",pitch_mm:"Target spacing (mm)",depth_mm:"Cut depth (mm)",border_mm:"End borders (mm)",angle_deg:"Pattern angle (°)",phase_deg:"Rotate around knob (°)"},
 bounds:{pitch_mm:[2,30],depth_mm:[.1,3],border_mm:[0,20],angle_deg:[0,45],phase_deg:[-360,360]},
 groups:{basic:["style","pitch_mm","depth_mm"],advanced:["border_mm","angle_deg","phase_deg"]},
 help:{
  style:"Choose a grip cut into the outside of an existing cylindrical knob. The original outer diameter is retained at the crests. These are continuous surface reliefs, separate from the raised Grip texture tool.",
  pitch_mm:"Target distance between repeats. Partelier fits a whole number around the circumference so the seam closes. Larger values give fewer, broader details. The actual spacing can differ slightly; depth is not automatically reduced to fit.",
  depth_mm:"Maximum radial material removed. A smaller depth gives a gentler grip and leaves more wall. Combinations that exceed the upright overhang limit or the geometry budget are refused. The result uses small planar facets; smooth styles are approximations. Check the wall around shaft holes in your knob.",
  border_mm:"Untouched cylindrical bands at both ends of the selected face. The texture fades in and out beside these bands instead of ending in a sudden shelf. A short face must leave enough height for both borders and transitions.",
  angle_deg:"Direction of the sloping pattern lines. This is a pattern angle, not the print overhang angle. Partelier separately checks the axial slopes for printing with the knob axis upright.",
  phase_deg:"Rotate the texture around the cylinder without changing its spacing or depth. Useful for aligning the pattern with a pointer or another detail."
 },
 descriptions:{
  diamond:"Crossed diagonal grooves leave a diamond grip.",straight:"Straight axial V grooves give a crisp, simple grip.",helical:"Grooves follow one sloping direction around the knob.",chevron:"Sloping grooves reverse once at the middle of the knob.",waves:"Flowing wavy grooves soften the visual rhythm.",flutes:"Rounded axial grooves give a softer grip than a V groove.",scallops:"Broad circular-section axial grooves give a scalloped grip.",dimples:"Repeated shallow depressions give a dimpled grip.",pyramids:"A grid of sloped facets leaves a pyramidal grip.",rings:"Circumferential grooves form stacked grip rings."
 }
};

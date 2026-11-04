"use strict";
window.PartelierThreadData={
  "defaults": {
    "profile": "printable_v",
    "mode": "external",
    "diameter_mm": 24.0,
    "pitch_mm": 3.0,
    "length_mm": 12.0,
    "depth_mm": 0.0,
    "clearance_mm": 0.25,
    "starts": 1,
    "handedness": "right",
    "lead_in_mm": 1.0,
    "offset_mm": 0.0,
    "wall_mm": 3.0,
    "coupon_clearance_step_mm": 0.1
  },
  "labels": {
    "profile": "Thread profile",
    "mode": "Apply to",
    "diameter_mm": "Nominal diameter (mm)",
    "pitch_mm": "Pitch (mm)",
    "length_mm": "Thread length (mm)",
    "depth_mm": "Thread depth \u00b7 0 = Auto (mm)",
    "clearance_mm": "Radial clearance / side (mm)",
    "starts": "Starts",
    "handedness": "Direction",
    "lead_in_mm": "Entry lead-in (mm)",
    "offset_mm": "Start offset (mm)",
    "wall_mm": "Coupon wall (mm)",
    "coupon_clearance_step_mm": "Test clearance step (mm)"
  },
  "help": {
    "profile": "Printable V is a custom coarse profile with truncated crests and 45\u00b0 flanks in its axial section, intended for printing with the thread axis upright. Rounded smooths the custom tooth shape. Valid custom depth keeps the profile slope; overly deep teeth are refused. Metric uses a nominal 60\u00b0 basic profile. These shapes do not guarantee print quality or fit on every printer. Custom profiles do not mate with standard metal threads.",
    "mode": "External cuts a thread into an existing shaft. Internal cuts into a cylindrical bore. Matched pair selects the shaft first, then the bore on a different body. Fit coupon generates one male and three separate test nuts without selecting a model. Their 1 / 2 / 3 raised outer marks identify the lower / selected / higher clearance.",
    "diameter_mm": "The nominal outside diameter of the male thread before print allowance. Printable and Rounded infer it from your first selected cylinder. Metric keeps the chosen nominal size. A matched pair shares this nominal diameter, applying clearance to the female only.",
    "pitch_mm": "Distance along the axis between neighbouring teeth. Larger pitches make coarser teeth. Multiple starts increase travel per turn: lead = pitch \u00d7 starts.",
    "length_mm": "Axial length of the threaded region. The selected cylindrical face must contain this length plus the start offset. Coupon mode starts at 6 mm for a small fit test.",
    "depth_mm": "Radial depth from crest to root. Zero chooses the profile default. A custom depth must leave usable teeth, room between turns and a connected core; invalid combinations are refused. Metric keeps its automatic nominal depth.",
    "clearance_mm": "Radial allowance per side, applied once. External reduces the male thread radii, useful when mating with an existing female part. Internal expands the female thread radii. Matched pair and Fit coupon keep the male nominal and expand only the female. At 0.25 mm per side the diameter changes by 0.50 mm. This is not a normal distance to the sloping flank. Test the fit on your printer.",
    "starts": "One start is the default. Two or three interleaved threads advance farther in one turn; axial travel equals pitch \u00d7 starts. Both mating parts must use the same value.",
    "handedness": "Right-hand tightens clockwise when viewed from the entry. Left-hand reverses the helix. A pair uses the same direction on both parts.",
    "lead_in_mm": "Axial length of the 45\u00b0 entry chamfers at both ends. The male tips narrow and the female entries widen to help the parts start together. Check the remaining wall around the wider female entries. Preview the chosen ends; this does not guarantee a support-free print in every orientation.",
    "offset_mm": "Distance along the selected cylinder from its inferred start end before the thread begins. The preview shows which end is used.",
    "wall_mm": "Material around each generated test nut. This changes the coupon only; existing bodies keep their outside shape.",
    "coupon_clearance_step_mm": "The three test nuts use clearance minus step, clearance, and clearance plus step. Raised marks on the outside identify them after printing: 1 mark = minus step, 2 marks = selected clearance, 3 marks = plus step. Defaults give 0.15 / 0.25 / 0.35 mm per side. Print the parts separately and compare before threading the full design."
  },
  "bounds": {
    "diameter_mm": [
      6,
      160
    ],
    "pitch_mm": [
      0.5,
      12
    ],
    "length_mm": [
      2,
      80
    ],
    "depth_mm": [
      0,
      5
    ],
    "clearance_mm": [
      0,
      1
    ],
    "starts": [
      1,
      3
    ],
    "lead_in_mm": [
      0,
      5
    ],
    "offset_mm": [
      0,
      100
    ],
    "wall_mm": [
      1.2,
      12
    ],
    "coupon_clearance_step_mm": [
      0,
      0.3
    ]
  },
  "groups": {
    "basic": [
      "mode",
      "profile",
      "diameter_mm",
      "pitch_mm",
      "length_mm",
      "clearance_mm"
    ],
    "advanced": [
      "lead_in_mm",
      "offset_mm",
      "depth_mm",
      "starts",
      "handedness"
    ],
    "coupon": [
      "wall_mm",
      "coupon_clearance_step_mm"
    ]
  },
  "metric": {
    "M6": [
      6,
      1
    ],
    "M8": [
      8,
      1.25
    ],
    "M10": [
      10,
      1.5
    ],
    "M12": [
      12,
      1.75
    ],
    "M16": [
      16,
      2
    ],
    "M20": [
      20,
      2.5
    ],
    "M24": [
      24,
      3
    ],
    "M30": [
      30,
      3.5
    ],
    "M36": [
      36,
      4
    ]
  }
};

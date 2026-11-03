"""Regenerate fan-data.js from strict Python settings and authored help."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import json,ast
from Partelier.partelier.tools.fans.settings import FanSettings,preset,STYLES,PC_SIZES,PROPS
root=Path(__file__).resolve().parents[1]

labels={'style': 'Fan style',
 'size_preset': 'Size preset',
 'diameter_mm': 'Rotor diameter (mm)',
 'blade_count': 'Blades',
 'hub_diameter_mm': 'Hub diameter (mm)',
 'hub_height_mm': 'Hub height (mm)',
 'shaft_diameter_mm': 'Shaft diameter (mm)',
 'shaft_clearance_mm': 'Hole allowance (mm)',
 'shaft_shape': 'Shaft shape',
 'shaft_flat_mm': 'D-flat depth (mm)',
 'set_screw_diameter_mm': 'Set screw bore · 0 off (mm)',
 'root_chord_mm': 'Root width (mm)',
 'mid_chord_mm': 'Middle width (mm)',
 'tip_chord_mm': 'Tip width (mm)',
 'root_angle_deg': 'Root angle (°)',
 'mid_angle_deg': 'Middle angle (°)',
 'tip_angle_deg': 'Tip angle (°)',
 'pitch_mode': 'Blade twist',
 'pitch_mm': 'Geometric pitch (mm)',
 'sweep_deg': 'Sweep (°)',
 'camber_percent': 'Camber (%)',
 'root_thickness_mm': 'Root thickness (mm)',
 'tip_thickness_mm': 'Tip thickness (mm)',
 'root_fillet_mm': 'Root fillet (mm)',
 'edge_round_mm': 'Tip edge radius (mm)',
 'rotation': 'Rotation · viewed from +Z',
 'ring_width_mm': 'Tip ring width (mm)',
 'ring_height_mm': 'Tip ring height (mm)',
 'tip_gap_mm': 'Radial tip gap (mm)',
 'frame_width_mm': 'Frame width (mm)',
 'frame_depth_mm': 'Frame depth (mm)',
 'mount_pitch_mm': 'Mount hole spacing (mm)',
 'mount_hole_mm': 'Mount hole diameter (mm)',
 'axial_clearance_mm': 'Axial clearance (mm)',
 'guard_thickness_mm': 'Guard thickness (mm)',
 'guard_spoke_mm': 'Guard rib width (mm)',
 'guard_spokes': 'Guard spokes',
 'output': 'Output',
 'outline_mode': 'Blade outline',
 'outline_scale_percent': 'Sketch width scale (%)',
 'blower_height_mm': 'Vane height (mm)',
 'blower_backplate_mm': 'Backplate thickness (mm)',
 'blower_vane_mm': 'Vane thickness (mm)',
 'volute_growth_mm': 'Scroll expansion (mm)',
 'volute_wall_mm': 'Housing wall / lid (mm)',
 'volute_outlet_mm': 'Outlet extension (mm)',
 'volute_inlet_mm': 'Inlet diameter · 0 Auto (mm)',
 'volute_motor_mm': 'Motor shaft opening (mm)',
 'volute_lid_gap_mm': 'Lid separation (mm)',
 'volute_mounts': 'Housing mounting holes',
 'guard_type': 'Guard design',
 'guard_pitch_mm': 'Pattern spacing (mm)'}

groups={'basic': ['style',
           'size_preset',
           'output',
           'guard_type',
           'diameter_mm',
           'blade_count',
           'hub_diameter_mm',
           'shaft_diameter_mm'],
 'blade': ['pitch_mode',
           'pitch_mm',
           'root_angle_deg',
           'mid_angle_deg',
           'tip_angle_deg',
           'root_chord_mm',
           'mid_chord_mm',
           'tip_chord_mm',
           'sweep_deg',
           'camber_percent',
           'root_thickness_mm',
           'tip_thickness_mm',
           'root_fillet_mm',
           'edge_round_mm',
           'rotation',
           'ring_width_mm',
           'ring_height_mm',
           'outline_mode',
           'outline_scale_percent',
           'blower_height_mm',
           'blower_backplate_mm',
           'blower_vane_mm'],
 'hub': ['hub_height_mm', 'shaft_shape', 'shaft_clearance_mm', 'shaft_flat_mm', 'set_screw_diameter_mm'],
 'frame': ['tip_gap_mm',
           'frame_width_mm',
           'frame_depth_mm',
           'mount_pitch_mm',
           'mount_hole_mm',
           'axial_clearance_mm',
           'guard_thickness_mm',
           'guard_spoke_mm',
           'guard_spokes',
           'volute_growth_mm',
           'volute_wall_mm',
           'volute_outlet_mm',
           'volute_inlet_mm',
           'volute_motor_mm',
           'volute_lid_gap_mm',
           'volute_mounts',
           'guard_pitch_mm']}

helps={'style': 'A: κλασικό PC axial. B: πλατύτερα πτερύγια. C: χαμηλό προφίλ. D: περιστρεφόμενο δαχτυλίδι στις '
          'άκρες. E/F/G: προπέλα2/3/4 πτερυγίων. Η αλλαγή εφαρμόζει ρητά το αντίστοιχο preset. H: radial '
          'blower impeller with straight vanes and a flat backplate. Optional scroll housing and removable '
          'inlet lid are available.',
 'size_preset': 'Τα PC formats περιγράφουν το πλαίσιο και τις οπές στήριξης. Η πραγματική πτερωτή είναι '
                'μικρότερη. Custom κρατά τις διαστάσεις σου. Τα prop presets ορίζουν διάμετρο και γεωμετρικό '
                'βήμα, όχι πιστοποιημένη απόδοση.',
 'diameter_mm': 'Rotor diameter. For a standalone guard this is the fan diameter: its circular aperture is '
                'this value plus twice the radial tip gap.',
 'blade_count': 'Αριθμός ίδιων πτερυγίων σε ίσες γωνιακές αποστάσεις. Περισσότερα πτερύγια μπορεί να '
                'χρειάζονται μικρότερα πλάτη ή μεγαλύτερο hub. Δεν προβλέπει παροχή ή θόρυβο.',
 'output': 'Rotor and combined outputs build the selected fan. Standalone guard creates only a flat '
           'protective grille with its square mounting rim and four holes; no rotor is needed.',
 'hub_diameter_mm': 'Rotor hub diameter. For a standalone spoke or ring guard this controls the solid centre '
                    'disk.',
 'hub_height_mm': 'Πραγματικό αξονικό ύψος hub. Το κέντρο της πτερωτής είναι στο επίπεδο XY ή στο επίπεδο '
                  'του επιλεγμένου κυκλικού ανοίγματος.',
 'shaft_diameter_mm': 'Μετρημένη διάμετρος άξονα. Η οπή προκύπτει προσθέτοντας Hole allowance στη διάμετρο. '
                      'Για PC εξωτερικό ρότορα χρειάζεται δική σου μέτρηση/αντάπτορας.',
 'shaft_clearance_mm': 'Περιθώριο στη ΔΙΑΜΕΤΡΟ της οπής. 3mm άξονας +0.2mm δίνουν οπή3.2mm. Το πραγματικό '
                       'fit εξαρτάται από την εκτύπωση· χρησιμοποίησε Hub fit test.',
 'shaft_shape': 'Round: κυκλική οπή. D-shaft: μία επίπεδη πλευρά με το μετρημένο D-flat depth. Το σχήμα δεν '
                'εγγυάται εφαρμογή χωρίς δοκιμή.',
 'shaft_flat_mm': 'Βάθος της επίπεδης πλευράς από την περιφέρεια της κυκλικής οπής. Αφορά μόνο D-shaft.',
 'set_screw_diameter_mm': '0: χωρίς εγκάρσια οπή. Θετική τιμή: κυλινδρική οπή στο hub για βίδα σύσφιξης, '
                          'ανάμεσα στις ρίζες. Δεν δημιουργούνται σπειρώματα.',
 'pitch_mode': 'Custom angles: ανεξάρτητη κλίση στη ρίζα, μέση και άκρη. Constant pitch: οι γωνίες '
               'προκύπτουν από atan(P/(2πr)). Το βήμα δεν είναι μετατόπιση αέρα που έχει μετρηθεί.',
 'pitch_mm': 'Γεωμετρικό βήμα ανά περιστροφή σε mm. Τα ονόματα preset5×3 κτλ. είναι σε ίντσες και '
             'μετατρέπονται σε mm. Μεγαλύτερο βήμα δίνει μεγαλύτερες γωνίες.',
 'root_angle_deg': 'Γωνία της διατομής κοντά στο hub ως προς το επίπεδο περιστροφής. Ενεργή μόνο σε Custom '
                   'angles.',
 'mid_angle_deg': 'Γωνία της διατομής στη μέση του διαθέσιμου μήκους. Ενεργή μόνο σε Custom angles.',
 'tip_angle_deg': 'Γωνία της διατομής στην άκρη. Ενεργή μόνο σε Custom angles.',
 'root_chord_mm': 'Πλάτος πτερυγίου στη ρίζα, από τη μία ακμή στην άλλη. Μεγάλη τιμή μπορεί να μη χωρά στο '
                  'hub.',
 'mid_chord_mm': 'Πλάτος πτερυγίου στη μέση του μήκους. Περιορίζεται από την απόσταση των διπλανών '
                 'πτερυγίων.',
 'tip_chord_mm': 'Πλάτος της τελευταίας διατομής. Οι ακραίες ακμές είναι καμπύλες, με προαιρετικό Tip edge '
                 'radius.',
 'sweep_deg': 'Πόσο στρέφεται προς τα πίσω/μπροστά το πτερύγιο από τη ρίζα στην άκρη. Διαφέρει από την κλίση '
              'της διατομής.',
 'camber_percent': 'Καμπυλότητα της μέσης γραμμής της διατομής ως ποσοστό του τοπικού πλάτους. 0 δίνει '
                   'συμμετρική διατομή. Αυτό είναι παραμετρικό σχήμα, όχι πιστοποιημένο αεροδυναμικό προφίλ.',
 'root_thickness_mm': 'Πάχος διατομής κοντά στη ρίζα. Δεν αλλάζει το πλάτος του πτερυγίου.',
 'tip_thickness_mm': 'Πάχος στην τελευταία διατομή. Δεν πρέπει να γίνει μικρότερο από ό,τι μπορεί να '
                     'αναπαράγει η εκτύπωσή σου.',
 'root_fillet_mm': 'Ακτίνα στρογγυλέματος στη σύνδεση hub–πτερυγίου. 0 αφήνει τη σύνδεση χωρίς πρόσθετο '
                   'fillet. Μεγάλη τιμή αρνείται αν δεν χωρά, δεν μικραίνει αυτόματα.',
 'edge_round_mm': 'Ακτίνα στις ακμές του άκρου του πρωτότυπου πτερυγίου. Μικρότερη από το μισό Tip '
                  'thickness. 0 κρατά την αρχική λοξή/καμπύλη διατομή.',
 'rotation': 'Φορά όπως κοιτάς από την πλευρά +Z προς το επίπεδο της πτερωτής. Αλλάζει η χειρομορφία της '
             'γεωμετρίας, όχι μόνο ένα βέλος.',
 'ring_width_mm': 'Ακτινικό πάχος του περιστρεφόμενου δαχτυλιδιού. Ενώνει τις άκρες και περιλαμβάνεται στη '
                  'διάμετρο Rotor.',
 'ring_height_mm': 'Αξονικό ύψος tip ring. Πρέπει να συναντά τα πτερύγια ώστε να σχηματίζεται ένα σώμα.',
 'tip_gap_mm': 'Ακτινικό κενό ανάμεσα στην πτερωτή και το πλαίσιο. Fit opening χρησιμοποιεί '
               'Drotor=Dopening−2×gap. Δεν υπολογίζει παραμόρφωση σε στροφές.',
 'frame_width_mm': 'Εξωτερική πλευρά τετράγωνου πλαισίου. Το κυκλικό άνοιγμα είναι διάμετρος πτερωτής συν '
                   'δύο tip gaps.',
 'frame_depth_mm': 'Αξονικό βάθος του πλαισίου. Πρέπει να καλύπτει το πραγματικό ύψος της πτερωτής και τα '
                   'δύο αξονικά κενά.',
 'mount_pitch_mm': 'Απόσταση κέντρων οπών σε Χ και Υ. Π.χ.120mm PC πλαίσιο χρησιμοποιεί105×105mm στα '
                   'presets.',
 'mount_hole_mm': 'Πραγματική διάμετρος των τεσσάρων οπών στερέωσης. Δεν προστίθεται άλλη κρυφή ανοχή.',
 'axial_clearance_mm': 'Ελεύθερη απόσταση από το αξονικό περίγραμμα της πτερωτής έως το μπροστινό/πίσω '
                       'επίπεδο του frame. Το guard τοποθετείται επιπλέον μπροστά.',
 'guard_thickness_mm': 'Πάχος του ξεχωριστού προστατευτικού σώματος.',
 'guard_spoke_mm': 'Material width of guard ribs and rings. All chosen designs connect to the mounting rim.',
 'guard_spokes': 'Πλήθος ισομοιρασμένων νεύρων του guard.',
 'outline_mode': 'Generated: πλάτη ρίζας/μέσης/άκρης. Sketch: ένα απλό κλειστό profile στο σύστημα του '
                 'sketch, από τη ρίζα αριστερά στην άκρη δεξιά. Χρειάζεται πεπερασμένο πλάτος και στα δύο '
                 'άκρα, χωρίς τρύπες/πολλαπλά διαστήματα.',
 'outline_scale_percent': 'Μεγέθυνση του πλάτους του επιλεγμένου sketch. Το μήκος προσαρμόζεται στο '
                          'διαθέσιμο μήκος πτερυγίου, κρατώντας την αρχική αναλογία στο100%.',
 'blower_height_mm': 'Axial height of straight radial vanes above the flat backplate. This impeller is a '
                     'geometry prototype; no volute housing or airflow prediction is included.',
 'blower_backplate_mm': 'Thickness of the full circular backing disk. The vanes and hub are joined to this '
                        'disk as one solid.',
 'blower_vane_mm': 'Tangential thickness of the straight radial vanes. Neighboring vanes must remain '
                   'separate outside the hub.',
 'volute_growth_mm': 'Increase in radial chamber size through one turn. It also sets the clear outlet width. '
                     'The scroll is a bounded polygonal Archimedean contour, not an airflow simulation.',
 'volute_wall_mm': 'Radial wall allowance, housing floor thickness and removable lid thickness. Mounting '
                   'bosses retain this wall around the screw bores.',
 'volute_outlet_mm': 'Extension of the tangential outlet beyond the large scroll radius. The open mouth '
                     'points along local -Y.',
 'volute_inlet_mm': 'Central opening in the removable lid. Auto uses hub diameter plus two housing walls. '
                    'The inlet must be wider than the hub and smaller than the impeller perimeter.',
 'volute_motor_mm': 'Clear opening through the housing floor for the motor shaft. This is not a bearing seat '
                    'or motor mount; measure your hardware.',
 'volute_lid_gap_mm': 'Small axial separation above the housing wall. The lid is a separate removable part; '
                      'the clearance is not a seal or a tongue-and-groove fit.',
 'volute_mounts': 'Add four exterior bosses and matching through-bores in the housing and lid. Hole diameter '
                  'uses Mount hole diameter. No thread or screw-head recess is generated.',
 'guard_type': 'Choose radial spokes, concentric rings with supporting spokes, parallel bars, a crossed '
               'grid, or honeycomb. All join to the square mounting rim. Diagrams explain the design before '
               'preview.',
 'guard_pitch_mm': 'Centre-to-centre spacing of rings, parallel bars or grid ribs. Honeycomb uses the cell '
                   'spacing. Rib width is separate; increase spacing for larger openings.'}

tree=ast.parse((root/'Partelier/partelier/tools/fans/settings.py').read_text(encoding='utf-8'))
bounds=next(ast.literal_eval(node.value) for node in ast.walk(tree) if isinstance(node,ast.Assign) and any(isinstance(target,ast.Name) and target.id=='bounds' for target in node.targets))
data={'defaults':FanSettings().to_dict(),'presets':{style+':'+size:preset(style,size).to_dict() for style in STYLES for size in (PROPS if style.startswith('prop') else PC_SIZES)},
      'pcSizes':PC_SIZES,'propSizes':PROPS,'labels':labels,'groups':groups,'help':helps,'bounds':{**bounds,'blade_count':(2,16),'guard_spokes':(3,12),'guard_pitch_mm':(4,80)}}
assert set(labels)==set(helps)==set(FanSettings().to_dict())
(root/'Partelier/partelier/ui/fan-data.js').write_text('"use strict";\nwindow.PartelierFanData=Object.freeze('+json.dumps(data,ensure_ascii=False,separators=(',',':'))+');\n',encoding='utf-8',newline='\n')

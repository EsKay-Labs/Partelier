"use strict";

// Local explanatory drawings, independent of the CAD preview and its queue.
window.PartelierPatternHelp = (() => {
    const entries = {
        truss_type: ["Truss layout · Διάταξη", "Warren: συνεχές ζιγκ-ζαγκ χωρίς ενδιάμεσους κάθετους στύλους. Pratt: κάθετοι στύλοι και διαγώνιοι προς το κάτω κέντρο. Howe: οι αντίθετοι διαγώνιοι με τους ίδιους κάθετους στύλους.", "Κόβονται τριγωνικά παράθυρα στην αρχική πλάκα. Οι νευρώσεις και το πλαίσιο παραμένουν ενιαίο σώμα. Οι ονομασίες περιγράφουν γεωμετρία, όχι υπολογισμένη αντοχή."],
        truss_bays: ["Bays · Αριθμός τμημάτων", "Χωρίζει τη διάσταση του span σε ίσα τμήματα. Περισσότερα bays σημαίνουν περισσότερους και μικρότερους διαγωνίους. Warren: 2–64. Pratt και Howe: ζυγός αριθμός 2–64 για συμμετρία.", "Το πάχος των μελών παραμένει αυτό που όρισες. Αν τα παράθυρα κλείνουν από πολύ πυκνά ή παχιά μέλη, μείωσε τα Bays ή το Member width. Δεν μειώνεται αυτόματα το πάχος."],
        truss_axis: ["Span direction · Κατεύθυνση", "Along long side: το truss αναπτύσσεται στη μεγαλύτερη πλευρά του επιλεγμένου ορθογωνίου. Along short side: στη μικρότερη. Η κατεύθυνση υπολογίζεται από την ίδια την πλάκα.", "Δεν εξαρτάται από τους παγκόσμιους άξονες του Fusion. Η πλάκα παραμένει στη θέση της και αλλάζει μόνο η διάταξη των νευρώσεων."],
        truss_member: ["Member width · Πάχος νευρώσεων", "Το πραγματικό πλάτος κάθε διαγωνίου και κάθετου στύλου, κάθετα στη γραμμή του. Αρχικά 2 mm. Το πάχος σε βάθος είναι το αρχικό πάχος της πλάκας.", "Στους κόμβους τα μέλη είναι ενωμένα με το πλαίσιο. Η ίδια τιμή εφαρμόζεται σε όλους τους εσωτερικούς στύλους. Περισσότερο υλικό δεν αποτελεί αυτόματα πιστοποίηση αντοχής."],
        truss_frame: ["Frame width · Περιμετρικό πλαίσιο", "Συμπαγές πλαίσιο γύρω από όλο το ορθογώνιο. Αρχικά 3 mm. Οι επάνω και κάτω πλευρές σχηματίζουν τα chords και οι δύο άκρες ενώνουν το σύνολο.", "Μετριέται από την αρχική εξωτερική ακμή μέχρι το πρώτο παράθυρο. Οι διαγώνιοι καταλήγουν στο πλαίσιο. Αν δεν μένει εσωτερικός χώρος, μείωσε Frame width ή χρησιμοποίησε μεγαλύτερη πλάκα."],
        mount_mode: ["Mounting holes · Οπές στερέωσης", "Off: χωρίς τρύπες. Plain: τέσσερις απλές διαμπερείς οπές στις γωνίες. Countersunk: οι ίδιες οπές με κωνική έδρα 90° για φρεζάτη βίδα.", "Δημιουργείται συμπαγής περιοχή γύρω από κάθε θέση, συνδεδεμένη με το πλαίσιο. Στα Raised καθαρίζουν τα πτερύγια από πάνω της, ώστε η κεφαλή να πατάει στο αρχικό face. Χρειάζεται μία επίπεδη ορθογώνια πλάκα. Πρώτα υπολογίζεται το border από τη βίδα/κεφαλή, μετά σχεδιάζονται τα ανοίγματα μέσα στην υπόλοιπη περιοχή."],
        mount_screw: ["Screw size · Μέγεθος βίδας", "M3, M4, M5 ή M6. Η οπή είναι η ονομαστική διάμετρος συν Hole allowance: M4 + 0.3 mm = 4.3 mm. Δεν δημιουργούνται σπειρώματα.", "Η αυτόματη κεφαλή χρησιμοποιεί τον κατάλογο ISO 10642 της Böllhoff για φρεζάτες βίδες. Διαφορετικοί τύποι έχουν διαφορετική κεφαλή: βάλε τη μετρημένη διάμετρο στο Head Ø όταν χρειάζεται."],
        mount_clearance_mm: ["Hole allowance · Περιθώριο οπής", "Προστίθεται στη διάμετρο της βίδας, όχι στην ακτίνα. Για M4, τιμή 0.3 δίνει οπή Ø4.3 mm. Είναι ανεξάρτητο από το περιθώριο της κεφαλής.", "Δεν εφαρμόζεται κλιμάκωση στη βίδα ή στο σπείρωμα. Η πραγματική εφαρμογή εξαρτάται και από την εκτύπωση. Η αλλαγή ενημερώνει αυτόματα το βάθος της κωνικής έδρας."],
        mount_head_extra_percent: ["Head allowance · Περιθώριο κεφαλής", "Ποσοστό πάνω στη διάμετρο της κεφαλής. Το αρχικό 10% δίνει μεγαλύτερη κωνική έδρα στις Countersunk και χώρο πατήματος στις Plain.", "Η γωνία μένει 90°. Το βάθος υπολογίζεται ως (διάμετρος κεφαλής με περιθώριο − διάμετρος οπής) / 2. Το preview αρνείται έδρα που δεν χωράει στο πάχος της πλάκας."],
        mount_head_mm: ["Head Ø · Διάμετρος κεφαλής", "0 = αυτόματη τιμή καταλόγου. Για άλλη βίδα, γράψε τη μετρημένη εξωτερική διάμετρο της κεφαλής, πριν προστεθεί το Head allowance.", "Για παράδειγμα, Head Ø 8 mm και allowance 10% δίνουν έδρα Ø8.8 mm. Αυτό αφορά φρεζάτη κεφαλή 90°· μια κυλινδρική κεφαλή χρειάζεται Plain ή διαφορετικό τύπο υποδοχής."],
        mount_inset_mm: ["Edge to centre · Θέση οπών", "Απόσταση από τις δύο εξωτερικές ακμές μέχρι το κέντρο κάθε γωνιακής οπής. 0 = Auto, με χώρο για οπή, κεφαλή και συμπαγές υλικό γύρω τους.", "Οι τέσσερις περιοχές δεν πρέπει να ακουμπούν μεταξύ τους ή να ξεφεύγουν από την πλάκα. Πρέπει επίσης να επικαλύπτουν το πλαίσιο. Το preview ελέγχει αυτές τις αποστάσεις χωρίς να αλλάζει μόνο του τις διαστάσεις σου."],
        grille_profile: ["Profile · Διατομή γρίλιας", "Flat: ανοίγματα μέσα στο αρχικό τοίχωμα. Raised: μπάρες ή πλέγμα πάνω από το face. Raised + chamfer: λοξότμητη κορυφή. Με Louvers η κλίση είναι ρυθμιζόμενη από 0° έως 45°, αρχικά 45°.", "Η πίσω πλευρά της ορθογώνιας πλάκας πατάει στο bed. Το frame ανεβαίνει μαζί με τα πτερύγια. Ελέγχονται οι κάτω πλευρές ως προς αυτή τη φορά εκτύπωσης· η τελική εκτύπωση χρειάζεται έλεγχο στον slicer."],
        grille_height_mm: ["Height · Ύψος πάνω από το face", "Πόσο προεξέχει η γρίλια πάνω από την αρχική επιφάνεια. Δεν περιλαμβάνει το πάχος της πλάκας. Η πλάγια μετατόπιση εξαρτάται από Height και Louver tilt. Στις 45° είναι ίση με το ύψος.", "Αν η περσίδα πλησιάζει πολύ το πλαίσιο, μείωσε Height ή αύξησε Border. Το άνοιγμα και το Rib width μετριούνται στη ρίζα, πάνω στο αρχικό face· το chamfer στενεύει την κορυφή των νεύρων."],
        grille_type: ["Grille type · Τύπος γρίλιας", "Parallel bars: μακριά παράλληλα ανοίγματα. Crossed grid: τετράγωνα ανοίγματα με διασταυρωμένα νεύρα. Louvers: λοξά κανάλια μέσα στο πάχος ορθογώνιας πλάκας.", "Το Rotation αλλάζει την κατεύθυνση πάνω στο face. Το Louver tilt αλλάζει την κλίση μέσα στο πάχος ή πάνω από το face στα Raised, από 0° έως 45°. Αρχικά οι γρίλιες λειτουργούν σε επίπεδες επιφάνειες."],
        grille_direction: ["Direction · Κατεύθυνση γρίλιας", "Στρέφει τα ανοίγματα πάνω στην επιλεγμένη επιφάνεια. Τα κουμπιά 0° / 45° / 90° είναι γρήγορες επιλογές· μπορείς να γράψεις και δική σου γωνία.", "Οι μοίρες ακολουθούν τους τοπικούς άξονες του κάθε face, όχι απαραίτητα τους άξονες του Fusion. Στις περσίδες το Tilt ρυθμίζει χωριστά την κλίση μέσα στο πάχος. Το 180° αντιστρέφει αυτή την κλίση."],
        opening_width: ["Opening width · Καθαρό άνοιγμα", "Το πλάτος του ανοίγματος πάνω στην επιλεγμένη επιφάνεια. Στη διασταυρωτή γρίλια είναι η πλευρά του τετραγώνου. Δεν περιλαμβάνει το νεύρο.", "Η απόσταση επανάληψης είναι Opening width + Rib width. Το άνοιγμα και το νεύρο μένουν σταθερά όταν μεγαλώνει το face· επαναλαμβάνονται περισσότερες φορές. Στο border μπορεί να μείνει τμήμα ανοίγματος."],
        rib_width: ["Rib width · Πλάτος νεύρου", "Το συμπαγές υλικό ανάμεσα στα ανοίγματα, μετρημένο πάνω στο face. Μεγαλύτερη τιμή αφήνει περισσότερο υλικό και μειώνει το πλήθος των ανοιγμάτων.", "Η αλλαγή κρατά σταθερό το Opening width. Σε λοξό κανάλι το κάθετο πάχος του νεύρου είναι μικρότερο από το πλάτος του στην επιφάνεια. Δεν αποτελεί προδιαγραφή αντοχής."],
        colour_depth: ["Colour depth · Βάθος χρώματος", "Το πάχος του χρωματισμένου υλικού προς το εσωτερικό. Το επάνω όριό του μένει ακριβώς στην αρχική επιφάνεια και γεμίζει την αντίστοιχη εσοχή χωρίς κενό.", "Πρέπει να μείνει συνεχές υλικό του βασικού σώματος από κάτω. Στο Bambu Studio διαλέγεις filament για καθένα από τα δύο parts. Το πλήθος χρωματισμένων layers εξαρτάται από τον προσανατολισμό και το layer height."],
        louver_angle_deg: ["Louver tilt · Κλίση περσίδας", "Κλίση από την κάθετο της πλάκας: 0° ίσια περσίδα, 45° λοξή. Αρχική και μέγιστη τιμή 45°. Ισχύει στα Flat, Raised και Raised + chamfer. Το Rotation στρέφει ολόκληρη τη γρίλια πάνω στην επιφάνεια.", "Αρχικά απαιτείται ορθογώνια επίπεδη πλάκα σταθερού πάχους. Το Rib width μετριέται πάνω στο face· το πραγματικό κάθετο πάχος λοξού νεύρου είναι μικρότερο. Δεν εγγυάται εκτύπωση χωρίς supports ή πλήρη απόκρυψη του εσωτερικού."],
        density: ["Density · Πυκνότητα", "Sparse: μεγαλύτερα και λιγότερα στοιχεία. Balanced: ενδιάμεση διάταξη. Dense: μικρότερα και περισσότερα. Το Auto fit συνυπολογίζει τις αναλογίες της επιφάνειας, το border και το ελάχιστο κενό.", "Αξιολογούνται έως 16 αριθμητικές προτάσεις και μόνο δύο ελέγχονται στην πραγματική επιφάνεια. Τα όρια εργασίας είναι έως 24 / 64 / 128 στοιχεία ανά face, με 400 συνολικά. Δεν αποτελούν εγγύηση αισθητικής ή αντοχής."],
        size_locked: ["Size · Αυτόματο ή δικό σου", "Automatic: το Auto fit προτείνει μέγεθος από την επιφάνεια και την πυκνότητα. Custom size: διατηρεί το Cell size που όρισες και προσαρμόζει την απόσταση ανάμεσα στα στοιχεία.", "Η αλλαγή του Cell size ενεργοποιεί αυτόματα το Custom size. Επίλεξε ξανά Automatic για νέα πρόταση. Σε πολλά faces μπορεί να προταθούν διαφορετικά μεγέθη· το preview αναφέρει το εύρος τους."],
        pattern: ["Pattern · Σχήμα", "15 επιλογές: βασικά πολύγωνα, στρογγυλεμένα τρίγωνα/εξάγωνα, πεντάγωνα Cairo και μωσαϊκά με συνδυασμούς πολυγώνων. Το ίδιο σχήμα χρησιμοποιείται για τρύπες, χάραξη, ανάγλυφο και Flat colour.", "Κάθε πολύγωνο μετρά ως ένα στοιχείο, ακόμη και όταν ανήκει σε συνδυασμό. Το μικρό δείγμα δείχνει την επιλεγμένη οικογένεια. Οι συνδυασμοί κρατούν το πραγματικό ελάχιστο κενό ανάμεσα στις πλευρές."],
        mode: ["Action · Τι δημιουργείται", "Through holes: διαμπερείς οπές στο επιλεγμένο τοίχωμα. Flat colour: διαχωρίζει χρωματιζόμενα μέρη στο ίδιο ύψος με την αρχική επιφάνεια. Engrave: αφαιρεί υλικό μέχρι το βάθος που ορίζεις. Emboss: προσθέτει ανάγλυφα στοιχεία επάνω στην επιφάνεια.", "Η τομή δείχνει οπή, χάραξη και ανάγλυφο. Το βάθος εμφανίζεται μόνο στις δύο τελευταίες επιλογές."],
        layout_mode: ["Layout · Γέμισμα επιφάνειας", "Auto fit: προτείνει μέγεθος και πλήθος με βάση την επιφάνεια και το Density. Balanced: κρατά ακριβώς το Cell size και αραιώνει τη διάταξη αυξάνοντας τα κενά, έως 48 στοιχεία ανά face. Automatic size: προσαρμόζει το Cell size για να γεμίσει η επιφάνεια, έως 200/face. Fill face και Exact pitch: κρατούν το Cell size και το Minimum gap που όρισες.", "Οι ονομασίες των ρυθμίσεων μένουν σταθερές. Το Auto fit και το Automatic size υπολογίζουν μέγεθος. Στο Auto fit μπορείς να το κλειδώσεις με Custom size. Το Balanced κρατά το μέγεθος και αυξάνει την απόσταση ανάμεσα στα στοιχεία. Τα στοιχεία στις άκρες κόβονται στο border όταν το Edge cells είναι Clip at border."],
        cell_size_mm: ["Cell size · Μέγεθος στοιχείου", "Για εξάγωνα: απόσταση μεταξύ απέναντι επίπεδων πλευρών. Για κύκλους: διάμετρος. Για τετράγωνα: πλευρά. Για ρόμβους: μεγάλη διαγώνιος. Για slots: συνολικό μήκος. Μεγαλύτερο μέγεθος σημαίνει συνήθως λιγότερα στοιχεία.", "Τα Balanced, Fill face και Exact pitch διατηρούν το μέγεθος. Το Auto fit και το Automatic size το προσαρμόζουν· το πραγματικό μέγεθος αναφέρεται στο preview. Στα μωσαϊκά: τρίγωνο = ονομαστική πλευρά, pentagon/octagon/Cairo = πλάτος του βασικού προφίλ, hexagons + triangles = πλευρά μικρού τριγώνου, octagons + squares = διαγώνιος μικρού τετραγώνου, rhombille = μεγάλη διαγώνιος ρόμβου. Το στρογγύλεμα αφαιρεί τις γωνίες από το ονομαστικό προφίλ. Στις άκρες μπορεί να μένει μόνο τμήμα του σχήματος."],
        pitch_mm: ["Pitch · Απόσταση κέντρων", "Η απόσταση ανάμεσα στα κέντρα γειτονικών στοιχείων στη διάταξη. Στις νέες διατάξεις υπολογίζεται από Cell size + Minimum gap. Οι παλιές διατάξεις επιτρέπουν απευθείας εισαγωγή του Pitch.", "Αν αυξήσεις το Pitch κρατώντας σταθερό το gap, μεγαλώνει και το στοιχείο. Σε πλήρη κύλινδρο η οριζόντια απόσταση μπορεί να αυξηθεί λίγο για να κλείσει η ραφή."],
        web_mm: ["Minimum gap · Ελάχιστο κενό", "Η ελάχιστη απόσταση ανάμεσα στα όρια γειτονικών στοιχείων. Στις οπές είναι το υλικό που απομένει ανάμεσά τους. Στο ανάγλυφο είναι η απόσταση μεταξύ εξογκωμάτων. Η αρχική τιμή είναι 7 mm.", "Η αλλαγή του gap διατηρεί το Cell size που έχεις ορίσει. Στο Balanced τα πραγματικά κενά μπορεί να είναι μεγαλύτερα, για να παραμένουν λιγότερα τα στοιχεία, και εμφανίζονται κάτω από το preview. Παράδειγμα: στοιχείο 10 mm + gap 5 mm → απόσταση κέντρων 15 mm. Σε καμπύλες επιφάνειες γίνεται επιπλέον έλεγχος απόστασης."],
        border_mm: ["Border · Περιμετρικό περιθώριο", "Η συμπαγής ζώνη ανάμεσα στο pattern και στα πραγματικά όρια του face, μαζί με υπάρχουσες τρύπες και εσοχές. Η αρχική τιμή είναι 7 mm. Με Clip at border τα σχήματα κόβονται στη γραμμή αυτού του περιθωρίου, ακόμη κι αν απομένει μισό εξάγωνο ή κύκλος.", "Το border είναι ελάχιστο. Με ενεργές οπές στερέωσης υπολογίζεται πρώτα μεγαλύτερη συμπαγής ζώνη, ώστε να χωρά η κεφαλή με το περιθώριο και το υλικό γύρω της. Για default M4 χρησιμοποιούνται τουλάχιστον 12.756 mm. Το Border used δείχνει την τελική τιμή πριν το preview. Υπάρχει μικρή συντηρητική ανοχή στα κοψίματα. Οι καμπύλες ή πολύ σύνθετες περιοχές μπορεί να απαιτούν περισσότερο περιθώριο ή να απορριφθούν. Η ραφή πλήρους κυλίνδρου δεν είναι πραγματική ακμή."],
        depth_mm: ["Depth / Height · Βάθος / Ύψος", "Flat colour: πάχος της χρωματισμένης ζώνης προς το εσωτερικό, χωρίς εξόγκωμα ή κενό. Engrave: πόσο βαθιά αφαιρείται υλικό από την επιφάνεια. Emboss: πόσο προεξέχει το ανάγλυφο. Οι μετρήσεις ακολουθούν την τοπική κάθετο της επιφάνειας.", "Δεν επηρεάζει τις Through holes: αυτές διαπερνούν το πρώτο επιλεγμένο τοίχωμα. Έλεγξε το πάχος του μοντέλου πριν αυξήσεις το βάθος χάραξης."],
        rotation_deg: ["Rotation · Περιστροφή", "Περιστρέφει ολόκληρη τη διάταξη επάνω στο face σε μοίρες, μαζί με τα στοιχεία της. Δεν περιστρέφει το σώμα στο Fusion.", "Σε πλήρη περιτύλιξη κυλίνδρου επιτρέπονται μόνο γωνίες συμβατές με τη συμμετρία του σχήματος, π.χ. πολλαπλάσια των 60° για εξάγωνα."],
        offset_u_mm: ["U offset · Οριζόντια μετατόπιση", "Μετατοπίζει το πλέγμα κατά μήκος του τοπικού άξονα U της επιφάνειας. Σε κύλινδρο ο U κινείται γύρω από την περιφέρεια. Δεν είναι απαραίτητα ο άξονας X του Fusion.", "Θετικές και αρνητικές τιμές επιτρέπονται. Η μετατόπιση επαναλαμβάνεται ανά περίοδο του πλέγματος. Στοιχεία που δεν χωρούν μέσα στο border παραλείπονται."],
        offset_v_mm: ["V offset · Κατακόρυφη μετατόπιση", "Μετατοπίζει το πλέγμα κατά μήκος του τοπικού άξονα V της επιφάνειας. Σε κύλινδρο ο V ακολουθεί το ύψος του. Δεν είναι απαραίτητα ο άξονας Y του Fusion.", "Χρήσιμο για να ευθυγραμμίσεις σειρές με άλλες λεπτομέρειες. Η αλλαγή δεν μετακινεί το ίδιο το face και δεν παρακάμπτει το border."],
        selection_scope: ["Apply to · Πού εφαρμόζεται", "Selected faces: επιλέγεις όλες τις πλευρές με απλά κλικ και πατάς Done για preview. Το Add faces κρατά την προηγούμενη επιλογή· το Clear selection ξεκινά από την αρχή. Whole body: εξετάζονται όλες οι υποστηριζόμενες επιφάνειες του σώματος, με χωριστή διάταξη στην καθεμία.", "Μικρά faces χωρίς χώρο παραμένουν ανέπαφα. Η επιλογή ολόκληρου σώματος μπορεί να περιλαμβάνει εσωτερικά τοιχώματα ή rims. Κατά το Edit δεν αλλάζει το scope· γι’ αυτό χρειάζεται νέο pattern."],
        edge_mode: ["Edge cells · Στοιχεία στις άκρες", "Clip at border: γεμίζει ως το όριο του border, κόβοντας τα στοιχεία στις άκρες. Μπορεί να απομένει μισό εξάγωνο, τμήμα κύκλου ή άλλο σχήμα. Αυτή είναι η νέα αρχική επιλογή.", "Whole cells only: κρατά μόνο ολόκληρα στοιχεία. Τα παλιά αποθηκευμένα patterns διατηρούν αυτή τη συμπεριφορά μέχρι να επιλέξεις Clip at border και Rebuild. Τα κομμάτια ενός στοιχείου μετρούν ως μία επανάληψη."],
    };
    const polygon = (x,y,r,shape) => shape === "circle"
        ? `<circle cx="${x}" cy="${y}" r="${r}"/>`
        : `<polygon points="${Array.from({length:6},(_,i)=>{const a=Math.PI/6+i*Math.PI/3;return `${x+r*Math.cos(a)},${y+r*Math.sin(a)}`;}).join(" ")}"/>`;
    function plate({size=10, gap=8, border=12, shape="hexagon", rotation=0, u=0, v=0, annotation="", partial=false}={}) {
        let cells="";
        const step=size*2+gap;
        for(let row=0;row<4;row++) for(let col=0;col<5;col++) {
            const x=25+col*step+(row%2?step/2:0)+u,y=30+row*step*.866+v;
            if(partial ? x+size>border&&x-size<140-border&&y+size>border&&y-size<124-border : x-size>=border&&x+size<=140-border&&y-size>=border&&y+size<=124-border) cells+=polygon(x,y,size,shape);
        }
        return `<rect x="1" y="1" width="138" height="122" rx="5" fill="#dbe7f8" stroke="#7891b6"/><rect x="${border}" y="${border}" width="${140-2*border}" height="${124-2*border}" fill="none" stroke="#d06d28" stroke-dasharray="3 3"/><g transform="rotate(${rotation} 70 62)" fill="#fff" stroke="#245fc2" stroke-width="1.6">${partial ? `<svg x="${border}" y="${border}" width="${140-2*border}" height="${124-2*border}" overflow="hidden"><g transform="translate(${-border} ${-border})">${cells}</g></svg>` : cells}</g>${annotation}`;
    }
    const arrow = (x1,y1,x2,y2) => `<path d="M${x1} ${y1}L${x2} ${y2}" fill="none" stroke="#bd501c" stroke-width="2" marker-end="url(#help-arrow)"/>`;
    function image(name) {
        let left=plate(),right=plate(),a="Πριν",b="Μετά";
        const grille=(opening,rib,cross=false)=>{
            let slots="";
            for(let y=12;y+opening<=108;y+=opening+rib){
                if(cross) for(let x=12;x+opening<=128;x+=opening+rib) slots+=`<rect x="${x}" y="${y}" width="${opening}" height="${opening}" fill="#fff"/>`;
                else slots+=`<rect x="12" y="${y}" width="116" height="${opening}" fill="#fff"/>`;
            }
            return `<rect x="4" y="4" width="132" height="112" rx="3" fill="#8fb5f4" stroke="#55759e"/>${slots}`;
        };
        const truss=(bays=4,width=4,frame=5,posts=false,vertical=false)=>{
            let lines='';
            for(let i=0;i<bays;i++) {
                const x=12+i*116/bays,u=12+(i+1)*116/bays,y=i%2?16:104,v=i%2?104:16;
                lines+=`<path d="M${x} ${y}L${u} ${v}"/>`;
                if(posts&&i)lines+=`<path d="M${x} 16V104"/>`;
            }
            return `<rect x="8" y="12" width="124" height="96" fill="#fff" stroke="#55759e" stroke-width="${frame}"/><g transform="${vertical?'translate(130 -10) rotate(90) scale(.75 .85)':'translate(0 0)'}" fill="none" stroke="#245fc2" stroke-width="${width}">${lines}</g>`;
        };
        if(name.startsWith("truss_")) {
            left=truss();right=truss(6);a="4 bays";b="6 bays";
            if(name==="truss_type") {right=truss(4,4,5,true);a="Warren · χωρίς στύλους";b="Στύλοι + διαγώνιοι";}
            if(name==="truss_member") {right=truss(4,9);a="Στενότερα μέλη";b="Φαρδύτερα μέλη";}
            if(name==="truss_frame") {right=truss(4,4,12);a="Στενότερο πλαίσιο";b="Φαρδύτερο πλαίσιο";}
            if(name==="truss_axis") {right=truss(4,4,5,false,true);a="Μεγάλη πλευρά";b="Μικρή πλευρά";}
        }
        else if(name==="grille_type") {left=grille(12,8);right=grille(12,8,true);a="Parallel bars";b="Crossed grid";}
        else if(name==="grille_direction") {left=grille(12,8);right=`<rect x="4" y="4" width="132" height="112" rx="3" fill="#8fb5f4" stroke="#55759e"/><svg x="12" y="12" width="116" height="96" overflow="hidden"><g transform="rotate(-45 58 48)" fill="#fff">${Array.from({length:14},(_,i)=>`<rect x="-90" y="${-100+i*20}" width="300" height="12"/>`).join("")}</g></svg>`;a="0°";b="45°";}
        else if(name==="opening_width") {left=grille(8,8);right=grille(22,8);a="Μικρότερο άνοιγμα";b="Μεγαλύτερο άνοιγμα";}
        else if(name==="rib_width") {left=grille(14,4);right=grille(14,18);a="Στενότερα νεύρα";b="Φαρδύτερα νεύρα";}
        else if(name==="colour_depth") {
            const section=d=>`<path d="M8 35H132V105H8Z" fill="#dbe7f8" stroke="#55759e"/><path d="M45 35H90V${35+d}H45Z" fill="#267de1" stroke="#245fc2"/>`;
            left=section(12);right=section(35);a="Ρηχή χρωματιστή ζώνη";b="Βαθύτερη · ίδια επιφάνεια";
        }
        else if(name.startsWith("mount_")) {
            const section=(head,hole)=>`<rect x="8" y="28" width="124" height="80" fill="#8fb5f4" stroke="#365f88"/><path d="M${70-head/2} 28L${70-hole/2} ${28+(head-hole)/2}V108H${70+hole/2}V${28+(head-hole)/2}L${70+head/2} 28Z" fill="#fff" stroke="#365f88"/>`;
            left=section(22,22);right=section(66,28);a="Plain · διαμπερής";b="90° · χώρος κεφαλής";
        }
        else if(name==="grille_profile"||name==="grille_height_mm") {
            const section=(height,chamfer)=>`<path d="M8 105H132" stroke="#bd501c" stroke-width="3"/><path d="M15 105V85H50V${85-height}L${chamfer?55:50} ${80-height}H${chamfer?65:70}L70 ${85-height}V85H115V105Z" fill="#8fb5f4" stroke="#365f88"/><path d="M15 85H115" stroke="#365f88" stroke-dasharray="3 3"/>`;
            left=section(15,false);right=section(40,true);a="Πίσω πλευρά στο bed";b="Ύψος + chamfer";
        }
        else if(name==="louver_angle_deg") {
            const section=shift=>`<path d="M10 25H130V105H10Z" fill="#dbe7f8" stroke="#55759e"/><path d="M45 25H70L${70+shift} 105H${45+shift}Z" fill="#fff" stroke="#245fc2"/>`;
            left=section(0);right=section(42);a="0° · τομή";b="45° · λοξό κανάλι";
        }
        else if(name==="density") {left=plate({size:16,gap:5});right=plate({size:7,gap:5,partial:true});a="Sparse · αραιό";b="Dense · πυκνό";}
        else if(name==="size_locked") {left=plate({size:7,gap:5});right=plate({size:14,gap:5});a="Automatic · πρόταση";b="Custom · μέγεθός σου";}
        else if(name==="pattern"||name==="grille_type") {right=plate({shape:"circle"});a="Εξάγωνα";b="Κύκλοι";}
        else if(name==="cell_size_mm"||name==="pitch_mm"||name==="opening_width") {left=plate({size:7,gap:6});right=plate({size:15,gap:6});a="Μικρότερο μέγεθος";b="Μεγαλύτερο μέγεθος";}
        else if(name==="layout_mode") {left=plate({size:7,gap:22});right=plate({size:7,gap:5,partial:true});a="Balanced · λιγότερα";b="Fill · στο μέγεθός σου";}
        else if(name==="edge_mode") {right=plate({partial:true});a="Ολόκληρα στοιχεία";b="Κόψιμο στο border";}
        else if(name==="web_mm"||name==="rib_width") {left=plate({size:8,gap:4});right=plate({size:8,gap:17});a="Μικρότερο gap";b="Μεγαλύτερο gap";}
        else if(name==="border_mm") {left=plate({size:8,gap:5,border:5});right=plate({size:8,gap:5,border:24});a="Μικρό border";b="Μεγάλο border";}
        else if(name==="rotation_deg") {right=plate({rotation:30});a="0°";b="30° · ενδεικτικά";}
        else if(name==="offset_u_mm") {right=plate({u:10,annotation:arrow(45,110,88,110)});a="U = 0";b="Μετατόπιση U →";}
        else if(name==="offset_v_mm") {right=plate({v:10,annotation:arrow(125,40,125,85)});a="V = 0";b="Μετατόπιση V ↓";}
        else if(name==="selection_scope") {
            const cube=all=>`<path d="M20 42L65 12L123 35L78 65Z" fill="${all?'#8fb5f4':'#dbe7f8'}" stroke="#55759e"/><path d="M20 42L78 65V117L20 94Z" fill="#8fb5f4" stroke="#55759e"/><path d="M78 65L123 35V87L78 117Z" fill="${all?'#8fb5f4':'#dbe7f8'}" stroke="#55759e"/>${polygon(42,68,7,'hexagon')}${polygon(61,79,7,'hexagon')}`;
            left=cube(false);right=cube(true);a="Selected faces";b="Whole body";
        } else if(name==="mode"||name==="depth_mm") {
            const section=(depth,raised)=>`<path d="M8 55H47V${raised?55-depth:55+depth}H90V55H132V105H8Z" fill="#dbe7f8" stroke="#55759e" stroke-width="2"/><path d="M8 55H132" stroke="#245fc2" stroke-dasharray="3 3"/>${arrow(111,55,111,raised?55-depth:55+depth)}`;
            left=section(name==="mode"?50:12,false);right=section(28,name==="mode");a=name==="mode"?"Through · τομή":"Ρηχή χάραξη · τομή";b=name==="mode"?"Emboss · τομή":"Βαθύτερη χάραξη · τομή";
        }
        return `<svg viewBox="0 0 320 160" role="img" aria-label="${entries[name][0]}: ${a} / ${b}" data-help-image="${name}"><defs><marker id="help-arrow" viewBox="0 0 6 6" refX="5" refY="3" markerWidth="5" markerHeight="5" orient="auto-start-reverse"><path d="M0 0L6 3L0 6" fill="#bd501c"/></marker></defs><g transform="translate(8 24)" fill="#fff" stroke="#245fc2">${left}</g><g transform="translate(172 24)" fill="#fff" stroke="#245fc2">${right}</g><g fill="#243e64" font-family="Segoe UI,sans-serif" font-size="10" font-weight="600" text-anchor="middle"><text x="78" y="16">${a}</text><text x="242" y="16">${b}</text></g></svg>`;
    }
    return Object.freeze({ get: (name,settings={}) => {
        if(String(settings.pattern).startsWith("truss_")) name=({pattern:"truss_type",web_mm:"truss_member",border_mm:"truss_frame"})[name]||name;
        else if(String(settings.pattern).startsWith("grille_")) name=({pattern:"grille_type",cell_size_mm:"opening_width",web_mm:"rib_width",rotation_deg:"grille_direction"})[name]||name;
        else if(settings.mode==="inlay"&&name==="depth_mm") name="colour_depth";
        return entries[name]?{title:entries[name][0],description:entries[name][1],detail:entries[name][2],image:image(name)}:null;
    } });
})();

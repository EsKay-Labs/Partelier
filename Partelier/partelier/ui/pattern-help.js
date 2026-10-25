"use strict";

// Local explanatory drawings, independent of the CAD preview and its queue.
window.PartelierPatternHelp = (() => {
    const entries = {
        grille_profile: ["Profile · Διατομή γρίλιας", "Flat: ανοίγματα μέσα στο αρχικό τοίχωμα. Raised: μπάρες ή πλέγμα πάνω από το face. Raised + chamfer: λοξότμητη κορυφή. Με Louvers οι υπερυψωμένες περσίδες χτίζονται στις 45°.", "Η πίσω πλευρά της ορθογώνιας πλάκας πατάει στο bed. Το frame ανεβαίνει μαζί με τα πτερύγια. Ελέγχονται οι κάτω πλευρές ως προς αυτή τη φορά εκτύπωσης· η τελική εκτύπωση χρειάζεται έλεγχο στον slicer."],
        grille_height_mm: ["Height · Ύψος πάνω από το face", "Πόσο προεξέχει η γρίλια πάνω από την αρχική επιφάνεια. Δεν περιλαμβάνει το πάχος της πλάκας. Στις εξωτερικές περσίδες 45° το ίδιο ύψος δίνει ίση πλάγια μετατόπιση.", "Αν η περσίδα πλησιάζει πολύ το πλαίσιο, μείωσε Height ή αύξησε Border. Το άνοιγμα και το Rib width μετριούνται στη ρίζα, πάνω στο αρχικό face· το chamfer στενεύει την κορυφή των νεύρων."],
        grille_type: ["Grille type · Τύπος γρίλιας", "Parallel bars: μακριά παράλληλα ανοίγματα. Crossed grid: τετράγωνα ανοίγματα με διασταυρωμένα νεύρα. Louvers: λοξά κανάλια μέσα στο πάχος ορθογώνιας πλάκας.", "Το Rotation αλλάζει την κατεύθυνση πάνω στο face. Το Louver tilt αλλάζει μόνο την κλίση μέσα στο πάχος. Αρχικά οι γρίλιες λειτουργούν σε επίπεδες επιφάνειες."],
        grille_direction: ["Direction · Κατεύθυνση γρίλιας", "Στρέφει τα ανοίγματα πάνω στην επιλεγμένη επιφάνεια. Τα κουμπιά 0° / 45° / 90° είναι γρήγορες επιλογές· μπορείς να γράψεις και δική σου γωνία.", "Οι μοίρες ακολουθούν τους τοπικούς άξονες του κάθε face, όχι απαραίτητα τους άξονες του Fusion. Στις περσίδες το Tilt ρυθμίζει χωριστά την κλίση μέσα στο πάχος. Το 180° αντιστρέφει αυτή την κλίση."],
        opening_width: ["Opening width · Καθαρό άνοιγμα", "Το πλάτος του ανοίγματος πάνω στην επιλεγμένη επιφάνεια. Στη διασταυρωτή γρίλια είναι η πλευρά του τετραγώνου. Δεν περιλαμβάνει το νεύρο.", "Η απόσταση επανάληψης είναι Opening width + Rib width. Το άνοιγμα και το νεύρο μένουν σταθερά όταν μεγαλώνει το face· επαναλαμβάνονται περισσότερες φορές. Στο border μπορεί να μείνει τμήμα ανοίγματος."],
        rib_width: ["Rib width · Πλάτος νεύρου", "Το συμπαγές υλικό ανάμεσα στα ανοίγματα, μετρημένο πάνω στο face. Μεγαλύτερη τιμή αφήνει περισσότερο υλικό και μειώνει το πλήθος των ανοιγμάτων.", "Η αλλαγή κρατά σταθερό το Opening width. Σε λοξό κανάλι το κάθετο πάχος του νεύρου είναι μικρότερο από το πλάτος του στην επιφάνεια. Δεν αποτελεί προδιαγραφή αντοχής."],
        colour_depth: ["Colour depth · Βάθος χρώματος", "Το πάχος του χρωματισμένου υλικού προς το εσωτερικό. Το επάνω όριό του μένει ακριβώς στην αρχική επιφάνεια και γεμίζει την αντίστοιχη εσοχή χωρίς κενό.", "Πρέπει να μείνει συνεχές υλικό του βασικού σώματος από κάτω. Στο Bambu Studio διαλέγεις filament για καθένα από τα δύο parts. Το πλήθος χρωματισμένων layers εξαρτάται από τον προσανατολισμό και το layer height."],
        louver_angle_deg: ["Louver tilt · Κλίση περσίδας", "Κλίση του καναλιού από την κάθετο της πλάκας: 0° ίσιο πέρασμα, 45° λοξό. Το Rotation στρέφει ολόκληρη τη γρίλια πάνω στην επιφάνεια.", "Αρχικά απαιτείται ορθογώνια επίπεδη πλάκα σταθερού πάχους. Το Rib width μετριέται πάνω στο face· το πραγματικό κάθετο πάχος λοξού νεύρου είναι μικρότερο. Δεν εγγυάται εκτύπωση χωρίς supports ή πλήρη απόκρυψη του εσωτερικού."],
        density: ["Density · Πυκνότητα", "Sparse: μεγαλύτερα και λιγότερα στοιχεία. Balanced: ενδιάμεση διάταξη. Dense: μικρότερα και περισσότερα. Το Auto fit συνυπολογίζει τις αναλογίες της επιφάνειας, το border και το ελάχιστο κενό.", "Αξιολογούνται έως 16 αριθμητικές προτάσεις και μόνο δύο ελέγχονται στην πραγματική επιφάνεια. Τα όρια εργασίας είναι έως 24 / 64 / 128 στοιχεία ανά face, με 400 συνολικά. Δεν αποτελούν εγγύηση αισθητικής ή αντοχής."],
        size_locked: ["Size · Αυτόματο ή δικό σου", "Automatic: το Auto fit προτείνει μέγεθος από την επιφάνεια και την πυκνότητα. Custom size: διατηρεί το Cell size που όρισες και προσαρμόζει την απόσταση ανάμεσα στα στοιχεία.", "Η αλλαγή του Cell size ενεργοποιεί αυτόματα το Custom size. Επίλεξε ξανά Automatic για νέα πρόταση. Σε πολλά faces μπορεί να προταθούν διαφορετικά μεγέθη· το preview αναφέρει το εύρος τους."],
        pattern: ["Pattern · Σχήμα", "15 επιλογές: βασικά πολύγωνα, στρογγυλεμένα τρίγωνα/εξάγωνα, πεντάγωνα Cairo και μωσαϊκά με συνδυασμούς πολυγώνων. Το ίδιο σχήμα χρησιμοποιείται για τρύπες, χάραξη, ανάγλυφο και Flat colour.", "Κάθε πολύγωνο μετρά ως ένα στοιχείο, ακόμη και όταν ανήκει σε συνδυασμό. Το μικρό δείγμα δείχνει την επιλεγμένη οικογένεια. Οι συνδυασμοί κρατούν το πραγματικό ελάχιστο κενό ανάμεσα στις πλευρές."],
        mode: ["Action · Τι δημιουργείται", "Through holes: διαμπερείς οπές στο επιλεγμένο τοίχωμα. Flat colour: διαχωρίζει χρωματιζόμενα μέρη στο ίδιο ύψος με την αρχική επιφάνεια. Engrave: αφαιρεί υλικό μέχρι το βάθος που ορίζεις. Emboss: προσθέτει ανάγλυφα στοιχεία επάνω στην επιφάνεια.", "Η τομή δείχνει οπή, χάραξη και ανάγλυφο. Το βάθος εμφανίζεται μόνο στις δύο τελευταίες επιλογές."],
        layout_mode: ["Layout · Γέμισμα επιφάνειας", "Auto fit: προτείνει μέγεθος και πλήθος με βάση την επιφάνεια και το Density. Balanced: κρατά ακριβώς το Cell size και αραιώνει τη διάταξη αυξάνοντας τα κενά, έως 48 στοιχεία ανά face. Automatic size: προσαρμόζει το Cell size για να γεμίσει η επιφάνεια, έως 200/face. Fill face και Exact pitch: κρατούν το Cell size και το Minimum gap που όρισες.", "Οι ονομασίες των ρυθμίσεων μένουν σταθερές. Το Auto fit και το Automatic size υπολογίζουν μέγεθος. Στο Auto fit μπορείς να το κλειδώσεις με Custom size. Το Balanced κρατά το μέγεθος και αυξάνει την απόσταση ανάμεσα στα στοιχεία. Τα στοιχεία στις άκρες κόβονται στο border όταν το Edge cells είναι Clip at border."],
        cell_size_mm: ["Cell size · Μέγεθος στοιχείου", "Για εξάγωνα: απόσταση μεταξύ απέναντι επίπεδων πλευρών. Για κύκλους: διάμετρος. Για τετράγωνα: πλευρά. Για ρόμβους: μεγάλη διαγώνιος. Για slots: συνολικό μήκος. Μεγαλύτερο μέγεθος σημαίνει συνήθως λιγότερα στοιχεία.", "Τα Balanced, Fill face και Exact pitch διατηρούν το μέγεθος. Το Auto fit και το Automatic size το προσαρμόζουν· το πραγματικό μέγεθος αναφέρεται στο preview. Στα μωσαϊκά: τρίγωνο = ονομαστική πλευρά, pentagon/octagon/Cairo = πλάτος του βασικού προφίλ, hexagons + triangles = πλευρά μικρού τριγώνου, octagons + squares = διαγώνιος μικρού τετραγώνου, rhombille = μεγάλη διαγώνιος ρόμβου. Το στρογγύλεμα αφαιρεί τις γωνίες από το ονομαστικό προφίλ. Στις άκρες μπορεί να μένει μόνο τμήμα του σχήματος."],
        pitch_mm: ["Pitch · Απόσταση κέντρων", "Η απόσταση ανάμεσα στα κέντρα γειτονικών στοιχείων στη διάταξη. Στις νέες διατάξεις υπολογίζεται από Cell size + Minimum gap. Οι παλιές διατάξεις επιτρέπουν απευθείας εισαγωγή του Pitch.", "Αν αυξήσεις το Pitch κρατώντας σταθερό το gap, μεγαλώνει και το στοιχείο. Σε πλήρη κύλινδρο η οριζόντια απόσταση μπορεί να αυξηθεί λίγο για να κλείσει η ραφή."],
        web_mm: ["Minimum gap · Ελάχιστο κενό", "Η ελάχιστη απόσταση ανάμεσα στα όρια γειτονικών στοιχείων. Στις οπές είναι το υλικό που απομένει ανάμεσά τους. Στο ανάγλυφο είναι η απόσταση μεταξύ εξογκωμάτων. Η αρχική τιμή είναι 7 mm.", "Η αλλαγή του gap διατηρεί το Cell size που έχεις ορίσει. Στο Balanced τα πραγματικά κενά μπορεί να είναι μεγαλύτερα, για να παραμένουν λιγότερα τα στοιχεία, και εμφανίζονται κάτω από το preview. Παράδειγμα: στοιχείο 10 mm + gap 5 mm → απόσταση κέντρων 15 mm. Σε καμπύλες επιφάνειες γίνεται επιπλέον έλεγχος απόστασης."],
        border_mm: ["Border · Περιμετρικό περιθώριο", "Η συμπαγής ζώνη ανάμεσα στο pattern και στα πραγματικά όρια του face, μαζί με υπάρχουσες τρύπες και εσοχές. Η αρχική τιμή είναι 7 mm. Με Clip at border τα σχήματα κόβονται στη γραμμή αυτού του περιθωρίου, ακόμη κι αν απομένει μισό εξάγωνο ή κύκλος.", "Το border είναι ελάχιστο. Υπάρχει μικρή συντηρητική ανοχή στα κοψίματα. Οι καμπύλες ή πολύ σύνθετες περιοχές μπορεί να απαιτούν περισσότερο περιθώριο ή να απορριφθούν. Η ραφή πλήρους κυλίνδρου δεν είναι πραγματική ακμή."],
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
        if(name==="grille_type") {left=grille(12,8);right=grille(12,8,true);a="Parallel bars";b="Crossed grid";}
        else if(name==="grille_direction") {left=grille(12,8);right=`<rect x="4" y="4" width="132" height="112" rx="3" fill="#8fb5f4" stroke="#55759e"/><svg x="12" y="12" width="116" height="96" overflow="hidden"><g transform="rotate(-45 58 48)" fill="#fff">${Array.from({length:14},(_,i)=>`<rect x="-90" y="${-100+i*20}" width="300" height="12"/>`).join("")}</g></svg>`;a="0°";b="45°";}
        else if(name==="opening_width") {left=grille(8,8);right=grille(22,8);a="Μικρότερο άνοιγμα";b="Μεγαλύτερο άνοιγμα";}
        else if(name==="rib_width") {left=grille(14,4);right=grille(14,18);a="Στενότερα νεύρα";b="Φαρδύτερα νεύρα";}
        else if(name==="colour_depth") {
            const section=d=>`<path d="M8 35H132V105H8Z" fill="#dbe7f8" stroke="#55759e"/><path d="M45 35H90V${35+d}H45Z" fill="#267de1" stroke="#245fc2"/>`;
            left=section(12);right=section(35);a="Ρηχή χρωματιστή ζώνη";b="Βαθύτερη · ίδια επιφάνεια";
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
        if(String(settings.pattern).startsWith("grille_")) name=({pattern:"grille_type",cell_size_mm:"opening_width",web_mm:"rib_width",rotation_deg:"grille_direction"})[name]||name;
        else if(settings.mode==="inlay"&&name==="depth_mm") name="colour_depth";
        return entries[name]?{title:entries[name][0],description:entries[name][1],detail:entries[name][2],image:image(name)}:null;
    } });
})();

"use strict";

// Local explanatory drawings, independent of the CAD preview and its queue.
window.PartelierPatternHelp = (() => {
    const entries = {
        pattern: ["Pattern · Σχήμα", "Το σχήμα κάθε επανάληψης: εξάγωνο, κύκλος, ρόμβος, τετράγωνο ή μακρόστενη οπή. Το ίδιο σχήμα χρησιμοποιείται για τρύπες, χάραξη και ανάγλυφο.", "Η εικόνα συγκρίνει εξάγωνα με κύκλους."],
        mode: ["Action · Τι δημιουργείται", "Through holes: διαμπερείς οπές στο επιλεγμένο τοίχωμα. Engrave: αφαιρεί υλικό μέχρι το βάθος που ορίζεις. Emboss: προσθέτει ανάγλυφα στοιχεία επάνω στην επιφάνεια.", "Η τομή δείχνει οπή, χάραξη και ανάγλυφο. Το βάθος εμφανίζεται μόνο στις δύο τελευταίες επιλογές."],
        layout_mode: ["Layout · Γέμισμα επιφάνειας", "Balanced: πιο αραιή διάταξη, έως 48 στοιχεία ανά face. Automatic size: προσαρμόζει το Cell size για να γεμίσει η επιφάνεια, έως 200/face. Fill face και Exact pitch: κρατούν το Cell size και το Minimum gap που όρισες.", "Οι ονομασίες των ρυθμίσεων μένουν σταθερές. Στους αυτόματους τρόπους το Cell size είναι στόχος και το πραγματικό μέγεθος φαίνεται κάτω από το preview. Τα στοιχεία στις άκρες κόβονται στο border όταν το Edge cells είναι Clip at border."],
        cell_size_mm: ["Cell size · Μέγεθος στοιχείου", "Για εξάγωνα: απόσταση μεταξύ απέναντι επίπεδων πλευρών. Για κύκλους: διάμετρος. Για τετράγωνα: πλευρά. Για ρόμβους: μεγάλη διαγώνιος. Για slots: συνολικό μήκος. Μεγαλύτερο μέγεθος σημαίνει συνήθως λιγότερα στοιχεία.", "Το Fill face και το Exact pitch διατηρούν το μέγεθος. Τα Balanced και Automatic size το προσαρμόζουν· το πραγματικό μέγεθος αναφέρεται στο preview. Στις άκρες μπορεί να μένει μόνο τμήμα του σχήματος."],
        pitch_mm: ["Pitch · Απόσταση κέντρων", "Η απόσταση ανάμεσα στα κέντρα γειτονικών στοιχείων στη διάταξη. Στις νέες διατάξεις υπολογίζεται από Cell size + Minimum gap. Οι παλιές διατάξεις επιτρέπουν απευθείας εισαγωγή του Pitch.", "Αν αυξήσεις το Pitch κρατώντας σταθερό το gap, μεγαλώνει και το στοιχείο. Σε πλήρη κύλινδρο η οριζόντια απόσταση μπορεί να αυξηθεί λίγο για να κλείσει η ραφή."],
        web_mm: ["Minimum gap · Ελάχιστο κενό", "Η ελάχιστη απόσταση ανάμεσα στα όρια γειτονικών στοιχείων. Στις οπές είναι το υλικό που απομένει ανάμεσά τους. Στο ανάγλυφο είναι η απόσταση μεταξύ εξογκωμάτων. Η αρχική τιμή είναι 5 mm.", "Η αλλαγή του gap διατηρεί το Cell size που έχεις ορίσει. Παράδειγμα: στοιχείο 10 mm + gap 5 mm → απόσταση κέντρων 15 mm. Σε καμπύλες επιφάνειες γίνεται επιπλέον έλεγχος απόστασης."],
        border_mm: ["Border · Περιμετρικό περιθώριο", "Η συμπαγής ζώνη ανάμεσα στο pattern και στα πραγματικά όρια του face, μαζί με υπάρχουσες τρύπες και εσοχές. Με Clip at border τα σχήματα κόβονται στη γραμμή αυτού του περιθωρίου, ακόμη κι αν απομένει μισό εξάγωνο ή κύκλος.", "Το border είναι ελάχιστο. Υπάρχει μικρή συντηρητική ανοχή στα κοψίματα. Οι καμπύλες ή πολύ σύνθετες περιοχές μπορεί να απαιτούν περισσότερο περιθώριο ή να απορριφθούν. Η ραφή πλήρους κυλίνδρου δεν είναι πραγματική ακμή."],
        depth_mm: ["Depth / Height · Βάθος / Ύψος", "Engrave: πόσο βαθιά αφαιρείται υλικό από την επιφάνεια. Emboss: πόσο προεξέχει το ανάγλυφο. Οι μετρήσεις ακολουθούν την τοπική κάθετο της επιφάνειας.", "Δεν επηρεάζει τις Through holes: αυτές διαπερνούν το πρώτο επιλεγμένο τοίχωμα. Έλεγξε το πάχος του μοντέλου πριν αυξήσεις το βάθος χάραξης."],
        rotation_deg: ["Rotation · Περιστροφή", "Περιστρέφει ολόκληρη τη διάταξη επάνω στο face σε μοίρες, μαζί με τα στοιχεία της. Δεν περιστρέφει το σώμα στο Fusion.", "Σε πλήρη περιτύλιξη κυλίνδρου επιτρέπονται μόνο γωνίες συμβατές με τη συμμετρία του σχήματος, π.χ. πολλαπλάσια των 60° για εξάγωνα."],
        offset_u_mm: ["U offset · Οριζόντια μετατόπιση", "Μετατοπίζει το πλέγμα κατά μήκος του τοπικού άξονα U της επιφάνειας. Σε κύλινδρο ο U κινείται γύρω από την περιφέρεια. Δεν είναι απαραίτητα ο άξονας X του Fusion.", "Θετικές και αρνητικές τιμές επιτρέπονται. Η μετατόπιση επαναλαμβάνεται ανά περίοδο του πλέγματος. Στοιχεία που δεν χωρούν μέσα στο border παραλείπονται."],
        offset_v_mm: ["V offset · Κατακόρυφη μετατόπιση", "Μετατοπίζει το πλέγμα κατά μήκος του τοπικού άξονα V της επιφάνειας. Σε κύλινδρο ο V ακολουθεί το ύψος του. Δεν είναι απαραίτητα ο άξονας Y του Fusion.", "Χρήσιμο για να ευθυγραμμίσεις σειρές με άλλες λεπτομέρειες. Η αλλαγή δεν μετακινεί το ίδιο το face και δεν παρακάμπτει το border."],
        selection_scope: ["Apply to · Πού εφαρμόζεται", "Selected faces: επηρεάζονται μόνο τα faces που επιλέγεις· το Add face προσθέτει άλλο ένα. Whole body: εξετάζονται όλες οι υποστηριζόμενες επιφάνειες του σώματος, με χωριστή διάταξη στην καθεμία.", "Μικρά faces χωρίς χώρο παραμένουν ανέπαφα. Η επιλογή ολόκληρου σώματος μπορεί να περιλαμβάνει εσωτερικά τοιχώματα ή rims. Κατά το Edit δεν αλλάζει το scope· γι’ αυτό χρειάζεται νέο pattern."],
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
        if(name==="pattern") {right=plate({shape:"circle"});a="Εξάγωνα";b="Κύκλοι";}
        else if(name==="cell_size_mm"||name==="pitch_mm") {left=plate({size:7,gap:6});right=plate({size:15,gap:6});a="Μικρότερο μέγεθος";b="Μεγαλύτερο μέγεθος";}
        else if(name==="layout_mode") {left=plate({size:18,gap:9});right=plate({size:7,gap:5,partial:true});a="Balanced · λιγότερα";b="Fill · στο μέγεθός σου";}
        else if(name==="edge_mode") {right=plate({partial:true});a="Ολόκληρα στοιχεία";b="Κόψιμο στο border";}
        else if(name==="web_mm") {left=plate({size:8,gap:4});right=plate({size:8,gap:17});a="Μικρότερο gap";b="Μεγαλύτερο gap";}
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
    return Object.freeze({ get: name => entries[name] ? {title:entries[name][0],description:entries[name][1],detail:entries[name][2],image:image(name)} : null });
})();

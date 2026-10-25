"use strict";

// One pattern session serves the honeycomb, perforation and texture presets.
(() => {
    const $ = id => document.getElementById(id);
    const defaults = Object.freeze({ pattern: "hexagon", mode: "through", pitch_mm: 19.5, web_mm: 7, depth_mm: 1, border_mm: 7, rotation_deg: 0, offset_u_mm: 0, offset_v_mm: 0, selection_scope: "faces", layout_mode: "auto", edge_mode: "clip", density: "balanced", size_locked: false, louver_angle_deg: 45, grille_profile: "flat", grille_height_mm: 3, mount_mode: "off", mount_screw: "M4", mount_clearance_mm: .3, mount_head_extra_percent: 10, mount_head_mm: 0, mount_inset_mm: 0 });
    const presets = { honeycomb: { pattern: "hexagon", mode: "through" }, perforation: { pattern: "circle", mode: "through" }, knurl: { pattern: "diamond", mode: "emboss" }, grilles: { pattern: "grille_parallel", mode: "through", layout_mode: "fill", pitch_mm: 7, web_mm: 2, border_mm: 7, edge_mode: "clip", rotation_deg: 0, offset_u_mm: 0, offset_v_mm: 0 } };
    const choices = {
        pattern: [["hexagon", "Hexagons"], ["rounded_hexagon", "Rounded hexagons"], ["elongated_hexagon", "Elongated hexagons"],
            ["triangle", "Triangles · alternating"], ["rounded_triangle", "Rounded triangles"], ["pentagon", "Pentagons"],
            ["cairo", "Cairo pentagons"], ["octagon", "Octagons"], ["trihex", "Hexagons + triangles"],
            ["octagon_square", "Octagons + squares"], ["rhombille", "Rhombille · cube grid"],
            ["circle", "Circles"], ["diamond", "Diamonds"], ["square", "Squares"], ["slot", "Slots"]],
        mode: [["through", "Through holes"], ["engrave", "Engrave"], ["emboss", "Emboss"], ["inlay", "Flat colour"]],
        layout_mode: [["auto", "Auto fit · visual balance"], ["balanced", "Balanced · fewer cells"], ["fill", "Fill face · fixed size"], ["fit", "Automatic size"], ["fixed", "Exact pitch"]],
        density: [["sparse", "Sparse"], ["balanced", "Balanced"], ["dense", "Dense"]],
        size_locked: [["false", "Automatic"], ["true", "Custom size"]],
        grille_profile: [["flat", "Flat · within the wall"], ["raised", "Raised · back to bed"], ["chamfer", "Raised + chamfer · back to bed"]],
        mount_mode: [["off", "Off"], ["plain", "4 plain holes"], ["countersink", "4 countersunk holes · 90°"]],
        mount_screw: [["M3","M3"],["M4","M4"],["M5","M5"],["M6","M6"]],
        selection_scope: [["faces", "Selected faces"], ["body", "Whole body"]],
        edge_mode: [["clip", "Clip at border"], ["whole", "Whole cells only"]]
    };
    const grilleChoices = [["grille_parallel","Parallel bars"],["grille_cross","Crossed grid"],["grille_louver","Louvers"]];
    const grille = () => state.settings.pattern.startsWith("grille_");
    const optionsFor = name => name === "pattern" && grille() ? grilleChoices : choices[name];
    let showingGrilles = false;
    const terminal = new Set(["idle", "created", "cancelled"]), retired = new Set();
    const signed = new Set(["rotation_deg", "offset_u_mm", "offset_v_mm"]);
    const state = { alias: null, selected: false, connected: false, capabilities: new Set(), others: { hinge: false, snap: false }, settings: { ...defaults }, revision: 0, session: null, busy: false, dirty: false, expecting: false, liveError: false, connectionError: false };
    let serial = 0, pushedVersion = 0, timer, queued = false, pending = 0, actions = Promise.resolve();
    let previewRequest, recoveryTimer, recoveryFlight;
    const active = () => !!state.session && !terminal.has(state.session.phase) && !!(state.session.sessionId || state.session.phase === "opening");
    const identity = () => active() ? state.session.sessionId : null;
    const supported = () => state.connected && state.capabilities.has("pattern-palette");
    const otherActive = () => state.others.hinge || state.others.snap;
    const selected = () => !!state.session?.selections?.surface?.selected;
    const current = () => !state.liveError && state.session?.phase === "preview" && state.session.revision === state.revision && state.session.previewCurrent !== false;
    const valid = () => $("pattern-settings").checkValidity();
    const editing = () => active() && !!state.session?.editing;
    const traceKey = "Partelier.patternTrace.v1", traceRing = [], traceQueue = [], traceLast = new Map();
    let traceTimer, traceSerial = 0;
    try {
        const saved = window.localStorage?.getItem(traceKey), entries = typeof saved === "string" && saved.length < 131072 ? JSON.parse(saved) : [];
        if (Array.isArray(entries)) for (const entry of entries.slice(-80)) if (entry && /^[A-Za-z0-9_.:-]{1,80}$/.test(entry.event)
                && Number.isFinite(entry.at) && entry.at >= 0 && entry.context && !Array.isArray(entry.context) && Object.keys(entry.context).length <= 32
                && Object.values(entry.context).every(value => value === null || typeof value === "boolean" || typeof value === "string" && value.length <= 120 || typeof value === "number" && Number.isFinite(value))) {
            const replay = { event:entry.event,at:entry.at,context:{ ...Object.fromEntries(Object.entries(entry.context).slice(0,31)),replayed:true } };
            traceRing.push(replay); traceQueue.push(replay);
        }
    } catch (_) {}
    function trace(event, extra = {}, dedupe = false) {
        try {
            const context = { sessionId: state.session?.sessionId || null, revision: state.revision, phase: state.session?.phase || "idle",
                pending, busy: state.busy, current: current(), surfaceSelected: selected(), waitingRequest: previewRequest?.requestId || null, ...extra };
            for (const key of Object.keys(context)) { const value = context[key]; context[key] = typeof value === "string" ? value.slice(0,120) : typeof value === "number" ? Number.isFinite(value) ? value : null : typeof value === "boolean" || value === null ? value : null; }
            const signature = JSON.stringify({ ...context, requestId: null }), key = `${event}:${context.action || ""}`;
            if (dedupe && traceLast.get(key) === signature) return;
            traceLast.set(key, signature);
            const entry = { event, at: Date.now(), context }; traceRing.push(entry); traceQueue.push(entry);
            if (traceRing.length > 80) traceRing.shift(); if (traceQueue.length > 80) traceQueue.shift();
            try { window.localStorage?.setItem(traceKey, JSON.stringify(traceRing)); } catch (_) {}
            if (traceTimer === undefined) traceTimer = window.setTimeout(flushTrace,400);
        } catch (_) { /* Diagnostics must never interrupt the tool. */ }
    }
    function flushTrace() {
        traceTimer = undefined;
        try {
            if (!traceQueue.length || typeof window.adsk?.fusionSendData !== "function") return;
            const entries = traceQueue.splice(0,10), requestId = `pattern-trace-${++traceSerial}`;
            while (entries.length > 1 && JSON.stringify({ protocol:1,requestId,entries }).length > 15000) traceQueue.unshift(entries.pop());
            Promise.resolve().then(() => window.adsk.fusionSendData("diagnostic_log",JSON.stringify({ protocol:1,requestId,entries }))).catch(() => {});
            if (traceQueue.length) traceTimer = window.setTimeout(flushTrace,400);
        } catch (_) {}
    }
    function traceSnapshot(snapshot) {
        return { nativePhase: ["idle","selecting","picking_faces","ready","computing","preview","opening","error","created","cancelled"].includes(snapshot?.phase) ? snapshot.phase : "invalid",
            nativeRevision: Number.isInteger(snapshot?.revision) ? snapshot.revision : null, nativeSelected: !!snapshot?.selections?.surface?.selected };
    }
    if (typeof window.addEventListener === "function") {
        window.addEventListener("error", event => trace("browser_error", { name: event.error?.name || "Error", line: event.lineno || 0, column: event.colno || 0 }));
        window.addEventListener("unhandledrejection", event => trace("unhandled_rejection", { name: event.reason?.name || "Error" }));
    }
    document.addEventListener("pointerdown", event => {
        const target = event.target?.closest?.("button,select") || event.target;
        if (["begin-pattern-button","edit-pattern-button","preview-pattern-button","create-pattern-button","cancel-pattern-button","pattern-select-surface","pattern-add-face"].includes(target?.id) || state.selected && target?.id === "tool-select")
            trace("pointerdown", { control:target.id,disabled:!!target.disabled,toolLocked:$("tool-select").disabled,pickLocked:$("pattern-select-surface").disabled,createLocked:$("create-pattern-button").disabled });
    },true);

    function message(text, error = false) {
        $("pattern-operation-status").textContent = text;
        $("pattern-operation-status").classList.toggle("error", error);
        $("pattern-operation-status").hidden = !text || (!error && !/created|rebuilt|cancelled|Starting|Creating|Rebuilding|Export|^\d+ cells\b/i.test(text));
    }
    function cancelTimer() { if (timer !== undefined) window.clearTimeout(timer); timer = undefined; }
    function recoverySession() {
        if (previewRequest && !previewRequest.done) return previewRequest.sessionId;
        return state.session?.phase === "computing" ? identity() : null;
    }
    function scheduleRecovery() {
        if (!recoverySession()) {
            if (recoveryTimer !== undefined) window.clearTimeout(recoveryTimer);
            recoveryTimer = undefined; return;
        }
        if (recoveryTimer !== undefined || recoveryFlight) return;
        recoveryTimer = window.setTimeout(async () => {
            recoveryTimer = undefined;
            const sessionId = recoverySession(); if (!sessionId) return;
            const flight = {}; recoveryFlight = flight;
            try { await send("pattern_status", {}, sessionId); }
            catch (_) {
                if (recoverySession() === sessionId) { state.connectionError = true; render(); }
            }
            finally { if (recoveryFlight === flight) recoveryFlight = undefined; scheduleRecovery(); }
        }, 2000);
    }
    function completePreview(snapshot, previous) {
        const waiting = previewRequest, sessionId = snapshot.sessionId || previous?.sessionId;
        if (waiting && !waiting.done && sessionId === waiting.sessionId && snapshot.revision >= waiting.revision
                && ["preview", "error", "cancelled"].includes(snapshot.phase)) {
            trace("preview_settled_from_state", { requestId: waiting.requestId, requestedRevision: waiting.revision, ...traceSnapshot(snapshot) });
            waiting.done = true; waiting.resolve(snapshot);
        }
    }
    function sync() {
        for (const input of $("pattern-settings").querySelectorAll("[name]")) { input.value = state.settings[input.name]; input.setCustomValidity(""); }
        $("pattern-cell_size_mm").value = Number((state.settings.pitch_mm-state.settings.web_mm).toFixed(6));
        if (state.settings.layout_mode === "auto" && !state.settings.size_locked && Number.isFinite(state.session?.suggestedSizeMm) && state.session.suggestedSizeMm > 0)
            $("pattern-cell_size_mm").value = Number(state.session.suggestedSizeMm.toFixed(6));
        $("pattern-cell_size_mm").setCustomValidity("");
        renderArt();
    }
    function renderArt() { $("pattern-illustration").innerHTML = window.PartelierIllustrations.renderPattern(state.settings); }
    function availability(committing) {
        const isGrille=grille();
        if (showingGrilles !== isGrille) {
            const input=$("pattern-pattern"); input.replaceChildren();
            for (const [value,text] of optionsFor("pattern")) { const option=document.createElement("option"); option.value=value; option.textContent=text; input.append(option); }
            input.value=state.settings.pattern; showingGrilles=isGrille;
        }
        $("pattern-pattern").parentElement.children[0].textContent=isGrille?"Grille type":"Pattern";
        $("pattern-pattern").parentElement.classList.toggle("full-width-parameter",isGrille);
        const direction=$("pattern-rotation_deg").parentElement, directionHome=$(isGrille?"pattern-design-fields":"pattern-placement-fields");
        if(direction.parentElement!==directionHome)directionHome.append(direction);
        direction.children[0].textContent=isGrille?"Direction (°)":"Rotation (°)";
        direction.classList.toggle("full-width-parameter",isGrille);
        $("grille-direction-presets").hidden=!isGrille;
        for(const angle of [0,45,90]) {
            const button=$("grille-direction-"+angle), selected=Number.isFinite(state.settings.rotation_deg)&&Math.abs(((state.settings.rotation_deg%360)+360)%360-angle)<1e-8;
            button.disabled=committing;button.classList.toggle("selected",selected);button.setAttribute("aria-pressed",String(selected));
        }
        for (const name of ["mode","layout_mode","edge_mode"]) { const input=$("pattern-"+name); input.parentElement.hidden=isGrille; }
        const raised=isGrille && state.settings.grille_profile!=="flat";
        const mounting=isGrille && state.settings.mount_mode!=="off";
        $("pattern-mounting").hidden=!isGrille;
        $("pattern-mount_mode").parentElement.classList.toggle("full-width-parameter",true);
        $("pattern-mount_screw").parentElement.hidden=!mounting;
        $("pattern-mount-options").hidden=!mounting;
        $("pattern-mount-summary").hidden=!mounting;
        if(mounting) {
            const sizes={M3:[3,6.72],M4:[4,8.96],M5:[5,11.2],M6:[6,13.44]},size=sizes[state.settings.mount_screw];
            const hole=size?.[0]+state.settings.mount_clearance_mm,head=(state.settings.mount_head_mm || size?.[1])*(1+state.settings.mount_head_extra_percent/100);
            const inset=state.settings.mount_inset_mm || head/2+1.7,fmt=value=>Number(value.toFixed(2));
            $("pattern-mount-summary").textContent=Number.isFinite(hole+head+inset)
                ? `4 corners · Ø${fmt(hole)} mm`+(state.settings.mount_mode==="countersink"?` · 90° seat Ø${fmt(head)} mm · depth ${fmt((head-hole)/2)} mm`:"")+` · centre inset ${fmt(inset)} mm. Preview checks the plate thickness and frame.`
                : "Check the mounting settings.";
        }
        $("pattern-grille_profile").parentElement.hidden=!isGrille;
        $("pattern-grille_profile").parentElement.classList.toggle("full-width-parameter",isGrille);
        $("pattern-grille_height_mm").parentElement.hidden=!raised;
        $("pattern-louver_angle_deg").parentElement.hidden=state.settings.pattern!=="grille_louver" || raised;
        $("pattern-offset_u_mm").parentElement.hidden=isGrille;
        for (const input of $("pattern-settings").querySelectorAll("[name]")) input.disabled = committing;
        const depth = $("pattern-depth_mm"), through = state.settings.mode === "through";
        depth.disabled = committing || through; depth.parentElement.hidden = through;
        if (through && (!Number.isFinite(state.settings.depth_mm) || state.settings.depth_mm <= 0)) {
            state.settings.depth_mm = defaults.depth_mm; depth.value = defaults.depth_mm; depth.setCustomValidity("");
        }
        $("pattern-selection_scope").disabled = committing || editing();
        if(raised || mounting) $("pattern-selection_scope").disabled=true;
        $("pattern-scope-note").hidden = !editing();
        for (const name of ["density", "size_locked"]) {
            const control = $("pattern-"+name); control.parentElement.hidden = state.settings.layout_mode !== "auto";
            control.disabled = committing || state.settings.layout_mode !== "auto";
        }
        $("pattern-pitch_mm").parentElement.children[0].textContent = "Pitch";
        $("pattern-pitch_mm").title = state.settings.layout_mode === "fit" ? "Automatic spacing adjusts this target to balance coverage of each face." : "Use this exact distance between repeated features.";
        const sized = true, size = $("pattern-cell_size_mm");
        $("pattern-pitch_mm").parentElement.hidden = sized;
        size.parentElement.hidden = !sized; size.disabled = committing || !sized;
        size.parentElement.children[0].textContent = isGrille ? "Opening width" : "Cell size";
        $("pattern-web_mm").parentElement.children[0].textContent = isGrille ? "Rib width · on face" : "Minimum gap";
        $("pattern-layout-note").textContent = state.settings.layout_mode === "auto"
            ? state.settings.size_locked ? "Το μέγεθος κλειδώθηκε · προσαρμόζονται οι αποστάσεις." : "Αυτόματη πρόταση μεγέθους και πλήθους. Άλλαξε το Cell size για να το κλειδώσεις."
            : state.settings.layout_mode === "fill"
            ? "Σταθερό μέγεθος · γέμισμα μέχρι το border. Έως 200/face."
            : state.settings.layout_mode === "balanced" ? "Σταθερό μέγεθος · έως 48/face, με μεγαλύτερα κενά όπου χρειάζεται."
            : "Το Automatic size προσαρμόζει το μέγεθος· το Exact pitch το διατηρεί.";
        $("pattern-depth_mm").parentElement.children[0].textContent = state.settings.mode === "inlay" ? "Colour depth" : "Depth / height";
        if(isGrille) $("pattern-layout-note").textContent="Επίπεδες επιφάνειες · σταθερό άνοιγμα και πλάτος νεύρου. Rotation αλλάζει την κατεύθυνση. Οι περσίδες χρειάζονται ορθογώνια πλάκα σταθερού πάχους.";
        if(raised) $("pattern-layout-note").textContent="Πίσω πλευρά στο bed · ένα ορθογώνιο face πλάκας σταθερού πάχους. Έως 200 ανοίγματα. Οι εξωτερικές περσίδες χτίζονται στις 45°. Το Height μετριέται πάνω από το face.";
        if(state.settings.mode==="inlay") $("pattern-layout-note").textContent += " Flat colour: επίπεδη επιφάνεια, ξεχωριστό μέρος για χρωματισμό. Το βάθος πρέπει να αφήνει υλικό από κάτω.";
    }
    function renderSelection() {
        const picking = !!state.session?.pickingFaces;
        const body = state.settings.selection_scope === "body", target = editing() ? "edit_target" : body ? "body" : "faces";
        const picked = state.session?.selections?.surface;
        const caption = editing() ? "Pattern result" : body ? "Body" : picked?.selected ? "Replace faces" : "Faces";
        const button = document.createElement("button"); button.id = "pattern-select-surface"; button.type = "button"; button.className = "selection-button";
        button.disabled = !supported() || !identity() || state.busy || picking || state.session?.phase === "opening";
        const label = document.createElement("strong"); label.textContent = caption;
        const value = document.createElement("span"); value.textContent = picked?.selected ? picked.label || "Selected" : "Pick";
        button.setAttribute("aria-label", `${caption}: ${picked?.selected ? picked.label || "Selected" : "not selected"}`);
        button.classList.toggle("is-selected", !!picked?.selected); button.append(label, value);
        button.addEventListener("click", () => { trace("click", { control:"surface",target }); cancelTimer(); run(async () => { await sessionAction("pattern_focus", { target }); await refresh(); },"pattern_focus"); });
        $("pattern-selections").replaceChildren(button);
        if (picking) {
            const done = document.createElement("button"); done.id = "pattern-finish-faces"; done.type = "button"; done.className = "create-button"; done.textContent = "Done · update preview";
            done.disabled = state.busy || !state.session.canFinishFaces;
            done.addEventListener("click", () => { cancelTimer(); run(async () => { await sessionAction("pattern_finish_faces"); await refresh(); },"pattern_finish_faces"); });
            $("pattern-selections").append(done);
            const clear = document.createElement("button"); clear.id = "pattern-clear-faces"; clear.type = "button"; clear.className = "selection-button"; clear.textContent = "Clear selection";
            clear.disabled = state.busy || !picked?.selected;
            clear.addEventListener("click", () => { cancelTimer(); run(() => sessionAction("pattern_clear_faces"),"pattern_clear_faces"); });
            $("pattern-selections").append(clear);
        } else if (!editing() && !body && picked?.selected && identity()) {
            const add = document.createElement("button"); add.id = "pattern-add-face"; add.type = "button"; add.className = "selection-button"; add.textContent = "Add faces"; add.disabled = button.disabled;
            add.addEventListener("click", () => { trace("click", { control:"add_face",target:"add_face" }); cancelTimer(); run(async () => { await sessionAction("pattern_focus", { target:"add_face" }); await refresh(); },"pattern_focus"); });
            $("pattern-selections").append(add);
        }
        $("pattern-selection-help").textContent = picking ? "Click sides to add them. Selected faces stay blue. Done updates preview. Clear selection starts over." : editing() ? "Pick a saved Partelier pattern." : body ? "Pick one body. Preview updates automatically." : picked?.selected ? "Add faces keeps your selection. Click more sides, then Done to update preview." : "Select all the sides you need, then Done to preview.";
        $("pattern-selection-help").hidden = (editing() || body) && !!identity() && selected() && !(state.busy && state.session?.phase === "selecting");
        if(grille() && (state.settings.grille_profile!=="flat" || state.settings.mount_mode!=="off") && !editing())
            $("pattern-selection-help").textContent="Select one rectangular plate face, then Done. The opposite flat back rests on the bed.";
        $("begin-pattern-button").textContent = body ? "Select body" : "Select faces";
    }
    function render() {
        const picking = !!state.session?.pickingFaces;
        const committing = state.session?.phase === "opening", busy = state.busy || committing, hasSession = active(), ready = !!identity() && selected();
        if (state.connectionError) message("Fusion status is not responding. Computation may still be running. Waiting to reconnect…", true);
        $("pattern-tool").hidden = !state.selected; $("pattern-action-dock").hidden = !state.selected;
        $("tool-select").disabled = hasSession || busy || otherActive();
        availability(committing || picking);
        $("pattern-settings").setAttribute("aria-busy", String(committing));
        $("begin-pattern-button").hidden = hasSession;
        $("begin-pattern-button").disabled = !state.selected || !supported() || !valid() || busy || hasSession || otherActive();
        $("edit-pattern-button").disabled = !state.selected || !supported() || !state.capabilities.has("pattern-edit") || busy || hasSession || otherActive();
        $("preview-pattern-button").hidden = picking || !ready || (!state.liveError && current());
        $("preview-pattern-button").disabled = picking || !ready || !valid() || busy;
        $("cancel-pattern-button").disabled = !identity() || busy;
        $("create-pattern-button").disabled = picking || !state.selected || !supported() || !valid() || busy || !ready || !current();
        $("create-pattern-button").textContent = editing() ? grille() ? "Rebuild grille" : "Rebuild pattern" : grille() ? "Create grille" : "Create pattern";
        $("export-pattern-button").hidden=grille() || state.settings.mode!=="inlay";
        $("export-pattern-button").disabled=!supported() || !state.capabilities.has("pattern-colour-export") || hasSession || busy || otherActive();
        $("pattern-availability").hidden = supported();
        $("pattern-availability").textContent = state.connected ? "Restart Partelier to enable surface patterns." : "Open Partelier in Fusion to select geometry.";
        const label = !supported() ? "Fusion required" : picking ? "select faces · click Done" : state.connectionError ? "connection needs attention" : busy && (state.expecting || state.session?.phase === "selecting") ? "selecting surfaces" : !ready ? "waiting for geometry" : !valid() ? "check inputs" : state.liveError || state.session?.phase === "error" ? "needs attention" : committing ? "creating" : current() ? "up to date" : busy || timer !== undefined || queued || state.session?.phase === "computing" ? "updating…" : "refresh needed";
        $("pattern-live-preview-status").textContent = `Live preview · ${label}`;
        $("pattern-live-preview-status").classList.toggle("is-current", ready && current());
        $("pattern-live-preview-status").classList.toggle("needs-attention", state.connectionError || ready && (!valid() || state.liveError || state.session?.phase === "error"));
        renderSelection(); scheduleRecovery();
        trace("locks", { toolLocked:$("tool-select").disabled, pickLocked:$("pattern-select-surface").disabled, cancelLocked:$("cancel-pattern-button").disabled, createLocked:$("create-pattern-button").disabled, supported:supported() },true);
    }
    function apply(snapshot) {
        const reject = reason => { trace("state_rejected", { reason,...traceSnapshot(snapshot) },true); return false; };
        if (!snapshot || !Number.isInteger(snapshot.revision) || typeof snapshot.phase !== "string") return reject("malformed");
        const previous = state.session;
        if (snapshot.sessionId && retired.has(snapshot.sessionId)) return reject("retired_session");
        if (snapshot.sessionId && previous?.sessionId && snapshot.sessionId !== previous.sessionId && active() && !state.expecting) return reject("other_session");
        if (snapshot.sessionId && snapshot.sessionId === previous?.sessionId && snapshot.revision < previous.revision) return reject("older_revision");
        if (snapshot.sessionId && snapshot.sessionId === previous?.sessionId && snapshot.revision === previous.revision) {
            if (["preview", "error"].includes(previous.phase) && ["computing", "ready", "selecting"].includes(snapshot.phase)) return reject("completed_revision");
            if (previous.phase === "opening" && !["opening", "created", "error", "cancelled"].includes(snapshot.phase)) return reject("commit_in_progress");
        }
        const newerEdits = snapshot.revision < state.revision;
        if (!snapshot.sessionId || terminal.has(snapshot.phase)) { if (previous?.sessionId) retired.add(previous.sessionId); if (snapshot.sessionId) retired.add(snapshot.sessionId); }
        state.session = snapshot; state.connectionError = false;
        trace("state_applied", traceSnapshot(snapshot),true);
        if (snapshot.sessionId) state.expecting = false;
        if (!newerEdits && ["preview", "error"].includes(snapshot.phase)) state.liveError = snapshot.phase === "error";
        if (!newerEdits && snapshot.settings) { state.settings = { ...defaults, ...snapshot.settings }; state.revision = snapshot.revision; sync(); }
        if (newerEdits && ["preview", "error"].includes(snapshot.phase)) message("Updating live preview…");
        else message(snapshot.message || "", snapshot.phase === "error");
        completePreview(snapshot, previous);
        render(); return true;
    }
    async function send(action, payload = {}, recoveryId = null) {
        const requestId = `pattern-ui-${++serial}`, version = pushedVersion;
        trace("send_start", { action,requestId,sentRevision:payload.revision ?? null },action==="pattern_status");
        const response = Promise.resolve().then(() => window.adsk.fusionSendData(action, JSON.stringify({ protocol: 1, requestId, ...payload })))
            .then(raw => { trace("send_ack", { action,requestId },action==="pattern_status"); return raw; },error => { trace("bridge_error", { action,requestId,name:error?.name || "Error" },action==="pattern_status"); throw error; });
        let timeout, raw, waiting, completion;
        if (action === "pattern_preview") {
            completion = new Promise(resolve => {
                waiting = { sessionId: payload.sessionId, revision: payload.revision, requestId, done: false,
                    resolve: snapshot => resolve(JSON.stringify({ protocol: 1, requestId, ok: true, patternState: snapshot })) };
                previewRequest = waiting;
            });
            scheduleRecovery();
        }
        try {
            if (completion) raw = await Promise.race([response, completion]);
            else if (["pattern_begin", "pattern_focus", "pattern_commit", "pattern_export"].includes(action)) raw = await response;
            else raw = await Promise.race([response, new Promise((_, reject) => { timeout = window.setTimeout(() => { trace("send_timeout", { action,requestId },action==="pattern_status"); reject(new Error("Fusion did not respond. Stop and Run Partelier, then try again.")); }, recoveryId ? 5000 : 30000); })]);
        } catch (error) { trace("send_error", { action,requestId,name:error?.name || "Error" },action==="pattern_status"); throw error;
        } finally {
            if (timeout !== undefined) window.clearTimeout(timeout);
            if (previewRequest === waiting) previewRequest = undefined;
        }
        let result;
        try { result = JSON.parse(raw); } catch (error) { trace("send_parse_error", { action,requestId,name:error?.name || "Error" }); throw error; }
        if (result.protocol !== 1 || result.requestId !== requestId || !result.ok) { trace("send_rejected", { action,requestId,ok:result.ok === true }); throw new Error(result.message || "Fusion returned an unexpected response."); }
        if (result.patternState) {
            const snapshot = result.patternState, newSession = action === "pattern_begin" && state.expecting && snapshot.sessionId;
            if (recoveryId && (state.session?.sessionId !== recoveryId || retired.has(recoveryId)
                    || (snapshot.sessionId && snapshot.sessionId !== recoveryId))) { trace("state_rejected", { reason:"obsolete_status",...traceSnapshot(snapshot) },true); return result; }
            if (!(pushedVersion !== version && !newSession && snapshot.revision <= (state.session?.revision ?? -1))) apply(snapshot);
            else trace("state_rejected", { reason:"newer_push",...traceSnapshot(snapshot) },true);
        }
        return result;
    }
    function run(task, action = "pattern_action") {
        pending++; state.busy = true; render();
        trace("action_queued", { action }); let failed = false;
        const running = actions.then(() => { trace("action_start", { action }); return task(); });
        actions = running.catch(error => { failed = true; trace("action_error", { action,name:error.name || "Error" }); state.liveError = true; message(error.message, true); });
        return actions.finally(() => { pending--; state.busy = pending > 0; trace("action_end", { action,ok:!failed }); render(); });
    }
    function sessionAction(action, extra = {}) {
        const sessionId = identity(); if (!sessionId) throw new Error("Start a pattern geometry session first.");
        const payload = { sessionId, ...extra };
        if (action === "pattern_focus") { state.session = { ...state.session, phase: "selecting", previewCurrent: false }; render(); }
        if (["pattern_update", "pattern_preview", "pattern_commit"].includes(action)) Object.assign(payload, { settings: { ...state.settings }, revision: state.revision });
        return send(action, payload);
    }
    async function refresh() {
        if (supported() && identity() && selected() && valid() && !state.session?.pickingFaces && state.session?.phase !== "opening") {
            state.liveError = false; state.session = { ...state.session, phase: "computing", previewCurrent: false };
            render(); await sessionAction("pattern_preview");
        }
    }
    function schedule() {
        cancelTimer(); if (!supported() || !identity() || !valid() || state.session?.pickingFaces || state.session?.phase === "opening") return;
        timer = window.setTimeout(() => {
            timer = undefined; if (queued) return; queued = true;
            run(async () => {
                queued = false; if (!identity() || !valid() || state.session?.phase === "opening") return;
                if (selected()) await refresh(); else { await sessionAction("pattern_update"); await refresh(); }
            },"live_preview");
        }, 160);
    }
    async function begin(edit) {
        if (!edit && !$("pattern-settings").reportValidity()) return;
        cancelTimer(); state.expecting = true; state.revision = 0; state.liveError = false; message("Starting surface selection in Fusion…");
        try { await send("pattern_begin", { settings: valid() ? { ...state.settings } : { ...defaults }, editing: edit }); }
        finally { state.expecting = false; }
        await refresh();
    }
    let helpTrigger;
    function addHelp(item, name, caption) {
        item.classList.add("has-parameter-help");
        const button = document.createElement("button"); button.type = "button"; button.id = `pattern-help-${name}`;
        button.className = "parameter-help"; button.textContent = "?";
        button.setAttribute("aria-label", `Βοήθεια: ${caption}`); button.setAttribute("aria-haspopup", "dialog");
        button.addEventListener("click", () => {
            const help = window.PartelierPatternHelp.get(name,state.settings); if (!help) return;
            helpTrigger = button;
            $("pattern-help-title").textContent = help.title;
            $("pattern-help-description").textContent = help.description;
            $("pattern-help-detail").textContent = help.detail;
            $("pattern-help-more").open = false;
            $("pattern-help-image").innerHTML = help.image;
            if (!$("pattern-parameter-help").open) $("pattern-parameter-help").showModal();
        });
        item.append(button);
    }
    $("pattern-help-close").addEventListener("click", () => $("pattern-parameter-help").close());
    $("pattern-parameter-help").addEventListener("close", () => { if (helpTrigger) helpTrigger.focus(); });
    $("pattern-parameter-help").addEventListener("click", event => {
        if (event.target !== $("pattern-parameter-help")) return;
        const rect = event.target.getBoundingClientRect();
        if (event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom) event.target.close();
    });
    for (const [name, caption, container] of [["pattern", "Pattern", "pattern-design-fields"], ["grille_profile", "Profile", "pattern-design-fields"], ["mount_mode", "Mounting holes", "pattern-mount-controls"], ["mount_screw", "Screw size", "pattern-mount-controls"], ["mode", "Action", "pattern-design-fields"], ["layout_mode", "Layout", "pattern-size-fields"], ["density", "Density", "pattern-size-fields"], ["size_locked", "Size", "pattern-size-fields"], ["selection_scope", "Apply to", "pattern-scope-fields"], ["edge_mode", "Edge cells", "pattern-scope-fields"]]) {
        const item = document.createElement("div"); item.className = "parameter-item";
        const label = document.createElement("label"); label.htmlFor = `pattern-${name}`; label.textContent = caption;
        const input = document.createElement("select"); input.id = `pattern-${name}`; input.name = name; input.required = true;
        for (const [value, text] of choices[name]) { const option = document.createElement("option"); option.value = value; option.textContent = text; input.append(option); }
        input.value = defaults[name]; item.append(label, input); addHelp(item,name,caption); $(container).append(item);
    }
    for (const [container, fields] of [["pattern-size-fields", [["cell_size_mm", "Cell size"], ["pitch_mm", "Pitch"], ["web_mm", "Minimum gap"], ["border_mm", "Border"], ["depth_mm", "Relief height"], ["louver_angle_deg", "Louver tilt (°)"], ["grille_height_mm", "Height above face (mm)"]]], ["pattern-mount-fields", [["mount_clearance_mm","Hole allowance (mm)"],["mount_head_extra_percent","Head allowance (%)"],["mount_head_mm","Head Ø · 0 = Auto (mm)"],["mount_inset_mm","Edge to centre · 0 = Auto (mm)"]]], ["pattern-placement-fields", [["rotation_deg", "Rotation (°)"], ["offset_u_mm", "U offset (mm)"], ["offset_v_mm", "V offset (mm)"]]]]) {
        for (const [name, caption] of fields) {
            const item = document.createElement("div"); item.className = "parameter-item";
            const label = document.createElement("label"); label.htmlFor = `pattern-${name}`; label.textContent = caption;
            const input = document.createElement("input"); input.id = `pattern-${name}`; if (name !== "cell_size_mm") input.name = name; input.type = "number"; input.required = true; input.step = "any";
            if (!signed.has(name)) input.min = "0";
            if (name === "louver_angle_deg") input.max="60";
            if (name === "grille_height_mm") {input.min="0.2";input.max="20";}
            if (name.startsWith("mount_")) input.max=({mount_clearance_mm:2,mount_head_extra_percent:30,mount_head_mm:40,mount_inset_mm:1000})[name];
            input.value = name === "cell_size_mm" ? defaults.pitch_mm-defaults.web_mm : defaults[name]; item.append(label, input); addHelp(item,name,caption); $(container).append(item);
            if(name==="rotation_deg") {
                const presets=document.createElement("div");presets.id="grille-direction-presets";presets.className="grille-direction-presets";presets.setAttribute("role","group");presets.setAttribute("aria-label","Grille direction presets");
                for(const angle of [0,45,90]) {
                    const button=document.createElement("button");button.id="grille-direction-"+angle;button.type="button";button.textContent=angle+"°";
                    button.addEventListener("click",()=>{if(button.disabled)return;input.value=String(angle);updateInput(input);});presets.append(button);
                }
                item.append(presets);
            }
        }
    }
    $("pattern-settings").addEventListener("submit", event => event.preventDefault());
    $("pattern-settings").addEventListener("input", event => updateInput(event.target));
    function updateInput(input) {
        const sized = true;
        if (input.id === "pattern-cell_size_mm") {
            const size = Number(input.value), okay = input.value.trim() !== "" && Number.isFinite(size) && size > 0;
            input.setCustomValidity(okay ? "" : "Enter a cell size greater than zero.");
            const pitch = $("pattern-pitch_mm"); pitch.value = okay ? Number((size+state.settings.web_mm).toFixed(6)) : "";
            pitch.setCustomValidity(okay ? "" : "Enter a cell size greater than zero.");
            state.settings.pitch_mm = okay ? size+state.settings.web_mm : NaN;
            if (state.settings.layout_mode === "auto") { state.settings.size_locked = true; $("pattern-size_locked").value = "true"; }
        } else if (!Object.prototype.hasOwnProperty.call(defaults, input.name)) return;
        const numeric = Number(input.value); trace("input", { name:input.name,value:input.type === "number" ? input.value.trim() && Number.isFinite(numeric) && Math.abs(numeric)<1e12 ? numeric : null : optionsFor(input.name)?.some(([value])=>value===input.value) ? input.value : "unsupported" });
        if (input.name === "selection_scope" && editing()) { input.value = state.settings.selection_scope; message("Create a new pattern to change between selected faces and a whole body.", true); return; }
        if (input.id === "pattern-cell_size_mm") { /* Derived locally; the host retains its strict snapshot contract. */ }
        else if (input.type === "number") {
            const value = Number(input.value), zeroAllowed = ["border_mm","louver_angle_deg","mount_clearance_mm","mount_head_extra_percent","mount_head_mm","mount_inset_mm"].includes(input.name);
            const okay = input.value.trim() !== "" && Number.isFinite(value) && (signed.has(input.name) || (zeroAllowed ? value >= 0 : value > 0));
            if (input.name === "web_mm" && sized && okay && $("pattern-cell_size_mm").checkValidity()) {
                state.settings.pitch_mm = Number((Number($("pattern-cell_size_mm").value)+value).toFixed(6));
                $("pattern-pitch_mm").value = state.settings.pitch_mm;
                $("pattern-pitch_mm").setCustomValidity("");
            }
            input.setCustomValidity(okay ? "" : signed.has(input.name) ? "Enter a finite number." : zeroAllowed ? "Enter zero or a positive number." : "Enter a number greater than zero."); state.settings[input.name] = value;
        } else {
            input.setCustomValidity(optionsFor(input.name).some(([value]) => value === input.value) ? "" : "Choose a supported option.");
            if (input.name === "selection_scope" && input.value !== state.settings.selection_scope && active()) state.session = { ...state.session, selections: {} };
            if (input.name === "size_locked" && input.value === "true" && $("pattern-cell_size_mm").checkValidity()) {
                state.settings.pitch_mm = Number($("pattern-cell_size_mm").value)+state.settings.web_mm;
                $("pattern-pitch_mm").value = state.settings.pitch_mm;
            }
            if (input.name === "size_locked" && input.value === "false") {
                const field = $("pattern-cell_size_mm"), currentSize = Number(field.value);
                const size = field.value.trim() && Number.isFinite(currentSize) && currentSize > 0 ? currentSize
                    : defaults.pitch_mm-defaults.web_mm;
                state.settings.pitch_mm = size+state.settings.web_mm;
                field.setCustomValidity(""); $("pattern-pitch_mm").setCustomValidity("");
                $("pattern-pitch_mm").value = state.settings.pitch_mm;
            }
            state.settings[input.name] = input.name === "size_locked" ? input.value === "true" : input.value;
            if((input.name==="grille_profile" && input.value!=="flat" || input.name==="mount_mode" && input.value!=="off") && !editing()) {
                state.settings.selection_scope="faces"; $("pattern-selection_scope").value="faces";
            }
        }
        if (input.id !== "pattern-cell_size_mm" && (input.name !== "web_mm" || !sized))
            $("pattern-cell_size_mm").value = Number((state.settings.pitch_mm-state.settings.web_mm).toFixed(6));
        state.revision++; state.dirty = true; state.liveError = false; availability(false); renderArt();
        if (active()) message(valid() ? "Updating live preview…" : "Check the highlighted input. Showing the previous valid preview.", !valid());
        render(); schedule();
    }
    $("export-pattern-button").addEventListener("click", () => run(async () => { const result=await send("pattern_export"); message(result.message || "Export finished."); },"pattern_export"));
    $("begin-pattern-button").addEventListener("click", () => { trace("click", { control:"begin" }); run(() => begin(false),"pattern_begin"); });
    $("edit-pattern-button").addEventListener("click", () => { trace("click", { control:"edit" }); run(() => begin(true),"pattern_edit"); });
    $("preview-pattern-button").addEventListener("click", () => { trace("click", { control:"refresh" }); if ($("pattern-settings").reportValidity()) { cancelTimer(); run(refresh,"pattern_preview"); } });
    $("create-pattern-button").addEventListener("click", () => { trace("click", { control:"commit" }); if ($("pattern-settings").reportValidity()) { cancelTimer(); run(() => sessionAction("pattern_commit"),"pattern_commit"); } });
    $("cancel-pattern-button").addEventListener("click", () => { trace("click", { control:"cancel" }); cancelTimer(); run(() => sessionAction("pattern_cancel"),"pattern_cancel"); });
    window.PartelierPatterns = Object.freeze({
        isActive() { return active(); },
        isBusy() { return state.busy || state.session?.phase === "opening"; },
        matches(id) { return Object.prototype.hasOwnProperty.call(presets, id); },
        select(id) {
            state.selected = this.matches(id);
            trace("tool_selected", { alias:state.selected ? id : "other" },true);
            if (state.selected && state.alias !== id && !active() && !otherActive()) { Object.assign(state.settings, grille() !== (id === "grilles") ? defaults : {}, presets[id]); state.revision = 0; state.liveError = false; sync(); }
            state.alias = state.selected ? id : null; render();
        },
        setOtherActive(values) { Object.assign(state.others, values); render(); },
        connect(result) {
            state.connected = true; state.capabilities = new Set(Array.isArray(result.capabilities) ? result.capabilities : []);
            trace("connected", { patternPalette:supported() });
            if (!state.dirty && result.patternDefaults && !result.patternState?.settings) { state.settings = { ...defaults, ...result.patternDefaults }; sync(); }
            for (const [key, snapshot] of [["hinge", result.hingeState], ["snap", result.snapState]]) if (snapshot) state.others[key] = !!snapshot.sessionId && !terminal.has(snapshot.phase);
            if (result.patternState) apply(result.patternState);
            renderArt(); render(); if (identity() && selected() && !current()) schedule();
            return active() ? grille() ? "grilles" : state.settings.pattern === "hexagon" ? "honeycomb" : state.settings.mode === "emboss" ? "knurl" : "perforation" : null;
        },
        handle(action, raw) { if (action !== "pattern_state") return false; try { const snapshot = JSON.parse(raw); trace("push_received",traceSnapshot(snapshot),true); if (apply(snapshot)) pushedVersion++; } catch (error) { trace("push_error", { name:error.name || "Error" }); throw error; } return true; }
    });
    trace("boot", { build:"0.16.0" }); renderArt(); render();
})();

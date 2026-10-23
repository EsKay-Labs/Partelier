"use strict";

// One pattern session serves the honeycomb, perforation and texture presets.
(() => {
    const $ = id => document.getElementById(id);
    const defaults = Object.freeze({ pattern: "hexagon", mode: "through", pitch_mm: 8, web_mm: 1.2, depth_mm: 1, border_mm: 2, rotation_deg: 0, offset_u_mm: 0, offset_v_mm: 0, selection_scope: "faces", layout_mode: "fit" });
    const presets = { honeycomb: { pattern: "hexagon", mode: "through" }, perforation: { pattern: "circle", mode: "through" }, knurl: { pattern: "diamond", mode: "emboss" } };
    const choices = {
        pattern: [["hexagon", "Hexagons"], ["circle", "Circles"], ["diamond", "Diamonds"], ["square", "Squares"], ["slot", "Slots"]],
        mode: [["through", "Through holes"], ["engrave", "Engrave"], ["emboss", "Emboss"]],
        layout_mode: [["fit", "Automatic"], ["fixed", "Exact pitch"]],
        selection_scope: [["faces", "Selected faces"], ["body", "Whole body"]]
    };
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

    function message(text, error = false) {
        $("pattern-operation-status").textContent = text;
        $("pattern-operation-status").classList.toggle("error", error);
        $("pattern-operation-status").hidden = !text || (!error && !/created|rebuilt|cancelled|Starting|Creating|Rebuilding|^\d+ cells\b/i.test(text));
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
            waiting.done = true; waiting.resolve(snapshot);
        }
    }
    function sync() {
        for (const input of $("pattern-settings").querySelectorAll("[name]")) { input.value = state.settings[input.name]; input.setCustomValidity(""); }
        renderArt();
    }
    function renderArt() { $("pattern-illustration").innerHTML = window.PartelierIllustrations.renderPattern(state.settings); }
    function availability(committing) {
        for (const input of $("pattern-settings").querySelectorAll("[name]")) input.disabled = committing;
        const depth = $("pattern-depth_mm"), through = state.settings.mode === "through";
        depth.disabled = committing || through; depth.parentElement.hidden = through;
        if (through && (!Number.isFinite(state.settings.depth_mm) || state.settings.depth_mm <= 0)) {
            state.settings.depth_mm = defaults.depth_mm; depth.value = defaults.depth_mm; depth.setCustomValidity("");
        }
        $("pattern-selection_scope").disabled = committing || editing();
        $("pattern-scope-note").hidden = !editing();
        $("pattern-pitch_mm").parentElement.children[0].textContent = state.settings.layout_mode === "fit" ? "Target pitch" : "Pitch";
        $("pattern-pitch_mm").title = state.settings.layout_mode === "fit" ? "Automatic spacing adjusts this target to balance coverage of each face." : "Use this exact distance between repeated features.";
        $("pattern-web_mm").parentElement.children[0].textContent = state.settings.mode === "emboss" ? "Gap between features" : "Solid web";
        $("pattern-depth_mm").parentElement.children[0].textContent = state.settings.mode === "engrave" ? "Engraving depth" : "Relief height";
    }
    function renderSelection() {
        const body = state.settings.selection_scope === "body", target = editing() ? "edit_target" : body ? "body" : "faces";
        const caption = editing() ? "Pattern result" : body ? "Body" : "Faces";
        const picked = state.session?.selections?.surface;
        const button = document.createElement("button"); button.id = "pattern-select-surface"; button.type = "button"; button.className = "selection-button";
        button.disabled = !supported() || !identity() || state.busy || state.session?.phase === "opening";
        const label = document.createElement("strong"); label.textContent = caption;
        const value = document.createElement("span"); value.textContent = picked?.selected ? picked.label || "Selected" : "Pick";
        button.setAttribute("aria-label", `${caption}: ${picked?.selected ? picked.label || "Selected" : "not selected"}`);
        button.classList.toggle("is-selected", !!picked?.selected); button.append(label, value);
        button.addEventListener("click", () => { cancelTimer(); run(async () => { await sessionAction("pattern_focus", { target }); await refresh(); }); });
        $("pattern-selections").replaceChildren(button);
        $("pattern-selection-help").textContent = editing() ? "Pick a saved Partelier pattern. Esc stops picking." : body ? "Pick a body to pattern its supported faces." : "Pick one or more faces. Esc finishes the selection.";
        $("pattern-selection-help").hidden = !!identity() && selected();
        $("begin-pattern-button").textContent = body ? "Select body" : "Select faces";
    }
    function render() {
        const committing = state.session?.phase === "opening", busy = state.busy || committing, hasSession = active(), ready = !!identity() && selected();
        if (state.connectionError) message("Fusion status is not responding. Computation may still be running. Waiting to reconnect…", true);
        $("pattern-tool").hidden = !state.selected; $("pattern-action-dock").hidden = !state.selected;
        $("tool-select").disabled = hasSession || busy || otherActive();
        availability(committing);
        $("pattern-settings").setAttribute("aria-busy", String(committing));
        $("begin-pattern-button").hidden = hasSession;
        $("begin-pattern-button").disabled = !state.selected || !supported() || !valid() || busy || hasSession || otherActive();
        $("edit-pattern-button").disabled = !state.selected || !supported() || !state.capabilities.has("pattern-edit") || busy || hasSession || otherActive();
        $("preview-pattern-button").hidden = !ready || (!state.liveError && current());
        $("preview-pattern-button").disabled = !ready || !valid() || busy;
        $("cancel-pattern-button").disabled = !identity() || busy;
        $("create-pattern-button").disabled = !state.selected || !supported() || !valid() || busy || !ready || !current();
        $("create-pattern-button").textContent = editing() ? "Rebuild pattern" : "Create pattern";
        $("pattern-availability").hidden = supported();
        $("pattern-availability").textContent = state.connected ? "Restart Partelier to enable surface patterns." : "Open Partelier in Fusion to select geometry.";
        const label = !supported() ? "Fusion required" : state.connectionError ? "connection needs attention" : !ready ? "waiting for geometry" : !valid() ? "check inputs" : state.liveError || state.session?.phase === "error" ? "needs attention" : committing ? "creating" : current() ? "up to date" : busy || timer !== undefined || queued || state.session?.phase === "computing" ? "updating…" : "refresh needed";
        $("pattern-live-preview-status").textContent = `Live preview · ${label}`;
        $("pattern-live-preview-status").classList.toggle("is-current", ready && current());
        $("pattern-live-preview-status").classList.toggle("needs-attention", state.connectionError || ready && (!valid() || state.liveError || state.session?.phase === "error"));
        renderSelection(); scheduleRecovery();
    }
    function apply(snapshot) {
        if (!snapshot || !Number.isInteger(snapshot.revision) || typeof snapshot.phase !== "string") return false;
        const previous = state.session;
        if (snapshot.sessionId && retired.has(snapshot.sessionId)) return false;
        if (snapshot.sessionId && previous?.sessionId && snapshot.sessionId !== previous.sessionId && active() && !state.expecting) return false;
        if (snapshot.sessionId && snapshot.sessionId === previous?.sessionId && snapshot.revision < previous.revision) return false;
        if (snapshot.sessionId && snapshot.sessionId === previous?.sessionId && snapshot.revision === previous.revision) {
            if (["preview", "error"].includes(previous.phase) && ["computing", "ready", "selecting"].includes(snapshot.phase)) return false;
            if (previous.phase === "opening" && !["opening", "created", "error", "cancelled"].includes(snapshot.phase)) return false;
        }
        const newerEdits = snapshot.revision < state.revision;
        if (!snapshot.sessionId || terminal.has(snapshot.phase)) { if (previous?.sessionId) retired.add(previous.sessionId); if (snapshot.sessionId) retired.add(snapshot.sessionId); }
        state.session = snapshot; state.connectionError = false;
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
        const response = Promise.resolve().then(() => window.adsk.fusionSendData(action, JSON.stringify({ protocol: 1, requestId, ...payload })));
        let timeout, raw, waiting, completion;
        if (action === "pattern_preview") {
            completion = new Promise(resolve => {
                waiting = { sessionId: payload.sessionId, revision: payload.revision, done: false,
                    resolve: snapshot => resolve(JSON.stringify({ protocol: 1, requestId, ok: true, patternState: snapshot })) };
                previewRequest = waiting;
            });
            scheduleRecovery();
        }
        try {
            if (completion) raw = await Promise.race([response, completion]);
            else if (["pattern_begin", "pattern_focus", "pattern_commit"].includes(action)) raw = await response;
            else raw = await Promise.race([response, new Promise((_, reject) => { timeout = window.setTimeout(() => reject(new Error("Fusion did not respond. Stop and Run Partelier, then try again.")), recoveryId ? 5000 : 30000); })]);
        } finally {
            if (timeout !== undefined) window.clearTimeout(timeout);
            if (previewRequest === waiting) previewRequest = undefined;
        }
        const result = JSON.parse(raw);
        if (result.protocol !== 1 || result.requestId !== requestId || !result.ok) throw new Error(result.message || "Fusion returned an unexpected response.");
        if (result.patternState) {
            const snapshot = result.patternState, newSession = action === "pattern_begin" && state.expecting && snapshot.sessionId;
            if (recoveryId && (state.session?.sessionId !== recoveryId || retired.has(recoveryId)
                    || (snapshot.sessionId && snapshot.sessionId !== recoveryId))) return result;
            if (!(pushedVersion !== version && !newSession && snapshot.revision <= (state.session?.revision ?? -1))) apply(snapshot);
        }
        return result;
    }
    function run(task) {
        pending++; state.busy = true; render();
        const running = actions.then(task);
        actions = running.catch(error => { state.liveError = true; message(error.message, true); });
        return actions.finally(() => { pending--; state.busy = pending > 0; render(); });
    }
    function sessionAction(action, extra = {}) {
        const sessionId = identity(); if (!sessionId) throw new Error("Start a pattern geometry session first.");
        const payload = { sessionId, ...extra };
        if (action === "pattern_focus") { state.session = { ...state.session, phase: "selecting", previewCurrent: false }; render(); }
        if (["pattern_update", "pattern_preview", "pattern_commit"].includes(action)) Object.assign(payload, { settings: { ...state.settings }, revision: state.revision });
        return send(action, payload);
    }
    async function refresh() {
        if (supported() && identity() && selected() && valid() && state.session?.phase !== "opening") {
            state.liveError = false; state.session = { ...state.session, phase: "computing", previewCurrent: false };
            render(); await sessionAction("pattern_preview");
        }
    }
    function schedule() {
        cancelTimer(); if (!supported() || !identity() || !valid() || state.session?.phase === "opening") return;
        timer = window.setTimeout(() => {
            timer = undefined; if (queued) return; queued = true;
            run(async () => {
                queued = false; if (!identity() || !valid() || state.session?.phase === "opening") return;
                if (selected()) await refresh(); else { await sessionAction("pattern_update"); await refresh(); }
            });
        }, 160);
    }
    async function begin(edit) {
        if (!edit && !$("pattern-settings").reportValidity()) return;
        cancelTimer(); state.expecting = true; state.revision = 0; state.liveError = false; message("Starting surface selection in Fusion…");
        try { await send("pattern_begin", { settings: valid() ? { ...state.settings } : { ...defaults }, editing: edit }); }
        finally { state.expecting = false; }
        await refresh();
    }
    for (const [name, caption, container] of [["pattern", "Pattern", "pattern-design-fields"], ["mode", "Action", "pattern-design-fields"], ["layout_mode", "Spacing", "pattern-size-fields"], ["selection_scope", "Apply to", "pattern-scope-fields"]]) {
        const item = document.createElement("div"); item.className = "parameter-item";
        const label = document.createElement("label"); label.htmlFor = `pattern-${name}`; label.textContent = caption;
        const input = document.createElement("select"); input.id = `pattern-${name}`; input.name = name; input.required = true;
        for (const [value, text] of choices[name]) { const option = document.createElement("option"); option.value = value; option.textContent = text; input.append(option); }
        input.value = defaults[name]; item.append(label, input); $(container).append(item);
    }
    for (const [container, fields] of [["pattern-size-fields", [["pitch_mm", "Pitch"], ["web_mm", "Solid web"], ["border_mm", "Solid border"], ["depth_mm", "Relief height"]]], ["pattern-placement-fields", [["rotation_deg", "Rotation (°)"], ["offset_u_mm", "U offset (mm)"], ["offset_v_mm", "V offset (mm)"]]]]) {
        for (const [name, caption] of fields) {
            const item = document.createElement("div"); item.className = "parameter-item";
            const label = document.createElement("label"); label.htmlFor = `pattern-${name}`; label.textContent = caption;
            const input = document.createElement("input"); input.id = `pattern-${name}`; input.name = name; input.type = "number"; input.required = true; input.step = "any";
            if (!signed.has(name)) input.min = "0";
            input.value = defaults[name]; item.append(label, input); $(container).append(item);
        }
    }
    $("pattern-settings").addEventListener("submit", event => event.preventDefault());
    $("pattern-settings").addEventListener("input", event => {
        const input = event.target; if (!Object.prototype.hasOwnProperty.call(defaults, input.name)) return;
        if (input.name === "selection_scope" && editing()) { input.value = state.settings.selection_scope; message("Create a new pattern to change between selected faces and a whole body.", true); return; }
        if (input.type === "number") {
            const value = Number(input.value), zeroAllowed = input.name === "border_mm";
            const okay = input.value.trim() !== "" && Number.isFinite(value) && (signed.has(input.name) || (zeroAllowed ? value >= 0 : value > 0));
            input.setCustomValidity(okay ? "" : signed.has(input.name) ? "Enter a finite number." : zeroAllowed ? "Enter zero or a positive number." : "Enter a number greater than zero."); state.settings[input.name] = value;
        } else {
            input.setCustomValidity(choices[input.name].some(([value]) => value === input.value) ? "" : "Choose a supported option.");
            if (input.name === "selection_scope" && input.value !== state.settings.selection_scope && active()) state.session = { ...state.session, selections: {} };
            state.settings[input.name] = input.value;
        }
        state.revision++; state.dirty = true; state.liveError = false; availability(false); renderArt();
        if (active()) message(valid() ? "Updating live preview…" : "Check the highlighted input. Showing the previous valid preview.", !valid());
        render(); schedule();
    });
    $("begin-pattern-button").addEventListener("click", () => run(() => begin(false)));
    $("edit-pattern-button").addEventListener("click", () => run(() => begin(true)));
    $("preview-pattern-button").addEventListener("click", () => { if ($("pattern-settings").reportValidity()) { cancelTimer(); run(refresh); } });
    $("create-pattern-button").addEventListener("click", () => { if ($("pattern-settings").reportValidity()) { cancelTimer(); run(() => sessionAction("pattern_commit")); } });
    $("cancel-pattern-button").addEventListener("click", () => { cancelTimer(); run(() => sessionAction("pattern_cancel")); });
    window.PartelierPatterns = Object.freeze({
        isActive() { return active(); },
        isBusy() { return state.busy || state.session?.phase === "opening"; },
        matches(id) { return Object.prototype.hasOwnProperty.call(presets, id); },
        select(id) {
            state.selected = this.matches(id);
            if (state.selected && state.alias !== id && !active() && !otherActive()) { Object.assign(state.settings, presets[id]); state.revision = 0; state.liveError = false; sync(); }
            state.alias = state.selected ? id : null; render();
        },
        setOtherActive(values) { Object.assign(state.others, values); render(); },
        connect(result) {
            state.connected = true; state.capabilities = new Set(Array.isArray(result.capabilities) ? result.capabilities : []);
            if (!state.dirty && result.patternDefaults && !result.patternState?.settings) { state.settings = { ...defaults, ...result.patternDefaults }; sync(); }
            for (const [key, snapshot] of [["hinge", result.hingeState], ["snap", result.snapState]]) if (snapshot) state.others[key] = !!snapshot.sessionId && !terminal.has(snapshot.phase);
            if (result.patternState) apply(result.patternState);
            renderArt(); render(); if (identity() && selected() && !current()) schedule();
            return active() ? state.settings.pattern === "hexagon" ? "honeycomb" : state.settings.mode === "emboss" ? "knurl" : "perforation" : null;
        },
        handle(action, raw) { if (action !== "pattern_state") return false; if (apply(JSON.parse(raw))) pushedVersion++; return true; }
    });
    renderArt(); render();
})();

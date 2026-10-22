"use strict";

// Snap-fit owns its form and session; the library only forwards host messages.
(() => {
    const $ = id => document.getElementById(id);
    const defaults = Object.freeze({ width_mm: 8, thickness_mm: 1.5, reach_mm: 16, clearance_mm: .3, hook_depth_mm: 1, lead_in_mm: 3, snap_count: 1, start_margin_mm: 5, end_margin_mm: 5, root_length_mm: 4, attachment_overlap_mm: .5 });
    const terminal = new Set(["idle", "created", "cancelled"]), retired = new Set();
    const nonnegative = new Set(["start_margin_mm", "end_margin_mm"]);
    const fields = [
        ["snap-size-fields", [["width_mm", "Tab width"], ["thickness_mm", "Tab thickness"], ["reach_mm", "Tab reach"]]],
        ["snap-fit-fields", [["clearance_mm", "Mating clearance"], ["hook_depth_mm", "Hook engagement"]]],
        ["snap-layout-fields", [["snap_count", "Count"], ["start_margin_mm", "Start margin"], ["end_margin_mm", "End margin"]]],
        ["snap-construction-fields", [["root_length_mm", "Root length"], ["lead_in_mm", "Lead-in length"], ["attachment_overlap_mm", "Attachment overlap"]]]
    ];
    const state = { selected: false, connected: false, capabilities: new Set(), hingeActive: false, session: null, settings: { ...defaults }, revision: 0, busy: false, dirty: false, expecting: false, liveError: false };
    let serial = 0, pushedVersion = 0, timer, queued = false, pending = 0, actions = Promise.resolve();
    const active = () => !!state.session && !terminal.has(state.session.phase) && !!(state.session.sessionId || state.session.phase === "opening");
    const identity = () => active() ? state.session.sessionId : null;
    const supported = () => state.connected && state.capabilities.has("snap-palette");
    const selected = () => (state.session?.editing ? ["edit_target"] : ["face_a", "face_b", "axis_edge"]).every(name => state.session?.selections?.[name]?.selected);
    const current = () => !state.liveError && state.session?.phase === "preview" && state.session.revision === state.revision && state.session.previewCurrent !== false;
    const valid = () => $("snap-settings").checkValidity();

    function message(text, error = false) {
        $("snap-operation-status").textContent = text;
        $("snap-operation-status").classList.toggle("error", error);
        $("snap-operation-status").hidden = !text || (!error && !/created|rebuilt|cancelled|Starting|Creating|Rebuilding/i.test(text));
    }
    function cancelTimer() {
        if (timer !== undefined) window.clearTimeout(timer);
        timer = undefined;
    }
    function syncFields() {
        for (const input of $("snap-settings").querySelectorAll("[name]")) {
            input.value = state.settings[input.name]; input.setCustomValidity("");
        }
    }
    function renderSelections() {
        $("snap-selections").replaceChildren();
        const labels = state.session?.editing ? [["edit_target", "Snap result"]] : [["face_a", "Hook face A"], ["face_b", "Receiver B"], ["axis_edge", "Seam edge"]];
        for (const [target, caption] of labels) {
            const picked = state.session?.selections?.[target];
            const button = document.createElement("button"); button.type = "button"; button.id = `snap-select-${target}`; button.className = "selection-button";
            button.disabled = !supported() || !identity() || state.busy || state.session?.phase === "opening";
            const label = document.createElement("strong"); label.textContent = caption;
            const value = document.createElement("span"); value.textContent = picked?.selected ? "✓" : "Pick";
            button.setAttribute("title", picked?.selected ? picked.label || "Selected" : caption);
            button.setAttribute("aria-label", `${caption}: ${picked?.selected ? picked.label || "Selected" : "not selected"}`);
            button.classList.toggle("is-selected", !!picked?.selected); button.append(label, value);
            button.addEventListener("click", () => { cancelTimer(); run(async () => { await sessionAction("snap_focus", { target }); await refresh(); }); });
            $("snap-selections").append(button);
        }
        $("snap-selection-help").textContent = state.session?.editing ? "Pick an existing snap-fit. Esc stops picking." : "Pick the base wall, lid wall, then their straight seam edge.";
        $("snap-selection-help").hidden = selected();
    }
    function render() {
        const committing = state.session?.phase === "opening", busy = state.busy || committing, hasSession = active(), ready = !!identity() && selected();
        $("snap-tool").hidden = !state.selected;
        $("snap-action-dock").hidden = !state.selected;
        $("tool-select").disabled = state.hingeActive || hasSession || busy;
        for (const input of $("snap-settings").querySelectorAll("[name]")) input.disabled = committing;
        $("snap-settings").setAttribute("aria-busy", String(committing));
        $("begin-snap-button").hidden = hasSession;
        $("begin-snap-button").disabled = !state.selected || !supported() || !valid() || busy || hasSession || state.hingeActive;
        $("edit-snap-button").disabled = !state.selected || !supported() || !state.capabilities.has("snap-edit") || busy || hasSession || state.hingeActive;
        $("preview-snap-button").hidden = !ready || (!state.liveError && current());
        $("preview-snap-button").disabled = !ready || !valid() || busy;
        $("cancel-snap-button").disabled = !identity() || busy;
        $("create-snap-button").disabled = !state.selected || !supported() || !valid() || busy || !ready || !current();
        $("create-snap-button").textContent = state.session?.editing ? "Rebuild snap-fit" : "Create snap-fit";
        $("snap-availability").hidden = supported();
        $("snap-availability").textContent = !state.connected ? "Open Partelier in Fusion to select geometry." : "Restart Partelier to enable snap-fits.";
        const label = !supported() ? "Fusion required" : !ready ? "waiting for geometry" : !valid() ? "check inputs" : state.liveError || state.session?.phase === "error" ? "needs attention" : committing ? "creating" : current() ? "up to date" : busy || timer !== undefined || queued || state.session?.phase === "computing" ? "updating…" : "refresh needed";
        $("snap-live-preview-status").textContent = `Live preview · ${label}`;
        $("snap-live-preview-status").classList.toggle("is-current", ready && current());
        $("snap-live-preview-status").classList.toggle("needs-attention", ready && (!valid() || state.liveError || state.session?.phase === "error"));
        renderSelections();
    }
    function apply(snapshot) {
        if (!snapshot || !Number.isInteger(snapshot.revision) || typeof snapshot.phase !== "string") return false;
        const previous = state.session;
        if (snapshot.sessionId && retired.has(snapshot.sessionId)) return false;
        if (snapshot.sessionId && previous?.sessionId && snapshot.sessionId !== previous.sessionId && active() && !state.expecting) return false;
        if (snapshot.sessionId && snapshot.sessionId === previous?.sessionId && snapshot.revision < previous.revision) return false;
        const newerEdits = snapshot.revision < state.revision;
        if (!snapshot.sessionId || terminal.has(snapshot.phase)) {
            if (previous?.sessionId) retired.add(previous.sessionId);
            if (snapshot.sessionId) retired.add(snapshot.sessionId);
        }
        state.session = snapshot;
        if (snapshot.sessionId) state.expecting = false;
        if (!newerEdits && ["preview", "error"].includes(snapshot.phase)) state.liveError = snapshot.phase === "error";
        if (!newerEdits && snapshot.settings) { state.settings = { ...defaults, ...snapshot.settings }; state.revision = snapshot.revision; syncFields(); }
        if (newerEdits && ["preview", "error"].includes(snapshot.phase)) message("Updating live preview…");
        else message(snapshot.message || "", snapshot.phase === "error");
        render(); return true;
    }
    async function send(action, payload = {}) {
        const requestId = `snap-ui-${++serial}`, version = pushedVersion;
        const response = Promise.resolve().then(() => window.adsk.fusionSendData(action, JSON.stringify({ protocol: 1, requestId, ...payload })));
        let timeout, raw;
        try {
            raw = ["snap_begin", "snap_focus", "snap_preview", "snap_commit"].includes(action) ? await response : await Promise.race([response, new Promise((_, reject) => { timeout = window.setTimeout(() => reject(new Error("Fusion did not respond. Stop and Run Partelier, then try again.")), 30000); })]);
        } finally { if (timeout !== undefined) window.clearTimeout(timeout); }
        const result = JSON.parse(raw);
        if (result.protocol !== 1 || result.requestId !== requestId || !result.ok) throw new Error(result.message || "Fusion returned an unexpected response.");
        if (result.snapState) {
            const snapshot = result.snapState, newSession = action === "snap_begin" && state.expecting && snapshot.sessionId;
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
        const sessionId = identity();
        if (!sessionId) throw new Error("Start a snap-fit geometry session first.");
        const payload = { sessionId, ...extra };
        if (["snap_update", "snap_preview", "snap_commit"].includes(action)) Object.assign(payload, { settings: { ...state.settings }, revision: state.revision });
        return send(action, payload);
    }
    async function refresh() {
        if (supported() && identity() && selected() && valid() && state.session?.phase !== "opening") {
            state.liveError = false; await sessionAction("snap_preview");
        }
    }
    function schedule() {
        cancelTimer();
        if (!supported() || !identity() || !valid() || state.session?.phase === "opening") return;
        timer = window.setTimeout(() => {
            timer = undefined;
            if (queued) return;
            queued = true;
            run(async () => {
                queued = false;
                if (!identity() || !valid() || state.session?.phase === "opening") return;
                if (selected()) await refresh();
                else await sessionAction("snap_update");
            });
        }, 160);
    }
    async function begin(editing) {
        if (!editing && !$("snap-settings").reportValidity()) return;
        cancelTimer(); state.expecting = true; state.revision = 0; state.liveError = false;
        message("Starting geometry selection in Fusion…");
        try { await send("snap_begin", { settings: valid() ? { ...state.settings } : { ...defaults }, editing }); }
        finally { state.expecting = false; }
        await refresh();
    }
    for (const [container, group] of fields) for (const [name, caption] of group) {
        const item = document.createElement("div"); item.className = "parameter-item";
        const label = document.createElement("label"); label.htmlFor = `snap-${name}`; label.textContent = caption;
        const input = document.createElement("input"); input.id = `snap-${name}`; input.name = name; input.type = "number"; input.required = true;
        input.min = name === "snap_count" ? "1" : "0"; input.step = name === "snap_count" ? "1" : "any";
        if (name === "snap_count") input.max = "20";
        input.value = defaults[name]; item.append(label, input); $(container).append(item);
    }
    $("snap-settings").addEventListener("submit", event => event.preventDefault());
    $("snap-settings").addEventListener("input", event => {
        const input = event.target;
        if (!Object.prototype.hasOwnProperty.call(defaults, input.name)) return;
        const number = Number(input.value), allowedZero = nonnegative.has(input.name);
        const validNumber = input.value.trim() !== "" && Number.isFinite(number) && (allowedZero ? number >= 0 : number > 0);
        input.setCustomValidity(validNumber ? "" : allowedZero ? "Enter zero or a positive number." : "Enter a number greater than zero.");
        state.settings[input.name] = number; state.revision++; state.dirty = true; state.liveError = false;
        if (active()) message(valid() ? "Updating live preview…" : "Check the highlighted input. Showing the previous valid preview.", !valid());
        render(); schedule();
    });
    $("begin-snap-button").addEventListener("click", () => run(() => begin(false)));
    $("edit-snap-button").addEventListener("click", () => run(() => begin(true)));
    $("preview-snap-button").addEventListener("click", () => { if ($("snap-settings").reportValidity()) { cancelTimer(); run(refresh); } });
    $("create-snap-button").addEventListener("click", () => { if ($("snap-settings").reportValidity()) { cancelTimer(); run(() => sessionAction("snap_commit")); } });
    $("cancel-snap-button").addEventListener("click", () => { cancelTimer(); run(() => sessionAction("snap_cancel")); });
    window.PartelierSnap = Object.freeze({
        select(toolId) { state.selected = toolId === "snap"; render(); },
        setHingeActive(value) { state.hingeActive = !!value; render(); },
        connect(result) {
            state.connected = true; state.capabilities = new Set(Array.isArray(result.capabilities) ? result.capabilities : []);
            if (!state.dirty && result.snapDefaults && !result.snapState?.settings) { state.settings = { ...defaults, ...result.snapDefaults }; syncFields(); }
            if (result.snapState) apply(result.snapState);
            $("snap-illustration").innerHTML = window.PartelierIllustrations.render("snap", {});
            render(); if (identity() && selected() && !current()) schedule();
            return active();
        },
        handle(action, raw) { if (action !== "snap_state") return false; if (apply(JSON.parse(raw))) pushedVersion++; return true; }
    });
    $("snap-illustration").innerHTML = window.PartelierIllustrations.render("snap", {});
    render();
})();

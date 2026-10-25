"use strict";

// Snap-fit owns its form and session; the library only forwards host messages.
(() => {
    const $ = id => document.getElementById(id);
    const defaults = Object.freeze({ width_mm: 8, thickness_mm: 1.5, reach_mm: 16, clearance_mm: .3, hook_depth_mm: 1, lead_in_mm: 3, snap_count: 1, start_margin_mm: 5, end_margin_mm: 5, root_length_mm: 4, attachment_overlap_mm: .5, snap_style: "standard", chamfer_edges: true, chamfer_size_mm: .3, print_support: true, snap_family: "hook", ball_radius_mm: 2, torsion_radius_mm: .8, annular_bead_width_mm: 2, annular_bead_height_mm: .5, annular_offset_mm: 3 });
    const families = [["hook", "Hook latch"], ["ball_detent", "Ball detent"], ["torsion", "Torsion latch"], ["annular", "Annular ring"]];
    const styles = [["standard", "Straight hook"], ["tapered", "Tapered hook"], ["twin", "Twin hook"]];
    const terminal = new Set(["idle", "created", "cancelled"]), retired = new Set();
    const nonnegative = new Set(["start_margin_mm", "end_margin_mm"]);
    const fields = [
        ["snap-size-fields", [["width_mm", "Tab width"], ["thickness_mm", "Tab thickness"], ["reach_mm", "Tab reach"]]],
        ["snap-fit-fields", [["clearance_mm", "Mating clearance"], ["hook_depth_mm", "Hook engagement"]]],
        ["snap-layout-fields", [["snap_count", "Count"], ["start_margin_mm", "Start margin"], ["end_margin_mm", "End margin"]]],
        ["snap-construction-fields", [["root_length_mm", "Root length"], ["lead_in_mm", "Lead-in length"], ["attachment_overlap_mm", "Attachment overlap"]]],
        ["snap-finish-fields", [["chamfer_size_mm", "Chamfer size"]]],
        ["snap-ball-fields", [["ball_radius_mm", "Ball radius"]]],
        ["snap-torsion-fields", [["torsion_radius_mm", "Torsion bar radius"]]],
        ["snap-annular-fields", [["annular_bead_width_mm", "Bead width"], ["annular_bead_height_mm", "Bead height"], ["annular_offset_mm", "Offset from rim"]]]
    ];
    const state = { selected: false, connected: false, capabilities: new Set(), hingeActive: false, session: null, settings: { ...defaults }, revision: 0, busy: false, dirty: false, expecting: false, liveError: false };
    let serial = 0, pushedVersion = 0, timer, queued = false, pending = 0, actions = Promise.resolve();
    const active = () => !!state.session && !terminal.has(state.session.phase) && !!(state.session.sessionId || state.session.phase === "opening");
    const identity = () => active() ? state.session.sessionId : null;
    const supported = () => state.connected && state.capabilities.has("snap-palette");
    const selected = () => (state.session?.editing ? ["edit_target"] : ["face_a", "face_b", "axis_edge"]).every(name => state.session?.selections?.[name]?.selected);
    const current = () => !state.liveError && state.session?.phase === "preview" && state.session.revision === state.revision && state.session.previewCurrent !== false;
    const valid = () => $("snap-settings").checkValidity();
    const annular = () => state.settings.snap_family === "annular";

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
            if (input.type === "checkbox") input.checked = state.settings[input.name];
            else input.value = state.settings[input.name];
            input.setCustomValidity("");
        }
        renderArt();
    }
    function renderArt() {
        $("snap-illustration").innerHTML = window.PartelierIllustrations.render("snap", {
            snapStyle: state.settings.snap_style, printSupport: state.settings.print_support,
            chamferEdges: state.settings.chamfer_edges, chamferSize: state.settings.chamfer_size_mm,
            snapFamily: state.settings.snap_family
        });
    }
    function updateFamilyAvailability(committing) {
        const ring = annular(), hook = state.settings.snap_family === "hook";
        if (!hook) { state.settings.snap_style = "standard"; $("snap-snap_style").value = "standard"; $("snap-snap_style").setCustomValidity(""); }
        if (ring) {
            state.settings.snap_count = 1; $("snap-snap_count").value = 1;
            state.settings.chamfer_edges = false; $("snap-chamfer_edges").checked = false;
        }
        $("snap-planar-section").hidden = ring; $("snap-annular-section").hidden = !ring;
        $("snap-style-fields").hidden = !hook;
        $("snap-ball-fields").hidden = state.settings.snap_family !== "ball_detent";
        $("snap-torsion-fields").hidden = state.settings.snap_family !== "torsion";
        $("snap-layout-options").hidden = ring; $("snap-edge-options").hidden = ring;
        for (const input of $("snap-settings").querySelectorAll("[name]")) {
            let visible = true;
            if (["width_mm", "thickness_mm", "reach_mm", "root_length_mm", "lead_in_mm", "hook_depth_mm", "snap_count", "start_margin_mm", "end_margin_mm"].includes(input.name)) visible = !ring;
            if (input.name === "lead_in_mm" && state.settings.snap_family === "ball_detent") visible = false;
            if (input.name === "snap_style") visible = hook;
            if (input.name === "ball_radius_mm") visible = state.settings.snap_family === "ball_detent";
            if (input.name === "torsion_radius_mm") visible = state.settings.snap_family === "torsion";
            if (input.name.startsWith("annular_")) visible = ring;
            if (["chamfer_edges", "chamfer_size_mm"].includes(input.name)) visible = !ring;
            input.disabled = committing || !visible;
            if (input.type === "number") {
                input.parentElement.hidden = !visible;
                const value = state.settings[input.name], zeroAllowed = nonnegative.has(input.name);
                if (!visible && (!Number.isFinite(value) || (zeroAllowed ? value < 0 : value <= 0))) {
                    state.settings[input.name] = defaults[input.name]; input.value = defaults[input.name]; input.setCustomValidity("");
                }
            }
        }
        const editing = active() && !!state.session?.editing, editRing = editing && state.session.settings?.snap_family === "annular";
        for (const option of $("snap-snap_family").children) option.disabled = committing || (editing && (option.value === "annular") !== !!editRing);
        $("snap-family-edit-note").hidden = !editing;
        $("snap-construction-summary").textContent = ring ? "Attachment" : state.settings.snap_family === "ball_detent" ? "Root & attachment" : "Root & lead-in";
        $("snap-construction-fields").classList.toggle("single-field", ring);
        $("snap-width_mm").parentElement.children[0].textContent = state.settings.snap_family === "torsion" ? "Mount width" : "Tab width";
        $("snap-thickness_mm").parentElement.children[0].textContent = state.settings.snap_family === "torsion" ? "Lever thickness" : "Tab thickness";
        $("snap-reach_mm").parentElement.children[0].textContent = state.settings.snap_family === "torsion" ? "Lever reach" : "Tab reach";
        $("snap-hook_depth_mm").parentElement.children[0].textContent = state.settings.snap_family === "ball_detent" ? "Nose engagement" : "Hook engagement";
        $("snap-print_support").parentElement.replaceChildren($("snap-print_support"), ring ? "45° groove roof" : "45° print ramps");
        $("snap-family-guidance").textContent = ring ? "A bead and groove on two coaxial cylinder necks." : state.settings.snap_family === "ball_detent" ? "A rounded detent nose and matching pocket on two walls." : state.settings.snap_family === "torsion" ? "A center lever on a transverse torsion bar, with a matching catch." : "A retaining hook and matching recess on two walls.";
        $("snap-help-placement").textContent = ring ? "Pick the outer cylinder of neck A, the inner cylinder of sleeve B, then a circular rim. Both cylindrical faces must be coaxial. Offset is measured from that rim along the selected axis." : "Select two coplanar exterior wall faces facing the same way: A on the base, B on the lid. Pick either facing straight rim; a gap between them is supported. The mechanism sits outside the walls and reaches from A toward B.";
        $("snap-help-mechanism").textContent = ring ? "Annular adds a continuous raised bead to A and a matching internal groove in B. Bead width, height and offset control the ring profile." : state.settings.snap_family === "ball_detent" ? "The flexible arm carries a rounded nose. Ball radius and nose engagement control the cam into and out of its matching pocket." : state.settings.snap_family === "torsion" ? "Two fixed end posts hold a transverse torsion bar. The center lever turns that bar to release its retaining hook." : "Straight uses one arm; Tapered reduces its thickness toward the catch. Twin uses two parallel arms on a shared root, with two matching recesses separated by a wall.";
        $("snap-help-print").textContent = ring ? "The optional 45° groove roof follows the ring axis. Review your chosen print orientation in the slicer. General edge chamfers are unavailable for this ring profile." : "45° print ramps add a root ramp and sloped receiver roof for printing in the shown +Z direction. Review your chosen orientation in the slicer.";
        $("begin-snap-button").textContent = ring ? "Select cylinders & rim" : "Select faces & edge";
        for (const [id, className, caption] of [["snap-legend-a", "part-a", ring ? "Neck A" : "Mechanism A"], ["snap-legend-b", "part-b", ring ? "Sleeve B" : "Receiver B"]]) {
            const swatch = document.createElement("i"); swatch.className = className; $(id).replaceChildren(swatch, caption);
        }
    }
    function updateFinishAvailability(committing) {
        const input = $("snap-chamfer_size_mm"), enabled = !annular() && state.settings.chamfer_edges;
        input.disabled = committing || !enabled;
        input.parentElement.hidden = !enabled;
        // A hidden invalid size must not poison the full host snapshot.
        if (!enabled && (!Number.isFinite(state.settings.chamfer_size_mm) || state.settings.chamfer_size_mm <= 0)) {
            state.settings.chamfer_size_mm = defaults.chamfer_size_mm;
            input.value = defaults.chamfer_size_mm; input.setCustomValidity("");
        }
    }
    function renderSelections() {
        $("snap-selections").replaceChildren();
        const editing = active() && !!state.session?.editing;
        const labels = editing ? [["edit_target", "Snap result"]] : annular() ? [["face_a", "Outer cylinder A"], ["face_b", "Inner cylinder B"], ["axis_edge", "Circular rim"]] : [["face_a", "Mechanism A"], ["face_b", "Receiver B"], ["axis_edge", "Seam edge"]];
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
        $("snap-selection-help").textContent = editing ? "Pick an existing snap-fit. Esc stops picking." : annular() ? "Pick the outer cylinder A, inner cylinder B, then a circular rim." : "Pick the base wall, lid wall, then their straight seam edge.";
        $("snap-selection-help").hidden = !!identity() && selected();
    }
    function render() {
        const committing = state.session?.phase === "opening", busy = state.busy || committing, hasSession = active(), ready = !!identity() && selected();
        $("snap-tool").hidden = !state.selected;
        $("snap-action-dock").hidden = !state.selected;
        $("tool-select").disabled = state.hingeActive || hasSession || busy || !!window.PartelierPatterns?.isActive() || !!window.PartelierPatterns?.isBusy() || !!window.PartelierDetails?.isActive() || !!window.PartelierDetails?.isBusy();
        window.PartelierPatterns?.setOtherActive({ snap: hasSession || busy, hinge: state.hingeActive });
        for (const input of $("snap-settings").querySelectorAll("[name]")) input.disabled = committing;
        updateFamilyAvailability(committing);
        updateFinishAvailability(committing);
        $("snap-settings").setAttribute("aria-busy", String(committing));
        $("begin-snap-button").hidden = hasSession;
        $("begin-snap-button").disabled = !state.selected || !supported() || !valid() || busy || hasSession || state.hingeActive || !!window.PartelierDetails?.isActive() || !!window.PartelierDetails?.isBusy();
        $("edit-snap-button").disabled = !state.selected || !supported() || !state.capabilities.has("snap-edit") || busy || hasSession || state.hingeActive || !!window.PartelierDetails?.isActive() || !!window.PartelierDetails?.isBusy();
        $("preview-snap-button").hidden = !ready || (!state.liveError && current());
        $("preview-snap-button").disabled = !ready || !valid() || busy;
        $("cancel-snap-button").disabled = !identity() || busy;
        $("create-snap-button").disabled = !state.selected || !supported() || !valid() || busy || !ready || !current();
        $("create-snap-button").textContent = active() && state.session?.editing ? "Rebuild snap-fit" : "Create snap-fit";
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
                else { await sessionAction("snap_update"); await refresh(); }
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
    for (const [container, name, caption, choices] of [["snap-family-fields", "snap_family", "Snap type", families], ["snap-style-fields", "snap_style", "Hook style", styles]]) {
        const label = document.createElement("label"); label.htmlFor = `snap-${name}`; label.textContent = caption;
        const input = document.createElement("select"); input.id = `snap-${name}`; input.name = name; input.required = true;
        for (const [value, text] of choices) { const option = document.createElement("option"); option.value = value; option.textContent = text; input.append(option); }
        input.value = defaults[name]; $(container).append(label, input);
    }
    for (const [container, name, caption] of [["snap-fit-fields", "print_support", "45° print ramps"], ["snap-finish-toggle", "chamfer_edges", "Outer edges only"]]) {
        const label = document.createElement("label"); label.className = "checkbox-field";
        const input = document.createElement("input"); input.type = "checkbox"; input.id = `snap-${name}`; input.name = name; input.checked = defaults[name];
        label.append(input, caption); $(container).append(label);
    }
    $("snap-settings").addEventListener("submit", event => event.preventDefault());
    $("snap-settings").addEventListener("input", event => {
        const input = event.target;
        if (!Object.prototype.hasOwnProperty.call(defaults, input.name)) return;
        const previousFamily = state.settings.snap_family;
        if (input.name === "snap_family" && active() && state.session?.editing && (input.value === "annular") !== (state.session.settings?.snap_family === "annular")) {
            input.value = previousFamily; message("Cancel and create a new snap-fit to switch between wall and cylinder geometry.", true); render(); return;
        }
        if (input.type === "number") {
            const number = Number(input.value), allowedZero = nonnegative.has(input.name);
            const validNumber = input.value.trim() !== "" && Number.isFinite(number) && (allowedZero ? number >= 0 : number > 0);
            input.setCustomValidity(validNumber ? "" : allowedZero ? "Enter zero or a positive number." : "Enter a number greater than zero.");
            state.settings[input.name] = number;
        } else if (input.type === "checkbox") state.settings[input.name] = input.checked;
        else if (input.name === "snap_style") {
            input.setCustomValidity(styles.some(([value]) => value === input.value) ? "" : "Choose a supported snap style.");
            state.settings.snap_style = input.value;
        } else if (input.name === "snap_family") {
            input.setCustomValidity(families.some(([value]) => value === input.value) ? "" : "Choose a supported snap family.");
            state.settings.snap_family = input.value;
            if ((previousFamily === "annular") !== annular() && active()) state.session = { ...state.session, selections: {} };
        }
        state.revision++; state.dirty = true; state.liveError = false;
        updateFamilyAvailability(false); updateFinishAvailability(false); renderArt();
        if (active()) message(valid() ? "Updating live preview…" : "Check the highlighted input. Showing the previous valid preview.", !valid());
        render(); schedule();
    });
    $("begin-snap-button").addEventListener("click", () => run(() => begin(false)));
    $("edit-snap-button").addEventListener("click", () => run(() => begin(true)));
    $("preview-snap-button").addEventListener("click", () => { if ($("snap-settings").reportValidity()) { cancelTimer(); run(refresh); } });
    $("create-snap-button").addEventListener("click", () => { if ($("snap-settings").reportValidity()) { cancelTimer(); run(() => sessionAction("snap_commit")); } });
    $("cancel-snap-button").addEventListener("click", () => { cancelTimer(); run(() => sessionAction("snap_cancel")); });
    window.PartelierSnap = Object.freeze({
        isActive() { return active(); },
        isBusy() { return state.busy || state.session?.phase === 'opening'; },
        select(toolId) { state.selected = toolId === "snap"; render(); },
        setHingeActive(value) { state.hingeActive = !!value; render(); },
        connect(result) {
            state.connected = true; state.capabilities = new Set(Array.isArray(result.capabilities) ? result.capabilities : []);
            if (!state.dirty && result.snapDefaults && !result.snapState?.settings) { state.settings = { ...defaults, ...result.snapDefaults }; syncFields(); }
            if (result.snapState) apply(result.snapState);
            renderArt();
            render(); if (identity() && selected() && !current()) schedule();
            return active();
        },
        handle(action, raw) { if (action !== "snap_state") return false; if (apply(JSON.parse(raw))) pushedVersion++; return true; }
    });
    renderArt();
    render();
})();

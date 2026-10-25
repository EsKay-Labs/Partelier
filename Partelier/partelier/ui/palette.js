"use strict";

(() => {
    const tools = window.PartelierCatalog, art = window.PartelierIllustrations;
    const $ = id => document.getElementById(id);
    const categories = [["mechanisms", "Mechanisms"], ["details", "Small details"], ["surfaces", "Surfaces"], ["patterns", "Patterns"]];
    const hingeDefaults = { length_mm: 40, hinge_count: 1, start_margin_mm: 0, end_margin_mm: 0, knuckle_count: 5, barrel_diameter_mm: 8, pin_diameter_mm: 3, diametral_clearance_mm: .3, rotation_clearance_mm: .3, axial_gap_mm: .3, leaf_reach_mm: 12, leaf_thickness_mm: 2, attachment_overlap_mm: .5, pin_overhang_mm: 2, axis_offset_mm: 4, include_pin: true, split_seam: false, seam_clearance_mm: .3, output_mode: "attached", leaf_profile: "rectangular", leaf_barrel_clearance_mm: .3, screw_holes: false, screw_diameter_mm: 3.2, screw_end_margin_mm: 6, chamfer_edges: false, chamfer_size_mm: .3, knuckle_profile: "round", web_profile: "tangent", fillet_edges: false, fillet_radius_mm: .6 };
    const designPresets = [
        { id: "classic", name: "Classic · round", note: "Round housings, five alternating knuckles and sharp edges.", values: { knuckle_profile: "round", knuckle_count: 5, chamfer_edges: false, fillet_edges: false, leaf_profile: "rectangular" } },
        { id: "soft", name: "Soft · filleted", note: "Rounded leaf edges, housing ends and hole mouths. Fillet radius starts at 0.6 mm.", values: { knuckle_profile: "round", knuckle_count: 5, chamfer_edges: false, fillet_edges: true, fillet_radius_mm: .6, leaf_profile: "rectangular" } },
        { id: "linear", name: "Linear · square", note: "Square housings inside the round envelope, with circular pin bores and 0.3 mm chamfers.", values: { knuckle_profile: "square", knuckle_count: 5, chamfer_edges: true, chamfer_size_mm: .3, fillet_edges: false, leaf_profile: "rectangular" } },
        { id: "compact", name: "Compact · 3 knuckles", note: "Three wider round knuckles with filleted edges. Overall dimensions remain yours to set.", values: { knuckle_profile: "round", knuckle_count: 3, chamfer_edges: false, fillet_edges: true, fillet_radius_mm: .6, leaf_profile: "rectangular" } },
        { id: "piano", name: "Piano · 11 knuckles", note: "Eleven alternating round knuckles with chamfered ends. Adjust the overall length for your design.", values: { knuckle_profile: "round", knuckle_count: 11, chamfer_edges: true, chamfer_size_mm: .3, fillet_edges: false, leaf_profile: "rectangular" } }
    ];
    const placementFields = [["hinge_count", "Count"], ["start_margin_mm", "Start margin"], ["end_margin_mm", "End margin"]];
    const primaryFields = [["length_mm", "Length per hinge"], ["barrel_diameter_mm", "Barrel diameter"], ["pin_diameter_mm", "Pin diameter"]];
    const fitFields = [["rotation_clearance_mm", "Movement clearance"], ["diametral_clearance_mm", "Bore clearance (diameter)"], ["axial_gap_mm", "Axial gap"], ["pin_overhang_mm", "Pin overhang / end"]];
    const attachmentFields = [["leaf_reach_mm", "Leaf reach"], ["leaf_thickness_mm", "Leaf thickness"], ["attachment_overlap_mm", "Attachment overlap"], ["axis_offset_mm", "Axis offset toward part B"], ["seam_clearance_mm", "Split seam clearance"], ["leaf_barrel_clearance_mm", "Leaf to barrel clearance"]];
    const holeFields = [["screw_diameter_mm", "Hole diameter"], ["screw_end_margin_mm", "Hole end margin"]];
    const nonnegativeFields = new Set(["start_margin_mm", "end_margin_mm", "rotation_clearance_mm"]);
    const terminalPhases = new Set(["idle", "created", "cancelled"]);
    // Page-local only: a reopened page can recover the host's active session.
    const retiredSessionIds = new Set();
    const state = { selected: "hinge", exploded: false, favorites: new Set(), connected: false, capabilities: new Set(), busy: false, dirty: false, hingeSettings: { ...hingeDefaults }, session: null, revision: 0, expectingSession: false, liveError: false };
    let serial = 0, pendingActions = 0, actionQueue = Promise.resolve(), updateQueued = false, updateTimer;
    let pushedStateVersion = 0;
    const livePreviewDelay = 160;

    const paletteMode = () => state.capabilities.has("hinge-palette");
    const legacyMode = () => state.connected && !paletteMode();
    const activeSession = () => state.session && !terminalPhases.has(state.session.phase) && (state.session.sessionId || state.session.phase === "opening");
    const sessionId = () => activeSession() ? state.session.sessionId : null;

    function renderToolMenu() {
        const groups = [];
        const append = (label, entries) => {
            if (!entries.length) return;
            const group = document.createElement("optgroup"); group.label = label;
            for (const tool of entries) {
                const option = document.createElement("option"); option.value = tool.id; option.textContent = tool.name; group.append(option);
            }
            groups.push(group);
        };
        append("Favorites", tools.filter(tool => state.favorites.has(tool.id)));
        for (const [id, label] of categories) append(label, tools.filter(tool => tool.category === id && !state.favorites.has(tool.id)));
        $("tool-select").replaceChildren(...groups); $("tool-select").value = state.selected;
        $("tool-count").textContent = `${tools.length} tools`;
    }

    function renderArt() {
        const canSeparate = ["hinge", "snap", "slider", "pockets", "lid", "alignment"].includes(state.selected);
        if (!canSeparate) state.exploded = false;
        $("detail-illustration").innerHTML = art.render(state.selected, { exploded: state.exploded, length: state.hingeSettings.length_mm, outputMode: state.hingeSettings.output_mode, leafProfile: state.hingeSettings.leaf_profile, screwHoles: state.hingeSettings.screw_holes, chamferEdges: state.hingeSettings.chamfer_edges, filletEdges: state.hingeSettings.fillet_edges, knuckleProfile: state.hingeSettings.knuckle_profile, knuckleCount: state.hingeSettings.knuckle_count, webProfile: state.hingeSettings.web_profile });
        $("assembled-button").textContent = canSeparate ? "Assembled" : "Isometric";
        $("exploded-button").disabled = !canSeparate;
        $("assembled-button").classList.toggle("selected", !state.exploded);
        $("assembled-button").setAttribute("aria-pressed", String(!state.exploded));
        $("exploded-button").classList.toggle("selected", state.exploded);
        $("exploded-button").setAttribute("aria-pressed", String(state.exploded));
        $("view-label").textContent = state.exploded ? "SEPARATED" : "ISOMETRIC";
    }

    function renderHingeLayout() { $("hinge-layout-illustration").innerHTML = art.renderHingeLayout(state.hingeSettings); }
    function validateNumberInput(input) {
        const number = Number(input.value), nonnegative = nonnegativeFields.has(input.name);
        const valid = input.value.trim() !== "" && Number.isFinite(number) && (nonnegative ? number >= 0 : number > 0);
        input.setCustomValidity(valid ? "" : nonnegative ? "Enter zero or a positive number." : "Enter a number greater than zero.");
    }
    function addNumbers(container, fields) {
        for (const [key, label] of fields) {
            const item = document.createElement("div"); item.className = "parameter-item";
            const caption = document.createElement("label"); caption.htmlFor = `hinge-${key}`; caption.textContent = label;
            const input = document.createElement("input"); input.id = `hinge-${key}`; input.name = key; input.type = "number"; input.required = true;
            input.min = key === "knuckle_count" ? "3" : key === "hinge_count" ? "1" : "0";
            input.step = key === "knuckle_count" ? "2" : key === "hinge_count" ? "1" : "any";
            if (key === "knuckle_count") input.max = "15";
            if (key === "hinge_count") input.max = "20";
            input.value = state.hingeSettings[key]; item.append(caption, input); $(container).append(item);
        }
    }
    function addCheckbox(container, name, caption) {
        const label = document.createElement("label"); label.className = "checkbox-field";
        const input = document.createElement("input"); input.id = `hinge-${name}`; input.type = "checkbox"; input.name = name; input.checked = state.hingeSettings[name];
        label.append(input, caption); $(container).append(label);
    }
    function addChoice(container, name, caption, choices) {
        const item = document.createElement("div"); item.className = "parameter-item"; item.id = `hinge-${name}-field`;
        const label = document.createElement("label"); label.htmlFor = `hinge-${name}`; label.textContent = caption;
        const select = document.createElement("select"); select.id = `hinge-${name}`; select.name = name;
        for (const [value, text] of choices) { const option = document.createElement("option"); option.value = value; option.textContent = text; select.append(option); }
        select.value = state.hingeSettings[name]; item.append(label, select); $(container).append(item);
    }
    function renderHingeFields() {
        for (const id of ["hinge-layout-fields", "hinge-fields", "hinge-fit-fields", "hinge-advanced-fields", "hinge-mode", "hinge-output-fields", "hinge-hole-fields", "hinge-hole-toggle", "hinge-finish-fields", "hinge-finish-choice", "hinge-fillet-fields", "hinge-design-fields"]) $(id).replaceChildren();
        addNumbers("hinge-layout-fields", placementFields); addNumbers("hinge-fields", primaryFields);
        addChoice("hinge-advanced-fields", "web_profile", "Attachment shape", [["tangent", "Tapered support"], ["flat", "Flat web"]]);
        addNumbers("hinge-fit-fields", fitFields); addNumbers("hinge-advanced-fields", attachmentFields); addNumbers("hinge-hole-fields", holeFields);
        addCheckbox("hinge-fit-fields", "include_pin", "Create separate pins");
        addCheckbox("hinge-mode", "split_seam", "Split seam (touching parts)");
        const note = document.createElement("p"); note.className = "helper-copy"; note.id = "hinge-mode-note"; $("hinge-mode").append(note);
        addChoice("hinge-output-fields", "output_mode", "Output", [["attached", "Attached to parts"], ["separate", "Separate leaves"]]);
        addChoice("hinge-advanced-fields", "leaf_profile", "Leaf corners", [["rectangular", "Flat / rectangular"], ["rounded", "Rounded free corners"]]);
        addCheckbox("hinge-hole-toggle", "screw_holes", "Add screw holes");
        addChoice("hinge-design-fields", "design_preset", "Style", [...designPresets.map(item => [item.id, item.name]), ["custom", "Custom configuration"]]);
        addChoice("hinge-finish-choice", "knuckle_profile", "Housing profile", [["round", "Round barrel"], ["square", "Square / linear"]]);
        addChoice("hinge-finish-choice", "edge_treatment", "Edge treatment", [["sharp", "Sharp"], ["chamfer", "Chamfer · 45°"], ["fillet", "Fillet · rounded"]]);
        addNumbers("hinge-finish-choice", [["knuckle_count", "Knuckles per hinge"]]);
        addNumbers("hinge-finish-fields", [["chamfer_size_mm", "Chamfer size"]]);
        addNumbers("hinge-fillet-fields", [["fillet_radius_mm", "Fillet radius"]]);
        updateHingeMode(); renderHingeLayout();
    }
    function syncHingeFields() {
        for (const input of $("hinge-settings").querySelectorAll("[name]")) {
            if (!(input.name in state.hingeSettings)) continue;
            if (input.type === "checkbox") input.checked = state.hingeSettings[input.name]; else input.value = state.hingeSettings[input.name];
            if (input.type === "number") validateNumberInput(input);
        }
        updateHingeMode(); renderHingeLayout(); renderArt();
    }
    function updateHingeMode() {
        const split = state.hingeSettings.split_seam, separate = state.hingeSettings.output_mode === "separate", fillet = state.hingeSettings.fillet_edges;
        const preset = designPresets.find(item => Object.entries(item.values).every(([key, value]) => state.hingeSettings[key] === value));
        $("hinge-design_preset").value = preset?.id || "custom";
        $("hinge-design-note").textContent = preset?.note || "Your own combination of housing, knuckles and edge treatment. Dimensions and placement stay editable.";
        $("hinge-edge_treatment").value = fillet ? "fillet" : state.hingeSettings.chamfer_edges ? "chamfer" : "sharp";
        const axis = $("hinge-axis_offset_mm"), clearance = $("hinge-seam_clearance_mm");
        for (const input of [axis, clearance]) {
            if ((input === axis ? split : !split) && !(Number(input.value) > 0 && Number.isFinite(Number(input.value)))) {
                input.value = hingeDefaults[input.name]; state.hingeSettings[input.name] = hingeDefaults[input.name]; input.setCustomValidity("");
            }
        }
        axis.disabled = split; clearance.disabled = !split || separate; clearance.parentElement.hidden = separate;
        $("hinge-leaf_profile-field").hidden = !separate || fillet; $("hinge-leaf_profile").disabled = !separate || fillet;
        $("hinge-leaf_barrel_clearance_mm").disabled = !separate;
        $("hinge-leaf_barrel_clearance_mm").parentElement.hidden = !separate;
        $("hinge-attachment_overlap_mm").disabled = separate;
        $("hinge-attachment_overlap_mm").parentElement.hidden = separate;
        $("hinge-advanced-title").textContent = separate ? "Leaf dimensions & placement" : "Attachment & seam";
        $("hinge-web_profile-field").hidden = false; $("hinge-web_profile").disabled = false;
        $("hinge-web-profile-note").textContent = state.hingeSettings.web_profile === "tangent"
            ? (separate ? "Tapered supports connect each housing to its leaf and remain within Leaf reach." : "Tapered supports meet the housing and return to the source face. On attached hinges, their footprint can extend beyond Leaf reach.")
            : "Flat attachment webs use Leaf reach and Leaf thickness. This option preserves the earlier support shape.";
        $("hinge-chamfer_size_mm").disabled = !state.hingeSettings.chamfer_edges;
        $("hinge-finish-fields").hidden = !state.hingeSettings.chamfer_edges;
        $("hinge-fillet_radius_mm").disabled = !fillet;
        $("hinge-fillet-fields").hidden = !fillet;
        $("hinge-holes").hidden = !separate;
        $("hinge-screw_holes").disabled = !separate;
        for (const name of ["screw_diameter_mm", "screw_end_margin_mm"]) $("hinge-" + name).disabled = !separate || !state.hingeSettings.screw_holes;
        for (const input of $("hinge-settings").querySelectorAll('input[type="number"]:disabled')) {
            if (!Number.isFinite(Number(input.value)) || (nonnegativeFields.has(input.name) ? Number(input.value) < 0 : Number(input.value) <= 0)) {
                input.value = hingeDefaults[input.name]; state.hingeSettings[input.name] = hingeDefaults[input.name]; input.setCustomValidity("");
            }
        }
        $("hinge-output-note").textContent = separate ? (fillet ? "Independent leaves with rounded edges and corners. Screw holes are optional." : "Independent leaves positioned on your reference parts. Choose flat or rounded free corners; screw holes are optional.") : "Hinge details join your two selected bodies. Only optional pins add separate bodies.";
        $("hinge-mode-note").textContent = separate
            ? (split ? "Axis centered on the shared edge. Source bodies stay unchanged." : "A shared edge centers the axis automatically. For parts with a gap, use the axis offset toward B.")
            : (split ? "Axis centered on the verified seam. Create opens the clearance in your two selected bodies." : "Supported touching seams are detected automatically after the shared edge is selected. An existing gap uses the axis offset toward B.");
    }
    function renderSelections() {
        const editing = !!state.session?.editing;
        const labels = editing ? [["edit_target", "Hinge result"]] : [["face_a", "Face A"], ["face_b", "Face B"], ["axis_edge", "Axis edge"]];
        $("hinge-selections").replaceChildren();
        for (const [target, caption] of labels) {
            const picked = state.session?.selections?.[target];
            const button = document.createElement("button"); button.type = "button"; button.className = "selection-button"; button.id = `select-${target}`;
            button.disabled = !paletteMode() || !sessionId() || state.busy || state.session?.phase === "opening";
            const label = document.createElement("strong"); label.textContent = caption;
            const value = document.createElement("span"); value.textContent = picked?.selected ? "✓" : "Pick";
            button.setAttribute("title", picked?.selected ? picked.label || "Selected" : caption);
            button.setAttribute("aria-label", caption + ": " + (picked?.selected ? picked.label || "Selected" : "not selected"));
            button.classList.toggle("is-selected", !!picked?.selected); button.append(label, value);
            button.addEventListener("click", () => runAction(async () => {
                cancelPendingUpdate(); await sessionAction("hinge_focus", { target }); await refreshLivePreview();
            }));
            $("hinge-selections").append(button);
        }
        $("selection-help").textContent = editing ? "Pick the existing hinge. Esc stops picking." : "Pick Face A, Face B, then the straight edge.";
        $("selection-help").hidden = selectionsReady();
    }
    function selectionsReady() {
        const names = state.session?.editing ? ["edit_target"] : ["face_a", "face_b", "axis_edge"];
        return names.every(name => state.session?.selections?.[name]?.selected);
    }
    function currentPreview() {
        return !state.liveError && state.session?.phase === "preview" && state.session.revision === state.revision && state.session.previewCurrent !== false;
    }
    function updateActions() {
        const committing = state.session?.phase === "opening";
        let unlocked = false;
        for (const control of $("hinge-settings").querySelectorAll("[name]")) {
            if (committing) {
                if (control.partelierBeforeCommit === undefined) control.partelierBeforeCommit = control.disabled;
                control.disabled = true;
            } else if (control.partelierBeforeCommit !== undefined) {
                control.disabled = control.partelierBeforeCommit;
                delete control.partelierBeforeCommit; unlocked = true;
            }
        }
        if (unlocked) updateHingeMode();
        $("hinge-settings").setAttribute("aria-busy", String(committing));
        const hinge = state.selected === "hinge", valid = $("hinge-settings").checkValidity(), active = !!activeSession();
        const palette = paletteMode(), ready = !!sessionId() && selectionsReady(), busy = state.busy || state.session?.phase === "opening";
        $("begin-hinge-button").disabled = !hinge || !palette || !valid || busy || active;
        $("begin-hinge-button").textContent = active ? "Geometry selected" : "Select faces & edge";
        $("begin-hinge-button").hidden = active;
        $("edit-hinge-button").disabled = !hinge || busy || active || !state.capabilities.has("hinge-edit");
        $("preview-hinge-button").hidden = legacyMode() || !ready || (!state.liveError && currentPreview()); $("cancel-hinge-button").hidden = legacyMode();
        $("preview-hinge-button").disabled = !hinge || !valid || !ready || busy;
        $("cancel-hinge-button").disabled = !sessionId() || busy;
        $("create-hinge-button").disabled = !hinge || !valid || busy || (palette ? !ready || !currentPreview() : !state.capabilities.has("hinge-create"));
        $("create-hinge-button").textContent = legacyMode() ? "Set up hinge in Fusion" : state.session?.editing ? "Rebuild hinge" : "Create hinge";
        $("create-hint").textContent = !hinge ? "This tool is planned; creation is not available." : !state.connected ? "Open Partelier in Fusion to select geometry and create a hinge." : palette ? "Live preview follows your changes. Create confirms the result; Cancel clears the preview." : "Restart the add-in to use the latest palette workflow.";
        $("create-hint").hidden = hinge;
        $("live-preview-status").hidden = !hinge;
        const previewLabel = !state.connected ? "Fusion required" : !ready ? "waiting for geometry" : !valid ? "check inputs" : (state.liveError || (state.session?.phase === "error" && state.session.revision === state.revision)) ? "needs attention" : committing ? "creating" : currentPreview() ? "up to date" : (state.busy || state.session?.phase === "computing" || updateTimer !== undefined || updateQueued || state.session.revision < state.revision) ? "updating…" : "refresh needed";
        $("live-preview-status").textContent = `Live preview · ${previewLabel}`;
        $("live-preview-status").classList.toggle("is-current", !!ready && currentPreview());
        $("live-preview-status").classList.toggle("needs-attention", !!ready && (!valid || state.liveError || (state.session?.phase === "error" && state.session.revision === state.revision)));
        renderSelections();
        window.PartelierSnap?.setHingeActive(active || busy);
        window.PartelierPatterns?.setOtherActive({ hinge: active || busy });
    }
    function operationStatus(message, error = false) {
        $("operation-status").textContent = message;
        $("operation-status").classList.toggle("error", error);
        $("operation-status").hidden = !error && !/created|rebuilt|cancelled|Starting|Creating|Rebuilding/i.test(message);
    }
    function applyHingeState(snapshot) {
        if (!snapshot || !Number.isInteger(snapshot.revision) || typeof snapshot.phase !== "string") return false;
        const previous = state.session;
        if (snapshot.sessionId && retiredSessionIds.has(snapshot.sessionId)) return false;
        if (snapshot.sessionId && previous?.sessionId && snapshot.sessionId !== previous.sessionId && activeSession() && !state.expectingSession) return false;
        if (snapshot.sessionId && snapshot.sessionId === previous?.sessionId && snapshot.revision < previous.revision) return false;
        const newerEdits = snapshot.revision < state.revision;
        if (!snapshot.sessionId || terminalPhases.has(snapshot.phase)) {
            if (previous?.sessionId) retiredSessionIds.add(previous.sessionId);
            if (snapshot.sessionId) retiredSessionIds.add(snapshot.sessionId);
        }
        state.session = snapshot;
        if (!newerEdits && ["preview", "error"].includes(snapshot.phase)) state.liveError = snapshot.phase === "error";
        if (snapshot.sessionId) state.expectingSession = false;
        if (!newerEdits && snapshot.settings) { state.hingeSettings = { ...hingeDefaults, ...snapshot.settings }; state.revision = snapshot.revision; syncHingeFields(); }
        if (newerEdits && ["preview", "error"].includes(snapshot.phase)) operationStatus("Updating live preview…");
        else operationStatus(snapshot.message || "", snapshot.phase === "error");
        updateActions();
        return true;
    }
    window.fusionJavaScriptHandler = { handle(action, data) { try { if (action === "hinge_state" && applyHingeState(JSON.parse(data))) pushedStateVersion++; else { window.PartelierSnap?.handle(action, data); window.PartelierPatterns?.handle(action, data); } return "OK"; } catch (_) { return "FAILED"; } } };

    function renderFavorite() {
        const favorite = state.favorites.has(state.selected); $("favorite-button").textContent = favorite ? "★" : "☆";
        $("favorite-button").setAttribute("aria-pressed", String(favorite)); $("favorite-button").setAttribute("aria-label", favorite ? "Remove from favorites" : "Add to favorites");
    }
    function renderDetail() {
        const tool = tools.find(item => item.id === state.selected);
        $("tool-workspace").classList.toggle("hinge-workspace", tool.id === "hinge");
        const snapTool = tool.id === "snap" && !!window.PartelierSnap;
        const patternTool = !!window.PartelierPatterns?.matches(tool.id);
        $("planned-tool").hidden = tool.id === "hinge" || snapTool || patternTool;
        $("hinge-action-dock").hidden = snapTool || patternTool;
        $("hinge-help").hidden = snapTool || patternTool;
        window.PartelierSnap?.select(tool.id);
        window.PartelierPatterns?.select(tool.id);
        $("detail-category").textContent = categories.find(([id]) => id === tool.category)[1];
        $("detail-title").textContent = tool.name; $("detail-description").textContent = tool.description; $("detail-outcome").textContent = tool.outcome; $("detail-stage").textContent = tool.stage; $("detail-note").textContent = tool.note;
        $("parameter-list").replaceChildren(...tool.inputs.map(([label, value]) => { const item = document.createElement("div"); item.className = "parameter-item"; const key = document.createElement("span"); key.textContent = label; const content = document.createElement("strong"); content.textContent = value; item.append(key, content); return item; }));
        $("workflow").replaceChildren(...tool.steps.map(step => { const item = document.createElement("li"); item.textContent = step; return item; }));
        $("parameter-list").hidden = tool.id === "hinge"; $("hinge-settings").hidden = tool.id !== "hinge"; $("inputs-note").hidden = tool.id === "hinge";
        document.querySelectorAll(".guide-disclosure").forEach(section => { section.open = false; });
        renderArt(); renderFavorite(); updateActions();
    }
    async function send(action, payload = {}) {
        const requestId = `ui-${++serial}`;
        const stateVersionAtRequest = pushedStateVersion;
        const response = Promise.resolve().then(() => window.adsk.fusionSendData(action, JSON.stringify({ protocol: 1, requestId, ...payload })));
        // Picks wait for the user; native geometry may also outlive a short
        // bridge timeout. Neither should report failure while Fusion is active.
        let timer, raw;
        try {
            raw = ["hinge_begin", "hinge_focus", "hinge_preview", "hinge_commit"].includes(action) ? await response : await Promise.race([response, new Promise((_, reject) => { timer = window.setTimeout(() => reject(new Error("Fusion did not respond. Stop and Run Partelier, then try again.")), 30000); })]);
        } finally { if (timer !== undefined) window.clearTimeout(timer); }
        const result = JSON.parse(raw);
        if (result.protocol !== 1 || result.requestId !== requestId || !result.ok) throw new Error(result.message || "Fusion returned an unexpected response.");
        if (result.hingeState) {
            // A native callback can finish before Qt delivers this request's
            // earlier acknowledgment. Never roll a newer pushed preview or
            // completed Create back to computing/opening at the same revision.
            const snapshot = result.hingeState;
            const newSession = action === "hinge_begin" && state.expectingSession && snapshot.sessionId;
            const superseded = pushedStateVersion !== stateVersionAtRequest && !newSession
                && snapshot.revision <= (state.session?.revision ?? -1);
            if (!superseded) applyHingeState(snapshot);
        }
        return result;
    }
    function runAction(task) {
        pendingActions++; state.busy = true; updateActions();
        const running = actionQueue.then(task);
        actionQueue = running.catch(error => { state.liveError = true; operationStatus(error.message, true); });
        return actionQueue.finally(() => { pendingActions--; state.busy = pendingActions > 0; updateActions(); });
    }
    async function sessionAction(action, extra = {}) {
        const identity = sessionId();
        if (!identity) throw new Error("Start a geometry session first.");
        const payload = { sessionId: identity, ...extra };
        if (["hinge_update", "hinge_preview", "hinge_commit"].includes(action)) Object.assign(payload, { settings: { ...state.hingeSettings }, revision: state.revision });
        return send(action, payload);
    }
    function cancelPendingUpdate() {
        if (updateTimer !== undefined) window.clearTimeout(updateTimer);
        updateTimer = undefined;
    }
    async function refreshLivePreview() {
        if (paletteMode() && sessionId() && selectionsReady() && $("hinge-settings").checkValidity()
                && state.session?.phase !== "opening") {
            state.liveError = false;
            await sessionAction("hinge_preview");
        }
    }
    function scheduleUpdate() {
        cancelPendingUpdate();
        if (!paletteMode() || !sessionId() || !$("hinge-settings").checkValidity()
                || state.session?.phase === "opening") return;
        updateTimer = window.setTimeout(() => {
            updateTimer = undefined;
            if (updateQueued) return;
            updateQueued = true;
            runAction(async () => {
                updateQueued = false;
                if (!sessionId() || !$("hinge-settings").checkValidity() || state.session?.phase === "opening") return;
                if (selectionsReady()) await refreshLivePreview();
                else await sessionAction("hinge_update");
            });
        }, livePreviewDelay);
    }
    async function beginHinge(editing) {
        if (!editing && !$("hinge-settings").reportValidity()) return;
        state.expectingSession = true; state.revision = 0; state.liveError = false;
        operationStatus("Starting geometry selection in Fusion…");
        try { await send("hinge_begin", { settings: $("hinge-settings").checkValidity() ? { ...state.hingeSettings } : { ...hingeDefaults }, editing }); }
        finally { state.expectingSession = false; }
        await refreshLivePreview();
    }
    async function connect(attempt = 0) {
        if (!window.adsk || typeof window.adsk.fusionSendData !== "function") { if (attempt < 8) window.setTimeout(() => connect(attempt + 1), 250); return; }
        try {
            const result = await send("ready"); state.connected = true; state.capabilities = new Set(Array.isArray(result.capabilities) ? result.capabilities : []);
            if (!state.dirty && result.hingeDefaults && !result.hingeState?.settings) { state.hingeSettings = { ...hingeDefaults, ...result.hingeDefaults }; syncHingeFields(); }
            $("connection-status").classList.add("connected"); $("connection-status").replaceChildren(); $("connection-status").append(document.createElement("i"), "Fusion connected");
            $("input-check-button").disabled = !state.capabilities.has("input-check"); $("bridge-message").textContent = "The foundation check opens a native Fusion dialog."; $("model-status").textContent = "Partelier 0.16.1";
            if (window.PartelierSnap?.connect(result)) { state.selected = "snap"; renderToolMenu(); renderDetail(); }
            const patternAlias = window.PartelierPatterns?.connect(result);
            if (patternAlias) { state.selected = patternAlias; renderToolMenu(); renderDetail(); }
            updateActions();
            if (sessionId() && selectionsReady() && !currentPreview()) scheduleUpdate();
        } catch (error) { $("connection-status").replaceChildren(document.createElement("i"), "Fusion connection unavailable"); $("bridge-message").textContent = error.message; }
    }

    $("tool-select").addEventListener("change", event => { state.selected = event.target.value; state.exploded = false; renderDetail(); $("tool-workspace").scrollTop = 0; });
    document.querySelector(".brand").addEventListener("click", event => { event.preventDefault(); $("tool-select").focus(); });
    $("favorite-button").addEventListener("click", () => { state.favorites.has(state.selected) ? state.favorites.delete(state.selected) : state.favorites.add(state.selected); renderFavorite(); renderToolMenu(); });
    $("assembled-button").addEventListener("click", () => { state.exploded = false; renderArt(); }); $("exploded-button").addEventListener("click", () => { state.exploded = true; renderArt(); }); $("reset-view").addEventListener("click", () => { state.exploded = false; renderArt(); });
    $("hinge-settings").addEventListener("submit", event => event.preventDefault());
    $("hinge-settings").addEventListener("input", event => {
        const input = event.target; if (!input.name) return;
        if (input.type === "number") validateNumberInput(input);
        if (input.name === "design_preset") {
            const preset = designPresets.find(item => item.id === input.value);
            if (preset) Object.assign(state.hingeSettings, preset.values);
            syncHingeFields();
        } else if (input.name === "edge_treatment") {
            state.hingeSettings.chamfer_edges = input.value === "chamfer";
            state.hingeSettings.fillet_edges = input.value === "fillet";
            if (state.hingeSettings.fillet_edges) { state.hingeSettings.leaf_profile = "rectangular"; $("hinge-leaf_profile").value = "rectangular"; }
        } else state.hingeSettings[input.name] = input.type === "checkbox" ? input.checked : input.type === "number" ? Number(input.value) : input.value;
        if (input.name === "output_mode" && input.value === "attached") { state.hingeSettings.screw_holes = false; $("hinge-screw_holes").checked = false; }
        state.dirty = true; state.revision++; state.liveError = false;
        updateHingeMode();
        if (["length_mm", "output_mode", "leaf_profile", "screw_holes", "design_preset", "knuckle_profile", "knuckle_count", "web_profile", "edge_treatment"].includes(input.name) && input.checkValidity()) renderArt();
        if (["hinge_count", "length_mm", "start_margin_mm", "end_margin_mm", "design_preset"].includes(input.name) && input.checkValidity()) renderHingeLayout();
        if (activeSession()) operationStatus($("hinge-settings").checkValidity() ? "Updating live preview…" : "Check the highlighted input. Showing the previous valid preview.", !$("hinge-settings").checkValidity());
        updateActions(); scheduleUpdate();
    });
    $("begin-hinge-button").addEventListener("click", () => runAction(() => beginHinge(false)));
    $("edit-hinge-button").addEventListener("click", () => runAction(async () => { if (paletteMode()) await beginHinge(true); else { await send("hinge_edit"); operationStatus("Select an existing hinge result in Fusion."); } }));
    $("preview-hinge-button").addEventListener("click", () => { if ($("hinge-settings").reportValidity()) runAction(async () => { cancelPendingUpdate(); await refreshLivePreview(); }); });
    $("create-hinge-button").addEventListener("click", () => { if ($("hinge-settings").reportValidity()) runAction(async () => { if (paletteMode()) { cancelPendingUpdate(); await sessionAction("hinge_commit"); } else { await send("hinge_create", { settings: state.hingeSettings }); operationStatus("The native hinge dialog opened."); } }); });
    $("cancel-hinge-button").addEventListener("click", () => runAction(async () => { cancelPendingUpdate(); await sessionAction("hinge_cancel"); }));
    $("about-button").addEventListener("click", () => $("about-dialog").showModal());
    $("input-check-button").addEventListener("click", async () => { $("input-check-button").disabled = true; try { await send("open_input_check"); $("about-dialog").close(); } catch (error) { $("bridge-message").textContent = error.message; } finally { $("input-check-button").disabled = !state.connected; } });
    document.addEventListener("keydown", event => { if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") { event.preventDefault(); $("tool-select").focus(); } });
    renderHingeFields(); renderToolMenu(); renderDetail(); connect();
})();

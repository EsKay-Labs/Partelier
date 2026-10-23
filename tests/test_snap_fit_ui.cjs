"use strict";
// Run both production controllers against a DOM/native-message fixture.
const assert = require("node:assert/strict"), fs = require("node:fs"), vm = require("node:vm"), path = require("node:path");
const ui = path.join(__dirname, "..", "Partelier", "partelier", "ui");
const html = fs.readFileSync(path.join(ui, "palette.html"), "utf8");
const defaults = { width_mm: 8, thickness_mm: 1.5, reach_mm: 16, clearance_mm: .3, hook_depth_mm: 1, lead_in_mm: 3, snap_count: 1, start_margin_mm: 5, end_margin_mm: 5, root_length_mm: 4, attachment_overlap_mm: .5, snap_style: "standard", chamfer_edges: true, chamfer_size_mm: .3, print_support: true, snap_family: "hook", ball_radius_mm: 2, torsion_radius_mm: .8, annular_bead_width_mm: 2, annular_bead_height_mm: .5, annular_offset_mm: 3 };
const idle = () => ({ sessionId: null, revision: 0, phase: "idle", editing: false, settings: null, selections: {}, message: "" });
function fixture(options = {}) {
    const ids = new Map();
    class Element {
        constructor(tag = "div") { this.tagName = tag; this.children = []; this.listeners = {}; this.disabled = false; this.hidden = false; this.open = false; this.checked = false; this._value = ""; this.custom = ""; const classes = new Set(); this.classList = { add: x => classes.add(x), remove: x => classes.delete(x), toggle: (x, on) => on ? classes.add(x) : classes.delete(x) }; }
        set id(value) { this._id = value; ids.set(value, this); } get id() { return this._id; }
        set value(value) { this._value = String(value); } get value() { return this._value; }
        append(...items) { for (const item of items) { this.children.push(item); if (item instanceof Element) item.parentElement = this; } }
        replaceChildren(...items) { this.children = []; this.append(...items); }
        setAttribute(name, value) { this[name] = value; }
        addEventListener(name, handler) { (this.listeners[name] ||= []).push(handler); }
        emit(name) { return Promise.all((this.listeners[name] || []).map(fn => fn({ target: this, preventDefault() {} }))); }
        querySelectorAll(selector) { const all = []; const visit = element => { for (const child of element.children) if (child instanceof Element) { if (selector === "[name]" ? !!child.name : child.tagName === "input" && child.type === "number" && child.disabled) all.push(child); visit(child); } }; visit(this); return all; }
        setCustomValidity(message) { this.custom = message; }
        checkValidity() { if (this.tagName === "form") return this.querySelectorAll("[name]").every(x => x.checkValidity()); if (this.disabled) return true; if (this.custom) return false; if (this.tagName === "select" && this.required) return this.children.some(option => option.value === this.value); if (this.type !== "number") return true; const value = Number(this.value), step = Number(this.step), min = Number(this.min); return this.value !== "" && Number.isFinite(value) && value >= min && (this.max === undefined || value <= Number(this.max)) && (!Number.isFinite(step) || Math.abs((value - min) / step - Math.round((value - min) / step)) < 1e-8); }
        reportValidity() { return this.checkValidity(); } focus() {} showModal() {} close() {}
    }
    for (const match of html.matchAll(/<([a-z]+)[^>]*\bid="([^"]+)"/g)) { const element = new Element(match[1]); element.id = match[2]; element.open = /\sopen(?:\s|>)/.test(match[0]); }
    const $ = id => { assert(ids.has(id), `Missing ${id}`); return ids.get(id); };
    for (const id of ["hinge-layout-fields", "hinge-fields", "hinge-fit-fields", "hinge-advanced-fields", "hinge-mode", "hinge-output-fields", "hinge-hole-fields", "hinge-hole-toggle", "hinge-finish-fields", "hinge-finish-choice", "hinge-fillet-fields", "hinge-design-fields"]) $("hinge-settings").append($(id));
    for (const id of ["snap-family-fields", "snap-style-fields", "snap-size-fields", "snap-fit-fields", "snap-layout-fields", "snap-construction-fields", "snap-finish-toggle", "snap-finish-fields", "snap-ball-fields", "snap-torsion-fields", "snap-annular-fields"]) $("snap-settings").append($(id));
    const document = { getElementById: $, createElement: tag => new Element(tag), querySelector: () => new Element("a"), querySelectorAll: () => [], addEventListener() {} };
    let snap = options.snap || idle(), hinge = options.hinge || idle(), sessionSequence = 0, timeouts = 0, timerSequence = 0;
    const timers = new Map(), requests = [], config = { ...options, failPreview: false, queuedPreview: false, holdPreview: false, holdCommit: false, holdPick: false, release: null, delayedPush: null, saved: null };
    const clone = value => JSON.parse(JSON.stringify(value));
    const push = snapshot => window.fusionJavaScriptHandler.handle("snap_state", JSON.stringify(snapshot));
    const window = { setTimeout(fn, ms) { if (ms === 30000) { timeouts++; return 0; } if (ms === 160) { const id = ++timerSequence; timers.set(id, fn); return id; } return setTimeout(fn, ms); }, clearTimeout(id) { timers.delete(id); clearTimeout(id); }, adsk: { fusionSendData(action, raw) {
        const request = JSON.parse(raw); requests.push([action, request]);
        const respond = (ok = true, message) => JSON.stringify({ protocol: 1, requestId: request.requestId, ok, message, capabilities: config.capabilities || ["hinge-palette", "hinge-edit", "snap-palette", "snap-edit"], hingeState: clone(hinge), snapState: clone(snap), snapDefaults: defaults });
        if (action.startsWith("hinge_")) {
            if (action === "hinge_begin") hinge = { ...idle(), sessionId: "a12dd31d-b2ca-4f47-8237-000000000001", phase: "selecting", settings: request.settings };
            if (action === "hinge_cancel") hinge = { ...hinge, sessionId: null, phase: "cancelled" };
            window.fusionJavaScriptHandler.handle("hinge_state", JSON.stringify(hinge));
            return Promise.resolve(respond());
        }
        if (["snap_update", "snap_preview", "snap_commit", "snap_focus", "snap_cancel"].includes(action) && request.sessionId !== snap.sessionId) return Promise.resolve(respond(false, "This snap-fit session has ended."));
        if (action === "snap_begin") {
            snap = { ...idle(), sessionId: "a12dd31d-b2ca-4f47-8237-" + String(++sessionSequence).padStart(12, "0"), phase: "selecting", editing: request.editing, settings: request.editing && config.saved ? { ...config.saved } : request.settings };
            if (config.completePick) { snap.selections = Object.fromEntries((request.editing ? ["edit_target"] : ["face_a", "face_b", "axis_edge"]).map(target => [target, { selected: true, label: target }])); snap.phase = "ready"; }
            if (config.delayedPush) { push(config.delayedPush); config.delayedPush = null; }
            push(snap);
        }
        if (action === "snap_focus") { snap.selections[request.target] = { selected: true, label: request.target }; snap.phase = "ready"; push(snap); }
        if (["snap_update", "snap_preview", "snap_commit"].includes(action)) {
            if ((snap.settings.snap_family === "annular") !== (request.settings.snap_family === "annular")) snap.selections = {};
            snap.settings = request.settings; snap.revision = request.revision;
            snap.phase = action === "snap_preview" ? config.queuedPreview ? "computing" : "preview" : action === "snap_commit" ? config.holdCommit ? "opening" : "created" : "ready";
            snap.message = action === "snap_commit" ? snap.editing ? "Snap-fit rebuilt." : "Snap-fit created." : action === "snap_preview" ? "Preview ready." : "Settings updated.";
            if (action === "snap_commit" && !config.holdCommit) snap.sessionId = null;
        }
        if (action === "snap_cancel") { snap.phase = "cancelled"; snap.sessionId = null; snap.message = "Snap-fit cancelled."; }
        if (action === "snap_preview" && config.failPreview) { config.failPreview = false; return Promise.resolve(respond(false, "The hook does not fit this receiver. Reduce engagement.")); }
        const result = respond();
        if ((["snap_begin", "snap_focus"].includes(action) && config.holdPick) || action === "snap_preview" && config.holdPreview || action === "snap_commit" && config.holdCommit) return new Promise(resolve => { config.release = () => resolve(result); });
        return Promise.resolve(result);
    } } };
    const context = vm.createContext({ window, document, console, setTimeout, clearTimeout });
    for (const file of ["catalog.js", "illustrations.js", "snap.js", "palette.js"]) vm.runInContext(fs.readFileSync(path.join(ui, file), "utf8"), context, { filename: file });
    const flush = async () => { for (let i = 0; i < 8; i++) await new Promise(resolve => setImmediate(resolve)); };
    const settle = async () => { const queued = [...timers.values()]; timers.clear(); queued.forEach(fn => fn()); await flush(); };
    return { $, config, requests, flush, settle, push, snapshot: () => clone(snap), timeouts: () => timeouts,
        async select(tool) { $("tool-select").value = tool; await $("tool-select").emit("change"); await flush(); },
        async click(id) { await $(id).emit("click"); await flush(); },
        async input(name, value, debounce = true) { const control = $(`snap-${name}`); if (control.type === "checkbox") control.checked = value; else control.value = value; for (const fn of $("snap-settings").listeners.input) fn({ target: control }); await flush(); if (debounce) await settle(); }
    };
}
(async () => {
    const f = fixture(); await f.flush();
    assert.equal(f.$("snap-tool").hidden, true);
    await f.select("snap");
    assert.equal(f.$("snap-tool").hidden, false);
    assert.equal(f.$("snap-action-dock").hidden, false);
    assert.equal(f.$("hinge-action-dock").hidden, true);
    assert.equal(f.$("hinge-help").hidden, true);
    assert.equal(f.$("planned-tool").hidden, true);
    assert.equal(f.$("begin-snap-button").disabled, false);
    assert.equal(f.$("create-snap-button").disabled, true);
    assert.equal(f.$("snap-options").open, false);
    assert.equal(f.$("snap-help").open, false);
    assert(f.$("snap-illustration").innerHTML.includes("<svg"));
    assert.equal(f.$("snap-snap_style").value, "standard");
    assert.equal(f.$("snap-family-fields").children[0].textContent, "Snap type");
    assert.equal(f.$("snap-style-fields").children[0].textContent, "Hook style");
    assert.deepEqual(f.$("snap-snap_family").children.map(option => option.textContent), ["Hook latch", "Ball detent", "Torsion latch", "Annular ring"]);
    assert.deepEqual(f.$("snap-snap_style").children.map(option => option.textContent), ["Straight hook", "Tapered hook", "Twin hook"]);
    const sizeSection = html.match(/<section[^>]+aria-labelledby="snap-size-title">([\s\S]*?)<\/section>/)[1];
    const sizeHeading = sizeSection.match(/<div class="section-heading">([\s\S]*?)<\/div>/)[1];
    assert(!sizeHeading.includes("snap-style-fields"), "snap type is a separate row outside the size heading");
    assert(sizeSection.indexOf('id="snap-style-fields"') < sizeSection.indexOf('id="snap-size-fields"'), "snap type precedes dimensions");
    assert.equal(f.$("snap-chamfer_edges").parentElement.children[1], "Outer edges only");
    assert.equal(f.$("snap-print_support").checked, true);
    assert.equal(f.$("snap-chamfer_edges").checked, true);
    assert.equal(f.$("snap-chamfer_size_mm").disabled, false);
    assert.deepEqual(f.$("snap-settings").querySelectorAll("[name]").map(x => x.name).sort(), Object.keys(defaults).sort());
    await f.input("width_mm", 9);
    f.config.holdPick = true;
    const timeouts = f.timeouts();
    f.$("begin-snap-button").emit("click"); await f.flush();
    assert.equal(f.timeouts(), timeouts, "native picking does not time out while waiting for the user");
    assert.equal(f.$("tool-select").disabled, true, "active native selection owns the tool menu");
    assert.equal(f.snapshot().settings.width_mm, 9);
    f.config.release(); f.config.holdPick = false; await f.flush();
    for (const target of ["face_a", "face_b", "axis_edge"]) await f.click(`snap-select-${target}`);
    assert.equal(f.snapshot().phase, "preview", "completing geometry automatically previews");
    assert.equal(f.$("create-snap-button").disabled, false);
    const standardArt = f.$("snap-illustration").innerHTML;
    const conceptMesh = svg => (svg.match(/<polygon[^>]*>/g) || []).join("");
    assert(standardArt.includes('data-print-support="true"'));
    await f.input("snap_style", "tapered");
    assert.equal(f.snapshot().settings.snap_style, "tapered", "style stays a string in the atomic host snapshot");
    assert(f.$("snap-illustration").innerHTML.includes('data-snap-style="tapered"'));
    assert.notEqual(conceptMesh(f.$("snap-illustration").innerHTML), conceptMesh(standardArt), "tapered concept changes its beam geometry");
    await f.input("snap_style", "twin");
    assert.equal(f.snapshot().settings.snap_style, "twin");
    const twinArt = f.$("snap-illustration").innerHTML;
    assert(twinArt.includes('data-snap-style="twin"'));
    assert((twinArt.match(/<polygon/g) || []).length > (standardArt.match(/<polygon/g) || []).length, "twin concept has two separate arm meshes");
    await f.input("print_support", false);
    assert.equal(f.snapshot().settings.print_support, false, "print support stays boolean");
    assert(f.$("snap-illustration").innerHTML.includes('data-print-support="false"'));
    assert.notEqual(conceptMesh(f.$("snap-illustration").innerHTML), conceptMesh(twinArt), "print ramps change the roof and root concept meshes");
    await f.input("chamfer_edges", false);
    assert.equal(f.snapshot().settings.chamfer_edges, false, "chamfer choice stays boolean");
    assert.equal(f.$("snap-chamfer_size_mm").disabled, true);
    assert.equal(f.$("snap-chamfer_size_mm").parentElement.hidden, true);
    assert(!f.$("snap-illustration").innerHTML.includes("Exposed-edge chamfer"));
    await f.input("chamfer_edges", true);
    const requestsBeforeInvalidChamfer = f.requests.length;
    await f.input("chamfer_size_mm", 0);
    assert.equal(f.$("snap-settings").checkValidity(), false);
    assert.equal(f.requests.length, requestsBeforeInvalidChamfer);
    await f.input("chamfer_edges", false);
    assert.equal(f.$("snap-settings").checkValidity(), true, "turning finish off clears its hidden invalid input");
    assert.equal(f.snapshot().settings.chamfer_size_mm, .3, "disabled invalid size is replaced with a valid full-snapshot value");
    await f.input("chamfer_edges", true);
    await f.input("chamfer_size_mm", .25);
    assert.equal(f.snapshot().settings.chamfer_size_mm, .25);
    assert(f.$("snap-illustration").innerHTML.includes("Exposed-edge chamfer · 0.25 mm"));
    await f.input("print_support", true);
    const requestsBeforeUnknownStyle = f.requests.length;
    await f.input("snap_style", "unsupported-style");
    assert.equal(f.$("snap-settings").checkValidity(), false);
    assert.equal(f.requests.length, requestsBeforeUnknownStyle, "invalid style cannot reach the host");
    await f.input("snap_style", "twin");
    const beforeInvalid = f.requests.length;
    await f.input("thickness_mm", 0);
    assert.equal(f.$("snap-settings").checkValidity(), false);
    assert.equal(f.$("create-snap-button").disabled, true);
    assert.equal(f.requests.length, beforeInvalid);
    await f.input("thickness_mm", 1.6);
    await f.input("snap_count", 1.5);
    assert.equal(f.$("snap-settings").checkValidity(), false, "count is an integer");
    await f.input("snap_count", 2);
    await f.input("start_margin_mm", 0);
    assert.equal(f.$("snap-settings").checkValidity(), true, "zero margin remains valid");
    const previews = () => f.requests.filter(([action]) => action === "snap_preview").length;
    const beforeDebounce = previews();
    f.$("snap-options").open = true;
    await f.input("reach_mm", 17, false); await f.input("reach_mm", 18, false);
    assert.equal(previews(), beforeDebounce);
    assert.equal(f.$("create-snap-button").disabled, true);
    await f.settle();
    assert.equal(previews(), beforeDebounce + 1, "rapid changes compute once");
    assert.equal(f.snapshot().settings.reach_mm, 18);
    assert.equal(f.$("snap-options").open, true);
    assert.deepEqual(Object.keys(f.requests.filter(([action]) => action === "snap_preview").at(-1)[1].settings).sort(), Object.keys(defaults).sort(), "every preview is a full settings snapshot");
    f.config.failPreview = true; await f.input("hook_depth_mm", 1.1);
    assert.equal(f.$("create-snap-button").disabled, true);
    assert(f.$("snap-operation-status").textContent.includes("Reduce engagement"));
    assert.equal(f.$("preview-snap-button").hidden, false);
    await f.click("preview-snap-button");
    assert.equal(f.$("create-snap-button").disabled, false);
    f.config.queuedPreview = true; f.config.holdPreview = true;
    await f.input("clearance_mm", .4, false);
    await f.settle();
    const computing = f.snapshot();
    assert.equal(computing.phase, "computing");
    f.push({ ...computing, phase: "preview", message: "Preview ready." });
    f.config.release(); f.config.holdPreview = false; f.config.queuedPreview = false; await f.flush();
    assert.equal(f.$("create-snap-button").disabled, false, "late computing acknowledgment cannot replace an earlier pushed preview");
    f.push({ ...computing, revision: computing.revision - 1, phase: "preview", settings: { ...defaults, reach_mm: 99 } });
    assert.equal(f.$("snap-reach_mm").value, "18", "older host revisions cannot overwrite edited dimensions");
    f.config.holdCommit = true;
    f.$("create-snap-button").emit("click"); await f.flush();
    const committing = f.snapshot();
    f.push(committing); await f.flush();
    assert.equal(f.$("snap-reach_mm").disabled, true);
    assert.equal(f.$("snap-snap_style").disabled, true);
    assert.equal(f.$("snap-print_support").disabled, true);
    assert.equal(f.$("snap-chamfer_edges").disabled, true);
    f.push({ ...committing, sessionId: null, phase: "created", message: "Snap-fit created." });
    f.config.release(); f.config.holdCommit = false; await f.flush();
    assert.equal(f.$("snap-reach_mm").disabled, false);
    assert.equal(f.$("snap-snap_style").disabled, false);
    assert.equal(f.$("snap-print_support").disabled, false);
    assert.equal(f.$("tool-select").disabled, false);
    assert.equal(f.$("cancel-snap-button").disabled, true, "late opening acknowledgment cannot revive a completed creation");
    f.config.completePick = true;
    await f.click("begin-snap-button");
    const retiring = f.snapshot();
    await f.click("cancel-snap-button");
    f.push({ ...retiring, phase: "preview" });
    assert.equal(f.$("tool-select").disabled, false, "late retired-session push is ignored");
    f.config.delayedPush = { ...retiring, phase: "preview" };
    await f.click("begin-snap-button");
    assert.notEqual(f.snapshot().sessionId, retiring.sessionId);
    assert.equal(f.$("create-snap-button").disabled, false);
    await f.click("cancel-snap-button");
    f.config.saved = { ...defaults, width_mm: 11.2, reach_mm: 22, root_length_mm: 6, snap_style: "standard", chamfer_edges: false, print_support: false };
    await f.click("edit-snap-button");
    assert.equal(f.$("snap-width_mm").value, "11.2");
    assert.equal(f.$("snap-root_length_mm").value, "6");
    assert.equal(f.$("snap-snap_style").value, "standard");
    assert.equal(f.$("snap-chamfer_edges").checked, false, "migrated saved sharp geometry stays sharp on Edit");
    assert.equal(f.$("snap-print_support").checked, false, "migrated saved flat geometry does not silently gain ramps");
    assert.equal(f.$("snap-chamfer_size_mm").disabled, true);
    assert.equal(f.$("create-snap-button").textContent, "Rebuild snap-fit");
    await f.input("reach_mm", 23);
    await f.click("create-snap-button");
    assert.equal(f.snapshot().settings.reach_mm, 23);
    assert.equal(f.snapshot().settings.chamfer_edges, false);
    assert.equal(f.snapshot().settings.print_support, false);
    assert(f.$("snap-operation-status").textContent.includes("rebuilt"));
    await f.select("hinge");
    assert.equal(f.$("snap-action-dock").hidden, true);
    assert.equal(f.$("hinge-action-dock").hidden, false);
    await f.click("begin-hinge-button");
    assert.equal(f.$("tool-select").disabled, true, "hinge geometry session also owns the tool menu");
    await f.click("cancel-hinge-button");
    assert.equal(f.$("tool-select").disabled, false);
    const recovered = fixture({ snap: { ...retiring, sessionId: "d28c515a-66dc-4c66-a57b-111111111111", phase: "preview", settings: { ...defaults, width_mm: 12, snap_style: "tapered", print_support: false, chamfer_edges: false } } }); await recovered.flush();
    assert.equal(recovered.$("tool-select").value, "snap", "reopened palette returns to the active snap-fit");
    assert.equal(recovered.$("snap-tool").hidden, false);
    assert.equal(recovered.$("snap-width_mm").value, "12");
    assert.equal(recovered.$("snap-snap_style").value, "tapered");
    assert.equal(recovered.$("snap-print_support").checked, false);
    assert.equal(recovered.$("snap-chamfer_edges").checked, false);
    assert.equal(recovered.$("create-snap-button").disabled, false);
    const unavailable = fixture({ capabilities: ["hinge-palette", "hinge-edit"] }); await unavailable.flush(); await unavailable.select("snap");
    assert.equal(unavailable.$("begin-snap-button").disabled, true, "no fake creation action without the native capability");
    assert.equal(unavailable.$("edit-snap-button").disabled, true);
    assert.equal(unavailable.$("snap-availability").hidden, false);
    assert(unavailable.$("snap-illustration").innerHTML.includes("<svg"));
    const g = fixture(); await g.flush(); await g.select("snap");
    await g.input("snap_style", "twin"); await g.input("snap_count", 3);
    await g.input("thickness_mm", 0);
    assert.equal(g.$("snap-settings").checkValidity(), false);
    await g.input("snap_family", "annular");
    assert.equal(g.$("snap-settings").checkValidity(), true, "unused invalid planar dimensions do not block annular setup");
    assert.equal(g.$("snap-thickness_mm").value, "1.5");
    assert.equal(g.$("snap-snap_style").value, "standard");
    assert.equal(g.$("snap-snap_count").value, "1");
    assert.equal(g.$("snap-chamfer_edges").checked, false);
    assert.equal(g.$("snap-chamfer_edges").disabled, true);
    assert.equal(g.$("snap-edge-options").hidden, true);
    assert.equal(g.$("snap-layout-options").hidden, true);
    assert.equal(g.$("snap-planar-section").hidden, true);
    assert.equal(g.$("snap-annular-section").hidden, false);
    assert.equal(g.$("snap-style-fields").hidden, true);
    for (const name of ["width_mm", "thickness_mm", "reach_mm", "lead_in_mm", "root_length_mm", "snap_count", "start_margin_mm", "end_margin_mm", "ball_radius_mm", "torsion_radius_mm"]) assert.equal(g.$(`snap-${name}`).disabled, true, `${name} is unused for a ring`);
    for (const name of ["annular_bead_width_mm", "annular_bead_height_mm", "annular_offset_mm", "clearance_mm", "attachment_overlap_mm"]) assert.equal(g.$(`snap-${name}`).disabled, false);
    assert.equal(g.$("snap-print_support").parentElement.children[1], "45° groove roof");
    assert(g.$("snap-select-face_a").title.includes("Outer cylinder A"));
    assert(g.$("snap-select-face_b").title.includes("Inner cylinder B"));
    assert(g.$("snap-select-axis_edge").title.includes("Circular rim"));
    const annularArt = g.$("snap-illustration").innerHTML;
    assert(annularArt.includes('data-snap-family="annular"'));
    assert(annularArt.includes("Cutaway · bead and matching groove"));
    assert.notEqual(conceptMesh(annularArt), conceptMesh(standardArt), "annular art builds ring profiles rather than wall latch meshes");
    await g.input("annular_bead_width_mm", 2.5);
    g.config.completePick = true; await g.click("begin-snap-button");
    assert.equal(g.snapshot().settings.snap_family, "annular");
    assert.equal(g.snapshot().settings.annular_bead_width_mm, 2.5);
    assert.equal(Object.keys(g.snapshot().settings).length, 21);
    assert.equal(g.$("create-snap-button").disabled, false);
    await g.input("snap_family", "ball_detent", false);
    assert.equal(g.$("create-snap-button").disabled, true, "wall/cylinder family changes invalidate the previous ready preview immediately");
    await g.settle();
    assert.deepEqual(g.snapshot().selections, {}, "the host is asked to clear incompatible cylinder references");
    assert.equal(g.requests.at(-1)[0], "snap_update", "new geometry is requested before another preview");
    assert.equal(g.$("snap-ball-fields").hidden, false);
    assert.equal(g.$("snap-ball_radius_mm").disabled, false);
    assert.equal(g.$("snap-lead_in_mm").disabled, true, "a spherical cam has no hook lead-in setting");
    assert.equal(g.$("snap-hook_depth_mm").parentElement.children[0].textContent, "Nose engagement");
    for (const target of ["face_a", "face_b", "axis_edge"]) await g.click(`snap-select-${target}`);
    assert.equal(g.$("create-snap-button").disabled, false);
    const ballArt = g.$("snap-illustration").innerHTML;
    assert(ballArt.includes('data-snap-family="ball_detent"'));
    assert.notEqual(conceptMesh(ballArt), conceptMesh(standardArt), "ball art contains a spherical cam nose and rounded receiving opening");
    await g.input("ball_radius_mm", 2.5);
    assert.equal(g.snapshot().settings.ball_radius_mm, 2.5);
    await g.input("ball_radius_mm", 0);
    assert.equal(g.$("snap-settings").checkValidity(), false);
    await g.input("snap_family", "torsion");
    assert.equal(g.$("snap-settings").checkValidity(), true);
    assert.equal(g.$("snap-ball_radius_mm").value, "2");
    assert.equal(g.$("snap-ball_radius_mm").disabled, true);
    assert.equal(g.$("snap-torsion_radius_mm").disabled, false);
    assert.equal(g.$("snap-width_mm").parentElement.children[0].textContent, "Mount width");
    assert.equal(g.$("snap-thickness_mm").parentElement.children[0].textContent, "Lever thickness");
    assert.equal(g.$("snap-lead_in_mm").disabled, false);
    assert.equal(g.$("snap-snap_style").value, "standard");
    assert.equal(g.$("create-snap-button").disabled, false, "compatible planar references remain selected across planar families");
    const torsionArt = g.$("snap-illustration").innerHTML;
    assert(torsionArt.includes('data-snap-family="torsion"'));
    assert.notEqual(conceptMesh(torsionArt), conceptMesh(ballArt), "torsion art adds its transverse bar, posts and center lever");
    await g.input("torsion_radius_mm", 1);
    assert.equal(g.snapshot().settings.torsion_radius_mm, 1);
    assert.equal(g.snapshot().settings.snap_family, "torsion");
    await g.click("cancel-snap-button");
    g.config.saved = { ...defaults, snap_family: "annular", snap_count: 1, chamfer_edges: false };
    await g.click("edit-snap-button");
    assert.equal(g.$("snap-family-edit-note").hidden, false);
    assert(g.$("snap-snap_family").children.filter(option => option.value !== "annular").every(option => option.disabled));
    const beforeForbiddenFamily = g.requests.length;
    await g.input("snap_family", "hook");
    assert.equal(g.requests.length, beforeForbiddenFamily);
    assert.equal(g.$("snap-snap_family").value, "annular");
    assert(g.$("snap-operation-status").textContent.includes("Cancel and create a new snap-fit"));
    await g.click("create-snap-button");
    assert(g.$("snap-snap_family").children.every(option => !option.disabled), "completed Edit releases its geometry-family lock");
    await g.input("snap_family", "hook");
    assert.equal(g.$("snap-style-fields").hidden, false);
    assert.equal(g.$("snap-planar-section").hidden, false);
    assert.equal(g.$("snap-annular-section").hidden, true);
    await g.click("edit-snap-button");
    await g.click("cancel-snap-button");
    g.config.saved = { ...defaults, snap_family: "ball_detent" };
    await g.click("edit-snap-button");
    await g.input("snap_family", "torsion");
    assert.equal(g.snapshot().settings.snap_family, "torsion", "Edit can change compatible planar mechanisms");
    assert.equal(g.$("snap-snap_family").children.find(option => option.value === "annular").disabled, true);
    await g.click("cancel-snap-button");
    const bundleVersion = JSON.parse(fs.readFileSync(path.join(__dirname, "../Partelier/Partelier.manifest"), "utf8")).version;
    assert(html.includes(`snap.js?v=${bundleVersion}`), "snap controller cache tag matches the installed bundle");
    console.log("Snap-fit UI contract passed: shared library, atomic snapshots, live preview, Edit/Rebuild, tool ownership, stale/retired states, early pushes and delayed native acknowledgments.");
})().catch(error => { console.error(error); process.exitCode = 1; });

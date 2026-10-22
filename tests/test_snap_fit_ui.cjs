"use strict";
// Run both production controllers against a DOM/native-message fixture.
const assert = require("node:assert/strict"), fs = require("node:fs"), vm = require("node:vm"), path = require("node:path");
const ui = path.join(__dirname, "..", "Partelier", "partelier", "ui");
const html = fs.readFileSync(path.join(ui, "palette.html"), "utf8");
const defaults = { width_mm: 8, thickness_mm: 1.5, reach_mm: 16, clearance_mm: .3, hook_depth_mm: 1, lead_in_mm: 3, snap_count: 1, start_margin_mm: 5, end_margin_mm: 5, root_length_mm: 4, attachment_overlap_mm: .5 };
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
        checkValidity() { if (this.tagName === "form") return this.querySelectorAll("[name]").every(x => x.checkValidity()); if (this.disabled || this.type !== "number") return true; const value = Number(this.value), step = Number(this.step), min = Number(this.min); return !this.custom && this.value !== "" && Number.isFinite(value) && value >= min && (this.max === undefined || value <= Number(this.max)) && (!Number.isFinite(step) || Math.abs((value - min) / step - Math.round((value - min) / step)) < 1e-8); }
        reportValidity() { return this.checkValidity(); } focus() {} showModal() {} close() {}
    }
    for (const match of html.matchAll(/<([a-z]+)[^>]*\bid="([^"]+)"/g)) { const element = new Element(match[1]); element.id = match[2]; element.open = /\sopen(?:\s|>)/.test(match[0]); }
    const $ = id => { assert(ids.has(id), `Missing ${id}`); return ids.get(id); };
    for (const id of ["hinge-layout-fields", "hinge-fields", "hinge-fit-fields", "hinge-advanced-fields", "hinge-mode", "hinge-output-fields", "hinge-hole-fields", "hinge-hole-toggle", "hinge-finish-fields", "hinge-finish-choice", "hinge-fillet-fields", "hinge-design-fields"]) $("hinge-settings").append($(id));
    for (const id of ["snap-size-fields", "snap-fit-fields", "snap-layout-fields", "snap-construction-fields"]) $("snap-settings").append($(id));
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
        async input(name, value, debounce = true) { const control = $(`snap-${name}`); control.value = value; for (const fn of $("snap-settings").listeners.input) fn({ target: control }); await flush(); if (debounce) await settle(); }
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
    f.push({ ...committing, sessionId: null, phase: "created", message: "Snap-fit created." });
    f.config.release(); f.config.holdCommit = false; await f.flush();
    assert.equal(f.$("snap-reach_mm").disabled, false);
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
    f.config.saved = { ...defaults, width_mm: 11.2, reach_mm: 22, root_length_mm: 6 };
    await f.click("edit-snap-button");
    assert.equal(f.$("snap-width_mm").value, "11.2");
    assert.equal(f.$("snap-root_length_mm").value, "6");
    assert.equal(f.$("create-snap-button").textContent, "Rebuild snap-fit");
    await f.input("reach_mm", 23);
    await f.click("create-snap-button");
    assert.equal(f.snapshot().settings.reach_mm, 23);
    assert(f.$("snap-operation-status").textContent.includes("rebuilt"));
    await f.select("hinge");
    assert.equal(f.$("snap-action-dock").hidden, true);
    assert.equal(f.$("hinge-action-dock").hidden, false);
    await f.click("begin-hinge-button");
    assert.equal(f.$("tool-select").disabled, true, "hinge geometry session also owns the tool menu");
    await f.click("cancel-hinge-button");
    assert.equal(f.$("tool-select").disabled, false);
    const recovered = fixture({ snap: { ...retiring, sessionId: "d28c515a-66dc-4c66-a57b-111111111111", phase: "preview", settings: { ...defaults, width_mm: 12 } } }); await recovered.flush();
    assert.equal(recovered.$("tool-select").value, "snap", "reopened palette returns to the active snap-fit");
    assert.equal(recovered.$("snap-tool").hidden, false);
    assert.equal(recovered.$("snap-width_mm").value, "12");
    assert.equal(recovered.$("create-snap-button").disabled, false);
    const unavailable = fixture({ capabilities: ["hinge-palette", "hinge-edit"] }); await unavailable.flush(); await unavailable.select("snap");
    assert.equal(unavailable.$("begin-snap-button").disabled, true, "no fake creation action without the native capability");
    assert.equal(unavailable.$("edit-snap-button").disabled, true);
    assert.equal(unavailable.$("snap-availability").hidden, false);
    assert(unavailable.$("snap-illustration").innerHTML.includes("<svg"));
    const bundleVersion = JSON.parse(fs.readFileSync(path.join(__dirname, "../Partelier/Partelier.manifest"), "utf8")).version;
    assert(html.includes(`snap.js?v=${bundleVersion}`), "snap controller cache tag matches the installed bundle");
    console.log("Snap-fit UI contract passed: shared library, atomic snapshots, live preview, Edit/Rebuild, tool ownership, stale/retired states, early pushes and delayed native acknowledgments.");
})().catch(error => { console.error(error); process.exitCode = 1; });

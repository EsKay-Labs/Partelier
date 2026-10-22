"use strict";
// Exercise real palette code with a tiny DOM/host contract fixture, not Fusion.
const assert = require("node:assert/strict"), fs = require("node:fs"), vm = require("node:vm"), path = require("node:path");
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
const root = path.join(__dirname, "..", "Partelier", "partelier", "ui");
const html = fs.readFileSync(path.join(root, "palette.html"), "utf8");
for (const match of html.matchAll(/<([a-z]+)[^>]*\bid="([^"]+)"/g)) { const element = new Element(match[1]); element.id = match[2]; element.open = /\sopen(?:\s|>)/.test(match[0]); }
const byId = id => { assert(ids.has(id), `Missing ${id}`); return ids.get(id); };
for (const id of ["hinge-layout-fields", "hinge-fields", "hinge-fit-fields", "hinge-advanced-fields", "hinge-mode", "hinge-output-fields", "hinge-hole-fields", "hinge-hole-toggle", "hinge-finish-fields", "hinge-finish-choice", "hinge-fillet-fields", "hinge-design-fields"]) byId("hinge-settings").append(byId(id));
const document = { getElementById: byId, createElement: tag => new Element(tag), querySelector: () => new Element("a"), querySelectorAll: () => [], addEventListener() {} };
const requests = [], identity = "caf51e65-f35b-44fc-b748-56ee3e879ae6";
let host = { sessionId: null, revision: 0, phase: "idle", editing: false, settings: null, selections: {}, message: "" }, releasePreview, releaseCommit, holdPreview = false, holdCommit = false, holdPick = false, releasePick, queuedCommit = false, completePick = false, failNextPreview = false;
let timeoutCount = 0, timerSequence = 0, sessionSequence = 0;
let queuedPreview = false, savedEditSettings = null, delayedRetiredPush = null;
const liveTimers = new Map();
const window = { setTimeout: (fn, ms) => { if (ms === 30000) { timeoutCount++; return 0; } if (ms === 160) { const id=++timerSequence; liveTimers.set(id,fn); return id; } return setTimeout(fn, ms); }, clearTimeout: id => { liveTimers.delete(id); clearTimeout(id); }, adsk: { fusionSendData(action, raw) {
    const request = JSON.parse(raw); requests.push([action, request]);
    if (["hinge_focus", "hinge_update", "hinge_preview", "hinge_commit", "hinge_cancel"].includes(action) && request.sessionId !== host.sessionId) {
        return Promise.resolve(JSON.stringify({ protocol: 1, requestId: request.requestId, ok: false, message: "This hinge session has ended." }));
    }
    if (action === "hinge_begin") host = { sessionId: identity.replace(/\w{12}$/, String(++sessionSequence).padStart(12, "0")), revision: 0, phase: "selecting", editing: request.editing, settings: request.editing && savedEditSettings ? { ...savedEditSettings } : request.settings, selections: {}, message: "Select geometry." };
    if (action === "hinge_begin" && completePick) {
        host.selections = Object.fromEntries((request.editing ? ["edit_target"] : ["face_a", "face_b", "axis_edge"]).map(name => [name,{selected:true,label:name}]));
        host.phase = "ready";
    }
    if (action === "hinge_focus") { host.selections[request.target] = { selected: true, label: `Selected ${request.target}` }; host.phase = "ready"; }
    if (["hinge_update", "hinge_preview", "hinge_commit"].includes(action)) { host.settings = request.settings; host.revision = request.revision; host.phase = action === "hinge_preview" ? (queuedPreview ? "computing" : "preview") : action === "hinge_commit" ? "created" : "ready"; host.message = action === "hinge_commit" ? "Hinge created." : action === "hinge_preview" ? "Preview ready." : "Parameters updated."; }
    if (action === "hinge_cancel") { host.phase = "cancelled"; host.sessionId = null; }
    if (action === "hinge_commit") { if (queuedCommit) { host.phase = "opening"; host.message = "Creating hinge…"; } else host.sessionId = null; }
    if (action === "hinge_preview" && failNextPreview) {
        failNextPreview = false;
        return Promise.resolve(JSON.stringify({protocol:1,requestId:request.requestId,ok:false,message:"The fillet radius does not fit the pin."}));
    }
    // An already-sent push can arrive while the next session starts.
    if (action === "hinge_begin" && delayedRetiredPush) {
        const stale = delayedRetiredPush; delayedRetiredPush = null;
        window.fusionJavaScriptHandler.handle("hinge_state", JSON.stringify(stale));
    }
    // Python publishes state during these callbacks, before Qt resolves the request.
    if (["hinge_begin", "hinge_focus"].includes(action)) window.fusionJavaScriptHandler.handle("hinge_state", JSON.stringify(host));
    const result = JSON.stringify({ protocol: 1, requestId: request.requestId, ok: true, capabilities: ["hinge-create", "hinge-edit", "hinge-palette"], hingeState: host });
    if (["hinge_begin", "hinge_focus"].includes(action) && holdPick) return new Promise(resolve => { releasePick = () => resolve(result); });
    if (action === "hinge_preview" && holdPreview) return new Promise(resolve => { releasePreview = () => resolve(result); });
    if (action === "hinge_commit" && holdCommit) return new Promise(resolve => { releaseCommit = () => resolve(result); });
    return Promise.resolve(result);
} } };
const sandbox = { window, document, console, setTimeout, clearTimeout };
vm.createContext(sandbox);
for (const file of ["catalog.js", "illustrations.js", "palette.js"]) vm.runInContext(fs.readFileSync(path.join(root, file), "utf8"), sandbox, { filename: file });
const flush = async () => { for (let i = 0; i < 8; i++) await new Promise(resolve => setImmediate(resolve)); };
const settleLivePreview = async () => { const queued=[...liveTimers]; liveTimers.clear(); for(const [,callback] of queued) callback(); await flush(); };
const input = async (name, value, settle = true) => { const control = byId(`hinge-${name}`); if (control.type === "checkbox") control.checked = value; else control.value = value; for (const listener of byId("hinge-settings").listeners.input) listener({ target: control }); await flush(); if (settle) await settleLivePreview(); };
(async () => {
    await flush();
    assert.equal(byId("create-hinge-button").disabled, true);
    assert.equal(byId("hinge-options").open, false, "advanced settings start collapsed");
    assert.equal(byId("hinge-help").open, false, "large art and explanations start collapsed");
    assert(html.indexOf('id="hinge-help"') < html.indexOf('id="detail-illustration"'));
    assert(html.indexOf('id="tool-workspace"') < html.indexOf('class="action-dock"'));
    const bundleVersion = JSON.parse(fs.readFileSync(path.join(__dirname, "../Partelier/Partelier.manifest"), "utf8")).version;
    assert.equal(byId("model-status").textContent, "Partelier " + bundleVersion, "displayed UI version matches the installed manifest");
    assert(byId("hinge-output-note").textContent.includes("selected bodies"), "attached output explains integration into the selected bodies");
    for (const asset of ["palette.css", "catalog.js", "illustrations.js", "palette.js"]) {
        assert(html.includes(`${asset}?v=${bundleVersion}`), `${asset} cache tag matches the installed bundle`);
    }
    assert.equal(byId("hinge-knuckle_count").parentElement.parentElement.id, "hinge-finish-choice");
    assert.equal(byId("hinge-rotation_clearance_mm").value, "0.3");
    await input("rotation_clearance_mm", 0);
    assert.equal(byId("hinge-settings").checkValidity(), true, "legacy zero movement clearance remains editable");
    await input("rotation_clearance_mm", -.1);
    assert.equal(byId("hinge-settings").checkValidity(), false);
    await input("rotation_clearance_mm", .3);
    assert.equal(byId("hinge-leaf_profile-field").hidden, true);
    assert.equal(byId("hinge-web_profile").value, "tangent");
    assert.equal(byId("hinge-web_profile").disabled, false);
    assert(byId("hinge-web-profile-note").textContent.includes("footprint can extend"));
    assert.equal((byId("detail-illustration").innerHTML.match(/data-tapered-support=/g) || []).length, 5);
    await input("web_profile", "flat");
    assert.equal(byId("detail-illustration").innerHTML.includes("data-tapered-support"), false);
    assert(byId("hinge-web-profile-note").textContent.includes("Flat attachment"));
    await input("web_profile", "tangent");
    assert.equal(byId("hinge-chamfer_size_mm").disabled, true);
    await input("edge_treatment", "chamfer");
    assert.equal(byId("hinge-chamfer_size_mm").disabled, false);
    await input("chamfer_size_mm", 0);
    assert.equal(byId("hinge-settings").checkValidity(), false);
    await input("chamfer_size_mm", .3);
    assert.equal(byId("hinge-settings").checkValidity(), true);
    assert(byId("detail-illustration").innerHTML.includes("data-edge-finish"));
    await input("edge_treatment", "sharp");
    await input("design_preset", "soft");
    assert.equal(byId("hinge-edge_treatment").value, "fillet");
    assert.equal(byId("hinge-fillet_radius_mm").disabled, false);
    assert(byId("detail-illustration").innerHTML.includes("data-fillet-finish"));
    await input("design_preset", "compact"); assert.equal(byId("hinge-knuckle_count").value, "3");
    await input("design_preset", "linear");
    assert.equal(byId("hinge-knuckle_profile").value, "square");
    assert(byId("detail-illustration").innerHTML.includes("data-square-housing"));
    assert.equal(byId("hinge-web_profile").disabled, false, "square housing supports the tapered shape");
    assert.equal((byId("detail-illustration").innerHTML.match(/data-tapered-support=/g) || []).length, 5);
    await input("design_preset", "piano"); assert.equal(byId("hinge-knuckle_count").value, "11");
    await input("design_preset", "classic");
    assert.equal(byId("hinge-fillet-fields").hidden, true);
    assert.equal(byId("hinge-web_profile").disabled, false);
    assert.equal(byId("hinge-web_profile").value, "tangent");
    await input("output_mode", "separate"); assert.equal(byId("hinge-leaf_profile-field").hidden, false);
    assert.equal(byId("hinge-attachment_overlap_mm").disabled, true);
    assert.equal(byId("hinge-web_profile-field").hidden, false);
    assert.equal(byId("hinge-web_profile").disabled, false, "separate leaves support the tapered shape");
    assert.equal((byId("detail-illustration").innerHTML.match(/data-tapered-support=/g) || []).length, 5);
    assert.equal(byId("hinge-attachment_overlap_mm").parentElement.hidden, true);
    assert.equal(byId("hinge-advanced-title").textContent, "Leaf dimensions & placement");
    await input("leaf_profile", "rounded"); await input("screw_holes", true); assert.equal(byId("hinge-screw_diameter_mm").disabled, false);
    assert.equal((byId("detail-illustration").innerHTML.match(/data-screw-hole=/g) || []).length, 4);
    await input("screw_diameter_mm", 0); assert.equal(byId("hinge-settings").checkValidity(), false);
    await input("screw_holes", false); assert.equal(byId("hinge-settings").checkValidity(), true);
    await input("output_mode", "attached"); assert.equal(byId("hinge-leaf_profile").value, "rounded");
    assert.equal(byId("hinge-leaf_barrel_clearance_mm").parentElement.hidden, true);
    assert.equal(byId("hinge-attachment_overlap_mm").disabled, false);
    assert.equal(byId("hinge-web_profile-field").hidden, false);
    assert.equal(byId("hinge-web_profile").disabled, false);
    const timersBeforePick = timeoutCount;
    holdPick = true;
    byId("begin-hinge-button").emit("click"); await flush();
    assert.equal(typeof releasePick, "function");
    assert.equal(timeoutCount, timersBeforePick, "interactive begin must have no 30-second timeout");
    assert.equal(byId("create-hinge-button").disabled, true);
    releasePick(); await flush(); holdPick = false;
    const timersBeforeFocus = timeoutCount;
    holdPick = true;
    byId("select-face_a").emit("click"); await flush();
    assert.equal(timeoutCount, timersBeforeFocus, "interactive repick must wait for the user or Esc");
    releasePick(); await flush(); holdPick = false;
    for (const target of ["face_a", "face_b", "axis_edge"]) { await byId(`select-${target}`).emit("click"); await flush(); }
    assert.equal(host.phase, "preview", "completing selection must automatically preview");
    assert.equal(byId("begin-hinge-button").hidden, true, "selected faces replace the large start button");
    assert.equal(host.settings.web_profile, "tangent");
    assert.equal(host.settings.rotation_clearance_mm, .3);
    const namedSettings = byId("hinge-settings").querySelectorAll("[name]").map(control => control.name).filter(name => !["design_preset", "edge_treatment"].includes(name));
    assert.deepEqual([...Object.keys(host.settings)].sort(), [...namedSettings, "chamfer_edges", "fillet_edges"].sort(), "every basic and advanced setting is serialized");
    byId("hinge-options").open = true; byId("hinge-help").open = true;
    await input("rotation_clearance_mm", 0);
    assert.equal(host.settings.rotation_clearance_mm, 0);
    assert.equal(byId("hinge-options").open, true, "live updates retain the user's disclosure choices");
    await input("rotation_clearance_mm", .4);
    assert.equal(host.settings.rotation_clearance_mm, .4);
    const beforeSupportChange = requests.filter(([action]) => action === "hinge_preview").length;
    await input("web_profile", "flat");
    assert.equal(host.settings.web_profile, "flat");
    assert.equal(requests.filter(([action]) => action === "hinge_preview").length, beforeSupportChange + 1);
    await input("web_profile", "tangent");
    await input("length_mm", 20);
    assert.equal(byId("create-hinge-button").disabled, false);
    const previewsBeforeEdits = requests.filter(([action]) => action === "hinge_preview").length;
    await input("design_preset", "linear", false);
    await input("design_preset", "compact", false);
    await input("design_preset", "soft", false);
    assert.equal(requests.filter(([action]) => action === "hinge_preview").length, previewsBeforeEdits, "rapid edits must wait for debounce");
    assert.equal(byId("create-hinge-button").disabled, true, "Create waits for the current live result");
    await settleLivePreview();
    assert.equal(requests.filter(([action]) => action === "hinge_preview").length, previewsBeforeEdits + 1);
    assert.equal(host.settings.fillet_edges, true);
    assert.equal(host.settings.knuckle_profile, "round");
    assert.equal(byId("live-preview-status").textContent, "Live preview · up to date");
    await input("length_mm", 0);
    await input("design_preset", "classic");
    assert.equal(byId("hinge-settings").checkValidity(), false, "a preset must not make invalid dimensions executable");
    await input("length_mm", 20);
    failNextPreview = true;
    await input("design_preset", "soft");
    assert.equal(byId("live-preview-status").textContent, "Live preview · needs attention", "bridge validation failure must not claim it is still updating");
    assert.equal(byId("create-hinge-button").disabled, true);
    assert.equal(byId("operation-status").hidden, false, "actionable preview errors are always visible");
    await byId("preview-hinge-button").emit("click"); await flush();
    assert.equal(byId("live-preview-status").textContent, "Live preview · up to date");
    await input("design_preset", "classic");
    holdPreview = true;
    const timersBeforePreview = timeoutCount;
    byId("preview-hinge-button").emit("click"); await flush();
    assert.equal(typeof releasePreview, "function");
    assert.equal(timeoutCount, timersBeforePreview, "native geometry must not time out while still running");
    await input("length_mm", 22);
    holdPreview = false; releasePreview(); await flush();
    assert.equal(byId("hinge-length_mm").value, "22", "old preview must not overwrite newer form edits");
    const latest = requests.filter(([action]) => action === "hinge_preview").at(-1)[1];
    assert.equal(latest.settings.length_mm, 22); assert(latest.revision > 1);
    assert.equal(latest.settings.knuckle_profile, "round");
    assert.equal(latest.settings.fillet_edges, false);
    assert.equal("design_preset" in latest.settings, false, "presentation choices must not leak into the strict recipe");
    assert.equal("edge_treatment" in latest.settings, false);
    holdCommit = true;
    byId("create-hinge-button").emit("click"); await flush();
    assert.equal(typeof releaseCommit, "function");
    assert.notEqual(byId("operation-status").textContent, "Hinge created.", "bridge acknowledgement is not native success");
    releaseCommit(); await flush();
    assert.equal(byId("operation-status").textContent, "Hinge created.");
    assert.equal(byId("begin-hinge-button").hidden, false);
    assert.equal(byId("begin-hinge-button").disabled, false);
    assert.equal(byId("create-hinge-button").disabled, true);
    completePick = true; holdCommit = false;
    await byId("begin-hinge-button").emit("click"); await flush();
    assert.equal(host.phase, "preview", "a completed native pick sequence must preview without another click");
    const previewsBeforeCancel = requests.filter(([action])=>action==="hinge_preview").length;
    await input("length_mm", 30, false);
    await byId("cancel-hinge-button").emit("click"); await flush(); await settleLivePreview();
    assert.equal(host.phase, "cancelled");
    assert.equal(requests.filter(([action])=>action==="hinge_preview").length,previewsBeforeCancel,"a cancelled timer must not resurrect preview");
    const commitsBeforeEdit = requests.filter(([action]) => action === "hinge_commit").length;
    savedEditSettings = { ...host.settings, length_mm: 60, hinge_count: 3, knuckle_count: 3, barrel_diameter_mm: 10, pin_diameter_mm: 4, include_pin: false, split_seam: true, chamfer_edges: true, chamfer_size_mm: .8, fillet_edges: false };
    queuedPreview = true; holdPreview = true;
    byId("edit-hinge-button").emit("click"); await flush();
    const editSession = host.sessionId;
    assert.equal(host.editing, true);
    assert.equal(host.phase, "computing", "Edit dispatches its actual saved dimensions for native preview");
    assert.equal(byId("hinge-length_mm").value, "60");
    assert.equal(byId("hinge-hinge_count").value, "3");
    const loadedEditPreview = requests.filter(([action]) => action === "hinge_preview").at(-1)[1];
    assert.equal(loadedEditPreview.settings.chamfer_size_mm, .8);
    assert.equal(loadedEditPreview.settings.include_pin, false);
    assert.equal(loadedEditPreview.settings.split_seam, true);
    host = { ...host, phase: "preview", previewCurrent: true, message: "Edit preview ready." };
    window.fusionJavaScriptHandler.handle("hinge_state", JSON.stringify(host));
    holdPreview = false; releasePreview(); await flush();
    assert.equal(byId("live-preview-status").textContent, "Live preview · up to date", "a delayed computing acknowledgment must not replace a completed preview push");
    assert.equal(byId("create-hinge-button").textContent, "Rebuild hinge");

    holdPreview = true;
    await input("length_mm", 62);
    const earlierPreview = releasePreview;
    await input("hinge_count", 2);
    await input("chamfer_size_mm", .4);
    host = { ...host, phase: "preview", previewCurrent: true, message: "Earlier edit preview ready." };
    const earlierEditState = { ...host };
    window.fusionJavaScriptHandler.handle("hinge_state", JSON.stringify(host));
    assert.equal(byId("hinge-hinge_count").value, "2", "a completion for an older revision cannot reset newer fields");
    assert.equal(byId("hinge-chamfer_size_mm").value, "0.4");
    holdPreview = false; earlierPreview(); await flush();
    const editUpdate = requests.filter(([action]) => action === "hinge_preview").at(-1)[1];
    assert.equal(editUpdate.sessionId, editSession);
    assert.equal(editUpdate.settings.length_mm, 62);
    assert.equal(editUpdate.settings.hinge_count, 2);
    assert.equal(editUpdate.settings.chamfer_size_mm, .4);
    assert(editUpdate.revision > 1, "multiple edit changes advance the session revision");
    host = { ...host, phase: "preview", previewCurrent: true, message: "Latest edit preview ready." };
    window.fusionJavaScriptHandler.handle("hinge_state", JSON.stringify(host));
    assert.equal(byId("live-preview-status").textContent, "Live preview · up to date");
    assert.equal(byId("create-hinge-button").disabled, false);
    window.fusionJavaScriptHandler.handle("hinge_state", JSON.stringify({ ...earlierEditState, phase: "computing", previewCurrent: false }));
    assert.equal(byId("live-preview-status").textContent, "Live preview · up to date", "an older same-session push cannot regress an accepted newer revision");
    assert.equal(byId("create-hinge-button").disabled, false);
    const retiredEditPreview = { ...host };
    await byId("cancel-hinge-button").emit("click"); await flush();
    assert.equal(byId("begin-hinge-button").disabled, false);
    window.fusionJavaScriptHandler.handle("hinge_state", JSON.stringify(retiredEditPreview));
    assert.equal(byId("begin-hinge-button").disabled, false, "a delayed active push must not revive a cancelled session");
    queuedPreview = false; delayedRetiredPush = retiredEditPreview;
    await byId("begin-hinge-button").emit("click"); await flush();
    assert.notEqual(host.sessionId, editSession, "New owns a fresh session after cancelling Edit");
    assert.equal(host.editing, false);
    assert.equal(byId("create-hinge-button").textContent, "Create hinge", "a retired Edit push during New cannot block the actual new session");
    assert.equal(requests.filter(([action]) => action === "hinge_preview").at(-1)[1].sessionId, host.sessionId);
    window.fusionJavaScriptHandler.handle("hinge_state", JSON.stringify(retiredEditPreview));
    assert.equal(byId("create-hinge-button").textContent, "Create hinge", "late retired pushes remain ignored after New becomes active");
    await input("length_mm", 25);
    await input("hinge_count", 1);
    assert.equal(host.settings.length_mm, 25);
    assert.equal(host.settings.hinge_count, 1);
    assert.equal(byId("create-hinge-button").disabled, false, "New remains responsive after Edit updates and Cancel");
    assert.equal(requests.filter(([action]) => action === "hinge_commit").length, commitsBeforeEdit, "Edit previews, parameter changes, Cancel and New never persist a result");
    await byId("cancel-hinge-button").emit("click"); await flush();
    window.fusionJavaScriptHandler.handle("hinge_state", JSON.stringify({ ...host, phase: "error", sessionId: null, message: "Could not start creation." }));
    assert.equal(byId("begin-hinge-button").disabled, false, "closed errors must allow a fresh session");
    holdCommit = false; queuedCommit = true;
    await byId("begin-hinge-button").emit("click"); await flush();
    for (const target of ["face_a", "face_b", "axis_edge"]) { await byId(`select-${target}`).emit("click"); await flush(); }
    await byId("create-hinge-button").emit("click"); await flush();
    assert.equal(byId("create-hinge-button").disabled, true, "queued native commit must block another commit");
    assert.equal(byId("cancel-hinge-button").disabled, true);
    assert.equal(byId("select-face_a").disabled, true);
    assert.equal(byId("hinge-length_mm").disabled, true);
    assert.notEqual(byId("operation-status").textContent, "Hinge created.");
    window.fusionJavaScriptHandler.handle("hinge_state", JSON.stringify({ ...host, sessionId: null, phase: "created", settings: { ...host.settings, split_seam: true }, message: "Hinge created." }));
    assert.equal(byId("begin-hinge-button").disabled, false);
    assert.equal(byId("hinge-length_mm").disabled, false);
    assert.equal(byId("hinge-axis_offset_mm").disabled, true, "unlock must retain the host's effective seam mode");

    await byId("begin-hinge-button").emit("click"); await flush();
    holdCommit = true;
    byId("create-hinge-button").emit("click"); await flush();
    assert.equal(host.phase, "opening");
    const completedSessionPush = { ...host };
    window.fusionJavaScriptHandler.handle("hinge_state", JSON.stringify({ ...host, sessionId: null, phase: "created", message: "Hinge created before acknowledgment." }));
    holdCommit = false; releaseCommit(); await flush();
    assert.equal(byId("begin-hinge-button").disabled, false, "a delayed opening acknowledgment cannot relock completed creation");
    assert.equal(byId("edit-hinge-button").disabled, false);
    assert.equal(byId("hinge-length_mm").disabled, false);
    assert.equal(byId("operation-status").textContent, "Hinge created before acknowledgment.");
    window.fusionJavaScriptHandler.handle("hinge_state", JSON.stringify(completedSessionPush));
    assert.equal(byId("begin-hinge-button").disabled, false, "a completed session cannot be revived by a delayed active push");

    // Retirement is page-local: a newly opened palette trusts ready's active host session.
    const recoveryIds = new Map();
    const recoveryElement = tag => {
        const element = new Element(tag);
        Object.defineProperty(element, "id", { get() { return this._id; }, set(value) { this._id = value; recoveryIds.set(value, this); } });
        return element;
    };
    for (const match of html.matchAll(/<([a-z]+)[^>]*\bid="([^"]+)"/g)) {
        const element = recoveryElement(match[1]); element.id = match[2];
        element.open = /\sopen(?:\s|>)/.test(match[0]);
    }
    const recoveryById = id => { assert(recoveryIds.has(id), "Missing recovery element " + id); return recoveryIds.get(id); };
    for (const child of byId("hinge-settings").children) recoveryById("hinge-settings").append(recoveryById(child.id));
    const recoveryDocument = { getElementById: recoveryById, createElement: recoveryElement, querySelector: () => recoveryElement("a"), querySelectorAll: () => [], addEventListener() {} };
    const recoveryWindow = { PartelierCatalog: window.PartelierCatalog, PartelierIllustrations: window.PartelierIllustrations, setTimeout: window.setTimeout, clearTimeout: window.clearTimeout, adsk: { fusionSendData(action, raw) {
        assert.equal(action, "ready");
        const request = JSON.parse(raw);
        return JSON.stringify({ protocol: 1, requestId: request.requestId, ok: true, capabilities: ["hinge-create", "hinge-edit", "hinge-palette"], hingeState: retiredEditPreview });
    } } };
    vm.runInNewContext(fs.readFileSync(path.join(root, "palette.js"), "utf8"), { window: recoveryWindow, document: recoveryDocument, console, setTimeout, clearTimeout });
    await flush();
    assert.equal(recoveryById("create-hinge-button").textContent, "Rebuild hinge");
    assert.equal(recoveryById("create-hinge-button").disabled, false, "a fresh palette can reconnect to the host's active session");
    assert.equal(recoveryById("hinge-length_mm").value, String(retiredEditPreview.settings.length_mm));
    assert.equal(window.fusionJavaScriptHandler.handle("hinge_state", "broken json"), "FAILED");
    process.stdout.write("Palette UI session contract passed: Edit/Cancel/New, early pushes, stale/retired sessions, delayed acknowledgments, fresh Connect recovery and queued native commit.\n");
})().catch(error => { console.error(error); process.exitCode = 1; });

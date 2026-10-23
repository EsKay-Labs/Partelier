"use strict";
// Exercise all three actual controllers through one native-message fixture.
const assert = require("node:assert/strict"), fs = require("node:fs"), vm = require("node:vm"), path = require("node:path");
const ui = path.join(__dirname, "..", "Partelier", "partelier", "ui"), html = fs.readFileSync(path.join(ui, "palette.html"), "utf8");
const defaults = { pattern: "hexagon", mode: "through", pitch_mm: 8, web_mm: 1.2, depth_mm: 1, border_mm: 2, rotation_deg: 0, offset_u_mm: 0, offset_v_mm: 0, selection_scope: "faces" };
const idle = () => ({ sessionId: null, revision: 0, phase: "idle", editing: false, settings: null, selections: {}, message: "" });
function fixture(options = {}) {
    const ids = new Map();
    class Element {
        constructor(tag="div") { this.tagName=tag; this.children=[]; this.listeners={}; this.disabled=false; this.hidden=false; this.checked=false; this.open=false; this._value=""; this.custom=""; const classes=new Set(); this.classList={add:x=>classes.add(x),remove:x=>classes.delete(x),toggle:(x,on)=>on?classes.add(x):classes.delete(x)}; }
        set id(value) { this._id=value; ids.set(value,this); } get id() { return this._id; }
        set value(value) { this._value=String(value); } get value() { return this._value; }
        append(...items) { for(const item of items) { this.children.push(item); if(item instanceof Element) item.parentElement=this; } }
        replaceChildren(...items) { this.children=[]; this.append(...items); }
        setAttribute(name,value) { this[name]=value; }
        addEventListener(name,handler) { (this.listeners[name] ||= []).push(handler); }
        emit(name) { return Promise.all((this.listeners[name]||[]).map(fn=>fn({target:this,preventDefault(){}}))); }
        querySelectorAll(selector) { const all=[]; const visit=element=>{for(const child of element.children) if(child instanceof Element) {if(selector==="[name]"?!!child.name:child.tagName==="input"&&child.type==="number"&&child.disabled) all.push(child);visit(child);}};visit(this);return all; }
        setCustomValidity(message) { this.custom=message; }
        checkValidity() { if(this.tagName==="form") return this.querySelectorAll("[name]").every(x=>x.checkValidity()); if(this.disabled) return true; if(this.custom) return false; if(this.tagName==="select"&&this.required) return this.children.some(x=>x.value===this.value); if(this.type!=="number") return true; const v=Number(this.value),s=Number(this.step),m=this.min===undefined?-Infinity:Number(this.min); return this.value!==""&&Number.isFinite(v)&&v>=m&&(this.max===undefined||v<=Number(this.max))&&(!Number.isFinite(s)||Math.abs((v-m)/s-Math.round((v-m)/s))<1e-8); }
        reportValidity() { return this.checkValidity(); } focus() {} showModal() {} close() {}
    }
    for(const match of html.matchAll(/<([a-z]+)[^>]*\bid="([^"]+)"/g)) { const e=new Element(match[1]);e.id=match[2]; }
    const $=id=>{assert(ids.has(id),`Missing ${id}`);return ids.get(id);};
    for(const id of ["hinge-layout-fields","hinge-fields","hinge-fit-fields","hinge-advanced-fields","hinge-mode","hinge-output-fields","hinge-hole-fields","hinge-hole-toggle","hinge-finish-fields","hinge-finish-choice","hinge-fillet-fields","hinge-design-fields"]) $("hinge-settings").append($(id));
    for(const id of ["snap-family-fields","snap-style-fields","snap-size-fields","snap-fit-fields","snap-layout-fields","snap-construction-fields","snap-finish-toggle","snap-finish-fields","snap-ball-fields","snap-torsion-fields","snap-annular-fields"]) $("snap-settings").append($(id));
    for(const id of ["pattern-design-fields","pattern-size-fields","pattern-scope-fields","pattern-placement-fields"]) $("pattern-settings").append($(id));
    const document={getElementById:$,createElement:tag=>new Element(tag),querySelector:()=>new Element("a"),querySelectorAll:()=>[],addEventListener(){}};
    const requests=[],timers=new Map(),config={...options,holdPick:false,holdPreview:false,queuedPreview:false,holdCommit:false,release:null,failPreview:false,delayedPush:null,saved:null};
    let host=options.pattern||idle(),hinge=options.hinge||idle(),snap=options.snap||idle(),sequence=0,timerSequence=0,timeouts=0;
    const clone=x=>JSON.parse(JSON.stringify(x)),push=x=>window.fusionJavaScriptHandler.handle("pattern_state",JSON.stringify(x));
    const window={setTimeout(fn,ms){if(ms===30000){timeouts++;return 0;}if(ms===160){const id=++timerSequence;timers.set(id,fn);return id;}return setTimeout(fn,ms);},clearTimeout(id){timers.delete(id);clearTimeout(id);},adsk:{fusionSendData(action,raw){
        const request=JSON.parse(raw);requests.push([action,request]);
        const respond=(ok=true,message)=>JSON.stringify({protocol:1,requestId:request.requestId,ok,message,capabilities:config.capabilities||["hinge-palette","hinge-edit","snap-palette","snap-edit","pattern-palette","pattern-edit"],hingeState:clone(hinge),snapState:clone(snap),patternState:clone(host),patternDefaults:defaults});
        for(const tool of ["hinge","snap"]) if(action.startsWith(tool+"_")) {
            let other=tool==="hinge"?hinge:snap;
            if(action===tool+"_begin") other={...idle(),sessionId:`a12dd31d-b2ca-4f47-8237-${tool==="hinge"?"111111111111":"222222222222"}`,phase:"selecting",settings:request.settings};
            if(action===tool+"_cancel") other={...other,sessionId:null,phase:"cancelled"};
            if(tool==="hinge")hinge=other;else snap=other;
            window.fusionJavaScriptHandler.handle(tool+"_state",JSON.stringify(other));return Promise.resolve(respond());
        }
        if(["pattern_update","pattern_preview","pattern_commit","pattern_cancel","pattern_focus"].includes(action)&&request.sessionId!==host.sessionId) return Promise.resolve(respond(false,"This pattern session has ended."));
        if(action==="pattern_begin") {
            host={...idle(),sessionId:"d28c515a-66dc-4c66-a57b-"+String(++sequence).padStart(12,"0"),phase:"selecting",editing:request.editing,settings:request.editing&&config.saved?{...config.saved}:request.settings};
            if(config.completePick){host.selections={surface:{selected:true,label:"3 supported faces"}};host.phase="ready";}
            if(config.delayedPush){push(config.delayedPush);config.delayedPush=null;}push(host);
        }
        if(action==="pattern_focus"){host.selections={surface:{selected:true,label:request.target==="body"?"Hexagonal body":"3 supported faces"}};host.phase="ready";push(host);}
        if(["pattern_update","pattern_preview","pattern_commit"].includes(action)) {
            if(host.settings.selection_scope!==request.settings.selection_scope)host.selections={};
            host.settings=request.settings;host.revision=request.revision;
            host.phase=action==="pattern_commit"?config.holdCommit?"opening":"created":host.selections.surface?.selected?action==="pattern_preview"?config.queuedPreview?"computing":"preview":"ready":"selecting";
            host.message=action==="pattern_commit"?host.editing?"Pattern rebuilt.":"Pattern created.":"Preview ready.";
            if(action==="pattern_commit"&&!config.holdCommit)host.sessionId=null;
        }
        if(action==="pattern_cancel"){host.phase="cancelled";host.sessionId=null;host.message="Pattern cancelled.";}
        if(action==="pattern_preview"&&config.failPreview){config.failPreview=false;return Promise.resolve(respond(false,"Offset failed on this curved face. Reduce depth."));}
        const result=respond();
        if(["pattern_begin","pattern_focus"].includes(action)&&config.holdPick||action==="pattern_preview"&&config.holdPreview||action==="pattern_commit"&&config.holdCommit)return new Promise(resolve=>{config.release=()=>resolve(result);});
        return Promise.resolve(result);
    }}};
    const context=vm.createContext({window,document,console,setTimeout,clearTimeout});
    for(const file of ["catalog.js","illustrations.js","snap.js","patterns.js","palette.js"])vm.runInContext(fs.readFileSync(path.join(ui,file),"utf8"),context,{filename:file});
    const flush=async()=>{for(let i=0;i<8;i++)await new Promise(resolve=>setImmediate(resolve));};
    const settle=async()=>{const pending=[...timers.values()];timers.clear();pending.forEach(fn=>fn());await flush();};
    return {$,window,requests,config,flush,settle,push,snapshot:()=>clone(host),timeouts:()=>timeouts,
        async select(id){$("tool-select").value=id;await $("tool-select").emit("change");await flush();},
        async click(id){await $(id).emit("click");await flush();},
        async input(name,value,debounce=true){const input=$("pattern-"+name);input.value=value;for(const fn of $("pattern-settings").listeners.input)fn({target:input});await flush();if(debounce)await settle();}
    };
}
(async()=>{
    const f=fixture();await f.flush();await f.select("honeycomb");
    assert.equal(f.$("pattern-tool").hidden,false);assert.equal(f.$("planned-tool").hidden,true);assert.equal(f.$("hinge-action-dock").hidden,true);assert.equal(f.$("snap-action-dock").hidden,true);
    assert.equal(f.$("pattern-pattern").value,"hexagon");assert.equal(f.$("pattern-mode").value,"through");assert.equal(f.$("pattern-depth_mm").disabled,true);
    assert.equal(f.$("begin-pattern-button").disabled,false);assert.equal(f.$("create-pattern-button").disabled,true);
    assert.deepEqual(f.$("pattern-settings").querySelectorAll("[name]").map(x=>x.name).sort(),Object.keys(defaults).sort());
    assert(f.$("pattern-illustration").innerHTML.includes('data-pattern-surface="cylinder"'));assert(f.$("pattern-illustration").innerHTML.includes('data-pattern-cell="hexagon"'));
    const hexArt=f.$("pattern-illustration").innerHTML;
    await f.input("pitch_mm",9);await f.select("perforation");assert.equal(f.$("pattern-pattern").value,"circle");assert.equal(f.$("pattern-pitch_mm").value,"9");
    await f.select("knurl");assert.equal(f.$("pattern-pattern").value,"diamond");assert.equal(f.$("pattern-mode").value,"emboss");assert.equal(f.$("pattern-depth_mm").disabled,false);
    assert.notEqual(f.$("pattern-illustration").innerHTML,hexArt,"texture has a raised wrapped mesh rather than a hexagonal opening label");
    for(const [name,value]of[["rotation_deg",-30],["offset_u_mm",-1.5],["offset_v_mm",0],["border_mm",0]])await f.input(name,value);
    assert.equal(f.$("pattern-settings").checkValidity(),true,"offsets/rotation are signed and border may be zero");
    f.config.holdPick=true;const timeouts=f.timeouts();f.$("begin-pattern-button").emit("click");await f.flush();assert.equal(f.timeouts(),timeouts);assert.equal(f.$("tool-select").disabled,true);
    f.config.release();f.config.holdPick=false;await f.flush();await f.click("pattern-select-surface");assert.equal(f.snapshot().phase,"preview");assert.equal(f.$("create-pattern-button").disabled,false);
    assert.equal(f.requests.filter(([a])=>a==="pattern_focus").at(-1)[1].target,"faces");
    const activeSettings=f.snapshot().settings;f.window.PartelierPatterns.select("honeycomb");assert.equal(f.$("pattern-pattern").value,activeSettings.pattern,"an active session ignores alias presets");
    f.window.PartelierSnap.setHingeActive(false);assert.equal(f.$("tool-select").disabled,true,"Snap rendering cannot unlock an active pattern session");
    f.window.fusionJavaScriptHandler.handle("hinge_state",JSON.stringify(idle()));assert.equal(f.$("tool-select").disabled,true);
    const previews=()=>f.requests.filter(([a])=>a==="pattern_preview").length,before=previews();
    await f.input("pitch_mm",10,false);await f.input("pitch_mm",11,false);assert.equal(previews(),before);assert.equal(f.$("create-pattern-button").disabled,true);await f.settle();assert.equal(previews(),before+1);
    assert.deepEqual(Object.keys(f.snapshot().settings).sort(),Object.keys(defaults).sort());assert.equal(f.snapshot().settings.offset_u_mm,-1.5);assert.equal(typeof f.snapshot().settings.pattern,"string");
    await f.input("mode","engrave");assert.equal(f.$("pattern-depth_mm").parentElement.children[0].textContent,"Engraving depth");
    const invalidBefore=f.requests.length;await f.input("depth_mm",0);assert.equal(f.$("pattern-settings").checkValidity(),false);assert.equal(f.requests.length,invalidBefore);
    await f.input("mode","through");assert.equal(f.snapshot().settings.depth_mm,1);assert.equal(f.$("pattern-depth_mm").disabled,true);assert.equal(f.$("pattern-settings").checkValidity(),true);
    f.config.failPreview=true;await f.input("web_mm",1.4);assert.equal(f.$("create-pattern-button").disabled,true);assert(f.$("pattern-operation-status").textContent.includes("Reduce depth"));await f.click("preview-pattern-button");assert.equal(f.$("create-pattern-button").disabled,false);
    f.config.queuedPreview=true;f.config.holdPreview=true;await f.input("pattern","slot",false);await f.settle();const computing=f.snapshot();assert.equal(computing.phase,"computing");f.push({...computing,phase:"preview"});f.config.release();f.config.holdPreview=false;f.config.queuedPreview=false;await f.flush();assert.equal(f.$("create-pattern-button").disabled,false,"late computing acknowledgments cannot replace pushed previews");
    f.push({...computing,revision:computing.revision-1,settings:{...defaults,pitch_mm:99},phase:"preview"});assert.equal(f.$("pattern-pitch_mm").value,"11");
    await f.input("selection_scope","body",false);assert.equal(f.$("create-pattern-button").disabled,true);await f.settle();assert.deepEqual(f.snapshot().selections,{});assert.equal(f.requests.at(-1)[0],"pattern_update");
    await f.click("pattern-select-surface");assert.equal(f.requests.filter(([a])=>a==="pattern_focus").at(-1)[1].target,"body");assert.equal(f.$("create-pattern-button").disabled,false);
    f.config.holdCommit=true;f.$("create-pattern-button").emit("click");await f.flush();const committing=f.snapshot();f.push(committing);assert.equal(f.$("pattern-pattern").disabled,true);f.push({...committing,sessionId:null,phase:"created",message:"Pattern created."});f.config.release();f.config.holdCommit=false;await f.flush();assert.equal(f.$("tool-select").disabled,false);assert.equal(f.$("cancel-pattern-button").disabled,true);
    f.config.completePick=true;await f.click("begin-pattern-button");const retiring=f.snapshot();await f.click("cancel-pattern-button");f.push({...retiring,phase:"preview"});assert.equal(f.$("tool-select").disabled,false);f.config.delayedPush={...retiring,phase:"preview"};await f.click("begin-pattern-button");assert.notEqual(f.snapshot().sessionId,retiring.sessionId);await f.click("cancel-pattern-button");
    f.config.saved={...defaults,pattern:"square",mode:"engrave",pitch_mm:12,depth_mm:.7,selection_scope:"body"};await f.click("edit-pattern-button");assert.equal(f.$("pattern-pattern").value,"square");assert.equal(f.$("pattern-depth_mm").value,"0.7");assert.equal(f.$("pattern-selection_scope").disabled,true);
    const beforeScope=f.requests.length;await f.input("selection_scope","faces");assert.equal(f.requests.length,beforeScope);assert.equal(f.$("pattern-selection_scope").value,"body");await f.input("depth_mm",.8);await f.click("create-pattern-button");assert.equal(f.snapshot().settings.depth_mm,.8);assert.equal(f.$("pattern-selection_scope").disabled,false);
    await f.select("snap");await f.click("begin-snap-button");assert.equal(f.$("tool-select").disabled,true);await f.select("honeycomb");assert.equal(f.$("begin-pattern-button").disabled,true,"Snap and Pattern cannot claim geometry together");await f.select("snap");await f.click("cancel-snap-button");assert.equal(f.$("tool-select").disabled,false);
    await f.select("hinge");await f.click("begin-hinge-button");assert.equal(f.$("tool-select").disabled,true);await f.click("cancel-hinge-button");assert.equal(f.$("tool-select").disabled,false);
    const recovered=fixture({pattern:{...retiring,sessionId:"d28c515a-66dc-4c66-a57b-999999999999",phase:"preview",settings:{...defaults,pattern:"circle",mode:"engrave",depth_mm:.6}}});await recovered.flush();assert.equal(recovered.$("tool-select").value,"perforation");assert.equal(recovered.$("pattern-mode").value,"engrave");assert.equal(recovered.$("create-pattern-button").disabled,false);
    const unavailable=fixture({capabilities:["hinge-palette","snap-palette"]});await unavailable.flush();await unavailable.select("honeycomb");assert.equal(unavailable.$("begin-pattern-button").disabled,true);assert.equal(unavailable.$("edit-pattern-button").disabled,true);assert.equal(unavailable.$("pattern-availability").hidden,false);
    const version=JSON.parse(fs.readFileSync(path.join(__dirname,"../Partelier/Partelier.manifest"),"utf8")).version;assert(html.includes(`patterns.js?v=${version}`));
    console.log("Pattern UI contract passed: presets, typed full snapshots, surface scopes, modes, live preview, Edit/Rebuild, three-tool locks, stale sessions and native acknowledgment ordering.");
})().catch(error=>{console.error(error);process.exitCode=1;});

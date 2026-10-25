"use strict";
// Exercise all three actual controllers through one native-message fixture.
const assert = require("node:assert/strict"), fs = require("node:fs"), vm = require("node:vm"), path = require("node:path");
const ui = path.join(__dirname, "..", "Partelier", "partelier", "ui"), html = fs.readFileSync(path.join(ui, "palette.html"), "utf8");
const defaults = { pattern: "hexagon", mode: "through", pitch_mm: 19.5, web_mm: 7, depth_mm: 1, border_mm: 7, rotation_deg: 0, offset_u_mm: 0, offset_v_mm: 0, selection_scope: "faces", layout_mode: "auto", edge_mode: "clip", density: "balanced", size_locked: false, louver_angle_deg: 45, grille_profile: "flat", grille_height_mm: 3, mount_mode: "off", mount_screw: "M4", mount_clearance_mm: .3, mount_head_extra_percent: 10, mount_head_mm: 0, mount_inset_mm: 0, truss_bays: 6, truss_axis: "long" };
const idle = () => ({ sessionId: null, revision: 0, phase: "idle", editing: false, settings: null, selections: {}, message: "" });
function fixture(options = {}) {
    const ids = new Map();
    class Element {
        constructor(tag="div") { this.tagName=tag; this.children=[]; this.listeners={}; this.disabled=false; this.hidden=false; this.checked=false; this.open=false; this._value=""; this.custom=""; const classes=new Set(); this.classList={add:x=>classes.add(x),remove:x=>classes.delete(x),toggle:(x,on)=>on?classes.add(x):classes.delete(x)}; }
        set id(value) { this._id=value; ids.set(value,this); } get id() { return this._id; }
        set value(value) { this._value=String(value); } get value() { return this._value; }
        append(...items) { for(const item of items) { if(item instanceof Element && item.parentElement) item.parentElement.children=item.parentElement.children.filter(child=>child!==item);this.children.push(item); if(item instanceof Element) item.parentElement=this; } }
        replaceChildren(...items) { this.children=[]; this.append(...items); }
        setAttribute(name,value) { this[name]=value; }
        addEventListener(name,handler) { (this.listeners[name] ||= []).push(handler); }
        emit(name) { return Promise.all((this.listeners[name]||[]).map(fn=>fn({target:this,preventDefault(){}}))); }
        querySelectorAll(selector) { const all=[]; const visit=element=>{for(const child of element.children) if(child instanceof Element) {if(selector==="[name]"?!!child.name:child.tagName==="input"&&child.type==="number"&&child.disabled) all.push(child);visit(child);}};visit(this);return all; }
        setCustomValidity(message) { this.custom=message; }
        checkValidity() { if(this.tagName==="form") return this.querySelectorAll("[name]").every(x=>x.checkValidity()); if(this.disabled) return true; if(this.custom) return false; if(this.tagName==="select"&&this.required) return this.children.some(x=>x.value===this.value); if(this.type!=="number") return true; const v=Number(this.value),s=Number(this.step),m=this.min===undefined?-Infinity:Number(this.min); return this.value!==""&&Number.isFinite(v)&&v>=m&&(this.max===undefined||v<=Number(this.max))&&(!Number.isFinite(s)||Math.abs((v-m)/s-Math.round((v-m)/s))<1e-8); }
        reportValidity() { return this.checkValidity(); } focus() { this.focused=true; } showModal() { this.open=true; } close() { this.open=false; this.emit("close"); }
    }
    for(const match of html.matchAll(/<([a-z]+)[^>]*\bid="([^"]+)"/g)) { const e=new Element(match[1]);e.id=match[2]; }
    const $=id=>{assert(ids.has(id),`Missing ${id}`);return ids.get(id);};
    for(const id of ["hinge-layout-fields","hinge-fields","hinge-fit-fields","hinge-advanced-fields","hinge-mode","hinge-output-fields","hinge-hole-fields","hinge-hole-toggle","hinge-finish-fields","hinge-finish-choice","hinge-fillet-fields","hinge-design-fields"]) $("hinge-settings").append($(id));
    for(const id of ["snap-family-fields","snap-style-fields","snap-size-fields","snap-fit-fields","snap-layout-fields","snap-construction-fields","snap-finish-toggle","snap-finish-fields","snap-ball-fields","snap-torsion-fields","snap-annular-fields"]) $("snap-settings").append($(id));
    for(const id of ["pattern-design-fields","pattern-size-fields","pattern-scope-fields","pattern-placement-fields","pattern-mount-controls","pattern-mount-fields"]) $("pattern-settings").append($(id));
    const documentListeners=new Map();
    const document={getElementById:$,createElement:tag=>new Element(tag),querySelector:()=>new Element("a"),querySelectorAll:()=>[],addEventListener(name,handler){(documentListeners.get(name)||documentListeners.set(name,[]).get(name)).push(handler);}};
    const requests=[],timers=new Map(),storage=new Map(Object.entries(options.storageSeed||{})),listeners=new Map(),config={...options,holdPick:false,holdPreview:false,queuedPreview:false,holdCommit:false,holdStatus:false,statusReleases:[],release:null,failPreview:false,failDiagnostic:false,holdDiagnostic:false,delayedPush:null,saved:null};
    let host=options.pattern||idle(),hinge=options.hinge||idle(),snap=options.snap||idle(),sequence=0,timerSequence=0,timeouts=0;
    const clone=x=>JSON.parse(JSON.stringify(x)),push=x=>window.fusionJavaScriptHandler.handle("pattern_state",JSON.stringify(x));
    const window={localStorage:{getItem:key=>{if(config.storageFailure)throw Error("storage unavailable");return storage.get(key)||null;},setItem:(key,value)=>{if(config.storageFailure)throw Error("storage unavailable");storage.set(key,value);}},addEventListener(name,handler){(listeners.get(name)||listeners.set(name,[]).get(name)).push(handler);},setTimeout(fn,ms){if(ms===30000){timeouts++;return 0;}if([160,400,2000,5000].includes(ms)){const id=++timerSequence;timers.set(id,{fn,ms});return id;}return setTimeout(fn,ms);},clearTimeout(id){timers.delete(id);clearTimeout(id);},adsk:{fusionSendData(action,raw){
        const request=JSON.parse(raw);requests.push([action,request]);
        if(action==="diagnostic_log"){if(config.failDiagnostic)return Promise.reject(Error("diagnostic endpoint unavailable"));if(config.holdDiagnostic)return new Promise(()=>{});return Promise.resolve(JSON.stringify({protocol:1,requestId:request.requestId,ok:true}));}
        const respond=(ok=true,message)=>JSON.stringify({protocol:1,requestId:request.requestId,ok,message,capabilities:config.capabilities||["hinge-palette","hinge-edit","snap-palette","snap-edit","pattern-palette","pattern-edit"],hingeState:clone(hinge),snapState:clone(snap),patternState:clone(host),patternDefaults:defaults});
        for(const tool of ["hinge","snap"]) if(action.startsWith(tool+"_")) {
            let other=tool==="hinge"?hinge:snap;
            if(action===tool+"_begin") other={...idle(),sessionId:`a12dd31d-b2ca-4f47-8237-${tool==="hinge"?"111111111111":"222222222222"}`,phase:"selecting",settings:request.settings};
            if(action===tool+"_cancel") other={...other,sessionId:null,phase:"cancelled"};
            if(tool==="hinge")hinge=other;else snap=other;
            window.fusionJavaScriptHandler.handle(tool+"_state",JSON.stringify(other));return Promise.resolve(respond());
        }
        if(["pattern_update","pattern_preview","pattern_commit","pattern_cancel","pattern_focus","pattern_finish_faces","pattern_clear_faces"].includes(action)&&request.sessionId!==host.sessionId) return Promise.resolve(respond(false,"This pattern session has ended."));
        if(action==="pattern_begin") {
            host={...idle(),sessionId:"d28c515a-66dc-4c66-a57b-"+String(++sequence).padStart(12,"0"),phase:"selecting",editing:request.editing,settings:request.editing&&config.saved?{...config.saved}:request.settings};
            if(config.completePick){host.selections={surface:{selected:true,label:"3 supported faces"}};host.phase="ready";}
            if(!request.editing&&host.settings.selection_scope==="faces"){host.pickingFaces=true;host.canFinishFaces=!!config.completePick;host.phase="picking_faces";}
            if(config.delayedPush){push(config.delayedPush);config.delayedPush=null;}push(host);
        }
        if(action==="pattern_focus"){
            if(["add_face","faces"].includes(request.target)){host.selections={surface:{selected:true,label:"3 supported faces"}};host.pickingFaces=true;host.canFinishFaces=true;host.phase="picking_faces";}
            else {host.selections={surface:{selected:true,label:request.target==="body"?"Hexagonal body":"3 supported faces"}};host.phase="ready";}
            push(host);
        }
        if(action==="pattern_clear_faces"){host.selections={surface:{selected:false,label:"Not selected"}};host.canFinishFaces=false;push(host);}
        if(action==="pattern_finish_faces"){host.pickingFaces=false;host.canFinishFaces=false;host.phase="ready";push(host);}
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
        if(action==="pattern_status"&&config.holdStatus)return new Promise(resolve=>config.statusReleases.push(()=>resolve(result)));
        if(["pattern_begin","pattern_focus"].includes(action)&&config.holdPick||action==="pattern_preview"&&config.holdPreview||action==="pattern_commit"&&config.holdCommit)return new Promise(resolve=>{config.release=()=>resolve(result);});
        return Promise.resolve(result);
    }}};
    const context=vm.createContext({window,document,console,setTimeout,clearTimeout});
    for(const file of ["catalog.js","illustrations.js","pattern-help.js","snap.js","patterns.js","palette.js"])vm.runInContext(fs.readFileSync(path.join(ui,file),"utf8"),context,{filename:file});
    const flush=async()=>{for(let i=0;i<8;i++)await new Promise(resolve=>setImmediate(resolve));};
    const advance=async ms=>{const pending=[...timers.entries()].filter(([,timer])=>timer.ms===ms);pending.forEach(([id])=>timers.delete(id));pending.forEach(([,timer])=>timer.fn());await flush();};
    const settle=()=>advance(160);
    return {$,window,requests,config,flush,settle,advance,push,storage,emitWindow:(name,event)=>{for(const handler of listeners.get(name)||[])handler(event);},emitDocument:(name,event)=>{for(const handler of documentListeners.get(name)||[])handler(event);},setHost:snapshot=>{host=clone(snapshot);},snapshot:()=>clone(host),timeouts:()=>timeouts,pendingTimers:ms=>[...timers.values()].filter(timer=>timer.ms===ms).length,
        async select(id){$("tool-select").value=id;await $("tool-select").emit("change");await flush();},
        async begin(){await this.click("begin-pattern-button");if(host.pickingFaces&&host.canFinishFaces)await this.click("pattern-finish-faces");},
        async click(id){await $(id).emit("click");await flush();},
        async input(name,value,debounce=true){const input=$("pattern-"+name);input.value=value;for(const fn of $("pattern-settings").listeners.input)fn({target:input});await flush();if(debounce)await settle();}
    };
}
(async()=>{
    const trussUI=fixture({completePick:true});await trussUI.flush();await trussUI.select("truss");
    assert.deepEqual(trussUI.$("pattern-pattern").children.map(option=>option.value),["truss_warren","truss_pratt","truss_howe"]);
    assert.equal(trussUI.$("pattern-cell_size_mm").parentElement.hidden,true);
    assert.equal(trussUI.$("pattern-mode").parentElement.hidden,true);
    assert.equal(trussUI.$("pattern-mounting").hidden,true);
    assert.equal(trussUI.$("pattern-grille_profile").parentElement.hidden,true);
    assert.equal(trussUI.$("pattern-web_mm").parentElement.children[0].textContent,"Member width (mm)");
    assert.equal(trussUI.$("pattern-border_mm").parentElement.children[0].textContent,"Frame width (mm)");
    assert.equal(trussUI.$("pattern-truss_bays").parentElement.hidden,false);
    assert.equal(trussUI.$("pattern-truss_axis").parentElement.hidden,false);
    assert(trussUI.$("pattern-illustration").innerHTML.includes('data-truss-style="truss_warren"'));
    await trussUI.begin();assert.equal(trussUI.snapshot().settings.truss_bays,6);
    assert.equal(trussUI.$("create-pattern-button").textContent,"Create truss");
    for(const name of ["pattern","truss_bays","truss_axis","web_mm","border_mm"]) {
        await trussUI.click("pattern-help-"+name);assert(trussUI.$("pattern-help-title").textContent.length>6);
        assert(trussUI.$("pattern-help-image").innerHTML.includes('data-help-image="truss_'));
        await trussUI.click("pattern-help-close");
    }
    await trussUI.input("pattern","truss_pratt");await trussUI.input("truss_bays",8);
    assert.equal(trussUI.snapshot().settings.pattern,"truss_pratt");assert.equal(trussUI.snapshot().settings.truss_bays,8);
    await trussUI.input("truss_axis","short");assert.equal(trussUI.snapshot().settings.truss_axis,"short");
    const beforeOdd=trussUI.requests.filter(([a])=>a==="pattern_preview").length;
    await trussUI.input("truss_bays",5);assert.equal(trussUI.$("pattern-settings").checkValidity(),false);
    assert.equal(trussUI.requests.filter(([a])=>a==="pattern_preview").length,beforeOdd);
    await trussUI.input("pattern","truss_warren");assert.equal(trussUI.$("pattern-settings").checkValidity(),true);
    await trussUI.click("cancel-pattern-button");await trussUI.select("honeycomb");
    assert.equal(trussUI.$("pattern-truss_bays").parentElement.hidden,true);
    assert.equal(trussUI.$("pattern-cell_size_mm").parentElement.hidden,false);
    assert.equal(trussUI.$("pattern-rotation_deg").parentElement.hidden,false);
    assert.equal(trussUI.$("pattern-offset_v_mm").parentElement.hidden,false);
    const grilleUI=fixture({completePick:true});await grilleUI.flush();await grilleUI.select("grilles");
    const patternGroup=grilleUI.$("tool-select").children.find(group=>group.label==="Patterns");
    assert.deepEqual(patternGroup.children.map(option=>option.value),["honeycomb","truss","grilles"],"Grilles is the third Patterns entry, separate from Truss");
    assert.deepEqual(grilleUI.$("pattern-pattern").children.map(option=>option.value),["grille_parallel","grille_cross","grille_louver"]);
    assert.equal(grilleUI.$("pattern-cell_size_mm").parentElement.children[0].textContent,"Opening width");
    assert.equal(grilleUI.$("pattern-web_mm").parentElement.children[0].textContent,"Rib width · on face");
    assert.equal(grilleUI.$("pattern-mode").parentElement.hidden,true);
    assert.equal(grilleUI.$("pattern-louver_angle_deg").parentElement.hidden,true);
    assert.equal(grilleUI.$("pattern-mounting").hidden,false);
    assert.equal(grilleUI.$("pattern-mount_mode").value,"off");
    assert.equal(grilleUI.$("pattern-mount-options").hidden,true);
    await grilleUI.click("pattern-help-pattern");assert(grilleUI.$("pattern-help-title").textContent.includes("Grille type"));await grilleUI.click("pattern-help-close");
    assert.equal(grilleUI.$("pattern-rotation_deg").parentElement.parentElement.id,"pattern-design-fields");
    assert.equal(grilleUI.$("pattern-rotation_deg").parentElement.children[0].textContent,"Direction (°)");
    await grilleUI.click("pattern-help-rotation_deg");assert(grilleUI.$("pattern-help-title").textContent.includes("Direction"));assert(grilleUI.$("pattern-help-image").innerHTML.includes('data-help-image="grille_direction"'));await grilleUI.click("pattern-help-close");
    await grilleUI.begin();
    const directionPreviews=grilleUI.requests.filter(([a])=>a==="pattern_preview").length;
    await grilleUI.click("grille-direction-45");await grilleUI.settle();
    assert.equal(grilleUI.snapshot().settings.rotation_deg,45);
    assert(grilleUI.$("pattern-illustration").innerHTML.includes('data-grille-direction="45"'));
    assert.equal(grilleUI.$("grille-direction-45")["aria-pressed"],"true");
    assert.equal(grilleUI.requests.filter(([a])=>a==="pattern_preview").length,directionPreviews+1);
    await grilleUI.input("rotation_deg",27);
    assert.equal(grilleUI.$("grille-direction-45")["aria-pressed"],"false");
    await grilleUI.input("pattern","grille_louver");
    assert.equal(grilleUI.$("pattern-louver_angle_deg").parentElement.hidden,false);
    await grilleUI.input("louver_angle_deg",0);
    assert.equal(grilleUI.$("pattern-settings").checkValidity(),true,"zero tilt is a valid straight channel");
    assert.equal(grilleUI.snapshot().settings.louver_angle_deg,0);
    assert(grilleUI.$("pattern-illustration").innerHTML.includes('data-grille-section="0"'));
    const zeroTilt=grilleUI.$("pattern-illustration").innerHTML;
    await grilleUI.input("louver_angle_deg",45);
    assert.notEqual(grilleUI.$("pattern-illustration").innerHTML,zeroTilt);
    await grilleUI.input("rotation_deg",225);
    assert.equal(grilleUI.$("grille-direction-45")["aria-pressed"],"false","inclined channels at 225 degrees reverse their tilt compared with 45");
    await grilleUI.input("grille_profile","raised");
    assert.equal(grilleUI.$("pattern-grille_height_mm").parentElement.hidden,false);
    assert.equal(grilleUI.$("pattern-louver_angle_deg").parentElement.hidden,false,"external louvers also expose adjustable tilt");
    assert.equal(grilleUI.$("pattern-selection_scope").disabled,true);
    assert(grilleUI.$("pattern-illustration").innerHTML.includes('data-grille-profile="raised"'));
    assert(grilleUI.$("pattern-illustration").innerHTML.includes('Back to bed'));
    assert.equal(grilleUI.$("pattern-louver_angle_deg").max,"45");
    const originalTiltArt=grilleUI.$("pattern-illustration").innerHTML;
    await grilleUI.input("louver_angle_deg",20);
    assert.equal(grilleUI.snapshot().settings.louver_angle_deg,20);
    assert(grilleUI.$("pattern-illustration").innerHTML.includes('data-grille-tilt="20"'));
    assert.notEqual(grilleUI.$("pattern-illustration").innerHTML,originalTiltArt);
    const validTiltPreviews=grilleUI.requests.filter(([a])=>a==="pattern_preview").length;
    await grilleUI.input("louver_angle_deg",46);
    assert.equal(grilleUI.$("pattern-settings").checkValidity(),false);
    assert.equal(grilleUI.requests.filter(([a])=>a==="pattern_preview").length,validTiltPreviews,"above 45 never requests native geometry");
    await grilleUI.input("louver_angle_deg",0);
    assert.equal(grilleUI.$("pattern-settings").checkValidity(),true);
    assert(grilleUI.$("pattern-illustration").innerHTML.includes('data-grille-tilt="0"'));
    await grilleUI.input("louver_angle_deg",45);
    const heightPreviews=grilleUI.requests.filter(([a])=>a==="pattern_preview").length;
    await grilleUI.input("grille_height_mm",4);
    assert.equal(grilleUI.snapshot().settings.grille_height_mm,4);
    assert.equal(grilleUI.requests.filter(([a])=>a==="pattern_preview").length,heightPreviews+1);
    assert(grilleUI.$("pattern-illustration").innerHTML.includes('data-grille-height="4"'));
    await grilleUI.click("pattern-help-grille_height_mm");
    assert(grilleUI.$("pattern-help-image").innerHTML.includes('data-help-image="grille_height_mm"'));
    await grilleUI.click("pattern-help-close");
    await grilleUI.input("grille_profile","chamfer");
    assert(grilleUI.$("pattern-illustration").innerHTML.includes('data-grille-profile="chamfer"'));
    await grilleUI.input("grille_profile","flat");
    assert.equal(grilleUI.$("pattern-grille_height_mm").parentElement.hidden,true);
    assert.equal(grilleUI.$("pattern-louver_angle_deg").parentElement.hidden,false);
    await grilleUI.input("mount_mode","countersink");
    assert.equal(grilleUI.$("pattern-mount-options").hidden,false);
    assert(grilleUI.$("pattern-mount-summary").textContent.includes("Ø4.3 mm"));
    assert(grilleUI.$("pattern-mount-summary").textContent.includes("Ø9.86 mm"));
    assert(grilleUI.$("pattern-mount-summary").textContent.includes("2.78 mm"));
    assert(grilleUI.$("pattern-mount-summary").textContent.includes("Border used 12.76 mm"));
    assert.equal(Number(grilleUI.$("pattern-border_mm").value),7,"the requested minimum is retained independently of the automatic border");
    await grilleUI.input("mount_screw","M3");
    assert(grilleUI.$("pattern-mount-summary").textContent.includes("Border used 10.29 mm"));
    await grilleUI.input("mount_screw","M6");
    assert(grilleUI.$("pattern-mount-summary").textContent.includes("Border used 17.68 mm"));
    await grilleUI.input("border_mm",20);
    assert(grilleUI.$("pattern-mount-summary").textContent.includes("Border used 20 mm"));
    await grilleUI.input("mount_screw","M4");await grilleUI.input("border_mm",7);
    assert.equal((grilleUI.$("pattern-illustration").innerHTML.match(/data-mounting-hole=/g)||[]).length,4);
    await grilleUI.input("mount_head_mm",8);
    assert(grilleUI.$("pattern-mount-summary").textContent.includes("Ø8.8 mm"));
    await grilleUI.input("mount_inset_mm",0);
    assert.equal(grilleUI.$("pattern-settings").checkValidity(),true,"Auto inset and Auto head permit zero");
    await grilleUI.click("pattern-help-mount_head_mm");
    assert(grilleUI.$("pattern-help-image").innerHTML.includes('data-help-image="mount_head_mm"'));
    await grilleUI.click("pattern-help-close");
    await grilleUI.input("mount_mode","plain");
    assert(!grilleUI.$("pattern-mount-summary").textContent.includes("90° seat"));
    await grilleUI.input("mount_mode","off");
    assert.equal(grilleUI.$("pattern-mount-options").hidden,true);
    await grilleUI.click("cancel-pattern-button");await grilleUI.select("honeycomb");
    assert.equal(grilleUI.$("pattern-mounting").hidden,true);
    assert.equal(grilleUI.$("pattern-grille_profile").parentElement.hidden,true);
    assert.equal(grilleUI.$("pattern-rotation_deg").parentElement.parentElement.id,"pattern-placement-fields");
    assert.equal(grilleUI.$("grille-direction-presets").hidden,true);
    assert.equal(grilleUI.$("pattern-pattern").children.length,15);
    assert.equal(grilleUI.$("pattern-layout_mode").value,"auto");
    assert.equal(grilleUI.$("pattern-web_mm").value,"7");
    await grilleUI.input("mode","inlay");
    assert.equal(grilleUI.$("pattern-depth_mm").parentElement.children[0].textContent,"Colour depth");
    assert.equal(grilleUI.$("pattern-depth_mm").parentElement.hidden,false);
    await grilleUI.click("pattern-help-depth_mm");assert(grilleUI.$("pattern-help-title").textContent.includes("Colour depth"));await grilleUI.click("pattern-help-close");
    assert(grilleUI.$("pattern-illustration").innerHTML.includes('data-pattern-mode="inlay"'));
    assert.equal(grilleUI.$("export-pattern-button").disabled,true,"older hosts do not advertise flat-colour export");
    const guide=fixture();await guide.flush();await guide.select("honeycomb");
    const beforeHelp=guide.requests.length;
    const polygonFamilies=["triangle","rounded_triangle","pentagon","octagon","trihex","octagon_square","cairo","rhombille","rounded_hexagon","elongated_hexagon"];
    assert.equal(guide.$("pattern-pattern").children.length,15,"fifteen real pattern choices");
    for(const family of polygonFamilies) {
        assert(fs.existsSync(path.join(ui,"pattern-previews",family+".svg")),family+" has a local visual sample");
        await guide.input("pattern",family);
        assert(guide.$("pattern-illustration").innerHTML.includes(`pattern-previews/${family}.svg`));
        assert(guide.$("pattern-illustration").innerHTML.includes(`data-pattern-cell="${family}"`));
    }
    await guide.input("pattern","hexagon");
    for(const name of [...Object.keys(defaults),"cell_size_mm"]) {
        await guide.click("pattern-help-"+name);
        assert.equal(guide.$("pattern-parameter-help").open,true);
        assert(guide.$("pattern-help-title").textContent.length>6);
        assert(guide.$("pattern-help-description").textContent.length>40);
        assert(guide.$("pattern-help-image").innerHTML.includes(`data-help-image="${name}"`));
        assert.equal(guide.$("pattern-help-"+name).type,"button","help never submits the parameter form");
        await guide.click("pattern-help-close");
        assert.equal(guide.$("pattern-parameter-help").open,false);
        assert.equal(guide.$("pattern-help-"+name).focused,true,"closing restores focus to the help trigger");
    }
    assert.equal(guide.requests.length,beforeHelp,"illustrated help never sends CAD or preview requests");
    assert.equal(guide.$("pattern-cell_size_mm").value,"12.5");
    assert.equal(guide.$("pattern-web_mm").value,"7");
    assert.equal(guide.$("pattern-border_mm").value,"7");
    assert.equal(guide.$("pattern-layout_mode").value,"auto");
    assert.equal(guide.$("pattern-size_locked").value,"false");
    assert.equal(guide.$("pattern-edge_mode").value,"clip");
    for(const mode of ["fit","fixed","balanced","fill"]) {
        await guide.input("layout_mode",mode);
        assert.equal(guide.$("pattern-cell_size_mm").parentElement.hidden,false);
        assert.equal(guide.$("pattern-cell_size_mm").parentElement.children[0].textContent,"Cell size");
        assert.equal(guide.$("pattern-web_mm").parentElement.children[0].textContent,"Minimum gap");
        assert.equal(guide.$("pattern-border_mm").parentElement.children[0].textContent,"Border");
    }
    assert.equal(guide.$("pattern-pitch_mm").parentElement.hidden,true);
    guide.config.completePick=true;await guide.begin();
    await guide.input("layout_mode","balanced");
    for(const size of [5,10,20]) {
        const previous=guide.requests.filter(([action])=>action==="pattern_preview").length;
        await guide.input("cell_size_mm",size);
        assert.equal(guide.snapshot().settings.pitch_mm-guide.snapshot().settings.web_mm,size);
        assert.equal(guide.requests.filter(([action])=>action==="pattern_preview").length,previous+1,"each Balanced size edit requests a current preview");
    }
    await guide.input("layout_mode","fill");await guide.input("web_mm",1.5);await guide.input("cell_size_mm",10);
    assert.equal(guide.snapshot().settings.pitch_mm,11.5);
    await guide.input("web_mm",2);
    assert.equal(guide.snapshot().settings.pitch_mm,12,"changing minimum gap preserves the explicit 10 mm cell size");
    assert.equal(guide.$("pattern-cell_size_mm").value,"10");
    assert.deepEqual(Object.keys(guide.snapshot().settings).sort(),Object.keys(defaults).sort(),"derived size does not change the host snapshot schema");
    const beforeInvalidSize=guide.requests.length;await guide.input("cell_size_mm",0);
    assert.equal(guide.requests.length,beforeInvalidSize);assert.equal(guide.$("create-pattern-button").disabled,true);
    await guide.input("cell_size_mm",9);assert.equal(guide.snapshot().settings.pitch_mm,11);
    await guide.input("web_mm","");assert.equal(guide.$("pattern-cell_size_mm").value,"9");
    await guide.input("web_mm",1.5);assert.equal(guide.snapshot().settings.pitch_mm,10.5,"clearing and retyping gap must not resize the cell");
    guide.config.holdPreview=true;guide.$("preview-pattern-button").emit("click");await guide.flush();
    const duringPreview=guide.requests.length;await guide.click("pattern-help-border_mm");
    assert.equal(guide.$("pattern-parameter-help").open,true);assert.equal(guide.requests.length,duringPreview,"help remains local during native computation");
    await guide.click("pattern-help-close");guide.config.release();guide.config.holdPreview=false;await guide.flush();
    const auto=fixture({completePick:true});await auto.flush();await auto.select("honeycomb");
    await auto.input("layout_mode","auto");await auto.begin();
    assert.equal(auto.$("pattern-density").parentElement.hidden,false);
    auto.push({...auto.snapshot(),suggestedSizeMm:18.25,previewCurrent:true});
    assert.equal(auto.$("pattern-cell_size_mm").value,"18.25","show the host proposal without changing the saved seed");
    const autoBefore=auto.requests.filter(([a])=>a==="pattern_preview").length;
    await auto.input("cell_size_mm",9);
    assert.equal(auto.snapshot().settings.size_locked,true);
    assert.equal(auto.snapshot().settings.pitch_mm,16);
    assert.equal(auto.$("pattern-size_locked").value,"true");
    assert.equal(auto.requests.filter(([a])=>a==="pattern_preview").length,autoBefore+1);
    await auto.input("density","dense");
    assert.equal(auto.snapshot().settings.size_locked,true,"density does not undo a manual size lock");
    assert.equal(auto.snapshot().settings.pitch_mm,16);
    await auto.input("size_locked","false");
    assert.equal(auto.snapshot().settings.size_locked,false,"the wire snapshot retains a real boolean");
    auto.push({...auto.snapshot(),suggestedSizeMm:18.25,previewCurrent:true});
    await auto.input("size_locked","true");
    assert.equal(auto.snapshot().settings.pitch_mm,25.25,"locking the displayed proposal adopts its actual dimension");
    await auto.input("cell_size_mm","");
    assert.equal(auto.$("create-pattern-button").disabled,true);
    await auto.input("size_locked","false");
    assert.equal(auto.snapshot().settings.size_locked,false,"Automatic recovers from an unfinished custom-size edit");
    assert(Number.isFinite(auto.snapshot().settings.pitch_mm));
    await auto.input("layout_mode","fill");
    assert.equal(auto.$("pattern-density").parentElement.hidden,true);
    assert.equal(auto.$("pattern-density").disabled,true);
    await auto.click("cancel-pattern-button");
    const firstPick=fixture();await firstPick.flush();await firstPick.select("honeycomb");firstPick.config.completePick=true;
    await firstPick.click("begin-pattern-button");
    assert.deepEqual(firstPick.requests.filter(([action])=>action.startsWith("pattern_")).map(([action])=>action),["pattern_begin"],"Begin never previews before Done");
    assert.equal(firstPick.snapshot().pickingFaces,true);
    assert.equal(firstPick.$("create-pattern-button").disabled,true);
    assert.equal(firstPick.$("pattern-finish-faces").disabled,false);
    assert.equal(firstPick.$("grille-direction-45").disabled,true,"direction presets cannot change settings while picking faces");
    await firstPick.click("pattern-finish-faces");
    assert.equal(firstPick.snapshot().phase,"preview");assert.equal(firstPick.$("create-pattern-button").disabled,false);
    const f=fixture();await f.flush();await f.select("honeycomb");
    assert.equal(f.$("pattern-tool").hidden,false);assert.equal(f.$("planned-tool").hidden,true);assert.equal(f.$("hinge-action-dock").hidden,true);assert.equal(f.$("snap-action-dock").hidden,true);
    assert.equal(f.$("pattern-pattern").value,"hexagon");assert.equal(f.$("pattern-mode").value,"through");assert.equal(f.$("pattern-depth_mm").disabled,true);
    assert.equal(f.$("pattern-layout_mode").value,"auto");assert.equal(f.$("pattern-layout_mode").parentElement.children[0].textContent,"Layout");
    assert.equal(f.$("pattern-pitch_mm").parentElement.children[0].textContent,"Pitch");
    assert.deepEqual(f.$("pattern-layout_mode").children.map(option=>[option.value,option.textContent]),[["auto","Auto fit · visual balance"],["balanced","Balanced · fewer cells"],["fill","Fill face · fixed size"],["fit","Automatic size"],["fixed","Exact pitch"]]);
    assert.equal(f.$("begin-pattern-button").disabled,false);assert.equal(f.$("create-pattern-button").disabled,true);
    assert(!f.$("pattern-selections").children.some(element=>element.id==="pattern-add-face"));
    assert.deepEqual(f.$("pattern-settings").querySelectorAll("[name]").map(x=>x.name).sort(),Object.keys(defaults).sort());
    assert(f.$("pattern-illustration").innerHTML.includes('data-pattern-surface="cylinder"'));assert(f.$("pattern-illustration").innerHTML.includes('data-pattern-cell="hexagon"'));
    const hexArt=f.$("pattern-illustration").innerHTML;
    await f.input("pitch_mm",9);await f.select("perforation");assert.equal(f.$("pattern-pattern").value,"circle");assert.equal(f.$("pattern-pitch_mm").value,"9");
    await f.select("knurl");assert.equal(f.$("pattern-pattern").value,"diamond");assert.equal(f.$("pattern-mode").value,"emboss");assert.equal(f.$("pattern-depth_mm").disabled,false);
    assert.notEqual(f.$("pattern-illustration").innerHTML,hexArt,"texture has a raised wrapped mesh rather than a hexagonal opening label");
    for(const [name,value]of[["rotation_deg",-30],["offset_u_mm",-1.5],["offset_v_mm",0],["border_mm",0]])await f.input(name,value);
    assert.equal(f.$("pattern-settings").checkValidity(),true,"offsets/rotation are signed and border may be zero");
    f.config.holdPick=true;const timeouts=f.timeouts();f.$("begin-pattern-button").emit("click");await f.flush();assert.equal(f.timeouts(),timeouts);assert.equal(f.$("tool-select").disabled,true);
    f.config.release();f.config.holdPick=false;await f.flush();await f.click("pattern-clear-faces");await f.click("cancel-pattern-button");f.config.completePick=true;await f.begin();await f.click("pattern-select-surface");await f.click("pattern-finish-faces");assert.equal(f.snapshot().phase,"preview");assert.equal(f.$("create-pattern-button").disabled,false);
    assert.equal(f.requests.filter(([a])=>a==="pattern_focus").at(-1)[1].target,"faces");
    assert.equal(f.$("pattern-add-face").disabled,false);assert(f.$("pattern-selection-help").textContent.includes("Done"));assert.equal(f.$("pattern-add-face").textContent,"Add faces");
    const beforeAdd=f.requests.length;
    await f.click("pattern-add-face");
    assert.equal(f.requests.at(-1)[1].target,"add_face");
    assert.deepEqual(f.requests.slice(beforeAdd).map(([action])=>action),["pattern_focus"],"opening face selection returns immediately and does not compute preview");
    assert.equal(f.$("pattern-finish-faces").disabled,false,"Done remains usable while selecting");
    assert.equal(f.$("cancel-pattern-button").disabled,false,"Cancel remains usable while selecting");
    assert.equal(f.$("pattern-cell_size_mm").disabled,true);
    assert.equal(f.$("preview-pattern-button").disabled,true);
    assert.equal(f.$("create-pattern-button").disabled,true);
    assert(f.$("pattern-selection-help").textContent.includes("blue"));
    const beforeClear=f.requests.length;
    await f.click("pattern-clear-faces");
    assert.deepEqual(f.requests.slice(beforeClear).map(([action])=>action),["pattern_clear_faces"],"Clear never computes preview");
    assert.equal(f.$("pattern-finish-faces").disabled,true);
    assert.equal(f.$("cancel-pattern-button").disabled,false,"empty native selection never traps Cancel");
    f.setHost({...f.snapshot(),phase:"picking_faces",pickingFaces:true,canFinishFaces:true,selections:{surface:{selected:true,label:"6 faces on Box"}}});f.push(f.snapshot());
    assert.equal(f.$("pattern-finish-faces").disabled,false);
    await f.click("pattern-finish-faces");
    assert.deepEqual(f.requests.slice(beforeAdd).map(([action])=>action),["pattern_focus","pattern_clear_faces","pattern_finish_faces","pattern_preview"],"Done computes one preview for all selected sides");
    assert.equal(f.$("create-pattern-button").disabled,false);
    const activeSettings=f.snapshot().settings;f.window.PartelierPatterns.select("honeycomb");assert.equal(f.$("pattern-pattern").value,activeSettings.pattern,"an active session ignores alias presets");
    f.window.PartelierSnap.setHingeActive(false);assert.equal(f.$("tool-select").disabled,true,"Snap rendering cannot unlock an active pattern session");
    f.window.fusionJavaScriptHandler.handle("hinge_state",JSON.stringify(idle()));assert.equal(f.$("tool-select").disabled,true);
    const previews=()=>f.requests.filter(([a])=>a==="pattern_preview").length,before=previews();
    await f.input("pitch_mm",10,false);await f.input("pitch_mm",11,false);assert.equal(previews(),before);assert.equal(f.$("create-pattern-button").disabled,true);await f.settle();assert.equal(previews(),before+1);
    assert.deepEqual(Object.keys(f.snapshot().settings).sort(),Object.keys(defaults).sort());assert.equal(f.snapshot().settings.offset_u_mm,-1.5);assert.equal(typeof f.snapshot().settings.pattern,"string");
    const beforeSpacing=previews();await f.input("layout_mode","fixed");assert.equal(previews(),beforeSpacing+1);assert.equal(f.snapshot().settings.layout_mode,"fixed");assert.equal(f.$("pattern-pitch_mm").parentElement.children[0].textContent,"Pitch");
    assert.equal(f.snapshot().selections.surface.selected,true,"spacing changes keep the selected faces");assert.equal(f.$("create-pattern-button").disabled,false);
    await f.input("layout_mode","fit");assert.equal(f.snapshot().settings.layout_mode,"fit");assert.equal(f.$("pattern-pitch_mm").parentElement.children[0].textContent,"Pitch");
    const fitted=f.snapshot(),status=f.$("pattern-operation-status"),fittedMessage="42 cells · fitted pitch 7.4–7.8 mm";
    f.push({...fitted,message:fittedMessage});assert.equal(status.hidden,false);assert.equal(status.textContent,fittedMessage);assert.equal(f.$("pattern-live-preview-status").textContent,"Live preview · up to date");
    f.push({...fitted,revision:fitted.revision-1,message:"12 cells · fitted pitch 99 mm"});assert.equal(status.textContent,fittedMessage,"stale preview metadata cannot replace the current fitted pitch");
    const previousHtml=status.innerHTML,plainMessage="42 cells · fitted pitch <b>7.4 mm</b>";
    f.push({...fitted,message:plainMessage});assert.equal(status.textContent,plainMessage);assert.equal(status.innerHTML,previousHtml,"preview metadata is written as text, never HTML");
    f.push({...fitted,message:"Surfaces selected."});assert.equal(status.hidden,true,"ordinary informative messages stay collapsed");
    f.push({...fitted,message:fittedMessage});assert.equal(status.hidden,false);
    await f.input("mode","engrave");assert.equal(f.$("pattern-depth_mm").parentElement.children[0].textContent,"Depth / height");
    const invalidBefore=f.requests.length;await f.input("depth_mm",0);assert.equal(f.$("pattern-settings").checkValidity(),false);assert.equal(f.requests.length,invalidBefore);
    await f.input("mode","through");assert.equal(f.snapshot().settings.depth_mm,1);assert.equal(f.$("pattern-depth_mm").disabled,true);assert.equal(f.$("pattern-settings").checkValidity(),true);
    f.config.failPreview=true;await f.input("web_mm",1.4);assert.equal(f.$("create-pattern-button").disabled,true);assert(f.$("pattern-operation-status").textContent.includes("Reduce depth"));await f.click("preview-pattern-button");assert.equal(f.$("create-pattern-button").disabled,false);
    f.config.queuedPreview=true;f.config.holdPreview=true;await f.input("pattern","slot",false);await f.settle();const computing=f.snapshot();assert.equal(computing.phase,"computing");f.push({...computing,phase:"preview"});f.config.release();f.config.holdPreview=false;f.config.queuedPreview=false;await f.flush();assert.equal(f.$("create-pattern-button").disabled,false,"late computing acknowledgments cannot replace pushed previews");
    f.push({...computing,revision:computing.revision-1,settings:{...defaults,pitch_mm:99},phase:"preview"});assert.equal(f.$("pattern-pitch_mm").value,String(computing.settings.pitch_mm));
    await f.input("selection_scope","body",false);assert.equal(f.$("create-pattern-button").disabled,true);await f.settle();assert.deepEqual(f.snapshot().selections,{});assert.equal(f.requests.at(-1)[0],"pattern_update");
    assert(!f.$("pattern-selections").children.some(element=>element.id==="pattern-add-face"),"body scope has no Add face action");
    await f.click("pattern-select-surface");assert.equal(f.requests.filter(([a])=>a==="pattern_focus").at(-1)[1].target,"body");assert.equal(f.$("create-pattern-button").disabled,false);
    f.config.holdCommit=true;f.$("create-pattern-button").emit("click");await f.flush();const committing=f.snapshot();f.push(committing);assert.equal(f.$("pattern-pattern").disabled,true);f.push({...committing,sessionId:null,phase:"created",message:"Pattern created."});f.config.release();f.config.holdCommit=false;await f.flush();assert.equal(f.$("tool-select").disabled,false);assert.equal(f.$("cancel-pattern-button").disabled,true);
    f.config.completePick=true;await f.begin();const retiring=f.snapshot();await f.click("cancel-pattern-button");f.push({...retiring,phase:"preview"});assert.equal(f.$("tool-select").disabled,false);f.config.delayedPush={...retiring,phase:"preview"};await f.begin();assert.notEqual(f.snapshot().sessionId,retiring.sessionId);await f.click("cancel-pattern-button");
    f.config.saved={...defaults,pattern:"square",mode:"engrave",pitch_mm:12,web_mm:5,border_mm:2,depth_mm:.7,selection_scope:"body",layout_mode:"fixed"};await f.click("edit-pattern-button");assert.equal(f.$("pattern-pattern").value,"square");assert.equal(f.$("pattern-web_mm").value,"5");assert.equal(f.$("pattern-border_mm").value,"2");assert.equal(f.$("pattern-layout_mode").value,"fixed");assert.equal(f.$("pattern-depth_mm").value,"0.7");assert.equal(f.$("pattern-selection_scope").disabled,true);
    assert.equal(f.$("pattern-layout_mode").value,"fixed","migrated recipes retain exact spacing when Edit opens");assert.equal(f.$("pattern-pitch_mm").parentElement.children[0].textContent,"Pitch");
    assert(!f.$("pattern-selections").children.some(element=>element.id==="pattern-add-face"),"Edit has no Add face action");
    const beforeScope=f.requests.length;await f.input("selection_scope","faces");assert.equal(f.requests.length,beforeScope);assert.equal(f.$("pattern-selection_scope").value,"body");await f.input("depth_mm",.8);await f.click("create-pattern-button");assert.equal(f.snapshot().settings.depth_mm,.8);assert.equal(f.snapshot().settings.layout_mode,"fixed");assert.equal(f.$("pattern-selection_scope").disabled,false);
    await f.select("snap");await f.click("begin-snap-button");assert.equal(f.$("tool-select").disabled,true);await f.select("honeycomb");assert.equal(f.$("begin-pattern-button").disabled,true,"Snap and Pattern cannot claim geometry together");await f.select("snap");await f.click("cancel-snap-button");assert.equal(f.$("tool-select").disabled,false);
    await f.select("hinge");await f.click("begin-hinge-button");assert.equal(f.$("tool-select").disabled,true);await f.click("cancel-hinge-button");assert.equal(f.$("tool-select").disabled,false);
    const recovered=fixture({pattern:{...retiring,sessionId:"d28c515a-66dc-4c66-a57b-999999999999",phase:"preview",settings:{...defaults,pattern:"circle",mode:"engrave",depth_mm:.6}}});await recovered.flush();assert.equal(recovered.$("tool-select").value,"perforation");assert.equal(recovered.$("pattern-mode").value,"engrave");assert.equal(recovered.$("create-pattern-button").disabled,false);
    const unavailable=fixture({capabilities:["hinge-palette","snap-palette"]});await unavailable.flush();await unavailable.select("honeycomb");assert.equal(unavailable.$("begin-pattern-button").disabled,true);assert.equal(unavailable.$("edit-pattern-button").disabled,true);assert.equal(unavailable.$("pattern-availability").hidden,false);
    for(const phase of ["preview","error","cancelled"]){
        const lost=fixture();await lost.flush();await lost.select("honeycomb");await lost.begin();
        lost.config.holdPreview=true;lost.config.queuedPreview=true;await lost.click("pattern-select-surface");lost.$("pattern-finish-faces").emit("click");await lost.flush();
        const computing=lost.snapshot();assert.equal(lost.window.PartelierPatterns.isBusy(),true);assert.equal(lost.$("cancel-pattern-button").disabled,true);
        lost.push({...computing,sessionId:"d28c515a-66dc-4c66-a57b-888888888888",phase});await lost.flush();assert.equal(lost.window.PartelierPatterns.isBusy(),true,"another session cannot settle the pending preview");
        const completed={...computing,phase,previewCurrent:phase==="preview",message:phase==="error"?"Native preview failed.":"24 cells"};
        if(phase==="preview"){completed.revision++;completed.settings={...completed.settings,pitch_mm:9};}
        lost.push(completed);await lost.flush();assert.equal(lost.window.PartelierPatterns.isBusy(),false,`${phase} settles a missing preview ACK without releasing it`);
        assert.equal(lost.pendingTimers(2000),0);
        if(phase==="preview"){
            assert.equal(lost.$("create-pattern-button").disabled,false);assert.equal(lost.$("cancel-pattern-button").disabled,false);
            lost.push({...completed,phase:"computing"});assert.equal(lost.$("create-pattern-button").disabled,false,"a late same-revision computing push cannot regress a completed preview");
            const originalAck=lost.config.release;lost.config.holdPreview=false;lost.config.queuedPreview=false;
            await lost.input("pitch_mm",10);assert.equal(lost.requests.filter(([a])=>a==="pattern_preview").length,2,"new input is no longer blocked behind the lost ACK");
            originalAck();await lost.flush();assert.equal(lost.$("pattern-pitch_mm").value,"10");assert.equal(lost.$("create-pattern-button").disabled,false,"late original ACK cannot replace the newer preview");
            await lost.click("cancel-pattern-button");
        }else if(phase==="error"){
            assert.equal(lost.$("preview-pattern-button").disabled,false);assert.equal(lost.$("cancel-pattern-button").disabled,false);
            await lost.click("cancel-pattern-button");lost.config.release();await lost.flush();
        }else{assert.equal(lost.$("tool-select").disabled,false);lost.config.release();await lost.flush();assert.equal(lost.$("tool-select").disabled,false);}
    }
    for(const missingAck of [false,true]){
        const recovered=fixture();await recovered.flush();await recovered.select("honeycomb");await recovered.begin();
        recovered.config.queuedPreview=true;recovered.config.holdPreview=missingAck;
        await recovered.click("pattern-select-surface");if(missingAck){recovered.$("pattern-finish-faces").emit("click");await recovered.flush();}else await recovered.click("pattern-finish-faces");
        const computing=recovered.snapshot();recovered.setHost({...computing,phase:"preview",previewCurrent:true,message:"36 cells · fitted pitch 8.2 mm"});
        await recovered.advance(2000);
        assert.equal(recovered.requests.filter(([a])=>a==="pattern_status").length,1);assert.equal(recovered.requests.filter(([a])=>a==="pattern_preview").length,1,"status recovery never recomputes geometry");
        assert.equal(recovered.window.PartelierPatterns.isBusy(),false);assert.equal(recovered.$("create-pattern-button").disabled,false);assert.equal(recovered.$("pattern-operation-status").textContent,"36 cells · fitted pitch 8.2 mm");
        assert.equal(recovered.pendingTimers(2000),0);assert.equal(recovered.pendingTimers(5000),0);await recovered.advance(2000);assert.equal(recovered.requests.filter(([a])=>a==="pattern_status").length,1);
        await recovered.click("cancel-pattern-button");if(missingAck){recovered.config.release();await recovered.flush();}assert.equal(recovered.$("tool-select").disabled,false);
        assert.equal(recovered.requests.some(([a])=>a==="pattern_commit"),false);
    }
    const offline=fixture();await offline.flush();await offline.select("honeycomb");await offline.begin();offline.config.queuedPreview=true;offline.config.holdStatus=true;await offline.click("pattern-select-surface");await offline.click("pattern-finish-faces");
    await offline.advance(2000);assert.equal(offline.pendingTimers(5000),1);await offline.advance(2000);assert.equal(offline.requests.filter(([a])=>a==="pattern_status").length,1,"only one read-only request is in flight");
    await offline.advance(5000);assert(offline.$("pattern-live-preview-status").textContent.includes("connection needs attention"));assert(offline.$("pattern-operation-status").textContent.includes("Computation may still be running"));assert.equal(offline.$("pattern-operation-status").hidden,false);
    assert.equal(offline.snapshot().phase,"computing");assert.equal(offline.requests.filter(([a])=>a==="pattern_preview").length,1);assert.equal(offline.$("cancel-pattern-button").disabled,false);
    offline.config.holdStatus=false;offline.setHost({...offline.snapshot(),phase:"preview",previewCurrent:true,message:"24 cells"});await offline.advance(2000);
    assert.equal(offline.requests.filter(([a])=>a==="pattern_status").length,2);assert.equal(offline.$("create-pattern-button").disabled,false);assert.equal(offline.$("pattern-live-preview-status").textContent,"Live preview · up to date");assert.equal(offline.$("pattern-operation-status").textContent,"24 cells");
    offline.config.statusReleases[0]();await offline.flush();assert.equal(offline.$("create-pattern-button").disabled,false,"a timed-out status reply has no effect when it eventually arrives");
    offline.config.holdStatus=true;await offline.input("pitch_mm",9);await offline.advance(2000);await offline.advance(5000);assert(offline.$("pattern-live-preview-status").textContent.includes("connection needs attention"));
    offline.push({...offline.snapshot(),phase:"preview",previewCurrent:true,message:"30 cells"});await offline.flush();assert.equal(offline.$("pattern-live-preview-status").textContent,"Live preview · up to date");assert.equal(offline.$("pattern-operation-status").textContent,"30 cells","an authoritative completion push clears connection attention too");assert.equal(offline.pendingTimers(2000),0);await offline.click("cancel-pattern-button");
    const retiredPoll=fixture();await retiredPoll.flush();await retiredPoll.select("honeycomb");await retiredPoll.begin();retiredPoll.config.queuedPreview=true;retiredPoll.config.holdStatus=true;await retiredPoll.click("pattern-select-surface");await retiredPoll.click("pattern-finish-faces");
    await retiredPoll.advance(2000);await retiredPoll.click("cancel-pattern-button");assert.equal(retiredPoll.pendingTimers(2000),0);await retiredPoll.advance(2000);assert.equal(retiredPoll.requests.filter(([a])=>a==="pattern_status").length,1);
    retiredPoll.config.queuedPreview=false;retiredPoll.config.completePick=true;await retiredPoll.begin();const newSession=retiredPoll.snapshot();retiredPoll.config.statusReleases[0]();await retiredPoll.flush();
    assert.equal(retiredPoll.$("create-pattern-button").disabled,false);assert.equal(retiredPoll.snapshot().sessionId,newSession.sessionId);assert.equal(retiredPoll.pendingTimers(2000),0);assert.equal(retiredPoll.pendingTimers(5000),0);await retiredPoll.click("cancel-pattern-button");
    const drainTrace=async fixture=>{for(let i=0;i<20&&fixture.pendingTimers(400);i++)await fixture.advance(400);};
    const entries=fixture=>fixture.requests.filter(([action])=>action==="diagnostic_log").flatMap(([,request])=>request.entries);
    const previousContext=Object.fromEntries(Array.from({length:32},(_,index)=>["field"+index,index])),previousAt=123456;
    const replayed=fixture({storageSeed:{"Partelier.patternTrace.v1":JSON.stringify([{event:"click",at:previousAt,context:previousContext}])}});await replayed.flush();await drainTrace(replayed);
    assert(entries(replayed).some(entry=>entry.event==="click"&&entry.at===previousAt&&entry.context.replayed===true&&Object.keys(entry.context).length<=32),"validated saved events are replayed with their original time");
    assert(entries(replayed).some(entry=>entry.event==="boot"&&entry.at!==previousAt&&entry.context.build==="0.17.0"&&!entry.context.replayed),"the current page boot remains distinct from replayed history");
    const logged=fixture();await logged.flush();await logged.select("honeycomb");logged.emitDocument("pointerdown",{target:logged.$("create-pattern-button")});await drainTrace(logged);
    assert(entries(logged).some(entry=>entry.event==="boot"&&entry.context.build==="0.17.0"));assert(entries(logged).some(entry=>entry.event==="pointerdown"&&entry.context.control==="create-pattern-button"&&entry.context.disabled===true));
    await logged.begin();await logged.click("pattern-select-surface");await logged.click("pattern-finish-faces");await drainTrace(logged);logged.config.failPreview=true;await logged.input("pitch_mm",9);await logged.click("preview-pattern-button");await logged.click("cancel-pattern-button");await drainTrace(logged);
    logged.config.completePick=true;await logged.begin();const loggedCurrent=logged.snapshot();logged.push({...loggedCurrent,revision:loggedCurrent.revision-1});await logged.click("create-pattern-button");logged.emitWindow("error",{error:{name:"TypeError"},lineno:123,colno:4});logged.emitWindow("unhandledrejection",{reason:{name:"RangeError"}});await drainTrace(logged);
    const traceEntries=entries(logged),events=new Set(traceEntries.map(entry=>entry.event));
    for(const event of ["click","input","action_queued","action_start","action_end","action_error","send_start","send_ack","send_rejected","push_received","state_applied","state_rejected","locks","browser_error","unhandled_rejection"])assert(events.has(event),`missing ${event} diagnostic`);
    for(const control of ["begin","surface","refresh","cancel","commit"])assert(traceEntries.some(entry=>entry.event==="click"&&entry.context.control===control));
    assert(traceEntries.some(entry=>entry.event==="input"&&entry.context.name==="pitch_mm"&&entry.context.value===9));
    for(const [,request]of logged.requests.filter(([action])=>action==="diagnostic_log")){
        assert(request.entries.length>=1&&request.entries.length<=10);assert(Buffer.byteLength(JSON.stringify(request),"utf8")<16384);
        for(const entry of request.entries){assert(/^[A-Za-z0-9_.:-]{1,80}$/.test(entry.event));assert(Number.isFinite(entry.at)&&entry.at>=0);assert(Object.keys(entry.context).length<=32);assert(Object.values(entry.context).every(value=>value===null||typeof value==="boolean"||typeof value==="string"&&value.length<=512||typeof value==="number"&&Number.isFinite(value)));}
    }
    assert(!JSON.stringify(traceEntries).includes("3 supported faces"));assert(!JSON.stringify(traceEntries).includes("Hexagonal body"));
    const bounded=fixture();await bounded.flush();await bounded.select("honeycomb");bounded.config.failDiagnostic=true;
    for(let i=0;i<120;i++)await bounded.input("pitch_mm",8+i,false);
    assert.equal(JSON.parse(bounded.storage.get("Partelier.patternTrace.v1")).length,80);await drainTrace(bounded);const diagnosticCount=bounded.requests.filter(([action])=>action==="diagnostic_log").length;assert(diagnosticCount<=8);await bounded.advance(400);assert.equal(bounded.requests.filter(([action])=>action==="diagnostic_log").length,diagnosticCount,"failed diagnostics cannot recursively log themselves");
    bounded.config.holdDiagnostic=true;bounded.config.failDiagnostic=false;await bounded.begin();await bounded.click("pattern-select-surface");await bounded.click("pattern-finish-faces");await drainTrace(bounded);assert.equal(bounded.$("create-pattern-button").disabled,false,"an unanswered diagnostic ACK cannot block the UI queue");await bounded.click("cancel-pattern-button");
    const noStorage=fixture({storageFailure:true});await noStorage.flush();await noStorage.select("honeycomb");await noStorage.begin();await noStorage.click("pattern-select-surface");await noStorage.click("pattern-finish-faces");await drainTrace(noStorage);assert.equal(noStorage.$("create-pattern-button").disabled,false);await noStorage.click("cancel-pattern-button");
    const polledTrace=fixture();await polledTrace.flush();await polledTrace.select("honeycomb");await polledTrace.begin();polledTrace.config.queuedPreview=true;await polledTrace.click("pattern-select-surface");await polledTrace.click("pattern-finish-faces");await drainTrace(polledTrace);
    for(let i=0;i<5;i++){await polledTrace.advance(2000);await drainTrace(polledTrace);}
    assert.equal(polledTrace.requests.filter(([action])=>action==="pattern_status").length,5);assert(entries(polledTrace).filter(entry=>["send_start","send_ack"].includes(entry.event)&&entry.context.action==="pattern_status").length<=2,"unchanged recovery polls are deduplicated in the trace");
    polledTrace.config.holdStatus=true;await polledTrace.advance(2000);await polledTrace.advance(5000);await drainTrace(polledTrace);assert(entries(polledTrace).some(entry=>entry.event==="send_timeout"&&entry.context.action==="pattern_status"));await polledTrace.click("cancel-pattern-button");
    const version=JSON.parse(fs.readFileSync(path.join(__dirname,"../Partelier/Partelier.manifest"),"utf8")).version;assert(html.includes(`patterns.js?v=${version}`));
    console.log("Pattern UI contract passed: presets, typed full snapshots, surface scopes, modes, live preview, Edit/Rebuild, three-tool locks, stale sessions and native acknowledgment ordering.");
})().catch(error=>{console.error(error);process.exitCode=1;});

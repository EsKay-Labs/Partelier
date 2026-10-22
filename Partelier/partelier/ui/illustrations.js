"use strict";

// Original illustrative meshes. These are explanatory SVGs, never CAD plans.
window.PartelierIllustrations = (() => {
    const A = "#b7c9df", B = "#69a3f0", DARK = "#435d80";
    const project = ([x, y, z]) => [220 + (x - y) * 2.12, 150 + (x + y) * .88 - z * 2.05];
    const point = p => project(p).map(v => v.toFixed(2)).join(",");
    const shade = (hex, amount) => "#" + hex.slice(1).match(/../g).map(v => Math.max(0, Math.min(255, Math.round(parseInt(v, 16) * amount))).toString(16).padStart(2, "0")).join("");

    function render(id, { exploded = false, length = 40, outputMode = "attached", leafProfile = "rectangular", screwHoles = false, chamferEdges = false, filletEdges = false, knuckleProfile = "round", knuckleCount = 5, webProfile = "tangent" } = {}) {
        const faces = [], overlays = [];
        const face = (vertices, color, light = 1, smooth = false) => faces.push({ vertices, smooth, color: shade(color, light), depth: vertices.reduce((n, p) => n + p[0] + p[1] + p[2] * .2, 0) / vertices.length });
        const box = (x, y, z, w, d, h, color = A) => {
            face([[x,y,z+h],[x+w,y,z+h],[x+w,y+d,z+h],[x,y+d,z+h]], color, 1);
            face([[x+w,y,z],[x+w,y+d,z],[x+w,y+d,z+h],[x+w,y,z+h]], color, .77);
            face([[x,y+d,z],[x+w,y+d,z],[x+w,y+d,z+h],[x,y+d,z+h]], color, .61);
        };
        const prism = (polygon, y, depth, color) => {
            const front = polygon.map(([x,z]) => [x,y+depth,z]);
            face(front, color, .73);
            polygon.forEach(([x,z], i) => {
                const [nx,nz] = polygon[(i+1)%polygon.length];
                face([[x,y,z],[nx,y,nz],[nx,y+depth,nz],[x,y+depth,z]], color, .82 + i % 2 * .16);
            });
        };
        const tube = (x, y, z, radius, bore, depth, color, sides = 24) => {
            for (let i = 0; i < sides; i++) {
                const a = i * Math.PI * 2 / sides, b = (i+1) * Math.PI * 2 / sides;
                const ring = (angle, r, yy) => [x+Math.cos(angle)*r, yy, z+Math.sin(angle)*r];
                face([ring(a,radius,y),ring(b,radius,y),ring(b,radius,y+depth),ring(a,radius,y+depth)], color, .68 + .22 * (Math.sin(a)+1)/2);
                face([ring(a,radius,y+depth),ring(b,radius,y+depth),ring(b,bore,y+depth),ring(a,bore,y+depth)], color);
                if (bore) face([ring(a,bore,y),ring(b,bore,y),ring(b,bore,y+depth),ring(a,bore,y+depth)], color, .36);
            }
        };
        const roundedTube = (x, y, z, radius, bore, depth, color, size = .6) => {
            size = Math.min(size, radius / 3, depth / 4);
            const stations = [0, size*.25, size*.5, size*.75, size, depth-size, depth-size*.75, depth-size*.5, depth-size*.25, depth];
            const profile = t => {
                const distance = Math.min(t, depth-t);
                const arc = distance >= size ? size : Math.sqrt(Math.max(0, size*size-(size-distance)**2));
                return [radius-size+arc, bore ? bore+size-arc : 0];
            };
            const ring = (angle, r, t) => [x+Math.cos(angle)*r, y+t, z+Math.sin(angle)*r];
            for (let i=0;i<24;i++) {
                const a=i*Math.PI/12,b=(i+1)*Math.PI/12;
                for (let j=0;j<stations.length-1;j++) {
                    const t=stations[j],u=stations[j+1], [r,h]=profile(t),[rr,hh]=profile(u);
                    face([ring(a,r,t),ring(b,r,t),ring(b,rr,u),ring(a,rr,u)],color,.72+.18*Math.sin(a),true);
                    if (bore) face([ring(a,h,t),ring(a,hh,u),ring(b,hh,u),ring(b,h,t)],color,.4,true);
                }
                for (const t of [0,depth]) { const [r,h]=profile(t); face([ring(a,r,t),ring(b,r,t),ring(b,h,t),ring(a,h,t)],color,.9,true); }
            }
        };
        const verticalTube = (x, y, z, radius, bore, height, color, sides = 16) => {
            for (let i=0; i<sides; i++) {
                const a=i*Math.PI*2/sides, b=(i+1)*Math.PI*2/sides;
                const ring=(angle,r,zz)=>[x+Math.cos(angle)*r,y+Math.sin(angle)*r,zz];
                face([ring(a,radius,z),ring(b,radius,z),ring(b,radius,z+height),ring(a,radius,z+height)],color,.7+.15*Math.sin(a));
                face([ring(a,radius,z+height),ring(b,radius,z+height),ring(b,bore,z+height),ring(a,bore,z+height)],color);
                if(bore) face([ring(a,bore,z),ring(b,bore,z),ring(b,bore,z+height),ring(a,bore,z+height)],color,.38);
            }
        };
        const frame = (x,y,z,w,d,t,h,color) => { box(x,y,z,w,t,h,color); box(x,y+d-t,z,w,t,h,color); box(x,y+t,z,t,d-2*t,h,color); box(x+w-t,y+t,z,t,d-2*t,h,color); };
        const beam = (p,q,width,height,color) => {
            const dx=q[0]-p[0],dy=q[1]-p[1],len=Math.hypot(dx,dy),nx=-dy/len*width/2,ny=dx/len*width/2;
            const poly=[[p[0]+nx,p[1]+ny,0],[q[0]+nx,q[1]+ny,0],[q[0]-nx,q[1]-ny,0],[p[0]-nx,p[1]-ny,0]];
            face(poly.map(([x,y])=>[x,y,height]),color);
            for(let i=0;i<4;i++){ const a=poly[i],b=poly[(i+1)%4]; face([a,b,[b[0],b[1],height],[a[0],a[1],height]],color,.65); }
        };
        const flatPlate = (polygon, z, height, color) => {
            face(polygon.map(([x,y]) => [x,y,z+height]), color);
            polygon.forEach(([x,y], index) => { const [xx,yy] = polygon[(index+1)%polygon.length]; face([[x,y,z],[xx,yy,z],[xx,yy,z+height],[x,y,z+height]], color, .7); });
        };
        const roundPlate = (x, y, z, width, depth, height, radius, color) => {
            const polygon = [];
            for (const [cx, cy, start] of [[x+width-radius,y+radius,-Math.PI/2],[x+width-radius,y+depth-radius,0],[x+radius,y+depth-radius,Math.PI/2],[x+radius,y+radius,Math.PI]]) {
                for (let i=0;i<=6;i++) { const angle=start+i*Math.PI/12; polygon.push([cx+radius*Math.cos(angle),cy+radius*Math.sin(angle)]); }
            }
            flatPlate(polygon,z,height,color);
        };
        const shift = exploded ? 13 : 0;
        if (id === "hinge") {
            const span = Math.max(24, Math.min(64, Number(length) || 40));
            if (outputMode === "separate") {
                for (const side of [-1, 1]) {
                    const inner = 4 + shift, outer = 26 + shift, low = -span/2, high = span/2;
                    let polygon = [[inner,low],[outer,low],[outer,high],[inner,high]];
                    if (filletEdges) {
                        const radius = Math.min(3, span/6);
                        polygon = [];
                        for (const [cx,cy,start] of [[outer-radius,low+radius,-Math.PI/2],[outer-radius,high-radius,0],[inner+radius,high-radius,Math.PI/2],[inner+radius,low+radius,Math.PI]]) {
                            for (let i=0;i<=6;i++) { const angle=start+i*Math.PI/12; polygon.push([cx+radius*Math.cos(angle),cy+radius*Math.sin(angle)]); }
                        }
                    } else if (leafProfile === "rounded") {
                        const radius = Math.min(5, span/5);
                        polygon = [[inner,low],[outer-radius,low]];
                        for (let i=0;i<=6;i++) { const angle = -Math.PI/2+i*Math.PI/12; polygon.push([outer-radius+Math.cos(angle)*radius,low+radius+Math.sin(angle)*radius]); }
                        polygon.push([outer,high-radius]);
                        for (let i=0;i<=6;i++) { const angle = i*Math.PI/12; polygon.push([outer-radius+Math.cos(angle)*radius,high-radius+Math.sin(angle)*radius]); }
                        polygon.push([inner,high]);
                    }
                    flatPlate(polygon.map(([x,y]) => [side*x,y]),1,1.8,side<0?A:B);
                    if (chamferEdges) {
                        const centerX = (inner + outer) / 2;
                        const rim = polygon.map(([x,y]) => point([side*(x + Math.sign(centerX-x)*.6), y + Math.sign(-y)*.6, 2.82])).join(" ");
                        overlays.push(`<polygon data-edge-finish="true" points="${rim}" fill="none" stroke="#e8efeb" stroke-width="1.1"/>`);
                    }
                    if (screwHoles) for (const y of [low+6,high-6]) {
                        const ring = Array.from({length:24},(_,i) => { const angle=i*Math.PI/12; return point([side*(20+shift)+Math.cos(angle)*2.3,y+Math.sin(angle)*2.3,2.8]); }).join(" ");
                        overlays.push(`<polygon data-screw-hole="true" points="${ring}" fill="#59645f" stroke="#7a8d83" stroke-width=".7"/>`);
                    }
                }
            } else {
                box(-35-shift,-span/2-5,-6,29,span+10,9,A);
                box(6+shift,-span/2-5,-6,29,span+10,9,B);
            }
            const count = Math.max(3, Math.min(15, Number(knuckleCount) || 5)), gap = Math.min(.8, span/count/5);
            for(let i=0;i<count;i++) {
                const y=-span/2+i*span/count+gap/2, d=span/count-gap, right=i%2===1;
                if (webProfile === "tangent") {
                    const side = right ? 1 : -1, offset = side * shift;
                    const tangentX = knuckleProfile === "square" ? 5 / Math.sqrt(2) : 25 / 9;
                    const tangentZ = knuckleProfile === "square" ? 5 + tangentX : 5 + 5 * Math.sqrt(56) / 9;
                    const footprint = tangentX + (tangentZ - 1) * (9 - tangentX) / (tangentZ - 5);
                    prism([[offset+side*footprint,1],[offset+side*3,1],[offset+side*tangentX,tangentZ]],y,d,right?B:A);
                    overlays.push('<path data-tapered-support="true" d="M' + point([offset+side*footprint,y+d,1]) + ' L' + point([offset+side*tangentX,y+d,tangentZ]) + '" fill="none" stroke="' + DARK + '" stroke-width=".7"/>');
                }
                if (filletEdges) roundPlate(right?shift:-9-shift,y,1,9,d,4,Math.min(1.2,d/4),right?B:A);
                else box(right?shift:-9-shift,y,1,9,d,4,right?B:A);
                if (knuckleProfile === "square") {
                    const half = 5 / Math.sqrt(2);
                    box((right?shift:-shift)-half,y,5-half,2*half,d,2*half,right?B:A);
                    const hole = Array.from({length:24},(_,j) => { const angle=j*Math.PI/12; return point([(right?shift:-shift)+Math.cos(angle)*2,y+d,5+Math.sin(angle)*2]); }).join(" ");
                    overlays.push(`<polygon data-square-housing="true" points="${hole}" fill="#263e61" stroke="#d6e6ff" stroke-width=".6"/>`);
                } else if (filletEdges) roundedTube(right?shift:-shift,y,5,5,2,d,right?B:A);
                else tube(right?shift:-shift,y,5,5,2,d,right?B:A);
                if (chamferEdges) {
                    const center = right?shift:-shift, half = 5 / Math.sqrt(2) - .3;
                    const rim = (knuckleProfile === "square"
                        ? [[center-half,y+d,5-half],[center+half,y+d,5-half],[center+half,y+d,5+half],[center-half,y+d,5+half]].map(point)
                        : Array.from({length:24},(_,j) => { const angle=j*Math.PI/12; return point([center+Math.cos(angle)*4.65,y+d,5+Math.sin(angle)*4.65]); })).join(" ");
                    overlays.push(`<polygon data-edge-finish="true" points="${rim}" fill="none" stroke="#e8efeb" stroke-width=".8"/>`);
                }
            }
            if (filletEdges) roundedTube(0,-span/2-(exploded?22:3),5,1.4,0,span+6,"#e9bd83",.35);
            else tube(0,-span/2-(exploded?22:3),5,1.4,0,span+6,"#e9bd83",16);
        } else if (id === "snap") {
            // Exterior vertical clasp: base below the seam, lid above it.
            const lift = exploded ? 22 : 0;
            box(-3,-20,-18,3,40,18,A);
            box(-3,-20,lift,1.7,40,22,B); // back of the blind receiver
            box(-1.3,-20,lift,1.3,40,12.7,B);
            box(-1.3,-20,16.3+lift,1.3,40,5.7,B);
            box(-1.3,-20,12.7+lift,1.3,15.7,3.6,B);
            box(-1.3,4.3,12.7+lift,1.3,15.7,3.6,B);
            box(-.5,-4,-4,2.3,8,4,A);
            box(.3,-4,-4,1.5,8,20,A);
            prism([[-1,13],[1.8,13],[1.8,16],[.3,16]],-4,8,A);
        } else if (id === "slider") {
            box(-17,-35,0,34,70,4,A);
            prism([[-8,4],[8,4],[12,12],[-12,12]],-33,66,A);
            const y=exploded?18:-12, z=exploded?14:0;
            box(-19,y,4+z,7,25,16,B); box(12,y,4+z,7,25,16,B); box(-19,y,17+z,38,25,5,B);
            box(-17,28,4,34,5,7,"#e9bd83");
        } else if (id === "pockets") {
            frame(-29,-23,0,58,46,10,9,A);
            box(-19,-13,0,38,26,2,DARK);
            verticalTube(0,0,2+(exploded?17:0),11,4,6,B,6);
            verticalTube(17,11,9,4.5,2,2,"#e9bd83",24);
        } else if (id === "lid") {
            box(-28,-22,0,56,44,3,A); frame(-28,-22,3,56,44,4,15,A);
            frame(-25,-19,18,50,38,2,4,B);
            const z=exploded?42:27;
            box(-28,-22,z,56,44,3,B); frame(-25,-19,z-4,50,38,2,4,B);
        } else if (id === "alignment") {
            box(-30,-22,0,60,44,4,A);
            const top = exploded ? 34 : 9;
            frame(-30,-22,top,60,44,8,4,B);
            box(-12,-14,top,24,28,4,B);
            for(const x of [-18,18]) {
                verticalTube(x,0,4,3,0,10,A);
                verticalTube(x,0,top,6,3.4,4,B);
            }
        } else if (id === "knurl") {
            box(-29,-23,0,58,46,4,A);
            for(let x=-24;x<27;x+=8) for(let y=-18;y<21;y+=8) {
                const peak=[x,y,8+(exploded?3:0)];
                face([[x-3.5,y,4],[x,y-3.5,4],peak],B,.82);
                face([[x,y-3.5,4],[x+3.5,y,4],peak],B,1);
                face([[x+3.5,y,4],[x,y+3.5,4],peak],B,.65);
                face([[x,y+3.5,4],[x-3.5,y,4],peak],B,.72);
            }
        } else if (id === "perforation") {
            frame(-33,-25,0,66,50,4,4,A);
            for(let x=-24;x<=24;x+=12) for(let y=-18;y<=18;y+=12) verticalTube(x,y,0,6,3.8,4,B,24);
        } else if (id === "honeycomb") {
            frame(-34,-25,0,68,50,2,5,A);
            for(let col=0;col<6;col++) for(let row=0;row<4;row++) {
                const x=-26+col*10.5, y=-17+row*12+(col%2)*6;
                if(y<21) verticalTube(x,y,0,7,5.8,5+(exploded?3:0),B,6);
            }
        } else if (id === "truss") {
            beam([-34,-18],[34,-18],4,5,A); beam([-34,18],[34,18],4,5,A);
            for(let i=0;i<4;i++) { const x=-34+i*17; beam([x,-18],[x+8.5,18],2.7,5,B); beam([x+8.5,18],[x+17,-18],2.7,5,B); }
            beam([-34,-18],[-34,18],3,5,A); beam([34,-18],[34,18],3,5,A);
        } else if (id === "ribs") {
            box(-29,-24,0,58,48,4,A); box(-29,-24,4,4,48,30,A);
            for(const y of [-17,-2,13]) prism([[-25,4],[18,4],[-25,31]],y,3,B);
        } else if (id === "labels") {
            box(-31,-23,0,62,46,5,A);
            box(-22,-12,5,23,4,2,B); prism([[0,5],[10,5],[0,14]],-14,8,B);
            for(let x=-22;x<26;x+=6) box(x,12,5,1,x%12===2?8:5,1.5,B);
        }
        faces.sort((a,b)=>a.depth-b.depth);
        const geometry = faces.map(f=>`<polygon points="${f.vertices.map(point).join(" ")}" fill="${f.color}" stroke="${f.smooth ? f.color : "#1d3038"}" stroke-width="${f.smooth ? ".15" : ".35"}" stroke-linejoin="round"/>`).join("");
        const grid = [-48,-24,0,24,48].map(n=>`<path d="M${point([n,-48,-1])}L${point([n,48,-1])}M${point([-48,n,-1])}L${point([48,n,-1])}"/>`).join("");
        return `<svg viewBox="0 0 440 270" ${filletEdges ? 'data-fillet-finish="true"' : ''} role="img" aria-label="${id} concept illustration${exploded ? ", separated view" : ""}"><g fill="none" stroke="#a4c5ce" opacity=".055" stroke-width=".8">${grid}</g><ellipse cx="220" cy="203" rx="124" ry="23" fill="#0b171f" opacity=".2"/>${geometry}${overlays.join("")}<g fill="none" stroke="#9bbac1" stroke-width="1" opacity=".5"><path d="M36 233h20m-20 0v-17m0 17-9 6"/></g><g fill="#9bbac1" font-family="Consolas,monospace" font-size="7" opacity=".65"><text x="60" y="236">X</text><text x="33" y="212">Z</text></g></svg>`;
    }
    function renderHingeLayout(settings = {}) {
        const finite = (value, fallback) => Number.isFinite(Number(value)) ? Number(value) : fallback;
        const count = Math.max(1, Math.min(20, Math.round(finite(settings.hinge_count, 1))));
        const length = Math.max(.0001, finite(settings.length_mm, 40));
        const start = Math.max(0, finite(settings.start_margin_mm, 0));
        const end = Math.max(0, finite(settings.end_margin_mm, 0));
        const label = value => String(Number(value.toPrecision(5)));
        // A schematic: the selected edge length is known only in Fusion.
        const unit = 36, gap = 20;
        const margin = value => value === 0 ? 0 : Math.max(8, Math.min(60, value / length * unit));
        const leftMargin = margin(start), rightMargin = margin(end);
        const inner = count === 1 ? unit + 52 : count * unit + (count - 1) * gap;
        const span = leftMargin + inner + rightMargin;
        const x = value => 22 + value / span * 296;
        const starts = Array.from({ length: count }, (_, index) => leftMargin + (count === 1 ? 26 : index * (unit + gap)));
        const blocks = starts.map((offset, index) => {
            const left = x(offset), width = x(offset + unit) - left;
            return `<g data-hinge-index="${index + 1}"><path d="M${left - 2}65h${width + 4}" stroke="#ae8750" stroke-width="2"/><rect x="${left}" y="57" width="${width}" height="16" rx="1.5" fill="#a8c4d1" stroke="#5f7a87"/><path d="M${left + width / 2}57v16" stroke="#235fce" stroke-width="${Math.min(width / 3, 5)}"/>${count <= 6 ? `<text x="${left + width / 2}" y="94" text-anchor="middle">${index + 1}</text>` : ""}</g>`;
        }).join("");
        const first = x(starts[0]), last = x(starts[count - 1] + unit);
        const minimum = count === 1 ? "≥ " : "";
        return `<svg viewBox="0 0 340 142" role="img" aria-label="Arrangement sketch of ${count} separate ${count === 1 ? "hinge" : "hinges"}; spacing is calculated in Fusion"><g font-family="Segoe UI, sans-serif" font-size="9" fill="#405675"><text x="22" y="20">Start ${minimum}${label(start)} mm</text><text x="318" y="20" text-anchor="end">End ${minimum}${label(end)} mm</text><path d="M22 34H${first}M${last}34H318M22 29v10M318 29v10" fill="none" stroke="#8ea6c7"/><path d="M22 65H318" stroke="#8ea6c7" stroke-dasharray="3 3"/><rect x="22" y="44" width="296" height="6" rx="2" fill="#d7e3e7"/><rect x="22" y="80" width="296" height="6" rx="2" fill="#d7e7ff"/>${blocks}<text x="170" y="115" text-anchor="middle">${count} ${count === 1 ? "hinge · centered between margins" : "separate hinges · equal gaps"}</text><text x="170" y="132" text-anchor="middle" fill="#4f617c" font-size="8">Arrangement sketch · spacing calculated in Fusion</text></g></svg>`;
    }
    return Object.freeze({ render, renderHingeLayout });
})();

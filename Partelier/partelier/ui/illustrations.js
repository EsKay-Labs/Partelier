"use strict";

// Original illustrative meshes. These are explanatory SVGs, never CAD plans.
window.PartelierIllustrations = (() => {
    const A = "#b7c9df", B = "#69a3f0", DARK = "#435d80";
    const project = ([x, y, z]) => [220 + (x - y) * 2.12, 150 + (x + y) * .88 - z * 2.05];
    const point = p => project(p).map(v => v.toFixed(2)).join(",");
    const shade = (hex, amount) => "#" + hex.slice(1).match(/../g).map(v => Math.max(0, Math.min(255, Math.round(parseInt(v, 16) * amount))).toString(16).padStart(2, "0")).join("");

    function render(id, { exploded = false, length = 40, outputMode = "attached", leafProfile = "rectangular", screwHoles = false, chamferEdges = false, filletEdges = false, knuckleProfile = "round", knuckleCount = 5, webProfile = "tangent", snapStyle = "standard", printSupport = false, chamferSize = .3, snapFamily = "hook" } = {}) {
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
        const yzPrism = (polygon, x, depth, color) => {
            face(polygon.map(([y,z]) => [x+depth,y,z]), color, .78);
            polygon.forEach(([y,z], i) => {
                const [ny,nz] = polygon[(i+1)%polygon.length];
                face([[x,y,z],[x,ny,nz],[x+depth,ny,nz],[x+depth,y,z]], color, .86);
            });
        };
        const sphere = (x, y, z, radius, color) => {
            const ring = (longitude, latitude) => [x+radius*Math.cos(latitude)*Math.cos(longitude), y+radius*Math.cos(latitude)*Math.sin(longitude), z+radius*Math.sin(latitude)];
            for (let i=0; i<16; i++) for (let j=0; j<8; j++) {
                const a=i*Math.PI/8, b=(i+1)*Math.PI/8, c=-Math.PI/2+j*Math.PI/8, d=c+Math.PI/8;
                face([ring(a,c),ring(b,c),ring(b,d),ring(a,d)],color,.72+.2*Math.cos(a),true);
            }
        };
        const profileRing = (stations, color, cutaway = false) => {
            const start = cutaway ? 3*Math.PI/4 : 0, count = cutaway ? 16 : 32;
            const ring = (angle, radius, z) => [Math.cos(angle)*radius,Math.sin(angle)*radius,z];
            for (let i=0; i<count; i++) {
                const a=start+i*Math.PI/16,b=a+Math.PI/16;
                for (let j=0; j<stations.length-1; j++) {
                    const [z,r,h]=stations[j], [zz,rr,hh]=stations[j+1];
                    face([ring(a,r,z),ring(b,r,z),ring(b,rr,zz),ring(a,rr,zz)],color,.85,true);
                    face([ring(a,h,z),ring(a,hh,zz),ring(b,hh,zz),ring(b,h,z)],color,.58,true);
                }
                for (const [z,r,h] of [stations[0],stations[stations.length-1]]) face([ring(a,r,z),ring(b,r,z),ring(b,h,z),ring(a,h,z)],color,.96);
            }
            if (cutaway) for (const angle of [start,start+Math.PI]) {
                face([...stations.map(([z,r]) => ring(angle,r,z)),...stations.slice().reverse().map(([z,,h]) => ring(angle,h,z))],color,.9);
            }
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
            const lift = exploded ? 22 : 0, style = ["standard", "tapered", "twin"].includes(snapStyle) ? snapStyle : "standard";
            const family = ["hook", "ball_detent", "torsion", "annular"].includes(snapFamily) ? snapFamily : "hook";
            if (family === "annular") {
                profileRing([[0,13,10],[12,13,10],[13,13.5,10],[14,13,10],[18,13,10]],A);
                const roof = printSupport ? [[13.8,17,13.8],[14.3,17,13.3]] : [[14.3,17,13.8],[14.3,17,13.3]];
                profileRing([[10+lift,17,13.3],[11.7+lift,17,13.3],[13+lift,17,13.8],...roof.map(([z,r,h]) => [z+lift,r,h]),[28+lift,17,13.3]],B,true);
                overlays.push('<text x="26" y="26" fill="#435d80" font-family="Segoe UI,sans-serif" font-size="9">Cutaway · bead and matching groove</text>');
            } else {
            const outerAt = z => family === "hook" && style === "tapered" ? 1.8 - .525 * Math.max(0, z) / 16 : 1.8;
            box(-3,-20,-18,3,40,18,A);
            box(-3,-20,lift,1.7,40,22,B); // back of the blind receiver
            const pocketHalf = family === "torsion" ? 1.633 : 4.3;
            if (family === "ball_detent") {
                const radius = 2.1, centerZ = 14+lift;
                const arc = Array.from({length:17},(_,i) => { const y=-radius+2*radius*i/16; return [y,Math.sqrt(Math.max(0,radius*radius-y*y))]; });
                yzPrism([[-20,lift],[20,lift],[20,22+lift],[radius,22+lift],...arc.slice().reverse().map(([y,h]) => [y,centerZ-h]),[-radius,22+lift],[-20,22+lift]],-1.3,1.3,B);
                if (printSupport) {
                    face([...arc.map(([y,h]) => [0,y,centerZ+h+1.3]),[0,radius,22+lift],[0,-radius,22+lift]],B,.78);
                    for (let i=0; i<arc.length-1; i++) {
                        const [y,h]=arc[i], [yy,hh]=arc[i+1];
                        face([[-1.3,y,centerZ+h],[-1.3,yy,centerZ+hh],[0,yy,centerZ+hh+1.3],[0,y,centerZ+h+1.3]],B,.86);
                    }
                } else yzPrism([...arc.map(([y,h]) => [y,centerZ+h]),[radius,22+lift],[-radius,22+lift]],-1.3,1.3,B);
            } else {
            box(-1.3,-20,lift,1.3,40,12.7,B);
            if (printSupport) {
                // The receiver roof rises at 45 degrees toward its outer mouth.
                prism([[-1.3,16.3+lift],[0,17.6+lift],[0,22+lift],[-1.3,22+lift]],-20,40,B);
            } else box(-1.3,-20,16.3+lift,1.3,40,5.7,B);
            const pocketHeight = printSupport ? 4.9 : 3.6;
            box(-1.3,-20,12.7+lift,1.3,20-pocketHalf,pocketHeight,B);
            box(-1.3,pocketHalf,12.7+lift,1.3,20-pocketHalf,pocketHeight,B);
            if (family === "hook" && style === "twin") box(-1.3,-.45,12.7+lift,1.3,.9,pocketHeight,B);
            }
            box(-.5,-4,-4,2.3,8,4,A);
            if (printSupport) prism([[0,-5.8],[1.8,-4],[0,-4]],-4,8,A);
            if (family === "torsion") {
                box(-.5,-4,-4,2.4,1.6,5.9,A); box(-.5,2.4,-4,2.4,1.6,5.9,A);
                tube(1.1,-3.2,1.1,.8,0,6.4,A,20);
            }
            const arms = family === "torsion" ? [[-1.333,2.666]] : family === "hook" && style === "twin" ? [[-4,3.25],[.75,3.25]] : [[-4,8]];
            for (const [y, width] of arms) {
                const start = family === "torsion" ? 1.1 : 0;
                prism([[.3,start],[outerAt(start),start],[outerAt(16),16],[.3,16]],y,width,A);
                if (family !== "ball_detent") prism([[-1,13],[outerAt(13),13],[outerAt(16),16],[.3,16]],y,width,A);
            }
            if (family === "ball_detent") sphere(1,0,14,2,A);
            if (chamferEdges) {
                const size = Number.isFinite(chamferSize) && chamferSize > 0 ? Number(chamferSize.toPrecision(3)) : .3;
                overlays.push(`<text x="26" y="26" fill="#435d80" font-family="Segoe UI,sans-serif" font-size="9">Exposed-edge chamfer · ${size} mm</text>`);
            }
            }
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
        const snapAttributes = id === "snap" ? `data-snap-family="${["hook", "ball_detent", "torsion", "annular"].includes(snapFamily) ? snapFamily : "hook"}" data-snap-style="${["standard", "tapered", "twin"].includes(snapStyle) ? snapStyle : "standard"}" data-print-support="${!!printSupport}"` : "";
        return `<svg viewBox="0 0 440 270" ${filletEdges ? 'data-fillet-finish="true"' : ''} ${snapAttributes} role="img" aria-label="${id} concept illustration${exploded ? ", separated view" : ""}"><g fill="none" stroke="#a4c5ce" opacity=".055" stroke-width=".8">${grid}</g><ellipse cx="220" cy="203" rx="124" ry="23" fill="#0b171f" opacity=".2"/>${geometry}${overlays.join("")}<g fill="none" stroke="#9bbac1" stroke-width="1" opacity=".5"><path d="M36 233h20m-20 0v-17m0 17-9 6"/></g><g fill="#9bbac1" font-family="Consolas,monospace" font-size="7" opacity=".65"><text x="60" y="236">X</text><text x="33" y="212">Z</text></g></svg>`;
    }
    function renderPattern(settings = {}) {
        const mosaics = ["triangle","rounded_triangle","pentagon","octagon","trihex","octagon_square","cairo","rhombille","rounded_hexagon","elongated_hexagon"];
        if (String(settings.pattern).startsWith("grille_")) {
            const cross=settings.pattern==="grille_cross",louver=settings.pattern==="grille_louver";
            const bars=Array.from({length:7},(_,i)=>`<rect x="${48+i*48}" y="36" width="16" height="184" fill="#7697be" stroke="#365f88"/>`).join("");
            const horizontal=cross?Array.from({length:4},(_,i)=>`<rect x="34" y="${65+i*44}" width="372" height="14" fill="#7697be" stroke="#365f88"/>`).join(""):"";
            const inclined=louver?Array.from({length:7},(_,i)=>`<path d="M${64+i*48},36l16,12v172l-16,-12z" fill="#496e9a"/>`).join(""):"";
            return `<svg viewBox="0 0 440 270" role="img" aria-label="Planar grille concept" data-pattern-surface="panel" data-pattern-cell="${settings.pattern}"><rect x="20" y="22" width="400" height="212" rx="8" fill="#365f88"/><rect x="34" y="36" width="372" height="184" fill="#edf4ff"/>${bars}${inclined}${horizontal}<text x="220" y="258" text-anchor="middle" fill="#365f88" font-size="12">${cross?"Crossed ribs":louver?"Inclined channels · planar plate":"Parallel bars · rotate for diagonal"}</text></svg>`;
        }
        if(settings.mode==="inlay") {
            if(mosaics.includes(settings.pattern)) return `<svg viewBox="0 0 440 270" role="img" aria-label="${settings.pattern} flat colour sample" data-pattern-surface="panel" data-pattern-mode="inlay"><image href="pattern-previews/${settings.pattern}.svg?v=0.13.2" x="24" y="10" width="392" height="230"/><text x="220" y="257" text-anchor="middle" fill="#365f88" font-size="12">Flat colour · flush surface · two material parts</text><g data-pattern-cell="${settings.pattern}"/></svg>`;
            const cells=Array.from({length:5},(_,row)=>Array.from({length:8},(_,col)=>{
                const x=52+col*44+(row%2)*22,y=45+row*39;
                if(settings.pattern==="circle") return `<circle cx="${x}" cy="${y}" r="15" fill="#267de1"/>`;
                if(settings.pattern==="square") return `<rect x="${x-13}" y="${y-13}" width="26" height="26" fill="#267de1"/>`;
                if(settings.pattern==="diamond") return `<path d="M${x},${y-17}l17,17l-17,17l-17,-17z" fill="#267de1"/>`;
                if(settings.pattern==="slot") return `<rect x="${x-17}" y="${y-8}" width="34" height="16" rx="8" fill="#267de1"/>`;
                return `<polygon points="${Array.from({length:6},(_,i)=>{const a=i*Math.PI/3;return `${x+17*Math.cos(a)},${y+17*Math.sin(a)}`;}).join(" ")}" fill="#267de1"/>`;
            }).join("")).join("");
            return `<svg viewBox="0 0 440 270" role="img" aria-label="Flat colour material regions concept" data-pattern-surface="panel" data-pattern-mode="inlay" data-pattern-cell="${settings.pattern}"><rect x="20" y="20" width="400" height="212" rx="8" fill="#687a91"/>${cells}<text x="220" y="258" text-anchor="middle" fill="#365f88" font-size="12">Flat colour · flush surface · two material parts</text></svg>`;
        }
        if (mosaics.includes(settings.pattern)) {
            const mode = ["through","engrave","emboss"].includes(settings.mode) ? settings.mode : "through";
            return `<svg viewBox="0 0 440 270" role="img" aria-label="${settings.pattern} polygon pattern sample" data-pattern-surface="panel" data-pattern-mode="${mode}"><image href="pattern-previews/${settings.pattern}.svg?v=0.13.2" x="24" y="10" width="392" height="230"/><text x="220" y="257" text-anchor="middle" fill="#536b8c" font-family="Segoe UI,sans-serif" font-size="9">Pattern sample · exact live preview follows your selected surface</text><g data-pattern-cell="${settings.pattern}"/></svg>`;
        }
        const pattern = ["hexagon", "circle", "diamond", "square", "slot"].includes(settings.pattern) ? settings.pattern : "hexagon";
        const mode = ["through", "engrave", "emboss"].includes(settings.mode) ? settings.mode : "through";
        const finite = (value, fallback) => Number.isFinite(Number(value)) ? Number(value) : fallback;
        const pitch = Math.max(6, Math.min(12, finite(settings.pitch_mm, 8)));
        const web = Math.max(.7, Math.min(pitch*.6, finite(settings.web_mm, 1.2)));
        const half = (pitch-web)/2, radius = 24, height = 34;
        const rotation = finite(settings.rotation_deg, 0)*Math.PI/180, cosine=Math.cos(rotation), sine=Math.sin(rotation);
        const offsetU = finite(settings.offset_u_mm, 0)%pitch, offsetV = finite(settings.offset_v_mm, 0)%pitch;
        const border = Math.max(2, Math.min(7, finite(settings.border_mm, 2)));
        const depth = Math.max(.35, Math.min(2, finite(settings.depth_mm, 1)));
        const cylinder = (u,z,r=radius) => { const angle=Math.PI/4+u/radius; return [r*Math.cos(angle),r*Math.sin(angle),z]; };
        const polygon = (vertices, fill, stroke="#526d91") => `<polygon points="${vertices.map(point).join(" ")}" fill="${fill}" stroke="${stroke}" stroke-width=".45" stroke-linejoin="round"/>`;
        const sides=[];
        for(let i=0;i<40;i++) {
            const a=i*Math.PI/20,b=(i+1)*Math.PI/20,at=(angle,r,z)=>[r*Math.cos(angle),r*Math.sin(angle),z];
            const vertices=[at(a,radius,0),at(b,radius,0),at(b,radius,height),at(a,radius,height)];
            sides.push({depth:vertices.reduce((sum,p)=>sum+p[0]+p[1],0),markup:polygon(vertices,shade(A,.8+.18*Math.cos(a-Math.PI/4)))});
            const rim=[at(a,radius,height),at(b,radius,height),at(b,radius-2.5,height),at(a,radius-2.5,height)];
            sides.push({depth:1000,markup:polygon(rim,"#d6e1ef")});
        }
        sides.sort((a,b)=>a.depth-b.depth);
        let shape;
        if(pattern==="circle") shape=Array.from({length:20},(_,i)=>[half*Math.cos(i*Math.PI/10),half*Math.sin(i*Math.PI/10)]);
        else if(pattern==="slot") shape=Array.from({length:20},(_,i)=>{const angle=i*Math.PI/10,r=half*.4;return [(Math.cos(angle)>=0?1:-1)*(half-r)+r*Math.cos(angle),r*Math.sin(angle)];});
        else if(pattern==="diamond") shape=[[0,-half],[half,0],[0,half],[-half,0]];
        else if(pattern==="square") { const h=half*.8;shape=[[-h,-h],[h,-h],[h,h],[-h,h]]; }
        else shape=Array.from({length:6},(_,i)=>[half*Math.cos(i*Math.PI/3),half*Math.sin(i*Math.PI/3)]);
        const cells=[];
        for(let row=-6;row<=6;row++) for(let column=-8;column<=8;column++) {
            const centerU=(column+(pattern==="hexagon"&&Math.abs(row)%2?.5:0))*pitch,centerV=row*pitch;
            const points=shape.map(([u,v])=>[(centerU+u)*cosine-(centerV+v)*sine+offsetU,(centerU+u)*sine+(centerV+v)*cosine+height/2+offsetV]);
            if(points.some(([u,z])=>Math.abs(u)>Math.PI*radius/2-border||z<border||z>height-border)) continue;
            const surface=points.map(([u,z])=>cylinder(u,z));
            const feature=points.map(([u,z])=>cylinder(u,z,mode==="emboss"?radius+depth:mode==="engrave"?radius-depth:radius+.04));
            const walls=[];
            if(mode!=="through") for(let i=0;i<points.length;i++) walls.push(polygon([surface[i],surface[(i+1)%points.length],feature[(i+1)%points.length],feature[i]],mode==="emboss"?"#3c77be":"#4d698b"));
            cells.push(`<g data-pattern-cell="${pattern}">${walls.join("")}${polygon(feature,mode==="through"?"#253e5d":mode==="engrave"?"#6b87aa":B,mode==="through"?"#1f3550":"#3d618d")}</g>`);
        }
        return `<svg viewBox="0 0 440 270" role="img" aria-label="${pattern} ${mode} wrapped cylinder concept" data-pattern-surface="cylinder" data-pattern-mode="${mode}"><ellipse cx="220" cy="208" rx="94" ry="20" fill="#d4dfed"/>${sides.map(side=>side.markup).join("")}${cells.join("")}<text x="24" y="245" fill="#536b8c" font-family="Segoe UI,sans-serif" font-size="9">Pattern follows the cylinder · concept illustration</text></svg>`;
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
    return Object.freeze({ render, renderHingeLayout, renderPattern });
})();

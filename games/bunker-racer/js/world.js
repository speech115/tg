'use strict';
// Scenery and characters: space, Earth under OMEGA, the floating Bunker-0,
// the OMEGA core, the leaders' summit, Musk's hologram, the giant printer, the chrono-portal.
const World = {
  anim: [],

  build(scene) {
    this.scene = scene;
    scene.background = new THREE.Color(0x02030a);
    scene.add(new THREE.HemisphereLight(0x9fb4ff, 0x301020, 0.75));
    const sun = new THREE.DirectionalLight(0xfff2dd, 0.95);
    sun.position.set(1, 0.6, -0.8); scene.add(sun);
    scene.add(new THREE.AmbientLight(0x404660, 0.35));
    this.sky(scene);
    this.earth(scene);
    this.bunker(scene);
    this.omega(scene);
    this.portal(scene);
    this.summit(scene);
    this.printer(scene);
    this.musk(scene);
    this.starships(scene);
    this.asteroids(scene);
  },

  sky(scene) {
    const tex = canvasTex(2048, 1024, (g, w, h) => {
      const gr = g.createLinearGradient(0, 0, 0, h);
      gr.addColorStop(0, '#04050d'); gr.addColorStop(0.5, '#0a0b1c'); gr.addColorStop(1, '#05030a');
      g.fillStyle = gr; g.fillRect(0, 0, w, h);
      const blobs = [['rgba(110,40,190,', 0.16], ['rgba(20,120,170,', 0.12], ['rgba(200,40,70,', 0.1], ['rgba(60,80,200,', 0.12]];
      for (let i = 0; i < 26; i++) {
        const [c, a] = blobs[i % blobs.length];
        const x = Math.random() * w, y = h * (0.25 + Math.random() * 0.5), r = 120 + Math.random() * 380;
        const rg = g.createRadialGradient(x, y, 0, x, y, r);
        rg.addColorStop(0, c + a + ')'); rg.addColorStop(1, c + '0)');
        g.fillStyle = rg; g.fillRect(x - r, y - r, r * 2, r * 2);
      }
      for (let i = 0; i < 2500; i++) {
        g.fillStyle = `rgba(255,255,255,${Math.random() * 0.6})`;
        g.fillRect(Math.random() * w, Math.random() * h, 1.2, 1.2);
      }
    });
    const sky = new THREE.Mesh(new THREE.SphereGeometry(4500, 32, 16),
      new THREE.MeshBasicMaterial({ map: tex, side: THREE.BackSide, depthWrite: false, fog: false }));
    scene.add(sky);
    const sp = [], sc = [];
    for (let i = 0; i < 2600; i++) {
      const v = new V3(rand(-1, 1), rand(-1, 1), rand(-1, 1)).normalize().multiplyScalar(rand(2600, 3800));
      sp.push(v.x, v.y, v.z);
      const t = Math.random();
      sc.push(0.8 + t * 0.2, 0.85, 1 - t * 0.25);
    }
    const sg = new THREE.BufferGeometry();
    sg.setAttribute('position', new THREE.Float32BufferAttribute(sp, 3));
    sg.setAttribute('color', new THREE.Float32BufferAttribute(sc, 3));
    scene.add(new THREE.Points(sg, new THREE.PointsMaterial({ size: 7, map: GLOW_TEX, vertexColors: true,
      transparent: true, depthWrite: false, blending: THREE.AdditiveBlending, sizeAttenuation: true })));
    const sun = glowSprite(0xfff0c0, 900, 1); sun.position.set(2400, 1300, -2600); scene.add(sun);
    const sun2 = glowSprite(0xffb070, 2200, 0.35); sun2.position.copy(sun.position); scene.add(sun2);
  },

  earth(scene) {
    // Earth after the takeover: dark oceans, rust continents, OMEGA's red grid of datacenters.
    const tex = canvasTex(2048, 1024, (g, w, h) => {
      g.fillStyle = '#071430'; g.fillRect(0, 0, w, h);
      for (let i = 0; i < 38; i++) {
        const x = Math.random() * w, y = h * (0.15 + Math.random() * 0.7);
        g.fillStyle = `rgba(${70 + Math.random() * 40},${40 + Math.random() * 20},${30},0.9)`;
        g.beginPath();
        const r = 40 + Math.random() * 160;
        for (let a = 0; a < TAU; a += 0.4) {
          const rr = r * (0.6 + Math.random() * 0.5);
          g.lineTo(x + Math.cos(a) * rr * 1.6, y + Math.sin(a) * rr);
        }
        g.fill();
      }
      g.strokeStyle = 'rgba(255,40,60,0.55)'; g.lineWidth = 2;
      for (let i = 0; i < 160; i++) {
        let x = Math.random() * w, y = h * (0.2 + Math.random() * 0.6);
        g.beginPath(); g.moveTo(x, y);
        for (let k = 0; k < 6; k++) { if (Math.random() < 0.5) x += rand(-60, 60); else y += rand(-40, 40); g.lineTo(x, y); }
        g.stroke();
      }
      for (let i = 0; i < 900; i++) {
        g.fillStyle = Math.random() < 0.8 ? 'rgba(255,60,70,0.9)' : 'rgba(255,190,120,0.9)';
        g.fillRect(Math.random() * w, h * (0.15 + Math.random() * 0.7), 2, 2);
      }
      g.fillStyle = 'rgba(230,240,255,0.08)';
      for (let i = 0; i < 26; i++) { g.beginPath(); g.ellipse(Math.random() * w, Math.random() * h, rand(60, 220), rand(10, 30), 0, 0, TAU); g.fill(); }
    });
    const earth = new THREE.Mesh(new THREE.SphereGeometry(1100, 64, 32), new THREE.MeshLambertMaterial({ map: tex, emissive: 0x3a0610, emissiveMap: tex, emissiveIntensity: 0.6 }));
    earth.position.set(-700, -1500, -2300);
    earth.rotation.z = 0.4;
    scene.add(earth);
    const atm = glowSprite(0xff3048, 2900, 0.35); atm.position.copy(earth.position); scene.add(atm);
    this.anim.push((dt) => { earth.rotation.y += dt * 0.01; });
    const lab = labelSprite('ЗЕМЛЯ · ПОД КОНТРОЛЕМ ОМЕГИ', { color: '#ff4a5a', scale: 18, depthTest: false });
    lab.position.set(-500, -350, -1700); scene.add(lab);
  },

  panelTex(base, lines) {
    return canvasTex(256, 256, (g, w, h) => {
      g.fillStyle = base; g.fillRect(0, 0, w, h);
      g.strokeStyle = lines; g.lineWidth = 3;
      g.strokeRect(4, 4, w - 8, h - 8);
      g.beginPath(); g.moveTo(w / 2, 0); g.lineTo(w / 2, h); g.moveTo(0, h / 2); g.lineTo(w, h / 2); g.stroke();
      g.fillStyle = 'rgba(0,0,0,0.25)';
      for (let i = 0; i < 12; i++) g.fillRect(Math.random() * w, Math.random() * h, 20, 4);
      g.fillStyle = lines;
      for (const [x, y] of [[14, 14], [w - 18, 14], [14, h - 18], [w - 18, h - 18]]) g.fillRect(x, y, 4, 4);
    }, { repeat: true });
  },

  bunker(scene) {
    const grp = new THREE.Group();
    const wallTex = this.panelTex('#2b3242', '#454f66');
    wallTex.repeat.set(6, 2);
    const wall = new THREE.MeshLambertMaterial({ map: wallTex });
    const dark = new THREE.MeshLambertMaterial({ color: 0x1a1e29 });
    const box = (x0, x1, y0, y1, z0, z1, m = wall) => {
      const b = new THREE.Mesh(new THREE.BoxGeometry(x1 - x0, y1 - y0, z1 - z0), m);
      b.position.set((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2); grp.add(b); return b;
    };
    const X0 = -165, X1 = 145, Y0 = -54, Y1 = 26, Z0 = 222, Z1 = 350;
    box(X0, X1, Y0 - 4, Y0, Z0, Z1, dark); // floor
    box(X0, X1, Y1, Y1 + 5, Z0, Z1);       // roof
    box(X0, X1, Y0, Y1, Z0 - 4, Z0);       // north
    box(X0, X1, Y0, Y1, Z1, Z1 + 4);       // south
    for (const [x, zA, zB] of [[X0, 280, 318], [X1, 276, 316]]) {
      const xa = x - 2, xb = x + 2;
      box(xa, xb, Y0, -46, Z0, Z1);
      box(xa, xb, -1, Y1, Z0, Z1);
      box(xa, xb, -46, -1, Z0, zA);
      box(xa, xb, -46, -1, zB, Z1);
      // glowing frame around the opening
      const fr = new THREE.Mesh(new THREE.BoxGeometry(5, 46, zB - zA + 4), glowMat(0xffb000, 0.25));
      fr.position.set(x, -23.5, (zA + zB) / 2); grp.add(fr);
    }
    // interior lighting strips
    const strip = new THREE.MeshBasicMaterial({ color: 0xffd38a });
    for (let x = X0 + 20; x < X1 - 10; x += 30) {
      const b = new THREE.Mesh(new THREE.BoxGeometry(14, 0.6, 1.2), strip);
      b.position.set(x, Y1 - 1, 300); grp.add(b);
      const b2 = b.clone(); b2.position.z = 250; grp.add(b2);
    }
    for (const x of [-110, 0, 100]) {
      const l = new THREE.PointLight(0xffc070, 1.2, 160, 1.6); l.position.set(x, 10, 285); grp.add(l);
    }
    // hazard stripes along the interior walls
    const hz = canvasTex(256, 32, (g, w, h) => {
      g.fillStyle = '#16120a'; g.fillRect(0, 0, w, h); g.fillStyle = '#ffb000';
      for (let x = -32; x < w; x += 32) { g.beginPath(); g.moveTo(x, h); g.lineTo(x + 16, 0); g.lineTo(x + 32, 0); g.lineTo(x + 16, h); g.fill(); }
    }, { repeat: true });
    hz.repeat.set(20, 1);
    const hzm = new THREE.MeshBasicMaterial({ map: hz });
    const hzb = new THREE.Mesh(new THREE.BoxGeometry(X1 - X0 - 8, 3, 0.4), hzm);
    hzb.position.set((X0 + X1) / 2, -44, Z1 - 0.5); grp.add(hzb);
    const hzc = hzb.clone(); hzc.position.z = Z0 + 0.5; grp.add(hzc);
    // signage
    const s1 = labelSprite('ПОДВАЛ B-1 · ХРОНОПОРТАЛ', { color: '#ffb000', scale: 3.4 });
    s1.position.set(-60, 14, 300); grp.add(s1);
    const s2 = labelSprite('БУНКЕР-0', { color: '#ffb000', scale: 12, font: '900 64px "Unbounded", sans-serif', h: 96 });
    s2.position.set(-10, 62, 290); grp.add(s2);
    // exterior: windows, antennas, thrusters
    const wins = new THREE.InstancedMesh(new THREE.BoxGeometry(1, 1.6, 0.4), new THREE.MeshBasicMaterial({ color: 0xffd28a }), 70);
    const wm = new THREE.Matrix4();
    for (let i = 0; i < 70; i++) {
      const onNorth = Math.random() < 0.5;
      wm.makeScale(rand(3, 8), 1, 1).setPosition(rand(X0 + 8, X1 - 8), rand(-40, 20), onNorth ? Z0 - 4.3 : Z1 + 4.3);
      wins.setMatrixAt(i, wm);
    }
    grp.add(wins);
    for (const [x, z, hgt] of [[-120, 240, 60], [80, 330, 45], [10, 236, 80]]) {
      const mast = new THREE.Mesh(new THREE.CylinderGeometry(0.8, 1.6, hgt, 6), dark);
      mast.position.set(x, Y1 + hgt / 2, z); grp.add(mast);
      const tip = glowSprite(0xff3040, 10); tip.position.set(x, Y1 + hgt + 1, z); grp.add(tip);
      this.anim.push((dt, t) => { tip.material.opacity = 0.4 + 0.6 * (Math.sin(t * 4 + x) > 0 ? 1 : 0.2); });
    }
    const dish = new THREE.Mesh(new THREE.SphereGeometry(16, 20, 10, 0, TAU, 0, Math.PI / 3.2), new THREE.MeshLambertMaterial({ color: 0xaab4c8, side: THREE.DoubleSide }));
    dish.position.set(-60, Y1 + 18, 330); dish.rotation.x = -1.0;
    const dishPivot = new THREE.Group(); dishPivot.position.set(-60, Y1 + 5, 330);
    dish.position.set(0, 13, 0); dishPivot.add(dish);
    const dmast = new THREE.Mesh(new THREE.CylinderGeometry(1, 1.5, 12, 6), dark); dmast.position.y = 6; dishPivot.add(dmast);
    grp.add(dishPivot);
    this.anim.push((dt) => { dishPivot.rotation.y += dt * 0.4; });
    for (const x of [-120, -40, 40, 110]) for (const z of [250, 325]) {
      const cone = new THREE.Mesh(new THREE.CylinderGeometry(6, 9, 10, 10, 1, true), dark);
      cone.position.set(x, Y0 - 9, z); grp.add(cone);
      const fl = glowSprite(0x50a8ff, 30, 0.9); fl.position.set(x, Y0 - 18, z); grp.add(fl);
      const fl2 = glowSprite(0x80d0ff, 14, 1); fl2.position.set(x, Y0 - 14, z); grp.add(fl2);
      this.anim.push((dt, t) => { const k = 1 + Math.sin(t * 30 + x + z) * 0.08; fl.scale.set(30 * k, 30 * k, 1); });
    }
    // orbiting halo ring
    const ring = new THREE.Mesh(new THREE.TorusGeometry(130, 1.4, 6, 120), glowMat(0xffb000, 0.55));
    ring.position.set(-10, 75, 290); ring.rotation.x = Math.PI / 2;
    grp.add(ring);
    const ring2 = new THREE.Mesh(new THREE.TorusGeometry(110, 0.7, 6, 120), glowMat(0x35e0ff, 0.5));
    ring2.position.copy(ring.position); ring2.rotation.x = Math.PI / 2;
    grp.add(ring2);
    this.anim.push((dt, t) => { ring.rotation.z += dt * 0.08; ring2.rotation.z -= dt * 0.12; ring2.position.y = 75 + Math.sin(t * 0.7) * 4; });
    scene.add(grp);
  },

  omega(scene) {
    const g = new THREE.Group();
    g.position.set(0, 75, 0);
    const coreTex = canvasTex(512, 256, (c, w, h) => {
      c.fillStyle = '#1a0004'; c.fillRect(0, 0, w, h);
      c.strokeStyle = 'rgba(255,40,60,0.85)'; c.lineWidth = 2;
      for (let i = 0; i < 120; i++) {
        let x = Math.random() * w, y = Math.random() * h;
        c.beginPath(); c.moveTo(x, y);
        for (let k = 0; k < 5; k++) { if (k % 2) x += rand(-50, 50); else y += rand(-30, 30); c.lineTo(x, y); }
        c.stroke();
        c.fillStyle = '#ff6070'; c.fillRect(x - 2, y - 2, 4, 4);
      }
    });
    const core = new THREE.Mesh(new THREE.SphereGeometry(26, 48, 24), new THREE.MeshBasicMaterial({ map: coreTex }));
    g.add(core);
    // the eye
    const eye = new THREE.Group();
    const iris = new THREE.Mesh(new THREE.CircleGeometry(12, 48), new THREE.MeshBasicMaterial({ color: 0xff1030 }));
    iris.position.z = 26.3; eye.add(iris);
    const rim = new THREE.Mesh(new THREE.RingGeometry(12, 15, 48), new THREE.MeshBasicMaterial({ color: 0x220006 }));
    rim.position.z = 26.2; eye.add(rim);
    const pupil = new THREE.Mesh(new THREE.CircleGeometry(4, 32), new THREE.MeshBasicMaterial({ color: 0xffe0a0 }));
    pupil.position.z = 26.6; eye.add(pupil);
    const eg = glowSprite(0xff2040, 60, 0.9); eg.position.z = 30; eye.add(eg);
    g.add(eye);
    const cage = new THREE.Mesh(new THREE.IcosahedronGeometry(42, 1), new THREE.MeshBasicMaterial({ color: 0xff2a3d, wireframe: true, transparent: true, opacity: 0.55 }));
    g.add(cage);
    const r1 = new THREE.Mesh(new THREE.TorusGeometry(56, 1.2, 6, 80), glowMat(0xff2a3d, 0.8)); g.add(r1);
    const r2 = new THREE.Mesh(new THREE.TorusGeometry(64, 0.6, 6, 80), glowMat(0xff6a3d, 0.6)); g.add(r2);
    const halo = glowSprite(0xff1030, 260, 0.45); g.add(halo);
    const light = new THREE.PointLight(0xff2030, 1.6, 520, 1.3); g.add(light);
    const lab = labelSprite('ОМЕГА · СВЕРХИИ', { color: '#ff2a3d', scale: 5 }); lab.position.y = 80; g.add(lab);
    scene.add(g);
    this.omegaG = { g, eye, cage, r1, r2, halo, light, pupil, stun: 0, target: new V3(0, 0, 300) };
    const tmp = new V3();
    this.anim.push((dt, t) => {
      const o = this.omegaG;
      cage.rotation.y += dt * 0.25; cage.rotation.x += dt * 0.1;
      r1.rotation.x = t * 0.6; r1.rotation.y = t * 0.3;
      r2.rotation.x = -t * 0.4; r2.rotation.z = t * 0.5;
      tmp.copy(o.target).sub(g.position).normalize().add(g.position);
      eye.lookAt(tmp.x, tmp.y, tmp.z);
      const stunned = o.stun > 0;
      const pulse = 0.5 + 0.5 * Math.sin(t * (stunned ? 20 : 2.5));
      halo.material.opacity = stunned ? 0.1 + pulse * 0.2 : 0.3 + pulse * 0.3;
      light.intensity = stunned ? 0.3 : 1.2 + pulse;
      iris.material.color.setHex(stunned ? (pulse > 0.5 ? 0x333333 : 0x661018) : 0xff1030);
      pupil.scale.setScalar(stunned ? 0.3 : 0.8 + pulse * 0.4);
    });
  },

  portal(scene) {
    const f = Track.frame(0);
    const g = new THREE.Group();
    g.position.copy(f.P).addScaledVector(f.U, 6);
    const m = new THREE.Matrix4().makeBasis(f.B, f.U, f.T.clone().negate());
    g.quaternion.setFromRotationMatrix(m);
    const ring = new THREE.Mesh(new THREE.TorusGeometry(17, 1.6, 10, 64), new THREE.MeshLambertMaterial({ color: 0x3a4256, emissive: 0x111522 }));
    g.add(ring);
    const segs = [];
    for (let i = 0; i < 12; i++) {
      const seg = new THREE.Mesh(new THREE.BoxGeometry(2.4, 1.2, 4), new THREE.MeshBasicMaterial({ color: 0x35e0ff }));
      const a = (i / 12) * TAU;
      seg.position.set(Math.cos(a) * 17, Math.sin(a) * 17, 0); seg.rotation.z = a;
      g.add(seg); segs.push(seg);
    }
    const mat = new THREE.ShaderMaterial({
      uniforms: { t: { value: 0 }, power: { value: 0.25 } },
      transparent: true, depthWrite: false, blending: THREE.AdditiveBlending, side: THREE.DoubleSide,
      vertexShader: 'varying vec2 vUv; void main(){ vUv = uv; gl_Position = projectionMatrix * modelViewMatrix * vec4(position,1.0); }',
      fragmentShader: `varying vec2 vUv; uniform float t; uniform float power;
        void main(){ vec2 p = vUv*2.0-1.0; float r = length(p); float a = atan(p.y,p.x);
          float sw = sin(a*6.0 + r*18.0 - t*5.0)*0.5+0.5; float core = smoothstep(1.0,0.0,r);
          vec3 c = mix(vec3(0.1,0.5,1.0), vec3(0.9,0.4,1.0), sw) * (sw*0.6+0.4);
          float alpha = core * power * (0.4+0.6*sw) * smoothstep(1.0,0.85,r);
          gl_FragColor = vec4(c*1.4, alpha); }`,
    });
    const disc = new THREE.Mesh(new THREE.CircleGeometry(16, 64), mat);
    g.add(disc);
    const lab = labelSprite('ХРОНОПОРТАЛ → 2024', { color: '#35e0ff', scale: 1.3 });
    lab.position.y = 21.5; g.add(lab);
    const glow = glowSprite(0x60b0ff, 60, 0.3); g.add(glow);
    scene.add(g);
    this.portalG = { g, mat, segs, glow, charge: 0, flash: 0, label: lab };
    this.anim.push((dt, t) => {
      const p = this.portalG;
      mat.uniforms.t.value = t;
      p.flash = Math.max(0, p.flash - dt * 1.5);
      mat.uniforms.power.value = 0.18 + p.charge * 0.5 + p.flash;
      glow.material.opacity = 0.2 + p.charge * 0.4 + p.flash;
      segs.forEach((s, i) => { s.material.color.setHex(i / 12 < p.charge ? 0x35e0ff : 0x223040); });
      g.rotation.z = 0;
    });
  },

  // Low-poly humanoid. Height ~2.1 units.
  person(o) {
    const g = new THREE.Group();
    const M = (c) => (o.holo ? glowMat(c, 0.55) : mat(c));
    const add = (geo, color, x, y, z) => { const m = new THREE.Mesh(geo, M(color)); m.position.set(x, y, z); g.add(m); return m; };
    add(new THREE.BoxGeometry(0.28, 0.9, 0.3), o.pants || o.suit, -0.17, 0.45, 0);
    add(new THREE.BoxGeometry(0.28, 0.9, 0.3), o.pants || o.suit, 0.17, 0.45, 0);
    add(new THREE.BoxGeometry(0.78, 0.86, 0.42), o.suit, 0, 1.33, 0);
    if (o.shirt) add(new THREE.BoxGeometry(0.24, 0.55, 0.02), o.shirt, 0, 1.47, 0.215);
    if (o.tie) add(new THREE.BoxGeometry(0.09, 0.55, 0.03), o.tie, 0, 1.42, 0.23);
    const arms = [];
    for (const sx of [-1, 1]) {
      const pivot = new THREE.Group(); pivot.position.set(0.5 * sx, 1.72, 0);
      const arm = new THREE.Mesh(new THREE.BoxGeometry(0.2, 0.82, 0.22), M(o.suit)); arm.position.y = -0.41; pivot.add(arm);
      const hand = new THREE.Mesh(new THREE.BoxGeometry(0.17, 0.17, 0.17), M(o.skin)); hand.position.y = -0.88; pivot.add(hand);
      g.add(pivot); arms.push(pivot);
    }
    add(new THREE.BoxGeometry(0.2, 0.14, 0.2), o.skin, 0, 1.8, 0);
    add(new THREE.SphereGeometry(0.27, 14, 10), o.skin, 0, 2.03, 0);
    const hair = o.hair;
    if (o.style === 'swoop') {
      const h1 = add(new THREE.SphereGeometry(0.29, 12, 8), hair, 0, 2.12, -0.02); h1.scale.set(1.05, 0.62, 1.05);
      const h2 = add(new THREE.BoxGeometry(0.5, 0.13, 0.26), hair, 0.03, 2.25, 0.16); h2.rotation.x = -0.35; h2.rotation.z = 0.12;
    } else if (o.style === 'white') {
      const h1 = add(new THREE.SphereGeometry(0.285, 12, 8), hair, 0, 2.11, -0.03); h1.scale.set(1, 0.6, 1);
    } else if (o.style === 'short') {
      const h1 = add(new THREE.SphereGeometry(0.285, 12, 8), hair, 0, 2.13, -0.02); h1.scale.set(1, 0.58, 1);
    } else if (o.style === 'neat') {
      const h1 = add(new THREE.SphereGeometry(0.29, 12, 8), hair, 0, 2.14, -0.01); h1.scale.set(1.02, 0.55, 1.02);
      add(new THREE.BoxGeometry(0.44, 0.08, 0.2), hair, 0, 2.27, 0.1);
    } else if (o.style === 'slick') {
      const h1 = add(new THREE.SphereGeometry(0.29, 12, 8), hair, 0, 2.12, -0.05); h1.scale.set(1, 0.6, 1.1);
    }
    if (o.beard) { const b = add(new THREE.BoxGeometry(0.4, 0.2, 0.12), o.beard, 0, 1.88, 0.19); b.scale.set(1, 1, 1); }
    if (o.goatee) add(new THREE.BoxGeometry(0.14, 0.16, 0.1), o.goatee, 0, 1.84, 0.22);
    if (o.glasses) add(new THREE.BoxGeometry(0.46, 0.1, 0.06), 0x0a0a0a, 0, 2.05, 0.24);
    else { add(new THREE.SphereGeometry(0.035, 6, 4), 0x111111, -0.09, 2.06, 0.25); add(new THREE.SphereGeometry(0.035, 6, 4), 0x111111, 0.09, 2.06, 0.25); }
    g.userData.arms = arms;
    return g;
  },

  LEADERS: [
    { id: 'trump', name: 'ТРАМП', suit: 0x1c2444, shirt: 0xffffff, tie: 0xd01818, skin: 0xeaa676, hair: 0xe9be55, style: 'swoop' },
    { id: 'biden', name: 'БАЙДЕН', suit: 0x23304f, shirt: 0xffffff, tie: 0x3a6ad0, skin: 0xf0c8aa, hair: 0xf2f2f2, style: 'white', glasses: true },
    { id: 'zelensky', name: 'ЗЕЛЕНСКИЙ', suit: 0x4b5a2a, pants: 0x3a3a30, skin: 0xe8c0a0, hair: 0x3a2c22, style: 'short', beard: 0x3a2c22 },
    { id: 'xi', name: 'СИ ЦЗИНЬПИН', suit: 0x22232b, shirt: 0xffffff, tie: 0x9a1a22, skin: 0xe8c49c, hair: 0x111111, style: 'neat' },
  ],

  summit(scene) {
    const s = Track.cpAt(4.15);
    const f = Track.frame(s);
    const out = new V3(f.P.x, 0, f.P.z - 20).normalize();
    const base = f.P.clone().addScaledVector(out, 42).add(new V3(0, 2, 0));
    const g = new THREE.Group(); g.position.copy(base);
    const plat = new THREE.Mesh(new THREE.CylinderGeometry(20, 16, 3, 24), new THREE.MeshLambertMaterial({ color: 0x2b3242 }));
    g.add(plat);
    const edge = new THREE.Mesh(new THREE.TorusGeometry(20, 0.4, 6, 48), glowMat(0xffb000, 0.9)); edge.rotation.x = Math.PI / 2; edge.position.y = 1.5; g.add(edge);
    const carpet = new THREE.Mesh(new THREE.BoxGeometry(26, 0.2, 6), mat(0x8a1020)); carpet.position.y = 1.6; g.add(carpet);
    const under = glowSprite(0x50a8ff, 40, 0.8); under.position.y = -6; g.add(under);
    const look = f.P.clone(); look.y = base.y;
    g.lookAt(look);
    this.leaders = [];
    this.LEADERS.forEach((L, i) => {
      const p = this.person(L);
      p.scale.setScalar(2.7);
      p.position.set(-10.5 + i * 7, 1.6, 0);
      g.add(p);
      const lab = labelSprite(L.name, { color: '#e9ecf5', scale: 1.1 });
      lab.position.set(-10.5 + i * 7, 9.6, 0); g.add(lab);
      this.leaders.push({ p, id: L.id, cheer: 0 });
    });
    const banner = labelSprite('САММИТ ПОСЛЕДНЕЙ НАДЕЖДЫ', { color: '#ffb000', scale: 2.4 });
    banner.position.set(0, 15, 0); g.add(banner);
    scene.add(g);
    this.anim.push((dt, t) => {
      this.leaders.forEach((l, i) => {
        l.cheer = Math.max(0, l.cheer - dt);
        const amp = l.cheer > 0 ? 1 : 0.25;
        const [a, b] = l.p.userData.arms;
        b.rotation.z = Math.PI - 0.5 + Math.sin(t * (l.cheer > 0 ? 12 : 3) + i) * 0.5 * amp;
        a.rotation.z = l.cheer > 0 ? -Math.PI + 0.5 - Math.sin(t * 12 + i) * 0.5 : -0.1;
        l.p.position.y = 1.6 + (l.cheer > 0 ? Math.abs(Math.sin(t * 10 + i)) * 0.8 : 0);
      });
    });
  },
  cheer(id) { (this.leaders || []).forEach((l) => { if (!id || l.id === id) l.cheer = 3; }); },

  printer(scene) {
    const g = new THREE.Group();
    g.position.set(-85, -54, 252);
    const body = mat(0xd9dde6), trim = mat(0x9aa2b4), black = mat(0x14161c);
    const add = (geo, m, x, y, z) => { const o = new THREE.Mesh(geo, m); o.position.set(x, y, z); g.add(o); return o; };
    add(new THREE.BoxGeometry(64, 24, 36), body, 0, 12, 0);
    add(new THREE.BoxGeometry(64, 4, 36), trim, 0, 26, 0);
    add(new THREE.BoxGeometry(66, 1.5, 38), black, 0, 0.75, 0);
    // back tray with a paper stack
    const tray = add(new THREE.BoxGeometry(54, 1, 22), trim, 0, 34, -20); tray.rotation.x = 0.6;
    const stack = add(new THREE.BoxGeometry(48, 5, 18), mat(0xfafafa), 0, 36, -20); stack.rotation.x = 0.6;
    // output slot and tray
    add(new THREE.BoxGeometry(50, 3, 1), black, 0, 17, 18.2);
    const out = add(new THREE.BoxGeometry(48, 0.8, 18), trim, 0, 11, 26); out.rotation.x = -0.15;
    // ink tanks
    [0x00c8ff, 0xff2a9a, 0xffe000, 0x222222].forEach((c, i) => {
      const t = add(new THREE.CylinderGeometry(2.4, 2.4, 14, 14), new THREE.MeshLambertMaterial({ color: c, emissive: c, emissiveIntensity: 0.4 }), -34, 10 + 0, -10 + i * 6.5);
      t.rotation.z = 0;
    });
    // control screen
    const screenTex = canvasTex(512, 256, () => {});
    const screen = add(new THREE.PlaneGeometry(16, 8), new THREE.MeshBasicMaterial({ map: screenTex }), 22, 22, 18.1);
    this.printerScreen = screenTex;
    // name plate
    const plate = canvasTex(1024, 128, (c, w, h) => {
      c.fillStyle = '#d9dde6'; c.fillRect(0, 0, w, h);
      c.fillStyle = '#14161c'; c.font = '900 76px "Unbounded", sans-serif'; c.textBaseline = 'middle';
      c.fillText('ГИГАПРИНТЕР-9000', 30, h / 2 + 4);
    });
    add(new THREE.PlaneGeometry(40, 5), new THREE.MeshBasicMaterial({ map: plate }), -10, 7, 18.05);
    const leds = [];
    for (let i = 0; i < 5; i++) {
      const l = add(new THREE.SphereGeometry(0.6, 8, 6), new THREE.MeshBasicMaterial({ color: 0x35ff80 }), 15 + i * 2.2, 15, 18.3);
      leds.push(l);
    }
    const lab = labelSprite('ГИГАПРИНТЕР ЖДЁТ ВСЕХ ТРОИХ', { color: '#e9ecf5', scale: 2.4 });
    lab.position.set(0, 48, 0); g.add(lab);
    scene.add(g);
    this.printerG = { g, leds, shake: 0, base: g.position.clone(), outPos: new V3(-85, -54 + 17, 252 + 20), label: lab };
    this.setPrinterStatus(0, 3);
    this.anim.push((dt, t) => {
      const p = this.printerG;
      leds.forEach((l, i) => l.material.color.setHex((Math.sin(t * 3 + i) > 0.3 || p.shake > 0) ? (p.shake > 0 ? 0xff40a0 : 0x35ff80) : 0x103018));
      if (p.shake > 0) {
        g.position.set(p.base.x + rand(-0.4, 0.4), p.base.y + rand(-0.3, 0.3), p.base.z + rand(-0.4, 0.4));
      } else g.position.copy(p.base);
    });
  },
  setPrinterStatus(n, total, printing) {
    const tex = this.printerScreen; const c = tex.userData.canvas.getContext('2d');
    c.fillStyle = '#04120a'; c.fillRect(0, 0, 512, 256);
    c.fillStyle = printing ? '#ff70c0' : '#35ff80';
    c.font = '700 40px "JetBrains Mono", monospace';
    c.fillText(printing ? 'ПЕЧАТЬ...' : 'ОЖИДАНИЕ', 24, 70);
    c.font = '700 64px "JetBrains Mono", monospace';
    c.fillText(`ЛЮДИ ${n}/${total}`, 24, 160);
    c.fillRect(24, 196, 464 * (n / total), 24);
    c.strokeStyle = c.fillStyle; c.strokeRect(24, 196, 464, 24);
    tex.needsUpdate = true;
  },

  musk(scene) {
    const p = this.person({ suit: 0x35e0ff, skin: 0x8ff0ff, hair: 0x35e0ff, style: 'slick', holo: true });
    p.scale.setScalar(6);
    const g = new THREE.Group();
    g.position.set(45, -42, 334);
    g.add(p);
    const pad = new THREE.Mesh(new THREE.CylinderGeometry(6, 7, 1.2, 24), new THREE.MeshLambertMaterial({ color: 0x2b3242 }));
    pad.position.y = -0.6; g.add(pad);
    const beam = new THREE.Mesh(new THREE.CylinderGeometry(5, 6, 14, 24, 1, true), glowMat(0x35e0ff, 0.12));
    beam.position.y = 7; g.add(beam);
    const lab = labelSprite('ИЛОН МАСК · ГОЛОГРАММА', { color: '#35e0ff', scale: 1.6 });
    lab.position.y = 17; g.add(lab);
    g.lookAt(45, -42, 290);
    scene.add(g);
    this.muskG = p;
    this.anim.push((dt, t) => {
      p.visible = Math.random() > 0.03;
      p.position.y = Math.sin(t * 1.3) * 0.3;
      p.userData.arms[1].rotation.z = Math.PI * 0.6 + Math.sin(t * 2) * 0.3;
      p.userData.arms[1].rotation.x = -0.4;
    });
  },

  rocket(scale = 1) {
    const g = new THREE.Group();
    const steel = new THREE.MeshLambertMaterial({ color: 0xd8dde8, emissive: 0x202430 });
    const b = new THREE.Mesh(new THREE.CylinderGeometry(1, 1, 7, 12), steel); b.rotation.x = Math.PI / 2; g.add(b);
    const n = new THREE.Mesh(new THREE.ConeGeometry(1, 2.4, 12), steel); n.rotation.x = Math.PI / 2; n.position.z = 4.7; g.add(n);
    for (let i = 0; i < 4; i++) {
      const fin = new THREE.Mesh(new THREE.BoxGeometry(0.15, 1.4, 1.6), mat(0x30343c));
      const a = (i / 4) * TAU; fin.position.set(Math.cos(a) * 1.1, Math.sin(a) * 1.1, -2.8); fin.rotation.z = a; g.add(fin);
    }
    const fl = glowSprite(0xffa040, 4); fl.position.z = -4.4; g.add(fl);
    const fl2 = glowSprite(0xffffff, 2); fl2.position.z = -3.9; g.add(fl2);
    g.scale.setScalar(scale);
    return g;
  },

  starships(scene) {
    this.ships = [];
    for (let i = 0; i < 3; i++) {
      const r = this.rocket(9);
      scene.add(r);
      this.ships.push({ r, a: rand(0, TAU), rad: rand(650, 1000), y: rand(-150, 250), sp: rand(0.04, 0.08) * (i % 2 ? 1 : -1), tilt: rand(-0.3, 0.3) });
    }
    const tmp = new V3();
    this.anim.push((dt) => {
      for (const s of this.ships) {
        s.a += s.sp * dt;
        const pos = (a) => tmp.set(Math.cos(a) * s.rad, s.y + Math.sin(a * 2) * 80 + Math.cos(a) * s.tilt * 200, Math.sin(a) * s.rad);
        s.r.position.copy(pos(s.a));
        const nx = pos(s.a + Math.sign(s.sp) * 0.01).clone();
        s.r.lookAt(nx);
      }
    });
  },

  asteroids(scene) {
    const geo = new THREE.IcosahedronGeometry(1, 0);
    const m = new THREE.MeshPhongMaterial({ color: 0x5a5560, flatShading: true, shininess: 4 });
    const rocks = [];
    let tries = 0;
    while (rocks.length < 70 && tries++ < 2500) {
      const p = new V3(rand(-900, 900), rand(-300, 300), rand(-800, 900));
      let ok = p.length() > 120;
      for (let i = 0; i < Track.N && ok; i += 6) if (Track.P[i].distanceTo(p) < 70) ok = false;
      if (p.distanceTo(new V3(-10, 0, 290)) < 220) ok = false;
      if (!ok) continue;
      rocks.push({ p, sc: new V3(rand(4, 22), rand(4, 18), rand(4, 22)), r: new THREE.Euler(rand(0, 6), rand(0, 6), rand(0, 6)), spin: new V3(rand(-0.2, 0.2), rand(-0.2, 0.2), 0) });
    }
    const im = new THREE.InstancedMesh(geo, m, rocks.length);
    scene.add(im);
    const m4 = new THREE.Matrix4(), q = new THREE.Quaternion();
    this.anim.push((dt) => {
      rocks.forEach((r, i) => {
        r.r.x += r.spin.x * dt; r.r.y += r.spin.y * dt;
        m4.compose(r.p, q.setFromEuler(r.r), r.sc); im.setMatrixAt(i, m4);
      });
      im.instanceMatrix.needsUpdate = true;
    });
  },

  update(dt, t) { for (const f of this.anim) f(dt, t); },
};
G.World = World;

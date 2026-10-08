'use strict';
// Racers, items, weapons, pickups, OMEGA's drones and wave, McAfee's drops, particles.

// ------------------------------------------------------------ particles
const Particles = {
  max: 4000, n: 0,
  init(scene) {
    const M = this.max;
    this.pos = new Float32Array(M * 3); this.col = new Float32Array(M * 3);
    this.size = new Float32Array(M); this.alpha = new Float32Array(M);
    this.vel = new Float32Array(M * 3); this.life = new Float32Array(M); this.maxLife = new Float32Array(M);
    this.drag = new Float32Array(M); this.grow = new Float32Array(M); this.grav = new Float32Array(M);
    const g = new THREE.BufferGeometry();
    g.setAttribute('position', new THREE.BufferAttribute(this.pos, 3).setUsage(THREE.DynamicDrawUsage));
    g.setAttribute('color', new THREE.BufferAttribute(this.col, 3).setUsage(THREE.DynamicDrawUsage));
    g.setAttribute('size', new THREE.BufferAttribute(this.size, 1).setUsage(THREE.DynamicDrawUsage));
    g.setAttribute('alpha', new THREE.BufferAttribute(this.alpha, 1).setUsage(THREE.DynamicDrawUsage));
    this.geo = g;
    this.mat = new THREE.ShaderMaterial({
      uniforms: { map: { value: GLOW_TEX }, proj: { value: 400 } },
      vertexShader: `attribute float size; attribute float alpha; attribute vec3 color; varying vec3 vC; varying float vA; uniform float proj;
        void main(){ vC = color; vA = alpha; vec4 mv = modelViewMatrix * vec4(position,1.0);
          gl_PointSize = clamp(size * proj / max(0.1,-mv.z), 0.0, 90.0); gl_Position = projectionMatrix * mv; }`,
      fragmentShader: `uniform sampler2D map; varying vec3 vC; varying float vA;
        void main(){ vec4 t = texture2D(map, gl_PointCoord); gl_FragColor = vec4(vC * t.rgb, t.a * vA); }`,
      transparent: true, depthWrite: false, blending: THREE.AdditiveBlending,
    });
    this.points = new THREE.Points(g, this.mat);
    this.points.frustumCulled = false;
    scene.add(this.points);
  },
  spawn(p, v, color, size, life, o = {}) {
    if (this.n >= this.max) return;
    const i = this.n++;
    this.pos[i * 3] = p.x; this.pos[i * 3 + 1] = p.y; this.pos[i * 3 + 2] = p.z;
    this.vel[i * 3] = v.x; this.vel[i * 3 + 1] = v.y; this.vel[i * 3 + 2] = v.z;
    const c = color instanceof THREE.Color ? color : new THREE.Color(color);
    this.col[i * 3] = c.r; this.col[i * 3 + 1] = c.g; this.col[i * 3 + 2] = c.b;
    this.size[i] = size; this.alpha[i] = 1; this.life[i] = life; this.maxLife[i] = life;
    this.drag[i] = o.drag || 0; this.grow[i] = o.grow || 0; this.grav[i] = o.grav || 0;
  },
  burst(p, color, count, speed, size, life, o = {}) {
    const v = new V3();
    for (let k = 0; k < count; k++) {
      v.set(rand(-1, 1), rand(-1, 1), rand(-1, 1)).normalize().multiplyScalar(speed * rand(0.3, 1));
      if (o.dir) v.addScaledVector(o.dir, o.dirK || 1);
      this.spawn(p, v, color, size * rand(0.6, 1.3), life * rand(0.6, 1.2), o);
    }
  },
  update(dt) {
    let i = 0;
    while (i < this.n) {
      this.life[i] -= dt;
      if (this.life[i] <= 0) { this.kill(i); continue; }
      const k = Math.exp(-this.drag[i] * dt);
      this.vel[i * 3] *= k; this.vel[i * 3 + 1] = this.vel[i * 3 + 1] * k - this.grav[i] * dt; this.vel[i * 3 + 2] *= k;
      this.pos[i * 3] += this.vel[i * 3] * dt; this.pos[i * 3 + 1] += this.vel[i * 3 + 1] * dt; this.pos[i * 3 + 2] += this.vel[i * 3 + 2] * dt;
      this.size[i] += this.grow[i] * dt;
      this.alpha[i] = Math.min(1, (this.life[i] / this.maxLife[i]) * 1.6);
      i++;
    }
    const g = this.geo;
    g.setDrawRange(0, this.n);
    g.attributes.position.needsUpdate = true; g.attributes.color.needsUpdate = true;
    g.attributes.size.needsUpdate = true; g.attributes.alpha.needsUpdate = true;
  },
  kill(i) {
    const j = --this.n;
    if (i === j) return;
    for (const [a, w] of [[this.pos, 3], [this.vel, 3], [this.col, 3]]) for (let c = 0; c < w; c++) a[i * w + c] = a[j * w + c];
    for (const a of [this.size, this.alpha, this.life, this.maxLife, this.drag, this.grow, this.grav]) a[i] = a[j];
  },
  clear() { this.n = 0; },
};

// ------------------------------------------------------------ items
const ITEMS = {
  nitro: { name: 'NITRO', color: '#ffb000' },
  nitro3: { name: 'NITRO ×3', color: '#ffb000' },
  slime: { name: 'PLASMA SLIME', color: '#7dff5a' },
  rocket: { name: 'MUSK ROCKET', color: '#e9ecf5' },
  gbomb: { name: 'GRAVITY BOMB', color: '#58b4ff' },
  shield: { name: 'FABLE+ASTRA SHIELD', color: '#61e8ff' },
  kill: { name: 'KILL SWITCH', color: '#ff2a3d' },
};
const WEAPONS = {
  laser: { name: 'LASER', ammo: 36, rate: 0.1, color: 0xff3b3b },
  rail: { name: 'RAILGUN', ammo: 6, rate: 0.55, color: 0x61e8ff },
  swarm: { name: 'ROCKET SWARM', ammo: 10, rate: 0.28, color: 0xffb000 },
};
function rollItem(rank, total, isHuman) {
  const r = rank / Math.max(1, total - 1); // 0 = leader, 1 = last
  if (isHuman && Math.random() < 0.004 + r * 0.02) return 'kill';
  const table = r < 0.3
    ? { slime: 34, gbomb: 18, nitro: 26, rocket: 14, shield: 8 }
    : r < 0.7
      ? { nitro: 24, rocket: 24, slime: 14, gbomb: 14, nitro3: 12, shield: 12 }
      : { nitro3: 30, rocket: 28, nitro: 14, gbomb: 12, shield: 16 };
  if (!isHuman) delete table.shield;
  let sum = 0; for (const k in table) sum += table[k];
  let x = Math.random() * sum;
  for (const k in table) { x -= table[k]; if (x <= 0) return k; }
  return 'nitro';
}

// ------------------------------------------------------------ car meshes
const CarMeshes = {
  kart(color, name) {
    const g = new THREE.Group();
    const col = new THREE.Color(color);
    const model = recolor(asset('kart', 'Kart'), {
      Paint: (m) => { m.color.copy(col); m.emissive = new THREE.Color(0, 0, 0); },
      Neon: { color: color, emissive: color, k: 5 },
    });
    g.add(model);
    const body = findMat(model, 'Paint');
    const wheels = ['Wheel_FL', 'Wheel_FR', 'Wheel_RL', 'Wheel_RR'].map((n) => model.getObjectByName(n)).filter(Boolean);
    const turret = model.getObjectByName('Turret') || new THREE.Group();
    turret.visible = false;
    const tip = glowSprite(0xff3b3b, 1.2, 1, 2.5); tip.position.set(0, 0.12, 1.65); turret.add(tip);
    const bci = glowSprite(0xff4fd8, 1.6, 0, 2.5); bci.position.set(0, 1.9, -0.75); g.add(bci);
    const ex1 = glowSprite(0xffa040, 1.2, 1, 2.5); ex1.position.set(-0.32, 0.82, -2.4); g.add(ex1);
    const ex2 = glowSprite(0xffa040, 1.2, 1, 2.5); ex2.position.set(0.32, 0.82, -2.4); g.add(ex2);
    // guardian orbs: Fable (gold) and Astra (cyan)
    const fable = glowSprite(0xffb347, 1.5, 1, 2.5); const astra = glowSprite(0x61e8ff, 1.5, 1, 2.5);
    fable.add(glowSprite(0xffffff, 0.5, 1, 3)); astra.add(glowSprite(0xffffff, 0.5, 1, 3));
    g.add(fable); g.add(astra);
    const shield = new THREE.Mesh(new THREE.IcosahedronGeometry(3.1, 2), new THREE.MeshBasicMaterial({ color: new THREE.Color(0x61e8ff).multiplyScalar(2), transparent: true, opacity: 0.18, blending: THREE.AdditiveBlending, depthWrite: false, wireframe: true }));
    shield.position.y = 1; shield.visible = false; g.add(shield);
    const label = labelSprite(name, { color: '#' + col.getHexString(), screen: 0.04 });
    label.position.y = 3.6; g.add(label);
    return { g, wheels, ex: [ex1, ex2], bci, turret, tip, orbs: [fable, astra], shield, label, body };
  },
  saucer(color, name, species) {
    const g = new THREE.Group();
    const model = recolor(asset('saucers', species === 'zeta' ? 'SaucerZeta' : 'SaucerNibiru'), {
      Neon: { color, emissive: color, k: 5 },
      Engine: { color, emissive: color, k: 6 },
    });
    model.traverse((m) => { if (m.isMesh && m.material.name.startsWith('Glass')) { m.material = m.material.clone(); m.material.transparent = true; m.material.opacity = 0.35; m.material.depthWrite = false; m.castShadow = false; m.renderOrder = 2; } });
    g.add(model);
    const body = findMat(model, 'Hull');
    const lights = [];
    for (let i = 0; i < 8; i++) {
      const a = (i / 8) * TAU;
      const l = glowSprite(color, 0.9, 1, 2.5); l.position.set(Math.cos(a) * 2.45, 1.12, Math.sin(a) * 2.45); g.add(l); lights.push(l);
    }
    const under = glowSprite(color, 5, 0.16, 1.2); under.position.y = 0.4; g.add(under);
    const beam = new THREE.Mesh(new THREE.CylinderGeometry(0.6, 1.6, 1.0, 16, 1, true), glowMat(color, 0.1, 1.5)); beam.position.y = 0.3; g.add(beam);
    const label = labelSprite(name, { color: '#' + new THREE.Color(color).getHexString(), screen: 0.034 });
    label.position.y = 3.4; g.add(label);
    return { g, lights, ex: [], under, label, beam, body, wheels: [] };
  },
};

// ------------------------------------------------------------ cars
class Car {
  constructor(o) {
    Object.assign(this, {
      name: o.name, team: o.team, color: o.color, local: -1, ai: true,
      s: 0, d: 0, h: 0, vh: 0, v: 0, psi: 0, lap: -1, finished: false, finishTime: 0, finishOrder: 0,
      item: null, itemCount: 0, roulette: 0, weapon: null, ammo: 0, fireCd: 0, bci: 0, neuro: 0,
      boostT: 0, boostK: 1, neuroT: 0, spinT: 0, spinA: 0, invulnT: 0, shieldT: 0, stallT: 0, falling: false,
      drift: 0, driftCharge: 0, driftHop: 0, airborne: false, padCd: 0, wallCd: 0, hack: null, aiHackT: 0,
      guardCd: rand(2, 6), skill: o.skill || 1, lane: o.lane || 0, aiItemDelay: rand(1, 3), place: 0,
      stats: { hits: 0, hacks: 0, hacksBeaten: 0, chips: 0, crates: 0, kills: 0, falls: 0 },
      disabledT: 0, ghostT: 0, lastLapT: 0,
    });
    this.isHuman = o.team === 'human';
    this.m = this.isHuman ? CarMeshes.kart(o.color, o.name) : CarMeshes.saucer(o.color, o.name, o.team === 'zeta' ? 'zeta' : 'reptile');
    this.pl = Track.newPlace();
    this.fwd = new V3(); this.up = new V3(0, 1, 0); this.pos = new V3();
    this.quat = new THREE.Quaternion();
  }
  get progress() { return this.lap * Track.L + this.s; }
  get controllable() { return this.spinT <= 0 && this.stallT <= 0 && this.disabledT <= 0 && !this.falling; }
  boost(t, k = 1.38) {
    this.boostT = Math.max(this.boostT, t); this.boostK = Math.max(k, this.boostT > t ? this.boostK : k);
    if (this.net) Net.toCar(this, ['boost', t, k]); // an online guest drives this kart on their machine
  }
  hit(dur = 1.1, o = {}) {
    if (this.invulnT > 0 || this.finished || this.disabledT > 0) return false;
    if (this.shieldT > 0) { Game.fx.shieldBlock(this); return false; }
    this.spinT = Math.max(this.spinT, dur);
    this.invulnT = dur + 0.5;
    this.v *= o.keep !== undefined ? o.keep : 0.45;
    if (o.launch) { this.vh = o.launch; this.airborne = true; }
    this.drift = 0; this.driftCharge = 0;
    this.stats.hits++;
    Game.sfx(this, 'spin');
    if (this.net) Net.toCar(this, ['hit', dur, o.keep !== undefined ? o.keep : 0.45, o.launch || 0]);
    return true;
  }

  update(dt, c) {
    const T = Track;
    if (this.finished) { this.v = damp(this.v, 0, 1, dt); }
    let gas = c.gas, brake = c.brake, steer = c.steer;
    if (!this.controllable || this.finished) { gas = 0; brake = 0; steer = 0; }
    this.tick(dt);
    if (this.spinT > 0) this.spinA += dt * 14; else this.spinA = damp(this.spinA, Math.round(this.spinA / TAU) * TAU, 10, dt);

    const g = T.gravity(this.s);
    const heavy = T.heavyF(this.s);
    let vmax = 60 * this.skill * (1 + 0.045 * this.bci) * (1 - 0.2 * heavy);
    if (this.boostT > 0) vmax *= this.boostK;
    if (this.neuroT > 0) vmax *= 1.32;
    if (this.hack || this.aiHackT > 0) vmax *= 0.55;
    const acc = 34 * (1 + 0.08 * this.bci) * (1 - 0.3 * heavy);
    if (gas > 0 && this.v < vmax) this.v += acc * gas * (1 - Math.max(0, this.v) / vmax * 0.85) * dt + (this.boostT > 0 ? 50 * dt : 0);
    if (this.v > vmax) this.v = damp(this.v, vmax, this.boostT > 0 ? 6 : 1.6, dt);
    if (brake > 0) this.v -= (this.v > 0 ? 55 : 22) * dt;
    if (!gas && !brake) this.v = damp(this.v, 0, 0.35, dt);
    this.v = clamp(this.v, -14, 140);
    if (this.disabledT > 0) this.v = 0;

    // drifting: hop, then hold to charge a mini-turbo
    if (c.driftPressed && !this.airborne && this.controllable && this.v > 20) { this.vh = 5.5 * Math.sqrt(1 / g); this.driftHop = 1; }
    if (this.drift === 0 && c.drift && Math.abs(steer) > 0.3 && this.v > 25 && this.controllable) { this.drift = Math.sign(steer); this.driftCharge = 0; }
    if (this.drift !== 0) {
      if (!c.drift || this.v < 18 || !this.controllable) {
        const lvl = this.driftCharge > 2.1 ? 3 : this.driftCharge > 1.3 ? 2 : this.driftCharge > 0.65 ? 1 : 0;
        if (lvl) { this.boost(0.35 + lvl * 0.35, 1.25 + lvl * 0.06); Game.sfx(this, 'boost'); }
        this.drift = 0; this.driftCharge = 0;
      } else {
        this.driftCharge += dt * (Math.sign(steer) === this.drift ? 1.25 : 0.6);
      }
    }
    // steering
    const grip = this.airborne ? 0.4 : 1;
    const speedK = clamp(Math.abs(this.v) / 20, 0, 1);
    let target = steer * (this.drift ? 0.62 : 0.5);
    if (this.drift) target = this.drift * 0.42 + steer * 0.3;
    this.psi = damp(this.psi, target * grip, this.drift ? 3.2 : 4.5, dt);
    this.psi = clamp(this.psi, -0.85, 0.85);

    // lateral & longitudinal motion in track space
    const b = T.tubeB(this.s);
    const fr = T.frame(this.s);
    const centr = this.airborne ? 0 : -fr.k * this.v * Math.abs(this.v) * 0.42 * (1 - b) * (this.drift ? 0.55 : 1);
    const latV = this.v * Math.sin(this.psi) * speedK + centr;
    this.d += latV * dt;
    this.s += this.v * Math.cos(this.psi) * dt;
    // the tube: gravity returns near the ends and pulls you back to the floor
    if (b > 0.999) {
      const pull = T.tubePull(this.s);
      const th = T.wrapD(this.d) / T.R;
      if (pull > 0) this.d -= (th / Math.PI) * pull * dt * 1.4;
    }
    // lap accounting
    if (this.s >= T.L) { this.s -= T.L; this.lap++; Game.onLap(this); }
    else if (this.s < 0) { this.s += T.L; this.lap--; }

    // vertical
    const onGap = T.isGap(this.s);
    if (this.falling) {
      this.vh -= 30 * dt; this.h += this.vh * dt;
      if (this.h < -70) Game.respawn(this);
    } else if (this.h > 0 || this.vh > 0) {
      this.airborne = true;
      this.vh -= 30 * g * dt;
      this.h += this.vh * dt;
      if (this.h <= 0) {
        if (onGap) { this.falling = true; this.stats.falls++; }
        else { if (this.vh < -16) Game.sfx(this, 'bump'); this.h = 0; this.vh = 0; this.airborne = false; this.driftHop = 0; }
      }
    } else if (onGap) { this.falling = true; this.vh = -2; this.stats.falls++; }
    else { this.airborne = false; this.h = 0; }

    // walls
    if (T.isWrap(this.s)) this.d = T.wrapD(this.d);
    else {
      const hw = T.hw(this.s) - 1.3;
      if (Math.abs(this.d) > hw && !this.falling) {
        const into = Math.abs(latV);
        this.d = Math.sign(this.d) * hw;
        if (into > 4 && this.wallCd <= 0) {
          this.v *= 1 - 0.22 * Math.min(1, into / 30);
          this.wallCd = 0.25;
          this.psi *= -0.3;
          Game.fx.sparks(this, Math.sign(this.d));
          Game.sfx(this, 'bump');
        }
      }
    }
  }
  // timers and the neuro meter (also run by the host for karts that online guests drive)
  tick(dt) {
    this.spinT -= dt; this.stallT -= dt; this.invulnT -= dt; this.shieldT -= dt; this.padCd -= dt; this.wallCd -= dt;
    this.fireCd -= dt; this.guardCd -= dt; this.disabledT -= dt;
    if (this.boostT > 0) { this.boostT -= dt; if (this.boostT <= 0) this.boostK = 1; }
    if (this.neuroT > 0) this.neuroT -= dt;
    if (this.bci > 0 && this.neuroT <= 0) this.neuro = Math.min(1, this.neuro + dt * 0.035 * this.bci);
  }

  syncMesh(dt, time) {
    const T = Track, pl = this.pl;
    T.place(this.s, this.d, this.h + (this.isHuman ? 0 : 0.25 + Math.sin(time * 3 + this.lane) * 0.15), pl);
    this.pos.copy(pl.p);
    this.up.copy(pl.up);
    const fwd = this.fwd.copy(pl.fwd).multiplyScalar(Math.cos(this.psi)).addScaledVector(pl.side, Math.sin(this.psi)).normalize();
    const x = new V3().crossVectors(pl.up, fwd).normalize();
    const y = new V3().crossVectors(fwd, x).normalize();
    const m4 = new THREE.Matrix4().makeBasis(x, y, fwd);
    this.quat.setFromRotationMatrix(m4);
    const g = this.m.g;
    g.position.copy(pl.p);
    g.quaternion.copy(this.quat);
    // visual extras: spin, lean, pitch
    const lean = new THREE.Quaternion().setFromEuler(new THREE.Euler(clamp(-this.vh * 0.02, -0.4, 0.4), this.spinA + (this.drift ? this.drift * 0.35 : 0), -this.psi * 0.3 - (this.drift ? this.drift * 0.12 : 0)));
    g.quaternion.multiply(lean);
    g.visible = !(this.disabledT > 0 && Math.floor(time * 10) % 2) && !(this.finished && this.finishFade <= 0);
    if (this.finished) { this.finishFade = (this.finishFade ?? 1) - dt; g.scale.setScalar(Math.max(0.01, this.finishFade)); }
    else g.scale.setScalar(1);
    const sp = Math.abs(this.v);
    for (const w of this.m.wheels) w.rotation.x += this.v * dt * 1.9;
    for (const e of this.m.ex) {
      const k = this.boostT > 0 || this.neuroT > 0 ? 2.4 : 0.45 + sp / 110;
      e.scale.set(k, k, 1);
      e.material.color.setHex(this.neuroT > 0 ? 0xff4fd8 : this.boostT > 0 ? 0x60c8ff : 0xffa040);
    }
    if (this.isHuman) {
      this.m.bci.material.opacity = this.bci ? 0.5 + 0.5 * Math.sin(time * 6) * 0.3 + this.bci * 0.15 : 0;
      this.m.bci.scale.setScalar(1 + this.bci * 0.5);
      this.m.turret.visible = !!this.weapon;
      if (this.weapon) this.m.tip.material.color.setHex(WEAPONS[this.weapon].color);
      this.m.shield.visible = this.shieldT > 0;
      if (this.shieldT > 0) { this.m.shield.rotation.y += dt * 2; this.m.shield.material.opacity = this.shieldT < 1.5 && Math.floor(time * 8) % 2 ? 0.05 : 0.22; }
      const [fa, as] = this.m.orbs;
      const a = time * 2.4 + this.lane;
      fa.position.set(Math.cos(a) * 2.6, 2.4 + Math.sin(a * 2) * 0.3, Math.sin(a) * 2.6);
      as.position.set(Math.cos(a + Math.PI) * 2.6, 2.4 + Math.sin(a * 2 + 1) * 0.3, Math.sin(a + Math.PI) * 2.6);
      const hacked = this.hack || this.aiHackT > 0;
      if (this.m.body) this.m.body.emissive.setHex(hacked && Math.floor(time * 12) % 2 ? 0xaa0018 : 0x000000);
    } else {
      this.m.lights.forEach((l, i) => { l.material.opacity = 0.4 + 0.6 * ((Math.floor(time * 8) + i) % 4 === 0 ? 1 : 0.2); });
    }
    // drift sparks / boost trail
    if (this.drift && !this.airborne) {
      const lvl = this.driftCharge > 2.1 ? 0xc060ff : this.driftCharge > 1.3 ? 0xff8a20 : this.driftCharge > 0.65 ? 0x40b0ff : 0xffffff;
      for (const sx of [-1.2, 1.2]) {
        const p = this.pos.clone().addScaledVector(x, sx).addScaledVector(fwd, -1.6).addScaledVector(this.up, 0.2);
        Particles.spawn(p, this.up.clone().multiplyScalar(rand(2, 6)).addScaledVector(x, rand(-3, 3)), lvl, 0.9, 0.25, { grav: 10 });
      }
    }
    if ((this.boostT > 0 || this.neuroT > 0) && Math.random() < 0.8) {
      const p = this.pos.clone().addScaledVector(fwd, -2.3).addScaledVector(this.up, 0.6);
      Particles.spawn(p, fwd.clone().multiplyScalar(-10).add(new V3(rand(-2, 2), rand(-2, 2), rand(-2, 2))), this.neuroT > 0 ? 0xff4fd8 : 0x60c8ff, 0.9, 0.3, { grow: -2 });
    }
  }
}

// ------------------------------------------------------------ AI driving
function aiControl(car, dt, race) {
  const T = Track;
  const c = { gas: 1, brake: 0, steer: 0, drift: false, driftPressed: false, pressed: {} };
  let targetD = car.lane;
  const look = car.s + 30 + car.v * 0.4;
  // go for item boxes if empty-handed
  if (!car.item && !car.roulette) {
    for (const row of race.boxRows) {
      const ds = T.sDiff(row.s, car.s);
      if (ds > 8 && ds < 90) {
        let best = null, bd = 1e9;
        for (const b of row.boxes) if (b.active && Math.abs(T.dDiff(b.d, car.d, row.s)) < bd && Math.abs(b.d) < T.HW) { bd = Math.abs(T.dDiff(b.d, car.d, row.s)); best = b; }
        if (best) targetD = best.d;
        break;
      }
    }
  }
  if (car.isHuman && car.bci < 3) {
    for (const ch of race.chips) {
      const ds = T.sDiff(ch.s, car.s);
      if (ch.active && ds > 5 && ds < 70 && Math.abs(ch.d) < T.HW) { targetD = ch.d; break; }
    }
  }
  // avoid hazards
  for (const hz of race.hazards) {
    const ds = T.sDiff(hz.s, car.s);
    if (ds > 0 && ds < 45 && Math.abs(T.dDiff(hz.d, targetD, hz.s)) < 4) targetD = hz.d + (hz.d > 0 ? -6 : 6);
  }
  // tube: stay low
  if (T.tubeB(look) > 0.5 && Math.abs(targetD) > 8) targetD = clamp(targetD, -8, 8);
  if (!T.isWrap(car.s)) targetD = clamp(targetD, -T.hw(car.s) + 2.5, T.hw(car.s) - 2.5);
  const fr = T.frame(look);
  const err = T.dDiff(targetD, car.d, car.s);
  const vlat = clamp(err * 1.6, -26, 26) + fr.k * car.v * Math.abs(car.v) * 0.42;
  const want = Math.asin(clamp(vlat / Math.max(12, car.v), -0.55, 0.55));
  c.steer = clamp(want / 0.5, -1, 1);
  return c;
}

Object.assign(G, { Particles, ITEMS, WEAPONS, rollItem, CarMeshes, Car, aiControl });

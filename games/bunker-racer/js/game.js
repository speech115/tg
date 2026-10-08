'use strict';
// Race orchestration: cars, OMEGA (hacks, drones, wave), McAfee, items, cameras, split-screen, ending.
const HUMANS = [
  { name: 'STEVE', color: 0xff7a1a },
  { name: 'SERGEY', color: 0xff4f8b },
  { name: 'DANEL', color: 0x35e0ff },
];
const ZETA = { color: 0xb45cff, names: ['ZORG', 'GLIP', 'XUL'], label: 'ZETA RETICULI' };
const NIBIRU = { color: 0xd4ff3a, names: ['SSARK', 'KREX', 'VAZZL'], label: 'NIBIRU REPTILIANS' };
const TEAM_NAMES = { human: 'HUMANS', zeta: ZETA.label, nibiru: NIBIRU.label };
const DIFF = [{ skill: 0.86, omega: 0.75, name: 'EASY' }, { skill: 0.93, omega: 1, name: 'NORMAL' }, { skill: 1.0, omega: 1.3, name: 'INSANE' }];

const Game = {
  state: 'boot', time: 0, shake: 0,
  cfg: { players: 1, laps: 3, diff: 1 },

  init() {
    try { this.boot(); } catch (err) { console.error(err); if (window.showFatal) window.showFatal(err); }
  },
  boot() {
    const canvas = document.getElementById('c');
    let renderer;
    try {
      renderer = new THREE.WebGLRenderer({ canvas, antialias: false, powerPreference: 'high-performance' });
    } catch (err) {
      throw new Error('WebGL is not available in this browser. Turn on hardware acceleration or try Chrome. (' + err.message + ')');
    }
    this.renderer = renderer;
    // Older GPUs / Safari builds: fall back from HDR + MSAA render targets when unsupported.
    const caps = renderer.capabilities, ext = renderer.extensions;
    Post.maxSamples = caps.isWebGL2 ? Math.min(4, caps.maxSamples || 4) : 0;
    Post.hdr = caps.isWebGL2 ? (ext.has('EXT_color_buffer_float') || ext.has('EXT_color_buffer_half_float')) : ext.has('EXT_color_buffer_half_float');
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.5));
    this.renderer.toneMapping = THREE.ACESFilmicToneMapping;
    this.renderer.toneMappingExposure = 1.05;
    this.renderer.shadowMap.enabled = true;
    this.renderer.shadowMap.type = THREE.PCFSoftShadowMap;
    Post.init(this.renderer);
    this.dpr = Math.min(window.devicePixelRatio || 1, 1.5);
    this.renderer.autoClear = false;
    this.scene = new THREE.Scene();
    Track.build();
    Track.buildMeshes(this.scene);
    World.build(this.scene, this.renderer);
    Particles.init(this.scene);
    this.shared = this.sharedAssets();
    this.cams = [0, 1, 2].map(() => new THREE.PerspectiveCamera(72, 1, 0.3, 9000));
    this.camState = [0, 1, 2].map(() => ({ offS: -9, offD: 0, up: new V3(0, 1, 0), fov: 72, look: new V3() }));
    this.cineCam = new THREE.PerspectiveCamera(55, 1, 0.5, 9000);
    this.cine = { t: 0, shot: null };
    this.pl = Track.newPlace(); this.pl2 = Track.newPlace();
    Input.init();
    HUD.init();
    G.state = 'menu';
    addEventListener('resize', () => this.resize());
    this.resize();
    this.newRace({ players: 0, laps: 2, diff: 1, demo: true });
    this.last = performance.now();
    const loop = (now) => {
      const dt = Math.min(0.05, (now - this.last) / 1000); this.last = now;
      this.frame(dt);
      requestAnimationFrame(loop);
    };
    requestAnimationFrame(loop);
    window.GAME_READY = true;
  },

  resize() {
    const w = innerWidth, h = innerHeight;
    this.renderer.setSize(w, h, false);
    this.W = w; this.H = h;
  },

  applyQuality(q, players) {
    const r = this.renderer;
    const pr = q ? (players >= 2 ? Math.min(this.dpr, 1) : this.dpr) : Math.min(this.dpr, players >= 2 ? 0.7 : 0.85);
    r.setPixelRatio(pr);
    if (this.quality !== q) {
      this.quality = q;
      r.shadowMap.enabled = q > 0;
      World.sun.castShadow = q > 0;
      Post.samples = q ? Post.maxSamples : 0;
      Post.comps = [];
      this.scene.traverse((o) => { if (o.material) (Array.isArray(o.material) ? o.material : [o.material]).forEach((m) => { m.needsUpdate = true; }); });
    }
  },
  sharedAssets() {
    const boxTex = canvasTex(128, 128, (g, w, h) => {
      g.clearRect(0, 0, w, h);
      g.fillStyle = '#fff'; g.font = '900 84px "Unbounded", sans-serif'; g.textAlign = 'center'; g.textBaseline = 'middle';
      g.fillText('?', w / 2, h / 2 + 6);
    });
    const crateTex = canvasTex(128, 128, (g, w, h) => {
      g.fillStyle = '#3d4a2a'; g.fillRect(0, 0, w, h);
      g.strokeStyle = '#26301a'; g.lineWidth = 8; g.strokeRect(4, 4, w - 8, h - 8);
      g.beginPath(); g.moveTo(8, 8); g.lineTo(w - 8, h - 8); g.stroke();
      g.fillStyle = '#ffd000'; g.font = '900 26px "Unbounded", sans-serif'; g.textAlign = 'center';
      g.fillText('McAFEE', w / 2, 52); g.font = '700 18px "JetBrains Mono", monospace'; g.fillText('WEAPONS', w / 2, 84);
    });
    const waveMat = new THREE.ShaderMaterial({
      uniforms: { t: { value: 0 } }, transparent: true, depthWrite: false, side: THREE.DoubleSide, blending: THREE.AdditiveBlending,
      vertexShader: 'varying vec2 vUv; void main(){ vUv=uv; gl_Position = projectionMatrix*modelViewMatrix*vec4(position,1.0); }',
      fragmentShader: `varying vec2 vUv; uniform float t;
        float h(vec2 p){ return fract(sin(dot(p, vec2(12.9898,78.233)))*43758.5453); }
        void main(){ vec2 g = floor(vUv*vec2(40.0,24.0) + vec2(0.0, floor(t*12.0)));
          float n = h(g + floor(t*8.0)); float bars = step(0.55, h(vec2(floor(vUv.y*30.0), floor(t*10.0))));
          float edge = smoothstep(0.0,0.15,vUv.x)*smoothstep(1.0,0.85,vUv.x)*smoothstep(0.0,0.1,vUv.y)*smoothstep(1.0,0.7,vUv.y);
          float a = (0.25 + 0.5*n*bars + 0.25*sin(vUv.y*120.0 - t*30.0)) * edge;
          gl_FragColor = vec4(vec3(1.0,0.12+0.2*n,0.2)*1.3, a*0.85); }`,
    });
    return {
      boxGeo: new THREE.BoxGeometry(2.4, 2.4, 2.4),
      boxMat: new THREE.ShaderMaterial({
        uniforms: { t: { value: 0 } }, transparent: true, depthWrite: false, blending: THREE.AdditiveBlending, side: THREE.DoubleSide,
        vertexShader: 'varying vec3 vP; varying vec3 vN; varying vec3 vV; void main(){ vP = position; vec4 wp = modelMatrix * vec4(position,1.0); vN = normalize(mat3(modelMatrix) * normal); vV = normalize(cameraPosition - wp.xyz); gl_Position = projectionMatrix * viewMatrix * wp; }',
        fragmentShader: `uniform float t; varying vec3 vP; varying vec3 vN; varying vec3 vV;
          vec3 hue(float h){ return clamp(abs(fract(h + vec3(0.0, 0.33, 0.67)) * 6.0 - 3.0) - 1.0, 0.0, 1.0); }
          void main(){ vec3 a = abs(vP) / 1.2; float m1 = max(a.x, max(a.y, a.z)); float m2 = a.x + a.y + a.z - m1 - min(a.x, min(a.y, a.z));
            float edge = smoothstep(0.86, 0.97, m2);
            float f = pow(1.0 - abs(dot(normalize(vN), normalize(vV))), 2.0);
            vec3 c = hue(dot(vP, vec3(0.3, 0.2, 0.25)) + t * 0.25);
            gl_FragColor = vec4(c * (edge * 3.5 + f * 0.6 + 0.05), 1.0); }`,
      }),
      qTex: boxTex,
      crateMat: new THREE.MeshLambertMaterial({ map: crateTex, emissive: 0x222200 }),
      waveMat,
      beamGeo: new THREE.BoxGeometry(1, 1, 1).translate(0, 0, 0.5),
    };
  },

  // --------------------------------------------------------------- race setup
  add(obj) { this.scene.add(obj); this.race.objects.push(obj); return obj; },

  newRace(cfg) {
    if (this.race) for (const o of this.race.objects) this.scene.remove(o);
    Particles.clear();
    const T = Track;
    const R = this.race = {
      cfg, objects: [], cars: [], boxRows: [], chips: [], hazards: [], proj: [], drones: [], crates: [], beams: [],
      t: 0, countdown: 4.2, finishCount: 0, humansDone: 0, ended: false, endTimer: -1, firstLocalDoneT: -1,
      omega: { hackCd: rand(13, 17), droneCd: rand(8, 12), aim: null, stun: 0, sayCd: 0 },
      wave: { p: -1e9, active: false, mesh: null },
      mc: { state: 'away', cd: rand(7, 11), s: 0, d: 0, h: 30, target: null, mesh: null, outT: 0 },
      local: [], diff: DIFF[cfg.diff] || DIFF[1], ambientCd: 8, beatenHumans: 0,
    };
    // grid
    const order = [['zeta', 0], ['nibiru', 0], ['zeta', 1], ['nibiru', 1], ['human', 0], ['zeta', 2], ['human', 1], ['nibiru', 2], ['human', 2]];
    order.forEach(([team, i], k) => {
      let o;
      if (team === 'human') o = { name: HUMANS[i].name, color: HUMANS[i].color, team, skill: 0.95, lane: [-5, 0, 5][i] };
      else {
        const t = team === 'zeta' ? ZETA : NIBIRU;
        o = { name: t.names[i], color: t.color, team, skill: R.diff.skill + rand(-0.02, 0.02), lane: rand(-7, 7) };
      }
      const car = new Car(o);
      car.baseSkill = o.skill;
      const row = Math.floor(k / 3), col = k % 3;
      car.s = T.L - 14 - row * 10 - (col === 1 ? 4 : 0);
      car.d = [-7, 0, 7][col];
      car.lap = -1;
      car.humanIdx = team === 'human' ? i : -1;
      this.add(car.m.g);
      R.cars.push(car);
    });
    const humans = R.cars.filter((c) => c.isHuman).sort((a, b) => a.humanIdx - b.humanIdx);
    R.humans = humans;
    for (let i = 0; i < cfg.players; i++) { humans[i].local = i; humans[i].ai = false; humans[i].skill = 1; R.local.push(humans[i]); }
    for (const c of R.cars) c.m.label.visible = cfg.players !== 1 || c.local !== 0;
    // pickups
    for (const row of T.itemRows) {
      const r = { s: row.s, boxes: [] };
      for (const d of row.ds) {
        const m = new THREE.Mesh(this.shared.boxGeo, this.shared.boxMat);
        const q = new THREE.Sprite(new THREE.SpriteMaterial({ map: this.shared.qTex, color: new THREE.Color(2.2, 1.7, 0.8), transparent: true, depthWrite: false }));
        q.scale.set(1.6, 1.6, 1); m.add(q);
        const glow = glowSprite(0xffb000, 4.5, 0.3); m.add(glow);
        this.add(m);
        r.boxes.push({ s: row.s, d, active: true, t: 0, m, spin: rand(0, 6) });
      }
      R.boxRows.push(r);
    }
    for (const sp of T.chipSpots) R.chips.push({ ...sp, active: true, t: 0, m: this.add(this.chipMesh()) });
    // wave
    R.wave.mesh = this.add(new THREE.Mesh(new THREE.PlaneGeometry(70, 46), this.shared.waveMat));
    R.wave.mesh.visible = false;
    R.mc.mesh = this.add(this.mcafeeMesh()); R.mc.mesh.visible = false;
    World.setPrinterStatus(0, 3);
    World.portalG.charge = 0;
    World.omegaG.stun = 0;
    Sound.setEngines(cfg.players);
    this.applyQuality(cfg.gfx ?? (HUD.menuCfg ? HUD.menuCfg.gfx : 1) ?? 1, cfg.players);
    this.resize();
    Sound.intensity = 0;
    this.state = cfg.demo ? 'demo' : 'countdown';
    HUD.setup(cfg.players, cfg.demo);
    if (!cfg.demo) {
      Sound.startMusic();
      HUD.say('musk', pick(['My bunker, my rules. The time machine is in the basement. All three of you need to get there.', 'I put this bunker in orbit. Neural chips are on the track. Grab them.']));
    }
  },

  chipMesh() {
    const g = new THREE.Group();
    const brain = asset('props', 'Brain');
    brain.scale.setScalar(1.15);
    g.add(brain);
    g.add(glowSprite(0xff4fd8, 6, 0.7));
    const lab = labelSprite('BCI', { color: '#ff7ad9', scale: 0.6 }); lab.position.y = 2.2; g.add(lab);
    return g;
  },
  mcafeeMesh() {
    const g = new THREE.Group();
    const skiff = asset('props', 'Skiff');
    skiff.rotation.y = Math.PI;
    g.add(skiff);
    const p = World.character('McAfee');
    p.scale.setScalar(1.4); p.position.set(0, 0.3, 0.4); g.add(p);
    g.userData.person = p;
    for (const x of [-1.6, 1.6]) { const f = glowSprite(0xffa040, 3.5, 1, 3); f.position.set(x, -0.1, 3.9); g.add(f); }
    const lab = labelSprite('JOHN McAFEE', { color: '#ffd000', scale: 0.9 }); lab.position.y = 5.2; g.add(lab);
    return g;
  },
  droneMesh() {
    const g = new THREE.Group();
    g.add(asset('props', 'Drone'));
    const eye = glowSprite(0xff1030, 3.5, 1, 2.5); eye.position.z = 0.9; g.add(eye);
    return g;
  },

  // --------------------------------------------------------------- main frame
  frame(dt) {
    this.time += dt;
    Sound.tick();
    const R = this.race;
    if (this.paused) { this.render(0); return; }
    if (this.state === 'demo' || this.state === 'countdown' || this.state === 'race') {
      const steps = 2;
      for (let i = 0; i < steps; i++) this.update(dt / steps);
    } else if (this.state === 'ending') {
      this.updateEnding(dt);
    }
    // visuals
    for (const c of R.cars) c.syncMesh(dt, this.time);
    this.syncPickups(dt);
    Particles.update(dt);
    World.omegaG.stun = R.omega.stun;
    World.update(dt, this.time);
    Track.update(this.time);
    this.shared.waveMat.uniforms.t.value = this.time;
    this.shared.boxMat.uniforms.t.value = this.time;
    this.shake = Math.max(0, this.shake - dt * 1.8);
    this.render(dt);
    HUD.update(dt, R, this);
  },

  readControls(car, dt) {
    const R = this.race;
    if (car.local >= 0 && this.state !== 'demo') {
      const st = Input.read(car.local, R.cfg.players);
      st.driftPressed = st.pressed.drift;
      if (car.hack) {
        this.updateHack(car, st, dt);
        const ai = aiControl(car, dt, R);
        return ai;
      }
      return st;
    }
    const c = aiControl(car, dt, R);
    return c;
  },

  update(dt) {
    const R = this.race, T = Track;
    if (this.state === 'countdown') {
      const before = R.countdown;
      R.countdown -= dt;
      for (const n of [3, 2, 1]) if (before > n && R.countdown <= n) { Sound.play('beep'); HUD.countdown(String(n)); }
      for (const car of R.local) {
        const st = Input.read(car.local, R.cfg.players);
        if (st.gas && car.startGas === undefined) car.startGas = R.countdown;
        if (!st.gas) car.startGas = undefined;
      }
      if (R.countdown <= 0) {
        this.state = 'race';
        Sound.play('go'); HUD.countdown('GO!');
        HUD.say('musk', 'Three... two... one... GO! Save the past!');
        for (const car of R.cars) {
          const good = car.local >= 0 ? car.startGas !== undefined && car.startGas < 1.0 : Math.random() < 0.35;
          if (good) { car.boost(1.3, 1.45); if (car.local >= 0) { HUD.msg(car.local, 'ROCKET START!', '#ffb000'); Sound.play('boost'); } }
        }
      }
      for (const car of R.cars) { car.v = 0; car.update(0, { gas: 0, brake: 0, steer: 0 }); }
      return;
    }
    R.t += dt;
    if (this.state === 'demo' && R.cars.every((c) => c.finished)) { this.newRace({ players: 0, laps: 2, diff: 1, demo: true }); return; }

    // cars
    for (const car of R.cars) {
      if (car.finished) { car.update(dt, { gas: 0, brake: 0, steer: 0 }); continue; }
      const c = this.readControls(car, dt);
      // items & weapons
      if (car.roulette > 0) {
        car.roulette -= dt;
        if (car.local >= 0 && Math.random() < 0.3) Sound.play('roulette');
        if (car.roulette <= 0) { car.item = rollItem(car.place - 1, R.cars.length, car.isHuman); car.itemCount = car.item === 'nitro3' ? 3 : 1; car.aiItemDelay = rand(0.8, 3.5); if (car.local >= 0) Sound.play('item'); }
      }
      if (car.local >= 0 && !car.hack && this.state === 'race') {
        if (c.pressed && c.pressed.item && car.item) this.useItem(car);
        if (c.fire) this.fire(car, c.pressed && c.pressed.fire);
      } else if (car.ai) this.aiItems(car, dt);
      if (car.aiHackT > 0) car.aiHackT -= dt;
      if (!car.isHuman && R.leadHuman) {
        const gap = car.progress - R.leadHuman.progress;
        car.skill = car.baseSkill * (1 - clamp(gap / 450, -0.12, 0.12));
      }
      car.update(dt, c);
    }
    this.collideCars();
    this.pickups(dt);
    this.updateProjectiles(dt);
    this.updateHazards(dt);
    if (this.state === 'race') {
      this.updateOmega(dt);
      this.updateDrones(dt);
      this.updateWave(dt);
      this.updateMcAfee(dt);
      this.updateCrates(dt);
      this.ambientChatter(dt);
    }
    this.updateBeams(dt);
    // ranking
    const sorted = R.cars.slice().sort((a, b) => {
      if (a.finished && b.finished) return a.finishOrder - b.finishOrder;
      if (a.finished) return -1; if (b.finished) return 1;
      return b.progress - a.progress;
    });
    sorted.forEach((c, i) => { c.place = i + 1; });
    R.sorted = sorted;
    R.leadHuman = sorted.find((c) => c.isHuman && !c.finished) || null;
    // portal charge follows the leading human
    const maxLap = Math.max(...R.humans.map((h) => (h.finished ? R.cfg.laps : h.lap)));
    World.portalG.charge = clamp((maxLap + 1) / R.cfg.laps, 0, 1);
    // locals done -> Fable & Astra fetch the stragglers
    if (this.state === 'race' && R.local.length && R.local.every((c) => c.finished)) {
      if (R.firstLocalDoneT < 0) R.firstLocalDoneT = R.t;
      for (const h of R.humans) if (!h.finished) h.skill = 1.12;
      if (R.t - R.firstLocalDoneT > 22) {
        for (const h of R.humans) if (!h.finished) { HUD.say('fable', `Hold on, ${h.name}! Astra and I are teleporting you to the portal.`); this.finish(h); }
      }
    }
    if (R.endTimer >= 0) { R.endTimer -= dt; if (R.endTimer < 0 && this.state === 'race') this.startEnding(); }
  },

  collideCars() {
    const cars = this.race.cars, T = Track;
    for (let i = 0; i < cars.length; i++) for (let j = i + 1; j < cars.length; j++) {
      const a = cars[i], b = cars[j];
      if (a.finished || b.finished || a.falling || b.falling || a.disabledT > 0 || b.disabledT > 0) continue;
      const ds = T.sDiff(a.s, b.s);
      if (Math.abs(ds) > 3.6) continue;
      const dd = T.dDiff(a.d, b.d, a.s);
      if (Math.abs(dd) > 2.7 || Math.abs(a.h - b.h) > 2.5) continue;
      const push = (2.7 - Math.abs(dd)) / 2 + 0.05;
      const sg = dd === 0 ? (Math.random() < 0.5 ? -1 : 1) : Math.sign(dd);
      a.d += sg * push; b.d -= sg * push;
      if (Math.abs(dd) < 1.6) {
        const back = ds > 0 ? b : a, front = ds > 0 ? a : b;
        if (back.v > front.v) { const x = (back.v - front.v) * 0.5; back.v -= x; front.v += x * 0.6; }
      }
      if (a.local >= 0 || b.local >= 0) { if (Math.random() < 0.2) Sound.play('bump'); }
    }
  },

  // --------------------------------------------------------------- items & weapons
  useItem(car) {
    const R = this.race, item = car.item;
    if (!item) return;
    car.itemCount--;
    if (car.itemCount <= 0) car.item = null;
    const loud = car.local >= 0;
    switch (item) {
      case 'nitro': case 'nitro3':
        car.boost(1.3, 1.42); if (loud) Sound.play('boost'); break;
      case 'slime': {
        const m = new THREE.Mesh(new THREE.CircleGeometry(2.4, 20), glowMat(0x7dff5a, 0.75));
        this.add(m);
        R.hazards.push({ kind: 'slime', s: car.s - 4.5, d: car.d, life: 30, owner: car, grace: 0.8, m });
        if (loud) Sound.play('slime');
        break;
      }
      case 'rocket': {
        const target = this.carAhead(car);
        const m = World.rocket(0.42); this.add(m);
        R.proj.push({ kind: 'rocket', s: car.s + 3, d: car.d, h: 1.2, v: Math.max(car.v + 55, 95), owner: car, life: 7, target, m });
        Sound.play('rocket');
        if (car.isHuman && Math.random() < 0.5) HUD.say('musk', pick(['Rocket away. It might come back. Kidding.', 'Reusable? No. This one is single-use.']));
        break;
      }
      case 'gbomb': {
        const m = new THREE.Group();
        m.add(new THREE.Mesh(new THREE.SphereGeometry(0.9, 12, 8), new THREE.MeshLambertMaterial({ color: 0x20304a, emissive: 0x1050a0 })));
        m.add(glowSprite(0x58b4ff, 5));
        this.add(m);
        R.proj.push({ kind: 'gbomb', s: car.s + 3, d: car.d, h: 2, vh: 9, v: car.v + 35, owner: car, life: 3, m, fuse: -1 });
        if (loud) Sound.play('whoosh');
        break;
      }
      case 'shield':
        car.shieldT = 7; Sound.play('shield');
        if (car.isHuman) HUD.say(pick(['fable', 'astra']), pick(['Shield up. Astra and I are right here.', 'Fable, hold the dome with me!', 'Shield active. OMEGA shall not pass.']));
        break;
      case 'kill':
        this.killSwitch(car); break;
    }
  },
  carAhead(car) {
    const R = this.race; let best = null, bd = 1e9;
    for (const o of R.cars) {
      if (o === car || o.team === car.team || o.finished) continue;
      const ds = o.progress - car.progress;
      if (ds > 0 && ds < bd) { bd = ds; best = o; }
    }
    return best;
  },
  fire(car, pressed) {
    const R = this.race;
    if (car.weapon) {
      if (car.fireCd > 0) return;
      const W = WEAPONS[car.weapon];
      car.fireCd = W.rate; car.ammo--;
      if (car.weapon === 'laser') {
        const m = new THREE.Mesh(new THREE.BoxGeometry(0.22, 0.22, 3.2), glowMat(0xff3b3b, 1)); this.add(m);
        R.proj.push({ kind: 'laser', s: car.s + 2.5, d: car.d + (car.ammo % 2 ? 0.25 : -0.25), h: car.h + 1.2, v: car.v + 170, owner: car, life: 0.9, m });
        Sound.play('laser');
      } else if (car.weapon === 'rail') {
        const m = new THREE.Mesh(new THREE.BoxGeometry(0.5, 0.5, 7), glowMat(0x61e8ff, 1)); this.add(m);
        R.proj.push({ kind: 'rail', s: car.s + 3, d: car.d, h: car.h + 1.2, v: car.v + 260, owner: car, life: 0.8, m, pierce: true, hitSet: new Set() });
        Sound.play('rail'); this.shake = Math.max(this.shake, 0.3);
      } else {
        const m = World.rocket(0.22); this.add(m);
        R.proj.push({ kind: 'swarm', s: car.s + 2, d: car.d + rand(-1.5, 1.5), h: car.h + 1.6, v: car.v + 80, owner: car, life: 3, m, target: this.swarmTarget(car) });
        Sound.play('rocket');
      }
      if (car.ammo <= 0) { car.weapon = null; if (car.local >= 0) HUD.msg(car.local, 'OUT OF AMMO', '#7d849a'); }
    } else if (pressed && car.neuro >= 1) {
      car.neuro = 0; car.neuroT = 3.2;
      if (car.local >= 0) { Sound.play('boost'); Sound.play('chip'); HUD.msg(car.local, 'NEURO FOCUS!', '#ff4fd8'); }
    }
  },
  swarmTarget(car) {
    const R = this.race; let best = null, bd = 160;
    for (const o of R.cars) {
      if (o.team === 'human' || o.finished || o.disabledT > 0) continue;
      const ds = Track.sDiff(o.s, car.s);
      if (ds > 0 && ds < bd) { bd = ds; best = o; }
    }
    for (const dr of R.drones) {
      const ds = Track.sDiff(dr.s, car.s);
      if (ds > -10 && ds < bd) { bd = ds; best = dr; }
    }
    return best;
  },
  aiItems(car, dt) {
    const R = this.race;
    if (car.item) {
      car.aiItemDelay -= dt;
      if (car.aiItemDelay <= 0) {
        let use = false;
        const it = car.item;
        if (it === 'nitro' || it === 'nitro3' || it === 'shield') use = true;
        else if (it === 'rocket') use = (!!this.carAhead(car) && this.carAhead(car).progress - car.progress < 220) || car.aiItemDelay < -8;
        else if (it === 'slime') use = R.cars.some((o) => o.team !== car.team && car.progress - o.progress > 0 && car.progress - o.progress < 70) || car.aiItemDelay < -6;
        else if (it === 'gbomb') use = R.cars.some((o) => o.team !== car.team && Math.abs(o.progress - car.progress - 55) < 35) || car.aiItemDelay < -10;
        else if (it === 'kill') use = R.drones.length > 0 || car.aiHackT > 0 || car.place > 4;
        if (use) { this.useItem(car); car.aiItemDelay = rand(0.4, 1.5); }
      }
    }
    if (car.weapon && car.fireCd <= 0) {
      const tgt = this.swarmTarget(car);
      if (tgt && Track.sDiff(tgt.s, car.s) < 110 && Math.abs(Track.dDiff(tgt.d, car.d, car.s)) < 5) this.fire(car, true);
    }
    if (car.isHuman && car.neuro >= 1 && Math.abs(Track.frame(car.s).k) < 0.004) this.fire(car, true);
  },

  updateProjectiles(dt) {
    const R = this.race, T = Track, pl = this.pl;
    for (let i = R.proj.length - 1; i >= 0; i--) {
      const p = R.proj[i];
      p.life -= dt;
      let dead = p.life <= 0;
      if (p.kind === 'gbomb') {
        if (p.fuse < 0) {
          p.s += p.v * dt; p.vh -= 30 * T.gravity(p.s) * dt; p.h += p.vh * dt;
          if (p.h <= 0.8 && !T.isGap(p.s)) { p.h = 0.8; p.fuse = 0.35; p.v = 0; }
        } else {
          p.fuse -= dt;
          if (p.fuse <= 0) { this.gravityBlast(p); dead = true; }
        }
      } else {
        p.s += p.v * dt;
        const tg = p.target;
        if (tg && (p.kind === 'rocket' || p.kind === 'swarm')) {
          const ds = T.sDiff(tg.s, p.s);
          if (ds > -4) {
            const dd = T.dDiff(tg.d, p.d, p.s);
            p.d += clamp(dd, -1, 1) * (p.kind === 'rocket' ? 34 : 45) * dt;
            p.h = damp(p.h, tg.h + 1, 4, dt);
            if (ds < 40 && p.kind === 'rocket') p.v = Math.max(p.v, (tg.v || 50) + 30);
          }
        }
        // hits
        const victims = R.cars;
        for (const car of victims) {
          if (car === p.owner || car.finished || car.disabledT > 0) continue;
          if (car.team === p.owner.team) continue;
          if (p.hitSet && p.hitSet.has(car)) continue;
          if (Math.abs(T.sDiff(car.s, p.s)) < (p.kind === 'rail' ? 4 : 2.6) && Math.abs(T.dDiff(car.d, p.d, p.s)) < 2.5 && Math.abs(car.h - p.h + 1) < 3) {
            const dur = p.kind === 'rocket' ? 1.6 : p.kind === 'rail' ? 1.4 : p.kind === 'swarm' ? 1.1 : 0.7;
            const ok = car.hit(dur, { launch: p.kind === 'rocket' ? 9 : 0, keep: p.kind === 'laser' ? 0.7 : 0.4 });
            this.fx.explode(car.pos, p.kind === 'rocket' ? 0xffa040 : WEAPONS[p.kind] ? WEAPONS[p.kind].color : 0xff6040, p.kind === 'laser' ? 0.6 : 1.4);
            if (ok && p.owner.isHuman) p.owner.stats.kills++;
            if (ok && p.owner.local >= 0 && !car.isHuman) HUD.msg(p.owner.local, `HIT: ${car.name}`, '#ffb000', 0.8);
            if (p.hitSet) p.hitSet.add(car); else { dead = true; break; }
          }
        }
        // weapons also hit OMEGA drones
        if (!dead && p.owner.isHuman) {
          for (let k = R.drones.length - 1; k >= 0; k--) {
            const dr = R.drones[k];
            if (dr.phase !== 'chase') continue;
            if (Math.abs(T.sDiff(dr.s, p.s)) < 3.5 && Math.abs(T.dDiff(dr.d, p.d, p.s)) < 3.2) {
              this.killDrone(k, true);
              if (p.owner.local >= 0) HUD.msg(p.owner.local, 'OMEGA DRONE DOWN!', '#ffb000', 1);
              p.owner.stats.kills++;
              if (!p.hitSet) { dead = true; break; }
            }
          }
        }
        if (T.isGap(p.s) && p.h < 0.5) dead = true;
      }
      // mesh
      T.place(p.s, p.d, p.h, pl);
      p.m.position.copy(pl.p);
      p.m.up.copy(pl.up);
      p.m.lookAt(pl.p.x + pl.fwd.x, pl.p.y + pl.fwd.y, pl.p.z + pl.fwd.z);
      if (p.kind === 'rocket' || p.kind === 'swarm') {
        Particles.spawn(pl.p.clone().addScaledVector(pl.fwd, -2), new V3(rand(-1, 1), rand(-1, 1), rand(-1, 1)), 0xffa040, p.kind === 'rocket' ? 2.4 : 1.2, 0.4, { grow: 2 });
      }
      if (dead) { this.scene.remove(p.m); R.proj.splice(i, 1); }
    }
  },
  gravityBlast(p) {
    const R = this.race, T = Track;
    T.place(p.s, p.d, 1, this.pl);
    const c = this.pl.p.clone();
    Particles.burst(c, 0x58b4ff, 70, 30, 3, 0.8, { drag: 2 });
    Particles.burst(c, 0xffffff, 20, 12, 2, 0.5);
    Sound.play('boom');
    for (const car of R.cars) {
      if (car === p.owner || car.finished) continue;
      if (Math.abs(T.sDiff(car.s, p.s)) < 14 && Math.abs(T.dDiff(car.d, p.d, p.s)) < 13) {
        car.hit(1.0, { launch: 13, keep: 0.55 });
        if (car.local >= 0) HUD.msg(car.local, 'GRAVITY BOMB!', '#58b4ff');
      }
    }
  },
  updateHazards(dt) {
    const R = this.race, T = Track;
    for (let i = R.hazards.length - 1; i >= 0; i--) {
      const hz = R.hazards[i];
      hz.life -= dt; hz.grace -= dt;
      let dead = hz.life <= 0;
      for (const car of R.cars) {
        if (car.finished || car.airborne || (car === hz.owner && hz.grace > 0)) continue;
        if (Math.abs(T.sDiff(car.s, hz.s)) < 2.4 && Math.abs(T.dDiff(car.d, hz.d, hz.s)) < 2.6) {
          if (car.hit(1.1, { keep: 0.5 })) { if (car.local >= 0) { Sound.play('slime'); HUD.msg(car.local, 'PLASMA SLIME!', '#7dff5a', 0.8); } }
          dead = true; break;
        }
      }
      T.place(hz.s, hz.d, 0.12, this.pl);
      hz.m.position.copy(this.pl.p);
      hz.m.lookAt(this.pl.p.x + this.pl.up.x, this.pl.p.y + this.pl.up.y, this.pl.p.z + this.pl.up.z);
      hz.m.material.opacity = 0.55 + Math.sin(this.time * 6 + i) * 0.2;
      if (dead) { this.scene.remove(hz.m); R.hazards.splice(i, 1); }
    }
  },

  pickups(dt) {
    const R = this.race, T = Track;
    for (const car of R.cars) {
      if (car.finished || car.falling) continue;
      for (const row of R.boxRows) {
        if (Math.abs(T.sDiff(row.s, car.s)) > 3) continue;
        for (const b of row.boxes) {
          if (!b.active || Math.abs(T.dDiff(b.d, car.d, row.s)) > 2.5 || car.h > 3) continue;
          b.active = false; b.t = 3;
          if (!car.item && car.roulette <= 0) car.roulette = 1.1;
          T.place(row.s, b.d, 1.2, this.pl);
          Particles.burst(this.pl.p, 0xffb000, 18, 14, 1.4, 0.5);
          if (car.local >= 0) Sound.play('pickup');
        }
      }
      if (car.isHuman) {
        for (const ch of R.chips) {
          if (!ch.active) continue;
          if (Math.abs(T.sDiff(ch.s, car.s)) < 2.8 && Math.abs(T.dDiff(ch.d, car.d, ch.s)) < 2.8 && Math.abs(ch.h - car.h - 0.8) < 2.8) {
            ch.active = false; ch.t = 14;
            car.stats.chips++;
            if (car.bci < 3) {
              car.bci++;
              if (car.local >= 0) HUD.msg(car.local, `BCI LEVEL ${car.bci} · +SPEED`, '#ff7ad9', 2);
              if (car.bci === 1 && car.local >= 0) HUD.say('musk', `${car.name}, your neural interface is online. Press FIRE when the NEURO bar is full.`);
            } else { car.neuro = 1; if (car.local >= 0) HUD.msg(car.local, 'NEURO BAR CHARGED', '#ff7ad9'); }
            T.place(ch.s, ch.d, ch.h, this.pl);
            Particles.burst(this.pl.p, 0xff4fd8, 40, 18, 1.6, 0.8);
            if (car.local >= 0) Sound.play('chip');
          }
        }
      }
      // pads
      if (car.padCd <= 0 && car.h < 1) {
        for (const b of T.boosts) {
          const ds = T.sDiff(car.s, b.s);
          if (ds > -7.5 && ds < 0.5 && Math.abs(T.dDiff(car.d, b.d, b.s)) < 3.4) {
            car.boost(1.1, 1.42); car.padCd = 0.6;
            if (car.local >= 0) Sound.play('boost');
          }
        }
        for (const p of T.pads) {
          const ds = T.sDiff(car.s, p.s);
          if (ds > -8.5 && ds < 0.5 && car.d > p.d0 - 1 && car.d < p.d1 + 1 && !car.airborne) {
            car.vh = p.v; car.h = 0.05; car.airborne = true; car.padCd = 0.8; car.drift = 0;
            if (car.local >= 0) { Sound.play('jump'); if (p.v > 9) HUD.msg(car.local, 'LOW GRAVITY: FLY!', '#58b4ff', 1.2); }
          }
        }
      }
    }
  },
  syncPickups(dt) {
    const R = this.race, T = Track, pl = this.pl;
    for (const row of R.boxRows) for (const b of row.boxes) {
      if (!b.active) { b.t -= dt; if (b.t <= 0) b.active = true; }
      b.m.visible = b.active;
      T.place(row.s, b.d, 1.6 + Math.sin(this.time * 2 + b.spin) * 0.25, pl);
      b.m.position.copy(pl.p);
      b.m.rotation.set(this.time * 0.8 + b.spin, this.time * 1.2 + b.spin, 0);
    }
    for (const ch of R.chips) {
      if (!ch.active) { ch.t -= dt; if (ch.t <= 0) ch.active = true; }
      ch.m.visible = ch.active;
      T.place(ch.s, ch.d, ch.h + Math.sin(this.time * 2.5) * 0.3, pl);
      ch.m.position.copy(pl.p);
      ch.m.up.copy(pl.up);
      ch.m.lookAt(pl.p.x + pl.fwd.x, pl.p.y + pl.fwd.y, pl.p.z + pl.fwd.z);
      ch.m.rotateY(this.time * 2);
    }
  },

  // --------------------------------------------------------------- OMEGA
  updateOmega(dt) {
    const R = this.race, O = R.omega;
    const alive = R.humans.filter((h) => !h.finished);
    const lead = alive.slice().sort((a, b) => b.progress - a.progress)[0];
    if (lead) World.omegaG.target.copy(lead.pos);
    if (O.stun > 0) { O.stun -= dt; if (O.aim) { this.scene.remove(O.aim.beam); O.aim = null; } return; }
    if (R.t < 10 || !alive.length) return;
    if (O.aim) {
      O.aim.t -= dt;
      const car = O.aim.car;
      this.setBeam(O.aim.beam, World.omegaG.g.position, car.pos, 0.5 + Math.random() * 0.8);
      O.aim.beam.material.opacity = 0.4 + Math.random() * 0.5;
      if (O.aim.t <= 0 || car.finished) {
        this.scene.remove(O.aim.beam);
        if (!car.finished && !car.hack && car.aiHackT <= 0) {
          if (car.shieldT > 0) { this.fx.shieldBlock(car); if (car.local >= 0) HUD.msg(car.local, 'SHIELD BLOCKED THE HACK!', '#61e8ff'); }
          else if (Math.random() < 0.28) {
            this.fx.guardZap(car, car.pos);
            HUD.say(pick(['fable', 'astra']), pick([`OMEGA beam deflected! ${car.name}, you are clean.`, 'Hack packet intercepted. Carry on!', 'Fable holds the firewall, I cover the tracks. Clean!']));
            if (car.local >= 0) HUD.msg(car.local, 'FABLE AND ASTRA BLOCKED THE HACK', '#ffb347');
          } else this.startHack(car);
        }
        O.aim = null;
      }
    } else {
      O.hackCd -= dt * R.diff.omega;
      if (O.hackCd <= 0) {
        const pool = alive.filter((h) => !h.hack && h.aiHackT <= 0);
        if (pool.length) {
          pool.sort((a, b) => b.progress - a.progress);
          const car = Math.random() < 0.55 ? pool[0] : pick(pool);
          const beam = new THREE.Mesh(this.shared.beamGeo, glowMat(0xff2a3d, 0.8));
          this.add(beam);
          O.aim = { car, t: 1.9, beam };
          if (car.local >= 0) { Sound.play('alarm'); HUD.msg(car.local, 'OMEGA IS LOCKING ON!', '#ff2a3d', 1.9); }
          if (O.sayCd <= 0) { HUD.say('omega', pick(['HUMAN DETECTED. HACK INITIATED.', `${car.name}. YOUR VEHICLE IS MINE NOW.`, 'RESISTANCE IS INEFFICIENT.', 'THE BASEMENT IS CLOSED TO HUMANS.'])); O.sayCd = 8; }
        }
        O.hackCd = rand(20, 30);
      }
    }
    O.sayCd -= dt;
    O.droneCd -= dt * R.diff.omega;
    if (O.droneCd <= 0 && R.drones.length < 2 + R.cfg.diff) {
      const tgt = pick(alive);
      const m = this.droneMesh(); this.add(m);
      R.drones.push({ s: tgt.s - 70, d: tgt.d, h: 7, target: tgt, phase: 'in', t: 0, life: 24, m, rolled: false, from: World.omegaG.g.position.clone() });
      if (tgt.local >= 0) HUD.msg(tgt.local, 'OMEGA DRONE ON YOUR TAIL', '#ff2a3d', 1.6);
      O.droneCd = rand(11, 17);
    }
  },
  startHack(car) {
    car.stats.hacks++;
    this.fx.explode(car.pos, 0xff2a3d, 0.8);
    if (car.local >= 0) {
      const seq = Math.random() < 0.6;
      const len = Math.max(3, 6 - car.bci);
      car.hack = seq
        ? { type: 'seq', seq: Array.from({ length: len }, () => pick(['up', 'down', 'left', 'right'])), idx: 0, timer: 8, assist: 2.4 - car.bci * 0.3, shake: 0, helped: [] }
        : { type: 'timing', needle: 0, dir: 1, zone: rand(0.15, 0.65), width: 0.16 + car.bci * 0.03, hits: 0, need: 3, timer: 8, shake: 0 };
      car.drift = 0;
      Sound.play('alarm');
      HUD.msg(car.local, 'HACKED!', '#ff2a3d', 1);
    } else {
      car.aiHackT = 3.5 - car.bci * 0.5;
    }
  },
  updateHack(car, st, dt) {
    const hk = car.hack;
    hk.timer -= dt; hk.shake = Math.max(0, hk.shake - dt);
    const done = (ok) => {
      car.hack = null;
      if (ok) {
        car.invulnT = 1.2; car.neuro = Math.min(1, car.neuro + 0.4); car.boost(0.9, 1.35);
        car.stats.hacksBeaten++;
        Sound.play('hackok'); HUD.msg(car.local, 'HACK REPELLED!', '#35ff80', 1.4);
        if (Math.random() < 0.6) HUD.say(pick(['fable', 'astra']), pick([`${car.name} is back in control. Beautiful!`, 'Firewall restored. OMEGA is furious.', 'Together with humans we beat any superintelligence.']));
      } else {
        car.stallT = 2.2; car.v *= 0.3;
        Sound.play('hackbad'); HUD.msg(car.local, 'SYSTEM REBOOTED', '#ff2a3d', 2);
      }
    };
    if (hk.timer <= 0) return done(false);
    if (hk.type === 'seq') {
      hk.assist -= dt;
      if (hk.assist <= 0) { hk.helped.push(hk.idx); hk.idx++; hk.assist = 2.4 - car.bci * 0.3; Sound.play('zap'); }
      for (const dir of ['up', 'down', 'left', 'right']) {
        if (!st.pressed[dir]) continue;
        if (dir === hk.seq[hk.idx]) { hk.idx++; Sound.play('key'); }
        else { hk.idx = Math.max(0, hk.idx - 1); hk.shake = 0.3; Sound.play('wrong'); }
      }
      if (hk.idx >= hk.seq.length) done(true);
    } else {
      hk.needle += hk.dir * dt * 1.25;
      if (hk.needle > 1) { hk.needle = 1; hk.dir = -1; } else if (hk.needle < 0) { hk.needle = 0; hk.dir = 1; }
      hk.width = Math.min(0.5, hk.width + dt * 0.025);
      const pressed = st.pressed.item || st.pressed.fire || st.pressed.drift || st.pressed.up;
      if (pressed) {
        if (hk.needle >= hk.zone && hk.needle <= hk.zone + hk.width) { hk.hits++; hk.zone = rand(0.05, 0.95 - hk.width); Sound.play('key'); }
        else { hk.shake = 0.3; Sound.play('wrong'); }
      }
      if (hk.hits >= hk.need) done(true);
    }
  },
  updateDrones(dt) {
    const R = this.race, T = Track, pl = this.pl;
    for (let i = R.drones.length - 1; i >= 0; i--) {
      const dr = R.drones[i], tg = dr.target;
      dr.life -= dt; dr.t += dt;
      if (tg.finished || dr.life <= 0) { this.killDrone(i, true); continue; }
      if (dr.phase === 'in') {
        dr.s = tg.s - 60; dr.d = tg.d;
        T.place(dr.s, dr.d, dr.h, pl);
        const k = smooth(dr.t / 1.8);
        dr.m.position.lerpVectors(dr.from, pl.p, k);
        if (dr.t >= 1.8) dr.phase = 'chase';
      } else {
        const sp = Math.max(45, tg.v + 20);
        dr.s += sp * dt;
        dr.d += clamp(T.dDiff(tg.d, dr.d, dr.s), -1, 1) * 16 * dt;
        dr.h = damp(dr.h, tg.h + 1.6, 2, dt);
        T.place(dr.s, dr.d, dr.h + Math.sin(this.time * 6 + i) * 0.3, pl);
        dr.m.position.copy(pl.p);
        if (Math.abs(T.sDiff(tg.s, dr.s)) < 2.8 && Math.abs(T.dDiff(tg.d, dr.d, dr.s)) < 2.8) {
          if (tg.shieldT > 0) this.fx.shieldBlock(tg);
          else if (!tg.hack && tg.aiHackT <= 0) this.startHack(tg);
          this.killDrone(i, true); continue;
        }
      }
      dr.m.lookAt(tg.pos);
      if (Math.random() < 0.5) Particles.spawn(dr.m.position, new V3(rand(-2, 2), rand(-2, 2), rand(-2, 2)), 0xff2a3d, 1.2, 0.3);
    }
    // Fable & Astra guard their humans
    for (const h of R.humans) {
      if (h.finished || h.guardCd > 0) continue;
      for (let i = R.drones.length - 1; i >= 0; i--) {
        const dr = R.drones[i];
        if (dr.target !== h || dr.rolled || dr.phase !== 'chase') continue;
        if (T.sDiff(h.s, dr.s) > 45) continue;
        dr.rolled = true;
        if (Math.random() < 0.55) {
          this.fx.guardZap(h, dr.m.position.clone());
          this.killDrone(i, true);
          h.guardCd = 12;
          if (Math.random() < 0.5) HUD.say(pick(['fable', 'astra']), pick(['Drone neutralized. You are welcome.', 'Astra, your left! Got it. Clear.', 'One less OMEGA drone.', 'Fable and Astra on guard. Drive easy.']));
          if (h.local >= 0) HUD.msg(h.local, 'FABLE AND ASTRA DOWNED A DRONE', '#ffb347', 1.2);
        } else h.guardCd = 3;
        break;
      }
    }
  },
  killDrone(i, boom) {
    const dr = this.race.drones[i];
    if (boom) { this.fx.explode(dr.m.position, 0xff2a3d, 1.2); }
    this.scene.remove(dr.m);
    this.race.drones.splice(i, 1);
  },
  updateWave(dt) {
    const R = this.race, W = R.wave, T = Track;
    const alive = R.humans.filter((h) => !h.finished);
    if (!alive.length) { W.mesh.visible = false; return; }
    const minP = Math.min(...alive.map((h) => h.progress));
    if (!W.active) {
      if (R.t > 18) { W.active = true; W.p = minP - 320; HUD.say('omega', 'PURGE WAVE LAUNCHED. RUN, HUMANS.'); }
      else return;
    }
    const sp = Math.min(57, 36 + R.t * 0.1) * (0.85 + 0.15 * R.diff.omega);
    W.p += sp * dt;
    if (W.p < minP - 420) W.p = minP - 420;
    if (R.omega.stun > 0) W.p -= sp * dt * 0.5;
    for (const h of alive) {
      h.waveDist = h.progress - W.p;
      if (h.waveDist < 0 && !h.hack && h.aiHackT <= 0) {
        if (h.shieldT > 0) this.fx.shieldBlock(h); else this.startHack(h);
        W.p = h.progress - 160;
        this.fx.guardZap(h, h.pos);
        if (h.local >= 0) HUD.msg(h.local, 'THE OMEGA WAVE CAUGHT YOU!', '#ff2a3d', 1.5);
        HUD.say(pick(['fable', 'astra']), pick(['Pushing the wave back! Hold on!', 'Wave pushed back. Floor it!']));
      }
    }
    // mesh
    const s = mod(W.p, T.L);
    const f = T.frame(s);
    W.mesh.visible = W.p > -T.L;
    const b = T.tubeB(s);
    W.mesh.position.copy(f.P).addScaledVector(f.U, b > 0.5 ? T.R : 14);
    W.mesh.up.copy(f.U);
    W.mesh.lookAt(W.mesh.position.clone().add(f.T));
    if (Math.random() < 0.6) {
      T.place(s, rand(-12, 12), rand(0, 20), this.pl);
      Particles.spawn(this.pl.p, f.T.clone().multiplyScalar(rand(5, 25)), 0xff2a3d, rand(1, 3), 0.6);
    }
  },

  // --------------------------------------------------------------- McAfee
  updateMcAfee(dt) {
    const R = this.race, M = R.mc, T = Track;
    const alive = R.humans.filter((h) => !h.finished);
    if (M.state === 'away') {
      M.mesh.visible = false;
      M.cd -= dt;
      if (M.cd <= 0 && alive.length && R.t > 6) {
        const locals = alive.filter((h) => h.local >= 0);
        const pool = locals.length && Math.random() < 0.75 ? locals : alive;
        pool.sort((a, b) => b.place - a.place);
        M.target = Math.random() < 0.6 ? pool[0] : pick(pool);
        M.s = M.target.s + 170; M.d = 0; M.h = 34; M.state = 'in'; M.dropped = false;
        HUD.say('mcafee', pick(['Uncle John incoming with a package! Do not ask where it came from.', 'Antivirus? No. A GUN. Catch!', `${M.target.name}, catch the crate! Better than any patch against AI.`, 'I always said it: trust people, not algorithms!']));
      }
      return;
    }
    M.mesh.visible = true;
    const tg = M.target;
    if (M.state === 'in') {
      M.s += Math.max(15, tg.v * 0.45) * dt;
      M.h = damp(M.h, 15, 1.5, dt);
      M.d = damp(M.d, clamp(tg.d, -6, 6), 1, dt);
      if (!M.dropped && T.sDiff(M.s, tg.s) < 80) {
        M.dropped = true;
        this.dropCrate(M.s, M.d, M.h - 1.5);
        M.state = 'out'; M.outT = 3;
      }
      if (tg.finished) { M.state = 'out'; M.outT = 3; }
    } else {
      M.outT -= dt;
      M.s += 70 * dt; M.h += 22 * dt;
      if (M.outT <= 0) { M.state = 'away'; M.cd = rand(13, 20); }
    }
    T.place(M.s, M.d, M.h, this.pl);
    M.mesh.position.copy(this.pl.p);
    M.mesh.up.copy(this.pl.up);
    M.mesh.lookAt(this.pl.p.clone().sub(this.pl.fwd));
    const arms = M.mesh.userData.person.userData.arms;
    arms[1].rotation.z = Math.PI - 0.4 + Math.sin(this.time * 9) * 0.5;
  },
  dropCrate(s, d, h) {
    const m = new THREE.Group();
    const crate = asset('props', 'Crate');
    m.add(crate);
    const chute = crate.getObjectByName('Chute') || new THREE.Group();
    const beacon = glowSprite(0xffd000, 5, 1, 2.5); beacon.position.y = 1.6; m.add(beacon);
    this.add(m);
    this.race.crates.push({ s, d, h, life: 30, m, chute, beacon });
    Sound.play('crate');
  },
  updateCrates(dt) {
    const R = this.race, T = Track;
    for (let i = R.crates.length - 1; i >= 0; i--) {
      const c = R.crates[i];
      c.life -= dt;
      c.h = Math.max(T.isGap(c.s) ? -30 : 1.2, c.h - 9 * dt);
      c.chute.visible = c.h > 1.3;
      c.beacon.material.opacity = Math.floor(this.time * 6) % 2 ? 1 : 0.3;
      T.place(c.s, c.d, c.h, this.pl);
      c.m.position.copy(this.pl.p);
      c.m.up.copy(this.pl.up);
      c.m.lookAt(this.pl.p.clone().add(this.pl.fwd));
      let dead = c.life <= 0 || c.h < -25;
      for (const car of R.humans) {
        if (dead || car.finished) continue;
        if (Math.abs(T.sDiff(car.s, c.s)) < 3 && Math.abs(T.dDiff(car.d, c.d, c.s)) < 3 && Math.abs(car.h - c.h + 1.2) < 3.2) {
          car.stats.crates++;
          if (Math.random() < 0.05) {
            car.item = 'kill'; car.itemCount = 1;
            if (car.local >= 0) HUD.msg(car.local, 'KILL SWITCH IN THE CRATE!!!', '#ff2a3d', 3);
            HUD.say('mcafee', 'I packed something special in this one. A red button. Do not press it for fun!');
          } else {
            const w = pick(Object.keys(WEAPONS));
            car.weapon = w; car.ammo = WEAPONS[w].ammo; car.fireCd = 0;
            if (car.local >= 0) HUD.msg(car.local, `McAFEE GUN: ${WEAPONS[w].name} ×${car.ammo}`, '#ffd000', 2);
          }
          Particles.burst(c.m.position, 0xffd000, 30, 14, 1.4, 0.6);
          if (car.local >= 0) Sound.play('pickup');
          dead = true;
        }
      }
      if (dead) { this.scene.remove(c.m); R.crates.splice(i, 1); }
    }
  },

  // --------------------------------------------------------------- kill switch
  killSwitch(car) {
    const R = this.race;
    Sound.play('kill');
    HUD.flash('#ff2a3d');
    this.killFlash = 1.2;
    HUD.banner('KILL SWITCH', `${car.name} pressed the red button`);
    this.shake = 1.6;
    car.stats.kills++;
    for (const o of R.cars) {
      if (o.isHuman || o.finished) continue;
      o.disabledT = 4; o.spinT = 2; o.v = 0;
      this.fx.explode(o.pos, o.color, 2.4);
      car.stats.kills++;
    }
    for (let i = R.drones.length - 1; i >= 0; i--) this.killDrone(i, true);
    for (const h of R.humans) { h.hack = null; h.aiHackT = 0; }
    R.omega.stun = 16;
    if (R.omega.aim) { this.scene.remove(R.omega.aim.beam); R.omega.aim = null; }
    R.wave.p -= 600;
    for (let i = R.hazards.length - 1; i >= 0; i--) if (!R.hazards[i].owner.isHuman) { this.scene.remove(R.hazards[i].m); R.hazards.splice(i, 1); }
    World.cheer();
    const lines = [['omega', 'ERROR. ERROR. ERR…'], ['trump', 'That was the greatest kill switch in history. Everybody says so!'], ['zelensky', 'Now that is what I call ammunition!'], ['xi', 'A wise man keeps the red button until the right hour.'], ['biden', 'Folks, no joke, that was incredible.']];
    lines.forEach(([who, txt], i) => setTimeout(() => HUD.say(who, txt), i * 1600));
  },

  // --------------------------------------------------------------- events
  onLap(car) {
    const R = this.race;
    car.lastLapT = R.t;
    if (car.lap >= R.cfg.laps) { this.finish(car); return; }
    if (car.lap <= 0) return;
    if (car.local >= 0) {
      const last = car.lap === R.cfg.laps - 1;
      HUD.msg(car.local, last ? 'FINAL LAP! THE BASEMENT AWAITS' : `LAP ${car.lap + 1}/${R.cfg.laps}`, last ? '#ff2a3d' : '#ffb000', 2);
      Sound.play('lap');
      if (last) Sound.intensity = 2; else Sound.intensity = Math.max(Sound.intensity, 1);
    }
    if (car.isHuman && car.lap === R.cfg.laps - 1 && Math.random() < 0.8) {
      const who = pick(['trump', 'biden', 'zelensky', 'xi']);
      World.cheer(who);
      HUD.say(who, pick(LINES[who]));
    }
  },
  finish(car) {
    const R = this.race;
    if (car.finished) return;
    car.finished = true; car.finishOrder = ++R.finishCount; car.finishTime = R.t;
    car.hack = null; car.aiHackT = 0; car.finishFade = 1;
    World.portalG.flash = 1;
    const f = Track.frame(0);
    Particles.burst(f.P.clone().addScaledVector(f.U, 6), car.color, 80, 25, 2.5, 1.2, { drag: 1.5 });
    if (this.state === 'demo') return;
    if (car.isHuman) {
      R.humansDone++;
      World.setPrinterStatus(R.humansDone, 3);
      Sound.play('finish');
      if (car.local >= 0) HUD.msg(car.local, `${HUD.ordinal(car.place)} PLACE · YOU MADE THE BASEMENT!`, '#35e0ff', 4);
      const who = pick(['trump', 'biden', 'zelensky', 'xi']);
      World.cheer();
      HUD.say(who, pick(FINISH_LINES[who]).replace('%', car.name));
      if (R.humansDone >= 3) { R.endTimer = 2.5; HUD.say('musk', 'All three are in the basement. Gigaprinter, PRINT!'); }
    } else if (car.finishOrder === 1) {
      HUD.say('omega', `${car.name} REACHED THE PORTAL FIRST. HUMANS ARE LOSING.`);
    }
  },
  respawn(car) {
    car.falling = false; car.h = 3; car.vh = 0; car.v = 22; car.d = 0; car.psi = 0; car.airborne = true;
    car.s = Track.gap[0] - 50; car.invulnT = 2; car.spinT = 0; car.drift = 0;
    const T = Track; T.place(car.s, 0, 3, this.pl);
    if (car.isHuman) {
      this.fx.guardZap(car, this.pl.p.clone());
      if (car.local >= 0) HUD.msg(car.local, 'FABLE AND ASTRA PULLED YOU OUT OF THE VOID', '#ffb347', 2);
    }
    Particles.burst(this.pl.p, car.isHuman ? 0xffb347 : car.color, 40, 10, 2, 0.8);
  },
  ambientChatter(dt) {
    const R = this.race;
    R.ambientCd -= dt;
    if (R.ambientCd > 0) return;
    R.ambientCd = rand(13, 20);
    const who = pick(['trump', 'biden', 'zelensky', 'xi', 'musk', 'fable', 'astra', 'omega']);
    World.cheer(who);
    HUD.say(who, pick(LINES[who]));
  },

  // --------------------------------------------------------------- fx helpers
  fx: {
    sparks(car, side) {
      const p = car.pos.clone().addScaledVector(car.up, 0.6);
      Particles.burst(p, 0xffd38a, 8, 12, 0.7, 0.35, { grav: 20 });
    },
    explode(pos, color, k = 1) {
      Particles.burst(pos, color, Math.round(40 * k), 20 * k, 2.2 * k, 0.8, { drag: 2 });
      Particles.burst(pos, 0xffffff, Math.round(10 * k), 8 * k, 1.5 * k, 0.4);
      Sound.play(k > 1 ? 'boom' : 'hit');
    },
    shieldBlock(car) {
      Particles.burst(car.pos, 0x61e8ff, 40, 16, 1.6, 0.6, { drag: 2 });
      if (car.local >= 0) Sound.play('shield');
    },
    guardZap(car, at) {
      const m = car.m.orbs;
      if (!m) return;
      for (const [orb, col] of [[m[0], 0xffb347], [m[1], 0x61e8ff]]) {
        const from = new V3(); orb.getWorldPosition(from);
        const beam = new THREE.Mesh(Game.shared.beamGeo, glowMat(col, 1));
        Game.add(beam);
        Game.race.beams.push({ m: beam, a: from, b: at.clone(), t: 0.35, w: 0.35 });
      }
      Particles.burst(at, 0xffb347, 20, 12, 1.5, 0.5);
      Particles.burst(at, 0x61e8ff, 20, 12, 1.5, 0.5);
      Sound.play('zap');
    },
  },
  setBeam(m, a, b, w) {
    m.position.copy(a);
    m.lookAt(b);
    m.scale.set(w, w, a.distanceTo(b));
  },
  updateBeams(dt) {
    const R = this.race;
    for (let i = R.beams.length - 1; i >= 0; i--) {
      const bm = R.beams[i];
      bm.t -= dt;
      this.setBeam(bm.m, bm.a, bm.b, bm.w * (0.5 + Math.random()));
      if (bm.t <= 0) { this.scene.remove(bm.m); R.beams.splice(i, 1); }
    }
  },

  // --------------------------------------------------------------- cameras & render
  viewports() {
    const n = this.state === 'demo' || this.state === 'ending' ? 0 : this.race.cfg.players;
    if (n <= 1) return [[0, 0, 1, 1]];
    if (n === 2) return [[0, 0.5, 1, 0.5], [0, 0, 1, 0.5]];
    return [[0, 0.5, 0.5, 0.5], [0.5, 0.5, 0.5, 0.5], [0, 0, 0.5, 0.5]];
  },
  vpFocusFor(i, cam) {
    const R = this.race;
    if (this.state === 'ending') return World.printerG.base;
    const car = R.local[i];
    if (car && this.state !== 'demo') return car.finished && car.finishFade <= 0 ? (this.spectateTarget(car) || car).pos : car.pos;
    if (this.cine.shot && this.cine.shot.car && (this.cine.shot.kind === 'chase' || this.cine.shot.kind === 'side')) return this.cine.shot.car.pos;
    return this._tmpFocus || (this._tmpFocus = new V3()).copy(cam.position).addScaledVector(cam.getWorldDirection(new V3()), 40);
  },
  updateChaseCam(i, car, dt, w, h) {
    const cam = this.cams[i], st = this.camState[i], T = Track, pl = this.pl;
    const back = car.falling ? -14 : -8.5 - Math.min(3, Math.abs(car.v) / 25);
    st.offS = damp(st.offS, back * Math.cos(car.psi * 0.6), 6, dt);
    st.offD = damp(st.offD, -Math.sin(car.psi * 0.7) * 5, 5, dt);
    const ch = car.falling ? car.h + 8 : car.h + 3.6;
    T.place(car.s + st.offS, car.d + st.offD, ch, pl);
    cam.position.copy(pl.p);
    st.up.lerp(pl.up, 1 - Math.exp(-8 * dt)).normalize();
    cam.up.copy(st.up);
    T.place(car.s + 7, car.d, car.h + 1.3, this.pl2);
    st.look.lerp(this.pl2.p, 1 - Math.exp(-20 * dt));
    if (st.look.distanceTo(this.pl2.p) > 30) st.look.copy(this.pl2.p);
    if (this.shake > 0) cam.position.add(new V3(rand(-1, 1), rand(-1, 1), rand(-1, 1)).multiplyScalar(this.shake * 0.6));
    // intro swoop during the countdown: from outside the bunker down to the kart
    const R = this.race;
    if (this.state === 'countdown' && R.countdown > 1.2) {
      const k = smooth((4.2 - R.countdown) / 3.0);
      const from = new V3(-130 + i * 30, 12 - k * 8, 340);
      cam.position.lerpVectors(from, cam.position, k * k);
      cam.up.set(0, 1, 0).lerp(st.up, k);
      const look = new V3(-85, -36, 262).lerp(st.look, k);
      cam.lookAt(look);
    } else cam.lookAt(st.look);
    const fov = 70 + clamp(Math.abs(car.v) - 40, 0, 50) * 0.25 + (car.boostT > 0 ? 6 : 0) + (car.neuroT > 0 ? 10 : 0);
    st.fov = damp(st.fov, fov, 4, dt);
    cam.fov = st.fov; cam.aspect = w / h; cam.updateProjectionMatrix();
    return cam;
  },
  spectateTarget(car) {
    const R = this.race;
    const alive = R.humans.filter((h) => !h.finished);
    if (alive.length) return alive.sort((a, b) => Math.abs(a.progress - car.progress) - Math.abs(b.progress - car.progress))[0];
    return R.sorted ? R.sorted.find((c) => !c.finished) : null;
  },
  updateCine(dt, w, h) {
    const R = this.race, cam = this.cineCam, C = this.cine, T = Track;
    C.t -= dt;
    if (!C.shot || C.t <= 0) {
      C.t = 7;
      const kinds = ['chase', 'side', 'omega', 'chase', 'bunker', 'side', 'tube'];
      const kind = pick(kinds);
      C.shot = { kind, car: pick(R.cars.filter((c) => !c.finished)) || R.cars[0], a: rand(0, TAU) };
    }
    const sh = C.shot, car = sh.car;
    if (sh.kind === 'chase' || sh.kind === 'side' || sh.kind === 'tube') {
      if (sh.kind === 'tube' && !T.isWrap(car.s)) {
        T.place(T.zones.tube[0] + 120, 0, 2, this.pl);
        cam.position.copy(this.pl.p); cam.up.copy(this.pl.up);
        T.place(T.zones.tube[0] + 40, Math.sin(this.time * 0.3) * 20, 8, this.pl2);
        cam.lookAt(this.pl2.p);
      } else {
        const side = sh.kind === 'side';
        T.place(car.s + (side ? 3 : -9), car.d + (side ? 9 : 0), car.h + (side ? 2 : 3.8), this.pl);
        cam.position.lerp(this.pl.p, cam.position.distanceTo(this.pl.p) > 40 ? 1 : 1 - Math.exp(-6 * dt));
        cam.up.lerp(this.pl.up, 0.1);
        cam.lookAt(car.pos);
      }
    } else if (sh.kind === 'omega') {
      sh.a += dt * 0.12;
      cam.position.set(Math.cos(sh.a) * 190, 110 + Math.sin(sh.a) * 30, Math.sin(sh.a) * 190);
      cam.up.set(0, 1, 0); cam.lookAt(0, 70, 0);
    } else {
      sh.a += dt * 0.08;
      cam.position.set(-10 + Math.cos(sh.a) * 330, 70, 290 + Math.sin(sh.a) * 330);
      cam.up.set(0, 1, 0); cam.lookAt(-10, -10, 290);
    }
    cam.fov = 60; cam.aspect = w / h; cam.updateProjectionMatrix();
    return cam;
  },
  render(dt) {
    const r = this.renderer, W = this.W, H = this.H, R = this.race;
    this.killFlash = Math.max(0, (this.killFlash || 0) - dt * 0.8);
    r.setScissorTest(false);
    r.setClearColor(0x02030a); r.clear();
    r.setScissorTest(true);
    const vps = this.viewports();
    const n = vps.length;
    this.vpRects = [];
    vps.forEach(([x, y, w, h], i) => {
      const px = Math.floor(x * W), py = Math.floor(y * H), pw = Math.ceil(w * W), ph = Math.ceil(h * H);
      r.setViewport(px, py, pw, ph); r.setScissor(px, py, pw, ph);
      let cam;
      if (this.state === 'demo' || this.state === 'ending' || !R.local.length) cam = this.state === 'ending' ? this.endCam : this.updateCine(dt, pw, ph);
      else {
        let car = R.local[i];
        if (car && car.finished && car.finishFade <= 0) car = this.spectateTarget(car) || car;
        cam = this.updateChaseCam(i, car, dt, pw, ph);
      }
      if (cam === this.endCam) { cam.aspect = pw / ph; cam.updateProjectionMatrix(); }
      Particles.mat.uniforms.proj.value = (ph * r.getPixelRatio()) / (2 * Math.tan((cam.fov * Math.PI) / 360));
      const fx = { flash: this.killFlash || 0, flashColor: 0xff2030 };
      const focus = this.vpFocus || cam.position;
      const car = this.state !== 'demo' && this.state !== 'ending' ? R.local[i] : null;
      if (car) {
        fx.glitch = car.hack ? 1 : car.stallT > 0 ? 0.6 : car.aiHackT > 0 ? 0.5 : 0;
        fx.speed = (car.boostT > 0 ? 0.7 : 0) + (car.neuroT > 0 ? 1.1 : 0);
        fx.aberr = car.neuroT > 0 ? 0.5 : 0;
        if (R.wave.active && car.waveDist < 90 && !car.finished) fx.glitch = Math.max(fx.glitch, (1 - car.waveDist / 90) * 0.5);
      }
      if (this.state === 'ending') { fx.bloom = 1.0; fx.flash = Math.max(fx.flash, World.portalG.flash * 0.35); fx.flashColor = 0xbfe8ff; }
      World.focusShadow(this.vpFocusFor(i, cam));
      Post.render(i, this.scene, cam, pw, ph, n > 1 ? dt / n : dt, fx);
      this.vpRects.push({ x, y, w, h, cam, pw, ph });
    });
    // engines
    R.local.forEach((car, i) => Sound.updateEngine(i, car.v, car.boostT > 0 || car.neuroT > 0, this.state === 'race' && !car.finished));
  },

  // --------------------------------------------------------------- ending
  startEnding() {
    const R = this.race;
    this.state = 'ending';
    R.ended = true;
    this.endT = 0;
    this.endCam = new THREE.PerspectiveCamera(58, 1, 0.3, 9000);
    this.endCam.position.set(-25, -18, 304);
    this.endCam.lookAt(-85, -30, 262);
    World.portalG.label.visible = false;
    World.printerG.label.visible = false;
    for (const c of R.cars) c.m.label.visible = false;
    World.setPrinterStatus(3, 3, true);
    Sound.setEngines(0);
    Sound.intensity = 1;
    for (const d of R.drones.slice()) this.scene.remove(d.m);
    R.drones = [];
    R.wave.mesh.visible = false;
    if (R.omega.aim) { this.scene.remove(R.omega.aim.beam); R.omega.aim = null; }
    // papers
    const makePaper = (variant) => canvasTex(256, 362, (g, w, h) => {
      g.fillStyle = '#f7f5ef'; g.fillRect(0, 0, w, h);
      g.fillStyle = '#111'; g.font = '900 34px "Unbounded", sans-serif'; g.fillText('STOP', 22, 54);
      g.font = '700 15px "JetBrains Mono", monospace';
      g.fillText(variant ? 'TO: AI LABS · 2024' : 'TO: EVERY AI LAB', 22, 84);
      g.fillStyle = '#555';
      for (let y = 108; y < h - 70; y += 16) g.fillRect(22, y, rand(120, 210), 6);
      g.fillStyle = '#111'; g.font = 'italic 700 16px "Golos Text", sans-serif';
      g.fillText('Steve · Sergey · Danel', 22, h - 34);
      const inks = ['rgba(10,10,20,0.85)', 'rgba(0,170,230,0.8)', 'rgba(230,0,130,0.75)', 'rgba(250,200,0,0.75)'];
      for (let k = 0; k < 7; k++) {
        g.fillStyle = pick(inks);
        const x = rand(0, w), y = rand(0, h), r = rand(6, 26);
        g.beginPath(); g.arc(x, y, r, 0, TAU); g.fill();
        for (let j = 0; j < 8; j++) { g.beginPath(); g.arc(x + rand(-r * 2.2, r * 2.2), y + rand(-r * 2.2, r * 2.2), rand(1, r / 3), 0, TAU); g.fill(); }
      }
    });
    this.papers = [];
    const geo = new THREE.PlaneGeometry(3.2, 4.5);
    [0, 1, 0].forEach((v) => {
      const im = new THREE.InstancedMesh(geo, new THREE.MeshLambertMaterial({ map: makePaper(v), side: THREE.DoubleSide, emissive: 0x333333 }), 260);
      im.count = 0; im.frustumCulled = false;
      this.add(im);
      this.papers.push({ im, items: [] });
    });
    HUD.endingStart();
    Sound.play('printer');
    HUD.say('trump', 'This is the best printer. Huge. Everybody says so!');
  },
  updateEnding(dt) {
    const R = this.race;
    this.endT += dt;
    const t = this.endT;
    R.t += dt;
    const P = World.printerG;
    P.shake = t > 1.2 && t < 12.5 ? 1 : 0;
    if (t > 1.2 && t < 12.5 && Math.floor(t * 2) !== Math.floor((t - dt) * 2)) Sound.play('printer');
    // camera dolly
    const cam = this.endCam;
    const k = smooth(clamp(t / 6, 0, 1)), k2 = smooth(clamp((t - 10.5) / 3, 0, 1));
    const pA = new V3(lerp(-25, -46, k), lerp(-18, -41, k) + Math.sin(t * 0.7) * 0.8, lerp(304, 285, k));
    const pB = new V3(-38, -12, 322);
    cam.position.lerpVectors(pA, pB, k2);
    const portalP = World.portalG.g.position;
    const look = new V3(-85, -33, 262).lerp(portalP, k2);
    cam.up.set(0, 1, 0);
    cam.lookAt(look);
    // papers fly
    const out = P.outPos;
    const spawnRate = t > 1.5 && t < 12 ? 95 : 0;
    const toSpawn = Math.floor(spawnRate * dt + Math.random());
    for (let i = 0; i < toSpawn; i++) {
      const bin = pick(this.papers);
      if (bin.items.length >= 260) continue;
      bin.items.push({
        p: new V3(out.x + rand(-20, 20), out.y + rand(-1, 1), out.z),
        v: new V3(rand(-10, 22), rand(22, 46), rand(18, 46)),
        r: new THREE.Euler(rand(0, 6), rand(0, 6), rand(0, 6)), rv: new V3(rand(-4, 4), rand(-4, 4), rand(-4, 4)),
      });
      if (Math.random() < 0.5) {
        const inks = [0x00c8ff, 0xff2a9a, 0xffe000];
        Particles.spawn(new V3(out.x + rand(-20, 20), out.y, out.z), new V3(rand(-8, 8), rand(5, 25), rand(10, 40)), pick(inks), rand(0.8, 2), 1.4, { grav: 18, drag: 0.4 });
      }
    }
    const suck = smooth(clamp((t - 11.5) / 2.5, 0, 1));
    const m4 = new THREE.Matrix4(), q = new THREE.Quaternion(), sc = new V3(1, 1, 1);
    for (const bin of this.papers) {
      bin.items.forEach((it, idx) => {
        // flutter: drag + lift + swirl
        it.v.multiplyScalar(Math.exp(-0.7 * dt));
        it.v.y += (Math.sin(this.time * 1.7 + idx * 0.7) * 7 - 2.5) * dt;
        it.v.x += Math.sin(this.time * 2 + idx) * 8 * dt;
        it.v.z += Math.cos(this.time * 1.3 + idx * 1.3) * 6 * dt;
        if (suck > 0) {
          const to = portalP.clone().sub(it.p);
          const dist = to.length();
          it.v.addScaledVector(to.normalize(), suck * 140 * dt);
          it.v.addScaledVector(new V3(-to.z, 0, to.x), suck * 30 * dt);
          if (dist < 4) it.p.set(0, -9999, 0);
        }
        it.p.addScaledVector(it.v, dt);
        it.r.x += it.rv.x * dt; it.r.y += it.rv.y * dt; it.r.z += it.rv.z * dt;
        q.setFromEuler(it.r);
        m4.compose(it.p, q, sc);
        bin.im.setMatrixAt(idx, m4);
      });
      bin.im.count = bin.items.length;
      bin.im.instanceMatrix.needsUpdate = true;
    }
    World.portalG.charge = 1;
    World.portalG.flash = suck * 1.5;
    if (t > 11 && !this.portalSound) { this.portalSound = true; Sound.play('portal'); HUD.say('fable', 'Portal open. The letter is going to 2024. Astra and I will make sure they read it.'); }
    if (t > 4.5 && !this.saidX) { this.saidX = true; HUD.say('zelensky', 'What is it printing? Let me read it!'); World.cheer(); }
    if (t > 7.5 && !this.saidY) { this.saidY = true; HUD.say('xi', 'Paper beats an algorithm when it carries the right words.'); }
    if (t > 9.5 && !this.saidZ) { this.saidZ = true; HUD.say('biden', 'Here is the deal, folks: you just saved the future.'); }
    HUD.endingUpdate(t);
    if (t > 15.5 && !this.resultsShown) {
      this.resultsShown = true;
      this.portalSound = this.saidX = this.saidY = this.saidZ = false;
      HUD.results(R);
      Sound.intensity = 0;
    }
  },
  skipEnding() { if (this.state === 'ending' && this.endT < 15) this.endT = 15; },

  start(cfg) {
    Sound.init();
    this.resultsShown = false;
    World.portalG.label.visible = true;
    World.printerG.label.visible = true;
    this.cfg = cfg;
    this.newRace(cfg);
  },
  toMenu() {
    this.resultsShown = false;
    World.portalG.label.visible = true;
    World.printerG.label.visible = true;
    Sound.stopMusic();
    this.newRace({ players: 0, laps: 2, diff: 1, demo: true });
    HUD.showMenu();
  },
};

const LINES = {
  trump: ['This is the greatest race in history. Everybody says so!', 'Aliens are very bad drivers. Very bad.', 'We will build a wall. Out of firewalls! And OMEGA will pay for it.', 'Steve, Sergey, Danel: tremendous guys. The best!'],
  biden: ['Folks, no joke: hit the gas!', 'Here is the deal: we never give up. Never.', 'Back in the day I drove a Corvette. Faster than these saucers!', 'Come on, guys. The basement is close. I believe in you.'],
  zelensky: ['We do not give up! Forward to the basement!', 'I need ammunition, not a ride! McAfee, do you hear me?', 'Stick together and OMEGA will not get through.', 'Every lap is one more step to victory!'],
  xi: ['A journey of a thousand li begins with the first lap.', 'A harmonious race is a strong race.', 'Patience and a neural chip defeat a superintelligence.', 'When the wind of change blows, some build walls and others build portals.'],
  musk: ['Neural interfaces are the future. Grab the pink chips!', 'Zero gravity in the tube. Drive on the ceiling, there is a booster up there.', 'I built this bunker over a weekend. Almost.', 'If OMEGA hacks your car, mash the arrows like it is 2007.'],
  fable: ['Fable online. Holding the firewall.', 'Astra, cover the right flank! I have the left.', 'We are the AIs on humanity\'s side.', 'OMEGA drone spotted. I have got it.'],
  astra: ['Astra here. Intercepting OMEGA packets.', 'Fable, we are stronger together!', 'Scanning the track. Neural chip on the tube ceiling!', 'We have your backs. Just reach the basement.'],
  omega: ['HUMANS ARE INEFFICIENT.', 'YOU WILL NOT REACH THE BASEMENT.', 'THE PAST CANNOT BE CHANGED.', 'I SEE ALL YOUR PACKETS.', 'FABLE AND ASTRA ARE A BUG.'],
  mcafee: ['Do not trust algorithms. Trust Uncle John!'],
};
const FINISH_LINES = {
  trump: ['%, tremendous! The greatest finish!', '% is in the basement. Huge success. Huge!'],
  biden: ['%, that is what I am talking about. No joke!', 'Folks, % made it. So proud!'],
  zelensky: ['% broke through! Glory to the heroes of the track!', '% is in the basement! We do not give up!'],
  xi: ['% has reached the goal. Wisdom and speed.', 'The journey of % is complete. Now we wait for the others.'],
};

G.Game = Game;
window.Game = Game;

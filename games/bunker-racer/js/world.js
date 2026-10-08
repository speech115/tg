'use strict';
// Scenery and characters. Models come from Blender (assets/*.glb); sky, Earth, OMEGA,
// holograms and glows are shaders. Lighting: one shadow-casting sun + an HDR environment
// map baked from the nebula sky.
const NOISE_GLSL = `
  float hash3(vec3 p){ p = fract(p * 0.3183099 + 0.1); p *= 17.0; return fract(p.x * p.y * p.z * (p.x + p.y + p.z)); }
  float noise3(vec3 x){ vec3 i = floor(x); vec3 f = fract(x); f = f * f * (3.0 - 2.0 * f);
    return mix(mix(mix(hash3(i), hash3(i + vec3(1,0,0)), f.x), mix(hash3(i + vec3(0,1,0)), hash3(i + vec3(1,1,0)), f.x), f.y),
               mix(mix(hash3(i + vec3(0,0,1)), hash3(i + vec3(1,0,1)), f.x), mix(hash3(i + vec3(0,1,1)), hash3(i + vec3(1,1,1)), f.x), f.y), f.z); }
  float fbm(vec3 p){ float a = 0.5, s = 0.0; for (int i = 0; i < 6; i++) { s += a * noise3(p); p *= 2.03; a *= 0.5; } return s; }`;

const SUN_DIR = new V3(0.62, 0.38, -0.69).normalize();

const World = {
  anim: [],

  build(scene, renderer) {
    this.scene = scene;
    this.renderer = renderer;
    this.lights(scene);
    this.sky(scene, renderer);
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

  lights(scene) {
    scene.add(new THREE.HemisphereLight(0x8fa6ff, 0x3a1020, 0.35));
    const sun = new THREE.DirectionalLight(0xfff0dc, 3.2);
    sun.castShadow = true;
    sun.shadow.mapSize.set(2048, 2048);
    const sc = sun.shadow.camera;
    sc.left = -55; sc.right = 55; sc.top = 55; sc.bottom = -55; sc.near = 10; sc.far = 600;
    sun.shadow.bias = -0.0004;
    sun.shadow.normalBias = 0.6;
    scene.add(sun); scene.add(sun.target);
    this.sun = sun;
  },
  focusShadow(p) {
    if (!p) return;
    this.sun.target.position.copy(p);
    this.sun.position.copy(p).addScaledVector(SUN_DIR, 300);
    this.sun.target.updateMatrixWorld();
  },

  // Nebula + stars rendered once into a cube map; the same sky (plus a few bright
  // panels) becomes the PMREM environment that lights every PBR material.
  skyMaterial() {
    return new THREE.ShaderMaterial({
      side: THREE.BackSide, depthWrite: false,
      vertexShader: 'varying vec3 vDir; void main(){ vDir = position; gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }',
      fragmentShader: `varying vec3 vDir; ${NOISE_GLSL}
        vec3 stars(vec3 d, float cells, float thr, float k){
          vec3 sp = d * cells; vec3 cell = floor(sp); float h = hash3(cell);
          if (h < thr) return vec3(0.0);
          vec3 cpos = cell + 0.5 + (vec3(hash3(cell + 1.3), hash3(cell + 2.7), hash3(cell + 4.1)) - 0.5) * 0.6;
          float b = smoothstep(0.42, 0.0, length(sp - cpos)) * (h - thr) / (1.0 - thr);
          return mix(vec3(0.65, 0.78, 1.0), vec3(1.0, 0.82, 0.6), hash3(cell + 9.0)) * b * k;
        }
        void main(){
          vec3 d = normalize(vDir);
          float n1 = fbm(d * 2.1 + 3.1);
          float n2 = fbm(d * 4.2 + vec3(n1 * 2.2));
          float band = exp(-pow(dot(d, normalize(vec3(0.35, 1.0, 0.25))) * 3.0, 2.0));
          vec3 col = vec3(0.003, 0.004, 0.01);
          col += vec3(0.32, 0.07, 0.55) * pow(n2, 3.2) * 1.9;
          col += vec3(0.02, 0.32, 0.42) * pow(fbm(d * 3.0 + 7.0), 4.0) * 2.4;
          col += vec3(0.65, 0.08, 0.14) * pow(fbm(d * 2.0 - 4.0), 5.0) * 2.6;
          col += vec3(0.4, 0.36, 0.46) * band * pow(n1, 2.0) * 0.9;
          col *= 0.55 + 0.45 * smoothstep(0.28, 0.7, fbm(d * 9.0));
          col += stars(d, 300.0, 0.982, 5.0) + stars(d, 110.0, 0.994, 14.0);
          gl_FragColor = vec4(col, 1.0);
        }`,
    });
  },
  sky(scene, renderer) {
    const skyScene = new THREE.Scene();
    skyScene.add(new THREE.Mesh(new THREE.SphereGeometry(100, 64, 32), this.skyMaterial()));
    const sunDisc = new THREE.Mesh(new THREE.SphereGeometry(4, 16, 8), new THREE.MeshBasicMaterial({ color: new THREE.Color(1, 0.95, 0.85).multiplyScalar(40) }));
    sunDisc.position.copy(SUN_DIR).multiplyScalar(90);
    skyScene.add(sunDisc);
    const cubeRT = new THREE.WebGLCubeRenderTarget(1024, { type: THREE.HalfFloatType, generateMipmaps: true, minFilter: THREE.LinearMipmapLinearFilter });
    const cubeCam = new THREE.CubeCamera(1, 1000, cubeRT);
    cubeCam.update(renderer, skyScene);
    scene.background = cubeRT.texture;
    // environment: sky + soft key/fill panels (warm sun side, cold nebula side, red Earth bounce)
    const envScene = skyScene.clone();
    const panel = (color, k, pos, size) => {
      const m = new THREE.Mesh(new THREE.PlaneGeometry(size, size), new THREE.MeshBasicMaterial({ color: new THREE.Color(color).multiplyScalar(k), side: THREE.DoubleSide }));
      m.position.copy(pos); m.lookAt(0, 0, 0); envScene.add(m);
    };
    panel(0xffe2c0, 2.6, SUN_DIR.clone().multiplyScalar(60), 50);
    panel(0x6fa0ff, 0.8, new V3(-60, 30, 40), 70);
    panel(0xff3050, 0.22, new V3(-20, -70, -40), 90);
    panel(0xc8d8ff, 0.4, new V3(0, 80, 0), 80);
    const pmrem = new THREE.PMREMGenerator(renderer);
    scene.environment = pmrem.fromScene(envScene, 0.02).texture;
    pmrem.dispose();
    // visible sun: hot core + wide glare + anamorphic streak
    const glare = glowSprite(0xfff0c8, 380, 1, 1.8); glare.position.copy(SUN_DIR).multiplyScalar(3000); scene.add(glare);
    const halo = glowSprite(0xffb070, 1300, 0.1, 1); halo.position.copy(glare.position); scene.add(halo);
    const streak = glowSprite(0xbfd8ff, 1, 0.12, 1.2); streak.scale.set(3600, 50, 1); streak.position.copy(glare.position); scene.add(streak);
  },

  earth(scene) {
    const day = canvasTex(2048, 1024, (g, w, h) => {
      g.fillStyle = '#0a1d44'; g.fillRect(0, 0, w, h);
      for (let i = 0; i < 46; i++) {
        const x = Math.random() * w, y = h * (0.18 + Math.random() * 0.64);
        g.fillStyle = `rgb(${70 + Math.random() * 30},${48 + Math.random() * 20},${36})`;
        g.beginPath();
        const r = 50 + Math.random() * 150;
        for (let a = 0; a < TAU; a += 0.3) { const rr = r * (0.55 + Math.random() * 0.55); g.lineTo(x + Math.cos(a) * rr * 1.7, y + Math.sin(a) * rr); }
        g.fill();
      }
      g.fillStyle = '#e8eef5'; g.fillRect(0, 0, w, h * 0.05); g.fillRect(0, h * 0.95, w, h * 0.05);
    });
    const lights = canvasTex(2048, 1024, (g, w, h) => {
      g.fillStyle = '#000'; g.fillRect(0, 0, w, h);
      g.strokeStyle = 'rgba(255,40,60,0.85)'; g.lineWidth = 2;
      for (let i = 0; i < 220; i++) {
        let x = Math.random() * w, y = h * (0.2 + Math.random() * 0.6);
        g.beginPath(); g.moveTo(x, y);
        for (let k = 0; k < 6; k++) { if (Math.random() < 0.5) x += rand(-60, 60); else y += rand(-40, 40); g.lineTo(x, y); }
        g.stroke();
      }
      for (let i = 0; i < 1600; i++) { g.fillStyle = Math.random() < 0.85 ? '#ff2a40' : '#ffb070'; g.fillRect(Math.random() * w, h * (0.15 + Math.random() * 0.7), 2, 2); }
    });
    const clouds = canvasTex(1024, 512, (g, w, h) => {
      g.clearRect(0, 0, w, h);
      for (let i = 0; i < 160; i++) {
        g.fillStyle = `rgba(255,255,255,${rand(0.05, 0.25)})`;
        g.beginPath(); g.ellipse(Math.random() * w, h * (0.1 + Math.random() * 0.8), rand(20, 120), rand(6, 22), rand(-0.3, 0.3), 0, TAU); g.fill();
      }
    });
    const pos = new V3(-700, -1500, -2300);
    const earth = new THREE.Mesh(new THREE.SphereGeometry(1100, 96, 48), new THREE.MeshStandardMaterial({
      map: day, emissiveMap: lights, emissive: 0xffffff, emissiveIntensity: 2.2, roughness: 0.75, metalness: 0,
    }));
    earth.position.copy(pos); earth.rotation.z = 0.4;
    scene.add(earth);
    const cl = new THREE.Mesh(new THREE.SphereGeometry(1112, 64, 32), new THREE.MeshStandardMaterial({ map: clouds, transparent: true, depthWrite: false, roughness: 1 }));
    cl.position.copy(pos); scene.add(cl);
    const atm = new THREE.Mesh(new THREE.SphereGeometry(1190, 64, 32), new THREE.ShaderMaterial({
      side: THREE.BackSide, transparent: true, depthWrite: false, blending: THREE.AdditiveBlending,
      uniforms: { sun: { value: SUN_DIR } },
      vertexShader: 'varying vec3 vN; varying vec3 vV; void main(){ vec4 wp = modelMatrix * vec4(position,1.0); vN = normalize(mat3(modelMatrix) * normal); vV = normalize(cameraPosition - wp.xyz); gl_Position = projectionMatrix * viewMatrix * wp; }',
      fragmentShader: `uniform vec3 sun; varying vec3 vN; varying vec3 vV;
        void main(){ float f = pow(clamp(1.0 + dot(vV, vN) * 1.25, 0.0, 1.0), 3.0);
          float lit = 0.35 + 0.65 * clamp(dot(-vN, sun) * 0.5 + 0.5, 0.0, 1.0);
          vec3 c = mix(vec3(1.0, 0.12, 0.2), vec3(0.35, 0.65, 1.0), lit);
          gl_FragColor = vec4(c * f * 2.4, f); }`,
    }));
    atm.position.copy(pos); scene.add(atm);
    this.anim.push((dt) => { earth.rotation.y += dt * 0.008; cl.rotation.y += dt * 0.011; });
    const lab = labelSprite('EARTH · UNDER OMEGA CONTROL', { color: '#ff4a5a', scale: 18, depthTest: false });
    lab.position.set(-500, -350, -1700); scene.add(lab);
  },

  bunker(scene) {
    const b = asset('bunker', 'Bunker', { cast: false, env: 0.35 });
    const lamp = findMat(b, 'Lamp'); if (lamp) lamp.emissiveIntensity = 3.5;
    const haz = findMat(b, 'Hazard'); if (haz) haz.emissiveIntensity = 1.4;
    const win = findMat(b, 'Window'); if (win) win.emissiveIntensity = 3;
    scene.add(b);
    this.bunkerG = b;
    const dish = b.getObjectByName('Dish');
    if (dish) this.anim.push((dt) => { dish.rotation.y += dt * 0.4; });
    for (const x of [-120, -40, 40, 110]) {
      const l = new THREE.PointLight(0xdfe8ff, 520, 0, 2); l.position.set(x, 12, 285); scene.add(l);
    }
    const hall = new THREE.PointLight(0xffd0a0, 450, 0, 2); hall.position.set(-85, -10, 250); scene.add(hall);
    // thruster plumes under the floating bunker
    for (const x of [-120, -40, 40, 110]) for (const z of [250, 325]) {
      const fl = glowSprite(0x50a8ff, 34, 0.9, 2.5); fl.position.set(x, -78, z); scene.add(fl);
      const fl2 = glowSprite(0xbfe8ff, 16, 1, 3); fl2.position.set(x, -72, z); scene.add(fl2);
      this.anim.push((dt, t) => { const k = 1 + Math.sin(t * 30 + x + z) * 0.08; fl.scale.set(34 * k, 46 * k, 1); });
    }
    // signage and halo rings
    const s1 = labelSprite('BASEMENT B-1 · CHRONO-PORTAL', { color: '#ffb000', scale: 3.4 });
    s1.position.set(-60, 14, 300); scene.add(s1);
    const s2 = labelSprite('BUNKER-0', { color: '#ffb000', scale: 12, font: '900 64px "Unbounded", sans-serif', h: 96 });
    s2.position.set(-10, 70, 290); scene.add(s2);
    const ring = new THREE.Mesh(new THREE.TorusGeometry(130, 1.2, 8, 160), glowMat(0xffb000, 0.8, 3));
    ring.position.set(-10, 78, 290); ring.rotation.x = Math.PI / 2; scene.add(ring);
    const ring2 = new THREE.Mesh(new THREE.TorusGeometry(112, 0.6, 8, 160), glowMat(0x35e0ff, 0.7, 3));
    ring2.position.copy(ring.position); ring2.rotation.x = Math.PI / 2; scene.add(ring2);
    this.anim.push((dt, t) => { ring.rotation.z += dt * 0.08; ring2.rotation.z -= dt * 0.12; ring2.position.y = 78 + Math.sin(t * 0.7) * 4; });
    // beacons on the masts blink
    const beacon = findMat(b, 'Beacon');
    if (beacon) this.anim.push((dt, t) => { beacon.emissiveIntensity = Math.sin(t * 4) > 0 ? 14 : 1; });
  },

  omega(scene) {
    const g = new THREE.Group();
    g.position.set(0, 75, 0);
    const coreMat = new THREE.ShaderMaterial({
      uniforms: { t: { value: 0 }, stun: { value: 0 } },
      vertexShader: 'varying vec3 vP; varying vec3 vN; varying vec3 vV; void main(){ vP = position; vec4 wp = modelMatrix * vec4(position,1.0); vN = normalize(mat3(modelMatrix) * normal); vV = normalize(cameraPosition - wp.xyz); gl_Position = projectionMatrix * viewMatrix * wp; }',
      fragmentShader: `uniform float t; uniform float stun; varying vec3 vP; varying vec3 vN; varying vec3 vV; ${NOISE_GLSL}
        void main(){
          vec3 p = normalize(vP);
          vec3 q = p * 9.0; vec3 gcell = abs(fract(q) - 0.5);
          float grid = smoothstep(0.47, 0.5, max(max(gcell.x, gcell.y), gcell.z));
          float pulse = smoothstep(0.6, 1.0, sin(dot(floor(q), vec3(1.7, 2.3, 3.1)) + t * 3.0));
          float n = fbm(p * 4.0 + t * 0.15);
          float fres = pow(1.0 - max(dot(vN, vV), 0.0), 2.5);
          vec3 base = vec3(0.05, 0.0, 0.01) + vec3(0.35, 0.02, 0.05) * n;
          vec3 col = base + vec3(3.5, 0.15, 0.3) * grid * (0.35 + pulse) + vec3(2.5, 0.2, 0.35) * fres;
          col *= mix(1.0, 0.25 + 0.75 * step(0.5, fract(t * 8.0)), stun);
          gl_FragColor = vec4(col, 1.0);
        }`,
    });
    const core = new THREE.Mesh(new THREE.SphereGeometry(26, 64, 32), coreMat);
    g.add(core);
    const eye = new THREE.Group();
    const irisMat = new THREE.ShaderMaterial({
      uniforms: { t: { value: 0 }, stun: { value: 0 } },
      vertexShader: 'varying vec2 vUv; void main(){ vUv = uv; gl_Position = projectionMatrix * modelViewMatrix * vec4(position,1.0); }',
      fragmentShader: `uniform float t; uniform float stun; varying vec2 vUv;
        void main(){ vec2 p = vUv * 2.0 - 1.0; float r = length(p); float a = atan(p.y, p.x);
          float rays = 0.6 + 0.4 * sin(a * 40.0 + sin(r * 30.0 - t * 4.0) * 2.0);
          vec3 c = mix(vec3(5.0, 0.3, 0.2), vec3(1.2, 0.0, 0.05), smoothstep(0.1, 0.95, r)) * rays;
          c = mix(c, vec3(8.0, 6.0, 3.0), smoothstep(0.24, 0.12, r) * (1.0 - stun));
          c *= smoothstep(1.0, 0.92, r) * mix(1.0, 0.3, stun);
          gl_FragColor = vec4(c, 1.0); }`,
    });
    const iris = new THREE.Mesh(new THREE.CircleGeometry(13, 64), irisMat);
    iris.position.z = 26.2; eye.add(iris);
    const rim = new THREE.Mesh(new THREE.TorusGeometry(13.6, 1.4, 12, 64), new THREE.MeshStandardMaterial({ color: 0x15161c, metalness: 1, roughness: 0.25 }));
    rim.position.z = 25.6; eye.add(rim);
    const eg = glowSprite(0xff2040, 70, 0.9, 2); eg.position.z = 32; eye.add(eg);
    g.add(eye);
    const cage = new THREE.LineSegments(new THREE.EdgesGeometry(new THREE.IcosahedronGeometry(42, 1)),
      new THREE.LineBasicMaterial({ color: new THREE.Color(2.4, 0.15, 0.25), transparent: true, opacity: 0.7 }));
    g.add(cage);
    const plates = new THREE.Group();
    const plateMat = new THREE.MeshStandardMaterial({ color: 0x22252e, metalness: 0.9, roughness: 0.3, emissive: 0x330004 });
    for (let i = 0; i < 10; i++) {
      const p = new THREE.Mesh(new THREE.BoxGeometry(14, 2, 4), plateMat);
      const a = (i / 10) * TAU;
      p.position.set(Math.cos(a) * 34, Math.sin(a * 2) * 6, Math.sin(a) * 34);
      p.lookAt(0, 0, 0);
      plates.add(p);
    }
    g.add(plates);
    const r1 = new THREE.Mesh(new THREE.TorusGeometry(56, 0.9, 8, 120), glowMat(0xff2a3d, 0.85, 3)); g.add(r1);
    const r2 = new THREE.Mesh(new THREE.TorusGeometry(64, 0.45, 8, 120), glowMat(0xff6a3d, 0.6, 3)); g.add(r2);
    const halo = glowSprite(0xff1030, 300, 0.4, 1.4); g.add(halo);
    const light = new THREE.PointLight(0xff2030, 30000, 235, 2); g.add(light);
    const lab = labelSprite('OMEGA · SUPERINTELLIGENCE', { color: '#ff2a3d', scale: 5 }); lab.position.y = 82; g.add(lab);
    scene.add(g);
    this.omegaG = { g, eye, stun: 0, target: new V3(0, 0, 300) };
    const tmp = new V3();
    this.anim.push((dt, t) => {
      const o = this.omegaG;
      const stunned = o.stun > 0 ? 1 : 0;
      coreMat.uniforms.t.value = t; coreMat.uniforms.stun.value = stunned;
      irisMat.uniforms.t.value = t; irisMat.uniforms.stun.value = stunned;
      cage.rotation.y += dt * 0.25; cage.rotation.x += dt * 0.1;
      plates.rotation.y -= dt * 0.18;
      r1.rotation.x = t * 0.6; r1.rotation.y = t * 0.3;
      r2.rotation.x = -t * 0.4; r2.rotation.z = t * 0.5;
      tmp.copy(o.target).sub(g.position).normalize().add(g.position);
      eye.lookAt(tmp.x, tmp.y, tmp.z);
      const pulse = 0.5 + 0.5 * Math.sin(t * (stunned ? 20 : 2.5));
      halo.material.opacity = stunned ? 0.1 + pulse * 0.15 : 0.25 + pulse * 0.25;
      light.intensity = stunned ? 5000 : 22000 + pulse * 16000;
    });
  },

  portal(scene) {
    const f = Track.frame(0);
    const g = new THREE.Group();
    g.position.copy(f.P).addScaledVector(f.U, 6);
    const m = new THREE.Matrix4().makeBasis(f.B, f.U, f.T.clone().negate());
    g.quaternion.setFromRotationMatrix(m);
    const ring = asset('props', 'Portal');
    g.add(ring);
    const emitters = [];
    for (let i = 0; i < 12; i++) {
      const e = ring.getObjectByName(`Emitter_${i}`);
      if (e) { e.material = e.material.clone(); emitters.push(e.material); }
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
          gl_FragColor = vec4(c * 3.0 * alpha, alpha); }`,
    });
    const disc = new THREE.Mesh(new THREE.CircleGeometry(15.6, 64), mat);
    g.add(disc);
    const lab = labelSprite('CHRONO-PORTAL → 2024', { color: '#35e0ff', scale: 1.3 });
    lab.position.y = 22.5; g.add(lab);
    const glow = glowSprite(0x60b0ff, 60, 0.3); g.add(glow);
    scene.add(g);
    this.portalG = { g, mat, glow, charge: 0, flash: 0, label: lab };
    const on = new THREE.Color(0x35e0ff), off = new THREE.Color(0x182030);
    this.anim.push((dt, t) => {
      const p = this.portalG;
      mat.uniforms.t.value = t;
      p.flash = Math.max(0, p.flash - dt * 1.5);
      mat.uniforms.power.value = 0.07 + p.charge * 0.35 + p.flash;
      glow.material.opacity = 0.08 + p.charge * 0.3 + p.flash;
      emitters.forEach((em, i) => { const lit = i / 12 < p.charge; em.emissive.copy(lit ? on : off); em.color.copy(lit ? on : off); em.emissiveIntensity = lit ? 6 + Math.sin(t * 6 + i) * 2 : 0.3; });
    });
  },

  character(name) {
    const c = asset('characters', name);
    c.userData.arms = [c.getObjectByName(`${name}_ArmL`), c.getObjectByName(`${name}_ArmR`)];
    return c;
  },

  LEADERS: [
    { id: 'trump', asset: 'Trump', name: 'TRUMP' },
    { id: 'biden', asset: 'Biden', name: 'BIDEN' },
    { id: 'zelensky', asset: 'Zelensky', name: 'ZELENSKY' },
    { id: 'xi', asset: 'Xi', name: 'XI JINPING' },
  ],

  summit(scene) {
    const s = Track.cpAt(4.15);
    const f = Track.frame(s);
    const out = new V3(f.P.x, 0, f.P.z - 20).normalize();
    const base = f.P.clone().addScaledVector(out, 42).add(new V3(0, 2, 0));
    const g = new THREE.Group(); g.position.copy(base);
    const metal = new THREE.MeshStandardMaterial({ color: 0x2b3242, metalness: 0.85, roughness: 0.35 });
    const plat = new THREE.Mesh(new THREE.CylinderGeometry(20, 15, 3, 48), metal);
    plat.receiveShadow = true; g.add(plat);
    const under = new THREE.Mesh(new THREE.ConeGeometry(14, 10, 32), metal); under.position.y = -6.5; under.rotation.x = Math.PI; g.add(under);
    const edge = new THREE.Mesh(new THREE.TorusGeometry(20, 0.35, 8, 96), glowMat(0xffb000, 0.95, 3)); edge.rotation.x = Math.PI / 2; edge.position.y = 1.5; g.add(edge);
    const carpet = new THREE.Mesh(new THREE.BoxGeometry(28, 0.2, 7), new THREE.MeshStandardMaterial({ color: 0x8a1020, roughness: 0.9 }));
    carpet.position.y = 1.6; carpet.receiveShadow = true; g.add(carpet);
    const lect = new THREE.Mesh(new THREE.BoxGeometry(30, 3, 1), new THREE.MeshStandardMaterial({ color: 0xeeeeee, metalness: 0.2, roughness: 0.4, transparent: true, opacity: 0.35 }));
    lect.position.set(0, 3, 4); g.add(lect);
    const under2 = glowSprite(0x50a8ff, 36, 0.8, 2.5); under2.position.y = -12; g.add(under2);
    const look = f.P.clone(); look.y = base.y;
    g.lookAt(look);
    this.leaders = [];
    this.LEADERS.forEach((L, i) => {
      const p = this.character(L.asset);
      p.scale.setScalar(2.7);
      p.position.set(-10.5 + i * 7, 1.7, 0);
      g.add(p);
      const lab = labelSprite(L.name, { color: '#e9ecf5', scale: 1.1 });
      lab.position.set(-10.5 + i * 7, 9.4, 0); g.add(lab);
      this.leaders.push({ p, id: L.id, cheer: 0 });
    });
    const banner = labelSprite('LAST HOPE SUMMIT', { color: '#ffb000', scale: 2.4 });
    banner.position.set(0, 15, 0); g.add(banner);
    const spot = new THREE.SpotLight(0xfff0e0, 2500, 0, 0.6, 0.5, 2);
    spot.position.set(0, 30, 25); spot.target.position.set(0, 2, 0); g.add(spot); g.add(spot.target);
    scene.add(g);
    this.anim.push((dt, t) => {
      this.leaders.forEach((l, i) => {
        l.cheer = Math.max(0, l.cheer - dt);
        const amp = l.cheer > 0 ? 1 : 0.25;
        const [a, b] = l.p.userData.arms;
        if (b) b.rotation.z = Math.PI - 0.5 + Math.sin(t * (l.cheer > 0 ? 12 : 3) + i) * 0.5 * amp;
        if (a) a.rotation.z = l.cheer > 0 ? -Math.PI + 0.5 - Math.sin(t * 12 + i) * 0.5 : -0.08;
        l.p.position.y = 1.7 + (l.cheer > 0 ? Math.abs(Math.sin(t * 10 + i)) * 0.8 : 0);
      });
    });
  },
  cheer(id) { (this.leaders || []).forEach((l) => { if (!id || l.id === id) l.cheer = 3; }); },

  printer(scene) {
    const g = new THREE.Group();
    g.position.set(-85, -54, 252);
    const model = asset('printer', 'Printer');
    g.add(model);
    const screenTex = canvasTex(512, 256, () => {});
    const screen = new THREE.Mesh(new THREE.PlaneGeometry(12, 5.2), new THREE.MeshBasicMaterial({ map: screenTex, color: new THREE.Color(2, 2, 2) }));
    screen.position.set(20.5, 21.95, 21.25); screen.rotation.x = -0.6;
    g.add(screen);
    this.printerScreen = screenTex;
    const plate = canvasTex(1024, 128, (c, w, h) => {
      c.fillStyle = '#d9dde6'; c.fillRect(0, 0, w, h);
      c.fillStyle = '#14161c'; c.font = '900 76px "Unbounded", sans-serif'; c.textBaseline = 'middle';
      c.fillText('GIGAPRINTER-9000', 30, h / 2 + 4);
    });
    const pl = new THREE.Mesh(new THREE.PlaneGeometry(40, 5), new THREE.MeshStandardMaterial({ map: plate, metalness: 0.3, roughness: 0.4 }));
    pl.position.set(-8, 6.5, 18.36); g.add(pl);
    const leds = findMat(model, 'Neon');
    const led = leds ? leds.clone() : null;
    if (led) model.traverse((m) => { if (m.isMesh && m.material === leds) m.material = led; });
    const lab = labelSprite('GIGAPRINTER WAITS FOR ALL THREE', { color: '#e9ecf5', scale: 2.4 });
    lab.position.set(0, 50, 0); g.add(lab);
    scene.add(g);
    this.printerG = { g, shake: 0, base: g.position.clone(), outPos: new V3(-85, -54 + 17, 252 + 20), label: lab };
    this.setPrinterStatus(0, 3);
    this.anim.push((dt, t) => {
      const p = this.printerG;
      if (led) {
        led.emissive.setHex(p.shake > 0 ? 0xff40a0 : 0x35ff80);
        led.emissiveIntensity = (Math.sin(t * 3) > 0.3 || p.shake > 0) ? 6 : 0.4;
      }
      if (p.shake > 0) g.position.set(p.base.x + rand(-0.4, 0.4), p.base.y + rand(-0.3, 0.3), p.base.z + rand(-0.4, 0.4));
      else g.position.copy(p.base);
    });
  },
  setPrinterStatus(n, total, printing) {
    const tex = this.printerScreen; const c = tex.userData.canvas.getContext('2d');
    c.fillStyle = '#04120a'; c.fillRect(0, 0, 512, 256);
    c.fillStyle = printing ? '#ff70c0' : '#35ff80';
    c.font = '700 40px "JetBrains Mono", monospace';
    c.fillText(printing ? 'PRINTING...' : 'WAITING', 24, 70);
    c.font = '700 64px "JetBrains Mono", monospace';
    c.fillText(`HUMANS ${n}/${total}`, 24, 160);
    c.fillRect(24, 196, 464 * (n / total), 24);
    c.strokeStyle = c.fillStyle; c.strokeRect(24, 196, 464, 24);
    tex.needsUpdate = true;
  },

  hologramMaterial(color = 0x35e0ff) {
    return new THREE.ShaderMaterial({
      uniforms: { t: { value: 0 }, color: { value: new THREE.Color(color) } },
      transparent: true, depthWrite: false, blending: THREE.AdditiveBlending, side: THREE.DoubleSide,
      vertexShader: 'varying vec3 vN; varying vec3 vV; varying vec3 vW; void main(){ vec4 wp = modelMatrix * vec4(position,1.0); vW = wp.xyz; vN = normalize(mat3(modelMatrix) * normal); vV = normalize(cameraPosition - wp.xyz); gl_Position = projectionMatrix * viewMatrix * wp; }',
      fragmentShader: `uniform float t; uniform vec3 color; varying vec3 vN; varying vec3 vV; varying vec3 vW;
        void main(){ float f = pow(1.0 - abs(dot(vN, vV)), 1.6);
          float scan = 0.55 + 0.45 * step(0.5, fract(vW.y * 1.6 - t * 2.0));
          float flick = 0.85 + 0.15 * sin(t * 37.0);
          gl_FragColor = vec4(color * (0.25 + f * 2.2) * scan * flick * 1.6, 0.35 + f * 0.5); }`,
    });
  },
  musk(scene) {
    const p = this.character('Musk');
    const holo = this.hologramMaterial();
    p.traverse((m) => { if (m.isMesh) { m.material = holo; m.castShadow = false; } });
    p.scale.setScalar(6);
    const g = new THREE.Group();
    g.position.set(45, -41.5, 334);
    g.add(p);
    const beam = new THREE.Mesh(new THREE.CylinderGeometry(5, 6, 14, 32, 1, true), glowMat(0x35e0ff, 0.1, 2));
    beam.position.y = 7; g.add(beam);
    const lab = labelSprite('ELON MUSK · HOLOGRAM', { color: '#35e0ff', scale: 1.6 });
    lab.position.y = 17; g.add(lab);
    g.lookAt(45, -41.5, 290);
    scene.add(g);
    this.muskG = p;
    this.anim.push((dt, t) => {
      holo.uniforms.t.value = t;
      p.visible = Math.random() > 0.02;
      p.position.y = Math.sin(t * 1.3) * 0.3;
      const armR = p.userData.arms[1];
      if (armR) { armR.rotation.z = Math.PI * 0.6 + Math.sin(t * 2) * 0.3; armR.rotation.x = -0.4; }
    });
  },

  rocket(scale = 1) {
    const g = new THREE.Group();
    const r = asset('props', 'Rocket', { cast: false });
    g.add(r);
    const fl = glowSprite(0xffa040, 4, 1, 3); fl.position.z = -4.9; g.add(fl);
    const fl2 = glowSprite(0xffffff, 2, 1, 3); fl2.position.z = -4.4; g.add(fl2);
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
        s.r.lookAt(pos(s.a + Math.sign(s.sp) * 0.01).clone());
      }
    });
  },

  asteroids(scene) {
    const lib = window.ASSETS.props;
    const geos = [0, 1, 2, 3].map((i) => {
      let geo = null;
      const node = lib.getObjectByName(`Rock_${i}`);
      if (node) node.traverse((m) => { if (!geo && m.isMesh) geo = m.geometry; });
      return geo;
    }).filter(Boolean);
    const rockMat = new THREE.MeshStandardMaterial({ color: 0x6a625c, roughness: 0.95, metalness: 0.05 });
    const per = 22;
    const meshes = geos.map((geo) => { const im = new THREE.InstancedMesh(geo, rockMat, per); scene.add(im); return im; });
    const rocks = [];
    let tries = 0;
    while (rocks.length < per * meshes.length && tries++ < 4000) {
      const p = new V3(rand(-950, 950), rand(-320, 320), rand(-850, 950));
      let ok = p.length() > 130;
      for (let i = 0; i < Track.N && ok; i += 6) if (Track.P[i].distanceTo(p) < 75) ok = false;
      if (p.distanceTo(new V3(-10, 0, 290)) < 230) ok = false;
      if (!ok) continue;
      const k = rand(4, 24);
      rocks.push({ p, sc: new V3(k * rand(0.7, 1.3), k * rand(0.6, 1.1), k * rand(0.7, 1.3)), r: new THREE.Euler(rand(0, 6), rand(0, 6), rand(0, 6)), spin: new V3(rand(-0.2, 0.2), rand(-0.2, 0.2), 0) });
    }
    meshes.forEach((im) => { im.count = 0; });
    const m4 = new THREE.Matrix4(), q = new THREE.Quaternion();
    this.anim.push((dt) => {
      meshes.forEach((im) => { im.count = 0; });
      rocks.forEach((r, i) => {
        r.r.x += r.spin.x * dt; r.r.y += r.spin.y * dt;
        const im = meshes[i % meshes.length];
        m4.compose(r.p, q.setFromEuler(r.r), r.sc); im.setMatrixAt(im.count++, m4);
      });
      meshes.forEach((im) => { im.instanceMatrix.needsUpdate = true; });
    });
  },

  update(dt, t) { for (const f of this.anim) f(dt, t); },
};
G.World = World;

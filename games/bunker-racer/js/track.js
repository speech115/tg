'use strict';
// The orbital circuit around Bunker-0. Everything lives in "track space":
// s = distance along the spline, d = lateral offset, h = height above surface.
// Zones: low gravity with a jump gap, a zero-G tube you can drive around,
// heavy gravity with a corkscrew, and the bunker basement with the chrono-portal.
const Track = {
  W: 24, HW: 12, R: 14,
  CP: [
    [0, -30, 300], [90, -27, 300], [170, -10, 292], [250, 10, 245], [300, 20, 155],
    [312, 24, 40], [288, 30, -72], [222, 40, -170], [120, 48, -228], [0, 52, -248],
    [-120, 48, -228], [-222, 42, -168], [-292, 36, -60], [-306, 30, 60], [-282, 20, 160],
    [-222, 4, 248], [-150, -18, 292], [-80, -28, 300],
  ],
  P: [], T: [], U: [], K: [], N: 0, L: 0, DS: 2,
  zones: {}, gap: null, pads: [], boosts: [], itemRows: [], chipSpots: [],
  _f: { P: new V3(), T: new V3(), U: new V3(), B: new V3(), k: 0 },

  cpAt(x) { // fractional control-point index -> s
    const n = this.CP.length; x = mod(x, n);
    const i = Math.floor(x), t = x - i;
    const a = this.cpS[i], b = i + 1 < n ? this.cpS[i + 1] : this.L;
    return a + (b - a) * t;
  },

  build() {
    const pts = this.CP.map((p) => new V3(p[0], p[1], p[2]));
    const curve = new THREE.CatmullRomCurve3(pts, true, 'centripetal');
    this.curve = curve;
    this.L = curve.getLength();
    this.N = Math.round(this.L / 2);
    this.DS = this.L / this.N;
    const N = this.N;
    for (let i = 0; i < N; i++) {
      this.P[i] = curve.getPointAt(i / N);
      this.T[i] = curve.getTangentAt(i / N).normalize();
    }
    // s of each control point
    this.cpS = pts.map((p) => {
      let best = 0, bd = Infinity;
      for (let i = 0; i < N; i++) { const dd = this.P[i].distanceToSquared(p); if (dd < bd) { bd = dd; best = i; } }
      return best * this.DS;
    });
    this.cpS[0] = 0;
    // zones
    const z = this.zones;
    z.lowg = [this.cpAt(7.6), this.cpAt(10.3)];
    z.tube = [this.cpAt(10.75), this.cpAt(13.0)];
    z.heavy = [this.cpAt(13.35), this.cpAt(15.45)];
    z.cork = [z.heavy[0] + 45, z.heavy[1] - 45];
    z.bunker = [this.cpAt(16.25), this.cpAt(1.55) + this.L];
    this.gap = [z.lowg[0] + 95, z.lowg[0] + 152];
    this.pads = [
      { s: z.lowg[0] + 80, d0: -12, d1: 12, v: 9.5 },
      { s: z.lowg[0] + 205, d0: -12, d1: -2, v: 7 },
      { s: z.lowg[0] + 245, d0: 2, d1: 12, v: 7 },
    ];
    // curvature & frames
    const up = new V3(0, 1, 0), Ub = [], Bb = [];
    for (let i = 0; i < N; i++) {
      const T = this.T[i];
      const u = up.clone().sub(T.clone().multiplyScalar(T.dot(up))).normalize();
      Ub[i] = u; Bb[i] = new V3().crossVectors(T, u).normalize();
    }
    const Kraw = [];
    for (let i = 0; i < N; i++) {
      const a = this.T[mod(i - 3, N)], b = this.T[mod(i + 3, N)];
      Kraw[i] = b.clone().sub(a).divideScalar(6 * this.DS).dot(Bb[i]);
    }
    for (let i = 0; i < N; i++) {
      let acc = 0; for (let j = -8; j <= 8; j++) acc += Kraw[mod(i + j, N)];
      this.K[i] = acc / 17;
    }
    for (let i = 0; i < N; i++) {
      const s = i * this.DS;
      const b = this.tubeB(s);
      const inB = this.inBunker(s) ? 1 : 0;
      let roll = clamp(this.K[i] * 38, -0.42, 0.42) * (1 - b) * (1 - inB);
      const c = z.cork;
      if (s > c[0] && s < c[1]) roll += TAU * smooth((s - c[0]) / (c[1] - c[0]));
      this.U[i] = Ub[i].clone().multiplyScalar(Math.cos(roll)).add(Bb[i].clone().multiplyScalar(Math.sin(roll))).normalize();
    }
    // placements
    const R = this.R;
    this.boosts = [
      { s: this.cpAt(3.4), d: -6 }, { s: this.cpAt(6.2), d: 6 }, { s: this.cpAt(6.25), d: -6 },
      { s: (z.tube[0] + z.tube[1]) / 2 + 35, d: Math.PI * R * 0.98 },
      { s: (z.tube[0] + z.tube[1]) / 2 - 10, d: Math.PI * R * 0.5 },
      { s: z.heavy[1] - 20, d: 0 }, { s: this.cpAt(16.9), d: -6 }, { s: this.cpAt(16.9), d: 6 },
    ];
    const tm = (z.tube[0] + z.tube[1]) / 2;
    this.itemRows = [
      { s: this.cpAt(2.6), ds: [-8, -2.7, 2.7, 8] },
      { s: this.cpAt(5.3), ds: [-8, -2.7, 2.7, 8] },
      { s: this.cpAt(7.25), ds: [-6, 0, 6] },
      { s: z.lowg[0] + 228, ds: [-8, -2.7, 2.7, 8] },
      { s: tm - 40, ds: [-6, 0, 6, R * 1.6, -R * 1.6, Math.PI * R] },
      { s: this.cpAt(15.75), ds: [-8, -2.7, 2.7, 8] },
      { s: this.cpAt(0.55), ds: [-6, 0, 6] },
    ];
    this.chipSpots = [
      { s: (this.gap[0] + this.gap[1]) / 2, d: 0, h: 4.3 },
      { s: tm + 10, d: Math.PI * R * 0.999, h: 1.3 },
      { s: (z.cork[0] + z.cork[1]) / 2, d: 7, h: 1.3 },
      { s: this.cpAt(4.3), d: -9.5, h: 1.3 },
    ];
  },

  inBunker(s) {
    s = mod(s, this.L); const b = this.zones.bunker;
    return s > b[0] || s < b[1] - this.L;
  },
  tubeB(s) {
    s = mod(s, this.L); const t = this.zones.tube;
    if (s <= t[0] || s >= t[1]) return 0;
    return smooth((s - t[0]) / 32) * smooth((t[1] - s) / 32);
  },
  hw(s) { return lerp(this.HW, Math.PI * this.R, this.tubeB(s)); },
  isWrap(s) { return this.tubeB(s) > 0.999; },
  // pull back to the tube floor before the exit (gravity returns)
  tubePull(s) {
    s = mod(s, this.L); const t = this.zones.tube;
    if (s <= t[0] || s >= t[1]) return 0;
    const fromStart = s - t[0], toEnd = t[1] - s;
    if (fromStart < 60) return 26 * (1 - fromStart / 60);
    if (toEnd < 110) return 40 * smooth(1 - (toEnd - 30) / 80);
    return 0;
  },
  zoneAt(s) {
    s = mod(s, this.L); const z = this.zones;
    if (s > z.lowg[0] && s < z.lowg[1]) return 'lowg';
    if (s > z.tube[0] && s < z.tube[1]) return 'tube';
    if (s > z.heavy[0] && s < z.heavy[1]) return 'heavy';
    if (this.inBunker(s)) return 'bunker';
    return 'space';
  },
  gravity(s) {
    switch (this.zoneAt(s)) {
      case 'lowg': return 0.25;
      case 'tube': return 0.45;
      case 'heavy': return 2.2;
      default: return 1;
    }
  },
  heavyF(s) {
    s = mod(s, this.L); const z = this.zones.heavy;
    if (s <= z[0] || s >= z[1]) return 0;
    return smooth((s - z[0]) / 20) * smooth((z[1] - s) / 20);
  },
  isGap(s) { s = mod(s, this.L); return s > this.gap[0] && s < this.gap[1]; },
  wrapD(d) { const C = TAU * this.R; return mod(d + C / 2, C) - C / 2; },
  dDiff(a, b, s) { const x = a - b; return this.isWrap(s) ? this.wrapD(x) : x; },
  sDiff(a, b) { return mod(a - b + this.L / 2, this.L) - this.L / 2; },

  frame(s) {
    const f = this._f, N = this.N;
    const x = mod(s, this.L) / this.DS;
    const i = Math.floor(x) % N, j = (i + 1) % N, t = x - Math.floor(x);
    f.P.lerpVectors(this.P[i], this.P[j], t);
    f.T.lerpVectors(this.T[i], this.T[j], t).normalize();
    f.U.lerpVectors(this.U[i], this.U[j], t);
    f.U.addScaledVector(f.T, -f.T.dot(f.U)).normalize();
    f.B.crossVectors(f.T, f.U).normalize();
    f.k = lerp(this.K[i], this.K[j], t);
    return f;
  },
  // world placement of a track-space point; fills out.p/out.up/out.side/out.fwd
  place(s, d, h, out) {
    const f = this.frame(s);
    const b = this.tubeB(s);
    out.fwd.copy(f.T);
    if (b <= 0) {
      out.p.copy(f.P).addScaledVector(f.B, d);
      out.up.copy(f.U); out.side.copy(f.B);
    } else {
      const R = this.R, th = d / R, c = Math.cos(th), sn = Math.sin(th);
      const dd = clamp(d, -this.HW * 4, this.HW * 4);
      // flat
      const fx = f.P.x + f.B.x * dd, fy = f.P.y + f.B.y * dd, fz = f.P.z + f.B.z * dd;
      // tube
      const tx = f.P.x + f.U.x * R * (1 - c) + f.B.x * R * sn;
      const ty = f.P.y + f.U.y * R * (1 - c) + f.B.y * R * sn;
      const tz = f.P.z + f.U.z * R * (1 - c) + f.B.z * R * sn;
      out.p.set(lerp(fx, tx, b), lerp(fy, ty, b), lerp(fz, tz, b));
      out.up.set(lerp(f.U.x, f.U.x * c - f.B.x * sn, b), lerp(f.U.y, f.U.y * c - f.B.y * sn, b), lerp(f.U.z, f.U.z * c - f.B.z * sn, b)).normalize();
      out.side.set(lerp(f.B.x, f.B.x * c + f.U.x * sn, b), lerp(f.B.y, f.B.y * c + f.U.y * sn, b), lerp(f.B.z, f.B.z * c + f.U.z * sn, b)).normalize();
    }
    if (h) out.p.addScaledVector(out.up, h);
    return out;
  },
  newPlace() { return { p: new V3(), up: new V3(), side: new V3(), fwd: new V3() }; },

  // ------------------------------------------------------------- meshes
  zoneTint(s) {
    switch (this.zoneAt(s)) {
      case 'lowg': return [0.45, 0.75, 1.0];
      case 'tube': return [0.8, 0.45, 1.0];
      case 'heavy': return [1.0, 0.55, 0.28];
      case 'bunker': return [1.0, 0.8, 0.45];
      default: return [0.55, 0.85, 1.0];
    }
  },
  roadTexture() {
    return canvasTex(256, 256, (g, w, h) => {
      g.fillStyle = '#121828'; g.fillRect(0, 0, w, h);
      g.strokeStyle = 'rgba(140,180,255,0.10)'; g.lineWidth = 1;
      for (let x = 0; x <= w; x += 32) { g.beginPath(); g.moveTo(x, 0); g.lineTo(x, h); g.stroke(); }
      for (let y = 0; y <= h; y += 32) { g.beginPath(); g.moveTo(0, y); g.lineTo(w, y); g.stroke(); }
      // panel seams
      g.fillStyle = 'rgba(0,0,0,0.35)'; g.fillRect(0, 126, w, 4);
      // edge bands
      for (let y = 0; y < h; y += 32) {
        g.fillStyle = (y / 32) % 2 ? '#e8f4ff' : '#4a5a7a';
        g.fillRect(2, y, 10, 32); g.fillRect(w - 12, y, 10, 32);
      }
      g.fillStyle = 'rgba(200,230,255,0.6)';
      g.fillRect(85, 0, 2, h); g.fillRect(169, 0, 2, h);
      g.fillStyle = '#ffffff';
      g.fillRect(126, 0, 4, 90); g.fillRect(126, 128, 4, 90);
    }, { repeat: true });
  },

  buildMeshes(scene) {
    const N = this.N, M = 28, R = this.R;
    const pl = this.newPlace();
    const pos = [], col = [], uv = [], idx = [];
    const upos = [], uidx = [];
    const rowOK = [];
    for (let i = 0; i <= N; i++) {
      const s = (i % N) * this.DS, sv = i * this.DS;
      const hw = this.hw(s);
      const tint = this.zoneTint(s);
      const b = this.tubeB(s);
      for (let j = 0; j <= M; j++) {
        const d = -hw + (2 * hw * j) / M;
        this.place(s, d, 0, pl);
        pos.push(pl.p.x, pl.p.y, pl.p.z);
        const edge = j === 0 || j === M ? 1.0 : 1;
        col.push(tint[0] * edge, tint[1] * edge, tint[2] * edge);
        uv.push(d / this.W + 0.5, sv / 24);
        if (b < 0.5) {
          this.place(s, d * 1.02, -0.9, pl);
        } else {
          this.place(s, d, -0.8, pl);
        }
        upos.push(pl.p.x, pl.p.y, pl.p.z);
      }
      rowOK[i] = !this.isGap(s);
    }
    for (let i = 0; i < N; i++) {
      if (!rowOK[i] || !rowOK[i + 1]) continue;
      const tubeRow = this.tubeB(i * this.DS) > 0.5;
      for (let j = 0; j < M; j++) {
        const a = i * (M + 1) + j, b = a + 1, c = a + M + 1, d = c + 1;
        idx.push(a, c, b, b, c, d);
        if (!tubeRow) uidx.push(a, b, c, b, d, c);
      }
    }
    const geo = new THREE.BufferGeometry();
    geo.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3));
    geo.setAttribute('color', new THREE.Float32BufferAttribute(col, 3));
    geo.setAttribute('uv', new THREE.Float32BufferAttribute(uv, 2));
    geo.setIndex(idx);
    const road = new THREE.Mesh(geo, new THREE.MeshBasicMaterial({ map: this.roadTexture(), vertexColors: true, side: THREE.DoubleSide }));
    scene.add(road);
    const ugeo = new THREE.BufferGeometry();
    ugeo.setAttribute('position', new THREE.Float32BufferAttribute(upos, 3));
    ugeo.setIndex(uidx);
    scene.add(new THREE.Mesh(ugeo, new THREE.MeshBasicMaterial({ color: 0x0a0d18, side: THREE.DoubleSide })));

    // force-field walls along the edges (not in the tube or the gap)
    const wallTex = canvasTex(4, 64, (g, w, h) => {
      const gr = g.createLinearGradient(0, h, 0, 0);
      gr.addColorStop(0, 'rgba(255,255,255,1)'); gr.addColorStop(0.08, 'rgba(255,255,255,0.9)');
      gr.addColorStop(0.12, 'rgba(255,255,255,0.35)'); gr.addColorStop(1, 'rgba(255,255,255,0)');
      g.fillStyle = gr; g.fillRect(0, 0, w, h);
    });
    for (const side of [-1, 1]) {
      const wp = [], wc = [], wu = [], wi = [];
      let v = 0;
      for (let i = 0; i <= N; i++) {
        const s = (i % N) * this.DS;
        const ok = this.tubeB(s) < 0.01 && !this.isGap(s);
        const tint = this.zoneTint(s);
        const hw = this.hw(s) * side;
        this.place(s, hw, 0, pl); wp.push(pl.p.x, pl.p.y, pl.p.z);
        this.place(s, hw, 3.2, pl); wp.push(pl.p.x, pl.p.y, pl.p.z);
        const k = ok ? 1 : 0;
        wc.push(tint[0] * k, tint[1] * k, tint[2] * k, tint[0] * k, tint[1] * k, tint[2] * k);
        wu.push(i / 4, 0, i / 4, 1);
        if (i < N) { wi.push(v, v + 2, v + 1, v + 1, v + 2, v + 3); }
        v += 2;
      }
      const wg = new THREE.BufferGeometry();
      wg.setAttribute('position', new THREE.Float32BufferAttribute(wp, 3));
      wg.setAttribute('color', new THREE.Float32BufferAttribute(wc, 3));
      wg.setAttribute('uv', new THREE.Float32BufferAttribute(wu, 2));
      wg.setIndex(wi);
      scene.add(new THREE.Mesh(wg, new THREE.MeshBasicMaterial({ map: wallTex, vertexColors: true, transparent: true,
        blending: THREE.AdditiveBlending, depthWrite: false, side: THREE.DoubleSide })));
    }

    // beacon lights under the road edges
    const bp = [], bc = [];
    for (let s = 0; s < this.L; s += 14) {
      if (this.tubeB(s) > 0.01 || this.isGap(s)) continue;
      const tint = this.zoneTint(s);
      for (const side of [-1, 1]) {
        this.place(s, this.HW * side * 1.05, -1.2, pl);
        bp.push(pl.p.x, pl.p.y, pl.p.z); bc.push(tint[0], tint[1], tint[2]);
      }
    }
    const bg = new THREE.BufferGeometry();
    bg.setAttribute('position', new THREE.Float32BufferAttribute(bp, 3));
    bg.setAttribute('color', new THREE.Float32BufferAttribute(bc, 3));
    scene.add(new THREE.Points(bg, new THREE.PointsMaterial({ size: 4, map: GLOW_TEX, vertexColors: true,
      transparent: true, blending: THREE.AdditiveBlending, depthWrite: false })));

    // tube rings
    const z = this.zones;
    const ringMat = glowMat(0xc070ff, 0.9);
    for (let s = z.tube[0] + 34; s < z.tube[1] - 30; s += 22) {
      const f = this.frame(s);
      const ring = new THREE.Mesh(new THREE.TorusGeometry(R + 0.9, 0.35, 6, 40), ringMat);
      ring.position.copy(f.P).addScaledVector(f.U, R);
      ring.lookAt(ring.position.clone().add(f.T));
      scene.add(ring);
    }
    // glass shell around the tube
    {
      const gp = [], gi = []; const MM = 32; let rows = 0;
      for (let s = z.tube[0] + 30; s <= z.tube[1] - 30; s += 4) {
        for (let j = 0; j <= MM; j++) {
          this.place(s, -Math.PI * R + (TAU * R * j) / MM, -1.5, pl);
          gp.push(pl.p.x, pl.p.y, pl.p.z);
        }
        rows++;
      }
      for (let r = 0; r < rows - 1; r++) for (let j = 0; j < MM; j++) {
        const a = r * (MM + 1) + j, b = a + 1, c = a + MM + 1, d = c + 1;
        gi.push(a, c, b, b, c, d);
      }
      const gg = new THREE.BufferGeometry();
      gg.setAttribute('position', new THREE.Float32BufferAttribute(gp, 3));
      gg.setIndex(gi);
      scene.add(new THREE.Mesh(gg, new THREE.MeshBasicMaterial({ color: 0x8040ff, transparent: true, opacity: 0.12,
        blending: THREE.AdditiveBlending, depthWrite: false, side: THREE.DoubleSide, wireframe: true })));
    }

    // zone gates
    const gate = (s, color, text) => {
      const f = this.frame(s);
      const g = new THREE.Group();
      const arch = new THREE.Mesh(new THREE.TorusGeometry(19, 0.8, 8, 48, Math.PI), glowMat(color, 0.95));
      g.add(arch);
      const lab = labelSprite(text, { color: '#' + new THREE.Color(color).getHexString(), scale: 2.2 });
      lab.position.set(0, 21.5, 0); g.add(lab);
      g.position.copy(f.P);
      const m = new THREE.Matrix4().makeBasis(f.B, f.U, f.T.clone().negate());
      g.quaternion.setFromRotationMatrix(m);
      scene.add(g);
    };
    gate(z.lowg[0], 0x58b4ff, 'НИЗКАЯ ГРАВИТАЦИЯ 0.25g');
    gate(z.tube[0] - 4, 0xc070ff, 'НУЛЕВАЯ ГРАВИТАЦИЯ · ЕЗДА ПО СТЕНАМ');
    gate(z.heavy[0], 0xff8a3d, 'ТЯЖЁЛАЯ ГРАВИТАЦИЯ 2.2g');
    gate(z.cork[0] - 6, 0xff5a2a, 'ИНВЕРСИЯ');
    gate(this.gap[0] - 25, 0xffb000, 'ПРЫГАЙ! РАЗРЫВ ТРАССЫ');

    // pads
    const padTex = canvasTex(128, 128, (g, w, h) => {
      g.clearRect(0, 0, w, h);
      g.strokeStyle = '#fff'; g.lineWidth = 14; g.lineJoin = 'miter';
      for (let k = 0; k < 3; k++) {
        const y = 100 - k * 36;
        g.beginPath(); g.moveTo(14, y); g.lineTo(64, y - 34); g.lineTo(114, y); g.stroke();
      }
    }, { repeat: true });
    const surfQuad = (s0, s1, d0, d1, h, material) => {
      const qp = [], qu = [], qi = []; const SN = 6, DN = 4;
      for (let a = 0; a <= SN; a++) for (let c = 0; c <= DN; c++) {
        this.place(s0 + ((s1 - s0) * a) / SN, d0 + ((d1 - d0) * c) / DN, h, pl);
        qp.push(pl.p.x, pl.p.y, pl.p.z); qu.push(c / DN, a / SN);
      }
      for (let a = 0; a < SN; a++) for (let c = 0; c < DN; c++) {
        const i0 = a * (DN + 1) + c; qi.push(i0, i0 + DN + 1, i0 + 1, i0 + 1, i0 + DN + 1, i0 + DN + 2);
      }
      const qg = new THREE.BufferGeometry();
      qg.setAttribute('position', new THREE.Float32BufferAttribute(qp, 3));
      qg.setAttribute('uv', new THREE.Float32BufferAttribute(qu, 2));
      qg.setIndex(qi);
      const m = new THREE.Mesh(qg, material); scene.add(m); return m;
    };
    this.surfQuad = surfQuad;
    const jumpMat = new THREE.MeshBasicMaterial({ map: padTex, color: 0x5fd0ff, transparent: true, blending: THREE.AdditiveBlending, depthWrite: false, side: THREE.DoubleSide });
    const boostMat = new THREE.MeshBasicMaterial({ map: padTex, color: 0xffb000, transparent: true, blending: THREE.AdditiveBlending, depthWrite: false, side: THREE.DoubleSide });
    this.padMats = [jumpMat, boostMat];
    for (const p of this.pads) surfQuad(p.s - 8, p.s, p.d0, p.d1, 0.08, jumpMat);
    for (const b of this.boosts) surfQuad(b.s - 7, b.s, b.d - 3, b.d + 3, 0.08, boostMat);
    const warnTex = canvasTex(128, 32, (g, w, h) => {
      g.fillStyle = '#111'; g.fillRect(0, 0, w, h);
      g.fillStyle = '#ffb000';
      for (let x = -32; x < w; x += 32) { g.beginPath(); g.moveTo(x, h); g.lineTo(x + 16, 0); g.lineTo(x + 32, 0); g.lineTo(x + 16, h); g.fill(); }
    }, { repeat: true });
    const warnMat = new THREE.MeshBasicMaterial({ map: warnTex, side: THREE.DoubleSide });
    surfQuad(this.gap[0] - 3, this.gap[0] - 0.2, -this.HW, this.HW, 0.05, warnMat);
    surfQuad(this.gap[1] + 0.2, this.gap[1] + 3, -this.HW, this.HW, 0.05, warnMat);

    // checkered start/finish line
    const chk = canvasTex(128, 32, (g, w, h) => {
      for (let x = 0; x < 16; x++) for (let y = 0; y < 4; y++) { g.fillStyle = (x + y) % 2 ? '#fff' : '#111'; g.fillRect(x * 8, y * 8, 8, 8); }
    });
    surfQuad(-1.5, 1.5, -this.HW, this.HW, 0.06, new THREE.MeshBasicMaterial({ map: chk, side: THREE.DoubleSide }));
  },
};
G.Track = Track;

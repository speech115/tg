'use strict';
// Shared helpers, textures and input for BUNKER-0.
window.G = window.G || {};
const V3 = THREE.Vector3;
const clamp = (x, a, b) => (x < a ? a : x > b ? b : x);
const lerp = (a, b, t) => a + (b - a) * t;
const smooth = (t) => (t <= 0 ? 0 : t >= 1 ? 1 : t * t * (3 - 2 * t));
const rand = (a = 0, b = 1) => a + Math.random() * (b - a);
const pick = (arr) => arr[Math.floor(Math.random() * arr.length)];
const damp = (a, b, k, dt) => lerp(a, b, 1 - Math.exp(-k * dt));
const mod = (a, n) => ((a % n) + n) % n;
const TAU = Math.PI * 2;

function canvasTex(w, h, draw, opts = {}) {
  const c = document.createElement('canvas');
  c.width = w; c.height = h;
  draw(c.getContext('2d'), w, h);
  const t = new THREE.CanvasTexture(c);
  if (opts.repeat) { t.wrapS = t.wrapT = THREE.RepeatWrapping; }
  t.anisotropy = 4;
  t.userData = { canvas: c };
  return t;
}

// Soft round glow used by sprites and particles.
const GLOW_TEX = canvasTex(128, 128, (g, w) => {
  const gr = g.createRadialGradient(w / 2, w / 2, 0, w / 2, w / 2, w / 2);
  gr.addColorStop(0, 'rgba(255,255,255,1)');
  gr.addColorStop(0.25, 'rgba(255,255,255,0.7)');
  gr.addColorStop(0.6, 'rgba(255,255,255,0.15)');
  gr.addColorStop(1, 'rgba(255,255,255,0)');
  g.fillStyle = gr; g.fillRect(0, 0, w, w);
});

function glowSprite(color, size, opacity = 1) {
  const m = new THREE.SpriteMaterial({ map: GLOW_TEX, color, transparent: true, opacity,
    blending: THREE.AdditiveBlending, depthWrite: false });
  const s = new THREE.Sprite(m);
  s.scale.set(size, size, 1);
  return s;
}

// Text label sprite (always faces camera).
function labelSprite(text, opts = {}) {
  const font = opts.font || '700 44px "Unbounded", "Golos Text", sans-serif';
  const pad = 18;
  const meas = document.createElement('canvas').getContext('2d');
  meas.font = font;
  const tw = Math.ceil(meas.measureText(text).width) + pad * 2;
  const th = opts.h || 72;
  const tex = canvasTex(tw, th, (g, w, h) => {
    if (opts.bg !== false) {
      g.fillStyle = opts.bg || 'rgba(5,6,13,0.72)';
      g.beginPath();
      const cut = 14;
      g.moveTo(cut, 0); g.lineTo(w, 0); g.lineTo(w, h - cut); g.lineTo(w - cut, h); g.lineTo(0, h); g.lineTo(0, cut);
      g.closePath(); g.fill();
      g.strokeStyle = opts.color || '#ffb000'; g.lineWidth = 4; g.stroke();
    }
    g.font = font; g.textBaseline = 'middle'; g.textAlign = 'center';
    g.fillStyle = opts.color || '#ffb000';
    g.fillText(text, w / 2, h / 2 + 2);
  });
  const m = new THREE.SpriteMaterial({ map: tex, transparent: true, depthWrite: false,
    depthTest: opts.depthTest !== false, sizeAttenuation: !opts.screen });
  const s = new THREE.Sprite(m);
  const sc = opts.scale || 1;
  if (opts.screen) s.scale.set((tw / th) * opts.screen, opts.screen, 1);
  else s.scale.set((tw / th) * 2 * sc, 2 * sc, 1);
  s.renderOrder = opts.renderOrder || 0;
  return s;
}

function mat(color, opts = {}) {
  return new THREE.MeshLambertMaterial(Object.assign({ color }, opts));
}
function glowMat(color, opacity = 1) {
  return new THREE.MeshBasicMaterial({ color, transparent: opacity < 1, opacity,
    blending: THREE.AdditiveBlending, depthWrite: false, side: THREE.DoubleSide });
}

// ---------------------------------------------------------------- input
const KEYSETS = {
  wasd: { up: ['KeyW'], down: ['KeyS'], left: ['KeyA'], right: ['KeyD'],
    item: ['KeyQ'], fire: ['KeyE'], drift: ['ShiftLeft', 'Space'] },
  ijkl: { up: ['KeyI'], down: ['KeyK'], left: ['KeyJ'], right: ['KeyL'],
    item: ['KeyU'], fire: ['KeyO'], drift: ['KeyH', 'KeyN'] },
  arrows: { up: ['ArrowUp', 'Numpad8'], down: ['ArrowDown', 'Numpad5', 'Numpad2'],
    left: ['ArrowLeft', 'Numpad4'], right: ['ArrowRight', 'Numpad6'],
    item: ['Enter', 'NumpadEnter', 'Numpad1', 'Period'], fire: ['ShiftRight', 'Numpad3', 'Comma'],
    drift: ['Slash', 'Numpad0', 'ControlRight'] },
};
function mergeSets(a, b) {
  const o = {};
  for (const k in a) o[k] = a[k].concat(b[k]);
  return o;
}
const LAYOUTS = {
  1: [mergeSets(KEYSETS.wasd, KEYSETS.arrows)],
  2: [KEYSETS.wasd, KEYSETS.arrows],
  3: [KEYSETS.wasd, KEYSETS.ijkl, KEYSETS.arrows],
};
const ALL_GAME_KEYS = new Set();
for (const s of Object.values(KEYSETS)) for (const k in s) s[k].forEach((c) => ALL_GAME_KEYS.add(c));

const Input = {
  keys: new Set(),
  touch: { left: false, right: false, gas: false, brake: false, item: false, fire: false, drift: false },
  prevActions: [{}, {}, {}],
  init() {
    addEventListener('keydown', (e) => {
      const st = window.Game && window.Game.state;
      if (ALL_GAME_KEYS.has(e.code) && (st === 'race' || st === 'countdown' || st === 'ending')) e.preventDefault();
      this.keys.add(e.code);
      if (G.onKey) G.onKey(e);
    });
    addEventListener('keyup', (e) => this.keys.delete(e.code));
    addEventListener('blur', () => this.keys.clear());
  },
  down(codes) { for (const c of codes) if (this.keys.has(c)) return true; return false; },
  // Returns control state for local player idx given number of local players.
  read(idx, count) {
    const set = (LAYOUTS[count] || LAYOUTS[1])[idx];
    const st = { gas: 0, brake: 0, steer: 0, up: false, down: false, left: false, right: false,
      item: false, fire: false, drift: false };
    if (set) {
      st.up = this.down(set.up); st.down = this.down(set.down);
      st.left = this.down(set.left); st.right = this.down(set.right);
      st.item = this.down(set.item); st.fire = this.down(set.fire); st.drift = this.down(set.drift);
    }
    const pads = navigator.getGamepads ? navigator.getGamepads() : [];
    const pad = pads && pads[idx];
    if (pad && pad.connected) {
      const ax = pad.axes[0] || 0, ay = pad.axes[1] || 0;
      const b = (i) => pad.buttons[i] && pad.buttons[i].pressed;
      if (ax < -0.35 || b(14)) st.left = true;
      if (ax > 0.35 || b(15)) st.right = true;
      if (ay < -0.5 || b(12) || b(0) || b(7)) st.up = true;
      if (ay > 0.5 || b(13) || b(1) || b(6)) st.down = true;
      if (b(2)) st.item = true;
      if (b(3)) st.fire = true;
      if (b(4) || b(5)) st.drift = true;
      if (Math.abs(ax) > 0.2) st.steerAnalog = ax;
    }
    if (idx === 0) {
      const t = this.touch;
      st.left = st.left || t.left; st.right = st.right || t.right;
      st.up = st.up || t.gas; st.down = st.down || t.brake;
      st.item = st.item || t.item; st.fire = st.fire || t.fire; st.drift = st.drift || t.drift;
    }
    st.gas = st.up ? 1 : 0;
    st.brake = st.down ? 1 : 0;
    st.steer = st.steerAnalog !== undefined ? st.steerAnalog : (st.right ? 1 : 0) - (st.left ? 1 : 0);
    // edge detection
    const prev = this.prevActions[idx] || {};
    st.pressed = {};
    for (const k of ['up', 'down', 'left', 'right', 'item', 'fire', 'drift']) st.pressed[k] = st[k] && !prev[k];
    this.prevActions[idx] = { up: st.up, down: st.down, left: st.left, right: st.right,
      item: st.item, fire: st.fire, drift: st.drift };
    return st;
  },
};

Object.assign(G, { V3, clamp, lerp, smooth, rand, pick, damp, mod, TAU, canvasTex, GLOW_TEX,
  glowSprite, labelSprite, mat, glowMat, Input, KEYSETS, LAYOUTS });

// Module entry: loads three.js r160 + addons, preloads the Blender-made GLB assets,
// then runs the classic game scripts in order with THREE exposed as a global.
import './three-setup.js';

const bar = document.getElementById('loadBar');
const label = document.getElementById('loadLabel');
const FILES = ['kart', 'saucers', 'characters', 'props', 'printer', 'bunker'];
const SCRIPTS = ['util', 'render', 'audio', 'track', 'world', 'entities', 'hud', 'game'];
const progress = {};
const setProgress = () => {
  const vals = FILES.map((f) => progress[f] || 0);
  const p = vals.reduce((a, b) => a + b, 0) / FILES.length;
  if (bar) bar.style.width = `${Math.round(p * 90)}%`;
};

function loadScript(src) {
  return new Promise((resolve, reject) => {
    const s = document.createElement('script');
    s.src = src; s.async = false;
    s.onload = resolve; s.onerror = () => reject(new Error(`Failed to load ${src}`));
    document.body.appendChild(s);
  });
}

async function boot() {
  const loader = new THREE.GLTFLoader();
  window.ASSETS = {};
  // .glb in the repo; hosts that only serve text get an embedded-glTF .json copy (tools/glb2json.mjs)
  const load = (f, ext) => loader.loadAsync(`assets/${f}.${ext}`, (e) => {
    if (e.total) { progress[f] = e.loaded / e.total; setProgress(); }
  });
  const [first, second] = window.ASSET_FORMAT === 'json' ? ['json', 'glb'] : ['glb', 'json'];
  await Promise.all(FILES.map((f) => load(f, first).catch(() => load(f, second))
    .then((g) => { window.ASSETS[f] = g.scene; progress[f] = 1; setProgress(); })));
  if (label) label.textContent = 'ASSEMBLING THE BUNKER…';
  for (const s of SCRIPTS) await loadScript(`js/${s}.js`);
  const fonts = document.fonts ? document.fonts.ready : Promise.resolve();
  await Promise.race([fonts, new Promise((r) => setTimeout(r, 2500))]);
  window.Game.init();
  if (window.BOOT_FAILED) return;
  if (bar) bar.style.width = '100%';
  const el = document.getElementById('loading');
  if (el) { el.classList.add('done'); setTimeout(() => { el.hidden = true; }, 700); }
}

boot().catch((err) => window.showFatal && window.showFatal(err));

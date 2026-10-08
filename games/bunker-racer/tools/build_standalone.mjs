// Builds Bunker-0.html: one self-contained file (three.js bundled, game code inlined,
// Blender models embedded as base64). It opens with a double-click from disk, works
// offline (fonts fall back to system ones) and needs no server or CDN.
//   npm install && npm run build:standalone [-- --artifact <out.html>]
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { build } from 'esbuild';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const rd = (p) => fs.readFileSync(path.join(root, p), 'utf8');
const safe = (code) => code.replace(/<\/script/gi, '<\\/script');
const SCRIPTS = ['util', 'render', 'audio', 'track', 'world', 'entities', 'hud', 'game'];
const ASSETS = ['kart', 'saucers', 'characters', 'props', 'printer', 'bunker'];

const three = await build({
  entryPoints: [path.join(root, 'js/three-setup.js')], bundle: true, minify: true,
  format: 'iife', write: false, legalComments: 'none', target: 'es2020',
});
const assetData = ASSETS.map((f) => `${JSON.stringify(f)}:"${fs.readFileSync(path.join(root, 'assets', `${f}.glb`)).toString('base64')}"`).join(',');

const boot = `(async () => {
  const bar = document.getElementById('loadBar');
  try {
    const loader = new THREE.GLTFLoader();
    window.ASSETS = {};
    const names = Object.keys(window.ASSET_DATA);
    for (let i = 0; i < names.length; i++) {
      const b64 = window.ASSET_DATA[names[i]], bin = atob(b64), bytes = new Uint8Array(bin.length);
      for (let k = 0; k < bin.length; k++) bytes[k] = bin.charCodeAt(k);
      const gltf = await new Promise((res, rej) => loader.parse(bytes.buffer, '', res, rej));
      window.ASSETS[names[i]] = gltf.scene;
      if (bar) bar.style.width = Math.round(((i + 1) / names.length) * 90) + '%';
      await new Promise((r) => setTimeout(r, 0));
    }
    window.ASSET_DATA = null;
    const fonts = document.fonts ? document.fonts.ready : Promise.resolve();
    await Promise.race([fonts, new Promise((r) => setTimeout(r, 2500))]);
    window.Game.init();
    if (window.BOOT_FAILED) return;
    if (bar) bar.style.width = '100%';
    const el = document.getElementById('loading');
    if (el) { el.classList.add('done'); setTimeout(() => { el.hidden = true; }, 700); }
  } catch (err) { window.showFatal(err); }
})();`;

let html = rd('index.html');
html = html.replace(/<script type="importmap">[\s\S]*?<\/script>\n/, '').replace(/<script type="module" src="js\/boot.js"><\/script>\n/, '');
html = html.replace('<title>', '<script>window.STANDALONE = true;</script>\n<title>');
const inline = [
  `<script>${safe(three.outputFiles[0].text)}</script>`,
  ...SCRIPTS.map((s) => `<script>/* js/${s}.js */\n${safe(rd(`js/${s}.js`))}</script>`),
  `<script>window.ASSET_DATA = {${assetData}};</script>`,
  `<script>${boot}</script>`,
].join('\n');
html = html.replace('</body>', () => `${inline}\n</body>`); // function form: the bundle contains $ patterns
if (!html.includes('window.STANDALONE = true') || html.includes('js/boot.js')) throw new Error('index.html layout changed; update build_standalone.mjs');

const out = path.join(root, 'Bunker-0.html');
fs.writeFileSync(out, html);
console.log(`${path.relative(process.cwd(), out)}: ${(fs.statSync(out).size / 1048576).toFixed(1)} MB`);

const ai = process.argv.indexOf('--artifact');
if (ai > 0) {
  // claude.ai artifacts wrap the page in their own document skeleton
  const art = html.replace(/<!doctype html>\n|<html[^>]*>\n|<head>\n|<meta charset="utf-8">\n|<meta name="viewport"[^>]*>\n|<\/head>\n|<body>\n|<\/body>\n|<\/html>\n/g, '');
  fs.writeFileSync(process.argv[ai + 1], art);
  console.log(`artifact page: ${process.argv[ai + 1]}`);
}

'use strict';
// DOM overlay: per-player panels, hacking mini-games, commentary, minimap, menu, ending, results.
const SPEAKERS = {
  trump: { name: 'Donald Trump', short: 'DT', color: '#e9be55' },
  biden: { name: 'Joe Biden', short: 'JB', color: '#7aa7ff' },
  zelensky: { name: 'Volodymyr Zelensky', short: 'VZ', color: '#a9c060' },
  xi: { name: 'Xi Jinping', short: 'XJ', color: '#ff6a6a' },
  musk: { name: 'Elon Musk', short: 'EM', color: '#35e0ff' },
  mcafee: { name: 'John McAfee', short: 'JM', color: '#ffd000' },
  fable: { name: 'Fable', short: 'F', color: '#ffb347' },
  astra: { name: 'Astra', short: 'A', color: '#61e8ff' },
  omega: { name: 'OMEGA', short: 'Ω', color: '#ff2a3d' },
};
const ICONS = {
  nitro: '<path d="M12 2c1 4 5 6 5 11a5 5 0 0 1-10 0c0-3 2-4 2-7 2 1 3 3 3 5 1-2 1-5 0-9z"/>',
  nitro3: '<path d="M7 6c.6 2.4 3 3.6 3 6.6a3 3 0 0 1-6 0c0-1.8 1.2-2.4 1.2-4.2C6.4 9 7 10 7 11.4 7.6 10 7.6 8.4 7 6zM17 6c.6 2.4 3 3.6 3 6.6a3 3 0 0 1-6 0c0-1.8 1.2-2.4 1.2-4.2C16.4 9 17 10 17 11.4c.6-1.4.6-3 0-5.4zM12 1c.6 2.4 3 3.6 3 6.6a3 3 0 0 1-6 0C9 5.8 10.2 5.2 10.2 3.4 11.4 4 12 5 12 6.4c.6-1.4.6-3 0-5.4z"/>',
  slime: '<path d="M3 17c0-4 3-5 5-9 1 3 2 4 4 4s3-3 4-5c1 4 5 5 5 10 0 2-2 3-4 3H7c-2 0-4-1-4-3z"/>',
  rocket: '<path d="M14 3c3 0 7 0 7 0s0 4 0 7l-7 7-4-4zM9 12l-4 1-3 3 5 1zM12 15l-1 4-3 3-1-5zM5 19l-2 2"/><circle cx="16" cy="8" r="1.6" fill="#05060d"/>',
  gbomb: '<circle cx="12" cy="12" r="5"/><ellipse cx="12" cy="12" rx="10" ry="3.5" fill="none" stroke="currentColor" stroke-width="1.6"/><ellipse cx="12" cy="12" rx="3.5" ry="10" fill="none" stroke="currentColor" stroke-width="1.2"/>',
  shield: '<path d="M12 2l8 3v6c0 5-3.5 9-8 11-4.5-2-8-6-8-11V5z"/>',
  kill: '<circle cx="12" cy="13" r="8"/><rect x="5" y="3" width="14" height="3" rx="1"/><circle cx="12" cy="13" r="4" fill="#05060d"/>',
};
const DIR_GLYPH = { up: '↑', down: '↓', left: '←', right: '→' };
const PTS = [15, 12, 10, 8, 7, 6, 5, 4, 3];

const HUD = {
  q: [], cur: null, curT: 0, panels: [], cache: new Map(), standT: 0,
  $(id) { return document.getElementById(id); },

  init() {
    this.hud = this.$('hud');
    this.info = this.$('info');
    this.mm = this.$('minimap');
    this.mmCtx = this.mm.getContext('2d');
    this.prepMinimap();
    // menu wiring
    const cfg = { players: 1, laps: 3, diff: 1, gfx: 1 };
    try { Object.assign(cfg, JSON.parse(localStorage.getItem('bunker0cfg') || '{}')); } catch (_) {}
    this.menuCfg = cfg;
    document.querySelectorAll('.seg').forEach((seg) => {
      const key = seg.dataset.key;
      seg.querySelectorAll('button').forEach((b) => {
        if (+b.dataset.v === cfg[key]) b.classList.add('on');
        b.addEventListener('click', () => {
          seg.querySelectorAll('button').forEach((x) => x.classList.remove('on'));
          b.classList.add('on'); cfg[key] = +b.dataset.v;
          this.renderControls();
        });
      });
    });
    this.renderControls();
    this.$('startBtn').addEventListener('click', () => this.start());
    this.$('againBtn').addEventListener('click', () => { this.$('results').hidden = true; this.start(); });
    this.$('menuBtn').addEventListener('click', () => { this.$('results').hidden = true; Game.toMenu(); });
    this.$('resumeBtn').addEventListener('click', () => this.pause(false));
    this.$('quitBtn').addEventListener('click', () => { this.pause(false); Game.toMenu(); });
    this.$('muteBtn').addEventListener('click', () => { const m = Sound.toggleMute(); this.$('muteBtn').textContent = m ? 'SOUND: OFF' : 'SOUND: ON'; });
    this.$('ending').addEventListener('click', () => Game.skipEnding());
    G.onKey = (e) => {
      if (e.code === 'Escape' && (Game.state === 'race' || Game.state === 'countdown')) this.pause(!Game.paused);
      if (e.code === 'KeyM' && Game.state !== 'demo') Sound.toggleMute();
      if (Game.state === 'ending' && (e.code === 'Space' || e.code === 'Enter')) Game.skipEnding();
      if (Game.state === 'demo' && e.code === 'Enter' && !this.$('menu').hidden) this.start();
    };
    this.touchMode = matchMedia('(pointer: coarse)').matches;
    this.setupTouch();
  },
  start() {
    const cfg = Object.assign({}, this.menuCfg);
    try { localStorage.setItem('bunker0cfg', JSON.stringify(cfg)); } catch (_) {}
    this.$('menu').hidden = true;
    Game.start(cfg);
  },
  showMenu() { this.$('menu').hidden = false; this.$('ending').hidden = true; this.$('results').hidden = true; },
  pause(on) {
    Game.paused = on;
    this.$('pause').hidden = !on;
    if (Sound.ctx) { if (on) Sound.ctx.suspend(); else Sound.ctx.resume(); }
  },
  renderControls() {
    const n = this.menuCfg.players;
    const names = ['STEVE', 'SERGEY', 'DANEL'];
    const colors = ['#ff7a1a', '#ff4f8b', '#35e0ff'];
    const sets = {
      1: [['W A S D / arrows', 'Q / Enter', 'E / right Shift', 'Space / Shift']],
      2: [['W A S D', 'Q', 'E', 'Space / Shift'], ['arrows', 'Enter', 'right Shift', '/ (slash)']],
      3: [['W A S D', 'Q', 'E', 'Space / Shift'], ['I J K L', 'U', 'O', 'H'], ['arrows', 'Enter', 'right Shift', '/ (slash)']],
    }[n];
    let html = '<div class="ctl-row ctl-head"><span></span><span>steer & gas</span><span>item</span><span>fire · neuro</span><span>drift</span></div>';
    sets.forEach((s, i) => {
      html += `<div class="ctl-row"><span class="ctl-name" style="--c:${colors[i]}">${names[i]}</span>${s.map((k) => `<span><kbd>${k}</kbd></span>`).join('')}</div>`;
    });
    if (n < 3) html += `<p class="ctl-note">Fable and Astra drive the other humans (${names.slice(n).join(', ')}). Gamepads connect automatically: pad 1 is Steve, pad 2 is Sergey, pad 3 is Danel.</p>`;
    else html += '<p class="ctl-note">Three on one keyboard is cramped but fun. Gamepads connect automatically.</p>';
    this.$('controls').innerHTML = html;
  },

  // ------------------------------------------------------------ race HUD
  setup(players, demo) {
    this.hud.innerHTML = '';
    this.panels = [];
    this.cache.clear();
    this.q = []; this.cur = null; this.$('comment').classList.remove('show');
    this.$('countdown').textContent = '';
    this.$('ending').hidden = true;
    this.hud.hidden = demo;
    this.info.hidden = demo;
    this.info.className = players === 3 ? 'quad' : players === 2 ? 'duo' : 'solo';
    document.body.dataset.players = demo ? 0 : players;
    const vps = players <= 1 ? [[0, 0, 1, 1]] : players === 2 ? [[0, 0, 1, 0.5], [0, 0.5, 1, 0.5]] : [[0, 0, 0.5, 0.5], [0.5, 0, 0.5, 0.5], [0, 0.5, 0.5, 0.5]];
    for (let i = 0; i < players; i++) {
      const [x, y, w, h] = vps[i];
      const el = document.createElement('div');
      el.className = 'vp';
      el.style.cssText = `left:${x * 100}%;top:${y * 100}%;width:${w * 100}%;height:${h * 100}%`;
      el.innerHTML = `
        <div class="vp-top">
          <div class="pos"><b data-k="pos">–</b><small>/9</small></div>
          <div class="who" style="--c:${['#ff7a1a', '#ff4f8b', '#35e0ff'][i]}">${['STEVE', 'SERGEY', 'DANEL'][i]}</div>
          <div class="lap"><span>LAP</span> <b data-k="lap">1</b>/<span data-k="laps">3</span><div class="time" data-k="time">0:00.0</div></div>
        </div>
        <div class="vp-zone" data-k="zone"></div>
        <div class="vp-msg" data-k="msg"></div>
        <div class="vp-warn" data-k="warn"></div>
        <div class="vp-bottom">
          <div class="slot" data-k="itemSlot"><div class="ico" data-k="ico"></div><div class="slot-txt"><small>ITEM</small><span data-k="item">—</span></div></div>
          <div class="slot weapon" data-k="wSlot"><div class="slot-txt"><small>McAFEE GUN</small><span data-k="weapon">none</span><div class="bar"><i data-k="ammo"></i></div></div></div>
          <div class="slot bci"><div class="slot-txt"><small>BCI · NEURO</small><span class="pips" data-k="pips"><i></i><i></i><i></i></span><div class="bar neuro"><i data-k="neuro"></i></div></div></div>
          <div class="speed"><b data-k="spd">0</b><small>km/h</small><div class="grav" data-k="grav">1.00g</div></div>
        </div>
        <div class="hack" data-k="hack" hidden>
          <div class="hack-head">OMEGA IS HACKING YOUR CAR</div>
          <div class="hack-body" data-k="hackBody"></div>
          <div class="hack-timer"><i data-k="hackT"></i></div>
          <div class="hack-help" data-k="hackHelp"></div>
        </div>`;
      this.hud.appendChild(el);
      const refs = {};
      el.querySelectorAll('[data-k]').forEach((n) => { refs[n.dataset.k] = n; });
      this.panels.push({ el, refs, msgT: 0, lastZone: '' });
    }
    const touch = this.touchMode && players === 1 && !demo;
    this.$('touch').hidden = !touch;
    document.body.classList.toggle('touch', touch);
  },
  set(i, k, v, prop = 'textContent') {
    const key = i + k + prop;
    if (this.cache.get(key) === v) return;
    this.cache.set(key, v);
    const el = this.panels[i] && this.panels[i].refs[k];
    if (!el) return;
    if (prop === 'width') el.style.width = v; else if (prop === 'html') el.innerHTML = v; else el[prop] = v;
  },
  msg(i, text, color = '#ffb000', dur = 1.6) {
    const p = this.panels[i]; if (!p) return;
    const el = p.refs.msg;
    el.textContent = text; el.style.color = color;
    el.classList.remove('pop'); void el.offsetWidth; el.classList.add('pop');
    p.msgT = dur;
  },
  countdown(text) {
    const el = this.$('countdown');
    el.textContent = text;
    el.classList.remove('pop'); void el.offsetWidth; el.classList.add('pop');
    clearTimeout(this.cdT);
    this.cdT = setTimeout(() => { el.textContent = ''; }, text.length > 2 ? 1200 : 900);
  },
  flash(color) {
    const el = this.$('flash'); el.style.background = color;
    el.classList.remove('go'); void el.offsetWidth; el.classList.add('go');
  },
  banner(title, sub) {
    const el = this.$('banner');
    el.innerHTML = `<b>${title}</b><span>${sub}</span>`;
    el.classList.remove('go'); void el.offsetWidth; el.classList.add('go');
  },
  say(who, text) {
    if (Game.state === 'demo') return;
    this.q.push({ who, text });
    if (this.q.length > 3) this.q.shift();
  },
  ordinal(n) { const s = ['TH', 'ST', 'ND', 'RD']; const v = n % 100; return n + (s[(v - 20) % 10] || s[v] || s[0]); },
  fmtTime(t) { const m = Math.floor(t / 60), s = t - m * 60; return `${m}:${s < 10 ? '0' : ''}${s.toFixed(1)}`; },

  update(dt, R, game) {
    // commentary
    this.curT -= dt;
    if (this.curT <= 0 && this.q.length) {
      const m = this.q.shift(); const sp = SPEAKERS[m.who] || SPEAKERS.musk;
      const el = this.$('comment');
      el.style.setProperty('--c', sp.color);
      el.innerHTML = `<div class="ava">${sp.short}</div><div><b>${sp.name}</b><p>${m.text}</p></div>`;
      el.classList.remove('show'); void el.offsetWidth; el.classList.add('show');
      this.curT = 2.2 + m.text.length * 0.035;
    } else if (this.curT <= 0) this.$('comment').classList.remove('show');
    this.$('goal').hidden = game.state !== 'countdown';
    if (game.state === 'demo' || game.state === 'ending') return;
    const T = Track;
    R.local.forEach((car, i) => {
      const p = this.panels[i]; if (!p) return;
      this.set(i, 'pos', String(car.place || i + 1));
      this.set(i, 'lap', String(clamp(car.lap + 1, 1, R.cfg.laps)));
      this.set(i, 'laps', String(R.cfg.laps));
      this.set(i, 'time', this.fmtTime(car.finished ? car.finishTime : R.t));
      this.set(i, 'spd', String(Math.round(Math.abs(car.v) * 3.6)));
      const g = T.gravity(car.s);
      this.set(i, 'grav', `${g.toFixed(2)}g`);
      // item
      let itemName = '—', ico = '';
      if (car.roulette > 0) { const k = Object.keys(ICONS)[Math.floor(game.time * 14) % 6]; ico = ICONS[k]; itemName = '...'; }
      else if (car.item) { ico = ICONS[car.item]; itemName = ITEMS[car.item].name + (car.itemCount > 1 ? ` ×${car.itemCount}` : ''); }
      this.set(i, 'item', itemName);
      this.set(i, 'ico', ico ? `<svg viewBox="0 0 24 24" fill="currentColor">${ico}</svg>` : '', 'html');
      p.refs.itemSlot.style.setProperty('--c', car.item ? ITEMS[car.item].color : '#7d849a');
      p.refs.itemSlot.classList.toggle('kill', car.item === 'kill');
      // weapon
      if (car.weapon) {
        const W = WEAPONS[car.weapon];
        this.set(i, 'weapon', `${W.name} · ${car.ammo}`);
        this.set(i, 'ammo', `${(car.ammo / W.ammo) * 100}%`, 'width');
      } else { this.set(i, 'weapon', car.neuro >= 1 ? 'FIRE = NEURO FOCUS' : 'none'); this.set(i, 'ammo', '0%', 'width'); }
      p.refs.wSlot.classList.toggle('armed', !!car.weapon);
      const pips = p.refs.pips.children;
      for (let k = 0; k < 3; k++) pips[k].classList.toggle('on', k < car.bci);
      this.set(i, 'neuro', `${car.neuro * 100}%`, 'width');
      p.refs.neuro.parentNode.classList.toggle('full', car.neuro >= 1);
      // zone banner
      const z = T.zoneAt(car.s);
      if (z !== p.lastZone) {
        p.lastZone = z;
        const names = { lowg: 'LOW GRAVITY · 0.25g', tube: 'ZERO GRAVITY · TUBE', heavy: 'HEAVY GRAVITY · 2.2g', bunker: 'BUNKER-0 · BASEMENT B-1', space: 'OPEN SPACE' };
        const el = p.refs.zone;
        el.textContent = names[z]; el.dataset.z = z;
        el.classList.remove('pop'); void el.offsetWidth; el.classList.add('pop');
      }
      // messages
      p.msgT -= dt;
      if (p.msgT <= 0) this.set(i, 'msg', '');
      // warnings
      let warn = '';
      if (R.omega.aim && R.omega.aim.car === car) warn = 'OMEGA BEAM LOCKED';
      else if (R.drones.some((d) => d.target === car && d.phase === 'chase')) warn = 'OMEGA DRONE PURSUING';
      else if (R.wave.active && car.waveDist !== undefined && car.waveDist < 180 && !car.finished) warn = `OMEGA WAVE · ${Math.max(0, Math.round(car.waveDist))} m`;
      else if (car.stallT > 0) warn = 'REBOOTING…';
      this.set(i, 'warn', warn);
      p.el.classList.toggle('danger', !!car.hack || (R.wave.active && car.waveDist < 80 && !car.finished));
      p.el.classList.toggle('spectate', car.finished);
      // hack overlay
      const hk = car.hack;
      p.refs.hack.hidden = !hk;
      if (hk) {
        if (hk.type === 'seq') {
          const html = hk.seq.map((d, k) => `<span class="${k < hk.idx ? (hk.helped.includes(k) ? 'ok help' : 'ok') : k === hk.idx ? 'now' : ''}">${DIR_GLYPH[d]}</span>`).join('');
          this.set(i, 'hackBody', `<div class="seq${hk.shake > 0 ? ' shake' : ''}">${html}</div><div class="hint">Repeat the arrows with your steering keys</div>`, 'html');
          this.set(i, 'hackHelp', 'Fable and Astra hack back: they clear one symbol every couple of seconds', 'textContent');
        } else {
          const html = `<div class="meter${hk.shake > 0 ? ' shake' : ''}"><i class="zone" style="left:${hk.zone * 100}%;width:${hk.width * 100}%"></i><i class="needle" style="left:${hk.needle * 100}%"></i></div><div class="hint">Press ITEM/FIRE/DRIFT when the needle is in the green zone · ${hk.hits}/${hk.need}</div>`;
          p.refs.hackBody.innerHTML = html; this.cache.delete(i + 'hackBodyhtml');
          this.set(i, 'hackHelp', 'Fable and Astra are widening the firewall window', 'textContent');
        }
        this.set(i, 'hackT', `${(hk.timer / 8) * 100}%`, 'width');
      }
    });
    // standings + minimap
    this.standT -= dt;
    if (this.standT <= 0 && R.sorted) {
      this.standT = 0.25;
      const charge = Math.round(World.portalG.charge * 100);
      const stun = R.omega.stun > 0;
      this.$('status').innerHTML = `<span>PORTAL <b>${charge}%</b></span><span>PRINTER <b>${R.humansDone}/3</b></span><span class="om${stun ? ' off' : ''}">OMEGA ${stun ? 'STUNNED' : 'ACTIVE'}</span>`;
      this.$('standings').innerHTML = R.sorted.map((c) => {
        const col = '#' + new THREE.Color(c.color).getHexString();
        return `<li class="${c.isHuman ? 'human' : ''}${c.finished ? ' done' : ''}" style="--c:${col}"><i></i><span>${c.name}</span>${c.finished ? '<em>B-1</em>' : c.hack || c.aiHackT > 0 ? '<em class="hk">HACKED</em>' : ''}</li>`;
      }).join('');
    }
    this.drawMinimap(R);
  },

  prepMinimap() {
    const T = Track;
    let x0 = 1e9, x1 = -1e9, z0 = 1e9, z1 = -1e9;
    for (const p of T.P) { x0 = Math.min(x0, p.x); x1 = Math.max(x1, p.x); z0 = Math.min(z0, p.z); z1 = Math.max(z1, p.z); }
    this.mmB = { x0: x0 - 30, x1: x1 + 30, z0: z0 - 30, z1: z1 + 60 };
  },
  drawMinimap(R) {
    const c = this.mm, g = this.mmCtx;
    const rect = c.getBoundingClientRect();
    const dpr = Math.min(2, devicePixelRatio || 1);
    const w = Math.max(10, Math.round(rect.width * dpr)), h = Math.max(10, Math.round(rect.height * dpr));
    if (c.width !== w || c.height !== h) { c.width = w; c.height = h; }
    g.clearRect(0, 0, w, h);
    const B = this.mmB, sc = Math.min(w / (B.x1 - B.x0), h / (B.z1 - B.z0));
    const ox = (w - (B.x1 - B.x0) * sc) / 2, oz = (h - (B.z1 - B.z0) * sc) / 2;
    const X = (x) => ox + (x - B.x0) * sc, Z = (z) => oz + (z - B.z0) * sc;
    const T = Track;
    // bunker
    g.fillStyle = 'rgba(255,176,0,0.12)'; g.strokeStyle = 'rgba(255,176,0,0.5)'; g.lineWidth = 1 * dpr;
    g.fillRect(X(-165), Z(222), (310) * sc, 128 * sc); g.strokeRect(X(-165), Z(222), 310 * sc, 128 * sc);
    // omega
    g.fillStyle = '#ff2a3d'; g.beginPath(); g.arc(X(0), Z(0), 5 * dpr * (World.omegaG.stun > 0 ? 0.6 : 1), 0, TAU); g.fill();
    // track by zone
    const zc = { lowg: '#58b4ff', tube: '#c070ff', heavy: '#ff8a3d', bunker: '#ffb000', space: '#5a6a8a' };
    g.lineCap = 'round'; g.lineWidth = 4 * dpr;
    let prevZ = null;
    for (let i = 0; i <= T.N; i += 3) {
      const p = T.P[i % T.N], z = T.zoneAt(i * T.DS);
      if (z !== prevZ) { if (prevZ) g.stroke(); g.beginPath(); g.strokeStyle = zc[z]; g.moveTo(X(p.x), Z(p.z)); prevZ = z; }
      else g.lineTo(X(p.x), Z(p.z));
    }
    g.stroke();
    // gap
    const gp = T.P[Math.round(((T.gap[0] + T.gap[1]) / 2) / T.DS)];
    g.fillStyle = '#02030a'; g.beginPath(); g.arc(X(gp.x), Z(gp.z), 4 * dpr, 0, TAU); g.fill();
    // wave
    if (R.wave.active && R.wave.mesh.visible) {
      const wp = T.P[Math.floor(mod(R.wave.p, T.L) / T.DS) % T.N];
      g.strokeStyle = '#ff2a3d'; g.lineWidth = 3 * dpr; g.beginPath(); g.arc(X(wp.x), Z(wp.z), 7 * dpr, 0, TAU); g.stroke();
    }
    // drones
    g.fillStyle = '#ff2a3d';
    for (const d of R.drones) { g.fillRect(X(d.m.position.x) - 2 * dpr, Z(d.m.position.z) - 2 * dpr, 4 * dpr, 4 * dpr); }
    // mcafee
    if (R.mc.mesh.visible) { g.fillStyle = '#ffd000'; g.font = `${10 * dpr}px "JetBrains Mono", monospace`; g.fillText('M', X(R.mc.mesh.position.x) - 3 * dpr, Z(R.mc.mesh.position.z) + 3 * dpr); }
    // cars
    for (const car of R.cars) {
      if (car.finished) continue;
      const r = (car.isHuman ? 4.5 : 3) * dpr;
      g.fillStyle = '#' + new THREE.Color(car.color).getHexString();
      g.beginPath(); g.arc(X(car.pos.x), Z(car.pos.z), r, 0, TAU); g.fill();
      if (car.local >= 0) { g.strokeStyle = '#fff'; g.lineWidth = 1.5 * dpr; g.stroke(); }
    }
  },

  // ------------------------------------------------------------ touch
  setupTouch() {
    const t = this.$('touch');
    t.querySelectorAll('[data-t]').forEach((b) => {
      const k = b.dataset.t;
      const on = (e) => { e.preventDefault(); Input.touch[k] = true; b.classList.add('on'); };
      const off = (e) => { e.preventDefault(); Input.touch[k] = false; b.classList.remove('on'); };
      b.addEventListener('pointerdown', on); b.addEventListener('pointerup', off);
      b.addEventListener('pointercancel', off); b.addEventListener('pointerleave', off);
    });
  },

  // ------------------------------------------------------------ ending & results
  endingStart() {
    this.hud.hidden = true; this.info.hidden = true; this.$('touch').hidden = true;
    const el = this.$('ending');
    el.hidden = false;
    el.className = '';
    this.letterTyped = 0;
    this.$('letterText').textContent = '';
  },
  endingUpdate(t) {
    const el = this.$('ending');
    const letter = this.$('letter');
    letter.classList.toggle('in', t > 3.2 && t < 12.2);
    const full = this.$('letterText').dataset.full;
    if (t > 3.6) {
      const n = Math.min(full.length, Math.floor((t - 3.6) * 70));
      if (n !== this.letterTyped) { this.letterTyped = n; this.$('letterText').textContent = full.slice(0, n); }
    }
    el.classList.toggle('white', t > 13.2);
    this.$('endTitle').classList.toggle('in', t > 0.3 && t < 3.4);
  },
  results(R) {
    this.$('ending').hidden = true;
    const el = this.$('results');
    el.hidden = false;
    const sorted = R.sorted || R.cars;
    const team = { human: 0, zeta: 0, nibiru: 0 };
    sorted.forEach((c, i) => { team[c.team] += PTS[i] || 0; });
    const best = Object.entries(team).sort((a, b) => b[1] - a[1])[0][0];
    this.$('teamScores').innerHTML = Object.entries(team).sort((a, b) => b[1] - a[1]).map(([k, v]) =>
      `<div class="team ${k}${k === best ? ' win' : ''}"><small>${TEAM_NAMES[k]}</small><b>${v}</b><span>points</span></div>`).join('');
    this.$('table').innerHTML = '<div class="tr th"><span>#</span><span>racer</span><span>team</span><span>time</span><span>pts</span></div>' + sorted.map((c, i) => {
      const col = '#' + new THREE.Color(c.color).getHexString();
      return `<div class="tr${c.isHuman ? ' human' : ''}" style="--c:${col}"><span>${i + 1}</span><span><i></i>${c.name}</span><span>${TEAM_NAMES[c.team]}</span><span>${c.finished ? this.fmtTime(c.finishTime) : 'racing'}</span><span>${PTS[i] || 0}</span></div>`;
    }).join('');
    this.$('stats').innerHTML = R.humans.map((h) => {
      const col = '#' + new THREE.Color(h.color).getHexString();
      return `<div class="stat" style="--c:${col}"><b>${h.name}</b><dl>
        <dt>BCI chips</dt><dd>${h.stats.chips}</dd><dt>Hacks survived</dt><dd>${h.stats.hacks}</dd>
        <dt>Hacks beaten by hand</dt><dd>${h.stats.hacksBeaten}</dd><dt>McAfee crates</dt><dd>${h.stats.crates}</dd>
        <dt>Enemies hit</dt><dd>${h.stats.kills}</dd><dt>Falls into the void</dt><dd>${h.stats.falls}</dd></dl></div>`;
    }).join('');
    const humanWin = best === 'human';
    this.$('resultsLead').textContent = humanWin
      ? 'Team Human won the race and delivered the letter. The AI labs of 2024 read it to the end. OMEGA was never switched on.'
      : 'The aliens beat the humans on points, but the portal only lets humans through. The letter still reached 2024. The AI labs read it. OMEGA was never switched on.';
  },
};
G.HUD = HUD;

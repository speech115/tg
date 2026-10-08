'use strict';
// Online multiplayer over WebRTC. PeerJS's free cloud server only introduces the browsers to each
// other; race traffic then flows peer to peer (relayed through PeerJS's TURN servers when a network
// blocks direct connections).
//
// The host's browser runs the race: AI, items, hits, OMEGA, McAfee, laps and finishes. Each guest
// drives its own kart on its own machine, so steering has no lag, and streams that kart's motion to
// the host 30 times a second. The host answers 20 times a second with a snapshot of the world, the
// guest's own stats, and events (sounds, commentary, explosions, "you were hit", "you are hacked").
const NET = {
  prefix: 'bunker0-',
  version: 1,
  lib: 'https://cdn.jsdelivr.net/npm/peerjs@1.5.4/dist/peerjs.min.js',
  site: 'https://bunker-racer.vercel.app/', // invite links from a downloaded Bunker-0.html point here
  codeChars: 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789',
  seatNames: ['STEVE', 'SERGEY', 'DANEL'],
  timeout: 12000,
};
const r2 = (x) => Math.round(x * 100) / 100;
const v3a = (p) => [r2(p.x), r2(p.y), r2(p.z)];
const hexOf = (c) => (typeof c === 'number' ? c : new THREE.Color(c).getHex());

const Net = {
  role: null, // null = offline, 'host' or 'guest'
  peer: null, code: '', mute: 0,
  guests: [], ev: [], snapT: 0, // host
  conn: null, slot: 0, lobby: null, lastSeen: 0, sendT: 0, edges: {}, ctl: null, ents: null, // guest

  // ---------------------------------------------------------- used by the game code
  quiet(fn) { this.mute++; try { return fn(); } finally { this.mute--; } },
  live() {
    const R = window.Game && Game.race;
    return this.role === 'host' && !!R && R.cfg.net === 'host' && (Game.state === 'countdown' || Game.state === 'race');
  },
  all(e) { if (this.live() && !this.mute) this.ev.push(e); },
  toCar(car, e) { const g = car.net; if (g && g.inRace && this.role === 'host') g.ev.push(e); },
  racers() { return this.role === 'host' ? this.guests.slice() : []; },
  send(m) { if (this.conn && this.conn.open) { try { this.conn.send(m); } catch (_) { /* closing */ } } },
  seats() {
    if (this.role === 'host') return ['you · host', ...[1, 2].map((s) => (this.guests.some((g) => g.slot === s) ? 'online' : ''))];
    if (this.role === 'guest') {
      const taken = (this.lobby && this.lobby.taken) || [1, 0, 0];
      return [0, 1, 2].map((i) => (i === this.slot ? 'you' : i === 0 ? 'host' : taken[i] ? 'online' : ''));
    }
    return [];
  },
  inviteLink() {
    const u = new URL(location.protocol.startsWith('http') ? location.href : NET.site), dev = new URLSearchParams(location.search).get('peer');
    u.search = ''; u.hash = '';
    u.searchParams.set('join', this.code);
    if (dev) u.searchParams.set('peer', dev);
    return u.toString();
  },

  // ---------------------------------------------------------- connecting
  load() {
    if (window.Peer) return Promise.resolve();
    if (!this.loading) {
      this.loading = new Promise((res, rej) => {
        const s = document.createElement('script');
        s.src = NET.lib; s.async = true;
        s.onload = () => (window.Peer ? res() : rej(new Error('The networking library failed to start.')));
        s.onerror = () => { this.loading = null; s.remove(); rej(new Error('Could not download the networking library. Check your internet connection.')); };
        document.head.appendChild(s);
      });
    }
    return this.loading;
  },
  opts() {
    // development: ?peer=localhost:9000 talks to a local PeerServer instead of the PeerJS cloud
    const dev = new URLSearchParams(location.search).get('peer');
    if (!dev) return { debug: 1 };
    const [host, port] = dev.split(':');
    return { host, port: +port || 9000, path: '/', secure: false, debug: 1, config: { iceServers: [] } };
  },
  // our own random id (rooms are short codes; guests get long ones), retried if it is taken
  async openAs(idFor, len) {
    let err = null;
    for (let i = 0; i < 4; i++) {
      const code = Array.from({ length: len }, () => pick(NET.codeChars.split(''))).join('');
      try { await this.open(idFor(code)); return code; } catch (e) { err = e; if (e.type !== 'unavailable-id') break; }
    }
    throw err || new Error('Could not connect.');
  },
  open(id) {
    return new Promise((res, rej) => {
      const p = new Peer(id, this.opts());
      let ok = false;
      const t = setTimeout(() => { if (!ok) { p.destroy(); rej(new Error('The matchmaking server did not answer. Check your connection and try again.')); } }, 15000);
      p.on('open', () => { ok = true; clearTimeout(t); this.peer = p; res(p); });
      p.on('error', (e) => { if (!ok) { clearTimeout(t); p.destroy(); rej(e); } else this.peerError(e); });
      // the signalling socket can drop while a race keeps running peer to peer; reconnect quietly
      p.on('disconnected', () => setTimeout(() => { if (this.peer === p && !p.destroyed && p.disconnected) p.reconnect(); }, 1500));
    });
  },
  peerError(e) {
    if (e.type === 'peer-unavailable' && this.joinFail) this.joinFail(new Error(`Room ${this.joining} not found. Check the code; the host must keep the game open.`));
    else console.warn('network:', e.type || '', e.message || e);
  },
  explain(e) {
    const type = e && e.type;
    if (type === 'browser-incompatible') return 'This browser does not support WebRTC. Try Chrome, Edge, Firefox or Safari.';
    if (type === 'network' || type === 'server-error' || type === 'socket-error' || type === 'socket-closed') return 'Could not reach the matchmaking server (PeerJS cloud). Check your connection and try again.';
    return (e && e.message) || String(e);
  },

  async host() {
    HUD.netMsg('Opening a room…');
    try {
      await this.load();
      this.leave(true);
      this.code = await this.openAs((code) => NET.prefix + code, 5);
      this.role = 'host'; this.guests = []; this.ev = [];
      this.keepAlive();
      this.peer.on('connection', (conn) => this.onGuest(conn));
      HUD.netMsg('Room open. Send the code or the invite link to your friends, then start the race.');
    } catch (e) {
      this.leave(true);
      HUD.netMsg(this.explain(e), true);
    }
    HUD.renderOnline();
  },
  async join(code) {
    code = String(code || '').toUpperCase().replace(/[^A-Z0-9]/g, '');
    HUD.netMsg(`Connecting to room ${code}…`);
    try {
      await this.load();
      this.leave(true);
      await this.openAs((id) => `${NET.prefix}g-${id}`, 12);
      this.joining = code;
      const conn = this.peer.connect(NET.prefix + code, { reliable: true, serialization: 'json' });
      await new Promise((res, rej) => {
        const t = setTimeout(() => rej(new Error('Could not reach the host. Check the code. Very strict networks (some offices and schools) block game connections.')), 20000);
        this.joinFail = (e) => { clearTimeout(t); rej(e); };
        conn.on('open', () => { clearTimeout(t); res(); });
        conn.on('error', (e) => { clearTimeout(t); rej(e); });
      });
      this.joinFail = null;
      this.role = 'guest'; this.conn = conn; this.code = code; this.lobby = null; this.slot = 0;
      this.lastSeen = performance.now();
      conn.on('data', (m) => this.fromHost(m));
      conn.on('close', () => this.lost('The host closed the room.'));
      conn.send({ t: 'hello', v: NET.version });
      HUD.netMsg('Connected. Waiting for the host to start the race.');
    } catch (e) {
      this.joinFail = null;
      this.leave(true);
      HUD.netMsg(this.explain(e), true);
    }
    HUD.renderOnline();
  },
  leave(silent) {
    const peer = this.peer, conns = this.guests.map((g) => g.conn).concat(this.conn ? [this.conn] : []);
    for (const c of conns) { try { c.send({ t: 'bye' }); } catch (_) { /* closed */ } }
    this.role = null; this.guests = []; this.conn = null; this.peer = null; this.code = ''; this.lobby = null;
    setTimeout(() => { for (const c of conns) { try { c.close(); } catch (_) { /* closed */ } } if (peer) peer.destroy(); }, 200);
    if (window.Game && Game.race && Game.race.cfg.net === 'guest') { HUD.pause(false); Game.toMenu(); }
    if (!silent) HUD.renderOnline();
  },
  lost(msg) {
    if (this.role !== 'guest') return;
    this.leave(true);
    HUD.netMsg(msg, true);
    HUD.renderOnline();
  },
  // liveness: both sides ping every second on a timer, so a race survives a slow frame
  ping() {
    if (!this.role) return;
    const now = performance.now(), frozen = now - (this.lastPing || now) > 3000;
    this.lastPing = now;
    if (frozen) { this.lastSeen = now; for (const g of this.guests) g.last = now; } // our page stalled (loading a race), not theirs
    if (this.role === 'host') {
      for (const g of this.guests.slice()) {
        if (now - g.last > NET.timeout) this.drop(g);
        else { try { g.conn.send({ t: 'p' }); } catch (_) { /* closing */ } }
      }
    } else if (now - this.lastSeen > NET.timeout) this.lost('Lost the connection to the host.');
    else this.send({ t: 'p' });
  },

  // ---------------------------------------------------------- host
  onGuest(conn) {
    const g = { conn, slot: 0, inRace: false, ev: [], last: performance.now() };
    conn.on('data', (m) => { g.last = performance.now(); this.fromGuest(g, m); });
    conn.on('close', () => this.drop(g));
    conn.on('error', () => this.drop(g));
  },
  fromGuest(g, m) {
    if (!m || typeof m !== 'object' || this.role !== 'host') return;
    if (m.t === 'I') this.guestState(g, m);
    else if (m.t === 'H') { const car = this.carOf(g); if (car && car.hack) Game.endHack(car, !!m.ok); }
    else if (m.t === 'hello') {
      if (m.v !== NET.version) { g.conn.send({ t: 'err', msg: 'The host runs a different version of the game. Reload the page on both computers.' }); return; }
      const free = [1, 2].find((s) => !this.guests.some((o) => o.slot === s));
      if (!free) { g.conn.send({ t: 'err', msg: 'The room is full: three humans are already in.' }); return; }
      g.slot = free;
      this.guests.push(g);
      g.conn.send({ t: 'welcome', slot: free });
      this.lobbyAll();
      HUD.netMsg(`${NET.seatNames[free]} joined the room.`);
      HUD.renderOnline();
    } else if (m.t === 'bye') this.drop(g);
  },
  drop(g) {
    const i = this.guests.indexOf(g);
    if (i < 0) return;
    this.guests.splice(i, 1);
    try { g.conn.close(); } catch (_) { /* closed */ }
    const car = this.carOf(g);
    if (car) {
      const R = Game.race;
      car.net = null; car.ai = true; car.hack = null; car.skill = 0.95;
      R.remote = R.remote.filter((c) => c !== car); R.players = R.players.filter((c) => c !== car);
      if (!car.finished) HUD.say('fable', `${car.name} lost the connection. Astra and I have the wheel.`);
    }
    this.lobbyAll();
    HUD.netMsg(`${NET.seatNames[g.slot]} left the room.`);
    HUD.renderOnline();
  },
  carOf(g) {
    const R = Game.race;
    return R && R.cfg.net === 'host' ? R.cars.find((c) => c.net === g) || null : null;
  },
  lobbyAll() {
    if (this.role !== 'host') return;
    const R = Game.race, racing = !!(R && R.cfg.net === 'host' && Game.state !== 'demo');
    const taken = [1, ...[1, 2].map((s) => (this.guests.some((g) => g.slot === s) ? 1 : 0))];
    const m = { t: 'lobby', taken, laps: HUD.menuCfg.laps, diff: HUD.menuCfg.diff, racing };
    for (const g of this.guests) { try { g.conn.send(m); } catch (_) { /* closing */ } }
  },
  startRace(cfg) {
    this.ev = []; this.snapT = 0; this.ids = 0;
    for (const g of this.guests) {
      g.inRace = true; g.ev = [];
      try { g.conn.send({ t: 'start', laps: cfg.laps, diff: cfg.diff }); } catch (_) { /* closing */ }
    }
  },
  backToLobby() {
    for (const g of this.guests) { g.inRace = false; try { g.conn.send({ t: 'menu' }); } catch (_) { /* closing */ } }
    setTimeout(() => this.lobbyAll(), 0);
  },
  ending(R) {
    const idx = (c) => R.cars.indexOf(c);
    this.ev.push(['ending', {
      so: (R.sorted || R.cars).map(idx),
      f: R.cars.map((c) => [c.finished ? 1 : 0, r2(c.finishTime), c.finishOrder]),
      st: R.humans.map((h) => h.stats),
    }]);
    this.flush();
  },
  guestState(g, m) {
    const car = this.carOf(g);
    if (!car || typeof m.s !== 'number' || !isFinite(m.s)) return;
    Object.assign(car, {
      s: m.s, d: m.d, h: m.h, vh: m.vh, v: m.v, psi: m.psi, drift: m.dr, driftCharge: m.dc,
      airborne: !!m.air, falling: !!m.fall, spinA: m.spA, boostT: m.bT, boostK: m.bK,
    });
    car.startGas = m.sg === null ? undefined : m.sg;
    car.stats.falls = m.falls | 0;
    if (car.finished) return;
    if (m.lap > car.lap) { while (car.lap < m.lap && !car.finished) { car.lap++; Game.onLap(car); } } else car.lap = m.lap;
    const ni = car.netIn || (car.netIn = { gas: 0, brake: 0, steer: 0, fire: false, pressed: {} });
    ni.gas = m.gas ? 1 : 0; ni.fire = !!m.fire;
    if (m.pi) ni.pressed.item = true;
    if (m.pf) ni.pressed.fire = true;
  },
  nid(o) { return o.nid || (o.nid = ++this.ids); },
  snapshot(R) {
    const idx = new Map(R.cars.map((c, i) => [c, i]));
    const flags = (c) => (c.boostT > 0 ? 1 : 0) | (c.neuroT > 0 ? 2 : 0) | (c.shieldT > 0 ? 4 : 0) | (c.hack ? 8 : 0) | (c.aiHackT > 0 ? 16 : 0)
      | (c.disabledT > 0 ? 32 : 0) | (c.finished ? 64 : 0) | (c.falling ? 128 : 0) | (c.airborne ? 256 : 0);
    return {
      t: 'S', st: Game.state === 'countdown' ? 'c' : 'r', cd: r2(R.countdown), rt: r2(R.t),
      c: R.cars.map((c) => [r2(c.s), r2(c.d), r2(c.h), r2(c.psi), r2(c.v), c.lap, r2(c.spinA), flags(c), c.drift, r2(c.driftCharge), c.place, r2(c.vh), c.bci, c.weapon || 0]),
      pk: R.boxRows.map((row) => row.boxes.map((b) => (b.active ? 1 : 0)).join('')).join(''),
      ch: R.chips.map((ch) => (ch.active ? 1 : 0)).join(''),
      pr: R.proj.map((p) => [this.nid(p), p.kind, r2(p.s), r2(p.d), r2(p.h), r2(p.v)]),
      hz: R.hazards.map((z) => [this.nid(z), r2(z.s), r2(z.d)]),
      dr: R.drones.map((d) => [this.nid(d), ...v3a(d.m.position), idx.get(d.target), d.phase === 'chase' ? 1 : 0]),
      cr: R.crates.map((k) => [this.nid(k), r2(k.s), r2(k.d), r2(k.h)]),
      om: [r2(R.omega.stun), R.omega.aim ? idx.get(R.omega.aim.car) : -1],
      wv: [R.wave.active ? 1 : 0, r2(R.wave.p), r2(R.wave.sp || 0)],
      mc: [R.mc.state === 'away' ? 0 : 1, r2(R.mc.s), r2(R.mc.d), r2(R.mc.h)],
      pc: r2(World.portalG.charge), hd: R.humansDone, so: (R.sorted || R.cars).map((c) => idx.get(c)),
      sh: r2(Game.shake), kf: r2(Game.killFlash || 0),
    };
  },
  own(c) {
    return {
      it: c.item, ic: c.itemCount, ro: r2(c.roulette), am: c.ammo, ne: r2(c.neuro), neT: r2(c.neuroT),
      spT: r2(c.spinT), stT: r2(c.stallT), inT: r2(c.invulnT), shT: r2(c.shieldT), diT: r2(c.disabledT), aiH: r2(c.aiHackT),
      hk: c.hack ? 1 : 0, fin: c.finished ? 1 : 0, fT: r2(c.finishTime), fO: c.finishOrder, wd: r2(c.waveDist ?? 1e4),
    };
  },
  flush() {
    const R = Game.race;
    if (!R || R.cfg.net !== 'host') return;
    const base = this.snapshot(R), ev = this.ev;
    this.ev = [];
    for (const g of this.guests) {
      if (!g.inRace) continue;
      const car = this.carOf(g);
      const m = Object.assign({}, base, { o: car ? this.own(car) : null, e: ev.concat(g.ev) });
      g.ev = [];
      try { g.conn.send(m); } catch (_) { /* closing */ }
    }
  },
  tick(dt) {
    if (this.role !== 'host') return;
    const R = Game.race;
    if (!R || R.cfg.net !== 'host' || !(Game.state === 'countdown' || Game.state === 'race' || Game.state === 'ending')) return;
    this.snapT -= dt;
    if (this.snapT <= 0) { this.snapT = 0.05; this.flush(); }
  },
  // background tabs get no animation frames and slow timers, but worker messages still arrive
  keepAlive() {
    if (this.worker !== undefined) return;
    this.worker = null;
    try {
      const url = URL.createObjectURL(new Blob(['setInterval(() => postMessage(0), 50);'], { type: 'text/javascript' }));
      this.worker = new Worker(url);
      this.worker.onmessage = () => {
        const R = Game.race;
        if (this.role !== 'host' || !R || R.cfg.net !== 'host' || Game.paused) return;
        if (performance.now() - (Game.frameAt || 0) > 250) Game.headless(0.05);
      };
    } catch (_) { /* file:// pages may not start workers; the race then pauses while hidden */ }
  },
  // broadcast the host's shared sounds, lines and effects (personal ones go through Game.sfx/note)
  hook() {
    const wrap = (obj, name, enc) => {
      const orig = obj[name];
      obj[name] = function (...a) {
        if (Net.mute || !Net.live()) return orig.apply(this, a);
        const r = Net.quiet(() => orig.apply(this, a));
        Net.ev.push(enc(...a));
        return r;
      };
    };
    const idx = (car) => Game.race.cars.indexOf(car);
    wrap(Sound, 'play', (n) => ['snd', n]);
    wrap(HUD, 'say', (who, text) => ['say', who, text]);
    wrap(HUD, 'countdown', (t) => ['cd', t]);
    wrap(HUD, 'flash', (c) => ['flash', c]);
    wrap(HUD, 'banner', (a, b) => ['banner', a, b]);
    wrap(World, 'cheer', (who) => ['cheer', who || 0]);
    wrap(World, 'setPrinterStatus', (n, total, done) => ['printer', n, total, done ? 1 : 0]);
    wrap(Particles, 'burst', (p, color, count, speed, size, life, o = {}) => ['burst', v3a(p), hexOf(color), count, r2(speed), r2(size), r2(life), o.drag || 0, o.grav || 0]);
    wrap(Game.fx, 'explode', (pos, color, k) => ['fx', 'explode', v3a(pos), hexOf(color), k === undefined ? 1 : k]);
    wrap(Game.fx, 'sparks', (car, side) => ['fx', 'sparks', idx(car), side]);
    wrap(Game.fx, 'shieldBlock', (car) => ['fx', 'shieldBlock', idx(car)]);
    wrap(Game.fx, 'guardZap', (car, at) => ['fx', 'guardZap', idx(car), v3a(at)]);
  },

  // ---------------------------------------------------------- guest
  fromHost(m) {
    this.lastSeen = performance.now();
    if (!m || typeof m !== 'object' || this.role !== 'guest') return;
    const R = Game.race, inRace = R && R.cfg.net === 'guest';
    switch (m.t) {
      case 'S': if (inRace) this.snap(m); break;
      case 'welcome': this.slot = m.slot; HUD.renderOnline(); break;
      case 'lobby': {
        this.lobby = m;
        const diff = ['EASY', 'MEAN', 'INSANE'][m.diff] || 'MEAN';
        HUD.netMsg(`You are ${NET.seatNames[this.slot]}. Host settings: ${m.laps} lap${m.laps > 1 ? 's' : ''}, aliens ${diff}.` + (m.racing && !inRace ? ' A race is running; you join the next one.' : ' Waiting for the host to start.'));
        HUD.renderOnline();
        break;
      }
      case 'start': this.begin(m); break;
      case 'menu':
        if (inRace) { HUD.pause(false); Game.toMenu(); }
        HUD.netMsg('The host went back to the menu. Waiting for the next race.');
        break;
      case 'err': { const msg = m.msg; this.leave(true); HUD.netMsg(msg, true); HUD.renderOnline(); break; }
      case 'bye': this.lost('The host closed the room.'); break;
    }
  },
  begin(m) {
    HUD.pause(false);
    for (const id of ['menu', 'results', 'ending']) document.getElementById(id).hidden = true;
    this.ents = { pr: new Map(), hz: new Map(), dr: new Map(), cr: new Map() };
    this.sendT = 0; this.edges = {}; this.ctl = null; this.waveP = -1e9; this.waveAt = performance.now();
    Game.start({ players: 1, laps: m.laps, diff: m.diff, gfx: HUD.menuCfg.gfx, net: 'guest', slot: this.slot });
  },
  snap(S) {
    if (Game.state !== 'ending') this.world(S);
    for (const e of S.e || []) this.event(e);
  },
  world(S) {
    const R = Game.race, T = Track, own = R.local[0];
    if (S.st === 'c') { if (Game.state === 'countdown') R.countdown = S.cd; } else if (Game.state === 'countdown') Game.state = 'race';
    R.t = S.rt;
    S.c.forEach((a, i) => {
      const c = R.cars[i];
      c.place = a[10]; c.bci = a[12]; c.weapon = a[13] || null;
      if (c === own) return;
      const f = a[7];
      c.boostT = f & 1 ? 1 : 0; c.neuroT = f & 2 ? 1 : 0; c.shieldT = f & 4 ? 3 : 0;
      c.hack = f & 8 ? c.hack || {} : null; c.aiHackT = f & 16 ? 1 : 0; c.disabledT = f & 32 ? 1 : 0;
      if (f & 64 && !c.finished) c.finishFade = 1;
      c.finished = !!(f & 64); c.falling = !!(f & 128); c.airborne = !!(f & 256);
      c.spinA = a[6]; c.drift = a[8]; c.driftCharge = a[9]; c.vh = a[11]; c.v = a[4];
      const p = a[5] * T.L + a[0];
      if (!c.nt) { c.s = a[0]; c.lap = a[5]; c.d = a[1]; c.h = a[2]; c.psi = a[3]; }
      c.nt = { p, d: a[1], h: a[2], psi: a[3] };
    });
    const o = S.o;
    if (o) {
      Object.assign(own, {
        item: o.it, itemCount: o.ic, roulette: o.ro, ammo: o.am, neuro: o.ne, neuroT: o.neT, spinT: o.spT,
        stallT: o.stT, invulnT: o.inT, shieldT: o.shT, disabledT: o.diT, aiHackT: o.aiH,
        finishTime: o.fT, finishOrder: o.fO, waveDist: o.wd,
      });
      if (!o.hk && own.hack) own.hack = null;
      if (o.fin && !own.finished) { own.finished = true; own.finishFade = 1; own.hack = null; }
    }
    let k = 0;
    for (const row of R.boxRows) for (const b of row.boxes) { const on = S.pk[k++] === '1'; if (b.active && !on) b.t = 3; b.active = on; }
    R.chips.forEach((ch, i) => { ch.active = S.ch[i] === '1'; });
    const E = this.ents;
    this.sync(E.pr, S.pr, R.proj, (a) => ({ kind: a[1], m: Game.add(Game.projMesh(a[1])) }), (p, a) => { p.s = a[2]; p.d = a[3]; p.h = a[4]; p.v = a[5]; });
    this.sync(E.hz, S.hz, R.hazards, () => ({ kind: 'slime', m: Game.add(Game.slimeMesh()) }), (z, a) => { z.s = a[1]; z.d = a[2]; });
    this.sync(E.dr, S.dr, R.drones, (a) => {
      const d = { m: Game.add(Game.droneMesh()), to: new V3(a[1], a[2], a[3]) };
      d.m.position.copy(d.to);
      return d;
    }, (d, a) => { d.to.set(a[1], a[2], a[3]); d.target = R.cars[a[4]]; d.phase = a[5] ? 'chase' : 'in'; });
    this.sync(E.cr, S.cr, R.crates, () => Game.crateMesh(), (c, a) => { c.s = a[1]; c.d = a[2]; c.h = a[3]; });
    R.omega.stun = S.om[0];
    const aimCar = S.om[1] >= 0 ? R.cars[S.om[1]] : null;
    if (R.omega.aim && !aimCar) { Game.scene.remove(R.omega.aim.beam); R.omega.aim = null; }
    if (aimCar) {
      if (!R.omega.aim) R.omega.aim = { car: aimCar, beam: Game.add(new THREE.Mesh(Game.shared.beamGeo, glowMat(0xff2a3d, 0.8))) };
      R.omega.aim.car = aimCar;
    }
    R.wave.active = !!S.wv[0]; R.wave.sp = S.wv[2]; this.waveP = S.wv[1]; this.waveAt = performance.now();
    const M = R.mc;
    M.vis = !!S.mc[0]; M.ts = S.mc[1]; M.td = S.mc[2]; M.th = S.mc[3];
    World.portalG.charge = S.pc;
    R.humansDone = S.hd;
    R.sorted = S.so.map((i) => R.cars[i]);
    Game.shake = Math.max(Game.shake, S.sh);
    Game.killFlash = Math.max(Game.killFlash || 0, S.kf);
  },
  sync(map, rows, list, make, update) {
    const seen = new Set();
    for (const a of rows) {
      let o = map.get(a[0]);
      if (!o) { o = make(a); map.set(a[0], o); }
      update(o, a);
      seen.add(a[0]);
    }
    for (const [id, o] of map) if (!seen.has(id)) { Game.scene.remove(o.m); map.delete(id); }
    list.length = 0;
    for (const o of map.values()) list.push(o);
  },
  event(e) {
    const R = Game.race, own = R.local[0], fx = Game.fx, opt = (x) => (x === null ? undefined : x);
    switch (e[0]) {
      case 'snd': Sound.play(e[1]); break;
      case 'say': HUD.say(e[1], e[2]); break;
      case 'cd': HUD.countdown(e[1]); break;
      case 'flash': HUD.flash(e[1]); break;
      case 'banner': HUD.banner(e[1], e[2]); break;
      case 'cheer': World.cheer(e[1] || undefined); break;
      case 'printer': World.setPrinterStatus(e[1], e[2], !!e[3]); break;
      case 'portal': World.portalG.flash = 1; break;
      case 'burst': Particles.burst(new V3(...e[1]), e[2], e[3], e[4], e[5], e[6], { drag: e[7], grav: e[8] }); break;
      case 'fx':
        if (e[1] === 'explode') fx.explode(new V3(...e[2]), e[3], e[4]);
        else if (e[1] === 'sparks') fx.sparks(R.cars[e[2]], e[3]);
        else if (e[1] === 'shieldBlock') fx.shieldBlock(R.cars[e[2]]);
        else if (e[1] === 'guardZap') fx.guardZap(R.cars[e[2]], new V3(...e[3]));
        break;
      case 'msg': HUD.msg(0, e[1], opt(e[2]), opt(e[3])); break;
      case 'boost': own.boost(e[1], e[2]); break;
      case 'hit':
        own.spinT = Math.max(own.spinT, e[1]); own.invulnT = e[1] + 0.5; own.v *= e[2];
        if (e[3]) { own.vh = e[3]; own.airborne = true; }
        own.drift = 0; own.driftCharge = 0;
        break;
      case 'vmul': own.v *= e[1]; break;
      case 'hack': if (!own.finished) { own.hack = e[1]; own.drift = 0; } break;
      case 'music': Sound.intensity = Math.max(Sound.intensity, e[1]); break;
      case 'ending': this.finale(e[1]); break;
    }
  },
  finale(d) {
    const R = Game.race;
    R.sorted = d.so.map((i) => R.cars[i]);
    d.f.forEach((f, i) => { const c = R.cars[i]; c.finished = !!f[0]; c.finishTime = f[1]; c.finishOrder = f[2]; });
    R.humans.forEach((h, i) => { if (d.st[i]) h.stats = d.st[i]; });
    Game.startEnding();
  },
  // one guest frame: drive our kart, glide everyone else toward the host's state, report back
  guestStep(dt) {
    const R = Game.race, own = R.local[0], T = Track;
    if (Game.state === 'countdown') {
      R.countdown -= dt;
      const st = Input.read(0, 1);
      if (st.gas && own.startGas === undefined) own.startGas = R.countdown;
      if (!st.gas) own.startGas = undefined;
      own.v = 0; own.update(0, { gas: 0, brake: 0, steer: 0 });
      this.ctl = st;
    } else {
      R.t += dt;
      for (let i = 0; i < 2; i++) {
        const h = dt / 2;
        let c = { gas: 0, brake: 0, steer: 0 };
        if (!own.finished) {
          const st = Input.read(0, 1);
          st.driftPressed = st.pressed.drift;
          if (st.pressed.item) this.edges.item = true;
          if (st.pressed.fire) this.edges.fire = true;
          this.ctl = st;
          if (own.hack) { Game.updateHack(own, st, h); c = aiControl(own, h, R); } else c = st;
        }
        own.update(h, c);
        Game.pads(own);
        Game.collideCars(own);
      }
    }
    const k = 1 - Math.exp(-10 * dt);
    for (const c of R.cars) {
      if (c === own || !c.nt) continue;
      const nt = c.nt, fwd = c.v * Math.cos(nt.psi) * dt;
      nt.p += fwd;
      const p0 = c.lap * T.L + c.s, err = nt.p - p0;
      const p = Math.abs(err) > 40 ? nt.p : p0 + fwd + err * k;
      c.lap = Math.floor(p / T.L); c.s = p - c.lap * T.L;
      const dd = T.dDiff(nt.d, c.d, c.s);
      c.d = Math.abs(dd) > 15 ? nt.d : c.d + dd * k;
      if (T.isWrap(c.s)) c.d = T.wrapD(c.d);
      c.h = Math.abs(nt.h - c.h) > 20 ? nt.h : damp(c.h, nt.h, 12, dt);
      c.psi = damp(c.psi, nt.psi, 12, dt);
    }
    for (const p of R.proj) { if (p.kind !== 'gbomb') p.s += p.v * dt; Game.placeProj(p); }
    R.hazards.forEach((z, i) => Game.placeHazard(z, i));
    for (const d of R.drones) {
      d.m.position.lerp(d.to, 1 - Math.exp(-12 * dt));
      if (d.target) d.m.lookAt(d.target.pos);
      if (Math.random() < 0.5) Particles.spawn(d.m.position, new V3(rand(-2, 2), rand(-2, 2), rand(-2, 2)), 0xff2a3d, 1.2, 0.3);
    }
    for (const c of R.crates) Game.placeCrate(c);
    if (R.omega.aim) {
      Game.setBeam(R.omega.aim.beam, World.omegaG.g.position, R.omega.aim.car.pos, 0.5 + Math.random() * 0.8);
      R.omega.aim.beam.material.opacity = 0.4 + Math.random() * 0.5;
    }
    if (R.wave.active) { R.wave.p = this.waveP + (R.wave.sp || 0) * (performance.now() - this.waveAt) / 1000; Game.placeWave(); } else R.wave.mesh.visible = false;
    const M = R.mc;
    if (M.vis) {
      if (!M.mesh.visible) { M.s = M.ts; M.d = M.td; M.h = M.th; }
      M.s += T.sDiff(M.ts, M.s) * k; M.d = damp(M.d, M.td, 10, dt); M.h = damp(M.h, M.th, 10, dt);
      M.mesh.visible = true;
      Game.placeMcAfee();
    } else M.mesh.visible = false;
    const lead = R.humans.filter((c) => !c.finished).sort((a, b) => b.progress - a.progress)[0];
    if (lead) World.omegaG.target.copy(lead.pos);
    Game.updateBeams(dt);
    this.sendT -= dt;
    if (this.sendT <= 0) { this.sendT = 1 / 30; this.report(own); }
  },
  report(c) {
    const st = this.ctl || {};
    this.send({
      t: 'I', s: r2(c.s), d: r2(c.d), h: r2(c.h), vh: r2(c.vh), v: r2(c.v), psi: Math.round(c.psi * 1000) / 1000, lap: c.lap,
      dr: c.drift, dc: r2(c.driftCharge), air: c.airborne ? 1 : 0, fall: c.falling ? 1 : 0, spA: r2(c.spinA),
      bT: r2(c.boostT), bK: r2(c.boostK), sg: c.startGas === undefined ? null : r2(c.startGas), falls: c.stats.falls,
      gas: st.gas ? 1 : 0, fire: st.fire ? 1 : 0, pi: this.edges.item ? 1 : 0, pf: this.edges.fire ? 1 : 0,
    });
    this.edges = {};
  },
};
Net.hook();
setInterval(() => Net.ping(), 1000);
G.Net = Net;
window.Net = Net;

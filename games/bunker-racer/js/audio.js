'use strict';
// Procedural sound: engines, effects and a synth soundtrack. No audio files.
const Sound = {
  ctx: null, master: null, sfx: null, music: null, muted: false,
  engines: [], musicOn: false, step: 0, nextT: 0, intensity: 0, noiseBuf: null,

  init() {
    if (this.ctx) { if (this.ctx.state === 'suspended') this.ctx.resume(); return; }
    const AC = window.AudioContext || window.webkitAudioContext;
    if (!AC) return;
    this.ctx = new AC();
    this.master = this.ctx.createGain(); this.master.gain.value = 0.8;
    const comp = this.ctx.createDynamicsCompressor();
    this.master.connect(comp); comp.connect(this.ctx.destination);
    this.sfx = this.ctx.createGain(); this.sfx.gain.value = 0.7; this.sfx.connect(this.master);
    this.music = this.ctx.createGain(); this.music.gain.value = 0.32; this.music.connect(this.master);
    const len = this.ctx.sampleRate * 1.5;
    this.noiseBuf = this.ctx.createBuffer(1, len, this.ctx.sampleRate);
    const d = this.noiseBuf.getChannelData(0);
    for (let i = 0; i < len; i++) d[i] = Math.random() * 2 - 1;
  },
  toggleMute() {
    this.muted = !this.muted;
    if (this.master) this.master.gain.value = this.muted ? 0 : 0.8;
    return this.muted;
  },
  get t() { return this.ctx ? this.ctx.currentTime : 0; },

  tone(freq, dur, opts = {}) {
    if (!this.ctx) return;
    const t0 = this.t + (opts.delay || 0);
    const o = this.ctx.createOscillator();
    const g = this.ctx.createGain();
    o.type = opts.type || 'square';
    o.frequency.setValueAtTime(freq, t0);
    if (opts.to) o.frequency.exponentialRampToValueAtTime(Math.max(20, opts.to), t0 + dur);
    const v = opts.vol || 0.2;
    g.gain.setValueAtTime(0.0001, t0);
    g.gain.exponentialRampToValueAtTime(v, t0 + (opts.attack || 0.01));
    g.gain.exponentialRampToValueAtTime(0.0001, t0 + dur);
    o.connect(g); g.connect(opts.dest || this.sfx);
    o.start(t0); o.stop(t0 + dur + 0.05);
  },
  noise(dur, opts = {}) {
    if (!this.ctx) return;
    const t0 = this.t + (opts.delay || 0);
    const src = this.ctx.createBufferSource(); src.buffer = this.noiseBuf;
    const f = this.ctx.createBiquadFilter();
    f.type = opts.filter || 'lowpass';
    f.frequency.setValueAtTime(opts.freq || 1200, t0);
    if (opts.to) f.frequency.exponentialRampToValueAtTime(opts.to, t0 + dur);
    f.Q.value = opts.q || 1;
    const g = this.ctx.createGain();
    g.gain.setValueAtTime(opts.vol || 0.3, t0);
    g.gain.exponentialRampToValueAtTime(0.0001, t0 + dur);
    src.connect(f); f.connect(g); g.connect(opts.dest || this.sfx);
    src.start(t0); src.stop(t0 + dur + 0.05);
  },

  // ---- effects
  play(name) {
    if (!this.ctx || this.muted) return;
    switch (name) {
      case 'beep': this.tone(660, 0.18, { type: 'square', vol: 0.18 }); break;
      case 'go': this.tone(1320, 0.5, { type: 'square', vol: 0.2 }); this.tone(990, 0.5, { type: 'sawtooth', vol: 0.08 }); break;
      case 'pickup': [523, 659, 784, 1046].forEach((f, i) => this.tone(f, 0.12, { delay: i * 0.05, type: 'triangle', vol: 0.15 })); break;
      case 'chip': [392, 587, 784, 1175, 1568].forEach((f, i) => this.tone(f, 0.2, { delay: i * 0.06, type: 'sine', vol: 0.2 })); break;
      case 'boost': this.noise(0.6, { freq: 400, to: 4000, filter: 'bandpass', q: 2, vol: 0.35 }); this.tone(120, 0.5, { to: 400, type: 'sawtooth', vol: 0.08 }); break;
      case 'laser': this.tone(1800, 0.12, { to: 200, type: 'square', vol: 0.07 }); break;
      case 'rail': this.tone(3000, 0.35, { to: 80, type: 'sawtooth', vol: 0.12 }); this.noise(0.3, { freq: 3000, to: 200, vol: 0.15 }); break;
      case 'rocket': this.noise(0.8, { freq: 800, to: 200, filter: 'bandpass', vol: 0.25 }); break;
      case 'boom': this.noise(0.9, { freq: 900, to: 60, vol: 0.5 }); this.tone(90, 0.6, { to: 30, type: 'sine', vol: 0.4 }); break;
      case 'hit': this.noise(0.25, { freq: 2000, to: 300, vol: 0.3 }); this.tone(200, 0.2, { to: 60, type: 'square', vol: 0.12 }); break;
      case 'bump': this.noise(0.12, { freq: 500, vol: 0.25 }); break;
      case 'spin': this.tone(700, 0.6, { to: 120, type: 'triangle', vol: 0.15 }); break;
      case 'slime': this.noise(0.3, { freq: 300, to: 900, filter: 'bandpass', q: 6, vol: 0.3 }); break;
      case 'jump': this.tone(200, 0.4, { to: 900, type: 'sine', vol: 0.15 }); break;
      case 'item': this.tone(440, 0.08, { type: 'square', vol: 0.1 }); this.tone(880, 0.1, { delay: 0.06, type: 'square', vol: 0.1 }); break;
      case 'roulette': this.tone(rand(500, 1200), 0.04, { type: 'square', vol: 0.05 }); break;
      case 'alarm': [0, 0.25, 0.5].forEach((d) => { this.tone(880, 0.12, { delay: d, type: 'square', vol: 0.16 }); this.tone(587, 0.12, { delay: d + 0.12, type: 'square', vol: 0.16 }); }); break;
      case 'hackok': [784, 988, 1175, 1568].forEach((f, i) => this.tone(f, 0.15, { delay: i * 0.07, type: 'square', vol: 0.12 })); break;
      case 'hackbad': this.tone(220, 0.5, { to: 55, type: 'sawtooth', vol: 0.2 }); break;
      case 'key': this.tone(1200, 0.05, { type: 'square', vol: 0.08 }); break;
      case 'wrong': this.tone(150, 0.15, { type: 'square', vol: 0.15 }); break;
      case 'shield': this.tone(300, 0.6, { to: 1200, type: 'sine', vol: 0.2 }); this.tone(450, 0.6, { to: 1800, type: 'sine', vol: 0.1 }); break;
      case 'zap': this.noise(0.2, { freq: 6000, to: 1500, filter: 'highpass', vol: 0.25 }); this.tone(2400, 0.15, { to: 600, type: 'sawtooth', vol: 0.08 }); break;
      case 'kill':
        this.tone(55, 2.5, { type: 'sawtooth', vol: 0.35 });
        this.tone(110, 2, { to: 27, type: 'square', vol: 0.2 });
        this.noise(2.5, { freq: 3000, to: 40, vol: 0.5 });
        [1046, 784, 523, 392].forEach((f, i) => this.tone(f, 0.4, { delay: 0.3 + i * 0.15, type: 'square', vol: 0.12 }));
        break;
      case 'lap': [659, 784, 988].forEach((f, i) => this.tone(f, 0.18, { delay: i * 0.09, type: 'square', vol: 0.14 })); break;
      case 'finish': [523, 659, 784, 1046, 1318].forEach((f, i) => this.tone(f, 0.3, { delay: i * 0.1, type: 'triangle', vol: 0.2 })); this.tone(130, 1.5, { to: 1000, type: 'sine', vol: 0.15 }); break;
      case 'crate': this.tone(300, 0.25, { to: 150, type: 'triangle', vol: 0.2 }); this.noise(0.2, { freq: 600, vol: 0.2 }); break;
      case 'printer':
        for (let i = 0; i < 8; i++) { this.noise(0.08, { delay: i * 0.13, freq: 2500, filter: 'bandpass', q: 3, vol: 0.25 }); this.tone(90, 0.08, { delay: i * 0.13 + 0.06, type: 'square', vol: 0.12 }); }
        break;
      case 'portal': this.tone(80, 3, { to: 2400, type: 'sawtooth', vol: 0.15 }); this.tone(120, 3, { to: 3600, type: 'sine', vol: 0.15 }); this.noise(3, { freq: 200, to: 8000, filter: 'bandpass', vol: 0.2 }); break;
      case 'whoosh': this.noise(0.5, { freq: 300, to: 3000, filter: 'bandpass', q: 1.5, vol: 0.2 }); break;
    }
  },

  // ---- engines (one per local player)
  setEngines(n) {
    if (!this.ctx) return;
    this.engines.forEach((e) => { try { e.o1.stop(); e.o2.stop(); } catch (_) {} e.g.disconnect(); });
    this.engines = [];
    for (let i = 0; i < n; i++) {
      const o1 = this.ctx.createOscillator(); o1.type = 'sawtooth';
      const o2 = this.ctx.createOscillator(); o2.type = 'square';
      const f = this.ctx.createBiquadFilter(); f.type = 'lowpass'; f.frequency.value = 600; f.Q.value = 3;
      const g = this.ctx.createGain(); g.gain.value = 0;
      const p = this.ctx.createStereoPanner ? this.ctx.createStereoPanner() : null;
      o1.connect(f); o2.connect(f); f.connect(g);
      if (p) { p.pan.value = n === 1 ? 0 : [-0.6, 0.6, 0][i]; g.connect(p); p.connect(this.sfx); } else g.connect(this.sfx);
      o1.start(); o2.start();
      this.engines.push({ o1, o2, f, g });
    }
  },
  updateEngine(i, speed, boost, active) {
    const e = this.engines[i]; if (!e) return;
    const t = this.t;
    const base = 45 + Math.abs(speed) * 1.7 + (boost ? 40 : 0);
    e.o1.frequency.setTargetAtTime(base, t, 0.05);
    e.o2.frequency.setTargetAtTime(base * 0.502, t, 0.05);
    e.f.frequency.setTargetAtTime(300 + Math.abs(speed) * 25 + (boost ? 1500 : 0), t, 0.05);
    const vol = active ? (0.05 + Math.min(1, Math.abs(speed) / 60) * 0.06) / Math.sqrt(this.engines.length) : 0;
    e.g.gain.setTargetAtTime(vol, t, 0.1);
  },

  // ---- music: 16-step sequencer in A minor, scheduled ahead
  startMusic() { if (!this.ctx) return; this.musicOn = true; this.nextT = this.t + 0.1; this.step = 0; },
  stopMusic() { this.musicOn = false; },
  tick() {
    if (!this.ctx || !this.musicOn) return;
    const spb = 60 / 132 / 4; // 16ths
    while (this.nextT < this.t + 0.2) {
      this.scheduleStep(this.step, this.nextT);
      this.step++; this.nextT += spb;
    }
  },
  scheduleStep(i, t) {
    const bar = Math.floor(i / 16) % 4, s = i % 16;
    const roots = [45, 41, 43, 40]; // A F G E
    const root = roots[bar];
    const hz = (m) => 440 * Math.pow(2, (m - 69) / 12);
    const play = (m, dur, type, vol, delay = 0) => {
      const o = this.ctx.createOscillator(); const g = this.ctx.createGain();
      o.type = type; o.frequency.value = hz(m);
      g.gain.setValueAtTime(0.0001, t + delay);
      g.gain.exponentialRampToValueAtTime(vol, t + delay + 0.01);
      g.gain.exponentialRampToValueAtTime(0.0001, t + delay + dur);
      o.connect(g); g.connect(this.music); o.start(t + delay); o.stop(t + delay + dur + 0.02);
    };
    // bass: driving 8ths with octave jumps
    if (s % 2 === 0) play(root - 12 + (s % 4 === 2 ? 12 : 0), 0.16, 'sawtooth', 0.22);
    // kick
    if (s % 4 === 0) {
      const o = this.ctx.createOscillator(); const g = this.ctx.createGain();
      o.frequency.setValueAtTime(150, t); o.frequency.exponentialRampToValueAtTime(40, t + 0.12);
      g.gain.setValueAtTime(0.6, t); g.gain.exponentialRampToValueAtTime(0.0001, t + 0.2);
      o.connect(g); g.connect(this.music); o.start(t); o.stop(t + 0.25);
    }
    // hats
    if (s % 2 === 1 || this.intensity > 1) {
      const src = this.ctx.createBufferSource(); src.buffer = this.noiseBuf;
      const f = this.ctx.createBiquadFilter(); f.type = 'highpass'; f.frequency.value = 7000;
      const g = this.ctx.createGain(); g.gain.setValueAtTime(s % 2 ? 0.12 : 0.05, t); g.gain.exponentialRampToValueAtTime(0.0001, t + 0.05);
      src.connect(f); f.connect(g); g.connect(this.music); src.start(t, Math.random()); src.stop(t + 0.06);
    }
    // snare on 4 and 12
    if (s === 4 || s === 12) {
      const src = this.ctx.createBufferSource(); src.buffer = this.noiseBuf;
      const f = this.ctx.createBiquadFilter(); f.type = 'bandpass'; f.frequency.value = 1800;
      const g = this.ctx.createGain(); g.gain.setValueAtTime(0.3, t); g.gain.exponentialRampToValueAtTime(0.0001, t + 0.18);
      src.connect(f); f.connect(g); g.connect(this.music); src.start(t, Math.random()); src.stop(t + 0.2);
    }
    // arpeggio
    const arp = [0, 3, 7, 12, 7, 3, 10, 7];
    if (this.intensity >= 1 || bar % 2 === 1) play(root + 12 + arp[s % 8] + (bar === 3 ? 4 - 3 : 0), 0.12, 'square', 0.05);
    // lead in final lap
    if (this.intensity >= 2 && s % 4 === 0) {
      const lead = [12, 15, 19, 17, 15, 12, 10, 12];
      play(root + 24 + lead[(i / 4) % 8 | 0], 0.3, 'sawtooth', 0.045);
    }
  },
};
G.Sound = Sound;

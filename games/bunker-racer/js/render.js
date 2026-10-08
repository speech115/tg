'use strict';
// Per-viewport post-processing: HDR scene -> bloom -> FX (aberration, speed blur,
// OMEGA hack glitch, flash, vignette, grain) -> ACES tone mapping in OutputPass.
const FX_SHADER = {
  uniforms: {
    tDiffuse: { value: null }, time: { value: 0 }, aberr: { value: 0.15 }, glitch: { value: 0 },
    vignette: { value: 0.55 }, flash: { value: 0 }, flashColor: { value: new THREE.Color(1, 0.1, 0.15) },
    grain: { value: 0.025 }, speed: { value: 0 }, tint: { value: new THREE.Color(1, 1, 1) },
  },
  vertexShader: 'varying vec2 vUv; void main(){ vUv = uv; gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }',
  fragmentShader: `
    uniform sampler2D tDiffuse; uniform float time, aberr, glitch, vignette, flash, grain, speed;
    uniform vec3 flashColor, tint; varying vec2 vUv;
    float hash(vec2 p){ return fract(sin(dot(p, vec2(12.9898, 78.233))) * 43758.5453); }
    void main(){
      vec2 uv = vUv;
      if (glitch > 0.0) {
        float row = floor(uv.y * 26.0 + floor(time * 13.0));
        float h = hash(vec2(row, floor(time * 19.0)));
        if (h > 1.0 - glitch * 0.4) uv.x += (hash(vec2(row, 3.7)) - 0.5) * 0.14 * glitch;
      }
      vec2 c = uv - 0.5; float r2 = dot(c, c);
      float ca = aberr * 0.01 + glitch * 0.012 + speed * 0.004;
      vec3 col = vec3(texture2D(tDiffuse, uv + c * ca).r, texture2D(tDiffuse, uv).g, texture2D(tDiffuse, uv - c * ca).b);
      if (speed > 0.01) {
        vec3 acc = col;
        for (int k = 1; k < 6; k++) acc += texture2D(tDiffuse, uv - c * speed * 0.018 * float(k)).rgb;
        col = mix(col, acc / 6.0, smoothstep(0.015, 0.22, r2));
      }
      if (glitch > 0.0) {
        col *= 1.0 - glitch * 0.3 * step(0.5, fract(uv.y * 220.0 + time * 40.0));
        col = mix(col, col * vec3(1.7, 0.35, 0.4), glitch * 0.4);
      }
      col *= tint;
      col += flashColor * flash;
      col *= 1.0 - vignette * smoothstep(0.12, 0.8, r2 * 1.7);
      col += (hash(uv * vec2(1931.0, 1087.0) + fract(time)) - 0.5) * grain;
      gl_FragColor = vec4(max(col, 0.0), 1.0);
    }`,
};

const Post = {
  comps: [], samples: 4,
  init(renderer) { this.r = renderer; },
  make() {
    const rt = new THREE.WebGLRenderTarget(16, 16, { type: THREE.HalfFloatType, samples: this.samples });
    const c = new THREE.EffectComposer(this.r, rt);
    const rp = new THREE.RenderPass(new THREE.Scene(), new THREE.PerspectiveCamera());
    const bloom = new THREE.UnrealBloomPass(new THREE.Vector2(16, 16), 0.55, 0.35, 1.0);
    const fx = new THREE.ShaderPass(FX_SHADER);
    c.addPass(rp); c.addPass(bloom); c.addPass(fx); c.addPass(new THREE.OutputPass());
    return { c, rp, bloom, fx, w: 0, h: 0, pr: 0 };
  },
  render(i, scene, cam, pw, ph, dt, o = {}) {
    const p = this.comps[i] || (this.comps[i] = this.make());
    const pr = this.r.getPixelRatio();
    if (p.w !== pw || p.h !== ph || p.pr !== pr) { p.c.setPixelRatio(pr); p.c.setSize(pw, ph); p.w = pw; p.h = ph; p.pr = pr; }
    p.rp.scene = scene; p.rp.camera = cam;
    const u = p.fx.uniforms;
    u.time.value += dt;
    u.glitch.value = damp(u.glitch.value, o.glitch || 0, 8, dt);
    u.speed.value = damp(u.speed.value, o.speed || 0, 5, dt);
    u.aberr.value = 0.12 + (o.aberr || 0);
    u.flash.value = o.flash || 0;
    if (o.flashColor) u.flashColor.value.set(o.flashColor);
    u.vignette.value = o.vignette !== undefined ? o.vignette : 0.55;
    p.bloom.strength = o.bloom !== undefined ? o.bloom : 0.55;
    p.c.render(dt);
  },
};
G.Post = Post;

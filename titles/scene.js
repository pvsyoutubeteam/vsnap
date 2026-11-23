// Chrome title renderer. Everything is a pure function of (card, time) so frames
// can be rendered offline in any order. Driven by render.mjs via window.setup /
// window.renderFrame; open scene.html?preview in a browser for a live look.
import * as THREE from 'three';
import { TTFLoader } from 'three/addons/loaders/TTFLoader.js';
import { Font } from 'three/addons/loaders/FontLoader.js';

const clamp01 = (x) => Math.min(1, Math.max(0, x));
const smooth = (a, b, x) => { const t = clamp01((x - a) / (b - a)); return t * t * (3 - 2 * t); };
const easeOut = (x) => 1 - Math.pow(1 - clamp01(x), 3);
const lerp = (a, b, t) => a + (b - a) * t;
function rng(seed) { let a = seed >>> 0; return () => { a |= 0; a = a + 0x6D2B79F5 | 0; let t = Math.imul(a ^ a >>> 15, 1 | a); t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t; return ((t ^ t >>> 14) >>> 0) / 4294967296; }; }

// ---------------------------------------------------------------- shaders
const CHROME_VERT = /* glsl */`
attribute vec2 aLine;            // x: line centre Y (group space), y: cap height
varying vec3 vWorldPos, vWorldNormal, vObjNormal, vGroupPos;
varying vec2 vLine;
uniform mat4 uGroupInv;
void main(){
  vec4 wp = modelMatrix * vec4(position,1.0);
  vWorldPos = wp.xyz;
  vWorldNormal = normalize(mat3(modelMatrix) * normal);
  vObjNormal = normal;
  vGroupPos = (uGroupInv * wp).xyz;
  vLine = aLine;
  gl_Position = projectionMatrix * viewMatrix * wp;
}`;

const CHROME_FRAG = /* glsl */`
precision highp float;
varying vec3 vWorldPos, vWorldNormal, vObjNormal, vGroupPos;
varying vec2 vLine;
uniform float uTime, uSweep, uSweepGain, uReveal, uAlpha, uLiquid, uBrush, uGlass, uHero;
uniform vec3 uGold, uWhite;

float box(float x, float c, float hw, float s){ return smoothstep(hw+s, hw-s, abs(x-c)); }

// Procedural dark studio: bright warm-white "cyc" above a hard horizon, dark floor
// with gold bounce, overhead key softbox, gold side strips, and a travelling sweep light.
vec3 env(vec3 d, float blur){
  float az = atan(d.x, d.z);
  float el = asin(clamp(d.y,-1.0,1.0));
  float s  = blur + 0.012;
  float hz = el - 0.035*sin(az*2.3 + 0.6) - 0.02;
  float sky = smoothstep(-s, s, hz);
  // sky: glowing at the horizon, falling to charcoal overhead
  vec3 skyC = mix(uWhite*0.82, vec3(0.03,0.028,0.034), pow(smoothstep(0.0, 0.40, hz), 0.7));
  skyC += uGold * 0.12 * exp(-hz*9.0);
  // floor: black at the horizon, gold bounce lower down
  vec3 flC  = mix(vec3(0.012,0.010,0.009), uGold*0.42, smoothstep(0.02, 0.5, -hz));
  vec3 c = mix(flC, skyC, sky);
  // overhead key softbox (catches top bevels)
  c += uWhite * 2.4 * smoothstep(0.62-s, 0.95+s, el) * box(az, 0.0, 1.5, 0.3+s);
  // gold side strips (catch left/right bevels and sides)
  c += uGold * 2.6 * (box(az, 1.35, 0.16, 0.05+s) + box(az, -1.35, 0.16, 0.05+s)) * box(el, 0.1, 0.8, 0.2);
  // warm under-light
  c += uGold * 1.6 * smoothstep(-0.7+s, -1.1-s, el);
  // slow drifting soft streaks in the sky
  float d1 = az + el*0.7 - 0.28 + 0.10*sin(uTime*0.23);
  float d2 = az + el*0.7 + 0.36 + 0.08*sin(uTime*0.17+2.0);
  c += uGold  * 0.9 * smoothstep(0.05+s, 0.0, abs(d1)) * sky;
  c += uWhite * 0.6 * smoothstep(0.03+s, 0.0, abs(d2)) * sky;
  // the sweep: a diagonal strip light travelling left to right
  float sw = az + el*0.55 - mix(-1.9, 1.9, uSweep);
  float core = smoothstep(0.045+s, 0.0, abs(sw));
  float halo = smoothstep(0.30+s, 0.0, abs(sw));
  c += (uWhite*6.5*core + uGold*0.8*halo*halo) * uSweepGain;
  // hero card: a second, thinner trailing streak
  float sw2 = sw + 0.42;
  c += uGold * 4.5 * smoothstep(0.02+s, 0.0, abs(sw2)) * uSweepGain * uHero;
  return c;
}

void main(){
  vec3 N = normalize(vWorldNormal);
  vec3 V = normalize(cameraPosition - vWorldPos);
  float nz = vObjNormal.z;
  float isFace  = step(0.985, nz);
  float isBevel = step(0.06, abs(nz)) * (1.0 - step(0.985, abs(nz)));
  float isSide  = 1.0 - step(0.06, abs(nz));

  // liquid: a slow low-frequency wobble of the face normal
  vec3 p = vGroupPos;
  vec2 w = vec2(sin(p.x*0.9 + p.y*1.7 + uTime*0.35) + 0.6*sin(p.x*2.3 - p.y*1.1 - uTime*0.22),
                cos(p.x*0.7 - p.y*2.1 + uTime*0.28) + 0.6*cos(p.x*1.9 + p.y*1.4 + uTime*0.31));
  N = normalize(N + vec3(w*uLiquid*isFace, 0.0));

  vec3 R = reflect(-V, N);
  // position-dependent lookup so each line of type mirrors the horizon through its
  // middle and the reflection scrolls across the word (flat mirrors need the help)
  float yn = (p.y - vLine.x) / max(vLine.y, 0.001);
  vec3 d = normalize(R + vec3(p.x*0.085, yn*0.62, 0.0) * (isFace + 0.35*(1.0-isFace)));

  float blur = isSide * 0.22;
  vec3 col;
  if (isBevel > 0.5) {
    // glassy edge: per-channel dispersion + fresnel lift
    vec3 o = vec3(0.02, 0.0, -0.02) * uGlass;
    col = vec3(env(normalize(d + vec3(o.x, o.x*0.5, 0.0)), 0.0).r,
               env(d, 0.0).g,
               env(normalize(d + vec3(o.z, o.z*0.5, 0.0)), 0.0).b);
    float fr = pow(1.0 - clamp(dot(N, V), 0.0, 1.0), 2.0);
    col = col * (1.15 + 0.9*uGlass*fr) + uWhite * 0.05 * uGlass;
  } else {
    col = env(d, blur);
  }
  // chrome tint; brushed, warmer, darker sides
  vec3 tint = vec3(0.97, 0.955, 0.93);
  if (isSide > 0.5) {
    float g = sin(p.x*61.0 + p.y*47.0) * sin(p.x*23.0 - p.y*91.0);
    float brush = 1.0 + uBrush * 0.35 * g;
    float depthFade = mix(0.35, 1.0, smoothstep(-1.2, 0.0, p.z));
    tint = vec3(0.62, 0.50, 0.38) * brush * depthFade;
  }
  col *= tint * uReveal;
  gl_FragColor = vec4(col * uAlpha, uAlpha);   // premultiplied
}`;

const FS_VERT = /* glsl */`varying vec2 vUv; void main(){ vUv = uv; gl_Position = vec4(position.xy, 0.0, 1.0); }`;

const BG_FRAG = /* glsl */`
precision highp float;
varying vec2 vUv; uniform float uTime, uHaze, uAspect; uniform vec3 uGold;
float hash(vec2 p){ return fract(sin(dot(p, vec2(127.1,311.7))) * 43758.5453); }
float noise(vec2 p){ vec2 i=floor(p), f=fract(p); f=f*f*(3.0-2.0*f);
  return mix(mix(hash(i),hash(i+vec2(1,0)),f.x), mix(hash(i+vec2(0,1)),hash(i+vec2(1,1)),f.x), f.y); }
float fbm(vec2 p){ float a=0.5, v=0.0; for(int i=0;i<5;i++){ v+=a*noise(p); p=p*2.03+17.0; a*=0.5; } return v; }
void main(){
  vec2 q = (vUv - 0.5) * vec2(uAspect, 1.0);
  float r = length(q);
  vec3 c = mix(vec3(0.015,0.010,0.007), vec3(0.004,0.003,0.004), smoothstep(0.0, 0.95, r));
  float h = fbm(q*1.6 + vec2(uTime*0.012, -uTime*0.006)) * fbm(q*0.8 - vec2(uTime*0.008, 0.0) + 5.0);
  c += uGold * 0.06 * uHaze * h * smoothstep(0.9, 0.1, abs(q.y + 0.08));
  gl_FragColor = vec4(c, 1.0);
}`;

const BOKEH_VERT = /* glsl */`
attribute vec3 iPos; attribute vec4 iCol; attribute vec3 iParam; // size, phase, speed
varying vec2 vQ; varying vec4 vCol; varying float vSharp;
uniform float uTime;
void main(){
  vec3 pos = iPos;
  pos.y += mod(uTime * iParam.z * 0.25 + iParam.y, 1.0) * 0.0 + uTime * iParam.z * 0.12;
  pos.x += 0.25 * sin(uTime*0.11*iParam.z + iParam.y*6.28);
  vec4 mv = viewMatrix * vec4(pos, 1.0);
  mv.xy += position.xy * iParam.x * vec2(0.86, 1.0);       // slight anamorphic oval
  float tw = 0.55 + 0.45 * sin(uTime * (0.6 + 1.7*fract(iParam.y*7.3)) + iParam.y*40.0);
  vCol = vec4(iCol.rgb, iCol.a * tw);
  vQ = position.xy * 2.0;
  vSharp = iParam.x;
  gl_Position = projectionMatrix * mv;
}`;
const BOKEH_FRAG = /* glsl */`
precision highp float;
varying vec2 vQ; varying vec4 vCol; varying float vSharp;
void main(){
  float r = length(vQ);
  float disc = smoothstep(1.0, 0.86, r);
  float ring = smoothstep(0.62, 0.95, r) * disc;
  float a = disc * (0.5 + 0.6*ring);
  gl_FragColor = vec4(vCol.rgb * vCol.a * a, 1.0);
}`;

const BRIGHT_FRAG = /* glsl */`
precision highp float; varying vec2 vUv; uniform sampler2D tMap; uniform float uThreshold;
void main(){ vec3 c = texture2D(tMap, vUv).rgb; float l = max(c.r, max(c.g, c.b));
  gl_FragColor = vec4(c * smoothstep(uThreshold, uThreshold*2.0, l), 1.0); }`;

const BLUR_FRAG = /* glsl */`
precision highp float; varying vec2 vUv; uniform sampler2D tMap; uniform vec2 uDir;
void main(){
  vec3 c = texture2D(tMap, vUv).rgb * 0.2270270;
  c += (texture2D(tMap, vUv + uDir*1.3846).rgb + texture2D(tMap, vUv - uDir*1.3846).rgb) * 0.3162162;
  c += (texture2D(tMap, vUv + uDir*3.2308).rgb + texture2D(tMap, vUv - uDir*3.2308).rgb) * 0.0702703;
  gl_FragColor = vec4(c, 1.0);
}`;

const COMP_FRAG = /* glsl */`
precision highp float; varying vec2 vUv;
uniform sampler2D tScene, tBloom, tBloomWide, tStreak;
uniform float uExposure, uBloom, uFlare; uniform vec3 uFlareTint;
uniform int uMode;   // 0 flattened+opaque, 1 clean title, 2 glow/flare only
vec3 aces(vec3 x){ return clamp((x*(2.51*x+0.03))/(x*(2.43*x+0.59)+0.14), 0.0, 1.0); }
void main(){
  vec4 s = texture2D(tScene, vUv);
  vec3 glow = (texture2D(tBloom, vUv).rgb * 0.6 + texture2D(tBloomWide, vUv).rgb * 0.5) * uBloom
            + texture2D(tStreak, vUv).rgb * uFlareTint * uFlare;
  vec3 lin = uMode == 0 ? s.rgb + glow : (uMode == 1 ? s.rgb : glow);
  vec3 c = pow(aces(lin * uExposure), vec3(1.0/2.2));
  // flare layer carries its own brightness as alpha, so a plain "Normal" composite reads as light
  float a = uMode == 0 ? 1.0 : (uMode == 1 ? s.a : max(c.r, max(c.g, c.b)));
  gl_FragColor = vec4(min(c, vec3(a)), a);     // premultiplied
}`;

// ---------------------------------------------------------------- state
let cfg, renderer, camera, fsCam, fsQuad, font;
let W, H, rtScene, rtA, rtB, rtBloom, rtWide, rtS1, rtS2;
let chromeMat, mats = {}, bgScene, bokehMat, bgMat;
const cards = [];        // { scene, group, letters[] }

function fsPass(material, target) {
  fsQuad.material = material;
  renderer.setRenderTarget(target);
  renderer.render(fsQuad, fsCam);
}
const rt = (w, h, opts = {}) => new THREE.WebGLRenderTarget(Math.max(1, w | 0), Math.max(1, h | 0), {
  type: THREE.HalfFloatType, minFilter: THREE.LinearFilter, magFilter: THREE.LinearFilter, depthBuffer: false, ...opts });
const shader = (frag, uniforms) => new THREE.ShaderMaterial({ vertexShader: FS_VERT, fragmentShader: frag, uniforms, depthTest: false, depthWrite: false });

function buildCard(card) {
  const T = cfg.type;
  const res = font.data.resolution;
  const adv = (ch, size) => ((font.data.glyphs[ch] || font.data.glyphs['?']).ha / res) * size;
  const lineW = (line, size) => [...line].reduce((w, ch) => w + adv(ch, size), 0) + T.tracking * size * (line.length - 1);
  const size = Math.min(T.maxWidth / Math.max(...card.lines.map((l) => lineW(l, 1))),
                        T.maxHeight / (card.lines.length * T.lineHeight * 0.72)) * (card.scale || 1);
  // cap height from the H
  const hb = new THREE.ShapeGeometry(font.generateShapes('H', size)); hb.computeBoundingBox();
  const cap = hb.boundingBox.max.y;
  const pitch = cap * T.lineHeight * 1.18;
  const group = new THREE.Group();
  const letters = [];
  const bevel = T.bevel * (size / 1.6);
  card.lines.forEach((line, li) => {
    const yBase = ((card.lines.length - 1) / 2 - li) * pitch - cap / 2;
    let x = -lineW(line, size) / 2;
    [...line].forEach((ch) => {
      const a = adv(ch, size);
      if (ch.trim()) {
        const geo = new THREE.ExtrudeGeometry(font.generateShapes(ch, size), {
          depth: T.depth, bevelEnabled: true, bevelThickness: bevel, bevelSize: bevel, bevelOffset: -bevel * 0.6,
          bevelSegments: T.bevelSegments, curveSegments: 18 });
        geo.translate(0, 0, -(T.depth + bevel));
        const n = geo.attributes.position.count;
        const aLine = new Float32Array(n * 2);
        for (let i = 0; i < n; i++) { aLine[i * 2] = yBase + cap / 2; aLine[i * 2 + 1] = cap; }
        geo.setAttribute('aLine', new THREE.BufferAttribute(aLine, 2));
        const mesh = new THREE.Mesh(geo, chromeMat);
        mesh.userData = { x, y: yBase, i: letters.length };
        mesh.position.set(x, yBase, 0);
        group.add(mesh); letters.push(mesh);
      }
      x += a + T.tracking * size;
    });
  });
  const scene = new THREE.Scene(); scene.add(group);
  return { scene, group, letters, card };
}

function buildBackground() {
  bgScene = new THREE.Scene();
  bgMat = shader(BG_FRAG, { uTime: { value: 0 }, uHaze: { value: cfg.look.haze }, uAspect: { value: W / H }, uGold: { value: new THREE.Color(...cfg.look.gold) } });
  const plate = new THREE.Mesh(new THREE.PlaneGeometry(2, 2), bgMat); plate.frustumCulled = false; plate.renderOrder = -1;
  bgScene.add(plate);
  const r = rng(20261123), N = 230;
  const iPos = new Float32Array(N * 3), iCol = new Float32Array(N * 4), iParam = new Float32Array(N * 3);
  const gold = cfg.look.gold, white = cfg.look.white;
  for (let i = 0; i < N; i++) {
    const small = i > 46;                              // champagne sparkle vs. big soft bokeh
    const z = small ? lerp(-14, -3, r()) : lerp(-60, -16, r());
    const spread = (21 - z) * 0.5;
    iPos.set([(r() * 2 - 1) * spread, (r() * 2 - 1) * spread * 0.6 - (small ? 1.5 : 0), z], i * 3);
    const m = r() * r(), k = small ? 0.8 : 0.02 + 0.11 * r() * r();
    iCol.set([lerp(gold[0], white[0], m), lerp(gold[1], white[1], m), lerp(gold[2], white[2], m), k * cfg.look.bokeh], i * 4);
    iParam.set([small ? 0.03 + 0.07 * r() : 0.9 + 2.6 * r(), r(), small ? 0.5 + r() : 0.15 * r()], i * 3);
  }
  const g = new THREE.InstancedBufferGeometry().copy(new THREE.PlaneGeometry(1, 1));
  g.instanceCount = N;
  g.setAttribute('iPos', new THREE.InstancedBufferAttribute(iPos, 3));
  g.setAttribute('iCol', new THREE.InstancedBufferAttribute(iCol, 4));
  g.setAttribute('iParam', new THREE.InstancedBufferAttribute(iParam, 3));
  bokehMat = new THREE.ShaderMaterial({ vertexShader: BOKEH_VERT, fragmentShader: BOKEH_FRAG, uniforms: { uTime: { value: 0 } },
    blending: THREE.AdditiveBlending, depthTest: false, depthWrite: false, transparent: true });
  const mesh = new THREE.Mesh(g, bokehMat); mesh.frustumCulled = false;
  bgScene.add(mesh);
}

window.setup = async function (config, scale = 1) {
  cfg = config;
  W = Math.round(cfg.output.width * scale / 2) * 2; H = Math.round(cfg.output.height * scale / 2) * 2;
  const canvas = document.createElement('canvas'); document.body.appendChild(canvas);
  renderer = new THREE.WebGLRenderer({ canvas, alpha: true, premultipliedAlpha: true, antialias: false, preserveDrawingBuffer: true });
  renderer.setPixelRatio(1); renderer.setSize(W, H, false); renderer.setClearColor(0x000000, 0); renderer.autoClear = true;
  camera = new THREE.PerspectiveCamera(cfg.camera.fov, W / H, 0.5, 200);
  fsCam = new THREE.OrthographicCamera(-1, 1, 1, -1, 0, 1);
  fsQuad = new THREE.Mesh(new THREE.PlaneGeometry(2, 2)); fsQuad.frustumCulled = false;
  rtScene = rt(W, H, { samples: 4, depthBuffer: true });
  rtA = rt(W / 4, H / 4); rtB = rt(W / 4, H / 4); rtBloom = rt(W / 4, H / 4); rtWide = rt(W / 8, H / 8);
  rtS1 = rt(W / 4, H / 4); rtS2 = rt(W / 4, H / 4);

  const L = cfg.look;
  chromeMat = new THREE.ShaderMaterial({ vertexShader: CHROME_VERT, fragmentShader: CHROME_FRAG, uniforms: {
    uTime: { value: 0 }, uSweep: { value: 0 }, uSweepGain: { value: 1 }, uReveal: { value: 1 }, uAlpha: { value: 1 }, uHero: { value: 0 },
    uLiquid: { value: L.liquid }, uBrush: { value: L.sideBrush }, uGlass: { value: L.edgeGlass },
    uGold: { value: new THREE.Color(...L.gold) }, uWhite: { value: new THREE.Color(...L.white) }, uGroupInv: { value: new THREE.Matrix4() } } });
  mats.bright = shader(BRIGHT_FRAG, { tMap: { value: null }, uThreshold: { value: 1 } });
  mats.blur = shader(BLUR_FRAG, { tMap: { value: null }, uDir: { value: new THREE.Vector2() } });
  mats.comp = shader(COMP_FRAG, { tScene: { value: null }, tBloom: { value: null }, tBloomWide: { value: null }, tStreak: { value: null },
    uExposure: { value: L.exposure }, uBloom: { value: L.bloom }, uFlare: { value: L.flare }, uMode: { value: 0 }, uFlareTint: { value: new THREE.Color(...L.flareTint) } });

  const buf = await (await fetch(cfg.font)).arrayBuffer();
  font = new Font(new TTFLoader().parse(buf));
  cards.length = 0;
  for (const c of cfg.cards) cards.push(buildCard(c));
  buildBackground();
  return { width: W, height: H };
};

// camera move shared by title and background so parallax matches when layered
function placeCamera(u) {
  const C = cfg.camera;
  camera.position.set(0, 0, lerp(C.startDistance, C.endDistance, u));
  camera.lookAt(0, 0, 0); camera.updateMatrixWorld();
}

function blur(src, dst, dx, dy) {
  mats.blur.uniforms.tMap.value = src.texture; mats.blur.uniforms.uDir.value.set(dx / src.width, dy / src.height);
  fsPass(mats.blur, dst);
}

function post(flareGain, mode, reuse = false) {
  const L = cfg.look, k = W / 1920;
  if (!reuse) {
  // bloom
  mats.bright.uniforms.tMap.value = rtScene.texture; mats.bright.uniforms.uThreshold.value = 1.0; fsPass(mats.bright, rtA);
  blur(rtA, rtB, 1.2 * k, 0); blur(rtB, rtBloom, 0, 1.2 * k);
  blur(rtBloom, rtB, 3 * k, 0); blur(rtB, rtA, 0, 3 * k); blur(rtA, rtWide, 2, 0); blur(rtWide, rtA, 0, 6 * k); blur(rtA, rtWide, 2, 0);
  // anamorphic streak: high threshold, horizontal-only blur at growing radii
  mats.bright.uniforms.uThreshold.value = L.flareThreshold; fsPass(mats.bright, rtS1);
  for (const [i, step] of [1, 2, 3.5, 6, 9, 13].entries()) blur(i % 2 ? rtS2 : rtS1, i % 2 ? rtS1 : rtS2, step * k, 0);
  blur(rtS1, rtS2, 0, 0.8 * k);
  }
  const u = mats.comp.uniforms;
  u.tScene.value = rtScene.texture; u.tBloom.value = rtBloom.texture; u.tBloomWide.value = rtWide.texture; u.tStreak.value = rtS2.texture;
  u.uFlare.value = L.flare * flareGain; u.uMode.value = mode;
  fsPass(mats.comp, null);
}

// Render one frame to the WebGL canvas. layer: 'title' (clean chrome, alpha) |
// 'flare' (bloom + anamorphic streaks of that card, alpha) | 'bg' (opaque).
// For 'title', t is seconds from the start of that card; for 'bg', seconds on the timeline.
window.drawFrame = function ({ layer, card = 0, t = 0 }) {
  if (layer === 'bg') {
    const u = (t / cfg.output.duration);
    placeCamera(u); camera.position.z = lerp(22, 19, u); camera.updateMatrixWorld();
    bgMat.uniforms.uTime.value = t; bokehMat.uniforms.uTime.value = t;
    renderer.setRenderTarget(rtScene); renderer.setClearColor(0x000000, 1); renderer.clear(); renderer.render(bgScene, camera);
    post(0.6, 0);
    return;
  }
  const c = cards[card], cd = c.card, d = cd.duration, hero = !!cd.hero;
  const u = t / d;
  placeCamera(u);
  const C = cfg.camera;
  c.group.rotation.set(THREE.MathUtils.degToRad(C.tiltX), THREE.MathUtils.degToRad(lerp(C.swingY[0], C.swingY[1], u)), 0);
  // letters: staggered rise on the way in, tracking opens very slightly over the hold
  const n = c.letters.length;
  for (const m of c.letters) {
    const e = easeOut((t - 0.05 - m.userData.i * (0.5 / n)) / 1.1);
    m.position.set(m.userData.x * (1 + 0.025 * u), m.userData.y - (1 - e) * 0.35, -(1 - e) * 1.6);
  }
  c.group.updateMatrixWorld(true);
  const U = chromeMat.uniforms;
  U.uGroupInv.value.copy(c.group.matrixWorld).invert();
  U.uTime.value = t + card * 13.7;
  const fadeOut = hero ? 1.6 : 0.9;
  U.uAlpha.value = smooth(0, 0.7, t) * (1 - smooth(d - fadeOut, d - 0.05, t));
  U.uReveal.value = lerp(0.25, 1, smooth(0.1, 1.5, t)) * (1 - 0.6 * smooth(d - fadeOut, d, t));
  // sweep: one pass after the letters land; the hero card gets a slower second pass
  const s1 = clamp01((t - 0.9) / (hero ? 3.4 : 2.8));
  const s2 = hero ? clamp01((t - 5.4) / 4.2) : 0;
  U.uSweep.value = hero && t > 5.2 ? s2 : s1;
  U.uSweepGain.value = cd.sweep ?? 1; U.uHero.value = hero ? 1 : 0;
  renderer.setRenderTarget(rtScene); renderer.setClearColor(0x000000, 0); renderer.clear(); renderer.render(c.scene, camera);
  post(cd.flare ?? 1, layer === 'flare' ? 2 : 1);
};

const out2d = document.createElement('canvas');
// layer 'comp' = title over the background at the card's place on the timeline (look-dev stills)
window.renderFrame = function (opts) {
  if (opts.layer !== 'comp') { window.drawFrame(opts); return renderer.domElement.toDataURL('image/png'); }
  out2d.width = W; out2d.height = H; const g = out2d.getContext('2d');
  window.drawFrame({ layer: 'bg', t: cfg.cards[opts.card].start + opts.t }); g.drawImage(renderer.domElement, 0, 0);
  window.drawFrame({ layer: 'title', card: opts.card, t: opts.t }); g.drawImage(renderer.domElement, 0, 0);
  if (!opts.noFlare) { window.drawFrame({ layer: 'flare', card: opts.card, t: opts.t }); g.drawImage(renderer.domElement, 0, 0); }
  return out2d.toDataURL('image/png');
};
// title + flare of the same frame; the scene is only rendered once
window.renderPair = function (opts) {
  window.drawFrame({ ...opts, layer: 'title' }); const title = renderer.domElement.toDataURL('image/png');
  post(cfg.cards[opts.card].flare ?? 1, 2, true); const flare = renderer.domElement.toDataURL('image/png');
  return [title, flare];
};

// live preview: scene.html?preview  (plays the whole timeline on a loop)
if (location.search.includes('preview')) {
  const config = await (await fetch('./config.json')).json();
  await window.setup(config, 0.5);
  const cv = document.createElement('canvas'); cv.width = W; cv.height = H; document.body.prepend(cv);
  renderer.domElement.style.display = 'none';
  const g = cv.getContext('2d'), t0 = performance.now();
  (function tick() {
    const t = ((performance.now() - t0) / 1000) % config.output.duration;
    window.drawFrame({ layer: 'bg', t }); g.drawImage(renderer.domElement, 0, 0);
    config.cards.forEach((c, i) => { if (t >= c.start && t < c.start + c.duration) { for (const layer of ['title', 'flare']) { window.drawFrame({ layer, card: i, t: t - c.start }); g.drawImage(renderer.domElement, 0, 0); } } });
    requestAnimationFrame(tick);
  })();
}

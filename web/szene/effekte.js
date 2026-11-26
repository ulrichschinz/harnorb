// Effekte: Hyperraum-Lichtstreifen, Erledigt-Box (Portal), Entladungsstrahl, Schockwelle, Effekttöne.
import * as THREE from "three";
import { tween, ease, warte } from "./tween.js";

const STREIFEN_VS = /* glsl */`
attribute float aEnde; attribute float aZufall;
uniform float uHyper, uZeit;
varying float vEnde; varying float vZufall;
void main(){
  vec3 p = position;
  float z = mod(p.z + uZeit * 60.0 * (0.5 + aZufall), 90.0) - 80.0;
  p.z = z + aEnde * (0.5 + uHyper * 14.0 * (0.4 + aZufall));
  vEnde = aEnde; vZufall = aZufall;
  gl_Position = projectionMatrix * modelViewMatrix * vec4(p, 1.0);
}`;
const STREIFEN_FS = /* glsl */`
uniform float uHyper;
varying float vEnde; varying float vZufall;
void main(){
  vec3 c = mix(vec3(0.5, 0.7, 1.0), vec3(1.0, 0.75, 1.0), vZufall) * (0.4 + vEnde);
  gl_FragColor = vec4(c * uHyper * 1.05, 1.0);
}`;

// Erledigt-Box als kleines Portal: dunkler Kern, schmaler schillernder Ereignishorizont, wirbelnde Akkretion.
// Vormultipliziert gemischt, damit der Kern den Hintergrund wirklich abdunkelt.
const PORTAL_FS = /* glsl */`
uniform float uZeit, uOffen, uBlitz;
varying vec2 vUv;
vec3 regenbogen(float t){ return 0.5 + 0.5 * cos(6.28318 * (t + vec3(0.0, 0.33, 0.67))); }
void main(){
  vec2 p = vUv * 2.0 - 1.0;
  float r = length(p);
  float w = atan(p.y, p.x);
  float rh = 0.5 + uBlitz * 0.25;                         // Horizont weitet sich beim Ankommen
  float horizont = exp(-pow((r - rh) * 26.0, 2.0));
  float band = smoothstep(rh + 0.38, rh, r) * smoothstep(rh - 0.02, rh + 0.03, r);
  float wirbel = pow(0.5 + 0.5 * sin(w * 3.0 + log(max(r, 0.01)) * 9.0 - uZeit * 5.0), 3.0);
  vec3 farbe = regenbogen(w / 6.28318 + r * 0.8 - uZeit * 0.25);
  farbe = farbe * farbe * 1.4;
  vec3 c = farbe * horizont * 1.7 + farbe * band * wirbel * 0.55;
  c += mix(vec3(1.0), farbe, 0.5) * uBlitz * horizont * 1.5;
  float kern = smoothstep(rh + 0.02, rh - 0.12, r);
  float a = (kern * 0.92 + horizont * 0.3) * uOffen;
  float aussen = smoothstep(1.0, 0.85, r);
  gl_FragColor = vec4(c * uOffen * aussen, a * aussen);
}`;
// Strahl: farbiger Lichtfaden mit Pulsen, die von der Kugel zur Karte laufen, dazu ein weicher Schein
const STRAHL_FS = /* glsl */`
uniform float uZeit, uStaerke;
varying vec2 vUv;
vec3 regenbogen(float t){ return 0.5 + 0.5 * cos(6.28318 * (t + vec3(0.0, 0.33, 0.67))); }
void main(){
  float x = (vUv.x - 0.5) * 2.0;
  float faden = exp(-x * x * 900.0);
  float spirale = exp(-pow((x - 0.35 * sin(vUv.y * 26.0 - uZeit * 18.0)) * 14.0, 2.0)) * 0.45;
  float schein = exp(-x * x * 10.0) * 0.12;
  float puls = 0.55 + 0.45 * pow(0.5 + 0.5 * sin(vUv.y * 22.0 - uZeit * 30.0), 4.0);
  vec3 farbe = regenbogen(vUv.y * 1.5 - uZeit * 1.2);
  farbe = farbe * farbe * 1.5;
  float ende = smoothstep(0.0, 0.06, vUv.y) * smoothstep(1.0, 0.92, vUv.y);
  vec3 c = mix(farbe, vec3(1.0), 0.35) * faden * 1.6 * puls + farbe * (spirale + schein) * puls;
  gl_FragColor = vec4(c * uStaerke * ende, 1.0);
}`;
// Spur: Funken hinter der fliegenden Karte
const SPUR_VS = /* glsl */`
attribute float aAlter; attribute float aZufall;
uniform float uPixel;
varying float vAlter; varying float vZufall;
void main(){
  vec4 mv = modelViewMatrix * vec4(position, 1.0);
  gl_Position = projectionMatrix * mv;
  gl_PointSize = uPixel * (1.0 - aAlter) * (0.6 + aZufall) / -mv.z;
  vAlter = aAlter; vZufall = aZufall;
}`;
const SPUR_FS = /* glsl */`
varying float vAlter; varying float vZufall;
vec3 regenbogen(float t){ return 0.5 + 0.5 * cos(6.28318 * (t + vec3(0.0, 0.33, 0.67))); }
void main(){
  if (vAlter >= 1.0) discard;
  vec2 p = gl_PointCoord * 2.0 - 1.0;
  float a = exp(-dot(p, p) * 4.0);
  vec3 c = mix(vec3(1.0), regenbogen(vZufall + vAlter * 0.5), 0.6);
  gl_FragColor = vec4(c * a * (1.0 - vAlter) * 0.9, 1.0);
}`;
const UV_VS = /* glsl */`varying vec2 vUv; void main(){ vUv = uv; gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }`;
const WELLE_FS = /* glsl */`
uniform float uR, uStaerke; varying vec2 vUv;
vec3 regenbogen(float t){ return 0.5 + 0.5 * cos(6.28318 * (t + vec3(0.0, 0.33, 0.67))); }
void main(){ vec2 p = vUv * 2.0 - 1.0; float r = length(p); float w = atan(p.y, p.x);
  float ring = exp(-pow((r - uR) * 30.0, 2.0));
  gl_FragColor = vec4(regenbogen(w / 6.28 + r) * ring * uStaerke * 1.5, 1.0); }`;

const zusatz = { transparent: true, blending: THREE.AdditiveBlending, depthWrite: false, depthTest: false };

export class Effekte {
  constructor(buehne) {
    this.b = buehne;
    const szene = buehne.szene;
    this.zeit = { value: 0 };

    // Hyperraum-Streifen: Linien in einem Tunnel um die Blickachse
    const n = 520, pos = new Float32Array(n * 6), ende = new Float32Array(n * 2), zuf = new Float32Array(n * 2);
    for (let i = 0; i < n; i++) {
      const w = Math.random() * Math.PI * 2, r = 2.2 + Math.random() ** 0.6 * 22, z = Math.random() * 90;
      const x = Math.cos(w) * r, y = Math.sin(w) * r;
      pos.set([x, y, z, x, y, z], i * 6);
      ende[i * 2] = 0; ende[i * 2 + 1] = 1;
      const q = Math.random(); zuf[i * 2] = q; zuf[i * 2 + 1] = q;
    }
    const g = new THREE.BufferGeometry();
    g.setAttribute("position", new THREE.BufferAttribute(pos, 3));
    g.setAttribute("aEnde", new THREE.BufferAttribute(ende, 1));
    g.setAttribute("aZufall", new THREE.BufferAttribute(zuf, 1));
    this.streifenU = { uHyper: { value: 0 }, uZeit: this.zeit };
    this.streifen = new THREE.LineSegments(g, new THREE.ShaderMaterial({ uniforms: this.streifenU, vertexShader: STREIFEN_VS, fragmentShader: STREIFEN_FS, ...zusatz }));
    this.streifen.frustumCulled = false;
    this.streifen.visible = false;
    szene.add(this.streifen);

    // Erledigt-Box: Portal am unteren Rand, nur sichtbar, solange etwas hineinfliegt
    this.portalU = { uZeit: this.zeit, uOffen: { value: 0 }, uBlitz: { value: 0 } };
    this.portal = new THREE.Mesh(new THREE.PlaneGeometry(1.5, 1.5), new THREE.ShaderMaterial({ uniforms: this.portalU, vertexShader: UV_VS, fragmentShader: PORTAL_FS,
      transparent: true, depthWrite: false, depthTest: false, blending: THREE.CustomBlending, blendSrc: THREE.OneFactor, blendDst: THREE.OneMinusSrcAlphaFactor }));
    this.portal.rotation.x = -1.1;
    this.portal.visible = false;
    this.portal.renderOrder = 8;
    szene.add(this.portal);

    // Entladungsstrahl
    this.strahlU = { uZeit: this.zeit, uStaerke: { value: 0 } };
    const sg = new THREE.PlaneGeometry(0.4, 1, 1, 1); sg.translate(0, 0.5, 0);
    this.strahl = new THREE.Mesh(sg, new THREE.ShaderMaterial({ uniforms: this.strahlU, vertexShader: UV_VS, fragmentShader: STRAHL_FS, ...zusatz, side: THREE.DoubleSide }));
    this.strahl.visible = false;
    this.strahl.renderOrder = 9;
    szene.add(this.strahl);

    // Schockwelle (z. B. beim Ankommen im Portal)
    this.welleU = { uR: { value: 0 }, uStaerke: { value: 0 } };
    this.welle = new THREE.Mesh(new THREE.PlaneGeometry(4, 4), new THREE.ShaderMaterial({ uniforms: this.welleU, vertexShader: UV_VS, fragmentShader: WELLE_FS, ...zusatz }));
    this.welle.visible = false;
    szene.add(this.welle);

    // Funkenspur (Ringpuffer)
    this.spurN = 260; this.spurI = 0;
    const sp = new THREE.BufferGeometry();
    this.spurPos = new Float32Array(this.spurN * 3); this.spurAlter = new Float32Array(this.spurN).fill(1); this.spurV = new Float32Array(this.spurN * 3);
    const sz = new Float32Array(this.spurN); for (let i = 0; i < this.spurN; i++) sz[i] = Math.random();
    sp.setAttribute("position", new THREE.BufferAttribute(this.spurPos, 3));
    sp.setAttribute("aAlter", new THREE.BufferAttribute(this.spurAlter, 1));
    sp.setAttribute("aZufall", new THREE.BufferAttribute(sz, 1));
    this.spurU = { uPixel: { value: 300 } };
    this.spur = new THREE.Points(sp, new THREE.ShaderMaterial({ uniforms: this.spurU, vertexShader: SPUR_VS, fragmentShader: SPUR_FS, ...zusatz }));
    this.spur.frustumCulled = false; this.spur.renderOrder = 9;
    szene.add(this.spur);

    this.ton = new Effekttoene();
    this.reduziert = buehne.reduziert;
  }

  portalOrt() {
    const s = this.b.sichtbar(0);
    return new THREE.Vector3(s.b / 2 - Math.min(1.6, s.b * 0.14), -s.h / 2 + 0.95, 0.5);
  }

  // Funken an Stelle p ausstoßen (Weltkoordinaten)
  funken(p, anzahl = 3) {
    for (let k = 0; k < anzahl; k++) {
      const i = this.spurI; this.spurI = (this.spurI + 1) % this.spurN;
      this.spurPos[i * 3] = p.x + (Math.random() - 0.5) * 0.15; this.spurPos[i * 3 + 1] = p.y + (Math.random() - 0.5) * 0.15; this.spurPos[i * 3 + 2] = p.z;
      this.spurV[i * 3] = (Math.random() - 0.5) * 0.6; this.spurV[i * 3 + 1] = (Math.random() - 0.5) * 0.6; this.spurV[i * 3 + 2] = (Math.random() - 0.5) * 0.6;
      this.spurAlter[i] = 0;
    }
  }

  update(dt, zeit) {
    this.zeit.value = zeit;
    const h = this.b.hyper;
    this.streifenU.uHyper.value = this.reduziert ? 0 : h;
    this.streifen.visible = h > 0.01 && !this.reduziert;
    this.streifen.position.copy(this.b.kamera.position).setZ(this.b.kamera.position.z - 8);
    this.welle.quaternion.copy(this.b.kamera.quaternion);
    let lebt = false;
    for (let i = 0; i < this.spurN; i++) {
      if (this.spurAlter[i] >= 1) continue;
      lebt = true;
      this.spurAlter[i] = Math.min(1, this.spurAlter[i] + dt * 1.6);
      for (let k = 0; k < 3; k++) this.spurPos[i * 3 + k] += this.spurV[i * 3 + k] * dt;
    }
    this.spur.visible = lebt;
    if (lebt) { this.spur.geometry.attributes.position.needsUpdate = true; this.spur.geometry.attributes.aAlter.needsUpdate = true; }
    this.spurU.uPixel.value = 9 * this.b.renderer.getPixelRatio() * (innerHeight / 900) * 10;
  }

  // Hyperraum-Übergang: Streckung, Lichtstreifen, FOV-Stoß, radiale Unschärfe
  async hyperraum(dauer = 900) {
    if (this.reduziert) return warte(150);
    this.b.pausiereMessung(dauer + 1500);
    this.ton.whoosh();
    this.b.hyperZiel = 1;
    await warte(dauer * 0.45);
    this.b.hyperZiel = 0;
    await warte(dauer * 0.55);
  }

  // Strahl von a nach b (Weltkoordinaten), Stärke 0..1
  strahlZwischen(a, b, staerke) {
    const d = new THREE.Vector3().subVectors(b, a);
    const l = d.length();
    this.strahl.visible = staerke > 0.01;
    this.strahl.position.copy(a);
    this.strahl.scale.set(0.8 + staerke * 0.4, l, 1);
    this.strahl.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), d.normalize());
    // flache Seite zur Kamera drehen
    const achse = d.clone();
    const zurKamera = new THREE.Vector3().subVectors(this.b.kamera.position, a);
    const seite = new THREE.Vector3().crossVectors(achse, zurKamera).normalize();
    const normal = new THREE.Vector3().crossVectors(seite, achse).normalize();
    const m = new THREE.Matrix4().makeBasis(seite, achse, normal);
    this.strahl.quaternion.setFromRotationMatrix(m);
    this.strahlU.uStaerke.value = staerke;
  }

  async portalAuf() {
    this.portal.position.copy(this.portalOrt());
    this.portal.visible = true;
    this.ton.portal();
    this.portal.quaternion.copy(this.b.kamera.quaternion);
    this.portal.rotateX(-0.55);
    await tween({ dauer: 450, ease: ease.outBack, update: (w) => { this.portalU.uOffen.value = Math.min(1, w); this.portal.scale.setScalar(0.2 + 0.8 * w); } }).fertig;
  }

  async portalZu() {
    this.portalU.uBlitz.value = 1;
    this.ton.pling();
    this.funken(this.portal.position, 40);
    this.welle.position.copy(this.portal.position);
    this.welle.visible = true;
    tween({ dauer: 700, ease: ease.outCubic, update: (w) => { this.welleU.uR.value = 0.15 + w * 0.8; this.welleU.uStaerke.value = (1 - w) * 0.6; }, fertig: () => { this.welle.visible = false; } });
    await tween({ dauer: 500, verzoegerung: 150, ease: ease.inCubic, update: (w) => {
      this.portalU.uBlitz.value = 1 - w; this.portalU.uOffen.value = 1 - w; this.portal.scale.setScalar(1 - w * 0.8);
    }, fertig: () => { this.portal.visible = false; } }).fertig;
  }
}

// Effekttöne per WebAudio (optional, mit M abschaltbar). Leise, kurz, ohne Dateien.
export class Effekttoene {
  constructor() {
    this.an = true;
    try { this.an = localStorage.getItem("harno-toene") !== "aus"; } catch (_) { /* egal */ }
    this.ctx = null;
  }
  setze(an) { this.an = an; try { localStorage.setItem("harno-toene", an ? "an" : "aus"); } catch (_) { /* egal */ } }
  _ctx() {
    if (!this.an) return null;
    if (!this.ctx) { try { this.ctx = new AudioContext(); } catch (_) { return null; } }
    if (this.ctx.state === "suspended") this.ctx.resume().catch(() => {});
    return this.ctx;
  }
  _ton(f0, f1, dauer, typ = "sine", laut = 0.05) {
    const c = this._ctx(); if (!c) return;
    const o = c.createOscillator(), g = c.createGain(), t = c.currentTime;
    o.type = typ; o.frequency.setValueAtTime(f0, t); o.frequency.exponentialRampToValueAtTime(f1, t + dauer);
    g.gain.setValueAtTime(0.0001, t); g.gain.exponentialRampToValueAtTime(laut, t + 0.03); g.gain.exponentialRampToValueAtTime(0.0001, t + dauer);
    o.connect(g).connect(c.destination); o.start(t); o.stop(t + dauer + 0.05);
  }
  whoosh() {
    const c = this._ctx(); if (!c) return;
    const n = c.sampleRate * 0.9, buf = c.createBuffer(1, n, c.sampleRate), d = buf.getChannelData(0);
    for (let i = 0; i < n; i++) d[i] = (Math.random() * 2 - 1) * Math.sin((Math.PI * i) / n) ** 2;
    const s = c.createBufferSource(); s.buffer = buf;
    const f = c.createBiquadFilter(); f.type = "bandpass"; f.Q.value = 1.2;
    const t = c.currentTime; f.frequency.setValueAtTime(300, t); f.frequency.exponentialRampToValueAtTime(3200, t + 0.45); f.frequency.exponentialRampToValueAtTime(400, t + 0.9);
    const g = c.createGain(); g.gain.value = 0.06;
    s.connect(f).connect(g).connect(c.destination); s.start();
  }
  laden() { this._ton(180, 900, 0.55, "sawtooth", 0.018); }
  zap() { this._ton(1400, 120, 0.35, "square", 0.02); }
  portal() { this._ton(220, 440, 0.4, "sine", 0.04); }
  pling() { this._ton(1320, 1760, 0.5, "sine", 0.05); this._ton(1980, 2640, 0.6, "sine", 0.025); }
  auf() { this._ton(500, 760, 0.18, "sine", 0.025); }
  zu() { this._ton(700, 420, 0.18, "sine", 0.02); }
}

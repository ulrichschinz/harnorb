// Bühne: Renderer, Kamera, Nachbearbeitung (Bloom, Hyperraum-Unschärfe, Vignette), Qualitätsstufen, fps.
import * as THREE from "three";
import { EffectComposer } from "three/addons/postprocessing/EffectComposer.js";
import { RenderPass } from "three/addons/postprocessing/RenderPass.js";
import { UnrealBloomPass } from "three/addons/postprocessing/UnrealBloomPass.js";
import { ShaderPass } from "three/addons/postprocessing/ShaderPass.js";
import { OutputPass } from "three/addons/postprocessing/OutputPass.js";
import { CSS3DRenderer } from "three/addons/renderers/CSS3DRenderer.js";
import { tick, naeher } from "./tween.js";

export const STUFEN = {
  hoch: { pixel: 2, bloom: 1, partikel: 1, schritte: 12, oktaven: 5 },
  mittel: { pixel: 1.25, bloom: 0.75, partikel: 0.7, schritte: 10, oktaven: 4 },
  // Bloom nie unter halber Auflösung: darunter entstehen sichtbare Blöcke um helle Punkte
  niedrig: { pixel: 1, bloom: 0.5, partikel: 0.45, schritte: 7, oktaven: 3 },
};
const REIHE = ["hoch", "mittel", "niedrig"];

const FinishShader = {
  uniforms: {
    tDiffuse: { value: null }, uHyper: { value: 0 }, uZeit: { value: 0 }, uVignette: { value: 1 },
    uAberration: { value: 0.0015 }, uKorn: { value: 0.018 }, uSaett: { value: 1 }, uComic: { value: 0 },
    uAufloesung: { value: new THREE.Vector2(1, 1) },
  },
  vertexShader: /* glsl */`varying vec2 vUv; void main(){ vUv = uv; gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }`,
  fragmentShader: /* glsl */`
    uniform sampler2D tDiffuse; uniform float uHyper, uZeit, uVignette, uAberration, uKorn, uSaett, uComic;
    uniform vec2 uAufloesung; varying vec2 vUv;
    float hash(vec2 p){ return fract(sin(dot(p, vec2(12.9898, 78.233))) * 43758.5453); }
    void main(){
      vec2 m = vUv - 0.5;
      float r = length(m);
      // chromatische Aberration, im Hyperraum stark
      float ab = uAberration * (0.4 + r * 2.0) + uHyper * 0.012 * r;
      vec3 c;
      c.r = texture2D(tDiffuse, vUv - m * ab).r;
      c.g = texture2D(tDiffuse, vUv).g;
      c.b = texture2D(tDiffuse, vUv + m * ab).b;
      // radiale Unschärfe zum Zentrum (Hyperraum)
      if (uHyper > 0.01) {
        vec3 s = vec3(0.0);
        for (int i = 1; i <= 10; i++) {
          float f = 1.0 - float(i) * 0.018 * uHyper;
          s += texture2D(tDiffuse, 0.5 + m * f).rgb;
        }
        c = mix(c, s / 10.0, clamp(uHyper, 0.0, 1.0) * 0.85);
        c += vec3(0.25, 0.45, 1.0) * uHyper * 0.08 * smoothstep(0.2, 0.7, r);
      }
      // Comic: Tuschelinien über Sobel auf der Helligkeit, leichte Tonwertstufen
      if (uComic > 0.5) {
        vec2 px = 1.0 / uAufloesung;
        vec3 L = vec3(0.299, 0.587, 0.114);
        float a = dot(texture2D(tDiffuse, vUv + px * vec2(-1.0, 1.0)).rgb, L), b = dot(texture2D(tDiffuse, vUv + px * vec2(0.0, 1.0)).rgb, L);
        float d = dot(texture2D(tDiffuse, vUv + px * vec2(1.0, 1.0)).rgb, L), e = dot(texture2D(tDiffuse, vUv + px * vec2(-1.0, 0.0)).rgb, L);
        float f = dot(texture2D(tDiffuse, vUv + px * vec2(1.0, 0.0)).rgb, L), g = dot(texture2D(tDiffuse, vUv + px * vec2(-1.0, -1.0)).rgb, L);
        float h = dot(texture2D(tDiffuse, vUv + px * vec2(0.0, -1.0)).rgb, L), k = dot(texture2D(tDiffuse, vUv + px * vec2(1.0, -1.0)).rgb, L);
        float gx = -a - 2.0 * e - g + d + 2.0 * f + k, gy = a + 2.0 * b + d - g - 2.0 * h - k;
        float kante = length(vec2(gx, gy)) / (0.35 + dot(c, L));
        float tinte = smoothstep(0.8, 1.5, kante);
        float m = max(max(c.r, c.g), c.b);
        c = mix(c, c / max(m, 1e-3) * (floor(m * 5.0 + 0.5) / 5.0), 0.6);
        c = mix(c, vec3(0.015, 0.012, 0.03), tinte * 0.9);
      }
      float l = dot(c, vec3(0.299, 0.587, 0.114));
      c = mix(vec3(l), c, uSaett);
      // Vignette
      c *= mix(1.0, smoothstep(0.95, 0.25, r), 0.55 * uVignette);
      // Filmkorn
      c += (hash(vUv * uAufloesung + fract(uZeit) * 91.7) - 0.5) * uKorn * (1.0 - uComic * 0.6);
      gl_FragColor = vec4(c, 1.0);
    }`,
};

export class Buehne {
  constructor(huelle, { reduziert = false } = {}) {
    this.huelle = huelle;
    this.reduziert = reduziert;
    this.renderer = new THREE.WebGLRenderer({ antialias: false, powerPreference: "high-performance", alpha: false, stencil: false });
    this.renderer.setClearColor(0x020308, 1);
    this.renderer.toneMapping = THREE.ACESFilmicToneMapping;
    this.renderer.toneMappingExposure = 1.05;
    this.renderer.outputColorSpace = THREE.SRGBColorSpace;
    this.renderer.domElement.className = "leinwand";
    huelle.appendChild(this.renderer.domElement);

    this.szene = new THREE.Scene();
    this.kamera = new THREE.PerspectiveCamera(38, 1, 0.1, 3000);
    this.kamera.position.set(0, 0, 10);
    this.kameraBasis = new THREE.Vector3(0, 0, 10);
    this.fovBasis = 38;

    this.css = new CSS3DRenderer();
    this.css.domElement.className = "css3d";
    huelle.appendChild(this.css.domElement);
    this.cssSzene = new THREE.Scene();

    this.composer = new EffectComposer(this.renderer);
    this.composer.addPass(new RenderPass(this.szene, this.kamera));
    this.bloom = new UnrealBloomPass(new THREE.Vector2(256, 256), 0.5, 0.3, 0.92);
    this.composer.addPass(this.bloom);
    this.finish = new ShaderPass(FinishShader);
    this.composer.addPass(this.finish);
    this.composer.addPass(new OutputPass());

    this.rueckrufe = [];
    this.zeit = 0;
    this.maus = new THREE.Vector2();
    this.mausGlatt = new THREE.Vector2();
    this.hyper = 0; this.hyperZiel = 0;
    this.bloomZiel = 0.5;
    this.fps = 60; this._frames = 0; this._fpsStart = performance.now();
    this.stufeWahl = "auto"; this.stufe = "hoch"; this._zuletztGewechselt = performance.now();
    this._zuwenig = 0; this._gutSeit = performance.now(); this._pauseBis = 0;
    this.beiStufe = [];

    addEventListener("resize", () => this.groesse());
    addEventListener("pointermove", (e) => {
      this.maus.set(e.clientX / innerWidth - 0.5, e.clientY / innerHeight - 0.5);
    }, { passive: true });
    this.setzeStufe("hoch");
    this.groesse();
  }

  get params() { return STUFEN[this.stufe]; }

  setzeStufe(name, grund = "") {
    if (this.stufe !== name) (this.stufenLog ||= []).push({ s: Math.round(performance.now() / 100) / 10, von: this.stufe, nach: name, fps: Math.round(this.fps), grund });
    this.stufe = name;
    const p = STUFEN[name];
    this.renderer.setPixelRatio(Math.min(devicePixelRatio || 1, p.pixel));
    this.groesse();
    this.pausiereMessung?.(2000);
    for (const f of this.beiStufe) f(p, name);
  }

  waehleStufe(wahl) { // "auto" | "hoch" | "mittel" | "niedrig"
    this.stufeWahl = wahl;
    if (wahl !== "auto") this.setzeStufe(wahl);
    else { this._gutSeit = performance.now(); this._zuwenig = 0; }
  }

  groesse() {
    const b = innerWidth, h = innerHeight;
    this.kamera.aspect = b / h;
    // Schmale Fenster: Kamera etwas zurück, damit Kugel und Karten passen
    this.kameraBasis.z = b / h < 0.9 ? 13.5 : 10;
    this.kamera.updateProjectionMatrix();
    this.renderer.setSize(b, h);
    this.composer.setPixelRatio(this.renderer.getPixelRatio());
    this.composer.setSize(b, h);
    const bf = STUFEN[this.stufe].bloom;
    this.bloom.resolution.set(b * bf, h * bf);
    this.bloom.setSize?.(Math.round(b * bf * this.renderer.getPixelRatio()), Math.round(h * bf * this.renderer.getPixelRatio()));
    this.css.setSize(b, h);
    this.finish.uniforms.uAufloesung.value.set(b, h);
    for (const f of this.beiGroesse || []) f(b, h);
  }

  // Sichtbare Breite/Höhe in Welteinheiten auf der Ebene z (für das Kartenlayout)
  sichtbar(z = 0) {
    const d = this.kameraBasis.z - z;
    const h = 2 * d * Math.tan((this.fovBasis * Math.PI) / 360);
    return { b: h * this.kamera.aspect, h, pxProEinheit: innerHeight / h };
  }

  jedesBild(f) { this.rueckrufe.push(f); }

  start() {
    let vorher = performance.now();
    const schleife = (jetzt) => {
      requestAnimationFrame(schleife);
      const dt = Math.min(0.1, (jetzt - vorher) / 1000); vorher = jetzt;
      this.zeit += dt;
      tick(jetzt);
      this._kamera(dt);
      for (const f of this.rueckrufe) { try { f(dt, this.zeit, jetzt); } catch (err) { console.error(err); } }
      this.hyper = naeher(this.hyper, this.hyperZiel, 7, dt);
      this.finish.uniforms.uHyper.value = this.hyper;
      this.finish.uniforms.uZeit.value = this.zeit;
      this.bloom.strength = naeher(this.bloom.strength, this.bloomZiel + this.hyper * 0.8, 5, dt);
      this.composer.render(dt);
      this.css.render(this.cssSzene, this.kamera);
      this._messe(jetzt);
    };
    requestAnimationFrame(schleife);
  }

  _kamera(dt) {
    this.mausGlatt.x = naeher(this.mausGlatt.x, this.maus.x, 2.5, dt);
    this.mausGlatt.y = naeher(this.mausGlatt.y, this.maus.y, 2.5, dt);
    const t = this.zeit, k = this.kamera, ruhig = this.reduziert ? 0.2 : 1;
    // leichtes Atmen plus Parallaxe zur Maus
    k.position.set(
      this.kameraBasis.x + (Math.sin(t * 0.21) * 0.12 + this.mausGlatt.x * 0.6) * ruhig,
      this.kameraBasis.y + (Math.sin(t * 0.17 + 1.3) * 0.08 - this.mausGlatt.y * 0.35) * ruhig,
      this.kameraBasis.z + Math.sin(t * 0.13) * 0.1 * ruhig - this.hyper * 1.2);
    k.lookAt(0, 0, 0);
    k.fov = this.fovBasis + this.hyper * 22;
    k.updateProjectionMatrix();
  }

  // Messung kurz aussetzen, z. B. beim Mikrofonstart oder während eines Effekts (Einbrüche dort sind normal)
  pausiereMessung(ms = 2500) { this._pauseBis = Math.max(this._pauseBis, performance.now() + ms); this._zuwenig = 0; }

  // Automatik mit Hysterese: Absenken erst nach fünf schwachen Sekunden in Folge (unter 45 fps),
  // Anheben nach 10 s stabil über 57 fps. Kurze Ruckler, Pausen und verdeckte Tabs zählen nicht.
  _messe(jetzt) {
    this._frames++;
    const d = jetzt - this._fpsStart;
    if (d < 1000) return;
    this.fps = (this._frames * 1000) / d; this._frames = 0; this._fpsStart = jetzt;
    if (this.stufeWahl !== "auto") return;
    if (document.hidden || d > 1600 || jetzt < this._pauseBis) { this._zuwenig = 0; this._gutSeit = jetzt; return; }
    const i = REIHE.indexOf(this.stufe);
    this.fpsLog = [...(this.fpsLog || []).slice(-30), Math.round(this.fps)];
    if (this.fps < 45) { this._zuwenig++; this._gutSeit = jetzt; } else this._zuwenig = 0;
    if (this.fps < 55) this._gutSeit = jetzt;
    if (this._zuwenig >= 5 && i < REIHE.length - 1 && jetzt - this._zuletztGewechselt > 4000) {
      this._zuletztGewechselt = jetzt; this._zuwenig = 0; this._gutSeit = jetzt;
      this.setzeStufe(REIHE[i + 1], "auto ab");
    } else if (i > 0 && jetzt - this._gutSeit > 10000 && jetzt - this._zuletztGewechselt > 10000) {
      this._zuletztGewechselt = jetzt; this._gutSeit = jetzt;
      this.setzeStufe(REIHE[i - 1], "auto auf");
    }
  }
}

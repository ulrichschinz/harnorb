// Hintergrund: Nebelkuppel, Sternenfeld in drei Ebenen (Parallaxe), Variante A „Mond“ mit Lichtnetz,
// Variante B „Kugelraumer“ mit Ringwulst und Wabenstruktur (eigener Entwurf).
import * as THREE from "three";
import { RAUSCHEN } from "./glsl.js";
import { tween, ease } from "./tween.js";

const SONNE = new THREE.Vector3(0.85, 0.35, 0.55).normalize();

const NEBEL_VS = /* glsl */`varying vec3 vDir; void main(){ vDir = normalize(position); gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }`;
const NEBEL_FS = /* glsl */`
uniform float uZeit, uOktaven, uComic, uSaett;
varying vec3 vDir;
${RAUSCHEN}
void main(){
  vec3 d = normalize(vDir);
  float n = fbmN(d * 2.2 + vec3(uZeit * 0.004, 0.0, 0.0), uOktaven);
  float m = fbmN(d * 4.5 - vec3(0.0, uZeit * 0.003, 0.0) + n, uOktaven);
  float band = exp(-pow(dot(d, normalize(vec3(0.3, 1.0, -0.2))) * 2.4, 2.0)); // Milchstraßenband
  vec3 c = vec3(0.002, 0.003, 0.010);
  c += vec3(0.20, 0.06, 0.32) * smoothstep(0.0, 0.9, n) * 0.16;
  c += vec3(0.02, 0.18, 0.30) * smoothstep(0.1, 0.9, m) * 0.12;
  c += vec3(0.30, 0.10, 0.18) * smoothstep(0.35, 1.0, n * m * 2.0) * 0.12;
  c += vec3(0.12, 0.11, 0.16) * band * (0.35 + 0.65 * smoothstep(-0.2, 0.6, m)) * 0.16;
  if (uComic > 0.5) c = c * 0.55 + vec3(0.0, 0.004, 0.022);
  float l = dot(c, vec3(0.3, 0.59, 0.11));
  gl_FragColor = vec4(mix(vec3(l), c, uSaett), 1.0);
}`;

const STERNE_VS = /* glsl */`
attribute float aGroesse; attribute vec3 aFarbe; attribute float aPhase;
uniform float uZeit, uPixel, uHyper;
varying vec3 vFarbe; varying float vGlanz;
void main(){
  vec4 mv = modelViewMatrix * vec4(position, 1.0);
  gl_Position = projectionMatrix * mv;
  float funkeln = 0.75 + 0.25 * sin(uZeit * (1.0 + aPhase * 3.0) + aPhase * 40.0);
  gl_PointSize = max(1.0, aGroesse * uPixel * (1.0 + uHyper * 1.5));
  vFarbe = aFarbe * funkeln; vGlanz = aGroesse;
}`;
const STERNE_FS = /* glsl */`
uniform float uComic, uSaett;
varying vec3 vFarbe; varying float vGlanz;
void main(){
  vec2 p = gl_PointCoord * 2.0 - 1.0;
  float d = length(p);
  float a = exp(-d * d * 7.0);
  if (vGlanz > 2.2) a += 0.6 * (exp(-abs(p.x) * 22.0) * exp(-abs(p.y) * 2.5) + exp(-abs(p.y) * 22.0) * exp(-abs(p.x) * 2.5));
  if (uComic > 0.5) a = step(abs(p.x) * abs(p.y) * 12.0 + d * 0.6, 0.35);
  float l = dot(vFarbe, vec3(0.3, 0.59, 0.11));
  gl_FragColor = vec4(mix(vec3(l), vFarbe, uSaett) * a, 1.0);
}`;

const MOND_VS = /* glsl */`
varying vec3 vPosO; varying vec3 vNormW; varying vec3 vPosW;
void main(){ vPosO = position; vNormW = normalize(mat3(modelMatrix) * normal); vec4 w = modelMatrix * vec4(position, 1.0); vPosW = w.xyz; gl_Position = projectionMatrix * viewMatrix * w; }`;
const MOND_FS = /* glsl */`
uniform float uZeit, uComic, uSaett, uNetz;
uniform vec3 uSonne; uniform mat3 uDreh;
varying vec3 vPosO; varying vec3 vNormW; varying vec3 vPosW;
${RAUSCHEN}
float krater(vec3 p, float s){
  vec3 z = zellen(p * s);
  float r = 0.25 + 0.3 * z.z;
  float d = z.x / r;
  float schuessel = d < 1.0 ? (d * d - 1.0) * 0.6 : 0.0;
  float wall = exp(-pow((d - 1.0) * 5.0, 2.0)) * 0.35;
  return (schuessel + wall) * step(0.45, z.z + 0.2);
}
float hoehe(vec3 p){
  return krater(p, 3.0) * 0.5 + krater(p + 3.1, 7.0) * 0.25 + krater(p + 7.7, 16.0) * 0.1 + fbm3(p * 8.0) * 0.05;
}
void main(){
  vec3 p = normalize(vPosO);
  float h = hoehe(p);
  // Normale aus der Höhe per Bildschirmableitung
  vec3 dx = dFdx(vPosW), dy = dFdy(vPosW);
  float hx = dFdx(h), hy = dFdy(h);
  vec3 N = normalize(vNormW);
  vec3 g = (cross(dy, N) * hx + cross(N, dx) * hy) / max(dot(dx, cross(dy, N)), 1e-6);
  vec3 Nb = normalize(N - g * 0.012);
  float maria = smoothstep(0.0, 0.5, fbm3(p * 1.6 + 2.0));
  vec3 albedo = mix(vec3(0.62, 0.60, 0.58), vec3(0.30, 0.30, 0.34), maria * 0.75) * (0.85 + h * 0.4);
  float licht = max(dot(Nb, uSonne), 0.0);
  if (uComic > 0.5) licht = floor(licht * 3.0 + 0.6) / 3.0;
  vec3 c = albedo * licht * 0.85;
  // Lichtnetz (Technogeflecht): feine Linien entlang von Zellkanten, Pulse wandern
  vec3 z = zellen(p * 11.0);
  float linie = 1.0 - smoothstep(0.0, 0.028, z.y - z.x);
  vec3 z2 = zellen(p * 27.0 + 5.0);
  float fein = 1.0 - smoothstep(0.0, 0.02, z2.y - z2.x);
  float puls = pow(0.5 + 0.5 * sin(z.z * 60.0 + uZeit * 1.6 - length(p.xy) * 8.0), 8.0);
  float nacht = smoothstep(0.15, -0.25, dot(N, uSonne));
  vec3 netz = vec3(0.25, 0.85, 1.0) * linie * (0.35 + puls * 2.2) + vec3(1.0, 0.65, 0.25) * fein * 0.25 * (0.4 + puls);
  // nur auf der Nachtseite und am Terminator (Stadtlichter), auf der Tagseite unsichtbar
  c += netz * uNetz * nacht * 1.2;
  // dünner Lichtsaum am Rand
  float rand = pow(1.0 - max(dot(N, normalize(cameraPosition - vPosW)), 0.0), 3.0);
  c += vec3(0.35, 0.55, 1.0) * rand * 0.35 * (0.3 + max(dot(N, uSonne), 0.0));
  float l = dot(c, vec3(0.3, 0.59, 0.11));
  gl_FragColor = vec4(mix(vec3(l), c, uSaett), 1.0);
}`;

// Kugelraumer: Wabenplatten, Paneelgürtel, Reihen beleuchteter Fenster (nachts heller), gläserne Polkuppeln
const RAUMER_FS = /* glsl */`
uniform float uZeit, uComic, uSaett;
uniform vec3 uSonne;
varying vec3 vPosO; varying vec3 vNormW; varying vec3 vPosW;
${RAUSCHEN}
float waben(vec2 uv){
  vec2 r = vec2(1.0, 1.732);
  vec2 h = r * 0.5;
  vec2 a = mod(uv, r) - h, b = mod(uv - h, r) - h;
  vec2 g = dot(a, a) < dot(b, b) ? a : b;
  vec2 q = abs(g);
  return max(dot(q, normalize(vec2(1.0, 1.732))), q.x);
}
void main(){
  vec3 p = normalize(vPosO);
  float lat = asin(clamp(p.y, -1.0, 1.0)), lon = atan(p.z, p.x);
  vec2 uv = vec2(lon * 6.0, lat * 6.0);
  float fuge = smoothstep(0.43, 0.47, waben(uv * 2.2));
  vec3 N = normalize(vNormW), V = normalize(cameraPosition - vPosW);
  float nl = dot(N, uSonne);
  float licht = max(nl, 0.0);
  if (uComic > 0.5) licht = floor(licht * 3.0 + 0.6) / 3.0;
  float platte = 0.75 + 0.25 * hash13(floor(vec3(uv * 2.2, 1.0)));
  float guertel = smoothstep(0.02, 0.0, abs(fract(lat * 2.6) - 0.5) - 0.44);
  vec3 basis = vec3(0.46, 0.48, 0.54) * platte * (1.0 - fuge * 0.55) * (1.0 - guertel * 0.45);
  float glanz = pow(max(dot(N, normalize(uSonne + V)), 0.0), 50.0) * 0.6 * licht;
  vec3 c = basis * (licht * 0.72 + 0.018) + vec3(glanz);
  // Fensterreihen
  float nacht = smoothstep(0.15, -0.35, nl);
  float rf = lat / 3.14159 * 22.0;
  float ri = floor(rf);
  float inReihe = smoothstep(0.2, 0.12, abs(fract(rf) - 0.5)) * step(0.5, mod(ri, 2.0)) * step(abs(lat), 1.15);
  float sp = lon / 6.28318 * 260.0 * max(cos(lat), 0.25);
  float inSpalte = smoothstep(0.34, 0.24, abs(fract(sp) - 0.5));
  float id = hash13(vec3(ri, floor(sp), 7.0));
  float an = step(0.32, id) * (0.8 + 0.2 * sin(uZeit * 0.4 + id * 50.0));
  vec3 fFarbe = mix(vec3(1.0, 0.78, 0.45), vec3(0.6, 0.85, 1.0), step(0.8, id));
  c += fFarbe * inReihe * inSpalte * an * (0.25 + nacht * 1.4);
  // Polkuppeln aus Glas mit Leuchtring
  float ap = abs(p.y);
  float kuppel = smoothstep(0.925, 0.935, ap);
  vec3 glas = vec3(0.03, 0.09, 0.16) + vec3(0.2, 0.55, 1.0) * 0.35 * (0.6 + 0.4 * sin(uZeit * 0.7)) + vec3(glanz * 2.0);
  c = mix(c, glas, kuppel);
  c += vec3(0.4, 0.8, 1.0) * exp(-pow((ap - 0.93) * 140.0, 2.0)) * 0.9;
  float rand = pow(1.0 - max(dot(N, V), 0.0), 3.0);
  c += vec3(0.4, 0.6, 1.0) * rand * 0.25;
  float l = dot(c, vec3(0.3, 0.59, 0.11));
  gl_FragColor = vec4(mix(vec3(l), c, uSaett), 1.0);
}`;
// Ringwulst: segmentierte Platten, Triebwerksöffnungen außen (dunkler Schlund, blauweiße Glut), Positionslichter
const WULST_FS = /* glsl */`
uniform float uZeit, uComic, uSaett;
uniform vec3 uSonne;
varying vec3 vPosO; varying vec3 vNormW; varying vec3 vPosW;
void main(){
  vec3 N = normalize(vNormW), V = normalize(cameraPosition - vPosW);
  float licht = max(dot(N, uSonne), 0.0);
  if (uComic > 0.5) licht = floor(licht * 3.0 + 0.6) / 3.0;
  float w = atan(vPosO.y, vPosO.x);
  float rho = length(vPosO.xy);
  float seg = smoothstep(0.0, 0.06, abs(fract(w * 48.0 / 6.28318) - 0.5) - 0.44);
  float glanz = pow(max(dot(N, normalize(uSonne + V)), 0.0), 40.0) * 0.5 * licht;
  vec3 c = vec3(0.36, 0.37, 0.42) * (licht * 0.95 + 0.02) * (0.7 + 0.3 * seg) + vec3(glanz);
  // Triebwerke: 16 runde Öffnungen auf der Außenseite
  float sw = (fract(w * 16.0 / 6.28318) - 0.5) * 6.28318 / 16.0 * rho;
  float aussen = smoothstep(1.06, 1.12, rho);
  float d = length(vec2(sw, vPosO.z)) / 0.1;
  float oeffnung = smoothstep(1.0, 0.85, d) * aussen;
  float wand = exp(-pow((d - 0.95) * 9.0, 2.0)) * aussen;
  float puls = 0.75 + 0.25 * sin(uZeit * 2.5 + floor(w * 16.0 / 6.28318) * 1.3);
  c = mix(c, vec3(0.01, 0.012, 0.02), oeffnung);
  c += vec3(0.45, 0.8, 1.7) * smoothstep(0.75, 0.0, d) * aussen * puls * 1.8;
  c += vec3(0.6, 0.7, 0.9) * wand * 0.35;
  // Fensterband auf der Oberseite
  float band = smoothstep(0.035, 0.02, abs(vPosO.z - 0.1)) * step(0.5, fract(w * 160.0 / 6.28318)) * smoothstep(1.02, 0.98, rho);
  c += vec3(1.0, 0.82, 0.5) * band * 0.9;
  // Positionslichter rot und grün, blinkend
  float blink = step(0.9, fract(uZeit * 0.8));
  float rot = exp(-pow(length(vec2((w - 1.57) * rho, vPosO.z)) * 25.0, 2.0));
  float gruen = exp(-pow(length(vec2((w + 1.57) * rho, vPosO.z)) * 25.0, 2.0));
  c += (vec3(1.0, 0.15, 0.1) * rot + vec3(0.1, 1.0, 0.3) * gruen) * blink * 4.0 * aussen;
  float l = dot(c, vec3(0.3, 0.59, 0.11));
  gl_FragColor = vec4(mix(vec3(l), c, uSaett), 1.0);
}`;

function sterne(anzahl, rMin, rMax, groesse) {
  const pos = new Float32Array(anzahl * 3), g = new Float32Array(anzahl), f = new Float32Array(anzahl * 3), ph = new Float32Array(anzahl);
  const farben = [[1, 1, 1], [0.75, 0.85, 1], [1, 0.9, 0.75], [1, 0.75, 0.7], [0.8, 0.9, 1]];
  for (let i = 0; i < anzahl; i++) {
    const u = Math.random() * 2 - 1, w = Math.random() * Math.PI * 2, r = rMin + Math.random() * (rMax - rMin);
    const s = Math.sqrt(1 - u * u);
    pos.set([Math.cos(w) * s * r, u * r, Math.sin(w) * s * r - rMin * 0.2], i * 3);
    g[i] = groesse * (0.5 + Math.random() ** 6 * 4);
    const c = farben[Math.floor(Math.random() * farben.length)];
    const hell = 0.5 + Math.random() * 0.8;
    f.set([c[0] * hell, c[1] * hell, c[2] * hell], i * 3);
    ph[i] = Math.random();
  }
  const geo = new THREE.BufferGeometry();
  geo.setAttribute("position", new THREE.BufferAttribute(pos, 3));
  geo.setAttribute("aGroesse", new THREE.BufferAttribute(g, 1));
  geo.setAttribute("aFarbe", new THREE.BufferAttribute(f, 3));
  geo.setAttribute("aPhase", new THREE.BufferAttribute(ph, 1));
  return geo;
}

export class Hintergrund {
  constructor(szene) {
    this.gruppe = new THREE.Group();
    szene.add(this.gruppe);
    this.u = { uZeit: { value: 0 }, uComic: { value: 0 }, uSaett: { value: 1 }, uOktaven: { value: 5 }, uSonne: { value: SONNE.clone() },
      uNetz: { value: 1 }, uPixel: { value: 1 }, uHyper: { value: 0 } };

    this.nebel = new THREE.Mesh(new THREE.SphereGeometry(1500, 48, 32), new THREE.ShaderMaterial({
      uniforms: this.u, vertexShader: NEBEL_VS, fragmentShader: NEBEL_FS, side: THREE.BackSide, depthWrite: false,
    }));
    this.nebel.renderOrder = -10;
    this.gruppe.add(this.nebel);

    this.sternEbenen = [];
    for (const [n, a, b, gr] of [[2600, 700, 1300, 1.3], [900, 160, 400, 1.6], [220, 40, 90, 2.0]]) {
      const pts = new THREE.Points(sterne(n, a, b, gr), new THREE.ShaderMaterial({
        uniforms: this.u, vertexShader: STERNE_VS, fragmentShader: STERNE_FS, transparent: true,
        blending: THREE.AdditiveBlending, depthWrite: false,
      }));
      pts.renderOrder = -9;
      this.gruppe.add(pts);
      this.sternEbenen.push(pts);
    }

    // Variante A: Mond
    this.mond = new THREE.Group();
    const mondKoerper = new THREE.Mesh(new THREE.SphereGeometry(1, 128, 96), new THREE.ShaderMaterial({
      uniforms: this.u, vertexShader: MOND_VS, fragmentShader: MOND_FS,
    }));
    this.mondKontur = new THREE.Mesh(new THREE.SphereGeometry(1.025, 64, 48), new THREE.MeshBasicMaterial({ color: 0x000000, side: THREE.BackSide }));
    this.mondKontur.visible = false;
    this.mond.add(mondKoerper, this.mondKontur);
    this.mond.scale.setScalar(10);
    this.mond.position.set(-40, 21, -125);
    this.mond.rotation.set(0.3, 0.8, 0.1);

    // Variante B: Kugelraumer
    this.raumer = new THREE.Group();
    const huelle = new THREE.Mesh(new THREE.SphereGeometry(1, 128, 96), new THREE.ShaderMaterial({
      uniforms: this.u, vertexShader: MOND_VS, fragmentShader: RAUMER_FS,
    }));
    const wulst = new THREE.Mesh(new THREE.TorusGeometry(1.0, 0.14, 48, 256), new THREE.ShaderMaterial({
      uniforms: this.u, vertexShader: MOND_VS, fragmentShader: WULST_FS,
    }));
    wulst.rotation.x = Math.PI / 2;
    wulst.scale.set(1.02, 1.02, 0.55);
    this.raumerKontur = new THREE.Group();
    const k1 = new THREE.Mesh(new THREE.SphereGeometry(1.03, 64, 48), new THREE.MeshBasicMaterial({ color: 0x000000, side: THREE.BackSide }));
    const k2 = new THREE.Mesh(new THREE.TorusGeometry(1.0, 0.16, 16, 96), new THREE.MeshBasicMaterial({ color: 0x000000, side: THREE.BackSide }));
    k2.rotation.x = Math.PI / 2; k2.scale.set(1.03, 1.03, 0.6);
    this.raumerKontur.add(k1, k2);
    this.raumerKontur.visible = false;
    this.raumer.add(huelle, wulst, this.raumerKontur);
    this.raumer.scale.setScalar(11);
    this.raumer.position.set(-40, 14, -100);
    this.raumer.rotation.set(0.32, 0, 0.2);

    // Nicht in die drehende Gruppe: sonst wandern Mond und Raumer mit der Zeit aus dem Bild
    szene.add(this.mond, this.raumer);
    // Bei Listen und Tafeln weicht der Hintergrundkörper in die Ecke aus, damit keine Karte ihn verdeckt
    this.versatz = 0; this.versatzZiel = 0;
    this.mondBasis = this.mond.position.clone(); this.raumerBasis = this.raumer.position.clone();
    this.art = null;
    this.setzeArt("mond", true);
  }

  qualitaet(p) { this.u.uOktaven.value = p.oktaven; this.pr = Math.min(devicePixelRatio || 1, p.pixel); }

  setzeStil(stil) {
    const comic = stil === "comic";
    this.u.uComic.value = comic ? 1 : 0;
    this.mondKontur.visible = comic;
    this.raumerKontur.visible = comic;
  }

  // Wechsel mit kurzem Auf- bzw. Abtauchen
  setzeArt(art, sofort = false) {
    if (art === this.art) return;
    const neu = art === "raumer" ? this.raumer : this.mond, alt = art === "raumer" ? this.mond : this.raumer;
    this.art = art;
    if (sofort) { neu.visible = true; alt.visible = false; return; }
    const altZ = alt.position.z, neuZ = neu.position.z;
    tween({ dauer: 700, ease: ease.inCubic, update: (w) => { alt.position.z = altZ - w * 400; }, fertig: () => { alt.visible = false; alt.position.z = altZ; } });
    neu.visible = true;
    neu.position.z = neuZ - 400;
    tween({ dauer: 1400, verzoegerung: 350, ease: ease.outCubic, update: (w) => { neu.position.z = neuZ - 400 * (1 - w); } });
  }

  abseits(an) { this.versatzZiel = an ? 1 : 0; }

  update(dt, zeit, saett, hyper) {
    this.versatz += (this.versatzZiel - this.versatz) * Math.min(1, dt * 1.8);
    // Hochformat (Telefon): Hintergrundkörper oben ins Bild holen statt links außerhalb
    const schmal = innerWidth / Math.max(innerHeight, 1) < 0.8;
    const bx = -7, by = 30;
    const mx = schmal ? bx : this.mondBasis.x, rx = schmal ? bx : this.raumerBasis.x;
    this.mond.position.x = mx - this.versatz * (schmal ? 4 : 30); this.mond.position.y = (schmal ? by : this.mondBasis.y) + this.versatz * (schmal ? 3 : 9);
    this.raumer.position.x = rx - this.versatz * (schmal ? 4 : 30);
    this.u.uZeit.value = zeit;
    this.u.uSaett.value = saett;
    this.u.uHyper.value = hyper;
    this.u.uPixel.value = (this.pr || Math.min(devicePixelRatio || 1, 2)) * (innerHeight / 900);
    this.mond.rotation.y += dt * 0.006;
    this.raumer.rotation.y += dt * 0.04;
    this.raumer.position.y = (schmal ? 26 : 14) + this.versatz * (schmal ? 3 : 9) + Math.sin(zeit * 0.2) * 0.4;
    // Sterne im Hyperraum gestreckt: die nahen Ebenen fliegen auf die Kamera zu
    this.sternEbenen[2].position.z = (hyper * 70) % 140;
    this.sternEbenen[1].position.z = (hyper * 40) % 200;
    this.gruppe.rotation.y = zeit * 0.0015;
  }
}

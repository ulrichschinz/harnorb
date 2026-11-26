// HarnoRb: schillernde Kugel wie eine Seifenblase mit Energiekern.
// Hülle: echte Dünnschicht-Interferenz über 16 Wellenlängen (CIE-Farbabgleich nach Wyman, Sloan, Shirley 2013),
// Filmdicke als Flussfeld mit Schwerkraftgefälle (oben dünn bis schwarz, unten dick), wirbelnde Bänder,
// Fresnel, gespiegeltes Studiolicht (Softbox, Streifenlicht), scharfe Glanzpunkte, Energieadern beim Aufladen.
// Zweite Farbschicht: die Rückseite der Blase, durch die Vorderseite gesehen (gibt Tiefe wie bei echten Blasen).
// Farbe physikalisch nah: nur teilweiser Grauabzug, höhere Ordnungen bleiben zart (Rosa, Mintgrün).
// Innen: kleine Spiralgalaxie mit gold-weißem Herz, Armen und Staubbahnen, per Raymarching nur durch die Kernkugel.
// Halo: runder, weicher Saum ohne Strahlen, Farbe aus dem groben Schwerkraftgefälle des Films, dazu Bloom.
// Stil „comic“: Farbstufen, Halbtonraster, Tuschekontur, gezeichnete Speedlines.
import * as THREE from "three";
import { RAUSCHEN } from "./glsl.js";

// ---------- Spektrale Gewichte (einmal in JS): Wellenlänge -> lineares sRGB, weiß normiert ----------
const N_WELLEN = 16;
function spektrum() {
  const g = (x, m, s1, s2) => { const t = (x - m) / (x < m ? s1 : s2); return Math.exp(-0.5 * t * t); };
  const roh = [];
  const summe = [0, 0, 0];
  for (let i = 0; i < N_WELLEN; i++) {
    const l = 390 + i * 21;
    const X = 1.056 * g(l, 599.8, 37.9, 31.0) + 0.362 * g(l, 442.0, 16.0, 26.7) - 0.065 * g(l, 501.1, 20.4, 26.2);
    const Y = 0.821 * g(l, 568.8, 46.9, 40.5) + 0.286 * g(l, 530.9, 16.3, 31.1);
    const Z = 1.217 * g(l, 437.0, 11.8, 36.0) + 0.681 * g(l, 459.0, 26.0, 13.8);
    const rgb = [3.2406 * X - 1.5372 * Y - 0.4986 * Z, -0.9689 * X + 1.8758 * Y + 0.0415 * Z, 0.0557 * X - 0.2040 * Y + 1.0570 * Z];
    roh.push(rgb); for (let k = 0; k < 3; k++) summe[k] += rgb[k];
  }
  return roh.map((c) => new THREE.Vector3(c[0] / summe[0], c[1] / summe[1], c[2] / summe[2]));
}
const SPEKTRUM = spektrum();

// Gemeinsam für Hülle und Halo: Filmdicke und Interferenzfarbe
// Gemeinsam für Hülle und Halo: Filmdicke und Interferenzfarbe
const FILM = /* glsl */`
uniform vec3 uSpek[${N_WELLEN}];
mat2 dreh2(float a){ float c = cos(a), s = sin(a); return mat2(c, -s, s, c); }
// Filmdicke in nm. q: Punkt auf der (verformten) Einheitskugel im Objektraum, t: Filmzeit.
// Seifenhaut wie unter dem Mikroskop: Schwerkraft zieht den Film nach unten (oben schwarz bis silbern-gold,
// unten dick), Konvektion verwirbelt ihn zu Marmor. Zweifacher Domain-Warp mit glattem, niederfrequentem
// Rauschen, damit die Bänder weich fließen und nirgends knicken.
float filmDicke(vec3 q, float t){
  vec3 p = q;
  p.xz = dreh2(0.55 * sin(q.y * 1.7 + t * 0.05) + t * 0.018) * p.xz;      // Scherung je Höhe
  vec3 w1 = vec3(snoise(p * 0.85 + vec3(0.0, t * 0.045, 0.0)),
                 snoise(p * 0.85 + vec3(4.1, -t * 0.038, 2.3)),
                 snoise(p * 0.85 + vec3(-3.7, 1.9, t * 0.03)));
  vec3 p2 = p + w1 * 0.42;
  vec2 w2 = vec2(snoise(p2 * 1.45 + vec3(1.3, t * 0.07, 0.0)), snoise(p2 * 1.45 + vec3(-2.1, 0.0, t * 0.06)));
  vec3 p3 = p2 + vec3(w2.x, w2.y * 0.6, w2.y) * 0.2;
  float g = clamp(0.5 - 0.5 * q.y + 0.13 * w1.x, 0.0, 1.0);             // 0 oben, 1 unten
  float d = mix(250.0, 720.0, pow(g, 0.85)) - 40.0 * (1.0 - smoothstep(0.0, 0.4, g)); // oben zartes Gold-Magenta, weich auslaufend
  // Bänder, die langsam nach unten sinken; oben schwach (dort ist der Film zu dünn für Farbe)
  d += 125.0 * sin(p3.y * 4.3 - t * 0.28 + w2.x * 1.1) * (0.32 + 0.68 * smoothstep(0.0, 0.6, g));
  d += 30.0 * w2.y * g + 38.0 * snoise(p3 * 3.1 + vec3(0.0, -t * 0.05, 0.0)) * g;
  return max(d, 0.0);
}
// Reflexionsfarbe eines Seifenfilms (n = 1.33), Phasensprung an der Oberseite: dünn -> schwarz.
// Weiß normiert: über viele Ordnungen gemittelt ergibt sich (1, 1, 1).
vec3 duennschicht(float d, float cosI){
  float n2 = 1.33;
  float cosT = sqrt(max(0.0, 1.0 - (1.0 - cosI * cosI) / (n2 * n2)));
  float opt = 12.56637 * n2 * d * cosT;
  vec3 s = vec3(0.0);
  for (int i = 0; i < ${N_WELLEN}; i++){
    float l = 390.0 + float(i) * 21.0;
    s += uSpek[i] * (0.5 - 0.5 * cos(opt / l));
  }
  return max(s * 2.0, 0.0);
}
// Grobe Variante mit jeder zweiten Wellenlänge (Rückseite der Blase, Halo)
vec3 duennschichtGrob(float d, float cosI){
  float n2 = 1.33;
  float cosT = sqrt(max(0.0, 1.0 - (1.0 - cosI * cosI) / (n2 * n2)));
  float opt = 12.56637 * n2 * d * cosT;
  vec3 s = vec3(0.0);
  for (int i = 0; i < ${N_WELLEN}; i += 2){
    float l = 390.0 + float(i) * 21.0 + 10.5;
    s += (uSpek[i] + uSpek[i + 1]) * (0.5 - 0.5 * cos(opt / l));
  }
  return max(s * 2.0, 0.0);
}
// Edle Farbe: nur ein Teil des Grauanteils wird abgezogen, die Sättigung kaum angehoben.
// So bleiben die höheren Ordnungen zart (Rosa, Mintgrün), die ersten Ordnungen kräftig (Gold, Magenta, Blau).
vec3 edel(vec3 f){
  float mn = min(min(f.r, f.g), f.b);
  f = max(f - mn * 0.32, 0.0) * 1.16;
  float l = dot(f, vec3(0.2126, 0.7152, 0.0722));
  return max(mix(vec3(l), f, 1.08), 0.0);
}
// Satte Farben (Comic, Energieadern): Grauanteil ganz abziehen
vec3 satt(vec3 f, float k){
  float mn = min(min(f.r, f.g), f.b);
  f = max(f - mn * k, 0.0);
  float l = dot(f, vec3(0.2126, 0.7152, 0.0722));
  return max(mix(vec3(l), f, 1.25), 0.0) * (1.0 + k * 0.9);
}
`;

const HUELLE_VS = /* glsl */`
uniform float uZeit, uPegel, uVerformung, uStreckung;
varying vec3 vPosW, vNormW, vPosO, vNormO;
${RAUSCHEN}
float verschiebung(vec3 n){
  float a = snoise(n * 1.6 + vec3(0.0, uZeit * 0.23, uZeit * 0.11)) * 0.6;
  float b = snoise(n * 3.7 - vec3(uZeit * 0.37)) * 0.08;
  // Stimme: niederfrequente, fast radialsymmetrische Pulsation (keine Beulen, Glanzlichter bleiben ganz)
  float c = 0.65 + 0.35 * snoise(n * 0.9 + vec3(0.0, uZeit * 0.45, 0.0));
  return (a + b) * uVerformung * 0.05 + c * uPegel * 0.026;
}
vec3 verschoben(vec3 n){ return n * (1.0 + verschiebung(n)); }
void main(){
  vec3 n = normalize(position);
  vec3 t = normalize(cross(n, abs(n.y) < 0.99 ? vec3(0.0, 1.0, 0.0) : vec3(1.0, 0.0, 0.0)));
  vec3 b = cross(n, t);
  float e = 0.012;
  vec3 p0 = verschoben(n);
  vec3 p1 = verschoben(normalize(n + t * e));
  vec3 p2 = verschoben(normalize(n + b * e));
  vec3 nn = normalize(cross(p1 - p0, p2 - p0));
  if (dot(nn, n) < 0.0) nn = -nn;
  vec3 p = p0;
  p.z *= 1.0 + uStreckung; // Hyperraum: in Flugrichtung gestreckt
  vPosO = p0; vNormO = nn;
  vec4 w = modelMatrix * vec4(p, 1.0);
  vPosW = w.xyz;
  vNormW = normalize(mat3(modelMatrix) * nn);
  gl_Position = projectionMatrix * viewMatrix * w;
}`;

const HUELLE_FS = /* glsl */`
uniform float uZeit, uPegel, uSaett, uHell, uFlacker, uSpirale, uSchwarz, uLadung, uComic, uSchritte, uFarbtempo, uTiefe, uFilmZeit;
uniform vec3 uKameraO;
uniform mat3 uObjZuWelt;
varying vec3 vPosW, vNormW, vPosO, vNormO;
${RAUSCHEN}
${FILM}
// Studio-Umgebung in Weltrichtungen: dunkler Raum mit kühlem Verlauf, große Softbox oben links,
// Streifenlicht rechts, ein weiches Ringlicht am Horizont (gibt dem Rand seine Farben), warmer Bodenreflex.
vec3 umgebung(vec3 r){
  vec3 c = mix(vec3(0.012, 0.014, 0.030), vec3(0.06, 0.06, 0.11), smoothstep(-0.6, 0.9, r.y));
  c += vec3(0.55, 0.60, 0.80) * exp(-r.y * r.y * 9.0) * 0.16;                       // Ringlicht Horizont
  c += vec3(0.35, 0.22, 0.60) * pow(max(dot(r, normalize(vec3(-0.8, -0.2, 0.4))), 0.0), 3.0) * 0.35;
  c += vec3(0.10, 0.40, 0.65) * pow(max(dot(r, normalize(vec3(0.8, -0.5, 0.35))), 0.0), 3.0) * 0.35;
  // Softbox
  vec3 f = normalize(vec3(-0.45, 0.6, 0.66));
  float d = dot(r, f);
  vec3 ax = normalize(cross(f, vec3(0.0, 1.0, 0.0))), ay = cross(ax, f);
  vec2 uv = vec2(dot(r, ax), dot(r, ay));
  float box = step(0.0, d) * smoothstep(0.25, 0.20, abs(uv.x)) * smoothstep(0.17, 0.12, abs(uv.y));
  float sprosse = 1.0 - (1.0 - smoothstep(0.006, 0.014, abs(uv.x))) * 0.8;
  c += vec3(1.0, 0.98, 0.95) * box * sprosse * 3.0;
  // Streifenlicht rechts, senkrecht
  vec3 f2 = normalize(vec3(0.9, 0.1, 0.42));
  vec3 ax2 = normalize(cross(f2, vec3(0.0, 1.0, 0.0)));
  float s2 = step(0.0, dot(r, f2)) * smoothstep(0.05, 0.03, abs(dot(r, ax2))) * smoothstep(0.75, 0.5, abs(r.y));
  c += vec3(0.85, 0.92, 1.0) * s2 * 1.0;
  // Bodenreflex, warm
  c += vec3(1.0, 0.55, 0.3) * pow(max(-r.y, 0.0), 5.0) * 0.3;
  return c;
}
// Weiche Fassung derselben Umgebung für die Rückseite (dort wirken scharfe Lichtfenster wie Fehler)
vec3 umgebungWeich(vec3 r){
  vec3 c = mix(vec3(0.012, 0.014, 0.030), vec3(0.06, 0.06, 0.11), smoothstep(-0.6, 0.9, r.y));
  c += vec3(0.55, 0.60, 0.80) * exp(-r.y * r.y * 6.0) * 0.18;
  c += vec3(1.0, 0.97, 0.95) * pow(max(dot(r, normalize(vec3(-0.45, 0.6, 0.66))), 0.0), 6.0) * 0.5;
  c += vec3(1.0, 0.55, 0.3) * pow(max(-r.y, 0.0), 5.0) * 0.3;
  return c;
}
float hash12(vec2 p){ vec3 p3 = fract(vec3(p.xyx) * 0.1031); p3 += dot(p3, p3.yzx + 33.33); return fract((p3.x + p3.y) * p3.z); }
// Innerer Kern: kleine Spiralgalaxie in einer Kugel (Radius 0,64) mit gold-weißem Herz, magentafarbenen und
// violetten Armen, türkisfarbenen Außenrändern und dunklen Staubbahnen. Raymarching nur durch die Kernkugel,
// darum dicht genug für Struktur; die Arme drehen und geben beim Drehen der Kamera echte Parallaxe.
vec3 kern(vec3 ro, vec3 rd, out float deckung){
  const float RK = 0.7;
  deckung = 0.0;
  float b = dot(ro, rd), c = dot(ro, ro) - RK * RK, h = b * b - c;
  // weicher Lichtschein um den Kern, auch für Strahlen, die ihn verfehlen
  float nah = max(0.0, -b);
  float abstand = sqrt(max(dot(ro, ro) - nah * nah, 0.0));
  vec3 schein = vec3(0.85, 0.35, 1.0) * exp(-abstand * abstand * 9.0) * (0.10 + uTiefe * 0.10 + uSpirale * 0.15 + uPegel * 0.12);
  if (h <= 0.0) return schein;
  h = sqrt(h);
  float t0 = max(-b - h, 0.0), t1 = -b + h;
  float n = max(uSchritte, 1.0);
  float st = (t1 - t0) / n;
  float zufall = hash12(gl_FragCoord.xy + fract(uZeit * 7.0) * 37.0);
  float rot = uZeit * (0.12 + uSpirale * 0.7);
  float c0 = cos(rot), s0 = sin(rot);
  vec3 summe = vec3(0.0);
  float T = 1.0;
  for (int i = 0; i < 16; i++){
    if (float(i) >= n) break;
    vec3 p = ro + rd * (t0 + (float(i) + zufall) * st);
    // geneigte Scheibe (etwa 55 Grad), damit man auf die Spirale schaut
    vec3 q = vec3(p.x, p.y * 0.57 - p.z * 0.82, p.y * 0.82 + p.z * 0.57);
    q = vec3(0.94 * q.x + 0.34 * q.y, 0.94 * q.y - 0.34 * q.x, q.z);
    q = vec3(c0 * q.x - s0 * q.z, q.y, s0 * q.x + c0 * q.z);
    float r = length(q.xz), rr = length(q);
    float w = atan(q.z, q.x);
    float phase = 2.0 * w - log(r + 0.035) * 4.3 + uZeit * 0.2;
    float arm = pow(0.5 + 0.5 * sin(phase), 3.4);
    float nb = 0.5 + 0.5 * (0.7 * snoise(q * 4.6 + vec3(0.0, uZeit * 0.1, 0.0)) + 0.3 * snoise(q * 11.0 - vec3(uZeit * 0.07, 0.0, 0.0)));
    float scheibe = exp(-q.y * q.y * mix(70.0, 18.0, uSpirale)) * smoothstep(RK, RK * 0.45, r);
    float bulge = exp(-rr * rr * 30.0);
    float herz = exp(-rr * rr * 320.0);
    float staub = pow(0.5 + 0.5 * sin(phase - 1.25), 7.0) * scheibe * smoothstep(0.05, 0.22, r);
    float knoten = pow(max(snoise(q * 15.0 + vec3(uZeit * 0.05)), 0.0), 3.0) * arm * scheibe;
    float neb = scheibe * (0.025 + arm * (0.25 + 1.1 * nb * nb)) + bulge * 0.3;
    float k = clamp(r / RK, 0.0, 1.0);
    vec3 farbe = mix(vec3(1.0, 0.70, 0.38), vec3(1.0, 0.22, 0.62), smoothstep(0.06, 0.34, k));
    farbe = mix(farbe, vec3(0.48, 0.22, 1.0), smoothstep(0.34, 0.68, k));
    farbe = mix(farbe, vec3(0.12, 0.80, 1.0), smoothstep(0.62, 0.98, k) * (0.4 + 0.6 * nb));
    vec3 em = farbe * neb * (3.0 + uTiefe * 2.8 + uSpirale * 1.5 + uPegel * 0.8) + vec3(1.0, 0.92, 0.82) * herz * (3.5 + uPegel * 2.5) + vec3(1.0, 0.55, 0.85) * knoten * (9.0 + uPegel * 3.0);
    float dichte = neb * 2.4 + staub * 10.0 + herz * 3.0;
    summe += T * em * st;
    T *= exp(-dichte * st * 1.5);
  }
  deckung = 1.0 - T;
  return summe + schein * T;
}
void main(){
  vec3 V = normalize(cameraPosition - vPosW);
  vec3 N = normalize(vNormW);
  float cosI = clamp(dot(N, V), 0.0, 1.0);
  float fres = 0.04 + 0.96 * pow(1.0 - cosI, 5.0);
  float rand = pow(1.0 - cosI, 1.8);

  float t = uFilmZeit;
  float d = filmDicke(vPosO, t) + uPegel * 16.0 * sin(t * 0.9 + vPosO.y * 1.6);
  vec3 film = duennschicht(d, cosI);
  vec3 col = edel(film);
  // untere Bänder etwas zurücknehmen (sonst neonhaft), gläserner statt glühend
  float unten = smoothstep(-0.05, -0.85, vPosO.y);
  col = mix(vec3(dot(col, vec3(0.2126, 0.7152, 0.0722))), col, 1.0 - 0.22 * unten);
  vec3 bunt = satt(film, 0.75 + uLadung * 0.2);
  if (uComic > 0.5) {
    // ruhige Comic-Fläche: grobe Filmfarbe (nur das Schwerkraftgefälle), wenige Farbstufen
    // Zellschattierung: eine schillernde Grundfarbe (Magenta, Violett, Türkis), drei Lichtstufen
    float gc = clamp(0.5 - 0.5 * vPosO.y, 0.0, 1.0);
    vec3 grob = satt(duennschichtGrob(mix(330.0, 470.0, gc) + 35.0 * sin(t * 0.2 + vPosO.x * 1.2), 0.8), 0.85);
    vec3 ton = grob / max(max(max(grob.r, grob.g), grob.b), 1e-3);
    float lam = dot(N, normalize(vec3(-0.45, 0.6, 0.66))) * 0.5 + 0.5;
    float stufe = lam > 0.72 ? 1.0 : lam > 0.42 ? 0.62 : 0.3;
    bunt = ton * stufe * 1.15;
    col = bunt;
  }

  vec3 R = reflect(-V, N);
  vec3 env = umgebung(R);
  vec3 L1 = normalize(vec3(-0.45, 0.6, 0.66)), L2 = normalize(vec3(0.9, 0.1, 0.42));
  float glanz = pow(max(dot(R, L1), 0.0), 420.0) * 5.0 + pow(max(dot(R, L2), 0.0), 220.0) * 0.7;

  // Vorderseite: Die Seifenhaut spiegelt die Umgebung in ihren Interferenzfarben, dazu ein Schimmer
  // aus Raumlicht, der zum Rand zunimmt. In der Mitte bleibt die Haut fast durchsichtig.
  float envL = dot(env, vec3(0.3, 0.59, 0.11));
  vec3 vorn = env * mix(col, vec3(1.0), 0.15 + 0.55 * smoothstep(0.6, 2.5, envL)) * (0.05 + 1.7 * fres) + mix(col, col * col, 0.5) * (0.004 + 0.6 * pow(1.0 - cosI, 2.6)) * (1.0 + uLadung * 0.4);

  // Rückseite der Blase, durch die Vorderseite gesehen: eine zweite, gegenläufig fließende Farbschicht.
  vec3 ein = normalize(vPosO);
  vec3 rd0 = normalize(vPosO - uKameraO);
  vec3 P2 = ein + rd0 * max(-2.0 * dot(ein, rd0), 0.0);
  float cos2 = clamp(dot(P2, rd0), 0.0, 1.0);
  vec3 film2 = edel(duennschichtGrob(filmDicke(P2, t), cos2));
  float fres2 = 0.04 + 0.96 * pow(1.0 - cos2, 5.0);
  vec3 env2 = umgebungWeich(normalize(uObjZuWelt * reflect(rd0, -P2)));
  vec3 hinten = (env2 * film2 * (0.10 + 1.3 * fres2) + film2 * (0.005 + 0.28 * pow(1.0 - cos2, 1.8))) * 0.35;

  // Kern: Sicht ins Innere leicht gebrochen (Objektraum)
  vec3 rd = refract(rd0, normalize(vNormO), 1.0 / 1.06);
  float deckung;
  vec3 innen = kern(ein * 0.999, normalize(rd), deckung);

  vec3 durch = (hinten * (1.0 - deckung) + innen) * (1.0 - fres * 0.85);
  vec3 farbe = durch * (1.0 - uSchwarz * 0.94) + vorn;
  farbe += vec3(glanz) * mix(vec3(1.0), col, 0.25);

  // „zeigen“: schwarze Kugel, nur die Ölhaut am Rand und die Spiegelungen schillern
  vec3 schwarz = col * rand * 1.3 + env * col * (0.12 + 1.7 * fres) * 0.8 + vec3(glanz) * 0.6;
  farbe = mix(farbe, schwarz, uSchwarz);

  // Aufladen (Erledigt): Energieadern und Rand in gesättigten Bandfarben, schneller Fluss, kein Weiß
  if (uLadung > 0.01) {
    float a1 = 1.0 - smoothstep(0.0, 0.06, abs(snoise(vPosO * 3.2 + vec3(0.0, uZeit * 1.7, uZeit * 0.6))));
    float a2 = 1.0 - smoothstep(0.0, 0.04, abs(snoise(vPosO * 6.5 - vec3(uZeit * 2.3, 0.0, 0.0))));
    float adern = (a1 + a2 * 0.6) * smoothstep(-0.2, 0.5, snoise(vPosO * 1.3 + vec3(uZeit * 0.8)));
    vec3 glut = satt(film, 1.0) * 0.6; // reine Bandfarbe, ohne Grauanteil
    farbe = farbe * (1.0 - 0.3 * uLadung) + glut * (0.9 * adern + 1.2 * rand) * uLadung;
  }

  if (uComic > 0.5) {
    // Comic: flache Zellfarbe statt Seifenhaut, der Kern scheint gedämpft durch, Glanzpunkt bleibt
    farbe = bunt * 0.8 + innen * 0.45 + vec3(step(0.5, glanz)) * 0.9;
    float hl = dot(farbe, vec3(0.333));
    vec2 zelle = fract(mat2(0.7071, -0.7071, 0.7071, 0.7071) * gl_FragCoord.xy / 6.0) - 0.5;
    // Halbton nur im Schatten (zum Rand und unten), nicht über die ganze Kugel
    float schatten = smoothstep(0.55, 0.15, cosI) * (0.6 + 0.4 * smoothstep(0.2, -0.7, vPosO.y));
    float punkt = step(length(zelle), 0.45 * schatten);
    farbe = mix(farbe, farbe * 0.3, punkt * 0.85);
    farbe *= smoothstep(0.07, 0.16, cosI);
  }

  // geschwächt: entsättigt, gedimmt, flackernd
  float l = dot(farbe, vec3(0.299, 0.587, 0.114));
  farbe = mix(vec3(l), farbe, uSaett);
  float flackern = 1.0 - uFlacker * (0.35 + 0.35 * step(0.6, snoise(vec3(uZeit * 6.0, 0.0, 0.0))));
  farbe *= uHell * flackern;
  // weiche Obergrenze gegen Ausbrennen (Farbe bleibt erhalten)
  farbe = farbe / (1.0 + max(max(farbe.r, farbe.g), farbe.b) * 0.12);

  float alpha = clamp(0.03 + fres * 0.85 + deckung * 0.9 + rand * 0.18 + uSchwarz * 0.9, 0.0, 1.0);
  if (uComic > 0.5) alpha = max(alpha, 0.9);
  gl_FragColor = vec4(farbe, alpha); // vormultipliziert: Farbe wird addiert, Alpha deckt den Hintergrund ab
}`;

const HALO_VS = /* glsl */`varying vec2 vUv; void main(){ vUv = uv; gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }`;
// Halo: rund, weich und ohne Strahlen. Die Farbe folgt nur dem groben Schwerkraftgefälle des Films am Rand
// (oben silbern-gold, unten magenta-blau) und wandert langsam; keine feinen Bänder, die als Strahlen erscheinen.
const HALO_FS = /* glsl */`
uniform float uZeit, uStaerke, uSaett, uPegel, uComic, uLadung, uFilmZeit, uLinien;
uniform mat3 uRandZuO;
varying vec2 vUv;
${RAUSCHEN}
${FILM}
float hash11(float p){ p = fract(p * 0.1031); p *= p + 33.33; p *= p + p; return fract(p); }
void main(){
  vec2 p = vUv * 2.0 - 1.0;
  float r = length(p);
  float innen = 1.0 / 3.0; // Kugelrand im Halo-Maßstab (Ebene 6 x 6, Kugel Radius 1)
  float aussen = r - innen;
  if (aussen < -0.03 || aussen > 0.5) discard;
  float w = atan(p.y, p.x);
  vec3 q = normalize(uRandZuO * vec3(cos(w), sin(w), 0.0));
  float g = clamp(0.5 - 0.5 * q.y, 0.0, 1.0);
  float dk = mix(260.0, 560.0, g) + 70.0 * sin(uFilmZeit * 0.21 + q.x * 1.6 + q.z * 1.2);
  vec3 film = edel(duennschichtGrob(dk, 0.5));
  film = mix(vec3(0.78, 0.74, 1.0) * dot(film, vec3(0.3, 0.59, 0.11)), film, 0.6); // zur Hälfte lavendelweißes Licht
  vec3 c;
  if (uComic > 0.5) {
    vec3 fs = satt(duennschichtGrob(dk, 0.35), 0.8);
    float n = 56.0;
    float sek = floor((w / 6.28318 + 0.5) * n);
    float h = hash11(sek * 1.37 + floor(uZeit * 6.0) * 0.11);
    float lage = fract((w / 6.28318 + 0.5) * n) - 0.5;
    float start = 0.05 + 0.06 * hash11(sek + 3.1);
    float laenge = (0.03 + 0.06 * h) * (0.6 + uPegel * 1.4 + uLadung);
    float u = (aussen - start) / laenge;
    float strich = step(abs(lage), 0.16 * (1.0 - u)) * step(0.0, u) * step(u, 1.0) * step(0.55, h);
    float aura = floor(exp(-max(aussen, 0.0) * 16.0) * 2.0) / 2.0 * step(0.0, aussen);
    c = mix(vec3(1.0), fs, 0.45) * strich * 0.8 * max(uLinien, uLadung) + fs * aura * 0.22;
  } else {
    float a = max(aussen, 0.0);
    float saum = exp(-a * 40.0) * smoothstep(-0.03, 0.0, aussen);
    float weit = exp(-a * 9.0) * 0.022 + exp(-a * 3.5) * 0.007;
    c = film * (saum * 0.16 + weit) * (1.0 + uPegel * 0.3 + uLadung * 0.3);
  }
  float l = dot(c, vec3(0.3, 0.59, 0.11));
  c = mix(vec3(l), c, uSaett);
  gl_FragColor = vec4(c * uStaerke * smoothstep(0.5, 0.32, aussen), 1.0);
}`;

const PARTIKEL_VS = /* glsl */`
attribute vec4 aBahn;   // Radius, Startwinkel, Neigung, Tempo
attribute vec2 aExtra;  // Größe, Zufall
uniform float uZeit, uSpirale, uPegel, uPixel, uSammeln, uStreuen;
varying vec3 vFarbe; varying float vAlpha;
vec3 regenbogen(float t){ return 0.5 + 0.5 * cos(6.28318 * (t + vec3(0.0, 0.33, 0.67))); }
void main(){
  float zz = aExtra.y;
  float r = aBahn.x * (1.0 - uSammeln * 0.25) + uPegel * (0.06 + 0.03 * sin(uZeit * 1.7 + zz * 40.0)) + uStreuen * 2.5 * zz;
  float th = aBahn.y + uZeit * aBahn.w * (1.0 + uSpirale * 1.5);
  vec3 bahn = vec3(cos(th) * r, 0.0, sin(th) * r);
  float neig = aBahn.z;
  bahn = vec3(bahn.x, bahn.z * sin(neig), bahn.z * cos(neig));
  bahn += 0.05 * vec3(sin(uZeit * 0.7 + zz * 30.0), cos(uZeit * 0.9 + zz * 21.0), sin(uZeit * 0.5 + zz * 11.0));
  // Spiralarme (ES als gleißende Spirale)
  float arm = floor(zz * 3.0);
  float s = fract(zz * 7.31 + uZeit * 0.12 * aBahn.w);
  float w = arm * 2.0944 + s * 10.0 - uZeit * 1.6;
  float rs = 1.05 + s * 0.75;
  vec3 spirale = vec3(cos(w) * rs, (s - 0.5) * 1.6 * (1.0 - s * 0.3), sin(w) * rs);
  vec3 p = mix(bahn, spirale, uSpirale);
  vec4 mv = modelViewMatrix * vec4(p, 1.0);
  gl_Position = projectionMatrix * mv;
  gl_PointSize = aExtra.x * uPixel * (1.0 + uPegel * 0.5 + uSpirale * 0.4) / -mv.z;
  vFarbe = regenbogen(zz * 1.7 + uZeit * 0.05 + s * uSpirale);
  vAlpha = (0.35 + 0.65 * fract(zz * 13.7 + uZeit * 0.3)) * (0.6 + 0.4 * sin(uZeit * 3.0 + zz * 50.0));
}`;
const PARTIKEL_FS = /* glsl */`
uniform float uHell, uSaett, uComic, uDeckung, uLadung;
varying vec3 vFarbe; varying float vAlpha;
void main(){
  vec2 p = gl_PointCoord * 2.0 - 1.0;
  float d = length(p);
  float a = exp(-d * d * 5.0) + 0.5 * exp(-abs(p.x) * 18.0) * exp(-abs(p.y) * 3.0) + 0.5 * exp(-abs(p.y) * 18.0) * exp(-abs(p.x) * 3.0);
  if (uComic > 0.5) a = step(abs(p.x) + abs(p.y), 0.6) + step(d, 0.25);
  vec3 c = mix(vec3(1.0), vFarbe, 0.4 + 0.55 * uLadung); // silbern, beim Aufladen farbig
  float l = dot(c, vec3(0.3, 0.59, 0.11));
  c = mix(vec3(l), c, uSaett);
  gl_FragColor = vec4(c * a * vAlpha * uHell * uDeckung * 0.85, 1.0);
}`;

// Denken: weiche Lichtbänder (dicht gesetzte, weiche Punkte), drei außen, zwei durch das Innere
const SPIRALE_VS = /* glsl */`
attribute float aT; attribute float aArm;
uniform float uZeit, uPixel, uPegel;
varying float vT; varying float vArm; varying float vInnen;
void main(){
  float t = aT;
  float innen = step(2.5, aArm);
  float w = t * mix(18.85, 12.0, innen) + uZeit * mix(2.4, -3.2, innen) + aArm * 2.0944;
  float y = (t - 0.5) * mix(2.9, 1.5, innen);
  float r = mix(1.2 * sqrt(max(0.0, 1.0 - pow((t - 0.5) * 1.55, 2.0))) + 0.2, 0.18 + 0.5 * sin(t * 3.14159), innen)
          + 0.04 * sin(t * 40.0 + uZeit * 5.0);
  vec3 p = vec3(cos(w) * r, y, sin(w) * r);
  vec4 mv = modelViewMatrix * vec4(p, 1.0);
  gl_Position = projectionMatrix * mv;
  gl_PointSize = uPixel * (1.0 + uPegel * 0.5) * (0.6 + 0.8 * sin(t * 3.14159)) * mix(1.0, 0.8, innen) / -mv.z;
  vT = t; vArm = aArm; vInnen = innen;
}`;
const SPIRALE_FS = /* glsl */`
uniform float uDeckung, uZeit, uComic;
varying float vT; varying float vArm; varying float vInnen;
vec3 regenbogen(float t){ return 0.5 + 0.5 * cos(6.28318 * (t + vec3(0.0, 0.33, 0.67))); }
void main(){
  vec2 p = gl_PointCoord * 2.0 - 1.0;
  float a = exp(-dot(p, p) * 3.0);
  if (uComic > 0.5) a = step(dot(p, p), 0.3);
  // Lichtpulse laufen das Band entlang, mit Nachleuchten
  float zug = pow(fract(vT * 2.0 - uZeit * 0.8 + vArm * 0.37), 5.0);
  vec3 farbe = regenbogen(vT * 0.8 + vArm * 0.21 + uZeit * 0.08);
  farbe = farbe * farbe * 1.3;
  vec3 c = mix(farbe, vec3(1.0), zug * 0.3) * (0.022 + zug * 0.14) * mix(1.0, 0.7, vInnen);
  gl_FragColor = vec4(c * a * uDeckung * sin(vT * 3.14159), 1.0);
}`;

export class Kugel {
  constructor(szene, { partikel = 2600 } = {}) {
    this.gruppe = new THREE.Group();
    this.gruppe.name = "harno";
    szene.add(this.gruppe);
    this.inneres = new THREE.Group(); // dreht sich langsam, enthält Partikel und Spiralen
    this.gruppe.add(this.inneres);

    const gemeinsam = { uZeit: { value: 0 }, uPegel: { value: 0 }, uFilmZeit: { value: 0 }, uSpek: { value: SPEKTRUM } };
    this.u = {
      ...gemeinsam, uVerformung: { value: 0.35 }, uStreckung: { value: 0 }, uSaett: { value: 1 }, uHell: { value: 1 },
      uFlacker: { value: 0 }, uSpirale: { value: 0 }, uSchwarz: { value: 0 }, uLadung: { value: 0 }, uComic: { value: 0 },
      uSchritte: { value: 14 }, uFarbtempo: { value: 1 }, uTiefe: { value: 0.5 }, uKameraO: { value: new THREE.Vector3(0, 0, 10) },
      uObjZuWelt: { value: new THREE.Matrix3() },
    };
    this.huelle = new THREE.Mesh(new THREE.SphereGeometry(1, 192, 144), new THREE.ShaderMaterial({
      uniforms: this.u, vertexShader: HUELLE_VS, fragmentShader: HUELLE_FS, transparent: true, depthWrite: false,
      blending: THREE.CustomBlending, blendSrc: THREE.OneFactor, blendDst: THREE.OneMinusSrcAlphaFactor,
      blendSrcAlpha: THREE.OneFactor, blendDstAlpha: THREE.OneMinusSrcAlphaFactor,
    }));
    this.huelle.renderOrder = 3;
    this.gruppe.add(this.huelle);

    // Comic-Kontur: Rückseite etwas größer, schwarz (Tuschelinie)
    this.kontur = new THREE.Mesh(new THREE.SphereGeometry(1.07, 96, 72),
      new THREE.MeshBasicMaterial({ color: 0x000000, side: THREE.BackSide }));
    this.kontur.renderOrder = 1;
    this.kontur.visible = false;
    this.gruppe.add(this.kontur);

    this.haloU = { uZeit: gemeinsam.uZeit, uFilmZeit: gemeinsam.uFilmZeit, uSpek: gemeinsam.uSpek, uStaerke: { value: 1 }, uSaett: this.u.uSaett,
      uPegel: gemeinsam.uPegel, uComic: this.u.uComic, uLadung: this.u.uLadung, uLinien: { value: 0 }, uRandZuO: { value: new THREE.Matrix3() } };
    this.halo = new THREE.Mesh(new THREE.PlaneGeometry(6, 6), new THREE.ShaderMaterial({
      uniforms: this.haloU, vertexShader: HALO_VS, fragmentShader: HALO_FS, transparent: true,
      blending: THREE.AdditiveBlending, depthWrite: false,
    }));
    this.halo.renderOrder = 0;
    this.gruppe.add(this.halo);

    this.partikelU = { uZeit: gemeinsam.uZeit, uPegel: gemeinsam.uPegel, uSpirale: this.u.uSpirale, uPixel: { value: 300 },
      uHell: this.u.uHell, uSaett: this.u.uSaett, uComic: this.u.uComic, uDeckung: { value: 1 }, uSammeln: { value: 0 }, uStreuen: { value: 0 }, uLadung: this.u.uLadung };
    this._baueKleinteile(partikel);

    this.spiraleU = { uZeit: gemeinsam.uZeit, uPixel: { value: 90 }, uPegel: gemeinsam.uPegel, uDeckung: { value: 0 }, uComic: this.u.uComic };
    const proArm = 1800, arme = 5, n = proArm * arme, t = new Float32Array(n), arm = new Float32Array(n);
    for (let i = 0; i < n; i++) { t[i] = (i % proArm) / proArm; arm[i] = Math.floor(i / proArm); }
    const g = new THREE.BufferGeometry();
    g.setAttribute("position", new THREE.BufferAttribute(new Float32Array(n * 3), 3));
    g.setAttribute("aT", new THREE.BufferAttribute(t, 1));
    g.setAttribute("aArm", new THREE.BufferAttribute(arm, 1));
    g.boundingSphere = new THREE.Sphere(new THREE.Vector3(), 3);
    this.spiralen = new THREE.Points(g, new THREE.ShaderMaterial({
      uniforms: this.spiraleU, vertexShader: SPIRALE_VS, fragmentShader: SPIRALE_FS, transparent: true,
      blending: THREE.AdditiveBlending, depthWrite: false,
    }));
    this.spiralen.renderOrder = 4;
    this.inneres.add(this.spiralen);

    this._inv = new THREE.Matrix4();
    this._m3 = new THREE.Matrix3();
    this._k3 = new THREE.Matrix3();
    this.filmZeit = 0;
    this.radius = 1.55;
  }

  _baueKleinteile(anzahl) {
    if (this.partikel) { this.inneres.remove(this.partikel); this.partikel.geometry.dispose(); }
    const bahn = new Float32Array(anzahl * 4), extra = new Float32Array(anzahl * 2);
    for (let i = 0; i < anzahl; i++) {
      const nah = Math.random() < 0.6;
      bahn[i * 4] = nah ? 1.08 + Math.random() ** 2 * 0.5 : 1.4 + Math.random() * 1.4;
      bahn[i * 4 + 1] = Math.random() * Math.PI * 2;
      bahn[i * 4 + 2] = (Math.random() - 0.5) * Math.PI;
      bahn[i * 4 + 3] = (0.08 + Math.random() * 0.35) * (Math.random() < 0.5 ? -1 : 1);
      extra[i * 2] = 0.5 + Math.random() ** 3 * 3.2;
      extra[i * 2 + 1] = Math.random();
    }
    const g = new THREE.BufferGeometry();
    g.setAttribute("position", new THREE.BufferAttribute(new Float32Array(anzahl * 3), 3));
    g.setAttribute("aBahn", new THREE.BufferAttribute(bahn, 4));
    g.setAttribute("aExtra", new THREE.BufferAttribute(extra, 2));
    g.boundingSphere = new THREE.Sphere(new THREE.Vector3(), 6);
    this.partikel = new THREE.Points(g, new THREE.ShaderMaterial({
      uniforms: this.partikelU, vertexShader: PARTIKEL_VS, fragmentShader: PARTIKEL_FS, transparent: true,
      blending: THREE.AdditiveBlending, depthWrite: false,
    }));
    this.partikel.renderOrder = 5;
    this.inneres.add(this.partikel);
  }

  qualitaet(p) {
    this.pr = Math.min(devicePixelRatio || 1, p.pixel); // Punktgrößen in echten Bildpunkten der Leinwand
    this.u.uSchritte.value = p.schritte;
    const ziel = Math.round(2600 * p.partikel);
    if (!this.partikel || this.partikel.geometry.attributes.aBahn.count !== ziel) this._baueKleinteile(ziel);
  }

  setzeStil(stil) {
    const comic = stil === "comic";
    this.u.uComic.value = comic ? 1 : 0;
    this.kontur.visible = comic;
  }

  // p: weich gemischte Zustandsparameter (siehe zustand.js); pegel 0..1
  update(dt, zeit, kamera, p, pegel) {
    this.u.uZeit.value = zeit;
    // Filmzeit läuft mit dem Zustandstempo, damit die Bänder beim Aufladen und Denken schneller fließen
    this.filmZeit += dt * (p.tempo + pegel * 0.9);
    this.u.uFilmZeit.value = this.filmZeit;
    this.u.uPegel.value = pegel;
    this.u.uVerformung.value = p.verformung;
    this.u.uSaett.value = p.saett;
    this.u.uHell.value = p.hell;
    this.u.uFlacker.value = p.flacker;
    this.u.uSpirale.value = p.spirale;
    this.u.uSchwarz.value = p.schwarz;
    this.u.uLadung.value = p.ladung;
    this.u.uFarbtempo.value = p.tempo;
    this.u.uTiefe.value = p.tiefe;
    this.u.uStreckung.value = p.streckung;
    this.haloU.uStaerke.value = p.halo;
    this.haloU.uLinien.value = p.pegel;
    this.partikelU.uDeckung.value = p.partikel;
    this.partikelU.uSammeln.value = p.sammeln;
    this.partikelU.uStreuen.value = p.streuen;
    this.spiraleU.uDeckung.value = p.spirale;
    const pr = this.pr || Math.min(devicePixelRatio || 1, 2);
    this.partikelU.uPixel.value = 3.2 * pr * (innerHeight / 900) * 10;
    this.spiraleU.uPixel.value = 13 * pr * (innerHeight / 900) * 10;
    this.inneres.rotation.y += dt * 0.08 * p.tempo;
    this.inneres.rotation.x = Math.sin(zeit * 0.1) * 0.15;
    this.huelle.rotation.y += dt * 0.05 * (1 + p.ladung * 3);
    this.gruppe.updateMatrixWorld();
    this._inv.copy(this.huelle.matrixWorld).invert();
    this.u.uKameraO.value.copy(kamera.position).applyMatrix4(this._inv);
    this.u.uObjZuWelt.value.setFromMatrix4(this.huelle.matrixWorld);
    this.halo.quaternion.copy(kamera.quaternion);
    this.halo.scale.setScalar(1);
    // Halo-Richtung (Bildebene der Kamera) in den Objektraum der Hülle
    this._k3.setFromMatrix4(kamera.matrixWorld);
    this._m3.setFromMatrix4(this._inv);
    this.haloU.uRandZuO.value.multiplyMatrices(this._m3, this._k3);
  }
}

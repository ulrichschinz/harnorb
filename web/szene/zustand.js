// Zustandsautomat der Kugel. Eingaben kommen aus dem Gespräch (Aufnahme, Zug, Vorlesen, Fehler) und der
// Szene (Karten zeigen, Fokus, Erledigt, Übergang). Der Zielzustand ergibt sich nach Vorrang; die
// Darstellungsparameter blenden weich dorthin über, statt hart umzuschalten.
import { naeher } from "./tween.js";

export const ZUSTAENDE = ["ruhe", "zuhoeren", "denken", "sprechen", "zeigen", "fokus", "erledigt", "geschwaecht", "uebergang"];

// Darstellungsparameter je Zustand. skala ist ein Faktor auf die Grundgröße der Ansicht.
const BASIS = { skala: 1, verformung: 0.35, saett: 1, hell: 1, flacker: 0, spirale: 0, schwarz: 0, ladung: 0, tempo: 1,
  tiefe: 0.5, halo: 0.68, partikel: 1, sammeln: 0, streuen: 0, streckung: 0, pegel: 0 };
export const PARAMETER = {
  ruhe: {},
  zuhoeren: { skala: 0.86, verformung: 0.18, halo: 0.8, sammeln: 1, tempo: 0.7, pegel: 1, tiefe: 0.7 },
  denken: { spirale: 1, tempo: 2.2, tiefe: 1, verformung: 0.5, halo: 1, partikel: 1.2 },
  sprechen: { pegel: 1, halo: 0.95, verformung: 0.2, tempo: 1.25, tiefe: 0.85 },
  zeigen: { schwarz: 1, halo: 0.6, tempo: 0.6, partikel: 0.6 },
  fokus: { tempo: 0.8, halo: 0.7 },
  erledigt: { ladung: 1, halo: 0.7, tempo: 3, verformung: 0.6, partikel: 0.9, sammeln: 1, tiefe: 0.35 },
  geschwaecht: { saett: 0.12, hell: 0.45, flacker: 1, tempo: 0.25, halo: 0.25, partikel: 0.25, verformung: 0.1 },
  uebergang: { streckung: 0.6, tempo: 3, halo: 1.3, streuen: 1 },
};

export class Automat {
  constructor() {
    this.e = { verbunden: true, fehlerBis: 0, aufnahme: false, erkennt: false, zug: false, spricht: false,
      zeigenBis: 0, fokus: false, erledigtBis: 0, uebergangBis: 0 };
    this.vorschau = null;   // Zustand fest vorgeben (Vorschau-Seite)
    this.p = { ...BASIS };
    this.name = "ruhe"; this.seit = performance.now();
    this.beiWechsel = [];
  }

  setze(k, v) { this.e[k] = v; }
  kurz(k, ms) { this.e[k] = performance.now() + ms; }

  ziel(jetzt = performance.now()) {
    if (this.vorschau) return this.vorschau;
    const e = this.e;
    if (jetzt < e.uebergangBis) return "uebergang";
    if (jetzt < e.erledigtBis) return "erledigt";
    if (!e.verbunden || jetzt < e.fehlerBis) return "geschwaecht";
    if (e.aufnahme) return "zuhoeren";
    if (jetzt < e.zeigenBis) return "zeigen";
    if (e.spricht) return "sprechen";
    if (e.zug || e.erkennt) return "denken";
    if (e.fokus) return "fokus";
    return "ruhe";
  }

  update(dt) {
    let z = this.ziel();
    const jetzt = performance.now();
    // Denken mindestens 600 ms zeigen, bevor Sprechen übernimmt (sonst ist es bei kurzen Zügen unsichtbar)
    if (this.name === "denken" && z === "sprechen" && jetzt - this.seit < 600) z = "denken";
    if (z !== this.name) this.seit = jetzt;
    if (z !== this.name) {
      const alt = this.name; this.name = z;
      for (const f of this.beiWechsel) f(z, alt);
    }
    const ziel = { ...BASIS, ...PARAMETER[z] };
    // schnelle Zustände blenden zügig, ruhige langsam
    const rate = z === "uebergang" || z === "erledigt" || z === "zuhoeren" ? 9 : z === "geschwaecht" ? 2.5 : 4;
    for (const k of Object.keys(BASIS)) this.p[k] = naeher(this.p[k], ziel[k], rate, dt);
    return this.p;
  }
}

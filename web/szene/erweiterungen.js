// Browser-Teil der Module: eigene Kartenarten und Erledigt-Effekte.
// Ein Modul mit web-Ordner liefert /modul/<name>/modul.js. Diese Datei exportiert
//   export default function registriere(harnorb) { … }
// und meldet darin an, was es mitbringt. `harnorb` ist die Schnittstelle unten (Version API_VERSION).
// Erhöht wird die Version nur, wenn sich etwas Bestehendes ändert; neue Felder kommen ohne Sprung dazu.
//
//   harnorb.kartenArt(name, { karte(el, k, hilfe), fokus?(el, k, hilfe), klasse? })
//       Zeichnet eine Karte selbst. Gilt für Karten, deren anzeige.art = name ist.
//       el: das Kartenelement (Größe, Klick und Bewegung übernimmt der Kern; transform, transform-origin,
//       position und opacity von el nicht anfassen, sonst stimmt die 3D-Platzierung nicht), k: die Karte vom Server
//       (titel, projekt, faellig, tags, anzeige.daten …), hilfe: { esc, meta(k), md }.
//   harnorb.effekt(name, async ({ k, el, eintrag, fx, kugelPos, THREE, tween, ease, warte }) => { … })
//       Erledigt-Effekt für Karten mit anzeige.effekt = name. eintrag.basis (Ort), eintrag.rot,
//       eintrag.skala, eintrag.op (Deckkraft) darf der Effekt animieren; danach entfernt der Kern die Karte.
//   harnorb.fx       Effekte des Kerns: strahlZwischen(a, b, staerke), funken(ort, n), portalAuf(), portalZu(),
//                  portalOrt(), hyperraum(ms), ton.{auf, zu, zap, laden, whoosh}
//   harnorb.stil(css) hängt Stylesheet-Text an, harnorb.stilDatei(pfad) eine CSS-Datei aus dem web-Ordner,
//   harnorb.modul ist der Modulname,
//   harnorb.url(pfad) die Adresse einer Datei im eigenen web-Ordner.
import * as THREE from "three";
import { tween, ease, warte } from "./tween.js";

export const API_VERSION = 1;
export const kartenArten = new Map();   // name -> { karte, fokus, klasse, modul }
export const effekte = new Map();       // name -> { fn, modul }
export const geladen = [];              // { name, ok, fehler }

export function schnittstelle(modul, fx) {
  return {
    version: API_VERSION, modul, fx, THREE, tween, ease, warte,
    url: (pfad) => `/modul/${encodeURIComponent(modul)}/${String(pfad).replace(/^\/+/, "")}`,
    kartenArt(name, def) {
      if (!def || typeof def.karte !== "function") throw new Error(`kartenArt ${name}: karte(el, k, hilfe) fehlt`);
      kartenArten.set(String(name).toLowerCase(), { ...def, modul });
    },
    effekt(name, fn) {
      if (typeof fn !== "function") throw new Error(`effekt ${name}: Funktion fehlt`);
      effekte.set(String(name).toLowerCase(), { fn, modul });
    },
    stil(css) { // als Constructable Stylesheet, das erlaubt die CSP ohne 'unsafe-inline'
      const blatt = new CSSStyleSheet();
      blatt.replaceSync(String(css));
      document.adoptedStyleSheets = [...document.adoptedStyleSheets, blatt];
    },
    stilDatei(pfad) {
      const l = document.createElement("link");
      l.rel = "stylesheet"; l.href = this.url(pfad); l.dataset.modul = modul;
      document.head.appendChild(l);
    },
  };
}

// Lädt alle modul.js, die der Server meldet. Ein kaputtes Modul hält die anderen nicht auf.
export async function ladeModule(fx, liste) {
  if (!liste) {
    try { liste = (await (await fetch("/api/status")).json()).modul_web || []; } catch (_) { return geladen; }
  }
  for (const { name, url } of liste) {
    try {
      const m = await import(url);
      const fn = m.default || m.registriere;
      if (typeof fn !== "function") throw new Error("modul.js exportiert keine Funktion registriere");
      await fn(schnittstelle(name, fx));
      geladen.push({ name, ok: true });
    } catch (e) {
      console.warn(`Modul ${name}:`, e);
      geladen.push({ name, ok: false, fehler: String(e?.message || e) });
    }
  }
  return geladen;
}

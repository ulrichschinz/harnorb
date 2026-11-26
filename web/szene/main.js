// HarnoRb: leere 3D-Szene, Gespräch mit der Kugel, Inhalte nur auf Zuruf.
import * as THREE from "three";
import { Buehne } from "./buehne.js";
import { Kugel } from "./kugel.js";
import { Hintergrund } from "./hintergrund.js";
import { Effekte } from "./effekte.js";
import { Karten } from "./karten.js";
import { Automat, ZUSTAENDE } from "./zustand.js";
import { Gespraech, api } from "./gespraech.js";
import { naeher, warte } from "./tween.js";
import { ladeModule, geladen as modulWeb, kartenArten, effekte } from "./erweiterungen.js";

const $ = (s) => document.querySelector(s);
const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const VORSCHAU = document.body.hasAttribute("data-vorschau");
const reduziert = matchMedia("(prefers-reduced-motion: reduce)").matches;
const merke = (k, v) => { try { localStorage.setItem(k, v); } catch (_) { /* egal */ } };
const lies = (k, d) => { try { return localStorage.getItem(k) ?? d; } catch (_) { return d; } };

// ---------- Aufbau ----------
const buehne = new Buehne($("#buehne"), { reduziert });
const hintergrund = new Hintergrund(buehne.szene);
const kugel = new Kugel(buehne.szene);
const fx = new Effekte(buehne);
const automat = new Automat();
const ort = { pos: new THREE.Vector3(0, 0.1, 0), r: 1.55, zielPos: new THREE.Vector3(0, 0.1, 0), zielR: 1.55 };
// Zielort der Kugel für die aktuelle Ansicht (frisch berechnet, damit das Kartenlayout nicht vom Vorbild abhängt)
let kartenBereit = false;
const kugelOrt = () => { if (kartenBereit) kugelLayout(); return { pos: ort.zielPos.clone(), r: ort.zielR }; };
const karten = new Karten(buehne, kugelOrt, fx, {
  klick: (k, ev) => klickAufKarte(k, ev), option: (t) => frage(t), ton: fx.ton,
});
// Browser-Teile der Module (eigene Kartenarten, Effekte); danach Sichtbares neu zeichnen
if (!VORSCHAU) ladeModule(fx).then(() => { if (kartenArten.size && szenenZustand) karten.neuZeichnen(); });
kartenBereit = true;
buehne.beiStufe.push((p) => { kugel.qualitaet(p); hintergrund.qualitaet(p); });
kugel.qualitaet(buehne.params); hintergrund.qualitaet(buehne.params);

let szenenZustand = { ansicht: "leer", karten: [], gewaehlt: null, fokus: null, text: null, optionen: null, stil: "leuchtend", hintergrund: "mond" };
let stil = "leuchtend";

function setzeStil(s, h, { sofort = false } = {}) {
  if (s && s !== stil) {
    stil = s;
    kugel.setzeStil(s); hintergrund.setzeStil(s);
    document.body.dataset.stil = s;
    buehne.bloomZiel = s === "comic" ? 0.3 : 0.5;
    buehne.finish.uniforms.uComic.value = s === "comic" ? 1 : 0;
  }
  if (h) hintergrund.setzeArt(h, sofort);
}

// Grundort und -größe der Kugel je Ansicht
function kugelLayout() {
  const s = buehne.sichtbar(0), breit = s.b / s.h > 1.05;
  const a = karten.ansicht;
  if (a === "fokus" || a === "text") {
    ort.zielR = 0.5; ort.zielPos.set(s.b / 2 - 1.25, s.h / 2 - 1.2, -0.2);
  } else if (a === "liste" || a === "optionen") {
    if (breit) { ort.zielR = 1.05; ort.zielPos.set(0, a === "optionen" && !karten.liste.size ? 0.5 : 0, -0.4); }
    else { ort.zielR = 0.75; ort.zielPos.set(0, s.h / 2 - 1.35, -0.4); }
  } else {
    ort.zielR = breit ? 1.55 : 1.25; ort.zielPos.set(0, 0.1, 0);
  }
}

// ---------- Bildschleife ----------
const FARBEN = { ruhe: "#9db8ff", zuhoeren: "#ff7a59", denken: "#c38bff", sprechen: "#68e0c0", zeigen: "#e6e6e6", fokus: "#9db8ff", erledigt: "#ffe08a", geschwaecht: "#777", uebergang: "#8fd3ff" };
let pegelGlatt = 0;
buehne.jedesBild((dt, zeit) => {
  const p = automat.update(dt);
  const roh = automat.name === "zuhoeren" ? g.micPegel() : automat.name === "sprechen" ? g.pegel() : (VORSCHAU && automat.vorschau === "sprechen" ? demoPegel(zeit) : 0);
  // Pegel geglättet: Anstieg ca. 90 ms, Abfall ca. 140 ms, damit die Kugel atmet statt zu zittern
  const pz = roh * p.pegel;
  pegelGlatt = naeher(pegelGlatt, pz, pz > pegelGlatt ? 11 : 7, dt);
  kugelLayout();
  ort.pos.x = naeher(ort.pos.x, ort.zielPos.x, 3.2, dt);
  ort.pos.y = naeher(ort.pos.y, ort.zielPos.y, 3.2, dt);
  ort.pos.z = naeher(ort.pos.z, ort.zielPos.z, 3.2, dt);
  ort.r = naeher(ort.r, ort.zielR, 3.2, dt);
  const atmen = 1 + Math.sin(zeit * 1.1) * 0.012 * (reduziert ? 0 : 1) + pegelGlatt * 0.045;
  kugel.gruppe.position.copy(ort.pos);
  kugel.gruppe.scale.setScalar(ort.r * p.skala * atmen);
  kugel.update(dt, zeit, buehne.kamera, p, pegelGlatt);
  hintergrund.abseits(karten.ansicht !== "leer" && buehne.sichtbar(0).b / buehne.sichtbar(0).h > 1.05);
  hintergrund.update(dt, zeit, Math.max(0.15, p.saett), buehne.hyper);
  fx.update(dt, zeit);
  karten.update(dt, zeit);
  buehne.finish.uniforms.uSaett.value = 0.75 + 0.25 * p.saett;
  knopf.style.setProperty("--pegel", (automat.name === "zuhoeren" ? pegelGlatt : 0).toFixed(3));
  if (diagOffen && Math.floor(zeit * 4) !== diagTakt) { diagTakt = Math.floor(zeit * 4); zeigeDiagStatus(); }
  if (VORSCHAU) $("#vorschau-info").textContent = `${automat.name} · ${stil} · ${hintergrund.art} · ${buehne.fps.toFixed(0)} fps · ${buehne.stufe}`;
  window.__harno = { fps: buehne.fps, zustand: automat.name, stufe: buehne.stufe, ansicht: karten.ansicht, karten: karten.liste.size, stil, hintergrund: hintergrund.art };
});
automat.beiWechsel.push((z) => {
  document.body.dataset.zustand = z; zeigeStatusPunkt();
  // Zustandswechsel mit neuen Effekten (Denken-Bänder, Hyperraum, Laden) ruckeln kurz: nicht als Dauerlast werten
  if (z !== "ruhe" && z !== "fokus") buehne.pausiereMessung(2500);
});

// ---------- Gespräch ----------
const g = new Gespraech({
  verbindung: (an) => { automat.setze("verbunden", an); zeigeStatusPunkt(); if (!an) zeigeErlaubnisse([]); },
  verlauf: (m) => {
    diagLeeren();
    untertitelLeeren();
    if (m.szene) { setzeStil(m.szene.stil, m.szene.hintergrund, { sofort: true }); szenenZustand = m.szene; karten.anwende(m.szene, { sofort: true }); automat.setze("fokus", m.szene.ansicht === "fokus"); }
    anfragen.length = 0; anfragen.push(...(m.erlaubnisse || [])); zeigeErlaubnisse();
  },
  nachVerlauf: () => { automat.setze("zug", g.laeuft != null); },
  ereignis: (ev, nachspiel) => {
    diagEreignis(ev);
    switch (ev.typ) {
      case "zug_start": automat.setze("zug", true); untertitelNeu(); break;
      case "zug_ende": automat.setze("zug", false); if (ev.fehler && !nachspiel) fehler(ev.fehler); untertitelEnde(); break;
      case "text": if (!nachspiel) untertitel(ev.text); break;
      case "nutzer": if (!nachspiel) untertitelUli(ev.text); break;
      case "fehler": if (!nachspiel) fehler(ev.text); break;
      case "szene": if (!nachspiel) szenenEreignis(ev); break;
      case "schnellbefehl": if (!nachspiel) untertitelUli(ev.text); break;
    }
  },
  fluechtig: (m) => {
    switch (m.typ) {
      case "erkannt": automat.setze("erkennt", false); diagZeile("erkannt", m.text ? `„${m.text}“ (${m.sekunden} s)` : "nichts verstanden"); if (!m.text) toast("Nichts verstanden."); break;
      case "fehler": fehler(m.text); break;
      case "erlaubnis": anfragen.push(m); zeigeErlaubnisse(); break;
      case "erlaubnis_erledigt": { const i = anfragen.findIndex((a) => a.id === m.id); if (i >= 0) anfragen.splice(i, 1); zeigeErlaubnisse(); break; }
      case "neu": diagLeeren(); toast("Neues Gespräch."); automat.setze("zug", false); break;
      case "vorleser": zeigeVorleser(m.art); break;
      case "stimmen": pruefeStatus(); break;
      case "leser": leserEreignis(m); break;
      case "einstellung": wendeEinstellung(m.name, m.wert); break;
    }
  },
  audioStart: () => automat.setze("spricht", true),
  audioEnde: () => automat.setze("spricht", false),
  aufnahme: (an) => { automat.setze("aufnahme", an); knopf.classList.toggle("an", an); if (!an && g.erkennt) automat.setze("erkennt", true); zeigeKnopfText(); },
  brauchtGeste: () => toast("Zum Vorlesen einmal klicken oder die Leertaste drücken."),
});

function frage(text) {
  if (!g.frage(text)) { toast("Keine Verbindung zum Server."); return false; }
  return true;
}

// ---------- Szenen-Ereignisse (mit Animation, nacheinander) ----------
let kette = Promise.resolve();
function szenenEreignis(ev) {
  if (["waehle", "fokus", "ausblenden", "erledigt"].includes(ev.aktion)) lokalGewaehlt = 0; // Server hat übernommen
  // Hängt eine Animation (z. B. ein Tween, der nie fertig wird), darf sie die folgenden Befehle nicht blockieren.
  const grenze = new Promise((r) => setTimeout(() => r("zeitueberschreitung"), 6000));
  kette = kette.then(() => Promise.race([spieleSzene(ev), grenze])).then((x) => {
    if (x === "zeitueberschreitung") { console.warn("Szene hing:", ev.aktion); diagZeile("fehler", "Animation hing: " + ev.aktion); setzeStil(ev.zustand.stil, ev.zustand.hintergrund); }
  }).catch((e) => console.error(e));
}

async function spieleSzene(ev) {
  const z = ev.zustand, vorher = szenenZustand;
  szenenZustand = z;
  buehne.pausiereMessung(2500); // Karten bauen und einfliegen: kurze Last, kein Grund zum Absenken
  automat.setze("fokus", z.ansicht === "fokus");
  switch (ev.aktion) {
    case "liste": {
      const wechsel = vorher.ansicht !== "leer" && (vorher.liste !== z.liste || vorher.ansicht !== "liste");
      karten.vorbereiten("liste");
      if (wechsel) { automat.kurz("uebergangBis", 700); const h = fx.hyperraum(800); await warte(280); karten.anwende(z); await h; }
      else { fx.ton.auf(); automat.kurz("zeigenBis", 1500); await warte(250); karten.anwende(z); }
      break;
    }
    case "fokus":
      karten.vorbereiten("fokus");
      automat.kurz("uebergangBis", 650);
      fx.hyperraum(750);
      await warte(200);
      karten.anwende(z);
      break;
    case "erledigt": {
      schliesseToasts("frage");
      buehne.pausiereMessung(4000);
      automat.kurz("erledigtBis", 1900);
      fx.ton.laden();
      await warte(reduziert ? 100 : 650);
      await karten.erledigtFlug(ev.karte, () => kugel.gruppe.position.clone());
      karten.vorbereiten("erledigt");
      karten.anwende(z);
      break;
    }
    case "ausblenden":
      fx.ton.zu();
      karten.vorbereiten("ausblenden");
      karten.anwende(z);
      break;
    case "text":
    case "optionen":
      fx.ton.auf();
      automat.kurz("zeigenBis", 1300);
      karten.vorbereiten(ev.aktion);
      karten.anwende(z);
      break;
    case "stil":
      if (z.stil !== stil) { automat.kurz("uebergangBis", 500); fx.hyperraum(600); await warte(250); }
      setzeStil(z.stil, z.hintergrund);
      break;
    default:
      karten.vorbereiten(ev.aktion);
      karten.anwende(z);
  }
}

function klickAufKarte(k) {
  if (k.option) return frage(k.titel);
  if (k.art === "projekt") return g.szene("zeige_liste", { art: "projekt:" + k.titel });
  if (szenenZustand.gewaehlt === k.nr) g.szene("fokus", { nummer: k.nr });
  else g.szene("waehle", { nummer: k.nr });
}

// ---------- Status, Fehler, Hinweise ----------
let fehlerZaehler = 0;
function fehler(text) {
  automat.kurz("fehlerBis", 3500);
  toast(text, "fehler");
  diagZeile("fehler", text);
  fehlerZaehler++;
}
function toast(text, art = "") {
  if (art === "frage") schliesseToasts("frage");
  const el = document.createElement("div");
  el.className = "toast " + art; el.textContent = text;
  $("#toasts").appendChild(el);
  requestAnimationFrame(() => el.classList.add("da"));
  setTimeout(() => { el.classList.remove("da"); setTimeout(() => el.remove(), 600); }, art === "fehler" ? 6000 : art === "frage" ? 2500 : 3200);
  return el;
}
function schliesseToasts(art) {
  for (const el of document.querySelectorAll("#toasts .toast." + art)) { el.classList.remove("da"); setTimeout(() => el.remove(), 400); }
}
let sprachBereit = false, statusInfo = {};
function zeigeStatusPunkt() {
  const p = $("#punkt");
  const ok = g.verbunden && sprachBereit;
  p.className = "punkt " + (!g.verbunden ? "fehler" : !sprachBereit ? "laedt" : automat.name);
  p.title = !g.verbunden ? "Keine Verbindung zum Server" : !sprachBereit ? "Sprachmodelle laden …" : `Bereit · ${automat.name}`;
  knopf.classList.toggle("bereit", ok);
}
async function pruefeStatus() {
  try {
    const s = await api("/api/status");
    statusInfo = s; sprachBereit = s.bereit;
    fuelleVorleser(s.stimmen); zeigeVorleser(s.vorleser); zeigeDienste(s.dienste);
    zeigeStatusPunkt();
    if (!s.bereit) setTimeout(pruefeStatus, 2000);
  } catch (_) { setTimeout(pruefeStatus, 3000); }
}

// ---------- Aktivierungsknopf (Sprechtaste) ----------
const knopf = $("#knopf");
let tippModus = false, druckBeginn = 0;
function zeigeKnopfText() {
  $("#knopf-text").textContent = g.nimmtAuf ? (tippModus ? "Ich höre … (tippen zum Senden)" : "Ich höre …")
    : automat.e.erkennt ? "Verstehe …" : "Leertaste halten";
}
// Audio beim ersten Kontakt vorwärmen (AudioContext und Effekttöne), damit der Mikrofonstart nicht ruckelt
for (const ev of ["pointerdown", "keydown"]) addEventListener(ev, () => { try { g.audio(); fx.ton._ctx?.(); } catch (_) { /* egal */ } }, { once: true, capture: true });
function sprechStart() {
  buehne.pausiereMessung(3000); // Mikrofonstart ruckelt kurz, das soll die Qualität nicht senken
  g.audio(); fx.ton._ctx?.();
  if (anfragen.length) return g.aufnahmeStart({ stoppen: false }); // Antwort auf die Erlaubnis-Tafel
  g.aufnahmeStart();
}
knopf.addEventListener("pointerdown", (e) => {
  e.preventDefault();
  if (tippModus && g.nimmtAuf) { tippModus = false; g.aufnahmeEnde(); return; }
  druckBeginn = performance.now(); sprechStart();
  knopf.setPointerCapture?.(e.pointerId);
});
knopf.addEventListener("pointerup", () => {
  if (tippModus) return;
  if (performance.now() - druckBeginn < 280) { tippModus = true; zeigeKnopfText(); return; } // kurz getippt: Aufnahme läuft weiter
  g.aufnahmeEnde();
});
knopf.addEventListener("pointercancel", () => { if (!tippModus) g.aufnahmeEnde(); });

// ---------- Tastatur ----------
const imFeld = (e) => ["INPUT", "TEXTAREA", "SELECT"].includes(e.target.tagName);
let erledigtScharf = 0;
let lokalGewaehlt = 0; // optimistisch: Zahl gedrückt, Server hat die Wahl noch nicht bestätigt
const gewaehlt = () => lokalGewaehlt || szenenZustand.gewaehlt;
const LISTEN_TASTEN = { a: "heute", i: "inbox", o: "ueberfaellig", w: "warten", p: "projekte", n: "naechste" };
document.addEventListener("keydown", (e) => {
  if (e.metaKey || e.ctrlKey || e.altKey) return;
  if (imFeld(e)) { if (e.key === "Escape") { e.target.blur(); schliesseEingabe(); } return; }
  const k = e.key.toLowerCase();
  if (VORSCHAU && vorschauTaste(e)) return;
  if (anfragen.length) { // Erlaubnis-Tafel hat Vorrang
    if (k === "j") { e.preventDefault(); beantworte(true); return; }
    if (k === "n" || e.key === "Escape") { e.preventDefault(); beantworte(false); return; }
  }
  if (e.code === "Space") { e.preventDefault(); if (!e.repeat) { tippModus = false; sprechStart(); } return; }
  if (e.repeat) return;
  if (e.key === "Escape") { if (!$("#hilfe").hidden) return zeigeHilfe(false); if (leserOffen) return schliesseLeser(); g.stoppe(); toast("Gestoppt."); return; }
  if (k === "u") return schalteUntertitel();
  if (k === "d") return schalteDiagnose();
  if (k === "k") return schalteKonfig();
  if (k === "l") return leserOffen ? schliesseLeser() : oeffneLeser("");
  if (k === "h" || e.key === "?") return zeigeHilfe($("#hilfe").hidden);
  if (k === "t" || e.key === "Enter" && !gewaehlt()) { e.preventDefault(); return oeffneEingabe(); }
  if (e.key === "Enter" && gewaehlt()) return g.szene("fokus", lokalGewaehlt ? { nummer: lokalGewaehlt } : {});
  if (LISTEN_TASTEN[k]) return g.szene("zeige_liste", { art: LISTEN_TASTEN[k] });
  if (k === "x" || e.key === "Backspace") return g.szene("ausblenden", {});
  if (/^[1-9]$/.test(e.key)) {
    if ((szenenZustand.karten || []).some((x) => x.nr === +e.key)) lokalGewaehlt = +e.key;
    return g.szene("waehle", { nummer: +e.key });
  }
  if (["ArrowDown", "ArrowRight", "ArrowUp", "ArrowLeft"].includes(e.key)) {
    const n = szenenZustand.karten?.length || 0; if (!n) return;
    const schritt = e.key === "ArrowDown" || e.key === "ArrowRight" ? 1 : -1;
    const jetzt = szenenZustand.gewaehlt || (schritt > 0 ? 0 : 1);
    e.preventDefault();
    return g.szene("waehle", { nummer: ((jetzt - 1 + schritt + n) % n) + 1 });
  }
  if (k === "e") {
    const ziel = szenenZustand.fokus || (szenenZustand.karten || []).find((x) => x.nr === gewaehlt());
    if (!ziel || ziel.art === "projekt") return toast("Erst eine Aufgabe wählen (Zahl) oder in den Fokus holen.");
    if (performance.now() - erledigtScharf < 2500) { erledigtScharf = 0; schliesseToasts("frage"); return g.szene("erledigt", szenenZustand.fokus ? {} : { nummer: ziel.nr }); }
    erledigtScharf = performance.now();
    return toast(`„${ziel.titel}“ erledigen? Noch einmal E drücken.`, "frage");
  }
  if (k === "g") return frage("Gib mir den Tagesüberblick.");
  if (k === "r") return frage("Lass uns die Inbox klären, Eintrag für Eintrag.");
  if (k === "s") return g.szene("stil", { stil: stil === "comic" ? "leuchtend" : "comic" });
  if (k === "b") return g.szene("stil", { hintergrund: hintergrund.art === "mond" ? "raumer" : "mond" });
  if (k === "m") { fx.ton.setze(!fx.ton.an); return toast(fx.ton.an ? "Effekttöne an." : "Effekttöne aus."); }
  if (k === "q") { const r = ["auto", "hoch", "mittel", "niedrig"]; const w = r[(r.indexOf(buehne.stufeWahl) + 1) % r.length]; buehne.waehleStufe(w); merke("harno-stufe", w); return toast("Qualität: " + w); }
  if (k === "f") { if (document.fullscreenElement) document.exitFullscreen(); else document.documentElement.requestFullscreen?.().catch(() => {}); }
});
document.addEventListener("keyup", (e) => {
  if (e.code === "Space" && !imFeld(e)) { e.preventDefault(); if (!tippModus) g.aufnahmeEnde(); }
});
addEventListener("blur", () => { if (!tippModus) g.aufnahmeEnde(); });

// ---------- Texteingabe (Notbedienung) ----------
function oeffneEingabe() { const f = $("#eingabe"); f.hidden = false; f.querySelector("input").focus(); }
function schliesseEingabe() { $("#eingabe").hidden = true; }
$("#eingabe").addEventListener("submit", (e) => {
  e.preventDefault(); const i = e.target.querySelector("input"); const t = i.value.trim();
  if (t && frage(t)) { i.value = ""; schliesseEingabe(); i.blur(); }
});

// ---------- Untertitel (U) ----------
let untertitelAn = lies("harno-untertitel", "aus") === "an";
let utText = "", utTimer = null;
function schalteUntertitel() { untertitelAn = !untertitelAn; merke("harno-untertitel", untertitelAn ? "an" : "aus"); $("#untertitel").hidden = !untertitelAn; toast(untertitelAn ? "Untertitel an." : "Untertitel aus."); }
function untertitelLeeren() { utText = ""; $("#ut-claude").textContent = ""; $("#ut-uli").textContent = ""; }
function untertitelNeu() { utText = ""; clearTimeout(utTimer); }
function untertitel(t) {
  utText += t; clearTimeout(utTimer);
  const satz = utText.replace(/\s+/g, " ").trim();
  $("#ut-claude").textContent = satz.length > 220 ? "… " + satz.slice(-220) : satz;
  $("#untertitel").classList.add("da");
}
function untertitelUli(t) { $("#ut-uli").textContent = t; $("#untertitel").classList.add("da"); }
function untertitelEnde() { clearTimeout(utTimer); utTimer = setTimeout(() => { $("#untertitel").classList.remove("da"); }, 6000); }
$("#untertitel").hidden = !untertitelAn;

// ---------- Diagnose (D) ----------
let diagOffen = false, diagTakt = -1;
const zuege = new Map();
function schalteDiagnose() { diagOffen = !diagOffen; $("#diagnose").classList.toggle("da", diagOffen); document.body.classList.toggle("diag-offen", diagOffen); if (diagOffen) { zeigeDiagStatus(); rolle(); } }
const kurzname = (n) => String(n).replace(/^mcp__([^_]+)__/, "$1: ").replace(/_[a-z]+_[a-z_]+_(get|post|put)$/, "");
function diagLeeren() { $("#d-verlauf").innerHTML = ""; zuege.clear(); }
function diagZeile(art, text) {
  const el = document.createElement("div"); el.className = "d-zeile " + art;
  el.innerHTML = `<span class="art">${esc(art)}</span><span class="txt">${esc(text)}</span>`;
  const v = $("#d-verlauf"); v.appendChild(el);
  while (v.childElementCount > 400) v.firstElementChild.remove(); // Diagnose hält nur die letzten Zeilen
  rolle(); return el;
}
function rolle() { const v = $("#d-verlauf"); v.scrollTop = v.scrollHeight; }
function diagEreignis(ev) {
  switch (ev.typ) {
    case "nutzer": diagZeile("uli", ev.text); zuege.delete(ev.zug); break;
    case "text": {
      let z = zuege.get(ev.zug);
      if (!z || !z.el.isConnected || z.el !== $("#d-verlauf").lastElementChild) { if (!ev.text.trim()) break; z = { el: diagZeile("harno", ""), text: "" }; zuege.set(ev.zug, z); }
      z.text += ev.text; z.el.querySelector(".txt").textContent = z.text.trim(); rolle(); break;
    }
    case "denken": diagZeile("denken", ev.text.slice(0, 300)); break;
    case "werkzeug": { const el = diagZeile("werkzeug", kurzname(ev.name)); el.dataset.wid = ev.wid; zuege.delete(ev.zug); break; }
    case "werkzeug_ende": { const el = $(`#d-verlauf [data-wid="${CSS.escape(ev.wid || "")}"]`); if (el) el.classList.add(ev.fehler ? "fehlerhaft" : "fertig"); break; }
    case "zug_ende": diagZeile("zug", `${ev.sekunden} s${ev.kosten != null ? ` · ${(+ev.kosten).toFixed(3)} $` : ""}${ev.abgebrochen ? " · gestoppt" : ""}${ev.fehler ? " · " + ev.fehler : ""}`); break;
    case "szene": diagZeile("szene", ev.aktion + (ev.art ? " " + ev.art : "") + (ev.karte ? " " + ev.karte.titel : "")); break;
    case "schnellbefehl": diagZeile("schnell", `„${ev.text}“ → ${ev.aktion}`); break;
    case "fehler": diagZeile("fehler", ev.text); break;
  }
}
function zeigeDiagStatus() {
  const s = statusInfo;
  $("#d-status").innerHTML = [
    ["Zustand", automat.name], ["Ansicht", karten.ansicht], ["fps", buehne.fps.toFixed(0) + " (" + buehne.stufe + (buehne.stufeWahl === "auto" ? ", auto" : "") + ")"],
    ["Server", g.verbunden ? "verbunden" : "getrennt"], ["Sprache", sprachBereit ? `${s.modell} · ${s.geraet}` : "lädt …"],
    ["Agent", s.agent || "?"], ["Aufgaben", s.aufgaben || "kein Modul"],
    ...(s.module || []).map((m) => [m.titel, (m.ok ? "" : "⚠ ") + m.text]),
    ...(s.modul_fehler || []).map((f) => ["Fehler", f]),
    ...modulWeb.map((m) => [`${m.name} (Browser)`, m.ok ? `${[...kartenArten.values()].filter((a) => a.modul === m.name).length} Kartenarten · ${[...effekte.values()].filter((x) => x.modul === m.name).length} Effekte` : "⚠ " + m.fehler]),
    ["Stil", stil + " · " + hintergrund.art],
  ].map(([a, b]) => `<div><span>${esc(a)}</span><b>${esc(b)}</b></div>`).join("");
}
$("#d-vorlesen").checked = lies("harno-vorlesen", "an") !== "aus";
g.vorlesen = $("#d-vorlesen").checked;
$("#d-vorlesen").onchange = (e) => { g.vorlesen = e.target.checked; merke("harno-vorlesen", g.vorlesen ? "an" : "aus"); if (!g.vorlesen) g.stummschalten(); };
$("#d-toene").checked = fx.ton.an;
$("#d-toene").onchange = (e) => fx.ton.setze(e.target.checked);
$("#d-stufe").value = lies("harno-stufe", "auto");
buehne.waehleStufe($("#d-stufe").value);
$("#d-stufe").onchange = (e) => { buehne.waehleStufe(e.target.value); merke("harno-stufe", e.target.value); };
$("#d-neu").onclick = () => g.neu();
$("#d-zu").onclick = () => schalteDiagnose();
$("#d-form").addEventListener("submit", (e) => { e.preventDefault(); const i = $("#d-text"); if (i.value.trim() && frage(i.value.trim())) i.value = ""; });
// Stimmenauswahl: der Server liefert alle Stimmen (Piper, Stimmendienste, ElevenLabs) als [{wert, name, gruppe, titel}].
const STIMMWAHL = ["#d-vorleser", "#k-stimme"];
function fuelleVorleser(stimmen) {
  if (!stimmen || !stimmen.length) return;
  for (const id of STIMMWAHL) {
    const sel = $(id), vorher = sel.value;
    sel.innerHTML = "";
    const gruppen = {};
    for (const v of stimmen) {
      let ziel = sel;
      if (v.gruppe !== "Lokal") {
        if (!gruppen[v.gruppe]) { gruppen[v.gruppe] = document.createElement("optgroup"); gruppen[v.gruppe].label = v.gruppe; sel.appendChild(gruppen[v.gruppe]); }
        ziel = gruppen[v.gruppe];
      }
      const o = document.createElement("option"); o.value = v.wert; o.textContent = v.name; if (v.titel) o.title = v.titel; ziel.appendChild(o);
    }
    if (vorher) sel.value = vorher;
  }
}
function zeigeVorleser(art) {
  if (!art) return;
  for (const id of STIMMWAHL) $(id).value = art;
  const o = $("#k-stimme").selectedOptions[0];
  $("#k-stimme-info").textContent = o ? (o.title && o.title !== o.textContent ? o.title : "") : "";
}
// ---------- Leser (L): Cockpit-Dateien und von HarnoRb erstellte Dokumente ----------
let leserOffen = false;
function oeffneLeser(pfad = "") {
  const r = $("#leser-rahmen"), ziel = "/leser#pfad=" + encodeURIComponent(pfad || "");
  if (!r.src) r.src = ziel; else r.contentWindow.location.hash = "pfad=" + encodeURIComponent(pfad || "");
  $("#leser-titel").textContent = pfad || "Cockpit";
  const el = $("#leser"); el.hidden = false; requestAnimationFrame(() => el.classList.add("da"));
  leserOffen = true; document.body.classList.add("leser-offen");
}
function schliesseLeser(melden = true) {
  if (!leserOffen) return;
  const el = $("#leser"); el.classList.remove("da"); setTimeout(() => { if (!leserOffen) el.hidden = true; }, 380);
  leserOffen = false; document.body.classList.remove("leser-offen");
  // Fokus aus dem Rahmen zurückholen, sonst landen Leertaste und Tasten weiter im unsichtbaren Leser
  if (el.contains(document.activeElement)) { knopf.focus({ preventScroll: true }); knopf.blur(); }
  if (melden) api("/api/leser", { method: "POST", body: JSON.stringify({ pfad: null }) }).catch(() => {});
}
function leserEreignis(m) {
  if (m.aktion === "oeffnen") return oeffneLeser(m.pfad);
  if (m.aktion === "browser") return oeffneLeser("");
  if (m.aktion === "schliessen") return schliesseLeser(false);
  if (leserOffen) $("#leser-rahmen").contentWindow.postMessage({ leser: m.aktion }, location.origin);
}
$("#leser-zu").onclick = () => schliesseLeser();
$("#leser-dateien").onclick = () => oeffneLeser("");
$("#leser-rahmen").addEventListener("load", () => {
  try { $("#leser-rahmen").contentWindow.addEventListener("hashchange", () => {
    $("#leser-titel").textContent = decodeURIComponent((($("#leser-rahmen").contentWindow.location.hash.match(/pfad=([^&]*)/) || [])[1]) || "") || "Cockpit"; }); } catch (_) {}
});
window.addEventListener("message", (e) => {
  if (e.origin !== location.origin || e.source !== $("#leser-rahmen").contentWindow) return;
  if (e.data?.leser === "schliessen") schliesseLeser();
  // Tasten aus dem Leser (der hat den Fokus) wie hier gedrückt behandeln
  if (e.data?.leser === "taste" && ["keydown", "keyup"].includes(e.data.typ))
    document.dispatchEvent(new KeyboardEvent(e.data.typ, { key: String(e.data.key), code: String(e.data.code), repeat: !!e.data.repeat, shiftKey: !!e.data.shift, cancelable: true }));
});
api("/api/leser").then((r) => { if (r.pfad != null) oeffneLeser(r.pfad); }).catch(() => {});

// ---------- Konfiguration (K) ----------
let konfigOffen = false;
function schalteKonfig(an = !konfigOffen) {
  konfigOffen = an; $("#konfig").classList.toggle("da", an);
  if (an) pruefeStatus();
}
function zeigeDienste(dienste) {
  const box = $("#k-dienste");
  if (!dienste || !dienste.length) { box.innerHTML = `<p class="k-hinweis">Noch kein Stimmendienst angebunden.</p>`; return; }
  box.innerHTML = dienste.map((d) => `<div class="k-dienst"><b>${esc(d.name)}</b><span class="knoepfe">
      <button data-aktion="aktualisieren" data-name="${esc(d.name)}" title="Stimmen neu holen">↻</button>
      <button data-aktion="entfernen" data-name="${esc(d.name)}" title="Dienst entfernen">Entfernen</button></span>
    <span class="url">${esc(d.url)}${d.token ? " · Token" : ""}${d.modell ? " · " + esc(d.modell.split("/").pop()) : ""}</span>
    <span class="info ${d.fehler ? "fehler" : ""}">${esc(d.fehler || ("Stimmen: " + (d.stimmen.join(", ") || "keine")))}</span></div>`).join("");
}
async function dienstAktion(daten) {
  try { const r = await api("/api/stimmendienst", { method: "POST", body: JSON.stringify(daten) }); toast(r.text); }
  catch (err) { toast("Stimmendienst: " + err.message, "fehler"); }
  pruefeStatus();
}
$("#k-dienste").addEventListener("click", (e) => {
  const b = e.target.closest("button[data-aktion]"); if (!b) return;
  dienstAktion({ aktion: b.dataset.aktion, name: b.dataset.name });
});
$("#k-neu").addEventListener("submit", (e) => {
  e.preventDefault(); const f = new FormData(e.target);
  dienstAktion({ aktion: "hinzufuegen", name: f.get("name"), url: f.get("url"), token: f.get("token") }).then(() => e.target.reset());
});
$("#k-probe").onclick = () => api("/api/stimmprobe", { method: "POST", body: "{}" }).catch((err) => toast(err.message, "fehler"));
$("#k-zu").onclick = () => schalteKonfig(false);
$("#k-stimme").onchange = async (e) => {
  try { await api("/api/vorleser", { method: "POST", body: JSON.stringify({ art: e.target.value }) }); }
  catch (err) { toast("Stimme: " + err.message, "fehler"); pruefeStatus(); }
};
// Menüpunkte per Sprache: der Server schickt {name, wert}, hier wirkt es wie ein Klick auf den Schalter.
function wendeEinstellung(name, wert) {
  const haken = (sel, an) => { const el = $(sel); if (el.checked !== an) { el.checked = an; el.dispatchEvent(new Event("change")); } };
  switch (name) {
    case "vorlesen": haken("#d-vorlesen", !!wert); break;
    case "toene": haken("#d-toene", !!wert); break;
    case "qualitaet": { const el = $("#d-stufe"); el.value = wert; el.dispatchEvent(new Event("change")); break; }
    case "untertitel": if (untertitelAn !== !!wert) schalteUntertitel(); break;
    case "diagnose": if (diagOffen !== !!wert) schalteDiagnose(); break;
    case "hilfe": zeigeHilfe(!!wert); break;
    case "konfiguration": schalteKonfig(!!wert); break;
  }
}
$("#d-vorleser").onchange = async (e) => {
  try { await api("/api/vorleser", { method: "POST", body: JSON.stringify({ art: e.target.value }) }); }
  catch (err) { toast("Stimme: " + err.message, "fehler"); pruefeStatus(); }
};

// ---------- Erlaubnis-Tafel ----------
const anfragen = [];
function zeigeErlaubnisse(liste) {
  if (liste) { anfragen.length = 0; anfragen.push(...liste); }
  const t = $("#erlaubnis");
  const a = anfragen[0];
  if (!a) { t.classList.remove("da"); setTimeout(() => { if (!anfragen.length) t.hidden = true; }, 400); return; }
  $("#erl-werkzeug").textContent = kurzname(a.werkzeug);
  $("#erl-eingabe").textContent = a.eingabe;
  $("#erl-mehr").textContent = anfragen.length > 1 ? `+${anfragen.length - 1} weitere` : "";
  t.hidden = false; requestAnimationFrame(() => t.classList.add("da"));
  automat.kurz("zeigenBis", 900);
}
function beantworte(ja) {
  const a = anfragen.shift(); if (!a) return;
  g.sende({ typ: "erlaubnis_antwort", id: a.id, ja });
  diagZeile("erlaubnis", `${kurzname(a.werkzeug)}: ${ja ? "erlaubt" : "abgelehnt"}`);
  zeigeErlaubnisse();
}
$("#erl-ja").onclick = () => beantworte(true);
$("#erl-nein").onclick = () => beantworte(false);

// ---------- Hilfe ----------
function zeigeHilfe(an) { $("#hilfe").hidden = !an; }
$("#hilfe").addEventListener("click", () => zeigeHilfe(false));
$("#hilfe-knopf").onclick = () => zeigeHilfe(true);

addEventListener("resize", () => { if (szenenZustand) karten.anwende(szenenZustand, { sofort: true }); });

// ---------- Vorschau (Phase 1): Zustände per Taste, Demo-Karten ohne Server ----------
const DEMO = [
  { art: "aufgabe", nr: 1, uuid: "d0000001-0000-4000-8000-000000000001", titel: "Folien für den Demo-Termin vorbereiten", projekt: "marketing", faellig: null, ueberfaellig: false, heute: false, tags: ["@computer"], laeuft: true },
  { art: "aufgabe", nr: 2, uuid: "d0000001-0000-4000-8000-000000000002", titel: "Angebot Musterfirma überarbeiten", projekt: "vertrieb.musterfirma", faellig: "2026-11-25", ueberfaellig: false, heute: true, tags: [], laeuft: false },
  { art: "aufgabe", nr: 3, uuid: "d0000001-0000-4000-8000-000000000003", titel: "Fahrrad zur Inspektion bringen", projekt: "privat", faellig: "2026-11-25", ueberfaellig: false, heute: true, tags: ["@unterwegs"], laeuft: false },
  { art: "aufgabe", nr: 4, uuid: "d0000001-0000-4000-8000-000000000004", titel: "Anonymisierungstest: Testdaten erzeugen", projekt: "anonymisierungstest", faellig: "2026-11-24", ueberfaellig: true, heute: false, tags: ["@computer"], laeuft: false },
  { art: "aufgabe", nr: 5, uuid: "d0000001-0000-4000-8000-000000000005", titel: "Steuerunterlagen für das Quartal sortieren", projekt: "verwaltung", faellig: "2026-11-23", ueberfaellig: true, heute: false, tags: ["@home"], laeuft: false },
  { art: "aufgabe", nr: 6, uuid: "d0000001-0000-4000-8000-000000000006", titel: "Wohnzimmerlampe reparieren", projekt: "privat", faellig: "2026-11-20", ueberfaellig: true, heute: false, tags: ["@home"], laeuft: false },
];
function demoPegel(t) { return Math.max(0, Math.sin(t * 9) * 0.5 + Math.sin(t * 23) * 0.3 + Math.sin(t * 3.1) * 0.3); }
function demo(aktion, mehr = {}) {
  const z = { ...szenenZustand, ...mehr };
  spieleSzene({ aktion, zustand: z, ...mehr.ev });
}
function vorschauTaste(e) {
  const k = e.key.toLowerCase();
  const i = "123456789".indexOf(e.key);
  if (i >= 0) { automat.vorschau = ZUSTAENDE[i]; if (ZUSTAENDE[i] === "uebergang") fx.hyperraum(900); return true; }
  if (k === "0") { automat.vorschau = null; return true; }
  if (k === "s") { setzeStil(stil === "comic" ? "leuchtend" : "comic"); return true; }
  if (k === "b") { setzeStil(null, hintergrund.art === "mond" ? "raumer" : "mond"); return true; }
  if (k === "c") { demo("liste", { ansicht: "liste", liste: "heute", titel: "Heute", karten: DEMO.map((x) => ({ ...x })), gesamt: 6, gewaehlt: null, fokus: null, text: null, optionen: null }); return true; }
  if (k === "g") { const n = ((szenenZustand.gewaehlt || 0) % (szenenZustand.karten?.length || 1)) + 1; szenenZustand = { ...szenenZustand, gewaehlt: n }; karten.waehle(n); return true; }
  if (k === "f") { const kk = szenenZustand.karten?.[(szenenZustand.gewaehlt || 1) - 1] || DEMO[1]; demo("fokus", { ansicht: "fokus", fokus: { ...kk, notizen: [{ tag: "2026-11-24", text: "Preisstaffel aus dem Workshop übernehmen" }] } }); return true; }
  if (k === "e") {
    const f = szenenZustand.fokus || szenenZustand.karten?.[0] || DEMO[0];
    const rest = (szenenZustand.karten || []).filter((x) => x.uuid !== f.uuid).map((x, j) => ({ ...x, nr: j + 1 }));
    demo("erledigt", { ansicht: rest.length ? "liste" : "leer", karten: rest, fokus: null, gewaehlt: null, ev: { karte: f } });
    return true;
  }
  if (k === "t") { demo("text", { ansicht: "text", text: { titel: "Entwurf: Antwort an die Druckerei", inhalt: "Hallo zusammen,\n\nvielen Dank für das Angebot. **Bitte** schickt uns noch einen Probedruck.\n\n- Auflage 500\n- Papier 170 g\n\nViele Grüße" } }); return true; }
  if (k === "o") { demo("optionen", { ansicht: "optionen", optionen: { frage: "Welche Liste?", optionen: ["Heute", "Überfällig", "Inbox"] } }); return true; }
  if (k === "x") { demo("ausblenden", { ansicht: "leer", karten: [], fokus: null, text: null, optionen: null, gewaehlt: null }); return true; }
  if (k === "q") { const r = ["auto", "hoch", "mittel", "niedrig"]; buehne.waehleStufe(r[(r.indexOf(buehne.stufeWahl) + 1) % r.length]); return true; }
  if (k === "h") { zeigeHilfe($("#hilfe").hidden); return true; }
  return false;
}

// ---------- Start ----------
setzeStil(lies("harno-stil-vorschau", "leuchtend"), "mond", { sofort: true });
buehne.start();
if (VORSCHAU) {
  automat.setze("verbunden", true); sprachBereit = true; zeigeStatusPunkt();
  // ?zustand=denken&stil=comic&hintergrund=raumer&karten=1 für Screenshots
  const q = new URLSearchParams(location.search);
  if (q.get("stil")) setzeStil(q.get("stil"), null, { sofort: true });
  if (q.get("hintergrund")) setzeStil(null, q.get("hintergrund"), { sofort: true });
  if (q.get("zustand")) automat.vorschau = q.get("zustand");
  if (q.get("karten")) vorschauTaste({ key: "c" });
  if (q.get("fokus")) setTimeout(() => vorschauTaste({ key: "f" }), 50);
  if (q.get("text")) vorschauTaste({ key: "t" });
} else {
  g.verbinde(); pruefeStatus();
  if (lies("harno-hilfe-gesehen", "") !== "ja") { setTimeout(() => toast("Leertaste halten und sprechen. H zeigt alle Tasten."), 1500); merke("harno-hilfe-gesehen", "ja"); }
}
zeigeKnopfText();
setInterval(zeigeKnopfText, 500);
// Interne Objekte nur für Vorschau und Diagnose (?diag) offenlegen
if (VORSCHAU || new URLSearchParams(location.search).has("diag")) window.__harnoIntern = { kugel, automat, buehne, karten, hintergrund, fx };

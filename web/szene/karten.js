// Karten: Aufgaben, Inbox-Einträge und Projekte als schwebende Glastafeln (CSS3D, Text scharf).
// Als Gruppe im Bogen um die Kugel, einzeln groß in der Mitte. Dazu Text-Tafel und Auswahlkarten.
import * as THREE from "three";
import { CSS3DObject } from "three/addons/renderers/CSS3DRenderer.js";
import { tween, ease, warte } from "./tween.js";
import { kartenArten, effekte } from "./erweiterungen.js";

const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
export function md(text) { // kleines, sicheres Markdown
  return esc(text).split(/\n{2,}/).map((p) => {
    p = p.replace(/\*\*(.+?)\*\*/g, "<b>$1</b>").replace(/`([^`]+)`/g, "<code>$1</code>").replace(/^#+\s*(.+)$/gm, "<b>$1</b>");
    if (/^\s*[-*] /m.test(p)) return "<ul>" + p.split(/\n/).map((l) => `<li>${l.replace(/^\s*[-*] /, "")}</li>`).join("") + "</ul>";
    return `<p>${p.replace(/\n/g, "<br>")}</p>`;
  }).join("");
}
const tagDatum = (iso) => { if (!iso) return ""; const [j, m, t] = iso.split("-"); return `${t}.${m}.`; };
const schluessel = (k) => (k.uuid ? k.uuid : "p:" + k.titel);

// Darstellungshinweise der Module (anzeige vom Server, dort geprüft)
const FARBE = { blau: "#7cc4ff", gruen: "#6fe3b5", gelb: "#ffe08a", orange: "#ffb36b", rot: "#ff8a6e", violett: "#c79bff", grau: "#a7adc4" };
const abzeichen = (k) => (k.anzeige?.abzeichen || []).map((a) => `<span class="abz">${esc(a)}</span>`).join("");
const symbol = (k) => (k.anzeige?.symbol ? `<span class="symbol">${esc(k.anzeige.symbol)}</span>` : "");
const untertitel = (k) => (k.anzeige?.untertitel ? `<div class="unterzeile">${esc(k.anzeige.untertitel)}</div>` : "");
function faerbe(el, k) {
  const f = k.anzeige?.farbe;
  el.classList.toggle("mit-farbe", !!f);
  if (f) el.style.setProperty("--modulfarbe", FARBE[f] || f); else el.style.removeProperty("--modulfarbe");
}

function metaZeile(k) {
  if (k.art === "projekt") return `<span>${esc(k.info)}</span>${abzeichen(k)}`;
  return abzeichen(k) + [k.projekt && `<span class="pr">${esc(k.projekt)}</span>`,
    k.faellig && `<span class="${k.ueberfaellig ? "ueberf" : k.heute ? "heute" : ""}">${k.ueberfaellig ? "überfällig " : "fällig "}${tagDatum(k.faellig)}</span>`,
    ...(k.tags || []).map((t) => `<span class="tag">${esc(t)}</span>`),
    k.laeuft && `<span class="laeuft">läuft</span>`].filter(Boolean).join("");
}

export class Karten {
  constructor(buehne, kugelOrt, effekte, { klick, option, ton } = {}) {
    this.b = buehne; this.kugelOrt = kugelOrt; this.fx = effekte;
    this.klick = klick || (() => {}); this.option = option || (() => {}); this.ton = ton;
    this.liste = new Map();     // schluessel -> Eintrag
    this.fokusEintrag = null;
    this.chips = [];
    this.gewaehlt = null;
    this.ansicht = "leer";
    this.listenName = null;
    this.titelEl = null;
    this.tafel = document.getElementById("tafel");
    // Ebene für die ruhende Fokuskarte: ohne 3D-Transformation, auf ganze Pixel gesetzt, damit Text gestochen scharf ist
    this.flachEbene = document.createElement("div");
    this.flachEbene.className = "flach-ebene";
    document.body.appendChild(this.flachEbene);
  }

  // Fokuskarte aus dem 3D-Renderer lösen (ruht) bzw. zurückgeben (bewegt sich wieder)
  _flach(e, an) {
    if (!!e.flach === an) return;
    e.flach = an;
    if (an) {
      this.b.cssSzene.remove(e.obj);
      this.flachEbene.appendChild(e.el);
      e.el.style.transform = ""; e.flachTransform = "";
    } else {
      e.el.style.transform = "";
      this.b.cssSzene.add(e.obj); // der Renderer hängt das Element im nächsten Bild selbst wieder ein
    }
  }

  // ---------- Einträge ----------

  _neu(k, klasse = "karte") {
    const el = document.createElement("div");
    el.className = klasse;
    const obj = new CSS3DObject(el);
    this.b.cssSzene.add(obj);
    this.b.css.domElement.firstChild?.appendChild(el); // sofort im DOM, damit die Höhe messbar ist
    const e = { k, el, obj, basis: new THREE.Vector3(), rot: new THREE.Vector3(), skala: 1, op: 0, schwebe: Math.random() * 6.28, aktiv: true };
    el.addEventListener("click", (ev) => { ev.stopPropagation(); this.klick(e.k, ev); });
    this._fuelle(e);
    return e;
  }

  // Eigene Kartenart eines Moduls; false, wenn keine gilt oder sie scheitert (dann zeichnet der Kern)
  _eigeneArt(e, wo) {
    const art = kartenArten.get(e.k.anzeige?.art || "");
    if (e.artKlasse) { e.el.classList.remove(...e.artKlasse.split(/\s+/)); e.artKlasse = ""; }
    const fn = art && (wo === "fokus" ? art.fokus : art.karte);
    if (!fn) return false;
    try {
      if (art.klasse) { e.artKlasse = art.klasse; e.el.classList.add(...art.klasse.split(/\s+/)); }
      fn(e.el, e.k, { esc, md, meta: metaZeile });
      return true;
    } catch (err) {
      console.warn(`Kartenart ${e.k.anzeige.art} (${art.modul}):`, err);
      return false;
    }
  }

  _fuelle(e) {
    const k = e.k;
    faerbe(e.el, k);
    if (e.el.classList.contains("fokuskarte")) {
      if (this._eigeneArt(e, "fokus")) return;
      e.el.innerHTML = `<div class="kopf"><span class="marke">Im Fokus</span>${metaZeile(k)}</div>
        <h1>${symbol(k)}${esc(k.titel)}</h1>${untertitel(k)}
        ${(k.notizen || []).length ? `<ul class="notizen">${k.notizen.map((n) => `<li><small>${tagDatum(n.tag)}</small>${esc(n.text)}</li>`).join("")}</ul>` : `<p class="leise">Noch keine Notizen.</p>`}
        <div class="hinweise"><kbd>E</kbd> erledigt · <kbd>X</kbd> ausblenden · oder einfach sagen</div>`;
      return;
    }
    e.el.classList.toggle("ueberf", !!k.ueberfaellig);
    e.el.classList.toggle("projekt", k.art === "projekt");
    e.el.classList.toggle("laeuft", !!k.laeuft);
    if (this._eigeneArt(e, "karte")) return;
    e.el.innerHTML = `<div class="nr">${k.nr}</div><div class="inhalt"><div class="titel">${symbol(k)}${esc(k.titel)}</div>${untertitel(k)}<div class="meta">${metaZeile(k)}</div></div>`;
  }

  _entferne(e) {
    e.aktiv = false;
    this.b.cssSzene.remove(e.obj);
    e.el.remove();
  }

  update(dt, zeit) {
    const px = this.b.sichtbar(0).pxProEinheit;
    const alle = [...this.liste.values(), ...this.chips, this.fokusEintrag, this._titel, ...(this._fliegend || [])].filter(Boolean);
    const f = this.fokusEintrag;
    if (f) {
      const ruht = !f.tw?.laeuft?.() && f.op >= 0.999 && Math.abs(f.skala - 1) < 1e-3 && f.basis.z === 0;
      this._flach(f, ruht);
      if (f.flach) {
        const x = Math.round(innerWidth / 2 + f.basis.x * px - f.el.offsetWidth / 2);
        const y = Math.round(innerHeight / 2 - f.basis.y * px - f.el.offsetHeight / 2);
        const t = `translate(${x}px, ${y}px)`;
        if (t !== f.flachTransform) { f.el.style.transform = t; f.flachTransform = t; }
        f.el.style.opacity = "1"; f.el.style.visibility = "visible";
      }
    }
    for (const e of alle) {
      if (e.flach) continue;
      const s = (e.skala / px);
      // Fokuskarte ruht, sobald sie angekommen ist: ohne Kippen bleibt der Text gestochen scharf
      const ruhig = e === this.fokusEintrag && !e.tw?.laeuft?.() ? 0 : 1;
      e.obj.position.set(e.basis.x, e.basis.y + Math.sin(zeit * 0.9 + e.schwebe) * 0.035 * e.op * ruhig, e.basis.z);
      e.obj.rotation.set(e.rot.x + Math.sin(zeit * 0.6 + e.schwebe) * 0.015 * ruhig, e.rot.y, e.rot.z);
      e.obj.scale.setScalar(Math.max(s, 1e-5));
      e.el.style.opacity = e.op.toFixed(3);
      e.el.style.visibility = e.op < 0.01 ? "hidden" : "visible";
    }
  }

  // ---------- Layout ----------

  kartenBreite() {
    const s = this.b.sichtbar(0);
    return Math.round(Math.min(340, innerWidth * (s.b / s.h > 1.05 ? 0.27 : 0.86)));
  }

  // hoehen: gemessene Kartenhöhen in px (nach dem Füllen), damit nichts überlappt
  _layoutListe(hoehen) {
    const s = this.b.sichtbar(0), px = s.pxProEinheit, n = hoehen.length;
    const breit = s.b / s.h > 1.05;
    const kartenB = this.kartenBreite() / px;
    const luecke = 12 / px;
    const orte = [];
    const hoeheVon = (idx) => idx.reduce((a, i) => a + hoehen[i] / px, 0) + luecke * Math.max(0, idx.length - 1);
    let oben = 0; // beide Spalten oben bündig, gemeinsam um die Kugelmitte zentriert
    const spalte = (idx, x, seite) => {
      const h = idx.map((i) => hoehen[i] / px);
      let y = oben;
      idx.forEach((i, j) => {
        const mitte = y - h[j] / 2; y -= h[j] + luecke;
        const bogen = (mitte / (s.h / 2)) ** 2;
        // leichter Bogen nach hinten, aber bündige Spalte und keine Schräglage (bessere Lesbarkeit)
        orte[i] = { pos: new THREE.Vector3(x + seite * bogen * 0.08, mitte + 0.05, 0.25 - bogen * 0.45),
          rot: new THREE.Vector3(0, seite * 0.1, 0) };
      });
    };
    if (breit) {
      const proSeite = Math.ceil(n / 2);
      const links = [...Array(proSeite).keys()], rechts = [...Array(n - proSeite).keys()].map((i) => i + proSeite);
      oben = Math.max(hoeheVon(links), hoeheVon(rechts)) / 2 + this.kugelOrt().pos.y;
      // fester Abstand zur Kugel (Radius plus Halo), unabhängig von der Kartenzahl; nur am Bildrand begrenzt
      const ko = this.kugelOrt();
      const sx = Math.min(s.b / 2 - kartenB / 2 - 0.25, ko.r * 1.45 + 0.35 + kartenB / 2);
      spalte(links, ko.pos.x - sx, 1);
      spalte(rechts, ko.pos.x + sx, -1);
    } else {
      let y = s.h / 2 - 2.3;
      for (let i = 0; i < n; i++) {
        const h = hoehen[i] / px;
        orte[i] = { pos: new THREE.Vector3(0, y - h / 2, 0.2), rot: new THREE.Vector3(-0.05, 0, 0) };
        y -= h + luecke * 0.7;
      }
    }
    return { orte, kartenB: kartenB * px };
  }

  _ueberschrift(text) {
    if (!text) { if (this._titel) { const t = this._titel; this._titel = null; tween({ dauer: 300, update: (w) => { t.op = 1 - w; }, fertig: () => this._entferne(t) }); } return; }
    if (!this._titel) {
      this._titel = this._neu({ titel: text }, "listentitel");
      this._titel.basis.copy(this.kugelOrt().pos);
    }
    this._titel.el.textContent = text;
    const s = this.b.sichtbar(0), ko = this.kugelOrt();
    const breit = s.b / s.h > 1.05;
    const ziel = breit ? new THREE.Vector3(0, ko.pos.y + ko.r + 0.45, 0.1) : new THREE.Vector3(0, s.h / 2 - 0.55, 0.1);
    const t = this._titel, start = t.basis.clone(), op0 = t.op;
    tween({ dauer: 600, ease: ease.outCubic, update: (w) => { t.basis.lerpVectors(start, ziel, w); t.op = op0 + (1 - op0) * w; } });
  }

  // ---------- Ansichten ----------

  anwende(z, { sofort = false } = {}) {
    this.ansicht = z.ansicht;
    const listeSichtbar = ["liste", "optionen"].includes(z.ansicht);
    const textSichtbar = z.ansicht === "text";
    this._setzeListe(listeSichtbar || textSichtbar ? z.karten : [], { gedimmt: textSichtbar, sofort, titel: listeSichtbar ? z.titel : "" , leerText: listeSichtbar && !z.karten.length ? z.titel : null});
    this._setzeFokus(z.ansicht === "fokus" ? z.fokus : null, sofort);
    this._setzeTafel(textSichtbar ? z.text : null, sofort);
    this._setzeChips(z.ansicht === "optionen" && z.optionen ? z.optionen : null, sofort);
    this.waehle(z.gewaehlt);
  }

  _setzeListe(karten, { gedimmt, sofort, titel, leerText }) {
    const neu = new Map(karten.map((k) => [schluessel(k), k]));
    // Weg: in die Kugel zurück (oder weggeweht, wenn der Fokus kommt)
    for (const [key, e] of [...this.liste]) {
      if (!neu.has(key)) { this.liste.delete(key); this._weg(e, this._wegArt || "zurueck", sofort); }
    }
    const ko = this.kugelOrt();
    const breiteKarte = this.kartenBreite();
    const eintraege = karten.map((k) => {
      const key = schluessel(k);
      let e = this.liste.get(key), frisch = false;
      if (!e) {
        e = this._neu(k); frisch = true;
        e.basis.copy(ko.pos); e.skala = 0.05; e.op = 0; e.rot.set(0, 0, (Math.random() - 0.5) * 1.2);
        this.liste.set(key, e);
      } else { e.k = k; this._fuelle(e); }
      e.el.style.width = breiteKarte + "px";
      return [e, frisch];
    });
    const { orte } = this._layoutListe(eintraege.map(([e]) => e.el.offsetHeight || 72));
    eintraege.forEach(([e, frisch], i) => {
      const ziel = orte[i];
      const zielPos = ziel.pos.clone(), zielRot = ziel.rot.clone();
      if (gedimmt) zielPos.z -= 3;
      const zielOp = gedimmt ? 0.12 : 1;
      if (sofort) { e.basis.copy(zielPos); e.rot.copy(zielRot); e.skala = 1; e.op = zielOp; return; }
      const p0 = e.basis.clone(), r0 = e.rot.clone(), s0 = e.skala, o0 = e.op;
      // Aufsteigen aus der Kugel: Bogen nach oben, dann an den Platz. Wechselt eine Karte die Spalte,
      // nimmt sie den Weg hinter den anderen vorbei, damit sich nichts überlappt.
      const spaltenWechsel = !frisch && Math.sign(p0.x - ko.pos.x) !== Math.sign(zielPos.x - ko.pos.x);
      const mitte = frisch ? p0.clone().lerp(zielPos, 0.5).add(new THREE.Vector3(0, 1.2, 1.5))
        : spaltenWechsel ? p0.clone().lerp(zielPos, 0.5).add(new THREE.Vector3(0, 0, -2.5)) : null;
      e.tw?.stop();
      e.tw = tween({ dauer: frisch ? 950 : 650, verzoegerung: frisch ? 160 + i * 70 : 0, ease: frisch ? ease.outBack : ease.inOutCubic, update: (w, roh) => {
        if (mitte) { // quadratische Bézierkurve, outBack schwingt leicht über den Platz hinaus
          const u = Math.min(w, 1.08), a = 1 - u;
          e.basis.copy(p0).multiplyScalar(a * a).addScaledVector(mitte, 2 * a * u).addScaledVector(zielPos, u * u);
        } else e.basis.lerpVectors(p0, zielPos, w);
        e.rot.lerpVectors(r0, zielRot, Math.min(1, w));
        e.skala = s0 + (1 - s0) * Math.min(1.1, w);
        e.op = o0 + (zielOp - o0) * Math.min(1, roh * 1.6);
      } });
    });
    this._ueberschrift(leerText ? leerText + " · leer" : titel);
  }

  _weg(e, art, sofort) {
    this._flach(e, false);
    if (sofort) return this._entferne(e);
    e.tw?.stop();
    const p0 = e.basis.clone(), r0 = e.rot.clone(), s0 = e.skala, o0 = e.op;
    this._fliegend = this._fliegend || [];
    this._fliegend.push(e);
    const ende = () => { this._entferne(e); this._fliegend = this._fliegend.filter((x) => x !== e); };
    if (art === "wehen") { // auseinander, an der Kamera vorbei
      const ziel = p0.clone().multiplyScalar(2.6).add(new THREE.Vector3(0, (Math.random() - 0.5) * 3, 6 + Math.random() * 3));
      const dreh = new THREE.Vector3((Math.random() - 0.5) * 2, (p0.x > 0 ? 1 : -1) * 1.6, (Math.random() - 0.5) * 2);
      e.tw = tween({ dauer: 800 + Math.random() * 300, ease: ease.inCubic, update: (w) => {
        e.basis.lerpVectors(p0, ziel, w); e.rot.lerpVectors(r0, dreh, w); e.op = o0 * (1 - w);
      }, fertig: ende });
    } else { // zurück in die Kugel, mit Drall
      const ziel = this.kugelOrt().pos.clone();
      e.tw = tween({ dauer: 650 + Math.random() * 250, ease: ease.inBack, update: (w) => {
        e.basis.lerpVectors(p0, ziel, Math.max(0, w)); e.rot.set(r0.x, r0.y + w * 2.5, r0.z + w * 1.5);
        e.skala = s0 * (1 - Math.max(0, Math.min(1, w)) * 0.95); e.op = o0 * (1 - Math.max(0, Math.min(1, w)));
      }, fertig: ende });
    }
  }

  _setzeFokus(k, sofort) {
    const alt = this.fokusEintrag;
    if (!k) {
      if (alt) { this.fokusEintrag = null; this._weg(alt, "zurueck", sofort); }
      return;
    }
    if (alt && alt.k.uuid === k.uuid) { alt.k = k; this._fuelle(alt); return; }
    if (alt) this._weg(alt, "wehen", sofort);
    // Herkunft: dieselbe Aufgabe aus der Liste (die dort schon weggeweht wird) oder die Kugel
    const herkunft = this._letzteListenPos?.get(k.uuid) || this.kugelOrt().pos.clone();
    const e = this._neu(k, "fokuskarte");
    const s = this.b.sichtbar(0);
    const breite = Math.min(640, innerWidth * 0.86);
    e.el.style.width = breite + "px";
    this.fokusEintrag = e;
    // Tiefe 0: dort ist ein CSS-Pixel genau ein Bildschirmpixel, die ruhende Karte springt beim Lösen nicht
    const ziel = new THREE.Vector3(s.b / s.h > 1.05 ? -0.4 : 0, -0.15, 0);
    if (sofort) { e.basis.copy(ziel); e.op = 1; e.skala = 1; return; }
    e.basis.copy(herkunft); e.op = 0; e.skala = 0.4; e.rot.set(0, -Math.PI * 0.9, 0);
    const p0 = e.basis.clone();
    e.tw = tween({ dauer: 1100, verzoegerung: 250, ease: ease.outBack, update: (w, roh) => {
      e.basis.lerpVectors(p0, ziel, w); e.rot.set(0, -Math.PI * 0.9 * (1 - w), 0);
      e.skala = 0.4 + 0.6 * w; e.op = Math.min(1, roh * 2);
    }, fertig: () => { e.basis.copy(ziel); e.skala = 1; e.op = 1; e.rot.set(0, 0, 0); } });
  }

  _setzeTafel(t, sofort) {
    const el = this.tafel;
    if (!t) {
      if (!el.hidden && !el.classList.contains("weg")) {
        el.classList.add("weg"); el.classList.remove("da");
        setTimeout(() => { if (el.classList.contains("weg")) el.hidden = true; }, sofort ? 0 : 600);
      }
      return;
    }
    el.querySelector(".t-titel").textContent = t.titel;
    el.querySelector(".t-inhalt").innerHTML = md(t.inhalt);
    el.querySelector(".t-inhalt").scrollTop = 0;
    el.hidden = false; el.classList.remove("weg");
    if (sofort) { el.classList.add("da"); return; }
    el.classList.remove("da"); void el.offsetWidth; el.classList.add("da");
  }

  _setzeChips(o, sofort) {
    for (const c of this.chips) this._weg(c, "zurueck", sofort);
    this.chips = [];
    if (!o) return;
    const s = this.b.sichtbar(0), ko = this.kugelOrt();
    const n = o.optionen.length;
    const px = s.pxProEinheit, w = 190 / px;
    const breit = Math.min(n * w * 1.1, s.b * 0.92);
    o.optionen.forEach((text, i) => {
      const e = this._neu({ titel: text, nr: i + 1, option: true }, "chip");
      e.el.innerHTML = `<span class="nr">${i + 1}</span>${esc(text)}`;
      e.el.style.width = Math.min(180, (breit / n) * px * 0.92) + "px";
      e.basis.copy(ko.pos); e.op = 0; e.skala = 0.1;
      const ziel = new THREE.Vector3(-breit / 2 + (i + 0.5) * (breit / n), ko.pos.y - ko.r - 0.75, 0.6);
      if (sofort) { e.basis.copy(ziel); e.op = 1; e.skala = 1; }
      else {
        const p0 = e.basis.clone();
        e.tw = tween({ dauer: 700, verzoegerung: 120 + i * 80, ease: ease.outBack, update: (w2, roh) => { e.basis.lerpVectors(p0, ziel, w2); e.skala = 0.1 + 0.9 * w2; e.op = Math.min(1, roh * 2); } });
      }
      this.chips.push(e);
    });
    if (o.frage) this._ueberschrift(o.frage);
  }

  waehle(nr) {
    this.gewaehlt = nr || null;
    for (const e of this.liste.values()) {
      const an = !!nr && e.k.nr === nr;
      if (e.el.classList.contains("gewaehlt") === an) continue;
      e.el.classList.toggle("gewaehlt", an);
      if (an) {
        this.ton?.auf();
        const z0 = e.basis.z, s0 = e.skala;
        tween({ dauer: 450, ease: ease.outBack, update: (w) => { e.basis.z = z0 + w * 0.7; e.skala = s0 + (1.1 - s0) * w; } });
      } else {
        const z0 = e.basis.z, s0 = e.skala;
        tween({ dauer: 400, ease: ease.outCubic, update: (w) => { e.basis.z = z0 - (z0 - 0.25) * w; e.skala = s0 + (1 - s0) * w; } });
      }
    }
  }

  // Vor dem Wechsel zum Fokus: Liste wegwehen statt in die Kugel saugen
  vorbereiten(aktion) {
    this._wegArt = aktion === "fokus" ? "wehen" : "zurueck";
    this._letzteListenPos = new Map([...this.liste.values()].map((e) => [e.k.uuid, e.basis.clone()]));
  }

  // Karte, die gleich in die Erledigt-Box fliegt: aus der Verwaltung lösen und zurückgeben
  loese(uuid) {
    if (this.fokusEintrag && this.fokusEintrag.k.uuid === uuid) { const e = this.fokusEintrag; this.fokusEintrag = null; return e; }
    for (const [key, e] of this.liste) if (e.k.uuid === uuid) { this.liste.delete(key); return e; }
    return null;
  }

  // Erledigt: Aufladen (außen), Strahl auf die Karte, Karte fliegt ins Portal
  async erledigtFlug(k, kugelPos) {
    let e = this.loese(k.uuid);
    if (!e) { // Karte war nicht sichtbar: kurz in der Mitte zeigen
      e = this._neu(k); e.el.style.width = "320px";
      e.basis.set(0, 0.2, 1); e.op = 0; e.skala = 0.6;
      await tween({ dauer: 400, ease: ease.outBack, update: (w) => { e.op = w; e.skala = 0.6 + 0.4 * w; } }).fertig;
    }
    e.tw?.stop();
    this._fliegend = this._fliegend || []; this._fliegend.push(e);
    e.el.classList.add("erledigt");
    const fx = this.fx, name = k.anzeige?.effekt || "strahl";
    const ende = () => { this._entferne(e); this._fliegend = this._fliegend.filter((x) => x !== e); };
    const eigen = effekte.get(name);
    if (eigen) {
      try { await eigen.fn({ k, el: e.el, eintrag: e, fx, kugelPos, THREE, tween, ease, warte }); }
      catch (err) { console.warn(`Effekt ${name} (${eigen.modul}):`, err); }
      return ende();
    }
    if (name === "sanft") { // ohne Strahl und Portal: leuchtet auf, hebt sich und verblasst
      fx.ton.auf();
      const p0 = e.basis.clone();
      await tween({ dauer: 900, ease: ease.inOutCubic, update: (w) => {
        e.basis.set(p0.x, p0.y + w * 0.6, p0.z + w * 0.4); e.skala = 1 + w * 0.08; e.op = 1 - w;
      } }).fertig;
      return ende();
    }
    const portal = fx.portalOrt();
    fx.portalAuf();
    // Strahl baut sich auf
    fx.ton.zap();
    await tween({ dauer: 260, ease: ease.outCubic, update: (w) => fx.strahlZwischen(kugelPos(), e.basis, w) }).fertig;
    const p0 = e.basis.clone(), mitte = p0.clone().lerp(portal, 0.5).add(new THREE.Vector3(0, 0.8, 1.6)), r0 = e.rot.clone();
    await tween({ dauer: 1000, ease: ease.inOutCubic, update: (w) => {
      const a = 1 - w;
      e.basis.copy(p0).multiplyScalar(a * a).addScaledVector(mitte, 2 * a * w).addScaledVector(portal, w * w);
      e.rot.set(r0.x - w * 1.2, r0.y + w * 3.5, r0.z + w * 0.8);
      e.skala = 1 - w * 0.92;
      e.op = 1 - Math.max(0, w - 0.75) * 4;
      fx.strahlZwischen(kugelPos(), e.basis, 1 - Math.max(0, w - 0.6) * 2.5);
      fx.funken(e.basis, w > 0.1 ? 3 : 1);
    } }).fertig;
    fx.strahlZwischen(kugelPos(), e.basis, 0);
    ende();
    await fx.portalZu();
  }

  // Nachdem Module eigene Kartenarten angemeldet haben: sichtbare Karten neu zeichnen
  neuZeichnen() {
    for (const e of [...this.liste.values(), this.fokusEintrag].filter(Boolean)) this._fuelle(e);
  }

  // Nach einer Größenänderung neu anordnen
  neuLayout(z) { if (z) this.anwende(z, { sofort: true }); }
}

export { warte };

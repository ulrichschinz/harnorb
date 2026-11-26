"use strict";
// Cockpit-Oberfläche: Überblick (Aufgabenmodul), Fokus auf eine Aufgabe, Gespräch mit Sprache.

const $ = (s) => document.querySelector(s);
const zustand = {
  daten: null, liste: "heute", fokus: null, ws: null,
  seq: 0,            // Nummer des letzten verarbeiteten Ereignisses
  zuege: new Map(),  // Zug-Nummer -> { blase, letzte }
  laeuft: null,      // Nummer des offenen Zugs
  nachspiel: false,  // true, während der Verlauf nach dem Verbinden neu aufgebaut wird
  stumm: false,      // true zwischen "stopp"/"frage" und der Quittung: Ton von vorher verwerfen
  erkennt: false,    // eine Aufnahme wird gerade erkannt
};

// ---------- Hilfen ----------
const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
function tw(s) { // Taskwarrior-Datum 20261117T230000Z -> Date
  if (!s) return null;
  const m = s.match(/^(\d{4})(\d{2})(\d{2})T(\d{2})(\d{2})(\d{2})Z$/);
  return m ? new Date(Date.UTC(+m[1], m[2] - 1, +m[3], +m[4], +m[5], +m[6])) : null;
}
const heute = () => { const d = new Date(); d.setHours(0, 0, 0, 0); return d; };
function datum(d) { return d ? d.toLocaleDateString("de-DE", { day: "2-digit", month: "2-digit" }) : ""; }
function faellig(t) {
  const d = tw(t.due); if (!d) return null;
  const morgen = new Date(heute()); morgen.setDate(morgen.getDate() + 1);
  return { d, ueberf: d < heute(), heute: d >= heute() && d < morgen };
}
async function api(pfad, opt = {}) {
  const r = await fetch(pfad, { headers: { "Content-Type": "application/json" }, ...opt });
  if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || r.statusText);
  return r.json();
}
function md(text) { // kleines, sicheres Markdown für die Anzeige
  return esc(text).split(/\n{2,}/).map((p) => {
    p = p.replace(/\*\*(.+?)\*\*/g, "<b>$1</b>").replace(/`([^`]+)`/g, "<code>$1</code>");
    if (/^\s*[-*] /m.test(p)) return "<ul>" + p.split(/\n/).map((l) => `<li>${l.replace(/^\s*[-*] /, "")}</li>`).join("") + "</ul>";
    return `<p>${p.replace(/\n/g, "<br>")}</p>`;
  }).join("");
}

// ---------- Überblick ----------
let ueberblickLauf = 0;
async function ladeUeberblick() {
  const lauf = ++ueberblickLauf;
  try {
    const daten = await api("/api/ueberblick");
    if (lauf !== ueberblickLauf) return; // eine neuere Abfrage läuft schon
    zustand.daten = daten;
    $("#punkt-aufgaben").className = "punkt " + (zustand.daten.fehler.length ? "fehler" : "ok");
    $("#punkt-aufgaben").title = zustand.daten.fehler.join("; ") || "Aufgaben verbunden";
  } catch (e) { $("#punkt-aufgaben").className = "punkt fehler"; return; }
  zeigeZahlen(); zeigeListe();
}
function zeigeZahlen() {
  const s = zustand.daten.summary || {};
  const z = [["Inbox", s.inbox, "inbox", s.inbox > 0], ["Überfällig", s.overdue, "heute", s.overdue > 0],
    ["Heute", s.due_today, "heute"], ["Nächste", s.next, "naechste"], ["Warten", s.waiting, "warten", s.waiting_followup_due > 0]];
  $("#zahlen").innerHTML = z.map(([n, w, l, warn]) => `<span class="zahl${warn ? " warn" : ""}" data-liste="${l}">${n} <b>${w ?? "–"}</b></span>`).join("");
  const r = s.last_review || {};
  const tag = tw(r.daily);
  if (!tag || tag < heute()) $("#zahlen").insertAdjacentHTML("beforeend", `<span class="zahl warn" data-prompt="Lass uns den Tagesreview machen.">Tagesreview offen</span>`);
}
function eintrag(t) {
  const f = faellig(t);
  const meta = [esc(t.project), f && (f.ueberf ? `<span class="ueberf">fällig ${datum(f.d)}</span>` : `fällig ${datum(f.d)}`),
    esc((t.tags || []).filter((x) => x.startsWith("@")).join(" ")), t.start && "läuft"].filter(Boolean).join(" · ");
  return `<li data-uuid="${esc(t.uuid)}" class="${zustand.fokus?.uuid === t.uuid ? "gewaehlt" : ""}"><span class="t">${esc(t.description)}</span><span class="m">${meta}</span></li>`;
}
function zeigeListe() {
  const d = zustand.daten; if (!d) return;
  const filter = $("#filter").value.toLowerCase();
  const passt = (t) => !filter || (t.description + " " + (t.project || "")).toLowerCase().includes(filter);
  let html = "";
  if (zustand.liste === "heute") {
    const n = (d.naechste || []).filter(passt);
    const ueberf = n.filter((t) => faellig(t)?.ueberf), heu = n.filter((t) => faellig(t)?.heute), laeuft = n.filter((t) => t.start && !faellig(t)?.ueberf && !faellig(t)?.heute);
    const g = (titel, l) => l.length ? `<li class="gruppe">${titel} (${l.length})</li>` + l.map(eintrag).join("") : "";
    html = g("Läuft", laeuft) + g("Heute fällig", heu) + g("Überfällig", ueberf.sort((a, b) => tw(a.due) - tw(b.due)));
    if (!html) html = `<li class="gruppe">Heute nichts fällig</li>`;
  } else if (zustand.liste === "projekte") {
    html = (d.projekte || []).filter((p) => !filter || p.name.toLowerCase().includes(filter))
      .map((p) => `<li data-projekt="${esc(p.name)}"><span class="t">${esc(p.name)}</span><span class="m">${esc(p.next)} nächste · ${esc(p.waiting)} warten${p.stalled ? ' · <span class="ueberf">steht still</span>' : ""}</span></li>`).join("");
  } else {
    const quelle = { naechste: d.naechste, inbox: d.inbox, warten: d.warten }[zustand.liste] || [];
    const l = quelle.filter(passt);
    if (zustand.liste === "naechste") l.sort((a, b) => (tw(a.due) || 9e15) - (tw(b.due) || 9e15));
    html = l.map(eintrag).join("") || `<li class="gruppe">leer</li>`;
  }
  $("#liste").innerHTML = html;
}

// ---------- Fokus ----------
let fokusLauf = 0;
// still: nur anzeigen bzw. auffrischen, dem Server nichts melden (er weiß es schon)
async function setzeFokus(uuid, { still = false } = {}) {
  const lauf = ++fokusLauf;
  if (!uuid) {
    zustand.fokus = null; $("#fokus-karte").hidden = true; $("#fokus-leer").hidden = false;
    try { localStorage.removeItem("fokus"); } catch (_) {}
    if (!still) sende({ typ: "fokus", aufgabe: null });
    zeigeListe(); return;
  }
  let t;
  try { t = await api(`/api/aufgabe/${encodeURIComponent(uuid)}`); }
  catch (e) { if (!still) hinweis("Aufgabe nicht geladen: " + e.message); return; }
  if (lauf !== fokusLauf) return; // inzwischen wurde etwas anderes gewählt
  if (t.status === "completed" || t.status === "deleted") {
    if (zustand.fokus?.uuid === uuid) hinweis(`„${t.description}“ ist ${t.status === "completed" ? "erledigt" : "gelöscht"}, Fokus gelöst.`);
    return setzeFokus(null);
  }
  zustand.fokus = t;
  try { localStorage.setItem("fokus", uuid); } catch (_) {}
  $("#fokus-leer").hidden = true; $("#fokus-karte").hidden = false;
  $("#fokus-titel").textContent = t.description;
  const f = faellig(t);
  $("#fokus-meta").innerHTML = [t.project && `<span>${esc(t.project)}</span>`,
    f && `<span class="${f.ueberf ? "ueberf" : ""}">fällig ${datum(f.d)}</span>`,
    ...(t.tags || []).map((x) => `<span>${esc(x)}</span>`)].filter(Boolean).join("");
  $("#b-start").textContent = t.start ? "Stoppen" : "Starten";
  $("#fokus-notizen").innerHTML = (t.annotations || []).map((a) => `<li><small>${datum(tw(a.entry))}</small>${esc(a.description)}</li>`).join("") || `<li class="leise">Noch keine Notizen.</li>`;
  if (!still) sende({ typ: "fokus", aufgabe: { uuid: t.uuid, titel: t.description } });
  zeigeListe();
}
// Der Server meldet "aktualisieren", sobald sich die Aufgabenquelle geändert haben kann.
let aktTimer = null;
function aktualisiere() {
  clearTimeout(aktTimer);
  aktTimer = setTimeout(() => { ladeUeberblick(); if (zustand.fokus) setzeFokus(zustand.fokus.uuid, { still: true }); }, 250);
}
const versuche = (fn) => async (e) => { try { await fn(e); } catch (err) { hinweis("Fehlgeschlagen: " + err.message); } };
$("#liste").addEventListener("click", (e) => {
  const li = e.target.closest("li"); if (!li) return;
  if (li.dataset.uuid) setzeFokus(li.dataset.uuid);
  if (li.dataset.projekt) frage(`Wie steht das Projekt „${li.dataset.projekt}“, und was ist dort die nächste Aktion?`);
});
$("#b-erledigt").onclick = versuche(async () => {
  const { uuid, description: titel } = zustand.fokus;
  await api(`/api/aufgabe/${uuid}/erledigt`, { method: "POST" });
  await setzeFokus(null); ladeUeberblick();
  frage(`Ich habe „${titel}“ erledigt. Gibt es einen Nachfolger oder eine nächste Aktion dazu?`);
});
$("#b-start").onclick = versuche(async () => {
  await api(`/api/aufgabe/${zustand.fokus.uuid}/${zustand.fokus.start ? "stopp" : "start"}`, { method: "POST" });
  aktualisiere();
});
$("#b-besprechen").onclick = () => frage("Lass uns diese Aufgabe besprechen: Was ist der konkrete nächste Schritt?");
$("#b-loesen").onclick = () => setzeFokus(null);
$("#notiz-form").onsubmit = versuche(async (e) => {
  e.preventDefault(); const text = $("#notiz").value.trim(); if (!text) return;
  await api(`/api/aufgabe/${zustand.fokus.uuid}/notiz`, { method: "POST", body: JSON.stringify({ text }) });
  $("#notiz").value = ""; aktualisiere();
});

// ---------- Gespräch ----------
// Der Server führt den Verlauf: Jedes Ereignis hat eine fortlaufende Nummer (seq) und gehört zu
// einem Zug. Beim Verbinden kommt der ganze Verlauf, danach jedes neue Ereignis. Angezeigt wird
// ausschließlich in dieser Reihenfolge, deshalb sieht es nach einem Reload genauso aus wie vorher.
function verbinde() {
  const ws = new WebSocket(`ws://${location.host}/ws`);
  ws.binaryType = "blob";
  let audioFolgt = false;
  ws.onopen = () => { zustand.ws = ws; zustand.stumm = false; };
  ws.onclose = () => {
    if (zustand.ws === ws) zustand.ws = null;
    zustand.erkennt = false; status();
    setTimeout(verbinde, 1500);
  };
  ws.onmessage = (e) => {
    if (e.data instanceof Blob) { if (audioFolgt) spiele(e.data); audioFolgt = false; return; }
    let m; try { m = JSON.parse(e.data); } catch (_) { return; }
    if (m.typ === "vorleser") { zeigeVorleser(m.art); return; }
    if (m.typ === "stimmen") { pruefeStatus(); return; }
    if (m.typ === "audio") { audioFolgt = !zustand.stumm && $("#vorlesen").checked; return; }
    try { empfange(m); } catch (err) { console.error(err); }
  };
}
function empfange(m) {
  switch (m.typ) {
    case "verlauf": { // nach dem Verbinden: alles neu aufbauen
      leereVerlauf();
      zustand.nachspiel = true;
      for (const ev of m.ereignisse) { try { verarbeite(ev); } catch (err) { console.error(err); } }
      zustand.nachspiel = false;
      zustand.seq = m.seq; zustand.laeuft = m.laeuft ?? null;
      erlaubnisseSetzen(m.erlaubnisse || []);
      let lokal = zustand.fokus?.uuid; try { lokal = lokal || localStorage.getItem("fokus"); } catch (_) {}
      if (m.fokus) setzeFokus(m.fokus.uuid, { still: true });
      else if (lokal) setzeFokus(lokal);
      status(); rolle(); break;
    }
    case "erkannt": zustand.erkennt = false; if (!m.text) hinweis("Nichts verstanden."); status(); break;
    case "gestoppt": zustand.stumm = false; break;
    case "erlaubnis": anfragen.push(m); zeigeErlaubnis(); break;
    case "erlaubnis_erledigt": erlaubnisErledigt(m.id); break;
    case "aktualisieren": aktualisiere(); break;
    case "fokus": setzeFokus(m.aufgabe?.uuid || null, { still: true }); break;
    case "neu": leereVerlauf(); hinweis("Neues Gespräch."); status(); break;
    default: if (m.seq) verarbeite(m); else if (m.typ === "fehler") hinweis(m.text);
  }
}
function leereVerlauf() { $("#verlauf").innerHTML = ""; zustand.zuege.clear(); zustand.laeuft = null; zustand.seq = 0; }
function zugVon(nr) {
  if (!zustand.zuege.has(nr)) zustand.zuege.set(nr, { blase: null, letzte: null });
  return zustand.zuege.get(nr);
}
// Antwortblase des Zugs. Nach einer Nachricht des Nutzers mitten im Zug beginnt darunter eine neue.
function antwortBlase(z) {
  if (!z.blase) {
    const el = document.createElement("div"); el.className = "blase claude";
    el.innerHTML = `<details class="ablauf" hidden><summary></summary><div class="denken"></div><div class="werkzeuge"></div></details><div class="inhalt"></div><div class="info"></div>`;
    $("#verlauf").appendChild(el);
    z.blase = z.letzte = { el, text: "", denken: "", werkzeuge: 0, zuletzt: "" };
  }
  return z.blase;
}
// Gedanken und Werkzeuge stehen eingeklappt über der Antwort, nie im Antworttext.
function zeigeAblauf(b) {
  const d = b.el.querySelector(".ablauf"); d.hidden = false;
  d.querySelector("summary").textContent = [b.denken.trim() && "Gedanken",
    b.werkzeuge && `${b.werkzeuge} Werkzeug${b.werkzeuge > 1 ? "e" : ""}`, b.zuletzt].filter(Boolean).join(" · ");
}
function verarbeite(ev) {
  if (ev.seq <= zustand.seq) return; // schon gesehen
  zustand.seq = ev.seq;
  const z = ev.zug != null ? zugVon(ev.zug) : null;
  switch (ev.typ) {
    case "zug_start":
      zustand.laeuft = ev.zug;
      if (ev.ausloeser === "agent") hinweis("Claude meldet sich von selbst.");
      break;
    case "nutzer": {
      const d = document.createElement("div"); d.className = "blase uli"; d.textContent = ev.text;
      $("#verlauf").appendChild(d);
      if (z.blase) { z.blase.zuletzt = ""; if (z.blase.werkzeuge || z.blase.denken.trim()) zeigeAblauf(z.blase); }
      z.blase = null; break;
    }
    case "text": {
      if (!z.blase && !ev.text.trim()) break; // keine leere Blase für reinen Leerraum
      const b = antwortBlase(z); b.text += ev.text;
      b.el.querySelector(".inhalt").innerHTML = md(b.text.trim()); break;
    }
    case "denken": {
      if (!z.blase && !ev.text.trim()) break;
      const b = antwortBlase(z); b.denken += ev.text;
      b.el.querySelector(".denken").textContent = b.denken.trim(); zeigeAblauf(b); break;
    }
    case "werkzeug": {
      const b = antwortBlase(z); b.werkzeuge += 1; b.zuletzt = kurzname(ev.name);
      const w = document.createElement("div"); w.className = "werkzeug"; w.dataset.wid = ev.wid || ""; w.textContent = b.zuletzt;
      b.el.querySelector(".werkzeuge").appendChild(w); zeigeAblauf(b); break;
    }
    case "werkzeug_ende": {
      const w = [...$("#verlauf").querySelectorAll(".werkzeug")].reverse().find((x) => x.dataset.wid === ev.wid);
      if (w) w.classList.add(ev.fehler ? "fehler" : "fertig");
      break;
    }
    case "zug_ende": {
      if (zustand.laeuft === ev.zug) zustand.laeuft = null;
      if (z.letzte) { z.letzte.zuletzt = ""; if (z.letzte.werkzeuge || z.letzte.denken.trim()) zeigeAblauf(z.letzte); }
      const info = z.letzte?.el.querySelector(".info");
      if (info) info.textContent = `${ev.sekunden} s${ev.abgebrochen ? " · gestoppt" : ""}`;
      if (ev.fehler) hinweis(ev.fehler);
      break;
    }
    case "fehler": hinweis(ev.text); break;
  }
  if (!zustand.nachspiel) { status(); rolle(); }
}
const verbunden = () => zustand.ws?.readyState === 1;
const sende = (o) => { if (!verbunden()) return false; zustand.ws.send(JSON.stringify(o)); return true; };
const kurzname = (n) => String(n).replace(/^mcp__([^_]+)__/, "$1: ").replace(/_[a-z]+_[a-z_]+_(get|post|put)$/, "");
function hinweis(t) { $("#verlauf").insertAdjacentHTML("beforeend", `<div class="systemhinweis">${esc(t)}</div>`); if (!zustand.nachspiel) rolle(); }
const rolle = () => { const v = $("#verlauf"); v.scrollTop = v.scrollHeight; };
// Schickt eine Nachricht. Geht auch, während Claude noch antwortet; sie erscheint, sobald der Server sie einreiht.
function frage(text) {
  if (!verbunden()) { hinweis("Keine Verbindung zum Server. Die Nachricht wurde nicht gesendet."); return false; }
  stummschalten(); zustand.stumm = true;
  return sende({ typ: "frage", text });
}
// Anzeige am Mikrofonknopf, abgeleitet aus dem Zustand
function status() {
  if (rekorder) return; // während der Aufnahme bleibt "Ich höre …"
  if (zustand.erkennt) mikroZustand("denkt", "Erkenne …");
  else mikroZustand(zustand.laeuft != null ? "denkt" : "");
}

// Vorlesen: Sätze kommen einzeln als WAV und werden nacheinander abgespielt.
const warteschlange = []; let spieler = null;
function spiele(blob) { warteschlange.push(URL.createObjectURL(blob)); if (!spieler) weiter(); }
function weiter() {
  const url = warteschlange.shift(); if (!url) { spieler = null; return; }
  const a = spieler = new Audio(url);
  const fertig = () => { URL.revokeObjectURL(url); if (spieler === a) weiter(); };
  a.onended = fertig; a.onerror = fertig;
  a.play().catch(fertig);
}
function stummschalten() {
  warteschlange.splice(0).forEach((u) => URL.revokeObjectURL(u));
  if (spieler) { const a = spieler; spieler = null; a.onended = a.onerror = null; a.pause(); }
}
// Stopp: Ton sofort aus; bis der Server quittiert, wird auch unterwegs befindlicher Ton verworfen.
function stoppe() { stummschalten(); if (sende({ typ: "stopp" })) zustand.stumm = true; }
$("#stopp").onclick = stoppe;
$("#neu").onclick = () => { stummschalten(); sende({ typ: "neu" }); };
$("#vorlesen").onchange = () => { if (!$("#vorlesen").checked) stummschalten(); };
$("#text-form").onsubmit = (e) => { e.preventDefault(); const t = $("#text").value.trim(); if (t && frage(t)) $("#text").value = ""; };
document.addEventListener("click", (e) => {
  const p = e.target.closest("[data-prompt]"); if (p) frage(p.dataset.prompt);
  const l = e.target.closest(".zahl[data-liste]"); if (l) waehleListe(l.dataset.liste);
});

// Erlaubnisdialog für Werkzeuge, die Claude Code sonst im Terminal erfragen würde.
// Mehrere Anfragen werden nacheinander gezeigt. Erlaubt ist nur der ausdrückliche Klick auf "Erlauben".
const anfragen = []; let aktuelle = null, stilleSchliessungen = 0;
function zeigeErlaubnis() {
  const d = $("#erlaubnis"); if (d.open || !anfragen.length) return;
  aktuelle = anfragen[0];
  $("#erl-werkzeug").textContent = kurzname(aktuelle.werkzeug); $("#erl-eingabe").textContent = aktuelle.eingabe;
  d.returnValue = ""; // sonst gälte nach einem "Erlauben" auch Esc beim nächsten Dialog als Zustimmung
  d.showModal();
}
function schliesseStill() { const d = $("#erlaubnis"); aktuelle = null; if (d.open) { stilleSchliessungen += 1; d.close(); } }
$("#erlaubnis").addEventListener("close", () => {
  if (stilleSchliessungen > 0) { stilleSchliessungen -= 1; zeigeErlaubnis(); return; }
  const m = aktuelle; aktuelle = null;
  if (m) {
    const i = anfragen.indexOf(m); if (i >= 0) anfragen.splice(i, 1);
    sende({ typ: "erlaubnis_antwort", id: m.id, ja: $("#erlaubnis").returnValue === "ja" });
  }
  zeigeErlaubnis();
});
function erlaubnisErledigt(id) { // beantwortet (auch in einem anderen Fenster) oder abgelaufen
  const i = anfragen.findIndex((a) => a.id === id); if (i < 0) return;
  const m = anfragen.splice(i, 1)[0];
  if (aktuelle === m) schliesseStill();
}
function erlaubnisseSetzen(liste) { // Stand des Servers nach dem Verbinden
  anfragen.length = 0; anfragen.push(...liste);
  if (aktuelle) schliesseStill(); else zeigeErlaubnis();
}

// Aufnahme: Knopf oder Leertaste halten.
let rekorder = null, stueckchen = [], aufnahmeBeginn = 0;
async function aufnahmeStart() {
  if (rekorder || $("#erlaubnis").open) return;
  stoppe(); // ins Wort fallen: Vorlesen und laufende Antwort anhalten
  try {
    const strom = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true } });
    rekorder = new MediaRecorder(strom); stueckchen = []; aufnahmeBeginn = performance.now();
    rekorder.ondataavailable = (e) => e.data.size && stueckchen.push(e.data);
    rekorder.onstop = () => {
      strom.getTracks().forEach((t) => t.stop());
      const blob = new Blob(stueckchen, { type: rekorder.mimeType }); rekorder = null;
      const lang = performance.now() - aufnahmeBeginn >= 350; // kürzer ist ein Versehen, keine Sprache
      if (lang && blob.size > 2000 && verbunden()) { zustand.ws.send(blob); zustand.erkennt = true; }
      else if (lang && !verbunden()) hinweis("Keine Verbindung zum Server. Die Aufnahme wurde nicht gesendet.");
      status();
    };
    rekorder.start(); mikroZustand("nimmt");
    if (losgelassen) aufnahmeEnde(); // Taste wurde schon losgelassen, während das Mikrofon noch öffnete
  } catch (e) { hinweis("Kein Mikrofon: " + e.message); }
}
let losgelassen = true;
function aufnahmeEnde() { losgelassen = true; if (rekorder && rekorder.state === "recording") rekorder.stop(); }
function mikroZustand(z, text) {
  const b = $("#mikro"); b.className = "mikro " + (z || "");
  $("#mikro-text").textContent = text || { nimmt: "Ich höre …", denkt: "Claude denkt …" }[z] || "Halten zum Sprechen";
}
const mk = $("#mikro");
mk.addEventListener("pointerdown", () => { losgelassen = false; aufnahmeStart(); });
mk.addEventListener("pointerup", aufnahmeEnde);
mk.addEventListener("pointerleave", aufnahmeEnde);
const imFeld = (e) => ["INPUT", "TEXTAREA"].includes(e.target.tagName);
document.addEventListener("keydown", (e) => {
  const dialog = $("#erlaubnis").open; // im Dialog gehören Esc und Leertaste dem Dialog
  if (e.code === "Space" && !imFeld(e) && !dialog) { e.preventDefault(); if (!e.repeat) { losgelassen = false; aufnahmeStart(); } }
  if (e.key === "Escape" && !dialog) stoppe();
  if (e.key === "f" && !imFeld(e) && !dialog && !e.metaKey && !e.ctrlKey && !e.altKey) $("#fokusmodus").click();
});
document.addEventListener("keyup", (e) => { if (e.code === "Space" && !imFeld(e) && !$("#erlaubnis").open) { e.preventDefault(); aufnahmeEnde(); } });

// ---------- Rahmen ----------
function waehleListe(l) {
  zustand.liste = l;
  document.querySelectorAll("#reiter button").forEach((b) => b.classList.toggle("an", b.dataset.liste === l));
  zeigeListe();
}
$("#reiter").onclick = (e) => e.target.dataset.liste && waehleListe(e.target.dataset.liste);
$("#filter").oninput = zeigeListe;
$("#fokusmodus").onclick = () => document.body.classList.toggle("nurfokus");
$("#datum").textContent = new Date().toLocaleDateString("de-DE", { weekday: "long", day: "numeric", month: "long" });

// Stimme umschalten: lokal (Piper) oder eine der ElevenLabs-Stimmen (Cloud)
function fuelleVorleser(stimmen) {
  // [{wert, name, gruppe, titel}] vom Server: Piper, Stimmendienste, ElevenLabs
  if (!stimmen || !stimmen.length) return;
  const sel = $("#vorleser"), vorher = sel.value;
  sel.innerHTML = "";
  const gruppen = {};
  for (const v of stimmen) {
    let ziel = sel;
    if (v.gruppe !== "Lokal") {
      if (!gruppen[v.gruppe]) { gruppen[v.gruppe] = document.createElement("optgroup"); gruppen[v.gruppe].label = v.gruppe; sel.appendChild(gruppen[v.gruppe]); }
      ziel = gruppen[v.gruppe];
    }
    const o = document.createElement("option");
    o.value = v.wert; o.textContent = v.name; if (v.titel) o.title = v.titel;
    ziel.appendChild(o);
  }
  if (vorher) sel.value = vorher;
}
function zeigeVorleser(art) {
  if (art) $("#vorleser").value = art;
}
$("#vorleser").onchange = async (e) => {
  try { await api("/api/vorleser", { method: "POST", body: JSON.stringify({ art: e.target.value }) }); }
  catch (err) { hinweis("Stimme: " + err.message); pruefeStatus(); }
};

async function pruefeStatus() {
  try {
    const s = await api("/api/status");
    fuelleVorleser(s.stimmen);
    zeigeVorleser(s.vorleser);
    $("#punkt-sprache").className = "punkt " + (s.bereit ? "ok" : "");
    $("#punkt-sprache").title = s.bereit ? `Sprache bereit (${s.modell}, ${s.geraet}, ${s.stimme})` : "Sprachmodelle laden …";
    if (!s.bereit) setTimeout(pruefeStatus, 2000);
  } catch (_) { setTimeout(pruefeStatus, 3000); }
}

verbinde(); pruefeStatus(); ladeUeberblick();
setInterval(ladeUeberblick, 120000); // Rückfall; sonst meldet der Server Änderungen ("aktualisieren")
// Der Fokus kommt nach dem Verbinden vom Server, ersatzweise aus dem localStorage (siehe "verlauf").

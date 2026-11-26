// Cockpit-Leser: zeigt Ordner, Markdown (mit Mermaid und Chart.js), HTML-Seiten, PDFs und Bilder.
// Navigation über den Hash (#pfad=…), damit HarnoRb den Leser im Rahmen steuern kann.
"use strict";
const $ = (s) => document.querySelector(s);
const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const SYM = { ordner: "📁", md: "📄", html: "🌐", pdf: "📕", bild: "🖼️", text: "📃", datei: "📦" };
const inhalt = $("#inhalt");

mermaid.initialize({ startOnLoad: false, theme: "dark", securityLevel: "strict", fontFamily: "Inter, system-ui, sans-serif",
  themeVariables: { primaryColor: "#2a2440", primaryBorderColor: "#b9a6ff", lineColor: "#9a97ad", primaryTextColor: "#e9e6f2" } });
Chart.defaults.color = "#cfcbe0"; Chart.defaults.borderColor = "rgba(255,255,255,.09)";
Chart.defaults.font.family = "Inter, system-ui, sans-serif";

function pfadAusHash() { return decodeURIComponent((location.hash.match(/pfad=([^&]*)/) || [])[1] || ""); }
function geheZu(pfad) { location.hash = "pfad=" + encodeURIComponent(pfad); }
const roh = (p) => "/roh/" + p.split("/").map(encodeURIComponent).join("/");
function ordnerVon(p) { return p.includes("/") ? p.slice(0, p.lastIndexOf("/")) : ""; }
function loese(basis, ziel) { // relativer Link in einer Cockpit-Datei -> Cockpit-Pfad
  const teile = (basis ? basis.split("/") : []);
  for (const t of ziel.split("/")) { if (t === "..") teile.pop(); else if (t && t !== ".") teile.push(t); }
  return teile.join("/");
}

function zeigePfad(p) {
  const teile = p ? p.split("/") : [];
  let acc = "";
  const links = [`<a href="#pfad=">Cockpit</a>`];
  for (const t of teile) { acc = acc ? acc + "/" + t : t; links.push(`<span>/</span><a href="#pfad=${encodeURIComponent(acc)}">${esc(t)}</a>`); }
  $("#pfad").innerHTML = links.join("");
}

async function lade() {
  const pfad = pfadAusHash();
  zeigePfad(pfad);
  $("#roh").hidden = true;
  inhalt.className = "inhalt";
  for (const c of Object.values(Chart.instances)) c.destroy(); // sonst bleiben alte Grafiken samt Beobachtern im Speicher
  inhalt.innerHTML = `<p class="leer">Lädt …</p>`;
  fetch("/api/leser", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ pfad }) }).catch(() => {});
  let d;
  try {
    const r = await fetch("/api/datei?pfad=" + encodeURIComponent(pfad));
    d = await r.json();
    if (!r.ok) throw new Error(d.detail || r.statusText);
  } catch (e) { inhalt.innerHTML = `<p class="leer">${esc(e.message)}</p>`; return; }
  document.title = (d.name || "Cockpit") + " – Cockpit-Leser";
  if (d.art !== "ordner") { $("#roh").href = roh(d.pfad); $("#roh").hidden = false; }
  switch (d.art) {
    case "ordner": return zeigeOrdner(d);
    case "md": return zeigeMarkdown(d);
    case "html": inhalt.className = "inhalt breit"; inhalt.innerHTML = `<iframe class="seite" sandbox="allow-scripts allow-popups" src="${roh(d.pfad)}" title="${esc(d.name)}"></iframe>`; return;
    case "pdf": inhalt.className = "inhalt breit"; inhalt.innerHTML = `<iframe src="${roh(d.pfad)}" title="${esc(d.name)}"></iframe>`; return;
    case "bild": inhalt.innerHTML = `<div class="bild"><img src="${roh(d.pfad)}" alt="${esc(d.name)}"></div>`; return;
    case "text": inhalt.innerHTML = `<div class="textdatei">${esc(d.inhalt)}</div>`; return;
    default: inhalt.innerHTML = `<p class="leer">Dieses Format zeige ich nicht an. <a href="${roh(d.pfad)}" download>Herunterladen</a></p>`;
  }
}

function zeigeOrdner(d) {
  const zeilen = d.eintraege.map((e) => `<a href="#pfad=${encodeURIComponent(e.pfad)}"><span class="sym">${SYM[e.art] || "📦"}</span>
    <span>${esc(e.name)}</span><span class="neben">${e.groesse != null ? groesse(e.groesse) : ""}</span></a>`);
  inhalt.innerHTML = `<div class="liste">${zeilen.join("") || '<p class="leer">Leer.</p>'}</div>`;
}
function groesse(b) { return b < 1024 ? b + " B" : b < 1048576 ? Math.round(b / 1024) + " KB" : (b / 1048576).toFixed(1) + " MB"; }

function frontmatter(text) {
  const m = text.match(/^---\n([\s\S]*?)\n---\n?/);
  if (!m) return [{}, text];
  const meta = {};
  for (const z of m[1].split("\n")) { const i = z.indexOf(":"); if (i > 0) meta[z.slice(0, i).trim()] = z.slice(i + 1).trim().replace(/^"|"$/g, ""); }
  return [meta, text.slice(m[0].length)];
}

let zaehler = 0;
async function zeigeMarkdown(d) {
  const [meta, text] = frontmatter(d.inhalt);
  const chips = ["type", "status", "date", "data_class"].filter((k) => meta[k]).map((k) => `<span class="${esc(meta[k])}">${esc(meta[k])}</span>`);
  if (meta.tags && meta.tags !== "[]") chips.push(`<span>${esc(meta.tags)}</span>`);
  const html = DOMPurify.sanitize(marked.parse(text, { gfm: true }), { ADD_ATTR: ["target"] });
  inhalt.innerHTML = (chips.length ? `<div class="meta">${chips.join("")}</div>` : "") + `<article class="doc">${html}</article>`;
  const basis = ordnerVon(d.pfad);
  for (const a of inhalt.querySelectorAll("a[href]")) {
    const h = a.getAttribute("href");
    if (/^(https?:|mailto:)/.test(h)) { a.target = "_blank"; a.rel = "noopener"; }
    else if (!h.startsWith("#")) a.href = "#pfad=" + encodeURIComponent(loese(basis, decodeURIComponent(h.split("#")[0])));
  }
  for (const img of inhalt.querySelectorAll("img[src]")) {
    const s = img.getAttribute("src");
    if (!/^(https?:|data:)/.test(s)) img.src = roh(loese(basis, decodeURIComponent(s)));
  }
  for (const code of inhalt.querySelectorAll("pre > code.language-mermaid")) {
    const box = document.createElement("div"); box.className = "diagramm";
    code.parentElement.replaceWith(box);
    const id = "m" + ++zaehler;
    try { const { svg } = await mermaid.render(id, code.textContent); box.innerHTML = svg; } // securityLevel strict: Mermaid bereinigt selbst
    catch (e) { box.innerHTML = `<div class="fehler">Diagramm fehlerhaft: ${esc(e.message || e)}</div>`; }
    finally { document.getElementById("d" + id)?.remove(); } // Mermaid lässt bei Fehlern seine Zeichenfläche im body liegen
  }
  for (const code of inhalt.querySelectorAll("pre > code.language-chart")) {
    const box = document.createElement("div"); box.className = "diagramm chart";
    code.parentElement.replaceWith(box);
    try {
      const cfg = JSON.parse(code.textContent);
      cfg.options = { responsive: true, maintainAspectRatio: false, ...(cfg.options || {}) };
      const c = document.createElement("canvas"); box.appendChild(c); new Chart(c, cfg);
    } catch (e) { box.innerHTML = `<div class="fehler">Grafik fehlerhaft: ${esc(e.message)}</div>`; }
  }
}

$("#suche").addEventListener("submit", async (e) => {
  e.preventDefault();
  const q = $("#q").value.trim(); if (!q) return;
  const r = await (await fetch("/api/dateisuche?q=" + encodeURIComponent(q))).json();
  zeigePfad(""); $("#roh").hidden = true; inhalt.className = "inhalt";
  inhalt.innerHTML = `<h3>Suche „${esc(q)}“</h3><div class="liste">${r.treffer.map((t) => `<a href="#pfad=${encodeURIComponent(t.pfad)}">
    <span class="sym">${SYM[t.art] || "📦"}</span><span>${esc(t.name)}</span><span class="neben"></span><span class="unter">${esc(t.pfad)}</span></a>`).join("") || '<p class="leer">Nichts gefunden.</p>'}</div>`;
});

// Steuerung von außen (HarnoRb): {leser: "runter" | "hoch" | "oben" | "unten"}
window.addEventListener("message", (e) => {
  if (e.origin !== location.origin || !e.data || !e.data.leser) return;
  const seite = window.innerHeight * 0.8;
  const ziel = { runter: [0, seite], hoch: [0, -seite] }[e.data.leser];
  if (ziel) window.scrollBy({ top: ziel[1], behavior: "smooth" });
  if (e.data.leser === "oben") window.scrollTo({ top: 0, behavior: "smooth" });
  if (e.data.leser === "unten") window.scrollTo({ top: document.body.scrollHeight, behavior: "smooth" });
});
window.addEventListener("hashchange", () => { window.scrollTo(0, 0); lade(); });
// Tasten der Szene (Leertaste zum Sprechen, Listen, L, Esc …) an HarnoRb weitergeben. Sonst bleiben sie hier hängen,
// sobald der Leser den Fokus hat, auch noch nachdem er geschlossen ist. Blättern und Links bleiben im Leser.
const EIGENE = new Set(["ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight", "PageUp", "PageDown", "Home", "End", "Tab", "Enter"]);
for (const typ of ["keydown", "keyup"]) document.addEventListener(typ, (e) => {
  if (e.target.matches("input, textarea, select") || e.metaKey || e.ctrlKey || e.altKey || EIGENE.has(e.key)) return;
  if (e.code === "Space") e.preventDefault(); // nicht blättern: Leertaste heißt Sprechen
  parent.postMessage({ leser: "taste", typ, key: e.key, code: e.code, repeat: e.repeat, shift: e.shiftKey }, location.origin);
});
lade();

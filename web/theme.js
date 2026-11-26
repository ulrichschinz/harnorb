// Themes im Browser: CSS-Variablen setzen und Hauptfarben aus einem Bild holen.
// Das Theme kommt vom Server (GET /api/theme, Ereignis „theme“), Aufbau siehe src/cockpit_ui/themes.py.
// Kern und Module lesen nur die CSS-Variablen; Kugel und Hintergrund bekommen ihre Werte in main.js.

// Szene: Variablen aus szene.css
export function szeneVariablen(t) {
  const f = t.farben || {}, v = (t.verlauf || []).filter(Boolean);
  const vars = {};
  for (const k of ["grund", "flaeche", "tief", "text", "akzent", "hinweis", "nutzer", "ok", "warn"]) if (f[k]) vars["--" + k] = f[k];
  if (v.length >= 3) vars["--irid"] = `conic-gradient(from var(--w, 0deg), ${[...v, v[0]].join(", ")})`;
  if (t.schrift) {
    vars["--schrift"] = `${t.schrift}, "SF Pro Display", -apple-system, system-ui, sans-serif`;
    vars["--schmal"] = `${t.schrift}, "SF Pro Text", -apple-system, system-ui, sans-serif`;
  }
  return vars;
}

// Leser: eigene, ruhigere Variablen (leser.css). Das Standard-Theme lässt den Leser, wie er ist.
export function leserVariablen(t) {
  if (!t || t.id === "harnorb") return {};
  const f = t.farben || {}, mix = (a, p, b) => `color-mix(in srgb, ${a} ${p}%, ${b})`;
  return {
    "--grund": f.tief, "--flaeche": mix(f.flaeche, 35, f.tief), "--code": mix(f.flaeche, 25, f.tief),
    "--linie": mix(f.text, 10, "transparent"), "--text": f.text, "--leise": mix(f.text, 62, f.tief),
    "--akzent": f.akzent, "--akzent2": (t.verlauf || [])[1] || f.akzent, "--ok": f.ok, "--warn": f.warn,
  };
}

const gesetzt = new WeakMap();   // Element -> Namen, die zuletzt gesetzt wurden (zum Zurücksetzen)
export function setzeVariablen(vars, el = document.documentElement) {
  for (const n of gesetzt.get(el) || []) if (!(n in vars)) el.style.removeProperty(n);
  for (const [n, w] of Object.entries(vars)) if (w) el.style.setProperty(n, w);
  gesetzt.set(el, Object.keys(vars));
}

export async function ladeTheme() {
  const r = await fetch("/api/theme");
  if (!r.ok) throw new Error("Theme nicht geladen (" + r.status + ")");
  return r.json();
}

// ---------- Hauptfarben eines Bildes (k-means im Lab-ähnlichen Raum, klein gerechnet) ----------

function zuHex(r, g, b) { return "#" + [r, g, b].map((x) => Math.round(Math.max(0, Math.min(255, x))).toString(16).padStart(2, "0")).join(""); }

export async function bildLaden(datei) {
  const url = URL.createObjectURL(datei);
  try {
    const img = new Image();
    img.src = url;
    await img.decode();
    return img;
  } finally { setTimeout(() => URL.revokeObjectURL(url), 1000); }
}

// -> [{farbe: "#rrggbb", anteil: 0..1}], häufigste zuerst
export function palette(img, n = 8) {
  const s = 96, k = Math.min(1, s / Math.max(img.naturalWidth, img.naturalHeight));
  const c = document.createElement("canvas");
  c.width = Math.max(1, Math.round(img.naturalWidth * k)); c.height = Math.max(1, Math.round(img.naturalHeight * k));
  const ctx = c.getContext("2d", { willReadFrequently: true });
  ctx.drawImage(img, 0, 0, c.width, c.height);
  const d = ctx.getImageData(0, 0, c.width, c.height).data;
  const px = [];
  for (let i = 0; i < d.length; i += 4) if (d[i + 3] > 200) px.push([d[i], d[i + 1], d[i + 2]]);
  if (!px.length) return [];
  // Start: gleichmäßig verteilte Pixel nach Helligkeit sortiert, dann 12 Runden k-means
  const sortiert = [...px].sort((a, b) => (a[0] + a[1] + a[2]) - (b[0] + b[1] + b[2]));
  let mitten = Array.from({ length: n }, (_, i) => [...sortiert[Math.floor((i + 0.5) * sortiert.length / n)]]);
  let zuordnung = new Uint8Array(px.length);
  for (let runde = 0; runde < 12; runde++) {
    const summe = mitten.map(() => [0, 0, 0, 0]);
    px.forEach((p, i) => {
      let best = 0, bd = Infinity;
      mitten.forEach((m, j) => { const dr = p[0] - m[0], dg = p[1] - m[1], db = p[2] - m[2]; const dd = 2 * dr * dr + 4 * dg * dg + 3 * db * db; if (dd < bd) { bd = dd; best = j; } });
      zuordnung[i] = best; const z = summe[best]; z[0] += p[0]; z[1] += p[1]; z[2] += p[2]; z[3]++;
    });
    mitten = summe.map((z, j) => (z[3] ? [z[0] / z[3], z[1] / z[3], z[2] / z[3]] : mitten[j]));
  }
  const zahl = mitten.map(() => 0);
  zuordnung.forEach((j) => zahl[j]++);
  return mitten.map((m, j) => ({ farbe: zuHex(...m), anteil: zahl[j] / px.length }))
    .filter((x) => x.anteil > 0.004).sort((a, b) => b.anteil - a.anteil);
}

// Verkleinertes JPEG für Claude (lange Seite höchstens max Pixel)
export function verkleinert(img, max = 1024) {
  const k = Math.min(1, max / Math.max(img.naturalWidth, img.naturalHeight));
  const c = document.createElement("canvas");
  c.width = Math.max(1, Math.round(img.naturalWidth * k)); c.height = Math.max(1, Math.round(img.naturalHeight * k));
  c.getContext("2d").drawImage(img, 0, 0, c.width, c.height);
  return c.toDataURL("image/jpeg", 0.85);
}

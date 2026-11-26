// Kleine Tween-Funktion: keine Abhängigkeit, läuft im Takt der Bühne (tick).
export const ease = {
  linear: (t) => t,
  inCubic: (t) => t * t * t,
  outCubic: (t) => 1 - (1 - t) ** 3,
  inOutCubic: (t) => (t < 0.5 ? 4 * t * t * t : 1 - (-2 * t + 2) ** 3 / 2),
  outBack: (t) => { const c1 = 1.70158, c3 = c1 + 1; return 1 + c3 * (t - 1) ** 3 + c1 * (t - 1) ** 2; },
  inBack: (t) => { const c1 = 1.70158, c3 = c1 + 1; return c3 * t * t * t - c1 * t * t; },
  outExpo: (t) => (t === 1 ? 1 : 1 - 2 ** (-10 * t)),
  inExpo: (t) => (t === 0 ? 0 : 2 ** (10 * t - 10)),
  outElastic: (t) => (t === 0 || t === 1 ? t : 2 ** (-10 * t) * Math.sin((t * 10 - 0.75) * (2 * Math.PI) / 3) + 1),
};

const laufend = new Set();
let tempo = 1; // < 1 bei reduzierter Bewegung nicht nötig, aber für Tests nützlich

export function setzeTempo(t) { tempo = t; }

// tween({ dauer, verzoegerung, ease, update(w, t), fertig() }) -> { stop(), fertig: Promise }
export function tween({ dauer = 600, verzoegerung = 0, ease: e = ease.outCubic, update, fertig } = {}) {
  let aufloesen;
  const t = {
    start: performance.now() + verzoegerung / tempo, dauer: Math.max(1, dauer / tempo), e, update, fertigFn: fertig,
    aktiv: true, versprechen: new Promise((r) => { aufloesen = r; }),
  };
  t.aufloesen = aufloesen;
  laufend.add(t);
  return { stop: () => { if (t.aktiv) { t.aktiv = false; laufend.delete(t); t.aufloesen(false); } }, laeuft: () => t.aktiv, fertig: t.versprechen };
}

export function tick(jetzt) {
  for (const t of [...laufend]) {
    if (jetzt < t.start) continue;
    const roh = Math.min(1, (jetzt - t.start) / t.dauer);
    try { t.update?.(t.e(roh), roh); } catch (err) { console.error(err); }
    if (roh >= 1) {
      laufend.delete(t); t.aktiv = false;
      try { t.fertigFn?.(); } catch (err) { console.error(err); }
      t.aufloesen(true);
    }
  }
}

export const warte = (ms) => new Promise((r) => setTimeout(r, ms / tempo));
export const lerp = (a, b, t) => a + (b - a) * t;
export const klemme = (x, a = 0, b = 1) => Math.max(a, Math.min(b, x));
// Weiches Annähern, unabhängig von der Bildrate
export const naeher = (ist, ziel, rate, dt) => ziel + (ist - ziel) * Math.exp(-rate * dt);

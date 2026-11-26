// Browser-Teil des Beispielmoduls zettel: Kartenart „zettel“ (Haftnotiz) und Effekt „zerknuellen“.
// Schnittstelle: web/szene/erweiterungen.js im Kern.
export default function registriere(harnorb) {
  if (harnorb.version !== 1) throw new Error(`zettel kennt Schnittstelle 1, nicht ${harnorb.version}`);

  harnorb.stil(`
    .karte.zettel { background: var(--zettel, #fff3a8); color: #3a3320; border: none; border-radius: 3px;
      box-shadow: 0 12px 26px rgba(0,0,0,.45); font-family: "Bradley Hand", "Segoe Print", cursive; }
    .karte.zettel .titel { font-family: inherit; font-size: 17px; color: #3a3320; }
    .karte.zettel .nr { background: #3a3320; color: #fff3a8; }
    .karte.zettel .meta { color: #6b5f3a; }
    .fokuskarte.zettel { background: var(--zettel, #fff3a8); color: #3a3320; font-family: "Bradley Hand", "Segoe Print", cursive; }
    .fokuskarte.zettel h1 { color: #3a3320; font-family: inherit; }
    .fokuskarte.zettel .marke { color: #6b5f3a; background: rgba(58, 51, 32, .08); }
    .fokuskarte.zettel .hinweise { color: #6b5f3a; background: none; }
    .fokuskarte.zettel kbd { color: #3a3320; border-color: #6b5f3a; }
  `);

  const zeichne = (el, k, h) => {
    el.style.setProperty("--zettel", k.anzeige?.daten?.farbe || "#fff3a8");
    el.innerHTML = `<div class="nr">${k.nr}</div><div class="inhalt"><div class="titel">${h.esc(k.titel)}</div>
      <div class="meta">${h.meta(k) || "Zettel"}</div></div>`;
  };
  harnorb.kartenArt("zettel", {
    klasse: "zettel",
    karte: zeichne,
    fokus: (el, k, h) => {
      el.style.setProperty("--zettel", k.anzeige?.daten?.farbe || "#fff3a8");
      el.innerHTML = `<div class="kopf"><span class="marke">Zettel im Fokus</span></div><h1>${h.esc(k.titel)}</h1>
        <div class="hinweise"><kbd>E</kbd> erledigt · <kbd>X</kbd> ausblenden</div>`;
    },
  });

  // Erledigt: Zettel zerknüllt sich, fällt und verschwindet mit Funken in der Kugel
  harnorb.effekt("zerknuellen", async ({ eintrag: e, fx, kugelPos, tween, ease }) => {
    fx.ton.whoosh();
    const p0 = e.basis.clone(), r0 = e.rot.clone();
    await tween({ dauer: 350, ease: ease.outCubic, update: (w) => { e.skala = 1 - w * 0.55; e.rot.z = r0.z + w * 0.9; } }).fertig;
    const ziel = kugelPos();
    await tween({ dauer: 700, ease: ease.inOutCubic, update: (w) => {
      e.basis.copy(p0).lerp(ziel, w); e.basis.y += Math.sin(w * Math.PI) * 0.7;
      e.rot.set(r0.x + w * 4, r0.y + w * 2, r0.z + w * 6); e.skala = 0.45 * (1 - w * 0.9);
      e.op = 1 - Math.max(0, w - 0.7) * 3.3;
      fx.funken(e.basis, 1);
    } }).fertig;
  });
}

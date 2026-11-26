// Freisprechen: Das Mikrofon bleibt offen, eine einfache Sprachpegel-Erkennung (VAD) merkt, wann
// gesprochen wird, und schickt jede Äußerung nach einer kurzen Pause als WAV an den Server.
// Erste Fassung ohne Modell: adaptiver Rauschpegel, Mindestdauer, Vorlauf. Whisper (vad_filter)
// und der Filter für erfundene Sätze auf dem Server sortieren Fehlauslöser aus.
// Während HarnoRb spricht, hört es nicht zu (noch kein Dazwischenreden).

export const STANDARD = {
  pauseMs: 900,        // so lange Stille beendet eine Äußerung
  startMs: 90,         // so lange über der Schwelle, bis es als Sprechen zählt
  mindestMs: 350,      // kürzere Äußerungen (Klopfen, Husten) verwerfen
  vorlaufMs: 400,      // Audio vor dem erkannten Beginn mitschicken (erste Silbe)
  maxMs: 60000,        // spätestens dann abschicken
  nachlaufMs: 700,     // nach dem Vorlesen so lange taub (Nachhall)
  faktor: 3.2,         // Schwelle = Rauschpegel × faktor
  minSchwelle: 0.012,  // absolute Untergrenze (RMS)
  fensterMs: 4000,     // über dieses Fenster wird der Rauschpegel geschätzt
};

export function wav16k(teile, rate) {
  // Float32-Stücke bei `rate` -> 16 kHz mono 16-bit WAV (lineare Interpolation reicht für Sprache)
  let laenge = 0; for (const t of teile) laenge += t.length;
  const alles = new Float32Array(laenge); let o = 0;
  for (const t of teile) { alles.set(t, o); o += t.length; }
  const schritt = rate / 16000, n = Math.floor(alles.length / schritt);
  const buf = new ArrayBuffer(44 + n * 2), v = new DataView(buf);
  const s = (p, t) => { for (let i = 0; i < t.length; i++) v.setUint8(p + i, t.charCodeAt(i)); };
  s(0, "RIFF"); v.setUint32(4, 36 + n * 2, true); s(8, "WAVE"); s(12, "fmt ");
  v.setUint32(16, 16, true); v.setUint16(20, 1, true); v.setUint16(22, 1, true);
  v.setUint32(24, 16000, true); v.setUint32(28, 32000, true); v.setUint16(32, 2, true); v.setUint16(34, 16, true);
  s(36, "data"); v.setUint32(40, n * 2, true);
  for (let i = 0; i < n; i++) {
    const x = i * schritt, j = Math.floor(x), f = x - j;
    const a = alles[j] ?? 0, b = alles[j + 1] ?? a;
    const w = Math.max(-1, Math.min(1, a + (b - a) * f));
    v.setInt16(44 + i * 2, w < 0 ? w * 0x8000 : w * 0x7fff, true);
  }
  return new Blob([buf], { type: "audio/wav" });
}

// Reine Entscheidungslogik, damit sie ohne Mikrofon testbar ist. füttere(rms, ms) -> "start" | "ende" | "verwerfen" | null
export class Pegelwaechter {
  constructor(o = {}) { this.o = { ...STANDARD, ...o }; this.rauschen = 0.004; this.verlauf = []; this.zurueck(); }
  zurueck() { this.spricht = false; this.ueber = 0; this.still = 0; this.dauer = 0; this.stimmhaft = 0; }
  get schwelle() { return Math.max(this.o.minSchwelle, this.rauschen * this.o.faktor); }
  _rauschen(rms, ms) {
    // Rauschpegel = leisester Rand (5 %) der letzten Sekunden. Sprache hat Lücken zwischen Wörtern,
    // gleichmäßiges Rauschen (Lüfter, Musik) hebt den Rand dagegen an und beendet so eine Dauer-„Äußerung“.
    this.verlauf.push(rms);
    const max = Math.round(this.o.fensterMs / ms); if (this.verlauf.length > max) this.verlauf.shift();
    if (this.verlauf.length < 10) return;
    const sortiert = [...this.verlauf].sort((x, y) => x - y);
    this.rauschen = sortiert[Math.floor(sortiert.length * 0.05)];
  }
  fuettere(rms, ms) {
    this._rauschen(rms, ms);
    const laut = rms > this.schwelle;
    if (!this.spricht) {
      this.ueber = laut ? this.ueber + ms : 0;
      if (this.ueber >= this.o.startMs) { this.spricht = true; this.dauer = this.ueber; this.stimmhaft = this.ueber; this.still = 0; return "start"; }
      return null;
    }
    this.dauer += ms;
    if (laut) { this.still = 0; this.stimmhaft += ms; } else this.still += ms;
    if (this.still >= this.o.pauseMs || this.dauer >= this.o.maxMs) {
      const gut = this.stimmhaft >= this.o.mindestMs;
      this.zurueck();
      return gut ? "ende" : "verwerfen";
    }
    return null;
  }
}

export class Freisprechen {
  // g: Gespraech (audio(), verbunden, ws, spricht, erkennt); darf(): ob gerade zugehört werden soll
  constructor(g, { darf = () => true, melde = () => {}, optionen = {} } = {}) {
    this.g = g; this.darf = darf; this.melde = melde;
    this.waechter = new Pegelwaechter(optionen);
    this.an = false; this.hoert = false; this.taubBis = 0;
    this.strom = null; this.knoten = null; this.quelle = null;
    this.vorlauf = []; this.vorlaufLaenge = 0; this.teile = [];
    this.analyser = null; this.daten = null;
  }

  async starte() {
    if (this.an) return true;
    const ctx = this.g.audio();
    if (!ctx) throw new Error("Kein Audio im Browser.");
    if (ctx.state !== "running") await ctx.resume().catch(() => {});
    if (!this._modul) {
      await ctx.audioWorklet.addModule(new URL("./abgriff-worklet.js", import.meta.url)); this._modul = true;
    }
    this.strom = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true } });
    this.quelle = ctx.createMediaStreamSource(this.strom);
    this.knoten = new AudioWorkletNode(ctx, "harno-abgriff");
    this.knoten.port.onmessage = (e) => this._stueck(e.data, ctx.sampleRate);
    this.quelle.connect(this.knoten);
    const stumm = ctx.createGain(); stumm.gain.value = 0; this.knoten.connect(stumm).connect(ctx.destination); // Worklet muss am Graphen hängen
    this.analyser = ctx.createAnalyser(); this.analyser.fftSize = 1024; this.daten = new Float32Array(1024);
    this.quelle.connect(this.analyser);
    this.rate = ctx.sampleRate; this.an = true; this.waechter.zurueck();
    return true;
  }

  stoppe() {
    if (!this.an) return;
    this.an = false;
    if (this.hoert) { this.hoert = false; this.melde("aus"); }
    try { this.quelle?.disconnect(); this.knoten?.disconnect(); } catch (_) { /* egal */ }
    this.strom?.getTracks().forEach((t) => t.stop());
    this.strom = this.quelle = this.knoten = this.analyser = null;
    this.teile = []; this.vorlauf = []; this.vorlaufLaenge = 0;
  }

  _stueck(f, rate) {
    if (!this.an) return;
    const ms = (f.length / rate) * 1000;
    // taub, solange HarnoRb spricht, erkannt wird oder es gerade nicht passt
    if (this.g.spricht) this.taubBis = performance.now() + this.waechter.o.nachlaufMs;
    const taub = this.g.spricht || this.g.erkennt || performance.now() < this.taubBis || !this.darf();
    if (taub) {
      if (this.hoert) { this.hoert = false; this.teile = []; this.waechter.zurueck(); this.melde("aus"); }
      this.vorlauf = []; this.vorlaufLaenge = 0;
      return;
    }
    let s = 0; for (let i = 0; i < f.length; i++) s += f[i] * f[i];
    const ereignis = this.waechter.fuettere(Math.sqrt(s / f.length), ms);
    if (this.hoert) this.teile.push(f);
    else {
      this.vorlauf.push(f); this.vorlaufLaenge += f.length;
      const max = (this.waechter.o.vorlaufMs / 1000) * rate;
      while (this.vorlaufLaenge - this.vorlauf[0].length > max) this.vorlaufLaenge -= this.vorlauf.shift().length;
    }
    if (ereignis === "start") {
      this.hoert = true; this.teile = this.vorlauf; this.vorlauf = []; this.vorlaufLaenge = 0;
      this.melde("an");
    } else if (ereignis === "ende" || ereignis === "verwerfen") {
      const teile = this.teile; this.teile = []; this.hoert = false;
      this.melde("aus");
      if (ereignis === "ende") this._sende(wav16k(teile, rate));
    }
  }

  _sende(blob) {
    if (!this.g.verbunden) { this.melde("fehler", "Keine Verbindung zum Server. Die Aufnahme wurde nicht gesendet."); return; }
    this.g.stummschalten();
    this.g.ws.send(blob); this.g.erkennt = true;
    this.melde("gesendet");
  }

  pegel() { // Mikrofonpegel 0..1 für die Kugel
    if (!this.analyser || !this.hoert) return 0;
    this.analyser.getFloatTimeDomainData(this.daten);
    let s = 0; for (let i = 0; i < this.daten.length; i++) s += this.daten[i] * this.daten[i];
    return Math.min(1, Math.sqrt(s / this.daten.length) * 9);
  }
}

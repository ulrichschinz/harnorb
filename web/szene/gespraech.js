// Gespräch: WebSocket zum Server, Vorlesen mit Pegel (AnalyserNode), Aufnahme mit Mikrofonpegel.
// Die Logik entspricht der klassischen Oberfläche (app.js): Der Server führt den Verlauf mit seq.

export async function api(pfad, opt = {}) {
  const r = await fetch(pfad, { headers: { "Content-Type": "application/json" }, ...opt });
  if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || r.statusText);
  return r.json();
}

export class Gespraech {
  constructor(h = {}) {
    this.h = h;               // Rückrufe: verlauf, ereignis, fluechtig, verbindung, audioStart, audioEnde, aufnahme
    this.ws = null;
    this.seq = 0;
    this.laeuft = null;
    this.stumm = false;
    this.erkennt = false;
    this.vorlesen = true;
    this.ctx = null; this.analyser = null; this.daten = null;
    this.warteschlange = []; this.quellen = new Set(); this.ende = 0; this.spricht = false;
    this.rekorder = null; this.stueckchen = []; this.aufnahmeBeginn = 0; this.losgelassen = true;
    this.micAnalyser = null; this.micDaten = null;
    this._pegel = 0; this._mic = 0;
  }

  // ---------- Verbindung ----------

  verbinde() {
    const ws = new WebSocket(`ws://${location.host}/ws`);
    ws.binaryType = "blob";
    let audioFolgt = false;
    ws.onopen = () => { this.ws = ws; this.stumm = false; this.h.verbindung?.(true); };
    ws.onclose = () => {
      if (this.ws === ws) this.ws = null;
      this.erkennt = false;
      this.h.verbindung?.(false);
      setTimeout(() => this.verbinde(), 1500);
    };
    ws.onmessage = (e) => {
      if (e.data instanceof Blob) { if (audioFolgt) this.spiele(e.data); audioFolgt = false; return; }
      let m; try { m = JSON.parse(e.data); } catch (_) { return; }
      if (m.typ === "audio") { audioFolgt = !this.stumm && this.vorlesen; return; }
      try { this._empfange(m); } catch (err) { console.error(err); }
    };
  }

  _empfange(m) {
    if (m.typ === "verlauf") {
      this.seq = 0;
      this.h.verlauf?.(m);
      for (const ev of m.ereignisse) this._verarbeite(ev, true);
      this.seq = m.seq; this.laeuft = m.laeuft ?? null;
      this.h.nachVerlauf?.(m);
      return;
    }
    if (m.typ === "erkannt") this.erkennt = false;
    if (m.typ === "gestoppt") this.stumm = false;
    if (m.typ === "neu") { this.laeuft = null; this.seq = 0; }
    if (m.seq) return this._verarbeite(m, false);
    this.h.fluechtig?.(m);
  }

  _verarbeite(ev, nachspiel) {
    if (ev.seq <= this.seq) return;
    this.seq = ev.seq;
    if (ev.typ === "zug_start") this.laeuft = ev.zug;
    if (ev.typ === "zug_ende" && this.laeuft === ev.zug) this.laeuft = null;
    this.h.ereignis?.(ev, nachspiel);
  }

  get verbunden() { return this.ws?.readyState === 1; }
  sende(o) { if (!this.verbunden) return false; this.ws.send(JSON.stringify(o)); return true; }

  frage(text) {
    if (!this.verbunden) return false;
    this.stummschalten(); this.stumm = true;
    return this.sende({ typ: "frage", text });
  }

  stoppe() { this.stummschalten(); if (this.sende({ typ: "stopp" })) this.stumm = true; }
  neu() { this.stummschalten(); this.sende({ typ: "neu" }); }
  szene(aktion, args = {}) { return this.sende({ typ: "szene_befehl", aktion, args }); }

  // ---------- Vorlesen ----------

  audio() { // AudioContext erst nach einer Geste des Nutzers (Autoplay-Regeln)
    if (!this.ctx) {
      try {
        this.ctx = new AudioContext();
        this.analyser = this.ctx.createAnalyser();
        this.analyser.fftSize = 1024;
        this.analyser.smoothingTimeConstant = 0.6;
        this.analyser.connect(this.ctx.destination);
        this.daten = new Float32Array(this.analyser.fftSize);
      } catch (_) { this.ctx = null; }
    }
    if (this.ctx?.state === "suspended") this.ctx.resume().then(() => this._weiter()).catch(() => {});
    return this.ctx;
  }

  spiele(blob) {
    this.warteschlange.push(blob);
    this._weiter();
  }

  // Jeder Teil wird sofort dekodiert und direkt hinter den vorigen gelegt (ctx-Zeit), damit
  // gestreamte Teile eines Satzes ohne Lücke aneinander anschließen.
  async _weiter() {
    if (this._dekodiert) return;
    const blob = this.warteschlange.shift();
    if (!blob) { this._fertig(); return; }
    const ctx = this.audio();
    if (!ctx || ctx.state !== "running") { // noch keine Geste: warten, bis der AudioContext läuft
      this.warteschlange.unshift(blob);
      if (ctx && !this._hinweisGegeben) { this._hinweisGegeben = true; this.h.brauchtGeste?.(); }
      return;
    }
    this._dekodiert = true;
    const runde = this._runde = (this._runde || 0) + 1;
    let puffer = null;
    try { puffer = await ctx.decodeAudioData(await blob.arrayBuffer()); } catch (_) { /* Teil überspringen */ }
    if (runde !== this._runde) return; // inzwischen stummgeschaltet
    this._dekodiert = false;
    if (puffer) {
      const q = ctx.createBufferSource();
      q.buffer = puffer; q.connect(this.analyser);
      const start = Math.max(ctx.currentTime + 0.02, this.ende);
      this.ende = start + puffer.duration;
      this.quellen.add(q);
      if (!this.spricht) { this.spricht = true; this.h.audioStart?.(); }
      q.onended = () => { this.quellen.delete(q); this._fertig(); };
      q.start(start);
    }
    this._weiter();
  }

  _fertig() { // Sprechen endet erst, wenn nichts mehr läuft, nichts dekodiert wird und nichts wartet
    if (this.spricht && !this.quellen.size && !this._dekodiert && !this.warteschlange.length) {
      this.spricht = false; this.h.audioEnde?.();
    }
  }

  stummschalten() {
    this.warteschlange.length = 0;
    this._runde = (this._runde || 0) + 1; this._dekodiert = false;
    for (const q of this.quellen) { q.onended = null; try { q.stop(); } catch (_) { /* schon aus */ } }
    this.quellen.clear(); this.ende = 0;
    if (this.spricht) { this.spricht = false; this.h.audioEnde?.(); }
  }

  pegel() { // Lautstärke der Stimme 0..1
    if (!this.analyser || !this.spricht) { this._pegel *= 0.9; return this._pegel; }
    this.analyser.getFloatTimeDomainData(this.daten);
    let s = 0; for (let i = 0; i < this.daten.length; i++) s += this.daten[i] * this.daten[i];
    const rms = Math.sqrt(s / this.daten.length);
    const ziel = Math.min(1, rms * 5.5);
    this._pegel = ziel > this._pegel ? ziel : this._pegel * 0.88 + ziel * 0.12;
    return this._pegel;
  }

  micPegel() {
    if (!this.micAnalyser || !this.rekorder) { this._mic *= 0.85; return this._mic; }
    this.micAnalyser.getFloatTimeDomainData(this.micDaten);
    let s = 0; for (let i = 0; i < this.micDaten.length; i++) s += this.micDaten[i] * this.micDaten[i];
    const ziel = Math.min(1, Math.sqrt(s / this.micDaten.length) * 9);
    this._mic = ziel > this._mic ? ziel : this._mic * 0.85 + ziel * 0.15;
    return this._mic;
  }

  // ---------- Aufnahme ----------

  async aufnahmeStart({ stoppen = true } = {}) {
    if (this.rekorder) return;
    this.losgelassen = false;
    if (stoppen) this.stoppe(); // ins Wort fallen: Vorlesen und laufende Antwort anhalten
    const ctx = this.audio();
    try {
      const strom = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true } });
      this.rekorder = new MediaRecorder(strom); this.stueckchen = []; this.aufnahmeBeginn = performance.now();
      if (ctx) {
        try {
          const src = ctx.createMediaStreamSource(strom);
          this.micAnalyser = ctx.createAnalyser(); this.micAnalyser.fftSize = 1024;
          this.micDaten = new Float32Array(1024);
          src.connect(this.micAnalyser);
        } catch (_) { this.micAnalyser = null; }
      }
      this.rekorder.ondataavailable = (e) => e.data.size && this.stueckchen.push(e.data);
      this.rekorder.onstop = () => {
        strom.getTracks().forEach((t) => t.stop());
        const blob = new Blob(this.stueckchen, { type: this.rekorder.mimeType }); this.rekorder = null;
        const lang = performance.now() - this.aufnahmeBeginn >= 350; // kürzer ist ein Versehen
        if (lang && blob.size > 2000 && this.verbunden) { this.ws.send(blob); this.erkennt = true; }
        else if (lang && !this.verbunden) this.h.fluechtig?.({ typ: "fehler", text: "Keine Verbindung zum Server. Die Aufnahme wurde nicht gesendet." });
        this.h.aufnahme?.(false);
      };
      this.rekorder.start();
      this.h.aufnahme?.(true);
      if (this.losgelassen) this.aufnahmeEnde();
    } catch (e) {
      this.h.fluechtig?.({ typ: "fehler", text: "Kein Mikrofon: " + e.message });
      this.h.aufnahme?.(false);
    }
  }

  aufnahmeEnde() { this.losgelassen = true; if (this.rekorder && this.rekorder.state === "recording") this.rekorder.stop(); }
  get nimmtAuf() { return !!this.rekorder; }
}

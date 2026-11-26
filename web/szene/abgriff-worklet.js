// Mikrofon-Abgriff für das Freisprechen: sammelt Audio in 1024er-Stücken und reicht sie an die Seite.
// Eigene Datei, weil die Content-Security-Policy Worklets aus blob:-Adressen nicht erlaubt.
class Abgriff extends AudioWorkletProcessor {
  constructor() { super(); this.puffer = new Float32Array(1024); this.n = 0; }
  process(eingaenge) {
    const k = eingaenge[0] && eingaenge[0][0];
    if (k) for (let i = 0; i < k.length; i++) {
      this.puffer[this.n++] = k[i];
      if (this.n === this.puffer.length) { this.port.postMessage(this.puffer.slice(0)); this.n = 0; }
    }
    return true;
  }
}
registerProcessor("harno-abgriff", Abgriff);

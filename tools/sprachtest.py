"""Sprachtest ohne Mikrofon: Sätze mit Piper sprechen, nach webm/opus wandeln und als Aufnahme über den
WebSocket an eine laufende Testinstanz schicken. Gibt erkannten Text, Szenenereignisse und Vorlese-Audio aus.

    uv run python tools/sprachtest.py --port 8461 "Zeig mir die Todos" "Die zweite" "Erledigt"

Nur gegen Testinstanzen benutzen (Attrappen-Agent, Modul beispiel), nie gegen die eigene laufende Instanz.
"""
import argparse
import asyncio
import io
import json
import os
import subprocess
import time
import wave
from pathlib import Path


def sprich(stimme, text):
    puffer = io.BytesIO()
    with wave.open(puffer, "wb") as w:
        stimme.synthesize_wav(text, w)
    return subprocess.run(["ffmpeg", "-nostdin", "-loglevel", "error", "-f", "wav", "-i", "pipe:0",
                           "-c:a", "libopus", "-b:a", "32k", "-f", "webm", "pipe:1"],
                          input=puffer.getvalue(), capture_output=True, check=True).stdout


async def satz(ws, daten, warte):
    await ws.send(daten if isinstance(daten, bytes) else json.dumps({"typ": "frage", "text": daten}))
    beginn, ergebnis = time.perf_counter(), {"erkannt": None, "szene": [], "audio": 0, "text": "", "schnell": None, "werkzeuge": []}
    ende = beginn + warte
    while time.perf_counter() < ende:
        try:
            m = await asyncio.wait_for(ws.recv(), timeout=max(0.1, ende - time.perf_counter()))
        except asyncio.TimeoutError:
            break
        if isinstance(m, bytes):
            ergebnis["audio"] += 1
            continue
        m = json.loads(m)
        t = m.get("typ")
        if t == "erkannt":
            ergebnis["erkannt"] = m["text"]
            ergebnis["erkennen_s"] = m.get("sekunden")
        elif t == "szene":
            ergebnis["szene"].append(m["aktion"] + (" " + m["art"] if m.get("art") else ""))
        elif t == "text":
            ergebnis["text"] += m["text"]
        elif t == "werkzeug":
            ergebnis["werkzeuge"].append(m["name"])
        elif t == "schnellbefehl":
            ergebnis["schnell"] = m["aktion"]
        elif t == "zug_ende":
            ende = min(ende, time.perf_counter() + 2.5)  # noch auf Vorlese-Audio warten
        elif t == "fehler":
            ergebnis.setdefault("fehler", []).append(m["text"])
    ergebnis["text"] = ergebnis["text"].strip()
    return ergebnis


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, required=True)
    ap.add_argument("--warte", type=float, default=12)
    ap.add_argument("--text", action="store_true", help="getippt statt gesprochen (ohne Piper/Whisper)")
    ap.add_argument("saetze", nargs="+")
    a = ap.parse_args()
    if a.port == 8450:
        raise SystemExit("Nicht gegen den Live-Server (8450) testen.")
    from piper import PiperVoice
    import websockets
    stimmen = Path(os.environ.get("COCKPIT_UI_STIMMEN", "~/.local/share/cockpit-ui/stimmen")).expanduser()
    stimme = PiperVoice.load(str(stimmen / "de_DE-thorsten-high.onnx"))
    url = f"ws://127.0.0.1:{a.port}/ws"
    async with websockets.connect(url, origin=f"http://127.0.0.1:{a.port}", max_size=None) as ws:
        verlauf = json.loads(await ws.recv())
        print("Szene beim Verbinden:", verlauf.get("szene", {}).get("ansicht"))
        for s in a.saetze:
            r = await satz(ws, s if a.text else sprich(stimme, s), a.warte)
            print(json.dumps({"gesagt": s} | r, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())

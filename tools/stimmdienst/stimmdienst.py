"""Stimmdienst: Qwen3-TTS auf einer Grafikkarte im eigenen Netz (z. B. ein PC, erreichbar über VPN).

Protokoll „http-tts“ (so spricht cockpit-ui jeden Stimmendienst an):
  GET  /stimmen                      -> {"stimmen": [{"id", "name", "beschreibung"}], "modell": "..."}
  POST /sprich {"text", "stimme"}    -> audio/wav
  POST /sprich_strom {"text", "stimme"} -> Folge von Teilen, je 4 Byte Länge (big endian) + WAV;
                                         angekündigt durch "strom": true in /stimmen
  GET  /gesund                       -> {"ok": true}

Stimmen: je Stimme im Ordner STIMMDIENST_STIMMEN eine <id>.wav (Vorlage, 5–20 s) und <id>.txt
(genau der gesprochene Text der Vorlage), optional <id>.json {"name", "beschreibung"}.
Optional STIMMDIENST_TOKEN: dann muss der Header „Authorization: Bearer <token>“ passen.

Beschleunigt mit faster-qwen3-tts (CUDA Graphs): auf der RTX 4060 ca. 0,5 s Rechenzeit je Sekunde
Audio statt 1,3 s mit qwen-tts allein. Benötigt transformers 5.15.x (5.24 bricht den Tokenizer).
Umgebung: uv venv .venv-fast; uv pip install faster-qwen3-tts fastapi uvicorn soundfile "transformers==5.15.1"

Start:  python stimmdienst.py --host 192.168.1.50 --port 8470
"""
import argparse
import asyncio
import io
import json
import os
import queue
import struct
import threading
import time
from pathlib import Path

import soundfile as sf
import torch
import uvicorn
from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel

MODELL = os.environ.get("STIMMDIENST_MODELL", "Qwen/Qwen3-TTS-12Hz-1.7B-Base")
STIMMEN = Path(os.environ.get("STIMMDIENST_STIMMEN", Path(__file__).parent / "stimmen")).expanduser()
TOKEN = os.environ.get("STIMMDIENST_TOKEN", "")
TEIL = int(os.environ.get("STIMMDIENST_TEIL", "6"))  # Schritte je Teil beim Streaming, 12 Schritte = 1 s Audio
WARTEN = float(os.environ.get("STIMMDIENST_WARTEN", "30"))   # so lange höchstens auf die Grafikkarte warten, sonst 503
HOECHSTENS = float(os.environ.get("STIMMDIENST_HOECHSTENS", "180"))  # Obergrenze je Auftrag in Sekunden

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
modell = None
vorlagen = {}   # id -> {"name", "beschreibung", "prompt"}
sperre = threading.Lock()


def laden():
    global modell
    from faster_qwen3_tts import FasterQwen3TTS
    modell = FasterQwen3TTS.from_pretrained(MODELL, device="cuda", dtype=torch.bfloat16)
    for wav in sorted(STIMMEN.glob("*.wav")):
        sid = wav.stem
        txt = wav.with_suffix(".txt")
        meta = json.loads(wav.with_suffix(".json").read_text()) if wav.with_suffix(".json").exists() else {}
        ref = {"ref_audio": str(wav), "ref_text": txt.read_text().strip() if txt.exists() else "",
               "xvec_only": not txt.exists()}
        vorlagen[sid] = {"name": meta.get("name", sid), "beschreibung": meta.get("beschreibung", ""), "ref": ref}
        modell.generate_voice_clone(text="Bereit.", language="German", **ref)  # CUDA Graphs und Vorlage vorbereiten
    print(f"stimmdienst: {MODELL} geladen, Stimmen: {', '.join(vorlagen) or 'keine'}", flush=True)


def pruefe(authorization):
    if TOKEN and authorization != f"Bearer {TOKEN}":
        raise HTTPException(401, "Token fehlt oder falsch")


class Auftrag(BaseModel):
    text: str
    stimme: str = ""
    sprache: str = "German"


@app.get("/gesund")
def gesund():
    return {"ok": modell is not None}


@app.get("/stimmen")
def stimmen(authorization: str = Header(default="")):
    pruefe(authorization)
    return {"modell": MODELL, "strom": True, "stimmen": [{"id": k, "name": v["name"], "beschreibung": v["beschreibung"]} for k, v in vorlagen.items()]}


def wav(audio, sr):
    puffer = io.BytesIO()
    sf.write(puffer, audio, sr, format="WAV", subtype="PCM_16")
    return puffer.getvalue()


def auftrag_pruefen(a, authorization):
    pruefe(authorization)
    if modell is None:
        raise HTTPException(503, "Modell lädt noch")
    if not a.text.strip() or len(a.text) > 2000:
        raise HTTPException(400, "Text leer oder zu lang")
    sid = a.stimme or next(iter(vorlagen), "")
    if sid not in vorlagen:
        raise HTTPException(404, f"Stimme {sid!r} unbekannt")
    return sid


def belegen():
    """Grafikkarte belegen oder nach WARTEN Sekunden mit 503 aufgeben, statt ewig zu hängen."""
    if not sperre.acquire(timeout=WARTEN):
        raise HTTPException(503, "Stimmdienst ist belegt")


ENDE = object()


@app.post("/sprich_strom")
async def sprich_strom(a: Auftrag, authorization: str = Header(default="")):
    sid = auftrag_pruefen(a, authorization)
    await asyncio.to_thread(belegen)
    stopp, fach = threading.Event(), queue.Queue()  # unbegrenzt: der Erzeuger blockiert nie, auch ohne Abnehmer

    def erzeuge():
        # Ein eigener Faden je Auftrag. Er gibt die Sperre in jedem Fall frei: am Ende, bei Fehlern und wenn der
        # Abnehmer weg ist (stopp). Früher hielt ein abgebrochener Strom die Sperre für immer.
        t, erst, laenge, abbruch = time.time(), None, 0.0, ""
        strom = None
        try:
            strom = modell.generate_voice_clone_streaming(text=a.text, language=a.sprache, chunk_size=TEIL,
                                                          **vorlagen[sid]["ref"])
            for audio, sr, _ in strom:
                if stopp.is_set():
                    abbruch = ", abgebrochen"
                    break
                if time.time() - t > HOECHSTENS:
                    abbruch = ", Zeitlimit"
                    break
                if len(audio) == 0:
                    continue
                erst = erst or time.time() - t
                laenge += len(audio) / sr
                daten = wav(audio, sr)
                fach.put(struct.pack(">I", len(daten)) + daten)
        except Exception as e:  # noqa: BLE001 - an den Abnehmer weiterreichen
            abbruch = f", Fehler: {e}"
            fach.put(e)
        finally:
            try:
                if strom is not None:
                    strom.close()
            finally:
                sperre.release()
                fach.put(ENDE)
                print(f"stimmdienst: {len(a.text)} Zeichen, {laenge:.1f} s Audio in {time.time() - t:.1f} s, "
                      f"erster Teil nach {erst or 0:.2f} s (Strom{abbruch})", flush=True)

    threading.Thread(target=erzeuge, name="stimmdienst-strom", daemon=True).start()

    async def teile():
        try:
            while True:
                try:
                    x = await asyncio.to_thread(fach.get, True, HOECHSTENS)
                except queue.Empty:
                    return
                if x is ENDE or isinstance(x, Exception):
                    return
                yield x
        finally:  # läuft auch, wenn der Client trennt (Abbruch der Antwort)
            stopp.set()

    return StreamingResponse(teile(), media_type="application/octet-stream")


@app.post("/sprich")
def sprich(a: Auftrag, authorization: str = Header(default="")):
    sid = auftrag_pruefen(a, authorization)
    t = time.time()
    belegen()
    try:
        wavs, sr = modell.generate_voice_clone(text=a.text, language=a.sprache, **vorlagen[sid]["ref"])
    finally:
        sperre.release()
    daten = wav(wavs[0], sr)
    dauer = time.time() - t
    print(f"stimmdienst: {len(a.text)} Zeichen, {len(wavs[0]) / sr:.1f} s Audio in {dauer:.1f} s", flush=True)
    return Response(daten, media_type="audio/wav", headers={"X-Rechenzeit": f"{dauer:.2f}"})


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8470)
    a = p.parse_args()
    laden()
    uvicorn.run(app, host=a.host, port=a.port, log_level="warning")

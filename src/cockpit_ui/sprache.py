"""Lokale Sprache: Erkennung mit faster-whisper, Vorlesen mit Piper. Läuft auf macOS und Linux."""
import io
import re
import subprocess
import threading
import wave

import numpy as np


def audio_zu_pcm(daten: bytes) -> np.ndarray:
    """Beliebiges Audio (webm/ogg/wav) -> 16 kHz mono float32, per ffmpeg."""
    roh = subprocess.run(
        ["ffmpeg", "-nostdin", "-loglevel", "error", "-i", "pipe:0",
         "-f", "s16le", "-ac", "1", "-ar", "16000", "pipe:1"],
        input=daten, capture_output=True, check=True, timeout=60).stdout
    return np.frombuffer(roh, np.int16).astype(np.float32) / 32768.0


class Erkenner:
    def __init__(self, modell: str, geraet: str):
        from faster_whisper import WhisperModel
        try:
            self.modell = WhisperModel(modell, device=geraet, compute_type="int8")
        except Exception:
            # MPS ist in ctranslate2 experimentell; notfalls CPU.
            self.modell = WhisperModel(modell, device="cpu", compute_type="int8")
        self.vokabular = ""
        self._sperre = threading.Lock()

    def erkenne(self, daten: bytes) -> str:
        pcm = audio_zu_pcm(daten)
        if len(pcm) < 16000 * 0.3:
            return ""
        with self._sperre:
            segmente, _ = self.modell.transcribe(
                pcm, language="de", vad_filter=True, beam_size=1,
                condition_on_previous_text=False,
                initial_prompt=self.vokabular or None)
            # Segmente, die Whisper selbst für wahrscheinlich sprachlos hält, weglassen
            text = " ".join(s.text.strip() for s in segmente
                            if not (s.no_speech_prob > 0.6 and s.avg_logprob < -0.7)).strip()
        return text if brauchbar(text) else ""


# Was Whisper aus Stille oder Rauschen gern macht (aus Untertiteln gelernt)
_ERFUNDEN = ("untertitel", "amara.org", "copyright wdr", "swr 20")


def brauchbar(text: str) -> bool:
    """Falsch für leere Erkennungen: nur Satzzeichen oder Leerraum (z. B. "." aus Stille)
    und die bekannten erfundenen Untertitel-Zeilen."""
    kern = re.sub(r"[\W_]+", "", text or "")
    if len(kern) < 2 and not kern.isdigit():
        return False
    klein = text.lower()
    return not (len(klein) < 80 and any(e in klein for e in _ERFUNDEN))


class Stimme:
    def __init__(self, onnx_pfad):
        from piper import PiperVoice
        self.stimme = PiperVoice.load(str(onnx_pfad))
        self._sperre = threading.Lock()

    def sprich(self, text: str) -> bytes:
        puffer = io.BytesIO()
        with self._sperre, wave.open(puffer, "wb") as w:
            self.stimme.synthesize_wav(text, w)
        return puffer.getvalue()


class ElevenLabsStimme:
    """Vorlesen über ElevenLabs (Cloud). Liefert MP3; der Browser spielt es wie die WAVs von Piper."""

    def __init__(self, stimme_id, modell):
        from elevenlabs import ElevenLabs
        self.client = ElevenLabs(timeout=30)  # liest ELEVENLABS_API_KEY aus der Umgebung
        self.stimme_id = stimme_id
        self.modell = modell
        self._vorher = ""
        self._sperre = threading.Lock()

    def stimmen(self):
        """Vorgefertigte Stimmen (premade) des Kontos; nur die sind im Free-Plan sicher per API nutzbar."""
        ergebnis = []
        for v in self.client.voices.get_all().voices:
            if v.category != "premade":
                continue
            l = v.labels or {}
            ergebnis.append({"id": v.voice_id, "name": v.name, "geschlecht": l.get("gender") or "", "akzent": l.get("accent") or ""})
        reihenfolge = {"female": 0, "neutral": 1, "male": 2}
        return sorted(ergebnis, key=lambda v: (reihenfolge.get(v["geschlecht"], 3), v["name"]))

    def sprich(self, text: str, stimme_id: str = "") -> bytes:
        with self._sperre:
            audio = self.client.text_to_speech.convert(
                text=text, voice_id=stimme_id or self.stimme_id, model_id=self.modell,
                language_code="de", output_format="mp3_44100_128",
                previous_text=self._vorher[-500:] or None)  # Übergänge zwischen Sätzen glätten
            daten = b"".join(audio)
            self._vorher = text
            return daten


def elevenlabs_fehler(e):
    """Kurze Meldung zu einem ElevenLabs-Fehler und ob er dauerhaft ist (dann auf Piper umschalten)."""
    code = getattr(e, "status_code", None)
    body = getattr(e, "body", None)
    detail = body.get("detail") if isinstance(body, dict) else None
    status = (detail.get("status") or "") if isinstance(detail, dict) else ""
    if status == "quota_exceeded" or "quota" in str(body or ""):
        return "ElevenLabs-Kontingent leer", True
    if code == 401:
        return "ElevenLabs-Key ungültig", True
    if code in (402, 403):
        return "ElevenLabs verweigert (Plan/Rechte)", True
    if code == 429:
        return "ElevenLabs überlastet", False
    if code:
        return f"ElevenLabs-Fehler {code}", False
    return "ElevenLabs nicht erreichbar", False


_MD = [
    (re.compile(r"```.*?```", re.S), " "),                 # Codeblöcke nicht vorlesen
    (re.compile(r"`([^`]*)`"), r"\1"),
    (re.compile(r"\[([^\]]+)\]\([^)]+\)"), r"\1"),          # Links: nur Text
    (re.compile(r"https?://\S+"), "ein Link"),
    (re.compile(r"(?<!\w)(?:~|\.{0,2})/[\w./-]+"), ""),     # Pfade
    (re.compile(r"^\s*[-*•]\s+", re.M), ""),
    (re.compile(r"^\s*#+\s*", re.M), ""),
    (re.compile(r"\|"), " "),
    (re.compile(r"[*_]{1,3}"), ""),
    (re.compile(r"→"), ", "),
]


def vorlesbar(text: str) -> str:
    for muster, ersatz in _MD:
        text = muster.sub(ersatz, text)
    return re.sub(r"\s+", " ", text).strip()


class Satzpuffer:
    """Sammelt gestreamten Text und gibt vollständige Sätze heraus, sobald sie fertig sind."""
    _ENDE = re.compile(r"(.+?[.!?:])(\s+|\n)|(.+?)\n\n", re.S)

    def __init__(self):
        self.rest = ""

    def hinzu(self, text: str):
        self.rest += text
        saetze = []
        while True:
            m = self._ENDE.match(self.rest)
            if not m:
                break
            satz = (m.group(1) or m.group(3) or "").strip()
            self.rest = self.rest[m.end():]
            # Abkürzungen wie "z. B." oder Datumsangaben "25.11." nicht als Satzende werten
            if satz and len(satz) < 8 and saetze:
                saetze[-1] += " " + satz
            elif satz:
                saetze.append(satz)
        return saetze

    def ende(self):
        r, self.rest = self.rest.strip(), ""
        return [r] if r else []

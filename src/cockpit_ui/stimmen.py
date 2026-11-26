"""Stimmendienste im Netz (Protokoll „http-tts“) und die gespeicherte Stimmenwahl.

Ein Stimmendienst ist ein kleiner HTTP-Server, der Text in WAV verwandelt, z. B. Qwen3-TTS auf
einem eigenen GPU-Rechner (`tools/stimmdienst/`). Protokoll:
  GET  /stimmen                    -> {"stimmen": [{"id", "name", "beschreibung"}], "modell"}
  POST /sprich {"text", "stimme"}  -> audio/wav
  POST /sprich_strom {...}         -> Teile, je 4 Byte Länge (big endian) + WAV; nur wenn /stimmen "strom": true meldet

Die Dienste und die gewählte Stimme stehen in `~/.config/cockpit-ui/stimmen.json`
(oder `COCKPIT_UI_STIMMEN_KONFIG`). Die Datei schreibt der Server selbst, wenn man in der
Oberfläche oder per Sprache etwas ändert. Ein Token steht dort am besten als Verweis
`env:NAME` bzw. `keychain:DIENST`, nicht im Klartext.
"""
import json
import os
import re
import struct
import threading
import urllib.error
import urllib.request
from pathlib import Path

from .konfig import aufloesen

PFAD = Path(os.environ.get("COCKPIT_UI_STIMMEN_KONFIG", "~/.config/cockpit-ui/stimmen.json")).expanduser()
NAME = re.compile(r"^[a-z0-9][a-z0-9_-]{0,30}$")


class DienstFehler(Exception):
    pass


class HttpStimme:
    """Ein Stimmendienst. sprich() liefert WAV-Bytes."""

    def __init__(self, name, url, token=""):
        self.name = name
        self.url = url.rstrip("/")
        self.token = token
        self.stimmen_liste = []    # [{"id", "name", "beschreibung"}]
        self.modell = ""
        self.strom = False         # Dienst kann Teile liefern, bevor der Satz fertig gerechnet ist
        self.fehler = ""
        self._sperre = threading.Lock()

    def _anfrage(self, pfad, daten=None, timeout=10, offen=False):
        kopf = {"User-Agent": "cockpit-ui/0.1"}
        tok = aufloesen(self.token) if self.token else ""
        if tok:
            kopf["Authorization"] = f"Bearer {tok}"
        if daten is not None:
            kopf["Content-Type"] = "application/json"
            daten = json.dumps(daten).encode()
        req = urllib.request.Request(self.url + pfad, data=daten, headers=kopf)
        try:
            if offen:
                return urllib.request.urlopen(req, timeout=timeout)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            text = e.read().decode(errors="replace")[:200]
            try:
                text = json.loads(text).get("detail", text)
            except Exception:
                pass
            raise DienstFehler(f"Stimmendienst {self.name}: {e.code} {text}") from None
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            grund = getattr(e, "reason", e)
            raise DienstFehler(f"Stimmendienst {self.name} nicht erreichbar ({grund})") from None

    def aktualisiere(self):
        """Holt die Stimmen des Dienstes. Fehler landen in self.fehler, nicht als Ausnahme."""
        try:
            d = json.loads(self._anfrage("/stimmen", timeout=5))
            self.stimmen_liste = [{"id": str(v["id"]), "name": str(v.get("name") or v["id"]),
                                   "beschreibung": str(v.get("beschreibung") or "")} for v in d.get("stimmen", [])]
            self.modell = str(d.get("modell") or "")
            self.strom = d.get("strom") is True
            self.fehler = ""
        except (DienstFehler, ValueError, KeyError) as e:
            self.stimmen_liste = []
            self.fehler = str(e)
        return self

    def sprich(self, text, stimme_id=""):
        with self._sperre:  # der Dienst rechnet ohnehin nacheinander
            return self._anfrage("/sprich", {"text": text, "stimme": stimme_id}, timeout=60)

    def sprich_strom(self, text, stimme_id=""):
        """Liefert WAV-Teile, sobald der Dienst sie gerechnet hat. Ohne Strom-Fähigkeit ein einziger Teil."""
        if not self.strom:
            yield self.sprich(text, stimme_id)
            return
        with self._sperre:
            # Zeitlimit je Lesevorgang: stockt der Dienst mitten im Satz, endet der Satz statt das Vorlesen zu blockieren
            antwort = self._anfrage("/sprich_strom", {"text": text, "stimme": stimme_id}, timeout=20, offen=True)
            with antwort:
                while True:
                    kopf = antwort.read(4)
                    if len(kopf) < 4:
                        return
                    (n,) = struct.unpack(">I", kopf)
                    teil = antwort.read(n)
                    if len(teil) < n:
                        raise DienstFehler(f"Stimmendienst {self.name}: Strom abgebrochen")
                    yield teil


def pruefe_dienst(name, url):
    name = str(name or "").strip().lower()
    url = str(url or "").strip()
    if not NAME.match(name):
        raise DienstFehler("Name: Kleinbuchstaben, Ziffern, - und _, höchstens 31 Zeichen (z. B. „pc“).")
    if not re.match(r"^https?://[^\s/]+(:\d+)?(/\S*)?$", url):
        raise DienstFehler("Adresse muss mit http:// oder https:// beginnen, z. B. http://192.168.1.50:8470")
    return name, url


def lade(pfad=PFAD):
    try:
        d = json.loads(pfad.read_text())
    except (OSError, ValueError):
        d = {}
    dienste = [x for x in d.get("dienste", []) if isinstance(x, dict) and x.get("name") and x.get("url")]
    return {"dienste": dienste, "auswahl": str(d.get("auswahl") or "")}


def speichere(daten, pfad=PFAD):
    pfad.parent.mkdir(parents=True, exist_ok=True)
    tmp = pfad.with_suffix(".tmp")
    tmp.write_text(json.dumps(daten, ensure_ascii=False, indent=2) + "\n")
    os.chmod(tmp, 0o600)
    tmp.replace(pfad)

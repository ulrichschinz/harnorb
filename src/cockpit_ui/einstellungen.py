"""Einstellungen des Kerns aus der Umgebung. Secrets nur aus der Umgebung oder der gitignorierten `.env`.

Module und ihre Einstellungen stehen in der Konfiguration je Rechner (konfig.py)."""
import os
import platform
from dataclasses import dataclass, field
from pathlib import Path


def lade_env(datei=Path(__file__).resolve().parents[2] / ".env"):
    """Liest KEY=WERT aus `.env` (vom ElevenLabs-Onboarding angelegt) in die Umgebung.

    Was schon in der Umgebung steht, gewinnt. Muss vor dem Import der SDKs laufen.
    """
    try:
        zeilen = datei.read_text().splitlines()
    except OSError:
        return
    for zeile in zeilen:
        zeile = zeile.strip()
        if not zeile or zeile.startswith("#") or "=" not in zeile:
            continue
        k, v = zeile.split("=", 1)
        k = k.strip().removeprefix("export ").strip()
        v = v.strip().strip('"').strip("'")
        if k and k not in os.environ:
            os.environ[k] = v


lade_env()


def _pfad(name, standard):
    return Path(os.environ.get(name, standard)).expanduser()


def _geraet():
    if os.environ.get("WHISPER_GERAET"):
        return os.environ["WHISPER_GERAET"]
    if platform.system() == "Darwin" and platform.machine() == "arm64":
        return "mps"
    try:
        import ctranslate2
        if ctranslate2.get_cuda_device_count() > 0:
            return "cuda"
    except Exception:
        pass
    return "cpu"


@dataclass
class Einstellungen:
    port: int = int(os.environ.get("COCKPIT_UI_PORT", "8450"))
    cockpit: Path = field(default_factory=lambda: _pfad("COCKPIT_DIR", "~/cockpit"))
    stimmen: Path = field(default_factory=lambda: _pfad("COCKPIT_UI_STIMMEN", "~/.local/share/cockpit-ui/stimmen"))
    stimme: str = os.environ.get("COCKPIT_UI_STIMME", "de_DE-thorsten-high")
    geraet: str = field(default_factory=_geraet)
    whisper_modell: str = os.environ.get("WHISPER_MODELL", "")
    # ElevenLabs als zweite Stimme (Cloud). Sarah ist eine vorgefertigte (premade), mehrsprachige Frauenstimme, im Free-Plan per API nutzbar.
    elevenlabs_stimme: str = os.environ.get("ELEVENLABS_STIMME", "EXAVITQu4vr4xnSDxMaL")
    elevenlabs_modell: str = os.environ.get("ELEVENLABS_MODELL", "eleven_flash_v2_5")
    # Welche Stimme beim Start vorliest: "elevenlabs" oder "piper"
    standard_stimme: str = os.environ.get("COCKPIT_UI_VORLESER", "")
    # Agent: "claude" (Claude Code im Cockpit). Weitere Adapter können folgen.
    agent: str = os.environ.get("COCKPIT_UI_AGENT", "claude")  # "attrappe": skriptgesteuert, für Tests
    # Schnellbefehle („zeig Inbox“, „weg damit“, „Stopp“) ohne Claude erkennen: "1" an, "0" aus
    schnellbefehle: bool = os.environ.get("COCKPIT_UI_SCHNELLBEFEHLE", "1") != "0"

    def __post_init__(self):
        if not self.whisper_modell:
            # Auf der CPU ist large-v3-turbo spürbar langsamer; small ist dort der Kompromiss.
            self.whisper_modell = "large-v3-turbo" if self.geraet in ("mps", "cuda") else "small"
        if not self.standard_stimme:
            self.standard_stimme = "elevenlabs" if os.environ.get("ELEVENLABS_API_KEY") else "piper"

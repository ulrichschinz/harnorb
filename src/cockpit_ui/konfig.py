"""Konfiguration je Rechner: welche Module laufen, wer spricht, welche Namen gelten.

Datei: `COCKPIT_UI_KONFIG` oder `~/.config/cockpit-ui/config.toml`. Sie gehört nicht ins Repo.
Vorlage: `konfig.beispiel.toml`. Fehlt die Datei, läuft kein Modul: nur Sprache, Szene und Agent.

Werte, die mit `env:NAME` beginnen, kommen aus der Umgebung, `keychain:DIENST` aus dem
macOS-Schlüsselbund. `env:NAME|Standard` nimmt den Standard, wenn NAME fehlt. Secrets stehen nie
in der Datei selbst.
"""
import os
import subprocess
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

STANDARD_PFAD = "~/.config/cockpit-ui/config.toml"
OHNE_DATEI = {}


def aufloesen(wert):
    """env:/keychain:-Verweise auflösen, rekursiv in Listen und Tabellen."""
    if isinstance(wert, dict):
        return {k: aufloesen(v) for k, v in wert.items()}
    if isinstance(wert, list):
        return [aufloesen(v) for v in wert]
    if not isinstance(wert, str):
        return wert
    if wert.startswith("env:"):
        name, _, standard = wert[4:].partition("|")
        return os.environ.get(name.strip(), standard)
    if wert.startswith("keychain:"):
        try:
            r = subprocess.run(["security", "find-generic-password", "-s", wert[9:].strip(), "-w"],
                               capture_output=True, text=True, timeout=5)
            return r.stdout.strip() if r.returncode == 0 else ""
        except (OSError, subprocess.TimeoutExpired):
            return ""
    return wert


@dataclass
class Konfig:
    datei: Path | None = None
    person: str = ""
    cockpit: Path | None = None
    namen: list = field(default_factory=list)
    module_pfade: list = field(default_factory=list)
    module: dict = field(default_factory=dict)     # name -> Einstellungen (aufgelöst)
    aufgaben: str = ""                             # welches Modul die Aufgaben liefert (leer: das erste)
    fehler: list = field(default_factory=list)


def lade(pfad=None):
    pfad = Path(pfad or os.environ.get("COCKPIT_UI_KONFIG") or STANDARD_PFAD).expanduser()
    k = Konfig()
    if pfad.is_file():
        try:
            roh = tomllib.loads(pfad.read_text())
            k.datei = pfad
        except (OSError, tomllib.TOMLDecodeError) as e:
            k.fehler.append(f"Konfiguration {pfad} unlesbar: {e}. Es läuft kein Modul.")
            return k
    else:
        roh = OHNE_DATEI
    k.person = str(roh.get("person") or "")
    if roh.get("cockpit"):
        k.cockpit = Path(str(roh["cockpit"])).expanduser()
    k.namen = [str(n) for n in roh.get("namen") or []]
    k.module_pfade = [Path(str(p)).expanduser() for p in roh.get("module_pfade") or []]
    k.aufgaben = str(roh.get("aufgaben") or "")
    k.module = {name: aufloesen(dict(werte or {})) for name, werte in (roh.get("module") or {}).items()}
    return k

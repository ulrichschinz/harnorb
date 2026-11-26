"""Module: alles, was über Kern (Sprache, Szene, Agent, Cockpit-Ordner) hinausgeht.

Der Kern kennt keine Module beim Namen, nur Fähigkeiten:

    aufgaben      Modul.aufgaben ist ein Objekt mit der Schnittstelle `Aufgaben` (unten)
    aenderungen   Modul.stand() liefert einen Vergleichswert; ändert er sich, frischt die Szene auf
    namen         Modul.namen() liefert Eigennamen für die Spracherkennung
    agent_wissen  Modul.prompt() liefert einen Baustein für die Systemanweisung,
                  Modul.werkzeuge() Werkzeugnamen, die ohne Rückfrage laufen dürfen
    darstellung   Aufgaben dürfen ein Feld `anzeige` tragen (Abzeichen, Farbe, Symbol, Untertitel,
                  Kartenart, Erledigt-Effekt); Modul.web ist ein Ordner mit `modul.js`, das im Browser
                  eigene Kartenarten und Effekte anmeldet (Schnittstelle in web/szene/erweiterungen.js)

Welche Module laufen, steht in der Konfiguration je Rechner (`konfig.py`). Eingebaut sind
`taskwarrior`, `beispiel` (erfundene Aufgaben zum Ausprobieren) und `mcp` (reine MCP-Anbindung
ohne Code). Eigene Module liegen in den
`module_pfade` der Konfiguration. Anleitung: docs/module-schreiben.md.
"""
import importlib
import importlib.util
import sys
from dataclasses import dataclass, field
from pathlib import Path

EINGEBAUT = ("taskwarrior", "beispiel", "mcp")


class ModulFehler(Exception):
    """Fehler eines Moduls, der dem Nutzer als Satz gezeigt werden kann (kein Stacktrace)."""


@dataclass
class Kern:
    """Was ein Modul vom Kern erfahren darf."""
    cockpit: Path
    person: str = ""


class Aufgaben:
    """Schnittstelle der Fähigkeit `aufgaben`. Alle Methoden sind synchron (der Kern ruft sie
    in einem Thread auf) und werfen bei Problemen `ModulFehler`.

    Datenformat ist die Teilmenge des Taskwarrior-Exports, die Taskwarrior ohnehin spricht. Andere Systeme übersetzen in dieses Format:

        Aufgabe  {uuid, description, status ("pending" | "completed" | "deleted"), project?,
                  due? ("YYYYMMDDTHHMMSSZ", UTC), tags? [..], start? (Datum, wenn sie läuft),
                  annotations? [{entry, description}]}
        Projekt  {name, next, waiting, stalled, status? ("active" | "on_hold" | "done")}
        Stand    {inbox, overdue, due_today, next, waiting, waiting_followup_due}

    `uuid` ist jede stabile ID aus Buchstaben, Ziffern und `-_.:`, höchstens 64 Zeichen.
    """
    def summary(self) -> dict: raise NotImplementedError
    def naechste(self) -> list: raise NotImplementedError
    def inbox(self) -> list: raise NotImplementedError
    def warten(self) -> list: raise NotImplementedError
    def projekte(self) -> list: raise NotImplementedError
    def projekt(self, name) -> list: raise NotImplementedError
    def aufgaben(self, q=None, due_before=None, project=None) -> list: raise NotImplementedError
    def aufgabe(self, uuid) -> dict: raise NotImplementedError
    def erledigt(self, uuid): raise NotImplementedError
    def starten(self, uuid): raise NotImplementedError
    def stoppen(self, uuid): raise NotImplementedError
    def notiz(self, uuid, text): raise NotImplementedError


@dataclass
class Modul:
    """Grundklasse. Ein Modul überschreibt nur, was es kann."""
    name: str
    konfig: dict = field(default_factory=dict)
    kern: Kern | None = None
    titel: str = ""
    aufgaben: Aufgaben | None = None
    aendert_bei: tuple = ()   # Teile von Werkzeugnamen, nach deren Ende die Szene neu lädt
    web: Path | None = None   # Ordner mit modul.js für den Browser (sonst: web/ neben dem Modul, Schlüssel `web`)

    def bereit(self):
        """(ok, Text) für Statuspunkt und Diagnose. Darf nicht lange blockieren."""
        return True, "aktiv"

    def prompt(self):
        return str(self.konfig.get("prompt") or "")

    def werkzeuge(self):
        return [str(w) for w in self.konfig.get("erlaubt") or []]

    def namen(self):
        return []

    def stand(self):
        """Vergleichswert für die Wache oder None (keine Wache)."""
        return None


def _lade_datei(name, pfad):
    spec = importlib.util.spec_from_file_location(f"cockpit_ui_lokal_{name}", pfad)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def finde(typ, pfade=()):
    """Python-Modul mit `erstelle(name, konfig, kern)`: erst eigene Pfade, dann eingebaute."""
    for basis in pfade:
        basis = Path(basis).expanduser()
        for kandidat in (basis / typ / "__init__.py", basis / f"{typ}.py"):
            if kandidat.is_file():
                return _lade_datei(typ, kandidat)
    if typ in EINGEBAUT:
        return importlib.import_module(f"{__name__}.{typ}")
    raise ModulFehler(f"Modul {typ!r} nicht gefunden (eingebaut: {', '.join(EINGEBAUT)}; "
                      f"gesucht in: {', '.join(str(p) for p in pfade) or 'keinen eigenen Pfaden'})")


def _web_ordner(m, konfig, typ, pfade):
    """Ordner mit `modul.js`: was das Modul setzt, sonst `web` aus der Konfiguration, sonst `web/`
    im Modulordner (`<pfad>/<typ>/web/`). Nur Ordner, in denen `modul.js` wirklich liegt."""
    kandidaten = [m.web, konfig.get("web")] + [Path(b).expanduser() / typ / "web" for b in pfade]
    for k in kandidaten:
        if k and (Path(k).expanduser() / "modul.js").is_file():
            return Path(k).expanduser().resolve()
    return None


def lade(eintraege, kern, pfade=()):
    """eintraege: {name: konfig}. Liefert (module, fehler). Ein kaputtes Modul hält den Rest nicht auf."""
    module, fehler = [], []
    for name, konfig in eintraege.items():
        konfig = dict(konfig or {})
        if konfig.get("aus"):
            continue
        typ = str(konfig.get("typ") or name)
        try:
            m = finde(typ, pfade).erstelle(name, konfig, kern)
            if not isinstance(m, Modul):
                raise ModulFehler("erstelle() liefert kein Modul")
            m.web = _web_ordner(m, konfig, typ, pfade)
            module.append(m)
        except Exception as e:  # ein Modul darf den Start nie verhindern
            fehler.append(f"Modul {name}: {e}")
    return module, fehler

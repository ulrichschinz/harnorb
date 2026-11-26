"""Modul beispiel: erfundene Aufgaben im Speicher, zum Ausprobieren und für Tests.

Konfiguration:  [module.beispiel]   (keine Einstellungen)

Erledigen, Starten, Stoppen und Notizen ändern nur den Speicher; nach einem Neustart ist alles
wieder wie am Anfang. Die Listen folgen denselben GTD-Regeln wie das Modul taskwarrior:
Inbox = ohne Projekt und ohne Tags, nächste Aktionen = Tag `next`, Warten = Tag `waiting`.
"""
import copy
import json
import threading
import uuid as uuidlib
from datetime import datetime, timedelta, timezone

from . import Aufgaben, Modul, ModulFehler


def _tw(tage, stunde=17):
    """Taskwarrior-Datum relativ zu heute (lokal), als UTC-Zeichenkette."""
    d = datetime.now().replace(hour=stunde, minute=0, second=0, microsecond=0) + timedelta(days=tage)
    return d.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _jetzt():
    return _tw(0, datetime.now().hour)


def _aufgabe(nr, titel, projekt=None, tags=("next",), faellig=None, start=False, notizen=(), anzeige=None):
    return ({"anzeige": anzeige} if anzeige else {}) | {
        "uuid": str(uuidlib.uuid5(uuidlib.NAMESPACE_URL, f"attrappe/{nr}")), "id": nr,
        "description": titel, "status": "pending", "project": projekt, "urgency": 10 - nr * 0.3,
        "tags": list(tags), "depends": [], "due": _tw(faellig) if faellig is not None else None,
        "start": _tw(0, 8) if start else None, "entry": _tw(-10, 9),
        "annotations": [{"entry": _tw(-2, 10), "description": n} for n in notizen],
    }


def anfang():
    a = [
        _aufgabe(1, "Angebot Musterfirma überarbeiten", "vertrieb.musterfirma", ("next", "@computer"), 0,
                 notizen=["Preisstaffel aus dem Workshop übernehmen"],
                 anzeige={"abzeichen": "Kunde", "farbe": "blau", "untertitel": "Musterfirma GmbH, Ansprechpartnerin Frau Beispiel"}),
        _aufgabe(2, "Steuerunterlagen für das Quartal sortieren", "verwaltung", ("next", "@home"), -2),
        _aufgabe(3, "Folien für den Demo-Termin vorbereiten", "marketing", ("next", "@computer"), 1, start=True),
        _aufgabe(4, "Anonymisierungstest: Testdaten erzeugen", "anonymisierungstest", ("next", "@computer"), -1,
                 notizen=["Mit synthetischen Namen, keine echten Kunden"]),
        _aufgabe(5, "Anonymisierungstest: Bericht schreiben", "anonymisierungstest", ("next",), 3),
        _aufgabe(6, "Fahrrad zur Inspektion bringen", "privat", ("next", "@unterwegs"), 0,
                 anzeige={"symbol": "🚲", "farbe": "gruen", "effekt": "sanft"}),
        _aufgabe(7, "Rückruf Steuerberater", "verwaltung", ("next", "@telefon")),
        _aufgabe(8, "Blogartikel über Sprachoberflächen skizzieren", "marketing", ("next", "@computer")),
        _aufgabe(9, "Antwort von der Druckerei zum Flyer", "marketing", ("waiting",), 2),
        _aufgabe(10, "Freigabe Testumgebung durch den Kunden", "anonymisierungstest", ("waiting",)),
        _aufgabe(11, "Idee: Kugel-Oberfläche auch fürs Tablet", None, ()),
        _aufgabe(12, "Zettel vom Küchentisch: Geburtstag Tante Erna", None, ()),
        _aufgabe(13, "Notiz aus dem Call: Schnittstelle prüfen", None, ()),
        _aufgabe(14, "Wohnzimmerlampe reparieren", "privat", ("next", "@home"), -5),
    ]
    return {t["uuid"]: t for t in a}


def _tag_von(tw):
    if not tw:
        return None
    return datetime.strptime(tw, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc).astimezone().date()


def _nach_dringlichkeit(liste):
    return sorted(liste, key=lambda t: -t["urgency"])


class Speicher(Aufgaben):
    def __init__(self):
        self.sperre = threading.RLock()
        self.reset()

    def reset(self):
        with self.sperre:
            self.speicher = anfang()

    # Lesen liefert Kopien, damit niemand von außen den Speicher verändert.
    def _offen(self):
        return [copy.deepcopy(t) for t in self.speicher.values() if t["status"] == "pending"]

    def summary(self):
        with self.sperre:
            offen, heute = self._offen(), datetime.now().date()
            return {"today": heute.isoformat(), "inbox": len(self._inbox(offen)),
                    "overdue": sum(1 for t in offen if _tag_von(t["due"]) and _tag_von(t["due"]) < heute),
                    "due_today": sum(1 for t in offen if _tag_von(t["due"]) == heute),
                    "next": sum(1 for t in offen if "next" in t["tags"]),
                    "waiting": sum(1 for t in offen if "waiting" in t["tags"]), "waiting_followup_due": 0}

    @staticmethod
    def _inbox(offen):
        return [t for t in offen if not t["tags"] and not t["project"]]

    def naechste(self):
        with self.sperre:
            return _nach_dringlichkeit([t for t in self._offen() if "next" in t["tags"]])

    def inbox(self):
        with self.sperre:
            return self._inbox(self._offen())

    def warten(self):
        with self.sperre:
            return [t for t in self._offen() if "waiting" in t["tags"]]

    def projekte(self):
        with self.sperre:
            offen = self._offen()
        ergebnis = []
        for n in sorted({t["project"] for t in offen if t["project"]}):
            l = [t for t in offen if t["project"] == n]
            nx = sum(1 for t in l if "next" in t["tags"])
            wa = sum(1 for t in l if "waiting" in t["tags"])
            ergebnis.append({"name": n, "status": "active", "next": nx, "waiting": wa,
                             "stalled": nx == 0 and wa == 0})
        return ergebnis

    def projekt(self, name):
        with self.sperre:
            return [t for t in self._offen() if t["project"] == name]

    def aufgaben(self, q=None, due_before=None, project=None):
        with self.sperre:
            l = self._offen()
        if q:
            l = [t for t in l if q.lower() in t["description"].lower()]
        if project:
            l = [t for t in l if t["project"] == project]
        if due_before:
            grenze = datetime.strptime(due_before, "%Y-%m-%d").date()
            l = [t for t in l if _tag_von(t["due"]) and _tag_von(t["due"]) < grenze]
        return _nach_dringlichkeit(l)

    def _hole(self, uuid):
        t = self.speicher.get(uuid)
        if t is None:
            raise ModulFehler("Diese Aufgabe gibt es nicht.")
        return t

    def aufgabe(self, uuid):
        with self.sperre:
            return copy.deepcopy(self._hole(uuid))

    def erledigt(self, uuid):
        with self.sperre:
            t = self._hole(uuid)
            t["status"], t["end"] = "completed", _jetzt()
            return copy.deepcopy(t)

    def starten(self, uuid):
        with self.sperre:
            t = self._hole(uuid)
            t["start"] = _jetzt()
            return copy.deepcopy(t)

    def stoppen(self, uuid):
        with self.sperre:
            t = self._hole(uuid)
            t["start"] = None
            return copy.deepcopy(t)

    def notiz(self, uuid, text):
        with self.sperre:
            t = self._hole(uuid)
            t["annotations"].append({"entry": _jetzt(), "description": str(text)})
            return copy.deepcopy(t)


class BeispielModul(Modul):
    def bereit(self):
        return True, "erfundene Aufgaben"

    def namen(self):
        return [p["name"] for p in self.aufgaben.projekte()]

    def stand(self):
        with self.aufgaben.sperre:
            return json.dumps(self.aufgaben.speicher, sort_keys=True)


def erstelle(name, konfig, kern):
    return BeispielModul(name, konfig, kern, titel=konfig.get("titel", "den Beispielaufgaben"),
                         aufgaben=Speicher())

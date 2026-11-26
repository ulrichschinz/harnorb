"""Modul taskwarrior: Aufgaben aus einem lokalen Taskwarrior (Befehl `task`, ab Version 2.6).

Die GTD-Listen folgen diesen Regeln:
    nächste  offene Aufgaben mit Tag `next`        warten  Tag `waiting`
    inbox    ohne Projekt und ohne Tags             verborgen  `wait` liegt in der Zukunft

    [module.taskwarrior]
    befehl = "task"                     # optional, Pfad zum Programm
    taskrc = "~/.taskrc"                # optional
    daten = "~/.task"                   # optional, rc.data.location
    tags = { next = "next", waiting = "waiting", someday = "someday" }   # optional
"""
import json
import os
import re
import shutil
import subprocess
from datetime import date, datetime, timezone
from pathlib import Path

from . import Aufgaben, Modul, ModulFehler

OFFEN = ["(", "status:pending", "or", "status:waiting", ")"]
ID = re.compile(r"[0-9a-fA-F-]{8,36}")


def _zeit(s):
    try:
        return datetime.strptime(s, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


def _tag(s):
    z = _zeit(s)
    return z.astimezone().date() if z else None


class Taskwarrior(Aufgaben):
    def __init__(self, befehl="task", taskrc=None, daten=None, tags=None):
        self.befehl = befehl
        self.taskrc = str(Path(taskrc).expanduser()) if taskrc else None
        self.daten = str(Path(daten).expanduser()) if daten else None
        t = {"next": "next", "waiting": "waiting", "someday": "someday"} | dict(tags or {})
        self.t_next, self.t_wait, self.t_some = t["next"], t["waiting"], t["someday"]

    # ---------- Aufruf ----------

    def vorhanden(self):
        return shutil.which(self.befehl) is not None

    def _task(self, *args):
        if not self.vorhanden():
            raise ModulFehler(f"Taskwarrior nicht gefunden ({self.befehl}).")
        rc = ["rc.confirmation=off", "rc.verbose=nothing", "rc.json.array=on", "rc.hooks=on"]
        if self.daten:
            rc.append(f"rc.data.location={self.daten}")
        env = os.environ | ({"TASKRC": self.taskrc} if self.taskrc else {})
        try:
            r = subprocess.run([self.befehl, *rc, *args], capture_output=True, text=True, timeout=20, env=env,
                               stdin=subprocess.DEVNULL)
        except (OSError, subprocess.TimeoutExpired) as e:
            raise ModulFehler(f"Taskwarrior antwortet nicht: {e}") from None
        if r.returncode != 0:
            raise ModulFehler(f"Taskwarrior: {(r.stderr or r.stdout).strip()[:200] or 'Fehler ' + str(r.returncode)}")
        return r.stdout

    def _export(self, *filter):
        roh = self._task(*filter, "export").strip()
        try:
            return json.loads(roh) if roh else []
        except json.JSONDecodeError:
            raise ModulFehler("Taskwarrior liefert kein JSON.") from None

    def _offen(self):
        jetzt = datetime.now(timezone.utc)
        alle = self._export(*OFFEN)
        for t in alle:
            w = _zeit(t.get("wait"))
            t["_verborgen"] = bool(w and w > jetzt)
        return alle

    @staticmethod
    def _sauber(l):
        return [{k: v for k, v in t.items() if not k.startswith("_")} for t in l]

    @staticmethod
    def _id(uuid):
        uuid = str(uuid or "").strip()
        if not ID.fullmatch(uuid):
            raise ModulFehler("Ungültige Aufgaben-ID.")
        return uuid

    # ---------- Listen ----------

    def summary(self):
        heute = date.today()
        roh = self._offen()
        sichtbar = [t for t in roh if not t["_verborgen"]]
        tags = lambda t: t.get("tags") or []
        return {
            "today": heute.isoformat(),
            "inbox": sum(1 for t in sichtbar if not t.get("project") and not tags(t)),
            "overdue": sum(1 for t in roh if (_tag(t.get("due")) or date.max) < heute),
            "due_today": sum(1 for t in roh if _tag(t.get("due")) == heute),
            "next": sum(1 for t in sichtbar if self.t_next in tags(t)),
            "waiting": sum(1 for t in roh if self.t_wait in tags(t)),
            "waiting_followup_due": sum(1 for t in roh if self.t_wait in tags(t)
                                        and (_tag(t.get("scheduled")) or date.max) <= heute),
            "someday": sum(1 for t in sichtbar if self.t_some in tags(t)),
        }

    def naechste(self):
        return self._sauber(t for t in self._offen() if not t["_verborgen"] and self.t_next in (t.get("tags") or []))

    def inbox(self):
        return self._sauber(t for t in self._offen()
                            if not t["_verborgen"] and not t.get("project") and not t.get("tags"))

    def warten(self):
        return self._sauber(t for t in self._offen() if self.t_wait in (t.get("tags") or []))

    def projekte(self):
        zahl = {}
        for t in self._offen():
            name = t.get("project")
            if not name:
                continue
            z = zahl.setdefault(name, {"name": name, "next": 0, "waiting": 0, "hidden": 0, "status": "active"})
            tags = t.get("tags") or []
            if t["_verborgen"]:
                z["hidden"] += 1
            elif self.t_next in tags:
                z["next"] += 1
            if self.t_wait in tags:
                z["waiting"] += 1
        for z in zahl.values():
            z["stalled"] = not (z["next"] or z["waiting"] or z["hidden"])
        return sorted(zahl.values(), key=lambda z: z["name"].lower())

    def projekt(self, name):
        return self._sauber(t for t in self._offen() if t.get("project") == name
                            or str(t.get("project") or "").startswith(name + "."))

    def aufgaben(self, q=None, due_before=None, project=None):
        grenze = date.fromisoformat(due_before) if due_before else None
        q = (q or "").lower()
        def passt(t):
            if project and t.get("project") != project:
                return False
            if grenze and not (_tag(t.get("due")) or date.max) < grenze:
                return False
            if q:
                text = " ".join([t.get("description") or "", t.get("project") or ""] +
                                [a.get("description") or "" for a in t.get("annotations") or []])
                return q in text.lower()
            return True
        return self._sauber(t for t in self._offen() if passt(t))

    def aufgabe(self, uuid):
        l = self._export(f"uuid:{self._id(uuid)}")
        if not l:
            raise ModulFehler("Aufgabe nicht gefunden.")
        return l[0]

    # ---------- Aktionen ----------

    def erledigt(self, uuid):
        self._task(self._id(uuid), "done")
        return {"ok": True}

    def starten(self, uuid):
        self._task(self._id(uuid), "start")
        return {"ok": True}

    def stoppen(self, uuid):
        self._task(self._id(uuid), "stop")
        return {"ok": True}

    def notiz(self, uuid, text):
        text = str(text or "").strip()
        if not text:
            raise ModulFehler("Notiz ist leer.")
        self._task(self._id(uuid), "annotate", "--", text)
        return {"ok": True}


class TaskwarriorModul(Modul):
    def bereit(self):
        if not self.aufgaben.vorhanden():
            return False, f"Programm {self.aufgaben.befehl} fehlt"
        return True, "lokal"

    def prompt(self):
        return self.konfig.get("prompt", "Aufgaben liegen in einem lokalen Taskwarrior (Befehl task). Für Änderungen, die "
                                         "die Szene nicht kann, nimm task über die Shell.")

    def namen(self):
        try:
            return [p["name"] for p in self.aufgaben.projekte()]
        except Exception:
            return []

    def stand(self):
        if not self.aufgaben.vorhanden():
            return None
        return json.dumps(self.aufgaben.summary(), sort_keys=True)


def erstelle(name, konfig, kern):
    tw = Taskwarrior(konfig.get("befehl") or "task", konfig.get("taskrc"), konfig.get("daten"), konfig.get("tags"))
    return TaskwarriorModul(name, konfig, kern, titel=konfig.get("titel", "Taskwarrior"), aufgaben=tw,
                            aendert_bei=("task",))

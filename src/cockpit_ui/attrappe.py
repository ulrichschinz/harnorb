"""Attrappen-Agent für Tests (COCKPIT_UI_AGENT=attrappe): kein Claude, keine Kosten.

Gleiche Schnittstelle wie ClaudeAgent (`sende`, `unterbrechen`, `neu`, `laeuft`, `zug`). Die Antworten
sind skriptgesteuert nach Stichwörtern im gesagten Text und erzeugen dieselben Ereignisse wie Claude:
Text (in Stücken gestreamt), Gedanken, Werkzeuge (auch mcp__szene__…, die die Szene wirklich steuern),
Erlaubnisfragen und Fehler.
"""
import asyncio
import re
import time
import uuid as uuidlib

from .szene import ZAHLWORT


class AttrappenAgent:
    TAKT = 0.04  # Sekunden zwischen Textstücken

    def __init__(self, cockpit, rueckfrage, melde, szene=None, **_):
        self.rueckfrage = rueckfrage
        self.melde = melde
        self.szene = szene
        self.zug = None
        self.zug_nr = 0
        self._abbruch = False
        self._aufgabe = None
        self._schlange = []

    @property
    def laeuft(self):
        return self.zug is not None

    async def sende(self, prompt, anzeige=None, quelle="text"):
        if self.zug is None:
            self.zug_nr += 1
            self.zug = self.zug_nr
            self._abbruch = False
            self.melde({"typ": "zug_start", "zug": self.zug, "ausloeser": "uli"})
            self.melde({"typ": "nutzer", "zug": self.zug, "id": str(uuidlib.uuid4()), "text": anzeige or prompt, "quelle": quelle})
            self._aufgabe = asyncio.create_task(self._zug(anzeige or prompt, self.zug))
        else:  # mitten im Zug: wie bei Claude einreihen
            self.melde({"typ": "nutzer", "zug": self.zug, "id": str(uuidlib.uuid4()), "text": anzeige or prompt, "quelle": quelle})
            self._schlange.append(anzeige or prompt)

    async def unterbrechen(self):
        self._abbruch = True

    async def neu(self):
        self._abbruch = True
        if self._aufgabe and not self._aufgabe.done():
            self._aufgabe.cancel()
        self.zug = None
        self._schlange.clear()

    # ---------- Ablauf ----------

    async def _sag(self, zug, text):
        for stueck in re.findall(r"\S+\s*", text):
            if self._abbruch:
                return
            self.melde({"typ": "text", "zug": zug, "text": stueck})
            await asyncio.sleep(self.TAKT)
        self.melde({"typ": "text", "zug": zug, "text": "\n\n"})

    async def _werkzeug(self, zug, name, args=None, dauer=0.3):
        wid = "toolu_" + uuidlib.uuid4().hex[:12]
        self.melde({"typ": "werkzeug", "zug": zug, "wid": wid, "name": name})
        fehler, ergebnis = False, ""
        try:
            if name.startswith("mcp__szene__") and self.szene:
                ergebnis = await self.szene(name.removeprefix("mcp__szene__"), args or {})
            else:
                await asyncio.sleep(dauer)
        except Exception as e:
            fehler, ergebnis = True, f"Fehler: {e}"
        self.melde({"typ": "werkzeug_ende", "zug": zug, "wid": wid, "name": name, "fehler": fehler})
        return fehler, ergebnis

    async def _zug(self, text, zug):
        beginn = time.perf_counter()
        fehler = None
        try:
            await self._antwort(text, zug)
            while self._schlange and not self._abbruch:
                await self._antwort(self._schlange.pop(0), zug)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            fehler = f"Attrappe: {e}"
        finally:
            if self.zug == zug:
                self.zug = None
                self.melde({"typ": "zug_ende", "zug": zug, "sekunden": round(time.perf_counter() - beginn, 1),
                            "kosten": 0.0, "abgebrochen": self._abbruch, "fehler": fehler})

    async def _antwort(self, text, zug):
        t = text.lower()
        sz = "mcp__szene__"

        def anzahl(ergebnis):
            m = re.search(r", (\d+) Einträge", ergebnis)
            return int(m.group(1)) if m else 0

        def titel_liste(ergebnis, n=3):
            return [re.sub(r" \[.*$", "", z.split(". ", 1)[1]) for z in ergebnis.splitlines()[1:n + 1] if ". " in z]

        async def liste(art, satz):
            await self._sag(zug, "Ich hole die Liste.")
            f, e = await self._werkzeug(zug, sz + "zeige_liste", {"art": art})
            if f:
                return await self._sag(zug, "Das hat nicht geklappt. " + e)
            n = anzahl(e)
            titel = titel_liste(e)
            await self._sag(zug, f"{satz} {n} Einträge." + (" Oben stehen " + ", ".join(titel) + "." if titel else ""))

        if "fehler" in t:
            await self._sag(zug, "Ich simuliere jetzt einen Fehler.")
            raise RuntimeError("simulierter Fehler")
        if "erlaubnis" in t:
            await self._sag(zug, "Dafür brauche ich deine Erlaubnis.")
            ja = await self.rueckfrage("Bash", {"command": "echo 'Attrappe fragt um Erlaubnis'"})
            return await self._sag(zug, "Danke, erlaubt." if ja else "In Ordnung, ich lasse es.")
        if re.search(r"\b(denk|lange|recherch)", t):
            self.melde({"typ": "denken", "zug": zug, "text": "Ich überlege, welche Quellen passen …"})
            await self._sag(zug, "Ich schaue in mehreren Quellen nach.")
            for name in ("mcp__aufgaben__summary", "Grep", "Read", "mcp__aufgaben__next"):
                if self._abbruch:
                    return
                await self._werkzeug(zug, name, dauer=1.2)
            return await self._sag(zug, "Fertig nachgedacht. Das Ergebnis ist eine ausgedachte Antwort der Attrappe.")
        for w, stil in (("comic", {"stil": "comic"}), ("leuchtend", {"stil": "leuchtend"}), ("realistisch", {"stil": "leuchtend"}),
                        ("kugelraumer", {"hintergrund": "raumer"}), ("raumer", {"hintergrund": "raumer"}),
                        ("mond", {"hintergrund": "mond"})):
            if w in t:
                await self._werkzeug(zug, sz + "stil", stil)
                return await self._sag(zug, "So sieht es jetzt aus.")
        m = re.search(r"projekt (\w[\w\-]*)", t)
        if m and "projekte" not in t:
            return await liste("projekt:" + m.group(1), f"Das Projekt {m.group(1)} hat")
        for muster, art, satz in ((r"überfällig", "ueberfaellig", "Überfällig sind"), (r"inbox|eingang", "inbox", "In der Inbox liegen"),
                                  (r"warte", "warten", "Du wartest auf"), (r"projekte", "projekte", "Aktiv sind"),
                                  (r"todo|todes|aufgaben|heute|steht an", "heute", "Heute stehen an:")):
            if re.search(muster, t):
                return await liste(art, satz)
        if re.search(r"weg damit|ausblenden|blende|zurück", t):
            await self._werkzeug(zug, sz + "ausblenden")
            return await self._sag(zug, "Weg ist es.")
        if re.search(r"erledigt|fertig|abhaken", t):
            f, e = await self._werkzeug(zug, sz + "erledigt", {})
            return await self._sag(zug, "Erledigt, gut gemacht." if not f else "Das ging nicht. " + e)
        if re.search(r"arbeite|fokus|nehme ich", t):
            f, e = await self._werkzeug(zug, sz + "fokus", {})
            return await self._sag(zug, "Im Fokus. Viel Erfolg." if not f else "Welche Aufgabe meinst du?")
        if re.search(r"was mache ich mit", t):
            nr = next((ZAHLWORT[w] for w in re.findall(r"[a-zäöü]+", t) if w in ZAHLWORT), 1)
            await self._werkzeug(zug, sz + "waehle", {"nummer": nr})
            await self._werkzeug(zug, sz + "zeige_optionen", {"frage": "Was wird daraus?",
                                                             "optionen": ["Nächste Aktion", "Projekt", "Irgendwann", "Löschen"]})
            return await self._sag(zug, "Ich schlage vor, daraus eine nächste Aktion zu machen. Die Möglichkeiten siehst du.")
        nr = next((w for w in re.findall(r"[a-zäöü]+|\d+", t) if w in ZAHLWORT or w.isdigit()), None)
        if nr is not None:
            f, e = await self._werkzeug(zug, sz + "waehle", {"nummer": nr})
            return await self._sag(zug, e.replace("Hervorgehoben: ", "Die hier: ") if not f else "Die Nummer sehe ich nicht.")
        if re.search(r"entwurf|tafel|text", t):
            await self._werkzeug(zug, sz + "zeige_text", {"titel": "Entwurf: Antwort an die Druckerei",
                                                          "inhalt": "Hallo zusammen,\n\nvielen Dank für das Angebot. **Bitte** schickt uns noch einen Probedruck.\n\n- Auflage 500\n- Papier 170 g\n\nViele Grüße"})
            return await self._sag(zug, "Den Entwurf siehst du auf der Tafel.")
        if re.search(r"welche|zeig mal|optionen", t):
            await self._werkzeug(zug, sz + "zeige_optionen", {"frage": "Welche Liste?", "optionen": ["Heute", "Überfällig", "Inbox"]})
            return await self._sag(zug, "Welche Liste meinst du: heute, überfällig oder die Inbox?")
        await self._sag(zug, f"Ich bin die Attrappe und habe verstanden: {text.strip()} Das ist eine längere Antwort, "
                             "damit man sieht, wie HarnoRb spricht und wie die Untertitel laufen.")

"""Szenenzustand der 3D-Oberfläche „HarnoRb“ und die Aktionen, die ihn ändern.

Die Szene ist leer, bis das Gespräch (Werkzeuge des MCP-Servers `szene`), ein Schnellbefehl
oder eine Taste etwas einblendet. Jede Aktion ändert den Zustand hier auf dem Server und geht als
Ereignis ins Protokoll, damit die Szene nach einem Neuladen wiederhergestellt werden kann:

    szene  {aktion, zug?, zustand, ...}
      aktion = liste     {art, titel, karten, gesamt}
               waehle    {uuid, nr}
               fokus     {karte}
               ausblenden
               erledigt  {karte}        (Erledigt-Strahl, danach ist die Karte fort)
               text      {titel, inhalt}
               optionen  {frage, optionen}
               stil      {stil, hintergrund}
               auffrischen {karten}     (die Aufgabenquelle hat sich geändert, Liste neu)

`zustand` ist immer der vollständige Szenenzustand nach der Aktion (siehe `Szene.leer`).
Die Kartendaten holt der Server direkt aus dem Aufgabenmodul (module.Aufgaben), Claude übergibt
nur Art und Filter. Ohne Aufgabenmodul gibt es nur Text, Optionen, Stil und Ausblenden.
"""
import asyncio
import difflib
import json
import re
from datetime import date, datetime, timezone

from .module import ModulFehler

ANSICHTEN = ("leer", "liste", "fokus", "text", "optionen")
STILE = ("leuchtend", "comic")
HINTERGRUENDE = ("mond", "raumer")
LISTEN = ("heute", "ueberfaellig", "naechste", "inbox", "warten", "projekte")
MAX_KARTEN = 12
ID = re.compile(r"[A-Za-z0-9][\w.:-]{0,63}")  # Aufgaben-ID (z. B. Taskwarrior-UUID)

TITEL = {"heute": "Heute", "ueberfaellig": "Überfällig", "naechste": "Nächste Aktionen", "inbox": "Inbox",
         "warten": "Warten auf", "projekte": "Projekte"}
ZAHLWORT = {"erste": 1, "ersten": 1, "zweite": 2, "zweiten": 2, "dritte": 3, "dritten": 3, "vierte": 4,
            "vierten": 4, "fünfte": 5, "fünften": 5, "sechste": 6, "sechsten": 6, "siebte": 7, "siebten": 7,
            "achte": 8, "achten": 8, "neunte": 9, "neunten": 9, "zehnte": 10, "zehnten": 10,
            "letzte": -1, "letzten": -1, "eins": 1, "zwei": 2, "drei": 3, "vier": 4, "fünf": 5,
            "sechs": 6, "sieben": 7, "acht": 8, "neun": 9, "zehn": 10}


ALIAS = {"todos": "heute", "aufgaben": "heute", "today": "heute", "overdue": "ueberfaellig", "next": "naechste",
         "nächste": "naechste", "eingang": "inbox", "waiting": "warten", "projects": "projekte"}


def normiere_art(art):
    art = str(art or "heute").strip()
    kopf, sep, rest = art.partition(":")
    kopf = kopf.lower()
    if sep and kopf in ("projekt", "suche"):
        return f"{kopf}:{rest.strip()}"
    kopf = kopf.replace("ü", "ue").replace("ä", "ae")
    return ALIAS.get(kopf, kopf)


class SzenenFehler(Exception):
    pass


def tw_tag(s):
    """Taskwarrior-Datum 20261117T230000Z -> lokales Datum."""
    if not s:
        return None
    try:
        return datetime.strptime(s, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc).astimezone().date()
    except ValueError:
        return None


FARBEN = ("blau", "gruen", "gelb", "orange", "rot", "violett", "grau")
EFFEKTE = ("strahl", "sanft")          # eingebaut; Module können eigene im Browser anmelden
NAME = re.compile(r"[a-z0-9][a-z0-9_-]{0,31}")
FARBE = re.compile(r"#[0-9a-fA-F]{3}([0-9a-fA-F]{3})?")


def anzeige(roh):
    """Darstellungshinweise eines Moduls prüfen und kürzen. Unbekanntes fällt still weg.
        {abzeichen: str | [str] (bis 3), farbe: Name aus FARBEN oder #hex, symbol: bis 4 Zeichen,
         untertitel: bis 120 Zeichen, art: Kartenart eines Moduls, effekt: Erledigt-Effekt}"""
    if not isinstance(roh, dict):
        return {}
    a = {}
    abz = roh.get("abzeichen")
    abz = [abz] if isinstance(abz, str) else abz if isinstance(abz, list) else []
    if abz := [str(x)[:24] for x in abz if str(x or "").strip()][:3]:
        a["abzeichen"] = abz
    f = str(roh.get("farbe") or "").strip()
    if f in FARBEN or FARBE.fullmatch(f):
        a["farbe"] = f
    if s := str(roh.get("symbol") or "").strip()[:4]:
        a["symbol"] = s
    if u := str(roh.get("untertitel") or "").strip()[:120]:
        a["untertitel"] = u
    for schl in ("art", "effekt"):
        w = str(roh.get(schl) or "").strip().lower()
        if NAME.fullmatch(w):
            a[schl] = w
    if isinstance(roh.get("daten"), dict):   # frei für eigene Kartenarten, klein halten
        d = json.dumps(roh["daten"], ensure_ascii=False)
        if len(d) <= 4000:
            a["daten"] = roh["daten"]
    return a


def karte(t, nr, heute=None):
    heute = heute or date.today()
    tag = tw_tag(t.get("due"))
    return {"anzeige": anzeige(t.get("anzeige")), "art": "aufgabe", "nr": nr, "uuid": str(t.get("uuid") or ""), "titel": str(t.get("description") or ""),
            "projekt": t.get("project") or "", "faellig": tag.isoformat() if tag else None,
            "ueberfaellig": bool(tag and tag < heute), "heute": tag == heute,
            "tags": [x for x in (t.get("tags") or []) if x.startswith("@")], "laeuft": bool(t.get("start"))}


def projekt_karte(p, nr):
    info = f"{p.get('next', 0)} nächste · {p.get('waiting', 0)} warten"
    return {"anzeige": anzeige(p.get("anzeige")), "art": "projekt", "nr": nr, "uuid": "", "titel": str(p.get("name") or ""), "projekt": str(p.get("name") or ""),
            "info": info + (" · steht still" if p.get("stalled") else ""), "faellig": None,
            "ueberfaellig": False, "heute": False, "tags": [], "laeuft": False, "steht_still": bool(p.get("stalled"))}


def nummer_aus(wert):
    """'2', 2, 'die zweite', 'zweiten' -> 2; 'letzte' -> -1; sonst None."""
    if isinstance(wert, int):
        return wert
    s = str(wert or "").strip().lower()
    if re.fullmatch(r"-?\d+", s):
        return int(s)
    for w in re.findall(r"[a-zäöüß]+", s):
        if w in ZAHLWORT:
            return ZAHLWORT[w]
    m = re.search(r"\d+", s)
    return int(m.group()) if m else None


class Szene:
    def __init__(self, aufgaben, melde, setze_fokus=None, quelle="der Aufgabenquelle"):
        """aufgaben: module.Aufgaben oder None (kein Aufgabenmodul); quelle: Name für Rückmeldungen.
        melde(ereignis) wie Sitzung.melde; setze_fokus({"uuid","titel"} | None) hält den
        Gesprächskontext (Aufgabe im Fokus) in der Sitzung aktuell."""
        self.aufgaben = aufgaben
        self.quelle = quelle
        self.melde = melde
        self.setze_fokus = setze_fokus or (lambda f: None)
        self.zustand = self.leer()
        self.stil = "leuchtend"
        self.hintergrund = "mond"

    @staticmethod
    def leer():
        return {"ansicht": "leer", "liste": None, "titel": "", "karten": [], "gesamt": 0, "gewaehlt": None,
                "fokus": None, "text": None, "optionen": None}

    def schnappschuss(self):
        return self.zustand | {"stil": self.stil, "hintergrund": self.hintergrund}

    def _melde(self, aktion, zug=None, **mehr):
        ev = {"typ": "szene", "aktion": aktion} | mehr | {"zustand": self.schnappschuss()}
        if zug is not None:
            ev["zug"] = zug
        self.melde(ev)

    async def _rw(self, methode, *a, **kw):
        if self.aufgaben is None:
            raise SzenenFehler("Es ist kein Aufgabenmodul aktiv.")
        fn = getattr(self.aufgaben, methode)
        loop = asyncio.get_running_loop()
        try:
            return await loop.run_in_executor(None, lambda: fn(*a, **kw))
        except ModulFehler as e:
            raise SzenenFehler(str(e)) from None

    # ---------- Daten ----------

    async def _lade(self, art):
        heute = date.today()
        if art in ("heute", "naechste"):
            l = await self._rw("naechste") or []
            if art == "heute":
                def wichtig(t):
                    tag = tw_tag(t.get("due"))
                    return t.get("start") or (tag and tag <= heute)
                h = [t for t in l if wichtig(t)]
                h.sort(key=lambda t: (not t.get("start"), tw_tag(t.get("due")) or date.max))
                if h:
                    return "Heute", h
                return "Nächste Aktionen (heute nichts fällig)", l
            l.sort(key=lambda t: tw_tag(t.get("due")) or date.max)
            return TITEL[art], l
        if art == "ueberfaellig":
            l = await self._rw("aufgaben", due_before=heute.isoformat()) or []
            l = [t for t in l if (tw_tag(t.get("due")) or date.max) < heute]
            l.sort(key=lambda t: tw_tag(t.get("due")))
            return TITEL[art], l
        if art == "inbox":
            return TITEL[art], await self._rw("inbox") or []
        if art == "warten":
            return TITEL[art], await self._rw("warten") or []
        if art == "projekte":
            l = [p for p in (await self._rw("projekte") or []) if (p.get("status") or "active") == "active"]
            return TITEL[art], l
        if art.startswith("projekt:"):
            name = await self._projektname(art.split(":", 1)[1])
            return f"Projekt {name}", await self._rw("projekt", name) or []
        if art.startswith("suche:"):
            q = art.split(":", 1)[1].strip()
            if not q:
                raise SzenenFehler("Suche ohne Suchtext")
            return f"Suche „{q}“", await self._rw("aufgaben", q=q) or []
        raise SzenenFehler(f"Unbekannte Liste {art!r}. Möglich: {', '.join(LISTEN)}, projekt:<name>, suche:<text>")

    async def _projektname(self, gesucht):
        gesucht = gesucht.strip()
        namen = [p.get("name") for p in (await self._rw("projekte") or []) if p.get("name")]
        if gesucht in namen:
            return gesucht
        einfach = lambda s: re.sub(r"[\W_]+", "", s.lower())
        g = einfach(gesucht)
        for n in namen:
            if einfach(n) == g or einfach(n.split(".")[-1]) == g:
                return n
        teil = [n for n in namen if g and g in einfach(n)]
        if len(teil) == 1:
            return teil[0]
        aehnlich = difflib.get_close_matches(g, [einfach(n) for n in namen], n=1, cutoff=0.6)
        if aehnlich:
            return next(n for n in namen if einfach(n) == aehnlich[0])
        raise SzenenFehler(f"Kein Projekt passt zu „{gesucht}“. Vorhanden: {', '.join(namen[:20])}")

    def _karte_zu(self, wert):
        """Nummer ('die zweite') oder UUID -> Karte der sichtbaren Liste."""
        karten = self.zustand["karten"]
        if wert in (None, ""):
            return None
        s = str(wert).strip()
        for k in karten:
            if k["uuid"] and (k["uuid"] == s or (len(s) >= 8 and k["uuid"].startswith(s))):
                return k
        n = nummer_aus(s)
        if n is not None and karten:
            if n == -1:
                return karten[-1]
            for k in karten:
                if k["nr"] == n:
                    return k
        return None

    # ---------- Aktionen ----------

    async def liste(self, art, filter=None, zug=None):
        art = normiere_art(art)
        titel, eintraege = await self._lade(art)
        if filter:
            f = filter.lower()
            eintraege = [t for t in eintraege if f in (str(t.get("description") or t.get("name") or "") + " " +
                                                       str(t.get("project") or "")).lower()]
        heute = date.today()
        if art == "projekte":
            karten = [projekt_karte(p, i + 1) for i, p in enumerate(eintraege[:MAX_KARTEN])]
        else:
            karten = [karte(t, i + 1, heute) for i, t in enumerate(eintraege[:MAX_KARTEN])]
        self.zustand = self.leer() | {"ansicht": "liste", "liste": art, "titel": titel, "karten": karten,
                                      "gesamt": len(eintraege)}  # eine neue Liste verdrängt den Fokus aus der Mitte
        self._melde("liste", zug, art=art, titel=titel, karten=karten, gesamt=len(eintraege))
        return self._beschreibe_liste()

    def _beschreibe_liste(self):
        z = self.zustand
        if not z["karten"]:
            return f"Eingeblendet: {z['titel']}, keine Einträge."
        zeilen = [f"Eingeblendet: {z['titel']}, {z['gesamt']} Einträge"
                  + (f" (die ersten {len(z['karten'])} sichtbar)" if z["gesamt"] > len(z["karten"]) else "") + ":"]
        for k in z["karten"]:
            extra = [k.get("projekt") if k["art"] == "aufgabe" else k.get("info"),
                     k["faellig"] and ("überfällig seit " if k["ueberfaellig"] else "fällig ") + k["faellig"],
                     "läuft" if k["laeuft"] else ""]
            zeilen.append(f"{k['nr']}. {k['titel']}" + (f" [{k['uuid']}]" if k["uuid"] else "")
                          + "".join(f" · {x}" for x in extra if x))
        return "\n".join(zeilen)

    async def waehle(self, wert, zug=None):
        k = self._karte_zu(wert)
        if k is None:
            raise SzenenFehler("Keine passende Karte in der sichtbaren Liste." if self.zustand["karten"]
                               else "Es ist keine Liste eingeblendet.")
        self.zustand["gewaehlt"] = k["nr"]
        self._melde("waehle", zug, nr=k["nr"], uuid=k["uuid"])
        return f"Hervorgehoben: {k['nr']}. {k['titel']}" + (f" [{k['uuid']}]" if k["uuid"] else "")

    async def fokus(self, wert=None, zug=None):
        k = self._karte_zu(wert) if wert not in (None, "") else None
        if k is None and wert in (None, "") and self.zustand["gewaehlt"]:
            k = self._karte_zu(self.zustand["gewaehlt"])
        if k is not None and k["art"] == "projekt":
            return await self.liste("projekt:" + k["titel"], zug=zug)
        uuid = k["uuid"] if k else str(wert or "").strip()
        if not ID.fullmatch(uuid):
            raise SzenenFehler("Welche Aufgabe? Nummer der Karte oder UUID angeben.")
        t = await self._rw("aufgabe", uuid)
        if not isinstance(t, dict) or t.get("status") in ("completed", "deleted"):
            raise SzenenFehler("Die Aufgabe ist nicht offen.")
        fk = karte(t, k["nr"] if k else 0) | {
            "notizen": [{"tag": (tw_tag(a.get("entry")) or date.today()).isoformat(), "text": a.get("description") or ""}
                        for a in (t.get("annotations") or [])][-6:]}
        self.zustand = self.zustand | {"ansicht": "fokus", "fokus": fk, "gewaehlt": fk["nr"] or None,
                                       "text": None, "optionen": None}
        self.setze_fokus({"uuid": fk["uuid"], "titel": fk["titel"]})
        self._melde("fokus", zug, karte=fk)
        return f"Im Fokus: {fk['titel']} [{fk['uuid']}]" + (f", Projekt {fk['projekt']}" if fk["projekt"] else "")

    async def ausblenden(self, behalte_fokus=False, zug=None):
        fokus = self.zustand.get("fokus") if behalte_fokus else None
        self.zustand = self.leer() | ({"ansicht": "fokus", "fokus": fokus} if fokus else {})
        if not fokus:
            self.setze_fokus(None)
        self._melde("ausblenden", zug)
        return "Szene ist leer." if not fokus else "Alles ausgeblendet außer der Aufgabe im Fokus."

    async def erledigt(self, wert=None, zug=None):
        k = self._karte_zu(wert) if wert not in (None, "") else None
        f = self.zustand.get("fokus")
        if k is None and wert in (None, ""):
            k = f or self._karte_zu(self.zustand["gewaehlt"])
        uuid = k["uuid"] if k else str(wert or "").strip()
        if not ID.fullmatch(uuid or ""):
            raise SzenenFehler("Welche Aufgabe ist erledigt? Nummer oder UUID angeben.")
        if k is None:
            t = await self._rw("aufgabe", uuid)
            k = karte(t, 0)
        await self._rw("erledigt", uuid)
        rest = [x for x in self.zustand["karten"] if x["uuid"] != uuid]
        for i, x in enumerate(rest):
            x["nr"] = i + 1
        war_fokus = bool(f and f["uuid"] == uuid)
        self.zustand = self.zustand | {"karten": rest, "gesamt": max(0, self.zustand["gesamt"] - (len(self.zustand["karten"]) - len(rest))),
                                       "gewaehlt": None}
        if war_fokus:
            self.zustand["fokus"] = None
            self.setze_fokus(None)
        if self.zustand["ansicht"] == "fokus" and not self.zustand["fokus"]:
            self.zustand["ansicht"] = "liste" if rest else "leer"
        if self.zustand["ansicht"] == "liste" and not rest:
            self.zustand = self.leer()
        self._melde("erledigt", zug, karte=k)
        return f"Erledigt in {self.quelle}: {k['titel']}."

    async def text(self, titel, inhalt, zug=None):
        titel, inhalt = str(titel or "")[:200], str(inhalt or "")[:20000]
        self.zustand = self.zustand | {"ansicht": "text", "text": {"titel": titel, "inhalt": inhalt}, "optionen": None}
        self._melde("text", zug, titel=titel, inhalt=inhalt)
        return f"Tafel „{titel}“ eingeblendet."

    async def optionen(self, frage, optionen, zug=None):
        optionen = [str(o)[:80] for o in (optionen or [])][:6]
        if not optionen:
            raise SzenenFehler("Keine Optionen angegeben.")
        self.zustand = self.zustand | {"ansicht": "optionen", "optionen": {"frage": str(frage or "")[:200], "optionen": optionen}}
        self._melde("optionen", zug, frage=frage, optionen=optionen)
        return "Optionen eingeblendet: " + ", ".join(f"{i + 1}. {o}" for i, o in enumerate(optionen))

    async def setze_stil(self, stil=None, hintergrund=None, zug=None):
        if stil:
            stil = {"realistisch": "leuchtend", "cartoon": "comic"}.get(stil, stil)
            if stil not in STILE:
                raise SzenenFehler(f"Stil {stil!r} gibt es nicht. Möglich: {', '.join(STILE)}")
            self.stil = stil
        if hintergrund:
            hintergrund = {"kugelraumer": "raumer", "nathan": "mond", "raumschiff": "raumer", "rauma": "raumer", "kugelrauma": "raumer"}.get(hintergrund, hintergrund)
            if hintergrund not in HINTERGRUENDE:
                raise SzenenFehler(f"Hintergrund {hintergrund!r} gibt es nicht. Möglich: {', '.join(HINTERGRUENDE)}")
            self.hintergrund = hintergrund
        self._melde("stil", zug, stil=self.stil, hintergrund=self.hintergrund)
        return f"Stil {self.stil}, Hintergrund {self.hintergrund}."

    async def auffrischen(self):
        """Sichtbare Liste neu laden (Aufgabenquelle hat sich geändert). Leise: kein Fehler nach außen."""
        z = self.zustand
        if z["ansicht"] != "liste" or not z["liste"]:
            return
        try:
            _, eintraege = await self._lade(z["liste"])
        except SzenenFehler:
            return
        heute = date.today()
        neu = ([projekt_karte(p, i + 1) for i, p in enumerate(eintraege[:MAX_KARTEN])] if z["liste"] == "projekte"
               else [karte(t, i + 1, heute) for i, t in enumerate(eintraege[:MAX_KARTEN])])
        if [k["uuid"] + k["titel"] for k in neu] == [k["uuid"] + k["titel"] for k in z["karten"]]:
            return
        self.zustand = z | {"karten": neu, "gesamt": len(eintraege), "gewaehlt": None}
        self._melde("auffrischen", karten=neu)

    def kontext(self):
        """Kurzbeschreibung des Sichtbaren für den Prompt, damit „die zweite“ eindeutig ist."""
        z = self.zustand
        if z["ansicht"] == "leer":
            return "Die Szene ist leer."
        if z["ansicht"] == "fokus" and z["fokus"]:
            return f"Im Fokus steht {z['fokus']['titel']} [{z['fokus']['uuid']}]."
        if z["ansicht"] == "text" and z["text"]:
            return f"Eingeblendet ist die Tafel „{z['text']['titel']}“."
        if z["ansicht"] == "optionen" and z["optionen"]:
            return "Eingeblendet sind Optionen: " + ", ".join(f"{i + 1}. {o}" for i, o in enumerate(z["optionen"]["optionen"]))
        teile = [f"{k['nr']}. {k['titel']}" + (f" [{k['uuid'][:8]}]" if k["uuid"] else "") for k in z["karten"]]
        g = f" Hervorgehoben ist Nummer {z['gewaehlt']}." if z["gewaehlt"] else ""
        return f"Eingeblendet ist die Liste {z['titel']}: " + "; ".join(teile) + "." + g

    async def aktion(self, name, args, zug=None):
        """Zentraler Einstieg für Werkzeuge, Schnellbefehle und Tasten."""
        a = args or {}
        if name == "zeige_liste":
            return await self.liste(a.get("art") or "heute", a.get("filter"), zug=zug)
        if name == "waehle":
            return await self.waehle(a.get("nummer") if a.get("nummer") not in (None, "") else a.get("uuid"), zug=zug)
        if name == "fokus":
            return await self.fokus(a.get("uuid") or a.get("nummer"), zug=zug)
        if name == "ausblenden":
            return await self.ausblenden(bool(a.get("behalte_fokus")), zug=zug)
        if name == "erledigt":
            return await self.erledigt(a.get("uuid") or a.get("nummer"), zug=zug)
        if name == "zeige_text":
            return await self.text(a.get("titel"), a.get("inhalt"), zug=zug)
        if name == "zeige_optionen":
            return await self.optionen(a.get("frage"), a.get("optionen"), zug=zug)
        if name == "stil":
            return await self.setze_stil(a.get("stil"), a.get("hintergrund"), zug=zug)
        raise SzenenFehler(f"Unbekannte Szenen-Aktion {name!r}")

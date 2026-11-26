"""HTTP- und WebSocket-Server. Nur 127.0.0.1, Host- und Origin-Prüfung."""
import asyncio
import base64
import hashlib
import json
import os
import re
import time
import uuid as uuidlib
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, Request, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import bedienung, dateien, konfig, module, schnellbefehl, stimmen, themes
from .agent import AUFGABEN_WERKZEUGE, ClaudeAgent, sprechstil, szene_werkzeuge
from .attrappe import AttrappenAgent
from .einstellungen import Einstellungen
from .module import ModulFehler
from .szene import ID, Szene, SzenenFehler
from .sprache import ElevenLabsStimme, Erkenner, Satzpuffer, Stimme, brauchbar, elevenlabs_fehler, vorlesbar

E = Einstellungen()
WEB = Path(__file__).resolve().parents[2] / "web"
ERLAUBTE_HOSTS = {f"127.0.0.1:{E.port}", f"localhost:{E.port}"}

app = FastAPI(title="cockpit-ui", docs_url=None, redoc_url=None, openapi_url=None)

# ---------- Module (Konfiguration je Rechner, siehe konfig.py und docs/module-schreiben.md) ----------

K = konfig.lade()
COCKPIT = Path(os.environ["COCKPIT_DIR"]).expanduser() if os.environ.get("COCKPIT_DIR") else (K.cockpit or E.cockpit)
MODULE, _fehler = module.lade(K.module, module.Kern(COCKPIT, K.person), K.module_pfade)
MODUL_FEHLER = K.fehler + _fehler
for _f in MODUL_FEHLER:
    print(f"cockpit-ui: {_f}", flush=True)
AUFGABEN_MODUL = next((m for m in MODULE if m.aufgaben is not None and (not K.aufgaben or m.name == K.aufgaben)), None)
AUFGABEN = AUFGABEN_MODUL.aufgaben if AUFGABEN_MODUL else None
QUELLE = AUFGABEN_MODUL.titel if AUFGABEN_MODUL else ""
zustand = {"erkenner": None, "stimme": None, "elevenlabs": None, "vorleser": E.standard_stimme,
           "el_stimme": E.elevenlabs_stimme, "el_stimmen": [],
           "dienste": {}, "http_wahl": ""}   # Stimmendienste im Netz: name -> HttpStimme; Wahl "dienst:stimme"
GESPEICHERT = stimmen.lade()


def _vorleser_wert():
    """Wert für das Auswahlmenü: "piper", "elevenlabs:<voice_id>" oder "http:<dienst>:<stimme>"."""
    if zustand["vorleser"] == "elevenlabs":
        return f"elevenlabs:{zustand['el_stimme']}"
    if zustand["vorleser"] == "http":
        return f"http:{zustand['http_wahl']}"
    return "piper"


def _http_stimmen():
    return [{"id": f"{d.name}:{v['id']}", "name": v["name"], "art": "http", "gruppe": f"Stimmendienst {d.name}",
             "geschlecht": "", "akzent": "", "beschreibung": v["beschreibung"]}
            for d in zustand["dienste"].values() for v in d.stimmen_liste]


def _alle_stimmen():
    """Alle wählbaren Stimmen außer Piper, für Namen per Sprache und das Auswahlmenü."""
    el = [dict(v, art="elevenlabs") for v in zustand["el_stimmen"]] if zustand["elevenlabs"] is not None else []
    return _http_stimmen() + el


def _stimmen_fuer_menue():
    liste = [{"wert": "piper", "name": "Lokal (Piper)", "gruppe": "Lokal"}]
    for v in _alle_stimmen():
        gruppe = v["gruppe"] if v["art"] == "http" else "ElevenLabs – " + bedienung.GESCHLECHT.get(v["geschlecht"], "Weitere")
        liste.append({"wert": f"{v['art']}:{v['id']}", "name": bedienung.kurzname(v), "gruppe": gruppe,
                      "titel": v.get("beschreibung") or v["name"]})
    return liste


def _merke_auswahl():
    GESPEICHERT["auswahl"] = _vorleser_wert()
    try:
        stimmen.speichere(GESPEICHERT)
    except OSError as e:
        print(f"cockpit-ui: Stimmenwahl nicht gespeichert: {e}", flush=True)


def _gespeicherte_auswahl_anwenden():
    """Setzt die zuletzt gewählte Stimme, sobald sie verfügbar ist (Dienste starten evtl. später)."""
    wunsch = GESPEICHERT.get("auswahl") or ""
    if not wunsch or wunsch == _vorleser_wert():
        return
    art, _, sid = wunsch.partition(":")
    try:
        _setze_vorleser(art, sid, merken=False)
    except bedienung.BedienFehler:
        pass
_aufgaben = set()  # hält Hintergrundaufgaben am Leben, bis sie fertig sind


def starte(coro):
    t = asyncio.create_task(coro)
    _aufgaben.add(t)
    t.add_done_callback(_aufgaben.discard)
    return t


class Sitzung:
    """Zustand des laufenden Gesprächs, unabhängig von einzelnen Browser-Verbindungen.

    Jedes Ereignis des Agenten bekommt eine fortlaufende Nummer (`seq`) und landet im Verlauf.
    Verbindungen abonnieren nur: Beim Verbinden gibt es den ganzen Verlauf, danach jedes neue
    Ereignis. So überlebt das Gespräch einen Reload, und die Reihenfolge ist überall dieselbe.
    """
    MAX = 5000

    def __init__(self):
        self.log = []
        self.seq = 0
        self.abos = []            # eine Warteschlange je Verbindung; die jüngste bekommt den Ton
        self.fokus = None         # {"uuid", "titel"} der Aufgabe im Fokus
        self.offen = {}           # id -> (Future, Anfrage): unbeantwortete Erlaubnisfragen
        self.sprech_gen = 0       # wird bei Stopp erhöht, ältere Sätze werden nicht mehr vorgelesen
        self.puffer = {}          # zug -> Satzpuffer
        self.vorlesen = asyncio.Queue()

    def rundruf(self, obj, roh=None, ausser=None):
        """Flüchtige Nachricht an alle Verbindungen (nicht im Verlauf)."""
        for q in self.abos:
            if q is not ausser:
                q.put_nowait((obj, roh))

    def schnappschuss(self, laeuft):
        return {"typ": "verlauf", "ereignisse": list(self.log), "seq": self.seq, "laeuft": laeuft,
                "fokus": self.fokus, "erlaubnisse": [a for _, a in self.offen.values()],
                "szene": SZ.schnappschuss() if SZ else None}

    def melde(self, ev):
        """Ereignis des Agenten: nummerieren, merken, verteilen, vorlesen."""
        self.seq += 1
        ev = ev | {"seq": self.seq}
        typ, zug = ev["typ"], ev.get("zug")
        letzter = self.log[-1] if self.log else None
        if typ in ("text", "denken") and letzter and letzter["typ"] == typ and letzter.get("zug") == zug:
            # Im Verlauf zusammenfassen (neues Objekt: das alte liegt evtl. noch in Warteschlangen)
            self.log[-1] = letzter | {"text": letzter["text"] + ev["text"], "seq": self.seq}
        else:
            # Szenen-Ereignisse tragen den ganzen Zustand samt Karten. Für den Verlauf beim Verbinden reicht der
            # aktuelle Zustand (schnappschuss), sonst wächst jeder Reload auf viele MB, die Server und Browser blockieren.
            self.log.append({k: v for k, v in ev.items() if k not in ("zustand", "karten")} if typ == "szene" else ev)
            if len(self.log) > self.MAX:
                del self.log[:len(self.log) - self.MAX]
        self.rundruf(ev)

        if typ == "text":
            for satz in self.puffer.setdefault(zug, Satzpuffer()).hinzu(ev["text"]):
                self.vorlesen.put_nowait((self.sprech_gen, satz))
        elif typ in ("werkzeug", "zug_ende") and zug in self.puffer:
            puffer = self.puffer[zug] if typ == "werkzeug" else self.puffer.pop(zug)
            for satz in puffer.ende():
                self.vorlesen.put_nowait((self.sprech_gen, satz))
        # Live-Aktualisierung: die Aufgabenquelle hat sich (vermutlich) geändert
        if typ == "zug_ende" or (typ == "werkzeug_ende" and _aendert(ev.get("name"))):
            self.rundruf({"typ": "aktualisieren", "grund": typ})
            if SZ is not None:
                try:
                    starte(SZ.auffrischen())
                except RuntimeError:  # kein laufender Event-Loop (Tests)
                    pass

    def sag(self, text):
        """Kurze Rückmeldung ohne Claude (Schnellbefehle) vorlesen."""
        if text:
            self.vorlesen.put_nowait((self.sprech_gen, text))

    def stille(self):
        """Verwirft alles, was noch vorgelesen werden sollte."""
        self.sprech_gen += 1
        self.puffer.clear()


def _aendert(werkzeug):
    w = (werkzeug or "").lower()
    return any(teil.lower() in w for m in MODULE for teil in m.aendert_bei)


SZ = None
S = Sitzung()


def _setze_fokus(f):
    if f != S.fokus:
        S.fokus = f
        S.rundruf({"typ": "fokus", "aufgabe": f})


SZ = Szene(AUFGABEN, S.melde, _setze_fokus, QUELLE or "der Aufgabenquelle")


# ---------- Sicherheit ----------

def _inline_hashes():
    """sha256 der Importmaps in den Seiten: Die CSP bleibt bei 'self' und erlaubt nur genau diese."""
    hashes = set()
    for seite in WEB.glob("*.html"):
        for m in re.finditer(r'<script type="importmap">(.*?)</script>', seite.read_text(), re.S):
            hashes.add("'sha256-%s'" % base64.b64encode(hashlib.sha256(m.group(1).encode()).digest()).decode())
    return " ".join(sorted(hashes))


SKRIPT_HASHES = _inline_hashes()


@app.middleware("http")
async def nur_lokal(request: Request, weiter):
    if request.headers.get("host") not in ERLAUBTE_HOSTS:
        return JSONResponse({"fehler": "Host nicht erlaubt"}, status_code=403)
    origin = request.headers.get("origin")
    if origin and origin.split("//", 1)[-1] not in ERLAUBTE_HOSTS:
        return JSONResponse({"fehler": "Origin nicht erlaubt"}, status_code=403)
    antwort = await weiter(request)
    if request.url.path.startswith("/static/") and "cache-control" not in antwort.headers:
        antwort.headers["Cache-Control"] = "no-cache"   # immer neu prüfen (ETag), sonst bleibt nach Änderungen altes JS hängen
    if "content-security-policy" in antwort.headers:   # Leser und Cockpit-Dateien bringen ihre eigene mit
        return antwort
    antwort.headers["Content-Security-Policy"] = (
        "default-src 'self'; script-src 'self' %s; connect-src 'self' ws://127.0.0.1:%d ws://localhost:%d; "
        "media-src 'self' blob:; img-src 'self' data: blob:" % (SKRIPT_HASHES, E.port, E.port))
    return antwort


# ---------- Start ----------

def _vokabular():
    """Namen aus Konfiguration, Modulen und Cockpit, damit Whisper Eigennamen richtig schreibt."""
    namen = set()
    for m in MODULE:
        try:
            namen.update(str(n) for n in m.namen() or [] if n)
        except Exception:
            pass
    for ordner in ("contacts/organizations", "contacts/people"):
        for f in (COCKPIT / ordner).glob("*.md"):
            m = re.search(r'^title:\s*"?([^"\n]+)', f.read_text(errors="ignore"), re.M)
            if m:
                namen.add(m.group(1).split("—")[0].strip())
    # Befehlswörter zuerst: Whisper verhört kurze Einwortsätze sonst leicht („Elidit“, „Focus“, „Totos“)
    feste = ["Erledigt.", "Fokus.", "Zeig mir die Todos.", "Inbox.", "Ausblenden.", "Überfällig.", "Projekte.", "Weg damit.",
             "Die zweite.", "Stopp.", "HarnoRb", "Cockpit", "Wochenreview", "Tagesreview"]
    feste += [m.titel for m in MODULE if m.titel] + K.namen + ([K.person] if K.person else [])
    return ", ".join(dict.fromkeys(feste + sorted(namen)))[:800]


async def _strom(stimme, text, sid, gen):
    """Schickt die Teile eines Satzes an den Browser, sobald der Stimmendienst sie liefert.
    Ein Fehler vor dem ersten Teil geht an den Aufrufer (Rückfall lokal), danach endet der Satz still."""
    loop = asyncio.get_running_loop()
    q, ende = asyncio.Queue(), object()

    def lauf():
        try:
            for teil in stimme.sprich_strom(text, sid):
                loop.call_soon_threadsafe(q.put_nowait, teil)
                if gen != S.sprech_gen:  # „Stopp“ oder neue Runde: Verbindung schließen
                    break
            loop.call_soon_threadsafe(q.put_nowait, ende)
        except Exception as e:
            loop.call_soon_threadsafe(q.put_nowait, e)

    loop.run_in_executor(None, lauf)
    n = 0
    while True:
        try:
            x = await asyncio.wait_for(q.get(), 0.5)
        except asyncio.TimeoutError:
            # „Stopp“ oder neue Runde: nicht auf den nächsten Teil eines stockenden Dienstes warten, sonst hängt
            # das Vorlesen insgesamt. Der Thread beendet sich beim nächsten Teil oder an seinem Zeitlimit.
            if gen != S.sprech_gen:
                return n
            continue
        if x is ende:
            return n
        if isinstance(x, Exception):
            if n == 0:
                raise x
            print(f"Vorlesen-Fehler im Strom: {x!r}"[:300], flush=True)
            return n
        if gen == S.sprech_gen and S.abos:
            S.abos[-1].put_nowait(({"typ": "audio"}, x))
            n += 1


async def sprecher():
    """Liest Satz für Satz vor. Eine Aufgabe für die ganze Sitzung; Fehler beenden sie nicht."""
    loop = asyncio.get_running_loop()
    while True:
        gen, satz = await S.vorlesen.get()
        try:
            if gen != S.sprech_gen or zustand["stimme"] is None or not S.abos:
                continue
            text = vorlesbar(satz)
            if not re.search(r"\w", text):
                continue
            stimme, sid = zustand["stimme"], None
            if zustand["vorleser"] == "elevenlabs" and zustand["elevenlabs"] is not None:
                stimme, sid = zustand["elevenlabs"], zustand["el_stimme"]
            elif zustand["vorleser"] == "http":
                dienst, _, sid = zustand["http_wahl"].partition(":")
                stimme = zustand["dienste"].get(dienst) or zustand["stimme"]
            try:
                if isinstance(stimme, stimmen.HttpStimme) and stimme.strom:
                    await _strom(stimme, text, sid, gen)
                    continue
                if stimme is zustand["stimme"]:
                    wav = await loop.run_in_executor(None, stimme.sprich, text)
                else:
                    wav = await loop.run_in_executor(None, stimme.sprich, text, sid)
            except Exception as e:
                if stimme is zustand["stimme"]:
                    raise
                # Cloud oder Stimmendienst nicht erreichbar, Guthaben leer: diesen Satz lokal vorlesen
                if isinstance(stimme, stimmen.HttpStimme):
                    kurz, dauerhaft = str(e), False
                else:
                    kurz, dauerhaft = elevenlabs_fehler(e)
                print(f"Vorlesen-Fehler: {e!r}"[:500], flush=True)
                if dauerhaft:
                    _setze_vorleser("piper", merken=False)  # nur einmal melden, Auswahl springt auf Piper
                    S.rundruf({"typ": "fehler", "text": f"{kurz} – lese ab jetzt lokal vor."})
                elif time.monotonic() - zustand.get("el_gemeldet", -1e9) > 60:
                    zustand["el_gemeldet"] = time.monotonic()
                    S.rundruf({"typ": "fehler", "text": f"{kurz} – lese lokal vor."})
                wav = await loop.run_in_executor(None, zustand["stimme"].sprich, text)
            if gen == S.sprech_gen and S.abos:
                S.abos[-1].put_nowait(({"typ": "audio"}, wav))
        except asyncio.CancelledError:
            raise
        except Exception as e:
            S.rundruf({"typ": "fehler", "text": f"Vorlesen: {e}"})


async def wache():
    """Merkt Änderungen, die nicht aus dieser Oberfläche kommen (Handy, andere Agenten).
    Jedes Modul mit stand() wird verglichen; ändert sich einer, frischt die Szene auf."""
    loop = asyncio.get_running_loop()
    letzte = {}
    while True:
        await asyncio.sleep(WACHE_TAKT)
        if any(not d.stimmen_liste for d in zustand["dienste"].values()):
            await dienste_aktualisieren(nur_fehlende=True)
        if not S.abos:
            continue
        for m in MODULE:
            try:
                jetzt = await loop.run_in_executor(None, m.stand)
            except Exception:
                continue
            if jetzt is None:
                continue
            if m.name in letzte and jetzt != letzte[m.name]:
                S.rundruf({"typ": "aktualisieren", "grund": m.name})
                await SZ.auffrischen()
            letzte[m.name] = jetzt


WACHE_TAKT = 30  # Sekunden


@app.on_event("startup")
async def start():
    loop = asyncio.get_running_loop()

    def laden():
        zustand["stimme"] = Stimme(E.stimmen / f"{E.stimme}.onnx")
        if os.environ.get("ELEVENLABS_API_KEY"):
            try:
                zustand["elevenlabs"] = ElevenLabsStimme(E.elevenlabs_stimme, E.elevenlabs_modell)
            except Exception:
                zustand["elevenlabs"] = None
        if zustand["elevenlabs"] is not None:
            try:
                zustand["el_stimmen"] = zustand["elevenlabs"].stimmen()
            except Exception:
                zustand["el_stimmen"] = []
            if not any(v["id"] == zustand["el_stimme"] for v in zustand["el_stimmen"]):
                zustand["el_stimmen"].insert(0, {"id": zustand["el_stimme"], "name": "Standardstimme", "geschlecht": "", "akzent": ""})
        if zustand["elevenlabs"] is None:
            zustand["vorleser"] = "piper"
        er = Erkenner(E.whisper_modell, E.geraet)
        er.vokabular = _vokabular()
        zustand["erkenner"] = er
    loop.run_in_executor(None, laden)
    for d in GESPEICHERT["dienste"]:
        zustand["dienste"][d["name"]] = stimmen.HttpStimme(d["name"], d["url"], d.get("token", ""))
    starte(dienste_aktualisieren())
    starte(sprecher())
    starte(wache())


async def rueckfrage(werkzeug, eingabe):
    """Fragt in allen offenen Fenstern um Erlaubnis. Offene Fragen überleben einen Reload."""
    rid = uuidlib.uuid4().hex
    fut = asyncio.get_running_loop().create_future()
    text = json.dumps(eingabe, ensure_ascii=False, indent=1)
    if len(text) > 20000:
        text = text[:20000] + f"\n… (gekürzt, insgesamt {len(text)} Zeichen)"
    anfrage = {"typ": "erlaubnis", "id": rid, "werkzeug": werkzeug, "eingabe": text}
    S.offen[rid] = (fut, anfrage)
    S.rundruf(anfrage)
    try:
        return await asyncio.wait_for(fut, timeout=180)
    except asyncio.TimeoutError:
        return False
    finally:
        S.offen.pop(rid, None)
        S.rundruf({"typ": "erlaubnis_erledigt", "id": rid})


async def szene_werkzeug(name, args):
    """Werkzeug des MCP-Servers „szene“: läuft im Zug des Agenten."""
    if name == "einstellung":
        try:
            return einstellung((args or {}).get("name"), (args or {}).get("wert"))
        except bedienung.BedienFehler as e:
            raise SzenenFehler(str(e)) from None
    if name in ("zeige_datei", "erstelle_dokument", "leser"):
        try:
            return leser_werkzeug(name, args or {})
        except dateien.DateiFehler as e:
            raise SzenenFehler(str(e)) from None
    if name == "theme":
        try:
            return theme_aktion(args or {})
        except themes.ThemeFehler as e:
            raise SzenenFehler(str(e)) from None
    if name == "stimmendienst":
        a = args or {}
        try:
            return await stimmendienst(a.get("aktion"), a.get("name", ""), a.get("url", ""), a.get("token", ""))
        except bedienung.BedienFehler as e:
            raise SzenenFehler(str(e)) from None
    return await SZ.aktion(name, args, zug=agent.zug)


async def dienste_aktualisieren(nur_fehlende=False):
    """Holt die Stimmen aller (bzw. der noch leeren) Dienste; das Netz im Thread, der Rest in der Schleife."""
    loop = asyncio.get_running_loop()
    vorher = [v["id"] for v in _http_stimmen()]
    for d in list(zustand["dienste"].values()):
        if not nur_fehlende or not d.stimmen_liste:
            await loop.run_in_executor(None, d.aktualisiere)
    _gespeicherte_auswahl_anwenden()
    if [v["id"] for v in _http_stimmen()] != vorher:
        S.rundruf({"typ": "stimmen"})


def _speichere_dienste():
    GESPEICHERT["dienste"] = [{"name": d.name, "url": d.url, **({"token": d.token} if d.token else {})}
                              for d in zustand["dienste"].values()]
    stimmen.speichere(GESPEICHERT)


async def stimmendienst(aktion, name="", url="", token=""):
    """Stimmendienste verwalten (Oberfläche, REST und Werkzeug). -> Antworttext."""
    aktion = str(aktion or "liste").strip().lower()
    if aktion in ("hinzufuegen", "hinzufügen", "aendern", "ändern"):
        try:
            name, url = stimmen.pruefe_dienst(name, url)
        except stimmen.DienstFehler as e:
            raise bedienung.BedienFehler(str(e)) from None
        d = stimmen.HttpStimme(name, url, str(token or ""))
        await asyncio.get_running_loop().run_in_executor(None, d.aktualisiere)
        zustand["dienste"][name] = d
        _speichere_dienste()
        S.rundruf({"typ": "stimmen"})
        if d.fehler:
            return f"Dienst {name} gespeichert, aber: {d.fehler}"
        return f"Dienst {name} angebunden, Stimmen: {', '.join(v['name'] for v in d.stimmen_liste) or 'keine'}."
    if aktion == "entfernen":
        name = str(name or "").strip().lower()
        if name not in zustand["dienste"]:
            raise bedienung.BedienFehler(f"Dienst {name!r} gibt es nicht.")
        if zustand["vorleser"] == "http" and zustand["http_wahl"].startswith(name + ":"):
            _setze_vorleser("piper")
        del zustand["dienste"][name]
        _speichere_dienste()
        S.rundruf({"typ": "stimmen"})
        return f"Dienst {name} entfernt."
    if aktion == "aktualisieren":
        await dienste_aktualisieren()
    elif aktion != "liste":
        raise bedienung.BedienFehler("aktion: liste | hinzufuegen | entfernen | aktualisieren")
    if not zustand["dienste"]:
        return "Keine Stimmendienste angebunden."
    zeilen = [f"{d.name} ({d.url}): " + (d.fehler or (", ".join(v["name"] for v in d.stimmen_liste) or "keine Stimmen"))
              for d in zustand["dienste"].values()]
    return "Stimmendienste: " + "; ".join(zeilen) + f". Stimme jetzt: {_stimmenname()}."


def _setze_vorleser(art, stimme_id="", merken=True):
    if art == "http":
        if stimme_id not in {v["id"] for v in _http_stimmen()}:
            raise bedienung.BedienFehler("Diese Stimme hat gerade kein Stimmendienst.")
        zustand["http_wahl"] = stimme_id
    elif art == "elevenlabs":
        if zustand["elevenlabs"] is None:
            raise bedienung.BedienFehler("ElevenLabs ist nicht eingerichtet (ELEVENLABS_API_KEY fehlt).")
        if stimme_id:
            if not any(v["id"] == stimme_id for v in zustand["el_stimmen"]):
                raise bedienung.BedienFehler("Unbekannte ElevenLabs-Stimme.")
            zustand["el_stimme"] = stimme_id
    elif art != "piper":
        raise bedienung.BedienFehler("Unbekannte Stimme.")
    zustand["vorleser"] = art
    wert = _vorleser_wert()
    if merken:
        _merke_auswahl()
    S.rundruf({"typ": "vorleser", "art": wert})
    return wert


def _stimmenname():
    if zustand["vorleser"] == "http":
        v = next((v for v in _http_stimmen() if v["id"] == zustand["http_wahl"]), None)
        return v["name"] if v else "Stimmendienst"
    if zustand["vorleser"] != "elevenlabs":
        return "lokal (Piper)"
    v = next((v for v in zustand["el_stimmen"] if v["id"] == zustand["el_stimme"]), None)
    return bedienung.kurzname(v) if v else "ElevenLabs"


def einstellung(name, wert=None):
    """Menüpunkt per Sprache oder Werkzeug. Ohne wert: aktuellen Stand und Möglichkeiten nennen."""
    name = bedienung.name_von(name)
    alle = _alle_stimmen()
    if name == "stimme":
        if wert in (None, "", "?", "liste"):
            namen = ", ".join(bedienung.kurzname(v) for v in alle)
            return f"Stimme jetzt: {_stimmenname()}. Möglich: lokal" + (f", {namen}." if namen else ".")
        art, v = bedienung.finde_stimme(wert, alle)
        _setze_vorleser(art, v["id"] if v else "")
        return f"Stimme {_stimmenname()}."
    if wert in (None, "", "?"):
        moeglich = "auto, hoch, mittel, niedrig" if name == "qualitaet" else "an, aus"
        return f"{name}: Stand kennt nur der Browser. Möglich: {moeglich}."
    w = bedienung.stufe(wert) if name == "qualitaet" else bedienung.schalter(wert)
    S.rundruf({"typ": "einstellung", "name": name, "wert": w})
    lesbar = {"toene": "Effekttöne", "qualitaet": "Qualität"}.get(name, name.capitalize())
    if name == "konfiguration":
        return f"Konfiguration {'offen' if w else 'zu'}."
    return f"{lesbar} {w if name == 'qualitaet' else ('an' if w else 'aus')}."


ANWEISUNG = sprechstil(K.person, QUELLE or None, [m.prompt() for m in MODULE])
agent = (AttrappenAgent if E.agent == "attrappe" else ClaudeAgent)(
    COCKPIT, rueckfrage, S.melde, szene_werkzeug, anweisung=ANWEISUNG,
    werkzeuge=szene_werkzeuge(AUFGABEN is not None), erlaubt=[w for m in MODULE for w in m.werkzeuge()])


# ---------- REST ----------

def _rw(methode, *a):
    if AUFGABEN is None:
        raise HTTPException(503, "Es ist kein Aufgabenmodul aktiv.")
    try:
        return getattr(AUFGABEN, methode)(*a)
    except ModulFehler as e:
        raise HTTPException(502, str(e))


def _modul_stand(m):
    try:
        ok, text = m.bereit()
    except Exception as e:
        ok, text = False, str(e)
    return {"name": m.name, "titel": m.titel or m.name, "ok": bool(ok), "text": str(text),
            "aufgaben": m is AUFGABEN_MODUL}


def _uuid(uuid):
    if not ID.fullmatch(uuid):
        raise HTTPException(400, "Ungültige Aufgaben-ID")
    return uuid


@app.get("/api/status")
def status():
    return {"bereit": zustand["erkenner"] is not None and zustand["stimme"] is not None,
            "modell": E.whisper_modell, "geraet": E.geraet, "stimme": E.stimme,
            "agent": E.agent, "aufgaben": QUELLE or None, "konfig": str(K.datei) if K.datei else None,
            "module": [_modul_stand(m) for m in MODULE], "modul_fehler": MODUL_FEHLER,
            "modul_web": [{"name": n, "url": f"/modul/{n}/modul.js"} for n in WEB_MODULE],
            "vorleser": _vorleser_wert(),
            "vorleser_moeglich": [v["wert"] for v in _stimmen_fuer_menue()],
            "stimmen": _stimmen_fuer_menue(),
            "dienste": [{"name": d.name, "url": d.url, "modell": d.modell, "fehler": d.fehler, "token": bool(d.token),
                         "stimmen": [v["name"] for v in d.stimmen_liste]} for d in zustand["dienste"].values()],
            "elevenlabs_stimmen": zustand["el_stimmen"] if zustand["elevenlabs"] is not None else []}


@app.post("/api/vorleser")
async def vorleser_setzen(request: Request):
    try:
        art = str((await request.json()).get("art", ""))
    except Exception:
        raise HTTPException(400, "Kein gültiges JSON")
    art, _, stimme_id = art.partition(":")
    if art not in ("piper", "elevenlabs", "http"):
        raise HTTPException(400, "Unbekannte Stimme")
    if art == "elevenlabs" and zustand["elevenlabs"] is None:
        raise HTTPException(409, "ElevenLabs ist nicht eingerichtet (ELEVENLABS_API_KEY fehlt)")
    try:
        return {"vorleser": _setze_vorleser(art, stimme_id)}
    except bedienung.BedienFehler as e:
        raise HTTPException(400, str(e)) from None


@app.post("/api/stimmendienst")
async def stimmendienst_rest(request: Request):
    """{"aktion": liste|hinzufuegen|entfernen|aktualisieren, "name", "url", "token"}"""
    try:
        a = await request.json()
    except Exception:
        raise HTTPException(400, "Kein gültiges JSON")
    try:
        return {"text": await stimmendienst(a.get("aktion"), a.get("name", ""), a.get("url", ""), a.get("token", ""))}
    except bedienung.BedienFehler as e:
        raise HTTPException(400, str(e)) from None


@app.post("/api/stimmprobe")
async def stimmprobe():
    """Liest einen kurzen Satz mit der gewählten Stimme vor."""
    S.sag(f"Hallo {K.person or 'du'}, so klinge ich als {_stimmenname()}.")
    return {"ok": True}


@app.get("/api/ueberblick")
async def ueberblick():
    loop = asyncio.get_running_loop()
    namen = ("summary", "naechste", "inbox", "warten", "projekte")
    teile = await asyncio.gather(*[loop.run_in_executor(None, _rw, f) for f in namen], return_exceptions=True)
    return {n: (None if isinstance(t, Exception) else t) for n, t in zip(namen, teile)} | {
        "fehler": list(dict.fromkeys(str(t.detail if hasattr(t, "detail") else t) for t in teile if isinstance(t, Exception)))}


@app.get("/api/aufgabe/{uuid}")
def aufgabe(uuid: str):
    return _rw("aufgabe", _uuid(uuid))


@app.post("/api/aufgabe/{uuid}/{aktion}")
async def aufgabe_aktion(uuid: str, aktion: str, request: Request):
    _uuid(uuid)
    aktionen = {"erledigt": "erledigt", "start": "starten", "stopp": "stoppen"}
    if aktion in aktionen:
        argumente = (aktionen[aktion], uuid)
    elif aktion == "notiz":
        try:
            text = str((await request.json()).get("text", "")).strip()
        except Exception:
            raise HTTPException(400, "Kein gültiges JSON")
        if not text:
            raise HTTPException(400, "Notiz ist leer")
        argumente = ("notiz", uuid, text)
    else:
        raise HTTPException(404, "Unbekannte Aktion")
    # Modulaufrufe blockieren; nicht im Event-Loop ausführen, sonst steht das Gespräch
    ergebnis = await asyncio.get_running_loop().run_in_executor(None, _rw, *argumente)
    S.rundruf({"typ": "aktualisieren", "grund": aktion})
    return ergebnis


# ---------- Gespräch ----------

JA = re.compile(r"^(ja|jawohl|ja bitte|ja klar|erlauben|erlaube|erlaubt|okay|ok|mach|mach das|einverstanden)\W*$", re.I)
NEIN = re.compile(r"^(nein|nee|ne|nein danke|ablehnen|lehne ab|abgelehnt|lieber nicht|nicht)\W*$", re.I)


def erlaubnis_per_stimme(text):
    """Offene Erlaubnisfrage mit „ja“ oder „nein“ beantworten (die älteste zuerst)."""
    if not S.offen:
        return False
    t = text.strip()
    ja = bool(JA.match(t))
    if not ja and not NEIN.match(t):
        return False
    rid, (fut, _) = next(iter(S.offen.items()))
    if not fut.done():
        fut.set_result(ja)
    S.melde({"typ": "schnellbefehl", "text": text, "aktion": "erlaubnis_" + ("ja" if ja else "nein"), "quelle": "sprache"})
    return True


async def schnell(text, quelle):
    """Schnellbefehl ohne Claude. True, wenn erkannt und ausgeführt."""
    if erlaubnis_per_stimme(text):
        return True
    if not E.schnellbefehle or agent.laeuft:
        return False
    if LESER["pfad"] is not None:
        t = schnellbefehl.normalisiere(text)
        aktion = {"runter": "runter", "weiter": "runter", "weiter runter": "runter", "nach unten": "runter", "scroll runter": "runter",
                  "hoch": "hoch", "zurueck nach oben": "oben", "zurück nach oben": "oben", "nach oben": "hoch", "ganz oben": "oben", "ganz unten": "unten",
                  "schliessen": "schliessen", "leser schliessen": "schliessen", "leser zu": "schliessen",
                  "zu": "schliessen", "weg damit": "schliessen", "dokument schliessen": "schliessen"}.get(t)
        if aktion:
            S.melde({"typ": "schnellbefehl", "text": text, "aktion": "leser " + aktion, "quelle": quelle})
            leser_werkzeug("leser", {"aktion": aktion})
            return True
    namen = [bedienung.kurzname(v).lower() for v in _alle_stimmen()]
    treffer = schnellbefehl.erkenne(text, SZ.zustand, namen)
    if not treffer:
        return False
    aktion, args, antwort = treffer
    if aktion in AUFGABEN_WERKZEUGE and AUFGABEN is None:
        return False  # ohne Aufgabenmodul versteht der Agent den Satz besser
    S.stille()
    S.melde({"typ": "schnellbefehl", "text": text, "aktion": aktion, "quelle": quelle})
    if aktion == "stopp":
        S.rundruf({"typ": "gestoppt"})
        return True
    if aktion == "neu":
        await neues_gespraech()
        S.sag("Neues Gespräch.")
        return True
    if aktion == "einstellung":
        try:
            S.sag(einstellung(args["name"], args.get("wert")))
        except bedienung.BedienFehler as e:
            S.melde({"typ": "fehler", "text": str(e)})
            S.sag("Das ging nicht.")
        return True
    if aktion == "befehle":
        aktion, args = "zeige_text", {"titel": "Was du sagen kannst", "inhalt": bedienung.BEFEHLE}
        antwort = "Hier sind die Sprachbefehle."
    elif aktion == "stimmen":
        aktion, args = "zeige_text", {"titel": "Stimmen", "inhalt": bedienung.stimmen_text(_alle_stimmen())
                                      + f"\n\nJetzt: {_stimmenname()}"}
        antwort = "Das sind die Stimmen."
    try:
        ergebnis = await SZ.aktion(aktion, args)
    except SzenenFehler as e:
        S.melde({"typ": "fehler", "text": str(e)})
        S.sag("Das ging nicht.")
        return True
    if antwort is None and aktion == "zeige_liste":
        antwort = SZ.zustand["titel"] + "."
    if aktion == "zeige_liste":
        n = SZ.zustand["gesamt"]
        antwort = f"{antwort} {'Nichts drin' if not n else ('Ein Eintrag' if n == 1 else f'{n} Einträge')}."
    elif aktion == "waehle":
        antwort = ergebnis.replace("Hervorgehoben: ", "").split(" [")[0].split(". ", 1)[-1]
    elif aktion == "fokus":
        antwort = "Im Fokus."
    elif aktion == "erledigt":
        antwort = "Erledigt."
    S.sag(antwort)
    return True


async def frage(text, quelle):
    """Nachricht des Nutzers an den Agenten. Geht auch, während ein Zug läuft."""
    S.stille()  # was noch vorgelesen würde, ist überholt
    if await schnell(text, quelle):
        return
    kontext = SZ.kontext()
    if S.fokus and not (SZ.zustand.get("fokus") or {}).get("uuid") == S.fokus["uuid"]:
        kontext += (f" {K.person or 'Der Nutzer'} hat die Aufgabe {S.fokus['uuid']} „{S.fokus['titel']}“"
                    f"{' aus ' + QUELLE if QUELLE else ''} im Fokus.")
    if LESER["pfad"] is not None:
        kontext += f" Im Leser offen: {LESER['pfad'] or 'Dateibaum'} (Cockpit-Pfad)."
    if HOCHGELADEN:
        kontext += " Zuletzt hochgeladen (neueste zuerst): " + "; ".join(
            f"{h['pfad']} ({h['name']}, {h['groesse'] // 1024 or 1} KB, {h['zeit']})" for h in HOCHGELADEN) + "."
    prompt = f"[Szene: {kontext}]\n\n{text}"
    await agent.sende(prompt, anzeige=text, quelle=quelle)


async def aufnahme(daten, q):
    """Sprachaufnahme erkennen und, wenn etwas gesagt wurde, als Nachricht schicken."""
    text, beginn = "", time.perf_counter()
    if zustand["erkenner"] is None:
        q.put_nowait(({"typ": "fehler", "text": "Spracherkennung lädt noch."}, None))
    else:
        try:
            text = await asyncio.get_running_loop().run_in_executor(None, zustand["erkenner"].erkenne, daten)
        except Exception as e:
            q.put_nowait(({"typ": "fehler", "text": f"Erkennung fehlgeschlagen: {e}"[:300]}, None))
    if not brauchbar(text):  # leer oder nur Satzzeichen (Stille): nicht an den Agenten
        text = ""
    q.put_nowait(({"typ": "erkannt", "text": text, "sekunden": round(time.perf_counter() - beginn, 1)}, None))
    if text:
        await frage(text, "sprache")


async def neues_gespraech():
    S.stille()
    await agent.neu()
    S.log.clear()
    SZ.zustand = SZ.leer()
    S.fokus = None
    for fut, _ in list(S.offen.values()):
        if not fut.done():
            fut.set_result(False)
    S.rundruf({"typ": "neu"})


async def sicher(coro, q):
    """Führt eine Hintergrundaufgabe aus und meldet Fehler an die Verbindung, statt sie zu verschlucken."""
    try:
        await coro
    except asyncio.CancelledError:
        raise
    except Exception as e:
        q.put_nowait(({"typ": "fehler", "text": f"{type(e).__name__}: {e}"[:300]}, None))


async def szene_befehl(aktion, args, q):
    try:
        if aktion == "stil":
            await SZ.setze_stil(args.get("stil"), args.get("hintergrund"))
        else:
            await SZ.aktion(aktion, args if isinstance(args, dict) else {})
    except SzenenFehler as e:
        q.put_nowait(({"typ": "fehler", "text": str(e)[:300]}, None))
    except Exception as e:
        q.put_nowait(({"typ": "fehler", "text": f"Szene: {e}"[:300]}, None))


@app.websocket("/ws")
async def gespraech(ws: WebSocket):
    if ws.headers.get("host") not in ERLAUBTE_HOSTS or \
            (ws.headers.get("origin") or "").split("//", 1)[-1] not in ERLAUBTE_HOSTS:
        await ws.close(code=1008)
        return
    await ws.accept()
    q = asyncio.Queue()
    # Verlauf und Abo ohne await dazwischen: kein Ereignis fehlt, keines kommt doppelt
    q.put_nowait((S.schnappschuss(agent.zug), None))
    S.abos.append(q)

    async def schreiber():
        while True:
            obj, roh = await q.get()
            await ws.send_json(obj)
            if roh is not None:
                await ws.send_bytes(roh)

    schreib_task = asyncio.create_task(schreiber())
    try:
        while True:
            nachricht = await ws.receive()
            if nachricht.get("type") == "websocket.disconnect":
                break
            try:
                if nachricht.get("bytes") is not None:  # Sprachaufnahme
                    starte(sicher(aufnahme(nachricht["bytes"], q), q))
                    continue
                daten = json.loads(nachricht.get("text") or "{}")
                typ = daten.get("typ")
                if typ == "frage":
                    text = str(daten.get("text") or "").strip()
                    if text:
                        q.put_nowait(({"typ": "gestoppt"}, None))
                        starte(sicher(frage(text, "text"), q))
                elif typ == "fokus":
                    a = daten.get("aufgabe")
                    S.fokus = ({"uuid": str(a["uuid"])[:64], "titel": str(a.get("titel") or "")[:300]}
                               if isinstance(a, dict) and a.get("uuid") else None)
                    S.rundruf({"typ": "fokus", "aufgabe": S.fokus}, ausser=q)
                elif typ == "stopp":
                    S.stille()
                    q.put_nowait(({"typ": "gestoppt"}, None))
                    if agent.laeuft:
                        starte(sicher(agent.unterbrechen(), q))
                elif typ == "neu":
                    starte(sicher(neues_gespraech(), q))
                elif typ == "szene_befehl":  # Tasten und Klicks in der Szene, ohne Claude
                    starte(szene_befehl(str(daten.get("aktion") or ""), daten.get("args") or {}, q))
                elif typ == "erlaubnis_antwort":
                    fut = S.offen.get(daten.get("id"), (None, None))[0]
                    if fut and not fut.done():
                        fut.set_result(daten.get("ja") is True)
            except Exception as e:  # eine kaputte Nachricht beendet die Verbindung nicht
                q.put_nowait(({"typ": "fehler", "text": f"Nachricht nicht verarbeitet: {e}"[:300]}, None))
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        schreib_task.cancel()
        if q in S.abos:
            S.abos.remove(q)


# ---------- Themes ----------

def _theme_melden(t):
    S.rundruf({"typ": "theme", "theme": t})
    art = (t.get("hintergrund") or {}).get("art")
    if t.get("stil") or art:   # Theme bringt Stil oder Hintergrund mit: wie ein Wechsel per Werkzeug stil
        starte(SZ.setze_stil(t.get("stil"), art))


def theme_aktion(a):
    """Werkzeug theme und REST: liste | zeige | waehle | speichere | loesche. -> Antworttext"""
    aktion = str(a.get("aktion") or "liste").strip().lower()
    if aktion == "liste":
        return f"Aktiv: {themes.aktiv()['name']}. Themes: " + ", ".join(
            t["name"] + ("" if t["eingebaut"] else " (eigen)") for t in themes.liste()) + "."
    if aktion == "zeige":
        t = themes.finde(a["name"]) if a.get("name") else themes.aktiv()
        return json.dumps(t, ensure_ascii=False)
    if aktion == "waehle":
        t = themes.setze_aktiv(a.get("name") or a.get("id") or "")
        _theme_melden(t)
        return f"Theme {t['name']} aktiv."
    if aktion == "speichere":
        roh = a.get("theme")
        if isinstance(roh, str):
            try:
                roh = json.loads(roh)
            except ValueError:
                raise themes.ThemeFehler("theme ist kein gültiges JSON.") from None
        t = themes.speichere(roh)
        if a.get("aktivieren", True) is not False:
            themes.setze_aktiv(t["id"])
            _theme_melden(t)
        return f"Theme {t['name']} gespeichert ({t['id']})" + (" und aktiv." if a.get("aktivieren", True) is not False else ".")
    if aktion == "loesche":
        t = themes.loesche(a.get("name") or "")
        _theme_melden(themes.aktiv())
        return f"Theme {t['name']} gelöscht."
    raise themes.ThemeFehler("aktion: liste | zeige | waehle | speichere | loesche")


BILD = re.compile(r"data:image/(jpeg|png|webp);base64,([A-Za-z0-9+/=]+)")
THEME_AUFTRAG = """\
{wer} hat ein Bild in die Oberfläche gezogen und möchte daraus ein Theme für HarnoRb. Ein schnelles Theme aus den \
Hauptfarben ist schon aktiv (id {id}). Schau dir das Bild an und verbessere es: Erfasse Stimmung und Farbwelt, gib dem \
Theme einen kurzen, treffenden Namen und eine Beschreibung in einem Satz, und speichere es mit theme (aktion speichere, \
gleiche id {id}). Regeln: dunkles Theme (grund und tief sehr dunkel, text sehr hell, gut lesbar), akzent und verlauf aus den \
prägenden Farben des Bildes, kugel.toenung im Hauptton (toenung_staerke 0.3 bis 0.7), galaxie vier Farben von innen \
(hell) nach außen, hintergrund.nebel drei dunkle Töne, passt ein comic-artiges Bild, stil comic. Sag danach in einem Satz, \
was du gemacht hast.
Hauptfarben (häufigste zuerst): {palette}
Aktuelles Theme: {theme}"""


@app.get("/api/theme")
def theme_aktiv():
    return themes.aktiv()


@app.get("/api/themes")
def theme_liste():
    return {"aktiv": themes.aktiv_id(), "themes": themes.liste()}


@app.post("/api/theme")
async def theme_rest(request: Request):
    try:
        a = await request.json()
    except Exception:
        raise HTTPException(400, "Kein gültiges JSON")
    try:
        return {"text": theme_aktion(a if isinstance(a, dict) else {}), "theme": themes.aktiv()}
    except themes.ThemeFehler as e:
        raise HTTPException(400, str(e)) from None


@app.post("/api/theme/bild")
async def theme_aus_bild(request: Request):
    """Bild (als data-URL, im Browser verkleinert) und seine Hauptfarben: sofort ein Theme aus der Palette,
    dann darf Claude es mit Blick auf das Bild verbessern (verfeinern=false lässt das weg)."""
    try:
        a = await request.json()
    except Exception:
        raise HTTPException(400, "Kein gültiges JSON")
    palette = [f for f in (a.get("palette") or [])[:16] if isinstance(f, str)]
    try:
        t = themes.speichere(themes.aus_palette(palette, str(a.get("name") or "")[:60]))
        themes.setze_aktiv(t["id"])
    except themes.ThemeFehler as e:
        raise HTTPException(400, str(e)) from None
    _theme_melden(t)
    m = BILD.fullmatch(str(a.get("bild") or ""))
    if a.get("verfeinern", True) and m and len(m.group(2)) < 2_000_000:
        auftrag = THEME_AUFTRAG.format(wer=K.person or "Der Nutzer", id=t["id"], palette=", ".join(palette),
                                       theme=json.dumps(t, ensure_ascii=False))
        bild = {"type": "image", "source": {"type": "base64", "media_type": f"image/{m.group(1)}", "data": m.group(2)}}
        starte(agent.sende(f"[Szene: {SZ.kontext()}]\n\n{auftrag}", anzeige="Theme aus einem Bild", quelle="theme", bilder=[bild]))
    return {"theme": t, "verfeinern": bool(m)}


# ---------- Leser: Cockpit-Dateien und von HarnoRb erzeugte Dokumente ----------

LESER = {"pfad": None}   # was gerade im Leser offen ist (übersteht ein Neuladen)


def zeige_im_leser(pfad):
    LESER["pfad"] = pfad
    S.rundruf({"typ": "leser", "aktion": "oeffnen", "pfad": pfad})


def leser_werkzeug(name, a):
    if name == "zeige_datei":
        d = dateien.lies(COCKPIT, a.get("pfad", ""))
        zeige_im_leser(d["pfad"])
        return f"Im Leser: {d['pfad'] or 'Cockpit'} ({d['art']})."
    if name == "erstelle_dokument":
        pfad = dateien.erstelle(COCKPIT, a.get("titel", ""), a.get("inhalt", ""), a.get("format", "markdown"),
                                a.get("beschreibung", ""))
        zeige_im_leser(pfad)
        S.melde({"typ": "dokument", "pfad": pfad})
        return f"Abgelegt unter {pfad} und im Leser geöffnet."
    aktion = str(a.get("aktion", "")).lower()
    if aktion not in ("runter", "hoch", "oben", "unten", "schliessen", "browser"):
        raise dateien.DateiFehler("aktion: runter | hoch | oben | unten | schliessen | browser")
    if aktion == "schliessen":
        LESER["pfad"] = None
    S.rundruf({"typ": "leser", "aktion": aktion})
    return "Leser: " + aktion + "."


LESER_CSP = ("default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; "
             "font-src 'self' data:; frame-src 'self'; object-src 'self'; connect-src 'self'")
# Von Claude gebaute HTML-Seiten: abgeschottet (eigener Ursprung, kein Netz, keine Cookies), Skripte erlaubt.
SEITEN_CSP = ("sandbox allow-scripts allow-popups; default-src 'self' 'unsafe-inline' data: blob:; "
              "script-src 'self' 'unsafe-inline'; connect-src 'none'; form-action 'none'")


HOCHGELADEN = []   # zuletzt hochgeladene Dateien dieser Sitzung, neueste zuerst (höchstens 5)


@app.post("/api/upload")
async def hochladen(dateien_: list[UploadFile] = File(alias="datei")):
    """Dateien aus der Szene (ziehen oder einfügen) im Eingang des Cockpits ablegen. Was damit geschieht,
    sagt der Nutzer danach; der Szenen-Kontext nennt die letzten Uploads."""
    abgelegt, fehler = [], []
    for f in dateien_[:20]:
        try:
            daten = await f.read(dateien.MAX_UPLOAD + 1)
            a = dateien.ablegen(COCKPIT, f.filename or "datei", daten, ordner=K.eingang)
        except dateien.DateiFehler as e:
            fehler.append(str(e))
            continue
        a["zeit"] = time.strftime("%H:%M")
        abgelegt.append(a)
        HOCHGELADEN.insert(0, a)
    del HOCHGELADEN[5:]
    if not abgelegt and fehler:
        raise HTTPException(400, "; ".join(fehler))
    return {"abgelegt": abgelegt, "fehler": fehler}


@app.get("/leser")
def leser_seite():
    return FileResponse(WEB / "leser.html", headers={"Content-Security-Policy": LESER_CSP})


@app.get("/api/datei")
def datei(pfad: str = ""):
    try:
        return dateien.lies(COCKPIT, pfad)
    except dateien.DateiFehler as e:
        raise HTTPException(404, str(e)) from None


@app.get("/api/dateisuche")
def dateisuche(q: str = ""):
    return {"treffer": dateien.suche(COCKPIT, q)}


@app.get("/api/leser")
def leser_stand():
    return {"pfad": LESER["pfad"]}


@app.post("/api/leser")
async def leser_setzen(request: Request):
    try:
        pfad = (await request.json()).get("pfad")
    except Exception:
        raise HTTPException(400, "Kein gültiges JSON")
    LESER["pfad"] = pfad or None
    return {"pfad": LESER["pfad"]}


@app.get("/roh/{pfad:path}")
def roh(pfad: str):
    try:
        p, mime = dateien.roh(COCKPIT, pfad)
    except dateien.DateiFehler as e:
        raise HTTPException(404, str(e)) from None
    csp = SEITEN_CSP if mime.startswith("text/html") else "default-src 'none'; img-src 'self'; style-src 'unsafe-inline'; object-src 'self'"
    return FileResponse(p, media_type=mime, headers={"Content-Security-Policy": csp, "X-Content-Type-Options": "nosniff",
                                                      "Cache-Control": "no-store"})


WEB_MODULE = {m.name: m.web for m in MODULE if m.web}
WEB_ENDUNGEN = {".js": "text/javascript", ".mjs": "text/javascript", ".css": "text/css", ".json": "application/json",
                ".png": "image/png", ".jpg": "image/jpeg", ".svg": "image/svg+xml", ".webp": "image/webp",
                ".wav": "audio/wav", ".mp3": "audio/mpeg", ".ogg": "audio/ogg", ".glsl": "text/plain"}


@app.get("/modul/{name}/{pfad:path}")
def modul_web(name: str, pfad: str):
    """Browser-Dateien eines Moduls (modul.js und was es nachlädt), nur aus seinem web-Ordner."""
    basis = WEB_MODULE.get(name)
    if basis is None:
        raise HTTPException(404, "Modul ohne Browser-Teil")
    p = (basis / pfad).resolve()
    if not p.is_relative_to(basis) or not p.is_file() or p.suffix.lower() not in WEB_ENDUNGEN:
        raise HTTPException(404, "Datei nicht gefunden")
    return FileResponse(p, media_type=WEB_ENDUNGEN[p.suffix.lower()], headers={"Cache-Control": "no-store"})


app.mount("/static", StaticFiles(directory=WEB), name="static")


@app.get("/")
def index():
    return FileResponse(WEB / "szene.html")


@app.get("/klassisch")
def klassisch():
    return FileResponse(WEB / "index.html")


@app.get("/vorschau")
def vorschau():
    return FileResponse(WEB / "szene-vorschau.html")

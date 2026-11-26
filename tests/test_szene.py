"""Tests für Ereignis `szene`, Schnappschuss, Schnellbefehle und Attrappe.

    uv run --with pytest --with httpx pytest -q

Läuft gegen das Modul beispiel (erfundene Aufgaben im Speicher), nie gegen echte Aufgaben.
"""
import asyncio
import importlib
import os
import sys
import time
from pathlib import Path

import pytest

WURZEL = Path(__file__).resolve().parents[1]
KONFIG = Path(os.environ.get("TMPDIR", "/tmp")) / f"cockpit-ui-test-{os.getpid()}.toml"
KONFIG.write_text("[module.beispiel]\n")
os.environ.update({"COCKPIT_UI_AGENT": "attrappe", "COCKPIT_UI_PORT": "8499", "COCKPIT_UI_VORLESER": "piper",
                   "COCKPIT_DIR": str(WURZEL / "tests"),
                   "COCKPIT_UI_KONFIG": str(KONFIG)})  # nie die echte Konfiguration

from cockpit_ui import schnellbefehl  # noqa: E402
from cockpit_ui.module.beispiel import Speicher  # noqa: E402
from cockpit_ui.szene import Szene, SzenenFehler, normiere_art, nummer_aus  # noqa: E402


SPEICHER = Speicher()


@pytest.fixture(autouse=True)
def frisch():
    SPEICHER.reset()
    yield


def neue_szene():
    ereignisse, fokus = [], []
    sz = Szene(SPEICHER, ereignisse.append, fokus.append, "den Beispielaufgaben")
    return sz, ereignisse, fokus


def lauf(coro):
    return asyncio.run(coro)


# ---------- Szene ----------

def test_liste_heute_meldet_szene_ereignis():
    sz, ev, _ = neue_szene()
    text = lauf(sz.liste("heute"))
    assert ev[-1]["typ"] == "szene" and ev[-1]["aktion"] == "liste"
    assert ev[-1]["zustand"]["ansicht"] == "liste"
    karten = ev[-1]["karten"]
    assert karten and karten[0]["nr"] == 1
    # läuft zuerst, dann nach Fälligkeit; nur Fälliges oder Laufendes
    assert karten[0]["laeuft"]
    assert all(k["laeuft"] or k["heute"] or k["ueberfaellig"] for k in karten)
    assert "1. " in text and "[" in text  # nummeriert, mit UUID für Claude


def test_listenarten():
    sz, ev, _ = neue_szene()
    for art in ("inbox", "warten", "projekte", "ueberfaellig", "naechste", "überfällig", "todos"):
        lauf(sz.liste(art))
        assert ev[-1]["aktion"] == "liste"
    assert normiere_art("Überfällig") == "ueberfaellig"
    assert normiere_art("projekt:Anonymisierungstest") == "projekt:Anonymisierungstest"
    lauf(sz.liste("inbox"))
    assert sz.zustand["gesamt"] == 3 and all(k["art"] == "aufgabe" for k in sz.zustand["karten"])
    lauf(sz.liste("projekte"))
    assert all(k["art"] == "projekt" for k in sz.zustand["karten"])
    lauf(sz.liste("ueberfaellig"))
    assert all(k["ueberfaellig"] for k in sz.zustand["karten"]) and sz.zustand["gesamt"] == 3


def test_projekt_unscharf_und_suche():
    sz, ev, _ = neue_szene()
    lauf(sz.liste("projekt:Anonymisierungs Test"))
    assert sz.zustand["titel"] == "Projekt anonymisierungstest" and sz.zustand["gesamt"] == 3
    lauf(sz.liste("suche:fahrrad"))
    assert sz.zustand["gesamt"] == 1
    with pytest.raises(SzenenFehler):
        lauf(sz.liste("projekt:gibtsnicht-xyz-qqq"))
    with pytest.raises(SzenenFehler):
        lauf(sz.liste("quatsch"))


def test_waehle_fokus_erledigt_ausblenden():
    sz, ev, fokus = neue_szene()
    lauf(sz.liste("heute"))
    n = len(sz.zustand["karten"])
    lauf(sz.waehle("die zweite"))
    assert sz.zustand["gewaehlt"] == 2 and ev[-1]["aktion"] == "waehle"
    zweite = sz.zustand["karten"][1]
    lauf(sz.fokus())  # ohne Angabe: die hervorgehobene
    assert sz.zustand["ansicht"] == "fokus" and sz.zustand["fokus"]["uuid"] == zweite["uuid"]
    assert fokus[-1] == {"uuid": zweite["uuid"], "titel": zweite["titel"]}
    assert "notizen" in sz.zustand["fokus"]
    lauf(sz.erledigt())
    assert ev[-1]["aktion"] == "erledigt" and ev[-1]["karte"]["uuid"] == zweite["uuid"]
    assert SPEICHER.speicher[zweite["uuid"]]["status"] == "completed"
    assert fokus[-1] is None
    z = ev[-1]["zustand"]
    assert z["ansicht"] == "liste" and len(z["karten"]) == n - 1
    assert [k["nr"] for k in z["karten"]] == list(range(1, n))
    lauf(sz.ausblenden())
    assert sz.zustand["ansicht"] == "leer" and ev[-1]["aktion"] == "ausblenden"


def test_text_optionen_stil_und_fehler():
    sz, ev, _ = neue_szene()
    lauf(sz.text("Entwurf", "Hallo **Welt**"))
    assert sz.zustand["ansicht"] == "text" and ev[-1]["inhalt"] == "Hallo **Welt**"
    lauf(sz.optionen("Welche Liste?", ["Heute", "Inbox"]))
    assert sz.zustand["optionen"]["optionen"] == ["Heute", "Inbox"]
    lauf(sz.setze_stil("comic", "kugelraumer"))
    assert ev[-1]["zustand"]["stil"] == "comic" and ev[-1]["zustand"]["hintergrund"] == "raumer"
    with pytest.raises(SzenenFehler):
        lauf(sz.setze_stil("barock"))
    with pytest.raises(SzenenFehler):
        lauf(sz.waehle(3))  # keine Liste sichtbar


def test_zug_wird_mitgegeben():
    sz, ev, _ = neue_szene()
    lauf(sz.aktion("zeige_liste", {"art": "inbox"}, zug=7))
    assert ev[-1]["zug"] == 7
    lauf(sz.aktion("ausblenden", {}))
    assert "zug" not in ev[-1]


def test_nummer_aus():
    assert nummer_aus("die zweite") == 2 and nummer_aus(3) == 3 and nummer_aus("letzte") == -1
    assert nummer_aus("Nummer 4") == 4 and nummer_aus("") is None


def test_kontext():
    sz, _, _ = neue_szene()
    assert "leer" in sz.kontext()
    lauf(sz.liste("inbox"))
    assert "1. " in sz.kontext() and "Inbox" in sz.kontext()


# ---------- Schnellbefehle ----------

@pytest.mark.parametrize("satz,aktion,art", [
    ("Zeig mir die Todos.", "zeige_liste", "heute"),
    ("Was ist überfällig?", "zeige_liste", "ueberfaellig"),
    ("Zeig mir die Inbox", "zeige_liste", "inbox"),
    ("Weg damit!", "ausblenden", None),
    ("Stopp.", "stopp", None),
    ("Zeig das Projekt Anonymisierungstest", "zeige_liste", "projekt:anonymisierungstest"),
])
def test_schnellbefehle(satz, aktion, art):
    t = schnellbefehl.erkenne(satz, {"ansicht": "leer"})
    assert t and t[0] == aktion
    if art:
        assert t[1]["art"] == art


def test_schnellbefehle_mit_kontext():
    liste = {"ansicht": "liste", "karten": [{"nr": 1}, {"nr": 2}], "gewaehlt": None}
    assert schnellbefehl.erkenne("Die zweite", liste)[:2] == ("waehle", {"nummer": "zweite"})
    assert schnellbefehl.erkenne("Daran arbeite ich jetzt", liste) is None  # nichts gewählt
    assert schnellbefehl.erkenne("Daran arbeite ich jetzt", liste | {"gewaehlt": 2})[0] == "fokus"
    fokus = {"ansicht": "fokus", "fokus": {"uuid": "x", "nr": 1}}
    assert schnellbefehl.erkenne("Erledigt", fokus)[0] == "erledigt"
    assert schnellbefehl.erkenne("Erledigt", {"ansicht": "leer"}) is None
    # Längeres und Unklares geht an Claude
    assert schnellbefehl.erkenne("Was mache ich mit dem ersten?", liste) is None
    assert schnellbefehl.erkenne("Kannst du mir bitte erklären, warum die Inbox so voll ist und was ich tun soll", {}) is None


# ---------- Server: Protokoll, Schnappschuss, WebSocket ----------

@pytest.fixture()
def server():
    from cockpit_ui import server as srv
    srv = importlib.reload(srv)
    srv.app.router.on_startup.clear()  # keine Sprachmodelle laden
    from fastapi.testclient import TestClient
    with TestClient(srv.app, base_url="http://127.0.0.1:8499") as c:
        yield srv, c


def ws(c):
    return c.websocket_connect("/ws", headers={"origin": "http://127.0.0.1:8499", "host": "127.0.0.1:8499"})


def bis(w, bedingung, max_n=400):
    for _ in range(max_n):
        m = w.receive_json()
        if bedingung(m):
            return m
    raise AssertionError("Ereignis kam nicht")


def test_schnappschuss_enthaelt_szene(server):
    srv, c = server
    with ws(c) as w:
        m = w.receive_json()
        assert m["typ"] == "verlauf" and m["szene"]["ansicht"] == "leer"
        assert m["szene"]["stil"] in ("leuchtend", "comic")
        w.send_json({"typ": "szene_befehl", "aktion": "zeige_liste", "args": {"art": "inbox"}})
        ev = bis(w, lambda m: m.get("typ") == "szene")
        assert ev["aktion"] == "liste" and ev["seq"] > 0
    with ws(c) as w:  # nach dem Neuladen ist die Szene wieder da
        m = w.receive_json()
        assert m["szene"]["ansicht"] == "liste" and m["szene"]["liste"] == "inbox"
        assert any(e["typ"] == "szene" for e in m["ereignisse"])


def test_attrappe_steuert_szene_ueber_werkzeug(server):
    srv, c = server
    with ws(c) as w:
        w.receive_json()
        w.send_json({"typ": "frage", "text": "Kannst du mir bitte zeigen, was heute so alles ansteht bei mir?"})
        werkzeug = bis(w, lambda m: m.get("typ") == "werkzeug")
        assert werkzeug["name"] == "mcp__szene__zeige_liste"
        sz = bis(w, lambda m: m.get("typ") == "szene")
        assert sz["zug"] == werkzeug["zug"] and sz["aktion"] == "liste"
        bis(w, lambda m: m.get("typ") == "zug_ende")
    with ws(c) as w:
        m = w.receive_json()
        assert m["szene"]["liste"] == "heute"
        typen = [e["typ"] for e in m["ereignisse"]]
        assert typen.index("zug_start") < typen.index("szene") < typen.index("zug_ende")


def test_schnellbefehl_ohne_agent(server):
    srv, c = server
    with ws(c) as w:
        w.receive_json()
        w.send_json({"typ": "frage", "text": "Zeig mir die Inbox"})
        m = bis(w, lambda m: m.get("typ") in ("schnellbefehl", "zug_start"))
        assert m["typ"] == "schnellbefehl"
        sz = bis(w, lambda m: m.get("typ") == "szene")
        assert sz["aktion"] == "liste" and sz["art"] == "inbox" and "zug" not in sz
        w.send_json({"typ": "frage", "text": "Weg damit"})
        sz = bis(w, lambda m: m.get("typ") == "szene")
        assert sz["aktion"] == "ausblenden"


def test_erlaubnis_ueber_attrappe(server):
    srv, c = server
    with ws(c) as w:
        w.receive_json()
        w.send_json({"typ": "frage", "text": "Bitte frag mich um Erlaubnis für einen Befehl"})
        e = bis(w, lambda m: m.get("typ") == "erlaubnis")
        w.send_json({"typ": "erlaubnis_antwort", "id": e["id"], "ja": True})
        bis(w, lambda m: m.get("typ") == "erlaubnis_erledigt")
        t = bis(w, lambda m: m.get("typ") == "text" and "erlaubt" in m["text"].lower())
        assert t


def test_fehlerhafter_szenenbefehl(server):
    srv, c = server
    with ws(c) as w:
        w.receive_json()
        w.send_json({"typ": "szene_befehl", "aktion": "waehle", "args": {"nummer": 9}})
        m = bis(w, lambda m: m.get("typ") == "fehler")
        assert "Liste" in m["text"]


def test_seiten_und_csp(server):
    srv, c = server
    for pfad in ("/", "/klassisch", "/vorschau"):
        r = c.get(pfad)
        assert r.status_code == 200, pfad
        csp = r.headers["content-security-policy"]
        assert "script-src 'self'" in csp and "http" not in csp.split("connect-src")[0]
    assert "three" in c.get("/").text
    assert c.get("/static/vendor/three-0.170.0/build/three.module.min.js").status_code == 200
    assert c.get("/", headers={"host": "evil.example"}).status_code == 403


# ---------- Runde 2: verhörte Befehlswörter ----------

@pytest.mark.parametrize("gehoert,erwartet", [
    ("Elidit", "erledigt"), ("Erlidigt.", "erledigt"), ("Focus", "fokus"), ("Zeig mir die Totos", "zeig mir die todos"),
    ("Inbocks", "inbox"), ("das muss ich noch erledigen", "das muss ich noch erledigen"), ("Projekt Test", "projekt test"),
])
def test_normalisiere_verhoerte_woerter(gehoert, erwartet):
    assert schnellbefehl.normalisiere(gehoert) == erwartet


def test_verhoerte_einwortbefehle_wirken():
    fokus = {"ansicht": "fokus", "fokus": {"nr": 1, "uuid": "x"}, "karten": [{"nr": 1}], "gewaehlt": None}
    assert schnellbefehl.erkenne("Elidit", fokus)[0] == "erledigt"
    liste = {"ansicht": "liste", "karten": [{"nr": 1}, {"nr": 2}], "gewaehlt": 2}
    assert schnellbefehl.erkenne("Focus.", liste)[0] == "fokus"
    assert schnellbefehl.erkenne("Erledigt.", liste)[0] == "erledigt"
    assert schnellbefehl.erkenne("Erledigt.", {"ansicht": "liste", "karten": [{"nr": 1}], "gewaehlt": None}) is None
    assert schnellbefehl.erkenne("Zeig mir die Totos.", {})[1] == {"art": "heute"}

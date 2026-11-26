"""Tests für Konfiguration, Modul-Lader, Systemanweisung, Taskwarrior-Modul und den Kern ohne Module.

    uv run --with pytest --with httpx pytest -q
"""
import asyncio
import importlib
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from cockpit_ui import konfig, module
from cockpit_ui.agent import sprechstil, szene_werkzeuge
from cockpit_ui.module import Kern, ModulFehler
from cockpit_ui.szene import Szene, SzenenFehler

WURZEL = Path(__file__).resolve().parents[1]
KERN = Kern(Path("/tmp"), "Testperson")


# ---------- Konfiguration ----------

def test_aufloesen(monkeypatch):
    monkeypatch.setenv("X_TEST_WERT", "geheim")
    monkeypatch.delenv("X_FEHLT", raising=False)
    assert konfig.aufloesen("env:X_TEST_WERT") == "geheim"
    assert konfig.aufloesen("env:X_FEHLT|standard") == "standard"
    assert konfig.aufloesen({"a": ["env:X_TEST_WERT", 3]}) == {"a": ["geheim", 3]}
    assert konfig.aufloesen("klartext") == "klartext"


def test_ohne_datei_kein_modul(tmp_path):
    k = konfig.lade(tmp_path / "fehlt.toml")
    assert k.datei is None and k.module == {}


def test_datei_lesen(tmp_path, monkeypatch):
    monkeypatch.setenv("X_KEY", "k1")
    datei = tmp_path / "config.toml"
    datei.write_text('person = "Alex"\nnamen = ["Kim"]\naufgaben = "tw"\n'
                     '[module.tw]\ntyp = "taskwarrior"\n[module.ontology]\ntyp = "mcp"\nkey = "env:X_KEY"\n'
                     '[module.alt]\naus = true\n')
    k = konfig.lade(datei)
    assert k.person == "Alex" and k.namen == ["Kim"] and k.aufgaben == "tw"
    assert k.module["ontology"]["key"] == "k1"
    m, fehler = module.lade(k.module, KERN)
    assert [x.name for x in m] == ["tw", "ontology"] and not fehler


def test_kaputte_datei(tmp_path):
    datei = tmp_path / "config.toml"
    datei.write_text("das ist [kein toml")
    k = konfig.lade(datei)
    assert k.fehler and not k.module


# ---------- Lader ----------

def test_unbekanntes_modul_haelt_den_rest_nicht_auf():
    m, fehler = module.lade({"gibtsnicht": {}, "o": {"typ": "mcp"}}, KERN)
    assert [x.name for x in m] == ["o"] and "gibtsnicht" in fehler[0]


def test_lokales_modul(tmp_path):
    (tmp_path / "notizen").mkdir()
    (tmp_path / "notizen" / "__init__.py").write_text(
        "from cockpit_ui.module import Modul\n"
        "class M(Modul):\n"
        "    def namen(self): return ['Zettel']\n"
        "def erstelle(name, konfig, kern): return M(name, konfig, kern, titel='Notizen')\n")
    m, fehler = module.lade({"notizen": {"prompt": "Notizen liegen im Ordner."}}, KERN, [tmp_path])
    assert not fehler and m[0].titel == "Notizen" and m[0].namen() == ["Zettel"]
    assert m[0].prompt() == "Notizen liegen im Ordner."


def test_mcp_modul():
    m, _ = module.lade({"ontology": {"typ": "mcp", "titel": "Ontology", "erlaubt": ["mcp__ontology__ask"]}}, KERN)
    assert "ontology" in m[0].prompt() and m[0].werkzeuge() == ["mcp__ontology__ask"]
    assert m[0].aufgaben is None and m[0].bereit()[0]


# ---------- Systemanweisung ----------

def test_sprechstil():
    mit = sprechstil("Alex", "Taskwarrior", ["Skill gtd gilt."])
    assert "Du sprichst mit Alex" in mit and "zeige_liste" in mit and "aus Taskwarrior" in mit and "Skill gtd gilt." in mit
    ohne = sprechstil()
    assert "dem Nutzer" in ohne and "zeige_liste" not in ohne and "kein Aufgabenmodul" in ohne
    assert "Taskwarrior" not in ohne and "Alex" not in ohne
    assert "zeige_liste" not in szene_werkzeuge(False) and "zeige_text" in szene_werkzeuge(False)


# ---------- Szene ohne Aufgabenmodul ----------

def test_szene_ohne_aufgaben():
    ev = []
    sz = Szene(None, ev.append)
    with pytest.raises(SzenenFehler, match="kein Aufgabenmodul"):
        asyncio.run(sz.liste("heute"))
    assert "Tafel" in asyncio.run(sz.text("T", "Inhalt"))
    asyncio.run(sz.auffrischen())  # leise


# ---------- Taskwarrior ----------

tw_fehlt = pytest.mark.skipif(shutil.which("task") is None, reason="Taskwarrior nicht installiert")


@pytest.fixture()
def tw(tmp_path):
    (tmp_path / "rc").write_text("")
    env = os.environ | {"TASKRC": str(tmp_path / "rc")}
    def add(*a):
        subprocess.run(["task", "rc.confirmation=off", "rc.verbose=nothing", f"rc.data.location={tmp_path / 'd'}", "add", *a],
                       env=env, check=True, capture_output=True)
    add("Inbox-Ding")
    add("Angebot schreiben", "project:buero", "+next", "due:today")
    add("Warte auf Max", "project:buero", "+waiting")
    add("Steuer", "project:privat", "+next", "due:yesterday")
    add("Später", "+next", "wait:tomorrow")
    add("Stillstand", "project:alt", "+someday")
    m, fehler = module.lade({"taskwarrior": {"taskrc": str(tmp_path / "rc"), "daten": str(tmp_path / "d")}}, KERN)
    assert not fehler
    return m[0]


@tw_fehlt
def test_taskwarrior_listen(tw):
    a = tw.aufgaben
    s = a.summary()
    assert (s["inbox"], s["next"], s["waiting"], s["due_today"], s["overdue"]) == (1, 2, 1, 1, 1)
    assert sorted(t["description"] for t in a.naechste()) == ["Angebot schreiben", "Steuer"]  # „Später“ verborgen
    assert [t["description"] for t in a.inbox()] == ["Inbox-Ding"]
    p = {x["name"]: x for x in a.projekte()}
    assert p["alt"]["stalled"] and not p["buero"]["stalled"]
    assert [t["description"] for t in a.aufgaben(q="MAX")] == ["Warte auf Max"]
    assert tw.bereit()[0] and "buero" in tw.namen() and tw.stand()


@tw_fehlt
def test_taskwarrior_in_der_szene(tw):
    ev = []
    sz = Szene(tw.aufgaben, ev.append, quelle=tw.titel)
    text = asyncio.run(sz.liste("heute"))
    assert "Steuer" in text and "Angebot schreiben" in text
    assert "Taskwarrior" in asyncio.run(sz.erledigt(1))
    assert asyncio.run(sz.liste("ueberfaellig")).endswith("keine Einträge.")
    with pytest.raises(ModulFehler):
        tw.aufgaben.erledigt("keine-id!")


# ---------- Server ganz ohne Aufgabenmodul ----------

@pytest.fixture()
def nackter_server(tmp_path, monkeypatch):
    datei = tmp_path / "config.toml"
    datei.write_text('[module.ontology]\ntyp = "mcp"\n')
    monkeypatch.setenv("COCKPIT_UI_KONFIG", str(datei))
    monkeypatch.setenv("COCKPIT_UI_AGENT", "attrappe")
    monkeypatch.setenv("COCKPIT_UI_PORT", "8499")
    monkeypatch.setenv("COCKPIT_DIR", str(tmp_path))
    from cockpit_ui import server as srv
    srv = importlib.reload(srv)
    srv.app.router.on_startup.clear()
    from fastapi.testclient import TestClient
    with TestClient(srv.app, base_url="http://127.0.0.1:8499") as c:
        yield srv, c
    monkeypatch.undo()
    importlib.reload(srv)


def test_kern_ohne_aufgaben(nackter_server):
    srv, c = nackter_server
    s = c.get("/api/status").json()
    assert s["aufgaben"] is None and [m["name"] for m in s["module"]] == ["ontology"]
    assert c.get("/api/ueberblick").json()["fehler"]
    assert c.get("/api/aufgabe/abcdef12").status_code == 503
    assert "kein Aufgabenmodul" in srv.ANWEISUNG and "ontology" in srv.ANWEISUNG
    assert asyncio.run(srv.schnell("Zeig mir die Todos.", "text")) is False  # geht an den Agenten


# ---------- Darstellung: Hinweise auf Karten und Browser-Teil der Module ----------

def test_anzeige_wird_geprueft():
    from cockpit_ui.szene import anzeige, karte
    a = anzeige({"abzeichen": ["Kunde", "", "x" * 40, "c", "d"], "farbe": "blau", "symbol": "🚲 lang",
                 "untertitel": "u" * 200, "art": "Zettel", "effekt": "kaputt name!", "unbekannt": 1,
                 "daten": {"farbe": "#fff"}})
    assert a == {"abzeichen": ["Kunde", "x" * 24, "c"], "farbe": "blau", "symbol": "🚲 la", "untertitel": "u" * 120,
                 "art": "zettel", "daten": {"farbe": "#fff"}}
    assert anzeige({"farbe": "url(javascript:1)"}) == {} and anzeige({"farbe": "#a1b2c3"}) == {"farbe": "#a1b2c3"}
    assert anzeige("quatsch") == {} and anzeige({"daten": {"x": "y" * 5000}}) == {}
    assert karte({"uuid": "a1", "description": "T", "anzeige": {"abzeichen": "Kunde"}}, 1)["anzeige"] == {"abzeichen": ["Kunde"]}
    assert karte({"uuid": "a1", "description": "T"}, 1)["anzeige"] == {}


def test_beispielmodul_zettel_mit_browser_teil():
    pfad = WURZEL / "beispiele" / "module"
    m, fehler = module.lade({"zettel": {}}, KERN, [pfad])
    assert not fehler and m[0].web == (pfad / "zettel" / "web").resolve()
    inbox = m[0].aufgaben.inbox()
    assert inbox and all(t["anzeige"]["art"] == "zettel" for t in inbox)
    m2, _ = module.lade({"beispiel": {}}, KERN, [pfad])
    assert m2[0].web is None   # eingebaut, kein Browser-Teil


@pytest.fixture()
def server_mit_web(tmp_path, monkeypatch):
    (tmp_path / "m" / "deko" / "web").mkdir(parents=True)
    (tmp_path / "m" / "deko" / "__init__.py").write_text(
        "from cockpit_ui.module import Modul\ndef erstelle(name, konfig, kern): return Modul(name, konfig, kern)\n")
    (tmp_path / "m" / "deko" / "web" / "modul.js").write_text("export default () => {};\n")
    (tmp_path / "m" / "deko" / "geheim.js").write_text("nicht ausliefern\n")
    (tmp_path / "m" / "deko" / "web" / "notiz.md").write_text("falsche Endung\n")
    datei = tmp_path / "config.toml"
    datei.write_text(f'module_pfade = ["{tmp_path / "m"}"]\n[module.deko]\n')
    monkeypatch.setenv("COCKPIT_UI_KONFIG", str(datei))
    monkeypatch.setenv("COCKPIT_UI_AGENT", "attrappe")
    monkeypatch.setenv("COCKPIT_UI_PORT", "8499")
    monkeypatch.setenv("COCKPIT_DIR", str(tmp_path))
    from cockpit_ui import server as srv
    srv = importlib.reload(srv)
    srv.app.router.on_startup.clear()
    from fastapi.testclient import TestClient
    with TestClient(srv.app, base_url="http://127.0.0.1:8499") as c:
        yield srv, c
    monkeypatch.undo()
    importlib.reload(srv)


def test_browser_teil_wird_ausgeliefert(server_mit_web):
    srv, c = server_mit_web
    assert c.get("/api/status").json()["modul_web"] == [{"name": "deko", "url": "/modul/deko/modul.js"}]
    r = c.get("/modul/deko/modul.js")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/javascript")
    assert c.get("/modul/deko/../geheim.js").status_code == 404
    assert c.get("/modul/deko/%2e%2e/geheim.js").status_code == 404
    assert c.get("/modul/deko/notiz.md").status_code == 404
    assert c.get("/modul/fremd/modul.js").status_code == 404

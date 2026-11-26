"""Tests für Themes: Prüfen, Palette, Ablage, REST und Werkzeug.

    uv run --with pytest --with httpx pytest -q tests/test_themes.py
"""
import importlib
import json
import os
from pathlib import Path

import pytest

WURZEL = Path(__file__).resolve().parents[1]
KONFIG = Path(os.environ.get("TMPDIR", "/tmp")) / f"cockpit-ui-test-themes-{os.getpid()}.toml"
KONFIG.write_text("[module.beispiel]\n")
os.environ.update({"COCKPIT_UI_AGENT": "attrappe", "COCKPIT_UI_PORT": "8499", "COCKPIT_UI_VORLESER": "piper",
                   "COCKPIT_DIR": str(WURZEL / "tests"), "COCKPIT_UI_KONFIG": str(KONFIG)})

from cockpit_ui import themes as T  # noqa: E402


@pytest.fixture(autouse=True)
def ordner(tmp_path, monkeypatch):
    monkeypatch.setenv("COCKPIT_UI_THEMES", str(tmp_path / "themes"))   # nie die echten Themes
    yield tmp_path / "themes"


def test_normiere_fuellt_auf_und_verwirft_unsinn():
    t = T.normiere({"name": "Test", "farben": {"text": "red", "akzent": "#ABC"}, "verlauf": ["#fff"],
                    "kugel": {"toenung": "#ff0000", "toenung_staerke": 7}, "stil": "kitsch", "boese": "<script>",
                    "schrift": "Comic Sans; } body { display:none"})
    assert t["id"] == "test" and "boese" not in t
    assert t["farben"]["text"] == T.STANDARD["farben"]["text"]       # kaputte Farbe -> Standard
    assert t["farben"]["akzent"] == "#aabbcc"                        # Kurzform ausgeschrieben
    assert t["verlauf"] == T.STANDARD["verlauf"]                     # zu kurzer Verlauf -> Standard
    assert t["kugel"]["toenung_staerke"] == 1.0                      # begrenzt
    assert t["stil"] is None and t["schrift"] == ""                  # nur erlaubte Werte, keine CSS-Einschleusung
    with pytest.raises(T.ThemeFehler):
        T.normiere({"farben": {}})                                   # ohne Namen


def test_eingebaute_themes_sind_gueltig():
    for tid, roh in T.EINGEBAUT.items():
        t = T.normiere(roh)
        assert t["id"] == tid and len(t["kugel"]["galaxie"]) == 4 and len(t["hintergrund"]["nebel"]) == 3


def test_aus_palette_dunkel_und_lesbar():
    t = T.aus_palette(["#1b2a3a", "#e07a2f", "#f2c14e", "#3a6ea5", "#0b0f14", "#d9d4c7"], "Hafen")
    assert t["id"] == "hafen" and t["name"] == "Hafen"
    assert T.hsl(t["farben"]["grund"])[2] < 0.05 and T.hsl(t["farben"]["tief"])[2] < 0.1
    assert T.hsl(t["farben"]["text"])[2] > 0.9
    assert 3 <= len(t["verlauf"]) <= 9 and len(set(t["verlauf"])) == len(t["verlauf"])
    assert t["kugel"]["toenung"] and 0 < t["kugel"]["toenung_staerke"] <= 1
    # Graues Bild: trotzdem ein brauchbarer Verlauf
    grau = T.aus_palette(["#111111", "#777777", "#eeeeee"])
    assert len(grau["verlauf"]) >= 3 and grau["id"].startswith("bild-")
    with pytest.raises(T.ThemeFehler):
        T.aus_palette(["kein", "hex"])


def test_ablage_aktiv_und_loeschen(ordner):
    assert T.aktiv()["id"] == "harnorb"
    t = T.speichere({"name": "Mein Rot", "farben": {"akzent": "#ff4040"}})
    assert (ordner / "mein-rot.json").is_file()
    assert T.setze_aktiv("Mein Rot")["id"] == "mein-rot" and T.aktiv()["farben"]["akzent"] == "#ff4040"
    assert [x["id"] for x in T.liste()][-1] == "mein-rot"
    # Eingebaute bleiben unberührt: gleicher Name wird zu einer eigenen Kopie
    assert T.speichere({"id": "nordlicht", "name": "Nordlicht"})["id"] == "nordlicht-eigen"
    with pytest.raises(T.ThemeFehler):
        T.loesche("bernstein")
    T.loesche("mein-rot")
    assert T.aktiv()["id"] == "harnorb" and not (ordner / "mein-rot.json").exists()
    with pytest.raises(T.ThemeFehler):
        T.finde("gibt-es-nicht")
    with pytest.raises(T.ThemeFehler):
        T.finde("../../etc/passwd")


@pytest.fixture()
def server():
    from cockpit_ui import server as srv
    srv = importlib.reload(srv)
    srv.app.router.on_startup.clear()
    from fastapi.testclient import TestClient
    with TestClient(srv.app, base_url="http://127.0.0.1:8499") as c:
        yield srv, c


def test_rest_und_werkzeug(server):
    srv, c = server
    assert c.get("/api/theme").json()["id"] == "harnorb"
    assert {t["id"] for t in c.get("/api/themes").json()["themes"]} >= {"harnorb", "bernstein", "nordlicht"}
    r = c.post("/api/theme", json={"aktion": "waehle", "name": "bernstein"})
    assert r.status_code == 200 and r.json()["theme"]["id"] == "bernstein"
    assert c.post("/api/theme", json={"aktion": "waehle", "name": "quatsch"}).status_code == 400
    r = c.post("/api/theme/bild", json={"palette": ["#102030", "#e05050", "#50e0a0"], "verfeinern": False})
    assert r.status_code == 200 and r.json()["theme"]["id"].startswith("bild-")
    assert c.get("/api/theme").json()["id"] == r.json()["theme"]["id"]

    async def werkzeug(name, args):
        return await srv.szene_werkzeug(name, args)
    import asyncio
    text = asyncio.run(werkzeug("theme", {"aktion": "speichere", "theme": json.dumps(
        {"name": "Herbst", "farben": {"akzent": "#e08030"}, "stil": "comic"})}))
    assert "Herbst" in text and c.get("/api/theme").json()["id"] == "herbst"
    assert "Herbst" in asyncio.run(werkzeug("theme", {"aktion": "liste"}))
    with pytest.raises(srv.SzenenFehler):
        asyncio.run(werkzeug("theme", {"aktion": "speichere", "theme": "{kaputt"}))

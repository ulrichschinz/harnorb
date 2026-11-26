"""Stimmendienste: Prüfung, Speicher, Protokoll gegen einen kleinen Testserver, Namen per Sprache."""
import json
import struct
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from cockpit_ui import bedienung as b
from cockpit_ui import stimmen
from cockpit_ui.schnellbefehl import erkenne


class Dienst(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        if self.path == "/stimmen":
            daten = json.dumps({"modell": "test", "strom": True, "stimmen": [{"id": "lena", "name": "Lena"}]}).encode()
            self.send_response(200); self.end_headers(); self.wfile.write(daten)
        else:
            self.send_response(404); self.end_headers()

    def do_POST(self):
        auftrag = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        if auftrag["stimme"] != "lena":
            self.send_response(404); self.end_headers(); self.wfile.write(b'{"detail": "unbekannt"}'); return
        if self.path == "/sprich_strom":
            self.send_response(200); self.end_headers()
            for wort in auftrag["text"].split():
                teil = b"RIFF" + wort.encode()
                self.wfile.write(struct.pack(">I", len(teil)) + teil)
            return
        self.send_response(200); self.end_headers(); self.wfile.write(b"RIFF" + auftrag["text"].encode())


@pytest.fixture
def dienst():
    srv = HTTPServer(("127.0.0.1", 0), Dienst)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_port}"
    srv.shutdown()


def test_protokoll(dienst):
    d = stimmen.HttpStimme("pc", dienst).aktualisiere()
    assert d.fehler == "" and d.stimmen_liste[0]["name"] == "Lena" and d.modell == "test"
    assert d.sprich("Hallo", "lena") == b"RIFFHallo"
    with pytest.raises(stimmen.DienstFehler, match="404"):
        d.sprich("Hallo", "bob")


def test_strom(dienst):
    d = stimmen.HttpStimme("pc", dienst).aktualisiere()
    assert d.strom is True
    assert list(d.sprich_strom("Hallo du da", "lena")) == [b"RIFFHallo", b"RIFFdu", b"RIFFda"]
    with pytest.raises(stimmen.DienstFehler, match="404"):
        list(d.sprich_strom("Hallo", "bob"))
    d.strom = False  # Dienst ohne Strom: ein einziger Teil über /sprich
    assert list(d.sprich_strom("Hallo du", "lena")) == [b"RIFFHallo du"]


def test_nicht_erreichbar():
    d = stimmen.HttpStimme("pc", "http://127.0.0.1:9").aktualisiere()
    assert "nicht erreichbar" in d.fehler and d.stimmen_liste == []


def test_pruefe_dienst():
    assert stimmen.pruefe_dienst(" PC ", "http://192.168.1.50:8470") == ("pc", "http://192.168.1.50:8470")
    for name, url in [("pc", "ftp://x"), ("p c", "http://x"), ("", "http://x"), ("pc", "100.1.1.1:8470")]:
        with pytest.raises(stimmen.DienstFehler):
            stimmen.pruefe_dienst(name, url)


def test_speichern(tmp_path):
    p = tmp_path / "s.json"
    assert stimmen.lade(p) == {"dienste": [], "auswahl": ""}
    stimmen.speichere({"dienste": [{"name": "pc", "url": "http://x"}], "auswahl": "http:pc:lena"}, p)
    assert stimmen.lade(p)["auswahl"] == "http:pc:lena"
    assert (p.stat().st_mode & 0o777) == 0o600


def test_namen_per_sprache():
    alle = [{"id": "pc:lena", "name": "Lena", "art": "http", "gruppe": "Stimmendienst pc", "geschlecht": ""},
            {"id": "s1", "name": "Sarah - Mature", "geschlecht": "female"}]
    assert b.finde_stimme("lena", alle) == ("http", alle[0])
    assert b.finde_stimme("sarah", alle)[0] == "elevenlabs"
    assert "Stimmendienst pc" in b.stimmen_text(alle)
    assert erkenne("Stimme Lena", {}, ["lena", "sarah"])[:2] == ("einstellung", {"name": "stimme", "wert": "lena"})


@pytest.mark.parametrize("satz, wert", [("Konfiguration öffnen", True), ("Konfiguration schließen", False),
                                        ("Einstellungen zeigen", True), ("Konfiguration zu", False)])
def test_konfiguration_per_sprache(satz, wert):
    assert erkenne(satz, {}, [])[:2] == ("einstellung", {"name": "konfiguration", "wert": wert})

"""Menüpunkte per Sprache: Erkennung der Sätze und Auflösung der Werte."""
import pytest

from cockpit_ui import bedienung as b
from cockpit_ui.schnellbefehl import erkenne

STIMMEN = [{"id": "s1", "name": "Sarah - Mature", "geschlecht": "female", "akzent": ""},
           {"id": "l1", "name": "Lily - Velvety", "geschlecht": "female", "akzent": ""},
           {"id": "g1", "name": "George - Warm", "geschlecht": "male", "akzent": ""}]
KURZ = ["sarah", "lily", "george"]


@pytest.mark.parametrize("satz, erwartet", [
    ("Stimme Lily", ("einstellung", {"name": "stimme", "wert": "lily"})),
    ("Wechsel auf Stimme Sarah", ("einstellung", {"name": "stimme", "wert": "sarah"})),
    ("Stimme lokal", ("einstellung", {"name": "stimme", "wert": "lokal"})),
    ("Vorlesen aus", ("einstellung", {"name": "vorlesen", "wert": False})),
    ("Mach das Vorlesen an", ("einstellung", {"name": "vorlesen", "wert": True})),
    ("Schalte die Töne an", ("einstellung", {"name": "toene", "wert": True})),
    ("Untertitel an", ("einstellung", {"name": "untertitel", "wert": True})),
    ("Freisprechen an", ("einstellung", {"name": "freisprechen", "wert": True})),
    ("Schalte das Freisprechen aus", ("einstellung", {"name": "freisprechen", "wert": False})),
    ("Diagnose ausblenden", ("einstellung", {"name": "diagnose", "wert": False})),
    ("Qualität auf niedrig", ("einstellung", {"name": "qualitaet", "wert": "niedrig"})),
    ("Stil Comic", ("stil", {"stil": "comic"})),
    ("Hintergrund Raumer", ("stil", {"hintergrund": "raumer"})),
    ("Hintergrund-Rauma", ("stil", {"hintergrund": "raumer"})),
    ("Was kann ich sagen?", ("befehle", {})),
    ("Welche Stimmen gibt es?", ("stimmen", {})),
    ("Neues Gespräch", ("neu", {})),
])
def test_menuesaetze(satz, erwartet):
    assert erkenne(satz, {}, KURZ)[:2] == erwartet


@pytest.mark.parametrize("satz", ["Stimme Bob", "ich stimme zu", "Vorlesen bitte", "stimmt das so"])
def test_kein_menuebefehl(satz):
    t = erkenne(satz, {}, KURZ)
    assert t is None or t[0] not in ("einstellung", "neu")


def test_finde_stimme():
    assert b.finde_stimme("lily", STIMMEN)[1]["id"] == "l1"
    assert b.finde_stimme("Geo", STIMMEN)[1]["id"] == "g1"
    assert b.finde_stimme("lokal", STIMMEN) == ("piper", None)
    with pytest.raises(b.BedienFehler):
        b.finde_stimme("bob", STIMMEN)


def test_werte():
    assert b.name_von("Töne") == "toene"
    assert b.schalter("aus") is False and b.schalter(True) is True
    assert b.stufe("automatisch") == "auto"
    with pytest.raises(b.BedienFehler):
        b.name_von("lautstaerke")
    assert "Frauen" in b.stimmen_text(STIMMEN) and "George" in b.stimmen_text(STIMMEN)

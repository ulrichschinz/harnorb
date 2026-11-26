"""Menüpunkte der Oberfläche per Sprache: Stimme, Vorlesen, Effekttöne, Qualität, Untertitel, Diagnose, Hilfe.

Reine Logik ohne Server, damit sie testbar bleibt. Der Server führt aus:
- Stimme setzt er selbst (sie gilt serverseitig für alle Fenster),
- alles andere schickt er als Ereignis {"typ": "einstellung", "name", "wert"} an den Browser,
  der es wie einen Klick auf den Schalter behandelt.

Erlaubnisanfragen gehören nicht hierher; dafür gibt es `erlaubnis_per_stimme` im Server.
"""
import re

SCHALTER = ("vorlesen", "toene", "untertitel", "diagnose", "hilfe", "konfiguration", "freisprechen")
STUFEN = ("auto", "hoch", "mittel", "niedrig")
NAMEN = SCHALTER + ("qualitaet", "stimme")

ALIAS = {
    "töne": "toene", "effekttöne": "toene", "effekttoene": "toene", "effekte": "toene", "ton": "toene",
    "sprachausgabe": "vorlesen", "qualität": "qualitaet", "grafik": "qualitaet", "stufe": "qualitaet",
    "vorleser": "stimme", "sprecherin": "stimme", "sprecher": "stimme", "befehle": "hilfe", "tasten": "hilfe",
    "konfig": "konfiguration", "freisprechmodus": "freisprechen", "freihändig": "freisprechen",
    "handsfree": "freisprechen", "dauerzuhören": "freisprechen", "config": "konfiguration", "einstellungen": "konfiguration", "stimmendienste": "konfiguration",
}
AN = {"an", "ein", "true", "1", "ja", "on", "einschalten", "anschalten", "anmachen", "zeigen", "auf", "öffnen"}
AUS = {"aus", "ab", "false", "0", "nein", "off", "ausschalten", "abschalten", "ausmachen", "ausblenden", "zu",
       "schliessen", "schließen"}
STUFE_ALIAS = {"automatisch": "auto", "hohe": "hoch", "niedrige": "niedrig", "mittlere": "mittel", "gering": "niedrig"}
LOKAL = {"lokal", "piper", "lokale", "thorsten", "offline"}


class BedienFehler(ValueError):
    pass


def name_von(name):
    n = str(name or "").strip().lower()
    n = ALIAS.get(n, n)
    if n not in NAMEN:
        raise BedienFehler(f"Einstellung {name!r} gibt es nicht. Möglich: {', '.join(NAMEN)}")
    return n


def schalter(wert):
    w = str(wert).strip().lower()
    if w in AN:
        return True
    if w in AUS:
        return False
    raise BedienFehler(f"{wert!r} verstehe ich nicht als an oder aus.")


def stufe(wert):
    w = str(wert).strip().lower()
    w = STUFE_ALIAS.get(w, w)
    if w not in STUFEN:
        raise BedienFehler(f"Qualität {wert!r} gibt es nicht. Möglich: {', '.join(STUFEN)}")
    return w


def kurzname(stimme):
    """„Sarah - Mature, Reassuring“ -> „Sarah“."""
    return stimme["name"].split(" - ")[0].strip()


def finde_stimme(wunsch, stimmen):
    """-> ("piper", None) oder (art, stimme) mit art aus stimme["art"] (Standard "elevenlabs").
    Name ohne Groß/Klein, auch nur der Anfang („alice“)."""
    w = str(wunsch or "").strip().lower()
    if w in LOKAL:
        return "piper", None
    for v in stimmen:
        if kurzname(v).lower() == w or v["id"] == wunsch:
            return v.get("art", "elevenlabs"), v
    treffer = [v for v in stimmen if len(w) >= 3 and kurzname(v).lower().startswith(w)]
    if len(treffer) == 1:
        return treffer[0].get("art", "elevenlabs"), treffer[0]
    raise BedienFehler(f"Stimme {wunsch!r} kenne ich nicht.")


GESCHLECHT = {"female": "Frauen", "neutral": "Neutral", "male": "Männer"}


def stimmen_text(stimmen):
    gruppen = {}
    for v in stimmen:
        gruppen.setdefault(v.get("gruppe") or GESCHLECHT.get(v["geschlecht"], "Weitere"), []).append(kurzname(v))
    zeilen = ["- **Lokal:** Piper (sag „Stimme lokal“)"]
    zeilen += [f"- **{g}:** {', '.join(n)}" for g, n in gruppen.items()]
    return "\n".join(zeilen)


BEFEHLE = """\
**Listen:** „zeig die Inbox“, „was ist überfällig“, „Todos“, „Warten“, „Projekte“, „Projekt Name“
**Karten:** „die zweite“, „daran arbeite ich“, „erledigt“, „weg damit“
**Stimme:** „Stimme Lena“, „Stimme lokal“, „welche Stimmen gibt es“, „Konfiguration öffnen“
**Stimmendienste:** „binde den Stimmendienst pc unter 192.168.1.50 Port 8470 an“, „entferne Dienst pc“ (macht HarnoRb)
**Schalter:** „Vorlesen aus“, „Töne an“, „Untertitel an“, „Freisprechen an“, „Diagnose an“, „Hilfe“
**Aussehen:** „Stil Comic“, „Stil leuchtend“, „Hintergrund Raumer“, „Hintergrund Mond“, „Qualität niedrig“
**Gespräch:** „Stopp“, „neues Gespräch“, „ja“ oder „nein“ bei einer Erlaubnisfrage

Alles andere verstehe ich als Frage an HarnoRb."""

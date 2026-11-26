"""Schnellbefehle: Standardsätze, die ohne Claude sofort wirken (schnell und kostenlos).

Erkannt werden nur kurze, eindeutige Sätze. Alles andere geht an Claude.
`erkenne(text, zustand)` -> (aktion, argumente, antwort) oder None.
"""
import re

from .szene import ZAHLWORT

_NORM = str.maketrans({"ß": "ss"})


def _klein(text):
    t = text.lower().translate(_NORM)
    t = re.sub(r"[^\wäöü:\- ]+", " ", t)
    return re.sub(r"\s+", " ", t).strip()


# Befehlswörter, die Whisper bei kurzen Sätzen gern verhört. Bekannte Fehlhörungen stehen fest drin,
# alles andere fängt eine Levenshtein-Distanz ab (höchstens 1 bei kurzen, 2 bei langen Wörtern).
SCHLUESSELWOERTER = ["erledigt", "fokus", "todos", "inbox", "ausblenden", "überfällig", "projekte", "fokussieren"]
VERHOERT = {
    "elidit": "erledigt", "elidigt": "erledigt", "erlidigt": "erledigt", "erledicht": "erledigt", "erledig": "erledigt",
    "erlegt": "erledigt", "erleditt": "erledigt", "eledigt": "erledigt", "erledigte": "erledigt",
    "focus": "fokus", "fockus": "fokus", "fokuss": "fokus", "vokus": "fokus", "phokus": "fokus",
    "totos": "todos", "todo": "todos", "to-dos": "todos", "toto": "todos", "todoss": "todos", "tudus": "todos",
    "inbocks": "inbox", "imbox": "inbox", "inboxx": "inbox", "inbugs": "inbox",
    "ueberfaellig": "überfällig", "uberfallig": "überfällig", "überfallig": "überfällig",
}


def _abstand(a, b):
    if abs(len(a) - len(b)) > 2:
        return 9
    vorher = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        jetzt = [i]
        for j, cb in enumerate(b, 1):
            jetzt.append(min(vorher[j] + 1, jetzt[j - 1] + 1, vorher[j - 1] + (ca != cb)))
        vorher = jetzt
    return vorher[-1]


# echte Wörter, die nah an einem Befehlswort liegen, aber etwas anderes bedeuten
ECHTE_WOERTER = {"projekt", "projekten", "erledigen", "erledige", "erledigst", "erledigung", "fokussiert", "ausblende",
                 "ausgeblendet", "einblenden", "todes", "tobias", "inboxen", "fokussiere"}


def _richte(wort):
    if wort in VERHOERT:
        return VERHOERT[wort]
    if len(wort) < 5 or wort in SCHLUESSELWOERTER or wort in ECHTE_WOERTER:
        return wort
    grenze = 1 if len(wort) < 7 else 2
    beste = min(SCHLUESSELWOERTER, key=lambda k: _abstand(wort, k))
    return beste if _abstand(wort, beste) <= grenze else wort


def normalisiere(text):
    """Kleinschreibung, Satzzeichen weg, verhörte Befehlswörter zurechtgerückt."""
    return " ".join(_richte(w) for w in _klein(text).split())


LISTEN = [
    (r"(inbox|eingang|posteingang)", "inbox", "Die Inbox."),
    (r"(überfällig|ueberfaellig|überfälligen)", "ueberfaellig", "Das Überfällige."),
    (r"(warte|warten|warteliste|worauf warte ich)", "warten", "Worauf du wartest."),
    (r"(projekte|projektliste)", "projekte", "Die Projekte."),
    (r"(nächsten aktionen|nächste aktionen|naechste)", "naechste", "Die nächsten Aktionen."),
    (r"(todos?|todes|to-dos|to dos|aufgaben|heute|was steht an)", "heute", "Deine Aufgaben für heute."),
]
ZEIG = r"^(zeig|zeige|zeigt|öffne|oeffne|was ist|was steht|was sind|wo ist|liste)\b"


# Menüpunkte: Ziel-Wort -> Name der Einstellung (siehe bedienung.py)
ZIELE = {"vorlesen": "vorlesen", "sprachausgabe": "vorlesen", "töne": "toene", "effekttöne": "toene",
         "effekte": "toene", "untertitel": "untertitel", "diagnose": "diagnose",
         "konfiguration": "konfiguration", "einstellungen": "konfiguration", "konfig": "konfiguration"}
AN_AUS = {"an": True, "ein": True, "einschalten": True, "anschalten": True, "anmachen": True, "zeigen": True,
          "öffnen": True, "oeffnen": True, "auf": True,
          "aus": False, "schließen": False, "schliessen": False, "zu": False, "ab": False, "ausschalten": False, "abschalten": False, "ausmachen": False, "ausblenden": False}
BITTE = r"(bitte )?"
VERB = r"((schalte?|schalt|mach|stell|stelle|nimm|nehm|nehme|wechsel|wechsle|wähle|waehle)( mal)?( die| das| den| auf)? )?"


def _menue(t, stimmen):
    """Sprachbefehle für die Menüpunkte. -> (aktion, args, antwort) oder None."""
    t = t.replace("-", " ")  # Whisper schreibt gern „Hintergrund-Rauma“
    ziele = "|".join(ZIELE)
    an_aus = "|".join(AN_AUS)
    m = re.fullmatch(BITTE + VERB + rf"(?P<z>{ziele}) (?P<w>{an_aus})( bitte)?", t)
    if m:
        return ("einstellung", {"name": ZIELE[m["z"]], "wert": AN_AUS[m["w"]]}, None)
    m = re.fullmatch(BITTE + VERB + r"(qualität|grafik)( auf)? (?P<w>auto|automatisch|hoch|mittel|niedrig)( bitte)?", t)
    if m:
        return ("einstellung", {"name": "qualitaet", "wert": m["w"]}, None)
    if re.fullmatch(r"(welche stimmen( gibt es| hast du| hast du denn)?( alle)?|stimmen( zeigen| liste)?|zeig( mir)? (die )?stimmen)( bitte)?", t):
        return ("stimmen", {}, None)
    m = re.fullmatch(BITTE + VERB + r"(stimme|sprecherin|sprecher)( auf| zu)? (?P<n>[a-zäöü]+)( bitte)?", t)
    if m and (m["n"] in stimmen or m["n"] in ("lokal", "piper")):
        return ("einstellung", {"name": "stimme", "wert": m["n"]}, None)
    m = re.fullmatch(BITTE + VERB + r"(stil|aussehen)( auf)? (?P<s>comic|cartoon|leuchtend|realistisch)( bitte)?", t)
    if m:
        return ("stil", {"stil": m["s"]}, "Stil " + m["s"] + ".")
    m = re.fullmatch(BITTE + VERB + r"hintergrund( auf)? (?P<h>mond|raumer|rauma|rahmer|kugelraumer|kugelrauma|raumschiff)( bitte)?", t)
    if m:
        h = "mond" if m["h"] == "mond" else "raumer"
        return ("stil", {"hintergrund": h}, "Hintergrund " + h + ".")
    if re.fullmatch(r"(was kann ich sagen|welche befehle( gibt es)?|sprachbefehle|befehle|hilfe|zeig( mir)? (die )?befehle)( bitte)?", t):
        return ("befehle", {}, None)
    if re.fullmatch(BITTE + r"(hilfe|befehle) (aus|zu|ausblenden|schliessen)", t):
        return ("einstellung", {"name": "hilfe", "wert": False}, None)
    if re.fullmatch(BITTE + r"(starte? )?(ein )?(neues gespräch|neues thema|neu anfangen)( starten| bitte)?", t):
        return ("neu", {}, None)
    return None


def erkenne(text, zustand, stimmen=()):
    """stimmen: Kurznamen der wählbaren ElevenLabs-Stimmen, klein geschrieben („sarah“)."""
    t = normalisiere(text or "")
    if not t:
        return None
    woerter = t.split()
    if len(woerter) > 7:
        return None
    if re.fullmatch(r"(stopp|stop|halt|ruhe|sei still)( bitte)?", t):
        return ("stopp", {}, None)
    treffer = _menue(t, set(stimmen))
    if treffer:
        return treffer
    if re.fullmatch(r"(bitte )?(ausblenden|blende (alles |das )?aus|weg damit|alles weg|weg|leere szene|"
                    r"zurück|schliessen|schliess das|mach (das |alles )?zu)( bitte)?", t):
        return ("ausblenden", {}, "")
    m = re.fullmatch(r"(zeig(e|t)? (mir )?(das )?)?projekt ([\w\-. ]{3,40})", t)
    if m and m.group(1):
        return ("zeige_liste", {"art": "projekt:" + m.group(5).strip()}, None)
    if re.search(ZEIG, t) or len(woerter) <= 2:
        for muster, art, antwort in LISTEN:
            if re.search(r"\b" + muster + r"\b", t):
                return ("zeige_liste", {"art": art}, antwort)
    sichtbar = zustand.get("karten") or []
    if sichtbar and zustand.get("ansicht") == "liste":
        m = re.fullmatch(r"(die |der |das |nummer |den )?(\w+)( bitte)?", t)
        if m and (m.group(2) in ZAHLWORT or m.group(2).isdigit()):
            return ("waehle", {"nummer": m.group(2)}, None)
    gewaehlt = zustand.get("gewaehlt") or (zustand.get("fokus") or {}).get("nr")
    if gewaehlt and re.fullmatch(r"(daran arbeite ich( jetzt)?|die nehme ich|(in den )?fokus( darauf| bitte)?|fokussieren|"
                                r"das mache ich( jetzt)?)", t):
        return ("fokus", {}, None)
    ziel = (zustand.get("ansicht") == "fokus" and zustand.get("fokus")) or \
        (zustand.get("ansicht") == "liste" and zustand.get("gewaehlt"))
    if ziel and re.fullmatch(r"(die |das )?(ist |das ist |schon |ist schon )?(erledigt|fertig|abgehakt|hab ich erledigt)( bitte)?", t):
        return ("erledigt", {}, None)
    return None

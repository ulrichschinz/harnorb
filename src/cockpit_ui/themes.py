"""Themes: Farben, Verlauf, Kugel und Hintergrund der Oberfläche als kleine JSON-Datei.

Ein Theme beschreibt nur Farben und ein paar Stärken, nie Code. Der Browser setzt daraus CSS-Variablen
(Kern und Module lesen nur diese) und die Shaderwerte von Kugel und Hintergrund (`web/theme.js`).

Eigene Themes liegen in `~/.config/cockpit-ui/themes/<id>.json` (anderer Ordner über
`COCKPIT_UI_THEMES`), das aktive steht in `aktiv.txt` daneben. Eingebaute Themes stehen unten und
lassen sich nicht überschreiben oder löschen.

Aufbau (alle Schlüssel freiwillig, Fehlendes kommt aus dem Standard-Theme „harnorb“):

    {"id": "herbst", "name": "Herbst", "beschreibung": "…",
     "farben": {"grund", "flaeche", "tief", "text", "akzent", "hinweis", "nutzer", "ok", "warn"},   # #hex
     "verlauf": ["#hex", …],                     # 3 bis 9 Farben für die schillernden Ränder
     "schrift": "Avenir Next, sans-serif",       # optional
     "kugel": {"toenung": "#hex" | null, "toenung_staerke": 0..1, "galaxie": [4 × #hex], "schein": "#hex"},
     "hintergrund": {"nebel": [3 × #hex], "licht": "#hex", "art": "mond" | "raumer" | null, "staerke": 0–2},
     "stil": "leuchtend" | "comic" | null, "leuchten": 0.1..1.2}
"""
import colorsys
import json
import os
import re
import unicodedata
from datetime import datetime
from pathlib import Path

ORDNER = Path(os.environ.get("COCKPIT_UI_THEMES", "~/.config/cockpit-ui/themes")).expanduser()
HEX = re.compile(r"#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})")
ID = re.compile(r"[a-z0-9][a-z0-9-]{0,39}")
SCHRIFT = re.compile(r"[\w\s,\"'-]{1,120}")
FARB_SCHLUESSEL = ("grund", "flaeche", "tief", "text", "akzent", "hinweis", "nutzer", "ok", "warn")


class ThemeFehler(Exception):
    pass


STANDARD = {
    "id": "harnorb", "name": "HarnoRb", "beschreibung": "Schillernde Seifenblase vor tiefem Blau, das Original.",
    "farben": {"grund": "#020308", "flaeche": "#242c5c", "tief": "#0a0c1e", "text": "#eef1ff", "akzent": "#96aaff",
               "hinweis": "#ffe08a", "nutzer": "#ffc0a8", "ok": "#7cf5d4", "warn": "#ff9a7a"},
    "verlauf": ["#ff6ad5", "#c774e8", "#ad8cff", "#8795e8", "#94d0ff", "#7cf5d4", "#f6f98e", "#ffb86b"],
    "schrift": "",
    "kugel": {"toenung": None, "toenung_staerke": 0.0, "galaxie": ["#ffb361", "#ff389e", "#7a38ff", "#1fccff"], "schein": "#d959ff"},
    "hintergrund": {"nebel": ["#330f52", "#052e4d", "#4d1a2e"], "licht": "#40d9ff", "art": None},
    "stil": None, "leuchten": 0.5,
}

EINGEBAUT = {t["id"]: t for t in (
    STANDARD,
    {"id": "bernstein", "name": "Bernstein", "beschreibung": "Warmes Gold und Kupfer, wie Abendlicht in Harz.",
     "farben": {"grund": "#070402", "flaeche": "#4a2a12", "tief": "#140a04", "text": "#fff3e4", "akzent": "#ffb45e",
                "hinweis": "#ffe08a", "nutzer": "#ffd0a0", "ok": "#b8e986", "warn": "#ff8a65"},
     "verlauf": ["#ffcf70", "#ff9f43", "#ff6b3d", "#e8505b", "#f7b267", "#ffe29a"],
     "kugel": {"toenung": "#ffa94d", "toenung_staerke": 0.7, "galaxie": ["#fff0c2", "#ffb347", "#ff6a3d", "#b8325a"], "schein": "#ff9a3c"},
     "hintergrund": {"nebel": ["#3d1d06", "#2a1206", "#4a1f10"], "licht": "#ffb347"}, "leuchten": 0.55},
    {"id": "nordlicht", "name": "Nordlicht", "beschreibung": "Grün und Türkis über einem kalten Polarhimmel.",
     "farben": {"grund": "#010605", "flaeche": "#123a3a", "tief": "#04110f", "text": "#eafff8", "akzent": "#5cf2c4",
                "hinweis": "#d8ff8a", "nutzer": "#b6f0ff", "ok": "#5cf2c4", "warn": "#ff8f8f"},
     "verlauf": ["#3cf2a0", "#2ee6d6", "#44b8ff", "#8a7dff", "#3cf2a0", "#c8ff7a"],
     "kugel": {"toenung": "#4cf0c0", "toenung_staerke": 0.65, "galaxie": ["#eaffd0", "#7dffb0", "#2ad4d4", "#5a6cff"], "schein": "#38e8b0"},
     "hintergrund": {"nebel": ["#06331f", "#04283a", "#1a1a44"], "licht": "#5cf2c4"}, "leuchten": 0.5},
)}


# ---------- Farben ----------

def _hex6(f):
    f = f.lower()
    return "#" + "".join(c * 2 for c in f[1:]) if len(f) == 4 else f


def farbe(wert, standard=None):
    w = str(wert or "").strip()
    return _hex6(w) if HEX.fullmatch(w) else standard


def _rgb(f):
    f = _hex6(f)
    return tuple(int(f[i:i + 2], 16) / 255 for i in (1, 3, 5))


def _hex(r, g, b):
    return "#" + "".join(f"{round(max(0, min(1, x)) * 255):02x}" for x in (r, g, b))


def hsl(f):
    """-> (Farbton 0..1, Sättigung, Helligkeit)"""
    h, l, s = colorsys.rgb_to_hls(*_rgb(f))
    return h, s, l


def aus_hsl(h, s, l):
    return _hex(*colorsys.hls_to_rgb(h % 1.0, max(0, min(1, l)), max(0, min(1, s))))


def _zahl(wert, standard, unten, oben):
    try:
        return max(unten, min(oben, float(wert)))
    except (TypeError, ValueError):
        return standard


def slug(text):
    t = unicodedata.normalize("NFKD", str(text or "").lower().replace("ä", "ae").replace("ö", "oe")
                              .replace("ü", "ue").replace("ß", "ss"))
    t = re.sub(r"[^a-z0-9]+", "-", t.encode("ascii", "ignore").decode()).strip("-")
    return t[:40].strip("-") or "theme"


# ---------- Prüfen ----------

def normiere(roh, basis=None):
    """Theme prüfen und vervollständigen. Unbekanntes fällt still weg, kaputte Farben nehmen den Standard.
    basis: Theme, dessen Werte für Fehlendes gelten (Standard: harnorb)."""
    if not isinstance(roh, dict):
        raise ThemeFehler("Ein Theme ist ein JSON-Objekt.")
    b = basis or STANDARD
    name = str(roh.get("name") or roh.get("id") or "").strip()[:60]
    if not name:
        raise ThemeFehler("Das Theme braucht einen Namen.")
    tid = str(roh.get("id") or "").strip().lower()
    t = {"id": tid if ID.fullmatch(tid) else slug(name), "name": name,
         "beschreibung": str(roh.get("beschreibung") or "").strip()[:300]}
    rf = roh.get("farben") if isinstance(roh.get("farben"), dict) else {}
    t["farben"] = {k: farbe(rf.get(k), b["farben"][k]) for k in FARB_SCHLUESSEL}
    verlauf = [f for f in (farbe(x) for x in (roh.get("verlauf") or [])) if f] if isinstance(roh.get("verlauf"), list) else []
    t["verlauf"] = verlauf[:9] if len(verlauf) >= 3 else list(b["verlauf"])
    s = str(roh.get("schrift") or "").strip()
    t["schrift"] = s if SCHRIFT.fullmatch(s) else ""
    rk = roh.get("kugel") if isinstance(roh.get("kugel"), dict) else {}
    bk = b["kugel"]
    gal = [f for f in (farbe(x) for x in (rk.get("galaxie") or [])) if f] if isinstance(rk.get("galaxie"), list) else []
    ton = farbe(rk.get("toenung")) if "toenung" in rk else bk["toenung"]
    t["kugel"] = {"toenung": ton,
                  "toenung_staerke": _zahl(rk.get("toenung_staerke"), bk["toenung_staerke"] if ton else 0.0, 0.0, 1.0) if ton else 0.0,
                  "galaxie": gal if len(gal) == 4 else list(bk["galaxie"]),
                  "schein": farbe(rk.get("schein"), bk["schein"])}
    rh = roh.get("hintergrund") if isinstance(roh.get("hintergrund"), dict) else {}
    bh = b["hintergrund"]
    nebel = [f for f in (farbe(x) for x in (rh.get("nebel") or [])) if f] if isinstance(rh.get("nebel"), list) else []
    art = rh.get("art") if rh.get("art") in ("mond", "raumer") else None
    t["hintergrund"] = {"nebel": nebel if len(nebel) == 3 else list(bh["nebel"]), "licht": farbe(rh.get("licht"), bh["licht"]), "art": art,
                        "staerke": _zahl(rh.get("staerke"), bh.get("staerke", 1.0), 0.0, 2.0)}
    t["stil"] = roh.get("stil") if roh.get("stil") in ("leuchtend", "comic") else None
    t["leuchten"] = _zahl(roh.get("leuchten"), b["leuchten"], 0.1, 1.2)
    if roh.get("quelle"):
        t["quelle"] = str(roh["quelle"])[:120]
    return t


# ---------- Aus einer Palette ----------

def aus_palette(palette, name=""):
    """Theme aus den Hauptfarben eines Bildes (Liste #hex, häufigste zuerst). Ohne KI, sofort.
    Dunkles Theme: Flächen aus dem Farbton der dunklen Bildteile, Akzent und Verlauf aus den kräftigen."""
    farben = [f for f in (farbe(x) for x in (palette or [])) if f]
    if not farben:
        raise ThemeFehler("Keine Farben im Bild gefunden.")
    werte = [(f, *hsl(f)) for f in farben]
    # Kräftigkeit: gesättigt und mittelhell, häufige Farben leicht bevorzugt
    def kraft(i_w):
        i, (_, h, s, l) = i_w
        return s * (1 - abs(l - 0.55) * 1.4) - i * 0.01
    bunt = [w for _, w in sorted(enumerate(werte), key=kraft, reverse=True) if w[2] > 0.18 and 0.12 < w[3] < 0.92]
    dunkel = sorted(werte, key=lambda w: w[3])
    akz = bunt[0] if bunt else max(werte, key=lambda w: w[2])
    ha, sa = akz[1], max(akz[2], 0.35)
    # Grundton der Flächen: dunkle Bildteile mit etwas Farbe, sonst der Akzent
    basis = next((w for w in dunkel if w[2] > 0.12), None) or akz
    hb, sb = basis[1], min(max(basis[2], 0.25), 0.6)

    verlauf = []
    for w in sorted(bunt[:7], key=lambda w: w[1]):
        f = aus_hsl(w[1], max(w[2], 0.55), min(max(w[3], 0.62), 0.78))
        if all(sum(abs(a - b) for a, b in zip(_rgb(f), _rgb(v))) > 0.12 for v in verlauf):   # fast gleiche nur einmal
            verlauf.append(f)
    while len(verlauf) < 4:   # zu wenig Farbe im Bild: Nachbarn des Akzents im Farbkreis
        verlauf.append(aus_hsl(ha + 0.09 * (len(verlauf) - 1), max(sa, 0.6), 0.7))
    verlauf = list(dict.fromkeys(verlauf))

    zweit = bunt[1] if len(bunt) > 1 else (ha + 0.08, sa, 0.6)
    zweit_h = zweit[1] if len(zweit) == 4 else zweit[0]
    warm = next((w for w in bunt if (w[1] < 0.17 or w[1] > 0.95) and w[3] > 0.45), None)
    gal = [aus_hsl(ha + 0.03, 0.5, 0.86)] + [aus_hsl(h, max(sa, 0.65), 0.6) for h in
                                            [w[1] for w in (bunt[:3] if len(bunt) >= 3 else [akz] * 3)]]
    nebel = [aus_hsl(w[1], min(max(w[2], 0.45), 0.8), 0.14) for w in (bunt + [basis] * 3)[:3]]
    roh = {
        "name": name or "Aus Bild " + datetime.now().strftime("%d.%m. %H:%M"),
        "id": slug(name) if name else "bild-" + datetime.now().strftime("%Y%m%d-%H%M%S"),
        "beschreibung": "Aus den Farben eines Bildes.",
        "farben": {"grund": aus_hsl(hb, sb * 0.6, 0.018), "flaeche": aus_hsl(hb, sb, 0.2), "tief": aus_hsl(hb, sb * 0.7, 0.06),
                   "text": aus_hsl(ha, 0.35, 0.95), "akzent": aus_hsl(ha, max(sa, 0.6), 0.74),
                   "hinweis": aus_hsl(warm[1], 0.9, 0.76) if warm else "#ffe08a",
                   "nutzer": aus_hsl(zweit_h, 0.75, 0.82), "ok": "#7cf5d4", "warn": "#ff9a7a"},
        "verlauf": verlauf,
        "kugel": {"toenung": aus_hsl(ha, max(sa, 0.6), 0.6), "toenung_staerke": 0.6, "galaxie": gal,
                  "schein": aus_hsl(ha, max(sa, 0.7), 0.62)},
        "hintergrund": {"nebel": nebel, "licht": aus_hsl(ha, 0.85, 0.65)},
        "leuchten": 0.5,
        "quelle": "bild",
    }
    return normiere(roh)


# ---------- Ablage ----------

def _ordner():
    return Path(os.environ.get("COCKPIT_UI_THEMES") or ORDNER).expanduser()


def liste():
    eigene = {}
    for p in sorted(_ordner().glob("*.json")):
        try:
            t = normiere(json.loads(p.read_text()))
        except (OSError, ValueError, ThemeFehler):
            continue
        if t["id"] not in EINGEBAUT:
            eigene[t["id"]] = t
    return [{"id": t["id"], "name": t["name"], "beschreibung": t.get("beschreibung", ""), "eingebaut": True} for t in EINGEBAUT.values()] + \
           [{"id": t["id"], "name": t["name"], "beschreibung": t.get("beschreibung", ""), "eingebaut": False} for t in eigene.values()]


def finde(wer):
    """Theme per id oder Name (ohne Groß-/Kleinschreibung). -> vollständiges Theme oder ThemeFehler"""
    w = str(wer or "").strip().lower()
    for kandidat in (w, slug(w)):
        if kandidat in EINGEBAUT:
            return normiere(EINGEBAUT[kandidat])
        p = _ordner() / f"{kandidat}.json"
        if ID.fullmatch(kandidat) and p.is_file():
            try:
                return normiere(json.loads(p.read_text()))
            except (OSError, ValueError) as e:
                raise ThemeFehler(f"Theme {kandidat} ist kaputt: {e}") from None
    for t in liste():
        if t["name"].lower() == w:
            return finde(t["id"])
    raise ThemeFehler(f"Theme {wer!r} gibt es nicht. Möglich: " + ", ".join(t["name"] for t in liste()))


def speichere(theme):
    t = normiere(theme)
    if t["id"] in EINGEBAUT:
        t["id"] = t["id"] + "-eigen"
    d = _ordner()
    d.mkdir(parents=True, exist_ok=True)
    ziel = d / f"{t['id']}.json"
    tmp = ziel.with_suffix(".tmp")
    tmp.write_text(json.dumps(t, ensure_ascii=False, indent=1))
    tmp.replace(ziel)
    return t


def loesche(wer):
    t = finde(wer)
    if t["id"] in EINGEBAUT:
        raise ThemeFehler("Eingebaute Themes lassen sich nicht löschen.")
    (_ordner() / f"{t['id']}.json").unlink(missing_ok=True)
    if aktiv_id() == t["id"]:
        setze_aktiv(STANDARD["id"])
    return t


def aktiv_id():
    try:
        return (_ordner() / "aktiv.txt").read_text().strip() or STANDARD["id"]
    except OSError:
        return STANDARD["id"]


def aktiv():
    try:
        return finde(aktiv_id())
    except ThemeFehler:
        return normiere(STANDARD)


def setze_aktiv(wer):
    t = finde(wer)
    d = _ordner()
    d.mkdir(parents=True, exist_ok=True)
    (d / "aktiv.txt").write_text(t["id"] + "\n")
    return t

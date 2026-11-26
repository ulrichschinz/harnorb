"""Cockpit-Dateien lesen und von HarnoRb erzeugte Dokumente ablegen.

Lesen: alles unter dem Cockpit-Ordner außer versteckten Pfaden (.git, .env, .index, .raw …) und
Dateien, die nach Secrets aussehen. Symlinks, die aus dem Cockpit hinausführen, sind gesperrt.
Schreiben: nur `erstelle()`, immer als neue Notiz unter `knowledge/` (bei HTML zusätzlich die Seite daneben).
"""
import datetime as dt
import mimetypes
import re
import unicodedata
from pathlib import Path

GESPERRT = re.compile(r"(^|/)\.|(\.(key|pem|p12|pfx|kdbx|env)$)|secret|credential|passw|token", re.I)
TEXT = {".md", ".txt", ".csv", ".json", ".yaml", ".yml", ".toml", ".py", ".sh", ".js", ".css", ".log", ".ini", ".cfg", ""}
BILD = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"}
MAX_TEXT = 2_000_000


class DateiFehler(ValueError):
    pass


def aufloesen(wurzel: Path, pfad: str) -> Path:
    """Relativer Cockpit-Pfad -> absoluter Pfad. Wirft DateiFehler bei allem außerhalb oder Gesperrtem."""
    rel = str(pfad or "").strip().lstrip("/")
    rel = re.sub(r"^(~/cockpit/|cockpit/)", "", rel)
    wurzel = wurzel.resolve()
    ziel = (wurzel / rel).resolve()
    if ziel != wurzel and wurzel not in ziel.parents:
        raise DateiFehler("Pfad liegt außerhalb des Cockpits.")
    relativ = ziel.relative_to(wurzel).as_posix() if ziel != wurzel else ""
    if relativ and GESPERRT.search(relativ):
        raise DateiFehler("Diese Datei ist gesperrt (versteckt oder Secret).")
    if not ziel.exists():
        raise DateiFehler(f"{relativ or '/'} gibt es nicht.")
    return ziel


def art_von(p: Path) -> str:
    if p.is_dir():
        return "ordner"
    s = p.suffix.lower()
    if s == ".md":
        return "md"
    if s in (".html", ".htm"):
        return "html"
    if s == ".pdf":
        return "pdf"
    if s in BILD:
        return "bild"
    if s in TEXT:
        return "text"
    return "datei"


def lies(wurzel: Path, pfad: str) -> dict:
    p = aufloesen(wurzel, pfad)
    rel = p.relative_to(wurzel.resolve()).as_posix() if p != wurzel.resolve() else ""
    art = art_von(p)
    d = {"pfad": rel, "art": art, "name": p.name or "Cockpit"}
    if art == "ordner":
        eintraege = []
        for k in sorted(p.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower())):
            r = k.relative_to(wurzel.resolve()).as_posix()
            if GESPERRT.search(r):
                continue
            eintraege.append({"name": k.name, "pfad": r, "art": art_von(k),
                              "groesse": k.stat().st_size if k.is_file() else None})
        d["eintraege"] = eintraege
    elif art in ("md", "text"):
        if p.stat().st_size > MAX_TEXT:
            raise DateiFehler("Datei zu groß für die Anzeige.")
        d["inhalt"] = p.read_text(errors="replace")
        d["geaendert"] = dt.datetime.fromtimestamp(p.stat().st_mtime).isoformat(timespec="minutes")
    return d


def roh(wurzel: Path, pfad: str):
    """-> (Pfad, MIME) für die direkte Auslieferung (PDF, Bilder, HTML-Seiten)."""
    p = aufloesen(wurzel, pfad)
    if p.is_dir():
        raise DateiFehler("Ordner kann man nicht direkt öffnen.")
    mime = mimetypes.guess_type(p.name)[0] or "application/octet-stream"
    if art_von(p) in ("md", "text"):
        mime = "text/plain; charset=utf-8"
    return p, mime


def suche(wurzel: Path, begriff: str, n=60) -> list:
    """Dateinamen-Suche (alle Wörter müssen im Pfad vorkommen)."""
    woerter = [w for w in _flach(begriff).split() if w]
    if not woerter:
        return []
    wurzel = wurzel.resolve()
    treffer = []
    for p in wurzel.rglob("*"):
        r = p.relative_to(wurzel).as_posix()
        if GESPERRT.search(r) or not p.is_file():
            continue
        flach = _flach(r)
        if all(w in flach for w in woerter):
            treffer.append({"pfad": r, "name": p.name, "art": art_von(p), "zeit": p.stat().st_mtime})
    treffer.sort(key=lambda t: -t["zeit"])
    return treffer[:n]


def _flach(s):
    s = s.lower().replace("ä", "ae").replace("ö", "oe").replace("ü", "ue").replace("ß", "ss")
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()


def slug(titel):
    s = re.sub(r"[^a-z0-9]+", "-", _flach(titel)).strip("-")
    return s[:60].rstrip("-") or "dokument"


def erstelle(wurzel: Path, titel: str, inhalt: str, format="markdown", beschreibung="", heute=None) -> str:
    """Legt ein Dokument als Notiz in knowledge/ ab. -> relativer Pfad der Datei, die der Leser zeigt."""
    titel = str(titel or "").strip()
    if not titel or not str(inhalt or "").strip():
        raise DateiFehler("Titel und Inhalt fehlen.")
    format = "html" if str(format).lower() in ("html", "htm") else "markdown"
    heute = heute or dt.date.today()
    ordner = wurzel / "knowledge"
    ordner.mkdir(exist_ok=True)
    basis = f"{heute.isoformat()}-{slug(titel)}"
    name, i = basis, 2
    while (ordner / f"{name}.md").exists() or (ordner / f"{name}.html").exists():
        name, i = f"{basis}-{i}", i + 1
    kopf = (f'---\ntype: note\ntitle: "{titel.replace(chr(34), chr(39))}"\nstatus: draft\ndate: {heute.isoformat()}\n'
            f"area: []\nsources: []\ntags: [harno]\ndata_class: internal\n---\n\n")
    if format == "html":
        (ordner / f"{name}.html").write_text(inhalt)
        text = (f"# {titel}\n\n{beschreibung.strip() or 'Von HarnoRb erstellte Seite.'}\n\n"
                f"Ansicht: [{name}.html]({name}.html) (in HarnoRb öffnen)\n")
        (ordner / f"{name}.md").write_text(kopf + text)
        return f"knowledge/{name}.html"
    text = inhalt.strip()
    if not text.startswith("# "):
        text = f"# {titel}\n\n{text}"
    (ordner / f"{name}.md").write_text(kopf + text + "\n")
    return f"knowledge/{name}.md"


MAX_UPLOAD = 20 * 1024 * 1024   # größere Dateien gehören nicht ins Cockpit (kein Platz für Binärriesen im Repo)


def _kopf_brief(titel, heute, extra=""):
    t = titel.replace(chr(34), chr(39))
    return (f'---\ntype: brief\ntitle: "{t}"\nstatus: open\ndate: {heute.isoformat()}\nfrom: harnorb\n'
            f"tags: [upload]\ndata_class: internal\n---\n\n{extra}")


def ablegen(wurzel: Path, name: str, daten: bytes, ordner="inbox", heute=None) -> dict:
    """Hochgeladene Datei im Eingang ablegen: `<ordner>/YYYY-MM-DD-slug.endung`, nie überschreiben.
    Markdown und Text ohne Frontmatter bekommen eine Eingangs-Frontmatter vorangestellt; jede andere Datei eine
    Begleitkarte (`….md`) daneben, die auf sie verweist. -> {"pfad", "karte", "name", "art", "groesse"}"""
    name = Path(str(name or "")).name.strip() or "datei"
    if len(daten) > MAX_UPLOAD:
        raise DateiFehler(f"{name} ist größer als {MAX_UPLOAD // (1024 * 1024)} MB.")
    if not daten:
        raise DateiFehler(f"{name} ist leer.")
    endung = Path(name).suffix.lower()
    if GESPERRT.search(name) or not re.fullmatch(r"(\.[a-z0-9]{1,8})?", endung):
        raise DateiFehler(f"{name}: Dateiname oder Endung nicht erlaubt.")
    heute = heute or dt.date.today()
    ziel = wurzel / ordner
    if ziel.resolve() != wurzel.resolve() and wurzel.resolve() not in ziel.resolve().parents:
        raise DateiFehler("Der Eingangsordner liegt außerhalb des Cockpits.")
    ziel.mkdir(parents=True, exist_ok=True)
    basis = f"{heute.isoformat()}-{slug(Path(name).stem)}"
    stamm, i = basis, 2
    while (ziel / f"{stamm}{endung}").exists() or (ziel / f"{stamm}.md").exists():
        stamm, i = f"{basis}-{i}", i + 1
    datei = ziel / f"{stamm}{endung}"
    titel = f"Hochgeladen: {name}"
    karte = None
    if endung in (".md", ".txt"):
        text = daten.decode("utf-8", errors="replace")
        if not text.startswith("---\n"):
            text = _kopf_brief(titel, heute) + text
        datei.write_text(text)
    else:
        datei.write_bytes(daten)
        karte = ziel / f"{stamm}.md"
        karte.write_text(_kopf_brief(titel, heute, f"# {titel}\n\nIn HarnoRb hochgeladen am {heute:%d.%m.%Y}: "
                                     f"[{datei.name}]({datei.name}) ({len(daten) // 1024 or 1} KB). Noch nicht "
                                     "verarbeitet: an den richtigen Ort überführen, dann `status: done`.\n"))
    rel = lambda p: p.relative_to(wurzel.resolve()).as_posix()
    return {"pfad": rel(datei.resolve()), "karte": rel(karte.resolve()) if karte else None, "name": name,
            "art": art_von(datei), "groesse": len(daten)}

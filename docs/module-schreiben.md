# Module schreiben und anbinden

HarnoRb besteht aus einem **Kern** und **Modulen**. Der Kern braucht nur einen Agenten (Claude Code)
und einen Cockpit-Ordner: Gespräch, Sprache, Szene mit Text, Optionen, Stil und Einstellungen.
Alles andere bringen Module mit, und zwar je Rechner, wie es dort passt. 

## 1. Welche Module laufen

Das bestimmt die Konfiguration des Rechners, `~/.config/cockpit-ui/config.toml` (anderer Pfad über
`COCKPIT_UI_KONFIG`). Vorlage mit allen Schlüsseln: [`konfig.beispiel.toml`](../konfig.beispiel.toml).
Fehlt die Datei, läuft nur der Kern.

```toml
person = "Alex"
[module.taskwarrior]          # Abschnittsname = Modulname; typ = Modulname, wenn nicht angegeben
[module.wissen]
typ = "mcp"
server = "ontology"
```

Werte als `env:NAME`, `env:NAME|Standard` oder `keychain:DIENST` werden beim Start aufgelöst. Secrets
gehören nie in die Datei. `aus = true` schaltet ein Modul ab. Jedes Modul kennt `prompt` (Hinweis an
den Agenten, ersetzt den eingebauten) und `erlaubt` (Werkzeuge, die ohne Rückfrage laufen dürfen;
nur lesende eintragen).

Was geladen ist, zeigt die Diagnose der Oberfläche (Taste D) und `GET /api/status` (`module`,
`modul_fehler`). Ein kaputtes Modul verhindert den Start nicht. Es erscheint dann als Fehler.

## 2. Eingebaute Module

| Modul | Fähigkeiten | Einstellungen |
|---|---|---|
| `taskwarrior` | Aufgaben aus dem lokalen `task`, Wache, Namen | `befehl`, `taskrc`, `daten`, `tags` |
| `beispiel` | erfundene Aufgaben im Speicher, zum Ausprobieren und für Tests | keine |
| `mcp` | nur Hinweis an den Agenten, Statuszeile, Namen | `server`, `titel`, `prompt`, `erlaubt`, `namen` |

## 3. Einen MCP-Server anbinden (ohne Code)

1. Den Server dort eintragen, wo Claude Code ihn lädt: `.mcp.json` im Cockpit-Ordner oder die
   Nutzereinstellungen (`claude mcp add …`). cockpit-ui startet Claude Code mit denselben
   Einstellungen wie das Terminal.
2. In der Konfiguration ein Modul `typ = "mcp"` anlegen, mit `prompt`: ein, zwei Sätze, wofür der
   Server da ist und was der Agent nicht ohne Freigabe tun darf.
3. Oberfläche neu starten.

## 4. Ein eigenes Modul in Python

Ein Modul ist eine Datei `NAME.py` oder ein Ordner `NAME/__init__.py` in einem der `module_pfade`
(z. B. `~/.config/cockpit-ui/module/`). Eigene Module gehen eingebauten gleichen Namens vor. Sie
laufen mit vollen Rechten im Server, deshalb nur eigene Dateien, nichts Heruntergeladenes.

Die Datei braucht eine Funktion `erstelle(name, konfig, kern)`, die ein `Modul` liefert:

```python
from cockpit_ui.module import Aufgaben, Modul, ModulFehler


class Zettel(Aufgaben):
    """Beispiel: Aufgaben aus einem System, das der Kern nicht kennt."""
    def __init__(self, ordner):
        self.ordner = ordner

    def naechste(self):
        return [{"uuid": "zettel-1", "description": "Beispiel", "status": "pending", "tags": ["next"]}]
    # … inbox, warten, projekte, projekt, aufgaben, aufgabe, summary, erledigt, starten, stoppen, notiz


class ZettelModul(Modul):
    def bereit(self):                       # Statuszeile: (ok, Text)
        return True, "lokal"

    def prompt(self):                       # Hinweis an den Agenten
        return self.konfig.get("prompt", "Aufgaben liegen als Zettel im Ordner …")

    def namen(self):                        # Eigennamen für die Spracherkennung
        return []

    def stand(self):                        # Vergleichswert für die Wache (alle 30 s) oder None
        return None


def erstelle(name, konfig, kern):           # kern.cockpit: Pfad, kern.person: Anrede
    return ZettelModul(name, konfig, kern, titel=konfig.get("titel", "Zettel"),
                       aufgaben=Zettel(konfig.get("ordner")), aendert_bei=("zettel",))
```

Ein Modul überschreibt nur, was es kann. Ohne `aufgaben` ist es ein reines Zusatzmodul.

### Regeln

- **Fehler** als `ModulFehler("Satz für den Nutzer")`, nie mit Secrets oder Stacktrace im Text.
- **Blockieren ist erlaubt**: Der Kern ruft alle Methoden in einem Thread auf. Zeitlimits setzt das
  Modul selbst (Richtwert 15 bis 20 s).
- **`bereit()` und `namen()`** müssen schnell und fehlertolerant sein. Sie laufen beim Start und bei jeder
  Statusabfrage.
- **`aendert_bei`**: Teile von Werkzeugnamen. Endet ein solches Werkzeug im Gespräch, lädt die Szene
  die sichtbare Liste neu (z. B. `("mcp__zettel__",)`).
- **`prompt()`**: kurz, gesprochen, nur über das eigene Modul. Er landet unter „Angebundene Module“ in
  der Systemanweisung.

## 5. Die Schnittstelle `Aufgaben`

Gibt es mehrere Aufgabenmodule, entscheidet `aufgaben = "name"` in der Konfiguration, sonst gilt das
erste. Ohne Aufgabenmodul bietet die Szene `zeige_liste`, `waehle`, `fokus` und `erledigt` gar nicht an.
Sätze wie „zeig die Todos“ gehen dann an den Agenten.

Das Datenformat ist die Teilmenge des Taskwarrior-Exports, die Taskwarrior ohnehin
spricht. Andere Systeme übersetzen in dieses Format:

| Methode | liefert |
|---|---|
| `summary()` | `{inbox, overdue, due_today, next, waiting, waiting_followup_due}` (Zahlen) |
| `naechste()`, `inbox()`, `warten()` | Liste von Aufgaben |
| `projekte()` | Liste `{name, next, waiting, stalled, status}`; `status` `active` / `on_hold` / `done` |
| `projekt(name)` | Aufgaben des Projekts |
| `aufgaben(q=None, due_before=None, project=None)` | Suche; `due_before` als `YYYY-MM-DD`, streng davor |
| `aufgabe(uuid)` | eine Aufgabe, auch erledigte (`status` zeigt das) |
| `erledigt(uuid)`, `starten(uuid)`, `stoppen(uuid)`, `notiz(uuid, text)` | Aktion, Rückgabe beliebig |

Eine Aufgabe ist `{uuid, description, status, project?, due?, tags?, start?, annotations?}`:
`status` ist `pending`, `completed` oder `deleted`. `due`, `start` und `annotations[].entry` sind Zeitpunkte
in UTC im Format `YYYYMMDDTHHMMSSZ`. `tags` enthält die GTD-Marken (`next`, `waiting`, `someday`) und
Kontexte (`@home`). `uuid` ist jede stabile ID aus Buchstaben, Ziffern und `-_.:`, höchstens 64 Zeichen.

## 6. Darstellung: Hinweise, eigene Karten, eigene Effekte

Karten, Fokus und Animationen zeichnet der Kern. Ein Modul kann daran auf zwei Stufen mitwirken.

**Stufe 1: Hinweise in den Daten.** Jede Aufgabe (und jedes Projekt) darf ein Feld `anzeige` tragen.
Der Kern prüft es (`szene.anzeige()`), Unbekanntes fällt still weg:

| Schlüssel | Wert | Wirkung |
|---|---|---|
| `abzeichen` | Text oder Liste, bis 3 × 24 Zeichen | kleine Marken in der Metazeile |
| `farbe` | `blau gruen gelb orange rot violett grau` oder `#hex` | Randfarbe, Nummer, Abzeichen |
| `symbol` | bis 4 Zeichen, z. B. ein Emoji | vor dem Titel |
| `untertitel` | bis 120 Zeichen | Zeile unter dem Titel |
| `effekt` | `strahl` (Standard), `sanft` oder ein Effekt aus Stufe 2 | Erledigt-Animation |
| `art` | Name einer Kartenart aus Stufe 2 | Karte zeichnet das Modul selbst |
| `daten` | kleines Objekt (≤ 4 KB JSON) | frei für die eigene Kartenart |

```python
{"uuid": "a1", "description": "Angebot überarbeiten", "status": "pending",
 "anzeige": {"abzeichen": "Kunde", "farbe": "blau", "untertitel": "Musterfirma GmbH"}}
```

**Stufe 2: Browser-Teil.** Liegt neben dem Modul ein Ordner `web/` mit `modul.js`
(`<module_pfad>/<name>/web/modul.js`, anderer Ort über den Schlüssel `web` oder das Attribut `Modul.web`),
liefert der Server ihn unter `/modul/<name>/…` aus, und die Szene lädt ihn beim Start:

```js
export default function registriere(harnorb) {          // harnorb.version === 1
  harnorb.stil(`.karte.zettel { background: #fff3a8; color: #3a3320; }`);
  harnorb.kartenArt("zettel", {
    klasse: "zettel",
    karte: (el, k, h) => { el.innerHTML = `<div class="titel">${h.esc(k.titel)}</div>`; },
    fokus: (el, k, h) => { el.innerHTML = `<h1>${h.esc(k.titel)}</h1>`; },   // optional
  });
  harnorb.effekt("zerknuellen", async ({ eintrag, fx, kugelPos, tween, ease }) => {
    await tween({ dauer: 600, ease: ease.inOutCubic, update: (w) => { eintrag.skala = 1 - w; eintrag.op = 1 - w; } }).fertig;
  });
}
```

Die vollständige Schnittstelle steht im Kopf von `web/szene/erweiterungen.js`, ein lauffähiges Beispiel
in `beispiele/module/zettel/` (in `module_pfade` eintragen, `[module.zettel]`). Regeln:

- Größe, Platz, Bewegung und Klick der Karte gehören dem Kern: `transform`, `transform-origin`,
  `position` und `opacity` des Kartenelements nicht setzen.
- Texte aus den Daten immer mit `h.esc()` einsetzen.
- Stylesheets nur über `harnorb.stil()` oder `harnorb.stilDatei()`; eingebettete `<style>`-Elemente blockiert die CSP.
- **Themes:** Farben nicht fest eintragen, sondern die CSS-Variablen des Kerns nehmen, dann passt das Modul
  zu jedem Theme: `--text`, `--leise`, `--flaeche`, `--tief`, `--grund`, `--akzent`, `--hinweis`, `--nutzer`,
  `--ok`, `--warn`, `--rand`, `--irid` (Verlauf), `--schrift`. Abgestufte Töne mit
  `color-mix(in srgb, var(--flaeche) 60%, transparent)`. Wer Farben in JavaScript braucht (Canvas, three.js),
  liest `harnorb.theme()` und meldet sich mit `harnorb.beiTheme((t) => …)` für Wechsel an. Eine bewusst eigene
  Optik wie der gelbe Zettel im Beispiel darf bleiben.
- Scheitert eine Kartenart oder ein Effekt, zeichnet der Kern die Standardkarte bzw. entfernt die Karte;
  die Meldung steht in der Browser-Konsole, geladene Browser-Teile zeigt die Diagnose (Taste D).
- Module laufen mit vollen Rechten, im Server wie im Browser. Nur eigene Dateien einbinden.

## 7. Prüfen

- `uv run --with pytest --with httpx pytest -q`: `tests/test_module.py` zeigt Muster für eigene Tests,
  etwa Taskwarrior in einem Wegwerf-Verzeichnis oder den Kern ganz ohne Module.
- Probelauf mit eigener Konfiguration und Attrappen-Agent ohne Kosten:
  `COCKPIT_UI_KONFIG=/tmp/test.toml COCKPIT_UI_AGENT=attrappe COCKPIT_UI_PORT=8461 uv run cockpit-ui`.

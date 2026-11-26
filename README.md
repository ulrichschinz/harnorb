<p align="center">
  <img src="web/logo/harnorb-512.png" alt="HarnoRb" width="200">
</p>

<h1 align="center">HarnoRb</h1>

<p align="center"><b>Sprich mit deinem Cockpit.</b><br>
Eine schillernde Kugel im leeren Raum, die zuhört, antwortet und dir genau das zeigt, was du gerade brauchst.</p>

<p align="center">
  Claude Code · lokale Spracherkennung · 3D-Szene im Browser · Module für deine Systeme · MIT
</p>

---

## Die Idee: ein Cockpit für dein ganzes Leben

Ein **Cockpit** ist ein ganz normaler Ordner, in dem ein KI-Agent für dich den Überblick behält. Er arbeitet darin wie ein Stabschef: Er erfasst, was du ihm erzählst, legt es am richtigen Ort ab, hält das Lagebild aktuell, bereitet Entscheidungen vor und erinnert dich an Zusagen. Die Regeln dafür stehen als Text im Ordner (zum Beispiel in einer `AGENTS.md` oder `CLAUDE.md`), damit jeder Agent und jeder Mensch nachlesen kann, wie es funktioniert.

So ein Ordner kann zum Beispiel enthalten:

- ein **Lagebild** (`STATUS.md`): Fokus, laufende Vorhaben, offene Punkte
- **Projekte** mit Ziel und Verlauf, **Entscheidungen** mit Begründung, **Kontakte**, **Termine**
- ein **Journal**, in dem jede Sitzung festhält, was passiert ist
- **Wissen**: Anleitungen, Recherchen, Notizen

Dazu kommen die Systeme, in denen deine Arbeit ohnehin lebt, angebunden über Module: eine Aufgabenverwaltung nach GTD, eine Wissensdatenbank, ein CRM, ein Kalender. Der Agent liest und schreibt dort über MCP-Server, das Cockpit verweist nur darauf, statt alles zu kopieren. Ein Grundsatz trägt das Ganze: **Was nicht aufgeschrieben ist, weiß kein Agent.**

## HarnoRb: das Gesicht dazu

Im Terminal ist so ein Cockpit mächtig, aber nicht gerade einladend. HarnoRb macht daraus ein Gespräch. Du öffnest den Browser, siehst eine leere Szene mit einer schillernden Kugel, hältst die Leertaste und sprichst:

> „Was steht heute an?“ · „Zeig mir die Inbox.“ · „Die zweite.“ · „Daran arbeite ich jetzt.“ · „Erledigt.“ · „Mach mir eine Übersicht über das Projekt.“

Die Kugel hört zu, denkt sichtbar nach und antwortet gesprochen. Inhalte erscheinen nur auf Zuruf: Aufgabenkarten schweben neben ihr, die Aufgabe im Fokus rückt nach vorn, Erledigtes fliegt mit einem Lichtstrahl in die Kugel. Sagst du „weg damit“, ist der Raum wieder leer. Dahinter arbeitet **Claude Code** in deinem Cockpit-Ordner, mit allen Hooks, Skills, MCP-Servern und Regeln, die dort gelten, genau wie im Terminal.

**Was HarnoRb mitbringt**

- **Sprechen statt tippen.** Spracherkennung mit Whisper und Stimme mit Piper laufen lokal auf macOS und Linux. Audio verlässt den Rechner nicht, solange du keinen Cloud-Vorleser einschaltest. Kurze Standardsätze („die zweite“, „weg damit“) erkennt der Server selbst, sofort und ohne Agent.
- **Eine Szene, die nur zeigt, was gebraucht wird.** Karten, Fokus, Texttafeln, Auswahl-Optionen, Erlaubnisfragen als Tafel vor der Kugel („ja“, „nein“ oder J/N).
- **Ein Leser für dein Cockpit.** Markdown mit Mermaid-Diagrammen und Charts, PDFs, Bilder. Bittest du um eine Übersicht, legt der Agent sie als Notiz im Cockpit ab und öffnet sie gleich.
- **Module für deine Systeme.** Aufgaben, Wissen, CRM: Jedes System kommt als Modul dazu und kann sogar eigene Kartenarten und Erledigt-Effekte mitbringen.
- **Eigene Stimmen.** Neben Piper und ElevenLabs kann HarnoRb jeden TTS-Server im eigenen Netz anbinden, zum Beispiel Qwen3-TTS mit einer selbst entworfenen Stimme auf einer Grafikkarte.
- **Volle Tastatur.** Für alles, was schneller getippt als gesagt ist (Taste **H** zeigt die Übersicht).
- **Zwei Stile.** Leuchtend oder Comic, Hintergrund Mond oder Raumschiff, Qualitätsstufen passen sich dem Rechner an.

## Schnellstart

Voraussetzungen: [`uv`](https://docs.astral.sh/uv/), `ffmpeg` und [Claude Code](https://docs.claude.com/en/docs/claude-code) (`claude`, angemeldet).

```
git clone https://github.com/ulrichschinz/harnorb.git && cd harnorb
uv sync
uv run python -m piper.download_voices --download-dir ~/.local/share/cockpit-ui/stimmen de_DE-thorsten-high
COCKPIT_DIR=~/mein-cockpit uv run harnorb --oeffnen          # http://127.0.0.1:8450/
```

Beim ersten Start lädt faster-whisper das Erkennungsmodell (large-v3-turbo, ca. 1,6 GB). Der grüne Punkt oben rechts zeigt, wann die Sprache bereit ist. Dann Leertaste halten und sprechen.

**Noch kein Cockpit?** Ein leerer Ordner mit einer `CLAUDE.md`, in der steht, wie der Agent für dich arbeiten soll, reicht für den Anfang. Zum Ausprobieren mit erfundenen Aufgaben genügt eine Konfiguration mit der Zeile `[module.beispiel]` (siehe unten).

## Module: wie dein Cockpit mit deinen Systemen spricht

Der Kern braucht nur Claude Code und einen Ordner. Alles andere schaltest du je Rechner in `~/.config/cockpit-ui/config.toml` ein (Vorlage: [`konfig.beispiel.toml`](konfig.beispiel.toml)):

```toml
person = "Alex"

[module.taskwarrior]        # Aufgaben aus dem lokalen Taskwarrior

[module.wissen]             # eine Wissensdatenbank, die schon als MCP-Server läuft
typ = "mcp"
server = "wissen"
```

Eingebaut sind ein Taskwarrior-Modul, ein Modul für beliebige MCP-Server (ganz ohne Code) und ein Beispielmodul mit erfundenen Aufgaben. Ein eigenes Modul ist eine kleine Python-Datei. Es kann Karten mit Hinweisen gestalten (Abzeichen, Farbe, Symbol, Untertitel) und mit einer `web/modul.js` eigene Kartenarten und Effekte in die Szene bringen. Das Beispiel `beispiele/module/zettel/` zeigt die Inbox als bunte Haftnotizen, die beim Erledigen zerknüllt in die Kugel fliegen. Anleitung: [docs/module-schreiben.md](docs/module-schreiben.md).

## Bedienen (`/`)

- **Leertaste halten** oder den **Ring unten** halten: sprechen, Loslassen schickt die Aufnahme. Kurz auf den Ring tippen: freihändig aufnehmen, nochmals tippen sendet.
- Sätze wie „Zeig mir die Todos“, „Was ist überfällig?“, „Die zweite“, „Daran arbeite ich jetzt“, „Erledigt“, „Zeig mir die Inbox“, „Weg damit“, „Zeig das Projekt …“, „Stopp“. Kurze Standardsätze erkennt der Server selbst (Schnellbefehle, sofort und ohne Claude), alles andere geht an Claude, das die Szene über den MCP-Server `szene` steuert.
- Tasten: **Esc** Stopp · **A/O/I/W/P/N** Heute/Überfällig/Inbox/Warten/Projekte/Nächste · **1–9**, **←/→** Karte wählen, **Enter** Fokus · **E E** erledigt · **X** ausblenden · **T** tippen · **G** Tagesüberblick · **R** Inbox klären · **U** Untertitel · **D** Diagnose (Verlauf, Werkzeuge, Stimme, Qualität) · **S** Stil leuchtend/Comic · **B** Hintergrund Mond/Kugelraumer · **Q** Qualität · **M** Effekttöne · **F** Vollbild · **H** Hilfe.
- Erlaubnisfragen erscheinen als Tafel vor der Kugel: **J**/**N**, Klick oder „ja“/„nein“ sagen.
- Karten anklicken: einmal wählen, zweimal Fokus. Projektkarten öffnen das Projekt.
- `/vorschau`: Szene ohne Server, alle Zustände per Taste 1–9 (Ruhe, Zuhören, Denken, Sprechen, Zeigen, Fokus, Erledigt, Geschwächt, Übergang), Demo-Karten mit C/G/F/E/T/O/X. Für Screenshots per URL: `?zustand=denken&stil=comic&hintergrund=raumer&karten=1`.
- `/klassisch`: die bisherige Oberfläche, unverändert.

## Leser: Dokumente und Cockpit-Dateien

HarnoRb zeigt Dateien des Cockpit-Ordners in einem großen Leser vor der Szene (Taste **L**, „zeig mir STATUS“, „runter“, „schließen“): Markdown gerendert (mit ```` ```mermaid ```` für Diagramme und ```` ```chart ```` für Chart.js-Grafiken), PDFs, Bilder, Textdateien und HTML-Seiten. Bittet man um eine Übersicht oder Grafik, legt Claude sie mit dem Werkzeug `erstelle_dokument` als Notiz unter `knowledge/` ab (Tag `harno`) und öffnet sie. Nur lesend; gesperrt sind versteckte Pfade (`.git`, `.env` …), Dateinamen wie Secrets und Symlinks nach draußen (`src/cockpit_ui/dateien.py`). HTML-Seiten laufen abgeschottet (CSP-Sandbox, kein Netz) und dürfen nur die lokalen Bibliotheken unter `/static/vendor/` laden.

## Stimmendienste (eigene TTS-Server im Netz)

Neben Piper (lokal) und ElevenLabs (Cloud) kann HarnoRb über beliebige **Stimmendienste** vorlesen (Protokoll „http-tts“: `GET /stimmen`, `POST /sprich {text, stimme}` -> WAV). Verwaltet wird das in der **Konfiguration** (Taste **K**) oder per Sprache: „Konfiguration öffnen“, „Stimme Lena“, „binde den Stimmendienst pc unter http://192.168.1.50:8470 an“, „entferne den Dienst pc“. Dienste und gewählte Stimme speichert der Server in `~/.config/cockpit-ui/stimmen.json` (Token dort am besten als `env:NAME`).

Referenzdienst: `tools/stimmdienst/stimmdienst.py`, Qwen3-TTS 1.7B Base mit geklonter Stimme, für einen Rechner mit NVIDIA-GPU (getestet mit 8 GB VRAM). Beschleunigt mit faster-qwen3-tts (CUDA Graphs): ca. 0,5 s Rechenzeit je Sekunde Audio, VRAM ca. 5 GB. Je Stimme liegen eine Vorlage (`<id>.wav`, 5 bis 20 s) und ihr gesprochener Text (`<id>.txt`) im Stimmenordner. Einrichtung und Start stehen im Kopf des Skripts. Den Dienst nur im eigenen Netz oder über ein VPN erreichbar machen und ein Token setzen.

## Einstellungen (Umgebungsvariablen)

Konfigurationspfade und Variablen tragen noch das Präfix des Arbeitstitels `cockpit-ui`; der Befehl `cockpit-ui` funktioniert weiter wie `harnorb`.

| Variable | Standard | Zweck |
|---|---|---|
| `COCKPIT_UI_PORT` | `8450` | Port, nur 127.0.0.1 |
| `COCKPIT_DIR` | `~/cockpit` | Arbeitsordner für Claude Code |
| `WHISPER_MODELL` | `large-v3-turbo` (GPU) / `small` (CPU) | Erkennungsmodell |
| `WHISPER_GERAET` | `mps` (Apple Silicon), `cuda`, sonst `cpu` | Rechenwerk |
| `COCKPIT_UI_STIMME` | `de_DE-thorsten-high` | Piper-Stimme |
| `COCKPIT_UI_STIMMEN` | `~/.local/share/cockpit-ui/stimmen` | Ordner der Stimmen |
| `COCKPIT_UI_KONFIG` | `~/.config/cockpit-ui/config.toml` | Konfiguration je Rechner: Person, Namen, Module |
| `COCKPIT_UI_AGENT` | `claude` | `attrappe`: skriptgesteuerter Agent für Tests, ohne Claude und ohne Kosten |
| `COCKPIT_UI_SCHNELLBEFEHLE` | `1` | `0` schaltet die Schnellbefehle ab (alles geht an Claude) |
| `COCKPIT_UI_VORLESER` | ElevenLabs, falls Key da | `piper` erzwingt die lokale Stimme |

## Aufbau

- `src/cockpit_ui/server.py`: FastAPI, lädt die Module, REST für das Aufgabenmodul, WebSocket `/ws` für das Gespräch. Host- und Origin-Prüfung, nur 127.0.0.1.
- `src/cockpit_ui/agent.py`: Claude Code über das Agent SDK als **dauerhafte Sitzung** im Cockpit-Ordner. Hooks, Skills, MCP und Regeln gelten wie im Terminal, die Gespräche landen über die Hooks in `conversations/`.
- `src/cockpit_ui/sprache.py`: Erkennung, Vorlesen, Satzpuffer (vorgelesen wird Satz für Satz, während Claude noch schreibt).
- `src/cockpit_ui/konfig.py`: Konfiguration je Rechner (`env:`/`keychain:`-Verweise).
- `src/cockpit_ui/module/`: Modul-Lader und Schnittstellen (`__init__.py`), eingebaut `taskwarrior.py` (lokales `task`), `beispiel.py` (erfundene Aufgaben im Speicher), `mcp.py` (MCP-Server ohne Code). Eigene Module aus `module_pfade`. Module können Karten mit Hinweisen (`anzeige`) gestalten und einen Browser-Teil (`web/modul.js`: eigene Kartenarten und Erledigt-Effekte, Schnittstelle in `web/szene/erweiterungen.js`) mitbringen; Beispiel `beispiele/module/zettel/`.
- `src/cockpit_ui/szene.py`: Szenenzustand und Aktionen (Liste, wählen, Fokus, ausblenden, erledigt, Text, Optionen, Stil). Jede Aktion geht als Ereignis `szene` mit `seq` (und `zug`, wenn sie aus einem Zug kommt) ins Protokoll; der Schnappschuss beim Verbinden enthält `szene`, deshalb übersteht die Szene ein Neuladen. Die Kartendaten holt der Server direkt aus dem Aufgabenmodul.
- `src/cockpit_ui/agent.py`: dazu der In-Process-MCP-Server `szene` (Werkzeuge `zeige_liste`, `waehle`, `fokus`, `ausblenden`, `erledigt`, `zeige_text`, `zeige_optionen`, `stil`) und die Systemanweisung (`sprechstil`: Kern, Aufgaben-Teil nur mit Aufgabenmodul, Bausteine der Module, Anrede aus der Konfiguration).
- `src/cockpit_ui/schnellbefehl.py`: lokale Erkennung kurzer Standardsätze; `src/cockpit_ui/attrappe.py`: Attrappen-Agent.
- `web/szene.html` (HarnoRb), `web/szene-vorschau.html` (Vorschau), `web/szene/`: `buehne.js` (Renderer, Bloom, Hyperraum-Unschärfe, Comic-Tuschelinien, Qualitätsstufen mit Hysterese: Absenken nach 5 s unter 45 fps, Anheben nach 10 s stabil, Messpause bei Mikrofonstart, Zustandswechseln, Kartenwechseln und Effekten; `__harnoIntern.buehne.stufenLog` zeigt Wechsel; `__harnoIntern` gibt es nur in der Vorschau oder mit `/?diag`), `kugel.js` (HarnoRb-Shader: Dünnschicht-Interferenz über 16 Wellenlängen mit CIE-Farbabgleich, Filmdicke als glatter zweifacher Domain-Warp mit Schwerkraftgefälle, nur teilweiser Grauabzug für physikalisch nahe Farben, Fresnel, Studio-Spiegelung, zweite Farbschicht der Blasenrückseite, Energieadern in reinen Bandfarben beim Aufladen, Spiralgalaxie als Kern mit Herz, Armen, Sternknoten und Staubbahnen, runder weicher Halo ohne Strahlen, Partikel, Lichtbänder beim Denken; Sprechpegel als ruhige radiale Pulsation, der Kern atmet mit der Stimme; Comic mit Zellschattierung, Halbton nur im Schatten, Speedlines nur beim Zuhören und Sprechen), `hintergrund.js` (Nebel, Sternenfeld in drei Ebenen, Mond mit Lichtnetz nur auf der Nachtseite, Kugelraumer), `karten.js` (CSS3D-Karten mit festem Spaltenabstand zur Kugel, oben bündig; ruhende Fokuskarte ohne 3D-Transformation auf ganzen Pixeln, Fokus, Tafel, Optionen, Erledigt-Flug), `effekte.js` (Lichtstreifen, Portal, Strahl, Effekttöne), `zustand.js` (Zustandsautomat), `gespraech.js` (WebSocket, Vorlesen mit Pegel, Aufnahme), `main.js`.
- `web/index.html`, `web/app.js`: klassische Oberfläche (`/klassisch`).
- `web/logo/`: Logo in allen Größen (16 bis 2048 px), Favicon, App-Icon und Hintergrundbilder bis 4K.
- `web/vendor/three-0.170.0/`: three.js **0.170.0** (MIT, `LICENSE` daneben), lokal per Importmap; nur `build/three.module.min.js` und die benötigten Addons (EffectComposer, RenderPass, UnrealBloomPass, ShaderPass, OutputPass, CSS3DRenderer samt Shadern). Keine CDN-Ladung; die CSP bleibt bei `'self'` plus dem sha256 der Importmap, den der Server beim Start berechnet.

## Testen (ohne echte Aufgaben, ohne Claude-Kosten)

```
printf '[module.beispiel]\n' > /tmp/beispiel.toml                  # erfundene Aufgaben im Speicher
HF_HUB_OFFLINE=1 COCKPIT_UI_KONFIG=/tmp/beispiel.toml COCKPIT_UI_PORT=8461 \
  COCKPIT_UI_AGENT=attrappe COCKPIT_UI_VORLESER=piper COCKPIT_DIR=/tmp/cockpit-test uv run harnorb &
uv run python tools/sprachtest.py --port 8461 "Zeig mir die Todos." "Die zweite." "Erledigt."   # Piper → webm → WebSocket
uv run --with pytest --with httpx pytest -q
```

`HF_HUB_OFFLINE=1` verhindert, dass faster-whisper beim Laden im Netz nachfragt (in abgeschotteten Umgebungen hängt das sonst). Testinstanzen nie auf Port 8450 starten.

## Messwerte (MacBook mit Apple Silicon)

- Erkennung large-v3-turbo auf MPS: ca. 1,5 bis 2,3 s für 4 bis 6 s Sprache. Mit den Eigennamen aus den Modulen (Projekte, `namen` in der Konfiguration) werden Firmen- und Personennamen deutlich besser erkannt; `small` scheitert daran oft.
- Piper thorsten-high: ein Satz in ca. 0,3 s.
- Claude Code: erste Antwort ca. 7 bis 8 s, abhängig von Werkzeugen und MCP-Servern im Cockpit-Ordner. Die Kosten je Runde hängen vom Kontext des Ordners ab.

## Lizenz

MIT, siehe [LICENSE](LICENSE). Die Bibliotheken unter `web/vendor/` (three.js 0.170.0, marked 12.0.2, DOMPurify 3.1.6, Mermaid 11.4.1, Chart.js 4.4.7) stehen unter ihren eigenen Lizenzen, jeweils als `LICENSE` daneben.

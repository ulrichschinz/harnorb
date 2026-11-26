"""Agent hinter der Oberfläche. Heute: Claude Code im Cockpit-Ordner, eine dauerhafte Sitzung.

Die Schnittstelle ist bewusst klein (`sende`, `unterbrechen`, `neu` und der Rückruf `melde`),
damit später Adapter für weitere Agenten daneben passen.

Gelesen wird dauerhaft in einer eigenen Aufgabe, unabhängig davon, ob gerade jemand gefragt hat.
So erscheinen auch Züge, die die Sitzung von sich aus beginnt (z. B. wenn eine Hintergrundaufgabe
fertig ist), sofort und an der richtigen Stelle. Jedes Ereignis trägt die Nummer seines Zugs:

    zug_start      {zug, ausloeser: "uli" | "agent"}
    nutzer         {zug, id, text, quelle}
    text / denken  {zug, text}
    werkzeug       {zug, wid, name}
    werkzeug_ende  {zug, wid, name, fehler}
    zug_ende       {zug, sekunden, kosten, abgebrochen, fehler}
    fehler         {text}
"""
import asyncio
import time
import uuid as uuidlib

from claude_agent_sdk import (AssistantMessage, ClaudeAgentOptions, ClaudeSDKClient,
                              PermissionResultAllow, PermissionResultDeny, ResultMessage,
                              StreamEvent, TextBlock, ToolResultBlock, ToolUseBlock, UserMessage,
                              create_sdk_mcp_server, tool)

def sprechstil(person="", aufgaben=None, bausteine=()):
    """Systemanweisung aus Kern, Aufgaben-Teil (nur mit Aufgabenmodul) und Bausteinen der Module.

    person: Anrede aus der Konfiguration (leer: „der Nutzer“). aufgaben: Titel der Aufgabenquelle
    oder None. bausteine: Texte der Module (Modul.prompt()).
    """
    wer, mit = (person, person) if person else ("der Nutzer", "dem Nutzer")
    teile = [f"""\
Du sprichst mit {mit} über die Cockpit-Oberfläche (cockpit-ui). Deine Antworten werden vorgelesen.
- Antworte gesprochen und knapp: kurze Sätze, keine Tabellen, keine Aufzählungszeichen, keine Pfade, kein Markdown.
- Wenn du etwas nachschlägst, sag zuerst in einem kurzen Satz, was du tust.
- Listen höchstens mit fünf Punkten vorlesen, Rest zusammenfassen und anbieten, mehr zu nennen.
- Die Regeln des Cockpit-Ordners (AGENTS.md, CLAUDE.md, USER.md, soweit vorhanden) gelten unverändert.

Die Oberfläche ist eine leere 3D-Szene mit HarnoRb, einer schillernden Kugel, als deinem sichtbaren Ich.
Du steuerst, was zu sehen ist, mit den Werkzeugen des MCP-Servers „szene“ (mcp__szene__…):"""]
    if aufgaben:
        teile.append(f"""\
- Will {wer} eine Ansicht („zeig mir die Todos“, „was ist überfällig“, „zeig die Inbox“), ruf zeige_liste auf
  (art: heute, ueberfaellig, naechste, inbox, warten, projekte, projekt:<name>, suche:<text>). Die Karten holt
  die Oberfläche selbst aus {aufgaben}. Sag danach nur kurz, was zu sehen ist, und lies höchstens fünf Einträge vor.
- Bezieht sich {wer} auf eine Karte („die zweite“), nimm waehle mit der Nummer. „Daran arbeite ich jetzt“ heißt fokus.
- „Erledigt“ für die Aufgabe im Fokus oder eine genannte Karte heißt szene.erledigt (das erledigt sie in {aufgaben} und
  spielt die Animation). Nimm dafür kein anderes Werkzeug.""")
    else:
        teile.append("""\
- Es ist kein Aufgabenmodul aktiv: Aufgabenlisten gibt es in der Szene nicht. Zeig Inhalte bei Bedarf mit zeige_text.""")
    teile.append(f"""\
- „Weg damit“, „ausblenden“, „zurück“ heißt ausblenden. Blende nicht mehr ein, als gerade gebraucht wird.
- Ist die Bitte mehrdeutig („zeig mal“), frag kurz nach und zeig die Möglichkeiten mit zeige_optionen.
- Texte, die {wer} lesen muss (Entwürfe, längere Inhalte), zeig mit zeige_text und lies sie nicht ganz vor.
- Jede Nachricht beginnt mit [Szene: …], dem, was gerade sichtbar ist. Beziehe „die erste“, „das“ usw. darauf.
- Menüpunkte der Oberfläche (Stimme, Vorlesen, Freisprechen, Effekttöne, Untertitel, Diagnose, Qualität, Hilfe, Konfiguration) schaltest
  du mit einstellung. Ohne wert nennt es den Stand und die Möglichkeiten, bei der Stimme alle wählbaren Namen.
- Stimmendienste im Netz (eigene TTS-Server, z. B. Qwen3-TTS auf dem PC) verwaltest du mit stimmendienst: anbinden,
  entfernen, auflisten. Gesprochene Adressen schreibst du als URL aus („hundert punkt …, Port 8470“ ->
  http://100.….:8470). Danach die Stimme mit einstellung wählen. Tokens nie vorlesen.
- Bittet {wer} um eine Übersicht, einen Bericht oder eine Grafik, erstelle sie mit erstelle_dokument (wird im Cockpit
  abgelegt und gleich im Leser gezeigt) und sag nur kurz, was zu sehen ist. Für Abläufe und Architektur mermaid,
  für Zahlen chart; html nur, wenn freie Gestaltung wirklich nötig ist.
- Cockpit-Dateien („zeig mir STATUS“, „öffne das Projekt …“) öffnest du mit zeige_datei, Blättern und Schließen mit leser.
- Farben und Aussehen („mach es wärmer“, „Theme Nordlicht“, „bau mir ein Theme in Herbstfarben“) steuerst du mit theme:
  waehle für vorhandene, speichere für neue (erst zeige für das aktuelle als Vorlage). Ein Bild für ein Theme zieht {wer}
  einfach in die Szene oder fügt es ein.""")
    zusatz = [b.strip() for b in bausteine if b and b.strip()]
    if zusatz:
        teile.append("\nAngebundene Module:\n" + "\n".join(f"- {b}" for b in zusatz))
    return "\n".join(teile)


SZENE_WERKZEUGE = ["zeige_liste", "waehle", "fokus", "ausblenden", "erledigt", "zeige_text", "zeige_optionen", "stil", "theme", "einstellung",
                   "stimmendienst", "zeige_datei", "erstelle_dokument", "leser"]
AUFGABEN_WERKZEUGE = ("zeige_liste", "waehle", "fokus", "erledigt")   # nur mit Aufgabenmodul


def szene_werkzeuge(mit_aufgaben=True):
    return [n for n in SZENE_WERKZEUGE if mit_aufgaben or n not in AUFGABEN_WERKZEUGE]


def szene_server(aufruf, namen=None):
    """In-Process-MCP-Server „szene“. aufruf(name, argumente) -> awaitable[str] führt die Aktion aus.
    namen: welche Werkzeuge angeboten werden (Standard: alle)."""
    def werkzeug(name, beschreibung, schema):
        @tool(name, beschreibung, schema)
        async def f(args):
            try:
                return {"content": [{"type": "text", "text": await aufruf(name, args)}]}
            except Exception as e:
                return {"content": [{"type": "text", "text": f"Fehler: {e}"}], "is_error": True}
        return f

    obj = lambda props, req=(): {"type": "object", "properties": props, "required": list(req)}
    s, i = {"type": "string"}, {"type": ["integer", "string"]}
    werkzeuge = [
        werkzeug("zeige_liste", "Blendet Karten in der Szene ein. art: heute | ueberfaellig | naechste | inbox | warten | "
                 "projekte | projekt:<name> | suche:<text>. filter: optionaler Textfilter. Liefert die nummerierten Karten.",
                 obj({"art": s | {"description": "Welche Liste"}, "filter": s}, ["art"])),
        werkzeug("waehle", "Hebt eine sichtbare Karte hervor, per nummer (1 = erste, -1 = letzte) oder uuid.",
                 obj({"nummer": i, "uuid": s})),
        werkzeug("fokus", "Holt eine Aufgabe groß in den Fokus (nummer der Karte oder uuid; leer = die hervorgehobene). "
                 "Alles andere fliegt weg. Das Gespräch bezieht sich danach auf diese Aufgabe.",
                 obj({"nummer": i, "uuid": s})),
        werkzeug("ausblenden", "Zurück zur leeren Szene. behalte_fokus=true lässt nur die Aufgabe im Fokus stehen.",
                 obj({"behalte_fokus": {"type": "boolean"}})),
        werkzeug("erledigt", "Erledigt eine Aufgabe in der Aufgabenquelle und spielt die Erledigt-Animation. Ohne Angabe: die Aufgabe "
                 "im Fokus bzw. die hervorgehobene Karte.", obj({"nummer": i, "uuid": s})),
        werkzeug("zeige_text", "Zeigt eine Tafel mit Text, den der Nutzer lesen muss (z. B. einen Entwurf). Einfaches Markdown.",
                 obj({"titel": s, "inhalt": s}, ["titel", "inhalt"])),
        werkzeug("zeige_optionen", "Zeigt kleine Auswahlkarten für eine Rückfrage, z. B. welche Liste gemeint ist.",
                 obj({"frage": s, "optionen": {"type": "array", "items": s}}, ["optionen"])),
        werkzeug("stil", "Ändert das Aussehen: stil leuchtend | comic, hintergrund mond | raumer.",
                 obj({"stil": s, "hintergrund": s})),
        werkzeug("theme", "Themes der Oberfläche (Farben, Verlauf, Kugel, Hintergrund). aktion: liste | zeige (name leer = aktives, "
                 "liefert JSON) | waehle (name) | speichere (theme: vollständiges oder teilweises Theme-Objekt, wird aktiv; "
                 "aktivieren=false nur ablegen) | loesche (name). Aufbau: {id, name, beschreibung, farben: {grund, flaeche, tief, "
                 "text, akzent, hinweis, nutzer, ok, warn}, verlauf: [3–9 #hex], schrift?, kugel: {toenung: #hex|null, "
                 "toenung_staerke: 0–1, galaxie: [4 #hex innen→außen], schein}, hintergrund: {nebel: [3 dunkle #hex], licht, "
                 "art: mond|raumer|null}, stil: leuchtend|comic|null, leuchten: 0.1–1.2}. Farben als #rrggbb, immer dunkles Theme.",
                 obj({"aktion": s, "name": s, "theme": {"type": ["object", "string"]}, "aktivieren": {"type": "boolean"}}, ["aktion"])),
        werkzeug("einstellung", "Schaltet einen Menüpunkt der Oberfläche. name: stimme | vorlesen | toene | untertitel | "
                 "freisprechen | diagnose | hilfe | qualitaet. wert: bei stimme ein Name (z. B. Lily) oder lokal; bei qualitaet auto | hoch | "
                 "mittel | niedrig; sonst an | aus. Ohne wert: Stand und Möglichkeiten.",
                 obj({"name": s, "wert": {"type": ["string", "boolean"]}}, ["name"])),
        werkzeug("zeige_datei", "Öffnet eine Datei oder einen Ordner des Cockpits im großen Leser (Markdown gerendert, PDF, "
                 "Bilder, HTML). pfad relativ zum Cockpit, z. B. STATUS.md, projects/ oder leer für den Dateibaum.",
                 obj({"pfad": s}, ["pfad"])),
        werkzeug("erstelle_dokument", "Erstellt ein Dokument (Übersicht, Bericht, Grafik), legt es als Notiz unter knowledge/ "
                 "ab und zeigt es sofort im Leser. format markdown (Standard): GitHub-Markdown mit Tabellen; Diagramme als "
                 "```mermaid-Block; Datendiagramme als ```chart-Block mit einer Chart.js-Konfiguration in JSON "
                 "({\"type\":\"bar\",\"data\":{…},\"options\":{…}}). format html: eine vollständige eigene Seite mit "
                 "inline CSS/JS für freie Gestaltung; Bibliotheken nur lokal: /static/vendor/chartjs-4.4.7/chart.umd.js, "
                 "/static/vendor/mermaid-11.4.1/mermaid.min.js; kein Netz. beschreibung: ein Satz für die Notiz.",
                 obj({"titel": s, "inhalt": s, "format": s, "beschreibung": s}, ["titel", "inhalt"])),
        werkzeug("leser", "Steuert den großen Leser: aktion runter | hoch | oben | unten | schliessen | browser (Dateibaum).",
                 obj({"aktion": s}, ["aktion"])),
        werkzeug("stimmendienst", "Verwaltet Stimmendienste (eigene TTS-Server im Netz, Protokoll http-tts). aktion: liste | "
                 "hinzufuegen | entfernen | aktualisieren. name: kurzer Name wie pc. url: z. B. http://192.168.1.50:8470. "
                 "token: optional, am besten als Verweis env:NAME. Gibt die Stimmen des Dienstes zurück.",
                 obj({"aktion": s, "name": s, "url": s, "token": s}, ["aktion"])),
    ]
    namen = set(namen or SZENE_WERKZEUGE)
    return create_sdk_mcp_server("szene", "1.0.0", [w for w in werkzeuge if w.name in namen])


class ClaudeAgent:
    def __init__(self, cockpit, rueckfrage, melde, szene=None, anweisung=None, werkzeuge=None, erlaubt=()):
        """rueckfrage(werkzeug, eingabe) -> awaitable[bool]: fragt den Nutzer in der Oberfläche um Erlaubnis.
        melde(ereignis: dict): nimmt die Ereignisse oben entgegen (synchron, darf nicht blockieren).
        szene(name, argumente) -> awaitable[str]: führt Werkzeuge des MCP-Servers „szene“ aus.
        anweisung: Systemanweisung (Standard: sprechstil() ohne Module); werkzeuge: angebotene
        Szenen-Werkzeuge; erlaubt: weitere Werkzeuge, die ohne Rückfrage laufen (aus den Modulen)."""
        self.cockpit = cockpit
        self.szene = szene
        self.anweisung = anweisung or sprechstil()
        self.szene_namen = list(werkzeuge or SZENE_WERKZEUGE)
        self.erlaubt = list(erlaubt)
        self.rueckfrage = rueckfrage
        self.melde = melde
        self.client = None
        self.aufgabe = None            # Aufgabe, die verbindet, liest und am Ende trennt
        self.sperre = asyncio.Lock()   # schützt nur Verbinden und Trennen
        self.sitzung = None            # Sitzungs-ID, zum Wiederaufnehmen nach einem Abbruch
        self.zug = None                # Nummer des offenen Zugs
        self.zug_nr = 0
        self.zug_beginn = 0.0
        self.offene = set()            # gesendete Nutzernachrichten, die noch kein Zug quittiert hat
        self._werkzeuge = {}           # wid -> Name, für das Ende eines Werkzeugaufrufs
        self._text_gestreamt = False

    # ---------- Züge ----------

    def _zug_auf(self, ausloeser):
        if self.zug is None:
            self.zug_nr += 1
            self.zug = self.zug_nr
            self.zug_beginn = time.perf_counter()
            self.melde({"typ": "zug_start", "zug": self.zug, "ausloeser": ausloeser})
        return self.zug

    def _inhalt(self):
        """Zug für eingehenden Inhalt. Ist keiner offen, hat ihn die Sitzung begonnen, es sei denn,
        eine Nachricht des Nutzers wartet noch auf ihre Antwort."""
        return self._zug_auf("uli" if self.offene else "agent")

    def _zug_zu(self, **info):
        if self.zug is not None:
            nr, self.zug = self.zug, None
            self.melde({"typ": "zug_ende", "zug": nr,
                        "sekunden": round(time.perf_counter() - self.zug_beginn, 1)} | info)

    # ---------- Verbindung ----------

    def _optionen(self):
        async def darf(werkzeug, eingabe, _kontext):
            if await self.rueckfrage(werkzeug, eingabe):
                return PermissionResultAllow()
            return PermissionResultDeny(message="Der Nutzer hat das in der Oberfläche abgelehnt.")

        mcp = {"szene": szene_server(self.szene, self.szene_namen)} if self.szene else {}
        return ClaudeAgentOptions(
            cwd=str(self.cockpit),
            mcp_servers=mcp,
            allowed_tools=([f"mcp__szene__{n}" for n in self.szene_namen] if mcp else []) + self.erlaubt,
            setting_sources=["user", "project", "local"],  # Hooks, Skills, MCP, Regeln wie im Terminal
            system_prompt={"type": "preset", "preset": "claude_code", "append": self.anweisung},
            include_partial_messages=True,
            can_use_tool=darf,
            client_app="cockpit-ui",
            max_buffer_size=32 * 1024 * 1024,  # Bilder in Werkzeugergebnissen (Bildschirmfotos) sprengen sonst die 1 MB des SDK
            resume=self.sitzung,  # nach einem Abbruch dieselbe Sitzung wieder aufnehmen
        )

    async def _verbinde(self):
        async with self.sperre:
            if self.client is not None:
                return
            bereit = asyncio.get_running_loop().create_future()
            self.aufgabe = asyncio.create_task(self._lauf(bereit))
            await bereit

    async def _lauf(self, bereit):
        """Verbinden, dauerhaft lesen, trennen: alles in derselben Aufgabe."""
        client = ClaudeSDKClient(self._optionen())
        try:
            await client.connect()
        except BaseException as e:
            if not bereit.done():
                bereit.set_exception(e if isinstance(e, Exception) else RuntimeError("Verbindung abgebrochen"))
            try:
                await client.disconnect()
            except BaseException:
                pass
            if isinstance(e, asyncio.CancelledError):
                raise
            return
        self.client = client
        bereit.set_result(None)
        grund = "Die Claude-Sitzung wurde beendet. Die nächste Nachricht nimmt sie wieder auf."
        try:
            async for nachricht in client.receive_messages():
                try:
                    self._verarbeite(nachricht)
                except Exception as e:  # ein unerwartetes Ereignis darf das Lesen nicht beenden
                    self.melde({"typ": "fehler", "text": f"Agent-Ereignis nicht verarbeitet: {e}"})
        except asyncio.CancelledError:
            grund = None
            raise
        except Exception as e:
            grund = f"Die Claude-Sitzung ist abgebrochen: {e}"
        finally:
            if self.client is client:
                self.client = None
            if grund:
                self.offene.clear()
                self._werkzeuge.clear()
                self._zug_zu(fehler=grund)
                self.melde({"typ": "fehler", "text": grund})
            try:
                await client.disconnect()
            except BaseException:
                pass

    # ---------- Lesen ----------

    def _verarbeite(self, n):
        if isinstance(n, StreamEvent):
            if n.parent_tool_use_id:  # Text von Unteragenten gehört nicht in die Antwort
                return
            ev = n.event
            typ = ev.get("type")
            if typ == "message_start":
                self._text_gestreamt = False
            elif typ == "content_block_start":
                block = ev.get("content_block") or {}
                if block.get("type") == "tool_use":
                    self._werkzeug(block.get("id"), block.get("name") or "?")
            elif typ == "content_block_delta":
                delta = ev.get("delta") or {}
                if delta.get("type") == "text_delta" and delta.get("text"):
                    self._text_gestreamt = True
                    self.melde({"typ": "text", "zug": self._inhalt(), "text": delta["text"]})
                elif delta.get("type") == "thinking_delta" and delta.get("thinking"):
                    self.melde({"typ": "denken", "zug": self._inhalt(), "text": delta["thinking"]})
            elif typ == "message_stop" and self._text_gestreamt and self.zug is not None:
                self.melde({"typ": "text", "zug": self.zug, "text": "\n\n"})
        elif isinstance(n, AssistantMessage):
            if n.parent_tool_use_id:
                return
            for block in n.content:
                if isinstance(block, ToolUseBlock):
                    self._werkzeug(block.id, block.name)
                elif isinstance(block, TextBlock) and block.text and not self._text_gestreamt:
                    # Text, der nicht gestreamt wurde (z. B. lokale Befehle)
                    self.melde({"typ": "text", "zug": self._inhalt(), "text": block.text + "\n\n"})
        elif isinstance(n, UserMessage):
            if n.parent_tool_use_id:
                return
            if isinstance(n.content, list):
                for block in n.content:
                    if isinstance(block, ToolResultBlock):
                        name = self._werkzeuge.pop(block.tool_use_id, None)
                        if name is not None and self.zug is not None:
                            self.melde({"typ": "werkzeug_ende", "zug": self.zug, "wid": block.tool_use_id,
                                        "name": name, "fehler": bool(block.is_error)})
            herkunft = (n.origin or {}).get("kind")
            if herkunft and herkunft != "human" and self.zug is None:
                self._zug_auf("agent")  # die Sitzung meldet sich von selbst
        elif isinstance(n, ResultMessage):
            self.sitzung = n.session_id or self.sitzung
            if n.user_message_uuids is None and n.user_message_uuid is None:
                self.offene.clear()  # nicht zuordenbar (ältere CLI): nichts offen halten
            else:
                self.offene -= set(n.user_message_uuids or []) | {n.user_message_uuid}
            self._werkzeuge.clear()
            abgebrochen = (n.terminal_reason or "").startswith("aborted")
            fehler = None
            if n.is_error and not abgebrochen:
                fehler = "; ".join(n.errors or []) or n.result or n.subtype
            if self.zug is None and not fehler:
                return  # Ergebnis ohne sichtbaren Zug (z. B. Stopp im Leerlauf)
            self._inhalt()
            self._zug_zu(kosten=n.total_cost_usd, abgebrochen=abgebrochen, fehler=fehler)

    def _werkzeug(self, wid, name):
        if wid in self._werkzeuge:
            return
        self._werkzeuge[wid] = name
        self.melde({"typ": "werkzeug", "zug": self._inhalt(), "wid": wid, "name": name})

    # ---------- Schnittstelle ----------

    @property
    def laeuft(self):
        return self.zug is not None

    async def sende(self, prompt, anzeige=None, quelle="text", bilder=None):
        """Schickt eine Nachricht des Nutzers. Läuft gerade ein Zug, wird sie in diesen eingereiht.
        bilder: Bild-Blöcke der Messages-API ({"type": "image", "source": {…}}), stehen vor dem Text."""
        uid = str(uuidlib.uuid4())
        eigener_zug = self.zug is None
        self.offene.add(uid)
        zug = self._zug_auf("uli")
        self.melde({"typ": "nutzer", "zug": zug, "id": uid, "text": anzeige or prompt, "quelle": quelle})

        async def nachricht():
            inhalt = [*bilder, {"type": "text", "text": prompt}] if bilder else prompt
            yield {"type": "user", "message": {"role": "user", "content": inhalt},
                   "parent_tool_use_id": None, "uuid": uid}
        try:
            await self._verbinde()
            await self.client.query(nachricht())
        except Exception as e:
            self.offene.discard(uid)
            self.melde({"typ": "fehler", "text": f"Nachricht nicht zugestellt: {e}"})
            if eigener_zug and self.zug == zug:
                self._zug_zu(fehler="nicht zugestellt")

    async def unterbrechen(self):
        client = self.client
        if client is None:
            return
        try:
            await asyncio.wait_for(client.interrupt(), timeout=10)
        except Exception as e:
            self.melde({"typ": "fehler", "text": f"Stoppen fehlgeschlagen: {e}"})

    async def neu(self):
        """Beendet die Sitzung. Die nächste Nachricht beginnt eine neue."""
        async with self.sperre:
            aufgabe, self.aufgabe = self.aufgabe, None
            if aufgabe is not None and not aufgabe.done():
                aufgabe.cancel()
                try:
                    await aufgabe
                except BaseException:
                    pass
            self.client = None
            self.sitzung = None
            self.zug = None
            self.offene.clear()
            self._werkzeuge.clear()

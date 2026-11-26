"""Beispielmodul zettel: zeigt, wie ein Modul eigene Karten und einen eigenen Erledigt-Effekt mitbringt.

Es nimmt die erfundenen Aufgaben des Moduls beispiel und markiert die Inbox-Einträge als Zettel.
Der Browser-Teil liegt in `web/modul.js` daneben und wird vom Kern selbst gefunden.

    module_pfade = ["~/projects/agentic-reach/cockpit-ui/beispiele/module"]   # bzw. der eigene Pfad
    [module.zettel]
"""
from cockpit_ui.module import Modul
from cockpit_ui.module.beispiel import Speicher


class ZettelSpeicher(Speicher):
    """Wie beispiel, nur tragen Einträge ohne Projekt und Tags die Kartenart `zettel`."""

    def _mit_anzeige(self, t):
        if isinstance(t, dict) and not t.get("project") and not t.get("tags"):
            t = t | {"anzeige": {"art": "zettel", "effekt": "zerknuellen",
                                 "daten": {"farbe": ["#fff3a8", "#ffd6e8", "#d4f5ff"][len(t["description"]) % 3]}}}
        return t

    def inbox(self):
        return [self._mit_anzeige(t) for t in super().inbox()]

    def aufgaben(self, q=None, due_before=None, project=None):
        return [self._mit_anzeige(t) for t in super().aufgaben(q, due_before, project)]

    def aufgabe(self, uuid):
        return self._mit_anzeige(super().aufgabe(uuid))


def erstelle(name, konfig, kern):
    return Modul(name, konfig, kern, titel=konfig.get("titel", "Zettel (Beispiel)"), aufgaben=ZettelSpeicher())

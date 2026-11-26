"""Modul mcp: bindet einen MCP-Server an, ohne eigenen Code.

Den Server selbst lädt der Agent aus seiner Konfiguration (Claude Code: `.mcp.json`, Nutzer- oder
Projekteinstellungen). Das Modul sagt der Oberfläche nur, dass es ihn gibt, und gibt dem Agenten
einen Hinweis, wofür er da ist:

    [module.ontology]
    typ = "mcp"
    server = "ontology"                   # Name des MCP-Servers (Standard: der Modulname)
    titel = "Ontology"
    prompt = "Für Firmenwissen …"          # optional
    erlaubt = ["mcp__ontology__ask"]      # optional: diese Werkzeuge ohne Rückfrage
    namen = ["Musterfirma"]               # optional: Eigennamen für die Spracherkennung
"""
from . import Modul


class McpModul(Modul):
    def bereit(self):
        return True, f"MCP-Server {self.konfig.get('server') or self.name} (über die Agent-Konfiguration)"

    def prompt(self):
        if self.konfig.get("prompt"):
            return str(self.konfig["prompt"])
        server = self.konfig.get("server") or self.name
        return f"Der MCP-Server „{server}“ ({self.titel}) ist angebunden; nutze ihn, wenn er zur Frage passt."

    def namen(self):
        return [str(n) for n in self.konfig.get("namen") or []]


def erstelle(name, konfig, kern):
    return McpModul(name, konfig, kern, titel=konfig.get("titel", name),
                    aendert_bei=(f"mcp__{konfig.get('server') or name}__",) if konfig.get("aendert_aufgaben") else ())

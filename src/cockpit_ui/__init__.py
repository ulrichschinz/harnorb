"""cockpit-ui: lokale Oberfläche für ein persönliches Cockpit mit Sprache."""


def main():
    import argparse
    import webbrowser

    import uvicorn

    from .einstellungen import Einstellungen

    ap = argparse.ArgumentParser(prog="cockpit-ui")
    ap.add_argument("--oeffnen", action="store_true", help="Browser öffnen")
    a = ap.parse_args()
    port = Einstellungen().port
    if a.oeffnen:
        webbrowser.open(f"http://127.0.0.1:{port}/")
    uvicorn.run("cockpit_ui.server:app", host="127.0.0.1", port=port, log_level="warning")

"""Leser: nur Cockpit, nichts Verstecktes, Dokumente landen als Notiz in knowledge/."""
import datetime as dt

import pytest

from cockpit_ui import dateien as d


@pytest.fixture
def cockpit(tmp_path):
    (tmp_path / "STATUS.md").write_text("---\ntype: status\n---\n# Lage\n")
    (tmp_path / "projects").mkdir()
    (tmp_path / "projects" / "a.md").write_text("# A")
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "config").write_text("x")
    (tmp_path / ".env").write_text("KEY=geheim")
    (tmp_path / "api-token.txt").write_text("geheim")
    (tmp_path.parent / "draussen.md").write_text("nein")
    (tmp_path / "link.md").symlink_to(tmp_path.parent / "draussen.md")
    return tmp_path


def test_lesen(cockpit):
    assert d.lies(cockpit, "STATUS.md")["art"] == "md"
    assert "# Lage" in d.lies(cockpit, "/STATUS.md")["inhalt"]
    wurzel = d.lies(cockpit, "")
    namen = [e["name"] for e in wurzel["eintraege"]]
    assert namen[0] == "projects" and "STATUS.md" in namen
    assert ".git" not in namen and ".env" not in namen and "api-token.txt" not in namen


@pytest.mark.parametrize("pfad", ["../draussen.md", ".env", ".git/config", "api-token.txt", "link.md", "gibtsnicht.md"])
def test_gesperrt(cockpit, pfad):
    with pytest.raises(d.DateiFehler):
        d.lies(cockpit, pfad)


def test_suche(cockpit):
    assert [t["pfad"] for t in d.suche(cockpit, "projects a")] == ["projects/a.md"]
    assert d.suche(cockpit, "geheim token") == []


def test_erstellen(cockpit):
    tag = dt.date(2026, 11, 26)
    p = d.erstelle(cockpit, "Systemübersicht HarnoRb", "## Teile\n\n```mermaid\ngraph LR; A-->B\n```", heute=tag)
    assert p == "knowledge/2026-11-26-systemuebersicht-harnorb.md"
    text = (cockpit / p).read_text()
    assert text.startswith("---\ntype: note\n") and "# Systemübersicht HarnoRb" in text and "tags: [harno]" in text
    p2 = d.erstelle(cockpit, "Systemübersicht HarnoRb", "<html><body>Hi</body></html>", format="html", heute=tag)
    assert p2 == "knowledge/2026-11-26-systemuebersicht-harnorb-2.html"
    assert "(2026-11-26-systemuebersicht-harnorb-2.html)" in (cockpit / "knowledge/2026-11-26-systemuebersicht-harnorb-2.md").read_text()
    with pytest.raises(d.DateiFehler):
        d.erstelle(cockpit, "", "x")


def test_ablegen(cockpit):
    tag = dt.date(2026, 11, 26)
    a = d.ablegen(cockpit, "Umsatz Q3.xlsx", b"PK\x03\x04daten", heute=tag)
    assert a["pfad"] == "inbox/2026-11-26-umsatz-q3.xlsx" and a["karte"] == "inbox/2026-11-26-umsatz-q3.md"
    karte = (cockpit / a["karte"]).read_text()
    assert "type: brief" in karte and "status: open" in karte and "(2026-11-26-umsatz-q3.xlsx)" in karte
    b = d.ablegen(cockpit, "umsatz q3.xlsx", b"x", heute=tag)          # nie überschreiben
    assert b["pfad"] == "inbox/2026-11-26-umsatz-q3-2.xlsx"
    m = d.ablegen(cockpit, "notiz.md", "# Hallo\n".encode(), heute=tag)
    assert m["karte"] is None and (cockpit / m["pfad"]).read_text().startswith("---\ntype: brief")
    fm = "---\ntype: note\ntitle: x\n---\n# X\n"
    assert (cockpit / d.ablegen(cockpit, "fertig.md", fm.encode(), heute=tag)["pfad"]).read_text() == fm
    assert d.ablegen(cockpit, "../../boese.pdf", b"%PDF", heute=tag)["pfad"] == "inbox/2026-11-26-boese.pdf"
    for name, daten in ((".env", b"x"), ("leer.pdf", b""), ("gross.bin", b"x" * (d.MAX_UPLOAD + 1))):
        with pytest.raises(d.DateiFehler):
            d.ablegen(cockpit, name, daten, heute=tag)
    with pytest.raises(d.DateiFehler):
        d.ablegen(cockpit, "a.pdf", b"x", ordner="../draussen", heute=tag)


def test_upload_rest(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from cockpit_ui import server as srv
    monkeypatch.setattr(srv, "COCKPIT", tmp_path)
    monkeypatch.setattr(srv, "HOCHGELADEN", [])
    with TestClient(srv.app, base_url="http://127.0.0.1:8499") as c:
        r = c.post("/api/upload", files=[("datei", ("Bericht.pdf", b"%PDF-1.4", "application/pdf")),
                                         ("datei", (".env", b"x", "text/plain"))])
        assert r.status_code == 200, r.text
        j = r.json()
        assert [a["name"] for a in j["abgelegt"]] == ["Bericht.pdf"] and len(j["fehler"]) == 1
        assert (tmp_path / j["abgelegt"][0]["pfad"]).read_bytes() == b"%PDF-1.4"
        assert srv.HOCHGELADEN[0]["pfad"].startswith("inbox/") and srv.HOCHGELADEN[0]["pfad"].endswith("-bericht.pdf")
        assert c.post("/api/upload", files=[("datei", ("leer.pdf", b"", "application/pdf"))]).status_code == 400

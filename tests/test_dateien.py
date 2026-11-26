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

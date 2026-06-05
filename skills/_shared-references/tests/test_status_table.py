"""Tests de la table de statut `_status.md` (parse / render / upsert / dédup)."""

from pathlib import Path

import status_table as st


_SAMPLE = """# Statut — pdfs

| Fichier | SHA256 | Statut | Articles wiki | Grille | MAJ |
| --- | --- | --- | --- | --- | --- |
| navigation-cotiere.pdf.txt | a1b2c3 | compilé | [[navigation/relevement]] | [[reading-grids/nav]] | 2026-06-04 |
| traite.pdf.txt | 9f8e7d | extrait | — | — | 2026-06-03 |
"""


def test_parse_basic():
    rows = st.parse_status(_SAMPLE)
    assert len(rows) == 2
    assert rows[0].fichier == "navigation-cotiere.pdf.txt"
    assert rows[0].sha256 == "a1b2c3"
    assert rows[0].statut == "compilé"
    assert rows[1].statut == "extrait"


def test_parse_absent_ou_vide():
    assert st.parse_status("") == []
    assert st.parse_status("# Statut — web\n\n(rien)\n") == []


def test_render_parse_roundtrip():
    rows = st.parse_status(_SAMPLE)
    rendered = st.render_status("pdfs", rows)
    again = st.parse_status(rendered)
    assert [r.cells() for r in again] == [r.cells() for r in rows]
    assert rendered.startswith("# Statut — pdfs")


def test_upsert_remplace_par_fichier():
    rows = st.parse_status(_SAMPLE)
    st.upsert_row(rows, st.StatusRow(fichier="traite.pdf.txt", sha256="NEW", statut="compilé"))
    assert len(rows) == 2  # pas d'ajout
    traite = next(r for r in rows if r.fichier == "traite.pdf.txt")
    assert traite.sha256 == "NEW" and traite.statut == "compilé"


def test_upsert_ajoute_nouveau():
    rows = st.parse_status(_SAMPLE)
    st.upsert_row(rows, st.StatusRow(fichier="autre.pdf.txt", sha256="zzz"))
    assert len(rows) == 3
    assert rows[-1].fichier == "autre.pdf.txt"


def test_known_shas():
    rows = st.parse_status(_SAMPLE)
    assert st.known_shas(rows) == {"a1b2c3", "9f8e7d"}


def test_load_save(tmp_path: Path):
    root = tmp_path / "work"
    root.mkdir()
    path = root / "raw" / "pdfs" / "_status.md"
    assert st.load_status(path) == []  # absent -> []
    rows = [st.StatusRow(fichier="x.pdf.txt", sha256="abc", maj="2026-06-04")]
    st.save_status(path, "pdfs", rows, work_root=root)
    reloaded = st.load_status(path)
    assert len(reloaded) == 1 and reloaded[0].sha256 == "abc"

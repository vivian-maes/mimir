"""Tests des helpers d'E/S partagés (écriture atomique confinée, suffixage, hachage)."""

from pathlib import Path

import pytest

import iohelpers
from guard import ConfinementError


def test_sha256_text_stable():
    assert iohelpers.sha256_text("abc") == iohelpers.sha256_text("abc")
    assert iohelpers.sha256_text("abc") != iohelpers.sha256_text("abd")
    # valeur connue (sanity)
    assert iohelpers.sha256_text("") == (
        "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    )


def test_atomic_write_text_confine(tmp_path: Path):
    root = tmp_path / "work"
    root.mkdir()
    out = iohelpers.atomic_write_text(root / "raw" / "a.txt", "héllo", work_root=root)
    assert out.read_text(encoding="utf-8") == "héllo"
    # le dossier parent a été créé
    assert out.parent.is_dir()
    # aucun fichier temporaire résiduel
    assert not list(out.parent.glob(".tmp-*"))


def test_atomic_write_refuse_hors_root(tmp_path: Path):
    root = tmp_path / "work"
    root.mkdir()
    with pytest.raises(ConfinementError):
        iohelpers.atomic_write_text(root / ".." / "evasion.txt", "x", work_root=root)


def test_write_json_roundtrip(tmp_path: Path):
    root = tmp_path / "work"
    root.mkdir()
    obj = {"title": "Navigation côtière", "ocr": False, "chapters": [{"order": 1}]}
    out = iohelpers.write_json(root / "x.toc.json", obj, work_root=root)
    import json

    assert json.loads(out.read_text(encoding="utf-8")) == obj
    # accents conservés (ensure_ascii=False)
    assert "côtière" in out.read_text(encoding="utf-8")


def test_unique_suffixed_path_double_suffixe(tmp_path: Path):
    # cas porteur : 'nom.pdf.txt' existe -> on veut 'nom-2.pdf.txt', PAS 'nom.pdf-2.txt'
    (tmp_path / "nom.pdf.txt").write_text("x")
    got = iohelpers.unique_suffixed_path(tmp_path, "nom", "pdf.txt")
    assert got.name == "nom-2.pdf.txt"

    got.write_text("y")
    got3 = iohelpers.unique_suffixed_path(tmp_path, "nom", "pdf.txt")
    assert got3.name == "nom-3.pdf.txt"


def test_unique_suffixed_path_libre(tmp_path: Path):
    got = iohelpers.unique_suffixed_path(tmp_path, "libre", "md")
    assert got.name == "libre.md"


def test_unique_suffixed_base_coherent(tmp_path: Path):
    # un seul suffixe partagé entre toutes les extensions liées
    (tmp_path / "nom.pdf").write_text("bin")
    base = iohelpers.unique_suffixed_base(tmp_path, "nom", ["pdf", "pdf.txt", "toc.json"])
    assert base == "nom-2"

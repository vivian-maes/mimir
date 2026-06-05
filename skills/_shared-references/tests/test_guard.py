"""Tests de la garde de confinement (DoD Phase 0 : refuser une écriture hors work_root)."""

from pathlib import Path

import pytest

from guard import ConfinementError, assert_within, is_within, safe_path


def test_ecriture_dans_work_root_acceptee(tmp_path: Path):
    root = tmp_path / "work"
    root.mkdir()
    target = root / "raw" / "pdfs" / "a.pdf.txt"
    resolved = assert_within(root, target)
    assert is_within(root, target)
    assert str(resolved).startswith(str(root.resolve()))


def test_work_root_lui_meme_accepte(tmp_path: Path):
    root = tmp_path / "work"
    root.mkdir()
    assert is_within(root, root)


def test_ecriture_hors_root_via_parent_refusee(tmp_path: Path):
    """Le DoD : une écriture hors work_root est refusée (cas `../`)."""
    root = tmp_path / "work"
    root.mkdir()
    evasion = root / ".." / "secret.md"
    assert not is_within(root, evasion)
    with pytest.raises(ConfinementError):
        assert_within(root, evasion)


def test_ecriture_chemin_absolu_externe_refusee(tmp_path: Path):
    root = tmp_path / "work"
    root.mkdir()
    other = tmp_path / "autre" / "fichier.md"
    with pytest.raises(ConfinementError):
        assert_within(root, other)


def test_prefixe_voisin_non_confondu(tmp_path: Path):
    """`work` ne doit pas contenir `work-bis` malgré le préfixe commun."""
    root = tmp_path / "work"
    root.mkdir()
    sibling = tmp_path / "work-bis" / "x.md"
    assert not is_within(root, sibling)


def test_symlink_evasion_refuse(tmp_path: Path):
    """Un symlink interne pointant hors racine est refusé (realpath)."""
    root = tmp_path / "work"
    root.mkdir()
    outside = tmp_path / "dehors"
    outside.mkdir()
    link = root / "echappe"
    link.symlink_to(outside)
    with pytest.raises(ConfinementError):
        assert_within(root, link / "vol.md")


def test_safe_path_construit_chemin_confine(tmp_path: Path):
    root = tmp_path / "work"
    root.mkdir()
    p = safe_path(root, "wiki", "navigation", "relevement.md")
    assert p == (root.resolve() / "wiki" / "navigation" / "relevement.md")


def test_safe_path_remontee_refusee(tmp_path: Path):
    root = tmp_path / "work"
    root.mkdir()
    with pytest.raises(ConfinementError):
        safe_path(root, "..", "evasion.md")

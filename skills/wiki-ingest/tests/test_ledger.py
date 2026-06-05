"""Tests du ledger d'ingestion (idempotence, atomicité, robustesse à la corruption)."""

import json
from pathlib import Path

import pytest

import ledger as L
from guard import ConfinementError


@pytest.fixture
def work(tmp_path):
    w = tmp_path / "work"
    w.mkdir()
    return w


def _ledger_path(work):
    return work / ".wiki" / "ingest-ledger.json"


# --- needs_compile ---------------------------------------------------------
def test_needs_compile_absent_present_modifie():
    led = {"raw/pdfs/x.pdf.txt": L.LedgerEntry(sha256="aaa", articles=["nav/r"], updated="2026-06-04")}
    assert L.needs_compile(led, "raw/pdfs/y.pdf.txt", "zzz") is True   # absent
    assert L.needs_compile(led, "raw/pdfs/x.pdf.txt", "aaa") is False  # SHA identique
    assert L.needs_compile(led, "raw/pdfs/x.pdf.txt", "bbb") is True   # SHA différent


# --- save/load round-trip + atomicité --------------------------------------
def test_save_load_roundtrip_et_atomique(work):
    path = _ledger_path(work)
    led = {}
    L.record(led, "raw/pdfs/x.pdf.txt", "aaa", ["nav/relevement"], updated="2026-06-04")
    L.save_ledger(path, led, work_root=work)

    assert path.is_file()                               # .wiki/ créé
    assert not list(path.parent.glob(".tmp-*"))         # pas de tmp résiduel
    reloaded = L.load_ledger(path)
    assert reloaded["raw/pdfs/x.pdf.txt"].sha256 == "aaa"
    assert reloaded["raw/pdfs/x.pdf.txt"].articles == ["nav/relevement"]


# --- absent -> {} ----------------------------------------------------------
def test_load_absent_vide(work):
    assert L.load_ledger(_ledger_path(work)) == {}


# --- corrompu -> {} (jamais d'exception) -----------------------------------
def test_load_json_casse_vide(work):
    path = _ledger_path(work)
    path.parent.mkdir(parents=True)
    path.write_text("{ ceci n'est pas du json", encoding="utf-8")
    assert L.load_ledger(path) == {}  # n'a pas levé


def test_load_forme_mal_typee_ignore_entrees_invalides(work):
    path = _ledger_path(work)
    path.parent.mkdir(parents=True)
    # entrée 42 invalide (ignorée), entrée valide conservée
    path.write_text(json.dumps({"a": 42, "raw/pdfs/x.pdf.txt": {"sha256": "aaa"}}), encoding="utf-8")
    led = L.load_ledger(path)
    assert "a" not in led
    assert led["raw/pdfs/x.pdf.txt"].sha256 == "aaa"
    assert led["raw/pdfs/x.pdf.txt"].articles == []  # champ manquant -> défaut


def test_load_racine_non_dict_vide(work):
    path = _ledger_path(work)
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(["pas", "un", "dict"]), encoding="utf-8")
    assert L.load_ledger(path) == {}


# --- confinement -----------------------------------------------------------
def test_save_hors_work_root_refuse(work):
    led = {}
    L.record(led, "x", "aaa", [], updated="2026-06-04")
    with pytest.raises(ConfinementError):
        L.save_ledger(work / ".." / "evasion.json", led, work_root=work)

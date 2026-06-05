"""Tests du CLI wiki-sync : dispatch des sous-commandes, ordre du cycle, verrou tenu."""

import json
from types import SimpleNamespace

import pytest

import wiki_sync
from sync import locking as sync_lock


@pytest.fixture(autouse=True)
def _lock_in_tmp(tmp_path, monkeypatch):
    """Verrou hors ~/.cache réel et hors work_root."""
    monkeypatch.setattr(sync_lock, "_DEFAULT_LOCK", tmp_path / "lock" / "wiki-sync.lock")


@pytest.fixture
def config_noop(tmp_path):
    """Config sans clé `sync` -> backend noop (toutes les ops réussissent)."""
    work = tmp_path / "work"
    work.mkdir()
    cfgp = tmp_path / "wiki.config.json"
    cfgp.write_text(json.dumps({"work_root": str(work)}), encoding="utf-8")
    return str(cfgp)


def test_sync_noop_reussit(config_noop, capsys):
    assert wiki_sync.main(["--config", config_noop, "sync"]) == 0
    out = capsys.readouterr().out
    assert "pull" in out and "push" in out and "validate" in out


@pytest.mark.parametrize("cmd", ["lock", "pull", "push", "validate"])
def test_sous_commandes_noop(config_noop, cmd):
    assert wiki_sync.main(["--config", config_noop, cmd]) == 0


def test_cycle_sync_ordre(config_noop, monkeypatch):
    """`sync` enchaîne pull -> push -> validate dans cet ordre."""
    order = []
    backend = SimpleNamespace(
        warnings=[],
        pull=lambda: order.append("pull") or 0,
        push=lambda: order.append("push") or 0,
        validate=lambda: order.append("validate") or 0,
    )
    monkeypatch.setattr(wiki_sync.sync, "get_backend", lambda cfg: backend)
    assert wiki_sync.main(["--config", config_noop, "sync"]) == 0
    assert order == ["pull", "push", "validate"]


def test_sync_dry_run_saute_push(config_noop, monkeypatch):
    order = []
    backend = SimpleNamespace(
        warnings=[],
        pull=lambda: order.append("pull") or 0,
        push=lambda: order.append("push") or 0,
        validate=lambda: order.append("validate") or 0,
    )
    monkeypatch.setattr(wiki_sync.sync, "get_backend", lambda cfg: backend)
    assert wiki_sync.main(["--config", config_noop, "sync", "--dry-run"]) == 0
    assert order == ["pull", "validate"]  # push sauté


def test_pull_echec_stoppe_le_cycle(config_noop, monkeypatch):
    order = []
    backend = SimpleNamespace(
        warnings=[],
        pull=lambda: order.append("pull") or 3,
        push=lambda: order.append("push") or 0,
        validate=lambda: order.append("validate") or 0,
    )
    monkeypatch.setattr(wiki_sync.sync, "get_backend", lambda cfg: backend)
    assert wiki_sync.main(["--config", config_noop, "sync"]) == 3
    assert order == ["pull"]  # ni push ni validate


def test_verrou_tenu_skip_propre(config_noop, capsys):
    """Si le verrou est déjà tenu, le CLI sort proprement en code 0."""
    held = sync_lock.acquire()
    try:
        assert wiki_sync.main(["--config", config_noop, "sync"]) == 0
        assert "🔒" in capsys.readouterr().out
    finally:
        held.release()

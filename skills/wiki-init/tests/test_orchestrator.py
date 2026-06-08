"""Tests du CLI wiki-init : création idempotente, confinement, diagnostic, amorçage sync."""

import json
from types import SimpleNamespace

import pytest

import wiki_init
from sync import locking as sync_lock


@pytest.fixture(autouse=True)
def _lock_in_tmp(tmp_path, monkeypatch):
    """Verrou hors ~/.cache réel et hors work_root (mêmes garanties que wiki-sync)."""
    monkeypatch.setattr(sync_lock, "_DEFAULT_LOCK", tmp_path / "lock" / "wiki-sync.lock")


def _make_config(tmp_path, *, sync_cfg=None, layout=None, work_exists=False):
    """Écrit un wiki.config.json de test ; work_root vide par défaut (cas premier run)."""
    work = tmp_path / "vault" / "second-cerveau"
    if work_exists:
        work.mkdir(parents=True)
    data = {"work_root": str(work)}
    if layout is not None:
        data["layout"] = layout
    if sync_cfg is not None:
        data["sync"] = sync_cfg
    cfgp = tmp_path / "wiki.config.json"
    cfgp.write_text(json.dumps(data), encoding="utf-8")
    return str(cfgp), work


# --- apply : création de l'arborescence ------------------------------------
def test_apply_cree_la_structure_sur_vault_vide(tmp_path):
    """work_root inexistant -> racine + 4 dossiers + accueil + INDEX créés."""
    cfgp, work = _make_config(tmp_path)  # work_root n'existe pas encore
    assert wiki_init.main(["--config", cfgp, "apply", "--skip-sync"]) == 0

    assert work.is_dir()
    for sub in ("_inbox", "raw", "wiki", "reading-grids"):
        assert (work / sub).is_dir(), f"{sub} manquant"
    assert (work / "_inbox" / "LISEZ-MOI.md").is_file()
    assert (work / "wiki" / "INDEX.md").is_file()
    # `.wiki/` (ledger) n'est PAS créé par l'init.
    assert not (work / ".wiki").exists()


def test_apply_respecte_le_layout_personnalise(tmp_path):
    cfgp, work = _make_config(tmp_path, layout={"inbox": "boite", "wiki": "savoir"})
    assert wiki_init.main(["--config", cfgp, "apply", "--skip-sync"]) == 0
    assert (work / "boite").is_dir()
    assert (work / "savoir").is_dir()
    assert (work / "boite" / "LISEZ-MOI.md").is_file()
    assert (work / "savoir" / "INDEX.md").is_file()


def test_apply_idempotent_ne_reecrit_pas_les_fichiers(tmp_path):
    """Relancer apply ne doit jamais écraser l'accueil/INDEX modifiés par l'utilisateur."""
    cfgp, work = _make_config(tmp_path)
    assert wiki_init.main(["--config", cfgp, "apply", "--skip-sync"]) == 0

    readme = work / "_inbox" / "LISEZ-MOI.md"
    index = work / "wiki" / "INDEX.md"
    readme.write_text("PERSO inbox", encoding="utf-8")
    index.write_text("PERSO index", encoding="utf-8")

    assert wiki_init.main(["--config", cfgp, "apply", "--skip-sync"]) == 0
    assert readme.read_text(encoding="utf-8") == "PERSO inbox"
    assert index.read_text(encoding="utf-8") == "PERSO index"


def test_apply_refuse_layout_evasion(tmp_path):
    """Un layout qui sort de work_root est refusé (confinement, §2)."""
    from guard import ConfinementError

    cfgp, _ = _make_config(tmp_path, layout={"inbox": "../../evasion"})
    with pytest.raises(ConfinementError):
        wiki_init.main(["--config", cfgp, "apply", "--skip-sync"])


# --- status (lecture seule) ------------------------------------------------
def test_status_affiche_chemins_et_ne_cree_rien(tmp_path, capsys):
    cfgp, work = _make_config(tmp_path)
    assert wiki_init.main(["--config", cfgp, "status"]) == 0
    out = capsys.readouterr().out
    assert "CONFIG_PATH=" in out
    assert "WORK_ROOT=" in out and str(work) in out
    assert "INBOX=" in out and "WIKI=" in out
    # status est en lecture seule : rien n'est créé.
    assert not work.exists()


# --- amorçage de la synchro ------------------------------------------------
def test_apply_amorce_sync_pull_puis_push(tmp_path, monkeypatch):
    """Sans --skip-sync, apply enchaîne pull -> push via le backend."""
    cfgp, _ = _make_config(tmp_path, sync_cfg={"backend": "git", "git": {"repo_root": str(tmp_path)}})
    order = []
    backend = SimpleNamespace(
        warnings=["note"],
        pull=lambda: order.append("pull") or 0,
        push=lambda: order.append("push") or 0,
        validate=lambda: order.append("validate") or 0,
    )
    monkeypatch.setattr(wiki_init.sync, "get_backend", lambda cfg: backend)
    assert wiki_init.main(["--config", cfgp, "apply"]) == 0
    assert order == ["pull", "push"]  # pas de validate à l'amorçage


def test_apply_pull_echec_n_appelle_pas_push(tmp_path, monkeypatch):
    cfgp, _ = _make_config(tmp_path, sync_cfg={"backend": "git", "git": {"repo_root": str(tmp_path)}})
    order = []
    backend = SimpleNamespace(
        warnings=[],
        pull=lambda: order.append("pull") or 2,
        push=lambda: order.append("push") or 0,
        validate=lambda: 0,
    )
    monkeypatch.setattr(wiki_init.sync, "get_backend", lambda cfg: backend)
    assert wiki_init.main(["--config", cfgp, "apply"]) == 2
    assert order == ["pull"]  # push non appelé


def test_apply_noop_sans_cle_sync_reussit(tmp_path):
    """Config sans clé `sync` -> backend noop : amorçage réel réussit (code 0)."""
    cfgp, work = _make_config(tmp_path)
    assert wiki_init.main(["--config", cfgp, "apply"]) == 0
    assert (work / "_inbox").is_dir()

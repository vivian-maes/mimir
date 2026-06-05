"""Tests e2e du backend git — 100 % hermétiques (repo + bare remote locaux, sans réseau)."""

import shutil
import subprocess
from pathlib import Path

import pytest

import sync
from sync.git import GitBackend

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git non installé")


def _git(repo: Path, *args: str) -> str:
    """Lance git dans `repo` (capture, échoue fort) — utilitaire de test."""
    res = subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, check=True
    )
    return res.stdout.strip()


class _Cfg:
    """Config minimale ciblant le backend git."""

    def __init__(self, work_root: Path, git_conf: dict):
        self.work_root = Path(work_root)
        self.sync = {"backend": "git", "git": git_conf}

    @property
    def backend(self) -> str:
        return self.sync["backend"]


@pytest.fixture
def repos(tmp_path):
    """Crée un bare remote `origin`, un clone de travail (branche main), un commit initial poussé."""
    origin = tmp_path / "origin.git"
    subprocess.run(["git", "init", "--bare", "-b", "main", str(origin)], check=True,
                   capture_output=True, text=True)

    work = tmp_path / "work"
    work.mkdir()
    _git(work, "init", "-b", "main")
    _git(work, "config", "user.email", "t@example.org")
    _git(work, "config", "user.name", "Test")
    _git(work, "remote", "add", "origin", str(origin))
    # contenu initial dans le scope + un fichier hors scope (ledger)
    (work / "raw").mkdir()
    (work / "raw" / "seed.txt").write_text("seed\n", encoding="utf-8")
    (work / ".wiki").mkdir()
    (work / ".wiki" / "ingest-ledger.json").write_text("{}", encoding="utf-8")
    _git(work, "add", "raw")
    _git(work, "commit", "-m", "init")
    _git(work, "push", "-u", "origin", "main")

    cfg = _Cfg(work, {"repo_root": str(work), "branch": "main",
                      "scope": ["raw", "wiki", "reading-grids", "_inbox"]})
    return cfg, work, origin


def test_factory_selectionne_git(repos):
    cfg, _, _ = repos
    assert isinstance(sync.get_backend(cfg), GitBackend)


def test_push_publie_le_scope_et_validate_ok(repos):
    cfg, work, origin = repos
    (work / "wiki").mkdir()
    (work / "wiki" / "article.md").write_text("# A\n", encoding="utf-8")

    assert sync.push(cfg) == 0
    # le commit est bien arrivé sur origin
    assert "article.md" in _git(origin, "ls-tree", "-r", "--name-only", "main")
    assert sync.validate(cfg) == 0  # HEAD local == origin/main


def test_push_exclut_le_ledger_hors_scope(repos):
    cfg, work, origin = repos
    (work / "wiki").mkdir()
    (work / "wiki" / "a.md").write_text("# A\n", encoding="utf-8")
    # on modifie le ledger (hors scope) : il ne doit JAMAIS être committé
    (work / ".wiki" / "ingest-ledger.json").write_text('{"x": 1}', encoding="utf-8")

    assert sync.push(cfg) == 0
    tree = _git(origin, "ls-tree", "-r", "--name-only", "main")
    assert "ingest-ledger.json" not in tree
    assert ".wiki" not in tree


def test_push_rien_a_committer_renvoie_zero(repos):
    cfg, work, _ = repos
    assert sync.push(cfg) == 0  # rien de neuf après le seed initial -> 0 (up-to-date)


def test_validate_detecte_divergence(repos):
    cfg, work, _ = repos
    (work / "wiki").mkdir()
    (work / "wiki" / "local.md").write_text("# local\n", encoding="utf-8")
    _git(work, "add", "wiki")
    _git(work, "commit", "-m", "commit local non poussé")
    assert sync.validate(cfg) == 1  # HEAD local devant origin/main
    assert sync.push(cfg) == 0
    assert sync.validate(cfg) == 0  # après push : convergent


def test_pull_rapporte_les_changements_distants(repos, tmp_path):
    cfg, work, origin = repos
    # un second clone pousse une nouveauté sur origin
    other = tmp_path / "other"
    _git(other.parent, "clone", str(origin), str(other))
    _git(other, "config", "user.email", "o@example.org")
    _git(other, "config", "user.name", "Other")
    (other / "raw").mkdir(exist_ok=True)
    (other / "raw" / "remote.txt").write_text("distant\n", encoding="utf-8")
    _git(other, "add", "raw")
    _git(other, "commit", "-m", "depuis l'autre machine")
    _git(other, "push", "origin", "main")

    assert sync.pull(cfg) == 0
    assert (work / "raw" / "remote.txt").is_file()

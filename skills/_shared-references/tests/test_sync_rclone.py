"""Tests du backend rclone — 100 % hermétiques (runner factice, aucun binaire rclone)."""

from pathlib import Path
from types import SimpleNamespace

import pytest

import sync
from sync.rclone import RcloneBackend


class FakeRunner:
    """Runner injectable : réponses par sous-commande rclone (`bisync`/`sync`/`lsf`)."""

    def __init__(self, responses=None):
        # responses[sub] = (rc, stdout, stderr) ou une liste consommée dans l'ordre
        self.responses = responses or {}
        self.calls: list[list[str]] = []

    def __call__(self, argv, **kwargs):
        self.calls.append(argv)
        sub = argv[1] if len(argv) > 1 else ""
        r = self.responses.get(sub, (0, "", ""))
        if isinstance(r, list):
            r = r.pop(0) if r else (0, "", "")
        rc, out, err = r
        return SimpleNamespace(returncode=rc, stdout=out, stderr=err)

    def subcommands(self) -> list[str]:
        return [c[1] for c in self.calls if len(c) > 1]


@pytest.fixture
def cfg(tmp_path):
    class Cfg:
        work_root = tmp_path
        sync = {
            "backend": "rclone",
            "rclone": {"remote": "mimir:Vault/kb", "filters": "filters.txt"},
        }
        backend = "rclone"

    (tmp_path / "filters.txt").write_text("+ **\n", encoding="utf-8")
    return Cfg()


def test_factory_selectionne_rclone(cfg):
    assert isinstance(sync.get_backend(cfg), RcloneBackend)


def test_pull_construit_bisync_size_only(cfg):
    runner = FakeRunner({"bisync": (0, "", "")})
    assert sync.pull(cfg, runner=runner) == 0
    argv = runner.calls[0]
    assert argv[:2] == ["rclone", "bisync"]
    assert "mimir:Vault/kb" in argv
    assert "--size-only" in argv
    assert "--filter-from" in argv
    assert argv[argv.index("--filter-from") + 1].endswith("filters.txt")


def test_fallback_sync_quand_resync_requis(cfg):
    runner = FakeRunner({
        "bisync": (1, "", "Bisync critical error: Must run --resync to recover."),
        "sync": (0, "", ""),
    })
    backend = RcloneBackend(cfg, runner=runner)
    assert backend.push() == 0                      # bootstrap réussi -> 0
    assert runner.subcommands() == ["bisync", "sync"]  # bisync échoue puis sync
    assert backend.warnings and "resync" in backend.warnings[0].lower()


def test_echec_bisync_non_resync_propage(cfg):
    runner = FakeRunner({"bisync": (7, "", "network unreachable")})
    backend = RcloneBackend(cfg, runner=runner)
    assert backend.pull() == 7                       # pas un cas resync -> propagé
    assert runner.subcommands() == ["bisync"]        # aucun fallback


def test_validate_ok_quand_comptage_proche(cfg, tmp_path):
    (tmp_path / "a.md").write_text("x", encoding="utf-8")
    (tmp_path / "b.md").write_text("y", encoding="utf-8")
    runner = FakeRunner({"lsf": (0, "a.md\nb.md\n", "")})
    assert sync.validate(cfg, runner=runner) == 0


def test_validate_repousse_si_ecart(cfg, tmp_path):
    # 10 fichiers locaux, mais le 1er lsf n'en voit aucun (listing stale)
    for i in range(10):
        (tmp_path / f"f{i}.md").write_text("x", encoding="utf-8")
    runner = FakeRunner({
        "lsf": [(0, "", ""), (0, "\n".join(f"f{i}.md" for i in range(10)), "")],
        "sync": (0, "", ""),
    })
    assert sync.validate(cfg, runner=runner) == 0
    # a tenté un sync de re-poussée entre les deux lsf
    assert "sync" in runner.subcommands()


def test_validate_echoue_si_lsf_ko(cfg):
    runner = FakeRunner({"lsf": (1, "", "directory not found")})
    assert sync.validate(cfg, runner=runner) == 1

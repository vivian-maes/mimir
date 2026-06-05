#!/usr/bin/env python3
"""Backend de synchro **rclone** — bisync WebDAV (kDrive) (SPEC §10).

Battle-tested sur kDrive WebDAV (cf. `wiki-sync/references/RCLONE_KDRIVE.md`) :

- `--size-only` est **obligatoire** : le WebDAV kDrive n'expose ni modtime ni hash
  fiable, donc `--checksum`/`--compare modtime` provoquent des suppressions
  ping-pong. `--size-only` est la seule comparaison viable.
- `pull` et `push` lancent le **même** `bisync` bidirectionnel (réconciliation en
  une passe). Dans une chaîne extract→ingest→grid→index, utiliser `--skip-sync`
  pour éviter de réconcilier plusieurs fois.
- **Premier run / état bisync perdu** : `bisync` refuse de tourner (« Must run
  --resync »). On **ne lance jamais `--resync` automatiquement** (acte manuel qui
  désigne un côté comme vérité) ; on bascule sur un `sync` unidirectionnel
  local→distant (bootstrap) et on signale qu'un `--resync` manuel est requis.
- `validate` est **anti-listing-stale** : `bisync` renvoie 0 même quand le listing
  kDrive est périmé et que rien n'a transféré → on compare le nombre de fichiers
  local vs `rclone lsf`, et on re-pousse via `sync` si l'écart dépasse la tolérance.
"""

from __future__ import annotations

import os
from pathlib import Path

from .base import SyncBackend

#: Sous-chaînes (minuscules) signalant qu'un `--resync` manuel est requis.
_RESYNC_MARKERS = ("must run --resync", "bisync aborted", "cannot find prior listing")

#: Dossiers de service jamais synchronisés (approximation pour le comptage local).
_IGNORED_DIRS = {".git", ".obsidian", ".wiki", ".rclone-bisync"}


class RcloneBackend(SyncBackend):
    """Synchro bidirectionnelle via `rclone bisync --size-only` + garde-fous kDrive."""

    name = "rclone"

    def __init__(self, cfg, runner=None):
        super().__init__(cfg, runner)
        conf = (getattr(cfg, "sync", {}) or {}).get("rclone", {}) or {}
        self.local = Path(cfg.work_root)
        self.remote = conf.get("remote")
        self.bin = conf.get("bin", "rclone")
        self.max_delete = str(conf.get("max_delete", 25))
        self.filters = self._resolve_filters(conf.get("filters", "filters.txt"))
        #: Messages non bloquants à remonter à l'appelant (ex. « --resync requis »).
        self.warnings: list[str] = []

    def _resolve_filters(self, value) -> Path | None:
        if not value:
            return None
        p = Path(os.path.expanduser(value))
        return p if p.is_absolute() else (self.local / p)

    # --- construction des commandes ----------------------------------------
    def _bisync_argv(self) -> list[str]:
        argv = [
            self.bin, "bisync", str(self.local), self.remote,
            "--size-only", "--conflict-loser", "pathname",
            "--conflict-suffix", "sync-conflict", "--max-delete", self.max_delete,
            "--resilient", "--recover", "--copy-links",
        ]
        if self.filters:
            argv += ["--filter-from", str(self.filters)]
        return argv

    def _sync_argv(self) -> list[str]:
        """Repli unidirectionnel local→distant (bootstrap / re-poussée anti-stale)."""
        argv = [self.bin, "sync", str(self.local), self.remote, "--size-only", "--copy-links"]
        if self.filters:
            argv += ["--filter-from", str(self.filters)]
        return argv

    # --- réconciliation -----------------------------------------------------
    def _reconcile(self) -> int:
        res = self._run(self._bisync_argv())
        if res.returncode == 0:
            return 0
        out = ((res.stdout or "") + (res.stderr or "")).lower()
        if any(m in out for m in _RESYNC_MARKERS):
            # premier run / état perdu : bootstrap unidirectionnel, jamais --resync auto
            fb = self._run(self._sync_argv())
            if fb.returncode == 0:
                self.warnings.append(
                    "bisync sans état antérieur : bootstrap `rclone sync` effectué — "
                    "lancer un `rclone bisync --resync` manuel pour établir l'état bisync."
                )
                return 0
            return fb.returncode
        return res.returncode

    def pull(self) -> int:
        return self._reconcile()

    def push(self) -> int:
        return self._reconcile()

    # --- validation anti-stale ---------------------------------------------
    def _local_count(self) -> int:
        n = 0
        for root, dirs, files in os.walk(self.local):
            dirs[:] = [d for d in dirs if d not in _IGNORED_DIRS]
            n += sum(1 for f in files if f != ".DS_Store")
        return n

    def _remote_count(self) -> int | None:
        res = self._run([self.bin, "lsf", self.remote, "--recursive", "--files-only"])
        if res.returncode != 0:
            return None
        return sum(1 for line in (res.stdout or "").splitlines() if line.strip())

    def validate(self, *, tolerance: int = 5) -> int:
        """Compare les comptages local/distant ; re-pousse une fois si l'écart est grand."""
        local = self._local_count()
        remote = self._remote_count()
        if remote is None:
            return 1
        if abs(local - remote) <= tolerance:
            return 0
        # listing potentiellement stale : re-pousser puis revérifier (SPEC §12.4)
        self._run(self._sync_argv())
        remote = self._remote_count()
        if remote is None:
            return 1
        return 0 if abs(local - remote) <= tolerance else 1

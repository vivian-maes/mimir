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
  --resync »). Par défaut on **ne lance pas `--resync`** : on bascule sur un `sync`
  unidirectionnel local→distant (bootstrap) et on signale qu'un `--resync` manuel est
  requis. Avec `sync.rclone.auto_resync: true`, le backend amorce automatiquement
  l'état via `bisync --resync` (union sans perte — pas de `--resync-mode`, donc un
  fichier divergent produit deux copies plutôt qu'un écrasement).
- **Auth depuis le JSON** : si `sync.rclone.remote_setup` est fourni, le backend
  crée/répare le remote rclone (`config create`/`update`) avant la synchro, le mot de
  passe étant lu dans la variable d'environnement nommée par `pass_env` (jamais stocké
  dans le JSON). Un remote présent voit son secret rafraîchi (auto-réparation du 401).
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
        #: Amorçage `--resync` automatique (opt-in) : sans état antérieur, union sans perte.
        self.auto_resync = bool(conf.get("auto_resync", False))
        #: Création/réparation du remote rclone depuis le JSON+env (opt-in) ; secret hors JSON.
        self.remote_setup = conf.get("remote_setup") or None
        #: Garde-fou : ne (re)configure le remote qu'une fois par instance de backend.
        self._remote_ensured = False
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

    def _resync_argv(self) -> list[str]:
        """Amorçage bisync : mêmes flags que `_bisync_argv` **+ `--resync`**.

        Pas de `--resync-mode` (qui désignerait un gagnant) : on conserve
        `--conflict-loser pathname --conflict-suffix sync-conflict`, donc un fichier
        divergent des deux côtés produit **deux copies** au lieu d'un écrasement
        silencieux — union sans perte (SPEC §10).
        """
        return self._bisync_argv() + ["--resync"]

    def _sync_argv(self) -> list[str]:
        """Repli unidirectionnel local→distant (bootstrap / re-poussée anti-stale)."""
        argv = [self.bin, "sync", str(self.local), self.remote, "--size-only", "--copy-links"]
        if self.filters:
            argv += ["--filter-from", str(self.filters)]
        return argv

    # --- auth : (re)configuration du remote depuis le JSON+env --------------
    def _ensure_remote(self) -> None:
        """Crée/répare le remote rclone à partir de `remote_setup` (opt-in, idempotent).

        Le mot de passe ne vit **jamais** dans le JSON : `pass_env` nomme la variable
        d'environnement qui le porte. Un remote absent est créé ; un remote présent voit
        son mot de passe rafraîchi (auto-réparation du 401). Sans `remote_setup`, le
        remote est présumé déjà configuré à la main (comportement historique).
        """
        if self._remote_ensured or not self.remote_setup or not self.remote:
            return
        self._remote_ensured = True  # une seule tentative par cycle, succès comme échec
        name = self.remote.split(":", 1)[0]
        if not name:
            return
        setup = self.remote_setup
        pass_env = setup.get("pass_env")
        password = os.environ.get(pass_env) if pass_env else None
        if not password:
            self.warnings.append(
                f"remote_setup actif mais le mot de passe (env {pass_env!r}) est absent : "
                "remote rclone non (re)configuré — la synchro peut échouer en 401."
            )
            return
        listed = self._run([self.bin, "listremotes"])
        existing = {ln.rstrip(":") for ln in (listed.stdout or "").splitlines() if ln.strip()}
        if name in existing:
            # remote présent : on rafraîchit juste le secret (répare un 401).
            argv = [self.bin, "config", "update", name, "pass", password,
                    "--obscure", "--non-interactive"]
        else:
            argv = [self.bin, "config", "create", name, "webdav",
                    "url", setup.get("url", ""),
                    "vendor", setup.get("vendor", "other"),
                    "user", setup.get("user", ""),
                    "pass", password, "--obscure", "--non-interactive"]
        res = self._run(argv)
        if res.returncode != 0:
            # ne jamais relayer le secret : on remonte seulement le code et le nom du remote.
            self.warnings.append(
                f"(re)configuration du remote rclone {name!r} échouée (rc={res.returncode})."
            )

    # --- réconciliation -----------------------------------------------------
    def _reconcile(self) -> int:
        self._ensure_remote()
        res = self._run(self._bisync_argv())
        if res.returncode == 0:
            return 0
        out = ((res.stdout or "") + (res.stderr or "")).lower()
        if any(m in out for m in _RESYNC_MARKERS):
            if self.auto_resync:
                # amorçage automatique opt-in : bisync --resync (union sans perte)
                rs = self._run(self._resync_argv())
                if rs.returncode == 0:
                    self.warnings.append(
                        "bisync sans état antérieur : état amorcé automatiquement via "
                        "`--resync` (union sans perte)."
                    )
                    return 0
                # resync KO : on retombe sur le bootstrap unidirectionnel ci-dessous.
            # repli unidirectionnel (auto_resync off, ou resync auto en échec)
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

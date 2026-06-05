#!/usr/bin/env python3
"""Verrou mutex inter-process de la synchro (`wiki-sync.lock`).

`_inbox/` et la zone de travail sont **synchronisés** : deux machines/cron
pourraient consommer ou publier en même temps. On sérialise via un verrou
`mkdir` atomique placé **hors `work_root`** (`~/.cache/mimir/…`) — sinon le
verrou se synchroniserait et bloquerait les autres machines (vigilance §12.9).

Promu depuis `wiki-extract/inbox_lock.py` (Phase 1) vers le socle partagé en
Phase 4 : tous les backends (`rclone`, `git`) et tous les orchestrateurs
réutilisent ce même verrou via `SyncBackend.lock()` ou la façade `sync.lock()`.
"""

from __future__ import annotations

import json
import os
import shutil
import socket
import time
from pathlib import Path

_DEFAULT_LOCK = Path(os.path.expanduser("~/.cache/mimir/wiki-sync.lock"))
_META_NAME = "owner.json"


class LockHeld(RuntimeError):
    """Le verrou est déjà tenu par un process vivant (frais)."""


def _lock_dir(cfg=None) -> Path:
    """Chemin du verrou : `sync.rclone.lock_dir` du config si présent, sinon défaut."""
    if cfg is not None:
        ld = (getattr(cfg, "sync", {}) or {}).get("rclone", {}).get("lock_dir")
        if ld:
            return Path(os.path.expanduser(ld))
    return _DEFAULT_LOCK


def _age_minutes(path: Path) -> float:
    try:
        return (time.time() - path.stat().st_mtime) / 60.0
    except OSError:
        return float("inf")


class SyncLock:
    """Contexte de verrou. `acquire()` lève `LockHeld` si déjà tenu et frais."""

    def __init__(self, cfg=None, *, timeout_min: int = 30):
        self.dir = _lock_dir(cfg)
        self.timeout_min = timeout_min
        self._held = False

    def acquire(self) -> "SyncLock":
        self.dir.parent.mkdir(parents=True, exist_ok=True)
        try:
            os.makedirs(self.dir, exist_ok=False)  # atomique : échoue si déjà présent
        except FileExistsError:
            if _age_minutes(self.dir) > self.timeout_min:
                # verrou périmé (process mort sans release) -> récupération
                shutil.rmtree(self.dir, ignore_errors=True)
                os.makedirs(self.dir, exist_ok=False)
            else:
                raise LockHeld(f"Verrou déjà tenu : {self.dir}")
        meta = {"pid": os.getpid(), "host": socket.gethostname(), "ts": time.time()}
        (self.dir / _META_NAME).write_text(json.dumps(meta), encoding="utf-8")
        self._held = True
        return self

    def release(self) -> None:
        """Libère le verrou seulement si c'est bien le nôtre (même pid)."""
        if not self._held:
            return
        try:
            meta = json.loads((self.dir / _META_NAME).read_text(encoding="utf-8"))
            if meta.get("pid") == os.getpid():
                shutil.rmtree(self.dir, ignore_errors=True)
        except (OSError, ValueError):
            shutil.rmtree(self.dir, ignore_errors=True)
        finally:
            self._held = False

    def __enter__(self) -> "SyncLock":
        return self.acquire()

    def __exit__(self, *exc) -> None:
        self.release()


#: Compat : ancien nom de classe (Phase 1).
InboxLock = SyncLock


def acquire(cfg=None, *, timeout_min: int = 30) -> SyncLock:
    """Raccourci : crée et acquiert un `SyncLock` (lève `LockHeld` si tenu)."""
    return SyncLock(cfg, timeout_min=timeout_min).acquire()

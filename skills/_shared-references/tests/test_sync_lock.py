"""Tests du verrou de synchro (mutex mkdir hors work_root) — promu en Phase 4."""

import os
import time
from pathlib import Path

import pytest

from sync import locking as sync_lock
from sync.locking import LockHeld, SyncLock


@pytest.fixture
def lock_at(tmp_path, monkeypatch):
    """Force le verrou dans un tmp dédié (jamais ~/.cache réel ni sous work_root)."""
    target = tmp_path / "lockzone" / "wiki-sync.lock"
    monkeypatch.setattr(sync_lock, "_DEFAULT_LOCK", target)
    return target


def test_acquire_release(lock_at: Path):
    lk = sync_lock.acquire()
    assert lock_at.is_dir()
    assert (lock_at / "owner.json").is_file()
    lk.release()
    assert not lock_at.exists()


def test_double_acquire_leve_lockheld(lock_at: Path):
    lk = sync_lock.acquire()
    try:
        with pytest.raises(LockHeld):
            sync_lock.acquire()
    finally:
        lk.release()


def test_verrou_perime_recupere(lock_at: Path):
    first = sync_lock.acquire()  # ne pas release : simule un process mort
    old = time.time() - 60 * 60  # rendre le verrou « vieux » au-delà du timeout
    os.utime(lock_at, (old, old))
    second = SyncLock(timeout_min=30).acquire()  # doit récupérer
    assert lock_at.is_dir()
    second.release()
    first._held = False  # cleanup


def test_lock_dir_depuis_config(lock_at: Path, tmp_path: Path):
    """Le lock_dir vient de `sync.rclone.lock_dir` quand il est fourni."""

    class Cfg:
        sync = {"rclone": {"lock_dir": str(tmp_path / "from-config" / "lock")}}

    lk = sync_lock.acquire(Cfg())
    try:
        assert (tmp_path / "from-config" / "lock").is_dir()
    finally:
        lk.release()


def test_lock_hors_work_root(lock_at: Path, tmp_path: Path):
    work_root = tmp_path / "work"
    work_root.mkdir()
    lk = sync_lock.acquire()
    try:
        # le verrou ne doit JAMAIS vivre sous work_root (vigilance §12.9)
        assert work_root not in lock_at.parents
    finally:
        lk.release()


def test_context_manager(lock_at: Path):
    with SyncLock() as lk:
        assert lock_at.is_dir()
        assert lk._held
    assert not lock_at.exists()


def test_alias_inbox_lock():
    """Compat : l'ancien nom `InboxLock` pointe sur `SyncLock`."""
    from sync.locking import InboxLock

    assert InboxLock is SyncLock

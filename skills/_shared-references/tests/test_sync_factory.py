"""Tests de la factory de backends (`get_backend`) et de l'injection du runner."""

import pytest

import sync
from sync.base import SyncBackend, SyncError


class _Cfg:
    def __init__(self, sync_conf):
        self.sync = sync_conf

    @property
    def backend(self):
        return self.sync.get("backend", "rclone")


def test_backend_inconnu_leve_syncerror():
    cfg = _Cfg({"backend": "dropbox"})
    with pytest.raises(SyncError):
        sync.get_backend(cfg)


def test_runner_injecte_est_utilise():
    """`_run` délègue au runner fourni (aucun subprocess réel)."""
    calls = []

    def fake_runner(argv, **kwargs):
        calls.append(argv)

        class R:
            returncode = 0
            stdout = ""
            stderr = ""

        return R()

    class _Backend(SyncBackend):
        name = "test"

        def pull(self):
            return self._run(["echo", "hi"]).returncode

        def push(self):
            return 0

        def validate(self):
            return 0

    b = _Backend(_Cfg({}), runner=fake_runner)
    assert b.pull() == 0
    assert calls == [["echo", "hi"]]


def test_lock_herite_du_backend(tmp_path, monkeypatch):
    """Tout backend expose `lock()` via le verrou partagé (hors work_root)."""
    from sync import locking as sync_lock

    target = tmp_path / "lock" / "wiki-sync.lock"
    monkeypatch.setattr(sync_lock, "_DEFAULT_LOCK", target)

    backend = sync.get_backend(_Cfg({}))  # noop
    lk = backend.lock()
    try:
        assert target.is_dir()
    finally:
        lk.release()

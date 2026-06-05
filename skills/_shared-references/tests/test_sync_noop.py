"""Tests du backend no-op (config sans clé `sync`) — garantit le non-breaking."""

import sync
from sync.noop import NoopBackend


class _Cfg:
    """Config minimale : pas de clé `sync` -> backend noop."""

    sync = {}
    backend = "rclone"  # ignoré tant que `sync` est vide


def test_factory_noop_quand_pas_de_sync():
    backend = sync.get_backend(_Cfg())
    assert isinstance(backend, NoopBackend)
    assert backend.name == "noop"


def test_noop_pull_push_validate_renvoient_zero():
    cfg = _Cfg()
    assert sync.pull(cfg) == 0
    assert sync.push(cfg) == 0
    assert sync.validate(cfg) == 0

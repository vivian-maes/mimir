#!/usr/bin/env python3
"""Backend no-op — sélectionné quand `wiki.config.json` n'a **pas** de clé `sync`.

C'est le comportement « contenu d'abord, synchro ensuite » (ROADMAP) : on
travaille sur un `work_root` **local** sans aucune I/O distante. Toutes les
fixtures de test (configs sans `sync`) retombent ici, ce qui garde la suite
verte et rend la Phase 4 **non-breaking**. Le verrou hérité de `SyncBackend`
reste actif (mutex local utile même sans remote).
"""

from __future__ import annotations

from .base import SyncBackend


class NoopBackend(SyncBackend):
    """Aucune synchro : `pull`/`push`/`validate` réussissent sans rien faire."""

    name = "noop"

    def pull(self) -> int:
        return 0

    def push(self) -> int:
        return 0

    def validate(self) -> int:
        return 0

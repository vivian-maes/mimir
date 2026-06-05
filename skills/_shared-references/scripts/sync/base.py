#!/usr/bin/env python3
"""Contrat commun des backends de synchro (SPEC §10).

Un backend implémente `lock()` / `pull()` / `push()` / `validate()`. Le verrou
est mutualisé (mêmes garanties pour tous les backends : mutex `mkdir` **hors**
`work_root`, cf. `lock.py`) ; chaque backend ne fournit donc que les trois
opérations réseau.

Toutes les commandes externes passent par `self._run(argv)`, qui délègue à un
**runner injectable** (`subprocess.run` par défaut) : les tests fournissent un
runner factice et restent 100 % hermétiques (aucun binaire `rclone`/`git` requis).

Conventions de code retour (SPEC §10) :

| Op           | 0                          | ≠ 0                                         |
| ------------ | -------------------------- | ------------------------------------------- |
| `pull()`     | état distant récupéré      | l'appelant **stoppe** (ne compile pas)      |
| `push()`     | local publié               | **signalé** ; travail local conservé        |
| `validate()` | local↔distant cohérent     | remédiation / échec contrôlé                |
"""

from __future__ import annotations

import subprocess
from abc import ABC, abstractmethod
from typing import Any, Callable, Sequence


class SyncError(RuntimeError):
    """Backend inconnu, indisponible, ou échec non récupérable."""


class SyncBackend(ABC):
    """Backend de synchro pluggable, borné à `work_root` (confinement, SPEC §2)."""

    name: str = "abstract"

    def __init__(self, cfg, runner: Callable[..., Any] | None = None):
        self.cfg = cfg
        self._runner = runner or subprocess.run

    # --- exécution externe (injectable pour les tests) ---------------------
    def _run(self, argv: Sequence[str], **kwargs: Any):
        """Exécute `argv` via le runner injecté (capture stdout/stderr, texte)."""
        kwargs.setdefault("capture_output", True)
        kwargs.setdefault("text", True)
        return self._runner(list(argv), **kwargs)

    # --- verrou (commun à tous les backends, hors zone synchronisée) -------
    def lock(self, **kwargs: Any):
        """Verrou mutex inter-process, **hors** `work_root` (vigilance §12.9)."""
        from . import locking

        return locking.acquire(self.cfg, **kwargs)

    # --- I/O distant (à implémenter par chaque backend) --------------------
    @abstractmethod
    def pull(self) -> int:
        """Récupère l'état distant → local **avant** compilation."""

    @abstractmethod
    def push(self) -> int:
        """Publie local → distant **après** compilation."""

    @abstractmethod
    def validate(self) -> int:
        """Vérifie la cohérence local↔distant après `push`."""

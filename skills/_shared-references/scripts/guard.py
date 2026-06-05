#!/usr/bin/env python3
"""Garde de confinement — toute opération est bornée à `work_root`.

Règle d'or Mimir (SPEC §2, vigilance §12.8) : lecture, écriture **et** synchro
ne touchent jamais quoi que ce soit **hors** de `work_root`. Ce module fournit la
brique commune que toutes les écritures/synchros des phases suivantes doivent
traverser avant d'agir.

La normalisation s'appuie sur `os.path.realpath` (résout les `..` *et* les
symlinks) + `os.path.commonpath`, de sorte qu'un `../évasion` ou un symlink
pointant hors racine soit refusé.
"""

from __future__ import annotations

import os
from pathlib import Path


class ConfinementError(ValueError):
    """Levée quand un chemin sort de `work_root`."""


def _resolved(p: str | os.PathLike[str]) -> str:
    """Chemin absolu, `~` étendu, `..`/symlinks résolus."""
    return os.path.realpath(os.path.expanduser(os.fspath(p)))


def is_within(work_root: str | os.PathLike[str], target: str | os.PathLike[str]) -> bool:
    """Vrai si `target` est `work_root` lui-même ou un descendant."""
    root = _resolved(work_root)
    tgt = _resolved(target)
    try:
        return os.path.commonpath([root, tgt]) == root
    except ValueError:
        # Lecteurs/volumes différents (Windows) ou chemins non comparables.
        return False


def assert_within(
    work_root: str | os.PathLike[str], target: str | os.PathLike[str]
) -> Path:
    """Vérifie le confinement et renvoie le chemin résolu (sinon `ConfinementError`)."""
    if not is_within(work_root, target):
        raise ConfinementError(
            f"Chemin hors work_root : {_resolved(target)!r} n'est pas sous {_resolved(work_root)!r}"
        )
    return Path(_resolved(target))


def safe_path(work_root: str | os.PathLike[str], *parts: str) -> Path:
    """Construit un chemin sous `work_root` en garantissant le confinement.

    `safe_path(root, "raw", "pdfs", name)` -> chemin absolu confiné, ou lève si
    `parts` tente de remonter hors racine (ex. `".."`).
    """
    candidate = os.path.join(_resolved(work_root), *parts)
    return assert_within(work_root, candidate)

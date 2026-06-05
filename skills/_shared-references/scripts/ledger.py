#!/usr/bin/env python3
"""Ledger d'ingestion `.wiki/ingest-ledger.json` — SHA des sources → état compilé.

Cœur de l'idempotence de `wiki-ingest` (SPEC §7) : on ne recompile une source que
si elle est absente du ledger ou si son SHA de contenu a changé. Le ledger associe
au **chemin relatif à `work_root`** du fichier de contenu (`raw/pdfs/x.pdf.txt`) son
SHA256, les articles produits (wikilinks) et la date de compilation.

Garde-fous (vigilance §12.12) :
- **Atomique** : l'écriture passe par `iohelpers.write_json` (tmp + `os.replace`),
  confinée à `work_root` — jamais de fichier à moitié écrit.
- **Hors sync** : le ledger vit sous `.wiki/` (hors `wiki/`/`raw/`), exclu de la synchro.
- **Corrompu → `{}`** : si le JSON est invalide ou mal typé, on repart d'un ledger vide
  (idempotent) au lieu de bloquer toute recompilation.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path

import iohelpers  # même dossier scripts/ (résolu via sys.path par le bootstrap / conftest)


@dataclass
class LedgerEntry:
    """État compilé d'une source : SHA du contenu + articles produits + date."""

    sha256: str
    articles: list[str] = field(default_factory=list)  # wikilinks "sujet/notion"
    updated: str = ""


def _coerce(value: object) -> LedgerEntry | None:
    """Convertit une valeur JSON en `LedgerEntry`, ou `None` si la forme est invalide."""
    if not isinstance(value, dict):
        return None
    sha = value.get("sha256")
    if not isinstance(sha, str) or not sha:
        return None
    articles = value.get("articles", [])
    if not isinstance(articles, list) or not all(isinstance(a, str) for a in articles):
        articles = []
    updated = value.get("updated", "")
    if not isinstance(updated, str):
        updated = ""
    return LedgerEntry(sha256=sha, articles=list(articles), updated=updated)


def load_ledger(path: str | os.PathLike[str]) -> dict[str, LedgerEntry]:
    """Lit le ledger. Absent OU corrompu (JSON invalide / forme inattendue) → `{}`.

    Ne lève jamais : une corruption ne doit pas bloquer la compilation (§12.12).
    """
    p = Path(path)
    if not p.is_file():
        return {}
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
        return {}
    if not isinstance(raw, dict):
        return {}
    ledger: dict[str, LedgerEntry] = {}
    for key, value in raw.items():
        if not isinstance(key, str):
            continue
        entry = _coerce(value)
        if entry is not None:
            ledger[key] = entry
    return ledger


def save_ledger(
    path: str | os.PathLike[str],
    ledger: dict[str, LedgerEntry],
    *,
    work_root: str | os.PathLike[str],
) -> Path:
    """Sérialise et écrit le ledger atomiquement (confiné à `work_root`).

    Réutilise `iohelpers.write_json` (tmp + `os.replace`) ; crée `.wiki/` au besoin.
    """
    obj = {key: asdict(entry) for key, entry in ledger.items()}
    return iohelpers.write_json(path, obj, work_root=work_root)


def needs_compile(
    ledger: dict[str, LedgerEntry], content_rel: str, sha256: str
) -> bool:
    """Vrai si l'entrée est absente OU si son SHA diffère (SPEC §7.3)."""
    entry = ledger.get(content_rel)
    return entry is None or entry.sha256 != sha256


def record(
    ledger: dict[str, LedgerEntry],
    content_rel: str,
    sha256: str,
    articles: list[str],
    *,
    updated: str,
) -> dict[str, LedgerEntry]:
    """Upsert en place de l'entrée (remplace SHA + articles + date). Renvoie le ledger."""
    ledger[content_rel] = LedgerEntry(
        sha256=sha256, articles=list(articles), updated=updated
    )
    return ledger

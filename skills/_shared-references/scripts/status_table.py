#!/usr/bin/env python3
"""Lecture/écriture des tables de statut `raw/<type>/_status.md` (SPEC §4.3).

Seule mutation tolérée dans `raw/` (immutabilité, §4.2) : ces tables. La colonne
SHA256 porte sur le **fichier de contenu** (`.pdf.txt`/`.epub.txt`/`.md`), jamais
sur le binaire — c'est l'entrée d'ingestion et la clé de déduplication.

Partagé avec `wiki-ingest` (Phase 2), qui réécrit les colonnes « Statut » /
« Articles wiki » / « Grille » après compilation.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import iohelpers

#: En-têtes de colonnes, dans l'ordre (SPEC §4.3).
COLUMNS = ["Fichier", "SHA256", "Statut", "Articles wiki", "Grille", "MAJ"]

#: Statuts du cycle de vie (SPEC §4.3) : déposé -> extrait -> partiellement compilé -> compilé.
STATUSES = ("déposé", "extrait", "partiellement compilé", "compilé")

_EMPTY = "—"
_SEP_CELL = re.compile(r"^:?-{2,}:?$")


@dataclass
class StatusRow:
    """Une ligne de `_status.md`. `fichier` = nom du fichier de CONTENU (clé)."""

    fichier: str
    sha256: str
    statut: str = "extrait"
    articles: str = _EMPTY
    grille: str = _EMPTY
    maj: str = ""

    def cells(self) -> list[str]:
        return [self.fichier, self.sha256, self.statut, self.articles, self.grille, self.maj]


def _split_row(line: str) -> list[str] | None:
    """Découpe une ligne de tableau Markdown en cellules ; `None` si pas un tableau."""
    s = line.strip()
    if not s.startswith("|"):
        return None
    # retire les pipes de bord puis découpe ; conserve les cellules vides internes
    inner = s.strip("|")
    return [c.strip() for c in inner.split("|")]


def parse_status(md_text: str) -> list[StatusRow]:
    """Parse une table `_status.md`. Tolérant : texte vide/absent -> `[]`."""
    rows: list[StatusRow] = []
    seen_header = False
    for line in md_text.splitlines():
        cells = _split_row(line)
        if cells is None:
            continue
        if not seen_header:
            # première ligne de tableau = en-tête de colonnes
            seen_header = True
            continue
        if all(_SEP_CELL.match(c or "") for c in cells if c != ""):
            # ligne séparatrice (|---|---|)
            continue
        # normalise la largeur sur le nombre de colonnes attendu
        cells = (cells + [""] * len(COLUMNS))[: len(COLUMNS)]
        fichier, sha, statut, articles, grille, maj = cells
        if not fichier:
            continue
        rows.append(
            StatusRow(
                fichier=fichier,
                sha256=sha,
                statut=statut or "extrait",
                articles=articles or _EMPTY,
                grille=grille or _EMPTY,
                maj=maj,
            )
        )
    return rows


def render_status(doc_type: str, rows: list[StatusRow]) -> str:
    """Rend la table Markdown complète pour un type (`pdfs`/`epubs`/`web`)."""
    head = f"# Statut — {doc_type}\n\n"
    header = "| " + " | ".join(COLUMNS) + " |\n"
    sep = "| " + " | ".join("---" for _ in COLUMNS) + " |\n"
    body = "".join("| " + " | ".join(r.cells()) + " |\n" for r in rows)
    return head + header + sep + body


def upsert_row(rows: list[StatusRow], row: StatusRow) -> list[StatusRow]:
    """Remplace la ligne de même `fichier` (en place), sinon l'ajoute. Ordre conservé."""
    for i, existing in enumerate(rows):
        if existing.fichier == row.fichier:
            rows[i] = row
            return rows
    rows.append(row)
    return rows


def known_shas(rows: list[StatusRow]) -> set[str]:
    """Ensemble des SHA de contenu déjà connus (déduplication, SPEC §6)."""
    return {r.sha256 for r in rows if r.sha256}


def load_status(path: str | Path) -> list[StatusRow]:
    """Lit + parse `_status.md`. Fichier absent -> `[]`."""
    p = Path(path)
    if not p.is_file():
        return []
    return parse_status(p.read_text(encoding="utf-8"))


def save_status(
    path: str | Path, doc_type: str, rows: list[StatusRow], *, work_root: str | Path
) -> Path:
    """Rend la table et l'écrit atomiquement (confiné à `work_root`)."""
    return iohelpers.atomic_write_text(path, render_status(doc_type, rows), work_root=work_root)

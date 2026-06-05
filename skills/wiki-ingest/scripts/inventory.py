#!/usr/bin/env python3
"""Inventaire de `raw/` et sélection des sources à (re)compiler (SPEC §7.2–§7.3).

On liste les **fichiers de contenu** (`.pdf.txt` / `.epub.txt` / web `.md`) — jamais
les binaires, ni les sidecars de service (`INDEX.md`, `_status.md`, `*.toc.json`,
`_assets/`) — et on calcule leur SHA256. La sélection compare au ledger : une source
absente ou au SHA différent est « à compiler » ; sinon elle est déjà à jour (idempotence).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import iohelpers
import ledger as ledger_mod

#: Extension du fichier de contenu par type de document.
_CONTENT_EXT = {"pdfs": ".pdf.txt", "epubs": ".epub.txt", "web": ".md"}
_SKIP_NAMES = {"INDEX.md", "_status.md", ".DS_Store"}


@dataclass
class ContentFile:
    """Un fichier de contenu raw prêt à être ingéré."""

    content_path: str   # relatif à work_root (posix), ex. "raw/pdfs/x.pdf.txt"
    doc_type: str       # pdfs | epubs | web
    sha256: str
    toc_path: str | None  # relatif à work_root, ou None (web)

    def as_dict(self) -> dict:
        return {
            "content_path": self.content_path,
            "doc_type": self.doc_type,
            "sha256": self.sha256,
            "toc_path": self.toc_path,
        }


def _rel(path: Path, work_root: Path) -> str:
    return path.relative_to(work_root).as_posix()


def scan_content(cfg) -> list[ContentFile]:
    """Liste tous les fichiers de contenu de `raw/{pdfs,epubs,web}` avec leur SHA."""
    out: list[ContentFile] = []
    work_root = cfg.work_root
    for doc_type, ext in _CONTENT_EXT.items():
        type_dir = cfg.RAW / doc_type
        if not type_dir.is_dir():
            continue
        for p in sorted(type_dir.iterdir()):
            if not p.is_file() or p.name in _SKIP_NAMES or p.name.startswith("."):
                continue
            if not p.name.endswith(ext):
                continue
            base = p.name[: -len(ext)]
            toc = type_dir / f"{base}.toc.json"
            out.append(
                ContentFile(
                    content_path=_rel(p, work_root),
                    doc_type=doc_type,
                    sha256=iohelpers.sha256_file(p),
                    toc_path=_rel(toc, work_root) if toc.is_file() else None,
                )
            )
    return out


def existing_notions(cfg) -> dict[str, list[str]]:
    """Notions déjà présentes par sujet (`{sujet: [notion-slug, …]}`) — informe l'antidoublon."""
    out: dict[str, list[str]] = {}
    if not cfg.WIKI.is_dir():
        return out
    for subject_dir in sorted(cfg.WIKI.iterdir()):
        if not subject_dir.is_dir() or subject_dir.name.startswith("_"):
            continue
        notions = sorted(
            p.stem
            for p in subject_dir.iterdir()
            if p.is_file() and p.suffix == ".md" and not p.name.startswith("_")
        )
        if notions:
            out[subject_dir.name] = notions
    return out


def select(cfg, led: dict[str, ledger_mod.LedgerEntry], source: str | None = None) -> dict:
    """Worklist des sources à compiler + notions existantes par sujet.

    `source` (optionnel) restreint l'inventaire à un seul fichier de contenu
    (chemin relatif à work_root ou absolu sous raw/).
    """
    files = scan_content(cfg)
    if source:
        wanted = Path(source)
        wanted_rel = (
            wanted.as_posix()
            if not wanted.is_absolute()
            else wanted.resolve().relative_to(cfg.work_root).as_posix()
        )
        files = [f for f in files if f.content_path == wanted_rel]
    worklist = [
        f.as_dict()
        for f in files
        if ledger_mod.needs_compile(led, f.content_path, f.sha256)
    ]
    return {"worklist": worklist, "existing_notions": existing_notions(cfg)}

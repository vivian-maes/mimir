#!/usr/bin/env python3
"""Audit de cohérence des liens du wiki — 3 passes, **lecture seule** (SPEC §9).

Aucune écriture (pas même `_status.md`) : l'audit doit pouvoir tourner en CI sans
effet de bord. Périmètre (décision P3) : les wikilinks **wiki/ + reading-grids/**
seulement ; les liens vers `raw/` (champ `sources`) sont hors scope.

Trois passes :
1. **liens cassés** — un `[[…]]` d'un article/grille sans fichier cible résolu ;
2. **fichiers fantômes** — un article réel non listé dans le `_INDEX.md` de son sujet ;
3. **index → vide** — un `[[…]]` d'un fichier d'index (`INDEX.md`/`_INDEX.md`) sans cible.

Chemins normalisés avec `os.path.normpath` avant test d'existence (sinon faux
positifs sur les `..`), comparaison NFD/NFC, via `wikilinks.resolve`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import wikilinks

_INDEX_NAMES = {"INDEX.md", "_INDEX.md"}


@dataclass
class AuditReport:
    broken: list[tuple[str, str]] = field(default_factory=list)    # (fichier, cible)
    orphans: list[str] = field(default_factory=list)              # article non indexé
    dangling: list[tuple[str, str]] = field(default_factory=list)  # (index, cible)

    @property
    def total(self) -> int:
        return len(self.broken) + len(self.orphans) + len(self.dangling)

    @property
    def ok(self) -> bool:
        return self.total == 0


def _is_index(path: Path) -> bool:
    return path.name in _INDEX_NAMES


def _audit_targets(md_text: str) -> list[str]:
    """Cibles à auditer : wikilinks hors ancres pures et hors liens vers `raw/`."""
    return [t for t in wikilinks.extract_wikilinks(md_text) if not t.startswith("raw/")]


def _markdown_files(cfg) -> list[Path]:
    """Tous les `.md` du périmètre audité : `wiki/**` + `reading-grids/*`."""
    files: list[Path] = []
    if cfg.WIKI.is_dir():
        files.extend(sorted(cfg.WIKI.rglob("*.md")))
    if cfg.READING_GRIDS.is_dir():
        files.extend(sorted(cfg.READING_GRIDS.glob("*.md")))
    return files


def _pass_broken_and_dangling(cfg, files: list[Path]) -> tuple[list, list]:
    """Passes 1 & 3 : liens cassés (hors index) et entrées d'index mortes."""
    broken: list[tuple[str, str]] = []
    dangling: list[tuple[str, str]] = []
    for f in files:
        rel = f.relative_to(cfg.work_root).as_posix()
        for target in _audit_targets(f.read_text(encoding="utf-8")):
            if wikilinks.resolve(cfg, f, target) is None:
                (dangling if _is_index(f) else broken).append((rel, target))
    return broken, dangling


def _pass_orphans(cfg) -> list[str]:
    """Passe 2 : articles réels non listés dans le `_INDEX.md` de leur sujet."""
    orphans: list[str] = []
    if not cfg.WIKI.is_dir():
        return orphans
    for subj_dir in sorted(cfg.WIKI.iterdir()):
        if not subj_dir.is_dir() or subj_dir.name.startswith("_"):
            continue
        index = subj_dir / "_INDEX.md"
        indexed: set[Path] = set()
        if index.is_file():
            for target in _audit_targets(index.read_text(encoding="utf-8")):
                resolved = wikilinks.resolve(cfg, index, target)
                if resolved is not None:
                    indexed.add(resolved)
        for article in sorted(subj_dir.iterdir()):
            if not article.is_file() or article.suffix != ".md" or article.name.startswith("_"):
                continue
            if article.resolve() not in {p.resolve() for p in indexed}:
                orphans.append(article.relative_to(cfg.work_root).as_posix())
    return orphans


def audit(cfg) -> AuditReport:
    """Exécute les 3 passes en lecture seule et renvoie le rapport."""
    files = _markdown_files(cfg)
    broken, dangling = _pass_broken_and_dangling(cfg, files)
    orphans = _pass_orphans(cfg)
    return AuditReport(broken=broken, orphans=orphans, dangling=dangling)


def render_report(report: AuditReport, *, today: str) -> str:
    """Rapport texte lisible (lecture seule)."""
    lines = [
        f"AUDIT wiki — {today}",
        f"Passe 1 — liens cassés ........... {len(report.broken)}",
        f"Passe 2 — fichiers fantômes ...... {len(report.orphans)}",
        f"Passe 3 — index → vide ........... {len(report.dangling)}",
        f"RÉSULTAT : {'OK (0 anomalie)' if report.ok else f'KO ({report.total} anomalies)'}",
    ]
    if report.broken:
        lines.append("")
        lines.append("Liens cassés :")
        lines += [f"  - {src} → [[{tgt}]]" for src, tgt in report.broken]
    if report.orphans:
        lines.append("")
        lines.append("Fichiers fantômes (non indexés) :")
        lines += [f"  - {p}" for p in report.orphans]
    if report.dangling:
        lines.append("")
        lines.append("Entrées d'index pointant dans le vide :")
        lines += [f"  - {src} → [[{tgt}]]" for src, tgt in report.dangling]
    return "\n".join(lines) + "\n"

#!/usr/bin/env python3
"""Lecture d'un article notion `wiki/<sujet>/<notion>.md` (frontmatter + résumé).

Mutualisé par `wiki-reading-grid` (besoin des `sources` pour relier un article à
son chapitre) et `wiki-index` (besoin du résumé d'une ligne par notion). Réutilise
`frontmatter.parse_frontmatter` (NFD/NFC-tolérant, déjà testé en Phase 2) ; le seul
ajout est l'extraction du **callout `>`** placé juste après le H1 du corps Karpathy,
qui n'est pas dans le frontmatter.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import slug
from frontmatter import parse_frontmatter


@dataclass
class ArticleInfo:
    """Vue d'un article notion. `exists=False` si le fichier est introuvable."""

    wikilink: str               # "sujet/notion"
    path: Path                  # chemin attendu (canonique) ; réel si exists
    exists: bool
    title: str = ""
    summary: str = ""           # texte du callout `>` (résumé d'une ligne)
    sources: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)


def extract_summary(body: str) -> str:
    """Première ligne de callout `>` du corps (le résumé Karpathy après le H1).

    Tolérant : renvoie `""` si aucun callout n'est présent. S'arrête à la première
    section `##` pour ne pas confondre une citation interne avec le résumé.
    """
    for line in body.splitlines():
        s = line.strip()
        if s.startswith("## "):
            break
        if s.startswith(">"):
            return s.lstrip(">").strip()
    return ""


def _normalize_wikilink(wikilink: str) -> str:
    """Tolère un préfixe `wiki/` résiduel : `wiki/sujet/notion` → `sujet/notion`.

    Les chemins du wiki sont relatifs à `cfg.WIKI` ; un `wiki/` en tête ferait
    résoudre `cfg.WIKI / "wiki/…"` (introuvable). Défensif pour tous les appelants.
    """
    return wikilink.strip().removeprefix("wiki/").lstrip("/")


def _find_article(cfg, wikilink: str) -> Path | None:
    """Localise le fichier d'un wikilink `sujet/notion` (NFD/NFC-safe), ou `None`."""
    wikilink = _normalize_wikilink(wikilink)
    parts = wikilink.split("/")
    notion = parts[-1]
    subject = "/".join(parts[:-1])
    subj_dir = cfg.WIKI / subject if subject else cfg.WIKI
    if not subj_dir.is_dir():
        return None
    for p in subj_dir.iterdir():
        if p.is_file() and p.suffix == ".md" and slug.same_file(p.stem, notion):
            return p
    return None


def load_article(cfg, wikilink: str) -> ArticleInfo:
    """Charge l'`ArticleInfo` d'un wikilink `sujet/notion`. Fichier absent → `exists=False`."""
    wikilink = _normalize_wikilink(wikilink)
    notion = wikilink.split("/")[-1]
    canonical = cfg.WIKI / f"{wikilink}.md"
    actual = _find_article(cfg, wikilink)
    if actual is None:
        return ArticleInfo(wikilink=wikilink, path=canonical, exists=False, title=notion)

    front, body = parse_frontmatter(actual.read_text(encoding="utf-8"))
    title = str(front.get("title") or notion)
    tags = front.get("tags") if isinstance(front.get("tags"), list) else []
    sources = front.get("sources") if isinstance(front.get("sources"), list) else []
    return ArticleInfo(
        wikilink=wikilink,
        path=actual,
        exists=True,
        title=title,
        summary=extract_summary(body),
        sources=list(sources),   # type: ignore[arg-type]
        tags=list(tags),         # type: ignore[arg-type]
    )

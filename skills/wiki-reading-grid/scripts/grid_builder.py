#!/usr/bin/env python3
"""Cœur déterministe de `wiki-reading-grid` : construit la grille d'un ouvrage.

La grille **restitue l'ordre de lecture** (chapitrage) perdu par l'éclatement en
notions. Elle ne duplique aucun contenu : elle **ordonne des liens**. Trois sources
sont croisées (SPEC §8) :

1. le `<base>.toc.json` (clé disque `chapters`, ordonnée) — l'ossature de lecture ;
2. le **ledger** — la liste des articles produits depuis cet ouvrage, dans l'ordre
   d'écriture par l'agent (proxy de l'ordre de lecture, conservé dans un chapitre) ;
3. les `sources` du frontmatter de chaque article — l'ancre `…#chK` rattache
   l'article au chapitre `order=K` de cet ouvrage.

Cas limites assumés (pas des bugs) : un chapitre sans article reçoit un marqueur
« travail restant » ; un article du ledger sans ancre résolvable pour cet ouvrage
est listé « Hors chapitrage » ; un wikilink sans fichier réel est laissé tel quel
(l'audit `wiki-index` le remontera).
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

import article_index
import ledger as ledger_mod
import slug
import wikilinks

#: Extensions de contenu reconnues (pour retrouver le `base` d'un chemin raw).
_CONTENT_EXTS = (".pdf.txt", ".epub.txt", ".md")
#: Ancre de chapitre `chK` dans une source. `K` est soit un **numéro** (`#ch3`),
#: soit un **code d'ouvrage** (`#chR2`, `#chG3`, `#chC1`). Dans les deux cas, `K`
#: doit matcher le champ `order` du `toc.json` (cf. `_chapter_key`).
_CH_ANCHOR_RE = re.compile(r"^ch([A-Za-z]{0,2}\d{1,3})$", re.IGNORECASE)


def _chapter_key(raw) -> str:
    """Clé de chapitre normalisée, pour matcher une ancre `#chK` et un `order` du toc.

    Numérique → sans zéros de tête (`"03"` → `"3"`) ; code d'ouvrage → majuscule
    (`"g3"` → `"G3"`). Toute autre valeur est renvoyée trimée/majuscule telle quelle.
    """
    s = str(raw).strip().upper()
    m = re.fullmatch(r"([A-Z]{0,2})0*(\d+)", s)
    return f"{m.group(1)}{m.group(2)}" if m else s


@dataclass
class GridResult:
    """Résultat de construction d'une grille (markdown + diagnostic)."""

    content_rel: str
    doc_type: str = ""
    work: str = ""
    toc_rel: str = ""
    n_chapters: int = 0
    markdown: str = ""
    linked_articles: list[str] = field(default_factory=list)     # wikilinks placés ≥1 chapitre
    unresolved_chapters: list[int] = field(default_factory=list)  # chapitres sans article
    orphan_articles: list[str] = field(default_factory=list)      # ledger sans ancre résolvable
    skipped: str | None = None                                    # ex. "no-toc" (web)


def _base_of(filename: str) -> str:
    """Retire l'extension de contenu (`nav.pdf.txt` → `nav`)."""
    for ext in _CONTENT_EXTS:
        if filename.endswith(ext):
            return filename[: -len(ext)]
    return Path(filename).stem


def _same_path(a: str, b: str) -> bool:
    """Égalité de chemins relatifs (normpath + NFD/NFC)."""
    return slug.same_file(os.path.normpath(a), os.path.normpath(b))


def _chapters_cited(sources: list[str], content_rel: str) -> list[str]:
    """Clés de chapitres (de CET ouvrage) citées par les `sources` d'un article.

    L'ordre de citation est préservé (pas de tri : les clés peuvent être des codes
    `R2`/`G3` non triables numériquement ; l'ordre de lecture est porté par le toc).
    """
    found: list[str] = []
    for src in sources:
        path, sep, anchor = src.partition("#")
        if not sep or not _same_path(path, content_rel):
            continue
        m = _CH_ANCHOR_RE.match(anchor.strip())
        if m:
            k = _chapter_key(m.group(1))
            if k not in found:
                found.append(k)
    return found


def build_grid(cfg, content_rel: str) -> GridResult:
    """Construit la grille de l'ouvrage de contenu `content_rel` (chemin relatif raw/).

    `markdown` ne contient que le **corps** (sans frontmatter) : le `created` est
    décidé à l'écriture (préservation idempotente), via `document()`.
    """
    parts = content_rel.split("/")
    doc_type = parts[1] if len(parts) > 1 else ""
    base = _base_of(parts[-1])
    toc_rel = f"{cfg.layout['raw']}/{doc_type}/{base}.toc.json"
    toc_path = cfg.work_root / toc_rel

    # Pas de chapitrage (web, ou toc manquant) → on n'invente pas de grille.
    if not toc_path.is_file():
        return GridResult(content_rel=content_rel, doc_type=doc_type, skipped="no-toc")

    toc = json.loads(toc_path.read_text(encoding="utf-8"))
    work = str(toc.get("title") or base)
    # L'ordre des chapitres dans le `toc.json` EST l'ordre de lecture (vrai pour des
    # `order` numériques 1,2,3… comme pour des codes d'ouvrage R1,G3,…). On ne retrie
    # pas : trier des codes alphanumériquement casserait l'ordre canonique.
    chapters = list(toc.get("chapters") or [])

    # Articles de cet ouvrage selon le ledger (ordre d'écriture agent préservé).
    led = ledger_mod.load_ledger(cfg.LEDGER)
    entry = led.get(content_rel)
    article_wikilinks = list(entry.articles) if entry else []

    # Rattachement article → chapitre(s) via les ancres #chK des sources.
    buckets: dict[str, list[str]] = {}
    orphans: list[str] = []
    placed: set[str] = set()
    for wl in article_wikilinks:
        info = article_index.load_article(cfg, wl)
        cited = _chapters_cited(info.sources, content_rel)
        if not cited:
            orphans.append(wl)
            continue
        for k in cited:
            buckets.setdefault(k, []).append(wl)
            placed.add(wl)

    body = _render(work, chapters, buckets, orphans)
    unresolved = [c.get("order") for c in chapters if not buckets.get(_chapter_key(c.get("order")))]
    return GridResult(
        content_rel=content_rel,
        doc_type=doc_type,
        work=work,
        toc_rel=toc_rel,
        n_chapters=len(chapters),
        markdown=body,
        linked_articles=sorted(placed),
        unresolved_chapters=unresolved,
        orphan_articles=orphans,
    )


def document(result: GridResult, created: str) -> str:
    """Document complet = frontmatter (avec `created`) + corps de la grille."""
    return (
        _with_frontmatter(result.work, result.content_rel, result.toc_rel, result.n_chapters, created)
        + result.markdown
    )


def _with_frontmatter(
    work: str, content_rel: str, toc_rel: str, n_chapters: int, created: str
) -> str:
    """Frontmatter de grille (FRONTMATTERS.md §2 / SPEC §8)."""
    safe_work = work.replace('"', "'")
    return (
        "---\n"
        "type: reading-grid\n"
        f'work: "{safe_work}"\n'
        f"source: {content_rel}\n"
        f"toc: {toc_rel}\n"
        f"chapters: {n_chapters}\n"
        f"created: {created}\n"
        "---\n\n"
    )


def _render(
    work: str,
    chapters: list[dict],
    buckets: dict[str, list[str]],
    orphans: list[str],
) -> str:
    """Corps Markdown : un bloc par chapitre + navigation Précédent/Suivant."""
    lines: list[str] = [f"# Grille de lecture — {work}", ""]
    last = len(chapters) - 1
    for i, ch in enumerate(chapters):
        order = ch.get("order")
        title = str(ch.get("title") or f"Chapitre {order}")
        anchor = wikilinks.chapter_anchor(order, title)
        lines.append(f"## {anchor}")
        lines.append("")
        wls = buckets.get(_chapter_key(order)) or []
        if wls:
            lines.append("Lire dans l'ordre :")
            lines.append("")
            for n, wl in enumerate(wls, start=1):
                lines.append(f"{n}. [[{wl}]]")
        else:
            lines.append("_Aucun article rattaché pour l'instant._")
        lines.append("")
        nav = _nav_line(chapters, i, last)
        if nav:
            lines.append(nav)
            lines.append("")

    if orphans:
        lines.append("## Hors chapitrage")
        lines.append("")
        for wl in orphans:
            lines.append(f"- [[{wl}]]")
        lines.append("")

    return "\n".join(lines).rstrip("\n") + "\n"


def _nav_line(chapters: list[dict], i: int, last: int) -> str:
    """Ligne `⬅ … | ➡ …` pointant vers les ancres de chapitre Précédent/Suivant."""
    bits: list[str] = []
    if i > 0:
        prev = chapters[i - 1]
        bits.append(f"⬅ [[#{wikilinks.chapter_anchor(prev.get('order'), str(prev.get('title') or ''))}]]")
    if i < last:
        nxt = chapters[i + 1]
        bits.append(f"➡ [[#{wikilinks.chapter_anchor(nxt.get('order'), str(nxt.get('title') or ''))}]]")
    return " | ".join(bits)

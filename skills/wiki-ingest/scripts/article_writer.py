#!/usr/bin/env python3
"""Écriture fiable d'un article notion `wiki/<sujet>/<notion>.md` (format Karpathy).

La *prose* Karpathy est produite par l'agent (travail sémantique) ; ce module ne
fait que la partie **déterministe** : slugs ASCII, frontmatter YAML, antidoublon,
assets localisés et **validation NFD/NFC** après écriture.

Antidoublon (SPEC §7, décision Phase 2 = *replace-body*) : si la notion existe déjà
(même `wiki/<sujet>/<notion>.md`, comparé via `slug.same_file` pour ne pas être
piégé par la décomposition NFD d'APFS), on **remplace le corps** et on **fusionne le
frontmatter** sans perte (`created` conservé ; `sources`/`tags` en union ; `updated`
= jour). Jamais de fichier suffixé `-2` côté wiki (contrairement à `raw/`).
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import iohelpers
import slug
from frontmatter import parse_frontmatter as parse_existing  # promu en socle partagé (P3)
from guard import assert_within


class ArticleError(ValueError):
    """Spec d'article invalide (slug vide, sujet/notion hors confinement…)."""


@dataclass
class ArticleSpec:
    """Données d'un article notion fournies par l'agent (corps = prose Karpathy)."""

    subject: str                              # libellé sujet → slugifié pour le dossier
    notion: str                               # titre affichable (accents OK) → slugifié
    body: str                                 # corps Karpathy (sans frontmatter)
    sources: list[str] = field(default_factory=list)  # ex. "raw/pdfs/x.pdf.txt#ch3"
    tags: list[str] = field(default_factory=list)
    title: str | None = None                  # défaut = notion


@dataclass
class ArticleResult:
    path: Path
    wikilink: str                             # "<sujet-slug>/<notion-slug>" (NFC)
    created: bool                             # True si nouvel article, False si remplacé


# --- rendu / parsing du frontmatter ---------------------------------------
def _render_list(values: list[str], *, quote: bool) -> str:
    """Rend une flow-list YAML `[a, b]` (sources entre guillemets, tags nus)."""
    if not values:
        return "[]"
    if quote:
        items = ", ".join('"' + v.replace('"', "'") + '"' for v in values)
    else:
        items = ", ".join(values)
    return f"[{items}]"


def render_frontmatter(
    *,
    title: str,
    subject: str,
    tags: list[str],
    sources: list[str],
    created: str,
    updated: str,
) -> str:
    """Frontmatter YAML d'un article notion (gabarit FRONTMATTERS.md §1, SPEC §5.2).

    Construit à la main (format contrôlé, pas de dépendance `yaml` runtime), comme
    le frontmatter web de `wiki-extract`.
    """
    safe_title = (title or "").replace('"', "'")
    return (
        "---\n"
        f'title: "{safe_title}"\n'
        f"subject: {subject}\n"
        f"tags: {_render_list(tags, quote=False)}\n"
        f"sources: {_render_list(sources, quote=True)}\n"
        f"created: {created}\n"
        f"updated: {updated}\n"
        "---\n\n"
    )


def _union(*lists: list[str]) -> list[str]:
    """Union ordonnée et dédupliquée de plusieurs listes."""
    seen: set[str] = set()
    out: list[str] = []
    for lst in lists:
        for item in lst:
            if item not in seen:
                seen.add(item)
                out.append(item)
    return out


# --- assets localisés par sujet -------------------------------------------
def _place_assets(
    cfg, subject_slug: str, notion_slug: str, body: str, assets: list[str], *, work_root: Path
) -> str:
    """Copie chaque asset dans `wiki/<sujet>/_assets/` et réécrit le lien dans le corps.

    Un `_assets` **par sujet** (jamais centralisé, §12.14). Nom préfixé par le slug
    de la notion **en cas de collision** (SPEC §5.4) ; le lien `_assets/<base>` du
    corps est alors réécrit vers le nom final.
    """
    if not assets:
        return body
    assets_dir = cfg.WIKI / subject_slug / cfg.ASSETS_DIRNAME
    for asset in assets:
        src = Path(asset)
        base = src.name
        final_name = base
        if (assets_dir / base).exists():  # collision → préfixe par notion
            final_name = f"{notion_slug}-{base}"
        iohelpers.atomic_write_bytes(
            assets_dir / final_name, src.read_bytes(), work_root=work_root
        )
        if final_name != base:
            body = body.replace(f"{cfg.ASSETS_DIRNAME}/{base}", f"{cfg.ASSETS_DIRNAME}/{final_name}")
    return body


# --- écriture d'un article -------------------------------------------------
def write_article(
    cfg,
    spec: ArticleSpec,
    *,
    today: date | None = None,
    assets: list[str] | None = None,
    dry_run: bool = False,
) -> ArticleResult:
    """Écrit (ou remplace) `wiki/<sujet>/<notion>.md`. Antidoublon = replace-body.

    Renvoie un `ArticleResult` (chemin, wikilink NFC, `created`).
    """
    today = today or date.today()
    work_root = cfg.work_root

    subject_slug = slug.slugify(spec.subject)
    notion_slug = slug.slugify(spec.notion)
    if not subject_slug:
        raise ArticleError(f"Sujet vide après slugification : {spec.subject!r}")
    if not notion_slug:
        raise ArticleError(f"Notion vide après slugification : {spec.notion!r}")

    subject_dir = assert_within(work_root, cfg.WIKI / subject_slug)
    target = assert_within(work_root, subject_dir / f"{notion_slug}.md")

    # --- antidoublon : la notion existe-t-elle déjà (NFD/NFC-safe) ? --------
    existing_path: Path | None = None
    if subject_dir.is_dir():
        for p in subject_dir.iterdir():
            if p.suffix == ".md" and slug.same_file(p.stem, notion_slug):
                existing_path = p
                break
    created = existing_path is None

    # --- frontmatter : neuf, ou fusionné depuis l'existant ------------------
    if existing_path is not None:
        front, _old_body = parse_existing(existing_path.read_text(encoding="utf-8"))
        created_date = str(front.get("created") or today.isoformat())
        title = spec.title or str(front.get("title") or spec.notion)
        old_tags = front.get("tags") if isinstance(front.get("tags"), list) else []
        old_sources = front.get("sources") if isinstance(front.get("sources"), list) else []
        tags = _union(old_tags, spec.tags)          # type: ignore[arg-type]
        sources = _union(old_sources, spec.sources)  # type: ignore[arg-type]
    else:
        created_date = today.isoformat()
        title = spec.title or spec.notion
        tags = _union(spec.tags)
        sources = _union(spec.sources)

    body = spec.body
    if not dry_run:
        body = _place_assets(cfg, subject_slug, notion_slug, body, assets or [], work_root=work_root)

    document = render_frontmatter(
        title=title,
        subject=subject_slug,
        tags=tags,
        sources=sources,
        created=created_date,
        updated=today.isoformat(),
    ) + body.lstrip("\n")

    wikilink = f"{subject_slug}/{slug.normalize_nfc(notion_slug)}"

    if dry_run:
        return ArticleResult(path=target, wikilink=wikilink, created=created)

    # immutabilité de nom : on écrit toujours sur le nom canonique slugifié ;
    # si un fichier existant a un nom équivalent mais distinct (NFD), on le supprime
    # après écriture pour éviter un doublon de fichiers.
    iohelpers.atomic_write_text(target, document, work_root=work_root)
    if existing_path is not None and existing_path.name != target.name:
        existing_path.unlink(missing_ok=True)

    # --- validation NFD/NFC : le wikilink résout-il vers le fichier réel ? --
    real = next(
        (p for p in subject_dir.iterdir() if p.suffix == ".md" and slug.same_file(p.stem, notion_slug)),
        None,
    )
    if real is None or not slug.same_file(real.stem, notion_slug):
        raise ArticleError(
            f"Validation NFD/NFC échouée : wikilink {wikilink!r} ne résout pas vers un fichier réel"
        )

    return ArticleResult(path=target, wikilink=wikilink, created=created)

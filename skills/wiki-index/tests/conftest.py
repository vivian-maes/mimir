"""Rend importables les scripts de `wiki-index/` ET du socle partagé, + fixtures vault.

Deux dossiers sur `sys.path` (imports plats, cohérent avec le socle Phase 0) :
- `skills/wiki-index/scripts/`         -> wiki_index, index_builder, link_audit
- `skills/_shared-references/scripts/` -> config_loader, slug, iohelpers, wikilinks,
  article_index, frontmatter, status_table, ledger, sync
"""

import json
import sys
from pathlib import Path

_HERE = Path(__file__).resolve()
_SKILL_SCRIPTS = _HERE.parent.parent / "scripts"
_SHARED_SCRIPTS = _HERE.parents[2] / "_shared-references" / "scripts"

for p in (_SKILL_SCRIPTS, _SHARED_SCRIPTS):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import pytest  # noqa: E402

import config_loader  # noqa: E402


def _article(notion, summary):
    return (
        "---\n"
        f'title: "{notion}"\n'
        "subject: navigation\n"
        "tags: [navigation]\n"
        'sources: ["raw/pdfs/navigation-cotiere.pdf.txt#ch2"]\n'
        "created: 2026-06-04\n"
        "updated: 2026-06-04\n"
        "---\n\n"
        f"# {notion}\n\n> {summary}\n\n## Définition\nTexte.\n"
    )


def _grid():
    return (
        "---\n"
        "type: reading-grid\n"
        'work: "Navigation côtière"\n'
        "source: raw/pdfs/navigation-cotiere.pdf.txt\n"
        "toc: raw/pdfs/navigation-cotiere.toc.json\n"
        "chapters: 2\n"
        "created: 2026-06-04\n"
        "---\n\n"
        "# Grille de lecture — Navigation côtière\n\n"
        "## Ch. 1 — Instruments\n\nLire dans l'ordre :\n\n1. [[navigation/relevement]]\n\n"
        "➡ [[#Ch. 2 — Se positionner]]\n\n"
        "## Ch. 2 — Se positionner\n\nLire dans l'ordre :\n\n"
        "1. [[navigation/triangulation]]\n2. [[navigation/maree]]\n\n⬅ [[#Ch. 1 — Instruments]]\n"
    )


@pytest.fixture
def cfg(tmp_path):
    work = tmp_path / "work"
    (work / "wiki" / "navigation").mkdir(parents=True)
    (work / "reading-grids").mkdir(parents=True)
    cfgp = tmp_path / "wiki.config.json"
    cfgp.write_text(json.dumps({"work_root": str(work)}), encoding="utf-8")
    return config_loader.load_config(cfgp)


@pytest.fixture
def vault(cfg):
    """Vault sain : 1 sujet, 3 notions, 1 grille rattachée. Audit doit ressortir à zéro."""
    nav = cfg.WIKI / "navigation"
    nav.joinpath("relevement.md").write_text(_article("Relèvement", "Angle vers un amer."), encoding="utf-8")
    nav.joinpath("triangulation.md").write_text(_article("Triangulation", "Recoupe deux relèvements."), encoding="utf-8")
    nav.joinpath("maree.md").write_text(_article("Marée", "Variation du niveau de la mer."), encoding="utf-8")
    (cfg.READING_GRIDS / "navigation-cotiere.md").write_text(_grid(), encoding="utf-8")
    return cfg

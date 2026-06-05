"""Rend importables les scripts de `wiki-reading-grid/` ET du socle partagé.

Deux dossiers sur `sys.path` (imports plats, cohérent avec le socle Phase 0) :
- `skills/wiki-reading-grid/scripts/`  -> wiki_reading_grid, grid_builder
- `skills/_shared-references/scripts/` -> config_loader, slug, iohelpers, status_table,
  ledger, frontmatter, article_index, wikilinks, sync
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
import ledger as ledger_mod  # noqa: E402
import status_table  # noqa: E402

CONTENT_REL = "raw/pdfs/navigation-cotiere.pdf.txt"


def _article(subject, notion, summary, sources):
    src = ", ".join(f'"{s}"' for s in sources)
    return (
        "---\n"
        f'title: "{notion}"\n'
        f"subject: {subject}\n"
        "tags: [navigation]\n"
        f"sources: [{src}]\n"
        "created: 2026-06-04\n"
        "updated: 2026-06-04\n"
        "---\n\n"
        f"# {notion}\n\n> {summary}\n\n## Définition\nTexte.\n"
    )


@pytest.fixture
def cfg(tmp_path):
    work = tmp_path / "work"
    (work / "raw" / "pdfs").mkdir(parents=True)
    (work / "wiki" / "navigation").mkdir(parents=True)
    (work / "reading-grids").mkdir(parents=True)
    cfgp = tmp_path / "wiki.config.json"
    cfgp.write_text(json.dumps({"work_root": str(work)}), encoding="utf-8")
    return config_loader.load_config(cfgp)


@pytest.fixture
def vault(cfg):
    """Vault minimal : 3 chapitres (ch1 sans article), 3 articles rattachés + 1 orphelin."""
    pdfs = cfg.RAW / "pdfs"
    (pdfs / "navigation-cotiere.pdf.txt").write_text("Contenu.\n", encoding="utf-8")
    toc = {
        "title": "Navigation côtière",
        "source": "raw/pdfs/navigation-cotiere.pdf",
        "pages": 240,
        "ocr": False,
        "chapters": [
            {"order": 1, "title": "Instruments", "page_start": 1, "page_end": 22},
            {"order": 2, "title": "Se positionner", "page_start": 23, "page_end": 48},
            {"order": 3, "title": "Marées", "page_start": 49, "page_end": 80},
        ],
    }
    (pdfs / "navigation-cotiere.toc.json").write_text(json.dumps(toc, ensure_ascii=False), encoding="utf-8")

    # _status.md avec la ligne de la source (sans grille encore)
    rows = [status_table.StatusRow(
        fichier="navigation-cotiere.pdf.txt", sha256="abc123", statut="compilé",
        articles="[[navigation/relevement]]", maj="2026-06-04")]
    status_table.save_status(pdfs / "_status.md", "pdfs", rows, work_root=cfg.work_root)

    nav = cfg.WIKI / "navigation"
    nav.joinpath("relevement.md").write_text(
        _article("navigation", "Relèvement", "Angle vers un amer.", [f"{CONTENT_REL}#ch2"]), encoding="utf-8")
    nav.joinpath("triangulation.md").write_text(
        _article("navigation", "Triangulation", "Recoupe deux relèvements.", [f"{CONTENT_REL}#ch2"]), encoding="utf-8")
    nav.joinpath("maree.md").write_text(
        _article("navigation", "Marée", "Variation du niveau de la mer.", [f"{CONTENT_REL}#ch3"]), encoding="utf-8")
    nav.joinpath("intro.md").write_text(
        _article("navigation", "Introduction", "Vue d'ensemble.", ["raw/web/preface.md"]), encoding="utf-8")

    led = {}
    ledger_mod.record(
        led, CONTENT_REL, "abc123",
        ["navigation/relevement", "navigation/triangulation", "navigation/maree", "navigation/intro"],
        updated="2026-06-04",
    )
    ledger_mod.save_ledger(cfg.LEDGER, led, work_root=cfg.work_root)
    return cfg

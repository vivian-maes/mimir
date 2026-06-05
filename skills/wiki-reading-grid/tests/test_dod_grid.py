"""DoD Phase 3 (grille) : suit le chapitrage source, zéro lien interne cassé."""

import re

import grid_builder as gb
import wiki_reading_grid as wrg
from frontmatter import parse_frontmatter

CONTENT_REL = "raw/pdfs/navigation-cotiere.pdf.txt"


def test_grille_suit_le_chapitrage(vault):
    """Les titres de chapitre apparaissent dans l'ordre exact du toc.json."""
    wrg.cmd_generate(vault, CONTENT_REL, skip_sync=True)
    doc = (vault.READING_GRIDS / "navigation-cotiere.md").read_text(encoding="utf-8")
    headings = [ln[3:].strip() for ln in doc.splitlines() if ln.startswith("## ") and ln.startswith("## Ch.")]
    assert headings == ["Ch. 1 — Instruments", "Ch. 2 — Se positionner", "Ch. 3 — Marées"]


def test_zero_lien_interne_casse(vault):
    """Chaque lien Précédent/Suivant `[[#…]]` pointe vers un titre `##` présent."""
    res = gb.build_grid(vault, CONTENT_REL)
    body = gb.document(res, "2026-06-04")
    headings = {ln[3:].strip() for ln in body.splitlines() if ln.startswith("## ")}
    internal = re.findall(r"\[\[#([^\]]+)\]\]", body)
    assert internal, "la grille doit comporter des liens de navigation"
    assert all(t in headings for t in internal)


def test_aucun_contenu_duplique(vault):
    """La grille n'ordonne que des liens : pas de corps d'article recopié."""
    wrg.cmd_generate(vault, CONTENT_REL, skip_sync=True)
    doc = (vault.READING_GRIDS / "navigation-cotiere.md").read_text(encoding="utf-8")
    _, body = parse_frontmatter(doc)
    assert "## Définition" not in body                      # corps Karpathy non recopié
    assert "Angle vers un amer." not in body                # résumé d'article non recopié

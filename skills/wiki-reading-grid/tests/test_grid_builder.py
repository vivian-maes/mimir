"""Tests unitaires du cœur de construction de grille (croisement toc × ledger × ancres)."""

import grid_builder as gb

CONTENT_REL = "raw/pdfs/navigation-cotiere.pdf.txt"


def test_chapters_cited():
    srcs = [f"{CONTENT_REL}#ch2", f"{CONTENT_REL}#ch4", "raw/web/x.md", "raw/pdfs/autre.pdf.txt#ch1"]
    assert gb._chapters_cited(srcs, CONTENT_REL) == [2, 4]   # autre ouvrage + web ignorés


def test_build_buckets_et_ordre(vault):
    res = gb.build_grid(vault, CONTENT_REL)
    assert res.skipped is None
    assert res.work == "Navigation côtière"
    assert res.n_chapters == 3
    # ch2 contient relèvement puis triangulation (ordre du ledger) ; ch3 marée
    body = res.markdown
    assert "## Ch. 2 — Se positionner" in body
    i_rel = body.index("[[navigation/relevement]]")
    i_tri = body.index("[[navigation/triangulation]]")
    assert i_rel < i_tri
    assert "[[navigation/maree]]" in body


def test_chapitre_sans_article(vault):
    res = gb.build_grid(vault, CONTENT_REL)
    assert 1 in res.unresolved_chapters                     # ch1 Instruments
    assert "_Aucun article rattaché pour l'instant._" in res.markdown


def test_orphelin_hors_chapitrage(vault):
    res = gb.build_grid(vault, CONTENT_REL)
    assert res.orphan_articles == ["navigation/intro"]       # sources web sans #ch
    assert "## Hors chapitrage" in res.markdown
    assert "- [[navigation/intro]]" in res.markdown


def test_prev_next_pointent_vers_titres_reels(vault):
    """DoD : chaque lien Précédent/Suivant pointe vers un titre `##` présent."""
    res = gb.build_grid(vault, CONTENT_REL)
    body = res.markdown
    headings = {ln[3:].strip() for ln in body.splitlines() if ln.startswith("## ")}
    import re
    for target in re.findall(r"\[\[#([^\]]+)\]\]", body):
        assert target in headings, f"lien interne cassé : #{target}"
    # premier chapitre : pas de ⬅ ; structure de navigation présente
    assert "➡ [[#Ch. 2 — Se positionner]]" in body


def test_web_sans_toc_skipped(vault):
    res = gb.build_grid(vault, "raw/web/preface.md")
    assert res.skipped == "no-toc"
    assert res.markdown == ""


def test_document_ajoute_frontmatter(vault):
    res = gb.build_grid(vault, CONTENT_REL)
    doc = gb.document(res, "2026-06-04")
    assert doc.startswith("---\ntype: reading-grid\n")
    assert 'work: "Navigation côtière"' in doc
    assert f"source: {CONTENT_REL}" in doc
    assert "chapters: 3" in doc
    assert "created: 2026-06-04" in doc

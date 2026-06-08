"""Tests unitaires du cœur de construction de grille (croisement toc × ledger × ancres)."""

import article_index
import grid_builder as gb

CONTENT_REL = "raw/pdfs/navigation-cotiere.pdf.txt"


def test_load_article_tolere_prefixe_wiki(vault):
    """`load_article` résout aussi bien `sujet/notion` que `wiki/sujet/notion`."""
    a = article_index.load_article(vault, "navigation/relevement")
    b = article_index.load_article(vault, "wiki/navigation/relevement")
    assert a.exists and b.exists
    assert a.path == b.path
    assert b.sources == [f"{CONTENT_REL}#ch2"]


def test_chapters_cited():
    srcs = [f"{CONTENT_REL}#ch2", f"{CONTENT_REL}#ch4", "raw/web/x.md", "raw/pdfs/autre.pdf.txt#ch1"]
    assert gb._chapters_cited(srcs, CONTENT_REL) == ["2", "4"]   # clés str ; autre ouvrage + web ignorés


def test_chapters_cited_codes_ouvrage():
    """`#chR2`/`#chG3` (codes d'ouvrage) sont reconnus et normalisés en majuscule."""
    srcs = [f"{CONTENT_REL}#chR2", f"{CONTENT_REL}#chg3", f"{CONTENT_REL}#chC1"]
    assert gb._chapters_cited(srcs, CONTENT_REL) == ["R2", "G3", "C1"]   # ordre de citation préservé


def test_chapter_key_normalise():
    assert gb._chapter_key(3) == "3"
    assert gb._chapter_key("03") == "3"          # zéros de tête (ancien #ch03)
    assert gb._chapter_key("g3") == "G3"         # code d'ouvrage en majuscule
    assert gb._chapter_key("R02") == "R2"


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

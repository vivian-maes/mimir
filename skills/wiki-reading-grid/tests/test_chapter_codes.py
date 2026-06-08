"""Grille d'un ouvrage à chapitres codés (R1-R9, G1-G6, C1-C2) — non-régression v0.6.0.

Reproduit le cas du guide brevet qui donnait « 0 article lié » : `toc.json` avec
`order` alphanumérique + articles ancrés `#chR1`/`#chG3`. Vérifie que la grille relie
les articles ET respecte l'ordre de lecture du `toc.json` (pas de tri alphabétique).
"""

import json

import grid_builder as gb
import ledger as ledger_mod

CONTENT_REL = "raw/pdfs/guide.pdf.txt"


def _article(notion, summary, sources):
    src = ", ".join(f'"{s}"' for s in sources)
    return (
        "---\n"
        f'title: "{notion}"\n'
        "subject: reglementation\n"
        "tags: [brevet]\n"
        f"sources: [{src}]\n"
        "created: 2026-06-04\n"
        "updated: 2026-06-04\n"
        "---\n\n"
        f"# {notion}\n\n> {summary}\n\n## Définition\nTexte.\n"
    )


def _vault_codes(cfg):
    pdfs = cfg.RAW / "pdfs"
    (pdfs / "guide.pdf.txt").write_text("Contenu.\n", encoding="utf-8")
    # Ordre de lecture canonique : R1 puis G3 (un tri alphabétique donnerait G3 avant R1).
    toc = {
        "title": "Guide brevet",
        "source": "raw/pdfs/guide.pdf",
        "pages": 156,
        "ocr": False,
        "chapters": [
            {"order": "R1", "title": "Notions, manoeuvres", "page_start": 3, "page_end": 40},
            {"order": "G3", "title": "Marées", "page_start": 123, "page_end": 126},
        ],
    }
    (pdfs / "guide.toc.json").write_text(json.dumps(toc, ensure_ascii=False), encoding="utf-8")

    reg = cfg.WIKI / "reglementation"
    reg.mkdir(parents=True, exist_ok=True)
    reg.joinpath("feux.md").write_text(
        _article("Feux", "Feux de navigation.", [f"{CONTENT_REL}#chR1"]), encoding="utf-8")
    mar = cfg.WIKI / "marees"
    mar.mkdir(parents=True, exist_ok=True)
    mar.joinpath("calcul-de-maree.md").write_text(
        _article("Calcul de marée", "Méthode des douzièmes.", [f"{CONTENT_REL}#chG3"]), encoding="utf-8")

    led = {}
    ledger_mod.record(
        led, CONTENT_REL, "sha-codes",
        ["reglementation/feux", "marees/calcul-de-maree"], updated="2026-06-04")
    ledger_mod.save_ledger(cfg.LEDGER, led, work_root=cfg.work_root)
    return cfg


def test_codes_ouvrage_relient_les_articles(cfg):
    res = gb.build_grid(_vault_codes(cfg), CONTENT_REL)
    assert res.skipped is None
    assert sorted(res.linked_articles) == ["marees/calcul-de-maree", "reglementation/feux"]
    assert res.orphan_articles == []
    assert res.unresolved_chapters == []          # R1 et G3 ont chacun un article


def test_ordre_de_lecture_du_toc_preserve(cfg):
    """R1 doit apparaître AVANT G3 (ordre du toc), pas trié alphabétiquement."""
    res = gb.build_grid(_vault_codes(cfg), CONTENT_REL)
    body = res.markdown
    assert "## Ch. R1 — Notions, manoeuvres" in body
    assert "## Ch. G3 — Marées" in body
    assert body.index("Ch. R1") < body.index("Ch. G3")
    assert "[[reglementation/feux]]" in body
    assert "[[marees/calcul-de-maree]]" in body

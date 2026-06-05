"""Tests de la génération des index (sujets, notions, grilles, préservation)."""

import index_builder as ib
from frontmatter import parse_frontmatter


def test_list_subjects_et_notions(vault):
    assert ib.list_subjects(vault) == ["navigation"]
    assert ib.list_notions(vault, "navigation") == ["maree", "relevement", "triangulation"]


def test_grids_by_subject(vault):
    grids = ib.grids_by_subject(vault)
    assert "navigation" in grids
    ref = grids["navigation"][0]
    assert ref.slug == "navigation-cotiere" and ref.work == "Navigation côtière" and ref.chapters == 2


def test_subject_index_notions_et_grilles(vault):
    ib.regenerate(vault, dry_run=False)
    doc = (vault.WIKI / "navigation" / "_INDEX.md").read_text(encoding="utf-8")
    assert "# Index — navigation" in doc
    assert "- [[navigation/relevement]] — Angle vers un amer." in doc
    assert "## Grilles de lecture" in doc
    assert "- [[reading-grids/navigation-cotiere]] — Navigation côtière (2 ch.)" in doc


def test_main_index_liste_sujets(vault):
    ib.regenerate(vault, dry_run=False)
    doc = (vault.WIKI / "INDEX.md").read_text(encoding="utf-8")
    assert "# Index du wiki" in doc
    # pas de description éditoriale -> fallback 3 premières notions
    assert "- [[navigation/_INDEX]] — maree, relevement, triangulation" in doc


def test_main_index_preserve_description_editoriale(vault):
    # 1re génération puis édition manuelle de la description
    ib.regenerate(vault, dry_run=False)
    index = vault.WIKI / "INDEX.md"
    index.write_text(
        "# Index du wiki\n\n> Carte par sujet.\n\n- [[navigation/_INDEX]] — pilotage, position, marées.\n",
        encoding="utf-8",
    )
    ib.regenerate(vault, dry_run=False)
    doc = index.read_text(encoding="utf-8")
    assert "- [[navigation/_INDEX]] — pilotage, position, marées." in doc   # non écrasée


def test_dry_run_n_ecrit_rien(vault):
    res = ib.regenerate(vault, dry_run=True)
    assert "navigation" in res.subjects
    assert not (vault.WIKI / "INDEX.md").exists()
    assert not (vault.WIKI / "navigation" / "_INDEX.md").exists()


def test_forme_majoritaire_prefixee(vault):
    # bascule le vault en forme préfixée : les liens d'articles passent en [[wiki/...]]
    nav = vault.WIKI / "navigation"
    nav.joinpath("relevement.md").write_text(
        nav.joinpath("relevement.md").read_text(encoding="utf-8")
        + "\n## Relations\n- [[wiki/navigation/triangulation]] : lien.\n- [[wiki/navigation/maree]] : lien.\n",
        encoding="utf-8",
    )
    res = ib.regenerate(vault, dry_run=False)
    assert res.form == "prefixed"
    doc = (vault.WIKI / "navigation" / "_INDEX.md").read_text(encoding="utf-8")
    assert "[[wiki/navigation/relevement]]" in doc

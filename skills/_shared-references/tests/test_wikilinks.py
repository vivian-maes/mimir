"""Tests des helpers wikilinks (extraction, forme majoritaire, résolution, ancrage)."""

import json

import pytest

import config_loader
import wikilinks as wl


@pytest.fixture
def cfg(tmp_path):
    work = tmp_path / "work"
    (work / "wiki" / "navigation").mkdir(parents=True)
    (work / "reading-grids").mkdir(parents=True)
    cfgp = tmp_path / "wiki.config.json"
    cfgp.write_text(json.dumps({"work_root": str(work)}), encoding="utf-8")
    return config_loader.load_config(cfgp)


# --- extraction ------------------------------------------------------------
def test_extract_alias_et_ancres():
    text = (
        "Voir [[navigation/relevement]] et [[navigation/route-fond|la route]].\n"
        "Ancre titre [[navigation/relevement#Définition]] et intra [[#Ch. 2 — X]].\n"
        "Bloc [[#^abc]] à ignorer.\n"
    )
    assert wl.extract_wikilinks(text) == [
        "navigation/relevement",
        "navigation/route-fond",
        "navigation/relevement",
    ]


def test_majority_form():
    assert wl.majority_form(["navigation/a", "navigation/b", "wiki/x/y"]) == "relative"
    assert wl.majority_form(["wiki/a/b", "wiki/c/d", "navigation/e"]) == "prefixed"
    assert wl.majority_form(["notion-simple"]) == "relative"   # pas de "/" -> ignoré


# --- résolution (normpath + NFD/NFC + confinement) -------------------------
def test_resolve_formes(cfg):
    (cfg.WIKI / "navigation" / "relevement.md").write_text("x", encoding="utf-8")
    (cfg.READING_GRIDS / "nav-cotiere.md").write_text("g", encoding="utf-8")
    src = cfg.WIKI / "navigation" / "_INDEX.md"

    assert wl.resolve(cfg, src, "navigation/relevement") is not None      # relative au wiki
    assert wl.resolve(cfg, src, "reading-grids/nav-cotiere") is not None  # préfixée
    assert wl.resolve(cfg, src, "navigation/inexistant") is None


def test_resolve_normpath_pas_de_faux_positif(cfg):
    (cfg.WIKI / "navigation" / "relevement.md").write_text("x", encoding="utf-8")
    src = cfg.WIKI / "navigation" / "_INDEX.md"
    # un `..` qui sort puis revient doit être normalisé, pas exploser
    assert wl.resolve(cfg, src, "navigation/../navigation/relevement") is not None


def test_resolve_hors_work_root(cfg):
    src = cfg.WIKI / "navigation" / "_INDEX.md"
    assert wl.resolve(cfg, src, "../../../etc/passwd") is None


# --- ancrage chapitre ------------------------------------------------------
def test_chapter_anchor():
    assert wl.chapter_anchor(3, "Se positionner") == "Ch. 3 — Se positionner"

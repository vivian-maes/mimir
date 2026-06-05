"""Tests de la lecture d'article (frontmatter + résumé callout)."""

import json

import pytest

import article_index as ai
import config_loader


@pytest.fixture
def cfg(tmp_path):
    work = tmp_path / "work"
    (work / "wiki" / "navigation").mkdir(parents=True)
    cfgp = tmp_path / "wiki.config.json"
    cfgp.write_text(json.dumps({"work_root": str(work)}), encoding="utf-8")
    return config_loader.load_config(cfgp)


_ARTICLE = """---
title: "Relèvement"
subject: navigation
tags: [navigation]
sources: ["raw/pdfs/nav.pdf.txt#ch3"]
created: 2026-06-04
updated: 2026-06-04
---

# Relèvement

> Mesure de l'angle vers un amer, pour se positionner.

## Définition
Texte de définition.
"""


def test_extract_summary():
    body = "# Relèvement\n\n> Résumé.\n\n## Définition\n> citation interne\n"
    assert ai.extract_summary(body) == "Résumé."
    assert ai.extract_summary("# T\n\n## Définition\nx\n") == ""   # pas de callout avant ##


def test_load_article(cfg):
    (cfg.WIKI / "navigation" / "relevement.md").write_text(_ARTICLE, encoding="utf-8")
    info = ai.load_article(cfg, "navigation/relevement")
    assert info.exists
    assert info.title == "Relèvement"
    assert info.summary == "Mesure de l'angle vers un amer, pour se positionner."
    assert info.sources == ["raw/pdfs/nav.pdf.txt#ch3"]
    assert info.tags == ["navigation"]


def test_load_article_absent(cfg):
    info = ai.load_article(cfg, "navigation/inexistant")
    assert not info.exists
    assert info.title == "inexistant"
    assert info.sources == []

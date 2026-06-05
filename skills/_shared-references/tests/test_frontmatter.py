"""Tests du parseur de frontmatter partagé (promu depuis article_writer, P3)."""

import frontmatter as fm


_ARTICLE = """---
title: "Relèvement"
subject: navigation
tags: [navigation, technique]
sources: ["raw/pdfs/nav.pdf.txt#ch3", "raw/web/amers.md"]
created: 2026-06-04
updated: 2026-06-04
---

# Relèvement

> Mesure de l'angle vers un amer.

## Définition
Texte.
"""


def test_parse_scalaires_et_listes():
    front, body = fm.parse_frontmatter(_ARTICLE)
    assert front["title"] == "Relèvement"          # guillemets retirés
    assert front["subject"] == "navigation"
    assert front["tags"] == ["navigation", "technique"]
    assert front["sources"] == ["raw/pdfs/nav.pdf.txt#ch3", "raw/web/amers.md"]
    assert front["created"] == "2026-06-04"
    assert body.startswith("# Relèvement")          # ligne vide initiale consommée


def test_sans_frontmatter():
    front, body = fm.parse_frontmatter("# Titre\n\ntexte\n")
    assert front == {}
    assert body == "# Titre\n\ntexte\n"


def test_parse_list_tolerant():
    assert fm.parse_list('[a, "b c", \'d\']') == ["a", "b c", "d"]
    assert fm.parse_list("[]") == []
    assert fm.parse_list("a, b") == ["a", "b"]       # crochets optionnels


def test_list_keys_personnalisables():
    text = "---\nfoo: [x, y]\n---\nbody\n"
    front, _ = fm.parse_frontmatter(text, list_keys=("foo",))
    assert front["foo"] == ["x", "y"]
    front2, _ = fm.parse_frontmatter(text)            # foo non listé -> scalaire brut
    assert front2["foo"] == "[x, y]"

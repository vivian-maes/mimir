#!/usr/bin/env python3
"""Slugs ASCII kebab-case et helpers de normalisation NFD/NFC.

Conventions Mimir (SPEC §12.2, §12.3) :

- Les **noms de fichiers** sont des slugs ASCII kebab-case ; le titre affichable
  (avec accents) est conservé dans le frontmatter, jamais dans le nom de fichier.
- macOS/APFS stocke les noms de fichiers en **NFD** (accents décomposés) tandis
  que les wikilinks Obsidian sont en **NFC** (accents composés) : comparer deux
  chemins sans normaliser produit de faux « liens morts ». `same_file()` règle ça.

Évolution de `slugify()` (`_old-kb-mimir-skills/kb-pdf-extract/scripts/`), corrigé
pour produire réellement de l'ASCII (l'ancienne version gardait les accents, `\\w`
étant Unicode par défaut en Python 3).
"""

from __future__ import annotations

import re
import unicodedata

_PUNCT_RE = re.compile(r"[^a-z0-9\s-]")
_DASH_RE = re.compile(r"[-\s]+")

#: Longueur maximale d'un slug (compatibilité noms de fichiers / wikilinks).
SLUG_MAX_LEN = 80


def strip_accents(s: str) -> str:
    """Retire les diacritiques en décomposant (NFKD) puis en ne gardant que l'ASCII."""
    decomposed = unicodedata.normalize("NFKD", s)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def slugify(s: str, max_len: int = SLUG_MAX_LEN) -> str:
    """Transforme une chaîne en slug ASCII kebab-case.

    >>> slugify("Baromètre")
    'barometre'
    >>> slugify("Brevet de Conduite")
    'brevet-de-conduite'
    >>> slugify("Route & Fond")
    'route-fond'
    """
    s = strip_accents(s).lower().strip()
    s = _PUNCT_RE.sub("", s)
    s = _DASH_RE.sub("-", s)
    s = s.strip("-")
    return s[:max_len].rstrip("-")


def normalize_nfc(s: str) -> str:
    """Forme composée (NFC) — celle utilisée par les wikilinks Obsidian."""
    return unicodedata.normalize("NFC", s)


def normalize_nfd(s: str) -> str:
    """Forme décomposée (NFD) — celle utilisée par macOS/APFS pour les noms de fichiers."""
    return unicodedata.normalize("NFD", s)


def same_file(a: str, b: str) -> bool:
    """Compare deux noms/chemins indépendamment de la normalisation NFD/NFC.

    Évite les faux négatifs APFS : `same_file("baromètre", "baromètre")` -> True.
    """
    return normalize_nfc(a) == normalize_nfc(b)


if __name__ == "__main__":  # petite démo / autotest
    import doctest

    failures, _ = doctest.testmod(verbose=False)
    if not failures:
        print("slug.py : doctests OK")

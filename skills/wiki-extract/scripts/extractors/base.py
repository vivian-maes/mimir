#!/usr/bin/env python3
"""Contrat commun des extracteurs (SPEC §6).

Chaque format (PDF/EPUB/web) est un module exposant :

    SUPPORTED_EXTS : set[str]          # ex. {".pdf"} ; vide pour le web (routé par URL)
    def extract(source, *, lang="fra+eng") -> ExtractResult

L'extracteur renvoie un `ExtractResult` ; il **n'écrit rien** sur disque (c'est
l'orchestrateur qui confine et écrit). Règle d'or (§12.5) : ne JAMAIS inventer de
contenu — si l'extraction est impossible (couche texte absente ET OCR indisponible,
fetch échoué…), lever `ExtractorError`/`ExtractorUnavailable`, pas de sortie vide.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


class ExtractorError(RuntimeError):
    """Échec d'extraction explicite (jamais de contenu inventé)."""


class ExtractorUnavailable(ExtractorError):
    """Outils requis absents (ex. couche texte vide ET aucun moteur OCR)."""


@dataclass(frozen=True)
class Chapter:
    """Entrée de chapitrage ORDONNÉE (alimente la grille de lecture, Phase 3)."""

    order: int
    title: str
    page_start: int | None = None  # None pour le web (headings sans pagination)
    page_end: int | None = None


@dataclass(frozen=True)
class Asset:
    """Image extraite/téléchargée. `original_ref` = lien d'origine à réécrire (web)."""

    filename: str  # nom de fichier proposé (ASCII), ex. "p012-img03.png"
    data: bytes
    original_ref: str | None = None


@dataclass(frozen=True)
class ExtractResult:
    """Résultat d'extraction d'une source — sérialisé ensuite dans raw/<type>/."""

    raw_content: str  # texte (.pdf.txt/.epub.txt) OU markdown inline (web)
    content_ext: Literal["pdf.txt", "epub.txt", "md"]
    metadata: dict  # title, source, type, created, ocr(bool), pages, lang…
    structure: list[Chapter]  # chapitrage ordonné (peut être [])
    assets: list[Asset] = field(default_factory=list)
    doc_type: Literal["pdfs", "epubs", "web"] = "pdfs"

#!/usr/bin/env python3
"""Extracteur Web/URL (SPEC §4.4, §6).

Nettoie une page (nav/pub/cookies) → **markdown inline** (anti link-rot) ;
images **localisées** (téléchargées), liens réécrits en relatif par l'orchestrateur.
Le frontmatter YAML est ajouté par l'orchestrateur à partir de `metadata`.

Préféré : `requests` + `trafilatura`. Fallbacks : `bs4` + `markdownify`, puis
`urllib` + `html.parser`. Échec de fetch/extraction → `ExtractorError` (jamais
de contenu inventé).
"""

from __future__ import annotations

import re
from datetime import date
from urllib.parse import urljoin, urlparse

from .base import Asset, ExtractorError, ExtractResult

SUPPORTED_EXTS: set[str] = set()  # routage par schéma URL, pas par extension

_UA = {"User-Agent": "Mozilla/5.0 (compatible; MimirWikiExtract/1.0)"}
_MD_IMG = re.compile(r"!\[[^\]]*\]\(([^)\s]+)")
_TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)


# --- réseau (isolé pour faciliter le test sans réseau) --------------------
def _fetch_html(url: str) -> str:
    try:
        import requests

        r = requests.get(url, headers=_UA, timeout=20)
        r.raise_for_status()
        return r.text
    except ImportError:
        from urllib.request import Request, urlopen

        with urlopen(Request(url, headers=_UA), timeout=20) as resp:  # noqa: S310
            charset = resp.headers.get_content_charset() or "utf-8"
            return resp.read().decode(charset, "replace")
    except Exception as exc:  # erreur réseau/HTTP -> explicite
        raise ExtractorError(f"Échec du téléchargement de {url} : {exc}") from exc


def _fetch_bytes(url: str) -> bytes | None:
    try:
        import requests

        r = requests.get(url, headers=_UA, timeout=20)
        r.raise_for_status()
        return r.content
    except ImportError:
        from urllib.request import Request, urlopen

        try:
            with urlopen(Request(url, headers=_UA), timeout=20) as resp:  # noqa: S310
                return resp.read()
        except Exception:
            return None
    except Exception:
        return None  # image manquante : on n'échoue pas tout le clipping


# --- HTML -> markdown ------------------------------------------------------
def _title(html: str) -> str | None:
    m = _TITLE_RE.search(html)
    return re.sub(r"\s+", " ", m.group(1)).strip() if m else None


def _to_markdown(html: str, url: str) -> str:
    # 1) trafilatura (qualité maximale)
    try:
        import trafilatura

        md = trafilatura.extract(
            html, output_format="markdown", include_images=True,
            include_links=True, url=url,
        )
        if md and md.strip():
            return md
    except Exception:
        pass
    # 2) bs4 + markdownify
    try:
        from bs4 import BeautifulSoup
        from markdownify import markdownify

        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["script", "style", "nav", "footer", "aside", "form"]):
            tag.decompose()
        main = soup.find("article") or soup.find("main") or soup.body or soup
        md = markdownify(str(main), heading_style="ATX")
        if md and md.strip():
            return re.sub(r"\n{3,}", "\n\n", md).strip()
    except Exception:
        pass
    # 3) stdlib minimal (texte)
    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        raise ExtractorError(f"Aucun contenu exploitable extrait de {url}.")
    return text


def _localize_images(markdown: str, url: str):
    """Télécharge les images référencées ; renvoie (assets, markdown inchangé).

    Les `original_ref` valent exactement la chaîne présente dans le markdown ;
    c'est l'orchestrateur qui réécrit ces liens vers `_assets/` (confinement).
    """
    assets: list[Asset] = []
    seen: set[str] = set()
    for src in _MD_IMG.findall(markdown):
        if src in seen or src.startswith("data:"):
            continue
        seen.add(src)
        absolute = urljoin(url, src)
        data = _fetch_bytes(absolute)
        if data is None:
            continue
        name = urlparse(absolute).path.rsplit("/", 1)[-1] or "image"
        assets.append(Asset(filename=name, data=data, original_ref=src))
    return assets, markdown


def extract(source, *, lang: str = "fra+eng") -> ExtractResult:
    url = str(source)
    html = _fetch_html(url)
    markdown = _to_markdown(html, url)
    assets, markdown = _localize_images(markdown, url)
    return ExtractResult(
        raw_content=markdown,
        content_ext="md",
        metadata={
            "title": _title(html) or url,
            "source": url,
            "type": "web",
            "created": date.today().isoformat(),
        },
        structure=[],  # headings de page : non exploités en P1
        assets=assets,
        doc_type="web",
    )

#!/usr/bin/env python3
"""Extracteur EPUB (SPEC §6).

La **spine** (ordre de lecture déclaré dans le `.opf`) = chapitrage natif → `.toc.json`.
Texte concaténé → `.epub.txt` ; images du conteneur → `_assets/`.

Préféré : `ebooklib` + `BeautifulSoup`. Fallback **stdlib pur** (`zipfile` +
`xml.etree` + `html.parser`) — aucune dépendance requise. Pas d'OCR (`ocr:false`).
"""

from __future__ import annotations

import posixpath
import zipfile
from html.parser import HTMLParser
from pathlib import Path
from xml.etree import ElementTree as ET

from .base import Asset, Chapter, ExtractorError, ExtractResult

SUPPORTED_EXTS = {".epub"}

_CONTAINER = "META-INF/container.xml"
_SKIP_TAGS = {"script", "style", "head"}
_HEADING_TAGS = {"h1", "h2", "h3", "h4", "h5", "h6"}
_BLOCK_TAGS = {"p", "div", "br", "li", "tr", "section"} | _HEADING_TAGS


class _TextHTMLParser(HTMLParser):
    """Extrait le texte d'un XHTML : ignore script/style, saute des lignes aux blocs."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self._parts: list[str] = []
        self._skip = 0
        self.title: str | None = None  # <title> du <head>
        self.heading: str | None = None  # 1er titre <h1>–<h6> du corps (repli)
        self._in_title = False
        self._in_heading = False

    def handle_starttag(self, tag, attrs):
        if tag in _SKIP_TAGS:
            self._skip += 1
        if tag == "title":
            self._in_title = True
        if tag in _HEADING_TAGS:
            self._in_heading = True
        if tag in _BLOCK_TAGS:
            self._parts.append("\n")

    def handle_endtag(self, tag):
        if tag in _SKIP_TAGS and self._skip:
            self._skip -= 1
        if tag == "title":
            self._in_title = False
        if tag in _HEADING_TAGS:
            self._in_heading = False

    def handle_data(self, data):
        if self._in_title and not self.title:  # capturer même si <title> est dans <head> (skip)
            t = data.strip()
            if t:
                self.title = t
        if self._skip:
            return
        if self._in_heading and not self.heading:
            t = data.strip()
            if t:
                self.heading = t
        self._parts.append(data)

    def chapter_title(self) -> str | None:
        """Titre du chapitre : <title> sinon 1er <h1>–<h6> (ebooklib vide le <head>)."""
        return self.title or self.heading

    def text(self) -> str:
        raw = "".join(self._parts)
        lines = [ln.strip() for ln in raw.splitlines()]
        out: list[str] = []
        for ln in lines:
            if ln or (out and out[-1]):  # compacte les lignes vides multiples
                out.append(ln)
        return "\n".join(out).strip()


# --- chemin préféré : ebooklib --------------------------------------------
def _extract_ebooklib(path: Path) -> ExtractResult:
    import ebooklib
    from ebooklib import epub

    book = epub.read_epub(str(path))
    title = (book.get_metadata("DC", "title") or [("",)])[0][0] or path.stem

    chapters: list[Chapter] = []
    texts: list[str] = []
    order = 0
    for idref, _linear in book.spine:
        item = book.get_item_with_id(idref)
        if item is None or item.get_type() != ebooklib.ITEM_DOCUMENT:
            continue
        parser = _TextHTMLParser()
        parser.feed(item.get_content().decode("utf-8", "replace"))
        chunk = parser.text()
        if not chunk:
            continue
        order += 1
        chapters.append(Chapter(order=order, title=parser.chapter_title() or f"Section {order}"))
        texts.append(chunk)

    assets = [
        Asset(filename=Path(it.get_name()).name, data=it.get_content())
        for it in book.get_items_of_type(ebooklib.ITEM_IMAGE)
    ]
    content = "\n\n".join(texts)
    if not content.strip():
        raise ExtractorError(f"EPUB sans texte exploitable : {path}")
    return ExtractResult(
        raw_content=content,
        content_ext="epub.txt",
        metadata={"title": title, "source": str(path), "type": "epub", "ocr": False},
        structure=chapters,
        assets=assets,
        doc_type="epubs",
    )


# --- fallback stdlib -------------------------------------------------------
def _opf_path(zf: zipfile.ZipFile) -> str:
    root = ET.fromstring(zf.read(_CONTAINER))
    rootfile = root.find(".//{*}rootfile")
    if rootfile is None or not rootfile.get("full-path"):
        raise ExtractorError("EPUB invalide : rootfile introuvable dans container.xml")
    return rootfile.get("full-path")


def _extract_stdlib(path: Path) -> ExtractResult:
    with zipfile.ZipFile(path) as zf:
        opf = _opf_path(zf)
        opf_dir = posixpath.dirname(opf)
        root = ET.fromstring(zf.read(opf))

        # titre
        title_el = root.find(".//{http://purl.org/dc/elements/1.1/}title")
        title = (title_el.text if title_el is not None and title_el.text else path.stem).strip()

        # manifest : id -> (href, media-type)
        manifest: dict[str, tuple[str, str]] = {}
        for item in root.findall(".//{*}manifest/{*}item"):
            iid = item.get("id")
            href = item.get("href")
            if iid and href:
                manifest[iid] = (href, item.get("media-type", ""))

        # spine ordonnée
        chapters: list[Chapter] = []
        texts: list[str] = []
        order = 0
        for itemref in root.findall(".//{*}spine/{*}itemref"):
            idref = itemref.get("idref")
            if not idref or idref not in manifest:
                continue
            href, media = manifest[idref]
            if "html" not in media and not href.endswith((".xhtml", ".html", ".htm")):
                continue
            full = posixpath.normpath(posixpath.join(opf_dir, href)) if opf_dir else href
            try:
                raw = zf.read(full).decode("utf-8", "replace")
            except KeyError:
                continue
            parser = _TextHTMLParser()
            parser.feed(raw)
            chunk = parser.text()
            if not chunk:
                continue
            order += 1
            chapters.append(Chapter(order=order, title=parser.chapter_title() or f"Section {order}"))
            texts.append(chunk)

        # images du manifest
        assets: list[Asset] = []
        for href, media in manifest.values():
            if media.startswith("image/"):
                full = posixpath.normpath(posixpath.join(opf_dir, href)) if opf_dir else href
                try:
                    assets.append(Asset(filename=posixpath.basename(href), data=zf.read(full)))
                except KeyError:
                    continue

    content = "\n\n".join(texts)
    if not content.strip():
        raise ExtractorError(f"EPUB sans texte exploitable : {path}")
    return ExtractResult(
        raw_content=content,
        content_ext="epub.txt",
        metadata={"title": title, "source": str(path), "type": "epub", "ocr": False},
        structure=chapters,
        assets=assets,
        doc_type="epubs",
    )


def extract(source, *, lang: str = "fra+eng") -> ExtractResult:
    path = Path(str(source))
    if not path.is_file():
        raise ExtractorError(f"Fichier EPUB introuvable : {path}")
    try:
        import ebooklib  # noqa: F401

        return _extract_ebooklib(path)
    except ExtractorError:
        raise
    except Exception:
        # ebooklib absent ou en échec -> fallback stdlib (robuste)
        return _extract_stdlib(path)

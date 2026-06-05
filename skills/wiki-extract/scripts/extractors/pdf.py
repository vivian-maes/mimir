#!/usr/bin/env python3
"""Extracteur PDF (SPEC §6, §12.5).

Stratégie : tenter la **couche texte** ; si absente/quasi vide, basculer en **OCR
auto**. Ne JAMAIS inventer de contenu — sans couche texte ET sans moteur OCR
disponible → `ExtractorUnavailable` (rien n'est écrit en aval).

Préféré : PyMuPDF (`fitz`) pour texte (`get_text("text")`), TOC natif (`get_toc`)
et images. Fallback : poppler (`pdftotext`, `pdfinfo`, `pdfimages`). OCR :
`ocrmypdf` (préféré) ou `pdftoppm` + `tesseract`.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

from .base import Asset, Chapter, ExtractorError, ExtractorUnavailable, ExtractResult

SUPPORTED_EXTS = {".pdf"}

#: En-dessous de ce volume de texte, on considère le PDF « scanné » et on tente l'OCR.
def _ocr_threshold(pages: int) -> int:
    return max(100, 5 * pages)


def _have(cmd: str) -> bool:
    return shutil.which(cmd) is not None


# --- couche texte ----------------------------------------------------------
def _text_pages_fitz(path: Path) -> tuple[str, int, "object|None"]:
    import fitz  # PyMuPDF

    doc = fitz.open(str(path))
    parts = [page.get_text("text") for page in doc]  # "text" : jamais "dict"/"blocks"
    return "\n\n".join(parts), doc.page_count, doc


def _text_pages_poppler(path: Path) -> tuple[str, int]:
    if not _have("pdftotext"):
        raise ExtractorUnavailable("Ni PyMuPDF ni pdftotext disponibles pour lire le PDF.")
    text = subprocess.run(
        ["pdftotext", "-enc", "UTF-8", str(path), "-"],
        capture_output=True, text=True, check=False,
    ).stdout
    pages = 0
    if _have("pdfinfo"):
        info = subprocess.run(["pdfinfo", str(path)], capture_output=True, text=True, check=False).stdout
        for line in info.splitlines():
            if line.startswith("Pages:"):
                pages = int(line.split(":", 1)[1].strip() or 0)
                break
    return text, pages


# --- OCR -------------------------------------------------------------------
def _ocr_text(path: Path, lang: str) -> str:
    """OCR auto. Lève `ExtractorUnavailable` si aucun moteur n'est disponible."""
    if _have("ocrmypdf"):
        with tempfile.TemporaryDirectory() as td:
            sidecar = Path(td) / "ocr.txt"
            out_pdf = Path(td) / "out.pdf"
            proc = subprocess.run(
                ["ocrmypdf", "-l", lang, "--sidecar", str(sidecar), "--quiet",
                 "--force-ocr", str(path), str(out_pdf)],
                capture_output=True, text=True, check=False,
            )
            if sidecar.is_file():
                txt = sidecar.read_text(encoding="utf-8", errors="replace")
                if txt.strip():
                    return txt
            raise ExtractorError(f"OCR (ocrmypdf) sans texte exploitable : {proc.stderr[:200]}")

    if _have("pdftoppm") and _have("tesseract"):
        with tempfile.TemporaryDirectory() as td:
            prefix = Path(td) / "page"
            subprocess.run(["pdftoppm", "-png", "-r", "300", str(path), str(prefix)],
                           capture_output=True, check=False)
            out = []
            for png in sorted(Path(td).glob("page*.png")):
                r = subprocess.run(["tesseract", str(png), "stdout", "-l", lang],
                                   capture_output=True, text=True, check=False)
                out.append(r.stdout)
            txt = "\n\n".join(out)
            if txt.strip():
                return txt
            raise ExtractorError("OCR (tesseract) sans texte exploitable.")

    raise ExtractorUnavailable(
        "Couche texte absente et aucun moteur OCR disponible (installer ocrmypdf "
        "ou tesseract+pdftoppm). Aucun contenu inventé."
    )


# --- chapitrage ------------------------------------------------------------
def _toc_fitz(doc, pages: int) -> list[Chapter]:
    toc = doc.get_toc(simple=True)  # [(level, title, page), …] ; page 1-based
    tops = [(t.strip(), p) for (lvl, t, p) in toc if lvl == 1 and t.strip()]
    chapters: list[Chapter] = []
    for i, (title, start) in enumerate(tops):
        end = (tops[i + 1][1] - 1) if i + 1 < len(tops) else pages
        chapters.append(Chapter(order=i + 1, title=title, page_start=start, page_end=end))
    return chapters


# --- images ----------------------------------------------------------------
def _images_fitz(doc) -> list[Asset]:
    assets: list[Asset] = []
    seen: set[int] = set()
    for pno in range(doc.page_count):
        page = doc[pno]
        for idx, img in enumerate(page.get_images(full=True), start=1):
            xref = img[0]
            if xref in seen:
                continue
            seen.add(xref)
            try:
                info = doc.extract_image(xref)
            except Exception:
                continue
            assets.append(Asset(filename=f"p{pno + 1:03d}-img{idx:02d}.{info['ext']}", data=info["image"]))
    return assets


def _images_poppler(path: Path) -> list[Asset]:
    if not _have("pdfimages"):
        return []
    assets: list[Asset] = []
    with tempfile.TemporaryDirectory() as td:
        prefix = Path(td) / "img"
        subprocess.run(["pdfimages", "-all", "-p", str(path), str(prefix)],
                       capture_output=True, check=False)
        for f in sorted(Path(td).iterdir()):
            assets.append(Asset(filename=f.name, data=f.read_bytes()))
    return assets


# --- point d'entrée --------------------------------------------------------
def extract(source, *, lang: str = "fra+eng") -> ExtractResult:
    path = Path(str(source))
    if not path.is_file():
        raise ExtractorError(f"Fichier PDF introuvable : {path}")

    doc = None
    try:
        import fitz  # noqa: F401

        text, pages, doc = _text_pages_fitz(path)
    except ExtractorError:
        raise
    except Exception:
        text, pages = _text_pages_poppler(path)

    ocr = False
    if len(text.strip()) < _ocr_threshold(pages):
        text = _ocr_text(path, lang)  # lève ExtractorUnavailable si pas de moteur
        ocr = True

    if doc is not None:
        chapters = _toc_fitz(doc, pages)
        assets = _images_fitz(doc)
    else:
        chapters = []  # heuristique de titres non fiable -> état honnête (vide)
        assets = _images_poppler(path)

    return ExtractResult(
        raw_content=text,
        content_ext="pdf.txt",
        metadata={"title": path.stem, "source": str(path), "type": "pdf",
                  "pages": pages, "ocr": ocr, "lang": lang if ocr else None},
        structure=chapters,
        assets=assets,
        doc_type="pdfs",
    )

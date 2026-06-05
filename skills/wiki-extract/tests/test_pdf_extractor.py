"""Tests de l'extracteur PDF : couche texte, TOC, OCR auto, indisponibilité OCR."""

import importlib.util
import shutil
import tempfile
from pathlib import Path

import pytest

from extractors import pdf
from extractors.base import ExtractorUnavailable

_has_fitz = importlib.util.find_spec("fitz") is not None
_has_ocr = shutil.which("ocrmypdf") is not None or (
    shutil.which("tesseract") is not None and shutil.which("pdftoppm") is not None
)
_has_text = _has_fitz or shutil.which("pdftotext") is not None

pytestmark = pytest.mark.skipif(not _has_fitz, reason="PyMuPDF requis pour générer les fixtures PDF")


@pytest.fixture
def text_pdf(tmp_path: Path) -> Path:
    import fitz

    doc = fitz.open()
    page = doc.new_page()
    lignes = [
        "Navigation cotiere : le relevement d'un amer permet de se positionner.",
        "Le compas magnetique donne le cap ; la route fond integre courant et derive.",
        "Trois relevements simultanes donnent un point par triangulation fiable.",
        "Ce chapitre detaille les instruments et les methodes de positionnement.",
    ]
    for i, ln in enumerate(lignes):
        page.insert_text((72, 72 + 24 * i), ln, fontsize=12)
    # un signet de niveau 1 (TOC natif)
    doc.set_toc([[1, "Se positionner", 1]])
    out = tmp_path / "nav.pdf"
    doc.save(str(out))
    return out


@pytest.fixture
def ocr_workdir(monkeypatch):
    """Répertoire de travail OCR sous $HOME.

    Le tmp du harness (`/tmp/claude-501`, perms 700 + attribut étendu) bloque
    l'ouverture de fichiers par le sous-process leptonica/tesseract. On travaille
    donc sous $HOME et on y route `TMPDIR` (temporaires internes d'ocrmypdf).
    Sans rapport avec la prod : `/tmp` y est normalement lisible.
    """
    d = Path(tempfile.mkdtemp(prefix="mimir-ocr-", dir=Path.home()))
    monkeypatch.setenv("TMPDIR", str(d))
    yield d
    shutil.rmtree(d, ignore_errors=True)


@pytest.fixture
def scanned_pdf(ocr_workdir: Path) -> Path:
    """PDF image-only (aucune couche texte) : on rend une page texte en image."""
    import fitz

    src = fitz.open()
    p = src.new_page()
    p.insert_text((72, 100), "OCRABLE HELLO WORLD", fontsize=40)
    pix = p.get_pixmap(dpi=200)

    img_doc = fitz.open()
    page = img_doc.new_page(width=pix.width, height=pix.height)
    page.insert_image(page.rect, pixmap=pix)
    out = ocr_workdir / "scan.pdf"
    img_doc.save(str(out))
    return out


@pytest.mark.skipif(not _has_text, reason="aucun moteur d'extraction texte PDF")
def test_pdf_texte(text_pdf: Path):
    res = pdf.extract(text_pdf)
    assert res.content_ext == "pdf.txt" and res.doc_type == "pdfs"
    assert res.metadata["ocr"] is False
    assert "relevement" in res.raw_content.lower()
    assert res.metadata["pages"] == 1
    # TOC natif capté
    assert res.structure and res.structure[0].title == "Se positionner"
    assert res.structure[0].page_start == 1 and res.structure[0].page_end == 1


@pytest.mark.skipif(not _has_ocr, reason="aucun moteur OCR (ocrmypdf / tesseract+pdftoppm)")
def test_pdf_ocr_auto(scanned_pdf: Path):
    res = pdf.extract(scanned_pdf, lang="eng")
    assert res.metadata["ocr"] is True
    assert "OCRABLE" in res.raw_content.upper()


def test_ocr_indisponible_leve_explicitement(scanned_pdf: Path, monkeypatch):
    # simule l'absence totale de moteur OCR -> ExtractorUnavailable (rien inventé)
    monkeypatch.setattr(pdf.shutil, "which", lambda name: None)
    with pytest.raises(ExtractorUnavailable):
        pdf.extract(scanned_pdf, lang="eng")

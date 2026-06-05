"""Tests de l'extracteur EPUB : chemin ebooklib + fallback stdlib (sans skip)."""

import zipfile
from pathlib import Path

import pytest

from extractors import epub
from extractors.base import ExtractorError

_CONTAINER = """<?xml version="1.0"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles><rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/></rootfiles>
</container>"""

_OPF = """<?xml version="1.0"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="id">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:title>Mon Livre de Test</dc:title>
    <dc:identifier id="id">urn:uuid:42</dc:identifier>
  </metadata>
  <manifest>
    <item id="c1" href="ch1.xhtml" media-type="application/xhtml+xml"/>
    <item id="c2" href="ch2.xhtml" media-type="application/xhtml+xml"/>
    <item id="img" href="images/fig.png" media-type="image/png"/>
  </manifest>
  <spine>
    <itemref idref="c1"/>
    <itemref idref="c2"/>
  </spine>
</package>"""

_CH1 = """<html xmlns="http://www.w3.org/1999/xhtml"><head><title>Instruments</title>
<style>.x{}</style></head><body><h1>Instruments</h1><p>Le compas magnétique.</p>
<script>ignore()</script></body></html>"""

_CH2 = """<html xmlns="http://www.w3.org/1999/xhtml"><head><title>Se positionner</title></head>
<body><h1>Se positionner</h1><p>Le relèvement d'un amer.</p></body></html>"""


@pytest.fixture
def epub_file(tmp_path: Path) -> Path:
    p = tmp_path / "livre.epub"
    with zipfile.ZipFile(p, "w") as zf:
        # mimetype en premier, non compressé (recommandation EPUB)
        zf.writestr("mimetype", "application/epub+zip", compress_type=zipfile.ZIP_STORED)
        zf.writestr("META-INF/container.xml", _CONTAINER)
        zf.writestr("OEBPS/content.opf", _OPF)
        zf.writestr("OEBPS/ch1.xhtml", _CH1)
        zf.writestr("OEBPS/ch2.xhtml", _CH2)
        zf.writestr("OEBPS/images/fig.png", b"\x89PNG\r\n\x1a\n-fake")
    return p


def _assert_result(res):
    assert res.content_ext == "epub.txt"
    assert res.doc_type == "epubs"
    assert res.metadata["ocr"] is False
    assert res.metadata["title"] == "Mon Livre de Test"
    # spine = 2 chapitres ordonnés
    assert [c.order for c in res.structure] == [1, 2]
    assert res.structure[0].title == "Instruments"
    assert res.structure[1].title == "Se positionner"
    # texte concaténé, sans script/style
    assert "compas magnétique" in res.raw_content
    assert "relèvement d'un amer" in res.raw_content
    assert "ignore()" not in res.raw_content
    # image extraite
    assert any(a.filename == "fig.png" for a in res.assets)


def test_extract_public(epub_file: Path):
    # chemin par défaut (ebooklib présent dans l'env de dev)
    _assert_result(epub.extract(epub_file))


def test_extract_stdlib_fallback(epub_file: Path):
    # force le fallback stdlib (aucune dépendance)
    _assert_result(epub._extract_stdlib(epub_file))


def test_fichier_absent(tmp_path: Path):
    with pytest.raises(ExtractorError):
        epub.extract(tmp_path / "nope.epub")

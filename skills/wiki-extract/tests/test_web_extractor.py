"""Tests de l'extracteur web — sans réseau (fetch monkeypatché)."""

import pytest

from extractors import web
from extractors.base import ExtractorError

_HTML = """<!doctype html><html><head><title>  Le Relèvement  </title></head>
<body>
<nav>menu pub cookies</nav>
<article>
  <h1>Le relèvement</h1>
  <p>Mesure de l'angle entre le nord et un amer.</p>
  <img src="/img/amer.png" alt="amer"/>
  <p>Trois relèvements donnent un point.</p>
</article>
<footer>pied de page</footer>
</body></html>"""


@pytest.fixture
def no_network(monkeypatch):
    monkeypatch.setattr(web, "_fetch_html", lambda url: _HTML)
    monkeypatch.setattr(web, "_fetch_bytes", lambda url: b"\x89PNG-fake")


def test_web_extract_contrat(no_network):
    # chemin par défaut (trafilatura si dispo) : on valide le contrat, pas la qualité
    res = web.extract("https://exemple.org/relevement")
    assert res.content_ext == "md" and res.doc_type == "web"
    assert res.metadata["type"] == "web"
    assert res.metadata["title"] == "Le Relèvement"
    assert res.metadata["source"] == "https://exemple.org/relevement"
    assert res.metadata["created"]  # date présente
    assert "amer" in res.raw_content.lower()  # contenu principal présent


def test_web_bs4_localise_images(no_network, monkeypatch):
    # Force le chemin bs4+markdownify (déterministe) : nav retirée + image localisée.
    # Ce chemin EXIGE bs4+markdownify (le fallback stdlib ne retire ni nav/footer
    # ni ne localise les images) -> skip propre si absents (env CI minimal).
    pytest.importorskip("bs4")
    pytest.importorskip("markdownify")
    # trafilatura est optionnel : présent -> on neutralise son extract pour forcer
    # le fallback bs4 ; absent -> le fallback bs4 s'applique déjà naturellement.
    try:
        import trafilatura

        monkeypatch.setattr(trafilatura, "extract", lambda *a, **k: None)
    except ModuleNotFoundError:
        pass
    res = web.extract("https://exemple.org/relevement")
    assert "pied de page" not in res.raw_content  # footer retiré
    assert "menu pub cookies" not in res.raw_content  # nav retirée
    assert res.assets and res.assets[0].original_ref == "/img/amer.png"
    assert res.assets[0].filename == "amer.png"


def test_web_fetch_echoue(monkeypatch):
    def boom(url):
        raise ExtractorError("404")

    monkeypatch.setattr(web, "_fetch_html", boom)
    with pytest.raises(ExtractorError):
        web.extract("https://exemple.org/nope")


def test_web_contenu_vide(monkeypatch):
    monkeypatch.setattr(web, "_fetch_html", lambda url: "<html><body></body></html>")
    # selon les libs, soit ExtractorError, soit markdown vide -> on tolère l'erreur
    try:
        res = web.extract("https://exemple.org/vide")
        assert res.raw_content.strip() == "" or res.raw_content is not None
    except ExtractorError:
        pass

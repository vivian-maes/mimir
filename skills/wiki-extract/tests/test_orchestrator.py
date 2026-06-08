"""Tests du cœur de l'orchestrateur (DoD Phase 1) via un extracteur factice.

Couvre, sans aucune lib lourde : routage, écriture raw/<type>/ complète, move
qui vide `_inbox/`, déduplication par SHA (suppression du re-dépôt), suffixage
`-2`, confinement (rien hors raw/+_inbox/), reprise sur crash (rejeu sans doublon).
"""

import json
from pathlib import Path

import pytest

import config_loader
import wiki_extract
from sync import locking as inbox_lock
from extractors.base import Asset, Chapter, ExtractResult, ExtractorError


@pytest.fixture(autouse=True)
def _lock_in_tmp(tmp_path, monkeypatch):
    """Verrou hors ~/.cache réel et hors work_root."""
    monkeypatch.setattr(inbox_lock, "_DEFAULT_LOCK", tmp_path / "lock" / "wiki-sync.lock")


@pytest.fixture
def cfg(tmp_path):
    work = tmp_path / "work"
    work.mkdir()
    (work / "_inbox").mkdir()
    cfgp = tmp_path / "wiki.config.json"
    cfgp.write_text(json.dumps({"work_root": str(work)}), encoding="utf-8")
    return config_loader.load_config(cfgp)


def _install_fake(monkeypatch, *, content, content_ext="pdf.txt", doc_type="pdfs",
                  assets=None, structure=None, error=None, title="Titre"):
    class Fake:
        SUPPORTED_EXTS = set()

        @staticmethod
        def extract(source, *, lang="fra+eng"):
            if error:
                raise error
            return ExtractResult(
                raw_content=content,
                content_ext=content_ext,
                metadata={"title": title, "pages": 3, "ocr": False, "source": str(source)},
                structure=structure if structure is not None else [Chapter(1, "Ch1", 1, 3)],
                assets=assets or [],
                doc_type=doc_type,
            )

    monkeypatch.setattr(wiki_extract.extractors, "get_extractor", lambda src: Fake)


def _drop(cfg, name, data=b"%PDF-binaire"):
    p = cfg.INBOX / name
    p.write_bytes(data)
    return p


# --- robustesse _inbox/ : les intrus n'interrompent pas le scan -----------
def test_scan_inbox_trie_supportes_et_intrus(cfg):
    """`.pdf`/`.epub` → à extraire ; `README.md`/`.txt` → ignorés ; `.`/.DS_Store écartés."""
    _drop(cfg, "guide.pdf")
    _drop(cfg, "livre.epub")
    _drop(cfg, "README.md", data=b"# procedure")
    _drop(cfg, "notes.txt", data=b"texte")
    _drop(cfg, ".DS_Store", data=b"\x00")
    to_extract, skipped = wiki_extract.scan_inbox(cfg)
    assert sorted(p.name for p in to_extract) == ["guide.pdf", "livre.epub"]
    assert sorted(p.name for p in skipped) == ["README.md", "notes.txt"]  # .DS_Store ni l'un ni l'autre


def test_run_ne_crashe_pas_sur_readme(cfg, monkeypatch):
    """Un README.md dans `_inbox/` ne fait plus échouer le batch ; le .pdf est traité."""
    _install_fake(monkeypatch, content="Texte du PDF.\n")
    _drop(cfg, "book.pdf")
    _drop(cfg, "README.md", data=b"# procedure")
    outcomes = wiki_extract.run(cfg, None, lang="fra+eng", dry_run=False, skip_sync=True)
    statuses = sorted(o.status for o in outcomes)
    assert statuses == ["extrait", "ignored"]
    assert (cfg.RAW / "pdfs" / "book.pdf.txt").is_file()
    assert (cfg.INBOX / "README.md").is_file()            # intrus laissé en place
    # code retour non-erreur
    assert not any(o.status == "error" for o in outcomes)


# --- écriture complète + move vide l'inbox --------------------------------
def test_pdf_complet_et_inbox_vide(cfg, monkeypatch):
    _install_fake(monkeypatch, content="Texte du PDF.\n")
    _drop(cfg, "book.pdf")
    outcomes = wiki_extract.run(cfg, None, lang="fra+eng", dry_run=False)

    assert [o.status for o in outcomes] == ["extrait"]
    pdfs = cfg.RAW / "pdfs"
    assert (pdfs / "book.pdf.txt").read_text(encoding="utf-8") == "Texte du PDF.\n"
    assert (pdfs / "book.pdf").is_file()  # binaire déplacé dans raw/
    toc = json.loads((pdfs / "book.toc.json").read_text(encoding="utf-8"))
    assert toc["ocr"] is False and toc["chapters"][0]["title"] == "Ch1"
    # _status.md contient une ligne avec le SHA du CONTENU
    status = (pdfs / "_status.md").read_text(encoding="utf-8")
    assert "book.pdf.txt" in status
    # _inbox/ vidé
    assert list(cfg.INBOX.iterdir()) == []


# --- déduplication : re-dépôt identique supprimé, pas de doublon ----------
def test_dedup_supprime_redepot(cfg, monkeypatch):
    _install_fake(monkeypatch, content="même contenu")
    _drop(cfg, "a.pdf")
    wiki_extract.run(cfg, None, lang="x", dry_run=False)

    # re-dépôt d'un binaire au contenu identique (autre nom)
    redo = _drop(cfg, "copie.pdf")
    out = wiki_extract.run(cfg, None, lang="x", dry_run=False)
    assert out[0].status == "skipped_duplicate"
    assert not redo.exists()  # supprimé de _inbox/
    # aucun fichier -2 créé
    assert not list((cfg.RAW / "pdfs").glob("*-2*"))
    assert list(cfg.INBOX.iterdir()) == []


# --- suffixage -2 : même nom, contenu différent ---------------------------
def test_suffixage_nom_identique_contenu_different(cfg, monkeypatch):
    _install_fake(monkeypatch, content="contenu A")
    _drop(cfg, "book.pdf")
    wiki_extract.run(cfg, None, lang="x", dry_run=False)

    _install_fake(monkeypatch, content="contenu B different")
    _drop(cfg, "book.pdf")  # même nom, mais l'ancien a été déplacé dans raw/
    out = wiki_extract.run(cfg, None, lang="x", dry_run=False)

    pdfs = cfg.RAW / "pdfs"
    assert out[0].suffixed is True
    assert (pdfs / "book-2.pdf.txt").read_text(encoding="utf-8") == "contenu B different"
    assert (pdfs / "book-2.pdf").is_file()
    assert (pdfs / "book-2.toc.json").is_file()
    # immutabilité : l'original intact
    assert (pdfs / "book.pdf.txt").read_text(encoding="utf-8") == "contenu A"


# --- erreur d'extraction : binaire conservé dans _inbox/ ------------------
def test_erreur_conserve_binaire(cfg, monkeypatch):
    _install_fake(monkeypatch, content="x", error=ExtractorError("couche texte vide, OCR indispo"))
    kept = _drop(cfg, "scan.pdf")
    out = wiki_extract.run(cfg, None, lang="x", dry_run=False)
    assert out[0].status == "error"
    assert kept.exists()  # NON déplacé : reprise possible
    assert not (cfg.RAW / "pdfs").exists()  # rien écrit dans raw/


# --- reprise sur crash : contenu+statut déjà écrits, binaire resté en inbox
def test_reprise_sans_doublon(cfg, monkeypatch):
    _install_fake(monkeypatch, content="déjà extrait")
    _drop(cfg, "first.pdf")
    wiki_extract.run(cfg, None, lang="x", dry_run=False)  # premier run complet (SHA enregistré)
    # simule l'état post-crash : raw+statut déjà là, binaire au MÊME contenu re-déposé
    leftover = _drop(cfg, "again.pdf")

    out = wiki_extract.run(cfg, None, lang="x", dry_run=False)
    assert out[0].status == "skipped_duplicate"
    assert not leftover.exists()
    assert not list((cfg.RAW / "pdfs").glob("*-2*"))


# --- confinement : rien hors raw/ + _inbox/ -------------------------------
def test_confinement_perimetre(cfg, monkeypatch):
    _install_fake(monkeypatch, content="texte")
    _drop(cfg, "book.pdf")
    wiki_extract.run(cfg, None, lang="x", dry_run=False)
    enfants = {p.name for p in cfg.work_root.iterdir()}
    assert enfants <= {"_inbox", "raw"}  # ni wiki/ ni reading-grids/ ni autre


# --- web : markdown inline + frontmatter + image localisée ----------------
def test_web_clipping(cfg, monkeypatch):
    asset = Asset(filename="img.png", data=b"PNG", original_ref="https://ex.org/i.png")
    _install_fake(
        monkeypatch,
        content="# Titre\n\n![x](https://ex.org/i.png)\n",
        content_ext="md",
        doc_type="web",
        assets=[asset],
        structure=[],
        title="Ma Page",
    )
    out = wiki_extract.run(cfg, "https://ex.org/article", lang="x", dry_run=False)
    assert out[0].status == "extrait"
    web = cfg.RAW / "web"
    md = next(web.glob("ma-page-*.md"))
    text = md.read_text(encoding="utf-8")
    assert text.startswith("---\n")  # frontmatter
    assert "type: web" in text
    assert "https://ex.org/i.png" not in text  # lien réécrit
    assert "_assets/" in text
    assert (web / "_assets").is_dir() and any((web / "_assets").iterdir())


# --- verrou tenu : skip propre --------------------------------------------
def test_verrou_tenu(cfg, monkeypatch):
    _install_fake(monkeypatch, content="x")
    held = inbox_lock.acquire()  # un autre process tient le verrou
    try:
        _drop(cfg, "book.pdf")
        out = wiki_extract.run(cfg, None, lang="x", dry_run=False)
        assert out[0].status == "locked"
        assert (cfg.INBOX / "book.pdf").exists()  # rien traité
    finally:
        held.release()


# --- dry-run : aucune écriture --------------------------------------------
def test_dry_run(cfg, monkeypatch):
    _install_fake(monkeypatch, content="x")
    kept = _drop(cfg, "book.pdf")
    out = wiki_extract.run(cfg, None, lang="x", dry_run=True)
    assert out[0].status == "extrait" and "dry-run" in out[0].message
    assert kept.exists()
    assert not (cfg.RAW / "pdfs").exists()


# --- pré-sync (pull) en échec : on n'extrait pas (SPEC §10) ----------------
def test_pull_echec_interrompt(cfg, monkeypatch):
    _install_fake(monkeypatch, content="x")
    kept = _drop(cfg, "book.pdf")
    monkeypatch.setattr(wiki_extract.sync, "pull", lambda c: 1)
    out = wiki_extract.run(cfg, None, lang="x", dry_run=False)
    assert out[0].status == "error" and "pull" in out[0].message
    assert kept.exists()  # rien consommé
    assert not (cfg.RAW / "pdfs").exists()


# --- post-sync (push) en échec : signalé, travail local conservé ----------
def test_push_echec_signale_mais_conserve(cfg, monkeypatch):
    _install_fake(monkeypatch, content="Texte.\n")
    _drop(cfg, "book.pdf")
    monkeypatch.setattr(wiki_extract.sync, "push", lambda c: 1)
    out = wiki_extract.run(cfg, None, lang="x", dry_run=False)
    statuses = [o.status for o in out]
    assert "extrait" in statuses and "error" in statuses
    assert (cfg.RAW / "pdfs" / "book.pdf.txt").is_file()  # écriture bien conservée


# --- --skip-sync : pull/push jamais appelés -------------------------------
def test_skip_sync_court_circuite(cfg, monkeypatch):
    _install_fake(monkeypatch, content="x")
    _drop(cfg, "book.pdf")
    monkeypatch.setattr(wiki_extract.sync, "pull", lambda c: (_ for _ in ()).throw(AssertionError("pull")))
    monkeypatch.setattr(wiki_extract.sync, "push", lambda c: (_ for _ in ()).throw(AssertionError("push")))
    out = wiki_extract.run(cfg, None, lang="x", dry_run=False, skip_sync=True)
    assert out[0].status == "extrait"

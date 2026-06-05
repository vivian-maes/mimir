"""Tests de l'écriture d'article (Karpathy, antidoublon replace-body, NFD/NFC, assets)."""

import json
from datetime import date
from pathlib import Path

import pytest

import config_loader
import article_writer as A
from article_writer import ArticleSpec


@pytest.fixture
def cfg(tmp_path):
    work = tmp_path / "work"
    work.mkdir()
    cfgp = tmp_path / "wiki.config.json"
    cfgp.write_text(json.dumps({"work_root": str(work)}), encoding="utf-8")
    return config_loader.load_config(cfgp)


_BODY = "# Relèvement\n\n> Résumé.\n\n## Définition\nReformulation.\n"


# --- création nominale -----------------------------------------------------
def test_creation_nominale(cfg):
    spec = ArticleSpec(
        subject="Navigation", notion="Relèvement", body=_BODY,
        sources=["raw/pdfs/x.pdf.txt#ch3"], tags=["navigation", "technique"],
    )
    res = A.write_article(cfg, spec, today=date(2026, 6, 4))

    assert res.created is True
    assert res.wikilink == "navigation/relevement"
    target = cfg.WIKI / "navigation" / "relevement.md"   # slug ASCII
    assert res.path == target and target.is_file()

    text = target.read_text(encoding="utf-8")
    assert text.startswith("---\n")
    assert 'title: "Relèvement"' in text
    assert "subject: navigation" in text
    assert "tags: [navigation, technique]" in text
    assert 'sources: ["raw/pdfs/x.pdf.txt#ch3"]' in text
    assert "created: 2026-06-04" in text and "updated: 2026-06-04" in text
    assert "## Définition" in text


# --- antidoublon = replace-body + fusion frontmatter -----------------------
def test_antidoublon_replace_body(cfg):
    A.write_article(
        cfg,
        ArticleSpec(subject="navigation", notion="Relèvement", body="# Relèvement\n\nV1 ancien\n",
                    sources=["raw/pdfs/x.pdf.txt"], tags=["navigation"]),
        today=date(2026, 6, 4),
    )
    res = A.write_article(
        cfg,
        ArticleSpec(subject="navigation", notion="Relèvement", body="# Relèvement\n\nV2 nouveau\n",
                    sources=["raw/web/y.md"], tags=["technique"]),
        today=date(2026, 6, 10),
    )

    assert res.created is False
    subject_dir = cfg.WIKI / "navigation"
    mds = list(subject_dir.glob("*.md"))
    assert len(mds) == 1                                  # un seul fichier, pas de -2
    text = mds[0].read_text(encoding="utf-8")
    assert "V2 nouveau" in text and "V1 ancien" not in text   # corps remplacé
    assert "created: 2026-06-04" in text                  # created conservé
    assert "updated: 2026-06-10" in text                  # updated = jour de la 2e passe
    assert 'sources: ["raw/pdfs/x.pdf.txt", "raw/web/y.md"]' in text  # union
    assert "tags: [navigation, technique]" in text        # union


# --- NFD/NFC : fichier ASCII, wikilink résout vers le fichier réel ---------
def test_nfd_nfc_slug_ascii(cfg):
    res = A.write_article(
        cfg, ArticleSpec(subject="Cuisine", notion="Béarnaise", body="# Béarnaise\n\nSauce.\n"),
        today=date(2026, 6, 4),
    )
    assert res.wikilink == "cuisine/bearnaise"
    assert (cfg.WIKI / "cuisine" / "bearnaise.md").is_file()


# --- double _assets : localisé par sujet, préfixé sur collision ------------
def test_assets_localises_par_sujet(cfg, tmp_path):
    img = tmp_path / "schema.png"
    img.write_bytes(b"PNG-A")
    body = "# Relèvement\n\n![schéma](_assets/schema.png)\n"
    A.write_article(
        cfg, ArticleSpec(subject="navigation", notion="Relèvement", body=body),
        today=date(2026, 6, 4), assets=[str(img)],
    )
    assets_dir = cfg.WIKI / "navigation" / "_assets"
    assert (assets_dir / "schema.png").read_bytes() == b"PNG-A"
    # rien écrit côté raw
    assert not (cfg.RAW / "web" / "_assets").exists()


def test_assets_prefixe_sur_collision(cfg, tmp_path):
    # un asset homonyme existe déjà -> le nouveau est préfixé par le slug de la notion
    assets_dir = cfg.WIKI / "navigation" / "_assets"
    assets_dir.mkdir(parents=True)
    (assets_dir / "schema.png").write_bytes(b"DEJA-LA")

    img = tmp_path / "schema.png"
    img.write_bytes(b"NOUVEAU")
    body = "# Relèvement\n\n![s](_assets/schema.png)\n"
    A.write_article(
        cfg, ArticleSpec(subject="navigation", notion="Relèvement", body=body),
        today=date(2026, 6, 4), assets=[str(img)],
    )
    assert (assets_dir / "schema.png").read_bytes() == b"DEJA-LA"        # intact
    assert (assets_dir / "relevement-schema.png").read_bytes() == b"NOUVEAU"
    text = (cfg.WIKI / "navigation" / "relevement.md").read_text(encoding="utf-8")
    assert "_assets/relevement-schema.png" in text                      # lien réécrit


# --- Mermaid + wikilinks écrits verbatim -----------------------------------
def test_mermaid_wikilink_verbatim(cfg):
    body = '# Relèvement\n\n```mermaid\nflowchart LR\n  A["[[navigation/triangulation]]"]\n```\n'
    A.write_article(
        cfg, ArticleSpec(subject="navigation", notion="Relèvement", body=body),
        today=date(2026, 6, 4),
    )
    text = (cfg.WIKI / "navigation" / "relevement.md").read_text(encoding="utf-8")
    assert 'A["[[navigation/triangulation]]"]' in text
    assert "[[[" not in text


# --- slug vide refusé ------------------------------------------------------
def test_slug_vide_refuse(cfg):
    with pytest.raises(A.ArticleError):
        A.write_article(
            cfg, ArticleSpec(subject="navigation", notion="!!!", body="# x\n"),
            today=date(2026, 6, 4),
        )


# --- dry-run : aucune écriture ---------------------------------------------
def test_dry_run_sans_ecriture(cfg):
    res = A.write_article(
        cfg, ArticleSpec(subject="navigation", notion="Relèvement", body=_BODY),
        today=date(2026, 6, 4), dry_run=True,
    )
    assert res.wikilink == "navigation/relevement"
    assert not (cfg.WIKI / "navigation").exists()

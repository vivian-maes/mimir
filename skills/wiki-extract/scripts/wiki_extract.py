#!/usr/bin/env python3
"""wiki-extract — orchestrateur d'extraction vers `raw/` immuable (SPEC §4, §6).

Usage :
    wiki_extract.py --config <wiki.config.json> [SOURCE] [--lang fra+eng] [--dry-run]

- SOURCE absent  -> scan de la dropzone `_inbox/` (mode cron/curator).
- SOURCE = chemin .pdf/.epub  -> extraction de ce binaire.
- SOURCE = URL http(s)        -> clipping web.

Garanties (DoD Phase 1) : confinement à `work_root`, immutabilité de `raw/`
(append-only, suffixage `-2`), table de statut `_status.md` (SHA du CONTENU),
déduplication par SHA, `_inbox/` vidé (move du binaire ; suppression si doublon),
reprise sur crash (le binaire reste en `_inbox/` tant que l'écriture n'a pas abouti).
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path

# --- bootstrap : rendre le socle partagé importable (hors tests) -----------
_SHARED = Path(__file__).resolve().parents[2] / "_shared-references" / "scripts"
for _cand in (os.environ.get("MIMIR_SHARED"), _SHARED):
    if _cand and Path(_cand).is_dir() and str(_cand) not in sys.path:
        sys.path.insert(0, str(_cand))
        break
if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

import config_loader  # noqa: E402
import iohelpers  # noqa: E402
import slug  # noqa: E402
import status_table  # noqa: E402
from guard import safe_path  # noqa: E402

import sync  # noqa: E402  (moteur de synchro partagé : lock/pull/push)
import extractors  # noqa: E402  (package)
from extractors.base import ExtractorError  # noqa: E402


_BIN_EXT = {"pdfs": "pdf", "epubs": "epub"}  # type -> extension binaire ; web = aucun
_SKIP_NAMES = {".DS_Store"}


@dataclass
class Outcome:
    source: str
    doc_type: str
    status: str  # extrait | skipped_duplicate | ignored | error | locked
    content_path: Path | None = None
    suffixed: bool = False
    message: str = ""


def _today() -> date:
    return date.today()


# --- nommage ---------------------------------------------------------------
def _slug_base(source: str | Path, result) -> str:
    """Slug ASCII de base (sans extension). Binaire : nom de fichier ; web : titre."""
    if extractors.is_url(source):
        cand = result.metadata.get("title") or str(source)
    else:
        name = Path(str(source)).name
        for ext in (".pdf", ".epub"):
            if name.lower().endswith(ext):
                name = name[: -len(ext)]
                break
        cand = name
    return slug.slugify(cand) or "sans-titre"


def _web_frontmatter(metadata: dict) -> str:
    """Frontmatter YAML du clipping web (SPEC §4.4) — construit à la main (format contrôlé)."""
    title = (metadata.get("title") or "").replace('"', "'")
    src = metadata.get("source", "")
    created = metadata.get("created") or _today().isoformat()
    return (
        "---\n"
        f'title: "{title}"\n'
        f"source: {src}\n"
        "type: web\n"
        f"created: {created}\n"
        "tags: [clippings]\n"
        "---\n\n"
    )


# --- placement du binaire / dédup -----------------------------------------
def _place_binary(src: Path, dest: Path, *, from_inbox: bool, work_root: Path) -> None:
    """Dépose le binaire dans raw/ : move depuis `_inbox/`, copie sinon (préserve la source)."""
    safe_path(work_root, *dest.relative_to(work_root).parts)  # confinement explicite
    if from_inbox:
        os.replace(src, dest)  # même FS (sous work_root) -> atomique
    else:
        shutil.copy2(src, dest)


# --- pipeline d'une source -------------------------------------------------
def process_source(cfg, source, *, from_inbox: bool, lang: str, dry_run: bool) -> Outcome:
    """Extrait une source unique (binaire ou URL) vers raw/<type>/."""
    work_root = cfg.work_root

    try:
        doc_type = extractors.doc_type_for(source)  # peut lever (format non supporté)
        type_dir = cfg.RAW / doc_type
        extractor = extractors.get_extractor(source)
        result = extractor.extract(source, lang=lang)
    except ExtractorError as exc:
        # format non supporté ou extraction en échec : binaire conservé dans _inbox/
        # (reprise au prochain run, pas de move) ; le batch n'est pas interrompu.
        return Outcome(str(source), "-", "error", message=str(exc))

    content_sha = iohelpers.sha256_text(result.raw_content)

    # --- déduplication par SHA de contenu ---------------------------------
    rows = status_table.load_status(type_dir / "_status.md")
    if content_sha in status_table.known_shas(rows):
        if from_inbox and not dry_run:
            Path(source).unlink(missing_ok=True)  # doublon : on supprime le re-dépôt
        return Outcome(str(source), doc_type, "skipped_duplicate", message="contenu déjà ingéré")

    # --- nommage (suffixage -2 cohérent entre fichiers liés) --------------
    base = _slug_base(source, result)
    if doc_type == "web":
        base = f"{base}-{_today():%Y%m%d}"
        exts = [result.content_ext]
    else:
        exts = [_BIN_EXT[doc_type], result.content_ext, "toc.json"]
    final_base = iohelpers.unique_suffixed_base(type_dir, base, exts)
    suffixed = final_base != base

    content_path = type_dir / f"{final_base}.{result.content_ext}"

    if dry_run:
        return Outcome(str(source), doc_type, "extrait", content_path, suffixed, "(dry-run)")

    # --- écritures (ordre critique : assets -> contenu -> toc -> statut) ---
    assets_dir = type_dir / cfg.ASSETS_DIRNAME
    raw_content = result.raw_content
    for asset in result.assets:
        asset_name = f"{final_base}-{asset.filename}"
        iohelpers.atomic_write_bytes(assets_dir / asset_name, asset.data, work_root=work_root)
        if asset.original_ref:  # web : réécrire le lien en relatif
            rel = f"{cfg.ASSETS_DIRNAME}/{asset_name}"
            raw_content = raw_content.replace(asset.original_ref, rel)

    if doc_type == "web":
        raw_content = _web_frontmatter(result.metadata) + raw_content

    iohelpers.atomic_write_text(content_path, raw_content, work_root=work_root)

    if doc_type != "web":
        toc = {
            "title": result.metadata.get("title", final_base),
            "source": str((type_dir / f"{final_base}.{_BIN_EXT[doc_type]}").relative_to(work_root)),
            "pages": result.metadata.get("pages"),
            "ocr": bool(result.metadata.get("ocr", False)),
            "chapters": [
                {
                    "order": c.order,
                    "title": c.title,
                    "page_start": c.page_start,
                    "page_end": c.page_end,
                }
                for c in result.structure
            ],
        }
        iohelpers.write_json(type_dir / f"{final_base}.toc.json", toc, work_root=work_root)

    status_table.upsert_row(
        rows,
        status_table.StatusRow(
            fichier=content_path.name,
            sha256=content_sha,
            statut="extrait",
            maj=_today().isoformat(),
        ),
    )
    status_table.save_status(type_dir / "_status.md", doc_type, rows, work_root=work_root)

    # --- move/copie du binaire APRÈS écriture réussie (reprise sûre) ------
    if doc_type != "web":
        dest_bin = type_dir / f"{final_base}.{_BIN_EXT[doc_type]}"
        _place_binary(Path(source), dest_bin, from_inbox=from_inbox, work_root=work_root)

    return Outcome(str(source), doc_type, "extrait", content_path, suffixed)


def scan_inbox(cfg) -> tuple[list[Path], list[Path]]:
    """Trie `_inbox/` (plat) : `(à_extraire, ignorés)`.

    `à_extraire` = binaires supportés (`.pdf`/`.epub`). `ignorés` = fichiers présents
    mais sans extracteur (README, `.txt`, etc.) : ils ne doivent PAS faire échouer le
    scan (sinon, en cron, non-ingestion silencieuse des sources valides). Les fichiers
    cachés et `.DS_Store` sont écartés en amont (ni traités ni signalés).
    """
    inbox = cfg.INBOX
    if not inbox.is_dir():
        return [], []
    valid: list[Path] = []
    skipped: list[Path] = []
    for p in sorted(inbox.iterdir()):
        if not (p.is_file() and p.name not in _SKIP_NAMES and not p.name.startswith(".")):
            continue
        (valid if extractors.is_supported(p) else skipped).append(p)
    return valid, skipped


def run(cfg, source, *, lang: str, dry_run: bool, skip_sync: bool = False) -> list[Outcome]:
    """Verrou -> pré-sync -> traite SOURCE (ou tout `_inbox/`) -> post-sync (SPEC §6).

    `lock` et `pull` précèdent toute consommation de `_inbox/` (synchronisé : sinon
    double-ingestion entre machines, vigilance §12.9) ; `push` publie `raw/` après
    écriture. `--skip-sync` court-circuite pull/push (chaînes, travail local).
    """
    try:
        lock = sync.lock(cfg)
    except sync.LockHeld as exc:
        return [Outcome(str(source or cfg.INBOX), "-", "locked", message=str(exc))]
    try:
        if not skip_sync and not dry_run and sync.pull(cfg) != 0:
            # pull en échec : ne pas extraire sur un raw/ potentiellement périmé (SPEC §10)
            return [Outcome(str(source or cfg.INBOX), "-", "error",
                            message="pré-sync (pull) en échec — extraction interrompue")]

        if source:
            from_inbox = (not extractors.is_url(source)) and (cfg.INBOX in Path(source).resolve().parents)
            outcomes = [process_source(cfg, source, from_inbox=from_inbox, lang=lang, dry_run=dry_run)]
        else:
            to_extract, skipped = scan_inbox(cfg)
            outcomes = [
                process_source(cfg, str(p), from_inbox=True, lang=lang, dry_run=dry_run)
                for p in to_extract
            ]
            outcomes += [
                Outcome(str(p), "-", "ignored", message="format non supporté (ni .pdf ni .epub)")
                for p in skipped
            ]

        # post-sync seulement si du contenu a réellement été écrit (pas en dry-run)
        if not skip_sync and not dry_run and any(o.status == "extrait" for o in outcomes):
            if sync.push(cfg) != 0:
                outcomes.append(Outcome(str(source or cfg.INBOX), "-", "error",
                                        message="post-sync (push) en échec — travail local conservé"))
        return outcomes
    finally:
        lock.release()


def _digest(outcomes: list[Outcome]) -> str:
    if not outcomes:
        return "Rien à traiter (_inbox/ vide)."
    lines = []
    for o in outcomes:
        tag = {
            "extrait": "✅ extrait" + (" (suffixé -2)" if o.suffixed else ""),
            "skipped_duplicate": "↩️  doublon (ignoré)",
            "ignored": "⚠️  ignoré (format non supporté)",
            "error": "❌ erreur",
            "locked": "🔒 verrou tenu",
        }.get(o.status, o.status)
        where = f" -> {o.content_path}" if o.content_path else ""
        msg = f" — {o.message}" if o.message else ""
        lines.append(f"{tag} [{o.doc_type}] {o.source}{where}{msg}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Extraction de sources vers raw/ (Mimir).")
    parser.add_argument(
        "--config", default=None,
        help="Chemin du wiki.config.json (optionnel ; auto-découverte si omis : "
             "$MIMIR_CONFIG, dossier du profil, ~/.config/mimir/wiki.config.json, ./wiki.config.json)",
    )
    parser.add_argument("source", nargs="?", help="Chemin .pdf/.epub ou URL ; absent = scan _inbox/")
    parser.add_argument("--lang", default="fra+eng", help="Langue(s) OCR (défaut: fra+eng)")
    parser.add_argument("--dry-run", action="store_true", help="N'écrit rien ; rapporte l'intention")
    parser.add_argument("--skip-sync", action="store_true", help="Court-circuite pull/push (travail local)")
    args = parser.parse_args(argv)

    cfg = config_loader.load_resolved_config(args.config)
    outcomes = run(cfg, args.source, lang=args.lang, dry_run=args.dry_run, skip_sync=args.skip_sync)
    print(_digest(outcomes))
    return 1 if any(o.status == "error" for o in outcomes) else 0


if __name__ == "__main__":
    raise SystemExit(main())

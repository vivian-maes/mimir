#!/usr/bin/env python3
"""wiki-reading-grid — génère la grille de lecture d'un ouvrage (SPEC §8).

Skill **déterministe** : aucune prose à inventer, l'agent enchaîne simplement les
sous-commandes. La grille croise `toc.json` × ledger × ancres `#chK` des articles
pour restituer l'ordre de lecture, avec navigation Précédent/Suivant au niveau
chapitre. Aucune duplication de contenu : elle ordonne des liens.

    wiki_reading_grid.py --config CFG generate --source raw/<type>/<nom>.<ext> [--skip-sync] [--dry-run]
    wiki_reading_grid.py --config CFG generate-all [--skip-sync] [--dry-run]

- `generate`     : (re)génère la grille d'un ouvrage. Idempotent (régénération
  complète ; seul `created` est préservé). MAJ de la colonne « Grille » de `_status.md`.
- `generate-all` : itère sur tous les `*.toc.json` de `raw/pdfs` + `raw/epubs` (le web,
  sans chapitrage, est ignoré).

Garanties : confinement à `work_root`, écriture atomique, slug de grille dérivé du
titre de l'ouvrage avec désambiguïsation `-2` en cas de collision. Synchro stubbée.
"""

from __future__ import annotations

import argparse
import json
import os
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
from frontmatter import parse_frontmatter  # noqa: E402

import grid_builder  # noqa: E402
import sync  # noqa: E402  (moteur de synchro partagé : pull/push)


@dataclass
class GenOutcome:
    action: str
    status: str  # généré | ignoré | error
    content_rel: str
    grid_path: str = ""
    detail: str = ""
    result: grid_builder.GridResult | None = None


def _today() -> date:
    return date.today()


def _to_content_rel(cfg, source: str) -> str:
    """Normalise un `--source` (relatif ou absolu) en chemin relatif à `work_root`."""
    p = Path(source)
    if p.is_absolute():
        return p.resolve().relative_to(cfg.work_root).as_posix()
    return p.as_posix()


def _resolve_grid_path(cfg, work: str, content_rel: str) -> tuple[Path, str | None]:
    """Chemin de la grille + `created` préservé.

    Idempotence : si une grille de **même `source`** existe déjà, on la réécrit au
    même endroit en conservant son `created`. Sinon on dérive le slug du titre, en
    suffixant `-2`, `-3`… si le slug est déjà pris par une grille d'une autre source.
    """
    grids_dir = cfg.READING_GRIDS
    if grids_dir.is_dir():
        for p in sorted(grids_dir.glob("*.md")):
            front, _ = parse_frontmatter(p.read_text(encoding="utf-8"))
            if front.get("source") == content_rel:
                return p, (str(front["created"]) if front.get("created") else None)

    base_slug = slug.slugify(work) or "grille"
    candidate = base_slug
    n = 2
    while (grids_dir / f"{candidate}.md").exists():
        candidate = f"{base_slug}-{n}"
        n += 1
    return grids_dir / f"{candidate}.md", None


def _update_status_grille(cfg, content_rel: str, grid_slug: str, *, today: str) -> bool:
    """Met à jour la colonne « Grille » de `raw/<type>/_status.md`. Préserve le reste.

    Renvoie False (sans créer de ligne fantôme) si la source n'a pas encore de ligne.
    """
    parts = content_rel.split("/")
    doc_type, fichier = parts[1], parts[-1]
    status_path = cfg.RAW / doc_type / "_status.md"
    rows = status_table.load_status(status_path)
    existing = next((r for r in rows if r.fichier == fichier), None)
    if existing is None:
        return False
    existing.grille = f"[[{cfg.layout['reading_grids']}/{grid_slug}]]"
    existing.maj = today
    status_table.upsert_row(rows, existing)
    status_table.save_status(status_path, doc_type, rows, work_root=cfg.work_root)
    return True


def cmd_generate(cfg, source: str, *, skip_sync: bool = False, dry_run: bool = False) -> GenOutcome:
    """(Re)génère la grille de l'ouvrage `source`. Idempotent."""
    if not skip_sync and sync.pull(cfg) != 0:
        raise RuntimeError("pré-sync (pull) en échec — génération interrompue")

    content_rel = _to_content_rel(cfg, source)
    result = grid_builder.build_grid(cfg, content_rel)
    if result.skipped:
        return GenOutcome("generate", "ignoré", content_rel, detail=f"sans chapitrage ({result.skipped})", result=result)

    path, preserved = _resolve_grid_path(cfg, result.work, content_rel)
    created = preserved or _today().isoformat()
    document = grid_builder.document(result, created)
    grid_rel = path.relative_to(cfg.work_root).as_posix()

    if dry_run:
        return GenOutcome("generate", "généré", content_rel, grid_path=grid_rel,
                          detail=f"(dry-run) {len(result.linked_articles)} article(s) liés", result=result)

    iohelpers.atomic_write_text(path, document, work_root=cfg.work_root)
    today = _today().isoformat()
    status_ok = _update_status_grille(cfg, content_rel, path.stem, today=today)
    detail = f"{path.name} ; {len(result.linked_articles)} article(s) liés, {len(result.unresolved_chapters)} chapitre(s) sans article"
    if not status_ok:
        detail += " (⚠ aucune ligne _status.md pour cette source)"

    if not skip_sync and sync.push(cfg) != 0:
        return GenOutcome("generate", "error", content_rel, grid_path=grid_rel,
                          detail="post-sync (push) en échec — travail local conservé", result=result)
    return GenOutcome("generate", "généré", content_rel, grid_path=grid_rel, detail=detail, result=result)


def _all_content_with_toc(cfg) -> list[str]:
    """Chemins de contenu (relatifs) de pdfs/epubs disposant d'un `.toc.json`."""
    out: list[str] = []
    for doc_type, ext in (("pdfs", ".pdf.txt"), ("epubs", ".epub.txt")):
        type_dir = cfg.RAW / doc_type
        if not type_dir.is_dir():
            continue
        for toc in sorted(type_dir.glob("*.toc.json")):
            base = toc.name[: -len(".toc.json")]
            content = type_dir / f"{base}{ext}"
            if content.is_file():
                out.append(content.relative_to(cfg.work_root).as_posix())
    return out


def cmd_generate_all(cfg, *, skip_sync: bool = False, dry_run: bool = False) -> list[GenOutcome]:
    """Régénère toutes les grilles (un appel par ouvrage chapitré)."""
    if not skip_sync and sync.pull(cfg) != 0:
        raise RuntimeError("pré-sync (pull) en échec — génération interrompue")
    outcomes: list[GenOutcome] = []
    for content_rel in _all_content_with_toc(cfg):
        outcomes.append(cmd_generate(cfg, content_rel, skip_sync=True, dry_run=dry_run))
    if not dry_run and not skip_sync:
        sync.push(cfg)
    return outcomes


# --- CLI -------------------------------------------------------------------
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Génère les grilles de lecture (Mimir).")
    parser.add_argument("--config", required=True, help="Chemin du wiki.config.json")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_gen = sub.add_parser("generate", help="(Re)génère la grille d'un ouvrage.")
    p_gen.add_argument("--source", required=True, help="Fichier de contenu raw/<type>/<nom>.<ext>")
    p_gen.add_argument("--skip-sync", action="store_true")
    p_gen.add_argument("--dry-run", action="store_true")

    p_all = sub.add_parser("generate-all", help="Régénère toutes les grilles (pdfs + epubs).")
    p_all.add_argument("--skip-sync", action="store_true")
    p_all.add_argument("--dry-run", action="store_true")

    args = parser.parse_args(argv)
    cfg = config_loader.load_config(args.config)

    if args.cmd == "generate":
        out = cmd_generate(cfg, args.source, skip_sync=args.skip_sync, dry_run=args.dry_run)
        print(json.dumps({
            "status": out.status, "content": out.content_rel, "grid_path": out.grid_path,
            "linked_articles": out.result.linked_articles if out.result else [],
            "unresolved_chapters": out.result.unresolved_chapters if out.result else [],
            "orphan_articles": out.result.orphan_articles if out.result else [],
        }, ensure_ascii=False, indent=2))
        print(f"{'✅' if out.status != 'error' else '❌'} {out.detail}", file=sys.stderr)
        return 1 if out.status == "error" else 0

    if args.cmd == "generate-all":
        outs = cmd_generate_all(cfg, skip_sync=args.skip_sync, dry_run=args.dry_run)
        gen = sum(1 for o in outs if o.status == "généré")
        skipped = sum(1 for o in outs if o.status == "ignoré")
        for o in outs:
            print(f"{'✅' if o.status == 'généré' else '•'} {o.content_rel} → {o.detail}", file=sys.stderr)
        print(f"{gen} grille(s) générée(s), {skipped} ignorée(s).", file=sys.stderr)
        return 1 if any(o.status == "error" for o in outs) else 0

    return 2


if __name__ == "__main__":
    raise SystemExit(main())

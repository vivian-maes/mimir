#!/usr/bin/env python3
"""wiki-index — régénère les index du wiki et audite les liens (SPEC §9).

Skill **déterministe** : aucune prose à inventer. Deux sous-commandes :

    wiki_index.py --config CFG regenerate [--skip-sync] [--dry-run]
    wiki_index.py --config CFG audit [--json]

- `regenerate` : reconstruit `wiki/INDEX.md` (sujets) + tous les `wiki/<sujet>/_INDEX.md`
  (notions + grilles). Écriture atomique confinée. Préserve la description éditoriale
  des sujets dans l'INDEX principal.
- `audit` : **lecture seule**, 3 passes (liens cassés / fichiers fantômes / index → vide).
  Code retour **0 ssi 0 anomalie** — exploitable en CI / pour le DoD.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
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

import index_builder  # noqa: E402
import link_audit  # noqa: E402
import sync  # noqa: E402  (moteur de synchro partagé : pull/push)


def _today() -> str:
    return date.today().isoformat()


def cmd_regenerate(cfg, *, skip_sync: bool = False, dry_run: bool = False):
    """Reconstruit les deux niveaux d'index. Renvoie l'`IndexResult`."""
    if not skip_sync and sync.pull(cfg) != 0:
        raise RuntimeError("pré-sync (pull) en échec — régénération interrompue")
    res = index_builder.regenerate(cfg, dry_run=dry_run)
    if not dry_run and not skip_sync:
        sync.push(cfg)
    return res


def cmd_audit(cfg):
    """Audit lecture seule (3 passes). Aucune synchro, aucune écriture."""
    return link_audit.audit(cfg)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Index + audit liens du wiki (Mimir).")
    parser.add_argument(
        "--config", default=None,
        help="Chemin du wiki.config.json (optionnel ; auto-découverte si omis : "
             "$MIMIR_CONFIG, dossier du profil, ~/.config/mimir/wiki.config.json, ./wiki.config.json)",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_reg = sub.add_parser("regenerate", help="Reconstruit INDEX.md + <sujet>/_INDEX.md.")
    p_reg.add_argument("--skip-sync", action="store_true")
    p_reg.add_argument("--dry-run", action="store_true")

    p_aud = sub.add_parser("audit", help="Audit liens (3 passes, lecture seule).")
    p_aud.add_argument("--json", action="store_true", help="Rapport machine (JSON).")

    args = parser.parse_args(argv)
    cfg = config_loader.load_resolved_config(args.config)

    if args.cmd == "regenerate":
        res = cmd_regenerate(cfg, skip_sync=args.skip_sync, dry_run=args.dry_run)
        print(json.dumps({
            "subjects": res.subjects, "written": res.written, "form": res.form,
        }, ensure_ascii=False, indent=2))
        tag = "(dry-run) " if args.dry_run else ""
        print(f"✅ {tag}{len(res.subjects)} sujet(s), {len(res.written)} index écrit(s).", file=sys.stderr)
        return 0

    if args.cmd == "audit":
        report = cmd_audit(cfg)
        if args.json:
            print(json.dumps({
                "ok": report.ok,
                "broken": report.broken,
                "orphans": report.orphans,
                "dangling": report.dangling,
            }, ensure_ascii=False, indent=2))
        else:
            print(link_audit.render_report(report, today=_today()))
        return 0 if report.ok else 1

    return 2


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""wiki-sync — synchronisation pluggable du vault Mimir (SPEC §10).

Usage :
    wiki_sync.py --config <wiki.config.json> {lock|pull|push|validate|sync} [--dry-run]

- `lock`     : teste l'acquisition du verrou (mutex hors work_root) puis le relâche.
- `pull`     : récupère l'état distant → local (pré-sync).
- `push`     : publie local → distant (post-sync).
- `validate` : vérifie la cohérence local↔distant.
- `sync`     : cycle complet `pull → push → validate` (trigger « synchronise le vault »).

Le backend (`rclone` | `git`, ou `noop` si le config n'a pas de clé `sync`) est
choisi par `sync.backend`. Le périmètre est **borné à `work_root`** (confinement,
SPEC §2) ; le verrou vit **hors** zone synchronisée (vigilance §12.9).
"""

from __future__ import annotations

import argparse
import os
import sys
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
import sync  # noqa: E402


def _line(op: str, rc: int) -> str:
    return f"{'✅' if rc == 0 else '❌'} {op} (code {rc})"


def _flush_warnings(backend) -> None:
    for w in getattr(backend, "warnings", []):
        print(f"⚠️  {w}")


def _with_lock(cfg, fn) -> int:
    """Exécute `fn` sous verrou ; verrou déjà tenu = skip propre (code 0, SPEC §10)."""
    try:
        lk = sync.lock(cfg)
    except sync.LockHeld as exc:
        print(f"🔒 {exc} — une autre synchro tourne, skip.")
        return 0
    try:
        return fn()
    finally:
        lk.release()


def cmd_lock(cfg, **_) -> int:
    return _with_lock(cfg, lambda: (print("✅ verrou disponible"), 0)[1])


def cmd_pull(cfg, **_) -> int:
    def run():
        backend = sync.get_backend(cfg)
        rc = backend.pull()
        print(_line("pull", rc))
        _flush_warnings(backend)
        return rc

    return _with_lock(cfg, run)


def cmd_push(cfg, **_) -> int:
    def run():
        backend = sync.get_backend(cfg)
        rc = backend.push()
        print(_line("push", rc))
        _flush_warnings(backend)
        return rc

    return _with_lock(cfg, run)


def cmd_validate(cfg, **_) -> int:
    def run():
        rc = sync.get_backend(cfg).validate()
        print(_line("validate", rc))
        return rc

    return _with_lock(cfg, run)


def cmd_sync(cfg, *, dry_run: bool = False) -> int:
    """Cycle complet `pull → push → validate` sous un unique verrou."""

    def cycle():
        backend = sync.get_backend(cfg)
        rc = backend.pull()
        print(_line("pull", rc))
        if rc != 0:
            return rc
        if not dry_run:
            rc = backend.push()
            print(_line("push", rc))
            if rc != 0:
                _flush_warnings(backend)
                return rc
        rc = backend.validate()
        print(_line("validate", rc))
        _flush_warnings(backend)
        return rc

    return _with_lock(cfg, cycle)


_COMMANDS = {
    "lock": cmd_lock,
    "pull": cmd_pull,
    "push": cmd_push,
    "validate": cmd_validate,
    "sync": cmd_sync,
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Synchronisation pluggable du vault (Mimir).")
    parser.add_argument(
        "--config", default=None,
        help="Chemin du wiki.config.json (optionnel ; auto-découverte si omis : "
             "$MIMIR_CONFIG, ~/.config/mimir/wiki.config.json, ./wiki.config.json)",
    )
    parser.add_argument("command", choices=sorted(_COMMANDS), help="Opération de synchro")
    parser.add_argument("--dry-run", action="store_true", help="`sync` : pull+validate sans push")
    args = parser.parse_args(argv)

    cfg = config_loader.load_resolved_config(args.config)
    if args.command == "sync":
        return cmd_sync(cfg, dry_run=args.dry_run)
    return _COMMANDS[args.command](cfg)


if __name__ == "__main__":
    raise SystemExit(main())

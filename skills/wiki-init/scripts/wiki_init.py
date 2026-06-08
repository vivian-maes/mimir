#!/usr/bin/env python3
"""wiki-init — amorçage du vault Mimir au premier usage (SPEC §2, §3, §10).

Usage :
    wiki_init.py [--config <wiki.config.json>] {apply|status} [--skip-sync]

- `status` : diagnostic en **lecture seule** — imprime le `wiki.config.json` résolu et
  tous les chemins dérivés (work_root, _inbox, raw, wiki, reading-grids), en signalant
  ce qui existe (✓) ou manque (✗). Répond à « où est mon wiki ».
- `apply`  : (défaut) crée la racine + l'arborescence, écrit un accueil `_inbox/` et un
  `wiki/INDEX.md` initial **s'ils sont absents** (jamais d'écrasement), puis amorce la
  synchro (`pull` → `push` sous verrou).

Sur un `work_root` vide, rien n'existe encore (ni `_inbox/` où déposer, ni état de
synchro) : `config_loader` ne crée rien et les autres skills ne créent leurs dossiers
qu'implicitement, à la première écriture. Ce skill pose donc la structure une fois,
de façon **idempotente** et **bornée à work_root** (confinement, §2).
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
import guard  # noqa: E402
import iohelpers  # noqa: E402
import sync  # noqa: E402

#: Fichier d'accueil déposé dans `_inbox/` (mode d'emploi pour l'utilisateur).
INBOX_README_NAME = "LISEZ-MOI.md"
#: Index initial déposé dans `wiki/` (point de départ ; régénéré par wiki-index).
INDEX_NAME = "INDEX.md"

_INBOX_README = """# _inbox — dépose ici tes sources

C'est la **boîte d'entrée** de ton second cerveau. Tout ce que tu déposes ici est
digéré automatiquement par Mimir :

- **PDF** et **EPUB** : glisse le fichier dans ce dossier.
- **Page web** : crée un fichier `.url` (ou donne le lien à Mimir) — il sera clippé.

Mimir extrait la matière brute vers `raw/` (immuable), puis la compile en articles
par notion dans `wiki/`. Le dossier `_inbox/` est **vidé** au fil du traitement
(le binaire est déplacé vers `raw/`, jamais copié).

> Ce fichier est informatif : tu peux le laisser, il n'est pas traité comme une source.
"""

_INDEX_INIT = """# Index du wiki

> Index initial posé par `wiki-init`. Il sera **régénéré automatiquement** par
> `wiki-index` dès que des articles existeront (`wiki-index regenerate`).

_Aucun sujet pour l'instant — dépose une première source dans `_inbox/` pour démarrer._
"""


def _line(op: str, rc: int) -> str:
    return f"{'✅' if rc == 0 else '❌'} {op} (code {rc})"


def _structure(cfg) -> list[tuple[str, Path]]:
    """Dossiers de base à garantir (ordre logique du pipeline), ancrés sur work_root."""
    return [
        ("_inbox", cfg.INBOX),
        ("raw", cfg.RAW),
        ("wiki", cfg.WIKI),
        ("reading-grids", cfg.READING_GRIDS),
    ]


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


# --- status (lecture seule) ------------------------------------------------
def cmd_status(cfg, **_) -> int:
    """Imprime la config résolue + l'état de la structure (existe / manquant)."""
    print(f"CONFIG_PATH={cfg.config_path}")
    for key, value in cfg.as_dict().items():
        print(f"{key}={value}")

    print("\nÉtat de la structure :")
    root = Path(cfg.work_root)
    print(f"  {'✓' if root.is_dir() else '✗'} work_root        {root}")
    for label, path in _structure(cfg):
        print(f"  {'✓' if Path(path).is_dir() else '✗'} {label:<15} {path}")
    files = [
        ("_inbox/" + INBOX_README_NAME, cfg.INBOX / INBOX_README_NAME),
        ("wiki/" + INDEX_NAME, cfg.WIKI / INDEX_NAME),
    ]
    for label, path in files:
        print(f"  {'✓' if Path(path).is_file() else '✗'} {label:<15} {path}")
    return 0


# --- apply -----------------------------------------------------------------
def _write_if_absent(cfg, path: Path, content: str) -> None:
    """Écrit `content` atomiquement (confiné) seulement si `path` n'existe pas."""
    guard.assert_within(cfg.work_root, path)
    if Path(path).exists():
        print(f"  · {path.name} déjà présent (inchangé)")
        return
    iohelpers.atomic_write_text(path, content, work_root=cfg.work_root)
    print(f"  + {path.name} créé")


def _amorcer_sync(cfg) -> int:
    """Premier cycle `pull` → `push` sous verrou (rclone amorce seul ; git premier commit)."""
    print("\nAmorçage de la synchro :")

    def run() -> int:
        backend = sync.get_backend(cfg)
        rc = backend.pull()
        print(_line("pull", rc))
        if rc == 0:
            rc = backend.push()
            print(_line("push", rc))
        for w in getattr(backend, "warnings", []):
            print(f"⚠️  {w}")
        return rc

    return _with_lock(cfg, run)


def cmd_apply(cfg, *, skip_sync: bool = False, **_) -> int:
    """Crée l'arborescence + l'accueil + l'INDEX (idempotent), puis amorce la synchro."""
    print("Création de l'arborescence (sous work_root) :")
    for label, path in [("work_root", Path(cfg.work_root))] + _structure(cfg):
        guard.assert_within(cfg.work_root, path)  # refuse un layout d'évasion (../)
        existed = Path(path).is_dir()
        iohelpers.ensure_dir(path)
        print(f"  {'·' if existed else '+'} {label:<15} {path}")

    print("\nFichiers d'amorçage :")
    _write_if_absent(cfg, cfg.INBOX / INBOX_README_NAME, _INBOX_README)
    _write_if_absent(cfg, cfg.WIKI / INDEX_NAME, _INDEX_INIT)

    rc = 0
    if skip_sync:
        print("\n↪ Synchro sautée (--skip-sync).")
    else:
        rc = _amorcer_sync(cfg)

    print("\nRécapitulatif :")
    cmd_status(cfg)
    return rc


_COMMANDS = {"apply": cmd_apply, "status": cmd_status}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Initialise le wiki Mimir (structure + amorçage synchro)."
    )
    parser.add_argument(
        "--config", default=None,
        help="Chemin du wiki.config.json (optionnel ; auto-découverte si omis : "
             "$MIMIR_CONFIG, dossier du profil, ~/.config/mimir/wiki.config.json, ./wiki.config.json)",
    )
    parser.add_argument(
        "command", nargs="?", choices=sorted(_COMMANDS), default="apply",
        help="apply (défaut) : crée la structure + amorce la synchro ; status : diagnostic lecture seule.",
    )
    parser.add_argument(
        "--skip-sync", action="store_true",
        help="apply : crée la structure sans amorcer la synchro (hors-ligne / backend noop).",
    )
    args = parser.parse_args(argv)

    cfg = config_loader.load_resolved_config(args.config)
    if args.command == "status":
        return cmd_status(cfg)
    return cmd_apply(cfg, skip_sync=args.skip_sync)


if __name__ == "__main__":
    raise SystemExit(main())

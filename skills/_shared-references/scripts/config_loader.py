#!/usr/bin/env python3
"""Chargeur de `wiki.config.json` — résout `work_root` et dérive les chemins.

`work_root` est la **racine unique** ; toutes les autres variables en dérivent
(SPEC §2). Tous les chemins exposés sont **absolus** : les sessions cron Hermes
n'ont pas de `cwd` garanti (vigilance §12.7).

Deux usages de `work_root`, le **mode étant déduit du chemin** (pas de flag) :

- **Mode A — vault complet** : `work_root` = racine du vault Obsidian
  (détectée par la présence d'un dossier `.obsidian/`).
- **Mode B — répertoire dédié** : `work_root` = un sous-répertoire `[base_repertoire]`.

La résolution des chemins est **identique** dans les deux modes (tout est ancré
sur `work_root`) ; le mode n'est qu'informatif et sert au périmètre de synchro (§10).

Usage CLI (diagnostic) :

    python config_loader.py /chemin/vers/wiki.config.json
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

try:  # validation par schéma si la dépendance est présente (sinon fallback manuel)
    import jsonschema  # type: ignore
except Exception:  # pragma: no cover - dépendance optionnelle
    jsonschema = None  # type: ignore

_SCHEMA_PATH = Path(__file__).resolve().parent.parent / "schema" / "wiki.config.schema.json"

#: Layout par défaut (SPEC §2/§3) — surchargé par la clé `layout` du config.
DEFAULT_LAYOUT = {
    "inbox": "_inbox",
    "raw": "raw",
    "wiki": "wiki",
    "reading_grids": "reading-grids",
    "ledger": ".wiki/ingest-ledger.json",
}

#: Nom de dossier des assets (un par sujet wiki ET un par type raw — vigilance §12.14).
ASSETS_DIRNAME = "_assets"

VALID_BACKENDS = {"rclone", "git"}


class ConfigError(ValueError):
    """Config absente, illisible, ou non conforme."""


@dataclass(frozen=True)
class Config:
    """Vue résolue d'un `wiki.config.json` (tous chemins absolus)."""

    config_path: Path
    work_root: Path
    layout: dict[str, str]
    sync: dict[str, Any] = field(default_factory=dict)
    mode: str = "B"  # "A" (vault complet) | "B" (répertoire dédié)

    # --- chemins dérivés (absolus), ancrés sur work_root --------------------
    @property
    def INBOX(self) -> Path:
        """Dropzone des sources à traiter (synchronisée, vidée par wiki-extract)."""
        return self.work_root / self.layout["inbox"]

    @property
    def RAW(self) -> Path:
        return self.work_root / self.layout["raw"]

    @property
    def WIKI(self) -> Path:
        return self.work_root / self.layout["wiki"]

    @property
    def READING_GRIDS(self) -> Path:
        return self.work_root / self.layout["reading_grids"]

    @property
    def LEDGER(self) -> Path:
        return self.work_root / self.layout["ledger"]

    @property
    def ASSETS_DIRNAME(self) -> str:
        """Nom (pas chemin) du dossier d'assets : il y en a un par conteneur."""
        return ASSETS_DIRNAME

    @property
    def backend(self) -> str:
        return str(self.sync.get("backend", "rclone"))

    def as_dict(self) -> dict[str, str]:
        """Variables dérivées, pratique pour le diagnostic / l'export shell."""
        return {
            "WORK_ROOT": str(self.work_root),
            "INBOX": str(self.INBOX),
            "RAW": str(self.RAW),
            "WIKI": str(self.WIKI),
            "READING_GRIDS": str(self.READING_GRIDS),
            "LEDGER": str(self.LEDGER),
            "MODE": self.mode,
            "BACKEND": self.backend,
        }


def _detect_mode(work_root: Path) -> str:
    """Mode A si `work_root` ressemble à une racine de vault (`.obsidian/`), sinon B."""
    return "A" if (work_root / ".obsidian").is_dir() else "B"


def _validate(raw: dict[str, Any]) -> None:
    """Valide la structure du config (schéma JSON si dispo, sinon contrôles manuels)."""
    if jsonschema is not None and _SCHEMA_PATH.exists():
        schema = json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))
        try:
            jsonschema.validate(raw, schema)
        except jsonschema.ValidationError as exc:  # type: ignore[attr-defined]
            raise ConfigError(f"wiki.config.json non conforme : {exc.message}") from exc
        return

    # Fallback manuel (jsonschema absent) — couvre l'essentiel du DoD.
    if not isinstance(raw.get("work_root"), str) or not raw["work_root"].strip():
        raise ConfigError("`work_root` manquant ou vide.")
    backend = raw.get("sync", {}).get("backend", "rclone")
    if backend not in VALID_BACKENDS:
        raise ConfigError(f"`sync.backend` invalide : {backend!r} (attendu : {VALID_BACKENDS}).")


def load_config(config_path: str | os.PathLike[str]) -> Config:
    """Charge et valide un `wiki.config.json`, renvoie une `Config` résolue."""
    path = Path(os.path.expanduser(os.fspath(config_path))).resolve()
    if not path.is_file():
        raise ConfigError(f"Config introuvable : {path}")
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ConfigError(f"JSON invalide dans {path} : {exc}") from exc

    _validate(raw)

    work_root = Path(os.path.expanduser(raw["work_root"]))
    if not work_root.is_absolute():
        # Un work_root relatif est ancré sur le dossier du config (cohérence cron).
        work_root = (path.parent / work_root)
    work_root = Path(os.path.realpath(work_root))

    layout = {**DEFAULT_LAYOUT, **(raw.get("layout") or {})}
    mode = raw.get("mode") or _detect_mode(work_root)

    return Config(
        config_path=path,
        work_root=work_root,
        layout=layout,
        sync=raw.get("sync") or {},
        mode=mode,
    )


if __name__ == "__main__":  # diagnostic
    import sys

    if len(sys.argv) != 2:
        print("Usage: config_loader.py <wiki.config.json>", file=sys.stderr)
        raise SystemExit(2)
    cfg = load_config(sys.argv[1])
    for key, value in cfg.as_dict().items():
        print(f"{key}={value}")

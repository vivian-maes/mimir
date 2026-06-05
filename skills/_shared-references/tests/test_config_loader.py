"""Tests du chargeur de config — résolution modes A/B + validation (DoD Phase 0)."""

import json
from pathlib import Path

import pytest

import config_loader
from config_loader import ConfigError, load_config


def _write_config(dir_: Path, work_root: Path, **extra) -> Path:
    cfg = {
        "work_root": str(work_root),
        "layout": {
            "raw": "raw",
            "wiki": "wiki",
            "reading_grids": "reading-grids",
            "ledger": ".wiki/ingest-ledger.json",
        },
        "sync": {"backend": "rclone"},
        **extra,
    }
    path = dir_ / "wiki.config.json"
    path.write_text(json.dumps(cfg), encoding="utf-8")
    return path


def test_mode_A_vault_complet(tmp_path: Path):
    """work_root = racine de vault (présence .obsidian/) → mode A, chemins sous le vault."""
    vault = tmp_path / "MonVault"
    (vault / ".obsidian").mkdir(parents=True)
    cfg_path = _write_config(tmp_path, vault)

    cfg = load_config(cfg_path)

    assert cfg.mode == "A"
    assert cfg.work_root == Path(vault).resolve()
    assert cfg.RAW == cfg.work_root / "raw"
    assert cfg.WIKI == cfg.work_root / "wiki"
    assert cfg.READING_GRIDS == cfg.work_root / "reading-grids"
    assert cfg.LEDGER == cfg.work_root / ".wiki" / "ingest-ledger.json"


def test_mode_B_repertoire_dedie(tmp_path: Path):
    """work_root = sous-répertoire dédié (pas de .obsidian/) → mode B, tout résolu dedans."""
    vault = tmp_path / "MonVault"
    base = vault / "02 - second cerveau"
    base.mkdir(parents=True)
    cfg_path = _write_config(tmp_path, base)

    cfg = load_config(cfg_path)

    assert cfg.mode == "B"
    assert cfg.work_root == Path(base).resolve()
    # Tout vit DANS le sous-répertoire, jamais à la racine du vault.
    assert str(cfg.RAW).startswith(str(base.resolve()))
    assert cfg.WIKI == cfg.work_root / "wiki"


def test_tous_chemins_absolus(tmp_path: Path):
    base = tmp_path / "dedie"
    base.mkdir()
    cfg = load_config(_write_config(tmp_path, base))
    for p in (cfg.work_root, cfg.RAW, cfg.WIKI, cfg.READING_GRIDS, cfg.LEDGER):
        assert p.is_absolute()


def test_work_root_relatif_ancre_sur_config(tmp_path: Path):
    """Un work_root relatif est ancré sur le dossier du config (sessions cron)."""
    base = tmp_path / "rel"
    base.mkdir()
    cfg_path = _write_config(tmp_path, Path("rel"))
    cfg = load_config(cfg_path)
    assert cfg.work_root == base.resolve()


def test_mode_force_dans_config(tmp_path: Path):
    base = tmp_path / "x"
    base.mkdir()
    cfg = load_config(_write_config(tmp_path, base, mode="A"))
    assert cfg.mode == "A"


def test_layout_par_defaut_si_absent(tmp_path: Path):
    base = tmp_path / "y"
    base.mkdir()
    path = base / "wiki.config.json"
    path.write_text(json.dumps({"work_root": str(base)}), encoding="utf-8")
    cfg = load_config(path)
    assert cfg.RAW == base.resolve() / "raw"
    assert cfg.backend == "rclone"


def test_config_introuvable(tmp_path: Path):
    with pytest.raises(ConfigError):
        load_config(tmp_path / "absent.json")


def test_json_invalide(tmp_path: Path):
    path = tmp_path / "wiki.config.json"
    path.write_text("{ pas du json", encoding="utf-8")
    with pytest.raises(ConfigError):
        load_config(path)


def test_work_root_manquant(tmp_path: Path):
    path = tmp_path / "wiki.config.json"
    path.write_text(json.dumps({"layout": {}}), encoding="utf-8")
    with pytest.raises(ConfigError):
        load_config(path)


def test_backend_invalide_rejete_en_fallback(tmp_path: Path, monkeypatch):
    """Sans jsonschema, le fallback manuel rejette un backend inconnu."""
    monkeypatch.setattr(config_loader, "jsonschema", None)
    base = tmp_path / "z"
    base.mkdir()
    cfg_path = _write_config(tmp_path, base, sync={"backend": "dropbox"})
    with pytest.raises(ConfigError):
        load_config(cfg_path)


def test_exemple_repo_se_charge():
    """wiki.config.example.json (racine repo) est chargeable et expose des chemins absolus."""
    example = Path(__file__).resolve().parents[3] / "wiki.config.example.json"
    cfg = load_config(example)
    d = cfg.as_dict()
    assert Path(d["RAW"]).is_absolute()
    assert d["BACKEND"] == "rclone"

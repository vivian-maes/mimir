"""Tests de l'auto-découverte du config — resolve_config_path / load_resolved_config.

Ordre de résolution garanti : explicit > $MIMIR_CONFIG > ~/.config/mimir > ./
(cf. config_loader.resolve_config_path). Tous les tests isolent l'environnement
via monkeypatch (HOME, MIMIR_CONFIG, cwd) pour ne dépendre d'aucun état machine.
"""

import json
from pathlib import Path

import pytest

import config_loader
from config_loader import (
    ConfigError,
    ENV_CONFIG,
    load_resolved_config,
    resolve_config_path,
)


def _make_config(path: Path) -> Path:
    """Écrit un wiki.config.json minimal valide à `path` (work_root = parent)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"work_root": str(path.parent)}), encoding="utf-8")
    return path


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch, tmp_path):
    """Environnement neutre : pas de MIMIR_CONFIG hérité, et `_self_root` neutralisé.

    `_self_root()` renvoie en vrai la racine du repo : un `wiki.config.json` y
    traînant fausserait les tests. On le pointe par défaut vers un dossier vide ;
    les tests qui veulent exercer ce candidat le re-monkeypatchent explicitement.
    """
    monkeypatch.delenv(ENV_CONFIG, raising=False)
    monkeypatch.setattr(config_loader, "_self_root", lambda: tmp_path / "no-self-root")


def test_explicit_prioritaire_sur_tout(tmp_path, monkeypatch):
    """Un chemin explicite court-circuite env, XDG et cwd."""
    explicit = tmp_path / "perso" / "wiki.config.json"
    _make_config(explicit)
    # Bruit : env + XDG + cwd existent aussi, mais explicit doit gagner.
    env_cfg = _make_config(tmp_path / "env" / "wiki.config.json")
    monkeypatch.setenv(ENV_CONFIG, str(env_cfg))
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    _make_config(Path(tmp_path / "home" / ".config" / "mimir" / "wiki.config.json"))
    monkeypatch.chdir(tmp_path)
    _make_config(tmp_path / "wiki.config.json")

    assert resolve_config_path(str(explicit)) == explicit.resolve()


def test_explicit_inexistant_renvoye_sans_verif(tmp_path):
    """Explicit absent du disque : renvoyé tel quel (load_config lèvera l'erreur)."""
    explicit = tmp_path / "n-existe-pas.json"
    assert resolve_config_path(str(explicit)) == explicit.resolve()


def test_env_prioritaire(tmp_path, monkeypatch):
    """MIMIR_CONFIG gagne quand env, XDG et cwd existent tous."""
    env_cfg = _make_config(tmp_path / "env" / "wiki.config.json")
    monkeypatch.setenv(ENV_CONFIG, str(env_cfg))
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    _make_config(tmp_path / "home" / ".config" / "mimir" / "wiki.config.json")
    monkeypatch.chdir(tmp_path)
    _make_config(tmp_path / "wiki.config.json")

    assert resolve_config_path() == env_cfg.resolve()


def test_xdg_si_pas_env(tmp_path, monkeypatch):
    """Sans env : ~/.config/mimir/wiki.config.json est choisi."""
    home = tmp_path / "home"
    xdg = _make_config(home / ".config" / "mimir" / "wiki.config.json")
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.chdir(tmp_path)  # pas de ./wiki.config.json ici

    assert resolve_config_path() == xdg.resolve()


def test_cwd_en_dernier(tmp_path, monkeypatch):
    """Sans env ni XDG : ./wiki.config.json est le dernier recours."""
    monkeypatch.setenv("HOME", str(tmp_path / "home-vide"))
    workdir = tmp_path / "work"
    cwd_cfg = _make_config(workdir / "wiki.config.json")
    monkeypatch.chdir(workdir)

    assert resolve_config_path() == cwd_cfg.resolve()


def test_ordre_xdg_avant_cwd(tmp_path, monkeypatch):
    """XDG ET cwd existent, pas d'env → XDG l'emporte."""
    home = tmp_path / "home"
    xdg = _make_config(home / ".config" / "mimir" / "wiki.config.json")
    monkeypatch.setenv("HOME", str(home))
    workdir = tmp_path / "work"
    _make_config(workdir / "wiki.config.json")
    monkeypatch.chdir(workdir)

    assert resolve_config_path() == xdg.resolve()


def test_racine_profil_si_pas_env(tmp_path, monkeypatch):
    """Sans env : le wiki.config.json du dossier du profil/repo est découvert."""
    profile = tmp_path / "profile"
    cfg = _make_config(profile / "wiki.config.json")
    monkeypatch.setattr(config_loader, "_self_root", lambda: profile)
    monkeypatch.setenv("HOME", str(tmp_path / "home-vide"))
    monkeypatch.chdir(tmp_path)  # pas de ./wiki.config.json

    assert resolve_config_path() == cfg.resolve()


def test_env_prioritaire_sur_racine_profil(tmp_path, monkeypatch):
    """$MIMIR_CONFIG l'emporte sur le wiki.config.json du dossier du profil."""
    env_cfg = _make_config(tmp_path / "env" / "wiki.config.json")
    monkeypatch.setenv(ENV_CONFIG, str(env_cfg))
    profile = tmp_path / "profile"
    _make_config(profile / "wiki.config.json")
    monkeypatch.setattr(config_loader, "_self_root", lambda: profile)

    assert resolve_config_path() == env_cfg.resolve()


def test_racine_profil_avant_xdg(tmp_path, monkeypatch):
    """Racine profil ET XDG existent, pas d'env → la racine profil l'emporte."""
    profile = tmp_path / "profile"
    cfg = _make_config(profile / "wiki.config.json")
    monkeypatch.setattr(config_loader, "_self_root", lambda: profile)
    home = tmp_path / "home"
    _make_config(home / ".config" / "mimir" / "wiki.config.json")
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.chdir(tmp_path)

    assert resolve_config_path() == cfg.resolve()


def test_env_fichier_absent_passe_au_suivant(tmp_path, monkeypatch):
    """MIMIR_CONFIG pointant un fichier absent → on retombe sur XDG (tolérant)."""
    monkeypatch.setenv(ENV_CONFIG, str(tmp_path / "fantome.json"))
    home = tmp_path / "home"
    xdg = _make_config(home / ".config" / "mimir" / "wiki.config.json")
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.chdir(tmp_path)

    assert resolve_config_path() == xdg.resolve()


def test_aucun_trouve_leve_configerror(tmp_path, monkeypatch):
    """Rien nulle part → ConfigError actionnable mentionnant les 4 emplacements."""
    # _self_root déjà neutralisé vers un dossier vide par l'autouse fixture.
    monkeypatch.setenv("HOME", str(tmp_path / "home-vide"))
    empty = tmp_path / "vide"
    empty.mkdir()
    monkeypatch.chdir(empty)

    with pytest.raises(ConfigError) as exc:
        resolve_config_path()
    msg = str(exc.value)
    assert ENV_CONFIG in msg
    assert "dossier du profil/repo" in msg
    assert ".config/mimir/wiki.config.json" in msg
    assert "wiki.config.json" in msg


def test_load_resolved_config_bout_en_bout(tmp_path, monkeypatch):
    """load_resolved_config() via MIMIR_CONFIG renvoie une Config exploitable."""
    env_cfg = _make_config(tmp_path / "env" / "wiki.config.json")
    monkeypatch.setenv(ENV_CONFIG, str(env_cfg))

    cfg = load_resolved_config()
    assert cfg.config_path == env_cfg.resolve()
    assert cfg.work_root.is_absolute()

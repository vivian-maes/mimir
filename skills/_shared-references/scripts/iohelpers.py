#!/usr/bin/env python3
"""Helpers d'E/S partagés — écriture atomique confinée, hachage, suffixage `-2`.

Mutualisés entre `wiki-extract` (Phase 1) et `wiki-ingest` (Phase 2, ledger
atomique + SHA de contenu). Toute écriture passe par la garde de confinement
(`guard.assert_within`) : rien ne s'écrit hors `work_root` (SPEC §2, §12.8).

L'écriture atomique = fichier temporaire **dans le même dossier** + `os.replace`
(atomique sur POSIX/APFS) : pas de fichier à moitié écrit, et le `rename` ne
traverse pas de système de fichiers.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any

import guard  # même dossier scripts/ (résolu via sys.path par le bootstrap / conftest)


# --- hachage ---------------------------------------------------------------
def sha256_text(text: str) -> str:
    """SHA256 d'un contenu texte (UTF-8). C'est l'entrée d'ingestion (SPEC §4.3)."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_file(path: str | os.PathLike[str]) -> str:
    """SHA256 d'un fichier (lecture par blocs) — utile pour un registre de binaires."""
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# --- dossiers --------------------------------------------------------------
def ensure_dir(path: str | os.PathLike[str]) -> Path:
    """Crée le dossier (et ses parents) s'il manque ; renvoie le `Path`."""
    p = Path(path)
    p.mkdir(parents=True, exist_ok=True)
    return p


# --- écriture atomique confinée -------------------------------------------
def _atomic_write(path: Path, *, work_root: Path, write) -> Path:
    """Coeur commun : confine, écrit un tmp dans le même dossier, `os.replace`."""
    target = guard.assert_within(work_root, path)
    ensure_dir(target.parent)
    fd, tmp_name = tempfile.mkstemp(dir=str(target.parent), prefix=".tmp-", suffix=target.suffix)
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as fh:
            write(fh)
        os.replace(tmp, target)  # atomique, même FS
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    return target


def atomic_write_text(
    path: str | os.PathLike[str], text: str, *, work_root: str | os.PathLike[str]
) -> Path:
    """Écrit `text` (UTF-8) de façon atomique et confinée. Renvoie le chemin final."""
    return _atomic_write(
        Path(path), work_root=Path(work_root), write=lambda fh: fh.write(text.encode("utf-8"))
    )


def atomic_write_bytes(
    path: str | os.PathLike[str], data: bytes, *, work_root: str | os.PathLike[str]
) -> Path:
    """Écrit des octets de façon atomique et confinée. Renvoie le chemin final."""
    return _atomic_write(Path(path), work_root=Path(work_root), write=lambda fh: fh.write(data))


def write_json(
    path: str | os.PathLike[str], obj: Any, *, work_root: str | os.PathLike[str]
) -> Path:
    """Sérialise `obj` en JSON lisible (indent 2, accents conservés) et l'écrit atomiquement."""
    text = json.dumps(obj, indent=2, ensure_ascii=False) + "\n"
    return atomic_write_text(path, text, work_root=work_root)


# --- suffixage append-only (`-2`, `-3`…) -----------------------------------
def unique_suffixed_path(
    directory: str | os.PathLike[str], base: str, ext: str
) -> Path:
    """Renvoie `directory/<base>.<ext>` si libre, sinon `<base>-2.<ext>`, `-3`…

    Le suffixe s'insère sur le **slug de base** (`base`), jamais via `Path.stem` :
    cela gère correctement les doubles suffixes (`nom.pdf.txt` -> `nom-2.pdf.txt`),
    où `Path('nom.pdf.txt').stem` vaudrait `'nom.pdf'`. `ext` est l'extension
    logique complète SANS point de tête : `"pdf"`, `"pdf.txt"`, `"epub.txt"`, `"md"`.

    Immutabilité de raw/ (SPEC §4.2) : on ne réutilise jamais un nom existant.
    """
    directory = Path(directory)
    candidate = directory / f"{base}.{ext}"
    if not candidate.exists():
        return candidate
    n = 2
    while True:
        candidate = directory / f"{base}-{n}.{ext}"
        if not candidate.exists():
            return candidate
        n += 1


def unique_suffixed_base(
    directory: str | os.PathLike[str], base: str, exts: list[str]
) -> str:
    """Renvoie un `base` (ou `base-N`) tel qu'AUCUN `<base>.<ext>` n'existe déjà.

    Garantit un nommage **cohérent** entre les fichiers liés d'une même source
    (`<base>.pdf`, `<base>.pdf.txt`, `<base>.toc.json`) : un seul suffixe `-N`
    partagé, décidé en regardant toutes les extensions d'un coup.
    """
    directory = Path(directory)

    def free(b: str) -> bool:
        return all(not (directory / f"{b}.{e}").exists() for e in exts)

    if free(base):
        return base
    n = 2
    while not free(f"{base}-{n}"):
        n += 1
    return f"{base}-{n}"

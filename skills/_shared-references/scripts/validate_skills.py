#!/usr/bin/env python3
"""Validateur de frontmatter agentskills.io — stand-in local de `skills-ref`.

`skills-ref validate` reste le **validateur canonique** du DoD Phase 0 ; il n'est
pas installé sur la machine de dev (cf. `../TOOLING.md`). Ce script applique le
même contrat (SPEC §11) pour la boucle de dev et le CI, et sort en code non-zéro
si un skill échoue :

- frontmatter présent, **pas de ligne vide** avant le premier `---` ;
- `name` requis, `^[a-z0-9]+(-[a-z0-9]+)*$`, **sans `--`**, **== nom du dossier** ;
- `description` requise, **≤ 1024 caractères** ;
- `version`/`platforms`/`title`/`category` **sous `metadata`** (erreur sinon) ;
- corps « léger » : avertissement si > ~5000 tokens (corps d'activation, SPEC §1/§11).

Usage :

    python validate_skills.py skills/wiki-extract            # un skill
    python validate_skills.py skills/wiki-*                   # plusieurs (glob shell)
"""

from __future__ import annotations

import glob
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

try:
    import yaml  # type: ignore
except Exception:  # pragma: no cover - dépendance optionnelle
    yaml = None  # type: ignore

NAME_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
DESCRIPTION_MAX = 1024
BODY_TOKEN_WARN = 5000
#: Clés qui doivent vivre sous `metadata`, pas à la racine (écart vs anciennes skills).
FORBIDDEN_TOPLEVEL = ("version", "platforms", "title", "category")


@dataclass
class Result:
    skill: str
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


def _split_frontmatter(text: str) -> tuple[str | None, str, str | None]:
    """Renvoie (frontmatter, corps, erreur). Exige `---` en toute première ligne."""
    if not text.startswith("---"):
        # Tolère un BOM mais pas une ligne vide / du texte avant le premier ---.
        return None, text, "Frontmatter absent : le fichier doit commencer par '---'."
    lines = text.splitlines()
    if lines[0].strip() != "---":
        return None, text, "La première ligne doit être exactement '---'."
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            fm = "\n".join(lines[1:i])
            body = "\n".join(lines[i + 1 :])
            return fm, body, None
    return None, text, "Frontmatter non terminé (pas de '---' de fermeture)."


def _parse_frontmatter(fm: str) -> tuple[dict, set[str]]:
    """Parse le frontmatter. Renvoie (mapping, clés_racine). Tolère l'absence de PyYAML."""
    if yaml is not None:
        data = yaml.safe_load(fm) or {}
        if not isinstance(data, dict):
            return {}, set()
        return data, set(data.keys())
    # Fallback : clés de premier niveau = lignes 'clef:' sans indentation.
    toplevel: set[str] = set()
    data: dict = {}
    current_key: str | None = None
    for line in fm.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if line[0] not in (" ", "\t"):
            m = re.match(r"^([A-Za-z0-9_-]+)\s*:\s*(.*)$", line)
            if m:
                current_key = m.group(1)
                toplevel.add(current_key)
                value = m.group(2).strip()
                # description multi-ligne via '>' ou '|' : capturée grossièrement ensuite.
                data[current_key] = value if value not in (">", "|", ">-", "|-") else ""
        elif current_key and data.get(current_key, None) == "":
            data[current_key] = (str(data[current_key]) + " " + line.strip()).strip()
    return data, toplevel


def validate_skill(skill_dir: Path) -> Result:
    res = Result(skill=skill_dir.name)
    skill_md = skill_dir / "SKILL.md"
    if not skill_md.is_file():
        res.errors.append("SKILL.md manquant.")
        return res

    text = skill_md.read_text(encoding="utf-8")
    fm, body, err = _split_frontmatter(text)
    if err:
        res.errors.append(err)
        return res

    data, toplevel = _parse_frontmatter(fm or "")

    name = str(data.get("name", "")).strip()
    if not name:
        res.errors.append("`name` requis.")
    else:
        if "--" in name or not NAME_RE.match(name):
            res.errors.append(f"`name` invalide : {name!r} (attendu [a-z0-9-], pas de '--').")
        if name != skill_dir.name:
            res.errors.append(
                f"`name` ({name!r}) doit être identique au nom du dossier ({skill_dir.name!r})."
            )

    description = str(data.get("description", "")).strip()
    if not description:
        res.errors.append("`description` requise.")
    elif len(description) > DESCRIPTION_MAX:
        res.errors.append(
            f"`description` trop longue : {len(description)} > {DESCRIPTION_MAX} caractères."
        )

    for key in FORBIDDEN_TOPLEVEL:
        if key in toplevel:
            res.errors.append(f"`{key}` doit vivre sous `metadata`, pas à la racine du frontmatter.")

    # Corps d'activation léger (~4 caractères/token).
    if len(body) / 4 > BODY_TOKEN_WARN:
        res.warnings.append(
            f"corps SKILL.md volumineux (~{int(len(body) / 4)} tokens > {BODY_TOKEN_WARN}) :"
            " déporter le détail dans references/."
        )
    return res


def _expand(paths: list[str]) -> list[Path]:
    out: list[Path] = []
    for p in paths:
        matches = glob.glob(p)
        targets = matches if matches else [p]
        for t in targets:
            path = Path(t)
            if path.is_dir() and path.name != "_shared-references":
                out.append(path)
    return out


def main(argv: list[str]) -> int:
    if not argv:
        print("Usage: validate_skills.py <skill_dir> [<skill_dir> ...]", file=sys.stderr)
        return 2

    skill_dirs = _expand(argv)
    if not skill_dirs:
        print("Aucun dossier de skill trouvé.", file=sys.stderr)
        return 2

    failed = 0
    for skill_dir in sorted(skill_dirs):
        res = validate_skill(skill_dir)
        if res.ok:
            mark = "OK  "
        else:
            mark = "FAIL"
            failed += 1
        print(f"[{mark}] {res.skill}")
        for w in res.warnings:
            print(f"       ⚠ {w}")
        for e in res.errors:
            print(f"       ✗ {e}")

    total = len(skill_dirs)
    print(f"\n{total - failed}/{total} skills valides.")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

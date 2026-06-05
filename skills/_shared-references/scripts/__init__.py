"""Socle commun des skills Mimir (Phase 0 — Fondations).

Code mutualisé entre les 5 skills `wiki-*` :

- `config_loader` : charge `wiki.config.json` et dérive les chemins absolus.
- `guard`         : garde de confinement bornant toute opération à `work_root`.
- `slug`          : slugs ASCII kebab-case + helpers NFD/NFC.
- `validate_skills` : validateur de frontmatter agentskills.io (stand-in `skills-ref`).

Voir `../CONVENTIONS.md` et la SPEC (§1–§3, §11).
"""

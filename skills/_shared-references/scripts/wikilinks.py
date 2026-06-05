#!/usr/bin/env python3
"""Extraction, résolution et ancrage des wikilinks Obsidian (`[[…]]`).

Mutualisé par `wiki-reading-grid` (grille + liens Précédent/Suivant) et `wiki-index`
(génération + audit liens). Règles Mimir (SPEC §9) :

- **Résolution** : normaliser chaque cible avec `os.path.normpath` AVANT le test
  d'existence (sinon faux positifs sur les `..`), comparer les noms via NFD/NFC
  (`slug.same_file`), et confiner à `work_root`.
- **Forme majoritaire** : un vault écrit ses wikilinks soit préfixés (`[[wiki/x]]`)
  soit relatifs (`[[x]]`). On détecte la forme dominante pour rester cohérent à
  l'écriture des index.

Ancrage des chapitres (`chapter_anchor`) : la grille de lecture relie les chapitres
par des liens intra-document `[[#…]]`. Obsidian résout un lien d'ancre vers un
**titre dont le texte est identique** ; on fait donc dériver le **titre du chapitre
et le lien Précédent/Suivant de la même fonction**, ce qui garantit qu'un lien pointe
toujours vers un titre réellement présent (pas de lien interne cassé).
"""

from __future__ import annotations

import os
import re
from collections import Counter
from pathlib import Path

import guard
import slug

#: Tout `[[ ... ]]` ; le contenu interne est nettoyé ensuite (alias, ancre).
_WIKILINK_RE = re.compile(r"\[\[([^\]]+)\]\]")

#: Préfixes de chemin = wikilink « préfixé » (vs relatif au dossier courant).
_PREFIXES = ("wiki/", "reading-grids/", "raw/")


def _target_of(inner: str) -> str | None:
    """Cible nette d'un `[[inner]]` : sans alias `|…`, sans ancre `#…`/`^…`.

    Renvoie `None` pour un lien purement intra-document (`[[#titre]]`/`[[^bloc]]`),
    hors périmètre d'un audit de liens entre fichiers.
    """
    inner = inner.split("|", 1)[0].strip()
    if not inner or inner[0] in "#^":
        return None
    # retire une éventuelle ancre de titre/bloc en fin de cible
    for sep in ("#", "^"):
        idx = inner.find(sep)
        if idx != -1:
            inner = inner[:idx]
    return inner.strip() or None


def extract_wikilinks(md_text: str) -> list[str]:
    """Cibles de tous les wikilinks d'un texte (hors ancres pures), ordre conservé."""
    out: list[str] = []
    for m in _WIKILINK_RE.finditer(md_text):
        target = _target_of(m.group(1))
        if target is not None:
            out.append(target)
    return out


def majority_form(targets: list[str]) -> str:
    """`"prefixed"` si la majorité des cibles « article » sont préfixées, sinon `"relative"`.

    On ne compte que les cibles pointant dans le vault (contenant un `/`), pour ne
    pas laisser les liens simples (`[[notion]]`) fausser la mesure.
    """
    counter: Counter[str] = Counter()
    for t in targets:
        if "/" not in t:
            continue
        counter["prefixed" if t.startswith(_PREFIXES) else "relative"] += 1
    if counter["prefixed"] > counter["relative"]:
        return "prefixed"
    return "relative"


def _exists_nfc_safe(path: Path) -> bool:
    """Existence NFD/NFC-tolérante : match exact, sinon comparaison de noms (APFS)."""
    if path.exists():
        return True
    parent = path.parent
    if not parent.is_dir():
        return False
    return any(slug.same_file(p.name, path.name) for p in parent.iterdir())


def resolve(cfg, src_file: Path, target: str) -> Path | None:
    """Résout une cible de wikilink vers un fichier réel sous `work_root`, ou `None`.

    Essaie, dans l'ordre : forme préfixée (depuis `work_root`), forme relative au
    `wiki/` (`sujet/notion`), puis relative au dossier du fichier source. Chaque
    candidat passe par `os.path.normpath` avant le test d'existence.
    """
    target = target.strip()
    if not target:
        return None
    rel = f"{target}.md"
    candidates = [
        cfg.work_root / rel,        # préfixée : wiki/…, reading-grids/…
        cfg.WIKI / rel,             # relative au wiki : sujet/notion, sujet/_INDEX
        src_file.parent / rel,      # relative au fichier courant
    ]
    for cand in candidates:
        norm = Path(os.path.normpath(cand))
        if not guard.is_within(cfg.work_root, norm):
            continue
        if _exists_nfc_safe(norm):
            return norm
    return None


def chapter_anchor(order: int, title: str) -> str:
    """Texte d'ancrage d'un chapitre — sert à LA FOIS au titre et au lien Précédent/Suivant.

    Obsidian résout `[[#X]]` vers un titre dont le texte vaut `X` : en dérivant le
    titre rendu et le lien de cette même chaîne, on garantit l'absence de lien
    interne cassé. Format : `Ch. 3 — Se positionner`.
    """
    return f"Ch. {order} — {title}".strip()

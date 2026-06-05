#!/usr/bin/env python3
"""Parsing de frontmatter YAML d'un document Markdown (NFD/NFC-tolérant).

Promu depuis `wiki-ingest/scripts/article_writer.py` (Phase 2) : à partir de la
Phase 3, trois consommateurs en ont besoin (`wiki-ingest`, `wiki-reading-grid`,
`wiki-index`). On garde la même sémantique tolérante : pas de dépendance `yaml`
runtime, frontmatter absent → `({}, texte)`.

Le parseur sépare l'en-tête `--- … ---` du corps et renvoie un `dict` où les clés
listées (`tags`, `sources` par défaut) sont décodées en `list[str]` (flow-list YAML
`[a, "b c"]`), les autres en chaînes débarrassées des guillemets.
"""

from __future__ import annotations

#: Clés dont la valeur est une flow-list YAML `[a, b]` (le reste = scalaire).
LIST_KEYS_DEFAULT = ("tags", "sources")


def parse_list(raw: str) -> list[str]:
    """Parse une flow-list `[a, "b c"]` → `["a", "b c"]` (tolérant)."""
    raw = raw.strip()
    if raw.startswith("[") and raw.endswith("]"):
        raw = raw[1:-1]
    out: list[str] = []
    for part in raw.split(","):
        item = part.strip().strip('"').strip("'").strip()
        if item:
            out.append(item)
    return out


def parse_frontmatter(
    text: str, *, list_keys: tuple[str, ...] = LIST_KEYS_DEFAULT
) -> tuple[dict[str, object], str]:
    """Sépare frontmatter et corps d'un document Markdown.

    Renvoie `(front, body)` où `front` porte les scalaires (chaînes) et les
    `list_keys` (listes). Tolérant : pas de frontmatter → `({}, text)`. Le corps
    est renvoyé débarrassé de l'éventuelle ligne vide qui suit le `---` fermant.
    """
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        return {}, text
    front: dict[str, object] = {}
    body_start = len(lines)
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            body_start = i + 1
            break
        line = lines[i].rstrip("\n")
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip()
        value = value.strip()
        if key in list_keys:
            front[key] = parse_list(value)
        else:
            front[key] = value.strip('"').strip("'")
    body = "".join(lines[body_start:])
    return front, body.lstrip("\n")

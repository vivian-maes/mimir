"""Rend importables les scripts de `wiki-extract/` ET du socle partagé.

Deux dossiers sur `sys.path` (imports plats, cohérent avec le socle Phase 0) :
- `skills/wiki-extract/scripts/`  -> wiki_extract, extractors (package)
- `skills/_shared-references/scripts/` -> config_loader, guard, slug, iohelpers, status_table, sync
"""

import sys
from pathlib import Path

_HERE = Path(__file__).resolve()
_WIKI_EXTRACT_SCRIPTS = _HERE.parent.parent / "scripts"
_SHARED_SCRIPTS = _HERE.parents[2] / "_shared-references" / "scripts"

for p in (_WIKI_EXTRACT_SCRIPTS, _SHARED_SCRIPTS):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

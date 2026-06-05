"""Rend importables les scripts de `wiki-ingest/` ET du socle partagé.

Deux dossiers sur `sys.path` (imports plats, cohérent avec le socle Phase 0) :
- `skills/wiki-ingest/scripts/`  -> wiki_ingest, article_writer, inventory
- `skills/_shared-references/scripts/` -> config_loader, guard, slug, iohelpers, status_table, ledger, sync
"""

import sys
from pathlib import Path

_HERE = Path(__file__).resolve()
_WIKI_INGEST_SCRIPTS = _HERE.parent.parent / "scripts"
_SHARED_SCRIPTS = _HERE.parents[2] / "_shared-references" / "scripts"

for p in (_WIKI_INGEST_SCRIPTS, _SHARED_SCRIPTS):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

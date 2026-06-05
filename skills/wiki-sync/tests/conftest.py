"""Rend importables les scripts de `wiki-sync/` ET du socle partagé.

- `skills/wiki-sync/scripts/`          -> wiki_sync
- `skills/_shared-references/scripts/` -> config_loader, sync (package), guard, …
"""

import sys
from pathlib import Path

_HERE = Path(__file__).resolve()
_SKILL_SCRIPTS = _HERE.parent.parent / "scripts"
_SHARED_SCRIPTS = _HERE.parents[2] / "_shared-references" / "scripts"

for p in (_SKILL_SCRIPTS, _SHARED_SCRIPTS):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

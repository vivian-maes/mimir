---
name: wiki-sync
description: >
  Synchronise le vault Mimir avec son stockage distant, en pré et post-compilation.
  Backend pluggable (rclone ou git) sélectionné par wiki.config.json. Déclencher sur
  « synchronise le vault », « pull/push le second cerveau », « lock/validate la synchro ».
  Périmètre strictement borné à work_root (confinement) ; verrou hors zone synchronisée.
license: Proprietary
metadata:
  version: "0.3.4"
  author: Vivian MAES
  tags: [knowledge-base, obsidian, sync, rclone, git]
  hermes:
    profile: mimir
    category: knowledge-management
    related_skills: [wiki-extract, wiki-ingest, wiki-reading-grid, wiki-index]
    config:
      - key: mimir.config_path
        description: "Chemin du wiki.config.json (sinon auto-découverte : MIMIR_CONFIG → ~/.config/mimir → ./)"
        default: "~/.config/mimir/wiki.config.json"
        prompt: Emplacement du wiki.config.json
      - key: mimir.work_root
        description: Racine unique du second cerveau (vault complet ou sous-répertoire dédié)
        default: ""
        prompt: Racine de travail (work_root)
      - key: mimir.sync.backend
        description: Backend de synchronisation du vault (rclone | git)
        default: rclone
        prompt: Backend de synchro
---

# wiki-sync

> Synchronisation pluggable du vault (Phase 4). Interface `lock` / `pull` / `push` /
> `validate`, deux backends (`rclone`, `git`), bornée à `work_root`.

## Quand l'utiliser

- **Avant** toute lecture de `raw/` (pré-sync `pull`) et **après** toute écriture wiki
  (post-sync `push`) — déjà câblé dans `wiki-extract` et `wiki-ingest`/`wiki-reading-grid`/`wiki-index`.
- **À la demande** : « synchronise le vault » → `sync` (cycle `pull → push → validate`).

## Architecture

Le moteur vit dans le socle partagé `_shared-references/scripts/sync/` (package importé
par tous les skills via `import sync`). Ce skill n'expose qu'un **CLI mince** par-dessus :

```
wiki_sync.py [--config <wiki.config.json>] {lock|pull|push|validate|sync} [--dry-run]
```

> `--config` est **optionnel** : sans lui, le config est auto-découvert dans l'ordre
> `$MIMIR_CONFIG` → `dossier du profil` → `~/.config/mimir/wiki.config.json` → `./wiki.config.json`.

Backend choisi par `sync.backend` du config (`rclone` | `git`). **Sans clé `sync`**, le
backend `noop` est utilisé (travail local, « contenu d'abord, synchro ensuite »).

| Op           | Sémantique                                             | Échec                                      |
| ------------ | ------------------------------------------------------ | ------------------------------------------ |
| `lock`       | Verrou mutex inter-process, **hors zone synchronisée** | déjà tenu ⇒ skip propre (code 0)           |
| `pull`       | Récupère l'état distant → local **avant** compilation  | non-zéro ⇒ stop, ne pas compiler           |
| `push`       | Publie local → distant **après** compilation           | non-zéro ⇒ signalé, travail local conservé |
| `validate`   | Vérifie la cohérence local↔distant après push          | écart ⇒ remédiation / échec contrôlé       |

> **Périmètre = `work_root`** (confinement, §2). En **mode B** (répertoire dédié), seul
> ce répertoire est synchronisé. Le **verrou vit hors** `work_root` (`~/.cache/mimir/`),
> sinon il se synchroniserait et bloquerait les autres machines (§12.9).

## Backends

- **rclone** (kDrive WebDAV) : `bisync --size-only` (+ `--conflict-loser pathname`,
  `--max-delete 25`, `--resilient --recover`, `--filter-from filters.txt`) ; fallback
  `sync` unidirectionnel au premier run / état bisync perdu (jamais `--resync` auto) ;
  `validate` anti-listing-stale (comptage local vs `rclone lsf`). Détails et pièges :
  [`references/RCLONE_KDRIVE.md`](references/RCLONE_KDRIVE.md).
- **git** : `pull --rebase` ; `add`/`commit`/`push` scopé (`_inbox/`, `raw/`, `wiki/`,
  `reading-grids/`) ; `validate` = `HEAD` local vs `origin/<branch>`. Détails :
  [`references/GIT_BACKEND.md`](references/GIT_BACKEND.md).

## Configuration (`wiki.config.json`)

```json
{
  "sync": {
    "backend": "rclone",
    "rclone": { "remote": "mimir:Vault/kb", "filters": "filters.txt", "lock_dir": "~/.cache/mimir/wiki-sync.lock" },
    "git":    { "repo_root": "/chemin/vault", "branch": "main", "scope": ["_inbox", "raw", "wiki", "reading-grids"] }
  }
}
```

## Références

- Conventions, confinement, pièges synchro : [`../_shared-references/CONVENTIONS.md`](../_shared-references/CONVENTIONS.md) §1, §7.
- Chargeur de config & garde : [`../_shared-references/scripts/`](../_shared-references/scripts/).
- Moteur de synchro : [`../_shared-references/scripts/sync/`](../_shared-references/scripts/sync/).
- Filtres rclone : [`../../filters.txt`](../../filters.txt).
- Spécification : `SPEC.md` §10.

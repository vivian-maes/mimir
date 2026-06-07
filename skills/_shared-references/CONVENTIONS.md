# Conventions partagées — Mimir

> Socle commun aux 5 skills `wiki-*`. Source de vérité : [`SPEC.md`](../../__projet__/SPEC.md) (v0.6).
> Ce fichier mutualise les conventions pour éviter le gonflement des `SKILL.md`.

---

## 1. Racine de travail & confinement `[SPEC §2]`

Un seul `wiki.config.json` (dans le `work_root`) définit tout. `work_root` est la **racine unique** ;
`RAW`, `WIKI`, `READING_GRIDS`, `LEDGER` en dérivent (résolus par
[`scripts/config_loader.py`](scripts/config_loader.py)).

- **Mode A — vault complet** : `work_root` = racine du vault Obsidian. Détecté par la présence d'un
  dossier `.obsidian/`. `raw/`, `wiki/`, `reading-grids/`, `.wiki/` vivent à la racine du vault.
- **Mode B — répertoire dédié** : `work_root` = un sous-répertoire `[base_repertoire]`. **Tout** Mimir
  vit dans ce répertoire ; le reste du vault n'est jamais touché. (C'est le cas de
  [`wiki.config.example.json`](../../wiki.config.example.json), qui pointe sur `…/02 - second cerveau`.)

La **résolution des chemins est identique** dans les deux modes — seul le périmètre de synchro change (§10).

> **Règle d'or — confinement.** Toute opération (lecture, écriture **et** synchro) est bornée à
> `work_root`. On ne crée/modifie/synchronise jamais rien **hors** de cette racine. Implémentée par
> [`scripts/guard.py`](scripts/guard.py) (`assert_within`, `safe_path`) : tout chemin d'écriture passe
> par cette garde. Normalisation `realpath` + `commonpath` ⇒ les `..` et symlinks d'évasion sont refusés.

Tous les chemins manipulés sont **absolus** (les sessions cron Hermes n'ont pas de `cwd` garanti).

---

## 2. Slugs ASCII kebab-case `[SPEC §12.3]`

- Les **noms de fichiers** sont des slugs **ASCII kebab-case** ; le titre affichable (avec accents)
  vit dans le frontmatter, jamais dans le nom de fichier.
- Helper unique : [`scripts/slug.py`](scripts/slug.py) → `slugify("Baromètre") == "barometre"`.
  (L'ancien `slugify` des `kb-*` gardait les accents — `\w` étant Unicode ; corrigé via décomposition NFKD.)

## 3. NFD / NFC `[SPEC §12.2]`

macOS/APFS stocke les noms de fichiers en **NFD** (accents décomposés), les wikilinks Obsidian sont en
**NFC** (composés). Comparer sans normaliser ⇒ faux « liens morts ». Toujours comparer via
`slug.same_file(a, b)` ; après chaque écriture, vérifier le match exact wikilink ↔ nom de fichier.

## 4. Mermaid `[SPEC §5.3, §12.6]`

Tout schéma est en **Mermaid** (jamais d'ASCII art). Pour citer un wikilink dans un nœud :
`A["[[navigation/relevement]]"]` — **jamais** `[[[…]]]` (erreur de parsing).

---

## 5. Immutabilité de `raw/` `[SPEC §4.2, §12.1]`

- Une source déposée n'est **jamais écrasée ni modifiée** ; re-dépôt ⇒ suffixer (`-2`, `-3`).
- Seule mutation tolérée dans `raw/` : la colonne **statut/SHA** de `_status.md`.
- L'ingestion **web** passe par un *staging* hors `raw/` (réversible) **avant** commit définitif.
- Les **binaires** (PDF/EPUB) transitent par `_inbox/` (dropzone **synchronisée**, à la racine de
  `work_root`) : `wiki-extract` les y consomme sous **verrou** `wiki-sync`, écrit dans `raw/<type>/`,
  puis **déplace** le binaire hors `_inbox/`. Le move `_inbox/`→`raw/` n'est pas une mutation de `raw/`.

## 6. Frontmatters & formats

Les gabarits (article notion, grille de lecture, `.toc.json`, `_status.md`, clipping web) sont dans
[`FRONTMATTERS.md`](FRONTMATTERS.md). Format d'article = **Karpathy** (H1 / résumé / Définition /
Points clés / Relations / Sources) ; **jamais** de dump brut d'une source.

## 7. Synchro (rappel pour Phase 4) `[SPEC §10]`

Conventions à implémenter en Phase 4 (non codées en P0) :

- **Verrou hors zone synchronisée** (`~/.cache/mimir/…`) — sinon il se synchronise et bloque les autres
  machines (vigilance §12.9).
- **rclone** : `--size-only` **obligatoire** (WebDAV/kDrive sans modtime fiable ; `--checksum` est
  catastrophique) ; `bisync` + fallback `sync` ; `validate` anti-listing-stale. Filtres : voir
  [`filters.txt`](../../filters.txt).
- **git** : lockfile ; `pull --rebase` ; commit/push scopé (`raw/`, `wiki/`, `reading-grids/`).

---

## 8. Les 14 pièges `[SPEC §12]`

1. **Immutabilité raw** : jamais d'écrasement ; seul statut/SHA bouge ; suffixage `-2` ; staging web réversible.
2. **NFD/NFC** : vérifier le match exact wikilink ↔ nom de fichier après chaque écriture.
3. **Slugs ASCII** kebab-case dans les noms ; titre affichable dans le frontmatter.
4. **Validation post-sync obligatoire** : bisync/sync renvoient 0 même sur listing kDrive *stale*.
5. **OCR auto** : tenter la couche texte, sinon basculer OCR (`ocrmypdf`/`tesseract`) ; tracer `ocr:true` ;
   vérifier avant compilation — ne jamais inventer le contenu d'un scan.
6. **Mermaid + wikilinks** : `["[[notion]]"]`, jamais `[[[…]]]`.
7. **Sessions cron sans cwd** : chemins absolus ancrés sur `work_root`, commandes inline.
8. **Confinement à `work_root`** : aucun effet de bord hors de cette racine.
9. **Verrou hors zone synchronisée**.
10. **Frontmatter non-standard** → déplacer sous `metadata` ; valider (`validate_skills.py` / `skills-ref`).
11. **`skill_manage(create)` ignore `external_dirs`** (#22236) → créer via `write_file`.
12. **Ledger atomique** (tmp + rename), **hors sync** ; si corrompu, repartir de `{}` (idempotent).
13. **Grille = liens ordonnés**, pas de duplication ; liens non résolus = travail restant visible.
14. **Double `_assets`** : un par sujet (wiki) **et** un par type (raw) — ne pas centraliser ; préfixer si collision.

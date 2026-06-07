# Changelog

Toutes les évolutions notables de Mimir sont consignées ici.

Format inspiré de [Keep a Changelog](https://keepachangelog.com/fr/1.1.0/) ;
versionnage [SemVer](https://semver.org/lang/fr/). Les frontmatters des skills
suivent la même version (bump synchronisé).

## [Unreleased]

## [0.3.5] - 2026-06-07

### Fixed

- **Skills de base manquantes après `hermes profile install` (doc corrigée).**
  `hermes profile install` ne copie que les *distribution-owned files* (les 5
  wiki-*) — il **ne seede PAS** les bundled skills de base (seuls `hermes profile
  create` les seede, et `hermes update` les synchronise dans tous les profils).
  Correction des affirmations erronées d'« héritage automatique » des skills
  (`config.yaml`, `SPEC.md` §11, `RUNBOOK_VALIDATION_HERMES.md` §5, `SOUL.md`) et
  ajout de l'étape post-install **`hermes update`** (« syncs new bundled skills to
  all profiles » → `mimir (+N new)`). Le modèle LLM, lui, reste bien hérité.

## [0.3.4] - 2026-06-07

### Changed

- **`distribution.yaml` conformé au schéma officiel Hermes.** Retrait de la clé
  `files:` (inexistante — Hermes copie tout le repo dans le profil) ; ajout de
  `license` et `distribution_owned` (`SOUL.md`, `config.yaml`, `skills/`).
  (Corrige la v0.3.3 qui embarquait encore le `files:` non conforme.)
- **`config.yaml` minimal (héritage).** Aucun bloc `model:` : le profil **hérite**
  du modèle du profil par défaut (sinon `mimir setup`). Retrait des blocs
  spéculatifs `delegation:`/`skills.hub:` (non confirmés par la doc officielle) et
  du `MIMIR_CONFIG` placeholder (inutile : `wiki.config.json` est auto-découvert
  dans le dossier du profil). SOUL/SPEC/runbook clarifient que « N compétences » ne
  compte que les skills custom, et documentent les étapes post-install (modèle,
  gateway).

### Removed

- **Poids mort interne supprimé** (jamais publié) : dossier `_old-kb-mimir-skills/`
  (anciens skills `kb-*`, remplacés par les `wiki-*` ; historique conservé par git)
  et les 3 notes de recherche Hermes (`hermes-sous-agents-vs-skills.md`,
  `hermes-remontee-modifications-auto-git.md`, `guide-devops-hermes-wiki-gitlab.md`)
  — potentiellement inexactes ; **source de vérité = doc officielle
  NousResearch/hermes-agent**. Conservés : les 3 `RUNBOOK_*.md` + le diagramme.

## [0.3.3] - 2026-06-07

### Added

- **Auto-découverte de la config dans le dossier du profil Hermes.** En plus de
  `$MIMIR_CONFIG`, `~/.config/mimir/` et `./`, le resolver cherche désormais à la
  **racine du profil/repo** : `~/.hermes/profiles/<profil>/wiki.config.json` (en
  prod) ou la racine du repo (en dev), déduite de l'emplacement de
  `config_loader.py` (`_self_root()`, `parents[3]`). Ordre :
  `$MIMIR_CONFIG` → **profil** → XDG → `./`. La config du profil prime sur la
  globale. UX : déposer son `wiki.config.json` dans le dossier du profil installé
  (p. ex. copier `wiki.config.example.json` → `wiki.config.json`) suffit — plus
  besoin de `MIMIR_CONFIG`.

### Changed

- **Profil Hermes renommé `wiki-curator` → `mimir`.** Le `distribution.yaml`
  porte `name: mimir` ; l'install crée `~/.hermes/profiles/mimir` et l'usage
  devient `hermes -p mimir chat`. Aligné sur l'identité produit (et la mythologie :
  Mímir = le sage gardien du savoir). Indices `metadata.hermes.profile` des 5
  skills + `SOUL.md`/`config.yaml`/SPEC/ROADMAP mis à jour.
  ⚠️ Après réinstallation, supprimer l'ancien profil : `rm -rf ~/.hermes/profiles/wiki-curator`.
- `.gitignore` ignore `/wiki.config.json` (la racine du repo est un emplacement de
  découverte en dev ; la config perso ne doit jamais être committée).

## [0.3.2] - 2026-06-07

### Fixed

- **`distribution.yaml` au vrai format Hermes.** Le manifest utilise désormais le
  schéma **plat** documenté (`name`/`version`/`description`/`author`/`files`) au
  lieu de la structure `apiVersion/kind/metadata/…` (qui causait
  `Error: distribution.yaml missing 'name'` à `hermes profile install`).
- **`SOUL.md` + `config.yaml` remontés à la racine du repo.** `profile install`
  copie les `files:` dans `~/.hermes/profiles/wiki-curator/` ; un profil attend
  `SOUL.md`/`config.yaml` à la racine de son dossier, donc ils doivent être listés
  à plat. Dossier `profiles/` supprimé. Allow-list de publication ajustée
  (`SOUL.md`, `config.yaml` ajoutés ; `profiles/` retiré).

## [0.3.1] - 2026-06-07

### Fixed

- **`hermes profile install` réparé.** Le manifest `distribution.yaml` est déplacé
  de `profiles/wiki-curator/` vers la **racine du repo** (requis : `profile install`
  ne supporte pas la syntaxe `#sous-dossier` et cherche le manifest à la racine).
  Chemins `soul`/`config` → `profiles/wiki-curator/`, `assets` → racine. Ajouté à
  l'allow-list de publication. Commande : `hermes profile install https://github.com/vivian-maes/mimir.git`.

### Changed

- **Réorganisation : gestion de projet sous `__projet__/`.** `ROADMAP.md`,
  `BACKLOG.md`, `SPEC.md` et les dossiers `_analyse_DevOps/`, `_old-kb-mimir-skills/`
  sont regroupés sous `__projet__/` (jamais publié — ajouté au garde-fou anti-fuite).
  Racine allégée ; artefacts publiés (README, CHANGELOG, VERSION, LICENSE, configs,
  `distribution.yaml`, `skills.sh.json`) conservés à la racine. Liens internes mis à jour.

## [0.3.0] - 2026-06-07

> Configuration « zéro friction » : on configure **une fois**, on appelle les
> skills **sans** `--config`. Exposition au Skills Hub d'Hermes (regroupement +
> bouton config) et install groupée par le profil mise en avant.

### Added

- **Auto-découverte du `wiki.config.json`.** `--config` devient **optionnel** sur
  les 5 skills. Quand il est omis, le config est résolu dans l'ordre
  `$MIMIR_CONFIG` → `~/.config/mimir/wiki.config.json` (XDG) → `./wiki.config.json`
  (`config_loader.resolve_config_path` / `load_resolved_config`). Message d'erreur
  actionnable si rien n'est trouvé. Plus besoin de répéter le chemin à chaque appel.
- **Skills Hub.** Frontmatters enrichis (`metadata.hermes.category`,
  `related_skills`, `config`) → les 5 skills apparaissent comme un **ensemble**
  avec un **bouton config**. Nouveau `skills.sh.json` (catégorie « Mimir — Second
  cerveau »), ajouté à l'allow-list de publication.

### Changed

- **Profil = voie d'install groupée recommandée.** `hermes profile install https://github.com/vivian-maes/mimir.git`
  (les 5 skills + config + cron d'un coup) mis en avant dans les runbooks. Le
  manifest **`distribution.yaml` est à la racine** du repo (requis par
  `profile install` ; pas de syntaxe `#sous-dossier`) ; `SOUL.md` + `config.yaml`
  restent sous `profiles/wiki-curator/`. Le `config.yaml` exporte `MIMIR_CONFIG`
  (appels sans `--config`) ; le cron garde `--config` explicite (sessions sans `cwd`).
- **CI tag-only.** Plus aucun pipeline hors tag (`workflow.rules` + suppression
  du job de validation au push) : la validation (frontmatters + 159 tests) et la
  publication ne tournent qu'au tag.
- **Publication GitHub incrémentale.** `scripts/publish_github.sh` n'écrase plus
  l'historique (`--force`) : il hérite de `origin/main` et ajoute **un seul
  commit par version** ne contenant **que le diff** (message `Release vX.Y.Z` +
  section CHANGELOG). Garde-fou anti-fuite conservé : les fichiers internes
  (`_analyse_DevOps/`, `_old-kb-mimir-skills/`, `ROADMAP.md`, `SPEC.md`,
  `.gitlab-ci.yml`) n'entrent jamais — ni en fichiers, ni en historique.

## [0.2.0] - 2026-06-05

> Première release packagée : les phases 0→4 sont livrées (les 5 skills `wiki-*`
> opérationnels). `VERSION` aligné sur les frontmatters des skills (tous à `0.2.0`).

### Added

- **Phase 5 — Packaging & déploiement Hermes** (amorce). Publication GitHub
  **filtrée par allow-list** (`scripts/publish_github.sh`) : seuls `skills/`,
  `README.md`, `VERSION`, `CHANGELOG.md`, `LICENSE`, `wiki.config.example.json`,
  `filters.txt`, `assets/` et `profiles/` partent vers le miroir GitHub ; les
  fichiers internes (`_analyse_DevOps/`, `_old-kb-mimir-skills/`, `ROADMAP.md`,
  `SPEC.md`, `.gitlab-ci.yml`) **ne sont jamais transmis** (la push-mirror native
  GitLab est écartée car elle ne sait pas filtrer). Publication **incrémentale**
  (un commit par version, diff seul ; pas de réécriture d'historique).
  `.gitlab-ci.yml` **tag-only** : `validate` (frontmatters + 159 tests) puis
  `publish:github`, sur tag uniquement. Profil opt-in **`wiki-curator`** (couche 2)
  : `profiles/wiki-curator/` (`distribution.yaml` + `SOUL.md` + `config.yaml` +
  cron de synchro) — jamais requis, les skills restent portables hors profil.

- **Phase 4 — Synchronisation pluggable** (`wiki-sync` v0.2.0). Moteur de synchro **pluggable**
  promu dans le socle partagé `_shared-references/scripts/sync/` : ABC `SyncBackend`
  (`lock`/`pull`/`push`/`validate`) + factory `get_backend(cfg, runner)` sélectionnant
  `rclone | git | noop` selon `sync.backend`, avec `runner=subprocess.run` **injectable**
  (tests 100 % hermétiques, aucun binaire requis). Façade `sync.pull/push/validate/lock(cfg)`
  importée par les 4 orchestrateurs. **Backend rclone** (`sync/rclone.py`) : `bisync --size-only`
  (+ `--conflict-loser pathname`, `--max-delete 25`, `--resilient --recover`, `--filter-from`),
  fallback `sync` unidirectionnel au premier run / état bisync perdu (jamais `--resync` auto),
  `validate` **anti-listing-stale** (comptage local vs `rclone lsf`). **Backend git**
  (`sync/git.py`) : `pull --rebase`, `add`/`commit`/`push` **scopé** (`_inbox/`, `raw/`, `wiki/`,
  `reading-grids/`), `validate` = `HEAD` local vs `origin/<branch>`. CLI `wiki_sync.py`
  (`lock|pull|push|validate|sync`, `--dry-run`) pour le trigger « synchronise le vault ».
  `SKILL.md` opérationnel + `references/{RCLONE_KDRIVE,GIT_BACKEND}.md` (savoir kDrive porté
  depuis l'ancien `kb-sync`). 32 tests pytest (factory/noop/lock + git e2e local + rclone mocké
  + CLI). DoD : cycle `pull → push → validate` vert sur git (réel) et rclone (mocké), verrou
  hors zone synchronisée empêchant la concurrence.

- **Phase 3 — Grille de lecture & index** (`wiki-reading-grid` v0.2.0, `wiki-index` v0.2.0).
  Deux skills **100 % déterministes** (aucun travail sémantique d'agent). `wiki-reading-grid` :
  `wiki_reading_grid.py` (`generate` / `generate-all`) + `grid_builder.py` qui croise
  `toc.json` (chapitres ordonnés) × ledger (articles d'un ouvrage) × ancres `#chK` des `sources`
  pour produire `reading-grids/<slug>.md` — liens **ordonnés par chapitre** + **Précédent/Suivant**
  (titre et lien dérivés d'une même fonction `chapter_anchor` ⇒ aucun lien interne cassé), MAJ de
  la colonne « Grille » de `_status.md`, idempotent (`created` préservé), slug dérivé du titre
  (désambiguïsation `-2`), web sans chapitrage ignoré. `wiki-index` : `wiki_index.py`
  (`regenerate` / `audit`) + `index_builder.py` (INDEX principal des sujets avec **description
  éditoriale préservée**, INDEX par sujet avec résumés issus du callout `>` + grilles rattachées,
  **forme majoritaire** des wikilinks) + `link_audit.py` (**audit lecture seule, 3 passes** :
  liens cassés / fichiers fantômes / index→vide, normalisation `os.path.normpath`, code retour
  0 ssi 0 anomalie). Nouveaux helpers partagés : `frontmatter.py` (parsing promu depuis
  `article_writer.py`), `article_index.py` (lecture d'article + résumé), `wikilinks.py`
  (extraction / forme majoritaire / résolution / ancrage chapitre). 35 tests pytest (helpers +
  2 skills), DoD vérifié (grille suit le chapitrage sans lien cassé ; audit à zéro sur vault sain).

- **Phase 2 — Compilation → wiki** (`wiki-ingest` v0.2.0). Modèle **agent-piloté + helpers** :
  l'agent décompose et reformule (méthode Karpathy), le Python ne fait que le déterministe.
  CLI fin `wiki_ingest.py` à trois sous-commandes (`inventory` → worklist des sources à compiler
  via diff ledger ; `write-article` → écrit/écrase un article notion ; `finalize` → MAJ `_status.md`
  + ledger). Nouveau **ledger** partagé `.wiki/ingest-ledger.json` (`ledger.py` : atomique tmp+rename,
  corrompu→`{}`, hors sync) pour l'**idempotence**. `article_writer.py` : frontmatter Karpathy,
  **antidoublon = remplacer le corps** + fusion frontmatter (`created` conservé, `sources`/`tags`
  en union), `_assets` par sujet, validation NFD/NFC. `inventory.py` (SHA + exclusions des
  sidecars de service). `sync_stub.py` (interface `pull`/`push`/`validate` du futur `wiki-sync`,
  no-op ; `--skip-sync`). 22 tests pytest.

- **Phase 1 — Extraction → raw** (`wiki-extract` v0.2.0). Orchestrateur CLI
  `wiki_extract.py` + dropzone **`_inbox/`** (synchronisée, verrouillée) ; 3 extracteurs
  pluggables (`pdf`, `epub`, `web`) sur contrat commun `extract() → ExtractResult`, chacun
  avec dégradation gracieuse (lib riche → fallback CLI/stdlib) et **jamais d'invention** de
  contenu (OCR auto PDF, sinon `ExtractorUnavailable`). Helpers partagés `iohelpers.py`
  (écriture atomique confinée, suffixage `-2`, SHA) et `status_table.py` (`_status.md`).
  Immutabilité de `raw/`, déduplication par SHA de contenu. Clé `inbox` ajoutée au layout de
  config. `wiki-extract/requirements.txt`. 57 tests pytest.

- **Phase 0 — Fondations.** Arborescence mono-repo `skills/` (5 skills `wiki-*` +
  `_shared-references/`).
- Socle Python partagé : chargeur `wiki.config.json` (`config_loader.py`), garde de
  confinement à `work_root` (`guard.py`), slugs ASCII + NFD/NFC (`slug.py`),
  validateur de frontmatter agentskills.io (`validate_skills.py`).
- Schéma JSON `wiki.config.schema.json` + exemple `wiki.config.example.json`.
- Conventions partagées : `CONVENTIONS.md`, `FRONTMATTERS.md`, `TOOLING.md`.
- Squelettes des 5 `SKILL.md` (frontmatter conforme, corps non fonctionnel).
- Tests pytest (résolution config modes A/B, confinement).
- Amorces packaging : `VERSION`, `CHANGELOG.md`, `.gitlab-ci.yml` (validation
  déclenchée uniquement sur tag), `filters.txt` (template rclone).

### Changed

- Le verrou `wiki-extract/inbox_lock.py` (Phase 1) est **promu** dans le socle partagé
  (`sync/locking.py`) et réutilisé par tous les backends et orchestrateurs ; l'ancien nom de
  classe `InboxLock` reste disponible en alias. `wiki-extract` câble désormais `lock → pull →
  extract → push` (flag `--skip-sync`). Défaut de scope git du schéma : `_inbox` inclus (SPEC §6).

### Removed

- Les trois copies dupliquées de `sync_stub.py` (`wiki-ingest`, `wiki-reading-grid`,
  `wiki-index`) et `wiki-extract/inbox_lock.py` — remplacées par le moteur partagé `sync/`.

[Unreleased]: https://github.com/vivian-maes/mimir/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/vivian-maes/mimir/releases/tag/v0.2.0

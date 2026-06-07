# Backend rclone — kDrive WebDAV (pièges & procédure)

> Savoir battle-tested (repris de l'ancien `kb-sync`). Le WebDAV kDrive est un remote
> **sans modtime ni hash fiable** : la synchro doit s'y adapter au mot près.

## Règles d'or

- **`--size-only` est obligatoire.** `--checksum` force le téléchargement des fichiers
  pour comparer (catastrophique en bande passante) ; `--compare modtime` provoque des
  listings incohérents et des **suppressions ping-pong** (des fichiers disparaissent
  localement parce que le remote les a « perdus » entre deux runs). `--size-only` est la
  seule comparaison viable.
- **Verrou hors zone synchronisée** (`~/.cache/mimir/wiki-sync.lock`) : sinon il se
  synchronise et le verrou d'une machine bloque les autres.
- **`--resync` non automatique par défaut** : sans état antérieur, le backend bascule sur un
  bootstrap unidirectionnel et signale qu'un `--resync` manuel est requis. Pour s'amorcer
  seul (machine distante, agent piloté par le JSON), poser `sync.rclone.auto_resync: true`
  (cf. « Amorçage automatique » plus bas).

## Commande bisync (pull/push)

```
rclone bisync <local> <remote> \
  --size-only --conflict-loser pathname --conflict-suffix sync-conflict \
  --max-delete 25 --resilient --recover --copy-links \
  --filter-from filters.txt
```

`--check-access` et `--track-renames` sont **retirés** (incompatibles WebDAV kDrive :
pas de hash commun, pas de modtime fiable).

## Premier run / état bisync perdu

`bisync` exige un `--resync` initial ; sans état antérieur il refuse (« Must run
--resync »). Le backend bascule alors sur un **bootstrap unidirectionnel** :

```
rclone sync <local> <remote> --size-only --copy-links --filter-from filters.txt
```

puis **signale** (warning) qu'un `rclone bisync --resync` manuel doit être lancé pour
établir proprement l'état bisync.

### Amorçage automatique (opt-in)

Avec `sync.rclone.auto_resync: true`, le backend amorce lui-même l'état bisync sur ce cas :
il lance `rclone bisync … --resync` (mêmes flags que la passe normale, **plus** `--resync`).
On ne passe **pas** de `--resync-mode` : `--conflict-loser pathname --conflict-suffix
sync-conflict` reste actif, donc un fichier divergent des deux côtés produit **deux copies**
(union sans perte) au lieu d'un écrasement silencieux. Si le `--resync` échoue, le backend
retombe sur le bootstrap unidirectionnel ci-dessus (filet de sécurité). C'est le réglage
attendu quand l'agent doit « se débrouiller seul depuis le JSON » sans rclone manuel.

### Auth pilotée par le JSON (opt-in)

Avec `sync.rclone.remote_setup`, le backend crée/répare le remote rclone **avant** la synchro,
sans `rclone config` manuel :

```jsonc
"remote_setup": {
  "url": "https://connect.drive.infomaniak.com/<id>/<dossier>",
  "vendor": "other",
  "user": "<login kDrive>",
  "pass_env": "MIMIR_KDRIVE_PASS"   // NOM de la variable d'env, pas le mot de passe
}
```

- Le **mot de passe d'application kDrive n'est jamais dans le JSON** : `pass_env` nomme la
  variable d'environnement qui le porte (à poser dans le `.env` du profil Hermes, exclu des
  fichiers « possédés » par `distribution.yaml`, donc jamais écrasé par `hermes update`).
- Remote absent ⇒ `rclone config create … webdav … --obscure` ; remote présent ⇒ `rclone
  config update … pass … --obscure` → **rafraîchit le secret et répare un 401** au run suivant.
- Si la variable d'env est absente, le backend n'écrit rien et émet un warning (la synchro
  peut alors échouer en 401) — il ne plante pas pour autant.
- **Caveat secret** : le mot de passe transite en clair par `argv` de `rclone config` (bref
  passage dans la table des process). Le backend ne le journalise jamais. Variante « zéro
  écriture » possible hors backend : définir le remote par variables `RCLONE_CONFIG_<NOM>_*`
  plutôt que muter `rclone.conf`.

> **Piège — cohérence du chemin.** L'état bisync est indexé par rclone sur le **chemin
> absolu** des deux côtés. Le backend utilise `cfg.work_root`, que `config_loader` **résout
> via `realpath()`** (symlinks et `..` résolus — ex. sur macOS `/tmp` → `/private/tmp`). Le
> `--resync` manuel doit donc viser **exactement ce chemin résolu**, sinon bisync ne
> retrouve pas l'état (« cannot find prior listings ») et le backend retombe indéfiniment
> sur le bootstrap unidirectionnel. En cas de doute :
> `python config_loader.py wiki.config.json` affiche le `WORK_ROOT` résolu à utiliser.

## Validation anti-listing-stale (le piège majeur)

`bisync` renvoie **0 même quand le listing kDrive est périmé** et qu'aucun fichier n'a
transféré (symptôme : `rclone lsf <remote>/wiki/` répond `directory not found` alors que
le log dit « Bisync successful »). `validate` ne fait donc **pas** confiance au code 0 :

1. compter les fichiers locaux (hors `.git/`, `.obsidian/`, `.wiki/`, `.DS_Store`) ;
2. compter les fichiers distants via `rclone lsf <remote> --recursive --files-only` ;
3. si l'écart dépasse la tolérance (~5, marge pour les exclusions), **re-pousser** via
   `rclone sync` (sans la garde `--max-delete`, donc autorisé à re-pousser ce que le cache
   croit présent) puis revérifier `lsf`. Réessayer avec un court `sleep` si le cache met
   quelques secondes à se réactualiser.

## Filtres (`filters.txt`)

Whitelist inversée (`+ **` final) excluant `.obsidian/`, `.git/`, `.wiki/` (ledger), le
lock, `**/.DS_Store`, `**/*.sync-conflict.*`, et les dossiers de quarantaine/corbeille.
**Après création** d'un dossier `_trash-*/` ou `.quarantine/`, ajouter immédiatement la
ligne d'exclusion **avant** le prochain sync, sinon rclone propage la corbeille vers kDrive.

## Pré-requis (setup machine, une fois)

- Remote `rclone config` (type `webdav`, vendor `other`, URL + mot de passe d'application
  kDrive) — **ou** `sync.rclone.remote_setup` + le secret en variable d'env, et l'agent le
  configure seul (cf. « Auth pilotée par le JSON »).
- `--resync` initial manuel pour établir l'état bisync — **ou** `sync.rclone.auto_resync:
  true` pour l'amorçage automatique.
- Un seul synchroniseur par machine (désactiver l'auto-sync Remotely Save d'Obsidian).

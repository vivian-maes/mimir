# Backend git

> Versionne la zone de travail dans un dépôt git et se synchronise via `origin`.
> Alternative au backend rclone quand le vault est déjà sous git (ou pour un remote Git).

## Configuration

```json
{
  "sync": {
    "backend": "git",
    "git": {
      "repo_root": "/chemin/vers/le/depot",
      "branch": "main",
      "scope": ["_inbox", "raw", "wiki", "reading-grids"]
    }
  }
}
```

- `repo_root` : racine du dépôt git (peut être `work_root` lui-même, ou un parent si le
  vault entier est versionné et que `work_root` est un sous-répertoire — mode B).
- `branch` : branche suivie (défaut `main`).
- `scope` : sous-arbres versionnés. **C'est la frontière de confinement côté git** : seuls
  ces chemins sont `add`/`commit`/`push`. Le ledger `.wiki/` et le verrou en sont exclus de
  fait (hors scope) — ils ne doivent jamais être committés.

## Opérations

| Op         | Commande                                                                 |
| ---------- | ------------------------------------------------------------------------ |
| `pull`     | `git -C <repo> pull --rebase origin <branch>`                            |
| `push`     | `git -C <repo> add -- <scope présents>` → `commit -m "auto(wiki): sync <date>"` → `push origin <branch>` |
| `validate` | `git fetch` puis comparaison `HEAD` local vs `origin/<branch>`           |

- **`push` quand rien n'a changé** : `git commit` répond « nothing to commit » → traité
  comme un **succès** (code 0), un `push` éventuel restant remonte les commits en retard.
- Seuls les chemins du `scope` **qui existent** sont stagés (pas d'erreur de pathspec).

## Pré-requis

- Dépôt git initialisé avec un remote `origin` accessible et une branche `<branch>` suivie.
- `user.name` / `user.email` configurés (nécessaires aux commits automatiques).
- En contexte Hermes : `external_dirs` + script d'auto-commit (cf. `_analyse_DevOps/`).
  ⚠️ `skill_manage(create)` ignore `external_dirs` (#22236) → créer les fichiers via `write_file`.

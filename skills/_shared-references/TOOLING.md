# Outillage & environnement — Mimir

> Dépendances système des skills `wiki-*` et état constaté sur la machine de dev.
> Mis à jour le 2026-06-04 (Phase 1).

---

## Dépendances par phase

| Outil               | Rôle                                                       | Phase | Install (macOS)                  |
| ------------------- | ---------------------------------------------------------- | ----- | -------------------------------- |
| **Python ≥ 3.11**   | socle (config, confinement, slugs, audit), extracteurs     | P0+   | `brew install python@3.12`       |
| **git ≥ 2.20**      | versionning skills, backend sync git, auto-commit          | P0/P4 | `brew install git`               |
| **rclone**          | backend sync rclone (kDrive WebDAV)                        | P4    | `brew install rclone`            |
| **PyMuPDF (`fitz`)**| extraction PDF (couche texte + TOC natif + images)         | P1    | `pip install pymupdf`            |
| **poppler** (`pdftotext`/`pdfinfo`/`pdfimages`/`pdftoppm`) | fallback texte/pages/images PDF + rastérisation OCR | P1    | `brew install poppler`           |
| **`ocrmypdf`**      | OCR auto des PDF scannés (préféré)                         | P1    | `brew install ocrmypdf`          |
| **`tesseract`**     | moteur OCR (langue configurable) ; fallback `pdftoppm`+`tesseract` | P1 | `brew install tesseract`     |
| **`ebooklib`**      | extraction EPUB (spine/manifest) — fallback : `zipfile` stdlib | P1 | `pip install ebooklib`          |
| **`trafilatura`**   | nettoyage web → markdown — fallback : `bs4`+`markdownify`, puis stdlib | P1 | `pip install trafilatura`  |
| **`beautifulsoup4` / `markdownify`** | extraction/conversion HTML (EPUB & web)   | P1    | `pip install beautifulsoup4 markdownify` |
| **`requests`**      | fetch HTTP du clipping web — fallback : `urllib` stdlib    | P1    | `pip install requests`           |

> **Dégradation gracieuse** : chaque extracteur tente la lib riche puis dégrade vers un fallback
> CLI/stdlib. La skill se charge même si une lib manque (portabilité Hermes). Tout est listé dans
> [`../../wiki-extract/requirements.txt`](../../wiki-extract/requirements.txt) (install groupé conseillé).

Dépendances Python optionnelles du socle (fallback si absentes) :
`jsonschema` (validation de config), `PyYAML` (parsing frontmatter), `pytest` (tests).
`pip install jsonschema pyyaml pytest`

---

## État constaté (machine de dev, 2026-06-04 — après install Phase 1)

| Outil                                   | Statut     |
| --------------------------------------- | ---------- |
| Python 3.12.7                           | ✅ présent  |
| git, rclone                             | ✅ présents |
| poppler (`pdftotext`/`pdfinfo`/`pdfimages`/`pdftoppm`) | ✅ présents |
| tesseract 5.5.2 (langues : `eng`, `osd`) | ✅ présent — **langue `fra` non installée** (`brew install tesseract-lang` pour l'OCR français) |
| ocrmypdf 17.5.0                         | ✅ présent  |
| PyMuPDF (fitz) 1.27                      | ✅ présent  |
| ebooklib / beautifulsoup4 / markdownify / trafilatura / requests | ✅ présents |

> **Note OCR (env. de dev)** : le tmp du harness (`/tmp/claude-501`, perms `700` + attribut étendu)
> empêche le sous-process leptonica/tesseract d'ouvrir ses fichiers. L'OCR fonctionne en routant
> `TMPDIR` (et le PDF d'entrée) hors de ce dossier — sans incidence en prod, où `/tmp` est lisible.
> Le test OCR applique ce contournement.

---

## Validateur de frontmatter (`skills-ref`)

Le DoD Phase 0 cite `skills-ref validate ./skills/*` comme validateur **canonique**. Il n'est pas
installé sur la machine. En attendant, [`scripts/validate_skills.py`](scripts/validate_skills.py)
applique le même contrat (SPEC §11) pour la boucle de dev et le CI.

Obtention de `skills-ref` (à confirmer selon la distribution agentskills.io) :

```sh
# piste npm
npx @agentskills/skills-ref validate ./skills/wiki-*
# ou pipx, selon le packaging publié
pipx run skills-ref validate ./skills/wiki-*
```

Quand `skills-ref` est disponible, l'utiliser comme référence ; `validate_skills.py` reste le
garde-fou hors-ligne (et la base du job CI, déclenché uniquement sur tag).

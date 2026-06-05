---
name: wiki-ingest
description: >
  Compile la base de connaissance (méthode Karpathy) : lit raw/ et produit des articles
  wiki par notion (un article = une notion, jamais un dump brut). Antidoublon, ledger SHA
  idempotent, mise à jour des statuts. Déclencher sur « compile la KB », « ingère les
  sources », « décompose ce PDF en articles ». Borné à work_root.
license: Proprietary
metadata:
  version: "0.2.0"
  author: Vivian MAES
  tags: [knowledge-base, obsidian, karpathy, ingestion]
  hermes:
    profile: wiki-curator
---

# wiki-ingest

## Quand l'utiliser

Pour transformer la **matière brute** (`raw/`) en **savoir construit par notion** (`wiki/`).
Trigger : « compile la KB », « ingère les sources », « décompose ce PDF en articles ».

## Principe

La décomposition en notions et la reformulation Karpathy sont **ton travail** (sémantique) :
tu lis le contenu, tu le **comprends** et tu le **reformules** notion par notion — **jamais**
de copier-coller brut (SPEC §0, §5). Les scripts ne font que les opérations **déterministes**
(inventaire SHA, écriture fiable, antidoublon, statuts, ledger) que tu enchaînes :

```sh
python scripts/wiki_ingest.py --config <wiki.config.json> <inventory|write-article|finalize> …
```

## Procédure

1. **Pré-sync** — implicite (stub en P2). Ajoute `--skip-sync` dans une chaîne pour ne pas
   synchroniser plusieurs fois.
2. **Inventaire** — `inventory [SOURCE]` renvoie un JSON : `worklist` (fichiers de contenu à
   compiler = absents du ledger ou SHA changé) + `existing_notions` (par sujet, pour l'antidoublon).
   ```sh
   python scripts/wiki_ingest.py --config CFG inventory --skip-sync
   ```
3. **Lecture** — pour chaque source de la worklist, lis le **`.txt`** (contenu, économe en tokens)
   et le **`.toc.json`** (chapitrage) ; web = le `.md`. Jamais le binaire.
4. **Décomposition par notion** — produis **N notions atomiques**. Pour chacune, détermine le
   **sujet** et rédige le corps au **format Karpathy** :

   ```markdown
   # <Titre de la notion>

   > Résumé d'une ligne (description fonctionnelle).

   ## Définition
   [Reformulation complète, en phrases.]

   ## Points clés
   [Tableaux, listes, schéma Mermaid si pertinent.]

   ## Relations
   - [[<sujet>/<autre-notion>]] : … en quoi elles se relient.

   ## Sources
   - [[raw/pdfs/<nom>.pdf.txt]] — chapitre N, p. X-Y.
   ```

   - **Mermaid** obligatoire pour les schémas (jamais d'ASCII art). Wikilink dans un nœud :
     `A["[[<sujet>/<notion>]]"]` — **jamais** `[[[…]]]`.
   - **Slugs ASCII** : le titre accentué reste dans le frontmatter ; le nom de fichier est
     slugifié automatiquement par le script.

5. **Écriture** — écris le corps dans un fichier temporaire, puis :
   ```sh
   python scripts/wiki_ingest.py --config CFG write-article \
       --subject navigation --notion "Relèvement" --body-file /tmp/relevement.md \
       --source "raw/pdfs/navigation-cotiere.pdf.txt#ch3" --tags navigation,technique \
       --asset /tmp/schema.png
   ```
   Le script gère le frontmatter, les slugs, l'antidoublon, `wiki/<sujet>/_assets/` et la
   validation NFD/NFC ; il renvoie `{wikilink, path, created}`.
   - **Antidoublon = remplacer le corps** : si la notion existe déjà, le script **remplace le
     corps** et **fusionne le frontmatter** (`created` conservé, `sources`/`tags` en union,
     `updated` = jour). Aucun fichier `-2` côté wiki.
   - **Double `_assets`** : les images d'un article vont dans `wiki/<sujet>/_assets/` (un par
     sujet) — distinct de `raw/<type>/_assets/`. Référence-les dans le corps en `_assets/<nom>`.

6. **Grosses vagues** — délègue la production via `delegate_task` (toolset `file`), puis
   **vérifie l'existence réelle** des `.md` produits avant de finaliser (les sous-agents
   réussissent parfois partiellement).

7. **Finalisation** — par source, enregistre les articles produits :
   ```sh
   python scripts/wiki_ingest.py --config CFG finalize \
       --source raw/pdfs/navigation-cotiere.pdf.txt --sha <sha256-du-.txt> \
       --articles navigation/relevement,navigation/triangulation --skip-sync
   ```
   MAJ `_status.md` (statut `compilé`, colonne « Articles wiki ») + ledger atomique. Une relance
   `inventory` ne ressortira plus cette source (idempotence). Utilise `--status "partiellement
   compilé"` s'il reste des notions à compiler.

8. **Post-sync** — implicite (stub en P2), sauf `--skip-sync`.

## Références

- Format Karpathy, antidoublon, double `_assets`, Mermaid : [`../_shared-references/CONVENTIONS.md`](../_shared-references/CONVENTIONS.md) §6, §8, [`FRONTMATTERS.md`](../_shared-references/FRONTMATTERS.md) §1, §4.
- Ledger, slug/NFD-NFC, écriture confinée : [`../_shared-references/scripts/`](../_shared-references/scripts/) (`ledger.py`, `slug.py`, `iohelpers.py`, `guard.py`).
- Spécification : `SPEC.md` §5, §7.

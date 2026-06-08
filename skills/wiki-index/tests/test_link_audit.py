"""Tests de l'audit liens (3 passes, lecture seule, normpath)."""

import index_builder as ib
import link_audit as la


def test_vault_sain_zero_anomalie(vault):
    ib.regenerate(vault, dry_run=False)
    report = la.audit(vault)
    assert report.ok and report.total == 0


def test_passe1_lien_casse(vault):
    ib.regenerate(vault, dry_run=False)
    art = vault.WIKI / "navigation" / "relevement.md"
    art.write_text(art.read_text(encoding="utf-8") + "\n## Relations\n- [[navigation/inexistant]] : lien.\n", encoding="utf-8")
    report = la.audit(vault)
    assert ("wiki/navigation/relevement.md", "navigation/inexistant") in report.broken
    assert report.dangling == []                     # ce n'est pas un fichier d'index


def test_passe2_fichier_fantome(vault):
    ib.regenerate(vault, dry_run=False)
    # nouvel article non régénéré dans l'index -> fantôme
    (vault.WIKI / "navigation" / "nouvelle.md").write_text("# Nouvelle\n\n> x\n", encoding="utf-8")
    report = la.audit(vault)
    assert "wiki/navigation/nouvelle.md" in report.orphans


def test_passe3_index_vers_vide(vault):
    ib.regenerate(vault, dry_run=False)
    idx = vault.WIKI / "navigation" / "_INDEX.md"
    idx.write_text(idx.read_text(encoding="utf-8") + "\n- [[navigation/fantome]]\n", encoding="utf-8")
    report = la.audit(vault)
    assert ("wiki/navigation/_INDEX.md", "navigation/fantome") in report.dangling


def test_normpath_pas_de_faux_positif(vault):
    ib.regenerate(vault, dry_run=False)
    art = vault.WIKI / "navigation" / "relevement.md"
    art.write_text(art.read_text(encoding="utf-8") + "\n## Relations\n- [[navigation/../navigation/maree]] : ok.\n", encoding="utf-8")
    report = la.audit(vault)
    assert report.broken == []                       # `..` normalisé, cible réelle


def test_liens_vers_raw_hors_scope(vault):
    ib.regenerate(vault, dry_run=False)
    art = vault.WIKI / "navigation" / "relevement.md"
    art.write_text(art.read_text(encoding="utf-8") + "\n- [[raw/pdfs/inexistant.pdf.txt]]\n", encoding="utf-8")
    report = la.audit(vault)
    assert report.broken == []                       # raw/ exclu du périmètre d'audit


def test_lien_accentue_suggere_slug_ascii(vault):
    """Un `[[navigation/relèvement]]` accentué (cassé) propose le slug ASCII existant."""
    ib.regenerate(vault, dry_run=False)
    art = vault.WIKI / "navigation" / "maree.md"
    art.write_text(
        art.read_text(encoding="utf-8") + "\n## Relations\n- [[navigation/relèvement]] : lien accentué.\n",
        encoding="utf-8",
    )
    report = la.audit(vault)
    assert ("wiki/navigation/maree.md", "navigation/relèvement") in report.broken
    assert report.suggestions.get("navigation/relèvement") == "navigation/relevement"
    out = la.render_report(report, today="2026-06-08")
    assert "(suggéré : [[navigation/relevement]])" in out


def test_lien_casse_sans_equivalent_pas_de_suggestion(vault):
    """Un lien cassé sans fichier slugifié correspondant n'a pas de suggestion."""
    ib.regenerate(vault, dry_run=False)
    art = vault.WIKI / "navigation" / "maree.md"
    art.write_text(art.read_text(encoding="utf-8") + "\n- [[navigation/inexistant]]\n", encoding="utf-8")
    report = la.audit(vault)
    assert "navigation/inexistant" not in report.suggestions


def test_audit_aucune_ecriture(vault):
    ib.regenerate(vault, dry_run=False)
    snapshot = {p: p.stat().st_mtime_ns for p in vault.work_root.rglob("*") if p.is_file()}
    la.audit(vault)
    after = {p: p.stat().st_mtime_ns for p in vault.work_root.rglob("*") if p.is_file()}
    assert snapshot == after                          # lecture seule : rien n'a bougé

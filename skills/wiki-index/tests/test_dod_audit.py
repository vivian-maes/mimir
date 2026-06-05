"""DoD Phase 3 (index/audit) : audit à ZÉRO sur vault sain + cohérence disque."""

import wiki_index as wi


def test_dod_audit_a_zero(vault):
    """Après régénération, l'audit ressort à zéro (code retour 0)."""
    wi.cmd_regenerate(vault, skip_sync=True)
    report = wi.cmd_audit(vault)
    assert report.ok
    # via la CLI : code retour 0
    cfgp = vault.config_path
    assert wi.main(["--config", str(cfgp), "regenerate", "--skip-sync"]) == 0
    assert wi.main(["--config", str(cfgp), "audit"]) == 0


def test_dod_audit_non_zero_si_anomalie(vault):
    """Un lien cassé fait sortir l'audit en code non nul (utile en CI)."""
    wi.cmd_regenerate(vault, skip_sync=True)
    art = vault.WIKI / "navigation" / "relevement.md"
    art.write_text(art.read_text(encoding="utf-8") + "\n- [[navigation/casse]]\n", encoding="utf-8")
    assert wi.main(["--config", str(vault.config_path), "audit"]) == 1


def test_dod_index_coherent_avec_disque(vault):
    """INDEX principal liste exactement les sujets ; _INDEX exactement les notions."""
    import index_builder as ib
    ib.regenerate(vault, dry_run=False)

    main_doc = (vault.WIKI / "INDEX.md").read_text(encoding="utf-8")
    assert main_doc.count("/_INDEX]]") == len(ib.list_subjects(vault))

    sub_doc = (vault.WIKI / "navigation" / "_INDEX.md").read_text(encoding="utf-8")
    for notion in ib.list_notions(vault, "navigation"):
        assert f"navigation/{notion}]]" in sub_doc

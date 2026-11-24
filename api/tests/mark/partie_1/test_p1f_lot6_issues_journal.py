"""Lot 6 : l'issue de fin d'appel ne lève pas pour une fiche mal formée, et le dit au journal (jamais un silence)."""

from __future__ import annotations

from loguru import logger

from api.services.actions_communes import issues as ISSUES


def test_une_fiche_mal_formee_ne_leve_pas_et_est_journalisee():
    lignes: list[str] = []
    sink = logger.add(lambda m: lignes.append(str(m)), level="ERROR")
    try:
        def commencee(_fiche):
            raise TypeError("fiche mal formée")

        assert ISSUES.issue_de_fin_d_appel({"x": 1}, "codes", "abandon", commencee) is None
    finally:
        logger.remove(sink)
    assert any("issue" in ligne for ligne in lignes), lignes

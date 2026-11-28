"""[.mark] Lot 8, T45 (reprise de l'audit) : le juge range la fiche « du tour d'avant » quand le CODE la range, dès qu'un article de sa case ``ajouter`` est pris
(``porte._ranger_la_fiche_ajoutee``), même si le panier ne grossit pas : la même ligne retirée et remise ne change pas le compte, mais l'article est pris.

(1) Une regina (ligne 1) / « Remplacez-la par une regina normale. » (la ligne 1 retirée, une regina prise) / « Une regina normale. » → le code refuse la fiche comme identique
au tour d'avant (T34, les articles seuls) et le modèle demande « un de plus ou le même ? ». (2) Une margherita (ligne 1) / « Enlevez la première, encore une margherita
normale. » / « Encore une margherita normale. » → de même. Le juge attend le panier inchangé et la question, jamais un article de plus."""

from __future__ import annotations

import pytest

from api.tests.mark.partie_1 import combinaisons as C

LIGNE_RETIREE_PUIS_REMISE = {
    "regina_remplacee_par_une_regina": ("E1", ("G1", "G11", "G1")),  # E1 : à emporter, panier vide ; G1 pose la regina en ligne 1
    "margherita_retiree_et_remise": ("E4", ("G7+G6", "G6")),  # E4 : une margherita en ligne 1, aucune question
}


@pytest.mark.parametrize("cas", list(LIGNE_RETIREE_PUIS_REMISE), ids=list(LIGNE_RETIREE_PUIS_REMISE))
async def test_la_fiche_qui_retire_et_remet_le_meme_article_est_celle_du_tour_d_avant(faire_monde, monkeypatch, cas):
    monde = await faire_monde("casa-italia")
    etat, suite = LIGNE_RETIREE_PUIS_REMISE[cas]
    r = await C.jouer(monde, monkeypatch, etat, suite)
    assert r.atteint and r.joues == len(suite), r
    assert not r.fautes, r.fautes

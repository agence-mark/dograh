"""[.mark] Lot 8, T45 : le juge des combinaisons compte l'ajout du tour d'avant par rapport au panier VIDÉ, comme le code (T45 = A, Pierre 28/11 3 h 59).

E7 (à emporter, une margherita, une proposition en attente) / « Une margherita normale et une regina normale. » → 2 margheritas, 1 regina / « Une margherita normale et une
regina normale, on vide et on annule. » → le panier vidé, puis 1 margherita, 1 regina / « Une margherita normale et une regina normale. » → le code refuse la fiche comme identique
au tour d'avant (T34, les articles seuls) et le modèle demande « Une deuxième margherita et une deuxième regina, ou c'était les mêmes ? ». La fiche du vidage a ajouté ses deux
articles au panier vidé (le panier a rétréci, mais ses articles sont pris) : le juge attend 1 margherita, 1 regina et la question, jamais 2 et 2."""

from __future__ import annotations

from api.services.commande import porte as PORTE
from api.tests.mark.partie_1 import combinaisons as C

APRES_LE_VIDAGE = ("E7", ("G5", "G5+G14", "G5"))  # la suite réduite de ``test_suites_tirees`` (T45)


async def test_la_fiche_redite_apres_le_vidage_est_la_meme_que_celle_du_vidage(faire_monde, monkeypatch):
    """E7 → G5 · G5+G14 · G5 : le code demande « un de plus ou le même ? » ; le juge ne l'attend plus en double (aucune faute)."""
    monde = await faire_monde("casa-italia")
    r = await C.jouer(monde, monkeypatch, *APRES_LE_VIDAGE)
    assert r.atteint and r.joues == 3, r
    assert not r.fautes, r.fautes


async def test_garde_le_code_qui_ajoute_apres_le_vidage_sans_question_est_une_faute(faire_monde, monkeypatch):
    """Mutation du code : la fiche redite après le vidage est appliquée (une deuxième margherita, une deuxième regina, rien demandé) ; le juge la voit (RC2)."""
    monde = await faire_monde("casa-italia")
    monkeypatch.setattr(PORTE, "_fiche_identique_au_tour_d_avant", lambda p, tour, fiche: None)
    r = await C.jouer(monde, monkeypatch, *APRES_LE_VIDAGE)
    assert r.atteint and r.joues == 3, r
    assert any(pas == "G5" and regle == "RC2" for pas, regle, _ in r.fautes), r.fautes

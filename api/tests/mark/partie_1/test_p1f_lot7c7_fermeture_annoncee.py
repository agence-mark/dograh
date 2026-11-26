"""[.mark] C7 B2 (T2, audit C7a Q1) : la fermeture s'annonce dès le premier tour qui l'apprend.

Décision d'Evan (20-21/11, « annoncer la fermeture dès le début ») : au tour où la commande apprend que tout est fermé, le modèle la dit d'après le statut et les faits de
l'état ; ``fermeture_dite`` (« déjà dite, ne la redis pas ») ne lui est donné qu'aux tours suivants. Avant : posé dès le premier tour, le modèle risquait de ne jamais la dire.
"""

from __future__ import annotations

from types import SimpleNamespace

from api.services.actions_communes import conversation as CONV
from api.services.actions_communes import journal_du_dit as J
from api.services.commande import panier as P
from api.services.commande import porte
from api.services.commande.moteur import prealables

TOUR = "tour_de_l_appel"  # posé par la porte à chaque fiche (``porte._lire_appliquer_conclure``)


def _source_fermee(planifiee: bool = False) -> SimpleNamespace:
    async def etat(_mode):
        return {"ouvert": False, "statut": "LIVRAISON_TERMINEE", "raison": "fin_de_service", "planifiee_permise": planifiee}

    return SimpleNamespace(modes=["emporter", "livraison"], libelles_des_modes={"emporter": "à emporter", "livraison": "en livraison"}, etat=etat)


def _faits(p: dict) -> dict:
    return porte._faits_de_la_fiche(p, False, None, (), (), None)


async def test_t2_la_fermeture_apprise_dans_ce_tour_n_est_pas_dite_deja():
    """Client « En livraison. » (22 h, tout est fermé) : au tour qui l'apprend, ``fermeture_dite`` est absent (le modèle l'annonce) ; au tour suivant, vrai (il ne la redit pas)."""
    p = P.nouveau()
    CONV.de(p)[TOUR] = 1
    await prealables.question_du_mode(_source_fermee(), p, "INCOMPLETE")
    assert J.deja_dit(p, J.FERMETURE)
    assert "fermeture_dite" not in _faits(p)
    CONV.de(p)[TOUR] = 2
    assert _faits(p)["fermeture_dite"] is True


async def test_t2_voisin_la_question_du_mode_reposee_ne_renote_pas_la_fermeture():
    """Voisin : la question du mode reposée au tour suivant ne remet pas la fermeture « à dire » ; elle reste dite."""
    p = P.nouveau()
    CONV.de(p)[TOUR] = 1
    await prealables.question_du_mode(_source_fermee(planifiee=True), p, "INCOMPLETE")
    CONV.de(p)[TOUR] = 2
    r = await prealables.question_du_mode(_source_fermee(planifiee=True), p, "INCOMPLETE")
    assert _faits(p)["fermeture_dite"] is True and not r.suggestion.startswith(" "), r


def test_t2_voisin_jamais_notee_jamais_dite():
    p = P.nouveau()
    CONV.de(p)[TOUR] = 3
    assert "fermeture_dite" not in _faits(p)

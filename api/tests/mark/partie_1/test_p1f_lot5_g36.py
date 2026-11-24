"""[.mark] Plan final Partie 1, lot 5 (R4) : le geste G36 (détour : rendre la main, retour) est codé, et la fin d'appel avec un panier ouvert se termine toujours.

Avant : G36 « ne faisait rien » (une phrase sans outil). Maintenant : une commande ouverte, « et pour réserver ? », la réservation rend la main, l'appel revient chez l'agent qui tient la
commande. Joué depuis E4, E5 et E11. Et : un panier ouvert, « au revoir » deux fois puis le silence : la fin finit par passer (jamais un appel coincé).
"""

from __future__ import annotations

import pytest

from api.services.groupe import passations as PASSATIONS
from api.services.workflow import action_non_aboutie as fin
from api.tests.mark.partie_1 import combinaisons as C
from api.tests.mark.test_action_ouverte_fin_d_appel import _moteur, _panier
from api.services.commande import panier


@pytest.mark.parametrize("etat", ["E4", "E5", "E11"])
async def test_le_detour_ramene_l_appel_a_la_commande_ouverte(faire_monde, monkeypatch, etat):
    monde = await faire_monde("casa-italia")
    r = await C.jouer(monde, monkeypatch, etat, ("G36",))
    assert r.atteint, f"{etat} non atteint"
    assert r.fautes == [], r.fautes


async def test_le_detour_est_vu_rouge_quand_le_code_ne_ramene_plus_l_appel(faire_monde, monkeypatch):
    """Sans le routage vers le porteur, G36 le dit : l'appel ne revient plus à la commande."""
    monde = await faire_monde("casa-italia")
    monkeypatch.setattr(PASSATIONS, "porteur_de_l_action_ouverte", lambda *a, **k: None)
    with pytest.raises(AssertionError, match="G36"):
        await C.jouer(monde, monkeypatch, "E4", ("G36",))


def test_un_panier_ouvert_au_revoir_deux_fois_puis_le_silence_l_appel_se_termine():
    """Le panier ouvert refuse la fin ; « au revoir » redit ne la bloque pas sans fin ; au silence (aucun tour depuis), le plafond du refus laisse l'appel se terminer."""
    fiche = {panier.CLE: _panier()}
    moteur = _moteur(fiche)
    assert fin.verifier_la_fin(moteur) is not None  # premier « au revoir » : refusé une fois
    fiche[fin.CLE_TOUR_APPELANT] = (fiche.get(fin.CLE_TOUR_APPELANT) or 0) + 1  # la personne redit « au revoir » : un nouveau tour
    decisions = [fin.verifier_la_fin(moteur)]
    for _ in range(fin.MAX_REFUS_DANS_LA_FOULEE + 2):  # puis le silence : la même demande de fin, sans parole ni outil
        if decisions[-1] is None:
            break
        decisions.append(fin.verifier_la_fin(moteur))
    assert decisions[-1] is None, "la fin ne passe jamais : l'appel est coincé"
    assert len(decisions) <= fin.MAX_REFUS_DANS_LA_FOULEE + 2

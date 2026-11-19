"""[.mark] SA-33, défaut 3 (appel 2559) : une confirmation n'est jamais acceptée dans le tour même où la relecture a été rendue.

| Test | Ce qu'il prouve |
|---|---|
| même tour | relecture rendue puis ``confirmer`` vrai sans tour de la personne : l'action n'est PAS jouée, refus neutre sans phrase |
| tour suivant | la personne a répondu : la confirmation est jouée comme avant |
| sans relecture | ``confirmer`` vrai sans relecture rendue : rien ne change (le moteur de l'action garde ses propres règles) |
| invisible | le résultat d'une relecture n'est pas modifié |
| sans compteur de tours | rien n'est retenu : le comportement d'avant |
| interrupteur éteint (défaut) | ``garde_confirmation_apres_reponse`` absent : la confirmation est jouée comme avant ; le modèle Restauration l'allume |
| commande réelle | ``finaliser`` (module commande) : la relecture puis ``confirmer`` dans le même tour n'enregistre pas ; au tour suivant, si |
"""

from __future__ import annotations

import pytest

from api.services.integrations.connectors import execution
from api.services.integrations.connectors.catalogue import Action, Connecteur, ContexteAction
from api.services.workflow.fiche_au_fil_de_leau import CLE_TOUR

RELECTURE = {"statut": "INCOMPLETE", "faits": {"a_confirmer": True, "total": 1490}, "suggestion": "Je vous relis : … C'est bon ?", "manque": "relecture"}


def _connecteur(joues: list):
    async def executer(action, arguments, ctx, delai_s):
        joues.append(dict(arguments))
        if arguments.get("confirmer") is True:
            return {"statut": "ENREGISTREE", "faits": {"numero": "A1"}, "suggestion": "C'est enregistré."}
        return dict(RELECTURE)

    action = Action(
        nom="conclure", description="", parametres=(), ecrit=True,
        preparer=lambda a, c: None, resultat=lambda r, a, c: r,
    )
    return Connecteur(nom="interne_essai", libelle="Essai", integration="", actions=(action,), interne=True, executer_interne=executer), action


ALLUME = {"garde_confirmation_apres_reponse": True}


def _ctx(fiche, configurations):
    return ContexteAction(reglages={}, modele=None, organization_id=1, appel={}, run_id=1, fiche=fiche, compte=None, configurations=configurations)


async def _appeler(fiche, joues, arguments, configurations=ALLUME):
    connecteur, action = _connecteur(joues)
    return await execution.appeler(1, connecteur, action, arguments, _ctx(fiche, configurations), 5.0)


@pytest.mark.parametrize("configurations", [None, {}, {"garde_confirmation_apres_reponse": False}])
async def test_interrupteur_eteint_la_confirmation_est_jouee_comme_avant(configurations):
    fiche, joues = {CLE_TOUR: 5}, []
    await _appeler(fiche, joues, {}, configurations)
    r = await _appeler(fiche, joues, {"confirmer": True}, configurations)
    assert r["statut"] == "ENREGISTREE" and "relectures_rendues" not in fiche


def test_le_modele_restauration_allume_la_garde():
    from api.routes.restauration_salle import REGLAGES_RESTAURATION
    from api.services.groupe.reglages import CLES_THEME_INTERVENTIONS

    assert REGLAGES_RESTAURATION["garde_confirmation_apres_reponse"] is True
    assert "garde_confirmation_apres_reponse" in CLES_THEME_INTERVENTIONS


async def test_une_confirmation_dans_le_tour_de_la_relecture_n_est_pas_jouee():
    fiche, joues = {CLE_TOUR: 5}, []
    relecture = await _appeler(fiche, joues, {})
    assert relecture == RELECTURE  # invisible : le résultat de la relecture est intact
    refus = await _appeler(fiche, joues, {"confirmer": True})
    assert joues == [{}], "la confirmation sans réponse de la personne a été jouée"
    assert refus["statut"] != "ENREGISTREE" and refus["suggestion"] == ""
    assert refus["manque"] == "reponse_a_la_relecture"


async def test_au_tour_suivant_de_la_personne_la_confirmation_est_jouee():
    fiche, joues = {CLE_TOUR: 5}, []
    await _appeler(fiche, joues, {})
    fiche[CLE_TOUR] = 6  # « Oui, c'est bon. »
    r = await _appeler(fiche, joues, {"confirmer": True})
    assert r["statut"] == "ENREGISTREE" and joues == [{}, {"confirmer": True}]


async def test_sans_relecture_rendue_une_confirmation_passe_comme_avant():
    fiche, joues = {CLE_TOUR: 5}, []
    r = await _appeler(fiche, joues, {"confirmer": True})
    assert r["statut"] == "ENREGISTREE"


async def test_sans_compteur_de_tours_rien_n_est_retenu():
    fiche, joues = {}, []
    await _appeler(fiche, joues, {})
    r = await _appeler(fiche, joues, {"confirmer": True})
    assert r["statut"] == "ENREGISTREE"


# --- Sur la vraie commande ------------------------------------------------------------------------------------

from api.tests.mark.test_base_client import base_essai, base_prete  # noqa: E402,F401
from api.tests.mark.test_restauration_classeur_commande import commerce  # noqa: E402,F401
from api.tests.mark.test_restauration_commande_finaliser import Appel  # noqa: E402


@pytest.mark.parametrize("en_deux_tours", [False, pytest.param(True, marks=pytest.mark.xfail(strict=True, reason="Repris au lot 6 : écrit sur la fiche avec la couche de parole (anciens-tests.md, D49)"))])
async def test_finaliser_ne_s_enregistre_qu_apres_un_tour_de_la_personne(commerce, en_deux_tours):
    from api.services.commande import moteur
    from api.services.integrations.connectors import confirmation

    a = await Appel(commerce, vente_en_plus=False).pret()
    fiche = {CLE_TOUR: 3}
    relecture = await a.jusqu_a_la_relecture()
    assert relecture.manque == "relecture" and relecture.faits.get("a_confirmer") is True
    confirmation.noter_la_relecture(fiche, "commande.finaliser", {"faits": relecture.faits})
    if en_deux_tours:
        fiche[CLE_TOUR] = 4
    refus = confirmation.confirmation_avant_la_reponse(fiche, "commande.finaliser", {"confirmer": True})
    if en_deux_tours:
        assert refus is None
        assert (await a.finaliser(confirmer=True)).statut == "ENREGISTREE"
    else:
        assert refus is not None and refus["manque"] == "reponse_a_la_relecture"
        assert not a.p.get("enregistree")
    assert moteur  # le moteur de la commande garde ses propres règles (empreinte, jeton)

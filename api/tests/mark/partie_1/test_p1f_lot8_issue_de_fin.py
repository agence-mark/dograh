"""[.mark] Partie 1, lot 8a (113, 113 bis) : l'issue « abandonnée » de fin d'appel est déclarée par chaque connecteur et choisie par UNE priorité écrite.

Comportement égal à la voix : la commande passe devant la réservation, une issue déjà posée n'est jamais écrasée, la réservation seule garde son issue.
"""

from __future__ import annotations

import pytest

from api.services.commande import panier as P
from api.services.modules import crochets
from api.services.reservation import moteur as R


def _commande_commencee() -> dict:
    ouverte = P.nouveau()
    ouverte.update(mode="emporter", lignes=[{"n": 1, "quantite": 1, "nom": "Margherita"}])
    return {P.CLE: ouverte}


def _reservation_commencee() -> dict:
    return {R.CLE: {"brouillon": {"personnes": 2}}}


def test_la_commande_seule_est_abandonnee():
    assert crochets.issue_de_fin(_commande_commencee()) == "commande_abandonnee"


def test_la_reservation_seule_garde_son_issue():
    assert crochets.issue_de_fin(_reservation_commencee()) == "reservation_abandonnee"


def test_deux_abandons_dans_le_meme_appel_donnent_l_issue_de_la_priorite_quel_que_soit_l_ordre_des_connecteurs(monkeypatch):
    fiche = {**_commande_commencee(), **_reservation_commencee()}
    assert crochets.ORDRE_DES_ISSUES[0] == "commande"
    assert crochets.issue_de_fin(fiche) == "commande_abandonnee"
    from api.services.integrations.connectors import catalogue

    vrai = catalogue.connecteurs
    monkeypatch.setattr(catalogue, "connecteurs", lambda: list(reversed(vrai())))
    assert crochets.issue_de_fin(fiche) == "commande_abandonnee"


def test_une_issue_deja_posee_n_est_jamais_ecrasee():
    fiche = {**_commande_commencee(), **_reservation_commencee(), "call_disposition": "commande_enregistree"}
    assert crochets.issue_de_fin(fiche) is None


def test_les_codes_regles_sont_ceux_des_connecteurs():
    fiche = {**_commande_commencee(), "commande_issues_reglees": {"commande_abandonnee": "Abandon"}}
    assert crochets.issue_de_fin(fiche) == "Abandon"


def test_rien_de_commence_rien_a_dire():
    assert crochets.issue_de_fin({}) is None
    assert crochets.issue_de_fin(None) is None


def test_seuls_la_commande_et_la_reservation_declarent_une_issue_de_fin():
    from api.services.integrations.connectors.catalogue import connecteurs

    assert {c.nom for c in connecteurs() if c.issue_de_fin} == {"commande", "reservation"}


@pytest.mark.parametrize("fiche", [{"commande_panier": "pas un dictionnaire"}, {"reservation_etat": 3}])
def test_une_fiche_mal_formee_ne_leve_pas(fiche):
    assert crochets.issue_de_fin(fiche) is None

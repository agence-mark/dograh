"""[.mark] Partie 1, lot 8a (113, 113 bis) : l'issue « abandonnée » de fin d'appel est déclarée par chaque connecteur et choisie par UNE priorité écrite.

Comportement égal à la voix : la commande passe devant la réservation, une issue déjà posée n'est jamais écrasée, la réservation seule garde son issue.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

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


# ---- 113 bis : au clavier, la même issue (avant, « commande abandonnée » n'était jamais posée au clavier)


async def _issue_au_clavier(fiche: dict, monkeypatch, classement: str | None = None) -> str | None:
    """L'issue écrite à la fin d'une partie au clavier (fin demandée ou par inactivité : ``complete_text_chat_session``) ; le classement par le modèle rend ``classement``."""
    from api.services.workflow import text_chat_session_service as service

    ecrit: dict = {}
    classe = AsyncMock(return_value=classement)
    monkeypatch.setattr(service, "extract_text_chat_final_variables", AsyncMock(return_value={}))
    monkeypatch.setattr(service, "extract_text_chat_final_disposition", classe)
    monkeypatch.setattr(service, "map_disposition", AsyncMock(return_value=None))
    monkeypatch.setattr(service, "_build_text_chat_completion_write", lambda **kwargs: ecrit.update(kwargs) or {})
    monkeypatch.setattr(service.db_client, "complete_workflow_run_text_session", AsyncMock())
    monkeypatch.setattr(service, "_upload_text_chat_transcript", AsyncMock())
    monkeypatch.setattr(service, "_enqueue_text_chat_completion", AsyncMock())
    monkeypatch.setattr(service, "_reload_text_chat_session", AsyncMock())
    workflow_run = SimpleNamespace(is_completed=False, workflow_id=5, workflow=SimpleNamespace(organization_id=7), definition=None)
    session = SimpleNamespace(workflow_run=workflow_run, revision=2, session_data={}, checkpoint={"current_node_id": "n1", "gathered_context": fiche})
    await service.complete_text_chat_session(run_id=1, text_session=session, expected_revision=2)
    ecrit["classe"] = classe.await_count
    return ecrit["issue"]


async def test_au_clavier_une_partie_finie_avec_un_panier_commence_finit_abandonnee(monkeypatch):
    assert await _issue_au_clavier(_commande_commencee(), monkeypatch) == "commande_abandonnee"


async def test_au_clavier_la_reservation_seule_garde_son_issue_et_la_commande_passe_devant(monkeypatch):
    assert await _issue_au_clavier(_reservation_commencee(), monkeypatch) == "reservation_abandonnee"
    assert await _issue_au_clavier({**_commande_commencee(), **_reservation_commencee()}, monkeypatch) == "commande_abandonnee"


async def test_au_clavier_rien_de_commence_c_est_le_classement_du_modele_qui_decide(monkeypatch):
    assert await _issue_au_clavier({}, monkeypatch, classement="appel_sans_suite") == "appel_sans_suite"


async def test_au_clavier_une_commande_enregistree_n_est_pas_abandonnee(monkeypatch):
    fiche = _commande_commencee()
    fiche[P.CLE]["enregistree"] = {"numero": "C1"}
    assert await _issue_au_clavier(fiche, monkeypatch) is None


async def test_au_clavier_une_issue_deja_posee_n_est_jamais_ecrasee(monkeypatch):
    fiche = {**_commande_commencee(), "call_disposition": "message_a_transmettre"}
    assert await _issue_au_clavier(fiche, monkeypatch, classement="message_a_transmettre") == "message_a_transmettre"

"""[.mark] agent-facon-tala, revue 2 (R-12, R-16, R-17) : les issues réservées se lisent dans ce que le run EXÉCUTE.

R-12 (majeur) : les issues réservées d'un outil (transfert, demande de rappel) étaient lues sur la version PUBLIÉE de chaque
agent du groupe, celui de départ compris, alors que le clavier joue le BROUILLON (``use_draft``). Un outil posé seulement dans
le brouillon voyait son issue non réservée : le classement final remplaçait le vrai résultat. La règle est celle de la passation
(``definition_to_run``) : l'agent de départ, c'est la version que le run a épinglée (clavier) ou le graphe de l'agent actif
(téléphone) ; les autres agents du groupe, la version que ce run utilise (brouillon d'un test, publiée sinon).

| Test | Ce qu'il prouve |
|---|---|
| groupe, brouillon | un collègue dont l'outil n'est que dans le brouillon : réservée quand le run joue le brouillon, pas sinon |
| groupe, publiée | un collègue dont l'outil n'est que dans la publiée : pas réservée quand le run joue le brouillon |
| départ | l'agent de départ se lit dans ce que le run exécute, pas dans la publiée |
| clavier, route réelle | outil seulement dans le brouillon : la fin de session garde l'issue de l'outil sans classement ; l'inverse : l'issue n'est pas réservée |
| téléphone | le moteur lit le graphe de l'agent actif et la version du run pour les collègues |
| R-16 | le groupe est lu une seule fois par fin de session clavier |
| R-17 | au rejeu d'un test, l'outil de rappel est simulé : aucune entrée, aucune issue, une note |
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from pipecat.tests import MockLLMService

from api.services.apres_appel.demande_de_rappel import ACTION
from api.services.apres_appel.rappels import CLE_RAPPEL, rappels_de
from api.services.tests_rejouables.simulation import CLE_NOTES, CLE_REJEU, RESULTAT_NEUTRE
from api.services.workflow.disposition_extraction import DispositionExtractionService
from api.services.workflow.issue_reservee import issues_reservees_du_groupe
from api.tests.mark.test_agent_facon_tala_lot_b1_demande_de_rappel import (
    CONFIG,
    ISSUE,
    _appels_du_modele,
    _clavier,
    _moteur,
    _outil,
)

ORG = 7
OUTIL = SimpleNamespace(category="native", definition={"config": {"action": ACTION, "call_disposition": ISSUE}})


def _def(*uuids):
    return SimpleNamespace(workflow_json={"nodes": [{"data": {"tool_uuids": list(uuids)}}]})


def _agent(identifiant, publiee=(), reglages=None):
    return SimpleNamespace(
        id=identifiant,
        workflow_configurations=reglages or {},
        released_definition=_def(*publiee),
        current_definition=None,
    )


def _groupe(publie_collegue=(), brouillon_collegue=()):
    """Un principal (départ) et un collègue : le collègue a ses outils publiés et un brouillon."""
    principal = _agent(1, reglages={"agents_specialises": [2]})
    collegue = _agent(2, publiee=publie_collegue, reglages={"agent_principal_id": 1})
    agents = {1: principal, 2: collegue}
    brouillons = {2: _def(*brouillon_collegue)}

    async def lire_workflow(identifiant, _org):
        return agents[identifiant]

    async def lire_outils(uuids, _org):
        return [OUTIL for u in uuids if u == "rappel"]

    def lire_definition(utilise_le_brouillon):
        async def lire(workflow):
            if utilise_le_brouillon and workflow.id in brouillons:
                return brouillons[workflow.id]
            return workflow.released_definition

        return lire

    return lire_workflow, lire_outils, lire_definition


# --------------------------------------------------------------------------- #
# R-12 : la lecture du groupe
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_un_outil_seulement_dans_le_brouillon_d_un_collegue_est_reserve_quand_le_run_joue_le_brouillon():
    lire_workflow, lire_outils, lire_definition = _groupe(brouillon_collegue=("rappel",))
    # le run joue le brouillon
    assert await issues_reservees_du_groupe(1, ORG, lire_workflow, lire_outils, lire_definition(True)) == {ISSUE}
    # un appel (version publiée) ne le voit pas, et la lecture d'avant (sans règle de version) non plus
    assert await issues_reservees_du_groupe(1, ORG, lire_workflow, lire_outils, lire_definition(False)) == set()
    assert await issues_reservees_du_groupe(1, ORG, lire_workflow, lire_outils) == set()


@pytest.mark.asyncio
async def test_un_outil_seulement_dans_la_publiee_n_est_pas_reserve_quand_le_run_joue_le_brouillon():
    lire_workflow, lire_outils, lire_definition = _groupe(publie_collegue=("rappel",), brouillon_collegue=())
    assert await issues_reservees_du_groupe(1, ORG, lire_workflow, lire_outils, lire_definition(True)) == set()
    assert await issues_reservees_du_groupe(1, ORG, lire_workflow, lire_outils, lire_definition(False)) == {ISSUE}


@pytest.mark.asyncio
async def test_l_agent_de_depart_se_lit_dans_ce_que_le_run_execute():
    lire_workflow, lire_outils, lire_definition = _groupe()
    # sa publiée n'a pas l'outil, le graphe exécuté l'a
    assert await issues_reservees_du_groupe(
        1, ORG, lire_workflow, lire_outils, lire_definition(True), uuids_de_depart=["rappel"]
    ) == {ISSUE}
    # l'inverse : le graphe exécuté ne l'a pas (la publiée l'avait)
    principal_publie = _agent(1, publiee=("rappel",), reglages={"agents_specialises": [2]})
    agents = {1: principal_publie, 2: _agent(2, reglages={"agent_principal_id": 1})}

    async def lire(identifiant, _org):
        return agents[identifiant]

    assert await issues_reservees_du_groupe(1, ORG, lire, lire_outils, uuids_de_depart=[]) == set()
    assert await issues_reservees_du_groupe(1, ORG, lire, lire_outils) == {ISSUE}


# --------------------------------------------------------------------------- #
# R-12 : le clavier, la vraie route
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_au_clavier_un_outil_seulement_dans_le_brouillon_garde_son_issue_sans_classement(
    db_session, async_session, test_client_factory
):
    tour, contexte, classement = await _clavier(
        db_session,
        async_session,
        test_client_factory,
        avec_outil=True,
        appel_du_modele=_appels_du_modele(),
        version="brouillon",
    )
    assert [e["origine"] for e in rappels_de(tour["checkpoint"]["gathered_context"])] == ["agent"]
    assert contexte["call_disposition"] == ISSUE
    classement.assert_not_awaited()


@pytest.mark.asyncio
async def test_au_clavier_un_outil_seulement_dans_la_publiee_n_est_pas_reserve(
    db_session, async_session, test_client_factory
):
    from api.services.workflow.text_chat_runner import issues_reservees_du_clavier

    tour, _contexte, _classement = await _clavier(
        db_session,
        async_session,
        test_client_factory,
        avec_outil=True,
        appel_du_modele=[MockLLMService.create_text_chunks("Très bien.")],
        version="publiee",
    )
    run = await db_session.get_workflow_run_by_id(tour["session"]["workflow_run_id"] if "session" in tour else tour["workflow_run_id"])
    run = (await db_session.get_workflow_run_with_context(run.id))[0]
    assert (run.extra or {}).get("use_draft") is True
    # le brouillon joué n'a pas l'outil : l'issue n'est pas réservée ; la lecture « publiée » (sans le run) la verrait
    assert await issues_reservees_du_clavier(run.workflow_id, run.workflow.organization_id, run) == set()
    assert await issues_reservees_du_clavier(run.workflow_id, run.workflow.organization_id) == {ISSUE}


# --------------------------------------------------------------------------- #
# R-12 : le téléphone
# --------------------------------------------------------------------------- #


async def _reservees_au_telephone(*, graphe_actif, utilise_le_brouillon, brouillon_collegue=(), publie_collegue=()):
    moteur = await _moteur()
    for noeud in moteur.active_agent.workflow.nodes.values():
        noeud.tool_uuids = list(graphe_actif)
    moteur.__dict__["_agent_factory"] = SimpleNamespace(_use_draft=utilise_le_brouillon)
    moteur.active_agent.workflow_id = 1
    agents = {
        1: _agent(1, reglages={"agents_specialises": [2]}),
        2: _agent(2, publiee=publie_collegue, reglages={"agent_principal_id": 1}),
    }

    async def lire_workflow(identifiant, organization_id):
        return agents[identifiant]

    async def brouillon(identifiant):
        return _def(*brouillon_collegue) if identifiant == 2 else None

    async def outils(uuids, _org):
        return [OUTIL for u in uuids if u == "rappel"]

    with (
        patch("api.services.workflow.pipecat_engine.db_client.get_workflow", lire_workflow),
        patch("api.services.workflow.pipecat_engine.db_client.get_draft_version", brouillon),
        patch.object(moteur, "lire_outils", outils),
    ):
        return await moteur._issues_reservees_aux_transferts()


@pytest.mark.asyncio
async def test_au_telephone_l_outil_du_graphe_de_l_agent_actif_est_reserve_meme_absent_de_la_publiee():
    assert await _reservees_au_telephone(graphe_actif=("rappel",), utilise_le_brouillon=False) == {ISSUE}


@pytest.mark.asyncio
async def test_au_telephone_un_outil_absent_du_graphe_actif_et_de_la_publiee_n_est_pas_reserve():
    assert await _reservees_au_telephone(graphe_actif=(), utilise_le_brouillon=False) == set()


@pytest.mark.asyncio
async def test_au_telephone_le_collegue_se_lit_dans_la_version_du_run():
    # appel de test (brouillon) : le brouillon du collègue compte ; appel réel (publiée) : non
    assert await _reservees_au_telephone(graphe_actif=(), utilise_le_brouillon=True, brouillon_collegue=("rappel",)) == {ISSUE}
    assert await _reservees_au_telephone(graphe_actif=(), utilise_le_brouillon=False, brouillon_collegue=("rappel",)) == set()
    # l'inverse : l'outil n'est que dans la publiée du collègue, l'appel de test joue son brouillon
    assert await _reservees_au_telephone(graphe_actif=(), utilise_le_brouillon=True, publie_collegue=("rappel",)) == set()
    assert await _reservees_au_telephone(graphe_actif=(), utilise_le_brouillon=False, publie_collegue=("rappel",)) == {ISSUE}


# --------------------------------------------------------------------------- #
# R-16 : le groupe est lu une seule fois
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_la_fin_de_session_clavier_lit_le_groupe_une_seule_fois(db_session, async_session, test_client_factory):
    """Une issue posée que le groupe ne réserve pas : la lecture sert au contrôle d'entrée ET au classement. Avant R-16 : deux lectures."""
    from api.services.workflow import text_chat_runner

    lectures = []
    vraie = text_chat_runner.issues_reservees_du_clavier

    async def comptee(*args, **kwargs):
        lectures.append(1)
        return await vraie(*args, **kwargs)

    async def aucune(*_a, **_k):
        return set()  # le groupe ne réserve rien : l'issue posée n'est pas gardée, le classement tourne

    with (
        patch.object(text_chat_runner, "issues_reservees_du_clavier", comptee),
        patch("api.services.workflow.issue_reservee.issues_reservees_du_groupe", aucune),
    ):
        _tour, contexte, _classement = await _clavier(
            db_session,
            async_session,
            test_client_factory,
            avec_outil=True,
            appel_du_modele=_appels_du_modele(),
            classement_reel=True,
        )
    assert contexte["call_disposition"] == "autre_issue"  # le classement a tourné
    assert len(lectures) == 1, lectures


# --------------------------------------------------------------------------- #
# R-17 : au rejeu d'un test
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_au_rejeu_l_outil_de_rappel_est_simule_aucune_entree_aucune_issue():
    moteur = await _moteur({"nom": "Faucheux", "numero_dicte": "0631524780", CLE_REJEU: True})
    from api.tests.mark.test_agent_facon_tala_lot_b1_demande_de_rappel import _appeler

    resultat = await _appeler(moteur, _outil(), objet="un devis")
    assert resultat == RESULTAT_NEUTRE
    assert CLE_RAPPEL not in moteur._gathered_context
    assert "call_disposition" not in moteur._gathered_context
    [note] = moteur._gathered_context[CLE_NOTES]
    assert note["nom"] == "demander_un_rappel" and note["categorie"] == "native" and note["arguments"] == {"objet": "un devis"}


@pytest.mark.asyncio
async def test_hors_rejeu_l_outil_de_rappel_ecrit_comme_avant():
    moteur = await _moteur({"nom": "Faucheux", "numero_dicte": "0631524780"})
    from api.tests.mark.test_agent_facon_tala_lot_b1_demande_de_rappel import _appeler

    assert (await _appeler(moteur, _outil(), objet="un devis"))["statut"] == "transmise"
    assert len(rappels_de(moteur._gathered_context)) == 1
    assert CONFIG["call_disposition"] == moteur._gathered_context["call_disposition"]

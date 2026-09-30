"""[.mark] D1 et D2 : une sortie refusée ne boucle plus quand la personne refuse.

Chantier correctifs-second-banc-34 (30/09/2026), run 904 : la personne refuse d'épeler
son nom et de donner son adresse. L'agent épelle le nom lui-même et le fait confirmer
(le code ne le compte pas, à raison), puis redemande la même confirmation ; la sortie
« nom, numéro et adresse notés » est refusée deux fois (tours 9 et 12) et le secours
(« la 3e tentative passe ») n'est jamais atteint : le modèle ne l'a pas retentée.

| Test | Ce qu'il prouve |
|---|---|
| sans progrès, autre tour | la 2e tentative à qui il manque les mêmes champs passe (`sortie_forcee`) |
| même tour | le modèle qui retente sans avoir rien demandé reste refusé |
| progrès | quelque chose a avancé : refusée encore, puis le plafond de 2 refus s'applique |
| consigne | le nom s'épelle par la personne elle-même ; un refus : dire pourquoi, puis reprendre |
| clavier, run 904 | deux messages de la personne, la 2e tentative sans progrès sort de l'étape |
"""

import copy
import uuid
from unittest.mock import AsyncMock, patch

import pytest

from api.services.workflow.fiche_au_fil_de_leau import (
    CLE_JOURNAL,
    CLE_TOUR,
    consigne_de_sortie,
    decider_la_sortie,
)
from api.tests.mark.test_clavier_porte_la_fiche import DEFINITION, _monter
from pipecat.tests import MockLLMService

MANQUANTS = [("nom", "non_epele"), ("commune", "vide"), ("adresse_intervention", "vide")]


def _statuts(fiche: dict) -> list[str]:
    return [e["statut"] for e in fiche[CLE_JOURNAL] if e.get("sortie")]


def test_D1_run_904_sans_progres_a_un_autre_tour_la_sortie_passe():
    fiche = {CLE_TOUR: 9}
    assert decider_la_sortie(fiche, "coordonnees_notees", MANQUANTS) == "refusee"
    fiche[CLE_TOUR] = 12
    assert decider_la_sortie(fiche, "coordonnees_notees", MANQUANTS) == "forcee"
    assert _statuts(fiche) == ["sortie_refusee", "sortie_forcee"]
    assert fiche[CLE_JOURNAL][-1]["motif"] == "sans_progres"


def test_D1_relecture_M2_le_tour_de_la_reponse_prime_sur_le_tour_courant():
    """La personne a parlé pendant l'attente des notes : le compteur a avancé, mais le
    modèle répondait au tour du refus. La sortie reste refusée."""
    fiche = {CLE_TOUR: 9}
    assert decider_la_sortie(fiche, "coordonnees_notees", MANQUANTS) == "refusee"
    fiche[CLE_TOUR] = 10
    assert decider_la_sortie(fiche, "coordonnees_notees", MANQUANTS, 9) == "refusee"


def test_D1_relecture_M4_sans_tour_compte_l_ancien_comportement():
    """Vocal, modules éteints : aucun tour compté. Refusée, refusée, puis le plafond."""
    fiche = {}
    assert decider_la_sortie(fiche, "coordonnees_notees", MANQUANTS) == "refusee"
    assert decider_la_sortie(fiche, "coordonnees_notees", MANQUANTS) == "refusee"
    assert decider_la_sortie(fiche, "coordonnees_notees", MANQUANTS) == "forcee"
    assert fiche[CLE_JOURNAL][-1]["motif"] == "plafond"


def test_D1_au_meme_tour_la_sortie_reste_refusee():
    fiche = {CLE_TOUR: 9}
    assert decider_la_sortie(fiche, "coordonnees_notees", MANQUANTS) == "refusee"
    assert decider_la_sortie(fiche, "coordonnees_notees", MANQUANTS) == "refusee"
    assert _statuts(fiche) == ["sortie_refusee", "sortie_refusee"]


def test_D1_un_progres_garde_le_refus_puis_le_plafond_s_applique():
    fiche = {CLE_TOUR: 9}
    assert decider_la_sortie(fiche, "coordonnees_notees", MANQUANTS) == "refusee"
    fiche[CLE_TOUR] = 10
    assert decider_la_sortie(fiche, "coordonnees_notees", MANQUANTS[1:]) == "refusee"
    fiche[CLE_TOUR] = 11
    assert decider_la_sortie(fiche, "coordonnees_notees", MANQUANTS[2:]) == "forcee"


def test_D1_une_autre_sortie_a_son_propre_compte():
    fiche = {CLE_TOUR: 9}
    assert decider_la_sortie(fiche, "coordonnees_notees", MANQUANTS) == "refusee"
    fiche[CLE_TOUR] = 10
    assert decider_la_sortie(fiche, "autre_sortie", MANQUANTS) == "refusee"


def test_D2_la_consigne_dit_qui_epelle_et_quoi_faire_d_un_refus():
    consigne = consigne_de_sortie(MANQUANTS)
    assert "nom épelé par la personne elle-même, lettre par lettre" in consigne
    assert "tu ne l'épelles jamais à sa place" in consigne
    assert "Si la personne refuse de les donner, dis-lui une fois pourquoi" in consigne


def _definition_avec_requis(requis):
    definition = copy.deepcopy(DEFINITION)
    definition["edges"][0]["data"]["champs_requis"] = requis
    return definition


async def _deux_messages(test_client_factory, user, workflow, tours):
    """Deux messages de la personne ; chaque tour construit son modèle (clavier C8)."""
    llm = [MockLLMService(mock_steps=[], chunk_delay=0.001)]  # accueil (texte fixe)
    llm += [MockLLMService(mock_steps=repliques, chunk_delay=0.001) for _, repliques in tours]
    llm += [MockLLMService(mock_steps=[], chunk_delay=0.001) for _ in range(3)]
    async with test_client_factory(user) as client:
        with (
            patch("api.services.workflow.text_chat_runner.create_llm_service", side_effect=llm),
            patch(
                "api.services.workflow.text_chat_runner.db_client.has_active_recordings",
                new=AsyncMock(return_value=False),
            ),
        ):
            creee = await client.post(f"/api/v1/workflow/{workflow.id}/text-chat/sessions", json={})
            assert creee.status_code == 200, creee.text
            session = creee.json()
            revision, charge = session["revision"], None
            for message, _ in tours:
                reponse = await client.post(
                    f"/api/v1/workflow/{workflow.id}/text-chat/sessions/"
                    f"{session['workflow_run_id']}/messages",
                    json={"text": message, "expected_revision": revision},
                )
                assert reponse.status_code == 200, reponse.text
                charge = reponse.json()
                revision = charge["revision"]
            return charge


@pytest.mark.asyncio
async def test_D1_au_clavier_run_904_la_personne_refuse_deux_fois_l_agent_enchaine(
    db_session, async_session, test_client_factory
):
    configuration = {
        "fiche_au_fil_de_leau": True,
        "fiche_champs": [{"nom": "numero_rappel", "origine": "dicte"}],
    }
    user, workflow = await _monter(
        db_session, async_session, configuration, _definition_avec_requis(["numero_rappel"])
    )
    porte = f"porte_{uuid.uuid4().hex[:6]}"
    charge = await _deux_messages(
        test_client_factory,
        user,
        workflow,
        [
            (
                "le technicien me rappellera",
                [
                    MockLLMService.create_function_call_chunks("fin", {}, tool_call_id=f"{porte}_1"),
                    MockLLMService.create_text_chunks("J'en ai besoin pour vous rappeler. Quel est votre numéro ?"),
                ],
            ),
            (
                "je ne le donnerai pas",
                [
                    MockLLMService.create_function_call_chunks("fin", {}, tool_call_id=f"{porte}_2"),
                    MockLLMService.create_text_chunks("Entendu, au revoir."),
                ],
            ),
        ],
    )
    assert charge["checkpoint"]["current_node_id"] == "end", charge["checkpoint"]
    journal = charge["checkpoint"]["gathered_context"]["fiche_journal"]
    assert [e["statut"] for e in journal if e.get("sortie") == "fin"] == [
        "sortie_refusee",
        "sortie_forcee",
    ], journal

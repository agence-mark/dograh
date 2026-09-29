"""[.mark] C8 : le clavier construit l'appel comme le vocal (fiche, outil, passe de fin).

Chantier correctifs-banc-34 (29/09/2026), plan `Labo-agent-vocal/plans/correctifs-banc-34/`.

Constat du banc de l'agent n° 34 (run 896) : au clavier, `noter_information` n'était
pas proposé et la fiche restait vide, parce que `text_chat_runner` construisait le
moteur sans `fiche=` (seul `run_pipeline.py` la passait). Un clavier qui ne mesure pas
l'agent réel ne sert à rien : le volume au clavier du n° 34 s'était arrêté là.

Ces tests passent par les VRAIES routes HTTP du clavier (création de session, message,
fin de session), sur la base de test ; seuls le modèle (réponses écrites d'avance) et
l'extraction (valeurs écrites d'avance) sont remplacés.

| Test | Ce qu'il prouve |
|---|---|
| outil | le modèle appelle `noter_information` au clavier : la valeur est écrite dans la fiche de la session et en base, avec son journal |
| refus | le contrôle « dit tel quel » de l'outil joue au clavier comme au téléphone |
| éteint | interrupteur éteint : l'outil reste inconnu, rien n'est écrit (comportement d'avant) |
| fin abandonnée | la personne ferme la conversation sans transition : la passe de fin d'appel remplit un champ vide, comme à la fin d'un appel |
"""

import copy
import uuid
from unittest.mock import AsyncMock, patch

import pytest

from api.db.models import OrganizationModel, UserModel, organization_users_association
from api.enums import OrganizationConfigurationKey
from api.schemas.ai_model_configuration import EffectiveAIModelConfiguration
from api.services.configuration.ai_model_configuration import (
    convert_legacy_ai_model_configuration_to_v2,
)
from api.tests.integrations._run_pipeline_helpers import USER_CONFIGURATION
from pipecat.tests import MockLLMService

DEFINITION = {
    "nodes": [
        {
            "id": "start",
            "type": "startCall",
            "position": {"x": 0, "y": 0},
            "data": {
                "name": "Start",
                "prompt": "Tu prends les coordonnées.",
                "is_start": True,
                "allow_interrupt": False,
                "add_global_prompt": False,
                "greeting_type": "text",
                "greeting": "Bonjour.",
            },
        },
        {
            "id": "end",
            "type": "endCall",
            "position": {"x": 0, "y": 200},
            "data": {
                "name": "End",
                "prompt": "Fin.",
                "is_end": True,
                "allow_interrupt": False,
                "add_global_prompt": False,
            },
        },
    ],
    "edges": [
        {
            "id": "start-end",
            "source": "start",
            "target": "end",
            "data": {"label": "Fin", "condition": "Quand c'est fini."},
        }
    ],
}

FICHE = {
    "fiche_au_fil_de_leau": True,
    "fiche_champs": [
        {"nom": "nom", "origine": "dicte", "description": "Nom de famille"},
        {"nom": "motif", "origine": "dicte", "description": "Ce que la personne demande"},
    ],
}


async def _monter(db_session, async_session, configurations: dict):
    """Organisation française, agent publié AVEC sa configuration (comme l'écran)."""
    suffixe = uuid.uuid4().hex[:10]
    org = OrganizationModel(provider_id=f"test-org-clavier-fiche-{suffixe}")
    async_session.add(org)
    await async_session.flush()
    user = UserModel(
        provider_id=f"test-user-clavier-fiche-{suffixe}",
        selected_organization_id=org.id,
    )
    async_session.add(user)
    await async_session.flush()
    await async_session.execute(
        organization_users_association.insert().values(
            user_id=user.id, organization_id=org.id
        )
    )
    modeles = copy.deepcopy(USER_CONFIGURATION)
    modeles["stt"]["language"] = "fr"
    await db_session.upsert_configuration(
        org.id,
        OrganizationConfigurationKey.MODEL_CONFIGURATION_V2.value,
        convert_legacy_ai_model_configuration_to_v2(
            EffectiveAIModelConfiguration.model_validate(modeles)
        ).model_dump(mode="json", exclude_none=True),
    )
    workflow = await db_session.create_workflow(
        name="Clavier fiche",
        workflow_definition=DEFINITION,
        user_id=user.id,
        organization_id=org.id,
    )
    await db_session.save_workflow_draft(
        workflow.id, workflow_definition=DEFINITION, workflow_configurations=configurations
    )
    await db_session.publish_workflow_draft(workflow.id)
    return user, workflow


async def _converser(test_client_factory, user, workflow, repliques, message, *, finir=False):
    """Crée la session, envoie UN message ; `finir` ferme la conversation ensuite."""
    llm = [
        MockLLMService(mock_steps=[], chunk_delay=0.001),  # accueil (texte fixe)
        MockLLMService(mock_steps=repliques, chunk_delay=0.001),
        # La fin de conversation crée son propre modèle d'extraction.
        MockLLMService(mock_steps=[], chunk_delay=0.001),
    ]
    async with test_client_factory(user) as client:
        with (
            patch(
                "api.services.workflow.text_chat_runner.create_llm_service",
                side_effect=llm,
            ),
            patch(
                "api.services.workflow.text_chat_runner.db_client.has_active_recordings",
                new=AsyncMock(return_value=False),
            ),
        ):
            creee = await client.post(
                f"/api/v1/workflow/{workflow.id}/text-chat/sessions", json={}
            )
            assert creee.status_code == 200, creee.text
            session = creee.json()
            reponse = await client.post(
                f"/api/v1/workflow/{workflow.id}/text-chat/sessions/"
                f"{session['workflow_run_id']}/messages",
                json={"text": message, "expected_revision": session["revision"]},
            )
            assert reponse.status_code == 200, reponse.text
            if not finir:
                return reponse.json(), session["workflow_run_id"]
            fin = await client.post(
                f"/api/v1/workflow/{workflow.id}/text-chat/sessions/"
                f"{session['workflow_run_id']}/end",
                json={"expected_revision": reponse.json()["revision"]},
            )
            assert fin.status_code == 200, fin.text
            return fin.json(), session["workflow_run_id"]


def _noter(arguments: dict, identifiant: str):
    return MockLLMService.create_function_call_chunks(
        "noter_information", arguments, tool_call_id=identifiant
    )


@pytest.mark.asyncio
async def test_C8_au_clavier_l_outil_ecrit_dans_la_fiche(
    db_session, async_session, test_client_factory
):
    user, workflow = await _monter(db_session, async_session, FICHE)
    charge, run_id = await _converser(
        test_client_factory,
        user,
        workflow,
        [_noter({"nom": "Lemaire"}, "note_1"), MockLLMService.create_text_chunks("Merci. Que puis-je faire ?")],
        "je m'appelle Lemaire",
    )
    fiche = charge["checkpoint"]["gathered_context"]
    assert fiche.get("nom") == "Lemaire", fiche
    assert any(
        e.get("champ") == "nom" and e.get("statut") == "ecrit" for e in fiche.get("fiche_journal") or []
    ), fiche.get("fiche_journal")
    run = await db_session.get_workflow_run_by_id(run_id)
    assert (run.gathered_context or {}).get("nom") == "Lemaire", run.gathered_context


@pytest.mark.asyncio
async def test_C8_au_clavier_une_valeur_jamais_dite_est_refusee(
    db_session, async_session, test_client_factory
):
    user, workflow = await _monter(db_session, async_session, FICHE)
    charge, _ = await _converser(
        test_client_factory,
        user,
        workflow,
        [_noter({"motif": "ramonage du poêle"}, "note_1"), MockLLMService.create_text_chunks("D'accord.")],
        "je voudrais un entretien",
    )
    fiche = charge["checkpoint"]["gathered_context"]
    assert not fiche.get("motif"), fiche
    assert any(
        e.get("champ") == "motif" and e.get("statut") == "refuse" for e in fiche.get("fiche_journal") or []
    ), fiche.get("fiche_journal")


@pytest.mark.asyncio
async def test_C8_interrupteur_eteint_rien_ne_change(
    db_session, async_session, test_client_factory
):
    user, workflow = await _monter(
        db_session, async_session, {**FICHE, "fiche_au_fil_de_leau": False}
    )
    charge, _ = await _converser(
        test_client_factory,
        user,
        workflow,
        [_noter({"nom": "Lemaire"}, "note_1"), MockLLMService.create_text_chunks("Merci.")],
        "je m'appelle Lemaire",
    )
    fiche = charge["checkpoint"]["gathered_context"]
    assert "nom" not in fiche and "fiche_journal" not in fiche, fiche


@pytest.mark.asyncio
async def test_C8_conversation_fermee_la_passe_de_fin_remplit_un_champ_vide(
    db_session, async_session, test_client_factory
):
    user, workflow = await _monter(db_session, async_session, FICHE)
    demandes = []

    async def extraction(_gestionnaire, variables, _contexte_parent, consigne, *a, **k):
        demandes.append(sorted(v.name for v in variables))
        return {"nom": "Lemaire"}

    with patch(
        "api.services.workflow.pipecat_engine_variable_extractor."
        "VariableExtractionManager._perform_extraction",
        new=extraction,
    ):
        charge, run_id = await _converser(
            test_client_factory,
            user,
            workflow,
            [MockLLMService.create_text_chunks("Très bien, et votre nom ?")],
            "c'est Lemaire pour un entretien",
            finir=True,
        )
    # La passe ne demande que les champs de la fiche restés vides.
    assert demandes == [["motif", "nom"]], demandes
    assert charge["gathered_context"].get("nom") == "Lemaire", charge["gathered_context"]
    run = await db_session.get_workflow_run_by_id(run_id)
    contexte = run.gathered_context or {}
    assert contexte.get("nom") == "Lemaire", contexte
    assert any(
        e.get("champ") == "nom" and e.get("source") == "balayage"
        for e in contexte.get("fiche_journal") or []
    ), contexte.get("fiche_journal")

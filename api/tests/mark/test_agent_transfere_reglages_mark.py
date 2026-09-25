"""[.mark] Un agent reçu par TRANSFERT est construit comme le premier agent.

Remise à niveau sur l'amont `4e6cb22b`, plan
`Labo-agent-vocal/plans/remise-a-niveau-amont-4e6cb22b/` (étape 3, relecture).

Pourquoi ce fichier existe
--------------------------
Depuis le découpage par agent de l'amont (`fc76383c`), un agent reçu par
transfert est construit par ``AgentRuntimeFactory.build``, qui appelait les
fabriques de voix et de modèle SANS nos arguments : l'agent aurait parlé sans
nos réglages de voix (nombres en mots, appels de fonction retirés), sans les
prononciations du lexique, sans sa clé de cache Mistral et sans le filtre du
nom. Tout cela en silence (R1) : le transfert marche, la voix parle.

La prochaine fusion de l'amont qui réécrit ``build`` fera rougir ce fichier.

| Test | La garantie |
|---|---|
| arguments | ``run_configs`` et le lexique arrivent à la voix, la clé de cache au modèle |
| filtre | l'agent porte SON filtre du nom, et ``attach`` le pose avant sa voix |
| estampille | l'appel dit avec quelle voix et quelle clé l'agent transféré a parlé |
"""

import copy
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from api.schemas.ai_model_configuration import EffectiveAIModelConfiguration
from api.services.pipecat import agent_runtime_factory as fabrique_agents
from api.services.pipecat.agent_runtime_factory import AgentRuntimeFactory
from api.services.pipecat.filtre_nom_civilite import FiltreNomCiviliteProcessor
from api.services.pipecat.service_factory import cle_de_cache
from api.tests.integrations._run_pipeline_helpers import USER_CONFIGURATION
from api.tests.mark.test_traversants_appel import DEFINITION

WORKFLOW_ID = 4242
LEXIQUE = object()  # identité suffit : il doit arriver tel quel à la voix
REGLAGES = {
    "interdire_nom_appelant": True,
    "tts_text_aggregation_mode": "sentence",
    "voice_numbers_as_words": True,
}


def _fabrique(variables=None):
    return AgentRuntimeFactory(
        organization_id=1,
        workflow_run_id=1,
        call_worker=SimpleNamespace(name="call-1", add_workers=AsyncMock()),
        audio_config=None,
        callbacks_factory=lambda visit_id: SimpleNamespace(
            generation_started=None, llm_text_frame=None
        ),
        lexique_metier=LEXIQUE,
        variables_appel=variables or (lambda: {"nom": "Dupont"}),
    )


def _configuration(**llm):
    modeles = copy.deepcopy(USER_CONFIGURATION)
    modeles["llm"].update(llm)
    return EffectiveAIModelConfiguration.model_validate(modeles)


async def _construire(fabrique, capture, configuration=None):
    configuration = configuration or _configuration()
    workflow = SimpleNamespace(id=WORKFLOW_ID, name="Destination")
    definition = SimpleNamespace(
        id=7,
        workflow_json=DEFINITION,
        workflow_configurations=REGLAGES,
        version_number=1,
        status="published",
    )

    def voix(*args, **kwargs):
        capture["voix"] = kwargs
        return SimpleNamespace(nom="voix")

    def modele(*args, **kwargs):
        capture.setdefault("modeles", []).append(kwargs)
        return SimpleNamespace(nom="modele")

    with (
        patch.object(
            fabrique, "resolve_destination", AsyncMock(return_value=(workflow, definition))
        ),
        patch(
            "api.services.configuration.ai_model_configuration."
            "get_effective_ai_model_configuration_for_workflow",
            AsyncMock(return_value=configuration),
        ),
        patch.object(fabrique_agents, "create_tts_service", voix),
        patch.object(fabrique_agents, "create_llm_service", modele),
        patch.object(fabrique, "attach", AsyncMock()),
    ):
        return await fabrique.build(workflow_id=WORKFLOW_ID)


@pytest.mark.asyncio
async def test_la_voix_et_le_modele_d_un_agent_transfere_recoivent_nos_arguments():
    capture: dict = {}
    agent = await _construire(_fabrique(), capture)

    assert capture["voix"]["run_configs"] is REGLAGES, "réglages de voix perdus"
    assert capture["voix"]["lexique"] is LEXIQUE, "prononciations du lexique perdues"
    conversation = capture["modeles"][0]
    assert conversation["prompt_cache_key"] == cle_de_cache(WORKFLOW_ID)
    assert agent.llm.nom == "modele" and agent.tts.nom == "voix"


@pytest.mark.asyncio
async def test_l_agent_transfere_porte_son_filtre_et_attach_le_pose_avant_sa_voix():
    capture: dict = {}
    agent = await _construire(_fabrique(), capture)
    assert isinstance(agent.filtre_nom_civilite, FiltreNomCiviliteProcessor)

    # Éteint sur l'agent de destination : aucun filtre.
    capture_eteint: dict = {}
    with patch.dict(REGLAGES, {"interdire_nom_appelant": False}):
        eteint = await _construire(_fabrique(), capture_eteint)
    assert eteint.filtre_nom_civilite is None

    # `attach` transmet le filtre au montage du sous-circuit de l'agent.
    monte: dict = {}

    def montage(*args, **kwargs):
        monte.update(kwargs)
        return SimpleNamespace()

    fabrique = _fabrique()
    with (
        patch.object(fabrique_agents, "build_agent_generation_pipeline", montage),
        patch.object(
            fabrique_agents,
            "create_agent_worker",
            lambda *a, **k: SimpleNamespace(event_handler=lambda nom: (lambda f: f)),
        ),
    ):
        await fabrique.attach(agent)
    assert monte["filtre_nom_civilite"] is agent.filtre_nom_civilite


@pytest.mark.asyncio
async def test_l_appel_dit_avec_quelle_voix_et_quelle_cle_l_agent_transfere_a_parle():
    mistral = _configuration(provider="mistral", model="mistral-large-2512")
    estampille = (await _construire(_fabrique(), {}, mistral)).runtime_configuration
    assert estampille["llm_prompt_cache_key"] == cle_de_cache(WORKFLOW_ID)
    # La voix : la même estampille que le premier agent (`stamp_voice_settings`).
    assert estampille.get("tts_settings"), "voix de l'agent transféré non estampillée"

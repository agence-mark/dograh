"""[.mark] passages-fiables, lots C2 (relecture des numéros des nouveaux agents) et E (laisser la parole).

| Test | Ce qu'il prouve |
|---|---|
| C2 | un agent créé (définition ou gabarit) a la relecture des numéros allumée ; la valeur lue par défaut reste éteinte |
| E sans outil | aucun outil offert au modèle, case allumée ou non (décision d'Evan du 29/10 : la demande de temps est reconnue par l'arbitre, `test_passages_fiables_avant_la_reponse.py`) |
| E attente | délai de la phrase douce (45 s), phrase douce au lieu de la relance, jamais de raccrochage, parole = attente levée |
| E clavier | pas de silence au clavier : écart écrit dans le test de parité |
"""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.tests import MockLLMService

from api.routes.workflow import router
from api.schemas.workflow_configurations import WorkflowConfigurationDefaults
from api.services.auth.depends import get_user
from api.services.groupe.reglages import CONFIGURATION_DE_CREATION
from api.services.phrases.catalogue import ATTENTE_ACCORDEE, MOTIFS
from api.services.pipecat.call_monitor_processor import CallMonitorProcessor
from api.services.workflow.laisser_la_parole import CLE_TRACE as TRACE_PAROLE

NOM_DE_L_ANCIEN_OUTIL = "laisser_la_parole"
from api.services.workflow.pipecat_engine import PipecatEngine
from api.services.workflow.pipecat_engine_callbacks import delai_de_la_relance, handle_user_idle
from api.tests.mark.test_relance_par_la_voix import _Agregateur, _Moteur as _MoteurSilence


# --------------------------------------------------------------------------- #
# C2 : la relecture des numéros allumée à la création
# --------------------------------------------------------------------------- #


def _app():
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_user] = lambda: SimpleNamespace(id=1, provider_id="p", selected_organization_id=11)
    return app


def _faux_client():
    from datetime import UTC, datetime

    creation = AsyncMock(
        return_value=SimpleNamespace(
            id=5, name="n", status="active", created_at=datetime.now(UTC), current_definition_id=1,
            template_context_variables={}, call_disposition_codes={}, workflow_configurations=dict(CONFIGURATION_DE_CREATION),
        )
    )
    return SimpleNamespace(
        create_workflow=creation,
        assert_trigger_paths_available=AsyncMock(),
        sync_triggers_for_workflow=AsyncMock(),
    )


def test_c2_un_agent_cree_par_la_definition_a_la_relecture_allumee():
    client = _faux_client()
    with patch("api.routes.workflow.db_client", client), patch(
        "api.routes.workflow.validate_workflow_tool_name_collisions", AsyncMock(return_value=[])
    ):
        reponse = TestClient(_app()).post(
            "/workflow/create/definition", json={"name": "Neuf", "workflow_definition": {"nodes": [], "edges": []}}
        )
    assert reponse.status_code == 200, reponse.text
    assert client.create_workflow.await_args.kwargs["workflow_configurations"] == {"relecture_des_numeros": True}


def test_c2_un_agent_cree_par_le_gabarit_a_la_relecture_allumee():
    # builder-agent-vocal, lot 1 : la création ne passe plus par le service hébergé ; le squelette est créé par
    # ``api.services.builder.creation``, qui écrit la même configuration de création.
    client = _faux_client()
    with patch("api.services.builder.creation.db_client", client), patch(
        "api.services.builder.creation.contexte.ecrire_notes", AsyncMock()
    ):
        reponse = TestClient(_app()).post(
            "/workflow/create/template", json={"call_type": "inbound", "use_case": "x", "activity_description": "y"}
        )
    assert reponse.status_code == 200, reponse.text
    assert client.create_workflow.await_args.kwargs["workflow_configurations"] == {"relecture_des_numeros": True}


def test_c2_la_valeur_lue_par_defaut_reste_eteinte_donc_aucun_agent_existant_ne_change():
    from api.services.pipecat.filtre_nom_civilite import creer_filtre_nom_civilite

    assert WorkflowConfigurationDefaults().relecture_des_numeros is False
    # un agent d'avant n'a pas la clé : le filtre de relecture n'est pas armé ; un agent neuf (clé écrite) l'est
    assert creer_filtre_nom_civilite({}, lambda: {}) is None
    assert creer_filtre_nom_civilite(dict(CONFIGURATION_DE_CREATION), lambda: {}) is not None


async def test_c2_la_base_ecrit_la_configuration_de_creation(db_session):
    """La configuration écrite à la création arrive dans l'agent ET dans sa première définition."""
    from api.db import db_client  # noqa: F401  (le fixture db_session est le même client)

    cree = await db_session.create_workflow(
        name="Création C2", workflow_definition={"nodes": [], "edges": []}, user_id=None,
        workflow_configurations=CONFIGURATION_DE_CREATION,
    )
    assert cree.workflow_configurations == {"relecture_des_numeros": True}
    ancien = await db_session.create_workflow(name="Ancien C2", workflow_definition={"nodes": [], "edges": []}, user_id=None)
    assert "relecture_des_numeros" not in (ancien.workflow_configurations or {})


# --------------------------------------------------------------------------- #
# E : laisser la parole
# --------------------------------------------------------------------------- #


def _moniteur(**reglages):
    moniteur = CallMonitorProcessor(
        response_source=lambda: None, on_response_timeout=lambda _s: None, on_user_idle=None,
        conversation_enabled=lambda: True,
    )
    moniteur.user_idle_timeout = 10.0
    moniteur.user_aggregator = SimpleNamespace(user_turn_controller=SimpleNamespace(has_active_user_turn=False))
    moniteur._active = True
    moniteur._waiting_for_user = True
    for nom, valeur in reglages.items():
        setattr(moniteur, nom, valeur)
    return moniteur


def test_e_la_case_est_eteinte_par_defaut():
    assert WorkflowConfigurationDefaults().laisser_la_parole is False


async def test_e_le_delai_de_l_attente_est_celui_de_la_phrase_douce_45_s_par_defaut():
    moteur = _MoteurSilence()
    assert MOTIFS[ATTENTE_ACCORDEE].delai_defaut_s == 45.0
    assert delai_de_la_relance(moteur) is None  # pas d'attente : le délai de Rythme
    moteur.call_monitor.attente_accordee = True
    assert delai_de_la_relance(moteur) == 45.0
    moteur.active_agent.reglages = {
        "phrases_regles": [{"motif": ATTENTE_ACCORDEE, "portee": "agent", "variantes": ["Je reste là."], "delai_s": 20, "active": True}]
    }
    assert delai_de_la_relance(moteur) == 20


async def test_e_pas_de_relance_avant_le_delai_le_moniteur_arme_le_delai_de_l_attente():
    moniteur = _moniteur(delai_de_relance=lambda: 45.0 if moniteur.attente_accordee else None)
    moniteur._arm_idle()
    loop = asyncio.get_running_loop()
    assert 9 < moniteur._deadline.when() - loop.time() <= 10
    moniteur.accorder_l_attente()  # re-arme avec le délai de l'attente
    assert moniteur._deadline_kind == "idle" and 44 < moniteur._deadline.when() - loop.time() <= 45
    moniteur._cancel_deadline()


class _MoteurAttente(_MoteurSilence):
    def __init__(self, **kw):
        super().__init__(**kw)
        self.call_monitor = _moniteur()
        self.call_monitor.attente_accordee = True


async def test_e_au_delai_la_phrase_douce_remplace_la_relance_et_il_n_y_a_jamais_de_raccrochage():
    moteur = _MoteurAttente(relances={"user_idle_max_prompts": 0})  # sans attente, la première relance raccrocherait
    agregateur = _Agregateur()
    await handle_user_idle(moteur, agregateur, 1)
    await moteur.phrases.attendre_la_fin()
    assert moteur.dites == ["Prenez votre temps, je suis toujours là."]
    assert agregateur.consignes == [] and moteur.raccroche is None
    assert moteur.call_monitor.attente_accordee is False  # puis le comportement normal reprend
    assert [t["evenement"] for t in moteur._gathered_context[TRACE_PAROLE]] == ["relance_douce_dite"]
    moteur.call_monitor._cancel_deadline()


async def test_e_la_phrase_douce_est_modifiable_a_l_ecran_et_eteinte_elle_se_tait_sans_raccrocher():
    moteur = _MoteurAttente()
    moteur.active_agent.reglages = {
        "phrases_regles": [{"motif": ATTENTE_ACCORDEE, "portee": "agent", "variantes": ["Je reste là."], "active": True}]
    }
    await handle_user_idle(moteur, _Agregateur(), 1)
    await moteur.phrases.attendre_la_fin()
    assert moteur.dites == ["Je reste là."]
    muet = _MoteurAttente()
    muet.active_agent.reglages = {
        "phrases_regles": [{"motif": ATTENTE_ACCORDEE, "portee": "agent", "variantes": ["x"], "active": False}]
    }
    agregateur = _Agregateur()
    await handle_user_idle(muet, agregateur, 1)
    assert muet.dites == [] and agregateur.consignes == [] and muet.raccroche is None
    assert muet.call_monitor.attente_accordee is False


async def test_e_la_personne_qui_reparle_leve_l_attente():
    moniteur = _moniteur()
    leves = []
    moniteur.sur_attente_levee = lambda: leves.append(True)
    moniteur.accorder_l_attente()
    assert moniteur.attente_accordee is True
    moniteur._user_started()
    assert moniteur.attente_accordee is False and leves == [True]
    moniteur._cancel_deadline()


async def test_e_sans_attente_la_relance_normale_et_le_raccrochage_sont_inchanges():
    moteur = _MoteurSilence(relances={"user_idle_max_prompts": 0})
    moteur.call_monitor = _moniteur()
    await handle_user_idle(moteur, _Agregateur(), 1)
    assert moteur.raccroche is not None  # sans l'attente : le comportement d'avant


async def test_e_un_vrai_moteur_n_offre_jamais_l_outil(three_node_workflow, no_disposition_mapping):
    """Plus aucun outil offert au modèle (téléphone et clavier : même `set_node`), case allumée ou non."""

    async def outils(reglages):
        moteur = PipecatEngine(
            llm=MockLLMService(), context=LLMContext(), workflow=three_node_workflow, call_context_vars={}, workflow_run_id=1
        )
        moteur.active_agent.reglages = reglages
        vus: list[list[str]] = []
        origine = moteur._update_llm_context

        async def espion(prompt, fonctions):
            vus.append([f.name for f in fonctions])
            return await origine(prompt, fonctions)

        moteur._update_llm_context = espion
        await moteur.set_node(moteur.active_agent.workflow.start_node_id)
        return vus[-1]

    assert NOM_DE_L_ANCIEN_OUTIL not in await outils({"laisser_la_parole": True})
    assert NOM_DE_L_ANCIEN_OUTIL not in await outils({})

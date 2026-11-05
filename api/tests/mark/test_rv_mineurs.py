"""[.mark] Partie 3, revue RV, points mineurs 4, 5, 6, 7 et 11 (le 10 est dans les tests des trois scripts de reprise).

| Test | Ce qu'il prouve |
|---|---|
| 4 : objet d'organisation | hors « Tout permettre », créer un agent, créer ou modifier un outil demande une carte, même sur « Tout permettre sur cet agent » ; « Tout permettre » les laisse passer |
| 5 : porte MCP | la famille « dépense » est refusée à Claude Code (``porte_mcp``) |
| 6 : auteur du chat | le mode d'un chat, ses cartes d'autorisation et l'accord de dépense sont refusés (403) à un autre compte de l'organisation |
| 7 : import | un identifiant d'outil d'une autre organisation n'est jamais gardé à l'import d'un agent en fichiers |
| 11 : R1 | les symboles privés de Pipecat dont la voix Gradium et la passation par le code dépendent existent ; la veille de session journalise en ``error`` |
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
import yaml
from pipecat.services.gradium.tts import GradiumTTSService

from api.services.builder import modes
from api.services.builder.actions import registre
from api.services.builder.actions.registre import PORTE_MCP, Contexte
from api.services.equipe_mark.permissions import PERMISSIONS
from api.tests.mark.builder_commun import AGENT, monde, utilisateur  # noqa: F401
from api.tests.mark.equipe_commun import client_http, creer_compte, entetes, sans_preparation_des_organisations  # noqa: F401
from api.tests.mark.test_builder_c2 import B, decor, fil_de


def _chat(mode: str) -> Contexte:
    return Contexte(user=utilisateur(1), workflow_id=AGENT, conversation={"messages": [], "mode": mode}, permissions=frozenset(PERMISSIONS))


# --- 4 : un objet d'organisation n'est jamais « l'agent ouvert » -----------------------------------------------------------------------


@pytest.mark.parametrize("nom", ["create_workflow", "create_tool", "outil_modifier"])
async def test_un_objet_d_organisation_demande_une_carte_hors_de_tout_permettre(monde, nom):  # noqa: F811
    action = registre.REGISTRE[nom]
    for mode in ("demander", "agent"):
        decision = await modes.decider(action, {}, _chat(mode))
        assert decision is not None and decision["code"] == modes.CODE_DEMANDE, (nom, mode)
    assert await modes.decider(action, {}, _chat("tout")) is None


async def test_modifier_le_brouillon_de_l_agent_ouvert_passe_toujours_sans_carte(monde):  # noqa: F811
    assert await modes.decider(registre.REGISTRE["brouillon_enregistrer"], {}, _chat("demander")) is None
    assert await modes.decider(registre.REGISTRE["reglages_regler"], {}, _chat("agent")) is None


# --- 5 : la porte MCP n'a pas la dépense -------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("nom", ["tests_rejouer", "attaques_lancer", "attaques_rejouer"])
async def test_la_porte_mcp_n_a_pas_les_rejeux_qui_depensent(monde, nom):  # noqa: F811
    contexte = Contexte(user=utilisateur(1), workflow_id=AGENT, porte=PORTE_MCP)
    decision = await modes.decider(registre.REGISTRE[nom], {}, contexte)
    assert decision is not None and decision["code"] == "porte_mcp"


@pytest.mark.parametrize("nom", ["test_demarrer", "test_tour", "test_finir"])
async def test_la_porte_mcp_garde_l_appelant_simule_joue_par_claude_code(monde, nom):  # noqa: F811
    contexte = Contexte(user=utilisateur(1), workflow_id=AGENT, porte=PORTE_MCP)
    assert await modes.decider(registre.REGISTRE[nom], {}, contexte) is None


# --- 6 : le chat est à son auteur ------------------------------------------------------------------------------------------------------


async def test_le_mode_et_les_cartes_d_un_chat_sont_a_son_auteur(db_session, sans_preparation_des_organisations):  # noqa: F811
    org, auteur, jeton, agent = await decor(db_session, "rv6")
    _, autre_jeton = await creer_compte(db_session, "rv6-autre@example.test", role="Administrateur", organisations=[org])
    fil = await fil_de(org, auteur, agent)
    async with client_http() as c:
        autre = await c.put(f"{B}/fils/{fil.id}/mode", json={"mode": "tout"}, headers=entetes(autre_jeton, org))
        carte = await c.post(f"{B}/fils/{fil.id}/autorisations/a1", json={"decision": "une_fois"}, headers=entetes(autre_jeton, org))
        retrait = await c.delete(f"{B}/fils/{fil.id}/autorisations/a1", headers=entetes(autre_jeton, org))
        depense = await c.post(f"{B}/fils/{fil.id}/depenses/d1", json={"accord": True}, headers=entetes(autre_jeton, org))
        moi = await c.put(f"{B}/fils/{fil.id}/mode", json={"mode": "agent"}, headers=entetes(jeton, org))
    assert [r.status_code for r in (autre, carte, retrait, depense)] == [403, 403, 403, 403]
    assert moi.status_code == 200 and moi.json()["mode"] == "agent"


# --- 7 : l'import ne garde pas l'outil d'une autre organisation -------------------------------------------------------------------


async def _rendre(valeur):
    return valeur


async def test_l_import_ne_garde_jamais_l_identifiant_d_un_outil_d_une_autre_organisation(monkeypatch):
    from api.services.export_agent import fichiers

    ici = SimpleNamespace(tool_uuid="outil-d-ici", name="Rendez-vous")
    monkeypatch.setattr(fichiers.db_client, "get_tools_for_organization", lambda organisation: _rendre([ici]))
    monkeypatch.setattr(fichiers, "lire_agent", lambda *_a, **_k: _rendre(None))
    graphe = {
        "nodes": [{"id": "1", "type": "agentNode", "data": {"name": "A", "prompt": "x", "tool_uuids": ["outil-d-ici", "outil-d-un-autre-client"]}}],
        "edges": [],
    }
    plan = await fichiers.construire_le_plan(
        7,
        1,
        {
            "agent.yaml": yaml.safe_dump({"format": fichiers.FORMAT, "version": fichiers.VERSION}),
            "graphe.yaml": yaml.safe_dump(graphe),
        },
    )
    assert plan.graphe["nodes"][0]["data"]["tool_uuids"] == ["outil-d-ici"]
    assert any(a["code"] == "outil_absent" for a in plan.avertissements)


# --- 11 : R1, les symboles de Pipecat dont nous dépendons ----------------------------------------------------------------------


SYMBOLES_PRIVES_DU_SERVICE = ("_setup_context_ids", "_init_sample_rate", "_resampler", "_websocket")
METHODES_PRIVEES_DU_SERVICE = ("_build_setup_msg", "_connect_websocket", "_disconnect_websocket", "_connect", "_disconnect")


def _manquants(service, attributs, methodes) -> list[str]:
    return [n for n in attributs if not hasattr(service, n)] + [n for n in methodes if not callable(getattr(type(service), n, None))]


def _service_amont():
    return GradiumTTSService(api_key="cle-de-test-sans-valeur")


def test_r1_les_symboles_de_pipecat_dont_depend_la_voix_gradium_existent():
    """``pipecat/gradium_voix.py`` lit ou surcharge ces noms privés : si Pipecat en renomme un, ce test devient rouge au lieu de laisser la
    réouverture de session s'éteindre en silence (R1)."""
    manquants = _manquants(_service_amont(), SYMBOLES_PRIVES_DU_SERVICE, METHODES_PRIVEES_DU_SERVICE)
    assert not manquants, f"Pipecat n'a plus : {manquants}"


def test_r1_le_test_mord_quand_un_symbole_disparait(monkeypatch):
    monkeypatch.delattr(GradiumTTSService, "_build_setup_msg")
    assert _manquants(_service_amont(), SYMBOLES_PRIVES_DU_SERVICE, METHODES_PRIVEES_DU_SERVICE) == ["_build_setup_msg"]


def test_r1_la_passation_par_le_code_existe_toujours():
    from api.services.workflow.pipecat_engine_custom_tools import CustomToolManager

    assert callable(getattr(CustomToolManager, "_create_transfer_agent_handler", None)), "la passation par le code ne trouverait plus son gestionnaire"


async def test_r1_la_veille_de_session_journalise_en_error_pas_en_silence(monkeypatch):
    from loguru import logger

    from api.services.pipecat.gradium_voix import MarkGradiumTTSService

    vus: list[tuple[str, str]] = []
    identifiant = logger.add(lambda m: vus.append((m.record["level"].name, m.record["message"])), level="DEBUG")

    async def casse(self, sauf_contexte=None):
        raise AttributeError("_setup_context_ids")

    monkeypatch.setattr(MarkGradiumTTSService, "rouvrir_si_necessaire", casse)
    monkeypatch.setattr(MarkGradiumTTSService, "INTERVALLE_VEILLE_S", 0.01)
    monkeypatch.setattr(MarkGradiumTTSService, "__str__", lambda self: "voix")
    service = MarkGradiumTTSService.__new__(MarkGradiumTTSService)  # la veille ne lit que l'intervalle et rouvrir_si_necessaire
    tache = asyncio.create_task(service._veille_de_session())
    try:
        await asyncio.sleep(0.1)
    finally:
        tache.cancel()
        logger.remove(identifiant)
    assert any(niveau == "ERROR" and "veille de session Gradium" in message for niveau, message in vus), vus

"""[.mark] Le transfert garanti à l'arrivée (chantier greffier-conversation, lot E).

Plan `Labo-agent-vocal/plans/greffier-conversation/`, lot E (C4, D6 du 13/10) : case par agent,
éteinte par défaut. À l'arrivée dans une étape qui porte un outil de transfert d'appel, magasin
``OUVERT``, c'est le CODE qui lance le transfert une fois la première réplique de l'étape dite
(runs 1118, 1120 à 1122 : Qwen ne l'appelait qu'une fois sur six).

| Test | Ce qu'il prouve |
|---|---|
| réglage | éteint par défaut, lu seulement à ``True``, estampillé seulement joué |
| conditions | case, magasin OUVERT, étape d'arrivée avec outils, pas une fin |
| porte écrite | la réplique d'arrivée jouée, le code appelle l'outil ; le modèle ne reparle pas pour ça |
| porte en fonction | la réponse qui suit le résultat est attendue, puis l'outil est appelé |
| gardes | pas de double transfert si le modèle l'a appelé ; rien si la personne a parlé, si l'étape a changé, magasin FERMÉ ou case éteinte |
| clavier (R1) | par les vraies routes : la porte en fonction, la réplique, puis le renvoi simulé (boutons) lancé par le code, et la trace « lance » |
"""

import asyncio
import uuid
from unittest.mock import AsyncMock, patch

import pytest

from api.services.pipecat.speech_playback import PlaybackOutcome
from api.services.workflow.fiche_au_fil_de_leau import (
    CLE_TRANSFERT_GARANTI,
    ReglagesFiche,
    estampiller_le_mode,
)
from api.services.workflow.pipecat_engine import (
    CLE_ETAT_OUVERTURE,
    TRACE_TRANSFERTS_GARANTIS,
    PipecatEngine,
)
from api.tests.mark.test_clavier_porte_la_fiche import FICHE, _monter
from api.tests.mark.test_fiche_montree import _contexte, _mistral
from api.tests.mark.test_outil_noter import CONFIG_ALLUMEE
from api.tests.mark.test_porte_parlee_consigne import _graphe
from api.tests.mark.test_porte_parlee_premiere_replique import (
    _definition_a_trois_etapes,
    _noeud,
)
from pipecat.tests import MockLLMService

ALLUME = {**CONFIG_ALLUMEE, CLE_TRANSFERT_GARANTI: True}
OUTIL = "transfer_team"


def test_le_reglage_est_eteint_par_defaut_et_estampille_seulement_joue():
    from api.schemas.workflow_configurations import WorkflowConfigurationDefaults

    assert WorkflowConfigurationDefaults().transfert_garanti is False
    assert ReglagesFiche.depuis(CONFIG_ALLUMEE).transfert_garanti is False
    assert (
        ReglagesFiche.depuis(
            {**CONFIG_ALLUMEE, CLE_TRANSFERT_GARANTI: "oui"}
        ).transfert_garanti
        is False
    )
    assert ReglagesFiche.depuis(ALLUME).transfert_garanti is True
    assert CLE_TRANSFERT_GARANTI not in estampiller_le_mode(
        {}, ReglagesFiche.depuis(CONFIG_ALLUMEE)
    )
    assert (
        estampiller_le_mode({}, ReglagesFiche.depuis(ALLUME))[CLE_TRANSFERT_GARANTI]
        is True
    )


def test_la_cle_de_l_etat_d_ouverture_est_celle_du_module():
    from api.services.pipecat.etat_ouverture import CLE_ETAT

    assert CLE_ETAT_OUVERTURE == CLE_ETAT


# --------------------------------------------------------------------------- #
# Le moteur
# --------------------------------------------------------------------------- #


def _definition() -> dict:
    definition = _definition_a_trois_etapes()
    _noeud(definition, "etape")["data"]["tool_uuids"] = ["outil-de-transfert"]
    return definition


async def _moteur(config=ALLUME, etat="OUVERT", etape="start"):
    graphe = _graphe(_definition())
    engine = PipecatEngine(
        llm=_mistral(),
        context=_contexte(),
        workflow=graphe,
        call_context_vars={CLE_ETAT_OUVERTURE: etat},
        workflow_run_id=1,
        fiche=ReglagesFiche.depuis(config),
    )
    agent = engine.active_agent
    await engine._prepare_node(agent, graphe.nodes[etape], apply_settings=False)
    agent.current_node = graphe.nodes[etape]
    engine.queue_text_message = AsyncMock(return_value=True)
    engine.end_call_with_reason = AsyncMock()
    engine._outil_de_transfert = AsyncMock(return_value=OUTIL)
    agent.queue_frame = AsyncMock()
    agent.llm.run_function_calls = AsyncMock()
    # L'étape d'arrivée enregistre ses outils dans la base : hors sujet ici.
    engine._prepare_node = _sans_outils(engine._prepare_node)
    return engine


def _sans_outils(preparer):
    async def preparer_sans_base(agent, node, **kw):
        with patch.object(type(node), "tool_uuids", new=[], create=True):
            return await preparer(agent, node, **kw)

    return preparer_sans_base


def _appels(engine) -> list[str]:
    return [
        appel.args[0][0].function_name
        for appel in engine.active_agent.llm.run_function_calls.await_args_list
    ]


def _etats(engine) -> list[str]:
    return [
        t["etat"] for t in engine._gathered_context.get(TRACE_TRANSFERTS_GARANTIS) or []
    ]


@pytest.mark.asyncio
async def test_conditions():
    engine = await _moteur()
    agent = engine.active_agent
    assert engine._transfert_garanti_s_applique(agent, "etape")
    assert not engine._transfert_garanti_s_applique(agent, "end")  # une fin
    assert not engine._transfert_garanti_s_applique(agent, "start")  # aucun outil
    assert not (await _moteur(etat="FERME"))._transfert_garanti_s_applique(
        agent, "etape"
    )
    eteint = await _moteur(config=CONFIG_ALLUMEE)
    assert not eteint._transfert_garanti_s_applique(eteint.active_agent, "etape")


async def _porte_ecrite(engine, reponse="reponse-arrivee"):
    assert await engine.prendre_porte_ecrite("vers_etape", reponse=reponse) == "prise"
    assert engine.active_agent.current_node.id == "etape"
    await asyncio.sleep(0.05)
    assert _appels(engine) == []  # la réplique n'est pas encore jouée
    return reponse


@pytest.mark.asyncio
async def test_porte_ecrite_la_replique_jouee_le_code_appelle_l_outil():
    engine = await _moteur()
    reponse = await _porte_ecrite(engine)
    engine.speech_playback.pending[reponse].finish(PlaybackOutcome.PLAYED)
    await asyncio.sleep(0.05)
    assert _appels(engine) == [OUTIL]
    assert _etats(engine) == ["lance"]
    # Le modèle ne reparle pas pour appeler l'outil (c'est le code qui le fait).
    engine.active_agent.queue_frame.assert_not_awaited()


@pytest.mark.asyncio
async def test_pas_de_double_transfert_si_le_modele_l_a_appele():
    engine = await _moteur()
    reponse = await _porte_ecrite(engine)
    engine.context.add_message(
        {
            "role": "assistant",
            "tool_calls": [
                {
                    "id": "x",
                    "type": "function",
                    "function": {"name": OUTIL, "arguments": "{}"},
                }
            ],
        }
    )
    engine.speech_playback.pending[reponse].finish(PlaybackOutcome.PLAYED)
    await asyncio.sleep(0.05)
    assert _appels(engine) == []
    assert _etats(engine) == ["par_le_modele"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "issue",
    [PlaybackOutcome.INTERRUPTED, PlaybackOutcome.TIMED_OUT, PlaybackOutcome.FAILED],
)
async def test_rien_si_la_replique_n_a_pas_ete_jouee_jusqu_au_bout(issue):
    """Revue du 13/10 : la personne coupe la réplique d'arrivée ; sa parole n'est pas encore
    dans la conversation (elle n'y entre qu'à sa fin de tour). Le transfert ne part pas."""
    engine = await _moteur()
    reponse = await _porte_ecrite(engine)
    engine.speech_playback.pending[reponse].finish(issue)
    await asyncio.sleep(0.05)
    assert _appels(engine) == []
    assert _etats(engine) == ["replique_non_jouee"]


@pytest.mark.asyncio
async def test_rien_si_la_personne_a_parle_entre_temps():
    engine = await _moteur()
    reponse = await _porte_ecrite(engine)
    engine.context.add_message({"role": "user", "content": "attendez, une question"})
    engine.speech_playback.pending[reponse].finish(PlaybackOutcome.PLAYED)
    await asyncio.sleep(0.05)
    assert _appels(engine) == []
    assert _etats(engine) == ["personne_a_parle"]


@pytest.mark.asyncio
async def test_pas_de_double_transfert_si_le_modele_l_appelle_avant_que_la_conversation_le_dise():
    """Revue du 13/10 : l'appel du modèle est relevé à l'instant où il est fait
    (``on_function_calls_started``), avant d'entrer dans la conversation."""
    engine = await _moteur()
    reponse = await _porte_ecrite(engine)
    from types import SimpleNamespace

    await engine.active_agent.llm._call_event_handler(
        "on_function_calls_started", [SimpleNamespace(function_name=OUTIL)]
    )
    await asyncio.sleep(0.02)
    engine.speech_playback.pending[reponse].finish(PlaybackOutcome.PLAYED)
    await asyncio.sleep(0.05)
    assert _appels(engine) == []
    assert _etats(engine) == ["par_le_modele"]


@pytest.mark.asyncio
async def test_sans_attente_possible_rien_ne_part():
    engine = await _moteur()
    engine._lancer_le_transfert_garanti(engine.active_agent, "etape", None)
    await asyncio.sleep(0.05)
    assert _appels(engine) == [] and _etats(engine) == ["sans_attente"]


@pytest.mark.asyncio
async def test_sans_outil_de_transfert_la_relance_d_avant_jamais_un_silence():
    """Revue du 13/10 : Post-scriptum « porte, note, phrase », l'étape porte une action qui
    n'est pas un transfert : le modèle reparle pour l'appeler, comme avant la case."""
    from api.services.workflow.fiche_au_fil_de_leau import (
        CLE_MODE,
        CLE_ORDRE_DE_LA_REPONSE,
    )

    engine = await _moteur(
        config={
            **ALLUME,
            CLE_MODE: "post_scriptum",
            CLE_ORDRE_DE_LA_REPONSE: "porte_note_phrase",
        }
    )
    engine._outil_de_transfert = AsyncMock(return_value=None)
    reponse = await _porte_ecrite(engine)
    engine.speech_playback.pending[reponse].finish(PlaybackOutcome.PLAYED)
    await asyncio.sleep(0.05)
    assert _appels(engine) == [] and _etats(engine) == ["sans_outil"]
    (appel,) = engine.active_agent.queue_frame.await_args_list
    from pipecat.frames.frames import LLMRunFrame

    assert isinstance(appel.args[0], LLMRunFrame)


@pytest.mark.asyncio
@pytest.mark.parametrize("config,etat", [(CONFIG_ALLUMEE, "OUVERT"), (ALLUME, "FERME")])
async def test_case_eteinte_ou_magasin_ferme_rien(config, etat):
    engine = await _moteur(config=config, etat=etat)
    await engine.prendre_porte_ecrite("vers_etape", reponse="r")
    await asyncio.sleep(0.05)
    assert "r" not in engine.speech_playback.pending
    assert _appels(engine) == [] and _etats(engine) == []


@pytest.mark.asyncio
async def test_porte_seule_la_reponse_suivante_est_attendue():
    engine = await _moteur()
    await engine.prendre_porte_ecrite("vers_etape", relancer=True)
    attendue = engine.speech_playback._expected_response
    assert attendue is not None  # posée avant de faire reparler le modèle
    attendue.finish(PlaybackOutcome.PLAYED)
    await asyncio.sleep(0.05)
    assert _appels(engine) == [OUTIL]


@pytest.mark.asyncio
async def test_porte_en_fonction_la_reponse_qui_suit_est_attendue():
    engine = await _moteur()
    agent = engine.active_agent
    fonction = await engine._create_transition_func("vers_etape", "etape", agent=agent)
    rappel = AsyncMock()
    from types import SimpleNamespace

    await fonction(
        SimpleNamespace(arguments={}, tool_call_id="t1", result_callback=rappel)
    )
    rappel.assert_awaited_once()
    attendue = engine.speech_playback._expected_response
    assert attendue is not None
    await asyncio.sleep(0.05)
    assert _appels(engine) == []
    attendue.finish(PlaybackOutcome.PLAYED)
    await asyncio.sleep(0.05)
    assert _appels(engine) == [OUTIL]


@pytest.mark.asyncio
async def test_rien_si_l_etape_a_change():
    engine = await _moteur()
    reponse = await _porte_ecrite(engine)
    engine.active_agent.current_node = engine.active_agent.workflow.nodes["start"]
    engine.speech_playback.pending[reponse].finish(PlaybackOutcome.PLAYED)
    await asyncio.sleep(0.05)
    assert _appels(engine) == [] and _etats(engine) == ["etape_quittee"]


# --------------------------------------------------------------------------- #
# Au clavier, par les vraies routes (R1)
# --------------------------------------------------------------------------- #


async def _agent(db_session, async_session):
    configurations = {**FICHE, CLE_TRANSFERT_GARANTI: True}
    user, workflow = await _monter(
        db_session, async_session, configurations, _definition()
    )
    outil = await db_session.create_tool(
        organization_id=workflow.organization_id,
        user_id=user.id,
        name="Transfer team",
        description="Transfer the caller to the team",
        category="transfer_call",
        definition={
            "schema_version": 1,
            "type": "transfer_call",
            "config": {"destination": "+33600000000", "timeout": 20},
        },
    )
    definition = _definition()
    _noeud(definition, "etape")["data"]["tool_uuids"] = [outil.tool_uuid]
    await db_session.save_workflow_draft(
        workflow.id,
        workflow_definition=definition,
        workflow_configurations=configurations,
    )
    await db_session.publish_workflow_draft(workflow.id)
    return user, workflow


@pytest.mark.asyncio
async def test_au_clavier_le_code_lance_le_renvoi_apres_la_replique(
    db_session, async_session, test_client_factory
):
    from api.services.pipecat import etat_ouverture
    from api.services.workflow import text_chat_runner

    user, workflow = await _agent(db_session, async_session)
    appel = uuid.uuid4().hex[:6]
    llm = [
        MockLLMService(mock_steps=[], chunk_delay=0.001),
        MockLLMService(
            mock_steps=[
                MockLLMService.create_function_call_chunks(
                    "vers_etape", {}, tool_call_id=f"p_{appel}"
                ),
                MockLLMService.create_text_chunks(
                    "Je vous mets en relation avec le magasin."
                ),
            ],
            chunk_delay=0.001,
        ),
        *[MockLLMService(mock_steps=[], chunk_delay=0.001) for _ in range(3)],
    ]
    vrai = etat_ouverture.injecter_etat_ouverture

    def ouvert(contexte, *a, **k):
        # Le magasin est OUVERT pour ce test, quel que soit le jour (fériés compris).
        return {**vrai(contexte, *a, **k), CLE_ETAT_OUVERTURE: "OUVERT"}

    vu_en_attente = False
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
            patch.object(
                text_chat_runner, "injecter_etat_ouverture", side_effect=ouvert
            ),
        ):
            creee = await client.post(
                f"/api/v1/workflow/{workflow.id}/text-chat/sessions", json={}
            )
            session = creee.json()
            run_id = session["workflow_run_id"]
            url = f"/api/v1/workflow/{workflow.id}/runs/{run_id}/renvoi-en-test"

            async def page():
                nonlocal vu_en_attente
                for _ in range(200):
                    etat = await client.get(url)
                    if etat.status_code == 200 and etat.json()["en_attente"]:
                        vu_en_attente = True
                        clic = await client.post(url, json={"accepte": True})
                        assert clic.status_code == 200, clic.text
                        return
                    await asyncio.sleep(0.1)

            tache = asyncio.create_task(page())
            reponse = await client.post(
                f"/api/v1/workflow/{workflow.id}/text-chat/sessions/{run_id}/messages",
                json={
                    "text": "mon poêle est en panne",
                    "expected_revision": session["revision"],
                },
            )
            await tache
    assert reponse.status_code == 200, reponse.text
    charge = reponse.json()
    assert vu_en_attente, "le renvoi n'a jamais été lancé"
    assert charge["is_completed"] is True, charge["session_data"]["turns"][-1]
    texte = repr(charge["session_data"]["turns"])
    assert "Je vous mets en relation avec le magasin." in texte
    run = await db_session.get_workflow_run_by_id(run_id)
    traces = (run.gathered_context or {}).get(TRACE_TRANSFERTS_GARANTIS) or []
    assert [t["etat"] for t in traces] == ["lance"], run.gathered_context


@pytest.mark.asyncio
async def test_une_reponse_suivie_apres_sa_sortie_compte_comme_jouee():
    """Essai du 13/10 (run 1139, clavier) : le texte de la réplique d'arrivée sort avant
    que le moteur la suive ; sa fin la donne jouée, pas muette (sinon pas de transfert)."""
    from pipecat.frames.frames import SpeechBoundaryFrame

    from api.services.pipecat.speech_playback import SpeechPlaybackTracker

    suivi = SpeechPlaybackTracker()
    suivi.after_output(None, SpeechBoundaryFrame("r1", beginning=True))
    suivi.note_output()
    phrase = suivi.suivre_une_reponse("r1")
    suivi.after_output(None, SpeechBoundaryFrame("r1", beginning=False))
    assert await phrase.wait() is True
    # Une réponse sans aucune sortie reste en échec.
    suivi.after_output(None, SpeechBoundaryFrame("r2", beginning=True))
    muette = suivi.suivre_une_reponse("r2")
    suivi.after_output(None, SpeechBoundaryFrame("r2", beginning=False))
    assert await muette.wait() is False
    assert muette.outcome is PlaybackOutcome.FAILED


# --------------------------------------------------------------------------- #
# [.mark] agents-specialises : à l'arrivée d'un agent appelé, la phrase de mise en relation est
# figée (réglage ``transfert_humain.phrase_mise_en_relation``), dite par le code, puis le
# transfert part sans aucun tour de modèle.
# --------------------------------------------------------------------------- #

PHRASE_FIGEE = "Phrase figée de mise en relation."
REGLAGE_PHRASE = {"transfert_humain": {"phrase_mise_en_relation": PHRASE_FIGEE}}


async def _moteur_fige(reglages=REGLAGE_PHRASE, etat="OUVERT", son_message=False):
    engine = await _moteur(config=CONFIG_ALLUMEE, etat=etat, etape="etape")
    engine.reglages_appel = dict(reglages)
    engine._outil_de_transfert_a_son_message = AsyncMock(return_value=son_message)
    return engine


@pytest.mark.asyncio
@pytest.mark.parametrize("etat", ["OUVERT", "SUR_RENDEZ_VOUS"])
async def test_fige_ouvert_la_phrase_du_reglage_est_rendue(etat):
    engine = await _moteur_fige(etat=etat)
    assert (
        await engine.transfert_fige_a_l_ouverture(engine.active_agent, "etape")
        == PHRASE_FIGEE
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "reglages,etat",
    [
        (REGLAGE_PHRASE, "FERME"),
        (REGLAGE_PHRASE, "PAUSE"),
        ({}, "OUVERT"),
        ({"transfert_humain": {"phrase_mise_en_relation": ""}}, "OUVERT"),
        ({"transfert_humain": {"phrase_mise_en_relation": "   "}}, "OUVERT"),
        ({"transfert_humain": "texte"}, "OUVERT"),
    ],
    ids=["ferme", "pause", "reglage absent", "reglage vide", "reglage blanc", "reglage illisible"],
)
async def test_fige_ferme_ou_reglage_vide_comportement_d_avant(reglages, etat):
    engine = await _moteur_fige(reglages=reglages, etat=etat)
    assert await engine.transfert_fige_a_l_ouverture(engine.active_agent, "etape") is None


@pytest.mark.asyncio
async def test_fige_sans_etat_d_ouverture_comme_la_regle_k3_l_outil_est_expose():
    """Même règle que K3 : sans état d'ouverture (agent sans horaires) l'outil est exposé comme
    avant, donc la phrase s'applique ; fermé ou en pause, jamais."""
    engine = await _moteur_fige(etat=None)
    assert (
        await engine.transfert_fige_a_l_ouverture(engine.active_agent, "etape")
        == PHRASE_FIGEE
    )


@pytest.mark.asyncio
async def test_fige_un_outil_qui_dit_son_message_attend_ce_que_l_ouverture_joue_deja():
    engine = await _moteur_fige(son_message=True)
    engine.queue_speech = AsyncMock()
    accueil = engine.speech_playback.create()
    await engine.dire_puis_transferer_a_l_ouverture(
        engine.active_agent, "etape", "", apres=accueil
    )
    await asyncio.sleep(0.05)
    assert _appels(engine) == [], "le transfert part pendant l'accueil"
    accueil.finish(PlaybackOutcome.PLAYED)
    await asyncio.sleep(0.05)
    assert _appels(engine) == [OUTIL] and _etats(engine) == ["lance"]


@pytest.mark.asyncio
async def test_fige_autres_garde_fous():
    agent_engine = await _moteur_fige()
    agent = agent_engine.active_agent
    # Au clavier : pas de voix.
    agent_engine.sans_sortie_audio = True
    assert await agent_engine.transfert_fige_a_l_ouverture(agent, "etape") is None
    agent_engine.sans_sortie_audio = False
    # Outil non exposé (ou lancé seulement avec des paramètres) : le modèle parle.
    agent_engine._outil_de_transfert = AsyncMock(return_value=None)
    assert await agent_engine.transfert_fige_a_l_ouverture(agent, "etape") is None
    agent_engine._outil_de_transfert = AsyncMock(return_value=OUTIL)
    # Une fin, une étape sans outil.
    assert await agent_engine.transfert_fige_a_l_ouverture(agent, "end") is None
    assert await agent_engine.transfert_fige_a_l_ouverture(agent, "start") is None
    # Un renvoi a déjà échoué dans l'appel (un seul renvoi par appel).
    agent_engine._un_renvoi_a_deja_echoue = lambda: True
    assert await agent_engine.transfert_fige_a_l_ouverture(agent, "etape") is None


@pytest.mark.asyncio
async def test_fige_un_outil_qui_porte_son_message_le_dit_lui_meme():
    engine = await _moteur_fige(son_message=True)
    assert await engine.transfert_fige_a_l_ouverture(engine.active_agent, "etape") == ""


@pytest.mark.asyncio
async def test_fige_le_message_de_l_outil_est_lu_dans_sa_configuration():
    from types import SimpleNamespace

    engine = await _moteur()
    engine._get_organization_id = AsyncMock(return_value=1)
    noeud = engine.active_agent.workflow.nodes["etape"]

    def outil(config):
        return SimpleNamespace(
            category="transfer_call", definition={"config": config}, name="x", tool_uuid="u"
        )

    cas = {
        "texte": ({"messageType": "custom", "customMessage": "Un instant."}, True),
        "texte vide": ({"messageType": "custom", "customMessage": " "}, False),
        "enregistrement": ({"messageType": "audio", "audioRecordingId": 7}, True),
        "aucun": ({"messageType": "none", "customMessage": "ignoré"}, False),
        "absent": ({}, False),
    }
    for nom, (config, attendu) in cas.items():
        engine.lire_outils = AsyncMock(return_value=[outil(config)])
        assert await engine._outil_de_transfert_a_son_message(noeud) is attendu, nom
    engine.lire_outils = AsyncMock(side_effect=RuntimeError("base"))
    assert await engine._outil_de_transfert_a_son_message(noeud) is False


@pytest.mark.asyncio
async def test_fige_la_phrase_est_dite_puis_le_transfert_part_sans_tour_de_modele():
    engine = await _moteur_fige()
    agent = engine.active_agent
    dite = engine.speech_playback.create()
    engine.queue_speech = AsyncMock(return_value=dite)
    await engine.dire_puis_transferer_a_l_ouverture(agent, "etape", PHRASE_FIGEE)
    (appel,) = engine.queue_speech.await_args_list
    # Lot 4 bis (F25) : la phrase du code laisse le micro ouvert ; coupée, le transfert ne part
    # pas (``test_fige_rien_si_la_personne_parle_avant_la_fin_de_la_phrase``).
    assert appel.args == (PHRASE_FIGEE,) and appel.kwargs["mute_user"] is False
    await asyncio.sleep(0.05)
    assert _appels(engine) == [], "le transfert part avant la fin de la phrase"
    dite.finish(PlaybackOutcome.PLAYED)
    await asyncio.sleep(0.05)
    assert _appels(engine) == [OUTIL] and _etats(engine) == ["lance"]
    agent.queue_frame.assert_not_awaited()  # aucun tour de modèle demandé


@pytest.mark.asyncio
async def test_fige_une_phrase_non_jouee_le_modele_reprend_la_parole():
    from pipecat.frames.frames import LLMRunFrame

    engine = await _moteur_fige()
    dite = engine.speech_playback.create()
    engine.queue_speech = AsyncMock(return_value=dite)
    await engine.dire_puis_transferer_a_l_ouverture(engine.active_agent, "etape", PHRASE_FIGEE)
    dite.finish(PlaybackOutcome.FAILED)
    await asyncio.sleep(0.05)
    assert _appels(engine) == [] and _etats(engine) == ["replique_non_jouee"]
    (frame,) = engine.active_agent.queue_frame.await_args_list
    assert isinstance(frame.args[0], LLMRunFrame)


@pytest.mark.asyncio
async def test_fige_un_outil_qui_dit_son_message_part_tout_de_suite_sans_phrase_du_code():
    engine = await _moteur_fige(son_message=True)
    engine.queue_speech = AsyncMock()
    await engine.dire_puis_transferer_a_l_ouverture(engine.active_agent, "etape", "")
    await asyncio.sleep(0.05)
    engine.queue_speech.assert_not_awaited()
    assert _appels(engine) == [OUTIL] and _etats(engine) == ["lance"]
    engine.active_agent.queue_frame.assert_not_awaited()


@pytest.mark.asyncio
async def test_fige_rien_si_la_personne_parle_avant_la_fin_de_la_phrase():
    engine = await _moteur_fige()
    dite = engine.speech_playback.create()
    engine.queue_speech = AsyncMock(return_value=dite)
    await engine.dire_puis_transferer_a_l_ouverture(engine.active_agent, "etape", PHRASE_FIGEE)
    engine.context.add_message({"role": "user", "content": "attendez, une question"})
    dite.finish(PlaybackOutcome.PLAYED)
    await asyncio.sleep(0.05)
    assert _appels(engine) == [] and _etats(engine) == ["personne_a_parle"]

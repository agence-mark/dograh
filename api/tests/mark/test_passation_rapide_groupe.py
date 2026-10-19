"""[.mark] Chantier agents-specialises, lot 6 : passation rapide, préchauffage sans voix, principal
resté chaud, attente réglable, renvoi unique, rappel après un renvoi échoué (A5, A6, A7, A19, K3, K8).

Plan `Labo-agent-vocal/plans/agents-specialises/` (lot 6) et décisions d'Evan du 16/10 (préchauffage SANS
ouvrir la voix, accueil resté chaud). Ces tests passent par le VRAI moteur, le VRAI coordinateur de
passation et les VRAIS gestionnaires d'outils (le pipeline fendu du banc `test_agent_transfer.py`) ; seuls
les modèles, la voix et la base (outils, définitions) sont remplacés.

| Groupe | Ce qu'il prouve |
|---|---|
| réglages | défauts du plan seulement dans un groupe ; un agent seul garde le comportement d'avant |
| passation rapide | conversation courte = aucun appel au modèle de résumé ; seul / limite 0 = résumé comme avant |
| principal chaud | le principal n'est pas libéré à la passation, rendu tel quel au retour, une visite par entrée, retiré une seule fois ; agent seul libéré comme avant ; jamais avorté ; en erreur = reconstruit |
| attente | aucune vers un agent déjà construit ; son, durée, « où » réglables ; absent = la sonnerie d'avant |
| préchauffage | les cibles sont chargées sans construire ni voix ni modèle ; la construction lit le cache ; erreur = construction normale |
| renvoi unique | un renvoi échoué : second refusé, transfert garanti éteint, ligne générique ; agent seul inchangé |
| K3 | outil de transfert non montré quand l'entreprise est fermée |
| K8 | un renvoi échoué vers l'établissement crée une demande « À rappeler » ; rien pour une personne de l'équipe |
"""

import asyncio
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from api.enums import ToolCategory
from api.services.equipe import transferts_humains as th
from api.services.groupe.prechauffage import (
    Precharge,
    cibles_de_passation,
    prechauffer_les_cibles,
)
from api.services.groupe.reglages_passation import (
    LIGNE_RENVOI_DEJA_ECHOUE,
    Attente,
    attente_de,
    limite_sans_resume,
    passation_courte,
    prechauffage_actif,
    renvoi_unique_actif,
)
from api.services.pipecat import agent_runtime_factory as fabrique_agents
from api.services.pipecat.agent_runtime_factory import (
    AgentBuildError,
)
from api.services.workflow import agent_transfer
from api.services.workflow.agent_transfer import TransferRequest
from api.services.workflow.pipecat_engine import CLE_ETAT_OUVERTURE
from api.services.workflow.tools.transfer_resolver import ResolvedTransferConfig
from api.tests.mark.banc_voix import brancher_la_parole_locale, voix_de_l_appel
from api.tests.mark.test_agent_transfere_reglages_mark import (
    WORKFLOW_ID,
    _configuration,
    _fabrique,
)
from api.tests.mark.test_diriger_vers_personne import _appeler, _essai, _moteur
from api.tests.mark.test_passation_clavier import _specialise
from api.tests.test_agent_transfer import (
    DESTINATION_WORKFLOW_ID,
    TransferAgentTool,
    TransferHarness,
    build_agent_workflow,
)
from pipecat.tests import MockLLMService

GROUPE = {"agents_specialises": [DESTINATION_WORKFLOW_ID]}
PATCH_OUTILS = (
    "api.services.workflow.pipecat_engine_custom_tools.db_client.get_tools_by_uuids"
)


# --------------------------------------------------------------------------- #
# 1. Les réglages : les défauts du plan ne valent que dans un groupe
# --------------------------------------------------------------------------- #


def test_les_defauts_du_plan_ne_valent_que_dans_un_groupe():
    assert prechauffage_actif(GROUPE) is True
    assert renvoi_unique_actif(GROUPE) is True
    assert limite_sans_resume(GROUPE) == 40
    # Un agent seul, sans réglage posé : exactement le comportement d'avant.
    for seul in ({}, None, {"autre": 1}):
        assert prechauffage_actif(seul) is False
        assert renvoi_unique_actif(seul) is False
        assert limite_sans_resume(seul) is None
        assert passation_courte(3, seul) is False
    # Un réglage posé explicitement vaut partout.
    assert prechauffage_actif({"prechauffage_agents": True}) is True
    assert renvoi_unique_actif({"un_seul_renvoi_par_appel": True}) is True
    assert limite_sans_resume({"passation_sans_resume_jusqua": 12}) == 12
    assert prechauffage_actif({**GROUPE, "prechauffage_agents": False}) is False
    assert renvoi_unique_actif({**GROUPE, "un_seul_renvoi_par_appel": False}) is False
    assert passation_courte(39, GROUPE) and not passation_courte(40, GROUPE)
    assert not passation_courte(1, {**GROUPE, "passation_sans_resume_jusqua": 0})


def test_le_reglage_attente_absent_ou_illisible_est_la_sonnerie_d_avant():
    for brut in (None, {}, {"attente": None}, {"attente": "n'importe quoi"}):
        a = attente_de(brut)
        assert a == Attente() and a.duree_min_s is None and a.passation and a.transfert_humain
        assert not a.sans_son and a.fichier is None
    a = attente_de(
        {
            "attente": {
                "son": {"storage_key": "k", "storage_backend": "s3"},
                "duree_min_s": 0,
                "passation": False,
                "transfert_humain": False,
            }
        }
    )
    assert a.fichier == ("k", "s3") and a.duree_min_s == 0.0
    assert a.passation is False and a.transfert_humain is False
    assert attente_de({"attente": {"son": "aucun"}}).sans_son
    assert attente_de({"attente": {"son": {"storage_key": "k"}}}).fichier is None
    assert attente_de({"attente": {"duree_min_s": "x"}}).duree_min_s is None


# --------------------------------------------------------------------------- #
# Montage : un appel à deux agents (le principal « 1 », un spécialisé « 99 »)
# --------------------------------------------------------------------------- #


async def _monter_groupe(reglages=None, *, messages=None):
    """Le banc de passation fendu, le premier agent = le principal du groupe ; le spécialisé
    construit porte ``agent_principal_id``. ``reglages=None`` : un agent SEUL (aucun réglage)."""
    harness = TransferHarness()
    # [.mark] Lot 3 (D7) : l'appel monte SA voix, comme run_pipeline (le banc de l'amont n'en a pas).
    with voix_de_l_appel() as banc:
        await harness.build(
            source_llm=MockLLMService(mock_steps=[], chunk_delay=0.001),
            destination_llm=MockLLMService(mock_steps=[], chunk_delay=0.001),
            source_workflow=build_agent_workflow(
                name="Accueil",
                greeting="Bonjour, je vous écoute.",
                tool_uuids=["tool-transfer-agent"],
            ),
            destination_workflow=build_agent_workflow(name="Specialise", greeting="Je note."),
        )
    brancher_la_parole_locale(harness, banc)
    harness.banc_voix = banc
    engine = harness.engine
    engine.reglages_appel = dict(reglages or {})
    engine.active_agent.reglages = dict(reglages or {})
    engine._get_organization_id = AsyncMock(return_value=1)
    factory = engine._agent_factory
    construire = factory.build

    async def construire_marque(*, workflow_id, visit_id):
        runtime = await construire(workflow_id=workflow_id, visit_id=visit_id)
        runtime.reglages = {"agent_principal_id": 1}
        return runtime

    factory.build = construire_marque
    if messages is not None:
        engine.context.set_messages(messages)
    await harness.start()
    return harness


async def _passer(harness, vers, **options):
    coordinateur = harness.engine.transfer_coordinator
    demande = TransferRequest(
        destination_workflow_id=vers,
        destination_label="vers",
        origin_visit_id=harness.engine.active_agent.visit_id,
        **options,
    )
    assert coordinateur.accept(demande)
    coordinateur.start(demande)
    await asyncio.wait_for(coordinateur._task, 20)
    return coordinateur.completed[-1]


def _sonnerie(monkeypatch):
    """Remplace la boucle d'attente : compte chaque musique, garde ses options et sa durée."""
    sonneries: list[dict] = []

    async def sonner(*, stop_event, **options):
        debut = time.monotonic()
        await stop_event.wait()
        sonneries.append({**options, "duree": time.monotonic() - debut})

    monkeypatch.setattr(agent_transfer, "play_hold_audio_loop", sonner)
    return sonneries


def _espionner(agent, nom):
    appels: list = []
    original = getattr(agent, nom)

    async def espion(*args, **kwargs):
        appels.append(args)
        return await original(*args, **kwargs)

    setattr(agent, nom, espion)
    return appels


# --------------------------------------------------------------------------- #
# 2. Le principal reste chaud
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_le_principal_reste_chaud_et_revient_sans_musique(monkeypatch):
    sonneries = _sonnerie(monkeypatch)
    harness = await _monter_groupe(GROUPE)
    engine = harness.engine
    principal = engine.active_agent
    liberations = _espionner(principal, "retire")
    avortements = _espionner(principal, "abort")
    try:
        with patch(PATCH_OUTILS, AsyncMock(return_value=[TransferAgentTool()])):
            # Principal → spécialisé : agent à construire, la musique d'attente joue.
            assert (await _passer(harness, 99))["outcome"] == "completed"
            specialise = engine.active_agent
            assert specialise is not principal and specialise.workflow_id == 99
            assert len(sonneries) == 1

            # Le principal est désactivé, PAS libéré : son pipeline reste ouvert.
            assert liberations == [] and avortements == []
            assert not principal.retired and not principal.worker.has_finished()
            assert not principal.worker.active
            assert engine._principal_chaud is principal
            assert engine._retired_agents.count(principal) == 1

            # Spécialisé → principal : rendu tel quel, jamais reconstruit, ni musique ni attente.
            debut = time.monotonic()
            assert (await _passer(harness, 1))["outcome"] == "completed"
            assert time.monotonic() - debut < 1.0
            assert harness.built_destinations == [99], "le principal chaud a été reconstruit"
            assert engine.active_agent is principal and principal.worker.active
            assert len(sonneries) == 1, "musique jouée vers un agent déjà construit"

            # Une visite par entrée dans le relevé ; même visite technique (pipeline et rappels y sont liés).
            assert principal.exited_at is None and principal.exit_reason is None
            assert principal.nb_entrees == 2
            visites = engine.agent_visits
            assert [v["workflow_id"] for v in visites] == [1, 99, 1]
            assert visites[0]["visit_id"] == visites[2]["visit_id"] == principal.visit_id
            assert visites[0]["exit_reason"] == "transferred" and visites[2].get("entree") == 2
            assert visites[2]["exited_at"] is None
            # Le principal n'est plus dans les agents écartés ; le spécialisé y est UNE fois.
            assert principal not in engine._retired_agents
            assert engine._retired_agents.count(specialise) == 1
            assert liberations == [] and avortements == []

            # Troisième passation : le principal repart chaud, toujours une seule fois dans la liste.
            assert (await _passer(harness, 99))["outcome"] == "completed"
            assert engine._retired_agents.count(principal) == 1
            assert len(engine.agent_visits) == 4
    finally:
        await harness.stop()
    # Fin d'appel : libéré UNE seule fois.
    assert len(liberations) == 1


@pytest.mark.asyncio
async def test_un_agent_seul_est_libere_comme_avant(monkeypatch):
    _sonnerie(monkeypatch)
    harness = await _monter_groupe(None)
    engine = harness.engine
    source = engine.active_agent
    liberations = _espionner(source, "retire")
    try:
        with patch(PATCH_OUTILS, AsyncMock(return_value=[TransferAgentTool()])):
            assert (await _passer(harness, 99))["outcome"] == "completed"
        assert len(liberations) == 1, "un agent seul doit être libéré à la passation"
        assert source.retired and engine._principal_chaud is None
        assert harness.built_destinations == [99]
    finally:
        await harness.stop()


@pytest.mark.asyncio
async def test_une_passation_vers_le_principal_chaud_qui_echoue_ne_l_avorte_jamais(monkeypatch):
    _sonnerie(monkeypatch)
    harness = await _monter_groupe(GROUPE)
    engine = harness.engine
    principal = engine.active_agent
    avortements = _espionner(principal, "abort")
    liberations = _espionner(principal, "retire")
    try:
        with patch(PATCH_OUTILS, AsyncMock(return_value=[TransferAgentTool()])):
            await _passer(harness, 99)
            specialise = engine.active_agent
            activer = engine.activate_agent

            async def activer_sauf_le_principal(agent, *, timeout):
                if agent is principal:
                    return False
                return await activer(agent, timeout=timeout)

            engine.activate_agent = activer_sauf_le_principal
            resultat = await _passer(harness, 1)
            assert resultat["outcome"] == "activation_failed"
            # Le principal n'est ni avorté ni libéré ; le spécialisé a gardé l'appel.
            assert avortements == [] and liberations == []
            assert not principal.retired and engine._principal_chaud is principal
            assert engine.active_agent is specialise and specialise.worker.active
            assert engine.pending_agent is None
            assert principal.nb_entrees == 1 and engine._retired_agents.count(principal) == 1

            # Le retour suivant marche, avec le même principal.
            engine.activate_agent = activer
            assert (await _passer(harness, 1))["outcome"] == "completed"
            assert engine.active_agent is principal and principal.nb_entrees == 2
    finally:
        await harness.stop()


@pytest.mark.asyncio
async def test_un_principal_chaud_en_erreur_ou_termine_n_est_pas_rendu(monkeypatch):
    _sonnerie(monkeypatch)
    harness = await _monter_groupe(GROUPE)
    engine = harness.engine
    ancien = engine.active_agent
    try:
        with patch(PATCH_OUTILS, AsyncMock(return_value=[TransferAgentTool()])):
            await _passer(harness, 99)
        assert engine.principal_chaud_pour(1) is ancien
        # En erreur (son pipeline a signalé une panne pendant qu'il attendait) : construction normale.
        ancien.error = "pipeline error"
        assert engine.principal_chaud_pour(1) is None
        neuf = SimpleNamespace(workflow_id=1)
        engine._agent_factory.build = AsyncMock(return_value=neuf)
        engine._fiche = None
        rendu = await engine.build_agent(workflow_id=1, visit_id="visit-neuf")
        assert rendu is neuf and engine._agent_factory.build.await_count == 1
        engine.discard_pending_agent(neuf)
        # Libéré (fin d'appel) : jamais rendu non plus.
        ancien.error = None
        ancien.retired = True
        assert engine.principal_chaud_pour(1) is None
    finally:
        await harness.stop()


# --------------------------------------------------------------------------- #
# 3. Passation rapide : historique sans résumé quand la conversation est courte
# --------------------------------------------------------------------------- #

CONVERSATION = [
    {"role": "user" if i % 2 == 0 else "assistant", "content": f"message {i}"}
    for i in range(10)
]


async def _passation_avec_resume(reglages):
    harness = await _monter_groupe(reglages, messages=CONVERSATION)
    llm = harness.engine.active_agent.inference_llm
    llm._generate_summary = AsyncMock(return_value=("Résumé de l'appel.", 3))
    try:
        with patch(PATCH_OUTILS, AsyncMock(return_value=[TransferAgentTool()])):
            assert (await _passer(harness, 99))["outcome"] == "completed"
        return llm._generate_summary.await_count, list(harness.engine.context.messages)
    finally:
        await harness.stop()


@pytest.mark.asyncio
async def test_une_conversation_courte_passe_sans_appel_au_modele_de_resume(monkeypatch):
    _sonnerie(monkeypatch)
    appels, messages = await _passation_avec_resume(GROUPE)
    assert appels == 0
    # L'historique est rendu tel quel : la dernière phrase de l'appelant y est.
    assert any(m.get("content") == "message 8" for m in messages)


@pytest.mark.asyncio
async def test_un_agent_seul_ou_une_limite_a_zero_garde_le_resume_d_avant(monkeypatch):
    _sonnerie(monkeypatch)
    appels, messages = await _passation_avec_resume(None)
    assert appels == 1
    assert any("Résumé de l'appel." in str(m.get("content")) for m in messages)
    appels, _ = await _passation_avec_resume({**GROUPE, "passation_sans_resume_jusqua": 0})
    assert appels == 1


# --------------------------------------------------------------------------- #
# 4. Attente réglable
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "attente",
    [{"son": "aucun"}, {"passation": False}],
    ids=["son aucun", "pas pour la passation"],
)
async def test_l_attente_eteinte_ne_joue_aucune_musique(monkeypatch, attente):
    sonneries = _sonnerie(monkeypatch)
    harness = await _monter_groupe({**GROUPE, "attente": attente})
    try:
        with patch(PATCH_OUTILS, AsyncMock(return_value=[TransferAgentTool()])):
            assert (await _passer(harness, 99))["outcome"] == "completed"
        assert sonneries == []
        assert harness.engine.active_agent.workflow_id == 99
    finally:
        await harness.stop()


@pytest.mark.asyncio
async def test_la_duree_minimale_se_regle_et_zero_est_permis(monkeypatch):
    monkeypatch.setattr(agent_transfer, "TRANSFER_MIN_HOLD_SECONDS", 1.5)
    sonneries = _sonnerie(monkeypatch)
    # Absent : la durée minimale d'avant.
    harness = await _monter_groupe(GROUPE)
    try:
        with patch(PATCH_OUTILS, AsyncMock(return_value=[TransferAgentTool()])):
            await _passer(harness, 99)
    finally:
        await harness.stop()
    assert sonneries[0]["duree"] >= 1.45
    # Zéro : la musique ne retient pas la passation.
    harness = await _monter_groupe({**GROUPE, "attente": {"duree_min_s": 0}})
    try:
        with patch(PATCH_OUTILS, AsyncMock(return_value=[TransferAgentTool()])):
            await _passer(harness, 99)
    finally:
        await harness.stop()
    assert sonneries[1]["duree"] < 1.0


@pytest.mark.asyncio
async def test_un_son_depose_est_lu_et_son_echec_garde_la_sonnerie(monkeypatch):
    sonneries = _sonnerie(monkeypatch)
    depose = {"storage_key": "org/attente.wav", "storage_backend": "s3"}
    chemins = AsyncMock(return_value="/cache/attente_8000.wav")
    monkeypatch.setattr(
        "api.services.pipecat.audio_file_cache.get_cached_ambient_noise_path", chemins
    )
    harness = await _monter_groupe({**GROUPE, "attente": {"son": depose}})
    try:
        with patch(PATCH_OUTILS, AsyncMock(return_value=[TransferAgentTool()])):
            await _passer(harness, 99)
    finally:
        await harness.stop()
    assert sonneries[0]["audio_file"] == "/cache/attente_8000.wav"
    assert chemins.await_args.args[:2] == ("org/attente.wav", "s3")
    # Le fichier ne se charge pas : la sonnerie par défaut, jamais une attente muette.
    chemins.return_value = None
    harness = await _monter_groupe({**GROUPE, "attente": {"son": depose}})
    try:
        with patch(PATCH_OUTILS, AsyncMock(return_value=[TransferAgentTool()])):
            await _passer(harness, 99)
    finally:
        await harness.stop()
    assert "audio_file" not in sonneries[1]


def _outil_de_transfert(destination="+33344000099"):
    outil = MagicMock()
    outil.tool_uuid = "u-transfert"
    outil.name = "Transfert"
    outil.category = ToolCategory.TRANSFER_CALL.value
    outil.definition = {
        "type": "transfer_call",
        "config": {"destination": destination, "timeout": 30},
    }
    return outil


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "attente,joue",
    [
        (None, True),
        ({"transfert_humain": False}, False),
        ({"son": "aucun"}, False),
        ({"duree_min_s": 0}, True),
    ],
)
async def test_l_attente_du_transfert_vers_un_humain_suit_le_reglage(
    monkeypatch, attente, joue
):
    """Le transfert vers un humain joue SA musique (pipeline du fork, pas Twilio) : branchée sur
    ``transfert_humain`` et ``son``. Absent : la sonnerie d'avant."""
    engine, mgr, _ = _moteur(monkeypatch)
    engine.reglages_appel = {**GROUPE, **({"attente": attente} if attente is not None else {})}
    engine._audio_config = SimpleNamespace(transport_out_sample_rate=8000)
    engine._transport_output = SimpleNamespace(queue_frame=AsyncMock())
    lancees = []

    async def boucle(*, stop_event, **options):
        lancees.append(options)

    # Un transfert réel (pas simulé) pour que l'attente soit jouée : le fournisseur est simulé.
    import api.services.workflow.pipecat_engine_custom_tools as outils

    monkeypatch.setattr(outils, "play_audio_loop", boucle)
    monkeypatch.setattr(outils, "est_un_essai", AsyncMock(return_value=False))
    from api.db import db_client

    monkeypatch.setattr(
        db_client,
        "get_workflow_run_by_id",
        AsyncMock(return_value=SimpleNamespace(mode="twilio", initial_context={}, gathered_context={})),
    )
    fournisseur = SimpleNamespace(
        transfer_call=AsyncMock(return_value={"call_sid": "CA1"}),
        supports_transfers=lambda: True,
        validate_config=lambda: True,
    )
    echec = SimpleNamespace(
        to_result_dict=lambda: {
            "status": "failed",
            "action": "transfer_failed",
            "reason": "no_answer",
            "message": "Pas de réponse.",
        }
    )
    gestionnaire_de_transfert = SimpleNamespace(
        store_transfer_context=AsyncMock(),
        wait_for_transfer_completion=AsyncMock(return_value=echec),
    )
    monkeypatch.setattr(outils, "get_telephony_provider_for_run", AsyncMock(return_value=fournisseur))
    monkeypatch.setattr(
        outils, "get_call_transfer_manager", AsyncMock(return_value=gestionnaire_de_transfert)
    )
    monkeypatch.setattr(
        outils,
        "resolve_transfer_config",
        AsyncMock(
            return_value=ResolvedTransferConfig(
                destination="+33344000099", timeout_seconds=30, source="static"
            )
        ),
    )
    await _appeler(mgr._create_transfer_call_handler(_outil_de_transfert(), "transfert"), {})
    assert bool(lancees) is joue


# --------------------------------------------------------------------------- #
# 5. Préchauffage : on charge, on ne construit rien
# --------------------------------------------------------------------------- #

DEFINITION_CIBLE = SimpleNamespace(
    id=7,
    workflow_json=_specialise(),
    workflow_configurations={},
    version_number=1,
    status="published",
)
CIBLE = SimpleNamespace(id=DESTINATION_WORKFLOW_ID, name="Specialise")


def _sans_service():
    """Tout service de voix ou de modèle créé au préchauffage fait échouer le test."""
    interdit = MagicMock(side_effect=AssertionError("un service a été construit au préchauffage"))
    return (
        patch("api.services.pipecat.service_factory.create_tts_service", interdit),
        patch.object(fabrique_agents, "create_llm_service", interdit),
        interdit,
    )


@pytest.mark.asyncio
async def test_le_prechauffage_charge_les_cibles_puis_les_construit_a_l_avance(monkeypatch):
    """fiabilite-orchestration, lot 3 (F5, remplace A5/A19 du 16/10) : les cibles sont chargées
    (définitions, configurations, outils), PUIS construites à l'avance (la réserve), inactives ; la
    passation prend l'agent de la réserve sans rien construire, et une autre se prépare en fond."""
    _sonnerie(monkeypatch)
    harness = await _monter_groupe(GROUPE)
    engine = harness.engine
    factory = engine._agent_factory
    factory.precharge = Precharge(organization_id=1)
    voix, modele, interdit = _sans_service()
    configuration = AsyncMock(return_value=_configuration())
    try:
        with (
            patch.object(factory, "resolve_destination", AsyncMock(return_value=(CIBLE, DEFINITION_CIBLE))),
            patch(
                "api.services.configuration.ai_model_configuration."
                "get_effective_ai_model_configuration_for_workflow",
                configuration,
            ),
            patch(
                "api.services.workflow.pipecat_engine.db_client.get_tools_by_uuids",
                AsyncMock(return_value=[TransferAgentTool()]),
            ),
            voix,
            modele,
        ):
            engine.lancer_prechauffage()
            await asyncio.wait_for(engine._tache_prechauffage, 10)
        precharge = factory.precharge
        assert list(precharge.agents) == [DESTINATION_WORKFLOW_ID], precharge.echecs
        assert precharge.echecs == {}
        charge = precharge.agents[DESTINATION_WORKFLOW_ID]
        assert charge.definition is DEFINITION_CIBLE and charge.dto.nodes
        interdit.assert_not_called()
        configuration.assert_awaited_once()
        # La réserve : l'agent est construit, inactif, rien n'a pris la main.
        assert harness.built_destinations == [DESTINATION_WORKFLOW_ID]
        pret = precharge.prets[DESTINATION_WORKFLOW_ID]
        assert pret.preconstruit is True
        assert engine.pending_agent is None
        assert engine.active_agent is not pret

        # La passation prend l'agent de la réserve : aucune construction pendant l'attente. La
        # réserve refaite en fond est enregistrée ici sans circuit : le banc réutilise le même
        # modèle factice à chaque construction, et un processeur n'a qu'une place.
        refaits: list[int] = []

        async def refaire(*, workflow_id, visit_id):
            refaits.append(workflow_id)
            return SimpleNamespace(
                preconstruit=False, error=None, is_running=True, travail=None, llm=None,
                visit_id=visit_id, reglages={},
            )

        factory.build = refaire
        with patch(PATCH_OUTILS, AsyncMock(return_value=[TransferAgentTool()])):
            resultat = await _passer(harness, DESTINATION_WORKFLOW_ID)
        assert resultat["outcome"] == "completed"
        assert resultat["to_visit_id"] == pret.visit_id
        assert engine.active_agent is pret
        assert resultat["installation"] == "reserve"
        assert resultat["installation_s"] < 0.5
        # Puis la réserve se refait en fond pour la passation suivante.
        async with asyncio.timeout(5):
            while DESTINATION_WORKFLOW_ID not in precharge.prets:
                await asyncio.sleep(0.02)
        assert precharge.prets[DESTINATION_WORKFLOW_ID] is not pret
        assert refaits == [DESTINATION_WORKFLOW_ID]
    finally:
        await harness.stop()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "reglages,message",
    [
        ({**GROUPE, "prechauffage_agents": False}, "réglage éteint"),
        (None, "agent seul"),
    ],
    ids=["éteint", "agent seul"],
)
async def test_pas_de_prechauffage_quand_il_est_eteint_ou_pour_un_agent_seul(
    monkeypatch, reglages, message
):
    harness = await _monter_groupe(reglages)
    engine = harness.engine
    engine._agent_factory.precharge = Precharge(organization_id=1)
    try:
        with patch.object(engine._agent_factory, "resolve_destination", AsyncMock()) as lecture:
            engine.lancer_prechauffage()
            assert engine._tache_prechauffage is None, message
            lecture.assert_not_awaited()
    finally:
        await harness.stop()


@pytest.mark.asyncio
async def test_une_erreur_de_prechauffage_laisse_la_passation_construire_normalement(monkeypatch):
    _sonnerie(monkeypatch)
    harness = await _monter_groupe(GROUPE)
    engine = harness.engine
    factory = engine._agent_factory
    factory.precharge = Precharge(organization_id=1)
    try:
        with (
            patch.object(
                factory,
                "resolve_destination",
                AsyncMock(side_effect=AgentBuildError("destination_not_found", "absente")),
            ),
            patch(
                "api.services.workflow.pipecat_engine.db_client.get_tools_by_uuids",
                AsyncMock(return_value=[TransferAgentTool()]),
            ),
        ):
            engine.lancer_prechauffage()
            await asyncio.wait_for(engine._tache_prechauffage, 10)
        assert factory.precharge.agents == {}
        assert DESTINATION_WORKFLOW_ID in factory.precharge.echecs  # cible absente : ignorée
        with patch(PATCH_OUTILS, AsyncMock(return_value=[TransferAgentTool()])):
            assert (await _passer(harness, 99))["outcome"] == "completed"
        assert harness.built_destinations == [99]
    finally:
        await harness.stop()


@pytest.mark.asyncio
async def test_la_construction_lit_le_cache_et_sans_cache_elle_lit_la_base():
    fabrique = _fabrique()
    fabrique.precharge = Precharge(organization_id=1)
    voix, modele, _ = _sans_service()
    configuration = AsyncMock(return_value=_configuration())
    with (
        patch.object(fabrique, "resolve_destination", AsyncMock(return_value=(CIBLE, DEFINITION_CIBLE))),
        patch(
            "api.services.configuration.ai_model_configuration."
            "get_effective_ai_model_configuration_for_workflow",
            configuration,
        ),
        voix,
        modele,
    ):
        await fabrique.prechauffer(WORKFLOW_ID)
    assert fabrique.precharge.agents[WORKFLOW_ID].user_config is configuration.return_value

    # La construction n'interroge plus ni la définition ni la configuration des modèles.
    lecture = AsyncMock(side_effect=AssertionError("lecture en base malgré le cache"))
    config_interdite = AsyncMock(side_effect=AssertionError("configuration relue malgré le cache"))
    with (
        patch.object(fabrique, "resolve_destination", lecture),
        patch(
            "api.services.configuration.ai_model_configuration."
            "get_effective_ai_model_configuration_for_workflow",
            config_interdite,
        ),
        patch("api.services.pipecat.service_factory.create_tts_service", MagicMock(return_value=SimpleNamespace())),
        patch.object(fabrique_agents, "create_llm_service", MagicMock(return_value=SimpleNamespace())),
        patch.object(fabrique, "attach", AsyncMock()),
    ):
        agent = await fabrique.build(workflow_id=WORKFLOW_ID)
    assert agent.workflow_id == WORKFLOW_ID and agent.definition_id == 7
    lecture.assert_not_awaited()

    # Sans cache pour cette cible : la base, comme avant.
    autre = _fabrique()
    lecture = AsyncMock(return_value=(CIBLE, DEFINITION_CIBLE))
    with (
        patch.object(autre, "resolve_destination", lecture),
        patch(
            "api.services.configuration.ai_model_configuration."
            "get_effective_ai_model_configuration_for_workflow",
            AsyncMock(return_value=_configuration()),
        ),
        patch("api.services.pipecat.service_factory.create_tts_service", MagicMock(return_value=SimpleNamespace())),
        patch.object(fabrique_agents, "create_llm_service", MagicMock(return_value=SimpleNamespace())),
        patch.object(autre, "attach", AsyncMock()),
    ):
        await autre.build(workflow_id=WORKFLOW_ID)
    lecture.assert_awaited_once()


@pytest.mark.asyncio
async def test_les_outils_d_un_ensemble_d_etapes_ne_sont_lus_qu_une_fois():
    lire = AsyncMock(return_value=[SimpleNamespace(tool_uuid="a"), SimpleNamespace(tool_uuid="b")])
    precharge = Precharge(organization_id=1)
    assert [o.tool_uuid for o in await precharge.outils(["a", "b", "inactif"], 1, lire)] == ["a", "b"]
    # Tout sous-ensemble déjà interrogé vient du cache (un outil inactif n'y est pas, comme en base).
    assert [o.tool_uuid for o in await precharge.outils(["b"], 1, lire)] == ["b"]
    assert await precharge.outils(["inactif"], 1, lire) == []
    assert lire.await_count == 1
    # Un identifiant jamais interrogé, ou une autre organisation : la base.
    await precharge.outils(["c"], 1, lire)
    await precharge.outils(["a"], 2, lire)
    assert lire.await_count == 3


def test_les_cibles_de_passation_sont_celles_des_outils_transfer_agent():
    autre = SimpleNamespace(category=ToolCategory.TRANSFER_CALL.value, definition={"config": {"workflow_id": 5}})
    assert cibles_de_passation([TransferAgentTool(), autre, TransferAgentTool()]) == [
        DESTINATION_WORKFLOW_ID
    ]


@pytest.mark.asyncio
async def test_prechauffer_les_cibles_ne_leve_jamais():
    class Fabrique:
        precharge = Precharge(organization_id=1)
        organization_id = 1

        async def prechauffer(self, *a, **k):
            raise RuntimeError("base injoignable")

    resultat = await prechauffer_les_cibles(
        Fabrique(),
        SimpleNamespace(nodes={}),
        lire_outils=AsyncMock(return_value=[TransferAgentTool()]),
    )
    assert resultat is None or resultat.agents == {}
    assert await prechauffer_les_cibles(SimpleNamespace(), SimpleNamespace(nodes={}), lire_outils=AsyncMock()) is None


# --------------------------------------------------------------------------- #
# 6. Un seul renvoi vers un humain par appel
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_le_second_renvoi_est_refuse_dans_un_groupe_et_permis_pour_un_agent_seul(monkeypatch):
    for reglages, second_refuse in ((GROUPE, True), ({}, False), ({**GROUPE, "un_seul_renvoi_par_appel": False}, False)):
        engine, mgr, _ = _moteur(monkeypatch)
        engine.reglages_appel = dict(reglages)
        _essai(monkeypatch, "refuse")
        gestionnaire = mgr._create_transfer_call_handler(_outil_de_transfert(), "transfert")
        premier = await _appeler(gestionnaire, {})
        assert premier["status"] == "transfer_failed"
        assert len(engine._gathered_context["transferts_humains"]) == 1
        second = await _appeler(gestionnaire, {})
        if second_refuse:
            assert second["reason"] == "renvoi_deja_echoue"
            assert second["message"] == LIGNE_RENVOI_DEJA_ECHOUE
            # Aucun appel sortant de plus, rien noté de plus.
            assert len(engine._gathered_context["transferts_humains"]) == 1
        else:
            assert second.get("reason") != "renvoi_deja_echoue"
            assert len(engine._gathered_context["transferts_humains"]) == 2


@pytest.mark.asyncio
async def test_un_renvoi_decroche_ne_ferme_pas_la_porte(monkeypatch):
    engine, mgr, _ = _moteur(monkeypatch)
    engine.reglages_appel = dict(GROUPE)
    engine._gathered_context["transferts_humains"] = [{"le": "x", "cible": "numero:***1", "issue": "decroche"}]
    assert mgr._renvoi_deja_echoue() is False
    engine._gathered_context["transferts_humains"].append({"le": "y", "cible": "numero:***1", "issue": "repondeur"})
    assert mgr._renvoi_deja_echoue() is True


@pytest.mark.asyncio
async def test_apres_un_renvoi_echoue_le_transfert_garanti_ne_repart_pas_et_la_ligne_est_donnee():
    from api.tests.mark.test_transfert_garanti import _moteur as moteur_garanti

    engine = await moteur_garanti()
    agent = engine.active_agent
    echec = [{"le": "x", "cible": "numero:***1", "issue": "sans_reponse"}]

    # Agent seul, avec ou sans échec : comme avant.
    assert engine._transfert_garanti_s_applique(agent, "etape")
    engine._gathered_context["transferts_humains"] = list(echec)
    assert engine._transfert_garanti_s_applique(agent, "etape")

    # Dans un groupe : un renvoi échoué, plus de transfert garanti, et la ligne dans le prompt.
    engine.reglages_appel = dict(GROUPE)
    assert not engine._transfert_garanti_s_applique(agent, "etape")
    await engine._prepare_node(agent, agent.workflow.nodes["etape"], apply_settings=False)
    assert LIGNE_RENVOI_DEJA_ECHOUE in agent.system_prompt
    # Réglage éteint, ou renvoi décroché : rien ne change.
    engine.reglages_appel = {**GROUPE, "un_seul_renvoi_par_appel": False}
    assert engine._transfert_garanti_s_applique(agent, "etape")
    engine.reglages_appel = dict(GROUPE)
    engine._gathered_context["transferts_humains"] = [{**echec[0], "issue": "decroche"}]
    assert engine._transfert_garanti_s_applique(agent, "etape")


# --------------------------------------------------------------------------- #
# 7. K3 : l'outil de transfert n'est pas montré quand l'entreprise est fermée
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "etat,montre",
    [("OUVERT", True), ("SUR_RENDEZ_VOUS", True), ("FERME", False), ("PAUSE", False), (None, True)],
)
async def test_k3_le_transfert_d_appel_n_est_montre_que_si_l_entreprise_est_ouverte(
    monkeypatch, etat, montre
):
    engine, mgr, _ = _moteur(monkeypatch)
    engine._call_context_vars = {CLE_ETAT_OUVERTURE: etat} if etat else {}
    from api.db import db_client

    monkeypatch.setattr(db_client, "get_tools_by_uuids", AsyncMock(return_value=[_outil_de_transfert()]))
    schemas = await mgr.get_tool_schemas(["u-transfert"])
    assert (len(schemas) == 1) is montre


# --------------------------------------------------------------------------- #
# 8. K8 : un renvoi échoué vers l'établissement laisse une demande « À rappeler »
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_k8_un_renvoi_echoue_vers_l_etablissement_est_a_rappeler(monkeypatch):
    from api.schemas.apres_appel import ApresAppelAgent
    from api.services.apres_appel.chaine import texte_du_mail
    from api.services.apres_appel.envoi import construire_envoi
    from api.services.apres_appel.rappels import ORIGINE_TRANSFERT, resume_du_rappel

    engine, mgr, _ = _moteur(monkeypatch, contexte={"caller_number": "+33612345678"})
    _essai(monkeypatch, "refuse")
    await _appeler(mgr._create_transfer_call_handler(_outil_de_transfert(), "transfert"), {})
    [entree] = engine._gathered_context["planificateur_rappel"]
    assert entree["origine"] == ORIGINE_TRANSFERT and entree["numero"] == "+33612345678"
    assert "n'a pas abouti" in resume_du_rappel(entree)

    # Par la chaîne d'après appel : la demande est « À rappeler », le mail le dit.
    run = SimpleNamespace(
        id=1, workflow_id=1, definition_id=1, mode="twilio", call_type="inbound",
        initial_context={"caller_number": "+33612345678"},
        gathered_context={"extracted_variables": {"motif": "facture"}, **engine._gathered_context},
        usage_info={}, created_at=None,
        definition=SimpleNamespace(workflow_configurations={}, version_number=1), workflow=None,
    )
    envoi = construire_envoi(run, {}, ApresAppelAgent(), [])
    assert envoi["demande"]["a_rappeler"] is True
    assert "mise en relation avec l'établissement" in envoi["demande"]["resume"]
    sujet, _corps = texte_du_mail(SimpleNamespace(envoi=envoi, fuseau=None), {})
    assert sujet.startswith("À rappeler")


@pytest.mark.asyncio
async def test_k8_rien_pour_une_personne_de_l_equipe_ni_pour_un_essai_simule(monkeypatch):
    engine, mgr, _ = _moteur(monkeypatch)
    mgr._cible_transfert_humain = "personne:camille"
    params = SimpleNamespace(result_callback=AsyncMock())
    await mgr._handle_transfer_result(
        {"action": "transfer_failed", "reason": "no_answer", "status": "transfer_failed"}, params, None
    )
    assert "planificateur_rappel" not in engine._gathered_context
    mgr._cible_transfert_humain = "numero:***0099"
    for simule in ("textchat_not_supported", "webrtc_not_supported"):
        await mgr._handle_transfer_result(
            {"action": "transfer_failed", "reason": simule, "status": "failed"}, params, None
        )
    assert "planificateur_rappel" not in engine._gathered_context
    # Un renvoi qui décroche ne demande aucun rappel.
    await mgr._handle_transfer_result(
        {"action": "destination_answered", "status": "success"}, params, None
    )
    assert "planificateur_rappel" not in engine._gathered_context


def test_un_renvoi_n_est_echoue_que_sur_une_issue_autre_que_decroche():
    assert th.un_renvoi_a_echoue({}) is False and th.un_renvoi_a_echoue(None) is False
    assert th.un_renvoi_a_echoue({"transferts_humains": [{"issue": "decroche"}]}) is False
    assert th.un_renvoi_a_echoue({"transferts_humains": [{"issue": "occupe"}]}) is True

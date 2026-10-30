"""[.mark] agent-facon-tala, lot 3 (C3 bis) : le délai de la passation mesuré morceau par morceau, et la
case « Préchauffer les collègues » (éteinte par défaut).

| Test | Ce qu'il prouve |
|---|---|
| mesure | décision, commit, requête du collègue, premier mot, premier son : chaque morceau entre dans l'enregistrement de la passation, même arrivé après son écriture |
| départ de requête | le crochet date chaque requête du client HTTP du modèle, ne s'empile pas, ne casse rien sans client |
| coordinateur | la passation demandée porte la visite d'origine (la décision se date sur ELLE) |
| case éteinte | par défaut rien ne part : aucune requête de préchauffage, au téléphone comme au clavier |
| case allumée | une requête d'un jeton par collègue, avec SON prompt d'entrée et SA clé de cache ; une fois par appel ; une erreur ne coûte rien |
| téléphone / clavier | les deux chemins réels (le moteur de l'appel, la route du clavier) lancent le préchauffage des collègues du groupe |
"""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from api.services.analyse_run.requetes_modele import noter_les_departs_de_requete
from api.services.groupe import prechauffage_du_cache as cache
from api.services.groupe.mesure_passation import MesureDePassation
from api.services.groupe.prechauffage import Precharge
from api.services.workflow.dto import ReactFlowDTO
from api.services.workflow.workflow_graph import WorkflowGraph
from api.tests.mark.test_passation_clavier import _groupe, _session, _specialise, _vide
from api.tests.mark.test_passation_rapide_groupe import (
    CIBLE,
    DEFINITION_CIBLE,
    GROUPE,
    _configuration,
    _monter_groupe,
    _sans_service,
    _sonnerie,
)
from api.tests.test_agent_transfer import DESTINATION_WORKFLOW_ID, TransferAgentTool

# --------------------------------------------------------------------------- #
# La mesure de la passation
# --------------------------------------------------------------------------- #


def test_chaque_morceau_du_delai_entre_dans_l_enregistrement():
    temps = [100.0]
    ecrits: list[dict] = []
    mesure = MesureDePassation(horloge=lambda: temps[0], enregistrements=lambda: ecrits)
    # L'accueil envoie sa requête à 100,0 ; la passation est demandée à 101,2 : la décision a pris 1,2 s.
    mesure.depart_de_requete("accueil", 100.0)
    temps[0] = 101.2
    mesure.demandee("xfer-1", "accueil")
    temps[0] = 101.5
    mesure.installee(0.3, "construit", 400.0, "collegue")
    temps[0] = 101.8
    mesure.commise()
    enregistrement = {"request_id": "xfer-1", "to_visit_id": "collegue"}
    ecrits.append(enregistrement)  # l'enregistrement est écrit AVANT les morceaux qui suivent
    mesure.completer(enregistrement)
    assert enregistrement["decision_s"] == 1.2
    assert enregistrement["commit_s"] == 0.6
    # Le collègue envoie sa première requête à 102,0 (0,8 s après la demande), dit son premier mot à
    # 102,9, la voix sonne à 103,4.
    mesure.depart_de_requete("accueil", 101.9)  # une requête de l'ancien agent : ignorée
    mesure.depart_de_requete("collegue", 102.0)
    mesure.depart_de_requete("collegue", 102.5)  # une seule fois : la première
    temps[0] = 102.9
    mesure.premier_mot("collegue")
    temps[0] = 103.4
    mesure.premier_octet()
    mesure.completer(enregistrement)
    assert enregistrement["requete_collegue_s"] == 0.8
    assert enregistrement["premier_mot_s"] == 1.7
    assert enregistrement["voix_premier_octet_s"] == 2.2
    assert enregistrement["installation_s"] == 0.3


def test_sans_requete_connue_la_decision_n_est_pas_inventee():
    mesure = MesureDePassation(horloge=lambda: 5.0)
    mesure.demandee("xfer-1", "accueil")
    mesure.depart_de_requete(None, 1.0)
    assert "decision_s" not in mesure.decoupe
    # L'appel sans visite d'origine (anciens appelants) marche comme avant.
    mesure.demandee("xfer-2")
    assert mesure.decoupe == {}


def test_une_requete_du_collegue_avant_le_commit_ne_date_rien():
    mesure = MesureDePassation(horloge=lambda: 0.0)
    mesure.demandee("x", "a")
    mesure.installee(0.1, "reserve", None, "b")
    mesure.depart_de_requete("b", 0.5)  # le collègue parle à son modèle avant d'entrer : pas sa 1re requête
    assert "requete_collegue_s" not in mesure.decoupe


class _Http:
    def __init__(self):
        self.event_hooks = {"request": [], "response": []}


def _service():
    http = _Http()
    return SimpleNamespace(_client=SimpleNamespace(_client=http)), http


@pytest.mark.asyncio
async def test_le_crochet_date_chaque_requete_et_ne_s_empile_pas():
    llm, http = _service()
    vus: list[float] = []
    assert noter_les_departs_de_requete(llm, vus.append) is True
    nouveau: list[float] = []
    assert noter_les_departs_de_requete(llm, nouveau.append) is True  # remplace, n'empile pas
    assert len(http.event_hooks["request"]) == 1
    await http.event_hooks["request"][0](object())
    assert vus == [] and len(nouveau) == 1


def test_sans_client_le_crochet_ne_casse_rien():
    assert noter_les_departs_de_requete(SimpleNamespace(), lambda _t: None) is False


@pytest.mark.asyncio
async def test_le_crochet_qui_leve_ne_coute_pas_la_requete():
    llm, http = _service()

    def casse(_instant):
        raise RuntimeError("mesure cassée")

    noter_les_departs_de_requete(llm, casse)
    await http.event_hooks["request"][0](object())  # ne lève pas


def test_la_passation_demandee_porte_la_visite_d_origine():
    from api.services.workflow.agent_transfer import AgentTransferCoordinator, TransferRequest

    engine = MagicMock()
    engine.is_call_disposed.return_value = False
    engine.active_agent.visit_id = "visite-a"
    engine.mesure_passation = MesureDePassation(horloge=lambda: 10.0)
    engine.mesure_passation.depart_de_requete("visite-a", 8.0)
    coordinateur = AgentTransferCoordinator(engine)
    requete = TransferRequest(
        destination_workflow_id=2,
        destination_label="x",
        origin_visit_id="visite-a",
        announcement=None,
    )
    assert coordinateur.accept(requete) is True
    assert engine.mesure_passation.decoupe["decision_s"] == 2.0


# --------------------------------------------------------------------------- #
# La case « Préchauffer les collègues »
# --------------------------------------------------------------------------- #


def test_la_case_est_eteinte_par_defaut_et_seul_un_vrai_booleen_l_allume():
    from api.schemas.workflow_configurations import WorkflowConfigurationDefaults

    assert WorkflowConfigurationDefaults().prechauffer_les_collegues is False
    assert cache.prechauffer_les_collegues_actif(None) is False
    assert cache.prechauffer_les_collegues_actif({}) is False
    assert cache.prechauffer_les_collegues_actif({"prechauffer_les_collegues": "oui"}) is False
    assert cache.prechauffer_les_collegues_actif({"prechauffer_les_collegues": True}) is True


def _graphe():
    return WorkflowGraph(
        ReactFlowDTO.model_validate(_specialise()), skip_instance_constraints_for={"trigger"}
    )


def _moteur_minimal():
    return SimpleNamespace(
        _format_prompt=lambda texte: texte,
        _has_recordings=False,
        _gathered_context={},
    )


@pytest.mark.asyncio
async def test_une_requete_d_un_jeton_avec_le_prompt_d_entree_et_la_cle_du_collegue():
    service = MagicMock()
    service.run_inference = AsyncMock(return_value="x")
    creer = MagicMock(return_value=service)
    moteur = _moteur_minimal()
    mesure = await cache.chauffer_un_collegue(
        moteur, 12, _graphe(), SimpleNamespace(llm=object()), creer_llm=creer
    )
    assert mesure["ok"] is True and mesure["agent_id"] == 12
    assert creer.call_args.kwargs == {"prompt_cache_key": "mark-wf-12"}
    appel = service.run_inference.await_args
    assert appel.kwargs["max_tokens"] == 1
    assert "Tu traites la demande." in appel.kwargs["system_instruction"]
    assert moteur._gathered_context["prechauffage_du_cache"] == [mesure]


@pytest.mark.asyncio
async def test_une_erreur_du_fournisseur_ne_coute_rien():
    service = MagicMock()
    service.run_inference = AsyncMock(side_effect=RuntimeError("pas de cache, pas de service"))
    moteur = _moteur_minimal()
    mesure = await cache.chauffer_un_collegue(
        moteur, 12, _graphe(), SimpleNamespace(llm=object()), creer_llm=lambda *a, **k: service
    )
    assert mesure["ok"] is False and mesure["erreur"] == "RuntimeError"


@pytest.mark.asyncio
async def test_une_fois_par_collegue_et_par_appel():
    service = MagicMock()
    service.run_inference = AsyncMock(return_value="x")
    moteur = _moteur_minimal()
    collegues = [(12, _graphe(), SimpleNamespace()), (13, _graphe(), SimpleNamespace())]
    premiers = await cache.chauffer_les_collegues(
        moteur, collegues, creer_llm=lambda *a, **k: service
    )
    seconds = await cache.chauffer_les_collegues(
        moteur, collegues, creer_llm=lambda *a, **k: service
    )
    assert [m["agent_id"] for m in premiers] == [12, 13] and seconds == []
    assert service.run_inference.await_count == 2


# --------------------------------------------------------------------------- #
# Les deux chemins réels
# --------------------------------------------------------------------------- #


async def _prechauffer_au_telephone(monkeypatch, reglages):
    _sonnerie(monkeypatch)
    harness = await _monter_groupe(reglages)
    engine = harness.engine
    factory = engine._agent_factory
    factory.precharge = Precharge(organization_id=1)
    voix, modele, _interdit = _sans_service()
    chauffer = AsyncMock(return_value={"ok": True})
    try:
        with (
            patch.object(
                factory, "resolve_destination", AsyncMock(return_value=(CIBLE, DEFINITION_CIBLE))
            ),
            patch(
                "api.services.configuration.ai_model_configuration."
                "get_effective_ai_model_configuration_for_workflow",
                AsyncMock(return_value=_configuration()),
            ),
            patch(
                "api.services.workflow.pipecat_engine.db_client.get_tools_by_uuids",
                AsyncMock(return_value=[TransferAgentTool()]),
            ),
            patch.object(cache, "chauffer_un_collegue", chauffer),
            voix,
            modele,
        ):
            engine.lancer_prechauffage()
            await asyncio.wait_for(engine._tache_prechauffage, 10)
            taches = [t for t in engine.__dict__.get("_taches_du_groupe", set()) if not t.done()]
            if taches:
                await asyncio.wait(taches, timeout=5)
    finally:
        await harness.stop()
    return chauffer


@pytest.mark.asyncio
async def test_au_telephone_la_case_allumee_chauffe_chaque_collegue_une_fois(monkeypatch):
    chauffer = await _prechauffer_au_telephone(
        monkeypatch, {**GROUPE, "prechauffer_les_collegues": True}
    )
    assert chauffer.await_count == 1, chauffer.await_args_list
    assert chauffer.await_args.args[1] == DESTINATION_WORKFLOW_ID


@pytest.mark.asyncio
async def test_au_telephone_la_case_eteinte_ne_change_rien(monkeypatch):
    chauffer = await _prechauffer_au_telephone(monkeypatch, GROUPE)
    chauffer.assert_not_awaited()


async def _creer_une_session_au_clavier(db_session, async_session, test_client_factory, reglages):
    user, principal, specialise = await _groupe(
        db_session, async_session, reglages_principal=reglages
    )
    chauffer = AsyncMock(return_value={"ok": True})
    with patch.object(cache, "chauffer_un_collegue", chauffer):
        await _session(test_client_factory, user, principal, [_vide()], [])
        await asyncio.sleep(0.5)
    return chauffer, specialise


@pytest.mark.asyncio
async def test_au_clavier_la_case_allumee_chauffe_les_collegues_a_la_creation(
    db_session, async_session, test_client_factory
):
    chauffer, specialise = await _creer_une_session_au_clavier(
        db_session, async_session, test_client_factory, {"prechauffer_les_collegues": True}
    )
    assert chauffer.await_count == 1, chauffer.await_args_list
    assert chauffer.await_args.args[1] == specialise.id


@pytest.mark.asyncio
async def test_au_clavier_la_case_eteinte_ne_change_rien(
    db_session, async_session, test_client_factory
):
    chauffer, _specialise = await _creer_une_session_au_clavier(
        db_session, async_session, test_client_factory, None
    )
    chauffer.assert_not_awaited()

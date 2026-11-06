"""[.mark] Partie 3, N3a : la latence par PHASE (transcription, modèle, outils, voix), par tour, par étape et par appel.

| Test | Ce qu'il prouve |
|---|---|
| phases | un tour se range par famille de service avec ``ttfb_kind`` de l'amont : « STTService » n'est jamais rangé sous la voix (le piège de la sous-chaîne) |
| outils | la somme des durées d'appels d'outils du tour ; absente quand aucun outil n'a tourné (pas de zéro inventé) |
| étapes | moyenne et pire cas par étape et par appel, sur les tours mesurés seulement |
| non mesuré | aucun journal, aucun tour mesuré, un tour sans mesure : ``None`` (jamais zéro) |
| modèles de l'amont | les mesures du test sont construites avec les VRAIES classes de Pipecat (``TTFBBreakdownMetrics``, ``FunctionCallMetrics``) : un champ renommé à une montée de version fait échouer |
| fin d'appel (R1) | la vraie ``on_pipeline_finished`` range la latence dans les annotations du run, ne la range pas pour un appel non mesuré, et une erreur de rangement n'empêche jamais la fin de l'appel |
| liste | la ligne de la liste lit l'annotation (``None`` = non mesuré) |
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pipecat.observers.user_bot_latency_observer import (
    FunctionCallMetrics,
    TTFBBreakdownMetrics,
)

from api.services.analyse_run.latence_par_phase import (
    champs,
    latence_des_tours,
    phases_du_tour,
    resume_de_latence,
)
from api.services.pipecat.event_handlers import register_event_handlers
from api.services.pipecat.termination_funnel_processor import TerminationFunnelProcessor


def _detail(stt=None, llm=None, tts=None, outils=()):
    ttfb = []
    if stt is not None:
        ttfb.append(TTFBBreakdownMetrics(processor="SonioxSTTService#0", start_time=1.0, duration_secs=stt).model_dump())
    if llm is not None:
        ttfb.append(TTFBBreakdownMetrics(processor="DograhMistralLLMService#1", model="m", start_time=1.0, duration_secs=llm).model_dump())
    if tts is not None:
        ttfb.append(TTFBBreakdownMetrics(processor="VoxtralTTSService#2", start_time=1.0, duration_secs=tts).model_dump())
    return {
        "ttfb": ttfb,
        "text_aggregation": None,
        "user_turn_secs": 0.4,
        "function_calls": [FunctionCallMetrics(function_name=n, start_time=1.0, duration_secs=d).model_dump() for n, d in outils],
    }


def _ev(tour, etape, **detail):
    return {"type": "mark-latency-breakdown", "turn": tour, "node_id": "n1", "node_name": etape, "payload": _detail(**detail)}


def test_un_tour_se_range_par_famille_de_service_sans_confondre_stt_et_tts():
    phases = phases_du_tour(_detail(stt=0.3, llm=0.8, tts=0.2))
    # le piège : « SonioxSTTService » contient « TTS » ; la transcription ne finit jamais sous la voix
    assert phases == {"transcription": 300.0, "modele": 800.0, "voix": 200.0}


def test_les_outils_s_additionnent_et_manquent_quand_aucun_outil_n_a_tourne():
    phases = phases_du_tour(_detail(llm=0.5, outils=[("noter_information", 0.12), ("chercher", 0.3)]))
    assert phases["outils"] == 420.0
    assert "outils" not in phases_du_tour(_detail(llm=0.5))


def test_moyenne_et_pire_cas_par_etape_et_par_appel():
    evenements = [
        _ev(1, "Accueil", stt=0.2, llm=0.6, tts=0.2),
        _ev(2, "Accueil", stt=0.4, llm=1.0, tts=0.2, outils=[("t", 0.2)]),
        _ev(3, "Devis", llm=2.0, tts=0.4),
    ]
    resume = resume_de_latence(evenements)
    assert resume["tours"] == 3
    assert resume["total"] == {"moyenne_ms": 1733.3, "pire_ms": 2400.0}
    assert resume["phases"]["modele"] == {"moyenne_ms": 1200.0, "pire_ms": 2000.0, "tours": 3}
    assert resume["phases"]["transcription"]["tours"] == 2  # le tour 3 n'a pas de mesure de transcription : il n'y compte pas
    accueil, devis = resume["par_etape"]["Accueil"], resume["par_etape"]["Devis"]
    assert accueil["tours"] == 2 and accueil["phases"]["modele"] == {"moyenne_ms": 800.0, "pire_ms": 1000.0, "tours": 2}
    assert accueil["phases"]["outils"]["pire_ms"] == 200.0 and devis["total"]["pire_ms"] == 2400.0


@pytest.mark.parametrize(
    "journal",
    [None, [], [{"type": "rtf-bot-text", "payload": {"text": "x"}}], [_ev(1, "A")], [{"type": "mark-latency-breakdown", "payload": None}]],
)
def test_un_appel_non_mesure_n_a_pas_de_latence_jamais_zero(journal):
    assert resume_de_latence(journal) is None
    assert latence_des_tours(journal) == []


def test_la_ligne_de_la_liste_lit_l_annotation_ou_dit_non_mesure():
    resume = resume_de_latence([_ev(1, "A", llm=0.5, tts=0.1)])
    assert champs({"latence": resume}) == {"latence": {"moyenne_ms": 600.0, "pire_ms": 600.0, "tours": 1}}
    for vide in (None, {}, {"latence": None}, {"latence": {}}, {"juge": {"modele": "x"}}):
        assert champs(vide) == {"latence": None}


# --- fin d'appel : la vraie on_pipeline_finished (R1) -------------------------------------------------------------------------------------


class _Source:
    def __init__(self):
        self.handlers = {}

    def event_handler(self, nom):
        def decorateur(f):
            self.handlers[nom] = f
            return f

        return decorateur


async def _fin_d_appel(monkeypatch, evenements, *, echec_du_rangement=False):
    async def maj(**kwargs):
        if echec_du_rangement and kwargs.get("annotations"):
            raise RuntimeError("base injoignable")

    espion = AsyncMock(side_effect=maj)
    for nom, valeur in (
        ("upload_workflow_run_artifacts", AsyncMock()),
        ("lancer_le_calcul_des_silences", lambda *a, **k: None),
        ("_capture_call_event", AsyncMock()),
        ("enqueue_job", AsyncMock()),
    ):
        monkeypatch.setattr(f"api.services.pipecat.event_handlers.{nom}", valeur)
    monkeypatch.setattr("api.services.pipecat.event_handlers.db_client.get_workflow_run_by_id", AsyncMock(return_value=None))
    monkeypatch.setattr("api.services.pipecat.event_handlers.db_client.update_workflow_run", espion)
    tache = _Source()
    tache.wait_for_observers = AsyncMock()
    tache.turn_trace_observer = None
    engine = SimpleNamespace(
        end_call_with_reason=AsyncMock(),
        record_call_tags=lambda tags: None,
        record_context=lambda ctx: None,
        get_gathered_context=AsyncMock(return_value={}),
        cleanup=AsyncMock(),
        finish_tool_calls=AsyncMock(),
    )
    register_event_handlers(
        task=tache,
        transport=_Source(),
        workflow_run_id=88,
        engine=engine,
        audio_buffer=SimpleNamespace(start_recording=AsyncMock(), stop_recording=AsyncMock()),
        in_memory_logs_buffer=SimpleNamespace(
            contains_user_speech=lambda: False,
            is_empty=not evenements,
            get_events=lambda: evenements,
            generate_transcript_text=lambda include_end_timestamps=False: "bonjour",
        ),
        transcript_log_coordinator=SimpleNamespace(flush=AsyncMock()),
        pipeline_metrics_aggregator=SimpleNamespace(get_all_usage_metrics_serialized=lambda: {}),
        termination_funnel=TerminationFunnelProcessor(),
        audio_config=SimpleNamespace(pipeline_sample_rate=16000),
        reglages_conservation=None,
    )
    await tache.handlers["on_pipeline_finished"](tache, None)
    return espion


def _annotations_envoyees(espion):
    return [c.kwargs["annotations"] for c in espion.call_args_list if c.kwargs.get("annotations")]


async def test_la_fin_d_appel_range_la_latence_dans_les_annotations_du_run(monkeypatch):
    espion = await _fin_d_appel(monkeypatch, [_ev(1, "Accueil", stt=0.2, llm=0.6, tts=0.2), _ev(2, "Accueil", llm=1.0, tts=0.2)])
    (annotation,) = _annotations_envoyees(espion)
    assert annotation["latence"]["tours"] == 2
    assert annotation["latence"]["par_etape"]["Accueil"]["phases"]["modele"]["pire_ms"] == 1000.0
    # le journal est rangé dans le même geste qu'avant (rien n'est retiré)
    assert any(c.kwargs.get("logs") for c in espion.call_args_list)


async def test_un_appel_non_mesure_ne_range_aucune_latence(monkeypatch):
    espion = await _fin_d_appel(monkeypatch, [{"type": "rtf-bot-text", "turn": 1, "payload": {"text": "Bonjour"}}])
    assert _annotations_envoyees(espion) == []


async def test_une_erreur_de_rangement_de_la_latence_ne_casse_jamais_la_fin_de_l_appel(monkeypatch):
    espion = await _fin_d_appel(monkeypatch, [_ev(1, "Accueil", llm=0.6)], echec_du_rangement=True)
    # la fin de l'appel est allée jusqu'au bout : le journal est rangé malgré l'erreur sur la latence
    assert any(c.kwargs.get("logs") for c in espion.call_args_list)


# --- la liste des appels et la liste de l'agent, vraie base ----------------------------------------------------------------------------------

from api.tests.mark.test_conversations_colonnes import _liste, _run, monde  # noqa: E402,F401


async def test_la_liste_des_appels_porte_la_latence_ou_dit_non_mesure(db_session, async_session, monde):
    org_a, agent_a, _, _ = monde
    resume = resume_de_latence([_ev(1, "A", llm=0.5, tts=0.1), _ev(2, "A", llm=1.5, tts=0.1)])
    await _run(async_session, agent_a, annotations={"latence": resume})
    await _run(async_session, agent_a)  # un ancien appel : rien de rangé
    runs, _ = await _liste(db_session, org_a)
    assert sorted(r["latence"] is None for r in runs) == [False, True]
    (mesure,) = [r["latence"] for r in runs if r["latence"]]
    assert mesure == {"moyenne_ms": 1100.0, "pire_ms": 1600.0, "tours": 2}


async def test_les_appels_d_un_agent_ne_laissent_sortir_des_annotations_que_la_latence(db_session, async_session, monde):
    org_a, agent_a, _, _ = monde
    resume = resume_de_latence([_ev(1, "Accueil", llm=0.5)])
    await _run(async_session, agent_a, annotations={"latence": resume, "juge": {"etat": "juge", "modele": "m"}})
    await _run(async_session, agent_a, annotations={"juge": {"etat": "juge", "modele": "m"}})
    runs, _ = await db_session.get_workflow_runs_by_workflow_id(agent_a.id, organization_id=org_a.id)
    vues = sorted((r.annotations or {} for r in runs), key=lambda a: len(a))
    assert vues[0] == {} and set(vues[1]) == {"latence"}

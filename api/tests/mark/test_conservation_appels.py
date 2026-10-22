"""[.mark] Non-regression test for the retention of the calls' copies (cloture-code-avant-migration, lot 6).

The questions this file answers, and only these:

    Does a call whose audio is not to be recorded send NO audio to storage -- and still compute its silences
    (sending and converting are two gestures: the trap of the plan)? Does the installation's ceiling win over
    a setting? Does the nightly purge empty what carries the conversation's text of the runs older than the
    organization's duration, delete their files, and keep the run's row (cost, duration, state) and its technical
    ``extra``? Does a dry run count without emptying anything? Do two organizations get two durations and never
    touch each other's runs? Does a file that cannot be deleted leave its run whole, to be retried? Do the
    routes keep one organization's settings away from another?

Why it exists
-------------
Two defects of ``b2211709`` against Evan's decisions (09/09 « verbatim yes, audio never », 06/10 « verbatim
6 months »): the audio upload was ON by default, and nothing ever emptied the copies a call leaves. 🔴 The
defect to keep out: cutting the audio upload by cutting the conversion, which also cuts the silences (they read
the same WAV files).

⚠️ What this file does NOT prove: that the screen shows the section (``conservation-appels-ecran.test.tsx``),
nor that a real storage deletes (``test_adelete_file.py``).
"""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from api.db.models import (
    OrganizationModel,
    UserModel,
    WebhookDeliveryModel,
    WorkflowRunModel,
    WorkflowRunTextSessionModel,
)
from api.enums import OrganizationConfigurationKey
from api.schemas.conservation_appels import ReglagesConservationAppels
from api.services.conservation_appels import purge
from api.services.conservation_appels.reglages import audio_voulu
from api.services.pipecat.event_handlers import register_event_handlers
from api.services.pipecat.termination_funnel_processor import TerminationFunnelProcessor

ROUTE = "/api/v1/organizations/conservation-appels"
GRAPHE = {
    "nodes": [{"id": "1", "type": "startCall", "data": {"name": "Start", "prompt": "Hello"}}],
    "edges": [],
}
MAINTENANT = datetime(2026, 10, 22, 4, 0, tzinfo=UTC)


# --------------------------------------------------------------------------- #
# 1. Sending the audio and converting it are two gestures
# --------------------------------------------------------------------------- #


class _Source:
    def __init__(self):
        self.handlers = {}

    def event_handler(self, nom):
        def decorateur(f):
            self.handlers[nom] = f
            return f

        return decorateur


async def _fin_d_appel(monkeypatch, *, plafond: bool, reglages):
    """Drive ``on_pipeline_finished`` with audio in the three buffers; returns what the upload and the silences got."""
    monkeypatch.setattr("api.services.pipecat.event_handlers.ENABLE_CALL_RECORDING_UPLOAD", plafond)
    envoye: dict = {}
    silences: dict = {}

    async def faux_envoi(run_id, **kwargs):
        envoye.update(kwargs)

    def faux_silences(run_id, appelant, agent, db):
        silences.update(appelant=appelant, agent=agent)

    for nom, valeur in (
        ("upload_workflow_run_artifacts", faux_envoi),
        ("lancer_le_calcul_des_silences", faux_silences),
        ("_capture_call_event", AsyncMock()),
        ("enqueue_job", AsyncMock()),
    ):
        monkeypatch.setattr(f"api.services.pipecat.event_handlers.{nom}", valeur)
    monkeypatch.setattr(
        "api.services.pipecat.event_handlers.db_client.get_workflow_run_by_id", AsyncMock(return_value=None)
    )
    monkeypatch.setattr("api.services.pipecat.event_handlers.db_client.update_workflow_run", AsyncMock())

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
    tampons = register_event_handlers(
        task=tache,
        transport=_Source(),
        workflow_run_id=88,
        engine=engine,
        audio_buffer=SimpleNamespace(start_recording=AsyncMock(), stop_recording=AsyncMock()),
        in_memory_logs_buffer=SimpleNamespace(
            contains_user_speech=lambda: False,
            is_empty=True,
            generate_transcript_text=lambda include_end_timestamps=False: "bonjour",
        ),
        transcript_log_coordinator=SimpleNamespace(flush=AsyncMock()),
        pipeline_metrics_aggregator=SimpleNamespace(get_all_usage_metrics_serialized=lambda: {}),
        termination_funnel=TerminationFunnelProcessor(),
        audio_config=SimpleNamespace(pipeline_sample_rate=16000),
        reglages_conservation=reglages,
    )
    pcm = b"\x00\x01" * 160
    await tampons.mixed.append(pcm)
    await tampons.user.append(pcm)
    await tampons.bot.append(pcm)
    await tache.handlers["on_pipeline_finished"](tache, None)
    return envoye, silences


@pytest.mark.parametrize(
    "plafond, audio_enregistre",
    [(True, False), (False, True), (False, False)],
    ids=["audio-non-coche", "plafond-ferme-audio-coche", "plafond-ferme-audio-non-coche"],
)
async def test_sans_audio_rien_n_est_envoye_mais_les_silences_sont_calcules(monkeypatch, plafond, audio_enregistre):
    envoye, silences = await _fin_d_appel(
        monkeypatch, plafond=plafond, reglages=ReglagesConservationAppels(audio_enregistre=audio_enregistre)
    )
    assert envoye["mixed_audio_wav"] is None and envoye["user_audio_wav"] is None and envoye["bot_audio_wav"] is None
    assert envoye["transcript_text"] == "bonjour", "the verbatim is a separate artifact, kept"
    # The trap: the silences read the same two tracks, converted whatever the setting says.
    assert silences["appelant"] and silences["agent"], "the silences must still receive both WAV files"


async def test_avec_audio_coche_et_plafond_ouvert_les_trois_pistes_partent(monkeypatch):
    envoye, silences = await _fin_d_appel(
        monkeypatch, plafond=True, reglages=ReglagesConservationAppels(audio_enregistre=True)
    )
    assert envoye["mixed_audio_wav"] and envoye["user_audio_wav"] and envoye["bot_audio_wav"]
    assert silences["appelant"] and silences["agent"]


async def test_un_appelant_qui_ne_connait_pas_les_reglages_garde_l_ancien_comportement(monkeypatch):
    # ``None``: the ceiling alone decides, as before this lot (the upstream test of the flag relies on it).
    assert audio_voulu(None) is True
    envoye, _ = await _fin_d_appel(monkeypatch, plafond=True, reglages=None)
    assert envoye["mixed_audio_wav"] and envoye["user_audio_wav"]


def test_les_defauts_de_mark():
    r = ReglagesConservationAppels()
    assert (r.purge_activee, r.duree_mois, r.audio_enregistre, r.audio_duree_mois, r.essai_a_blanc) == (
        True, 6, False, 6, True,
    )


# --------------------------------------------------------------------------- #
# 2. The nightly purge
# --------------------------------------------------------------------------- #


class _Stockage:
    """A storage that records what is deleted; ``echecs`` are addresses it cannot delete."""

    def __init__(self, echecs=()):
        self.supprimes: list[str] = []
        self.echecs = set(echecs)

    async def adelete_file(self, adresse):
        if adresse in self.echecs:
            return False
        self.supprimes.append(adresse)
        return True


@pytest.fixture
def stockage(monkeypatch):
    s = _Stockage()
    monkeypatch.setattr(purge, "get_storage_for_backend", lambda backend: s)
    return s


@pytest.fixture
async def monde(db_session, async_session):
    async def _organisation(nom):
        org = OrganizationModel(provider_id=f"org-conservation-{nom}")
        async_session.add(org)
        await async_session.flush()
        user = UserModel(provider_id=f"user-conservation-{nom}", selected_organization_id=org.id)
        async_session.add(user)
        await async_session.flush()
        agent = await db_session.create_workflow(
            name=f"Agent {nom}", workflow_definition=GRAPHE, user_id=user.id, organization_id=org.id
        )
        return org, user, agent

    org_a, user_a, agent_a = await _organisation("a")
    org_b, user_b, agent_b = await _organisation("b")
    return SimpleNamespace(org_a=org_a, user_a=user_a, agent_a=agent_a, org_b=org_b, user_b=user_b, agent_b=agent_b)


async def _run(async_session, agent, *, jours, avec_objets=True, texte=True):
    """A run created ``jours`` days before MAINTENANT, with the copies a call leaves behind."""
    run = WorkflowRunModel(
        name=f"run-{jours}j",
        workflow_id=agent.id,
        mode="twilio",
        created_at=MAINTENANT - timedelta(days=jours),
        usage_info={"duree_s": 123},
        cost_info={"total": 0.42},
        initial_context={"caller_number": "+33600000000"},
        gathered_context={"fiche": {"nom": "SECRET-DU-VERBATIM"}, "tool_results": [{"r": "SECRET-DE-L-OUTIL"}], "trace": ["x"]},
        logs={"realtime_feedback_events": [{"text": "SECRET-DE-LA-CONVERSATION"}]},
        annotations={"mark_apres_appel": {"etapes": {"synthese": {"texte": "SECRET-DE-LA-SYNTHESE"}}}},
        transcript_url=None,
        recording_url=None,
        extra={"call_id": "CA123", "stockage": "technique"},
    )
    if avec_objets:
        if texte:
            run.transcript_url = "transcripts/PLACEHOLDER.txt"
        run.recording_url = "recordings/PLACEHOLDER.wav"
        run.extra = {
            **run.extra,
            "recordings": {
                "mixed": {"storage_key": "recordings/PLACEHOLDER.wav", "track": "mixed"},
                "user": {"storage_key": "recordings/PLACEHOLDER/user.wav", "track": "user"},
                "bot": {"storage_key": "recordings/PLACEHOLDER/bot.wav", "track": "bot"},
            },
        }
    async_session.add(run)
    await async_session.flush()
    if avec_objets:
        # The addresses carry the run's id, like the upload writes them.
        run.transcript_url = f"transcripts/{run.id}.txt" if texte else None
        run.recording_url = f"recordings/{run.id}.wav"
        run.extra = {
            **{k: v for k, v in run.extra.items() if k != "recordings"},
            "recordings": {
                "mixed": {"storage_key": f"recordings/{run.id}.wav", "track": "mixed"},
                "user": {"storage_key": f"recordings/{run.id}/user.wav", "track": "user"},
                "bot": {"storage_key": f"recordings/{run.id}/bot.wav", "track": "bot"},
            },
        }
        await async_session.flush()
    return run


async def _relire(db_session, run_id):
    return await db_session.get_workflow_run_by_id(run_id)


def _reglages(**plus):
    return ReglagesConservationAppels(essai_a_blanc=False, **plus)


async def test_le_plus_vieux_est_vide_le_plus_recent_intact_et_la_ligne_du_run_reste(
    monde, async_session, db_session, stockage
):
    vieux = await _run(async_session, monde.agent_a, jours=200)
    recent = await _run(async_session, monde.agent_a, jours=30)
    bilan = await purge.purger_une_organisation(monde.org_a.id, maintenant=MAINTENANT, reglages=_reglages())

    apres = await _relire(db_session, vieux.id)
    assert (apres.logs, apres.initial_context, apres.gathered_context, apres.annotations) == ({}, {}, {}, {})
    assert apres.transcript_url is None
    # What stays: the row, its cost, its duration, its state, and the technical extra.
    assert apres.usage_info == {"duree_s": 123} and apres.cost_info == {"total": 0.42}
    assert apres.extra["call_id"] == "CA123" and apres.extra["stockage"] == "technique"
    assert apres.extra["conservation"]["texte"], "the marker of what was done"
    # The recent one is whole.
    intact = await _relire(db_session, recent.id)
    assert "SECRET-DU-VERBATIM" in str(intact.gathered_context) and intact.transcript_url
    assert intact.logs and intact.annotations and intact.initial_context
    assert bilan.runs_texte == 1 and bilan.a_blanc is False


async def test_tool_results_et_la_trace_partent_avec_le_contexte_recueilli(monde, async_session, db_session, stockage):
    vieux = await _run(async_session, monde.agent_a, jours=200)
    await purge.purger_une_organisation(monde.org_a.id, maintenant=MAINTENANT, reglages=_reglages())
    apres = await _relire(db_session, vieux.id)
    assert "SECRET-DE-L-OUTIL" not in str(apres.gathered_context) and apres.gathered_context == {}


async def test_les_objets_sont_supprimes_texte_a_la_duree_audio_a_la_sienne(monde, async_session, db_session, stockage):
    # 200 days: older than 6 months (text) but younger than 12 months (audio).
    run = await _run(async_session, monde.agent_a, jours=200)
    await purge.purger_une_organisation(
        monde.org_a.id, maintenant=MAINTENANT, reglages=_reglages(audio_duree_mois=12)
    )
    assert stockage.supprimes == [f"transcripts/{run.id}.txt"], "only the transcript at the text duration"
    garde = await _relire(db_session, run.id)
    assert garde.recording_url == f"recordings/{run.id}.wav", "the audio keeps its address until ITS duration"

    # The audio duration passes: the audio files go, the addresses with them.
    plus_tard = MAINTENANT + timedelta(days=200)
    bilan = await purge.purger_une_organisation(
        monde.org_a.id, maintenant=plus_tard, reglages=_reglages(audio_duree_mois=12)
    )
    assert set(stockage.supprimes) == {
        f"transcripts/{run.id}.txt",
        f"recordings/{run.id}.wav",
        f"recordings/{run.id}/user.wav",
        f"recordings/{run.id}/bot.wav",
    }
    apres = await _relire(db_session, run.id)
    assert apres.recording_url is None and "recordings" not in apres.extra and apres.extra["conservation"]["audio"]
    assert bilan.runs_audio == 1 and bilan.objets == 3


async def test_un_run_sans_objet_est_vide_sans_erreur(monde, async_session, db_session, stockage):
    run = await _run(async_session, monde.agent_a, jours=200, avec_objets=False)
    bilan = await purge.purger_une_organisation(monde.org_a.id, maintenant=MAINTENANT, reglages=_reglages())
    assert stockage.supprimes == [] and bilan.runs_texte == 1 and bilan.echecs == 0
    assert (await _relire(db_session, run.id)).gathered_context == {}


async def test_l_essai_a_blanc_compte_sans_rien_effacer(monde, async_session, db_session, stockage):
    run = await _run(async_session, monde.agent_a, jours=200)
    bilan = await purge.purger_une_organisation(
        monde.org_a.id, maintenant=MAINTENANT, reglages=ReglagesConservationAppels(essai_a_blanc=True)
    )
    assert bilan.a_blanc is True and bilan.runs_texte == 1 and bilan.runs_audio == 1 and bilan.objets == 4
    assert stockage.supprimes == [], "a dry run deletes no file"
    intact = await _relire(db_session, run.id)
    assert "SECRET-DU-VERBATIM" in str(intact.gathered_context) and intact.transcript_url and "conservation" not in intact.extra
    # The result is kept for the screen.
    ligne = await db_session.get_configuration(monde.org_a.id, OrganizationConfigurationKey.CONSERVATION_APPELS_BILAN.value)
    assert ligne.value["a_blanc"] is True and ligne.value["runs_texte"] == 1


async def test_la_purge_eteinte_ne_fait_rien_et_n_ecrit_rien(monde, async_session, db_session, stockage):
    run = await _run(async_session, monde.agent_a, jours=500)
    bilan = await purge.purger_une_organisation(
        monde.org_a.id, maintenant=MAINTENANT, reglages=_reglages(purge_activee=False)
    )
    assert bilan is None and stockage.supprimes == []
    assert (await _relire(db_session, run.id)).transcript_url
    assert await db_session.get_configuration(monde.org_a.id, OrganizationConfigurationKey.CONSERVATION_APPELS_BILAN.value) is None


async def test_deux_organisations_deux_durees_et_jamais_les_runs_de_l_autre(monde, async_session, db_session, stockage):
    run_a = await _run(async_session, monde.agent_a, jours=100)
    run_b = await _run(async_session, monde.agent_b, jours=100)
    # A keeps 6 months, B 3 months: the same age is emptied in B only. Each passage touches its own runs.
    await purge.purger_une_organisation(monde.org_a.id, maintenant=MAINTENANT, reglages=_reglages(duree_mois=6))
    assert (await _relire(db_session, run_a.id)).transcript_url and (await _relire(db_session, run_b.id)).transcript_url
    await purge.purger_une_organisation(monde.org_b.id, maintenant=MAINTENANT, reglages=_reglages(duree_mois=3))
    assert (await _relire(db_session, run_a.id)).transcript_url, "A's run is not B's to empty"
    assert (await _relire(db_session, run_b.id)).transcript_url is None
    assert f"transcripts/{run_b.id}.txt" in stockage.supprimes and f"transcripts/{run_a.id}.txt" not in stockage.supprimes


async def test_un_fichier_qui_ne_part_pas_laisse_le_run_entier_puis_la_nuit_suivante_le_reprend(
    monde, async_session, db_session, monkeypatch
):
    run = await _run(async_session, monde.agent_a, jours=200)
    en_panne = _Stockage(echecs={f"transcripts/{run.id}.txt"})
    monkeypatch.setattr(purge, "get_storage_for_backend", lambda backend: en_panne)
    bilan = await purge.purger_une_organisation(monde.org_a.id, maintenant=MAINTENANT, reglages=_reglages())
    assert bilan.echecs == 1 and bilan.runs_texte == 0
    intact = await _relire(db_session, run.id)
    assert intact.transcript_url == f"transcripts/{run.id}.txt", "the address is not lost while the file stands"
    assert "SECRET-DU-VERBATIM" in str(intact.gathered_context)

    reparee = _Stockage()
    monkeypatch.setattr(purge, "get_storage_for_backend", lambda backend: reparee)
    bilan = await purge.purger_une_organisation(monde.org_a.id, maintenant=MAINTENANT + timedelta(days=1), reglages=_reglages())
    assert bilan.echecs == 0 and bilan.runs_texte == 1
    assert (await _relire(db_session, run.id)).gathered_context == {}


async def test_un_second_passage_ne_refait_rien(monde, async_session, stockage):
    await _run(async_session, monde.agent_a, jours=200)
    premier = await purge.purger_une_organisation(monde.org_a.id, maintenant=MAINTENANT, reglages=_reglages())
    second = await purge.purger_une_organisation(monde.org_a.id, maintenant=MAINTENANT, reglages=_reglages())
    assert premier.runs_texte == 1 and premier.runs_audio == 1
    assert second.runs_texte == 0 and second.runs_audio == 0 and second.objets == 0


async def test_une_adresse_hors_des_prefixes_de_l_envoi_n_est_jamais_supprimee(monde, async_session, db_session, stockage):
    run = await _run(async_session, monde.agent_a, jours=200, avec_objets=False)
    run.transcript_url = "ailleurs/important.txt"
    run.recording_url = "ailleurs/important.wav"
    run.extra = {"recordings": {"user": {"storage_key": "ailleurs/autre.wav"}}}
    await async_session.flush()
    await purge.purger_une_organisation(monde.org_a.id, maintenant=MAINTENANT, reglages=_reglages())
    assert stockage.supprimes == []


async def test_la_session_texte_et_les_envois_deja_faits_sont_vides_pas_ceux_en_attente(
    monde, async_session, db_session, stockage
):
    run = await _run(async_session, monde.agent_a, jours=200, avec_objets=False)
    async_session.add(WorkflowRunTextSessionModel(workflow_run_id=run.id, session_data={"m": "SECRET-DE-LA-SESSION"}, checkpoint={"c": "SECRET"}))

    def _envoi(statut, noeud):
        return WebhookDeliveryModel(
            workflow_run_id=run.id, organization_id=monde.org_a.id, endpoint_url="https://exemple.invalid/hook",
            webhook_node_id=noeud, payload={"texte": "SECRET-DU-WEBHOOK"}, status=statut,
        )

    async_session.add_all([_envoi("succeeded", "n1"), _envoi("dead_letter", "n2"), _envoi("pending", "n3")])
    await async_session.flush()
    await purge.purger_une_organisation(monde.org_a.id, maintenant=MAINTENANT, reglages=_reglages())

    from sqlalchemy import select

    async_session.expire_all()
    session = (await async_session.execute(select(WorkflowRunTextSessionModel))).scalars().one()
    assert session.session_data == {} and session.checkpoint == {}
    envois = {e.webhook_node_id: e for e in (await async_session.execute(select(WebhookDeliveryModel))).scalars().all()}
    assert envois["n1"].payload == {} and envois["n2"].payload == {}
    assert envois["n3"].payload == {"texte": "SECRET-DU-WEBHOOK"}, "a pending delivery is sent from its payload: untouched"


async def test_la_tache_de_nuit_parcourt_les_organisations_et_un_echec_n_arrete_pas_les_autres(monde, monkeypatch):
    vus = []

    async def faux(organization_id, **kwargs):
        vus.append(organization_id)
        if organization_id == monde.org_a.id:
            raise RuntimeError("panne")
        return None

    monkeypatch.setattr(purge, "purger_une_organisation", faux)
    notifie = AsyncMock()
    monkeypatch.setattr("api.services.apres_appel.notification.notifier", notifie)
    sortie = await purge.conservation_de_nuit()
    assert {monde.org_a.id, monde.org_b.id} <= set(vus)
    assert sortie[monde.org_a.id]["statut"] == "echec" and sortie[monde.org_b.id]["statut"] == "eteinte"
    assert notifie.await_count >= 1


def test_la_tache_est_planifiee_a_une_minute_distincte_de_la_nuit_apres_appel():
    from api.services.apres_appel.taches import nuit as nuit_apres_appel
    from api.tasks.arq import WorkerSettings

    taches = {t.coroutine: t for t in WorkerSettings.cron_jobs}
    assert purge.conservation_de_nuit in taches, "the nightly purge is on arq's cron"
    assert (taches[purge.conservation_de_nuit].hour, taches[purge.conservation_de_nuit].minute) != (
        taches[nuit_apres_appel].hour,
        taches[nuit_apres_appel].minute,
    )


# --------------------------------------------------------------------------- #
# 3. The routes
# --------------------------------------------------------------------------- #


async def test_la_route_rend_les_defauts_et_enregistre(monde, test_client_factory):
    async with test_client_factory(monde.user_a) as client:
        lue = (await client.get(ROUTE)).json()
        assert lue["reglages"]["essai_a_blanc"] is True and lue["reglages"]["duree_mois"] == 6
        assert lue["reglages"]["audio_enregistre"] is False and lue["dernier_passage"] is None
        corps = {**lue["reglages"], "duree_mois": 9, "essai_a_blanc": False}
        ecrite = await client.put(ROUTE, json=corps)
        assert ecrite.status_code == 200 and ecrite.json()["reglages"]["duree_mois"] == 9
        assert (await client.get(ROUTE)).json()["reglages"]["essai_a_blanc"] is False


async def test_les_bornes_sont_refusees_avant_d_ecrire(monde, test_client_factory):
    async with test_client_factory(monde.user_a) as client:
        for champ, valeur in (("duree_mois", 0), ("duree_mois", 121), ("audio_duree_mois", 0)):
            reponse = await client.put(ROUTE, json={champ: valeur})
            assert reponse.status_code == 422, (champ, valeur)
        assert (await client.get(ROUTE)).json()["reglages"]["duree_mois"] == 6, "nothing was written"


async def test_le_plafond_de_l_installation_interdit_d_allumer_l_audio(monde, test_client_factory, monkeypatch):
    monkeypatch.setattr("api.services.conservation_appels.reglages.ENABLE_CALL_RECORDING_UPLOAD", False)
    async with test_client_factory(monde.user_a) as client:
        lue = (await client.get(ROUTE)).json()
        assert lue["audio_autorise_par_l_installation"] is False
        refus = await client.put(ROUTE, json={"audio_enregistre": True})
        assert refus.status_code == 422 and "audio_enregistre" in refus.text
        assert (await client.get(ROUTE)).json()["reglages"]["audio_enregistre"] is False
    monkeypatch.setattr("api.services.conservation_appels.reglages.ENABLE_CALL_RECORDING_UPLOAD", True)
    async with test_client_factory(monde.user_a) as client:
        assert (await client.put(ROUTE, json={"audio_enregistre": True})).status_code == 200


async def test_les_reglages_d_une_organisation_ne_sont_pas_ceux_d_une_autre(monde, test_client_factory):
    async with test_client_factory(monde.user_a) as client_a:
        await client_a.put(ROUTE, json={"duree_mois": 2, "essai_a_blanc": False})
    async with test_client_factory(monde.user_b) as client_b:
        lue = (await client_b.get(ROUTE)).json()
        assert lue["reglages"]["duree_mois"] == 6 and lue["reglages"]["essai_a_blanc"] is True


async def test_sans_organisation_choisie_la_route_refuse(test_client_factory):
    async with test_client_factory(SimpleNamespace(selected_organization_id=None)) as client:
        assert (await client.get(ROUTE)).status_code == 400
        assert (await client.put(ROUTE, json={})).status_code == 400

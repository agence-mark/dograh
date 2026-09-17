"""[.mark] Non-regression test for the town check, in the call and on the keyboard.

The questions this file answers:

    With the switch on (the default), does the caller reading step
    (``lecture_appelant.py``, one step for numbers and towns since the plan
    nombres-dictes) annotate the caller's last message only at a step that
    collects a town, only once -- and does the recorded transcript keep what
    the caller said while the model and the variable extraction read the note?
    Where the step sits for each pair of switches is asserted in
    ``test_conversion_nombres_transcription.py``.

Why it exists
-------------
Decision D1 of 2026-09-16 rests on one fact: the aggregator records the
transcript from the text it wrote, BEFORE the step downstream annotates the
context. 🔴 If an upgrade of Pipecat recorded the transcript from the context
message instead, the note would land in every verbatim, in silence. Test 4
runs the REAL user aggregator, with the REAL transcript handlers, to see it.

⚠️ What this file does NOT prove: that the town recognised is right (that is
``test_analyse_communes.py`` and ``test_codes_postaux_dictes.py``), nor that
the screen shows the switch (``ui/``).
"""

import asyncio
import inspect
import re
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pipecat.frames.frames import (
    LLMContextFrame,
    ProposedUserStartedSpeakingFrame,
    ProposedUserStoppedSpeakingFrame,
    TranscriptionFrame,
)
from pipecat.pipeline.pipeline import Pipeline
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import (
    LLMAssistantAggregator,
    LLMUserAggregator,
    LLMUserAggregatorParams,
)
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor
from pipecat.tests import run_test
from pipecat.tests.utils import SleepFrame
from pipecat.turns.user_turn_strategies import ExternalUserTurnStrategies

from api.schemas.organization_preferences import AdresseEtablissement
from api.schemas.workflow_configurations import WorkflowConfigurationDefaults
from api.services.pipecat import lecture_appelant, run_pipeline
from api.services.pipecat.lecture_appelant import (
    CLE_TRACE_NOMBRES,
    LectureAppelantProcessor,
    creer_lecture_appelant,
    lire_message_tape,
)
from api.services.pipecat.realtime_feedback_observer import register_turn_log_handlers
from api.services.pipecat.verification_communes import (
    CLE_TRACE,
    consigner_dans,
    etape_concernee,
)
from api.services.workflow import text_chat_runner
from api.services.workflow.conversation_history import build_conversation_history

MAGASIN = AdresseEtablissement(code_postal="60740", code_insee="60589", commune="Saint-Maximin")
STT_FRANCAIS = SimpleNamespace(language="fr", language_hints=None)

NOEUD_COORDONNEES = SimpleNamespace(
    name="coordonnees",
    extraction_variables=[SimpleNamespace(name="numero"), SimpleNamespace(name="commune")],
)
NOEUD_ACCUEIL = SimpleNamespace(name="accueil", extraction_variables=[SimpleNamespace(name="motif")])

MENTION_BEAUVAIS = (
    "[Vérification de la commune : « Beauvet » correspond à Beauvais (60000, Oise). "
    "Utilise ce nom sans le faire répéter.]"
)

# ⚠️ ``run_test`` gives the pipeline one second to start. The FIRST start of a
# process can take longer on a slow machine (measured 2026-09-16 on a Windows
# workstation, where an existing test of this suite fails the same way when
# run alone), and a worker that fails to start then freezes the teardown.
DEMARRAGE_S = 15


def _processeur(noeud, consigner=None, adresse=MAGASIN, conversion=False, langue_francaise=True):
    """The caller reading step, town check on, conversion off unless asked."""
    return LectureAppelantProcessor(
        conversion=conversion,
        verification=True,
        langue_francaise=langue_francaise,
        adresse=adresse,
        etape_courante=lambda: noeud,
        consigner=consigner,
    )


def _contexte(*messages):
    return LLMContext(messages=[dict(m) for m in messages])


# --------------------------------------------------------------------------- #
# 1. The switch
# --------------------------------------------------------------------------- #


def test_interrupteur_allume_par_defaut_eteint_sur_demande():
    assert WorkflowConfigurationDefaults().verification_communes is True
    etape = lambda: None  # noqa: E731
    # A stored null means "not filled in": the default, on.
    for configuration in ({}, None, {"verification_communes": None}):
        construite = creer_lecture_appelant(configuration, STT_FRANCAIS, None, etape)
        assert isinstance(construite, LectureAppelantProcessor)
        assert construite._verification is True
    # Off, with the conversion off by default: no step at all.
    assert creer_lecture_appelant({"verification_communes": False}, STT_FRANCAIS, None, etape) is None


def test_linterrupteur_ne_relit_que_sa_cle():
    """⛔ Another setting stored out of bounds must not kill the call here."""
    etape = lambda: None  # noqa: E731
    assert creer_lecture_appelant({"max_call_duration": 0, "horaires_ouverture": 12}, None, None, etape) is not None


@pytest.mark.parametrize(
    "noms,attendu",
    [
        (["commune"], True),
        (["commune_intervention"], True),
        (["adresse"], True),
        (["adresse_chantier"], True),
        (["Commune"], True),
        (["motif", "numero"], False),
        (["communes"], False),
        ([], False),
    ],
)
def test_etape_concernee(noms, attendu):
    noeud = SimpleNamespace(extraction_variables=[SimpleNamespace(name=n) for n in noms])
    assert etape_concernee(noeud) is attendu
    assert etape_concernee(None) is False


# --------------------------------------------------------------------------- #
# 2. On: what comes out
# --------------------------------------------------------------------------- #


async def _faire_passer(processeur, *trames):
    await run_test(processeur, frames_to_send=list(trames), start_timeout=DEMARRAGE_S)


@pytest.mark.asyncio
async def test_a_letape_coordonnees_la_mention_est_ajoutee():
    contexte = _contexte(
        {"role": "assistant", "content": "Dans quelle commune ?"},
        {"role": "user", "content": "c'est à Beauvet"},
    )
    await _faire_passer(_processeur(NOEUD_COORDONNEES), LLMContextFrame(context=contexte))
    assert contexte.messages[-1]["content"] == f"c'est à Beauvet {MENTION_BEAUVAIS}"
    # Earlier messages untouched.
    assert contexte.messages[0] == {"role": "assistant", "content": "Dans quelle commune ?"}


@pytest.mark.asyncio
async def test_a_une_autre_etape_rien_ne_change():
    contexte = _contexte({"role": "user", "content": "c'est à Beauvet"})
    await _faire_passer(_processeur(NOEUD_ACCUEIL), LLMContextFrame(context=contexte))
    assert contexte.messages[-1]["content"] == "c'est à Beauvet"


@pytest.mark.asyncio
async def test_conversion_eteinte_le_modele_garde_les_mots_la_mention_est_la():
    """Plan « qui fait quoi »: town check on, conversion off. The reader helps
    the town (a postal code said in words), the model keeps the words."""
    recueilli: dict = {}
    texte = "Saint-Maximin soixante sept cent quarante"
    contexte = _contexte({"role": "user", "content": texte})
    await _faire_passer(
        _processeur(NOEUD_COORDONNEES, consigner=consigner_dans(lambda: recueilli)),
        LLMContextFrame(context=contexte),
    )
    assert contexte.messages[-1]["content"] == (
        f"{texte} [Vérification de la commune : « Saint-Maximin » correspond à "
        "Saint-Maximin (60740, Oise). Utilise ce nom sans le faire répéter.]"
    )
    # No number record without the conversion.
    assert CLE_TRACE_NOMBRES not in recueilli
    assert len(recueilli[CLE_TRACE]) == 1


@pytest.mark.asyncio
async def test_une_autre_langue_la_verification_du_16_09_inchangee():
    """Not French: the reader does not run, the town check of 2026-09-16 does."""
    contexte = _contexte({"role": "user", "content": "c'est à Beauvet"})
    await _faire_passer(
        _processeur(NOEUD_COORDONNEES, conversion=True, langue_francaise=False), LLMContextFrame(context=contexte)
    )
    assert contexte.messages[-1]["content"] == f"c'est à Beauvet {MENTION_BEAUVAIS}"


@pytest.mark.asyncio
async def test_un_contexte_renvoye_deux_fois_une_seule_mention():
    """After a tool call the same context goes to the model again."""
    contexte = _contexte({"role": "user", "content": "c'est à Beauvet"})
    await _faire_passer(
        _processeur(NOEUD_COORDONNEES), LLMContextFrame(context=contexte), LLMContextFrame(context=contexte)
    )
    assert contexte.messages[-1]["content"].count("[Vérification de la commune") == 1


@pytest.mark.asyncio
async def test_une_analyse_interrompue_ne_marque_pas_le_message_examine():
    """Review of 2026-09-16: an interruption cancels the processing task during
    the analysis. Marked BEFORE the await, the message was then never analysed
    again, and the model never got the note."""
    processeur = _processeur(NOEUD_COORDONNEES)
    contexte = _contexte({"role": "user", "content": "c'est à Beauvet"})
    vrai = lecture_appelant.lire_texte

    with patch.object(lecture_appelant, "lire_texte", side_effect=asyncio.CancelledError):
        with pytest.raises(asyncio.CancelledError):
            await processeur._lire_contexte(LLMContextFrame(context=contexte))
    assert contexte.messages[-1]["content"] == "c'est à Beauvet"

    with patch.object(lecture_appelant, "lire_texte", side_effect=vrai):
        await processeur._lire_contexte(LLMContextFrame(context=contexte))
    assert contexte.messages[-1]["content"] == f"c'est à Beauvet {MENTION_BEAUVAIS}"


@pytest.mark.asyncio
async def test_seul_le_dernier_message_de_lappelant_est_annote():
    contexte = _contexte(
        {"role": "user", "content": "j'habite à Sanlis"},
        {"role": "assistant", "content": "Et votre numéro ?"},
        {"role": "user", "content": "c'est à Beauvet"},
        {"role": "assistant", "content": "un instant"},
    )
    await _faire_passer(_processeur(NOEUD_COORDONNEES), LLMContextFrame(context=contexte))
    assert contexte.messages[0]["content"] == "j'habite à Sanlis"
    assert contexte.messages[2]["content"].endswith(MENTION_BEAUVAIS)
    assert contexte.messages[3]["content"] == "un instant"


@pytest.mark.asyncio
async def test_le_contexte_provisoire_est_annote_aussi():
    """T7: Flux's eager end of turn (dormant today) sends a provisional context.

    ⚠️ Honest scope (review of 2026-09-16): this sends the SAME context object
    twice over, so it only proves a frame marked ``speculation=True`` is
    annotated. It does NOT prove the real context gets the note: Pipecat runs
    the early answer on a COPY, and a confirmed early answer writes the real
    message without going through this step. That gap is written in the module.
    """
    contexte = _contexte({"role": "user", "content": "c'est à Beauvet"})
    recueilli: dict = {}
    await _faire_passer(
        _processeur(NOEUD_COORDONNEES, consigner=consigner_dans(lambda: recueilli)),
        LLMContextFrame(context=contexte, speculation=True),
    )
    assert contexte.messages[-1]["content"].endswith(MENTION_BEAUVAIS)
    assert recueilli[CLE_TRACE][0]["provisoire"] is True


@pytest.mark.asyncio
async def test_la_trace_est_ecrite_dans_le_contexte_recueilli():
    """T8: the note is not in the transcript; the bench reads this instead."""
    recueilli: dict = {}
    contexte = _contexte({"role": "user", "content": "c'est à Beauvet"})
    await _faire_passer(
        _processeur(NOEUD_COORDONNEES, consigner=consigner_dans(lambda: recueilli)), LLMContextFrame(context=contexte)
    )
    (trace,) = recueilli[CLE_TRACE]
    assert trace["etape"] == "coordonnees"
    assert trace["entendu"] == "Beauvet"
    assert trace["statut"] == "sure"
    assert trace["commune_retenue"]["nom"] == "Beauvais"
    assert trace["commune_retenue"]["code_insee"] == "60057"
    assert "provisoire" not in trace


@pytest.mark.asyncio
async def test_une_incertaine_est_tracee_sans_commune_retenue():
    recueilli: dict = {}
    contexte = _contexte({"role": "user", "content": "j'habite à Bovet"})
    await _faire_passer(
        _processeur(NOEUD_COORDONNEES, consigner=consigner_dans(lambda: recueilli)), LLMContextFrame(context=contexte)
    )
    (trace,) = recueilli[CLE_TRACE]
    assert trace["statut"] == "a_confirmer"
    assert trace["commune_retenue"] is None
    assert "Beauvais" in [p["nom"] for p in trace["propositions"]]


@pytest.mark.asyncio
async def test_la_trace_de_lappel_tranche_le_code_postal_du_tour_suivant():
    """N2 ②, through the step: « Bovet » to confirm, then « soixante mille »."""
    recueilli: dict = {}
    processeur = _processeur(NOEUD_COORDONNEES, consigner=consigner_dans(lambda: recueilli))
    contexte = _contexte({"role": "user", "content": "j'habite à Bovet"})
    await processeur._lire_contexte(LLMContextFrame(context=contexte))
    contexte.add_message({"role": "assistant", "content": "Beauvais ou Boves ?"})
    contexte.add_message({"role": "user", "content": "soixante mille"})
    await processeur._lire_contexte(LLMContextFrame(context=contexte))
    # Decision of Evan, 2026-09-16: 60000 carries several towns and « Bovet » was
    # not heard exactly: Beauvais comes first, to confirm.
    assert contexte.messages[-1]["content"] == (
        "soixante mille [Vérification de la commune : « soixante mille » peut être "
        "Beauvais (60000, Oise), Allonne (60000, Oise) ou Goincourt (60000, Oise). "
        "Demande d'abord si c'est Beauvais ; si ce n'est pas elle, propose Allonne, puis Goincourt. "
        "Nomme chaque commune avec son département. "
        "Si aucune ne convient, fais préciser la commune avant de la noter.]"
    )


@pytest.mark.asyncio
async def test_un_echec_de_lanalyse_laisse_le_message_intact():
    contexte = _contexte({"role": "user", "content": "c'est à Beauvet"})
    with patch.object(lecture_appelant, "analyser_message", side_effect=RuntimeError("panne")):
        descendantes, _ = await run_test(
            _processeur(NOEUD_COORDONNEES), frames_to_send=[LLMContextFrame(context=contexte)], start_timeout=DEMARRAGE_S
        )
    assert contexte.messages[-1]["content"] == "c'est à Beauvet"
    # And the frame still reached the model.
    assert any(isinstance(t, LLMContextFrame) for t in descendantes)


@pytest.mark.asyncio
async def test_la_boucle_nest_pas_retenue_pendant_lanalyse():
    """The reading runs in a worker thread: the event loop keeps beating.

    ⚠️ Compared, not thresholded. Measured 2026-09-16: an analysis of a long
    sentence takes ~22 ms and, in a thread, still freezes the loop up to ~17 ms
    (the GIL is held between rapidfuzz's grouped calls). An absolute bound
    would flake on a loaded machine and barely separate the two cases; the
    number of beats during the same work, in a thread versus on the loop, does.
    """
    phrase = "je voudrais un ramonage c'est au 12 rue de la gare à Pont Saint Maxence 60700"

    async def battements_pendant(travail) -> int:
        battements = []

        async def metronome():
            while True:
                battements.append(1)
                await asyncio.sleep(0.001)

        tache = asyncio.create_task(metronome())
        await asyncio.sleep(0)
        try:
            for _ in range(10):
                await travail()
        finally:
            tache.cancel()
        return len(battements)

    async def en_tache_de_fond():
        await lecture_appelant.lire_texte(
            phrase, conversion=True, verification=True, langue_francaise=True,
            adresse=MAGASIN, noeud=NOEUD_COORDONNEES, consigner=None,
        )

    async def sur_la_boucle():
        lecture_appelant._lire(phrase, MAGASIN, [], True, True, False)

    await en_tache_de_fond()  # warm: the list and the imports
    fond = await battements_pendant(en_tache_de_fond)
    boucle = await battements_pendant(sur_la_boucle)
    assert fond >= 3 * max(boucle, 1), (fond, boucle)


# --------------------------------------------------------------------------- #
# 3. At the level of the feature: the real aggregator, the real transcript handlers
# --------------------------------------------------------------------------- #


class _Capture(FrameProcessor):
    """Stands in for the model: records what each context says when it arrives."""

    def __init__(self):
        super().__init__()
        self.lu_par_le_modele: list[str] = []

    async def process_frame(self, frame, direction: FrameDirection):
        await super().process_frame(frame, direction)
        if isinstance(frame, LLMContextFrame):
            self.lu_par_le_modele.append(frame.context.messages[-1]["content"])
        await self.push_frame(frame, direction)


@pytest.mark.asyncio
async def test_le_verbatim_garde_ce_qui_a_ete_dit_le_modele_et_lextraction_lisent_la_mention():
    contexte = LLMContext(messages=[{"role": "assistant", "content": "Dans quelle commune ?"}])
    agregateur = LLMUserAggregator(
        contexte, params=LLMUserAggregatorParams(user_turn_strategies=ExternalUserTurnStrategies())
    )
    enregistre = []
    coordinateur = SimpleNamespace(
        record_user_transcript=AsyncMock(side_effect=lambda text, **_: enregistre.append(text)),
        record_assistant_transcript=AsyncMock(),
    )
    register_turn_log_handlers(coordinateur, agregateur, LLMAssistantAggregator(contexte))
    modele = _Capture()

    await run_test(
        Pipeline([agregateur, _processeur(NOEUD_COORDONNEES), modele]),
        frames_to_send=[
            ProposedUserStartedSpeakingFrame(),
            TranscriptionFrame(text="c'est à Beauvet", user_id="", timestamp="now"),
            ProposedUserStoppedSpeakingFrame(),
            SleepFrame(sleep=1.0),
        ],
        start_timeout=DEMARRAGE_S,
    )

    # Counted, both ways: one turn recorded, one context read by the model.
    assert enregistre == ["c'est à Beauvet"]
    assert modele.lu_par_le_modele == [f"c'est à Beauvet {MENTION_BEAUVAIS}"]
    # The variable extraction reads the context's conversation history.
    assert MENTION_BEAUVAIS in build_conversation_history(contexte)


# --------------------------------------------------------------------------- #
# 4. The keyboard bench (D7, R5)
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_clavier_message_annote_a_letape_concernee_seulement():
    recueilli: dict = {}
    consigner = consigner_dans(lambda: recueilli)
    assert await lire_message_tape("c'est à Beauvet", {}, STT_FRANCAIS, MAGASIN, NOEUD_COORDONNEES, consigner) == (
        f"c'est à Beauvet {MENTION_BEAUVAIS}"
    )
    assert len(recueilli[CLE_TRACE]) == 1
    assert (
        await lire_message_tape("c'est à Beauvet", {}, STT_FRANCAIS, MAGASIN, NOEUD_ACCUEIL, consigner)
        == "c'est à Beauvet"
    )
    assert (
        await lire_message_tape(
            "c'est à Beauvet", {"verification_communes": False}, STT_FRANCAIS, MAGASIN, NOEUD_COORDONNEES, consigner
        )
        == "c'est à Beauvet"
    )
    assert len(recueilli[CLE_TRACE]) == 1


class _Arret(Exception):
    pass


async def _message_tape_jusquau_modele(texte: str, configuration: dict):
    """The keyboard path RUN up to the model's queue: (context, gathered context)."""
    contexte_capture = {}

    class _Moteur:
        def __init__(self, **kwargs):
            self._current_node = NOEUD_COORDONNEES
            self._gathered_context = {}
            contexte_capture["contexte"] = kwargs["context"]
            contexte_capture["moteur"] = self

        def __getattr__(self, nom):
            return MagicMock()

        async def initialize(self):
            pass

        async def set_node(self, *a, **k):
            pass

        async def queue_node_opening(self, **k):
            return "none"

        def get_node_greeting(self, *_):
            return None

        async def close_mcp_sessions(self):
            pass

        async def cleanup(self):
            pass

    llm = MagicMock()
    llm.queue_frame = AsyncMock(side_effect=_Arret)
    run = SimpleNamespace(
        workflow_id=6,
        name="essai",
        initial_context={},
        definition=SimpleNamespace(
            workflow_json={
                "nodes": [
                    {"id": "start", "type": "startCall", "position": {"x": 0, "y": 0},
                     "data": {"name": "Start", "prompt": "Bonjour.", "is_start": True, "allow_interrupt": False,
                              "add_global_prompt": False, "greeting_type": "text", "greeting": "Bonjour."}},
                    {"id": "end", "type": "endCall", "position": {"x": 0, "y": 200},
                     "data": {"name": "End", "prompt": "Fin.", "is_end": True, "allow_interrupt": False,
                              "add_global_prompt": False}},
                ],
                "edges": [{"id": "e", "source": "start", "target": "end",
                           "data": {"label": "Fin", "condition": "Quand c'est fini."}}],
            },
            workflow_configurations={"adresse_etablissement": MAGASIN.model_dump(), **configuration},
        ),
        workflow=SimpleNamespace(organization_id=11, user=SimpleNamespace(id=1)),
    )
    agent = SimpleNamespace(id=6, organization_id=11, workflow_configurations={})
    with (
        patch.object(text_chat_runner, "db_client") as base,
        patch.object(text_chat_runner, "PipecatEngine", _Moteur),
        patch.object(text_chat_runner, "create_llm_service", MagicMock(return_value=llm)),
        patch.object(text_chat_runner, "create_pipeline_task", MagicMock()),
        patch.object(text_chat_runner, "run_pipeline_worker", AsyncMock()),
        patch.object(text_chat_runner, "wait_for_pipeline_worker_started", AsyncMock()),
        patch.object(text_chat_runner, "execute_pre_call_fetch", AsyncMock(return_value=None)),
        patch.object(text_chat_runner, "create_recording_audio_fetcher", MagicMock()),
        patch(
            "api.services.organization_preferences.get_organization_preferences",
            AsyncMock(side_effect=RuntimeError("pas de base")),
        ),
        patch(
            "api.services.configuration.ai_model_configuration.get_effective_ai_model_configuration_for_workflow",
            AsyncMock(return_value=SimpleNamespace(
                llm=SimpleNamespace(provider="openai", model="gpt-4.1"), embeddings=None, stt=STT_FRANCAIS
            )),
        ),
        patch("api.services.managed_model_services.ensure_mps_correlation_id", AsyncMock(return_value=None)),
        patch.object(text_chat_runner, "stamp_sampling_settings", lambda cible, _llm: cible),
    ):
        base.get_workflow_run_with_context = AsyncMock(return_value=(run, None))
        base.get_workflow = AsyncMock(return_value=agent)
        base.update_workflow_run = AsyncMock()
        base.has_active_recordings = AsyncMock(return_value=False)
        with pytest.raises(_Arret):
            await text_chat_runner.execute_text_chat_pending_turn(
                workflow_run_id=7,
                workflow_id=6,
                session_data={"turns": [{"status": "pending", "user_message": {"text": texte}}]},
                checkpoint=None,
            )
    return contexte_capture["contexte"], contexte_capture["moteur"]._gathered_context


@pytest.mark.asyncio
async def test_clavier_execute_le_message_tape_arrive_annote_au_contexte():
    contexte, recueilli = await _message_tape_jusquau_modele("c'est à Beauvet", {})
    assert contexte.messages[-1] == {"role": "user", "content": f"c'est à Beauvet {MENTION_BEAUVAIS}"}
    assert len(recueilli[CLE_TRACE]) == 1


@pytest.mark.asyncio
async def test_clavier_execute_un_code_postal_dicte_arrive_en_chiffres_avec_la_mention():
    """R5: the keyboard reads like a call, conversion on."""
    contexte, recueilli = await _message_tape_jusquau_modele(
        "Saint-Maximin soixante sept cent quarante", {"conversion_nombres_transcription": True}
    )
    assert contexte.messages[-1] == {
        "role": "user",
        "content": (
            "Saint-Maximin 60740 [Vérification de la commune : « Saint-Maximin » correspond à "
            "Saint-Maximin (60740, Oise). Utilise ce nom sans le faire répéter.]"
        ),
    }
    (nombre,) = recueilli[CLE_TRACE_NOMBRES]
    assert (nombre["type"], nombre["retenu"], nombre["statut"]) == ("code_postal", "60740", "sure")


# --------------------------------------------------------------------------- #
# 5. Branching on the source
# --------------------------------------------------------------------------- #


def test_le_chemin_telephonique_cree_letape_avec_ladresse_et_le_noeud_courant():
    source = inspect.getsource(run_pipeline)
    assert re.search(
        r"lecture_appelant=creer_lecture_appelant\(\s*run_configs,\s*user_config\.stt,\s*adresse_etablissement,"
        r"\s*lambda: engine\._current_node,\s*consigner_dans\(lambda: engine\._gathered_context\)",
        source,
    ), "The phone path no longer builds the caller reading step with the agent's configuration."
    assert len(re.findall(r"creer_lecture_appelant\(", source)) == 1


def test_le_chemin_clavier_annote_avant_dajouter_le_message():
    source = inspect.getsource(text_chat_runner)
    annotation = re.search(
        r"message_pour_le_modele = await lire_message_tape\(\s*pending_user_message,\s*run_configs,"
        r"\s*getattr\(user_config, \"stt\", None\)",
        source,
    )
    ajout = re.search(r'context\.add_message\(\{"role": "user", "content": message_pour_le_modele\}\)', source)
    assert annotation and ajout
    assert annotation.start() < ajout.start()

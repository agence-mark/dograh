import asyncio
import hashlib
import time
from dataclasses import dataclass, field, replace as _remplacer
from datetime import UTC, datetime
from typing import Any

from fastapi.encoders import jsonable_encoder
from loguru import logger
from pipecat.bus.serializers.json import JSONMessageSerializer
from pipecat.frames.frames import (
    BotStartedSpeakingFrame,
    BotStoppedSpeakingFrame,
    CancelFrame,
    EndFrame,
    FunctionCallInProgressFrame,
    FunctionCallResultFrame,
    LLMAssistantPushAggregationFrame,
    LLMContextFrame,
    LLMFullResponseEndFrame,
    LLMFullResponseStartFrame,
    SpeechBoundaryFrame,
    TextFrame,
    TTSAudioRawFrame,
    TTSSpeakFrame,
    TTSStartedFrame,
    TTSStoppedFrame,
)
from pipecat.pipeline.pipeline import Pipeline
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import (
    LLMAssistantAggregatorParams,
    LLMContextAggregatorPair,
    LLMUserAggregatorParams,
)
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor
from pipecat.utils.run_context import set_current_org_id

from api.db import db_client
from api.enums import WorkflowRunMode, WorkflowRunState
from api.schemas.workflow_configurations import WorkflowConfigurationDefaults
from api.services.analyse_run.captures import estampiller_la_version
from api.services.communes.adresse import (
    injecter_adresse_etablissement,
    lire_adresse_etablissement,
)
from api.services.configuration.registry import ServiceProviders
from api.services.lexique.ecoute import injecter_lexique_propose, termes_proposes
from api.services.lexique.reglages import interrupteur_allume, lire_lexique_de_lappel
from api.services.pipecat.audio_config import create_audio_config
from api.services.annonce.stockage import lire_annonce_ouverture
from api.services.equipe.appel import injecter_equipe
from api.services.etablissements.appel import (
    annonce_heritee,
    CLE_FICHE_DE_LAGENT,
    configuration_heritee,
    injecter_etablissement,
    lire_lappel,
)
from api.services.etablissements.phrases import (
    injecter_phrases,
    lexique_avec_etablissement,
    lexique_de_lappel_avec_etablissement,
)
from api.services.objets_agent.appel import injecter_objets
from api.services.pipecat.etat_ouverture import (
    injecter_date_heure_appel,
    injecter_etat_ouverture,
    rafraichir_annonce,
)
from api.services.pipecat.lecture_appelant import _question_avant, lire_message_tape
from api.services.pipecat.pipeline_builder import create_pipeline_task
from api.services.pipecat.greffier import (
    format_garanti_du_bloc as format_garanti_du_greffier,
    greffier_du_moteur,
    preparer_le_greffier,
    resoudre_le_bloc_du_greffier,
)
from api.services.pipecat.post_scriptum import post_scriptum_du_moteur
from api.services.pipecat.reglages_tour_de_parole import (
    collecter_reglages_tour_de_parole,
)
from api.services.pipecat.replique_inachevee import brancher_la_relance
from api.services.pipecat.trace_modele import brancher_la_trace
from api.services.travail.clavier import remettre_les_travaux_termines
from api.services.pipecat.pipeline_metrics_aggregator import (
    PipelineMetricsAggregator,
)
from api.services.pipecat.pre_call_fetch import execute_pre_call_fetch
from api.services.pipecat.reconnaissance_lexique import annoter_message_tape
from api.services.workflow.fiche_au_fil_de_leau import (
    CLE_ETAT,
    CLE_JOURNAL,
    ReglagesFiche,
    attendre_les_notes,
    delai_des_notes,
    estampiller_le_mode,
)
from api.services.pipecat.recording_audio_cache import create_recording_audio_fetcher
from api.services.pipecat.service_factory import (
    cle_de_cache,
    create_llm_service,
    stamp_prompt_cache_key,
    stamp_sampling_settings,
)
from api.services.pipecat.tracing_config import (
    build_remote_parent_context,
    get_trace_url,
)
from api.services.pipecat.verification_communes import consigner_dans
from api.services.pipecat.worker_runner import (
    run_pipeline_worker,
    wait_for_pipeline_worker_started,
)
from api.services.workflow.dto import ReactFlowDTO
from api.services.groupe.fiche import fiche_fusionnee
from api.services.groupe.prechauffage_du_cache import (
    chauffer_les_collegues,
    collegues_depuis_la_base,
    prechauffer_les_collegues_actif,
)
from api.services.workflow.arbitre import preparer_l_arbitre, resoudre_le_bloc_de_l_arbitre
from api.services.pipecat.avant_la_requete import autour_du_cerveau
from api.services.workflow.decideur_de_fin_de_tour import brancher_le_decideur_de_fin_de_tour
from api.services.analyse_run.requetes_modele import brancher_le_journal_des_requetes
from api.services.pipecat.filtre_nom_civilite import creer_filtre_nom_civilite
from api.services.workflow.text_agent_factory import TextAgentFactory
from api.services.workflow.initial_context import merge_external_initial_context
from api.services.workflow.pipecat_engine import (
    ENGINE_OWNED_CONTEXT_KEYS,
    FINAL_EXTRACTION_TIMEOUT_SECONDS,
    PipecatEngine,
)
from api.services.workflow.workflow_graph import WorkflowGraph

TEXT_CHAT_CHECKPOINT_VERSION = 1
TEXT_CHAT_TURN_TIMEOUT_SECONDS = 60.0
TEXT_CHAT_IDLE_SETTLE_SECONDS = 0.2
TEXT_CHAT_INTERNAL_CANCEL_REASON = "text_chat_turn_complete"
# [.mark] Chantier agents-specialises (lot 2) : au plus trois passages par tour (le
# tour, puis l'ouverture d'un agent appelé, puis une seconde passation tout de suite).
TEXT_CHAT_MAX_PASSAGES = 3


@dataclass
class _AgentDuTour:
    """[.mark] L'agent qui parle pendant un passage du clavier : son graphe, son modèle."""

    workflow_id: int
    definition_id: int | None
    nom: str
    graphe: Any
    llm: Any
    inference_llm: Any
    variable_extraction_llm: Any
    reglages: dict[str, Any]
    visit_id: str | None = None
    # [.mark] Lot 4 d'orchestrateur-trois-cerveaux : la configuration de modèles de cet agent (celle
    # de l'appel pour le premier), d'où le cerveau de fond tire son modèle par défaut.
    config: Any = None


@dataclass
class _Passage:
    """[.mark] Ce qu'un passage du clavier laisse : son moteur, sa conversation, sa capture."""

    engine: Any
    context: Any
    capture: Any
    sorties: list[str]
    usage: dict[str, Any]


_TACHES_DE_FOND: set = set()


def _tache_de_fond(coroutine) -> None:
    """Une tâche qui vit seule (référence gardée jusqu'à sa fin) : le tour ne l'attend pas."""
    tache = asyncio.get_running_loop().create_task(coroutine)
    _TACHES_DE_FOND.add(tache)
    tache.add_done_callback(_TACHES_DE_FOND.discard)


async def _chauffer_les_collegues_du_clavier(engine, graphe_du_principal, id_du_principal: int) -> None:
    """[.mark] agent-facon-tala, C3 bis : le préchauffage du cache des collègues, comme au début d'un
    appel (mêmes collègues : les cibles des outils de passation du principal). ⛔ Ne lève jamais."""
    try:
        fabrique = engine._agent_factory
        collegues = await collegues_depuis_la_base(
            engine, fabrique, graphe_du_principal, ids_a_exclure={id_du_principal}
        )
        await chauffer_les_collegues(engine, collegues)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[prechauffage] cache du clavier abandonné : {e!r}")


def agent_a_cerveaux_neufs(
    agent: "_AgentDuTour", creer, cle_du_cache: str, *, avec_extraction: bool
) -> "_AgentDuTour":
    """[.mark] agent-facon-tala, C3 : le même agent (graphe, réglages, visite) avec des cerveaux
    neufs. Un cerveau est un processeur du circuit d'UN passage ; une fois ce circuit arrêté, le
    remettre dans un circuit neuf ne démarre jamais (la trame de départ ne sort pas). ``creer`` fabrique
    un cerveau à partir des options du service (clé de cache, usage)."""
    cerveau = creer(prompt_cache_key=cle_du_cache)
    extraction = creer(usage_context="variable_extraction") if avec_extraction else cerveau
    return _remplacer(
        agent, llm=cerveau, inference_llm=cerveau, variable_extraction_llm=extraction
    )


async def _attendre_le_groupe(engine, *, capture_processor, response_window, runner_task) -> None:
    """[.mark] Une passation lancée pendant le tour (outil, retour au principal) et les
    gestes du code (fin figée) finissent avant le démontage du tour. Rien à attendre :
    retour immédiat (tour d'avant). ⛔ Ne lève jamais."""
    try:
        marqueur = capture_processor.activity_count
        coordinateur = engine.__dict__.get("_transfer_coordinator")
        attendues = [
            t
            for t in (getattr(coordinateur, "_task", None),)
            if t is not None and not t.done()
        ]
        attendues += [
            t for t in engine.__dict__.get("_taches_du_groupe", set()) if not t.done()
        ]
        if not attendues:
            return
        await asyncio.wait(attendues, timeout=TEXT_CHAT_TURN_TIMEOUT_SECONDS)
        reste = [t for t in engine.__dict__.get("_taches_du_groupe", set()) if not t.done()]
        if reste:
            await asyncio.wait(reste, timeout=TEXT_CHAT_TURN_TIMEOUT_SECONDS)
        if capture_processor.activity_count > marqueur and not runner_task.done():
            await _wait_for_quiescence(
                capture_processor=capture_processor,
                response_window=response_window,
                runner_task=runner_task,
                activity_marker=marqueur,
            )
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[passation] clavier : attente de fin de tour en échec : {e!r}")


def _pipecat_type_tag(type_: type) -> str:
    return f"{type_.__module__}.{type_.__name__}"


def _pipecat_json_serializer() -> JSONMessageSerializer:
    return JSONMessageSerializer()


def _serialize_text_chat_checkpoint_messages(messages: list[Any]) -> list[Any]:
    """Serialize Pipecat context messages for JSONB checkpoint storage."""
    # Pipecat's bus JSON serializer already knows how to preserve LLMContext,
    # LLMSpecificMessage, and binary provider fields such as Gemini signatures.
    # Keep the serializer shape dependency contained to these checkpoint helpers.
    encoded_context = _pipecat_json_serializer()._serialize_value(
        LLMContext(messages=list(messages))
    )
    encoded_data = (
        encoded_context.get("__data__") if isinstance(encoded_context, dict) else None
    )
    encoded_messages = (
        encoded_data.get("messages") if isinstance(encoded_data, dict) else None
    )
    if not isinstance(encoded_messages, list):
        raise TypeError("Pipecat LLMContext serializer returned an unexpected shape")
    return encoded_messages


def _deserialize_text_chat_checkpoint_messages(messages: list[Any]) -> list[Any]:
    """Restore JSONB checkpoint messages to Pipecat context message objects."""
    restored_context = _pipecat_json_serializer()._deserialize_value(
        {
            "__type__": _pipecat_type_tag(LLMContext),
            "__data__": {"messages": list(messages)},
        }
    )
    if not isinstance(restored_context, LLMContext):
        raise TypeError("Pipecat LLMContext deserializer returned an unexpected type")
    return restored_context.get_messages()


def text_chat_trace_id(workflow_run_id: int) -> str:
    """Deterministic Langfuse trace id for a text-chat session.

    Each turn runs in its own short-lived pipeline, so there is no single
    long-running task to own the trace the way a voice call does. Deriving the
    id from the run id means every turn re-creates the *same* trace id and all
    per-turn spans land in one shared trace — without persisting extra state
    across the otherwise stateless turn requests.
    """
    digest = hashlib.sha256(f"dograh-text-chat:{workflow_run_id}".encode()).hexdigest()
    return digest[:32]


def default_text_chat_checkpoint() -> dict[str, Any]:
    return {
        "version": TEXT_CHAT_CHECKPOINT_VERSION,
        "anchor_turn_id": None,
        "current_node_id": None,
        "messages": [],
        "gathered_context": {},
        "tool_state": {},
    }


def normalize_text_chat_checkpoint(
    checkpoint: dict[str, Any] | None,
) -> dict[str, Any]:
    normalized = {
        **default_text_chat_checkpoint(),
        **(checkpoint or {}),
    }
    normalized["messages"] = list(normalized.get("messages") or [])
    normalized["gathered_context"] = dict(normalized.get("gathered_context") or {})
    normalized["tool_state"] = dict(normalized.get("tool_state") or {})
    return normalized


def pending_text_chat_user_message(
    session_data: dict[str, Any] | None,
) -> str | None:
    """The user text of a turn still pending when the session ended.

    ``append_text_chat_user_message`` persists the user's message into
    ``session_data`` and only folds it into ``checkpoint["messages"]`` once the
    turn executes. A session completed while a turn is in flight -- the worker
    died mid-turn, or an ``/end`` arrived carrying no ``expected_revision`` --
    therefore holds that message in its transcript but not in its checkpoint.
    Extraction reads it from here so it does not miss the last thing the user
    said, which is usually the one that matters most.
    """
    turns = list((session_data or {}).get("turns") or [])
    if not turns or turns[-1].get("status") != "pending":
        return None
    user_message = turns[-1].get("user_message") or {}
    return ((user_message.get("text") or "").strip()) or None


@dataclass
class TextChatTurnExecutionResult:
    assistant_text: str | None
    assistant_created_at: str
    events: list[dict[str, Any]]
    usage: dict[str, Any]
    checkpoint: dict[str, Any]
    gathered_context: dict[str, Any]
    initial_context: dict[str, Any]
    state: str
    is_completed: bool


@dataclass
class _ResponseWindowState:
    active_assistant_segments: int = 0
    active_llm_completions: int = 0
    pending_context_requests: int = 0
    blocking_tool_call_ids: set[str] = field(default_factory=set)
    outputs: list[str] = field(default_factory=list)

    def note_direct_context_request(self) -> None:
        self.pending_context_requests += 1

    def note_upstream_context_request(self) -> None:
        self.pending_context_requests += 1

    def note_llm_start(self) -> None:
        if self.pending_context_requests > 0:
            self.pending_context_requests -= 1
        self.active_llm_completions += 1

    def note_llm_end(self) -> None:
        if self.active_llm_completions > 0:
            self.active_llm_completions -= 1

    def note_assistant_turn_started(self) -> None:
        self.active_assistant_segments += 1

    def note_assistant_turn_stopped(self, content: str) -> None:
        if self.active_assistant_segments > 0:
            self.active_assistant_segments -= 1
        normalized_content = content.strip()
        if normalized_content:
            self.outputs.append(normalized_content)

    def note_function_call_in_progress(self, tool_call_id: str, blocking: bool) -> None:
        if blocking:
            self.blocking_tool_call_ids.add(tool_call_id)

    def note_function_call_result(self, tool_call_id: str) -> None:
        self.blocking_tool_call_ids.discard(tool_call_id)

    @property
    def has_blocking_tool_calls(self) -> bool:
        return bool(self.blocking_tool_call_ids)

    @property
    def frontier_is_idle(self) -> bool:
        return (
            self.pending_context_requests == 0
            and self.active_llm_completions == 0
            and self.active_assistant_segments == 0
            and not self.has_blocking_tool_calls
        )


class _TaskQueueProxy:
    def __init__(self, queue_frame):
        self.queue_frame = queue_frame


class _JournalDuClavier:
    """[.mark] Le journal d'un appel, au clavier : une entrée devient un événement du tour (A2)."""

    def __init__(self, capture: "_TextChatCaptureProcessor") -> None:
        self._capture = capture

    async def append(self, entree: dict[str, Any]) -> None:
        self._capture._append_event(str(entree.get("type") or ""), dict(entree.get("payload") or {}))


class _TextChatCaptureProcessor(FrameProcessor):
    def __init__(
        self,
        response_window: _ResponseWindowState,
        context: LLMContext,
        engine: PipecatEngine,
    ) -> None:
        super().__init__()
        self.last_activity_at = time.monotonic()
        self.activity_count = 0
        self.events: list[dict[str, Any]] = []
        self._response_window = response_window
        self._context = context
        self._engine = engine

    def _touch(self) -> None:
        self.last_activity_at = time.monotonic()
        self.activity_count += 1

    def _append_event(self, event_type: str, payload: dict[str, Any]) -> None:
        self.events.append(
            {
                "type": event_type,
                "created_at": datetime.now(UTC).isoformat(),
                "payload": jsonable_encoder(payload),
            }
        )

    async def process_frame(self, frame, direction: FrameDirection):
        await super().process_frame(frame, direction)
        self._touch()
        playback = self._engine.speech_playback
        await playback.before_output(self, frame)
        if isinstance(
            frame, (SpeechBoundaryFrame, LLMFullResponseStartFrame, EndFrame)
        ):
            playback.after_output(self, frame)
        if isinstance(frame, (TextFrame, TTSSpeakFrame)) and frame.text.strip():
            playback.note_output()
        if isinstance(frame, TTSAudioRawFrame):
            playback.after_output(self, frame)

        if isinstance(frame, TTSSpeakFrame):
            append_to_context = (
                frame.append_to_context if frame.append_to_context is not None else True
            )
            text = frame.text.strip()
            if text:
                await self._engine.should_mute_user(BotStartedSpeakingFrame())
                self._response_window.outputs.append(text)
                if append_to_context:
                    self._context.add_message({"role": "assistant", "content": text})
                await self._engine.should_mute_user(BotStoppedSpeakingFrame())
            return

        if isinstance(frame, LLMContextFrame) and direction == FrameDirection.UPSTREAM:
            self._response_window.note_upstream_context_request()

        if isinstance(frame, TTSStartedFrame):
            await self._engine.should_mute_user(BotStartedSpeakingFrame())

        if isinstance(frame, TTSStoppedFrame):
            await self.push_frame(frame, direction)
            await self.push_frame(LLMAssistantPushAggregationFrame(), direction)
            await self._engine.should_mute_user(BotStoppedSpeakingFrame())
            return

        if (
            isinstance(frame, LLMFullResponseStartFrame)
            and direction == FrameDirection.DOWNSTREAM
        ):
            self._response_window.note_llm_start()
            # Text delivery is this pipeline's playback boundary. Feed the
            # shared engine tracker even though there is no audio transport.
            await self._engine.should_mute_user(BotStartedSpeakingFrame())

        if (
            isinstance(frame, LLMFullResponseEndFrame)
            and direction is FrameDirection.DOWNSTREAM
        ):
            self._response_window.note_llm_end()
            await self.push_frame(frame, direction)
            # Text chat has no TTS/output transport, so mixed text+tool responses
            # would otherwise leave function calls waiting forever on a
            # BotStoppedSpeakingFrame that never arrives.
            await self.push_frame(BotStoppedSpeakingFrame(), FrameDirection.UPSTREAM)
            await self._engine.should_mute_user(BotStoppedSpeakingFrame())
            playback.after_output(self, frame)
            return

        if isinstance(frame, FunctionCallInProgressFrame):
            self._response_window.note_function_call_in_progress(
                tool_call_id=frame.tool_call_id,
                blocking=frame.cancel_on_interruption,
            )
            self._append_event(
                "tool_call_started",
                {
                    "function_name": frame.function_name,
                    "tool_call_id": frame.tool_call_id,
                    "arguments": dict(frame.arguments or {}),
                },
            )
        elif isinstance(frame, FunctionCallResultFrame):
            self._response_window.note_function_call_result(frame.tool_call_id)
            self._append_event(
                "tool_call_result",
                {
                    "function_name": frame.function_name,
                    "tool_call_id": frame.tool_call_id,
                    "result": frame.result,
                },
            )
        elif isinstance(frame, EndFrame):
            self._append_event("session_end", {"reason": frame.reason})
        elif isinstance(frame, CancelFrame):
            if frame.reason != TEXT_CHAT_INTERNAL_CANCEL_REASON:
                self._append_event("session_cancelled", {"reason": frame.reason})

        await self.push_frame(frame, direction)


def _merge_usage_info(
    existing: dict[str, Any] | None,
    delta: dict[str, Any] | None,
) -> dict[str, Any]:
    merged = dict(existing or {})
    delta = dict(delta or {})

    merged_llm = dict(merged.get("llm") or {})
    for key, value in (delta.get("llm") or {}).items():
        current = dict(merged_llm.get(key) or {})
        merged_llm[key] = {
            "prompt_tokens": int(current.get("prompt_tokens") or 0)
            + int(value.get("prompt_tokens") or 0),
            "completion_tokens": int(current.get("completion_tokens") or 0)
            + int(value.get("completion_tokens") or 0),
            "total_tokens": int(current.get("total_tokens") or 0)
            + int(value.get("total_tokens") or 0),
            "cache_read_input_tokens": int(current.get("cache_read_input_tokens") or 0)
            + int(value.get("cache_read_input_tokens") or 0),
            "cache_creation_input_tokens": int(
                current.get("cache_creation_input_tokens") or 0
            )
            + int(value.get("cache_creation_input_tokens") or 0),
        }
    merged["llm"] = merged_llm

    for section in ("tts", "stt"):
        merged_section = dict(merged.get(section) or {})
        for key, value in (delta.get(section) or {}).items():
            merged_section[key] = float(merged_section.get(key) or 0) + float(value)
        merged[section] = merged_section

    merged["call_duration_seconds"] = int(
        merged.get("call_duration_seconds") or 0
    ) + int(delta.get("call_duration_seconds") or 0)

    return merged


def merge_text_chat_usage_info(
    existing: dict[str, Any] | None,
    delta: dict[str, Any] | None,
) -> dict[str, Any]:
    return _merge_usage_info(existing, delta)


def _resolve_checkpoint_for_pending_turn(
    session_data: dict[str, Any],
    checkpoint: dict[str, Any] | None,
) -> dict[str, Any]:
    turns = list(session_data.get("turns") or [])
    if not turns:
        return normalize_text_chat_checkpoint(checkpoint)

    pending_turn = turns[-1]
    if pending_turn.get("status") != "pending":
        return normalize_text_chat_checkpoint(checkpoint)

    for turn in reversed(turns[:-1]):
        if turn.get("status") != "completed":
            continue
        stored_checkpoint = turn.get("checkpoint_after_turn")
        if stored_checkpoint:
            return normalize_text_chat_checkpoint(stored_checkpoint)
        break

    return normalize_text_chat_checkpoint(checkpoint)


async def _wait_for_quiescence(
    *,
    capture_processor: _TextChatCaptureProcessor,
    response_window: _ResponseWindowState,
    runner_task: asyncio.Task,
    activity_marker: int,
    timeout_seconds: float = TEXT_CHAT_TURN_TIMEOUT_SECONDS,
) -> None:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout_seconds

    while loop.time() < deadline:
        if runner_task.done():
            await runner_task
            return

        if (
            capture_processor.activity_count <= activity_marker
            and response_window.frontier_is_idle
        ):
            await asyncio.sleep(0.05)
            continue

        if (
            response_window.frontier_is_idle
            and (time.monotonic() - capture_processor.last_activity_at)
            >= TEXT_CHAT_IDLE_SETTLE_SECONDS
        ):
            return

        await asyncio.sleep(0.05)

    raise TimeoutError(
        "Timed out waiting for text chat response window to settle "
        f"(pending_context_requests={response_window.pending_context_requests}, "
        f"active_llm_completions={response_window.active_llm_completions}, "
        f"active_assistant_segments={response_window.active_assistant_segments}, "
        f"blocking_tool_calls={sorted(response_window.blocking_tool_call_ids)})"
    )


def _derniere_replique_agent(context) -> str | None:
    """[.mark] Lot 1 (11/10) : la dernière réplique de l'agent, lue EXACTEMENT comme au
    téléphone (revue du 11/10 : même fonction, ``lecture_appelant._question_avant``)."""
    try:
        messages = list(context.messages)
        return _question_avant(messages, len(messages))
    except Exception:  # noqa: BLE001 -- la lecture continue sans la question
        return None


async def execute_text_chat_pending_turn(
    *,
    workflow_run_id: int,
    workflow_id: int,
    session_data: dict[str, Any],
    checkpoint: dict[str, Any] | None,
) -> TextChatTurnExecutionResult:
    turns = list(session_data.get("turns") or [])
    if not turns or turns[-1].get("status") != "pending":
        raise ValueError("Text chat session has no pending turn to execute")

    pending_turn = turns[-1]
    pending_user_message = (
        ((pending_turn.get("user_message") or {}).get("text") or "").strip()
        if pending_turn.get("user_message") is not None
        else None
    )
    workflow_run, _ = await db_client.get_workflow_run_with_context(workflow_run_id)
    if not workflow_run or workflow_run.workflow_id != workflow_id:
        raise ValueError("Workflow run not found for text chat execution")
    if workflow_run.definition is None:
        raise ValueError("Workflow run is missing a pinned definition")
    if workflow_run.workflow is None or workflow_run.workflow.user is None:
        raise ValueError("Workflow run is missing workflow context")

    workflow = await db_client.get_workflow(
        workflow_id, organization_id=workflow_run.workflow.organization_id
    )
    if workflow is None:
        raise ValueError("Workflow not found for text chat execution")
    # Stamp the async context so OTEL spans are tagged with this org and routed
    # to its Langfuse project (the voice paths do this in run_pipeline /
    # webrtc_signaling; the text path previously skipped it, so its spans never
    # reached org-specific exporters).
    set_current_org_id(workflow.organization_id)

    run_definition = workflow_run.definition
    run_configs = run_definition.workflow_configurations or {}

    from api.services.configuration.ai_model_configuration import (
        get_effective_ai_model_configuration_for_workflow,
    )

    user_config = await get_effective_ai_model_configuration_for_workflow(
        organization_id=workflow.organization_id,
        workflow_configurations=run_configs,
    )
    if user_config.llm is None:
        raise ValueError("Text chat requires an LLM configuration")

    workflow_graph = WorkflowGraph(
        ReactFlowDTO.model_validate(run_definition.workflow_json),
        skip_instance_constraints_for={"trigger"},
    )

    from api.services.managed_model_services import (
        MPS_CORRELATION_ID_CONTEXT_KEY,
        ensure_mps_correlation_id,
    )

    base_initial_context = dict(workflow_run.initial_context or {})
    mps_correlation_id = await ensure_mps_correlation_id(
        ai_model_config=user_config,
        workflow_run_id=workflow_run_id,
        initial_context=base_initial_context,
    )

    # [.mark] One cache key per agent (D1), on the conversation only (D6).
    llm = create_llm_service(
        user_config,
        correlation_id=mps_correlation_id,
        prompt_cache_key=cle_de_cache(workflow_id),
    )
    inference_llm = llm
    call_dispositions = WorkflowConfigurationDefaults.model_validate(
        {"call_dispositions": run_configs.get("call_dispositions") or []}
    ).call_dispositions
    needs_extraction_llm = workflow_graph.uses_variable_extraction() or bool(
        call_dispositions
    )
    variable_extraction_llm = (
        create_llm_service(
            user_config,
            correlation_id=mps_correlation_id,
            usage_context="variable_extraction",
        )
        if needs_extraction_llm
        and user_config.llm.provider == ServiceProviders.DOGRAH.value
        else llm
    )

    runtime_configuration = {
        "llm_provider": user_config.llm.provider,
        "llm_model": user_config.llm.model,
    }
    # The keyboard bench runs through here, not through run_pipeline. Stamping
    # only the phone path would leave every bench result unable to say what it
    # was played with -- which is the whole reason the stamp exists.
    stamp_sampling_settings(runtime_configuration, user_config.llm)
    stamp_prompt_cache_key(
        runtime_configuration, user_config.llm, cle_de_cache(workflow_id)
    )
    initial_context = {
        **base_initial_context,
        "workflow_run_id": workflow_run_id,
        "runtime_configuration": runtime_configuration,
    }
    if mps_correlation_id:
        initial_context[MPS_CORRELATION_ID_CONTEXT_KEY] = mps_correlation_id
    # [.mark] Opening state, BEFORE the pre-call fetch (which wins, D7) and the
    # persistence below. On later turns the keys persisted by the first turn
    # are kept (D7 again): the state stays the one of the first turn (D8).
    # [.mark] The organization's announcement settings (chantier
    # reglages-annonce-ouverture, 18/09), read once like the address below: the
    # keyboard bench must hear exactly what a call hears.
    # ⛔ And NO ``direction`` here, on purpose. An outbound call announces
    # nothing (decision of Evan, 18/09), but a keyboard run is created with
    # ``call_type`` left at its database default, which is ``outbound``: passing
    # it would silence the announcement on EVERY bench, which is precisely where
    # Evan and Pierre listen for it. The keyboard replays what a caller hears.
    reglages_annonce = await lire_annonce_ouverture(workflow.organization_id)
    # [.mark] The establishment the keyboard plays (chantier l-agent-travaille,
    # E3): no called number here, so the one chosen in the test window, else
    # the agent's first, else the organization's first. Same inheritance as a
    # call; no establishment, the same configuration comes back.
    lecture_de_lappel = await lire_lappel(
        workflow.organization_id,
        workflow_id,
        initial_context,
        # [.mark] Lot 1 d'agents-specialises (F1) : la fiche choisie par l'agent.
        fiche_choisie=run_configs.get(CLE_FICHE_DE_LAGENT),
    )
    etablissement_servi = lecture_de_lappel.servi
    # [.mark] Lot 1 d'agents-specialises (F3, C3), étendu par F-8 (Evan, 22/10) : un
    # établissement servi n'hérite de rien, quelle que soit la façon dont il a été trouvé.
    configs_heritees, origines_heritees = configuration_heritee(
        run_configs,
        etablissement_servi.etablissement if etablissement_servi else None,
    )
    reglages_annonce = annonce_heritee(
        reglages_annonce,
        etablissement_servi.etablissement if etablissement_servi else None,
    )
    if etablissement_servi is not None:
        etablissement_servi.origines.update(origines_heritees)
        initial_context["runtime_configuration"]["etablissement"] = etablissement_servi.estampille()
    initial_context = injecter_etablissement(initial_context, etablissement_servi)
    # [.mark] cloture-code, F7: the agent's objects, as for a call (read with the fiche, before the
    # sentences). Nothing changes without any, not even the stamp.
    initial_context, estampille_objets = injecter_objets(initial_context, lecture_de_lappel)
    if estampille_objets is not None:
        initial_context["runtime_configuration"]["objets"] = estampille_objets
    # [.mark] The catalogue of sentences (E5), the establishment's content first.
    initial_context = injecter_phrases(
        initial_context,
        lecture_de_lappel.phrases,
        etablissement_servi.etablissement if etablissement_servi else None,
    )
    # [.mark] The team known to the agent (chantier l-agent-collegue, C4, C5): only when
    # the agent's switch is on; nothing changes otherwise, not even the stamp.
    initial_context, estampille_equipe = injecter_equipe(
        initial_context,
        run_configs,
        lecture_de_lappel.equipe,
        lecture_de_lappel.etablissement_id,
        lecture_de_lappel.lu_depuis,
        lecture_de_lappel.noms_des_lieux,
    )
    if estampille_equipe is not None:
        initial_context["runtime_configuration"]["equipe"] = estampille_equipe
    initial_context = injecter_etat_ouverture(
        initial_context, configs_heritees, reglages=reglages_annonce
    )
    # [.mark] Date and time of the call (latence-modele D2), same moment and
    # same rule: later turns keep the values persisted by the first one.
    initial_context = injecter_date_heure_appel(initial_context)
    # [.mark] Business address (verification-communes D2, D4), same moment and
    # same rule: later turns keep the value persisted by the first one.
    adresse_etablissement = await lire_adresse_etablissement(
        configs_heritees, workflow.organization_id
    )
    initial_context = injecter_adresse_etablissement(
        initial_context, adresse_etablissement
    )
    # [.mark] The organization's trade vocabulary (plan lexique-metier, L10):
    # the keyboard bench reads a typed message like a call's. Empty when the
    # agent's switch is off, and never raises.
    lexique_metier = await lire_lexique_de_lappel(run_configs, workflow.organization_id)
    # [.mark] The establishment's own terms (E6), added to the organization's, only
    # when the agent's switch is on (an empty vocabulary stays empty).
    if etablissement_servi is not None and interrupteur_allume(run_configs):
        lexique_metier = lexique_avec_etablissement(
            lexique_metier, etablissement_servi.etablissement
        )
    initial_context = injecter_lexique_propose(
        initial_context, termes_proposes(lexique_metier)
    )
    # [.mark] The record, read once: the stamp says the note-taking mode the
    # keyboard PLAYED (plan mode-prise-de-notes), the engine gets the same.
    reglages_fiche = ReglagesFiche.depuis(run_configs, lexique=lexique_metier)
    reglages_fiche, service_greffier = preparer_le_greffier(
        reglages_fiche,
        # [.mark] Lot C d'agent-leger-greffier : la clé de bibliothèque du greffier.
        await resoudre_le_bloc_du_greffier(run_configs, workflow.organization_id),
        user_config,
        initial_context["runtime_configuration"],
    )
    estampiller_le_mode(initial_context["runtime_configuration"], reglages_fiche)
    # [.mark] passages-fiables (lot B) : le cerveau propre de l'arbitre, si son bloc est réglé (sinon le greffier).
    service_arbitre = preparer_l_arbitre(
        await resoudre_le_bloc_de_l_arbitre(run_configs, workflow.organization_id),
        user_config,
        initial_context["runtime_configuration"],
    )
    # [.mark] Quel code et quelle version de l'agent jouent l'essai (langwatch-et-fenetre-du-run, lot 2).
    estampiller_la_version(initial_context["runtime_configuration"], run_definition)

    base_checkpoint = _resolve_checkpoint_for_pending_turn(session_data, checkpoint)

    # Text sessions create a fresh pipeline for every turn. Run the Start-node
    # pre-call fetch only before the first node opening, then persist the
    # hydrated context so later per-turn pipelines reuse it without fetching
    # again. This must happen before PipecatEngine.set_node(), which renders the
    # Start-node prompt and greeting from call_context_vars.
    is_initial_node_opening = base_checkpoint.get(
        "current_node_id"
    ) is None and not any(turn.get("status") == "completed" for turn in turns[:-1])
    start_node = workflow_graph.nodes.get(workflow_graph.start_node_id)
    if (
        is_initial_node_opening
        and start_node
        and start_node.should_run_pre_call_fetch(None)
        and start_node.pre_call_fetch_url
    ):
        fetch_result = await execute_pre_call_fetch(
            url=start_node.pre_call_fetch_url,
            credential_uuid=start_node.pre_call_fetch_credential_uuid,
            call_context_vars=initial_context,
            workflow_id=workflow_id,
            organization_id=workflow.organization_id,
        )
        if fetch_result:
            initial_context = merge_external_initial_context(
                initial_context, fetch_result
            )
            # [.mark] Same reason as the telephony path: the fetch can overwrite
            # the opening state after the announcement was derived from it.
            initial_context = rafraichir_annonce(initial_context, reglages_annonce)

    await db_client.update_workflow_run(
        workflow_run_id,
        initial_context=initial_context,
    )

    embeddings_api_key = None
    embeddings_model = None
    embeddings_base_url = None
    embeddings_provider = None
    embeddings_endpoint = None
    embeddings_api_version = None
    if user_config.embeddings:
        from api.services.configuration.ai_model_configuration import (
            apply_managed_embeddings_base_url,
        )

        embeddings_api_key = user_config.embeddings.api_key
        embeddings_model = user_config.embeddings.model
        embeddings_provider = getattr(user_config.embeddings, "provider", None)
        embeddings_base_url = apply_managed_embeddings_base_url(
            provider=embeddings_provider,
            base_url=getattr(user_config.embeddings, "base_url", None),
        )
        embeddings_endpoint = getattr(user_config.embeddings, "endpoint", None)
        embeddings_api_version = getattr(user_config.embeddings, "api_version", None)

    has_recordings = await db_client.has_active_recordings(workflow.organization_id)
    context_compaction_enabled = (workflow.workflow_configurations or {}).get(
        "context_compaction_enabled", False
    )
    # Stitch every per-turn pipeline of this session into one Langfuse trace by
    # handing each task the same remote parent context (derived from the run id).
    trace_id = text_chat_trace_id(workflow_run_id)

    # [.mark] Chantier agents-specialises (lot 2) : l'agent actif de l'appel. Le
    # premier agent (celui du run) tant que le checkpoint ne dit rien d'autre.
    premier_agent = _AgentDuTour(
        workflow_id=workflow_id,
        definition_id=getattr(run_definition, "id", None),
        nom=getattr(workflow, "name", "") or "",
        graphe=workflow_graph,
        llm=llm,
        inference_llm=inference_llm,
        variable_extraction_llm=variable_extraction_llm,
        reglages=dict(run_configs),
    )

    agents_joues: set[int] = set()

    def _premier_agent_a_neuf() -> "_AgentDuTour":
        return agent_a_cerveaux_neufs(
            premier_agent,
            lambda **options: create_llm_service(
                user_config, correlation_id=mps_correlation_id, **options
            ),
            cle_de_cache(workflow_id),
            avec_extraction=needs_extraction_llm
            and user_config.llm.provider == ServiceProviders.DOGRAH.value,
        )

    async def charger_agent(actif: dict[str, Any]) -> "_AgentDuTour | None":
        """L'agent ``actif`` (après une passation), à sa définition épinglée, dans
        l'organisation de l'appel. ``None`` s'il n'est plus lisible."""
        try:
            identifiant = int(actif["workflow_id"])
            if identifiant == workflow_id and actif.get("definition_id") in (
                None,
                premier_agent.definition_id,
            ):
                if id(premier_agent) not in agents_joues:
                    return premier_agent
                # [.mark] agent-facon-tala, C3 : le premier agent a déjà joué un passage de ce tour
                # (passation puis retour au même tour). Son cerveau est un processeur arrêté avec ce
                # circuit : le remettre dans un circuit neuf, c'est un départ qui n'aboutit jamais
                # (la trame de départ ne sort pas, le tour reste bloqué). Même agent, cerveau neuf.
                return _premier_agent_a_neuf()
            agent_workflow = await db_client.get_workflow(
                identifiant, organization_id=workflow.organization_id
            )
            definition = (
                await db_client.get_workflow_definition(
                    identifiant, int(actif["definition_id"]), workflow.organization_id
                )
                if actif.get("definition_id") is not None
                else None
            )
            if agent_workflow is None or definition is None or not definition.workflow_json:
                return None
            reglages = definition.workflow_configurations or {}
            config = await get_effective_ai_model_configuration_for_workflow(
                organization_id=workflow.organization_id,
                workflow_configurations=reglages,
            )
            if config.llm is None:
                return None
            graphe = WorkflowGraph(
                ReactFlowDTO.model_validate(definition.workflow_json),
                skip_instance_constraints_for={"trigger"},
            )
            agent_llm = create_llm_service(
                config,
                correlation_id=mps_correlation_id,
                prompt_cache_key=cle_de_cache(identifiant),
            )
            agent_extraction = (
                create_llm_service(
                    config,
                    correlation_id=mps_correlation_id,
                    usage_context="variable_extraction",
                )
                if (graphe.uses_variable_extraction() or bool(call_dispositions))
                and config.llm.provider == ServiceProviders.DOGRAH.value
                else agent_llm
            )
            return _AgentDuTour(
                workflow_id=identifiant,
                definition_id=definition.id,
                nom=agent_workflow.name,
                graphe=graphe,
                llm=agent_llm,
                inference_llm=agent_llm,
                variable_extraction_llm=agent_extraction,
                reglages=dict(reglages),
                visit_id=actif.get("visit_id"),
                config=config,
            )
        except Exception as e:  # noqa: BLE001 -- le clavier reprend le premier agent
            logger.error(f"[passation] clavier : agent actif illisible ({actif}) : {e!r}")
            return None

    async def jouer_un_passage(
        agent: "_AgentDuTour",
        checkpoint_du_passage: dict[str, Any],
        pending_user_message: str | None,
        ouverture: dict[str, Any] | None,
    ) -> "_Passage":
        context = LLMContext()
        context.set_messages(
            _deserialize_text_chat_checkpoint_messages(checkpoint_du_passage["messages"])
        )
        response_window = _ResponseWindowState()

        async def send_node_transition(
            node_id: str,
            node_name: str,
            previous_node_id: str | None,
            previous_node_name: str | None,
            allow_interrupt: bool = False,
            porte: str | None = None,  # [.mark] C12 : la porte écrite (Postscript)
            agent: str | None = None,  # [.mark] agents-specialises : l'agent qui prend la main
        ) -> None:
            capture_processor.events.append(
                {
                    "type": "node_transition",
                    "created_at": datetime.now(UTC).isoformat(),
                    "payload": {
                        "node_id": node_id,
                        "node_name": node_name,
                        "previous_node_id": previous_node_id,
                        "previous_node_name": previous_node_name,
                        "allow_interrupt": allow_interrupt,
                        **({"porte_ecrite": porte} if porte else {}),
                        **({"agent": agent} if agent else {}),
                    },
                }
            )

        engine = PipecatEngine(
            llm=agent.llm,
            inference_llm=agent.inference_llm,
            variable_extraction_llm=agent.variable_extraction_llm,
            context=context,
            workflow=agent.graphe,
            call_context_vars=initial_context,
            workflow_run_id=workflow_run_id,
            node_transition_callback=send_node_transition,
            embeddings_api_key=embeddings_api_key,
            embeddings_model=embeddings_model,
            embeddings_base_url=embeddings_base_url,
            embeddings_provider=embeddings_provider,
            embeddings_endpoint=embeddings_endpoint,
            embeddings_api_version=embeddings_api_version,
            has_recordings=has_recordings,
            context_compaction_enabled=context_compaction_enabled,
            call_dispositions=call_dispositions,
            # Each text turn owns a short-lived pipeline. Complete extraction before
            # leaving a node so teardown cannot discard the result before checkpointing.
            run_transition_variable_extraction_in_background=False,
            # [.mark] C8 (correctifs-banc-34): the keyboard builds the call like the
            # voice path (`run_pipeline.py`): the record, its `noter_information`
            # tool and the end-of-call pass. Without it the keyboard measured an
            # agent that is not the one callers reach (run 896).
            # [.mark] agents-specialises (lot 3) : la fiche de l'APPEL ; un agent appelé
            # par passation y ajoute ses champs (même nom = la définition du premier).
            fiche=reglages_fiche if agent is premier_agent else fiche_fusionnee(reglages_fiche, agent.reglages),
        )
        engine._gathered_context = dict(checkpoint_du_passage["gathered_context"])
        # [.mark] Chantier agents-specialises (lot 2) : la passation au clavier. Le
        # moteur connaît l'agent qui parle, l'appel connaît ses réglages, et la
        # fabrique construit un agent appelé sans voix ni sous-circuit.
        engine.sans_sortie_audio = True
        engine.reglages_appel = dict(run_configs)
        # [.mark] cloture-code, F8 (M4): the keyboard leaves out a switched-off module's tools, like the call.
        from api.services.modules.appel import brancher_les_modules

        brancher_les_modules(engine, run_configs)
        actif = engine.active_agent
        actif.workflow_id = agent.workflow_id
        actif.definition_id = agent.definition_id
        actif.workflow_name = agent.nom
        actif.reglages = dict(agent.reglages)
        if agent.visit_id:
            actif.visit_id = agent.visit_id
        engine._transfer_outcomes = list(
            engine._gathered_context.get("agent_transfers") or []
        )
        engine.set_agent_factory(
            TextAgentFactory(
                organization_id=workflow.organization_id,
                workflow_run_id=workflow_run_id,
                use_draft=bool((getattr(workflow_run, "extra", None) or {}).get("use_draft")),
                mps_correlation_id=mps_correlation_id,
                creer_llm=lambda *a, **k: create_llm_service(*a, **k),
            )
        )
        # [.mark] agent-facon-tala, C3 bis : « Préchauffer les collègues » (éteinte par défaut), comme au
        # début d'un appel : une fois, au premier tour de la session, en fond (le tour ne l'attend pas).
        if (
            is_initial_node_opening
            and agent is premier_agent
            and prechauffer_les_collegues_actif(run_configs)
        ):
            _tache_de_fond(
                _chauffer_les_collegues_du_clavier(engine, workflow_graph, workflow_id)
            )
        # [.mark] Lot 4 d'orchestrateur-trois-cerveaux (D8) : le cerveau de fond de l'agent qui
        # parle, si son travail en arrière-plan est allumé. Au clavier il travaille dans le tour
        # et son résultat est remis au tour suivant (``travail/clavier.py``).
        await engine.preparer_le_travail(
            actif, user_config=agent.config or user_config, attacher=False
        )
        # [.mark] D1 et D10 de repliques-coupees : la trace du cerveau et la réflexion
        # de secours, comme au téléphone (réglages de l'agent qui parle : ils suivent
        # son cerveau).
        brancher_la_trace(
            engine, agent.llm, agent.reglages, getattr(agent, "workflow_name", None)
        )
        brancher_la_relance(engine, agent.llm, agent.reglages)
        capture_processor = _TextChatCaptureProcessor(response_window, context, engine)
        # [.mark] actions-sures-et-parite-clavier (A2) : les refus et reprises du modèle de conversation, comme au
        # téléphone ; au clavier ils vont aux événements du tour (pas de journal d'appel).
        brancher_le_journal_des_requetes(agent.llm, _JournalDuClavier(capture_processor))

        assistant_params = LLMAssistantAggregatorParams()
        # [.mark] Lot 3 de cloture-code : le tour vide de Pipecat 1.12, réglé comme au téléphone
        # (éteint par défaut ; sinon la paire construisait sa relance active).
        context_aggregator = LLMContextAggregatorPair(
            context,
            assistant_params=assistant_params,
            user_params=LLMUserAggregatorParams(
                empty_user_turn=collecter_reglages_tour_de_parole(
                    agent.reglages or run_configs
                ).configuration_du_tour_vide()
            ),
        )
        assistant_context_aggregator = context_aggregator.assistant()

        # [.mark] passages-fiables (R3) : le décideur unique de fin de tour (filet de fin, passage sur la fiche, arbitre,
        # sortie d'impasse), comme au téléphone.
        brancher_le_decideur_de_fin_de_tour(engine, assistant_context_aggregator, service_arbitre)

        @assistant_context_aggregator.event_handler("on_assistant_turn_started")
        async def on_assistant_turn_started(_aggregator):
            response_window.note_assistant_turn_started()

        @assistant_context_aggregator.event_handler("on_assistant_turn_stopped")
        async def on_assistant_turn_stopped(_aggregator, message):
            response_window.note_assistant_turn_stopped(message.content or "")

        # Text chat has no wire transport; reuse the neutral 16 kHz config shape
        # from the browser pipeline so TTS/recording helpers still have sane defaults.
        audio_config = create_audio_config(WorkflowRunMode.SMALLWEBRTC.value)
        pipeline_metrics_aggregator = PipelineMetricsAggregator()
        # [.mark] Lot 4 (D12) : le greffier et le cerveau de fond versent leurs jetons ici.
        engine.collecteur_de_cout = pipeline_metrics_aggregator

        conversation_parent_context = build_remote_parent_context(trace_id)
        # The stitched trace has no real root span (each per-turn conversation span
        # hangs off a synthetic remote parent), so Langfuse can't infer a name and
        # shows "Unnamed trace". Name it explicitly via the conversation span.
        trace_span_attributes = {
            "langfuse.trace.name": workflow_run.name or f"text-chat-{workflow_run_id}"
        }
        # [.mark] Plan mode-prise-de-notes (lot 5): the keyboard plays the postscript
        # like the phone (C8), right after the model, so what is captured, shown and
        # kept in memory is what the voice would have said. None outside that mode.
        post_scriptum = post_scriptum_du_moteur(engine) or greffier_du_moteur(
            engine,
            service_greffier,
            run_configs.get("greffier_consigne"),
            format_garanti_du_greffier(run_configs),
        )
        # [.mark] actions-sures-et-parite-clavier (A2) : le filtre du nom, de la civilité et de la relecture des
        # numéros, après le post-scriptum comme au téléphone : ce que le clavier montre et garde en mémoire est ce
        # que la voix aurait dit. ``None`` quand ses interrupteurs sont éteints (le défaut).
        filtre_nom_civilite = creer_filtre_nom_civilite(
            agent.reglages or run_configs,
            lambda: engine._gathered_context.get("extracted_variables", {}),
            lambda: engine._gathered_context,
            # La voix de l'appel, comme au téléphone (``agent_runtime_factory`` : ``_voix_de_l_appel``).
            voix=getattr(user_config, "tts", None),
        )
        # [.mark] passages-fiables : l'option 2 et la notice d'un tour, par les trames autour du cerveau, comme au
        # téléphone (``AgentRuntimeFactory.attach``). ``(None, None)`` pour un agent tout éteint.
        avant_le_cerveau, apres_le_cerveau = autour_du_cerveau(engine, engine.active_agent)
        pipeline = Pipeline(
            [
                p
                for p in (
                    avant_le_cerveau,
                    agent.llm,
                    apres_le_cerveau,
                    post_scriptum,
                    filtre_nom_civilite,
                    capture_processor,
                    assistant_context_aggregator,
                    pipeline_metrics_aggregator,
                )
                if p is not None
            ]
        )
        task = create_pipeline_task(
            pipeline,
            workflow_run_id,
            audio_config,
            conversation_parent_context=conversation_parent_context,
            conversation_type="text",
            additional_span_attributes=trace_span_attributes,
        )
        runner_task = asyncio.create_task(run_pipeline_worker(task))

        engine.call_worker = task
        engine.set_audio_config(audio_config)
        engine.set_transport_output(_TaskQueueProxy(task.queue_frame))
        engine.set_fetch_recording_audio(
            create_recording_audio_fetcher(
                organization_id=workflow.organization_id,
                pipeline_sample_rate=audio_config.pipeline_sample_rate,
            )
        )

        try:
            await wait_for_pipeline_worker_started(task, timeout=5.0, run_task=runner_task)

            await engine.initialize()

            if ouverture is None:
                current_node_id = checkpoint_du_passage.get("current_node_id")
                target_node_id = current_node_id or agent.graphe.start_node_id
                await engine.set_node(
                    target_node_id,
                    emit_transition_event=current_node_id is None,
                )
                previous_for_opening = current_node_id
                generate_opening = pending_user_message is None
            else:
                # [.mark] L'ouverture d'un agent appelé, mise de côté par la passation du
                # passage précédent (l'événement « passé à l'agent » est déjà parti).
                target_node_id = ouverture["node_id"]
                await engine.set_node(target_node_id, emit_transition_event=False)
                previous_for_opening = ouverture.get("previous_node_id")
                generate_opening = bool(ouverture.get("generate_if_no_greeting"))
            engine.call_monitor.activate()

            opening_marker = capture_processor.activity_count
            opening_expects_llm = generate_opening and (
                previous_for_opening == target_node_id
                or engine.get_node_greeting(target_node_id) is None
            )
            if opening_expects_llm:
                response_window.note_direct_context_request()
            opening = await engine.queue_node_opening(
                node_id=target_node_id,
                previous_node_id=previous_for_opening,
                generate_if_no_greeting=generate_opening,
            )
            if opening.action != "llm" and opening_expects_llm:
                response_window.pending_context_requests = max(
                    0, response_window.pending_context_requests - 1
                )
            if ouverture is not None:
                # [.mark] agents-specialises (lot 3, A7) : un agent appelé dont la
                # première étape porte un outil de transfert commence par le transfert.
                engine.garantir_a_l_ouverture(
                    engine.active_agent, target_node_id, getattr(opening, "playback", None)
                )
            if opening.action != "none":
                await _wait_for_quiescence(
                    capture_processor=capture_processor,
                    response_window=response_window,
                    runner_task=runner_task,
                    activity_marker=opening_marker,
                )

            if pending_user_message is not None:
                # [.mark] Caller reading on the keyboard too (nombres-dictes R5,
                # verification-communes D7), BEFORE the message enters the context:
                # the model reads it directly, there is no aggregator step here.
                # [.mark] The trade names first (T8), like in a call: the numbers
                # and the towns then read a message where "Supra" is written properly.
                message_pour_le_modele = await annoter_message_tape(
                    pending_user_message,
                    run_configs,
                    lexique_metier,
                    engine.active_agent.current_node,
                    consigner_dans(lambda: engine._gathered_context),
                )
                message_pour_le_modele = await lire_message_tape(
                    message_pour_le_modele,
                    run_configs,
                    getattr(user_config, "stt", None),
                    adresse_etablissement,
                    engine.active_agent.current_node,
                    consigner_dans(lambda: engine._gathered_context),
                    lexique=lexique_metier,
                    # [.mark] Lot 1 (11/10) : la dernière réplique de l'agent, comme au téléphone.
                    question_avant=_derniere_replique_agent(context),
                )
                # [.mark] Lot 4 d'orchestrateur-trois-cerveaux (D8) : le résultat d'un travail de
                # fond terminé au tour d'avant entre ici, avant la réplique tapée, sous la forme
                # du téléphone (``[Résultat du travail : …]``).
                remettre_les_travaux_termines(engine._gathered_context, context)
                context.add_message({"role": "user", "content": message_pour_le_modele})
                generation_marker = capture_processor.activity_count
                response_window.note_direct_context_request()
                engine.expect_response()
                # [.mark] passages-fiables : par la tête du circuit (avant le cerveau) quand elle est posée.
                await (avant_le_cerveau or agent.llm).queue_frame(LLMContextFrame(context))
                await _wait_for_quiescence(
                    capture_processor=capture_processor,
                    response_window=response_window,
                    runner_task=runner_task,
                    activity_marker=generation_marker,
                )
            # [.mark] Chantier agents-specialises : une passation ou un geste du code
            # (retour au principal, fin figée) se termine avant le démontage du tour.
            await _attendre_le_groupe(
                engine,
                capture_processor=capture_processor,
                response_window=response_window,
                runner_task=runner_task,
            )
            # [.mark] Lot 4 d'orchestrateur-trois-cerveaux : un travail de fond lancé pendant ce
            # tour finit avant le démontage (ses outils et ses sessions vivent encore) ; son
            # résultat est dans la trace et sera remis au tour suivant.
            for travail in list(engine.travaux):
                await travail.attendre()
        finally:
            try:
                if not task.has_finished():
                    await task.cancel(reason=TEXT_CHAT_INTERNAL_CANCEL_REASON)
                await runner_task
            finally:
                await engine.close_mcp_sessions()
                await engine.cleanup()

        # [.mark] A postscript note or a clerk pass still being written belongs to
        # this turn's record (the clerk waits for a second model: a longer bound).
        await attendre_les_notes(engine.notes_en_cours, delai_des_notes(engine.fiche))
        return _Passage(
            engine=engine,
            context=context,
            capture=capture_processor,
            sorties=list(response_window.outputs),
            usage=pipeline_metrics_aggregator.get_all_usage_metrics_serialized(),
        )

    # [.mark] Un tour = un passage, plus un par passation faite pendant le tour
    # (l'agent appelé ouvre sur son graphe). Sans passation : exactement le tour d'avant.
    agent_du_tour = premier_agent
    if base_checkpoint.get("agent_actif"):
        agent_du_tour = await charger_agent(base_checkpoint["agent_actif"]) or premier_agent
    passages: list[_Passage] = []
    checkpoint_du_passage = base_checkpoint
    message_du_passage = pending_user_message
    ouverture_du_passage: dict[str, Any] | None = None
    for _ in range(TEXT_CHAT_MAX_PASSAGES):
        agents_joues.add(id(agent_du_tour))
        passage = await jouer_un_passage(
            agent_du_tour, checkpoint_du_passage, message_du_passage, ouverture_du_passage
        )
        passages.append(passage)
        suite = passage.engine.ouverture_differee
        if suite is None or passage.engine.is_call_disposed():
            break
        nouvel = passage.engine.active_agent
        actif_suivant = {
            "workflow_id": nouvel.workflow_id,
            "definition_id": nouvel.definition_id,
            "visit_id": nouvel.visit_id,
            "nom": nouvel.workflow_name,
        }
        greeting = nouvel.workflow.nodes.get(suite["node_id"])
        ouvre = bool(suite.get("generate_if_no_greeting")) or (
            suite.get("previous_node_id") != suite["node_id"]
            and greeting is not None
            and bool(greeting.greeting)
        )
        if not ouvre:
            # Le nouvel agent attend la réplique de l'appelant : rien à jouer ce tour-ci.
            break
        suivant = await charger_agent(actif_suivant)
        if suivant is None:
            break
        checkpoint_du_passage = {
            **checkpoint_du_passage,
            "current_node_id": suite["node_id"],
            "messages": _serialize_text_chat_checkpoint_messages(
                passage.context.get_messages()
            ),
            "gathered_context": jsonable_encoder(await passage.engine.get_gathered_context()),
        }
        agent_du_tour = suivant
        message_du_passage = None
        ouverture_du_passage = suite

    dernier = passages[-1]
    engine = dernier.engine
    gathered_context = await engine.get_gathered_context()
    sorties = [s for p in passages for s in p.sorties if s]
    assistant_text = "\n\n".join(sorties).strip() if sorties else None
    assistant_created_at = datetime.now(UTC).isoformat()
    usage: dict[str, Any] = {}
    for p in passages:
        usage = _merge_usage_info(usage, p.usage) if len(passages) > 1 else p.usage
    current_node = engine.active_agent.current_node
    context_messages = dernier.context.get_messages()
    encoded_messages = _serialize_text_chat_checkpoint_messages(context_messages)
    encoded_gathered_context = jsonable_encoder(gathered_context)
    encoded_tool_state = jsonable_encoder(base_checkpoint.get("tool_state") or {})

    updated_checkpoint = {
        "version": TEXT_CHAT_CHECKPOINT_VERSION,
        "anchor_turn_id": pending_turn.get("id"),
        "current_node_id": current_node.id if current_node else None,
        "messages": encoded_messages,
        "gathered_context": encoded_gathered_context,
        "tool_state": encoded_tool_state,
    }
    # [.mark] L'agent qui parle, s'il n'est pas le premier : le tour suivant se
    # reconstruit sur son graphe. Absent = le premier agent (checkpoint d'avant).
    actif_final = engine.active_agent
    if actif_final.workflow_id and actif_final.workflow_id != workflow_id:
        updated_checkpoint["agent_actif"] = {
            "workflow_id": actif_final.workflow_id,
            "definition_id": actif_final.definition_id,
            "visit_id": actif_final.visit_id,
            "nom": actif_final.workflow_name,
        }

    trace_url = get_trace_url(trace_id, org_id=workflow.organization_id)
    if trace_url:
        encoded_gathered_context = {**encoded_gathered_context, "trace_url": trace_url}

    encoded_events = jsonable_encoder([e for p in passages for e in p.capture.events])
    encoded_usage = jsonable_encoder(usage)
    encoded_initial_context = jsonable_encoder(initial_context)

    return TextChatTurnExecutionResult(
        assistant_text=assistant_text,
        assistant_created_at=assistant_created_at,
        events=encoded_events,
        usage=encoded_usage,
        checkpoint=updated_checkpoint,
        gathered_context=encoded_gathered_context,
        initial_context=encoded_initial_context,
        state=(
            WorkflowRunState.COMPLETED.value
            if engine.is_call_disposed()
            else WorkflowRunState.RUNNING.value
        ),
        is_completed=engine.is_call_disposed(),
    )


async def extract_text_chat_final_disposition(
    *,
    workflow_run_id: int,
    workflow_id: int,
    organization_id: int,
    checkpoint: dict[str, Any] | None,
    session_data: dict[str, Any] | None = None,
    extracted: dict[str, Any] | None = None,
) -> str | None:
    """[.mark] agent-facon-tala, C4: the business outcome of a chat that ends without the agent's own ending
    (the person leaves, inactivity, the keyboard's end). The same classifier as a voice call's teardown
    (``DispositionExtractionService``), reading the conversation AND the record (the checkpoint's, with what the
    end-of-chat pass just wrote in ``extracted``); when the reason is not clear and the person spoke, the list's
    "unclear call" outcome if the list has one. ``None``: nothing to say. Never raises (the caller persists the
    completion after this)."""
    from api.services.workflow.disposition_extraction import DispositionExtractionService
    from api.services.workflow.issue_de_fin import issue_finale, texte_de_la_fiche

    try:
        base_checkpoint = normalize_text_chat_checkpoint(checkpoint)
        if not base_checkpoint.get("current_node_id"):
            return None
        messages = _deserialize_text_chat_checkpoint_messages(base_checkpoint["messages"])
        pending_user_message = pending_text_chat_user_message(session_data)
        if pending_user_message:
            messages = [*messages, {"role": "user", "content": pending_user_message}]
        if not any(isinstance(m, dict) and m.get("role") == "user" for m in messages):
            return None
        workflow_run, run_organization_id = await db_client.get_workflow_run_with_context(
            workflow_run_id
        )
        if (
            not workflow_run
            or workflow_run.workflow_id != workflow_id
            or workflow_run.definition is None
            or run_organization_id != organization_id
        ):
            return None
        run_configs = workflow_run.definition.workflow_configurations or {}
        options = tuple(
            WorkflowConfigurationDefaults.model_validate(
                {"call_dispositions": run_configs.get("call_dispositions") or []}
            ).call_dispositions
        )
        if not options:
            return None

        from api.services.configuration.ai_model_configuration import (
            get_effective_ai_model_configuration_for_workflow,
        )
        from api.services.managed_model_services import MPS_CORRELATION_ID_CONTEXT_KEY

        set_current_org_id(organization_id)
        user_config = await get_effective_ai_model_configuration_for_workflow(
            organization_id=organization_id, workflow_configurations=run_configs
        )
        if user_config.llm is None:
            return None
        initial_context = dict(workflow_run.initial_context or {})
        llm = create_llm_service(
            user_config,
            correlation_id=initial_context.get(MPS_CORRELATION_ID_CONTEXT_KEY),
            usage_context="variable_extraction",
        )
        context = LLMContext()
        context.set_messages(messages)
        fiche = {**(base_checkpoint.get("gathered_context") or {}), **(extracted or {})}
        service = DispositionExtractionService(
            llm=llm, context=context, options=options, template_context=initial_context
        )
        retenue = None
        try:
            async with asyncio.timeout(FINAL_EXTRACTION_TIMEOUT_SECONDS):
                retenue = await service.extract(
                    organization_id=organization_id,
                    workflow_run_id=workflow_run_id,
                    fiche=texte_de_la_fiche(ReglagesFiche.depuis(run_configs), fiche),
                )
        except asyncio.TimeoutError:
            logger.warning(
                f"Final text-chat disposition timed out after {FINAL_EXTRACTION_TIMEOUT_SECONDS}s "
                f"for run {workflow_run_id}"
            )
        return issue_finale(options, retenue, a_parle=True)
    except Exception as e:  # noqa: BLE001 -- best effort: a chat always completes
        logger.error(f"Final text-chat disposition failed for run {workflow_run_id}: {e}")
        return None


async def extract_text_chat_final_variables(
    *,
    workflow_run_id: int,
    workflow_id: int,
    organization_id: int,
    checkpoint: dict[str, Any] | None,
    session_data: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Extract the current node's variables for a chat ending without a transition.

    Voice calls get this from ``PipecatEngine._end_call``. Text chats have no
    engine at session end -- each turn tears its pipeline down -- so until this
    ran, the only extraction trigger was a node transition. A user who simply
    closes the widget never causes one, which left every abandoned chat with no
    extracted variables at all and any webhook rendered from
    ``gathered_context`` shipping blanks.

    Returns the extracted values, or an empty dict when there is nothing to
    extract. Never raises: the caller persists completion *after* this, so an
    escaping exception would leave the chat incomplete -- no transcript, no
    completion job and no webhook at all, which is worse than the blank fields
    this exists to prevent. Parsing the stored checkpoint is therefore inside
    the handler too: a legacy or corrupt shape raises from
    `normalize_text_chat_checkpoint` and `_deserialize_text_chat_checkpoint_messages`
    (which rejects unexpected shapes by design), not just from the work below.
    """
    try:
        base_checkpoint = normalize_text_chat_checkpoint(checkpoint)
        current_node_id = base_checkpoint.get("current_node_id")
        if not current_node_id:
            # No turn ever completed, so no node was entered and nothing was said.
            return {}

        messages = _deserialize_text_chat_checkpoint_messages(
            base_checkpoint["messages"]
        )
        # The checkpoint lags a turn that never finished executing; its user
        # message lives in session_data. The transcript already includes it, so
        # extraction must too or the two disagree about what was said.
        pending_user_message = pending_text_chat_user_message(session_data)
        if pending_user_message:
            messages = [*messages, {"role": "user", "content": pending_user_message}]

        if not any(
            isinstance(message, dict) and message.get("role") == "user"
            for message in messages
        ):
            # Only the greeting happened. Nothing a node could extract from.
            return {}

        # `get_workflow_run_with_context` is the unscoped system-caller read, so
        # the run is fetched by id and its ownership validated here instead --
        # the workflow_id check alone proves nothing, being derived from this
        # same row. See api/AGENTS.md, "Organization Scoping (Security)".
        (
            workflow_run,
            run_organization_id,
        ) = await db_client.get_workflow_run_with_context(workflow_run_id)
        if (
            not workflow_run
            or workflow_run.workflow_id != workflow_id
            or workflow_run.definition is None
            or workflow_run.workflow is None
        ):
            return {}
        if run_organization_id != organization_id:
            # A caller reached a run outside the organization it authorized
            # against. Nothing is extracted, and it is logged rather than
            # silently skipped because it means a bug upstream, not an
            # ordinary "nothing to extract".
            logger.warning(
                f"Refusing final text-chat extraction for run {workflow_run_id}: "
                f"run belongs to organization {run_organization_id}, "
                f"caller authorized against {organization_id}"
            )
            return {}

        workflow_graph = WorkflowGraph(
            ReactFlowDTO.model_validate(workflow_run.definition.workflow_json),
            skip_instance_constraints_for={"trigger"},
        )
        node = workflow_graph.nodes.get(current_node_id)
        run_configs = workflow_run.definition.workflow_configurations or {}
        # [.mark] C8: with the record on, the end of the chat runs the record's
        # end-of-call pass (like `_end_call` on a voice call), whatever the node
        # declares; the node's own extraction is off under the record (D28).
        fiche_allumee = bool(ReglagesFiche.depuis(run_configs))
        if not node or not (
            fiche_allumee or (node.extraction_enabled and node.extraction_variables)
        ):
            return {}

        from api.services.configuration.ai_model_configuration import (
            get_effective_ai_model_configuration_for_workflow,
        )

        # Route this extraction's spans to the org's Langfuse project, the way
        # the turn path does for every other text-chat span.
        set_current_org_id(organization_id)

        user_config = await get_effective_ai_model_configuration_for_workflow(
            organization_id=organization_id,
            workflow_configurations=run_configs,
        )
        if user_config.llm is None:
            return {}

        from api.services.managed_model_services import MPS_CORRELATION_ID_CONTEXT_KEY

        initial_context = dict(workflow_run.initial_context or {})
        # Reuse the id the conversation already billed against rather than
        # minting a new one for a run that is over.
        correlation_id = initial_context.get(MPS_CORRELATION_ID_CONTEXT_KEY)
        llm = create_llm_service(
            user_config,
            correlation_id=correlation_id,
            usage_context="variable_extraction",
        )

        context = LLMContext()
        context.set_messages(messages)
        engine = PipecatEngine(
            llm=llm,
            variable_extraction_llm=llm,
            context=context,
            workflow=workflow_graph,
            call_context_vars=initial_context,
            workflow_run_id=workflow_run_id,
            fiche=(
                ReglagesFiche.depuis(
                    run_configs,
                    # [.mark] With the establishment's terms the conversation read (L2).
                    lexique=await lexique_de_lappel_avec_etablissement(
                        run_configs, organization_id, workflow_id, initial_context
                    ),
                )
                if fiche_allumee
                else None
            ),
        )
        engine._gathered_context = dict(base_checkpoint["gathered_context"])

        async with asyncio.timeout(FINAL_EXTRACTION_TIMEOUT_SECONDS):
            extracted = await engine.extract_variables_standalone(node)
        if fiche_allumee:
            # [.mark] C8: the pass writes into the record in place, with its
            # journal; hand back what it wrote AND the record's own trail, or
            # the top-level completion merge would drop them.
            recueilli = await engine.get_gathered_context()
            extracted = {
                **(extracted or {}),
                **{
                    cle: recueilli[cle]
                    for cle in (CLE_ETAT, CLE_JOURNAL)
                    if cle in recueilli
                },
            }
        if not extracted:
            return {}

        result = {
            key: value
            for key, value in extracted.items()
            if key not in ENGINE_OWNED_CONTEXT_KEYS
        }
        # The engine merged this turn's values into the `extracted_variables`
        # it was seeded with. The completion write merges only at the top
        # level, so hand back the whole sub-dict or earlier transitions' values
        # would be dropped.
        result["extracted_variables"] = dict(
            (await engine.get_gathered_context()).get("extracted_variables") or {}
        )
        return jsonable_encoder(result)
    except asyncio.TimeoutError:
        logger.warning(
            f"Final text-chat variable extraction timed out after "
            f"{FINAL_EXTRACTION_TIMEOUT_SECONDS}s for run {workflow_run_id}"
        )
        return {}
    except Exception as e:
        # Extraction is best-effort: never block a chat from completing.
        logger.error(
            f"Final text-chat variable extraction failed for run {workflow_run_id}: {e}"
        )
        return {}

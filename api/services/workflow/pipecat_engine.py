import uuid
from dataclasses import dataclass
from typing import (
    TYPE_CHECKING,
    Awaitable,
    Callable,
    Iterable,
    Literal,
    Mapping,
    Optional,
    Sequence,
    Union,
)

from pipecat.adapters.schemas.tools_schema import ToolsSchema
from pipecat.frames.frames import (
    BotStartedSpeakingFrame,
    BotStoppedSpeakingFrame,
    CancelFrame,
    EndFrame,
    FunctionCallFromLLM,
    FunctionCallResultProperties,
    LLMRunFrame,
    SpeechBoundaryFrame,
)
from pipecat.pipeline.worker import PipelineWorker
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.services.llm_service import FunctionCallParams
from pipecat.services.settings import LLMSettings
from pipecat.utils.enums import EndTaskReason

from api.db import db_client
from api.services.annonce.constantes import OUVERT, SUR_RENDEZ_VOUS
from api.services.groupe.fiche import champs_fusionnes
from api.services.groupe.passations import (
    LIGNE_PLAFOND,
    RAISON_RETOUR,
    agent_principal_de,
    choisir_la_fin,
    est_une_etape_de_retour,
    est_une_etape_de_retour_de_l_accueil,
    etape_de_retour_du_graphe,
    est_un_groupe,
    fins_du_noeud,
    plafond_atteint,
    porte_reecrite_vers_le_retour,
)
from api.services.groupe.filet_de_fin import (
    TRACE_FILET,
    contient_une_formule,
    filet_allume,
    formules_de,
    porte_de_retour,
)
from api.services.groupe.notes import (
    note_d_aller,
    note_de_retour,
    noter_les_champs_de_l_agent,
    outil_de_passation_vers,
)
from api.services.groupe.parcours import rendre_le_parcours
from api.services.groupe.postes import memoire_du_processus_mo
from api.services.groupe.prechauffage import precharge_de, prechauffer_les_cibles
from api.services.equipe.transferts_humains import un_renvoi_a_echoue
from api.services.phrases.catalogue import MISE_EN_RELATION
from api.services.groupe.reglages_passation import (
    LIGNE_RENVOI_DEJA_ECHOUE,
    prechauffage_actif,
    renvoi_unique_actif,
)
from api.enums import ToolCategory
from api.errors.failure import (
    classify_exception,
    failure_metadata_for_processor,
    log_failure,
)
from api.schemas.workflow_configurations import CallDispositionOption
from api.services.pipecat.audio_playback import play_audio
from api.services.pipecat.call_monitor_processor import CallMonitorProcessor
from api.services.pipecat.greeting import GreetingController
from api.services.pipecat.speech_playback import (
    PlaybackOutcome,
    SpeechPlayback,
    SpeechPlaybackTracker,
)
from api.services.workflow.agent_runtime import AgentRuntime, new_visit_id
from api.services.workflow.workflow_graph import (  # [.mark] C9 : transition_tool_name
    Node,
    WorkflowGraph,
    transition_tool_name,
)

if TYPE_CHECKING:
    from pipecat.frames.frames import Frame
    from pipecat.services.anthropic.llm import AnthropicLLMService
    from pipecat.services.google.llm import GoogleLLMService
    from pipecat.services.openai.llm import OpenAILLMService
    from pipecat.utils.tracing.tracing_context import TracingContext

    LLMService = Union[OpenAILLMService, AnthropicLLMService, GoogleLLMService]

import asyncio
import time

from loguru import logger

from api.services.managed_model_services import MPS_CORRELATION_ID_CONTEXT_KEY
from api.services.workflow import pipecat_engine_callbacks as engine_callbacks
from api.services.workflow.answer_handling import ANSWER_TERMINAL_REASONS, handle_answer
from api.services.workflow.disposition_extraction import (
    CALL_DISPOSITION_CONTEXT_KEY,
    DispositionExtractionService,
)
from api.services.workflow.disposition_mapping import (
    apply_disposition_mapping,
    get_disposition_mapping,
)
from api.services.workflow.fiche_au_fil_de_leau import (
    CLE_TOUR,
    MODE_GREFFIER,
    MODE_OUTIL,
    Notices,
    ReglagesFiche,
    attendre_les_notes,
    delai_des_notes,
    balayer_la_fiche,
    brancher_noter_information,
    consigne_du_mode,
    montrer_la_fiche,
    suivre_les_tours,
)
from api.services.workflow.initial_context import GREETING_OVERRIDE_CONTEXT_KEY
from api.services.workflow.mcp_tool_session import McpToolSession
from api.services.workflow.pipecat_engine_context_composer import (
    compose_functions_for_node,
    compose_system_prompt_for_node,
)
from api.services.workflow.pipecat_engine_context_summarizer import (
    ContextSummarizationManager,
)
from api.services.workflow.pipecat_engine_custom_tools import (
    CustomToolManager,
)
from api.services.workflow.pipecat_engine_variable_extractor import (
    VariableExtractionManager,
)
from api.services.workflow.porte_parlee import (
    consigne_des_portes,
    etapes_sans_premiere_replique,
)
from api.services.workflow.tools.knowledge_base import (
    retrieve_from_knowledge_base,
)
from api.utils.template_renderer import render_template

CALL_STATUS_CONTEXT_KEY = "call_status"
# [.mark] Lot E de greffier-conversation : l'état d'ouverture injecté à l'appel
# (``etat_ouverture.CLE_ETAT``, tenu égal par un test), et la trace du transfert garanti.
CLE_ETAT_OUVERTURE = "etat_ouverture"
TRACE_TRANSFERTS_GARANTIS = "transferts_garantis"

# Gathered-context keys the engine records itself. Variable extraction merges
# its results into the same dict, so these are held back from that merge.
#
# The call disposition is recorded only by the engine, which keeps its mapped
# counterpart in sync for reporting, filters and external-PBX write-backs.
ENGINE_OWNED_CONTEXT_KEYS = frozenset(
    {
        CALL_DISPOSITION_CONTEXT_KEY,
        "mapped_call_disposition",
        CALL_STATUS_CONTEXT_KEY,
        "call_tags",
        "answer_supervisor",
    }
)

# How long the terminal extraction gets before the call is disposed of without
# it. In-pipeline cancellations funnel through `end_call_with_reason`, so this
# coroutine is now the only thing that ends the pipeline: an LLM that never
# answers would otherwise hold the call, its telephony channel and every
# service behind it open indefinitely. Measured on the abrupt-hangup path at
# p50 1.4s / p90 4.0s / max 21.3s, so this cuts off the tail and nothing else.
FINAL_EXTRACTION_TIMEOUT_SECONDS = 10.0

# [.mark] agents-specialises (revue du 16/10) : le marqueur « ce modèle porte la fiche de
# l'appel » et son suivi des tours, posés sur le modèle lui-même.
_MARQUE_FICHE = "_mark_porte_la_fiche"
_SUIVI_FICHE = "_mark_suivi_de_la_fiche"


def _marque(objet, nom):
    """[.mark] Lu dans les attributs propres de l'objet (un simulacre de test n'invente rien)."""
    return getattr(objet, "__dict__", {}).get(nom)


def _accepte_agent(rappel) -> bool:
    """[.mark] Le rappel de transition accepte-t-il ``agent=`` ? Lu sur la signature."""
    import inspect

    try:
        parametres = inspect.signature(rappel).parameters.values()
    except (TypeError, ValueError):
        return False
    return any(
        p.name == "agent" or p.kind is inspect.Parameter.VAR_KEYWORD for p in parametres
    )


@dataclass(frozen=True)
class NodeOpeningResult:
    """The opening action and the playback owned by that invocation."""

    action: Literal["none", "greeting", "llm"]
    playback: SpeechPlayback | None = None


class PipecatEngine:
    def __init__(
        self,
        *,
        task: Optional[PipelineWorker] = None,
        llm: Optional["LLMService"] = None,
        inference_llm: Optional["LLMService"] = None,
        variable_extraction_llm: Optional["LLMService"] = None,
        context: Optional[LLMContext] = None,
        workflow: WorkflowGraph,
        call_context_vars: dict,
        workflow_run_id: Optional[int] = None,
        node_transition_callback: Optional[
            Callable[[str, str, Optional[str], Optional[str], bool], Awaitable[None]]
        ] = None,
        embeddings_api_key: Optional[str] = None,
        embeddings_model: Optional[str] = None,
        embeddings_base_url: Optional[str] = None,
        embeddings_provider: Optional[str] = None,
        embeddings_endpoint: Optional[str] = None,
        embeddings_api_version: Optional[str] = None,
        has_recordings: bool = False,
        is_realtime: bool = False,
        context_compaction_enabled: bool = False,
        run_transition_variable_extraction_in_background: bool = True,
        call_dispositions: Sequence[CallDispositionOption] | None = None,
        fiche: Optional[ReglagesFiche] = None,
    ):
        self._call_worker = task
        # [.mark] La fiche au fil de l'eau : None = interrupteur éteint, rien ne change.
        # Elle s'accroche au modèle du PREMIER agent de l'appel (celui reçu ici,
        # qui devient `active_agent.llm`) : ses réglages sont ceux de cet agent.
        # Un agent reçu par transfert (éteint chez .mark) n'a pas de fiche.
        self._fiche = fiche
        self._llm_de_la_fiche = llm if fiche is not None else None
        # [.mark] Plan porte-parlee (D3) : les étapes sans première réplique, au journal.
        if fiche is not None and fiche.portes_dans_la_reponse:
            sans = etapes_sans_premiere_replique(workflow)
            if sans:
                logger.warning(
                    "[porte] étapes sans première réplique (ligne générique) : "
                    + ", ".join(sans)
                )
        # Plan mode-prise-de-notes, lot 2 : une seule relance par tour ne
        # concerne que l'outil ; sans outil, aucune note ne relance le modèle.
        self._tours_fiche = (
            suivre_les_tours(llm)
            if fiche is not None and llm is not None and fiche.mode == MODE_OUTIL
            else None
        )
        # Plan mode-prise-de-notes (D4) : sans outil, ce que la dernière note
        # demande au modèle arrive au tour suivant, par l'état de la fiche.
        self._notices_fiche = (
            Notices() if fiche is not None and fiche.mode != MODE_OUTIL else None
        )
        # Les notes du post-scriptum encore en cours, attendues avant la passe de fin.
        self.notes_en_cours: set[asyncio.Task] = set()
        # [.mark] Plan porte-parlee (D7) : les raccrochages après une porte écrite.
        self._taches_de_porte: set[asyncio.Task] = set()
        # [.mark] Plan postscriptum-note-d-abord (C3) : la réplique de l'appelant déjà
        # relancée après une réponse muette (une relance par réplique, jamais plus).
        self._replique_relancee: object = None
        # [.mark] C12 : la porte écrite qui provoque le changement d'étape en cours.
        self._porte_ecrite_annoncee: str | None = None
        # Plan mode-prise-de-notes, partie 2 : le greffier de l'appel (None hors
        # de ce mode), clos à la passe de fin.
        self.greffier = None
        # [.mark] Chantier agents-specialises (lot 3, 2A) : la fiche appartient à
        # l'APPEL. Les modèles qui la portent (le premier agent, puis chaque agent
        # appelé par passation) portent un marqueur (_MARQUE_FICHE) ; chacun voit l'état
        # de la fiche.
        if fiche is not None and llm is not None:
            self._porter_la_fiche(llm, suivi=self._tours_fiche)
        self._is_realtime = is_realtime
        # LLM used for out-of-band inference (variable extraction, context
        # summarization). Falls back to the pipeline LLM when not provided.
        # In realtime mode the pipeline LLM is a speech-to-speech service
        # that does not implement run_inference, so a separate text LLM
        # must be passed in.
        resolved_inference_llm = inference_llm or llm
        # Execution state belongs to a visit; call resources stay on the engine.
        self._active_agent: AgentRuntime = AgentRuntime(
            visit_id=new_visit_id(),
            workflow_id=0,
            definition_id=None,
            workflow_name="",
            workflow=workflow,
            llm=llm,
            inference_llm=resolved_inference_llm,
            # Variable and disposition extraction can share a separately
            # tagged managed-model client without rerouting normal
            # conversation calls.
            variable_extraction_llm=variable_extraction_llm or resolved_inference_llm,
            worker=task,
            is_realtime=is_realtime,
            entered_at=time.time(),
        )
        self._active_agent.greeting_override = (call_context_vars or {}).get(
            GREETING_OVERRIDE_CONTEXT_KEY
        )
        self._agent_on_hold = False
        self._pending_agent: AgentRuntime | None = None
        self._retired_agents: list[AgentRuntime] = []
        self._agent_visits: list[dict] = []
        self._transfer_outcomes: list[dict] = []
        # Set by run setup on every cascade call; a realtime call gets none
        # and so can never transfer.
        self._agent_factory = None
        self._transfer_coordinator = None
        # [.mark] Chantier agents-specialises (lot 2). Les réglages qui règlent l'appel
        # (ceux du premier agent : plafond de passations…), posés par le circuit ;
        # ``sans_sortie_audio`` : le clavier (ni annonce, ni musique) ; l'ouverture
        # d'un agent appelé au clavier, jouée au passage suivant ; les tâches du groupe
        # (fin figée, retour au principal) que le clavier attend avant de finir le tour.
        self.reglages_appel: dict = {}
        # [.mark] Lot 6 (A5) : le principal du groupe, resté chaud (désactivé, jamais libéré)
        # pendant qu'un spécialisé a la main ; la tâche du préchauffage (sans voix).
        self._principal_chaud: Optional[AgentRuntime] = None
        self._tache_prechauffage: Optional[asyncio.Task] = None
        self.sans_sortie_audio = False
        self.ouverture_differee: Optional[dict] = None
        self._taches_du_groupe: set[asyncio.Task] = set()
        self.context = context
        self._call_context_vars = call_context_vars
        self._workflow_run_id = workflow_run_id
        self._node_transition_callback = node_transition_callback
        self._run_transition_variable_extraction_in_background = (
            run_transition_variable_extraction_in_background
        )
        self._call_dispositions = tuple(call_dispositions or ())
        self._initialized = False
        self._call_disposed = False
        self._shutdown_task: asyncio.Task | None = None
        self._gathered_context: dict = {}
        self._response_timeout_task: Optional[asyncio.Task] = None
        self._pending_extraction_tasks: set[asyncio.Task] = set()
        # True once terminal call disposal has run its synchronous extraction.
        # Recoverable operations such as a failed transfer use a repeatable
        # flush and must not consume this one-shot finalization state.
        self._final_extraction_done: bool = False

        # Will be set later in initialize() when we have
        # access to _context
        self._variable_extraction_manager = None
        self._disposition_extraction_service: Optional[DispositionExtractionService] = (
            None
        )

        # Track current LLM reference text for TTS aggregation correction
        self._current_llm_generation_reference_text: str = ""

        # Controls whether user input should be muted
        self._mute_pipeline: bool = False
        self.answer_supervisor = None
        self._answer_user_aggregator = None

        self.speech_playback = SpeechPlaybackTracker()
        self.call_monitor = CallMonitorProcessor(
            response_source=lambda: (
                None if self.transfer_in_progress else self.active_agent.llm
            ),
            on_response_timeout=self._on_response_timeout,
            on_user_idle=self._on_user_idle,
            conversation_enabled=self._conversation_enabled,
            max_duration_end_task_callback=self.create_max_duration_callback(),
        )
        # [.mark] fiabilite-orchestration (lot 5, F7) : délai de la règle « l'appelant se tait » et
        # suspension pendant un travail de fond, lus par le moniteur.
        self.call_monitor.delai_de_relance = lambda: engine_callbacks.delai_de_la_relance(self)
        self.call_monitor.relance_suspendue = lambda: engine_callbacks.relance_suspendue(self)
        self.speech_playback.add_observer(self.call_monitor)
        self.greeting = GreetingController(self.speech_playback, lambda: self.context)

        # Tracks whether the bot is currently speaking (for allow_interrupt logic)
        self._bot_is_speaking: bool = False

        # Custom tool manager (initialized in initialize())
        self._custom_tool_manager: Optional[CustomToolManager] = None

        # Cached organization ID (resolved lazily from workflow run)
        self._organization_id: Optional[int] = None

        # The organization's disposition mapping, loaded once in initialize().
        # Held on the engine rather than fetched where it is used because the
        # two places that stamp a disposition -- set_call_disposition and
        # end_call_with_reason -- run on the teardown path, where a DB round
        # trip cannot be afforded (see end_call_with_reason). Empty means
        # "no mapping", which is the identity translation.
        self._disposition_mapping: dict[str, str] = {}

        # Embeddings configuration (passed from run_pipeline.py)
        self._embeddings_api_key: Optional[str] = embeddings_api_key
        self._embeddings_model: Optional[str] = embeddings_model
        self._embeddings_base_url: Optional[str] = embeddings_base_url
        self._embeddings_provider: Optional[str] = embeddings_provider
        self._embeddings_endpoint: Optional[str] = embeddings_endpoint
        self._embeddings_api_version: Optional[str] = embeddings_api_version

        # Audio configuration (set via set_audio_config from _run_pipeline)
        self._audio_config = None

        # Transport output processor for injecting audio directly into the
        # output, bypassing STT (set via set_transport_output from _run_pipeline)
        self._transport_output = None
        # [.mark] Lot 3 (D7) : la route locale de la parole dictée (le pont de l'appel), posée
        # par ``run_pipeline``. None (clavier, tests de l'amont) : tout passe par l'agent actif.
        self._parole_locale = None
        # [.mark] Lot 3 (D7, D18) : l'horodatage passation demandee, premier octet de voix,
        # lu au banc d'apres le chantier (jamais joue pendant).
        from api.services.groupe.mesure_passation import MesureDePassation

        self.mesure_passation = MesureDePassation()
        # [.mark] Lot 4 d'orchestrateur-trois-cerveaux (D8, D12) : le collecteur de coût de
        # l'appel (posé par le circuit : le greffier et le cerveau de fond y versent leurs
        # jetons) et les cerveaux de fond des agents de l'appel (arrêtés au nettoyage).
        self.collecteur_de_cout = None
        self.travaux: list = []
        # [.mark] fiabilite-orchestration (F15, F23) : le diseur des phrases dites par le code.
        from api.services.phrases.diseur import DiseurDePhrases

        self.phrases = DiseurDePhrases(self)

        # Recording audio fetcher (set via set_fetch_recording_audio from _run_pipeline)
        self._fetch_recording_audio = None

        # Organization-level availability; each formatted node prompt decides
        # whether to enable recording response instructions and routing.
        self._has_recordings: bool = has_recordings

        # Background context summarization on node transitions
        self._context_compaction_enabled: bool = context_compaction_enabled
        self._context_summarization_manager: Optional[ContextSummarizationManager] = (
            None
        )

    @property
    def active_agent(self) -> AgentRuntime:
        """The agent currently entitled to speak to the caller."""
        return self._active_agent

    @property
    def pending_agent(self) -> Optional[AgentRuntime]:
        """An agent prepared for a handoff that has not committed yet."""
        return self.__dict__.get("_pending_agent")

    @property
    def call_worker(self) -> Optional[PipelineWorker]:
        """The worker that lives for the whole call.

        Transport, recording, recognition, the shared aggregators and the call
        timer run here. An agent's generation stage may run in a worker of its
        own; this one outlives all of them. Not called "the task": with agent
        workers in play that name says nothing about which worker is meant,
        and ending the call, resolving the call trace and speaking a line each
        belong to a different one.
        """
        return self.__dict__.get("_call_worker")

    @call_worker.setter
    def call_worker(self, worker: Optional[PipelineWorker]) -> None:
        """Bind the call-scoped worker, which is built after the engine.

        A realtime call's only agent runs in this same worker, so binding the
        call worker also completes that agent. A cascade agent has a worker of
        its own and is left alone here.
        """
        self._call_worker = worker
        if not self._active_agent.is_child and self._active_agent.worker is None:
            self._active_agent.worker = worker

    async def _get_organization_id(self) -> Optional[int]:
        """Get and cache the organization ID from workflow run."""
        if self._organization_id is None:
            self._organization_id = (
                await db_client.get_organization_id_by_workflow_run_id(
                    self._workflow_run_id
                )
            )
        return self._organization_id

    def _get_otel_context(self):
        """Extract the OTel Context from the task's TracingContext.

        Returns the turn-level context if available, otherwise the
        conversation-level context, or None.
        """
        tracing_ctx: TracingContext | None = getattr(
            self.call_worker, "_tracing_context", None
        )
        if not tracing_ctx:
            return None
        return tracing_ctx.get_turn_context() or tracing_ctx.get_conversation_context()

    async def initialize(self):
        # TODO: May be set_node in a separate task so that we return from initialize immediately
        if self._initialized:
            logger.warning(f"{self.__class__.__name__} already initialized")
            return
        try:
            self._initialized = True

            # Helper that encapsulates variable extraction logic
            self._variable_extraction_manager = VariableExtractionManager(self)

            if self._call_dispositions:
                self._disposition_extraction_service = DispositionExtractionService(
                    llm=self.active_agent.variable_extraction_llm,
                    context=self.context,
                    options=self._call_dispositions,
                    template_context=self._call_context_vars,
                )

            # Helper that encapsulates custom tool management
            self._custom_tool_manager = CustomToolManager(self)

            # Loaded here, at call setup, so that stamping a disposition during
            # teardown stays synchronous. A failure to load leaves the identity
            # mapping in place: recording the untranslated disposition is worse
            # than the mapped one but far better than failing the call.
            try:
                self._disposition_mapping = await get_disposition_mapping(
                    await self._get_organization_id()
                )
            except Exception as e:
                logger.error(f"Error loading the organization disposition mapping: {e}")

            # Open persistent MCP server sessions for this call (degrades on failure)
            await self._open_mcp_sessions()

            # Helper that encapsulates context summarization
            if self._context_compaction_enabled:
                self._context_summarization_manager = ContextSummarizationManager(self)

            logger.debug(f"{self.__class__.__name__} initialized")
        except Exception as e:
            logger.error(f"Error initializing {self.__class__.__name__}: {e}")
            raise

    async def _update_llm_context(self, system_prompt: str, functions: list[dict]):
        """Update LLM settings with the composed system prompt and tool list."""

        # An empty node tool list must clear the previous node's tools before
        # providers update or reconnect their session.
        self.context.set_tools(ToolsSchema(standard_tools=functions))

        # For Gemini Live, set context on the LLM before _update_settings so that
        # _connect (triggered by reconnect) can read tools from it.
        if (
            hasattr(self.active_agent.llm, "_context")
            and not self.active_agent.llm._context
            and self.context
        ):
            self.active_agent.llm._context = self.context

        await self.active_agent.llm._update_settings(
            LLMSettings(system_instruction=system_prompt)
        )

    def _format_prompt(self, prompt: str) -> str:
        """Delegate prompt formatting to the shared workflow.utils implementation."""

        return render_template(prompt, self._call_context_vars)

    async def _create_transition_func(
        self,
        name: str,
        transition_to_node: str,
        transition_speech: Optional[str] = None,
        transition_speech_type: Optional[str] = None,
        transition_speech_recording_id: Optional[str] = None,
        *,
        agent: AgentRuntime | None = None,
    ):
        agent = agent or self.active_agent

        async def transition_func(function_call_params: FunctionCallParams) -> None:
            """Inner function that handles the node change tool calls"""
            logger.info(f"LLM Function Call EXECUTED: {name}")
            logger.info(
                f"Function: {name} -> transitioning to node: {transition_to_node}"
            )
            logger.info(f"Arguments: {function_call_params.arguments}")

            try:
                # Perform variable extraction before transitioning to new node
                await self._perform_variable_extraction_if_needed(
                    self.active_agent.current_node,
                    run_in_background=self._run_transition_variable_extraction_in_background,
                )

                # Queue transition speech/audio before switching nodes
                speech_type = transition_speech_type or "text"
                if (
                    speech_type == "audio"
                    and transition_speech_recording_id
                    and self._fetch_recording_audio
                ):
                    logger.info(
                        f"Playing transition audio: {transition_speech_recording_id}"
                    )
                    await self.queue_speech(
                        recording_pk=int(transition_speech_recording_id), mute_user=True
                    )
                elif transition_speech:
                    await self.queue_text_message(transition_speech, mute_user=True)

                # Set context for the new node, so that when the function call result
                # frame is received by LLMContextAggregator and an LLM generation
                # is done, we have updated context and functions
                await self.set_node(transition_to_node, origin_visit_id=agent.visit_id)

                # [.mark] Chantier agents-specialises (lot 2) : étape de retour au
                # principal (A1) ou nœud de fin aux phrases figées (A17) : c'est le
                # code qui agit, le modèle ne reparle pas (``run_llm=False``).
                principal = self._principal_du_retour(agent, transition_to_node)
                phrase_figee = (
                    None
                    if principal is not None
                    else self._phrase_de_fin_figee(agent, transition_to_node)
                )
                contexte_pret = asyncio.Event() if principal is not None else None
                geste = False
                if principal is not None:
                    geste = self._rendre_au_principal(
                        agent, principal, context_ready=contexte_pret
                    )
                elif phrase_figee is not None:
                    geste = True
                    self._mute_pipeline = True
                    self._tache_du_groupe(self._dire_la_fin_figee(agent, phrase_figee))

                is_end_node = agent.workflow.nodes[transition_to_node].is_end
                if geste:
                    pass
                elif is_end_node:
                    # Register before the tool result can trigger generation.
                    closing_speech = self.speech_playback.expect_response(
                        source=agent.llm
                    )
                    self._mute_pipeline = True
                elif self._transfert_garanti_s_applique(agent, transition_to_node):
                    # [.mark] Lot E de greffier-conversation (C4, D6) : la réponse qui
                    # suit ce résultat est la première réplique de l'étape ; une fois
                    # dite, le code lance le transfert.
                    self._lancer_le_transfert_garanti(
                        agent, transition_to_node, self._attendre_la_reponse(agent)
                    )

                async def on_context_updated() -> None:
                    """Finish an end node after its response reaches the caller."""
                    if contexte_pret is not None:
                        contexte_pret.set()
                    if is_end_node and not geste:
                        # This callback runs in its own task, leaving input audio,
                        # model generation, and transport playback free to continue.
                        # EndFrame closes realtime sessions; transport draining
                        # alone cannot recover audio the model hasn't sent yet.
                        await closing_speech.wait()
                        if self.agent_can_act(agent):
                            await self.end_call_with_reason(
                                EndTaskReason.END_CALL.value
                            )

                result = {"status": "done"}

                suivi = self._suivi_de(agent)
                relance = (
                    suivi.relance(function_call_params.tool_call_id)
                    if suivi is not None
                    else None
                )
                properties = FunctionCallResultProperties(
                    on_context_updated=on_context_updated,
                    # [.mark] Fiche : dans un tour avec une note, seul le dernier
                    # résultat relance ; None = regroupement de Pipecat, inchangé.
                    # [.mark] agents-specialises : après un geste du code, jamais.
                    run_llm=False if geste else relance,
                )

                # Call results callback from the pipecat framework
                # so that a new llm generation can be triggred if
                # required
                await function_call_params.result_callback(
                    result, properties=properties
                )

            except Exception as e:
                logger.error(f"Error in transition function {name}: {str(e)}")
                error_result = {"status": "error", "error": str(e)}
                # [.mark] Fiche : une porte en erreur ferme aussi son tour.
                suivi = self._suivi_de(agent)
                relance = (
                    suivi.relance(function_call_params.tool_call_id)
                    if suivi is not None
                    else None
                )
                await function_call_params.result_callback(
                    error_result,
                    properties=None
                    if relance is None
                    else FunctionCallResultProperties(run_llm=relance),
                )

        return agent.bind_tool(self, transition_func)

    # --- [.mark] Plan porte-parlee (lot 4) : la porte écrite dans la réponse ---

    def _porte_de_l_etape(self, nom: str):
        """L'arête de l'étape en cours dont le nom de porte est ``nom``, ou None.
        Le code ne choisit jamais : il retrouve la porte écrite, ou rien."""
        node = self.active_agent.current_node
        if node is None or node.is_end:
            return None
        arete = next((e for e in node.out_edges if e.get_function_name() == nom), None)
        if arete is not None:
            return arete
        # [.mark] Plan postscriptum-note-d-abord (C9, run 1041) : le modèle écrit le NOM
        # DE L'ÉTAPE d'arrivée (« → coordonnees ») au lieu de celui de la porte. Une
        # seule porte de l'étape y mène : c'est elle, sans ambiguïté. Deux ou plus :
        # rien (le code ne choisit jamais entre deux portes). Formulaire du lot 4
        # (Evan, 08/10) : en « porte, note, phrase » seulement.
        if not getattr(self.fiche, "note_d_abord", False):
            return porte_reecrite_vers_le_retour(self.active_agent.workflow, node, nom)
        vers_l_etape = [
            e
            for e in node.out_edges
            if transition_tool_name(self.active_agent.workflow.nodes[e.target].name) == nom
        ]
        if len(vers_l_etape) == 1:
            logger.info(f"[porte] « {nom} » est le nom d'une étape : sa seule porte est prise")
            return vers_l_etape[0]
        return porte_reecrite_vers_le_retour(self.active_agent.workflow, node, nom)

    def porte_vers_une_fin_figee(self, nom: str) -> bool:
        """C4 (banc du 16/10) : la porte écrite ``nom`` mène-t-elle à un nœud de fin aux phrases
        figées (A17) ? Le lecteur de portes tait alors la suite de la réponse. ⛔ Ne lève jamais."""
        try:
            arete = self._porte_de_l_etape(nom)
            if arete is None:
                return False
            cible = self.active_agent.workflow.nodes.get(arete.target)
            return bool(
                cible is not None
                and cible.is_end
                and self._phrase_de_fin_figee(self.active_agent, arete.target) is not None
            )
        except Exception:  # noqa: BLE001
            return False

    def est_une_porte_de_l_etape(self, nom: str) -> bool:
        """[.mark] Revue du 11/10 (Q4) : ``nom`` désigne-t-il une porte de l'étape en cours ?
        ⛔ Ne lève jamais."""
        try:
            return self._porte_de_l_etape(nom) is not None
        except Exception:  # noqa: BLE001
            return False

    def phrase_de_transition_ecrite(self, nom: str) -> Optional[str]:
        """D16 : la phrase de transition ÉCRITE de la porte ``nom`` (le processeur
        la pousse avant la phrase du modèle). Un enregistrement audio : None, il
        est joué au changement d'étape."""
        arete = self._porte_de_l_etape(nom)
        if arete is None or (arete.data.transition_speech_type or "text") != "text":
            return None
        return arete.transition_speech or None

    async def prendre_porte_ecrite(
        self,
        nom: str,
        *,
        transition_dite: bool = False,
        reponse: Optional[str] = None,
        relancer: bool = False,
    ) -> str:
        """D6 : la porte ``nom`` écrite par le modèle, prise à la fin de sa réponse
        (interruption comprise), comme ``_create_transition_func`` mais sans
        résultat de fonction ni relance : la phrase dite est la première réplique.

        ``transition_dite`` : la phrase de transition écrite est déjà partie (D16).
        ``reponse`` : l'identifiant de lecture de la réponse en cours ; vers une
        étape de fin, c'est elle la phrase de fin (D7) : on attend qu'elle soit
        jouée, puis on raccroche. ``relancer`` : la réponse n'a rien dit ; le
        modèle reparle dans la nouvelle étape (comme une porte appelée en fonction).

        Rend l'état pour la trace : ``prise``, ``inconnue`` ou ``echec``.
        ⛔ Ne lève jamais : une porte mal écrite ne coûte pas l'appel."""
        agent = self.active_agent
        arete = self._porte_de_l_etape(nom)
        if arete is None:
            logger.warning(f"[porte] « {nom} » n'est pas une porte de l'étape : rien")
            return "inconnue"
        try:
            logger.info(f"[porte] porte écrite prise : {nom} -> {arete.target}")
            # [.mark] Lot 7 (K1) : une porte réécrite vers l'étape de retour laisse sa trace.
            cible_dite = agent.workflow.nodes[arete.target]
            if arete.get_function_name() != nom and est_une_etape_de_retour(cible_dite):
                if transition_tool_name(cible_dite.name) != nom:
                    self._gathered_context.setdefault("porte_reecrite", []).append(
                        {
                            "ecrite": nom,
                            "etape": getattr(agent.current_node, "name", None),
                            "vers": cible_dite.name,
                            "tour": self._gathered_context.get(CLE_TOUR),
                        }
                    )
            await self._perform_variable_extraction_if_needed(
                agent.current_node,
                run_in_background=self._run_transition_variable_extraction_in_background,
            )
            if (
                (arete.data.transition_speech_type or "text") == "audio"
                and arete.data.transition_speech_recording_id
                and self._fetch_recording_audio
            ):
                await self.queue_speech(
                    recording_pk=int(arete.data.transition_speech_recording_id),
                    mute_user=True,
                )
            elif arete.transition_speech and not transition_dite:
                await self.queue_text_message(arete.transition_speech, mute_user=True)
            fin = agent.workflow.nodes[arete.target].is_end
            # [.mark] Plan postscriptum-note-d-abord (C4, Q5, run 1034) : l'étape d'arrivée
            # porte un outil (un transfert) : une fois la phrase d'arrivée jouée, le modèle
            # reparle UNE fois dans cette étape pour l'appeler, sans attendre la personne.
            # Revue du 08/10 : en « porte, note, phrase » seulement (comportement d'avant).
            # [.mark] Lot E de greffier-conversation (C4, D6) : case allumée, entreprise
            # ouverte (``OUVERT``), c'est le code qui lance le transfert.
            garanti = not fin and self._transfert_garanti_s_applique(agent, arete.target)
            outil_a_l_arrivee = (
                not fin
                and not relancer
                and getattr(self._fiche, "note_d_abord", False)
                and bool(agent.workflow.nodes[arete.target].tool_uuids)
            )
            phrase_d_arrivee = (
                self.speech_playback.suivre_une_reponse(reponse)
                if outil_a_l_arrivee and reponse
                else None
            )
            phrase_de_fin = (
                self.speech_playback.suivre_une_reponse(reponse)
                if fin and reponse and not relancer
                else None
            )
            phrase_garantie = (
                self.speech_playback.suivre_une_reponse(reponse)
                if garanti and reponse and not relancer
                else None
            )
            # [.mark] Chantier agents-specialises (A17) : un nœud de fin aux phrases
            # figées ne demande aucune réponse au modèle.
            phrase_figee = self._phrase_de_fin_figee(agent, arete.target) if fin else None
            # Comme `_create_transition_func` : l'attente de la réponse de fin est
            # posée avant de changer d'étape, jamais après (revue du 05/10).
            closing = (
                self.speech_playback.expect_response(source=agent.llm)
                if fin and relancer and phrase_figee is None
                else None
            )
            # C12 : le nom de la porte part avec l'événement du changement d'étape.
            self._porte_ecrite_annoncee = arete.get_function_name()
            try:
                await self.set_node(arete.target, origin_visit_id=agent.visit_id)
            finally:
                self._porte_ecrite_annoncee = None
            # [.mark] Chantier agents-specialises (lot 2) : retour au principal (A1),
            # ou fin figée (A17) dite après la réplique en cours, sans relance du modèle.
            principal = self._principal_du_retour(agent, arete.target)
            if principal is not None and self._rendre_au_principal(agent, principal):
                return "prise"
            if phrase_figee is not None:
                self._mute_pipeline = True
                self._tache_du_groupe(
                    self._dire_la_fin_figee(agent, phrase_figee, avant=phrase_de_fin)
                )
                return "prise"
            if fin and not relancer:
                self._mute_pipeline = True

                async def raccrocher() -> None:
                    if phrase_de_fin is not None:
                        await phrase_de_fin.wait()
                    if self.agent_can_act(agent):
                        await self.end_call_with_reason(EndTaskReason.END_CALL.value)

                tache = asyncio.get_running_loop().create_task(raccrocher())
                self._taches_de_porte.add(tache)
                tache.add_done_callback(self._taches_de_porte.discard)
            elif garanti and not relancer:
                # Revue du 13/10 : sans outil de transfert dans l'étape, le repli est la
                # relance d'avant (« outil à l'arrivée »), jamais un silence.
                self._lancer_le_transfert_garanti(
                    agent, arete.target, phrase_garantie, repli=outil_a_l_arrivee
                )
            elif outil_a_l_arrivee:

                async def appeler_l_outil() -> None:
                    if phrase_d_arrivee is not None:
                        await phrase_d_arrivee.wait()
                    if self.agent_can_act(agent):
                        logger.info("[porte] étape d'arrivée avec un outil : le modèle reparle")
                        await agent.queue_frame(LLMRunFrame())

                tache = asyncio.get_running_loop().create_task(appeler_l_outil())
                self._taches_de_porte.add(tache)
                tache.add_done_callback(self._taches_de_porte.discard)
            elif relancer:
                if closing is not None:
                    self._mute_pipeline = True

                    async def raccrocher_apres() -> None:
                        await closing.wait()
                        if self.agent_can_act(agent):
                            await self.end_call_with_reason(
                                EndTaskReason.END_CALL.value
                            )

                    tache = asyncio.get_running_loop().create_task(raccrocher_apres())
                    self._taches_de_porte.add(tache)
                    tache.add_done_callback(self._taches_de_porte.discard)
                if garanti:
                    # La première réplique de l'étape sera celle que le modèle va dire.
                    self._lancer_le_transfert_garanti(
                        agent, arete.target, self._attendre_la_reponse(agent)
                    )
                await agent.queue_frame(LLMRunFrame())
            return "prise"
        except Exception as e:  # noqa: BLE001 -- une porte ne coûte jamais l'appel
            logger.error(f"[porte] porte écrite « {nom} » en échec : {e!r}")
            return "echec"

    # --- [.mark] Lot E de greffier-conversation (C4, D6) : le transfert garanti ---

    def _transfert_garanti_s_applique(self, agent: AgentRuntime, cible: str) -> bool:
        """Case allumée, agent qui porte la fiche, étape d'arrivée (hors fin) qui porte des
        outils, entreprise ``OUVERT`` à l'appel (ses horaires). ⛔ Ne lève jamais."""
        try:
            if self._fiche is None or not self._fiche.transfert_garanti:
                return False
            if not self._porte_la_fiche(agent):
                return False
            noeud = agent.workflow.nodes.get(cible)
            if noeud is None or noeud.is_end or not noeud.tool_uuids:
                return False
            # [.mark] Lot 6 (A7) : un seul renvoi vers un humain par appel : un renvoi déjà
            # échoué, et le transfert garanti ne repart pas (tout agent de l'appel).
            if self._un_renvoi_a_deja_echoue():
                return False
            return (self._call_context_vars or {}).get(CLE_ETAT_OUVERTURE) == OUVERT
        except Exception as e:  # noqa: BLE001
            logger.error(f"[transfert] garantie illisible : {e!r}")
            return False

    def _un_renvoi_a_deja_echoue(self) -> bool:
        """[.mark] Lot 6 (A7) : réglage « un seul renvoi par appel » allumé (vrai par défaut
        dans un groupe) et un transfert vers un humain a déjà échoué dans cet appel
        (``transferts_humains``, écrit à chaque issue). ⛔ Ne lève jamais."""
        try:
            return renvoi_unique_actif(self.reglages_appel) and un_renvoi_a_echoue(
                self._gathered_context
            )
        except Exception:  # noqa: BLE001
            return False

    def _attendre_la_reponse(self, agent: AgentRuntime):
        """La prochaine réponse du modèle, suivie AVANT d'être demandée ; ``None`` si une
        autre est déjà attendue (le transfert part alors sans attendre de phrase)."""
        try:
            return self.speech_playback.expect_response(source=agent.llm)
        except RuntimeError:
            logger.warning("[transfert] une réponse est déjà attendue : pas d'attente")
            return None

    async def _outil_de_transfert(self, noeud) -> Optional[str]:
        """Le nom de fonction du premier outil de transfert d'appel de l'étape qui se lance
        sans paramètre (destination fixe) ; ``None`` sinon."""
        from api.services.workflow.tools.custom_tool import tool_to_function_schema

        organisation = await self._get_organization_id()
        if not organisation:
            return None
        outils = await self.lire_outils(list(noeud.tool_uuids), organisation)
        for outil in outils:
            if outil.category != ToolCategory.TRANSFER_CALL.value:
                continue
            fonction = tool_to_function_schema(outil)["function"]
            if (fonction.get("parameters") or {}).get("required"):
                logger.info(
                    f"[transfert] {fonction['name']} demande des paramètres : laissé au modèle"
                )
                continue
            return fonction["name"]
        return None

    def _suivre_les_appels(self, llm) -> None:
        """Revue du 13/10 : les fonctions que le modèle appelle, relevées à l'instant où il
        les appelle (``on_function_calls_started``), et non quand l'appel entre dans la
        conversation (plus tard, par une tâche à part). Une fois par service."""
        if not hasattr(self, "_fonctions_appelees"):
            self._fonctions_appelees: list[str] = []
            self._services_suivis: set[int] = set()
        if id(llm) in self._services_suivis or not hasattr(llm, "add_event_handler"):
            return
        self._services_suivis.add(id(llm))

        async def relever(_service, appels) -> None:
            self._fonctions_appelees.extend(
                getattr(appel, "function_name", None) for appel in appels or []
            )

        llm.add_event_handler("on_function_calls_started", relever)

    def _appels_depuis(self, debut: int, depuis_appels: int) -> tuple[set[str], bool]:
        """Depuis l'arrivée : les fonctions appelées par le modèle, et si la personne a
        parlé (sa réplique dans la conversation)."""
        messages = self.context.get_messages()[debut:] if self.context else []
        appelees = set(getattr(self, "_fonctions_appelees", [])[depuis_appels:])
        appelees |= {
            (appel.get("function") or {}).get("name")
            for message in messages
            if message.get("role") == "assistant"
            for appel in message.get("tool_calls") or []
        }
        return appelees, any(m.get("role") == "user" for m in messages)

    def _tracer_le_transfert(self, **detail) -> None:
        try:
            self._gathered_context.setdefault(TRACE_TRANSFERTS_GARANTIS, []).append(
                {"tour": self._gathered_context.get(CLE_TOUR), **detail}
            )
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[transfert] trace non écrite : {e!r}")

    def _lancer_le_transfert_garanti(
        self,
        agent: AgentRuntime,
        cible: str,
        phrase,
        *,
        repli: bool = False,
        a_l_ouverture: bool = False,
    ) -> None:
        """Une fois la première réplique de l'étape ``cible`` JOUÉE jusqu'au bout
        (``phrase``), le code appelle l'outil de transfert comme le modèle l'aurait appelé.
        Rien si la réplique a été coupée, n'a pas été jouée ou n'a pas pu être suivie (revue
        du 13/10 : la personne parle peut-être, le modèle lui répondra), si l'agent ne peut
        plus agir, si l'étape a changé, si le modèle l'a appelé lui-même ou si la personne a
        parlé. Sans outil de transfert dans l'étape et ``repli`` : la relance d'avant
        (« outil à l'arrivée »).

        ``a_l_ouverture`` (arrivée d'un agent appelé, phrase figée dite par le code, aucun tour
        du modèle demandé) : sans ``phrase``, le transfert part tout de suite (l'outil dit lui-même
        son message) ; et quand le transfert ne peut pas partir, le modèle reprend la parole au
        lieu d'un silence. ⛔ Ne lève jamais."""
        debut = len(self.context.get_messages()) if self.context else 0
        self._suivre_les_appels(agent.llm)
        depuis_appels = len(self._fonctions_appelees)

        async def transferer() -> None:
            try:
                noeud = agent.workflow.nodes[cible]
                nom = await self._outil_de_transfert(noeud)
                async def reprendre_la_parole() -> None:
                    if self.agent_can_act(agent):
                        logger.info("[transfert] étape d'arrivée sans transfert lancé : le modèle reparle")
                        await agent.queue_frame(LLMRunFrame())

                if nom is None:
                    self._tracer_le_transfert(etape=noeud.name, etat="sans_outil")
                    if repli or a_l_ouverture:
                        if phrase is not None:
                            await phrase.wait()
                        await reprendre_la_parole()
                    return
                if phrase is None and not a_l_ouverture:
                    self._tracer_le_transfert(etape=noeud.name, outil=nom, etat="sans_attente")
                    return
                if phrase is not None and not await phrase.wait():
                    issue = phrase.outcome
                    self._tracer_le_transfert(
                        etape=noeud.name,
                        outil=nom,
                        etat="replique_non_jouee",
                        issue=getattr(issue, "value", str(issue)),
                    )
                    if a_l_ouverture:
                        await reprendre_la_parole()
                    return
                if not self.agent_can_act(agent):
                    return
                courant = agent.current_node
                if courant is None or courant.id != cible:
                    self._tracer_le_transfert(etape=noeud.name, outil=nom, etat="etape_quittee")
                    return
                appelees, a_parle = self._appels_depuis(debut, depuis_appels)
                if nom in appelees:
                    self._tracer_le_transfert(etape=noeud.name, outil=nom, etat="par_le_modele")
                    return
                if a_parle:
                    self._tracer_le_transfert(etape=noeud.name, outil=nom, etat="personne_a_parle")
                    return
                logger.info(f"[transfert] {nom} lancé par le code à l'arrivée dans {noeud.name}")
                await agent.llm.run_function_calls(
                    [
                        FunctionCallFromLLM(
                            function_name=nom,
                            tool_call_id=f"mark_transfert_{uuid.uuid4().hex[:12]}",
                            arguments={},
                            context=self.context,
                        )
                    ]
                )
                self._tracer_le_transfert(etape=noeud.name, outil=nom, etat="lance")
            except Exception as e:  # noqa: BLE001 -- un transfert ne coûte jamais l'appel
                logger.error(f"[transfert] transfert garanti en échec : {e!r}")

        tache = asyncio.get_running_loop().create_task(transferer())
        self._taches_de_porte.add(tache)
        tache.add_done_callback(self._taches_de_porte.discard)

    # --- [.mark] Chantier agents-specialises (lot 2) : retour au principal, fins figées ---

    def _principal_du_retour(self, agent: AgentRuntime, cible: str) -> Optional[int]:
        """L'agent principal vers qui rendre l'appel, si ``cible`` est une étape marquée
        « retour au principal » chez un agent qui a un principal (A1) ; ``None`` sinon
        (comportement d'avant). ⛔ Ne lève jamais."""
        try:
            noeud = agent.workflow.nodes.get(cible)
            if noeud is None or noeud.is_end or not est_une_etape_de_retour(noeud):
                return None
            principal = agent_principal_de(agent.reglages)
            if principal is None or principal == agent.workflow_id:
                return None
            if not self.agent_transfer_enabled:
                logger.warning("[groupe] étape de retour, mais aucune passation possible ici")
                return None
            return principal
        except Exception as e:  # noqa: BLE001
            logger.error(f"[groupe] retour au principal illisible : {e!r}")
            return None

    def _phrase_de_fin_figee(self, agent: AgentRuntime, cible: str) -> Optional[str]:
        """La phrase de fin choisie par le code (A17) si ``cible`` est un nœud de fin qui
        porte une liste ``fins`` ; ``None`` sinon (comportement d'avant). ⛔ Ne lève jamais."""
        try:
            noeud = agent.workflow.nodes.get(cible)
            if noeud is None or not noeud.is_end:
                return None
            fins = fins_du_noeud(noeud)
            if not fins:
                return None
            phrase = choisir_la_fin(fins, self._gathered_context)
            return self._format_prompt(phrase) if phrase else None
        except Exception as e:  # noqa: BLE001
            logger.error(f"[groupe] phrases de fin illisibles : {e!r}")
            return None

    def _tache_du_groupe(self, coroutine) -> None:
        taches = self.__dict__.setdefault("_taches_du_groupe", set())
        tache = asyncio.get_running_loop().create_task(coroutine)
        taches.add(tache)
        tache.add_done_callback(taches.discard)

    def _debut_de_la_derniere_etape(self, agent: AgentRuntime) -> Optional[int]:
        """Après le banc du 16/10 (décision d'Evan) : au retour, le principal ne reçoit que les
        échanges de la DERNIÈRE étape du spécialisé (celle de « autre chose ? », entière, au cas
        où une réplique est coupée en deux) et la fiche, jamais toute la conversation. Rend
        l'indice où cette étape commence dans la conversation, lu dans ``parcours_etapes`` (le
        clavier le garde d'un tour à l'autre) ; ``None`` (toute la conversation, comme avant)
        si l'étape n'est pas retrouvée. ⛔ Ne lève jamais."""
        try:
            for entree in reversed(self._gathered_context.get("parcours_etapes") or []):
                if entree.get("agent_id") != agent.workflow_id:
                    break
                noeud = next(
                    (n for n in agent.workflow.nodes.values() if n.name == entree.get("etape")),
                    None,
                )
                if noeud is not None and est_une_etape_de_retour(noeud):
                    continue
                debut = entree.get("debut")
                return debut if isinstance(debut, int) and debut >= 0 else None
            return None
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[groupe] début de la dernière étape illisible : {e!r}")
            return None

    def _rendre_au_principal(
        self, agent: AgentRuntime, principal: int, *, context_ready=None
    ) -> bool:
        """Le code passe la main au principal : ni annonce, ni musique, historique sans
        résumé ; le principal ne parle que si le dernier mot est à l'appelant (A1, A21).
        Rend ``False`` si la passation n'a pas pu partir. ⛔ Ne lève jamais."""
        try:
            from api.services.workflow.agent_transfer import TransferRequest

            request = TransferRequest(
                destination_workflow_id=principal,
                destination_label=RAISON_RETOUR,
                origin_visit_id=agent.visit_id,
                announcement=None,
                play_greeting=False,
                silencieuse=True,
                sans_resume=True,
                ouverture="si_l_appelant_attend",
                raison=RAISON_RETOUR,
                depuis=self._debut_de_la_derniere_etape(agent),
                etape_de_retour=True,
            )
            if not self.transfer_coordinator.accept(request):
                logger.warning("[groupe] retour au principal refusé : une passation est en cours")
                return False
            logger.info(f"[groupe] retour au principal {principal} lancé par le code")
            self.transfer_coordinator.start(request, context_ready=context_ready)
            return True
        except Exception as e:  # noqa: BLE001 -- un retour ne coûte jamais l'appel
            logger.error(f"[groupe] retour au principal en échec : {e!r}")
            return False

    def etat_pour_le_filet(self) -> tuple:
        """[.mark] Lot 2 d'orchestrateur-trois-cerveaux (B2) : où l'on est au début d'une réplique
        (l'agent qui a la main, son étape) ; si cela change avant la fin, une porte a été prise."""
        agent = self.active_agent
        return (agent.visit_id, getattr(agent.current_node, "id", None))

    async def filet_de_fin(self, texte: str, depart: tuple | None) -> bool:
        """[.mark] Lot 2 d'orchestrateur-trois-cerveaux (B2, D5) : le filet de fin d'appel d'un
        collègue. Sa réplique contient une formule de fin, il n'a pris aucune porte pendant elle : le
        code prend la sortie « retour » (l'accueil conclut depuis son étape de retour). Case par agent,
        éteinte par défaut ; rien hors d'un groupe. Rend ``True`` si la porte a été prise.
        ⛔ Ne lève jamais."""
        try:
            agent = self.active_agent
            if depart is None or not (texte or "").strip():
                return False
            if not self.agent_transfer_enabled or not self.agent_can_act(agent):
                return False
            if not filet_allume(agent.reglages) or depart != self.etat_pour_le_filet():
                return False
            if self.transfer_coordinator.in_progress:
                return False
            arete = porte_de_retour(agent.current_node, agent.workflow)
            if arete is None:
                return False
            if not contient_une_formule(texte, formules_de(self._call_context_vars)):
                return False
            logger.info("[filet] formule de fin sans porte : le code prend la sortie retour")
            cible = agent.workflow.nodes[arete.target]
            self._gathered_context.setdefault("porte_reecrite", []).append(
                {
                    "ecrite": TRACE_FILET,
                    "etape": getattr(agent.current_node, "name", None),
                    "vers": cible.name,
                    "tour": self._gathered_context.get(CLE_TOUR),
                }
            )
            return await self.prendre_porte_ecrite(arete.get_function_name()) == "prise"
        except Exception as e:  # noqa: BLE001 -- un filet ne coûte jamais l'appel
            logger.error(f"[filet] fin d'appel en échec : {e!r}")
            return False

    async def _dire_la_fin_figee(self, agent: AgentRuntime, phrase: str, avant=None) -> None:
        """Après la réplique en cours (``avant``), le code dit la phrase de fin telle
        quelle, puis raccroche (A17). ⛔ Ne lève jamais."""
        try:
            if avant is not None:
                await avant.wait()
            if not self.agent_can_act(agent):
                # Revue du 16/10 : l'appelant de la fin figée a coupé le pipeline ; un autre
                # agent a la main, l'appel ne doit pas rester muet.
                self._mute_pipeline = False
                return
            self._mute_pipeline = True
            speech = await self.queue_speech(phrase, append_to_context=True, mute_user=True)
            await speech.wait()
            if self.agent_can_act(agent):
                await self.end_call_with_reason(EndTaskReason.END_CALL.value)
        except Exception as e:  # noqa: BLE001
            logger.error(f"[groupe] fin figée en échec : {e!r}")
            if self.agent_can_act(agent):
                await self.end_call_with_reason(EndTaskReason.END_CALL.value)

    async def relancer_une_reponse_muette(self) -> bool:
        """[.mark] C3 (banc du 07/10, blancs de 8 à 13 s) : la réponse du modèle n'a
        rien dit et n'a pris aucune porte (une note seule) : le modèle reparle, UNE
        fois par réplique de l'appelant. Rend ``True`` si la relance est partie.
        ⛔ Ne lève jamais."""
        try:
            replique = self._gathered_context.get(CLE_TOUR)
            if replique is None and self.context is not None:
                replique = sum(
                    1 for m in self.context.get_messages() if m.get("role") == "user"
                )
            if replique is not None and replique == self._replique_relancee:
                logger.info("[porte] réponse muette déjà relancée à cette réplique : rien")
                return False
            self._replique_relancee = replique
            logger.info("[porte] réponse sans phrase ni porte : le modèle reparle")
            await self.active_agent.queue_frame(LLMRunFrame())
            return True
        except Exception as e:  # noqa: BLE001 -- une relance ne coûte jamais l'appel
            logger.error(f"[porte] relance d'une réponse muette en échec : {e!r}")
            return False

    async def _register_transition_function_with_llm(
        self,
        name: str,
        transition_to_node: str,
        transition_speech: Optional[str] = None,
        transition_speech_type: Optional[str] = None,
        transition_speech_recording_id: Optional[str] = None,
        *,
        agent: AgentRuntime | None = None,
    ):
        agent = agent or self.active_agent
        logger.debug(
            f"Registering function {name} to transition to node {transition_to_node} with LLM"
        )

        # Create transition function
        transition_func = await self._create_transition_func(
            name,
            transition_to_node,
            transition_speech,
            transition_speech_type,
            transition_speech_recording_id,
            agent=agent,
        )

        # Register function with LLM
        agent.llm.register_function(
            name,
            transition_func,
            is_node_transition=True,
        )

    async def _register_knowledge_base_function(
        self, document_uuids: list[str], *, agent: AgentRuntime | None = None
    ) -> None:
        """Register knowledge base retrieval function with the LLM.

        Args:
            document_uuids: List of document UUIDs to filter the search by
        """
        logger.debug(
            f"Registering knowledge base retrieval function with {len(document_uuids)} document(s)"
        )

        agent = agent or self.active_agent

        async def retrieve_kb_func(function_call_params: FunctionCallParams) -> None:
            logger.info("LLM Function Call EXECUTED: retrieve_from_knowledge_base")
            logger.info(f"Arguments: {function_call_params.arguments}")

            try:
                query = function_call_params.arguments.get("query", "")
                organization_id = await self._get_organization_id()

                if not organization_id:
                    raise ValueError(
                        "Organization ID not available for knowledge base retrieval"
                    )

                result = await retrieve_from_knowledge_base(
                    query=query,
                    organization_id=organization_id,
                    document_uuids=document_uuids,
                    limit=3,  # Return top 3 most relevant chunks
                    embeddings_api_key=self._embeddings_api_key,
                    embeddings_model=self._embeddings_model,
                    embeddings_base_url=self._embeddings_base_url,
                    embeddings_provider=self._embeddings_provider,
                    embeddings_endpoint=self._embeddings_endpoint,
                    embeddings_api_version=self._embeddings_api_version,
                    correlation_id=self._call_context_vars.get(
                        MPS_CORRELATION_ID_CONTEXT_KEY
                    ),
                    tracing_context=self._get_otel_context(),
                )

                await function_call_params.result_callback(result)

            except Exception as e:
                logger.error(f"Knowledge base retrieval failed: {e}")
                await function_call_params.result_callback(
                    {"error": str(e), "chunks": [], "query": query, "total_results": 0}
                )

        # Register the function with the LLM
        agent.llm.register_function(
            "retrieve_from_knowledge_base", agent.bind_tool(self, retrieve_kb_func)
        )

    async def _perform_variable_extraction_if_needed(
        self,
        node: Optional[Node],
        run_in_background: bool = True,
    ) -> Optional[dict]:
        """Perform variable extraction if the node has extraction enabled.

        Args:
            node: The node to extract variables from.
            run_in_background: If True, runs extraction as a fire-and-forget task.
                If False, awaits the extraction synchronously.
        """
        if not (node and node.extraction_enabled and node.extraction_variables):
            return
        # [.mark] D28 : interrupteur allumé, la fiche s'écrit par l'outil ; la
        # relecture étape par étape réécrirait une correction déjà notée.
        # ⛔ Signature inchangée : des doublures de test de l'amont l'enveloppent.
        if self._fiche_sur_l_agent_actif():
            return None

        # Capture the current turn context for otel tracing
        # before creating the background task.
        parent_context = self._get_otel_context()

        extraction_prompt = self._format_prompt(node.extraction_prompt)
        node_variables = [
            variable
            for variable in node.extraction_variables
            if variable.name not in ENGINE_OWNED_CONTEXT_KEYS
        ]
        if not node_variables:
            logger.debug(
                f"No LLM-derived variables configured for node: {node.name}; "
                "skipping variable extraction"
            )
            return None
        extraction_variables = [
            (
                v.model_copy(update={"prompt": self._format_prompt(v.prompt)})
                if v.prompt
                else v
            )
            for v in node_variables
        ]

        async def _do_extraction() -> Optional[dict]:
            try:
                logger.debug(f"Starting variable extraction for node: {node.name}")
                extracted_data = (
                    await self._variable_extraction_manager._perform_extraction(
                        extraction_variables, parent_context, extraction_prompt
                    )
                )
                if not isinstance(extracted_data, dict):
                    logger.warning(
                        f"Variable extraction for node {node.name} returned "
                        f"{type(extracted_data).__name__} instead of dict, "
                        f"skipping update. Data: {extracted_data}"
                    )
                    return None
                requested_names = {variable.name for variable in extraction_variables}
                unexpected_names = extracted_data.keys() - requested_names
                if unexpected_names:
                    logger.warning(
                        f"Variable extraction for node {node.name} returned "
                        f"unrequested keys {sorted(unexpected_names)}; ignoring them"
                    )
                extracted_data = {
                    key: value
                    for key, value in extracted_data.items()
                    if key in requested_names
                }
                # Extraction variable names are author-supplied and nothing
                # validates them against the keys the engine owns. Let one
                # through and it would desynchronise the call's outcome:
                # `call_disposition` would carry the extracted value while
                # `mapped_call_disposition` -- which is what reporting, filters
                # and the PBX write-back all read -- kept the recorded one.
                self._gathered_context.update(
                    {
                        key: value
                        for key, value in extracted_data.items()
                        if key not in ENGINE_OWNED_CONTEXT_KEYS
                    }
                )
                extracted_variables = self._gathered_context.setdefault(
                    "extracted_variables", {}
                )
                extracted_variables.update(extracted_data)
                logger.debug(
                    f"Variable extraction completed for node: {node.name}. Extracted: {extracted_data}"
                )
                return extracted_data
            except Exception as e:
                metadata = failure_metadata_for_processor(
                    self.active_agent.variable_extraction_llm
                )
                log_failure(
                    classify_exception(
                        e,
                        source=metadata.source,
                        provider=metadata.provider,
                        error_owner=metadata.error_owner,
                    ),
                    organization_id=self._organization_id,
                    workflow_run_id=self._workflow_run_id,
                    node_name=node.name,
                )
                return None

        if run_in_background:
            logger.debug(
                f"Scheduling background variable extraction for node: {node.name}"
            )
            task = asyncio.create_task(
                _do_extraction(), name=f"variable-extraction:{node.name}"
            )
            self._pending_extraction_tasks.add(task)
            task.add_done_callback(self._pending_extraction_tasks.discard)
            return None
        else:
            logger.debug(
                f"Performing synchronous variable extraction for node: {node.name}"
            )
            return await _do_extraction()

    async def _await_pending_extractions(self, timeout: float = 30.0) -> None:
        """Await all in-flight background extraction tasks.

        Args:
            timeout: Maximum seconds to wait for pending extractions.
        """
        if not self._pending_extraction_tasks:
            return

        task_names = [t.get_name() for t in self._pending_extraction_tasks]
        logger.debug(
            f"Awaiting {len(self._pending_extraction_tasks)} pending extraction task(s): {task_names}"
        )
        start_time = asyncio.get_event_loop().time()
        try:
            results = await asyncio.wait_for(
                asyncio.gather(*self._pending_extraction_tasks, return_exceptions=True),
                timeout=timeout,
            )
            elapsed = asyncio.get_event_loop().time() - start_time
            # Log any exceptions returned by gather
            for task_name, result in zip(task_names, results):
                if isinstance(result, Exception):
                    logger.error(
                        f"Pending extraction task '{task_name}' failed: {result}"
                    )
            logger.debug(f"All pending extraction tasks completed in {elapsed:.2f}s")
        except asyncio.TimeoutError:
            incomplete = [
                t.get_name() for t in self._pending_extraction_tasks if not t.done()
            ]
            logger.warning(
                f"Timed out waiting for pending extraction tasks after {timeout}s. "
                f"Incomplete: {incomplete}"
            )

    async def flush_variable_extraction(self) -> Optional[dict]:
        """Refresh extracted variables without marking the call finalized.

        This operation is intentionally repeatable. Transfer routing and
        external-PBX field mappings need current conversation values, but a
        failed transfer can return control to the agent and gather more input.
        """
        await self._await_pending_extractions()
        # [.mark] D11 : interrupteur allumé, la relecture de toute la conversation
        # (fin d'appel, routage de transfert) ne remplit que les champs vides de
        # la fiche. Avec le D28 ci-dessus, ce sont les deux seuls points où le
        # moteur décide de relire la conversation (D36).
        if self._fiche_sur_l_agent_actif():
            return await self._balayer_la_fiche()
        return await self._perform_variable_extraction_if_needed(
            self.active_agent.current_node,
            run_in_background=False,
        )

    def _fiche_sur_l_agent_actif(self) -> bool:
        """[.mark] La fiche vaut pour l'agent dont le modèle la porte.

        Un agent reçu par transfert (découpage par agent de l'amont, fc76383c)
        n'a ni `noter_information` ni la fiche : pour lui, l'extraction de
        l'amont reste en place, sinon rien ne serait collecté pendant sa visite.
        """
        return (
            self._fiche is not None
            and self._porte_la_fiche(self.active_agent)
        )

    def _porter_la_fiche(self, llm, *, suivi=None) -> None:
        """[.mark] Chantier agents-specialises (lot 3, 2A, 2B) : ``llm`` porte la fiche de
        l'appel : l'état de la fiche à chaque requête (D14), le suivi des tours (mode
        outil). Une fois par modèle. ⛔ Ne lève jamais."""
        try:
            if self._fiche is None or llm is None:
                return
            # Revue du 16/10 : un marqueur posé sur le modèle lui-même, jamais son id(),
            # qu'un modèle créé après la libération d'un autre peut reprendre.
            if _marque(llm, _MARQUE_FICHE) is True:
                return
            setattr(llm, _MARQUE_FICHE, True)
            if self._fiche.mode == MODE_OUTIL:
                setattr(llm, _SUIVI_FICHE, suivi if suivi is not None else suivre_les_tours(llm))
            # D14 : l'état de la fiche, montré à chaque requête de conversation.
            montrer_la_fiche(
                llm,
                self._fiche,
                lambda: self._gathered_context,
                self._notices_fiche,
                # Lot E d'agent-leger-greffier (P1) : les étiquettes de l'étape en cours.
                lambda: getattr(
                    getattr(self.active_agent, "current_node", None),
                    "champs_etape",
                    (),
                ),
                # Revue du 13/10 (lot C de greffier-conversation) : l'étape a-t-elle des portes ?
                lambda: bool(
                    getattr(
                        getattr(self.active_agent, "current_node", None), "out_edges", None
                    )
                ),
            )
        except Exception as e:  # noqa: BLE001
            logger.error(f"[fiche] fiche non branchée sur l'agent : {e!r}")

    def _porte_la_fiche(self, agent: AgentRuntime) -> bool:
        """[.mark] Lot 3 (2A) : le modèle de ``agent`` porte-t-il la fiche de l'appel ?"""
        if self._fiche is None or agent is None:
            return False
        return agent.llm is self._llm_de_la_fiche or _marque(agent.llm, _MARQUE_FICHE) is True

    def _suivi_de(self, agent: AgentRuntime):
        """[.mark] Lot 3 : le suivi des tours du modèle de ``agent`` (mode outil)."""
        suivi = _marque(getattr(agent, "llm", None), _SUIVI_FICHE)
        return suivi if suivi is not None else self._tours_fiche

    def _fusionner_la_fiche(self, runtime: AgentRuntime) -> None:
        """[.mark] Lot 3 (P4) : les champs de l'agent appelé entrent dans la fiche de
        l'appel ; même nom = un seul champ, la définition de l'agent qui a décroché.
        La fiche est modifiée EN PLACE : les modules qui la tiennent la voient.
        ⛔ Ne lève jamais."""
        try:
            # [.mark] Lot 2 d'orchestrateur-trois-cerveaux : les noms des champs du collègue, notés
            # dans la fiche (la note de retour dit ce qui reste de SA demande).
            noter_les_champs_de_l_agent(
                self._gathered_context,
                runtime.workflow_id,
                ReglagesFiche.depuis(dict(runtime.reglages or {})) if self._fiche else None,
            )
            champs = champs_fusionnes(self._fiche, runtime.reglages)
            if champs is not None:
                object.__setattr__(self._fiche, "champs", champs)
                logger.info(
                    f"[fiche] champs de l'agent {runtime.workflow_id} ajoutés à la fiche"
                )
        except Exception as e:  # noqa: BLE001
            logger.error(f"[fiche] fusion des champs en échec : {e!r}")

    def _ouvrir_une_demande(self, runtime: AgentRuntime) -> None:
        """[.mark] Lot 17 (fiche à plusieurs demandes) : à la passation vers un spécialisé qui
        n'est pas le premier à travailler dans l'appel, la demande en cours est close (ses champs
        « demande » quittent la vue à plat de la fiche) ; le spécialisé part d'une demande vide.
        Rien au retour au principal, rien pour un agent seul. Appelée d'un seul endroit
        (``commit_agent``). ⛔ Ne lève jamais."""
        try:
            principal_id = agent_principal_de(getattr(runtime, "reglages", None))
            if self._fiche is not None and principal_id is None and self.est_le_principal(runtime):
                # Revue du 16/10 : retour au principal, la demande du spécialisé est photographiée.
                from api.services.fiche.demandes import photographier_la_demande

                photographier_la_demande(self._gathered_context, self._fiche)
                return
            if self._fiche is None or principal_id is None:
                return
            from api.schemas.apres_appel import ApresAppelAgent
            from api.services.fiche.demandes import ouvrir_une_demande

            try:
                champ_motif = ApresAppelAgent.model_validate(
                    (self.reglages_appel or {}).get("apres_appel") or {}
                ).champ("motif")
            except Exception:  # noqa: BLE001 -- sans réglage lisible : pas de motif de bloc
                # Revue du 16/10 : jamais un nom de champ en dur (zéro vocabulaire dans le code).
                champ_motif = None
            noms = {
                a.workflow_id: a.workflow_name
                for a in [*self._retired_agents, self.active_agent]
                if a is not None and getattr(a, "workflow_id", None)
            }
            ouvrir_une_demande(
                self._gathered_context,
                self._fiche,
                vers_un_specialise=True,
                principal_id=principal_id,
                noms_des_agents=noms,
                champ_motif=champ_motif,
            )
        except Exception as e:  # noqa: BLE001
            logger.error(f"[demandes] ouverture d'une demande en échec : {e!r}")

    def garantir_a_l_ouverture(self, agent: AgentRuntime, cible: str, phrase) -> None:
        """[.mark] Lot 3 (A7) : un agent appelé dont la première étape porte un outil de
        transfert commence par le transfert, entreprise ouverte, une fois sa première
        réplique jouée (même mécanisme que l'arrivée dans une étape). ⛔ Ne lève jamais."""
        try:
            if self._transfert_garanti_s_applique(agent, cible):
                self._lancer_le_transfert_garanti(agent, cible, phrase)
        except Exception as e:  # noqa: BLE001
            logger.error(f"[transfert] garantie à l'ouverture en échec : {e!r}")

    async def _outil_de_transfert_a_son_message(self, noeud) -> bool:
        """Le premier outil de transfert d'appel de l'étape porte-t-il son propre message
        (texte ou enregistrement) ? Il le dit alors lui-même quand il est lancé : la phrase
        figée du réglage ne s'y ajoute pas. ⛔ Ne lève jamais (doute : non)."""
        try:
            organisation = await self._get_organization_id()
            if not organisation:
                return False
            for outil in await self.lire_outils(list(noeud.tool_uuids), organisation):
                if outil.category != ToolCategory.TRANSFER_CALL.value:
                    continue
                config = (outil.definition or {}).get("config") or {}
                genre = config.get("messageType", "none")
                return bool(
                    (genre == "custom" and str(config.get("customMessage") or "").strip())
                    or (genre == "audio" and config.get("audioRecordingId"))
                )
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[transfert] message de l'outil illisible : {e!r}")
        return False

    async def transfert_fige_a_l_ouverture(self, agent: AgentRuntime, cible: str) -> Optional[str]:
        """[.mark] Un agent appelé arrive sur l'étape ``cible`` : le code dit-il lui-même la mise
        en relation, sans tour de modèle ? ``None`` : non, comportement d'avant (le modèle parle,
        ``garantir_a_l_ouverture``). Sinon la phrase à dire (``""`` : l'outil de transfert porte
        déjà son message, il le dit en partant).

        Oui seulement si : la règle « mise en relation » de l'agent appelé, à l'étape ``cible``, est
        allumée (fiabilite-orchestration, lot 4 bis ; l'ancien réglage
        ``transfert_humain.phrase_mise_en_relation`` du principal est repris tel quel) ;
        l'étape (hors fin) porte un transfert d'appel que le code peut lancer seul ; l'entreprise
        est ouverte, sur rendez-vous ou sans horaires (la règle qui montre l'outil au modèle, K3) et aucun renvoi
        n'a déjà échoué ; il y a une voix (jamais au clavier). ⛔ Ne lève jamais."""
        try:
            if getattr(self, "sans_sortie_audio", False):
                return None
            noeud = agent.workflow.nodes.get(cible)
            regle = self.phrases.phrase(
                MISE_EN_RELATION,
                agent,
                getattr(noeud, "name", None),
                etape_id=getattr(noeud, "id", None),
            )
            if regle is None or not regle.dite:
                return None
            texte = regle.variantes[0]
            if noeud is None or noeud.is_end or not noeud.tool_uuids:
                return None
            if self._un_renvoi_a_deja_echoue():
                return None
            # Même règle que K3 (``_transfert_expose``) : sans état d'ouverture (agent sans
            # horaires), l'outil est exposé comme avant ; fermé ou en pause, il ne l'est pas.
            etat = (self._call_context_vars or {}).get(CLE_ETAT_OUVERTURE)
            if etat and etat not in (OUVERT, SUR_RENDEZ_VOUS):
                return None
            if await self._outil_de_transfert(noeud) is None:
                return None
            return "" if await self._outil_de_transfert_a_son_message(noeud) else texte
        except Exception as e:  # noqa: BLE001
            logger.error(f"[transfert] phrase figée à l'ouverture illisible : {e!r}")
            return None

    async def dire_puis_transferer_a_l_ouverture(
        self, agent: AgentRuntime, cible: str, texte: str, *, apres=None
    ) -> None:
        """[.mark] La suite de ``transfert_fige_a_l_ouverture`` : la phrase est dite par la voix de
        l'agent appelé, puis le code lance le transfert une fois la phrase jouée (si elle n'est
        pas jouée, ou si le transfert ne peut pas partir, le modèle reprend la parole). Le modèle
        n'est pas sollicité pour cette ouverture. ``apres`` : sans phrase du code (l'outil dit son
        message), ce que l'ouverture joue déjà, que le transfert attend. ⛔ Ne lève jamais."""
        try:
            phrase = apres
            if texte:
                # Lot 4 bis : par le diseur (variantes tournées, trace, coupable par l'appelant ;
                # coupée, le transfert ne part pas et le modèle répond).
                noeud = agent.workflow.nodes.get(cible)
                phrase = await self.phrases.dire_la_parole(
                    MISE_EN_RELATION,
                    agent,
                    etape=getattr(noeud, "name", None),
                    etape_id=getattr(noeud, "id", None),
                )
                if phrase is None:
                    raise RuntimeError("mise en relation non dite")
            self._lancer_le_transfert_garanti(agent, cible, phrase, a_l_ouverture=True)
        except Exception as e:  # noqa: BLE001
            logger.error(f"[transfert] phrase figée à l'ouverture en échec : {e!r}")
            try:
                if self.agent_can_act(agent):
                    await agent.queue_frame(LLMRunFrame())
            except Exception:  # noqa: BLE001
                pass

    @property
    def fiche(self) -> Optional[ReglagesFiche]:
        """[.mark] Les réglages de la fiche de l'appel (None : éteinte)."""
        return self._fiche

    @property
    def notices_fiche(self) -> Optional[Notices]:
        """[.mark] Plan mode-prise-de-notes (D4) : None en mode outil."""
        return self._notices_fiche

    def post_scriptum_attendu(self) -> bool:
        """[.mark] L'étape en cours porte-t-elle la consigne du post-scriptum ?
        Mêmes conditions que la consigne (``_prepare_node``) : l'agent qui porte
        la fiche, hors étape de fin."""
        agent = self.active_agent
        node = getattr(agent, "current_node", None)
        return (
            self._fiche_sur_l_agent_actif()
            and node is not None
            and not node.is_end
        )

    async def _balayer_la_fiche(self) -> Optional[dict]:
        """[.mark] D11 : le filet de fin d'appel, par le point d'écriture unique."""
        # Plan mode-prise-de-notes : une note du post-scriptum encore en cours
        # finit avant (bornée), sinon la passe la croiserait.
        await attendre_les_notes(self.notes_en_cours, delai_des_notes(self._fiche))
        if self.greffier is not None:
            # Une passe plus lente n'écrira plus après la passe de fin.
            self.greffier.clore()
        parent_context = self._get_otel_context()
        try:
            return await balayer_la_fiche(
                self._fiche,
                lambda variables, consigne: (
                    self._variable_extraction_manager._perform_extraction(
                        variables, parent_context, consigne
                    )
                ),
                self._gathered_context,
                self.context.get_messages() if self.context else [],
            )
        except Exception as e:
            logger.error(f"[fiche] Balayage de fin d'appel en échec : {e}")
            return None

    async def extract_variables_standalone(self, node: Node) -> Optional[dict]:
        """Run one node's extraction on an engine that never owned a pipeline.

        A text chat ends outside any pipeline -- every turn builds and tears one
        down, and the session-end request arrives with none running -- so its
        final extraction cannot come through ``_end_call``. This hands that path
        the single piece of ``initialize`` extraction needs, without opening MCP
        sessions or pushing LLM settings for a conversation that is already over.

        Callers own the resulting values; ``self._gathered_context`` is updated
        in place as usual, but nothing here persists it.
        """
        if self._variable_extraction_manager is None:
            self._variable_extraction_manager = VariableExtractionManager(self)
        self.active_agent.current_node = node
        # [.mark] C8 (correctifs-banc-34): a keyboard chat closed without a
        # transition ends like a call, by the record's end-of-call pass.
        if self._fiche_sur_l_agent_actif():
            return await self._balayer_la_fiche()
        return await self._perform_variable_extraction_if_needed(
            node, run_in_background=False
        )

    async def perform_final_variable_extraction(self) -> None:
        """Perform the one-shot variable extraction used during call disposal.

        Awaits any background extractions still running from previous nodes,
        then runs the current node's extraction inline. Idempotency prevents
        duplicate terminal extraction when multiple teardown paths converge.
        """
        if self._final_extraction_done:
            logger.debug("Final variable extraction already performed; skipping")
            return
        await self.flush_variable_extraction()
        self._final_extraction_done = True

    async def _prepare_node(
        self, agent: AgentRuntime, node: Node, *, apply_settings=True
    ) -> None:
        """Prepare one runtime's prompt and tools without changing the call."""
        manager = (
            self._custom_tool_manager
            if agent is self.active_agent
            else CustomToolManager(self, agent)
        )
        if not node.is_end:
            for edge in node.out_edges:
                await self._register_transition_function_with_llm(
                    edge.get_function_name(),
                    edge.target,
                    edge.transition_speech,
                    edge.data.transition_speech_type,
                    edge.data.transition_speech_recording_id,
                    agent=agent,
                )
        if node.tool_uuids and manager:
            await manager.register_handlers(
                node.tool_uuids,
                mcp_tool_filters=getattr(node, "mcp_tool_filters", None),
            )
        if node.document_uuids:
            await self._register_knowledge_base_function(
                node.document_uuids, agent=agent
            )
        prompt = compose_system_prompt_for_node(
            node=node,
            workflow=agent.workflow,
            format_prompt=self._format_prompt,
            has_recordings=self._has_recordings,
        )
        # [.mark] Plan porte-parlee (D5) : mêmes conditions que la consigne du
        # mode ci-dessous, et seulement case allumée (Postscript seulement).
        portes_parlees = (
            self._fiche is not None
            and self._fiche.portes_dans_la_reponse
            and not node.is_end
            and self._porte_la_fiche(agent)
        )
        functions = await compose_functions_for_node(
            node=node,
            custom_tool_manager=manager,
            portes_en_fonctions=not portes_parlees,
        )
        # [.mark] D12 : l'outil de la fiche n'existe que si l'interrupteur est
        # allumé. Pas sur une étape de fin (comme au lot 0). Seulement pour
        # l'agent dont le modèle porte la fiche (découpage par agent, fc76383c).
        # Plan mode-prise-de-notes : et seulement en mode outil.
        if (
            self._fiche is not None
            and self._fiche.mode == MODE_OUTIL
            and not node.is_end
            and self._porte_la_fiche(agent)
        ):
            functions.append(
                brancher_noter_information(
                    self._fiche,
                    agent.llm,
                    lambda: self._gathered_context,
                    lambda: self.context.get_messages() if self.context else [],
                    self._suivi_de(agent),
                )
            )
        # [.mark] Lot 4 d'orchestrateur-trois-cerveaux (D8) : l'outil « confier », seulement pour
        # un agent dont le travail en arrière-plan est allumé ET dont le cerveau de fond s'est
        # construit (``agent.travail``). Rien pour les autres : la requête reste identique.
        # Chantier modules-et-cerveaux (lot 5, M3) : et seulement à une étape cochée
        # (``travail_de_fond``). Un travail déjà lancé revient quelle que soit l'étape.
        travail = getattr(agent, "travail", None)
        etape_du_fond = (
            travail is not None
            and not node.is_end
            and getattr(node, "travail_de_fond", False) is True
        )
        if etape_du_fond:
            from api.services.travail.agent import brancher_confier_le_travail

            functions.append(brancher_confier_le_travail(self, travail, agent, node))
        # [.mark] fiabilite-orchestration, lot 1 (F2) : « annuler » avec « confier », et à toute
        # étape où un travail est en cours (l'appelant peut toujours annuler).
        if etape_du_fond or (travail is not None and not node.is_end and travail.occupe):
            from api.services.travail.agent import brancher_annuler_le_travail

            functions.append(brancher_annuler_le_travail(self, travail, agent))
        texte = prompt.text
        # [.mark] Plan mode-prise-de-notes (D3) : la consigne du mode, écrite par
        # le code à la fin du prompt, là où l'outil serait proposé (mêmes
        # conditions que D12 ci-dessus). Outil : rien.
        if (
            self._fiche is not None
            and not node.is_end
            and self._porte_la_fiche(agent)
        ):
            bloc = consigne_du_mode(self._fiche)
            if bloc:
                texte = f"{texte}\n\n{bloc}"
            # [.mark] fiabilite-orchestration, lot 2 (C4) : « ce sont des suggestions » écrit une
            # fois ici, plus dans chaque ligne « Encore attendu » ou « Déjà connu ».
            if self._fiche.etiquettes or self._fiche.deja_connu:
                from api.services.workflow.fiche_au_fil_de_leau import CONSIGNE_DES_SUGGESTIONS

                texte = f"{texte}\n\n{CONSIGNE_DES_SUGGESTIONS}"
        # [.mark] Plan porte-parlee (D4, D5, D11) : les portes de l'étape et les
        # premières répliques, après la consigne du post-scriptum.
        if portes_parlees:
            bloc = consigne_des_portes(
                node,
                agent.workflow,
                self._format_prompt,
                note_d_abord=self._fiche is not None and self._fiche.note_d_abord,
                # Chantier greffier-conversation, lot A : ni séparateur ni note.
                greffier=self._fiche is not None and self._fiche.mode == MODE_GREFFIER,
                # Lot 4 ter de repliques-coupees : le bloc de fin d'étape lisible.
                lisible=self._fiche is not None and self._fiche.parcours_lisible,
            )
            if bloc:
                texte = f"{texte}\n\n{bloc}"
        # [.mark] Chantier agents-specialises (A18) : plafond de passations atteint dans
        # cet appel : la ligne générique, à la fin du prompt de l'étape.
        if not node.is_end and plafond_atteint(
            self.__dict__.get("_gathered_context"), self.__dict__.get("reglages_appel")
        ):
            texte = f"{texte}\n\n{LIGNE_PLAFOND}"
        # [.mark] Lot 6 (A7) : un transfert a déjà échoué dans cet appel : la ligne générique,
        # pour l'agent qui arrive comme pour celui qui reste.
        if not node.is_end and self._un_renvoi_a_deja_echoue():
            texte = f"{texte}\n\n{LIGNE_RENVOI_DEJA_ECHOUE}"
        # [.mark] Lot 2 d'orchestrateur-trois-cerveaux (D2, D3) : la note de passation écrite par
        # le code, dans le prompt de l'étape (retour de l'accueil, ou première étape du collègue).
        note = self._note_de_passation(agent, node)
        if note:
            texte = f"{texte}\n\n{note}"
        agent.tools = ToolsSchema(standard_tools=functions)
        agent.system_prompt = texte
        if agent.recording_router is not None:
            agent.recording_router.set_enabled(prompt.recording_enabled)
        if apply_settings:
            await agent.llm._update_settings(LLMSettings(system_instruction=texte))

    def _champ_motif(self) -> str | None:
        """Le champ « motif » réglé pour l'organisation (jamais un nom en dur). ⛔ Ne lève jamais."""
        try:
            from api.schemas.apres_appel import ApresAppelAgent

            return ApresAppelAgent.model_validate(
                (self.reglages_appel or {}).get("apres_appel") or {}
            ).champ("motif")
        except Exception:  # noqa: BLE001
            return None

    def _note_de_passation(self, agent: AgentRuntime, node: Node) -> str | None:
        """[.mark] Lot 2 d'orchestrateur-trois-cerveaux (D2, D3) : la note du code pour l'étape qui
        s'ouvre. Étape de retour de l'accueil : la note de retour. Première étape d'un collègue
        appelé par passation : la note d'aller. Rien ailleurs, rien hors d'un groupe : un agent seul
        garde son prompt à l'octet. Recalculée depuis la fiche à chaque construction du prompt (au
        clavier, chaque tour refait le moteur). ⛔ Ne lève jamais."""
        try:
            if node.is_end or not est_un_groupe(self.__dict__.get("reglages_appel")):
                return None
            gathered = self.__dict__.get("_gathered_context")
            if not isinstance(gathered, dict):
                return None
            if est_une_etape_de_retour_de_l_accueil(node):
                noms = {
                    a.workflow_id: a.workflow_name
                    for a in [*self.__dict__.get("_retired_agents", []), self.active_agent]
                    if a is not None and getattr(a, "workflow_id", None)
                }
                return note_de_retour(
                    self._fiche,
                    gathered,
                    principal_id=agent.workflow_id,
                    champ_motif=self._champ_motif(),
                    noms=noms,
                )
            if (
                agent_principal_de(agent.reglages) is not None
                and node.id == agent.workflow.start_node_id
            ):
                outil = None
                demande = getattr(self.__dict__.get("_transfer_coordinator"), "_request", None)
                if (
                    getattr(demande, "destination_workflow_id", None) == agent.workflow_id
                    and getattr(demande, "etape_de_retour", False) is not True
                    and isinstance(getattr(demande, "raison", None), str)
                ):
                    outil = demande.raison
                if outil is None:
                    outil = outil_de_passation_vers(gathered, agent.workflow_id)
                if outil is None:
                    return None
                return note_d_aller(
                    self._fiche, gathered, outil=outil, champ_motif=self._champ_motif()
                )
            return None
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[notes] note de passation non posée : {e!r}")
            return None

    async def _setup_llm_context(self, node: Node) -> None:
        agent = self.active_agent
        await self._prepare_node(agent, node, apply_settings=False)
        if agent is self.active_agent:
            self.context.set_otel_span_name(f"llm-{node.name}")
            await self._update_llm_context(
                agent.system_prompt, agent.tools.standard_tools
            )

    async def set_node(
        self,
        node_id: str,
        emit_transition_event: bool = True,
        *,
        origin_visit_id: Optional[str] = None,
    ):
        """
        Simplified set_node implementation according to v2 PRD.

        Args:
            node_id: Node to enter, in the running agent's graph.
            emit_transition_event: Whether to report the transition to the UI.
            origin_visit_id: The agent visit requesting the change. A request
                from a visit that no longer owns the call is rejected: a tool
                call that landed just as a handoff committed must not move the
                new agent to a node id from the old agent's graph.
        """
        agent = self._active_agent
        if origin_visit_id is not None and origin_visit_id != agent.visit_id:
            logger.debug(
                f"Rejecting node change from retired visit {origin_visit_id}; "
                f"{agent.visit_id} owns the call"
            )
            return

        node = self.active_agent.workflow.nodes[node_id]

        logger.debug(
            f"Executing node: name: {node.name} allow_interrupt: {node.allow_interrupt} is_end: {node.is_end}"
        )

        # Track previous node for transition event
        previous_node_name = (
            self.active_agent.current_node.name
            if self.active_agent.current_node
            else None
        )
        previous_node_id = (
            self.active_agent.current_node.id
            if self.active_agent.current_node
            else None
        )

        # Set current node for all nodes (including static ones) so STT mute filter works
        self.active_agent.current_node = node

        # Track visited nodes in gathered context for call tags
        nodes_visited = self._gathered_context.setdefault("nodes_visited", [])
        if node.name not in nodes_visited:
            nodes_visited.append(node.name)
        self._noter_le_parcours(agent, node)

        # Send node transition event if callback is provided
        if emit_transition_event and self._node_transition_callback:
            try:
                porte = self._porte_ecrite_annoncee
                await self._node_transition_callback(
                    node_id,
                    node.name,
                    previous_node_id,
                    previous_node_name,
                    node.allow_interrupt,
                    **({"porte": porte} if porte else {}),
                )
            except Exception as e:
                # Log but don't fail - feedback is non-critical
                logger.debug(f"Failed to send node transition event: {e}")

        # Handle start nodes
        if node.is_start:
            await self._handle_start_node(node)
        # Handle end nodes
        elif node.is_end:
            await self._handle_end_node(node)
        # Handle normal agent nodes
        else:
            await self._handle_agent_node(node)

        # Summarize context in background after non-start node transitions
        # to clean up tool calls from previous nodes
        if previous_node_id is not None and self._context_summarization_manager:
            await self._context_summarization_manager.start()

    async def _handle_start_node(self, node: Node) -> None:
        """Set up context immediately; the answer supervisor owns initial listening."""
        await self._setup_llm_context(node)

    def set_answer_supervisor(self, supervisor, user_aggregator, idle_timeout: float):
        self.answer_supervisor = supervisor
        self._answer_user_aggregator = user_aggregator
        self.call_monitor.bind_user(user_aggregator, idle_timeout=idle_timeout)

    async def handle_answer_supervision(self):
        await handle_answer(self, self.answer_supervisor)

    def get_node_greeting(self, node_id: str) -> Optional[tuple[str, Optional[str]]]:
        """Return the greeting info for a node, or None if not configured.

        Returns:
            A tuple of (greeting_type, value) where:
            - ("text", rendered_text) for text greetings spoken via TTS
            - ("audio", recording primary key) for configured audio greetings
            - ("audio_recording_id", recording ID) for call-level audio overrides
            Or None if no greeting is configured.
        """
        node = self.active_agent.workflow.nodes.get(node_id)
        if not node:
            return None

        # A programmatic override applies only to the workflow entry greeting;
        # greetings on later nodes continue to use their saved configuration.
        if node.is_start:
            override = self.active_agent.greeting_override
            if isinstance(override, dict):
                override_type = override.get("type")
                if override_type == "text":
                    text = override.get("text")
                    if isinstance(text, str) and text.strip():
                        return ("text", self._format_prompt(text))
                elif override_type == "audio":
                    recording_id = override.get("recording_id")
                    if isinstance(recording_id, str) and recording_id.strip():
                        return ("audio_recording_id", recording_id.strip())
                logger.warning(
                    "Ignoring invalid greeting_override; using Start-node greeting"
                )

        greeting_type = node.greeting_type or "text"

        if greeting_type == "audio" and node.greeting_recording_id:
            return ("audio", node.greeting_recording_id)

        if node.greeting:
            return ("text", self._format_prompt(node.greeting))

        return None

    def get_start_greeting(self) -> Optional[tuple[str, Optional[str]]]:
        """Return the greeting info for the start node, or None if not configured."""
        return self.get_node_greeting(self.active_agent.workflow.start_node_id)

    async def queue_node_opening(
        self,
        *,
        node_id: str,
        previous_node_id: Optional[str] = None,
        generate_if_no_greeting: bool = False,
        origin_visit_id: Optional[str] = None,
        wait_for_playback: bool = False,
        mute_user: bool = False,
        opening_context: LLMContext | None = None,
    ) -> NodeOpeningResult:
        """Queue the opening behavior for a node.

        This is the shared source of truth for how a node begins once the
        engine is ready and the node has already been set on the context.
        Cascade openings share the same greeting policy at call startup and
        after agent transfers: two words interrupt, and only completed
        greetings enter assistant context.

        Args:
            node_id: The node being opened.
            previous_node_id: The node just left. Passing the same id as
                ``node_id`` suppresses the configured greeting when resuming
                an existing node, such as a text-chat checkpoint, or when an
                agent transfer is set to continue the conversation.
            generate_if_no_greeting: Ask the LLM for an opening turn when the
                node has no configured greeting.
            origin_visit_id: The agent visit this opening belongs to. An
                opening queued for a visit that is no longer running is
                dropped, so exactly one opening runs per activation.
            wait_for_playback: Await the opening's own output completion.
            mute_user: Hold a mute for the lifetime of the opening.
            opening_context: Isolated context for a provisional generated opening.

        Returns:
            The action ("greeting", "llm", or "none") and its playback handle,
            if tracked. The handle retains the outcome after playback finishes.
        """
        agent = self._active_agent
        if origin_visit_id is not None and origin_visit_id != agent.visit_id:
            logger.debug(
                f"Dropping node opening from retired visit {origin_visit_id}; "
                f"{agent.visit_id} owns the call"
            )
            return NodeOpeningResult("none")

        if previous_node_id != node_id:
            greeting_info = self.get_node_greeting(node_id)
            if greeting_info:
                greeting_type, greeting_value = greeting_info
                if (
                    greeting_type in {"audio", "audio_recording_id"}
                    and greeting_value
                    and self._fetch_recording_audio
                    and self._transport_output is not None
                ):
                    logger.debug(f"Playing audio greeting recording: {greeting_value}")
                    fetch_kwargs = (
                        {"recording_id": greeting_value}
                        if greeting_type == "audio_recording_id"
                        else {"recording_pk": int(greeting_value)}
                    )
                    speech = await self.queue_speech(
                        **fetch_kwargs,
                        append_to_context=True,
                        persist_to_logs=False,
                        mute_user=mute_user,
                        greeting=not self._is_realtime,
                    )
                    if speech.outcome is not PlaybackOutcome.FAILED:
                        if wait_for_playback:
                            await speech.wait()
                        await self._open_realtime_after_recorded_greeting(speech.text)
                        return NodeOpeningResult("greeting", speech)
                    logger.warning(
                        f"Failed to fetch audio greeting {greeting_value}, "
                        "falling back to LLM generation"
                    )
                elif greeting_value and agent.worker is not None:
                    logger.debug("Playing text greeting via TTS")
                    # Completed greeting playback is retained in context so
                    # the LLM knows the caller has already been greeted.
                    if self._is_realtime:
                        # Realtime adapters consume the opening text as a prompt
                        # and generate a response; configured tool text is skipped.
                        speech = self.speech_playback.expect_response(
                            source=agent.llm, mute_user=mute_user
                        )
                        try:
                            await agent.speak(
                                greeting_value,
                                append_to_context=True,
                                persist_to_logs=False,
                            )
                        except BaseException:
                            speech.finish(PlaybackOutcome.FAILED)
                            raise
                    else:
                        speech = await self.queue_speech(
                            greeting_value,
                            append_to_context=True,
                            persist_to_logs=False,
                            mute_user=mute_user,
                            greeting=True,
                        )
                    if wait_for_playback:
                        await speech.wait()
                    return NodeOpeningResult("greeting", speech)

        if (
            generate_if_no_greeting
            and agent.llm is not None
            and self.context is not None
        ):
            logger.debug("Queueing initial LLM generation for node opening")
            # Queue after the voicemail detector in the live pipeline so the
            # detector can gate initial generations when needed.
            speech = (
                self.speech_playback.expect_response(
                    source=agent.llm,
                    mute_user=mute_user,
                    greeting=not self._is_realtime,
                )
                if wait_for_playback or mute_user or not self._is_realtime
                else None
            )
            try:
                self.expect_response()
                await agent.run_llm(opening_context or self.context)
            except BaseException:
                if speech:
                    speech.finish(PlaybackOutcome.FAILED)
                raise
            if wait_for_playback:
                await speech.wait()
            return NodeOpeningResult("llm", speech)

        return NodeOpeningResult("none")

    async def _open_realtime_after_recorded_greeting(
        self, transcript: str | None
    ) -> None:
        """Hand the opening turn to a realtime service after a recording.

        Realtime providers seed their session, and open their caller-audio
        gate, off the opening turn the engine gives them. A recorded greeting
        is queued straight to the output transport, so without this the
        session stays unseeded and Gemini Live discards every caller frame -
        the bot greets, then never answers.

        The transcript goes with it because the handoff happens while the
        recording is still playing: the assistant aggregator only commits it
        to ``LLMContext`` once playback drains, which is too late to be part
        of the provider's session seed. Waiting for that commit instead would
        leave the caller unheard for the length of the greeting, and an
        interruptible node does not mute them.

        A no-op for text LLMs, which hold no session and re-read the context
        on every generation.
        """
        handle_prerecorded_greeting = getattr(
            self.active_agent.llm, "handle_prerecorded_greeting", None
        )
        if handle_prerecorded_greeting is None:
            return
        await handle_prerecorded_greeting(self.context, transcript)

    async def _handle_end_node(self, node: Node) -> None:
        """Handle end node execution."""
        # Setup LLM context with prompts and functions.
        await self._setup_llm_context(node)

    async def _handle_agent_node(self, node: Node) -> None:
        """Handle agent node execution."""
        # Setup LLM context with prompts and functions.
        await self._setup_llm_context(node)

    def set_call_disposition(self, disposition: str) -> None:
        """Fix the call's disposition ahead of teardown.

        ``end_call_with_reason`` falls back to its own ``call_status`` only when
        no disposition has been recorded, so an outcome already known to be
        final before the pipeline winds down has to be stamped here.

        An external-PBX transfer is the case that needs it. The PBX pulls the
        customer off our media leg within ~100ms of its transfer API returning,
        so ``on_client_disconnected`` fires while the transfer handler is still
        waiting out its post-handoff settle delay. Whichever path reaches
        ``end_call_with_reason`` first wins the disposition and the other is a
        no-op, so without this the completed transfer is recorded as a user
        hangup.
        """
        self._gathered_context[CALL_DISPOSITION_CONTEXT_KEY] = disposition
        self._gathered_context["mapped_call_disposition"] = self.map_disposition(
            disposition
        )

    def refine_call_disposition(
        self,
        fallback_disposition: str,
        extracted_disposition: str | None,
    ) -> None:
        """Replace the mechanical fallback with a classified business outcome.

        ``end_call_with_reason`` initially copies ``call_status`` into
        ``call_disposition``. Only the dedicated disposition service may refine
        it; ordinary node extractions are deliberately not consulted.

        A no-op whenever the fallback changed while classification was running
        or the service returned no supported disposition.
        """
        if (
            not extracted_disposition
            or self._gathered_context.get(CALL_DISPOSITION_CONTEXT_KEY)
            != fallback_disposition
        ):
            return

        logger.debug(
            f"Refining call disposition: {fallback_disposition} -> "
            f"{extracted_disposition}"
        )
        self.set_call_disposition(extracted_disposition)
        self.record_call_tags([extracted_disposition])

    def map_disposition(self, disposition: str | None) -> str | None:
        """Translate ``disposition`` through the organization's mapping.

        Public because the external-PBX transfer path records the call's outcome
        on the PBX before it is stamped here -- it needs the same translation
        this engine will apply, and must not resolve it a second way.
        """
        return apply_disposition_mapping(self._disposition_mapping, disposition)

    def record_context(self, values: Mapping[str, object]) -> None:
        """Merge caller-supplied values into the call's gathered context.

        The engine owns this dict for the life of the call. Teardown handlers
        add to it through here rather than mutating a snapshot they took
        earlier, so there is one copy of the truth to read and persist at the
        end instead of several that have to be reconciled.
        """
        self._gathered_context.update(values)

    def record_call_tags(self, tags: Iterable[str] = ()) -> None:
        """Add call tags, along with any carried by ``tag_*`` context keys.

        A workflow author can name an extraction variable ``tag_something`` to
        turn its value into a call tag. Those arrive through the extraction
        merge, so promoting them belongs here, next to the tags the engine
        records itself. Idempotent, so teardown paths may call it more than
        once.
        """
        call_tags = self._gathered_context.setdefault("call_tags", [])
        promoted = [
            value
            for key, value in self._gathered_context.items()
            if key.startswith("tag_") and isinstance(value, str)
        ]
        for tag in (*tags, *promoted):
            if tag and tag not in call_tags:
                call_tags.append(tag)

    async def end_call_with_reason(
        self, call_status: str, abort_immediately: bool = False
    ):
        """Own teardown outside any child tool that retirement may cancel."""
        if self._shutdown_task is None:
            self._shutdown_task = asyncio.create_task(
                self._end_call(call_status, abort_immediately), name="call-shutdown"
            )
        await asyncio.shield(self._shutdown_task)

    async def _end_call(
        self,
        call_status: str,
        abort_immediately: bool = False,
    ):
        """End the pipeline and record its status and business outcome.

        Args:
            call_status: Observable call-termination mechanism.
            abort_immediately: Queue a cancellation instead of a graceful end.
        """
        if self._call_disposed:
            logger.debug(f"Call already Disposed: {self._call_disposed}")
            return

        self._call_disposed = True
        self.speech_playback.cancel_all()

        # Mute the pipeline
        self._mute_pipeline = True

        # A handoff in flight is invalidated before anything else, so no later
        # phase can activate an agent into a call that is ending.
        coordinator = self.__dict__.get("_transfer_coordinator")
        if coordinator is not None:
            await coordinator.invalidate(call_status)

        # The call status is the observed termination mechanism. It is never
        # generated by an LLM.
        self._gathered_context[CALL_STATUS_CONTEXT_KEY] = call_status

        # Prefer a business outcome already recorded during the call -- by an
        # end-call tool or a transfer. Otherwise the mechanical status is the
        # disposition fallback.
        #
        # Stamped before the extraction below rather than after it, so that a
        # call always carries an outcome even when that extraction times out or
        # comes back with nothing. `refine_call_disposition` upgrades it once
        # the extraction has actually landed.
        recorded_disposition = self._gathered_context.get(
            CALL_DISPOSITION_CONTEXT_KEY, ""
        )
        should_extract_disposition = not bool(recorded_disposition)
        call_disposition = (
            recorded_disposition or self._gathered_context[CALL_STATUS_CONTEXT_KEY]
        )
        self._gathered_context[CALL_DISPOSITION_CONTEXT_KEY] = call_disposition
        # A dict lookup against the mapping loaded in `initialize`, not a DB
        # round trip -- see `_disposition_mapping`.
        self._gathered_context["mapped_call_disposition"] = self.map_disposition(
            call_disposition
        )

        # Tagged with the untranslated disposition. Tags are Dograh's own
        # vocabulary -- `user_speech`, `not_connected` -- and are what the
        # mapping-less view of a run is read from.
        self.record_call_tags([call_disposition])

        if call_status not in (
            EndTaskReason.PIPELINE_ERROR.value,
            EndTaskReason.VOICEMAIL_DETECTED.value,
            *ANSWER_TERMINAL_REASONS,
        ):
            # Finish ordinary node extraction, then classify the call outcome
            # independently when the mechanical status is only a fallback.
            # Bound both calls together so a stuck LLM cannot hold the call open.
            extracted_disposition = None
            try:
                async with asyncio.timeout(FINAL_EXTRACTION_TIMEOUT_SECONDS):
                    await self.perform_final_variable_extraction()
                    if (
                        should_extract_disposition
                        and self._disposition_extraction_service is not None
                    ):
                        extracted_disposition = (
                            await self._disposition_extraction_service.extract(
                                parent_context=self._get_otel_context(),
                                organization_id=self._organization_id,
                                workflow_run_id=self._workflow_run_id,
                            )
                        )
            except asyncio.TimeoutError:
                logger.warning(
                    f"Final extraction did not finish within "
                    f"{FINAL_EXTRACTION_TIMEOUT_SECONDS}s; keeping the recorded "
                    f"disposition '{call_disposition}'"
                )
            if should_extract_disposition:
                self.refine_call_disposition(
                    call_disposition,
                    extracted_disposition,
                )

        # Agent workers are shut down before the call pipeline, and waited for.
        # A terminal frame queued below travels this worker's pipeline and
        # nothing else, so a child left running would be cancelled later by the
        # runner -- losing its last audio and its usage metrics -- instead of
        # draining into a transport that is still up.
        await self.retire_agents(call_status, drain=not abort_immediately)

        # One run row anchors the call, so which agents it visited, on which
        # definitions and models, is recorded on its gathered context. Written
        # after retirement so every visit carries its exit. Without this a
        # transferred call reports only the agent it started on.
        if self.__dict__.get("_agent_visits") or self.active_agent.is_child:
            self._gathered_context["agent_visits"] = self.agent_visits

        frame_to_push = (
            CancelFrame(reason=call_status)
            if abort_immediately
            else EndFrame(reason=call_status)
        )

        # No persist here. This used to write the gathered context before
        # queueing the frame, because the pipeline could be cancelled out from
        # under this coroutine and `on_pipeline_finished` would then write a
        # snapshot taken before the extraction landed. In-pipeline
        # cancellations now funnel back through this method (see
        # TerminationFunnelProcessor), so the frame below is what ends the
        # pipeline and `on_pipeline_finished` cannot run until it does -- one
        # write, of the finished context, is enough. Hangup strategies read
        # only keys recorded at call setup or at transfer time, never the
        # terminal extraction.
        logger.debug(
            f"Finishing run with call status: {call_status}, disposition: "
            f"{self._gathered_context.get(CALL_DISPOSITION_CONTEXT_KEY, call_disposition)} "
            f"queueing frame {frame_to_push}"
        )
        await self.call_worker.queue_frame(frame_to_push)

    async def queue_speech(
        self,
        text: str | None = None,
        *,
        audio: bytes | None = None,
        recording_pk: int | None = None,
        recording_id: str | None = None,
        transcript: str | None = None,
        append_to_context: bool = False,
        persist_to_logs: bool = True,
        mute_user: bool = False,
        timeout: float = 35,
        greeting: bool = False,
    ) -> SpeechPlayback:
        """Queue one message and return its independently owned playback result.

        Recording preparation is bounded and happens before acquiring a mute.
        Text and audio boundaries follow the same route as their message, so
        completion acknowledges output rather than unrelated bot activity.
        Playback ownership and its timeout start before preparation, so a
        greeting can be interrupted while its recording is still loading.
        """
        from pipecat.frames.frames import TTSSpeakFrame

        if (
            sum(
                value is not None for value in (text, audio, recording_pk, recording_id)
            )
            != 1
        ):
            raise ValueError("Provide exactly one speech source")

        speech = self.speech_playback.create(timeout=timeout, greeting=greeting)

        def completed(outcome):
            speech.finish(outcome)
            return speech

        try:
            if self.is_call_disposed():
                return completed(PlaybackOutcome.CLOSED)
            if text is not None and (self._is_realtime or not text.strip()):
                return completed(PlaybackOutcome.SKIPPED)
            if recording_pk is not None or recording_id is not None:
                if not self._fetch_recording_audio or self._transport_output is None:
                    return completed(PlaybackOutcome.FAILED)
                try:
                    async with asyncio.timeout(10):
                        recording = await self._fetch_recording_audio(
                            **(
                                {"recording_pk": recording_pk}
                                if recording_pk is not None
                                else {"recording_id": recording_id}
                            )
                        )
                    if recording is None:
                        return completed(PlaybackOutcome.FAILED)
                    audio, transcript = recording.audio, recording.transcript
                except Exception:
                    logger.warning("Could not prepare recorded speech")
                    return completed(PlaybackOutcome.FAILED)

            if self.is_call_disposed():
                return completed(PlaybackOutcome.CLOSED)
            frames = []
            if greeting:
                append_to_context = False
                persist_to_logs = True
            if text is not None:
                if self.active_agent.worker is None:
                    return completed(PlaybackOutcome.FAILED)
                # [.mark] Lot 3 d'orchestrateur-trois-cerveaux (D7) : UN SEUL chemin de parole
                # à la fois. Un agent a la main : la parole passe par lui (dans l'ordre de son
                # texte). Personne n'a la main (attente d'une passation, ``selected_visit_id``
                # vaut None) : route locale du pont, vers la voix de l'appel, sans réveiller
                # l'agent source. Jamais les deux.
                queue_frame = self.active_agent.queue_frame
                if self._parole_locale is not None and self.selected_visit_id is None:
                    queue_frame = self._parole_locale
                frames.append(
                    TTSSpeakFrame(
                        text,
                        append_to_context=append_to_context,
                        persist_to_logs=persist_to_logs,
                    )
                )
            else:
                if not audio or self._transport_output is None:
                    return completed(PlaybackOutcome.FAILED)
                queue_frame = self._transport_output.queue_frame

                async def collect(frame):
                    frames.append(frame)

                await play_audio(
                    audio,
                    sample_rate=(
                        self._audio_config.pipeline_sample_rate
                        if self._audio_config
                        else 16000
                    ),
                    queue_frame=collect,
                    transcript=transcript,
                    append_to_context=append_to_context,
                    persist_to_logs=persist_to_logs,
                )

            if speech.done:
                return speech
            speech.text = text if text is not None else (transcript or "")
            speech.mute_user = mute_user
            await queue_frame(SpeechBoundaryFrame(speech.id, beginning=True))
            for frame in frames:
                await queue_frame(frame)
            await queue_frame(SpeechBoundaryFrame(speech.id, beginning=False))
        except BaseException:
            speech.finish(PlaybackOutcome.FAILED)
            raise
        return speech

    async def queue_text_message(
        self, text: str, *, append_to_context: bool = False, mute_user: bool = False
    ) -> bool:
        """Queue a message whose caller does not need to await playback."""
        speech = await self.queue_speech(
            text, append_to_context=append_to_context, mute_user=mute_user
        )
        return speech.outcome not in (
            PlaybackOutcome.FAILED,
            PlaybackOutcome.SKIPPED,
            PlaybackOutcome.CLOSED,
        )

    async def should_mute_user(self, frame: "Frame") -> bool:
        """
        Callback for CallbackUserMuteStrategy to determine if the user should be muted.

        This method tracks bot speaking state from frames and mutes the user when:
        - The pipeline is being shut down (_mute_pipeline is True), OR
        - A pending speech operation requested muting, OR
        - After answer supervision, the bot is speaking and the current node
          has allow_interrupt=False

        Returns:
            True if the user should be muted, False otherwise.
        """
        # Track bot speaking state from frames
        if isinstance(frame, BotStartedSpeakingFrame):
            self._bot_is_speaking = True
        elif isinstance(frame, BotStoppedSpeakingFrame):
            self._bot_is_speaking = False

        # Always mute if pipeline is shutting down
        if self._mute_pipeline:
            return True

        # Mute while queued speech (transition/tool message) is pending or playing
        if self.speech_playback.mutes_user:
            return True

        # [.mark] E1: upstream lifts the mute for the whole greeting. Only when
        # the greeting is open for this agent; otherwise the greeting keeps the
        # protection of production (`allow_interrupt=False` below).
        if self.greeting.interruptible and (
            self.speech_playback.greeting_pending or self.greeting.awaiting_turn
        ):
            return False

        # Keep caller turns live while a committed answer verdict waits for the
        # greeting to finish. The supervisor's gate still holds their inference.
        if self.answer_supervisor and self.answer_supervisor.blocks_workflow:
            return False

        # Mute if bot is speaking and current node doesn't allow interruption
        if self._bot_is_speaking and self.active_agent.current_node:
            # If we should not allow interruption, mute the pipeline
            if not self.active_agent.current_node.allow_interrupt:
                return True

        return False

    def regler_relances(self, run_configs: dict | None) -> None:
        """[.mark] The agent's own idle reminders (`user_idle_prompt`,
        `user_idle_goodbye_prompt`, `user_idle_max_prompts`), read by
        `engine_callbacks.handle_user_idle` when the call monitor of upstream
        (4e6cb22b) decides the caller has been quiet. Nothing set: upstream's
        texts and count, exactly."""
        self.reglages_relances = dict(run_configs or {})

    def should_interrupt_user_turn(self) -> bool:
        """Greeting word thresholds are enforced by the active start strategy."""
        if self.speech_playback.greeting_pending:
            return True
        return (
            self.answer_supervisor is None or not self.answer_supervisor.blocks_workflow
        )

    async def interrupt_screening_reply(self) -> bool:
        """Stop screening playback before greeting the human who picked up."""
        await self._answer_user_aggregator.broadcast_interruption()
        return await self.drain_call_pipeline()

    async def _on_user_idle(self, attempt: int) -> None:
        await engine_callbacks.handle_user_idle(
            self, self.call_monitor.user_aggregator, attempt
        )

    def create_max_duration_callback(self):
        """
        This callback is called when the call duration exceeds the max duration.
        We use this to send the EndTaskFrame.
        """
        return engine_callbacks.create_max_duration_callback(self)

    def create_generation_started_callback(self, visit_id: Optional[str] = None):
        """
        This callback is called when a new generation starts.
        This is used to reset the flags that control the flow of the engine.

        Args:
            visit_id: The agent visit whose generation stage this belongs to.
                A retired agent finishing its last generation must not reset
                the reference text the running agent is building.
        """
        return engine_callbacks.create_generation_started_callback(
            self, visit_id=visit_id
        )

    def create_llm_text_frame_callback(self, visit_id: Optional[str] = None):
        """Return the text accumulator for one agent visit's generation stage."""

        async def accumulate(text: str) -> None:
            await self.handle_llm_text_frame(text, visit_id=visit_id)

        return accumulate

    def owns_generation(self, visit_id: Optional[str]) -> bool:
        """Whether ``visit_id`` is the agent currently owning the call."""
        return visit_id is None or visit_id == self._active_agent.visit_id

    def create_aggregation_correction_callback(self) -> Callable[[str], str]:
        """Create a callback that corrects corrupted aggregation using reference text."""
        return engine_callbacks.create_aggregation_correction_callback(self)

    def set_context(self, context: LLMContext) -> None:
        """Set the LLM context.

        This allows setting the context after the engine has been created,
        which is useful when the context needs to be created after the engine.
        """
        self.context = context

    # ------------------------------------------------------------------
    # Agent lifecycle
    #
    # The engine alone authorizes agent activation, context replacement and
    # call completion. `AgentTransferCoordinator` sequences a handoff; every
    # step that changes who owns the call comes back through here.
    # ------------------------------------------------------------------

    def set_agent_factory(self, factory) -> None:
        """Enable in-call agent transfer by supplying a runtime factory."""
        self._agent_factory = factory
        # [.mark] fiabilite-orchestration, lot 3 (F5) : la connexion du premier agent est le
        # premier poste de l'appel ; un collègue au même fournisseur la reprend.
        postes = getattr(factory, "postes", None)
        agent = self.__dict__.get("_active_agent")
        if postes is not None and agent is not None:
            postes.enregistrer(agent.llm, getattr(agent, "workflow_name", None))

    @property
    def agent_transfer_enabled(self) -> bool:
        """Whether this call can hand the caller to another agent.

        True for every cascade call. False only in realtime, where the tool
        still registers but refuses, so the agent tells the caller rather than
        failing silently.
        """
        return self.__dict__.get("_agent_factory") is not None

    @property
    def transfer_coordinator(self):
        """The call's handoff coordinator, created on first use."""
        if self._transfer_coordinator is None:
            from api.services.workflow.agent_transfer import AgentTransferCoordinator

            self._transfer_coordinator = AgentTransferCoordinator(self)
        return self._transfer_coordinator

    @property
    def transfer_in_progress(self) -> bool:
        """Whether a handoff is running, so ordinary prompting must hold off."""
        coordinator = self.__dict__.get("_transfer_coordinator")
        return coordinator is not None and coordinator.in_progress

    @property
    def agent_visits(self) -> list[dict]:
        """One record per agent visit, oldest first, including the live one."""
        return [*self.__dict__.get("_agent_visits", []), self.active_agent.describe()]

    @property
    def hold_audio_sample_rate(self) -> int:
        """Sample rate for ringer audio queued straight to the transport."""
        if self._audio_config:
            return self._audio_config.transport_out_sample_rate
        return 8000

    @property
    def transport_output_queue_frame(self):
        """Frame sink that reaches the caller without passing through STT."""
        return self._transport_output.queue_frame

    async def start_initial_agent(self, timeout: float = 10.0) -> bool:
        """Attach and activate the agent the call starts on.

        Runs once the call pipeline is up, so the agent's worker joins the
        call's conversation trace and the runner is there to start it. A
        no-op when the first agent runs in the call worker itself.
        """
        agent = self._active_agent
        if not agent.is_child:
            return True
        if self._agent_factory is None or self._call_worker is None:
            logger.error("Cannot start the initial agent without a factory")
            return False

        await self._agent_factory.attach(agent)
        if agent.worker is None or agent.retired:
            return False
        # [.mark] Lot 4 d'orchestrateur-trois-cerveaux : le cerveau de fond du premier agent
        # rejoint l'appel avec lui, maintenant que le circuit d'appel tourne.
        if getattr(agent, "travail", None) is not None:
            await agent.travail.attacher()
        if not await agent.wait_until_started(timeout=timeout):
            return False
        return await self.activate_agent(agent, timeout=timeout)

    async def build_agent(self, *, workflow_id: int, visit_id: str) -> AgentRuntime:
        """Build a destination agent and attach it to the call, inactive."""
        if self._agent_factory is None:
            from api.services.pipecat.agent_runtime_factory import AgentBuildError

            raise AgentBuildError(
                "transfer_unavailable",
                "This call was not set up to transfer between agents",
            )
        # [.mark] Lot 6 (A5) : la cible est le principal resté chaud : on le rend tel quel
        # (même pipeline, mêmes services, même visite), il reprend avec l'historique et la fiche.
        chaud = self.principal_chaud_pour(workflow_id)
        if chaud is not None:
            self._pending_agent = chaud
            self.mesure_passation.installee(0.0, "principal_chaud", memoire_du_processus_mo())
            logger.info(f"[groupe] principal {workflow_id} resté chaud : rendu sans construction")
            return chaud
        debut = time.monotonic()
        # [.mark] fiabilite-orchestration, lot 3 (F5) : le collègue construit à l'avance.
        runtime = self._prendre_dans_la_reserve(workflow_id)
        origine = "reserve"
        if runtime is None:
            origine = "construit"
            runtime = await self._agent_factory.build(
                workflow_id=workflow_id, visit_id=visit_id
            )
        self._pending_agent = runtime
        # [.mark] Lot 4 d'orchestrateur-trois-cerveaux (D8) : le cerveau de fond de l'agent
        # appelé, avant la préparation de son étape (l'outil « confier » en dépend).
        await self.preparer_le_travail(runtime)
        # [.mark] fiabilite-orchestration, lot 4 (F20) : la garde du modèle du collègue (déjà posée
        # sur un collègue de la réserve).
        from api.services.panne.garde_modele import garder_l_agent

        await garder_l_agent(self, runtime)
        # [.mark] Chantier agents-specialises (lot 3) : la fiche de l'appel suit l'agent
        # appelé (ses champs s'ajoutent, son modèle la porte) avant la préparation de son
        # étape, pour qu'il ait l'outil de note, la consigne et l'état de la fiche.
        if self._fiche is not None:
            self._fusionner_la_fiche(runtime)
            self._porter_la_fiche(runtime.llm)
        self.mesure_passation.installee(
            time.monotonic() - debut,
            origine,
            memoire_du_processus_mo(),
            getattr(runtime, "visit_id", None),
        )
        return runtime

    async def preparer_le_travail(
        self, runtime: AgentRuntime, *, user_config=None, attacher: bool = True
    ) -> None:
        """[.mark] Lot 4 d'orchestrateur-trois-cerveaux (D8, D13) : construit le cerveau de fond de
        ``runtime`` si son travail en arrière-plan est allumé (``runtime.travail``), et l'attache à
        l'appel (``attacher``). Le premier agent s'attache plus tard, quand le circuit d'appel
        tourne (``start_initial_agent``). Rien si le travail est éteint.
        ⛔ Ne lève jamais : un échec joue l'agent sans cerveau de fond."""
        try:
            from api.services.travail.agent import preparer_le_travail

            travail = await preparer_le_travail(self, runtime, user_config=user_config)
            if travail is not None and attacher:
                await travail.attacher()
        except Exception as e:  # noqa: BLE001
            logger.error(f"[travail] cerveau de fond non préparé : {type(e).__name__}")

    async def prepare_agent(self, runtime: AgentRuntime) -> None:
        # [.mark] Lot 6 : un principal resté chaud garde ses sessions déjà ouvertes.
        if not runtime.mcp_sessions:
            await self._open_mcp_sessions(runtime)
        node = runtime.workflow.nodes[runtime.workflow.start_node_id]
        # [.mark] Lot 2 d'orchestrateur-trois-cerveaux (D1) : au retour d'un collègue, l'accueil
        # reprend sur son étape de retour s'il en a une (prompt rédigé) ; sinon l'étape de départ.
        if self._retour_demande():
            retour = etape_de_retour_du_graphe(runtime.workflow)
            if retour is not None:
                node = retour
        await self._prepare_node(runtime, node)
        runtime.current_node = node

    def _retour_demande(self) -> bool:
        """La passation en cours est un retour au principal qui demande l'étape de retour de
        l'accueil. Une maquette de coordinateur : non. ⛔ Ne lève jamais."""
        try:
            demande = getattr(self.transfer_coordinator, "_request", None)
            return getattr(demande, "etape_de_retour", False) is True
        except Exception:  # noqa: BLE001
            return False

    def commit_agent(self, runtime: AgentRuntime, snapshot) -> None:
        """The only handoff commit point. No awaits and no provider work."""
        from api.services.workflow.agent_handoff_context import messages_after_boundary

        self.mesure_passation.commise()  # [.mark] lot 3 : le commit de la passation
        tail = messages_after_boundary(self.context, snapshot.boundary)
        self.context.set_messages([*snapshot.messages, *tail])
        self.context.set_tools(runtime.tools)
        self.context.set_otel_span_name(f"llm-{runtime.current_node.name}")
        runtime.entered_at = time.time()
        self._ouvrir_une_demande(runtime)  # [.mark] lot 17
        self.install_agent(runtime, previous=self.active_agent)
        self._custom_tool_manager = CustomToolManager(self, runtime)
        self._agent_on_hold = False
        nodes = self._gathered_context.setdefault("nodes_visited", [])
        if runtime.current_node.name not in nodes:
            nodes.append(runtime.current_node.name)
        self._noter_le_parcours(runtime, runtime.current_node)
        logger.info(
            f"[transfer] installed {runtime.visit_id}: "
            f"{len(snapshot.messages)} handoff messages (summarized={snapshot.summarized}) "
            f"+ {len(tail)} live messages"
        )

    async def notify_agent_entered(self, runtime: AgentRuntime) -> None:
        node = runtime.current_node
        if self._node_transition_callback:
            try:
                # [.mark] agents-specialises : l'événement porte le nom de l'agent, quand le
                # rappel l'accepte (revue du 16/10 : signature lue, pas de second appel).
                if _accepte_agent(self._node_transition_callback):
                    await self._node_transition_callback(
                        node.id,
                        node.name,
                        None,
                        None,
                        node.allow_interrupt,
                        agent=runtime.workflow_name or None,
                    )
                else:
                    await self._node_transition_callback(
                        node.id, node.name, None, None, node.allow_interrupt
                    )
            except Exception as error:
                logger.debug(f"Failed to send agent transition event: {error}")

    @property
    def selected_visit_id(self) -> str | None:
        return None if self._agent_on_hold else self.active_agent.visit_id

    def agent_can_act(self, runtime: AgentRuntime) -> bool:
        return not self._call_disposed and self.selected_visit_id == runtime.visit_id

    def install_agent(
        self,
        runtime: AgentRuntime,
        *,
        previous: Optional[AgentRuntime] = None,
        previous_exit_reason: str = "transferred",
    ) -> None:
        """Make ``runtime`` the agent that owns the call.

        Closes the previous visit into the call's history rather than
        discarding it: usage, nodes visited and outcome are per visit and are
        all reported at the end of the call. The exit is stamped here, before
        the history entry is taken, so the record is not a snapshot of a visit
        that had not ended yet.
        """
        # [.mark] Lot 6 (A5) : un principal resté chaud qui reprend la main sort des agents
        # écartés (il n'y figure jamais deux fois) et sa visite repart de zéro, pour que le
        # relevé compte UNE visite par entrée : même ``visit_id`` (son pipeline et ses rappels
        # y sont liés), ``entered_at`` posé au commit, ``exited_at``/``exit_reason`` vidés.
        if any(a is runtime for a in self._retired_agents):
            self._retired_agents = [a for a in self._retired_agents if a is not runtime]
            runtime.exited_at = None
            runtime.exit_reason = None
            runtime.nb_entrees += 1
        if previous is not None and previous is not runtime:
            previous.exited_at = previous.exited_at or time.time()
            previous.exit_reason = previous.exit_reason or previous_exit_reason
            self._agent_visits.append(previous.describe())
            if not any(a is previous for a in self._retired_agents):
                self._retired_agents.append(previous)
        self._active_agent = runtime
        self._pending_agent = None
        # [.mark] D1 : l'agent qui prend (ou reprend, principal chaud) la main reparle.
        from api.services.pipecat.main_passee import rendre_la_parole

        rendre_la_parole(getattr(runtime, "llm", None))

    def discard_pending_agent(self, runtime: AgentRuntime) -> None:
        """Forget a destination that was prepared but never took the call.

        Its worker is released by the caller; this drops the engine's handle
        so `pending_agent` does not keep reporting a retired agent, and
        teardown does not try to shut it down a second time.
        """
        if self._pending_agent is runtime:
            self._pending_agent = None

    async def activate_agent(self, runtime: AgentRuntime, *, timeout: float) -> bool:
        """Let ``runtime`` back into the conversation and confirm it took.

        An inactive worker is handed no frames from the bus, so activation is
        what actually connects an agent to the caller. It only takes effect
        once the worker has started, which is why this confirms rather than
        assuming the message was enough.
        """
        self._bind_call_monitor(runtime)
        if not runtime.is_child or self._call_worker is None:
            return True

        await self._call_worker.activate_worker(runtime.worker.name)

        deadline = asyncio.get_running_loop().time() + timeout
        while asyncio.get_running_loop().time() < deadline:
            if runtime.worker.active:
                logger.debug(f"Agent visit {runtime.visit_id} activated")
                return True
            await asyncio.sleep(0.01)
        logger.warning(
            f"Agent visit {runtime.visit_id} did not activate within {timeout}s"
        )
        return False

    async def deactivate_agent(self, runtime: AgentRuntime) -> None:
        """Take ``runtime`` out of the conversation without ending it.

        Gates inference structurally: the agent stops receiving context frames
        while recognition, recording and the call timer carry on. Reversible --
        a rolled-back handoff activates the same worker again.
        """
        self.call_monitor.cancel()
        if not runtime.is_child or self._call_worker is None:
            return
        self._agent_on_hold = True
        await self._call_worker.deactivate_worker(runtime.worker.name)

    async def drain_call_pipeline(self, timeout: float = 5.0) -> bool:
        """Wait for everything in flight to reach the caller.

        The flush probe travels through the selected agent's worker and back, so
        this drains the agent's generation stage as well as the call pipeline.
        During hold it stays on the call pipeline and drains queued ring audio.
        """
        if self._call_worker is None:
            return False
        return await self._call_worker.flush_pipeline(timeout=timeout)

    async def pause_background_context_writers(self) -> None:
        """Stop anything that would mutate the conversation behind a handoff."""
        if self._context_summarization_manager:
            await self._context_summarization_manager.cleanup()
        await self._await_pending_extractions()

    def record_transfer_outcome(self, record: dict) -> None:
        """Record how one handoff attempt ended, for the call's run record."""
        # [.mark] Lot 3 : la mesure du premier octet, si la voix a deja parle.
        self.mesure_passation.completer(record)
        self._transfer_outcomes.append(record)
        self._gathered_context["agent_transfers"] = list(self._transfer_outcomes)

    async def handle_agent_error(self, runtime: AgentRuntime, frame) -> None:
        """Decide what one agent's pipeline error means for the call.

        The call pipeline's termination funnel treats a terminal error as the
        end of the call, which is right only for the agent the caller is
        actually talking to. An agent still being prepared, or one already
        handed over, fails its own transfer and leaves the call alone.
        """
        from api.services.pipecat.termination_funnel_processor import (
            is_terminal_error,
        )

        if not is_terminal_error(frame):
            return

        runtime.error = getattr(frame, "error", None) or "pipeline error"
        if runtime is not self._active_agent:
            logger.warning(
                f"Agent visit {runtime.visit_id} is unusable ({runtime.error}); "
                "the call continues with the agent that owns it"
            )
            return

        logger.error(
            f"Agent visit {runtime.visit_id} is unusable ({runtime.error}); "
            "ending the call"
        )
        await self.end_call_with_reason(EndTaskReason.PIPELINE_ERROR.value)

    async def retire_agents(self, reason: str, *, drain: bool = True) -> None:
        """Shut down every agent worker this call created.

        Terminal frames queued on the call worker drain the call pipeline
        only: child propagation runs off a bus message that a frame on the
        push queue never produces. Without this the runner eventually cancels
        the orphans at shutdown, which cuts their final audio and metrics
        instead of draining them.

        Args:
            reason: Recorded as each visit's exit reason.
            drain: Let each agent finish what it is saying. False on the abort
                path, where the caller is already gone or the call is over its
                hard limit and waiting would only delay teardown.
        """
        agents = [
            self.active_agent,
            self.pending_agent,
            *self.__dict__.get("_retired_agents", []),
        ]
        vus: list[AgentRuntime] = []  # [.mark] lot 6 : jamais deux fois le même agent
        for agent in agents:
            if agent is None or not agent.is_child:
                continue
            if any(agent is v for v in vus):
                continue
            vus.append(agent)
            agent.exited_at = agent.exited_at or time.time()
            agent.exit_reason = agent.exit_reason or reason
            if drain:
                await agent.retire(reason)
            else:
                await agent.abort(reason)

    # --- [.mark] Chantier agents-specialises (lot 7, D91) : le parcours (agent, étape) ---

    def _noter_le_parcours(self, agent: AgentRuntime, node: Node) -> None:
        """Une entrée par (agent, étape), dans l'ordre : ``nodes_visited`` dédoublonne par nom
        d'étape (l'ordre entre deux agents qui ont une étape du même nom se perd). Une entrée par
        ENTRÉE dans une étape : deux entrées de suite dans la même étape du même agent n'en font
        qu'une, mais un retour chez le principal après un spécialisé en ajoute une. Écrit
        ``parcours_etapes`` (la liste) et ``parcours`` (« Agent › étape › étape »), seulement dans un
        groupe : un agent seul garde ses clés d'avant. ⛔ Ne lève jamais."""
        try:
            if not est_un_groupe(self.reglages_appel):
                return
            liste = self._gathered_context.setdefault("parcours_etapes", [])
            entree = {
                "agent": agent.workflow_name or None,
                "agent_id": agent.workflow_id or None,
                "etape": node.name,
                # Après le banc du 16/10 : où commence l'étape dans la conversation (le retour
                # au principal ne lui rend que les échanges de la dernière étape du spécialisé).
                "debut": len(self.context.messages) if self.context is not None else None,
            }
            dernier = liste[-1] if liste else None
            if dernier is not None and (
                dernier.get("agent_id"),
                dernier.get("etape"),
            ) == (entree["agent_id"], entree["etape"]):
                return
            liste.append({k: v for k, v in entree.items() if v is not None})
            self._gathered_context["parcours"] = rendre_le_parcours(liste)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[parcours] non noté : {e!r}")

    # --- [.mark] Chantier agents-specialises (lot 6) : principal chaud, préchauffage ---

    def est_le_principal(self, agent: AgentRuntime) -> bool:
        """``agent`` est-il le principal d'un groupe ? L'appel est porté par un groupe et
        l'agent n'a pas de principal au-dessus de lui. ⛔ Ne lève jamais."""
        try:
            return bool(
                agent is not None
                and agent.is_child
                and est_un_groupe(self.reglages_appel)
                and agent_principal_de(agent.reglages) is None
                and self.agent_transfer_enabled
            )
        except Exception:  # noqa: BLE001
            return False

    def garder_chaud(self, source: AgentRuntime) -> bool:
        """Le principal qui passe la main est désactivé, PAS libéré (A5) : rend ``True`` quand
        ``source`` est le principal et reste donc ouvert. Un agent seul : ``False`` (libéré
        comme avant). ⛔ Ne lève jamais."""
        if not self.est_le_principal(source):
            return False
        self._principal_chaud = source
        return True

    def principal_chaud_pour(self, workflow_id: int) -> Optional[AgentRuntime]:
        """Le principal resté chaud, s'il est la cible demandée et encore utilisable (sans
        erreur, non libéré, pipeline vivant) ; ``None`` sinon (construction normale)."""
        chaud = self.__dict__.get("_principal_chaud")
        if (
            chaud is None
            or chaud.workflow_id != workflow_id
            or chaud is self._active_agent
            or chaud.error
            or not chaud.is_running
        ):
            return None
        return chaud

    def lancer_prechauffage(self) -> None:
        """Au décroché, après le premier agent : charge à l'avance (sans voix) ce que la
        construction des agents cibles lira en base. En tâche de fond, jamais bloquant,
        réglage ``prechauffage_agents`` (vrai par défaut dans un groupe). ⛔ Ne lève jamais."""
        from api.services.phrases.sons import lancer_la_fabrique

        try:
            if not self.agent_transfer_enabled or not prechauffage_actif(self.reglages_appel):
                # fiabilite-orchestration, lot 4 ter (F22) : les sons des phrases du premier agent.
                lancer_la_fabrique(self)
                return
            agent = self.active_agent

            async def preparer() -> None:
                precharge = await prechauffer_les_cibles(
                    self._agent_factory,
                    agent.workflow,
                    ids_a_exclure={agent.workflow_id},
                    lire_outils=db_client.get_tools_by_uuids,
                )
                # [.mark] fiabilite-orchestration, lot 3 (F5, F6) : puis la réserve, chaque
                # collègue construit à l'avance (service, worker, cerveau de fond).
                if precharge is not None:
                    for cible in list(precharge.agents):
                        await self._mettre_en_reserve(cible)
                # Lot 4 ter (F22) : puis les sons des phrases de l'appel (collègues compris).
                lancer_la_fabrique(self)

            self._tache_prechauffage = asyncio.get_running_loop().create_task(preparer())
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[prechauffage] non lancé : {e!r}")

    async def _mettre_en_reserve(self, workflow_id: int) -> None:
        """[.mark] fiabilite-orchestration, lot 3 (F5, F6) : construit ``workflow_id`` à l'avance
        (inactif sous l'appel) avec son cerveau de fond, et le range dans la réserve de l'appel.
        Un échec n'y range rien : la passation construira comme avant. ⛔ Ne lève jamais."""
        precharge = precharge_de(self)
        # Revue du 19/10 : deux passations rapprochées vers le même collègue ne lancent qu'une
        # construction (sinon la seconde écraserait la première, un worker resterait orphelin).
        en_construction = self.__dict__.setdefault("_reserve_en_construction", set())
        if (
            precharge is None
            or workflow_id in precharge.prets
            or workflow_id in en_construction
            or self.is_call_disposed()
        ):
            return
        en_construction.add(workflow_id)
        try:
            from api.services.workflow.agent_runtime import new_visit_id

            debut = time.monotonic()
            runtime = await self._agent_factory.build(
                workflow_id=workflow_id, visit_id=new_visit_id()
            )
            runtime.preconstruit = True
            await self.preparer_le_travail(runtime)
            from api.services.panne.garde_modele import garder_l_agent

            await garder_l_agent(self, runtime)
            if self.is_call_disposed():
                return
            precharge.prets[workflow_id] = runtime
            logger.info(
                f"[prechauffage] agent {workflow_id} construit à l'avance en "
                f"{time.monotonic() - debut:.3f}s (réserve : {len(precharge.prets)})"
            )
        except Exception as e:  # noqa: BLE001 -- la passation construira normalement
            precharge.echecs[workflow_id] = repr(e)
            logger.warning(f"[prechauffage] agent {workflow_id} non construit à l'avance : {e!r}")
        finally:
            en_construction.discard(workflow_id)

    def _prendre_dans_la_reserve(self, workflow_id: int) -> Optional[AgentRuntime]:
        """[.mark] Lot 3 (F5) : le collègue construit à l'avance, s'il est encore utilisable ; il
        quitte la réserve, et un autre se construit en fond pour la passation suivante."""
        precharge = precharge_de(self)
        if precharge is None:
            return None
        runtime = precharge.prets.pop(workflow_id, None)
        if runtime is None:
            return None
        if runtime.error or not runtime.is_running:
            logger.warning(f"[prechauffage] agent {workflow_id} de la réserve inutilisable : construit")
            return None
        self._tache_du_groupe(self._mettre_en_reserve(workflow_id))
        return runtime

    async def lire_outils(self, uuids, organization_id: int) -> list:
        """Les outils d'un ensemble d'étapes : lus dans le cache de l'appel quand le
        préchauffage les a déjà chargés, sinon en base comme avant."""
        precharge = precharge_de(self)
        if precharge is None:
            return await db_client.get_tools_by_uuids(list(uuids), organization_id)
        return await precharge.outils(uuids, organization_id, db_client.get_tools_by_uuids)

    def set_audio_config(self, audio_config) -> None:
        """Set the audio configuration for the pipeline."""
        self._audio_config = audio_config

    def set_parole_locale(self, queue_frame) -> None:
        """[.mark] Lot 3 (D7) : la route locale de la parole dictée pendant l'attente d'une
        passation (``AgentBridgeProcessor.dire_en_local``)."""
        self._parole_locale = queue_frame

    def set_transport_output(self, transport_output) -> None:
        """Set the transport output processor for direct audio playback.

        Audio queued here bypasses STT and the rest of the pipeline,
        going straight to the caller.
        """
        self._transport_output = transport_output
        self.speech_playback.bind_output(transport_output)
        self._bind_call_monitor(self.active_agent)

    def _conversation_enabled(self) -> bool:
        return self.agent_can_act(self.active_agent) and not self.transfer_in_progress

    def _response_watch_enabled(self, runtime: AgentRuntime) -> bool:
        from api.services.workflow.agent_transfer import TransferPhase

        coordinator = self._transfer_coordinator
        return self.agent_can_act(runtime) and (
            not self.transfer_in_progress or coordinator.phase is TransferPhase.OPENING
        )

    def _bind_call_monitor(self, runtime: AgentRuntime) -> None:
        self.speech_playback.observe_responses(runtime.llm)
        self.call_monitor.bind_source(
            runtime.llm, enabled=lambda: self._response_watch_enabled(runtime)
        )

    def expect_response(self) -> None:
        """Declare an explicit response request before dispatch to the agent."""
        self.call_monitor.expect_response(self.active_agent.llm)

    def _on_response_timeout(self, source) -> None:
        """Own failure recovery outside the stalled generation worker."""

        async def end_unresponsive_call():
            # An interruption or handoff can win the race with this task.
            if (
                source is not self.active_agent.llm
                or not self._response_watch_enabled(self.active_agent)
                or not self.call_monitor.response_timed_out(source)
            ):
                return
            logger.error(
                f"Response watchdog expired for visit {self.active_agent.visit_id}; "
                "ending the call after response audio stopped making progress"
            )
            # Provider retries already had the response budget. Replaying an
            # arbitrary workflow turn could duplicate a tool's side effects.
            await self.end_call_with_reason(
                EndTaskReason.PIPELINE_ERROR.value, abort_immediately=True
            )

        self._response_timeout_task = asyncio.create_task(
            end_unresponsive_call(), name="call-response-timeout"
        )

    def set_fetch_recording_audio(self, fetch_fn) -> None:
        """Set the recording audio fetcher callback."""
        self._fetch_recording_audio = fetch_fn

    def set_mute_pipeline(self, mute: bool) -> None:
        """Set the pipeline mute state.

        This controls whether user input should be muted via the CallbackUserMuteStrategy.
        When muted, the user's audio input will be blocked.

        Args:
            mute: True to mute user input, False to allow input
        """
        logger.debug(f"Setting pipeline mute state to: {mute}")
        self._mute_pipeline = mute

    async def handle_llm_text_frame(self, text: str, visit_id: Optional[str] = None):
        """Accumulate LLM text frames to build reference text.

        The reference text corrects the assistant aggregator's transcript, and
        that aggregator is call-scoped, so text from an agent that no longer
        owns the call is dropped rather than mixed into the running agent's.
        """
        if not self.owns_generation(visit_id):
            return
        # [.mark] fiabilite-orchestration, lot 3 : le premier mot de l'agent appelé (passation découpée).
        if text:
            self.mesure_passation.premier_mot(visit_id)
        self._current_llm_generation_reference_text += text

    def is_call_disposed(self):
        """Check whether a call has been disposed by the engine"""
        return self._call_disposed

    async def get_gathered_context(self) -> dict:
        """Read the call's gathered context.

        A copy, so a caller cannot edit the engine's state by accident: writes
        go through ``record_context`` / ``record_call_tags`` / the disposition
        recorders. Still shallow -- nested values are shared -- so treat the
        result as read-only rather than as an isolated snapshot.
        """
        return self._gathered_context.copy()

    async def _open_mcp_sessions(self, agent: AgentRuntime | None = None) -> None:
        """Connect every MCP-category tool referenced by any workflow node.
        Failures degrade (session marked unavailable); never raises."""
        from api.services.workflow.tools.mcp_tool import (
            McpDefinitionError,
            validate_mcp_definition,
        )

        agent = agent or self.active_agent
        try:
            tool_uuids: set[str] = set()
            for node in agent.workflow.nodes.values():
                for tu in getattr(node, "tool_uuids", None) or []:
                    tool_uuids.add(tu)
            if not tool_uuids:
                return

            organization_id = await self._get_organization_id()
            if not organization_id:
                logger.warning("Cannot open MCP sessions: organization_id missing")
                return

            tools = await self.lire_outils(sorted(tool_uuids), organization_id)
            for tool in tools:
                if tool.category != ToolCategory.MCP.value:
                    continue
                try:
                    cfg = validate_mcp_definition(tool.definition)
                except McpDefinitionError as e:
                    logger.warning(
                        f"Skipping MCP tool '{tool.name}' ({tool.tool_uuid}): "
                        f"invalid definition: {e}"
                    )
                    continue

                credential = None
                if cfg["credential_uuid"]:
                    try:
                        credential = await db_client.get_credential_by_uuid(
                            cfg["credential_uuid"], organization_id
                        )
                    except Exception as e:
                        logger.warning(
                            f"MCP tool '{tool.name}': credential fetch failed: {e}"
                        )
                        continue

                session = McpToolSession(
                    tool_uuid=tool.tool_uuid,
                    tool_name=tool.name,
                    url=cfg["url"],
                    credential=credential,
                    tools_filter=cfg["tools_filter"],
                    timeout_secs=cfg["timeout_secs"],
                    sse_read_timeout_secs=cfg["sse_read_timeout_secs"],
                )
                agent.mcp_sessions[tool.tool_uuid] = session
                await session.start_managed()
        except Exception as e:
            logger.warning(
                f"Failed to open MCP sessions; call proceeds without MCP tools: {e}",
                exc_info=True,
            )

    async def close_mcp_sessions(self) -> None:
        """Release connection owners, including on early call startup failure."""
        for agent in [self.active_agent, self.pending_agent, *self._retired_agents]:
            if agent is not None:
                await agent.close_mcp_sessions()

    async def cleanup(self):
        """Clean up engine resources on disconnect.

        Connection owners are finalized by close_mcp_sessions() in the run
        finally block, including failures before the pipeline starts.
        """
        self.speech_playback.cancel_all()
        # Cancel any pending timeout tasks
        if self._response_timeout_task and not self._response_timeout_task.done():
            self._response_timeout_task.cancel()
        # [.mark] Revue du 16/10 : un préchauffage encore en cours ne survit pas à l'appel.
        prechauffage = self.__dict__.get("_tache_prechauffage")
        if prechauffage is not None and not prechauffage.done():
            prechauffage.cancel()

        # [.mark] Lot 4 d'orchestrateur-trois-cerveaux (D8) : fin d'appel = travaux de fond annulés.
        for travail in list(self.__dict__.get("travaux", [])):
            await travail.fermer(forcer=True)

        # Cancel any in-flight background summarization.
        if self._context_summarization_manager:
            await self._context_summarization_manager.cleanup()

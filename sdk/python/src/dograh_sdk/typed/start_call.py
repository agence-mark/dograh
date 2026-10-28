"""GENERATED — do not edit by hand.

Regenerate with `python -m dograh_sdk.codegen` against the target
Dograh backend. Source of truth: the backend's model-backed node-spec
catalog served from `/api/v1/node-types`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, ClassVar, Literal, Optional

from dograh_sdk.typed._base import TypedNode


@dataclass(kw_only=True)
class StartCall_Extraction_variablesRow:
    """
    Each entry declares one variable to capture, with its name, data type,
    and extraction hint. Call outcomes are configured separately in workflow
    settings.
    """

    name: str
    """
    snake_case identifier used downstream.
    """
    type: Literal['string', 'number', 'boolean'] = 'string'
    """
    Data type of the extracted value.
    """
    prompt: Optional[str] = None
    """
    Per-variable hint describing what to look for.
    """

@dataclass(kw_only=True)
class StartCall(TypedNode):
    """
    Entry point of the workflow — plays a greeting and opens the
    conversation.  LLM hint: The entry point of every workflow (exactly one
    required). Plays an optional greeting, can fetch context from an
    external API before the call begins, and executes the first
    conversational turn.
    """

    type: ClassVar[str] = 'startCall'

    prompt: str
    """
    Agent system prompt for the opening turn. Supports
    {{template_variables}} from pre-call fetch and the initial context.
    """

    name: str = 'Start Call'
    """
    Short identifier shown in the canvas and call logs.
    """

    greeting_type: Literal['text', 'audio'] = 'text'
    """
    Whether the optional greeting is spoken via TTS from text or played from
    a pre-recorded audio file.
    """

    greeting: Optional[str] = None
    """
    Text spoken via TTS at the start of the call. Supports
    {{template_variables}}. Leave empty to skip the greeting.
    """

    greeting_recording_id: Optional[str] = None
    """
    Pre-recorded audio file played at the start of the call.
    """

    champs_etape: Optional[str] = None
    """
    Record fields this step gathers, in order of priority, separated by
    commas. Used only when "Show the model what is known and what is
    expected" is on in the agent's settings: the code then names the missing
    ones ("Still expected: …"), and the step's tools wait until they are
    known.
    """

    qui_decide_du_passage: Optional[Literal['agent', 'collecte', 'choix', 'libre']] = None
    """
    Agent (default): the model alone takes the exits. Collection: the code
    takes the first exit once every field of the step is gathered. Choice:
    the code takes the exit whose condition on the record holds, else the
    arbiter chooses. Free: the agent leads, the arbiter is the safety net.
    """

    moment_du_passage: Optional[Literal['apres_la_reponse', 'attendre_le_dernier_champ']] = None
    """
    After the reply (default): the code passes once the agent has answered.
    Wait for the last field: when a single field is missing, the request
    waits (briefly) for the clerk to read the caller's last words, and the
    next step speaks at once.
    """

    delai_du_passage: Optional[float] = None
    """
    Longest wait for the clerk before the usual timing plays instead.
    Default 1.5.
    """

    arbitre: Optional[bool] = None
    """
    A separate small model, asked in parallel as the caller finishes
    speaking, which exit (if any) the conversation calls for. Empty: off,
    except on a Choice or Free step. It passes only when sure.
    """

    seuil_de_l_arbitre: Optional[float] = None
    """
    Lowest confidence at which the arbiter's choice is taken (0 to 1).
    Default 0.8.
    """

    allow_interrupt: bool = False
    """
    When true, the user can interrupt the agent mid-utterance.
    """

    add_global_prompt: bool = True
    """
    When true and a Global node exists, prepends the global prompt to this
    node's prompt at runtime.
    """

    delayed_start: bool = False
    """
    Set the initial listening window for outbound voicemail and screening
    handling. A brief human greeting can end the wait sooner.
    """

    delayed_start_duration: float = 1.2
    """
    Seconds to listen for a silent answer before opening. 0.1–10. Replaces
    the default 1.2-second listening window.
    """

    extraction_enabled: bool = False
    """
    When true, runs an LLM extraction pass for this node.
    """

    extraction_prompt: Optional[str] = None
    """
    Overall instructions guiding variable extraction.
    """

    extraction_variables: list[StartCall_Extraction_variablesRow] = field(default_factory=list)
    """
    Each entry declares one variable to capture, with its name, data type,
    and extraction hint. Call outcomes are configured separately in workflow
    settings.
    """

    tool_uuids: list[str] = field(default_factory=list)
    """
    Tools the agent can invoke during the opening turn.
    """

    document_uuids: list[str] = field(default_factory=list)
    """
    Documents the agent can reference.
    """

    pre_call_fetch_mode: Literal['disabled', 'always', 'inbound', 'outbound'] = 'disabled'
    """
    Controls when a POST request is made to enrich the call context before
    the Start node opens.
    """

    pre_call_fetch_url: Optional[str] = None
    """
    URL the pre-call POST request is sent to. The request body includes
    caller and called numbers.
    """

    pre_call_fetch_credential_uuid: Optional[str] = None
    """
    Optional credential attached to the pre-call request.
    """


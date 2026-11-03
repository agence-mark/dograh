"""Pydantic schemas for reusable Dograh tools.

These models are the single contract for tool creation/update across the
REST API, generated SDKs, and the MCP authoring surface. Field descriptions
are human/API-facing; ``llm_hint`` JSON schema extras are guidance for LLMs
when the same schema is surfaced through MCP or SDK authoring flows.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

from api.enums import ToolCategory

DEFAULT_MCP_TIMEOUT_SECS = 30
DEFAULT_MCP_SSE_READ_TIMEOUT_SECS = 300
MAX_TRANSFER_CALL_DISPOSITION_LENGTH = 64

ToolParameterType = Literal["string", "number", "boolean", "object", "array"]
HttpMethod = Literal["GET", "POST", "PUT", "PATCH", "DELETE"]
ToolCategoryValue = Literal[
    "http_api",
    "end_call",
    "transfer_call",
    "transfer_agent",
    "calculator",
    "native",
    "integration",
    "mcp",
]


def _llm_hint(text: str) -> dict[str, str]:
    return {"llm_hint": text}


class ToolParameter(BaseModel):
    """A parameter that the tool accepts from the model at call time."""

    name: str = Field(
        description="Parameter name used as a key in the tool request body.",
        json_schema_extra=_llm_hint(
            "Use a stable snake_case name the agent can naturally fill."
        ),
    )
    type: ToolParameterType = Field(
        description="JSON type for the parameter value.",
        json_schema_extra=_llm_hint(
            "Allowed values are string, number, boolean, object, and array."
        ),
    )
    description: str = Field(
        description="Description shown to the model for this parameter.",
        json_schema_extra=_llm_hint(
            "Write this as an instruction to the agent: what value to provide and when."
        ),
    )
    required: bool = Field(
        default=True,
        description="Whether this parameter is required when the tool is called.",
    )
    # [.mark] U3 sexies (E74) : où le paramètre part dans la requête, ses valeurs permises et son défaut.
    # ``None`` : le comportement d'avant (corps pour POST/PUT/PATCH, requête pour GET/DELETE).
    emplacement: Literal["chemin", "requete", "corps", "en_tete"] | None = Field(
        default=None,
        description="Where the value goes in the request: path, query, body or header. Empty: as before.",
    )
    valeurs_permises: list[str] | None = Field(
        default=None,
        max_length=100,
        description="Closed list of allowed values. Empty: any value.",
    )
    defaut: Any | None = Field(
        default=None,
        description="Value used when the model gives none. Must be an allowed value when a list is set.",
    )

    @model_validator(mode="after")
    def _defaut_permis(self) -> ToolParameter:
        if self.defaut is not None and self.valeurs_permises and str(self.defaut) not in self.valeurs_permises:
            raise ValueError(f"The default of {self.name} is not one of its allowed values.")
        return self


class PresetToolParameter(BaseModel):
    """A parameter injected by Dograh at runtime."""

    name: str = Field(description="Parameter name used as a key in the request body.")
    type: ToolParameterType = Field(
        description="JSON type for the resolved value.",
        json_schema_extra=_llm_hint(
            "Allowed values are string, number, boolean, object, and array."
        ),
    )
    value_template: str = Field(
        description="Fixed value or template, e.g. {{initial_context.phone_number}}.",
        json_schema_extra=_llm_hint(
            "Use {{initial_context.*}} for call-start context and "
            "{{gathered_context.*}} for values extracted during the call."
        ),
    )
    required: bool = Field(
        default=True,
        description="Whether the parameter must resolve to a non-empty value.",
    )


class EnteteDeRequete(BaseModel):
    """[.mark] U3 sexies (E74) : un en-tête de requête, en clair, tiré d'une variable ou secret (jamais réaffiché)."""

    nom: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9!#$%&'*+.^_`|~-]+$", description="Header name.")
    sorte: Literal["texte", "variable", "secret"] = Field(
        default="texte",
        description=(
            "text: the value as written; variable: a template such as {{initial_context.x}}; "
            "secret: the value lives in an encrypted credential of the organization and is never shown again."
        ),
    )
    valeur: str | None = Field(default=None, max_length=2000, description="Text or template. Not for a secret.")
    identifiant_uuid: str | None = Field(
        default=None, max_length=36, description="Credential holding the secret value. Only for a secret."
    )

    @model_validator(mode="after")
    def _selon_la_sorte(self) -> EnteteDeRequete:
        if self.sorte == "secret":
            if not self.identifiant_uuid:
                raise ValueError("A secret header names the credential that holds its value.")
            if self.valeur:
                raise ValueError("A secret header carries no value of its own.")
        elif not (self.valeur or "").strip():
            raise ValueError("A header needs a value.")
        return self


class CopieDansLaFiche(BaseModel):
    """[.mark] U3 sexies (E74) : une valeur de la réponse recopiée dans la fiche de l'appel (``gathered_context``)."""

    chemin: str = Field(min_length=1, max_length=200, description="Path in the answer, such as client.id or items.0.name.")
    cle: str = Field(
        min_length=1, max_length=64, pattern=r"^[a-z][a-z0-9_]{0,63}$", description="Key written in the call record."
    )


class ReponseSimulee(BaseModel):
    """[.mark] U3 sexies (E74) : une réponse enregistrée, servie à l'essai et au banc seulement, jamais en appel réel."""

    nom: str = Field(default="Réponse simulée", max_length=80)
    quand: dict[str, str] = Field(
        default_factory=dict,
        description="Served when every given parameter has this value. Empty: served whatever the parameters.",
    )
    statut: int = Field(default=200, ge=100, le=599)
    donnees: Any = Field(default=None, description="The body of the answer.")


class ComportementOutil(BaseModel):
    """[.mark] U3 sexies point 3 (E74) : le comportement commun aux types qui appellent l'extérieur. Tout vit dans
    ``definition.config`` (aucune migration). Les valeurs par défaut gardent le comportement d'avant."""

    phrase_avant_mode: Literal["auto", "toujours", "jamais"] | None = Field(
        default=None,
        description=(
            "Sentence said before the tool. auto: only if the tool is slow; always; never. "
            "Empty: always when a sentence is written (as before)."
        ),
    )
    mode_execution: Literal["immediat", "apres_la_phrase", "arriere_plan"] = Field(
        default="immediat",
        description=(
            "immediat: the tool starts at once; apres_la_phrase: it starts when the sentence is finished; "
            "arriere_plan: the model gets an immediate answer and the result lands in the call record "
            "(a tool that only reads)."
        ),
    )
    interruption_appelant: bool = Field(
        default=False, description="The caller may cut the sentence said before and while the tool works."
    )
    son_pendant_enregistrement_id: int | None = Field(
        default=None, description="Recording played once while the tool works, past the patience threshold."
    )
    phrase_attente: str | None = Field(
        default=None, max_length=300, description="Said once if the tool has not finished after the patience threshold."
    )
    seuil_patience_ms: int = Field(default=1200, ge=0, le=15000, description="Patience threshold in milliseconds.")
    phrase_repli: str | None = Field(default=None, max_length=300, description="Said when the tool fails.")
    # Gérés par le serveur (la route d'essai les écrit, une mise à jour de l'outil les conserve).
    dernier_essai: dict[str, Any] | None = Field(
        default=None, description="Server-managed: the last trial (success, mode, date)."
    )
    premier_essai: dict[str, Any] | None = Field(
        default=None, description="Server-managed: who validated the first trial, and when."
    )


class HttpApiConfig(ComportementOutil):
    """Configuration for HTTP API tools."""

    method: HttpMethod = Field(
        description="HTTP method to use for the request.",
        json_schema_extra=_llm_hint("Use one of GET, POST, PUT, PATCH, DELETE."),
    )
    url: str = Field(
        description="Target HTTP or HTTPS URL.",
        json_schema_extra=_llm_hint(
            "Use the final endpoint URL. Authentication belongs in credential_uuid, "
            "not embedded in the URL."
        ),
    )
    headers: dict[str, str] | None = Field(
        default=None,
        description="Static headers to include with every request.",
        json_schema_extra=_llm_hint(
            "Do not place secrets here. Store secrets in the UI credential manager "
            "and reference them with credential_uuid."
        ),
    )
    credential_uuid: str | None = Field(
        default=None,
        description="Reference to an external credential for request authentication.",
        json_schema_extra=_llm_hint(
            "Use a credential_uuid returned by list_credentials. The MCP flow does "
            "not create credential secrets."
        ),
    )
    parameters: list[ToolParameter] | None = Field(
        default=None,
        description="Parameters the model must provide when calling this tool.",
    )
    preset_parameters: list[PresetToolParameter] | None = Field(
        default=None,
        description=(
            "Parameters injected by Dograh from fixed values or workflow context "
            "templates."
        ),
    )
    timeout_ms: int | None = Field(
        default=5000,
        ge=1,
        description="Request timeout in milliseconds.",
    )
    # [.mark] correctifs-apres-banc-v4, lot 3 : les essais. Défaut 0 = une seule requête, comme avant.
    essais: int = Field(
        default=0,
        ge=0,
        le=2,
        description=(
            "Extra attempts (0 to 2) when the service does not answer or is down. 0: a single request."
        ),
    )
    attente_entre_essais_s: float = Field(
        default=1.0,
        ge=0,
        le=30,
        description="Seconds to wait between two attempts.",
    )
    sans_risque_de_doublon: bool = Field(
        default=False,
        description=(
            "The tool can be called again without risk of a duplicate (a lookup, a search). Off: "
            "it is called again only when the request never left (connection refused, unknown host); "
            "a timeout or a 5xx answer is then not retried. A 4xx answer is never retried."
        ),
    )
    customMessage: str | None = Field(
        default=None,
        description=(
            "Custom message to play before the tool executes, while the "
            "request is in flight."
        ),
    )
    customMessageType: Literal["text", "audio"] | None = Field(
        default=None, description="Type of custom message."
    )
    customMessageRecordingId: str | None = Field(
        default=None, description="Recording ID for an audio custom message."
    )
    body_template: dict[str, Any] | None = Field(
        default=None,
        description="Optional JSON body template for POST, PUT, and PATCH requests.",
        json_schema_extra=_llm_hint(
            "Use {{parameter_name}} placeholders to position LLM and preset "
            "parameters anywhere in the body, including nested objects and arrays; "
            "also {{initial_context.*}}. A value that is exactly one placeholder "
            "keeps the value's original JSON type. Omit this field to send all "
            "parameters as a flat top-level JSON object. Ignored for GET and DELETE."
        ),
    )
    body_format: Literal["json", "form"] = Field(
        default="json",
        description=(
            "Encoding of the POST, PUT, and PATCH request body: 'json' sends "
            "application/json, 'form' sends application/x-www-form-urlencoded."
        ),
        json_schema_extra=_llm_hint(
            "Use 'form' only for APIs that accept form-encoded bodies and "
            "reject JSON. In form mode, list values repeat the field name once per "
            "item and object values are sent as JSON strings."
        ),
    )

    # [.mark] U3 sexies point 2 (E74)
    en_tetes_ext: list[EnteteDeRequete] = Field(
        default_factory=list,
        max_length=30,
        description="Headers as text, variable or secret. A secret is read from a credential, never shown.",
    )
    chemins_gardes: list[str] = Field(
        default_factory=list,
        max_length=50,
        description="Paths of the answer the model gets (others dropped). Empty: the whole answer.",
    )
    copies_dans_la_fiche: list[CopieDansLaFiche] = Field(
        default_factory=list,
        max_length=30,
        description="Values of the answer copied in the call record, before any filtering.",
    )
    reponses_simulees: list[ReponseSimulee] = Field(
        default_factory=list,
        max_length=20,
        description="Recorded answers served by the trial and the test bench only, never in a real call.",
    )

    @model_validator(mode="after")
    def _arriere_plan_seulement_en_lecture(self) -> HttpApiConfig:
        if self.mode_execution == "arriere_plan" and self.method != "GET" and not self.sans_risque_de_doublon:
            raise ValueError("The background mode is for a tool that only reads (GET, or marked without risk of duplicate).")
        return self

    @field_validator("method", mode="before")
    @classmethod
    def validate_method(cls, v: Any) -> str:
        if not isinstance(v, str):
            raise ValueError("method must be one of GET, POST, PUT, PATCH, DELETE")
        method = v.upper()
        if method not in {"GET", "POST", "PUT", "PATCH", "DELETE"}:
            raise ValueError("method must be one of GET, POST, PUT, PATCH, DELETE")
        return method


class EndCallConfig(BaseModel):
    """Configuration for End Call tools."""

    messageType: Literal["none", "custom", "audio"] = Field(
        default="none", description="Type of goodbye message."
    )
    customMessage: str | None = Field(
        default=None, description="Custom message to play before ending the call."
    )
    audioRecordingId: str | None = Field(
        default=None, description="Recording ID for audio goodbye message."
    )
    endCallReason: bool = Field(
        default=False,
        description=(
            "When enabled, the model must provide a reason for ending the call. "
            "The reason is set as call disposition and added to call tags."
        ),
    )
    endCallReasonDescription: str | None = Field(
        default=None,
        description=(
            "Description shown to the model for the reason parameter. Used only "
            "when endCallReason is enabled."
        ),
    )


class HttpTransferResolverConfig(BaseModel):
    """HTTP endpoint used to resolve transfer destination at call time."""

    type: Literal["http"] = Field(default="http", description="Resolver type.")
    url: str = Field(description="HTTP or HTTPS endpoint for transfer resolution.")
    headers: dict[str, str] | None = Field(
        default=None,
        description="Static headers to include with every resolver request.",
    )
    credential_uuid: str | None = Field(
        default=None,
        description="Reference to an external credential for resolver authentication.",
    )
    timeout_ms: int = Field(
        default=3000,
        ge=500,
        le=5000,
        description="Resolver request timeout in milliseconds.",
    )
    wait_message: str | None = Field(
        default=None,
        description="Optional short message played while Dograh resolves routing.",
    )
    parameters: list[ToolParameter] | None = Field(
        default=None,
        description="Parameters the model may provide when calling this transfer tool.",
    )
    preset_parameters: list[PresetToolParameter] | None = Field(
        default=None,
        description=(
            "Parameters injected by Dograh from fixed values or workflow context "
            "templates."
        ),
    )

    @field_validator("url")
    @classmethod
    def validate_url(cls, v: str) -> str:
        if not isinstance(v, str) or not v.startswith(("http://", "https://")):
            raise ValueError("config.resolver.url must be an http(s) URL")
        return v


class ContextDestinationRoute(BaseModel):
    """Map one context value to a transfer destination."""

    context_value: str = Field(
        min_length=1,
        max_length=255,
        description="Context value that selects this destination.",
    )
    destination: str = Field(
        min_length=1,
        max_length=255,
        description=(
            "VICIdial in-group, SIP endpoint, E.164 phone number, or context "
            "template used when this route matches."
        ),
    )

    @field_validator("context_value", "destination")
    @classmethod
    def strip_non_empty(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("mapping values cannot be blank")
        return stripped


class ContextDestinationRule(BaseModel):
    """One context lookup with its value-to-destination routes."""

    context_path: str = Field(
        min_length=1,
        max_length=255,
        description=(
            "Context path used for routing. An unprefixed path checks gathered "
            "context first, then initial context; use initial_context.* or "
            "gathered_context.* to select one explicitly."
        ),
    )
    routes: list[ContextDestinationRoute] = Field(min_length=1, max_length=100)

    @field_validator("context_path")
    @classmethod
    def strip_context_path(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("context path cannot be blank")
        return stripped

    @model_validator(mode="after")
    def validate_unique_values(self):
        values = [route.context_value.casefold() for route in self.routes]
        if len(values) != len(set(values)):
            raise ValueError("context mapping values must be unique")
        return self


class ContextDestinationMappingConfig(BaseModel):
    """Resolve a transfer destination from gathered or initial context.

    Rules are evaluated in order. The first rule whose context value matches
    one of its routes wins; ``fallback_destination`` applies only when no rule
    matched. Destinations may be provider-native values or context templates.
    """

    rules: list[ContextDestinationRule] | None = Field(
        default=None,
        description="Ordered routing rules evaluated top to bottom; first match wins.",
    )
    context_path: str | None = Field(
        default=None,
        exclude=True,
        description=(
            "Deprecated single-rule context path. Use rules instead; accepted for "
            "backward compatibility."
        ),
    )
    routes: list[ContextDestinationRoute] | None = Field(
        default=None,
        exclude=True,
        description=(
            "Deprecated single-rule routes. Use rules instead; accepted for "
            "backward compatibility."
        ),
    )
    fallback_destination: str | None = Field(
        default=None,
        max_length=255,
        description=(
            "Optional provider-native destination or context template used when "
            "no rule matched."
        ),
    )

    @model_validator(mode="before")
    @classmethod
    def fold_single_rule(cls, data: Any) -> Any:
        """Accept the legacy single-rule shape (context_path plus routes)."""
        if not isinstance(data, dict) or data.get("rules") is not None:
            return data
        if "context_path" not in data and "routes" not in data:
            return data
        folded = {
            key: value
            for key, value in data.items()
            if key not in ("context_path", "routes")
        }
        folded["rules"] = [
            {"context_path": data.get("context_path"), "routes": data.get("routes")}
        ]
        return folded

    @model_validator(mode="after")
    def require_rules(self):
        if not self.rules:
            raise ValueError("context mapping rules must contain at least one rule")
        if len(self.rules) > 20:
            raise ValueError("context mapping rules cannot contain more than 20 rules")
        return self

    @field_validator("fallback_destination")
    @classmethod
    def normalize_fallback(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.strip() or None


class TransferCallConfig(BaseModel):
    """Configuration for Transfer Call tools."""

    destination_source: Literal["static", "dynamic", "context_mapping"] = Field(
        default="static",
        description=(
            "Whether the destination is static/template, resolved by HTTP, or "
            "selected by ordered gathered/initial-context mapping rules."
        ),
    )
    destination: str = Field(
        default="",
        description=(
            "Phone number, SIP endpoint, or template to transfer the call to, e.g. "
            "+1234567890, PJSIP/1234, or {{initial_context.transfer_destination}}."
        ),
    )
    messageType: Literal["none", "custom", "audio"] = Field(
        default="none", description="Type of message to play before transfer."
    )
    customMessage: str | None = Field(
        default=None, description="Custom message to play before transferring."
    )
    audioRecordingId: str | None = Field(
        default=None, description="Recording ID for audio message before transfer."
    )
    timeout: int = Field(
        default=30,
        ge=5,
        le=120,
        description="Maximum seconds to wait for the destination to answer.",
    )
    call_disposition: str | None = Field(
        default=None,
        max_length=MAX_TRANSFER_CALL_DISPOSITION_LENGTH,
        description=(
            "Optional disposition to record after a successful transfer. When "
            "omitted, Dograh records its provider-specific transfer default."
        ),
    )
    parameters: list[ToolParameter] | None = Field(
        default=None,
        description=(
            "Parameters the model may provide when calling this transfer tool, "
            "for example state, department, or transfer reason."
        ),
    )
    resolver: HttpTransferResolverConfig | None = Field(
        default=None,
        description="Optional resolver that determines transfer routing at call time.",
    )
    context_mapping: ContextDestinationMappingConfig | None = Field(
        default=None,
        description="Optional ordered context-to-destination routing rules.",
    )

    @field_validator("call_disposition", mode="before")
    @classmethod
    def normalize_call_disposition(cls, value: object) -> object:
        if isinstance(value, str):
            value = value.strip()
            return value or None
        return value

    @model_validator(mode="after")
    def validate_destination_source_config(self):
        if self.destination_source == "dynamic" and self.resolver is None:
            raise ValueError(
                "config.resolver is required when destination_source is dynamic"
            )
        if (
            self.destination_source == "context_mapping"
            and self.context_mapping is None
        ):
            raise ValueError(
                "config.context_mapping is required when destination_source is "
                "context_mapping"
            )
        return self


class McpToolConfig(ComportementOutil):
    """Configuration for a customer MCP server tool definition."""

    transport: Literal["streamable_http", "sse"] = Field(
        default="streamable_http",
        description="MCP transport protocol: streamable HTTP, or SSE.",
    )
    # [.mark] U3 sexies point 6 (E74)
    en_tetes_ext: list[EnteteDeRequete] = Field(
        default_factory=list, max_length=30, description="Free headers sent to the server (text, variable or secret)."
    )
    reglages_outils: dict[str, Literal["autorise", "confirmer", "desactive"]] = Field(
        default_factory=dict,
        description=(
            "Per MCP tool: allowed (default), confirm with the caller first, or disabled "
            "(a disabled tool is never offered to the model)."
        ),
    )
    customMessage: str | None = Field(default=None, description="Sentence said before a tool of this server.")
    customMessageType: Literal["text", "audio"] | None = Field(default=None, description="Type of that sentence.")
    customMessageRecordingId: str | None = Field(default=None, description="Recording ID for an audio sentence.")
    url: str = Field(
        description="MCP server URL. Must use http:// or https://.",
        json_schema_extra=_llm_hint("Use the server's streamable HTTP MCP endpoint."),
    )
    credential_uuid: str | None = Field(
        default=None,
        description="Reference to an external credential for MCP server auth.",
        json_schema_extra=_llm_hint(
            "Use a credential_uuid returned by list_credentials. Credentials are "
            "created by the user in the UI."
        ),
    )
    tools_filter: list[str] = Field(
        default_factory=list,
        description="Allowlist of MCP tool names to expose. Empty exposes all tools.",
        json_schema_extra=_llm_hint(
            "Use exact MCP tool names from the remote server catalog when you need "
            "to restrict the exposed tools."
        ),
    )
    timeout_secs: int = Field(
        default=DEFAULT_MCP_TIMEOUT_SECS,
        ge=0,
        description="Connection timeout in seconds.",
    )
    sse_read_timeout_secs: int = Field(
        default=DEFAULT_MCP_SSE_READ_TIMEOUT_SECS,
        ge=0,
        description="SSE read timeout in seconds.",
    )
    discovered_tools: list[dict[str, Any]] = Field(
        default_factory=list,
        description=(
            "Server-managed cache of the MCP server's tool catalog "
            "[{name, description}]. Populated best-effort by the backend."
        ),
        json_schema_extra=_llm_hint("Do not author this field; the server fills it."),
    )

    @field_validator("url")
    @classmethod
    def validate_url(cls, v: str) -> str:
        if not isinstance(v, str) or not v.startswith(("http://", "https://")):
            raise ValueError("config.url must be an http(s) URL")
        return v

    @field_validator("tools_filter")
    @classmethod
    def validate_tools_filter(cls, v: list[str]) -> list[str]:
        if not all(isinstance(tool_name, str) for tool_name in v):
            raise ValueError("config.tools_filter must be a list of strings")
        return v


class HttpApiToolDefinition(BaseModel):
    """Tool definition for HTTP API tools."""

    schema_version: int = Field(default=1, description="Schema version.")
    type: Literal["http_api"] = Field(description="Tool type.")
    config: HttpApiConfig = Field(description="HTTP API configuration.")


class EndCallToolDefinition(BaseModel):
    """Tool definition for End Call tools."""

    schema_version: int = Field(default=1, description="Schema version.")
    type: Literal["end_call"] = Field(description="Tool type.")
    config: EndCallConfig = Field(description="End Call configuration.")


class TransferCallToolDefinition(BaseModel):
    """Tool definition for Transfer Call tools."""

    schema_version: int = Field(default=1, description="Schema version.")
    type: Literal["transfer_call"] = Field(description="Tool type.")
    config: TransferCallConfig = Field(description="Transfer Call configuration.")


class TransferAgentConfig(BaseModel):
    """Configuration for Transfer Agent tools.

    One tool, one destination. An agent that can hand the caller to several
    places gets several of these tools, and the model chooses between them the
    way it chooses between any other tools -- by their names and descriptions.
    That keeps the routing decision in the one place the model already reasons
    about, and leaves nothing to configure here but where the call goes.

    Most of how a handoff sounds is fixed: the caller hears a ringer while the
    next agent is prepared. The handover line is configurable because it is
    caller-facing and Dograh runs in more than one language, and so is whether
    the next agent opens with its greeting, because an agent that greets
    callers on its own number should not re-introduce itself mid-conversation.
    """

    workflow_id: int = Field(
        description=(
            "Id of the Dograh agent to transfer to. Must be in the same "
            "organization, and must not be a speech-to-speech agent."
        ),
        json_schema_extra=_llm_hint(
            "Name the tool after this agent, e.g. 'Transfer to Billing', and "
            "describe when to use it -- that is what the model routes on."
        ),
    )
    message: str = Field(
        default="Let me connect you with the right person. One moment please.",
        max_length=500,
        description=(
            "Spoken by the current agent, in its own voice, before the caller "
            "is handed over. Supports template variables. Leave empty to hand "
            "over without saying anything."
        ),
    )
    play_greeting: bool = Field(
        default=True,
        description=(
            "Whether the destination agent opens with its Start Call greeting. "
            "When false, it skips the greeting and opens with a reply generated "
            "from the handover note, continuing the conversation instead of "
            "introducing itself."
        ),
    )


class TransferAgentToolDefinition(BaseModel):
    """Tool definition for Transfer Agent tools."""

    schema_version: int = Field(default=1, description="Schema version.")
    type: Literal["transfer_agent"] = Field(description="Tool type.")
    config: TransferAgentConfig = Field(description="Transfer Agent configuration.")


class CalculatorToolDefinition(BaseModel):
    """Tool definition for Calculator tools."""

    schema_version: int = Field(default=1, description="Schema version.")
    type: Literal["calculator"] = Field(description="Tool type.")


class McpToolDefinition(BaseModel):
    """Persisted MCP tool definition."""

    schema_version: int = Field(default=1, description="Schema version.")
    type: Literal["mcp"] = Field(description="Tool type.")
    config: McpToolConfig = Field(description="MCP server configuration.")


class IntegrationToolConfig(BaseModel):
    """[.mark] A connector's action (chantier l-agent-travaille, L5; plan connecteurs-agent D5 to D9,
    D17, D18). The organization is never here: the engine gives it (D6)."""

    connecteur: str = Field(min_length=1, max_length=64, description="Connector of the catalogue.")
    action: str = Field(min_length=1, max_length=64, description="Action of that connector.")
    reglages: dict[str, Any] = Field(
        default_factory=dict,
        description="The client's rules for this action (durations, ranges, notice…), from the audit.",
    )
    delai_ms: int = Field(default=5000, ge=500, le=15000, description="Deadline of the action during the call.")
    phrase_attente: str | None = Field(
        default=None,
        max_length=300,
        description=(
            "The patience phrase: said by the code, after the model's text, only when the tool "
            "has not finished after the patience threshold. Empty: nothing is ever said."
        ),
    )
    # [.mark] Lot D d'agent-leger-greffier (D6): the threshold of the patience phrase, and
    # the fields the action reads, found by the code before it runs (record, traces, clerk).
    seuil_patience_ms: int = Field(
        default=1200, ge=0, le=15000, description="Patience threshold: below it, nothing is said."
    )
    champs_requis: list[
        Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=64)]
    ] = Field(
        default_factory=list,
        max_length=20,
        description=(
            "Fields of the record the action needs. Missing ones are looked for in the reading "
            "modules' traces, then the clerk is waited for; still missing, the model is told to "
            "ask for them. Empty: the tool runs as before."
        ),
    )
    attente_max_ms: int = Field(
        default=2500, ge=0, le=15000, description="Longest wait for the clerk's pass."
    )
    sources_champs: list[Literal["fiche", "traces", "greffier"]] = Field(
        default_factory=lambda: ["fiche", "traces", "greffier"],
        description="Where the required fields are looked for, in this order.",
    )
    phrase_repli: str | None = Field(
        default=None, max_length=300, description="Said when the deadline passes or the software fails."
    )
    anticipable: bool = Field(
        default=False,
        description="Read-only actions only: launch it as soon as its trigger fields are in the record.",
    )
    declencheurs: dict[str, str] = Field(
        default_factory=dict,
        description="Parameter of the action → field of the record that gives it (anticipation).",
    )


    # Gérés par le serveur (U3 sexies point 4) : voir ``ComportementOutil``.
    dernier_essai: dict[str, Any] | None = Field(
        default=None, description="Server-managed: the last trial (success, mode, date)."
    )
    premier_essai: dict[str, Any] | None = Field(
        default=None, description="Server-managed: who validated the first trial, and when."
    )

    @model_validator(mode="after")
    def _action_connue(self) -> IntegrationToolConfig:
        from api.services.integrations.connectors.catalogue import trouver

        trouve = trouver(self.connecteur, self.action)
        if trouve is None:
            raise ValueError(f"Unknown action « {self.connecteur}.{self.action} ».")
        action = trouve[1]
        if self.anticipable and (action.ecrit or not action.anticipable_permis):
            raise ValueError("An action that writes is never anticipated.")
        noms = {p.nom for p in action.parametres}
        inconnus = sorted(set(self.declencheurs) - noms)
        if inconnus:
            raise ValueError(f"Not a parameter of the action: {', '.join(inconnus)}.")
        if self.anticipable and not self.declencheurs:
            raise ValueError("An anticipated action needs its trigger fields.")
        return self


class IntegrationToolDefinition(BaseModel):
    """[.mark] Tool definition of a connector's action (type ``integration``)."""

    schema_version: int = Field(default=1, description="Schema version.")
    type: Literal["integration"] = Field(description="Tool type.")
    config: IntegrationToolConfig = Field(description="Connector, action and the client's rules.")


class ChampRequisDuRappel(BaseModel):
    """[.mark] Un champ de la fiche que l'outil « demander un rappel » exige avant d'écrire."""

    champ: str = Field(pattern=r"^[a-z][a-z0-9_]{0,63}$", description="Name of the record field that must be noted.")
    libelle: str | None = Field(default=None, max_length=80, description="How the tool names it when it is missing.")
    repli_appel: str | None = Field(
        default=None,
        pattern=r"^[a-z][a-z0-9_]{0,63}$",
        description="A call variable that stands in for the field when it is not noted (the caller's own number).",
    )


class DemandeDeRappelConfig(BaseModel):
    """[.mark] Configuration de l'outil natif « demander un rappel » (agent-facon-tala, lot B1)."""

    action: Literal["demander_un_rappel"] = Field(description="The native action.")
    parameters: list[ToolParameter] = Field(default_factory=list, description="What the model gives (object, wished moment).")
    champs_requis: list[ChampRequisDuRappel] = Field(
        default_factory=list, description="Record fields that must be noted before the request is written."
    )
    call_disposition: str | None = Field(
        default=None,
        max_length=MAX_TRANSFER_CALL_DISPOSITION_LENGTH,
        description="Disposition recorded when the request is written, and only then.",
    )

    @field_validator("call_disposition", mode="before")
    @classmethod
    def normalize_call_disposition(cls, value: object) -> object:
        if isinstance(value, str):
            value = value.strip()
            return value or None
        return value


class NativeToolDefinition(BaseModel):
    """[.mark] Tool definition of a built-in action (type ``native``): the call-back request."""

    schema_version: int = Field(default=1, description="Schema version.")
    type: Literal["native"] = Field(description="Tool type.")
    config: DemandeDeRappelConfig = Field(description="Call-back request configuration.")


ToolDefinition = Annotated[
    HttpApiToolDefinition
    | EndCallToolDefinition
    | TransferCallToolDefinition
    | TransferAgentToolDefinition
    | CalculatorToolDefinition
    | McpToolDefinition
    | IntegrationToolDefinition
    | NativeToolDefinition,
    Field(discriminator="type"),
]


class CreateToolRequest(BaseModel):
    """Request schema for creating a reusable tool."""

    name: str = Field(
        max_length=255,
        description="Display name for the tool.",
        json_schema_extra=_llm_hint(
            "Use a concise action-oriented name; this influences the function "
            "name shown to the agent."
        ),
    )
    description: str | None = Field(
        default=None,
        description="Description shown to the agent when deciding whether to call it.",
        json_schema_extra=_llm_hint(
            "State exactly when the agent should call the tool and what result it gets."
        ),
    )
    category: ToolCategoryValue = Field(
        default=ToolCategory.HTTP_API.value,
        description="Tool category. Must match definition.type.",
    )
    icon: str | None = Field(
        default="globe", max_length=50, description="Lucide icon identifier."
    )
    icon_color: str | None = Field(
        default="#3B82F6", max_length=7, description="Hex color for the tool icon."
    )
    definition: ToolDefinition = Field(description="Typed tool definition.")

    @model_validator(mode="before")
    @classmethod
    def default_category_from_definition(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        if data.get("category"):
            return data
        definition = data.get("definition")
        if isinstance(definition, dict) and definition.get("type"):
            return {**data, "category": definition["type"]}
        return data

    @field_validator("category")
    @classmethod
    def validate_category(cls, v: str) -> str:
        valid_categories = [c.value for c in ToolCategory]
        if v not in valid_categories:
            raise ValueError(
                f"Invalid category '{v}'. Must be one of: {', '.join(valid_categories)}"
            )
        return v

    @model_validator(mode="after")
    def validate_category_matches_definition(self) -> CreateToolRequest:
        definition_type = self.definition.type
        if self.category != definition_type:
            raise ValueError(
                f"category '{self.category}' must match definition.type "
                f"'{definition_type}'"
            )
        return self


class UpdateToolRequest(BaseModel):
    """Request schema for updating a reusable tool."""

    name: str | None = Field(default=None, max_length=255)
    description: str | None = None
    icon: str | None = Field(default=None, max_length=50)
    icon_color: str | None = Field(default=None, max_length=7)
    definition: ToolDefinition | None = None
    status: str | None = None


class CreatedByResponse(BaseModel):
    """Response schema for the user who created a tool."""

    id: int
    provider_id: str


class ToolResponse(BaseModel):
    """Response schema for a reusable tool."""

    id: int
    tool_uuid: str
    name: str
    description: str | None
    category: str
    icon: str | None
    icon_color: str | None
    status: str
    definition: dict[str, Any]
    created_at: datetime
    updated_at: datetime | None
    created_by: CreatedByResponse | None = None

    model_config = ConfigDict(from_attributes=True)


class McpRefreshResponse(BaseModel):
    """Result of re-discovering an MCP server's tool catalog."""

    tool_uuid: str
    discovered_tools: list = Field(default_factory=list)
    error: str | None = None


class ToolTestRequest(BaseModel):
    """Request body for testing an HTTP API tool outside a live call."""

    llm_params: dict[str, Any] = Field(
        default_factory=dict,
        description="Values for parameters normally supplied by the model.",
    )
    preset_params: dict[str, Any] = Field(
        default_factory=dict,
        description="Resolved values for parameters normally supplied from presets.",
    )


class ToolTestResponse(BaseModel):
    """Result of testing an HTTP API tool."""

    status: str
    status_code: int | None = None
    data: Any | None = None
    error: str | None = None
    hint: str | None = None
    request_method: str
    request_url: str
    request_headers: dict[str, str] = Field(default_factory=dict)
    request_body: dict[str, Any] | None = None
    request_params: dict[str, Any] | None = None
    duration_ms: int

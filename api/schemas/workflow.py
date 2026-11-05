from datetime import datetime
from typing import Any, Dict

from pydantic import BaseModel

from api.enums import CallType


class WorkflowRunResponseSchema(BaseModel):
    id: int
    workflow_id: int
    workflow_name: str | None = None
    version_number: int | None = None
    name: str
    mode: str
    created_at: datetime
    is_completed: bool
    transcript_url: str | None
    recording_url: str | None
    user_recording_url: str | None = None
    bot_recording_url: str | None = None
    transcript_public_url: str | None = None
    recording_public_url: str | None = None
    user_recording_public_url: str | None = None
    bot_recording_public_url: str | None = None
    public_access_token: str | None = None
    cost_info: Dict[str, Any] | None
    usage_info: Dict[str, Any] | None = None
    definition_id: int | None  # This is for backward compatibility
    initial_context: dict | None = None
    gathered_context: dict | None = None
    call_type: CallType
    logs: Dict[str, Any] | None = None
    annotations: Dict[str, Any] | None = None
    # [.mark] V1b : la note du juge (colonne `note_juge`), lue par la page d'une conversation.
    note_juge: float | None = None
    # [.mark] N3b : le résumé de l'appel (une ou deux phrases) et sa source (synthese ou modele), lus par la page d'une conversation.
    resume: str | None = None
    resume_source: str | None = None

"""[.mark] The switch and the language rule of writing dictated numbers as digits.

Why this module exists
----------------------
On 2026-09-15 a phone number was dictated as "le zéro sept quatre vingt huit
vingt six quatorze zéro neuf". Deepgram Flux transcribed it correctly, in
words. Mistral then stitched those words back into eleven wrong digits, twice
in a row. The transcription was right; the model's arithmetic was not. The fix
hands the model digits (``text2num``, MIT, local, no network call).

Since the plan nombres-dictes (2026-09-16, N1), the writing itself is done by
the single reading step right before the model
(``api/services/pipecat/lecture_appelant.py``, reader in
``api/services/nombres/``), no longer by a step before the user aggregator:
``text2num`` there froze ONE reading of a postal code ("soixante sept cent
quarante" -> 67140). What stays here is what that step reads:

- the agent's switch, off by default;
- whether the agent's transcription is French.

🔒 The recorded transcript now keeps the caller's WORDS; the model, the
variable extraction and the call's context read the digits. The language is
the AGENT'S: after the aggregator a sentence no longer carries the language
its transcription detected.
"""

from loguru import logger

from api.schemas.workflow_configurations import WorkflowConfigurationDefaults

CLE_INTERRUPTEUR = "conversion_nombres_transcription"


def _est_francais(code) -> bool:
    return bool(code) and str(code).lower().startswith("fr")


def langue_agent_francaise(stt_config) -> bool:
    """Whether the agent's transcription is set up for French.

    1. ``stt.language`` starts with ``fr`` -> French.
    2. ``stt.language`` is ``multi`` or empty -> French only if
       ``stt.language_hints`` holds a code starting with ``fr``.
    3. Anything else -> not French.
    """
    langue = getattr(stt_config, "language", None)
    if _est_francais(langue):
        return True
    if not langue or str(langue).lower() == "multi":
        indications = getattr(stt_config, "language_hints", None) or []
        return any(_est_francais(code) for code in indications)
    return False


def conversion_allumee(run_configs: dict | None) -> bool:
    """The agent's switch, read alone through the schema (a stored null = default = off).

    ⛔ Only this key goes through the schema, not the whole configuration: any
    OTHER setting out of its bounds in the database (a max_call_duration of 0,
    hours of 5000 characters written by hand) made the call die at set-up.
    Counter-review of 2026-09-15.
    """
    try:
        return WorkflowConfigurationDefaults.model_validate(
            {CLE_INTERRUPTEUR: (run_configs or {}).get(CLE_INTERRUPTEUR)}
        ).conversion_nombres_transcription
    except Exception as erreur:  # noqa: BLE001 -- the call must go on
        logger.warning(f"[.mark] Number conversion switch unreadable, left off: {erreur!r}")
        return False

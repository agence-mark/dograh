"""Shared helpers for tuning pipecat ``TransportParams`` per run mode.

These live outside ``transport_setup.py`` (which is non-telephony only) so
that both the WebRTC factory there and the telephony provider factories
under ``api.services.telephony.providers/<name>/transport.py`` can call
into the same place.
"""

# Realtime (speech-to-speech) LLMs don't emit ``TTSStoppedFrame``, so the
# bot-stopped-speaking signal relies on the output-queue-drained fallback.
# The default 3s tail leaves a long gap before the assistant aggregator
# closes its turn; 0.5s keeps the conversation snappy without cutting into
# the bot's own audio (audio chunks arrive far more frequently than this).
REALTIME_BOT_VAD_STOP_SECS = 0.5


def realtime_param_overrides(is_realtime: bool) -> dict:
    """Return kwargs to splat into ``TransportParams`` for the given run mode.

    Currently this only tunes ``bot_vad_stop_secs``; new realtime-specific
    knobs should be added here so each transport stays a thin shim.
    """
    if not is_realtime:
        return {}
    return {"bot_vad_stop_secs": REALTIME_BOT_VAD_STOP_SECS}


# --------------------------------------------------------------------------- #
# [.mark] Noise filtering on the incoming audio
# --------------------------------------------------------------------------- #

FILTRE_DE_BRUIT_AUCUN = "none"
FILTRE_DE_BRUIT_RNNOISE = "rnnoise"


def filtre_de_bruit_overrides(run_configs: dict | None) -> dict:
    """Return the ``audio_in_filter`` kwarg for the agent's noise setting.

    🔑 Here, next to ``realtime_param_overrides``, for the same reason: this is
    the one place every transport passes through -- the browser one and the
    seven telephony ones. Wired transport by transport, the filter would apply
    to whichever ones were remembered, and to none added later.

    🔒 Default is no filter, which is today's behaviour. RNNoise is installed
    but off: a noise filter can just as easily get in the transcription's way,
    and that is judged on a real phone line, not decided here.

    ⛔ The import is deliberately lazy. ``pyrnnoise`` is an optional extra, and
    an extra missing from the image stops the API from starting at import time
    -- paid for on the Mistral patch. Imported only when an agent actually
    turns the filter on, a missing extra breaks that agent's call and nothing
    else.
    """
    choix = (run_configs or {}).get("audio_in_noise_filter") or FILTRE_DE_BRUIT_AUCUN
    if choix != FILTRE_DE_BRUIT_RNNOISE:
        return {}

    from pipecat.audio.filters.rnnoise_filter import RNNoiseFilter

    return {"audio_in_filter": RNNoiseFilter()}

"""[.mark] Non-regression test for the Pipecat settings stamp.

The questions this file answers:

    Does a voice call record the settings it was actually played with,
    defaults included -- and does the keyboard bench record none of them?

Why it exists
-------------
Without a stamp, a recorded call cannot say which pause, which voice detector
or which mute strategies produced it. An A/B result is then an anecdote: it
cannot be replayed, and nothing catches a setting that changed between two
runs. The same reasoning as the two stamps that came before this one, applied
to the settings this patch exposes.

🔑 The EFFECTIVE values, not only what the client filled in. A run stamped
with "nothing configured" becomes unreadable the day a patch moves a default:
the question after the fact is always "what did THIS call run with".

⛔ A stamp that lies is worse than no stamp. The keyboard bench goes through
neither the transcription, nor the voice, nor the turn strategies, so it
stamps none of this -- asserted below, and not only in a comment.
"""

import inspect

from api.schemas.workflow_configurations import WorkflowConfigurationDefaults
from api.services.pipecat.service_factory import (
    REGLAGES_PIPECAT_ESTAMPILLES,
    stamp_pipeline_settings,
)
from api.services.workflow import text_chat_runner


def test_un_appel_sans_reglage_est_estampille_avec_les_valeurs_effectives():
    """⛔ Not an empty record, and not nulls: the values that played."""
    estampille = stamp_pipeline_settings({}, {})["pipeline_settings"]
    assert estampille["user_speech_timeout"] == 0.6
    assert estampille["vad_stop_secs"] == 0.2
    assert estampille["audio_in_noise_filter"] == "none"
    assert estampille["mute_until_first_bot_complete"] is True
    assert estampille["tts_markdown_filter_enabled"] is False


def test_un_reglage_rempli_est_celui_qui_est_estampille():
    estampille = stamp_pipeline_settings(
        {}, {"user_speech_timeout": 1.5, "mute_always": True}
    )["pipeline_settings"]
    assert estampille["user_speech_timeout"] == 1.5
    assert estampille["mute_always"] is True
    # The rest keeps its effective default rather than disappearing.
    assert estampille["vad_confidence"] == 0.7


def test_lestampille_nefface_pas_les_estampilles_existantes():
    runtime = {"llm_sampling": {"temperature": 0.1}, "stt_settings": {}}
    stamp_pipeline_settings(runtime, {})
    assert runtime["llm_sampling"] == {"temperature": 0.1}
    assert "stt_settings" in runtime
    assert "pipeline_settings" in runtime


def test_lestampille_couvre_chaque_reglage_expose():
    """⛔ A setting exposed on screen but absent from the stamp is invisible
    after the fact: the A/B that used it could not be read back."""
    exposables = {
        nom
        for nom in WorkflowConfigurationDefaults.model_fields
        if nom.startswith(
            (
                "vad_",
                "smart_turn_pre",
                "smart_turn_max",
                "mute_",
                "tts_",
                "turn_wait",
                "turn_start_use",
                "incomplete_",
                "filter_incomplete",
                "audio_idle",
                "audio_in_noise",
                "user_speech_timeout",
                "user_turn_stop_timeout",
                "stt_ttfs",
            )
        )
    }
    manquants = exposables - set(REGLAGES_PIPECAT_ESTAMPILLES)
    assert manquants == set(), (
        f"These settings are configurable but are not stamped on the run: "
        f"{sorted(manquants)}. A call played with them could not say so."
    )


def test_lestampille_ne_prend_pas_toute_la_configuration():
    """⛔ An explicit list, not every key.

    Stamped wholesale, a run would carry per-service overrides, secrets, and
    whatever a later patch adds -- and nobody would notice.
    """
    estampille = stamp_pipeline_settings(
        {},
        {
            "user_speech_timeout": 1.5,
            "mark_per_service_override": True,
            "model_overrides": {"stt": {"api_key": "ne-doit-pas-sortir"}},
        },
    )["pipeline_settings"]
    assert "model_overrides" not in estampille
    assert "mark_per_service_override" not in estampille


def test_les_consignes_de_relance_ne_sont_pas_estampillees():
    """Free text, potentially long. What matters after the fact is how many
    times the agent asked before hanging up, and that IS stamped."""
    estampille = stamp_pipeline_settings({}, {})["pipeline_settings"]
    assert "user_idle_prompt" not in estampille
    assert "user_idle_goodbye_prompt" not in estampille
    assert estampille["user_idle_max_prompts"] == 1


def test_le_banc_au_clavier_nestampille_pas_ces_reglages():
    """⛔ It transcribes nothing, speaks nothing and runs no turn strategy.

    ⚠️ Read honestly, and the review of 14/09 was right to push on this. A
    lone negative assertion -- "this string is absent from that module" --
    would pass for ever on a string nobody ever wrote there, and would prove
    nothing while looking like a guarded invariant.

    So it is asserted in TWO parts: the module does stamp something (it calls
    ``stamp_sampling_settings``, which is true today and keeps this test
    pointed at a module that still stamps), and it does NOT stamp the Pipecat
    settings. The first half is what makes the second meaningful: if the
    keyboard bench stopped stamping altogether, or this import went stale, the
    test goes red instead of quietly passing.
    """
    source = inspect.getsource(text_chat_runner)
    assert "stamp_sampling_settings" in source, (
        "The keyboard bench no longer stamps anything at all, so the assertion "
        "below no longer says what it claims to say. Check what this module "
        "became before adjusting it."
    )
    assert "stamp_pipeline_settings" not in source, (
        "The keyboard bench stamps the Pipecat settings. It goes through none "
        "of them -- no transcription, no voice, no turn strategy -- so the "
        "stamp would describe settings that played no part in the run."
    )

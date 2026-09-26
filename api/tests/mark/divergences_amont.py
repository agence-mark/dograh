"""[.mark] The upstream tests we make fail ON PURPOSE, and why.

A fork that diverges from upstream has two honest options for the tests that
encode the behaviour it changed: delete them, or declare them. ⛔ Deleting is
the bad one -- it is silent, it hides the divergence from whoever merges the
next upstream release, and it removes the only place where the reason is
written down.

So they are declared here, and ``conftest.py`` marks them ``xfail``.

🔑 **``strict=True`` is the point of this file.** A declared divergence that
starts PASSING again is reported as a failure (``XPASS``), not quietly ignored.
That happens the day upstream changes its mind, or the day one of our patches
is lost in a merge -- and both are things we want to be told about, loudly.
It is the same invariant in both directions: the test must fail for the reason
we wrote, and it must stop failing the moment that reason disappears.

⛔ **Do not add a test here to make CI green.** The only thing that belongs in
this file is a behaviour Evan decided, written down elsewhere as a decision.
Anything else is a bug being papered over, and the next reader has no way to
tell the two apart.
"""

# Keyed by the test FILE (relative to ``api/``), then by the test FUNCTION name.
# 🆕 25/09/2026: when only SOME parameter sets of a function diverge, the value
# is a dict {parametrised id: reason} instead of a reason, and the other sets
# stay ordinary tests that must pass.
# ⛔ Deliberately not keyed by full parametrised id: those ids carry the values
# under test, so they churn on every upstream edit. Both functions below fail
# on ALL of their parameter sets -- checked, 2026-09-16 -- so the function name
# is exact here and does not swallow a passing case by accident.
# [.mark] E1 (25/09/2026) : l'accueil non interruptible par defaut.
_ACCUEIL_NON_INTERRUPTIBLE = (
    "[.mark] Decision d'Evan du 25/09/2026 (E1, reference/17-decisions.md) : "
    "l'accueil n'est PAS interruptible par defaut. Le micro de l'appelant reste "
    "coupe pendant la premiere phrase de l'agent (mute_until_first_bot_complete, "
    "ou FirstSpeech quand la supervision de decroche tourne), comme en "
    "production avant la montee sur 4e6cb22b. L'amont retire cette coupure pour "
    "les appels en cascade et laisse couper l'accueil a 2 mots ; chez nous c'est "
    "le reglage accueil_interruptible, eteint par defaut. Prouve le 25/09 : avec "
    "la coupure de l'amont, ces 141 tests passent tous."
)

# [.mark] E3 (25/09/2026) : l'export BigQuery neutralise.
_BIGQUERY_NEUTRALISE = (
    "[.mark] Decision d'Evan du 25/09/2026 (E3, reference/17-decisions.md, "
    "« un gros non ») : l'export des evenements d'appel vers BigQuery, seule "
    "destination de l'amont (0d5b68fb), est refuse cote serveur quelle que "
    "soit la configuration (registration() et l'entree de l'envoi). Ces tests "
    "de l'amont enregistrent ou envoient vers BigQuery. Prouve le 26/09 : "
    "garde retiree, les 24 tests des deux fichiers passent."
)

DIVERGENCES_ASSUMEES = {
    "tests/test_deepgram_endpoint_service_factory.py": {
        "test_unset_endpoint_falls_back_to_the_default_host": (
            "[.mark] Decision d'Evan du 16/09/2026 : une adresse Deepgram VIDE "
            "replie sur l'Europe, la ou l'amont replie sur son endpoint "
            "mondial. Sans ce repli, une configuration enregistree avant "
            "l'ouverture du champ enverrait l'audio de l'appelant aux "
            "Etats-Unis en silence. Voir Labo-agent-vocal/reference/17-decisions.md"
        ),
        "test_endpoint_is_offered_in_the_configuration_schema": (
            "[.mark] Decision d'Evan du 16/09/2026 : le champ d'adresse est "
            "bien offert et librement saisissable comme chez l'amont, mais son "
            "DEFAUT est l'endpoint europeen et non l'endpoint mondial. Les "
            "trois autres assertions de ce test (menu des regions, saisie "
            "libre) sont, elles, satisfaites."
        ),
    },
    "tests/test_answer_supervisor_late_speech.py": {
        "test_delayed_human_classification_answers_the_interruption_once": _ACCUEIL_NON_INTERRUPTIBLE,
        "test_discarded_final_segment_does_not_count_toward_next_partial": _ACCUEIL_NON_INTERRUPTIBLE,
        "test_disconnect_while_waiting_for_interrupting_turn": _ACCUEIL_NON_INTERRUPTIBLE,
        "test_human_after_screening_answers_when_recorded_greeting_already_ran": {
            "True": _ACCUEIL_NON_INTERRUPTIBLE,
        },
        "test_human_during_screening_reply_is_retained_and_releases_workflow": _ACCUEIL_NON_INTERRUPTIBLE,
        "test_human_interrupts_screening_reply_before_initial_greeting": _ACCUEIL_NON_INTERRUPTIBLE,
        "test_interrupted_greeting_text_is_logged_but_excluded_from_inference": _ACCUEIL_NON_INTERRUPTIBLE,
        "test_interrupted_greeting_waits_for_human_classification": _ACCUEIL_NON_INTERRUPTIBLE,
        "test_late_screening_interrupts_greeting_then_hands_over_once": _ACCUEIL_NON_INTERRUPTIBLE,
        "test_late_voicemail_interrupts_opening_then_applies_policy": _ACCUEIL_NON_INTERRUPTIBLE,
        "test_missing_final_does_not_answer_the_pre_greeting_hello": _ACCUEIL_NON_INTERRUPTIBLE,
        "test_second_partial_word_interrupts_greeting_and_answers_finished_turn": _ACCUEIL_NON_INTERRUPTIBLE,
        "test_speech_starting_during_recording_fetch_interrupts_at_two_words": {
            "False-False": _ACCUEIL_NON_INTERRUPTIBLE,
            "False-True": _ACCUEIL_NON_INTERRUPTIBLE,
        },
        "test_two_word_final_also_interrupts_and_answers_once": _ACCUEIL_NON_INTERRUPTIBLE,
    },
    "tests/test_answer_supervisor_playback.py": {
        "test_hello_produces_exactly_one_opening": {
            "text-0-True": _ACCUEIL_NON_INTERRUPTIBLE,
            "audio-0-True": _ACCUEIL_NON_INTERRUPTIBLE,
            "llm-1-True": _ACCUEIL_NON_INTERRUPTIBLE,
        },
    },
    "tests/test_answer_supervisor_wiring.py": {
        "test_initial_user_mute_depends_on_realtime_and_answer_handling": {
            "False-False-FunctionCallUserMuteStrategy": _ACCUEIL_NON_INTERRUPTIBLE,
            "False-True-FunctionCallUserMuteStrategy": _ACCUEIL_NON_INTERRUPTIBLE,
            "True-True-FunctionCallUserMuteStrategy": _ACCUEIL_NON_INTERRUPTIBLE,
        },
    },
    "tests/integrations/test_call_events.py": {
        "test_completed_call_exports_events_without_persisting_them": _BIGQUERY_NEUTRALISE,
    },
    "tests/test_call_event_sinks.py": {
        "test_settings_org_isolation_secret_roundtrip_and_validation": _BIGQUERY_NEUTRALISE,
        "test_partial_preferences_updates_preserve_legacy_settings_and_sink": _BIGQUERY_NEUTRALISE,
        "test_delivery_retries_only_failed_rows_and_honors_revocation": _BIGQUERY_NEUTRALISE,
        "test_delivery_retry_preserves_identity": _BIGQUERY_NEUTRALISE,
        "test_shutdown_drains_and_closes_submission": _BIGQUERY_NEUTRALISE,
    },
}

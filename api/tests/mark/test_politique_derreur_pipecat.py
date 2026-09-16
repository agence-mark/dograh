"""[.mark] Non-regression test for what a provider error does to a live call.

The question this file answers, and it answers only this one:

    Which provider failures END the caller's call, and which ones leave the
    agent silently standing?

Why it exists
-------------
Since Pipecat 1.8 an error no longer carries its own verdict. A failure is
classified into an ``ErrorCategory``; a PERMANENT category costs the processor
its usability, and the pipeline worker then applies its
``ProcessorUnusablePolicy``. Dograh sets that policy to ``CANCEL``, so a
permanently unusable service ends the call instead of leaving the agent mute.

⛔ We do not own any of that machinery -- it is upstream's, and upstream has its
own tests for it. This file exists because .mark DEPENDS on it, and a dependency
nobody asserts is a dependency that can change under us at the next version bump
without a single red light. What is protected here is the BOUNDARY:

* a rejected key, a forbidden resource, a malformed request (400, 401, 403, 404,
  422) end the call;
* 🔴 a spent quota (402), a rate limit (429) and a provider outage (5xx) do NOT.

That second line is the whole reason the ``delai-modele`` chantier still has to
exist: when Mistral answers 429 or 500, or simply never answers, the call stays
up and the caller hears nothing. Nothing in the upgrade changed that, and this
file is what will say so out loud the day it does.

⚠️ On the version this fork ran before 2026-09-16 this file does not fail, it
does not even import: ``pipecat.utils.errors`` and ``ProcessorUnusablePolicy``
did not exist. That is a red for the WRONG reason, and it is written down here
rather than claimed as proof.
"""

from types import SimpleNamespace

from pipecat.frames.frames import ErrorFrame
from pipecat.pipeline.worker import ProcessorUnusablePolicy
from pipecat.utils.errors import ErrorCategory, classify_http_status_code

from api.services.pipecat import pipeline_builder
from api.services.pipecat.termination_funnel_processor import is_terminal_error

# The verdict expected for each status code a provider actually returns to us.
# ⛔ Written as a literal, not derived from the same table the code reads: a
# table compared with itself always agrees.
FINS_DAPPEL = {400: True, 401: True, 403: True, 404: True, 422: True}
APPELS_QUI_SURVIVENT = {402: False, 429: False, 500: False, 502: False, 503: False}


def test_la_politique_du_pipeline_est_bien_lannulation(monkeypatch):
    """🔑 The single line .mark depends on, asserted on the BUILT worker.

    Pipecat's own default is ``CONTINUE`` -- report and keep running. On that
    default a rejected Deepgram key would leave the agent up and mute for the
    whole call. Asserted through the real builder rather than by reading the
    source, so moving the line somewhere else cannot keep this green.
    """
    captured = {}
    worker = SimpleNamespace(turn_tracking_observer=None)

    def capture_worker(*args, **kwargs):
        captured.update(kwargs)
        return worker

    monkeypatch.setenv("ENABLE_TURN_LOGGING", "false")
    monkeypatch.setattr(pipeline_builder, "PipelineWorker", capture_worker)

    pipeline_builder.create_pipeline_task(object(), workflow_run_id=88)

    assert captured["processor_unusable_policy"] is ProcessorUnusablePolicy.CANCEL
    assert ProcessorUnusablePolicy.CONTINUE is not ProcessorUnusablePolicy.CANCEL


def test_les_codes_qui_terminent_lappel():
    for code, termine in FINS_DAPPEL.items():
        categorie = classify_http_status_code(code)
        assert categorie.is_permanent is termine, (
            f"{code} -> {categorie}: a rejected key or a malformed request must "
            f"cost the service its usability, or the caller talks to a mute agent"
        )


def test_les_codes_qui_laissent_lappel_debout():
    """🔴 The half that keeps `delai-modele` necessary.

    ⛔ Not an oversight and not a bug to fix here: a rate limit or a provider
    outage may clear on the next attempt, so ending the call on them would hang
    up on callers a retry would have served. The consequence is that SOMETHING
    ELSE has to notice the silence, and that something does not exist yet.
    """
    for code, termine in APPELS_QUI_SURVIVENT.items():
        categorie = classify_http_status_code(code)
        assert categorie.is_permanent is termine, (
            f"{code} -> {categorie}: ending the call on a transient failure "
            f"would hang up on a caller a retry would have served"
        )


def test_la_frontiere_est_comptee_et_asserte_dans_les_deux_sens():
    """⛔ Both directions and the count, so a category added upstream shows up.

    Membership alone would stay green if upstream made QUOTA permanent, or added
    a tenth category nobody looked at. The exact set is the assertion.
    """
    permanentes = {c for c in ErrorCategory if c.is_permanent}
    assert permanentes == {
        ErrorCategory.AUTHENTICATION,
        ErrorCategory.AUTHORIZATION,
        ErrorCategory.INVALID_REQUEST,
    }
    assert len(permanentes) == 3
    assert len(ErrorCategory) == 9, "a category was added or removed upstream"


def test_un_code_inconnu_ne_raccroche_pas():
    """An unrecognised code is UNKNOWN, and UNKNOWN is not permanent.

    🔑 The safe direction: a status nobody classified must not hang up a call.
    """
    categorie = classify_http_status_code(418)
    assert categorie is ErrorCategory.UNKNOWN
    assert categorie.is_permanent is False


def test_lentonnoir_reconnait_le_meme_verdict():
    """The funnel decides a call outcome from the SAME notion of usability.

    ⛔ Two ways of deciding "this call is over" that could disagree would let a
    call end without being recorded, or be recorded without ending.
    """
    inutilisable = ErrorFrame("provider key rejected")
    inutilisable.processor = SimpleNamespace(is_usable=False)
    assert is_terminal_error(inutilisable) is True

    survivable = ErrorFrame("provider reconnecting")
    survivable.processor = SimpleNamespace(is_usable=True)
    assert is_terminal_error(survivable) is False

    # The deprecated flag is the same verdict from a service that still sets it.
    assert is_terminal_error(ErrorFrame("legacy", fatal=True)) is True

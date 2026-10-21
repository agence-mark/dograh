"""Callback factory helpers for :pyclass:`~api.services.workflow.pipecat_engine.PipecatEngine`.

Each helper takes a :class:`PipecatEngine` instance and returns an async
callback function suitable for passing to the various pipeline processors.
Separating these helpers into their own module keeps
``pipecat_engine.py`` focused on high-level engine orchestration logic while
encapsulating the callback implementations here for easier maintenance and
unit-testing.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from api.schemas.workflow_configurations import (
    DEFAULT_USER_IDLE_GOODBYE_PROMPT,
    DEFAULT_USER_IDLE_MAX_PROMPTS,
    DEFAULT_USER_IDLE_PROMPT,
)
from api.services.analyse_run.incidents_appel import noter_la_relance
from loguru import logger
from pipecat.frames.frames import (
    LLMMessagesAppendFrame,
)
from pipecat.utils.enums import EndTaskReason

if TYPE_CHECKING:
    from api.services.workflow.pipecat_engine import PipecatEngine


# ---------------------------------------------------------------------------
# User-idle handling
# ---------------------------------------------------------------------------


def _phrase_de_silence(engine: "PipecatEngine"):
    """[.mark] Lot 5 (F7) : la phrase en vigueur du motif « l'appelant se tait », ou ``None``.
    ⛔ Ne lève jamais."""
    try:
        from api.services.phrases.catalogue import APPELANT_SE_TAIT

        phrases = getattr(engine, "phrases", None)
        return phrases.phrase(APPELANT_SE_TAIT) if phrases is not None else None
    except Exception as erreur:  # noqa: BLE001
        logger.warning(f"[phrases] phrase de silence illisible : {erreur!r}")
        return None


def delai_de_la_relance(engine: "PipecatEngine") -> float | None:
    """[.mark] Lot 5 : le délai posé par la règle « l'appelant se tait » ; ``None`` : le réglage
    de Rythme (``max_user_idle_timeout``) reste le délai."""
    phrase = _phrase_de_silence(engine)
    if phrase is not None and phrase.dite and phrase.delai_pose:
        return phrase.delai_s
    return None


def relance_suspendue(engine: "PipecatEngine") -> bool:
    """[.mark] Lot 5 : aucune relance pendant un travail de fond en cours. ⛔ Ne lève jamais."""
    try:
        from api.services.travail.agent import ligne_du_travail

        return ligne_du_travail(engine) is not None
    except Exception:  # noqa: BLE001
        return False


async def _relance_dite_par_la_voix(engine: "PipecatEngine") -> bool:
    """[.mark] Lot 5 (F7) : la relance est la phrase fixe du motif « l'appelant se tait », dite
    par la voix sans le modèle. ``True`` : le cas est réglé (dite, ou refusée par un verrou du
    diseur et re-surveillée) ; ``False`` : la règle est éteinte, le modèle relance comme avant."""
    from api.services.phrases.catalogue import APPELANT_SE_TAIT

    phrase = _phrase_de_silence(engine)
    if phrase is None or not phrase.dite:
        return False
    # Au clavier (sans sortie audio), une attente ne se dit pas : le modèle relance comme avant.
    if getattr(engine, "sans_sortie_audio", False) is True:
        return False
    dite = await engine.phrases.dire(APPELANT_SE_TAIT)
    moniteur = getattr(engine, "call_monitor", None)
    if moniteur is not None:
        moniteur.relance_par_la_voix(dite=dite)
    return True


async def handle_user_idle(engine: "PipecatEngine", aggregator, attempt: int) -> None:
    """Execute the monitor's idle decision; timing and retry state live there.

    [.mark] The two instructions and the number of prompts are the agent's own
    (`user_idle_prompt`, `user_idle_goodbye_prompt`, `user_idle_max_prompts`),
    read from the settings the call was set up with
    (`PipecatEngine.regler_relances`). Before, both texts were written here in
    English with exactly one prompt before the hang-up, and nothing on any
    screen said so. Their defaults are those very texts and that count: an
    agent that fills in nothing behaves exactly as upstream.

    ⚠️ They are INSTRUCTIONS given to the model, not sentences spoken word for
    word: each one already asks the model to answer in the caller's language.
    """
    reglages = getattr(engine, "reglages_relances", None) or {}
    idle_prompt = reglages.get("user_idle_prompt") or DEFAULT_USER_IDLE_PROMPT
    goodbye_prompt = (
        reglages.get("user_idle_goodbye_prompt") or DEFAULT_USER_IDLE_GOODBYE_PROMPT
    )
    # ⛔ `is None`, not `or`: 0 is a legitimate value (hang up on the first
    # silence) and `or` would silently turn it back into 1.
    max_prompts = reglages.get("user_idle_max_prompts")
    max_prompts = DEFAULT_USER_IDLE_MAX_PROMPTS if max_prompts is None else int(max_prompts)
    # [.mark] correctifs-apres-banc-v4 (lot 4, décision 1 d'Evan) : le nombre de relances est lu dans la
    # règle « l'appelant se tait » quand elle le pose ; sinon les réglages de Rythme, comme avant.
    regle = _phrase_de_silence(engine)
    if regle is not None and regle.active and regle.max_pose:
        max_prompts = regle.max_par_attente

    logger.debug(f"Handling user_idle, attempt: {attempt}")
    # [.mark] The run keeps each reminder (langwatch-et-fenetre-du-run, lot 2).
    await noter_la_relance(engine, attempt, raccroche=attempt > max_prompts)
    if attempt <= max_prompts:
        # [.mark] Lot 5 (F7) : phrase fixe dite par la voix, sans le modèle (règle allumée,
        # défaut) ; éteinte : la relance par le modèle d'avant (`user_idle_prompt`).
        if await _relance_dite_par_la_voix(engine):
            return
        await aggregator.push_frame(
            LLMMessagesAppendFrame(
                [{"role": "user", "content": idle_prompt}], run_llm=True
            )
        )
        return
    # [.mark] La sortie réglée dans la règle (« Ensuite » : dire, noter dans la fiche, puis raccrocher,
    # transférer ou continuer) remplace le au revoir donné au modèle. Un transfert qui ne part pas laisse
    # le au revoir d'avant : l'appelant n'est jamais abandonné.
    if regle is not None and regle.active and regle.sortie_posee:
        from api.services.phrases.sorties import executer

        issue = await executer(
            engine,
            engine.phrases,
            regle,
            raison_de_fin=EndTaskReason.USER_IDLE_MAX_DURATION_EXCEEDED.value,
        )
        if issue.prise_en_main or issue.action == "continuer":
            return
    await aggregator.push_frame(
        LLMMessagesAppendFrame([{"role": "user", "content": goodbye_prompt}], run_llm=True)
    )
    await engine.end_call_with_reason(
        EndTaskReason.USER_IDLE_MAX_DURATION_EXCEEDED.value
    )


# ---------------------------------------------------------------------------
# Max-duration handling
# ---------------------------------------------------------------------------


def create_max_duration_callback(engine: "PipecatEngine"):
    """Return a callback that cancels the task when the hard call limit is exceeded."""

    async def handle_max_duration():
        logger.debug("Max call duration exceeded. Terminating call")
        await engine.end_call_with_reason(
            EndTaskReason.CALL_DURATION_EXCEEDED.value,
            abort_immediately=True,
        )

    return handle_max_duration


# ---------------------------------------------------------------------------
# Generation-started handling
# ---------------------------------------------------------------------------


def create_generation_started_callback(
    engine: "PipecatEngine", *, visit_id: str | None = None
):
    """Return a callback that resets flags at the start of each LLM generation.

    Args:
        engine: The call's engine.
        visit_id: The agent visit whose generation stage fires this. A
            generation starting in an agent that has already handed the call
            over is ignored, so it cannot clear the reference text the new
            agent is mid-way through building.
    """

    async def handle_generation_started():
        if not engine.owns_generation(visit_id):
            logger.debug(f"Ignoring generation start from retired visit {visit_id}")
            return
        logger.debug("LLM generation started in callback processor")
        # Clear reference text from previous generation
        engine._current_llm_generation_reference_text = ""

    return handle_generation_started


def create_aggregation_correction_callback(engine: "PipecatEngine"):
    """Create a callback that uses engine's reference text to correct corrupted aggregation."""

    def correct_corrupted_aggregation(ref: str, corrupted: str) -> str:
        """Correct corrupted text by aligning it with reference text.

        This is a pure function that doesn't depend on engine instance.
        """
        # 1) Safety check: if ref (minus spaces) is shorter than corrupted, bail out
        # also if corrupted is less than 10 characters, lets also return that since most likely
        # Elevenlabs returned the right alignment
        alnum_corr = "".join(ch for ch in corrupted if ch.isalnum())
        alnum_ref = "".join(ch for ch in ref if ch.isalnum())

        if corrupted in ref or len(alnum_ref) < len(alnum_corr) or len(alnum_corr) < 10:
            return corrupted

        logger.debug(
            f"In correct_corrupted_aggregation: ref: {ref} corrupted: {corrupted}"
        )

        # 2) Find where in `ref` we should start aligning.
        #    We take the first N (N=10) characters of `corrupted`
        #    and look for all their occurrences in `ref`.
        #    We pick the *last* one
        prefix = corrupted[:10]

        # find all start‐indices of that prefix in ref
        starts = [m.start() for m in re.finditer(re.escape(prefix), ref)]
        start_idx = starts[-1] if starts else 0

        # 3) Now run the same two‑pointer scan from start_idx
        i, j = start_idx, 0
        out_chars = []
        while i < len(ref) and j < len(corrupted):
            r_ch, c_ch = ref[i], corrupted[j]
            if r_ch == c_ch:
                out_chars.append(r_ch)
                i += 1
                j += 1

            elif c_ch == " ":
                # extra space in corrupted → skip it
                j += 1

            elif r_ch == " " or r_ch in ".,;:!?":
                # missing structural char in corrupted → emit from ref
                out_chars.append(r_ch)
                i += 1

            else:
                # letter mismatch → best‑effort copy from ref
                out_chars.append(r_ch)
                i += 1
                j += 1

        # 4) A final check - the final created output should be exactly
        # as corrupted sentence sans whitespace.
        alnum_out = "".join([ch for ch in out_chars if ch.isalnum()])
        if alnum_out != alnum_corr:
            return corrupted

        # 5) Join and return exactly what we built
        return "".join(out_chars)

    def correct_aggregation(corrupted: str) -> str:
        reference = engine._current_llm_generation_reference_text

        if not reference:
            return corrupted

        # Apply the correction algorithm
        corrected = correct_corrupted_aggregation(reference, corrupted)
        return corrected

    return correct_aggregation

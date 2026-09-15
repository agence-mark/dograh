"""[.mark] Write the numbers a caller dictates as digits, before the model reads them.

Why this module exists
----------------------
On 2026-09-15 a phone number was dictated as "le zéro sept quatre vingt huit
vingt six quatorze zéro neuf". Deepgram Flux transcribed it correctly, in
words. Mistral then stitched those words back into eleven wrong digits, twice
in a row. The transcription was right; the model's arithmetic was not.

🔑 The fix is to hand the model digits it does not have to assemble: the final
transcript is rewritten by ``text2num`` (``alpha2digit``, MIT, local, no
network call) just before the user aggregator, so the model reads
"le 07 88 26 14 09".

🔒 Off by default, per agent. An agent that leaves the switch off builds
exactly the same list of processors as before this patch.

⚠️ What it deliberately does NOT touch:

- Interim transcripts. The "minimum words" interruption strategy counts the
  words of the transcripts it sees, interims included, and it runs in the
  aggregator, AFTER this step. Leaving the interims in words keeps that count
  unchanged. The model only reads final transcripts, so nothing is lost there.
  The one case affected: "minimum words" with interim transcripts turned off,
  where a dictated number counts as fewer words.
- The live transcript shown during the call. Observers read frames later, from
  a queue, so rewriting the frame in place would let the live view show words
  on one sentence and digits on the next. The conversion therefore works on a
  COPY that keeps the frame id: the live observer already marked that id as
  seen when the transcription pushed the original, skips the copy, and keeps
  showing words. The recorded transcript comes from the aggregator and carries
  the digits. Gap accepted on 2026-09-15.
- Realtime mode, which has no transcription step to convert.
- Any language but French.
"""

import copy

from loguru import logger

from api.schemas.workflow_configurations import WorkflowConfigurationDefaults
from pipecat.frames.frames import Frame, TranscriptionFrame
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor


def _est_francais(code) -> bool:
    return bool(code) and str(code).lower().startswith("fr")


def langue_agent_francaise(stt_config) -> bool:
    """Whether the agent's transcription is set up for French.

    Decided once, when the pipeline is built, and used for any sentence that
    carries no detected language of its own:

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


def _alpha2digit(texte: str) -> str:
    # ⛔ Imported lazily: a dependency missing from the image would otherwise
    # stop the whole API from starting, for every agent, including those that
    # never turned the switch on. Lazily, it breaks nothing (see below).
    from text_to_num import alpha2digit

    return alpha2digit(texte, "fr")


class ConversionNombresProcessor(FrameProcessor):
    """Rewrites the numbers of a final French transcript as digits."""

    def __init__(self, *, langue_agent_francaise: bool, **kwargs):
        super().__init__(**kwargs)
        self._langue_agent_francaise = langue_agent_francaise

    def _a_convertir(self, frame: TranscriptionFrame) -> bool:
        # A sentence with a detected language decides for itself; otherwise
        # the agent's configuration decides.
        if frame.language:
            return _est_francais(frame.language)
        return self._langue_agent_francaise

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)

        # ⛔ Final transcripts going downstream only. ``InterimTranscriptionFrame``
        # is not a subclass of ``TranscriptionFrame``, so interims pass as is.
        if (
            isinstance(frame, TranscriptionFrame)
            and direction == FrameDirection.DOWNSTREAM
            and frame.text
            and self._a_convertir(frame)
        ):
            try:
                # ⛔ A copy, never the original: see the module docstring. A
                # shallow copy keeps the frame id, which is what keeps the
                # live observer from showing the sentence a second time.
                converti = copy.copy(frame)
                converti.text = _alpha2digit(frame.text)
                frame = converti
            except Exception as erreur:
                # ⛔ A conversion failure must never cost the call: the model
                # gets the transcript in words, as it did before this patch.
                logger.warning(
                    f"[.mark] Number conversion failed, transcript kept as is: {erreur!r}"
                )

        await self.push_frame(frame, direction)


def creer_conversion_nombres(
    run_configs: dict | None, stt_config
) -> ConversionNombresProcessor | None:
    """The conversion step for this agent, or ``None`` when its switch is off.

    🔑 Read through the schema, like the other settings: a stored ``null`` means
    "not filled in" and falls back to the default, which is off.
    """
    effectifs = WorkflowConfigurationDefaults.model_validate(run_configs or {})
    if not effectifs.conversion_nombres_transcription:
        return None
    return ConversionNombresProcessor(
        langue_agent_francaise=langue_agent_francaise(stt_config)
    )

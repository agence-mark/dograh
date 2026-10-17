"""The call's routing boundary for replaceable agent workers."""

from collections.abc import Callable

from pipecat.bus.bridge_processor import BusBridgeProcessor
from pipecat.bus.messages import BusFrameMessage, BusMessage
from pipecat.frames.frames import (
    BotSpeakingFrame,
    BotStartedSpeakingFrame,
    BotStoppedSpeakingFrame,
    CancelFrame,
    CancelWorkerFrame,
    EndFrame,
    EndWorkerFrame,
    ErrorFrame,
    Frame,
    HeartbeatFrame,
    InputAudioRawFrame,
    InterruptionFrame,
    InterruptionWorkerFrame,
    LLMContextFrame,
    MetricsFrame,
    OutputTransportMessageUrgentFrame,
    PipelineFlushFrame,
    StartFrame,
    StopFrame,
    StopWorkerFrame,
    UserStartedSpeakingFrame,
    UserStoppedSpeakingFrame,
)
from pipecat.pipeline.worker import PipelineWorker
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor

# These must reach both the call processors and the selected agent exactly once.
TEED_FRAMES = (
    BotSpeakingFrame,
    BotStartedSpeakingFrame,
    BotStoppedSpeakingFrame,
    InterruptionFrame,
    UserStartedSpeakingFrame,
    UserStoppedSpeakingFrame,
)
CALL_FRAMES = (
    StartFrame,
    EndFrame,
    CancelFrame,
    StopFrame,
    InputAudioRawFrame,
    HeartbeatFrame,
    CancelWorkerFrame,
    EndWorkerFrame,
    StopWorkerFrame,
    InterruptionWorkerFrame,
    MetricsFrame,
    ErrorFrame,
    OutputTransportMessageUrgentFrame,
)
AGENT_EDGE_EXCLUDED_FRAMES = TEED_FRAMES + (ErrorFrame,)


class AgentBridgeProcessor(BusBridgeProcessor):
    """Route speech to/from one visit; keep recording and call control local.

    An upstream worker's ``active`` flag gates its input only. This boundary
    also rejects late output from a source or candidate. Usage from every
    visit still reaches the call's metrics collector.
    """

    def __init__(
        self,
        *,
        selected_visit: Callable[[], str | None],
        allow_inference: Callable[[], bool],
        **kwargs,
    ):
        super().__init__(**kwargs)
        self._selected_visit = selected_visit
        self._allow_inference = allow_inference
        # [.mark] Lot 3 (D7) : identifiants des trames de parole que le CODE a posées ici,
        # à dire par la voix de l'appel sans passer par un agent (voir ``dire_en_local``).
        self._paroles_locales: set[int] = set()

    async def dire_en_local(self, frame: Frame) -> None:
        """[.mark] Lot 3 (D7) : fait dire ``frame`` (une phrase dictée par le code, ou la
        frontière qui l'encadre) par la voix de l'APPEL, sans passer par aucun agent.

        Sert pendant l'attente d'une passation (``selected_visit`` vaut None : le pont jette
        tout ce qui vient d'un agent). Jamais utilisé quand un agent a la main : sa parole suit
        alors son circuit, dans l'ordre du texte du modèle (un seul chemin à la fois). La trame
        est posée dans la file d'entrée du pont, donc une interruption l'efface comme toute
        parole en attente (rien n'est dit après)."""
        self._paroles_locales.add(frame.id)
        await self.queue_frame(frame, FrameDirection.DOWNSTREAM)

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await FrameProcessor.process_frame(self, frame, direction)
        if isinstance(frame, InterruptionFrame):
            # Les paroles locales encore en file sont effacées par l'interruption : leurs
            # identifiants ne doivent pas rester (elles ne reviendront jamais).
            self._paroles_locales.clear()
        if frame.id in self._paroles_locales:
            self._paroles_locales.discard(frame.id)
            await self.push_frame(frame, direction)
            return
        if isinstance(frame, CALL_FRAMES + TEED_FRAMES):
            await self.push_frame(frame, direction)
            if not isinstance(frame, TEED_FRAMES):
                return
        target = self._selected_visit()
        if isinstance(frame, LLMContextFrame) and not self._allow_inference():
            return
        if isinstance(frame, PipelineFlushFrame) and target is None:
            await self.push_frame(frame, direction)
            return
        if target is not None:
            await self._bus.send(
                BusFrameMessage(
                    source=self._worker_name,
                    target=target,
                    frame=frame,
                    direction=direction,
                )
            )

    async def on_bus_message(self, message: BusMessage) -> None:
        if not isinstance(message, BusFrameMessage):
            return
        if message.source != self._selected_visit() and not isinstance(
            message.frame, MetricsFrame
        ):
            return
        await super().on_bus_message(message)


class AgentWorker(PipelineWorker):
    """A child exchanges frames with its call, never with another child."""

    def __init__(self, *args, call_worker_name: str, **kwargs):
        super().__init__(*args, **kwargs)
        self._call_worker_name = call_worker_name

    async def _queue_bridged_frame(self, message: BusFrameMessage) -> None:
        if message.source == self._call_worker_name:
            await super()._queue_bridged_frame(message)

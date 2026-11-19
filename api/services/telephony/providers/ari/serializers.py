"""Asterisk frame serializer (re-exported from pipecat) and its [.mark] subclass.

[.mark] ``AsteriskFrameSerializerMark`` is the serializer the ARI transport builds: it
adds the flush command Asterisk expects when the caller interrupts the agent.
"""

from pipecat.frames.frames import Frame, InterruptionFrame
from pipecat.serializers.asterisk import AsteriskFrameSerializer

# [.mark] chan_websocket command that drops the audio Asterisk still has queued.
FLUSH_MEDIA_COMMAND = "FLUSH_MEDIA"


class AsteriskFrameSerializerMark(AsteriskFrameSerializer):
    """[.mark] Sends Asterisk its flush command when the caller interrupts the agent.

    The parent sends nothing on an interruption, on the grounds that Asterisk has no
    buffer clear command, but chan_websocket has one: ``FLUSH_MEDIA``, sent as a text
    frame in the default control format (plain text).
    """

    async def serialize(self, frame: Frame) -> str | bytes | None:
        if isinstance(frame, InterruptionFrame):
            return FLUSH_MEDIA_COMMAND
        return await super().serialize(frame)


__all__ = [
    "FLUSH_MEDIA_COMMAND",
    "AsteriskFrameSerializer",
    "AsteriskFrameSerializerMark",
]

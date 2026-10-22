"""Twilio frame serializer.

[.mark] Lot 3 bis de cloture-code-avant-migration (22/10/2026). Pipecat lit chaque message du flux
Twilio sans garde : ``json.loads``, puis ``message["media"]["payload"]``, puis ``base64.b64decode``.
Un message tronqué ou incomplet lève alors ``JSONDecodeError``, ``KeyError`` ou ``binascii.Error``,
et l'appel tombe. Ici, seul ce message est ignoré (``None``) : l'appel continue.

Le sérialiseur de l'amont reste la base ; ``transport.py`` et ``appel_simule/pipeline.py`` importent
celui-ci. Si l'amont retire la classe, ce fichier est l'unique endroit à reprendre.
"""

import binascii
import json

from loguru import logger
from pipecat.frames.frames import Frame
from pipecat.serializers.twilio import (
    TwilioFrameSerializer as _TwilioFrameSerializerAmont,
)


class TwilioFrameSerializer(_TwilioFrameSerializerAmont):
    """[.mark] Ignore un message Twilio malformé au lieu de couper l'appel."""

    async def deserialize(self, data: str | bytes) -> Frame | None:
        try:
            return await super().deserialize(data)
        except (json.JSONDecodeError, KeyError, binascii.Error) as erreur:
            # Le contenu du message n'est jamais écrit : il peut porter de l'audio ou des identifiants.
            logger.warning(
                "Message Twilio malformé ignoré ({}), l'appel continue",
                type(erreur).__name__,
            )
            return None


__all__ = ["TwilioFrameSerializer"]

"""[.mark] Lot 3 bis de cloture-code-avant-migration (22/10/2026) : un message Twilio malformé ne coupe pas l'appel.

Pipecat lit chaque message du flux sans garde (``json.loads``, ``message["media"]["payload"]``,
``base64.b64decode``). Notre sérialiseur rattrape ces trois erreurs, rend ``None`` pour le seul
message en cause, et continue de traduire les messages suivants. Les tests passent par le
sérialiseur **branché** dans le transport Twilio et dans l'appel simulé, pas par la classe seule.
"""

import base64

import pytest
from pipecat.clocks.system_clock import SystemClock
from pipecat.frames.frames import InputAudioRawFrame
from pipecat.processors.frame_processor import FrameProcessorSetup
from pipecat.utils.asyncio.task_manager import TaskManager

from api.services.appel_simule import pipeline as pipeline_appel_simule
from api.services.telephony.providers.twilio import serializers, transport

# 1 600 octets de μ-law : deux cents millisecondes à 8 kHz. Le rééchantillonneur ne rend rien
# pour un paquet d'une vingtaine de millisecondes (il garde son retard) : mesuré le 22/10.
PAQUET_MULAW = base64.b64encode(bytes([0xFF]) * 1600).decode()


async def _serializer_pret():
    # Raccrochage automatique éteint : pas d'identifiants Twilio à fournir au test (le chemin
    # de lecture testé ici ne les utilise pas).
    serializer = serializers.TwilioFrameSerializer(
        stream_sid="MZtest",
        call_sid="CAtest",
        params=serializers.TwilioFrameSerializer.InputParams(auto_hang_up=False),
    )
    worker = type("Worker", (), {"app_resources": None, "worker_runner": None})()
    await serializer.setup(
        FrameProcessorSetup(
            audio_in_sample_rate=16000,
            clock=SystemClock(),
            task_manager=TaskManager(),
            pipeline_worker=worker,
        )
    )
    return serializer


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "message_malforme",
    [
        '{"event": "media", "media": {"payload": "AAAA',  # tronqué : JSONDecodeError
        '{"event": "media"}',  # pas de corps média : KeyError
        '{"event": "media", "media": {"payload": "A"}}',  # base64 invalide : binascii.Error
    ],
    ids=["tronque", "sans-media", "base64-invalide"],
)
async def test_message_malforme_rend_none_sans_couper_l_appel(message_malforme):
    serializer = await _serializer_pret()

    assert await serializer.deserialize(message_malforme) is None

    # Le message suivant, sain, est encore traduit en audio : l'appel n'est pas coupé.
    suivant = await serializer.deserialize(
        '{"event": "media", "media": {"payload": "' + PAQUET_MULAW + '"}}'
    )
    assert isinstance(suivant, InputAudioRawFrame)


def test_transport_twilio_utilise_le_serializer_qui_rattrape():
    assert transport.TwilioFrameSerializer is serializers.TwilioFrameSerializer


@pytest.mark.asyncio
async def test_appel_simule_utilise_le_serializer_qui_rattrape():
    serializer = pipeline_appel_simule.serialiseur_sans_telephonie("MZtest", "CAtest")

    assert isinstance(serializer, serializers.TwilioFrameSerializer)
    assert await serializer.deserialize('{"event": "media"') is None

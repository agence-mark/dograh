"""Exotel transport factory."""

from api.services.pipecat.audio_config import AudioConfig
from api.services.pipecat.audio_mixer import build_audio_out_mixer
from api.services.pipecat.transport_params import (
    filtre_de_bruit_overrides,
    realtime_param_overrides,
)
from api.services.telephony.factory import load_credentials_for_transport
from fastapi import WebSocket
from loguru import logger
from pipecat.transports.websocket.fastapi import (
    FastAPIWebsocketParams,
    FastAPIWebsocketTransport,
)

from .serializers import ExotelFrameSerializer


async def create_transport(
    websocket: WebSocket,
    workflow_run_id: int,
    audio_config: AudioConfig,
    organization_id: int,
    *,
    ambient_noise_config: dict | None = None,
    telephony_configuration_id: int | None = None,
    is_realtime: bool = False,
    # [.mark] The agent's configuration, for the incoming-noise filter.
    run_configs: dict | None = None,
    stream_sid: str,
    call_sid: str,
):
    logger.info(
        f"[run {workflow_run_id}] Creating Exotel transport - "
        f"stream_sid={stream_sid}, call_sid={call_sid}"
    )

    await load_credentials_for_transport(
        organization_id, telephony_configuration_id, expected_provider="exotel"
    )

    serializer = ExotelFrameSerializer(
        stream_sid=stream_sid,
        call_sid=call_sid,
        params=ExotelFrameSerializer.InputParams(
            exotel_sample_rate=8000,
            sample_rate=audio_config.pipeline_sample_rate,
        ),
    )

    mixer = await build_audio_out_mixer(
        audio_config.transport_out_sample_rate, ambient_noise_config
    )

    return FastAPIWebsocketTransport(
        websocket=websocket,
        params=FastAPIWebsocketParams(
            audio_in_enabled=True,
            audio_out_enabled=True,
            audio_in_sample_rate=audio_config.transport_in_sample_rate,
            audio_out_sample_rate=audio_config.transport_out_sample_rate,
            audio_out_mixer=mixer,
            serializer=serializer,
            **realtime_param_overrides(is_realtime),
            # [.mark] Ajoute le 2026-09-16 avec la montee vers `23d22b95` :
            # exotel est le NEUVIEME transport, et il doit traverser le meme
            # point de collecte que les huit autres. ⛔ Sans cette ligne,
            # l'audio entrerait non filtre sur ce seul transport, et rien ne
            # le dirait. C'est le test `test_filtre_de_bruit_rnnoise` qui l'a
            # signale a la fusion.
            **filtre_de_bruit_overrides(run_configs),
        ),
    )

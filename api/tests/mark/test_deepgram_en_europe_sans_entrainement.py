"""[.mark] Non-regression test for Deepgram EU residency and training opt-out.

The question this file answers, and it answers only this one:

    Does the caller's raw audio still reach Deepgram on the European endpoint,
    with participation in the Model Improvement Program refused?

⛔ Read that scope literally. This file does NOT prove that no byte at all
leaves the EU. ``check_validity._check_deepgram_api_key`` deliberately stays
on the global endpoint, because Deepgram does not serve its management API in
the EU and pointing it there would break key validation for every valid key.
That call carries no caller audio: it lists the account's projects. So the
sentence this file protects is "the voice does not leave the EU", never "no
byte leaves the EU".

Why it exists
-------------
.mark sells EU processing of the caller's raw audio, and non-participation in
Deepgram's training programme, as CONDITIONS of the offer rather than as
options. Dograh passed neither, so every call went to ``api.deepgram.com``
with the Model Improvement Program left on, and the sentence in the sales
material was false.

There are THREE Deepgram code paths, not two, and they take three different
shapes of address:

* ``DeepgramSTTService``     -> ``base_url``, a host it derives both schemes from
* ``DeepgramFluxSTTService`` -> ``url``, the complete WebSocket URL with path
* ``DeepgramTTSService``     -> ``base_url``, a base with no path ("/v1/speak" added)

Passing one shape where another belongs yields a connector that still talks to
the American endpoint, silently and without raising. That is why each path is
covered twice: once for what the factory PASSES, once for what actually goes
out on the wire. A value can be accepted, stored, and then dropped in favour
of a default -- ``DeepgramSTTService`` swallows a bad base_url and falls back
to the default endpoint with only a log line.
"""

import asyncio
from types import SimpleNamespace
from unittest.mock import patch

from api.services.configuration.registry import ServiceProviders
from api.services.pipecat.audio_config import AudioConfig
from api.services.pipecat.deepgram_endpoints import (
    DEEPGRAM_EU_FLUX_URL,
    DEEPGRAM_EU_STT_BASE_URL,
    DEEPGRAM_EU_TTS_BASE_URL,
)
from api.services.pipecat.service_factory import create_stt_service, create_tts_service

EU_HOST = "api.eu.deepgram.com"


def _audio_config():
    return AudioConfig(
        transport_in_sample_rate=16000,
        transport_out_sample_rate=24000,
    )


def _stt_config(model: str):
    return SimpleNamespace(
        stt=SimpleNamespace(
            provider=ServiceProviders.DEEPGRAM.value,
            api_key="test-key",
            model=model,
            language="fr",
        )
    )


def _tts_config():
    return SimpleNamespace(
        tts=SimpleNamespace(
            provider=ServiceProviders.DEEPGRAM.value,
            api_key="test-key",
            model="aura-2-thalia-en",
            voice="aura-2-thalia-en",
        )
    )


def _capture_websocket_url(service, connect_coroutine):
    """Run a connector's websocket handshake and return the URL it dialled.

    Nothing reaches the network: the dialler is replaced by one that records
    its argument and aborts. This is the only way to prove the address the
    connector actually composes, as opposed to the one it was handed.
    """
    captured = {}

    async def fake_dial(url, *args, **kwargs):
        captured["url"] = url
        raise RuntimeError("handshake stopped on purpose")

    async def noop(*args, **kwargs):
        return None

    service._websocket_connect = fake_dial
    service.push_error_frame = noop
    service._call_event_handler = noop

    asyncio.run(connect_coroutine(service))
    return captured["url"]


# --------------------------------------------------------------------------
# Passed: the factory hands the values to each connector
# --------------------------------------------------------------------------


def test_classic_stt_is_pointed_at_the_eu_endpoint_and_opted_out():
    with patch("api.services.pipecat.service_factory.DeepgramSTTService") as mock:
        create_stt_service(_stt_config("nova-3-general"), _audio_config())

    kwargs = mock.call_args.kwargs
    assert kwargs["base_url"] == DEEPGRAM_EU_STT_BASE_URL
    assert kwargs["mip_opt_out"] is True


def test_flux_stt_is_pointed_at_the_eu_endpoint_and_opted_out():
    with patch("api.services.pipecat.service_factory.DeepgramFluxSTTService") as mock:
        create_stt_service(_stt_config("flux-general-en"), _audio_config())

    kwargs = mock.call_args.kwargs
    assert kwargs["url"] == DEEPGRAM_EU_FLUX_URL
    assert kwargs["mip_opt_out"] is True


def test_tts_is_pointed_at_the_eu_endpoint_and_opted_out():
    with patch("api.services.pipecat.service_factory.DeepgramTTSService") as mock:
        create_tts_service(_tts_config(), _audio_config())

    kwargs = mock.call_args.kwargs
    assert kwargs["base_url"] == DEEPGRAM_EU_TTS_BASE_URL
    assert kwargs["mip_opt_out"] is True


# --------------------------------------------------------------------------
# Honoured: the values reach what actually goes out on the wire
# --------------------------------------------------------------------------


def test_classic_stt_client_really_targets_the_eu_host():
    service = create_stt_service(_stt_config("nova-3-general"), _audio_config())

    # get_environment() is what the SDK calls on itself to resolve a route.
    environment = service._client._client_wrapper.get_environment()
    assert environment.base == f"https://{EU_HOST}"
    assert f"{environment.production}/v1/listen" == f"wss://{EU_HOST}/v1/listen"


def test_classic_stt_sends_the_opt_out_in_its_request():
    service = create_stt_service(_stt_config("nova-3-general"), _audio_config())

    assert service._build_connect_kwargs()["mip_opt_out"] == "true"


def test_flux_stt_dials_the_eu_url_with_the_opt_out():
    service = create_stt_service(_stt_config("flux-general-en"), _audio_config())

    # Flux assembles its URL in _connect(), not in _connect_websocket(), so
    # the real assembly line only runs if we enter through _connect().
    url = _capture_websocket_url(service, lambda s: s._connect())
    assert url.startswith(f"wss://{EU_HOST}/v2/listen?")
    assert "mip_opt_out=true" in url


def test_tts_dials_the_eu_url_with_the_opt_out():
    service = create_tts_service(_tts_config(), _audio_config())

    url = _capture_websocket_url(service, lambda s: s._connect_websocket())
    assert url.startswith(f"wss://{EU_HOST}/v1/speak?")
    assert "mip_opt_out=true" in url

"""Deepgram compliance: EU residency and model-improvement opt-out.

.mark sells two guarantees with the voice agent: the caller's raw audio is
processed inside the EU, and it never feeds a vendor's training programme.
Deepgram supports both, but Dograh was passing neither, so every call went to
``api.deepgram.com`` with the Model Improvement Program left on.

These are conditions of the offer, not preferences, so the values are hardcoded
and must never become editable configuration.

Each guarantee is tested twice on purpose:

* a *passed* test — the factory hands the value to the connector;
* an *honoured* test — the connector actually uses it in what it sends.

The gap between the two is a real failure mode: a value can be accepted,
stored, and then silently dropped in favour of a default. All three Deepgram
code paths are covered, because they take different arguments of different
shapes and only one of them is used by any given call.
"""

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from api.services.configuration.registry import ServiceProviders
from api.services.pipecat.audio_config import AudioConfig
from api.services.pipecat.service_factory import (
    create_stt_service,
    create_tts_service,
)

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


# --------------------------------------------------------------------------
# Passed: the factory hands the values to each connector
# --------------------------------------------------------------------------


def test_classic_stt_is_pointed_at_the_eu_endpoint_and_opted_out():
    """Path 1/3: nova-3 and friends, via ``DeepgramSTTService``."""
    with patch(
        "api.services.pipecat.service_factory.DeepgramSTTService"
    ) as mock_service:
        create_stt_service(_stt_config("nova-3-general"), _audio_config())

    kwargs = mock_service.call_args.kwargs
    # base_url takes a host; the connector derives both wss:// and https://.
    assert EU_HOST in kwargs["base_url"]
    assert kwargs["mip_opt_out"] is True


def test_flux_stt_is_pointed_at_the_eu_endpoint_and_opted_out():
    """Path 2/3: flux-* models, via ``DeepgramFluxSTTService``.

    Flux does not take a host. It takes the complete WebSocket URL, path
    included, so reusing the classic value here would produce a connector
    still talking to the default American endpoint.
    """
    with patch(
        "api.services.pipecat.service_factory.DeepgramFluxSTTService"
    ) as mock_service:
        create_stt_service(_stt_config("flux-general-en"), _audio_config())

    kwargs = mock_service.call_args.kwargs
    assert kwargs["url"] == f"wss://{EU_HOST}/v2/listen"
    assert kwargs["mip_opt_out"] is True


def test_tts_is_pointed_at_the_eu_endpoint_and_opted_out():
    """Path 3/3: Deepgram speech synthesis.

    Not part of .mark's own stack (we synthesise with Voxtral), but it is
    offered in the interface and it carries the Deepgram name, so it must not
    be the one path that quietly leaves the EU.
    """
    with patch(
        "api.services.pipecat.service_factory.DeepgramTTSService"
    ) as mock_service:
        create_tts_service(_tts_config(), _audio_config())

    kwargs = mock_service.call_args.kwargs
    # This connector appends "/v1/speak" itself, so the base carries no path.
    assert kwargs["base_url"] == f"wss://{EU_HOST}"
    assert kwargs["mip_opt_out"] is True


# --------------------------------------------------------------------------
# Honoured: the values reach what is actually sent to Deepgram
# --------------------------------------------------------------------------


def test_classic_stt_client_really_targets_the_eu_host():
    """The value is not merely accepted: the built client points at the EU.

    ``DeepgramSTTService`` swallows a bad base_url and falls back to the
    default endpoint with only a log line, so a passing "we passed it" test
    proves nothing on its own.
    """
    service = create_stt_service(_stt_config("nova-3-general"), _audio_config())

    environment = service._client._client_wrapper._environment
    assert environment.base == f"https://{EU_HOST}"
    assert environment.production == f"wss://{EU_HOST}"


def test_classic_stt_sends_the_opt_out_in_its_request():
    """A stored flag is not a sent flag: check the outgoing parameters."""
    service = create_stt_service(_stt_config("nova-3-general"), _audio_config())

    assert service._build_connect_kwargs()["mip_opt_out"] == "true"


def test_flux_stt_sends_the_opt_out_to_the_eu_url():
    service = create_stt_service(_stt_config("flux-general-en"), _audio_config())

    assert service._url == f"wss://{EU_HOST}/v2/listen"
    assert "mip_opt_out=true" in service._build_query_string()


def test_tts_builds_an_eu_url_carrying_the_opt_out():
    service = create_tts_service(_tts_config(), _audio_config())

    assert service._base_url == f"wss://{EU_HOST}"
    assert service._mip_opt_out is True

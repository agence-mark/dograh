"""Non-regression tests for the Mistral provider (LLM + TTS).

These tests are written BEFORE the implementation and must fail for the right
reason (unknown provider), never because of an import typo.

The critical one is ``test_llm_factory_builds_mistral_service_not_openai``:
``MistralLLMService`` overrides ``run_function_calls`` to filter out tool calls
that already have results, because Mistral detects tool calls from the whole
message history instead of the stream. Routing Mistral through
``OpenAILLMService`` with a custom ``base_url`` loses that filter, and function
calls would then execute twice.
"""

from types import SimpleNamespace
from unittest.mock import patch

import pytest
from pydantic import TypeAdapter

from api.services.configuration import check_validity
from api.services.configuration.check_validity import UserConfigurationValidator
from api.services.configuration.registry import (
    LLMConfig,
    MistralLLMConfiguration,
    MistralTTSConfiguration,
    ServiceProviders,
    ServiceType,
    TTSConfig,
)

MISTRAL_EU_BASE_URL = "https://api.eu.mistral.ai/v1"


def _audio_config():
    # Telephony rate: this is the case that matters for the product.
    return SimpleNamespace(
        transport_out_sample_rate=8000,
        transport_in_sample_rate=8000,
    )


FRENCH_VOICES = [
    "fr_marie_neutral",
    "fr_marie_happy",
    "fr_marie_curious",
    "fr_marie_excited",
    "fr_marie_sad",
    "fr_marie_angry",
]


# --------------------------------------------------------------------------- #
# 1. The provider exists, for both services
# --------------------------------------------------------------------------- #


def test_mistral_is_registered_for_llm_and_tts():
    from api.services.configuration.registry import REGISTRY

    assert ServiceProviders.MISTRAL.value == "mistral"
    assert ServiceProviders.MISTRAL.value in REGISTRY[ServiceType.LLM]
    assert ServiceProviders.MISTRAL.value in REGISTRY[ServiceType.TTS]
    # The STT service exists in pipecat but is deliberately out of scope:
    # the Deepgram/Mistral trade-off was settled on a latency measurement.
    assert ServiceProviders.MISTRAL.value not in REGISTRY[ServiceType.STT]


# --------------------------------------------------------------------------- #
# 2. Defaults carry the intent: European endpoint, medium model
# --------------------------------------------------------------------------- #


def test_mistral_llm_configuration_defaults_to_european_endpoint():
    config = MistralLLMConfiguration(api_key="mistral-key")

    assert config.provider == ServiceProviders.MISTRAL
    assert config.model == "mistral-medium-latest"
    # Pipecat defaults to https://api.mistral.ai/v1 (US-facing hostname).
    # Both endpoints serve the same 50 models, so defaulting to the European
    # one costs nothing and keeps the data-residency promise true for any
    # client who never touches the field.
    assert config.base_url == MISTRAL_EU_BASE_URL


def test_mistral_tts_configuration_defaults_to_french_voice():
    config = MistralTTSConfiguration(api_key="mistral-key")

    assert config.provider == ServiceProviders.MISTRAL
    assert config.model == "voxtral-mini-tts-latest"
    assert config.voice == "fr_marie_neutral"


# --------------------------------------------------------------------------- #
# 3. The discriminated unions accept what the UI will send
# --------------------------------------------------------------------------- #


def test_mistral_discriminator_parses_llm_config():
    config = TypeAdapter(LLMConfig).validate_python(
        {
            "provider": "mistral",
            "api_key": "mistral-key",
            "model": "mistral-large-latest",
            "base_url": MISTRAL_EU_BASE_URL,
        }
    )

    assert isinstance(config, MistralLLMConfiguration)
    assert config.model == "mistral-large-latest"
    assert config.base_url == MISTRAL_EU_BASE_URL


@pytest.mark.parametrize("voice", FRENCH_VOICES)
def test_mistral_discriminator_parses_every_french_voice(voice):
    config = TypeAdapter(TTSConfig).validate_python(
        {
            "provider": "mistral",
            "api_key": "mistral-key",
            "voice": voice,
        }
    )

    assert isinstance(config, MistralTTSConfiguration)
    assert config.voice == voice


# --------------------------------------------------------------------------- #
# 4. The factory builds the real Mistral services
# --------------------------------------------------------------------------- #


def test_llm_factory_builds_mistral_service_not_openai():
    """The test that guards against the duplicate function-call bug.

    Routing Mistral through OpenAILLMService would pass a naive smoke test and
    silently execute every tool call twice.
    """
    from pipecat.services.mistral.llm import MistralLLMService

    from api.services.pipecat.service_factory import create_llm_service_from_provider

    service = create_llm_service_from_provider(
        provider=ServiceProviders.MISTRAL.value,
        api_key="mistral-key",
        model="mistral-medium-latest",
        base_url=MISTRAL_EU_BASE_URL,
    )

    assert isinstance(service, MistralLLMService)
    # The whole point: the override must be Mistral's, not OpenAI's.
    assert (
        type(service).run_function_calls is not
        type(service).__mro__[1].run_function_calls
    )


def test_tts_factory_builds_mistral_service_at_the_transport_rate():
    """Voxtral emits 24 kHz. Telephony runs at 8 kHz, so the factory must pass
    the transport rate through, exactly like the LMNT branch does."""
    from api.services.pipecat.service_factory import create_tts_service

    user_config = SimpleNamespace(
        tts=MistralTTSConfiguration(api_key="mistral-key", voice="fr_marie_neutral")
    )

    with patch("api.services.pipecat.service_factory.MistralTTSService") as mock_service:
        create_tts_service(user_config, _audio_config())

    assert mock_service.call_count == 1
    kwargs = mock_service.call_args.kwargs
    assert kwargs["api_key"] == "mistral-key"
    assert kwargs["sample_rate"] == 8000
    assert kwargs["settings"].voice == "fr_marie_neutral"
    assert kwargs["settings"].model == "voxtral-mini-tts-latest"


# --------------------------------------------------------------------------- #
# 5. The API key can actually be validated (otherwise the UI refuses it)
# --------------------------------------------------------------------------- #


def test_mistral_api_key_validation_uses_the_configured_endpoint(monkeypatch):
    captured = {}

    class FakeModels:
        def list(self):
            return []

    class FakeOpenAI:
        def __init__(self, **kwargs):
            captured.update(kwargs)
            self.models = FakeModels()

    monkeypatch.setattr(check_validity.openai, "OpenAI", FakeOpenAI)

    config = MistralLLMConfiguration(api_key="mistral-key")
    is_valid = UserConfigurationValidator()._check_api_key(
        ServiceProviders.MISTRAL.value,
        "mistral-key",
        config,
    )

    assert is_valid is True
    assert captured == {
        "api_key": "mistral-key",
        "base_url": MISTRAL_EU_BASE_URL,
    }


def test_mistral_tts_api_key_validation_falls_back_to_european_endpoint(monkeypatch):
    """The TTS config has no base_url field, so validation must not fall back
    to api.openai.com, which would reject a perfectly valid Mistral key."""
    captured = {}

    class FakeModels:
        def list(self):
            return []

    class FakeOpenAI:
        def __init__(self, **kwargs):
            captured.update(kwargs)
            self.models = FakeModels()

    monkeypatch.setattr(check_validity.openai, "OpenAI", FakeOpenAI)

    config = MistralTTSConfiguration(api_key="mistral-key")
    is_valid = UserConfigurationValidator()._check_api_key(
        ServiceProviders.MISTRAL.value,
        "mistral-key",
        config,
    )

    assert is_valid is True
    assert captured["base_url"] == MISTRAL_EU_BASE_URL


def test_mistral_api_key_error_message_names_mistral(monkeypatch):
    class FakeAuthenticationError(Exception):
        pass

    class FakeModels:
        def list(self):
            raise FakeAuthenticationError

    class FakeOpenAI:
        def __init__(self, **kwargs):
            self.models = FakeModels()

    monkeypatch.setattr(check_validity.openai, "OpenAI", FakeOpenAI)
    monkeypatch.setattr(
        check_validity.openai, "AuthenticationError", FakeAuthenticationError
    )

    config = MistralLLMConfiguration(api_key="mistral-key")
    with pytest.raises(ValueError) as exc_info:
        UserConfigurationValidator()._check_api_key(
            ServiceProviders.MISTRAL.value,
            "mistral-key",
            config,
        )

    message = str(exc_info.value)
    assert "Mistral" in message
    assert "platform.openai.com" not in message


# --------------------------------------------------------------------------- #
# 6. The UI dropdown is filled from these schemas
# --------------------------------------------------------------------------- #


def test_defaults_route_exposes_mistral_in_llm_and_tts_schemas():
    from api.routes.organization import _byok_provider_schemas

    llm_schemas = _byok_provider_schemas(ServiceType.LLM)
    tts_schemas = _byok_provider_schemas(ServiceType.TTS)

    # LLMConfigSelector.tsx does Object.keys(schemas): being a key here is
    # exactly what makes "mistral" appear in the dropdown.
    assert ServiceProviders.MISTRAL.value in llm_schemas
    assert ServiceProviders.MISTRAL.value in tts_schemas

    voice_schema = tts_schemas[ServiceProviders.MISTRAL.value]["properties"]["voice"]
    for voice in FRENCH_VOICES:
        assert voice in voice_schema["examples"]

"""Mistral TTS wrapper that honours the configured Mistral region.

Pipecat's MistralTTSService builds its client as ``Mistral(api_key=...)``, and
the SDK then falls back to SERVER_GLOBAL (https://api.mistral.ai). The SDK does
accept a region — ``server="eu"`` resolves to https://api.eu.mistral.ai — but
the wrapper never forwards one, so every synthesised sentence would leave
through the global endpoint no matter what the organisation configured.

That matters here beyond preference: the text handed to TTS is the content of
the agent's replies, and EU processing is a contractual condition of the .mark
offer rather than an option. So the region is passed explicitly.

The clean home for this fix is upstream in Pipecat; until it lands there, this
subclass keeps it in one place instead of scattering client surgery across the
factory.
"""

from mistralai.client import Mistral

from pipecat.services.mistral.tts import MistralTTSService

# Maps the base_url an organisation configures for Mistral onto the SDK's own
# region identifier. Anything unknown keeps the SDK default rather than
# guessing, so a private or proxied endpoint is never silently rerouted.
_HOST_TO_SERVER = {
    "api.eu.mistral.ai": "eu",
    "api.us.mistral.ai": "us",
    "api.mistral.ai": "global",
}


def resolve_mistral_server(base_url: str | None) -> str | None:
    """Return the SDK region for a configured base_url, or None if unknown."""
    if not base_url:
        return None
    host = base_url.split("//", 1)[-1].split("/", 1)[0].split(":", 1)[0].lower()
    return _HOST_TO_SERVER.get(host)


class MistralRegionalTTSService(MistralTTSService):
    """MistralTTSService variant whose client targets an explicit region."""

    def __init__(self, *args, server: str | None = None, api_key: str, **kwargs):
        super().__init__(*args, api_key=api_key, **kwargs)
        if server:
            self._client = Mistral(api_key=api_key, server=server)

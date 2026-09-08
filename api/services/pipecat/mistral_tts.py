"""Mistral TTS wrapper that honours the configured Mistral endpoint.

Pipecat's MistralTTSService builds its client as ``Mistral(api_key=...)`` and
never forwards an endpoint, so the SDK falls back to SERVER_GLOBAL
(https://api.mistral.ai) whatever the organisation configured.

That matters beyond preference here: the text handed to TTS is the content of
the agent's replies, and EU processing is a contractual condition of the .mark
offer rather than an option.

The clean home for this fix is upstream in Pipecat; until it lands there, this
subclass keeps it in one place instead of scattering client surgery across the
factory.
"""

from pipecat.services.mistral.tts import MistralTTSService

# Mistral's own region identifiers, which the SDK resolves to its published
# hosts. Preferred over a raw URL when the configured host is one of them, so
# that a change on Mistral's side follows the SDK rather than our copy of it.
_HOST_TO_SERVER = {
    "api.eu.mistral.ai": "eu",
    "api.us.mistral.ai": "us",
    "api.mistral.ai": "global",
}


def _host_of(base_url: str) -> str:
    return base_url.split("//", 1)[-1].split("/", 1)[0].split(":", 1)[0].lower()


def resolve_mistral_endpoint(base_url: str | None) -> tuple[str | None, str | None]:
    """Turn a configured base_url into the SDK's (server, server_url) pair.

    A known Mistral host resolves to its region identifier. Anything else — a
    private gateway, a proxy, a region Mistral adds after this code was written
    — is passed through as an explicit server_url, stripped of the ``/v1``
    suffix the SDK appends itself.

    What this must never do is return nothing for an unknown host: the SDK
    would then silently fall back to the global endpoint, which is exactly the
    configured-then-ignored failure this module exists to prevent.
    """
    if not base_url:
        return None, None
    server = _HOST_TO_SERVER.get(_host_of(base_url))
    if server:
        return server, None
    trimmed = base_url.rstrip("/")
    if trimmed.endswith("/v1"):
        trimmed = trimmed[: -len("/v1")]
    return None, trimmed


class MistralRegionalTTSService(MistralTTSService):
    """MistralTTSService variant whose client targets an explicit endpoint."""

    def __init__(
        self,
        *args,
        server: str | None = None,
        server_url: str | None = None,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        # Settings the existing client's configuration rather than building a
        # second one: get_server_details() reads server_url first, then server.
        if server_url:
            self._client.sdk_configuration.server_url = server_url
        elif server:
            self._client.sdk_configuration.server = server

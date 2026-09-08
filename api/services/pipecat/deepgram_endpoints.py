"""Deepgram endpoints and compliance flags, hardcoded on purpose.

These are NOT configuration. They live here, next to their only consumer
(``service_factory.py``), rather than in ``configuration/`` -- neither in
``registry.py``, which describes what a user may configure, nor in
``configuration/options/``, which holds the menus of choices offered to a
user. Nobody chooses these values.

.mark sells EU processing of the caller's raw audio, and non-participation in
Deepgram's Model Improvement Program, as CONDITIONS of the offer rather than
as options. Exposing them as editable configuration would hand the promise to
someone able to undo it.

Deepgram serves /v1/listen, /v2/listen and /v1/speak on the European endpoint
with the same API keys, so this costs nothing; the only exclusion is the
Whisper models, which are not offered here anyway. The management API is NOT
served there -- see ``check_validity._check_deepgram_api_key``, which stays on
the global endpoint deliberately.

The three values are NOT interchangeable, and that is the point: each
connector takes a different shape of address, and passing one where another
belongs yields a connector that still talks to the default American endpoint,
silently and without raising.
"""

# A scheme + host. DeepgramSTTService derives both the wss:// and https://
# forms from it (see pipecat deepgram/stt.py::_derive_deepgram_urls).
DEEPGRAM_EU_STT_BASE_URL = "https://api.eu.deepgram.com"

# The complete WebSocket URL, path included: DeepgramFluxSTTService only
# appends the query string to it.
DEEPGRAM_EU_FLUX_URL = "wss://api.eu.deepgram.com/v2/listen"

# A base with no path: DeepgramTTSService appends "/v1/speak" itself.
DEEPGRAM_EU_TTS_BASE_URL = "wss://api.eu.deepgram.com"

"""Deepgram European endpoints: the DEFAULT the audio goes to.

🔑 2026-09-16, decision d'Evan. These were a lock until that date; they are
now defaults. The address is a normal configurable field again, with Europe as
the value nobody has to think about, because Dograh is our own internal tool
and holding a field shut is not worth what it costs at every upstream merge.

What did NOT change: the Model Improvement Program opt-out is still imposed by
the factory, on all three paths, whatever a configuration says. It does not
depend on the region, refusing it forfeits a discount, and that is accepted.

``DEEPGRAM_EU_STT_BASE_URL`` is what the factory falls back to when the field
arrives empty, and what ``registry.py`` mirrors as the field default; a test
compares the two. ⛔ The other two are NO LONGER read by the factory, which
derives all three shapes from the configured value: they stay as the reference
the tests measure the wire against. Correcting one of them alone would change
nothing in production -- raised by the review of 2026-09-16.

Deepgram serves /v1/listen, /v2/listen and /v1/speak on the European endpoint
with the same API keys, so the endpoint choice itself costs nothing; the only
exclusion is the Whisper models, which are not offered here anyway. The
management API is NOT served there -- see
``check_validity._check_deepgram_api_key``, which stays on the global endpoint
deliberately.

⛔ The three values are NOT interchangeable, and that is the point: each
connector takes a different shape of address, and passing one where another
belongs yields a connector that still talks to the default American endpoint,
silently and without raising. ``_deepgram_websocket_url`` derives all three
from one configured value for exactly that reason.
"""

# A scheme + host. DeepgramSTTService derives both the wss:// and https://
# forms from it (see pipecat deepgram/stt.py::_derive_deepgram_urls).
DEEPGRAM_EU_STT_BASE_URL = "https://api.eu.deepgram.com"

# The complete WebSocket URL, path included: DeepgramFluxSTTService only
# appends the query string to it.
DEEPGRAM_EU_FLUX_URL = "wss://api.eu.deepgram.com/v2/listen"

# A base with no path: DeepgramTTSService appends "/v1/speak" itself.
DEEPGRAM_EU_TTS_BASE_URL = "wss://api.eu.deepgram.com"

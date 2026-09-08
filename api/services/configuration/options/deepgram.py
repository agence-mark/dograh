"""Deepgram model catalogue and compliance endpoints."""

# Compliance constants, hardcoded on purpose.
#
# .mark sells EU processing of the caller's raw audio, and non-participation in
# Deepgram's Model Improvement Program, as CONDITIONS of the offer rather than
# as options. Exposing them as editable configuration would hand the promise to
# someone able to undo it, so they are not part of any configuration schema.
#
# Deepgram serves /v1/listen, /v2/listen and /v1/speak on the European endpoint
# with the same API keys, so this costs nothing; the only exclusion is the
# Whisper models, which are not offered here anyway.
#
# The three values are NOT interchangeable, and that is the point: each
# connector takes a different shape of address.
#   * DEEPGRAM_EU_STT_BASE_URL -- a host. DeepgramSTTService derives both the
#     wss:// and https:// forms from it.
#   * DEEPGRAM_EU_FLUX_URL -- the complete WebSocket URL, path included, because
#     DeepgramFluxSTTService only appends the query string to it.
#   * DEEPGRAM_EU_TTS_BASE_URL -- a base with no path; DeepgramTTSService
#     appends "/v1/speak" itself.
# Passing one where another belongs yields a connector that still talks to the
# default American endpoint, silently.
DEEPGRAM_EU_STT_BASE_URL = "https://api.eu.deepgram.com"
DEEPGRAM_EU_FLUX_URL = "wss://api.eu.deepgram.com/v2/listen"
DEEPGRAM_EU_TTS_BASE_URL = "wss://api.eu.deepgram.com"

DEEPGRAM_FLUX_MODELS = ("flux-general-en", "flux-general-multi")
DEEPGRAM_FLUX_MULTILINGUAL_LANGUAGES = (
    "de",
    "en",
    "es",
    "fr",
    "hi",
    "it",
    "ja",
    "nl",
    "pt",
    "ru",
)
DEEPGRAM_FLUX_MULTILINGUAL_LANGUAGE_OPTIONS = (
    "multi",
    *DEEPGRAM_FLUX_MULTILINGUAL_LANGUAGES,
)
DEEPGRAM_STT_MODELS = ("nova-3-general", "nova-3-medical", *DEEPGRAM_FLUX_MODELS)
DEEPGRAM_LANGUAGES = (
    "multi",
    "ar",
    "ar-AE",
    "ar-SA",
    "ar-QA",
    "ar-KW",
    "ar-SY",
    "ar-LB",
    "ar-PS",
    "ar-JO",
    "ar-EG",
    "ar-SD",
    "ar-TD",
    "ar-MA",
    "ar-DZ",
    "ar-TN",
    "ar-IQ",
    "ar-IR",
    "be",
    "bn",
    "bs",
    "bg",
    "ca",
    "cs",
    "da",
    "da-DK",
    "de",
    "de-CH",
    "el",
    "en",
    "en-US",
    "en-AU",
    "en-GB",
    "en-IN",
    "en-NZ",
    "es",
    "es-419",
    "et",
    "fa",
    "fi",
    "fr",
    "fr-CA",
    "he",
    "hi",
    "hr",
    "hu",
    "id",
    "it",
    "ja",
    "kn",
    "ko",
    "ko-KR",
    "lt",
    "lv",
    "mk",
    "mr",
    "ms",
    "nl",
    "nl-BE",
    "no",
    "pl",
    "pt",
    "pt-BR",
    "pt-PT",
    "ro",
    "ru",
    "sk",
    "sl",
    "sr",
    "sv",
    "sv-SE",
    "ta",
    "te",
    "th",
    "tl",
    "tr",
    "uk",
    "ur",
    "vi",
    "zh-CN",
    "zh-TW",
)

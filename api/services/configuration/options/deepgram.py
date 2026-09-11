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

# Models where ``keywords`` has been REPLACED by keyterm prompting, so sending
# it does nothing at all (verified on
# https://developers.deepgram.com/docs/keywords, 2026-09-11).
#
# ⛔ An EXCLUSION, not a white list of the models that accept it. The model
# field takes free input, and Deepgram has dozens of older models
# (`nova-2-finance`, `nova-2-drivethru`…): a white list would silently drop the
# setting for every model nobody thought to enumerate. Raised by the second
# review of 2026-09-11, which had already made the same point about the
# thirteen classic settings.
#
# 🔑 ONE list, used by the screen to hide the field AND by the factory to drop
# it from the request. Two lists would be two chances to diverge, and the
# screen would stop describing what goes out.
DEEPGRAM_KEYTERM_MODELS = (
    "nova-3",
    "nova-3-general",
    "nova-3-medical",
    *DEEPGRAM_FLUX_MODELS,
)

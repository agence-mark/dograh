SONIOX_STT_MODELS = ("stt-rt-v5",)

SONIOX_STT_LANGUAGES = (
    "multi",
    "af",
    "ar",
    "az",
    "be",
    "bg",
    "bn",
    "bs",
    "ca",
    "cs",
    "cy",
    "da",
    "de",
    "el",
    "en",
    "es",
    "et",
    "eu",
    "fa",
    "fi",
    "fr",
    "gl",
    "gu",
    "he",
    "hi",
    "hr",
    "hu",
    "id",
    "it",
    "ja",
    "kk",
    "kn",
    "ko",
    "lt",
    "lv",
    "mk",
    "ml",
    "mr",
    "ms",
    "nl",
    "no",
    "pa",
    "pl",
    "pt",
    "ro",
    "ru",
    "sk",
    "sl",
    "sq",
    "sr",
    "sv",
    "sw",
    "ta",
    "te",
    "th",
    "tl",
    "tr",
    "uk",
    "ur",
    "vi",
    "zh",
)

# [.mark] Chantier voix-soniox, lot 2 (voix). Le modele de voix de Soniox.
SONIOX_TTS_MODELS = ("tts-rt-v2",)

# [.mark] Les langues du connecteur Pipecat de NOTRE epinglage : les codes que
# `language_to_soniox_tts_language` rend pour toute `Language` de Pipecat (131 codes,
# releves le 22/10/2026 dans `pipecat/src/pipecat/services/soniox/tts.py`). Ce n'est PAS
# la liste de la transcription : la voix en sait bien plus. Un test garde les deux sens
# (rien en trop, rien en moins) ; a relire a chaque montee de Pipecat.
SONIOX_TTS_LANGUAGES = (
    "af", "am", "ar", "as", "ast", "az", "ba", "be", "bg", "bn",
    "bo", "br", "bs", "ca", "ceb", "ckb", "cmn", "cs", "cy", "da",
    "de", "el", "en", "eo", "es", "et", "eu", "fa", "ff", "fi",
    "fil", "fo", "fr", "ga", "gd", "gl", "gu", "ha", "haw", "he",
    "hi", "hr", "ht", "hu", "hy", "id", "ig", "is", "it", "iu",
    "ja", "jv", "jw", "ka", "kab", "kea", "kk", "km", "kn", "ko",
    "kok", "ku", "ky", "la", "lb", "lg", "ln", "lo", "lt", "luo",
    "lv", "mai", "mg", "mi", "mk", "ml", "mn", "mr", "ms", "mt",
    "my", "mymr", "nb", "ne", "nl", "nn", "no", "nso", "ny", "oc",
    "or", "pa", "pl", "ps", "pt", "ro", "ru", "sa", "sd", "si",
    "sk", "sl", "sn", "so", "sq", "sr", "su", "sv", "sw", "ta",
    "te", "tg", "th", "tk", "tl", "tr", "tt", "ug", "uk", "umb",
    "ur", "uz", "vi", "wo", "wuu", "xh", "yi", "yo", "yue", "zh",
    "zu",
)

# [.mark] Lot 2 bis (D2) : la liste des voix, figee dans le code.
#
# ⛔ SOURCE ET LIMITE. Relevee le 21/10/2026 par `GET /v1/tts-models` (cle du
# labo, point mondial) : le catalogue compte environ 200 voix, a trois champs
# (identifiant, description, genre). Seules les 11 voix FRANCAISES ont ete
# consignees (note `2026-10-21-note-etat-de-l-art-conversation-naturelle.md`,
# § 6) ; la liste complete n'a pas ete enregistree. Elle est a relever par
# `api/scripts/mark/releve_voix_soniox.py` (jamais lance dans ce chantier : aucun
# appel a Soniox), puis a ajouter ici avec sa date. Tant qu'elle ne l'est pas,
# la saisie libre de l'ecran couvre toute autre voix (ou une voix clonee).
# ⛔ Aucune description ni aucun genre n'est invente : `None` = non releve.
SONIOX_TTS_VOIX_RELEVE = "2026-10-21"
SONIOX_TTS_VOIX_SOURCE = "GET /v1/tts-models (api.soniox.com)"
# Dans l'ordre d'affichage : les trois candidats d'accueil d'abord (Mathieu,
# Celine, Julien), puis les autres voix de France, puis le Quebec.
SONIOX_TTS_VOIX = (
    {"id": "Mathieu", "francais": True, "accent": "France", "genre": None, "description": "amical, posé"},
    {"id": "Celine", "francais": True, "accent": "France", "genre": None, "description": "articulation précise"},
    {"id": "Julien", "francais": True, "accent": "France", "genre": None, "description": "chaleureux, vif en conversation"},
    {"id": "Olivier", "francais": True, "accent": "France", "genre": None, "description": None},
    {"id": "Elodie", "francais": True, "accent": "France", "genre": None, "description": None},
    {"id": "Camille", "francais": True, "accent": "France", "genre": None, "description": None},
    {"id": "Manon", "francais": True, "accent": "France", "genre": None, "description": "parisienne"},
    {"id": "Baptiste", "francais": True, "accent": "France", "genre": None, "description": None},
    {"id": "Noemie", "francais": True, "accent": "France", "genre": None, "description": None},
    {"id": "Genevieve", "francais": True, "accent": "Québec", "genre": None, "description": None},
    {"id": "Antoine", "francais": True, "accent": "Québec", "genre": None, "description": None},
)
SONIOX_TTS_VOIX_IDS = tuple(voix["id"] for voix in SONIOX_TTS_VOIX)
# La voix proposee d'office : la premiere de la liste (candidat d'accueil), jamais
# celle du connecteur (Bryce, anglaise).
SONIOX_TTS_VOIX_PAR_DEFAUT = SONIOX_TTS_VOIX_IDS[0]

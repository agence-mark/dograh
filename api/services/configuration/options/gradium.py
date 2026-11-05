"""[.mark] Lot GT (builder partie 3) : la voix Gradium, ses valeurs et ses bornes.

Tout vient de la documentation officielle de Gradium, lue le 05/11/2026 :
- https://docs.gradium.ai/guides/voice-settings (``temp``, ``padding_bonus``, ``rewrite_rules``,
  ``pronunciation_id``) ;
- https://docs.gradium.ai/guides/websocket-lifecycle.md (message ``setup``, ``output_format``) ;
- https://docs.gradium.ai/guides/recipes/telephony-audio.md (``ulaw_8000``) ;
- https://docs.gradium.ai/guides/data-residency.md (``eu.api.gradium.ai``).
Aucune valeur n'est choisie ici : ce sont les defauts et les bornes que le fournisseur publie.
"""

GRADIUM_TTS_MODELS = ("default",)

# Les deux voix francaises nommees par la note d'Evan du 05/11/2026 (demo Gradbot). Le genre vient de la
# note ; l'accent et la description ne sont pas releves (jamais devines). Toute autre voix de la
# bibliotheque Gradium se saisit par son identifiant.
GRADIUM_TTS_VOIX = (
    {"id": "jBULVCDhf05tOJN5", "nom": "Romane", "francais": True, "accent": None, "genre": "féminin", "description": None},
    {"id": "iEu63s1rhn_kegTr", "nom": "Gaspard", "francais": True, "accent": None, "genre": "masculin", "description": None},
)
GRADIUM_TTS_VOIX_IDS = tuple(voix["id"] for voix in GRADIUM_TTS_VOIX)
GRADIUM_TTS_VOIX_PAR_DEFAUT = GRADIUM_TTS_VOIX_IDS[0]
GRADIUM_TTS_VOIX_RELEVE = "2026-11-05"
GRADIUM_TTS_VOIX_SOURCE = "note d'Evan du 05/11/2026 (démo Gradbot, voix françaises du catalogue)"

# ``temp`` : defaut 0,7 ; plage conseillee 0,0 a 1,4 ; la validation du fournisseur va jusqu'a 1,5.
GRADIUM_TEMP_PAR_DEFAUT = 0.7
GRADIUM_TEMP_MIN = 0.0
GRADIUM_TEMP_MAX = 1.4

# ``padding_bonus`` : defaut 0 ; plage conseillee -4 a 4 ; la validation du fournisseur va de -5 a 5.
GRADIUM_PADDING_MIN = -4.0
GRADIUM_PADDING_MAX = 4.0

# La vitesse se regle en facteur (x 1,2). Conversion de la demo Gradbot : padding_bonus = -4 x (vitesse - 1),
# bornee a +-4. Le facteur est donc borne a 0 .. 2 par la conversion ; l'ecran propose 0,5 .. 2,0.
GRADIUM_VITESSE_MIN = 0.5
GRADIUM_VITESSE_MAX = 2.0

# ``rewrite_rules`` : une langue ou un lieu active toutes les regles de cette langue ; ``none`` les coupe.
GRADIUM_REWRITE_RULES = ("fr", "fr-be", "fr-ch", "en", "de", "es", "pt", "none")

# ``output_format`` : ``auto`` suit la frequence du transport (PCM a cette frequence si Gradium la sert,
# sinon PCM 48 kHz) ; les deux autres sont les formats du telephone (8 kHz, sans reechantillonnage).
GRADIUM_FORMATS_DE_SORTIE = ("auto", "pcm_8000", "ulaw_8000")
# Les frequences PCM que la documentation nomme (telephony-audio, limits).
GRADIUM_FREQUENCES_PCM = (8000, 16000, 24000, 48000)
GRADIUM_FREQUENCE_PAR_DEFAUT = 48000

# Adresses : l'Europe n'est une garantie que pour une organisation inscrite a la residence UE par le support ;
# sinon la requete atterrit en Europe « au mieux » (``best-effort; zone=eu``).
GRADIUM_TTS_ADRESSE_EUROPE = "wss://eu.api.gradium.ai/api/speech/tts"
GRADIUM_TTS_ADRESSE_MONDIALE = "wss://api.gradium.ai/api/speech/tts"
GRADIUM_TTS_ADRESSE_ETATS_UNIS = "wss://us.api.gradium.ai/api/speech/tts"

# Une session dure au plus 300 s selon la note d'Evan du 05/11/2026 (formule tarifaire de Gradium). ⚠️ La page
# « Limits » de la documentation lue le 05/11 dit 3000 s : l'ecart est note dans 18-a-exposer.md. Le service
# rouvre la connexion avant la plus petite des deux valeurs, la plus sure.
GRADIUM_SESSION_MAX_S = 300.0
GRADIUM_MARGE_DE_REOUVERTURE_S = 60.0

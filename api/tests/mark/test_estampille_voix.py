"""[.mark] Non-regression test for the voice stamped on a run.

The question this file answers, and it answers only this one:

    Does a voice call record WHICH VOICE it was actually played with, and the
    endpoint that voice was fetched from?

Why it exists
-------------
A run already stamps ``tts_provider`` and ``tts_model``, but neither the voice
identifier nor the endpoint. Two voices of the same provider are therefore
indistinguishable after the fact -- and ``aura-2-helena-en`` against
``aura-2-thalia-en`` is exactly the comparison the next voice bench is made of.
Without this stamp no voice bench is verifiable: the result would be an
anecdote attached to a run that cannot say what produced it.

That is the §5.4 trap of ``18-ajout-fournisseur.md``, raised by the lab on
2026-09-21 after ten voice incidents in sixteen calls.

⛔ What this file does NOT prove: that a real call reaches the database with
this stamp. It proves the value is built, that the phone path calls the
function that builds it, and that the keyboard bench does not. Playing a real
call is a paid action and belongs to a bench session, not to a test suite.
"""

import inspect
from types import SimpleNamespace

from api.services.configuration.registry import (
    DeepgramTTSConfiguration,
    ElevenlabsTTSConfiguration,
    MistralTTSConfiguration,
)
from api.services.pipecat.service_factory import stamp_voice_settings


def _configuration_de_base() -> dict:
    """What Dograh stamps today, before ours is added to it."""
    return {
        "stt_provider": "deepgram",
        "stt_model": "nova-3",
        "tts_provider": "mistral",
        "tts_model": "voxtral-mini-tts-latest",
        "llm_provider": "mistral",
        "llm_model": "mistral-large-2512",
    }


def test_un_appel_dit_avec_quelle_voix_il_a_ete_joue():
    """The provider and the model were already stamped; the voice was not.

    Six Voxtral emotions share one model name, so ``tts_model`` alone cannot
    say whether a call was played with the expressive voice or the neutral one
    -- and the lab measured on 2026-09-21 that the expressive one is precisely
    the one that drifts.
    """
    stampe = stamp_voice_settings(
        _configuration_de_base(),
        MistralTTSConfiguration(api_key="mistral-key", voice="fr_marie_neutral"),
    )

    assert stampe["tts_settings"]["voice"] == "fr_marie_neutral"


def test_lappel_dit_aussi_a_quelle_adresse_la_voix_a_ete_demandee():
    """The endpoint decides which jurisdiction synthesises the text spoken to
    the caller, which is the same residency question as transcription."""
    stampe = stamp_voice_settings(
        _configuration_de_base(),
        MistralTTSConfiguration(api_key="k", base_url="https://api.eu.mistral.ai"),
    )

    assert stampe["tts_settings"]["endpoint"] == "https://api.eu.mistral.ai"


def test_ladresse_estampillee_est_celle_RESOLUE_pas_celle_du_schema():
    """🚨 Same reasoning as the resolved turn-stop timeout: an empty field is
    not "no endpoint", it is the fallback written in the factory.

    Read off the schema, a configuration saved before the field existed would
    stamp an empty endpoint while the call really went to Europe -- and a stamp
    that lies is worse than no stamp.
    """
    stampe = stamp_voice_settings(
        _configuration_de_base(),
        DeepgramTTSConfiguration(api_key="cle", base_url=""),
    )

    assert stampe["tts_settings"]["endpoint"] == "https://api.eu.deepgram.com"


def test_une_adresse_deepgram_sans_schema_est_estampillee_normalisee():
    """The factory accepts a bare host and assumes TLS, so the stamp has to
    report the address that was really contacted, not what was typed."""
    stampe = stamp_voice_settings(
        _configuration_de_base(),
        DeepgramTTSConfiguration(api_key="cle", base_url="api.deepgram.com"),
    )

    assert stampe["tts_settings"]["endpoint"] == "https://api.deepgram.com"


def test_une_adresse_mistral_VIDE_est_estampillee_MONDIALE():
    """🔴 Le cas qui compte le plus, et celui qu'un schéma ne dit pas.

    Vidé à l'écran, le champ ne fait pas partir la voix "nulle part" : le SDK
    Mistral repart sur son point d'entrée MONDIAL. Or le traitement en Europe
    est une condition de l'offre, pas une préférence (`mistral_tts.py` l'écrit
    en tête). Estampiller "rien" laisserait lire "pas d'adresse" là où l'appel
    est parti aux États-Unis -- exactement la fiche qui ment.
    """
    stampe = stamp_voice_settings(
        _configuration_de_base(),
        MistralTTSConfiguration(api_key="k", base_url=""),
    )

    assert stampe["tts_settings"]["endpoint"] == "https://api.mistral.ai"


def test_une_adresse_mistral_europeenne_est_estampillee_europeenne():
    """Le défaut du schéma, qui est celui de tous nos appels."""
    stampe = stamp_voice_settings(
        _configuration_de_base(), MistralTTSConfiguration(api_key="k")
    )

    assert stampe["tts_settings"]["endpoint"] == "https://api.eu.mistral.ai"


def test_une_passerelle_mistral_est_estampillee_telle_quelle():
    """Une adresse que Mistral ne publie pas est transmise au SDK telle
    quelle : la fiche doit dire la même chose que la requête."""
    stampe = stamp_voice_settings(
        _configuration_de_base(),
        MistralTTSConfiguration(api_key="k", base_url="https://passerelle.interne/v1"),
    )

    assert stampe["tts_settings"]["endpoint"] == "https://passerelle.interne"


def test_la_voix_elevenlabs_ENVOYEE_est_celle_qui_est_estampillee():
    """⛔ §5.4 dans les deux sens : ce commit a déplacé la normalisation de la
    voix ElevenLabs hors de la fabrique, et c'est la SEULE ligne de production
    qu'il change. Sans cette assertion, quelqu'un qui déciderait plus tard
    d'estampiller le nom lisible ferait envoyer "Marie - abc123" comme
    identifiant de voix -- plus aucune voix sur les configurations héritées, et
    la suite resterait verte. ElevenLabs est le défaut du produit.
    """
    from types import SimpleNamespace as Config

    from api.services.pipecat.audio_config import AudioConfig
    from api.services.pipecat.service_factory import create_tts_service

    configuration = ElevenlabsTTSConfiguration(api_key="cle", voice="Marie - abc123")
    service = create_tts_service(
        Config(tts=configuration),
        AudioConfig(transport_in_sample_rate=16000, transport_out_sample_rate=24000),
    )

    envoyee = service._settings.voice
    estampillee = stamp_voice_settings(_configuration_de_base(), configuration)[
        "tts_settings"
    ]["voice"]

    assert envoyee == "abc123"
    assert estampillee == envoyee


def test_elevenlabs_estampille_lidentifiant_reellement_envoye():
    """⛔ §5.4: the stamp and the request go through the SAME function.

    ElevenLabs configurations carry a legacy ``"Name - voice_id"`` shape, and
    the factory sends only the identifier. Stamping the configured string
    would attribute to the call a voice name the provider never received.
    """
    stampe = stamp_voice_settings(
        _configuration_de_base(),
        ElevenlabsTTSConfiguration(api_key="cle", voice="Marie - abc123"),
    )

    assert stampe["tts_settings"]["voice"] == "abc123"


def test_la_casse_de_la_voix_sarvam_est_la_meme_des_deux_cotes():
    """⛔ Le défaut §5.4 laissé sur le champ voisin.

    La fabrique Sarvam met la voix en minuscules avant de l'envoyer. Une
    estampille qui garderait la majuscule attribuerait à l'appel une voix que
    le fournisseur n'a pas reçue -- petit écart, même défaut que celui que ce
    patch existe pour fermer.
    """
    from types import SimpleNamespace as Config

    from api.services.configuration.registry import SarvamTTSConfiguration
    from api.services.pipecat.audio_config import AudioConfig
    from api.services.pipecat.service_factory import create_tts_service

    configuration = SarvamTTSConfiguration(api_key="cle", voice=" Anushka ")
    service = create_tts_service(
        Config(tts=configuration),
        AudioConfig(transport_in_sample_rate=16000, transport_out_sample_rate=24000),
    )

    envoyee = service._settings.voice
    estampillee = stamp_voice_settings(_configuration_de_base(), configuration)[
        "tts_settings"
    ]["voice"]

    assert envoyee == "anushka"
    assert estampillee == envoyee


def test_un_fournisseur_sans_voix_declaree_nest_pas_estampille_a_vide():
    """An empty record would read as "played with no voice", which is false:
    the factory still hands a fallback to several providers. Saying nothing is
    the honest answer when the configuration declares nothing."""
    stampe = stamp_voice_settings(
        _configuration_de_base(),
        SimpleNamespace(provider="inworld", model="inworld-tts-1"),
    )

    assert "tts_settings" not in stampe


def test_une_voix_vide_nest_pas_estampillee():
    """Same rule, the case that actually happens: a section saved before the
    field was opened arrives with an empty string."""
    stampe = stamp_voice_settings(
        _configuration_de_base(),
        SimpleNamespace(provider="cartesia", model="sonic-2", voice="   "),
    )

    assert "tts_settings" not in stampe


def test_aucune_configuration_de_voix_ne_fait_rien():
    """A realtime call has no separate synthesis service."""
    stampe = stamp_voice_settings(_configuration_de_base(), None)

    assert "tts_settings" not in stampe


def test_ce_qui_etait_deja_estampille_reste_intact():
    """The stamp is added to what Dograh records, it does not replace it."""
    avant = _configuration_de_base()

    stampe = stamp_voice_settings(dict(avant), MistralTTSConfiguration(api_key="k"))

    for cle, valeur in avant.items():
        assert stampe[cle] == valeur


def test_le_chemin_telephonique_estampille_bien_la_voix():
    """⛔ The function working proves nothing about the function being CALLED.

    Lesson of 2026-09-11: a stamp nobody invokes is a stamp that does not
    exist, and the recordings would simply carry no voice -- silently, exactly
    like before this chantier.

    ⚠️ Read honestly: this reads the runner's source rather than running it,
    because running it needs the full stack. It catches the failure that
    actually threatens us -- the call being dropped by a refactor.
    """
    from api.services.pipecat import run_pipeline

    source = inspect.getsource(run_pipeline)

    assert "stamp_voice_settings(runtime_configuration" in source, (
        "run_pipeline no longer stamps the voice: a recorded call could not "
        "say which voice produced it, and no voice bench would be verifiable."
    )


def test_la_voix_est_estampillee_DANS_le_bloc_hors_temps_reel():
    """⛔ A realtime call has no ``user_config.tts`` at all.

    Stamped outside the guard, a speech-to-speech run would either crash at
    assembly or stamp a synthesis service that played no part in it.

    ⛔ The check is membership of the guard's block, NOT "same indentation as
    its neighbour": a refactor that moved BOTH stamps out would keep them
    aligned with each other and leave such a test green (family ③ of §7, the
    proof that is not one). Raised by the independent review of 2026-09-22.
    """
    from api.services.pipecat import run_pipeline

    lignes = inspect.getsource(run_pipeline).splitlines()

    garde = next(
        (i for i, l in enumerate(lignes) if l.strip() == "if not is_realtime:"), None
    )
    assert garde is not None, "la garde `if not is_realtime:` a disparu de run_pipeline"
    retrait_garde = len(lignes[garde]) - len(lignes[garde].lstrip())

    dans_le_bloc = False
    for ligne in lignes[garde + 1 :]:
        if not ligne.strip():
            continue
        # Le bloc s'arrête à la première ligne revenue au retrait de la garde.
        if len(ligne) - len(ligne.lstrip()) <= retrait_garde:
            break
        if ligne.lstrip().startswith("stamp_voice_settings(runtime_configuration"):
            dans_le_bloc = True
            break

    assert dans_le_bloc, (
        "the voice stamp is not inside the `if not is_realtime` block: a "
        "realtime run would be stamped with a synthesis service it never used."
    )


def test_le_banc_au_clavier_nestampille_PAS_la_voix():
    """⚠️ Stated rather than pretended.

    The keyboard bench makes nobody speak, so a voice stamp there would record
    a voice that played no part in the run. A stamp that lies is worse than no
    stamp -- it would be read later as evidence.
    """
    from api.services.workflow import text_chat_runner

    source = inspect.getsource(text_chat_runner)

    assert "stamp_voice_settings" not in source, (
        "the keyboard bench stamps a voice, which it never played: a recorded "
        "run would claim a voice it was not played with."
    )

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
    assembly or stamp a synthesis service that played no part in it. The
    transcription stamp sits inside that same guard, for the same reason, so
    the check is: both lines live at the same indentation level.
    """
    from api.services.pipecat import run_pipeline

    lignes = inspect.getsource(run_pipeline).splitlines()

    def _indentation(prefixe: str) -> int:
        for ligne in lignes:
            if ligne.lstrip().startswith(prefixe):
                return len(ligne) - len(ligne.lstrip())
        raise AssertionError(f"ligne introuvable : {prefixe}")

    assert _indentation("stamp_voice_settings(runtime_configuration") == _indentation(
        "stamp_transcription_settings(runtime_configuration"
    ), (
        "the voice stamp left the `if not is_realtime` block: a realtime run "
        "would be stamped with a synthesis service it never used."
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

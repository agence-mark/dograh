"""[.mark] Non-regression test for the voice text filters.

The question this file answers, and only this one:

    Does every voice provider get its text filters from ONE collection point,
    is the agent's markdown switch honoured there, and does an agent that
    fills in nothing get exactly the list it got before this patch?

⛔ Read that scope literally. It does NOT prove the voice sounds better. What
a filter does to a real call is judged by ear, in the browser, on the bench
agent.

Why it exists
-------------
Three phrasings of the prompt failed to stop the model answering with
``**bold**``, and the asterisks were read out loud. Pipecat has carried a
``MarkdownTextFilter`` all along; nothing in Dograh ever built one.

The shape of the defect this file guards against is not the filter itself.
Before this patch, all seventeen provider branches of ``create_tts_service``
carried their own ``text_filters=[xml_function_tag_filter]`` literal. A setting
added the obvious way -- branch by branch -- applies to whichever providers
whoever adds it happens to think of, and a provider added next month silently
gets none of them. That is why one assertion below is on the SOURCE: it is the
only way to state "no branch builds its own list" rather than "the four
branches I remembered to test do not".

🔒 Default OFF, deliberately. The filter is absent today, so installing it ON
would be choosing a value, which is not this patch's job -- the A/B benches
choose, a later patch moves the default.
"""

import inspect
from types import SimpleNamespace

import pytest

from api.schemas.workflow_configurations import (
    DEFAULT_TTS_MARKDOWN_FILTER_ENABLED,
    WorkflowConfigurationDefaults,
)
from api.services.configuration.registry import (
    CartesiaTTSConfiguration,
    DeepgramTTSConfiguration,
    ElevenlabsTTSConfiguration,
    MistralTTSConfiguration,
)
from api.services.pipecat import service_factory
from api.services.pipecat.audio_config import AudioConfig
from api.services.pipecat.service_factory import (
    construire_filtres_de_texte_voix,
    create_tts_service,
)
from pipecat.utils.text.markdown_text_filter import MarkdownTextFilter
from pipecat.utils.text.xml_function_tag_filter import XMLFunctionTagFilter

# ⛔ The literal list every provider received before this patch. Comparing
# against a list re-derived from the code would be tautological: the code is
# what moves.
FILTRES_AUJOURDHUI = (XMLFunctionTagFilter,)


def _audio_config():
    return AudioConfig(
        transport_in_sample_rate=16000,
        transport_out_sample_rate=24000,
    )


def _voix(configuration_tts, run_configs=None):
    """Build the voice service the runtime builds, through the public factory."""
    user_config = SimpleNamespace(tts=configuration_tts)
    return create_tts_service(user_config, _audio_config(), run_configs=run_configs)


# Four providers built for real, chosen to span the shapes: Deepgram (settings
# object), Mistral (our own regional subclass), Cartesia and ElevenLabs
# (websocket services). The SOURCE assertion below covers the other thirteen.
FOURNISSEURS = {
    "cartesia": lambda: CartesiaTTSConfiguration(api_key="cartesia-key"),
    "deepgram": lambda: DeepgramTTSConfiguration(api_key="deepgram-key"),
    "elevenlabs": lambda: ElevenlabsTTSConfiguration(api_key="elevenlabs-key"),
    "mistral": lambda: MistralTTSConfiguration(api_key="mistral-key"),
}


# --------------------------------------------------------------------------- #
# 1. An agent that fills in nothing is built exactly as before
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("nom", sorted(FOURNISSEURS))
def test_sans_reglage_la_liste_est_celle_daujourdhui(nom):
    service = _voix(FOURNISSEURS[nom]())
    assert tuple(type(f) for f in service._text_filters) == FILTRES_AUJOURDHUI


@pytest.mark.parametrize("nom", sorted(FOURNISSEURS))
def test_filtre_eteint_explicitement_ne_change_rien(nom):
    service = _voix(
        FOURNISSEURS[nom](), run_configs={"tts_markdown_filter_enabled": False}
    )
    assert tuple(type(f) for f in service._text_filters) == FILTRES_AUJOURDHUI


# --------------------------------------------------------------------------- #
# 2. Turned on, the filter is there -- on every provider
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("nom", sorted(FOURNISSEURS))
def test_filtre_allume_sur_chaque_fournisseur(nom):
    service = _voix(
        FOURNISSEURS[nom](), run_configs={"tts_markdown_filter_enabled": True}
    )
    types = [type(f) for f in service._text_filters]
    assert types == [XMLFunctionTagFilter, MarkdownTextFilter], (
        f"{nom} did not receive the markdown filter. Either its branch still "
        f"builds its own list, or it does not forward text_filters at all."
    )


def test_lordre_met_le_filtre_de_balises_en_premier():
    """The markdown filter must never see a half-stripped tool call."""
    filtres = construire_filtres_de_texte_voix({"tts_markdown_filter_enabled": True})
    assert isinstance(filtres[0], XMLFunctionTagFilter)
    assert isinstance(filtres[1], MarkdownTextFilter)


# --------------------------------------------------------------------------- #
# 3. No branch builds its own list any more
# --------------------------------------------------------------------------- #


def test_aucune_branche_ne_construit_sa_propre_liste():
    """The assertion that covers the thirteen providers not built above.

    ⛔ Deliberately on the source text. A setting wired branch by branch is
    the exact defect this patch removes, and no runtime assertion can state
    "and none of the other sixteen either".
    """
    source = inspect.getsource(service_factory.create_tts_service)
    assert "text_filters=[" not in source, (
        "A branch of create_tts_service builds its own text_filters list again. "
        "Every branch must receive the list from construire_filtres_de_texte_voix, "
        "or a setting turned on will apply to some providers and not others."
    )
    assert source.count("text_filters=text_filters") == 17, (
        "Every provider branch that forwards text filters must forward the "
        "collected list. The count changed: a provider was added or removed, "
        "and this test is where that gets noticed."
    )


# --------------------------------------------------------------------------- #
# 4. The setting is declared, so it is on screen
# --------------------------------------------------------------------------- #


def test_le_reglage_est_declare_avec_le_defaut_daujourdhui():
    configuration = WorkflowConfigurationDefaults()
    assert configuration.tts_markdown_filter_enabled is False
    assert DEFAULT_TTS_MARKDOWN_FILTER_ENABLED is False


# --------------------------------------------------------------------------- #
# 5. What the filter actually does to the text
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_le_gras_ne_se_prononce_plus():
    filtre = MarkdownTextFilter()
    await filtre.reset_interruption()
    assert await filtre.filter("**dix-huit heures**") == "dix-huit heures"


@pytest.mark.asyncio
async def test_les_parentheses_restent_prononcees():
    """Written down because it is the limit of this lot, not an oversight.

    A stage direction the model writes in parentheses is still spoken.
    Filtering parentheses would eat the useful ones too, so it stays a matter
    for the prompt and the dedicated node.
    """
    filtre = MarkdownTextFilter()
    await filtre.reset_interruption()
    assert "(un instant, je tente le transfert)" in await filtre.filter(
        "(un instant, je tente le transfert)"
    )

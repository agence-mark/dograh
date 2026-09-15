"""[.mark] Non-regression test for writing dictated numbers as digits.

The questions this file answers:

    With the switch off, is the pipeline exactly the one of before? With it
    on, does a final French transcript reach the aggregator in digits -- and
    do interims, other languages and ordinary sentences come out untouched?

Why it exists
-------------
On 2026-09-15 a phone number dictated in words was transcribed correctly by
Flux and then stitched into eleven wrong digits by the model, twice. The
conversion hands the model digits instead.

🔑 Tested at the level of the feature: a transcript goes THROUGH the processor
and what comes out is read. Where the processor sits is asserted on the list
the real ``build_pipeline`` returns, and that it is called with the agent's
configuration is asserted in ``test_transmission_de_la_configuration.py``.
"""

from types import SimpleNamespace
from unittest.mock import patch

import pytest
from pipecat.frames.frames import InterimTranscriptionFrame, TranscriptionFrame
from pipecat.processors.frame_processor import FrameProcessor
from pipecat.transcriptions.language import Language

from api.schemas.workflow_configurations import WorkflowConfigurationDefaults
from api.services.pipecat import conversion_nombres
from api.services.pipecat.conversion_nombres import (
    ConversionNombresProcessor,
    creer_conversion_nombres,
    langue_agent_francaise,
)
from api.services.pipecat.pipeline_builder import (
    build_pipeline,
    build_realtime_pipeline,
)
from pipecat.tests import run_test

PHRASE_DU_15_09 = "le zéro sept quatre vingt huit vingt six quatorze zéro neuf"

STT_FRANCAIS = SimpleNamespace(language="fr", language_hints=None)


def _transport():
    entree, sortie = FrameProcessor(), FrameProcessor()
    return SimpleNamespace(input=lambda: entree, output=lambda: sortie)


def _composants():
    """The positional arguments of ``build_pipeline``, as named processors."""
    return {
        "transport": _transport(),
        "stt": FrameProcessor(),
        "audio_buffer": FrameProcessor(),
        "llm": FrameProcessor(),
        "tts": FrameProcessor(),
        "user_context_aggregator": FrameProcessor(),
        "assistant_context_aggregator": FrameProcessor(),
        "pipeline_engine_callback_processor": FrameProcessor(),
        "pipeline_metrics_aggregator": FrameProcessor(),
        "termination_funnel": FrameProcessor(),
    }


async def _sortie(processeur, trame):
    descendantes, _ = await run_test(processeur, frames_to_send=[trame])
    return [t for t in descendantes if isinstance(t, type(trame))]


def _finale(texte, language=None):
    return TranscriptionFrame(
        text=texte, user_id="appelant", timestamp="0", language=language
    )


# --------------------------------------------------------------------------- #
# 1. Off: today's pipeline, unchanged
# --------------------------------------------------------------------------- #


def test_eteint_la_liste_des_processeurs_est_identique():
    composants = _composants()
    # ⚠️ Each Pipeline wraps the list in its own source and sink objects, so
    # the two ends differ by construction: the processors between them are
    # what is compared.
    sans = build_pipeline(**composants).processors[1:-1]
    avec = build_pipeline(**composants, conversion_nombres=None).processors[1:-1]
    assert len(sans) == 11
    assert avec == sans
    assert not any(isinstance(p, ConversionNombresProcessor) for p in avec)


def test_le_defaut_est_eteint():
    assert WorkflowConfigurationDefaults().conversion_nombres_transcription is False
    assert creer_conversion_nombres({}, STT_FRANCAIS) is None
    assert creer_conversion_nombres(None, STT_FRANCAIS) is None
    # ⛔ A stored null means "not filled in", not a value.
    assert (
        creer_conversion_nombres(
            {"conversion_nombres_transcription": None}, STT_FRANCAIS
        )
        is None
    )


# --------------------------------------------------------------------------- #
# 2. On: where it sits
# --------------------------------------------------------------------------- #


def test_allume_le_processeur_est_juste_avant_lagregateur():
    composants = _composants()
    conversion = creer_conversion_nombres(
        {"conversion_nombres_transcription": True}, STT_FRANCAIS
    )
    assert isinstance(conversion, ConversionNombresProcessor)

    processeurs = build_pipeline(**composants, conversion_nombres=conversion).processors
    agregateur = composants["user_context_aggregator"]
    assert processeurs.index(conversion) == processeurs.index(agregateur) - 1
    # And after the transcription: it converts what the transcription wrote.
    assert processeurs.index(conversion) > processeurs.index(composants["stt"])


def test_le_pipeline_temps_reel_ne_contient_pas_la_conversion():
    """No transcription step in realtime mode, so nothing to convert."""
    pipeline = build_realtime_pipeline(
        _transport(),
        FrameProcessor(),
        FrameProcessor(),
        FrameProcessor(),
        FrameProcessor(),
        FrameProcessor(),
        FrameProcessor(),
        FrameProcessor(),
    )
    assert not any(
        isinstance(p, ConversionNombresProcessor) for p in pipeline.processors
    )


# --------------------------------------------------------------------------- #
# 3. On: what comes out
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_la_phrase_du_15_09_sort_en_chiffres():
    processeur = ConversionNombresProcessor(langue_agent_francaise=True)
    (trame,) = await _sortie(processeur, _finale(PHRASE_DU_15_09))
    assert trame.text == "le 07 88 26 14 09"
    # The other fields are left alone.
    assert trame.user_id == "appelant"
    assert trame.timestamp == "0"


@pytest.mark.asyncio
async def test_la_phrase_dorigine_nest_pas_modifiee_et_la_copie_garde_son_identifiant():
    """🔒 D2: the live transcript stays in words.

    Observers read the frame later, from a queue. Rewritten in place, the live
    view would show words or digits depending on timing. A copy is pushed
    instead, with the SAME id: the live observer has already seen that id and
    skips it, rather than showing the sentence twice.
    """
    processeur = ConversionNombresProcessor(langue_agent_francaise=True)
    originale = _finale(PHRASE_DU_15_09)
    (sortie,) = await _sortie(processeur, originale)

    assert originale.text == PHRASE_DU_15_09
    assert sortie is not originale
    assert sortie.text == "le 07 88 26 14 09"
    assert sortie.id == originale.id


@pytest.mark.asyncio
@pytest.mark.parametrize("phrase", ["il me reste deux bûches", "une fois par an"])
async def test_les_phrases_ordinaires_sortent_inchangees(phrase):
    processeur = ConversionNombresProcessor(langue_agent_francaise=True)
    (trame,) = await _sortie(processeur, _finale(phrase))
    assert trame.text == phrase


@pytest.mark.asyncio
async def test_une_transcription_provisoire_sort_inchangee():
    """⛔ The "minimum words" interruption counts the words of interims."""
    processeur = ConversionNombresProcessor(langue_agent_francaise=True)
    provisoire = InterimTranscriptionFrame(
        text=PHRASE_DU_15_09, user_id="appelant", timestamp="0"
    )
    (trame,) = await _sortie(processeur, provisoire)
    assert trame.text == PHRASE_DU_15_09


@pytest.mark.asyncio
async def test_la_langue_detectee_de_la_phrase_decide():
    processeur = ConversionNombresProcessor(langue_agent_francaise=True)
    (anglaise,) = await _sortie(processeur, _finale("vingt ans", Language.EN))
    assert anglaise.text == "vingt ans"

    processeur = ConversionNombresProcessor(langue_agent_francaise=False)
    (francaise,) = await _sortie(processeur, _finale("vingt ans", Language.FR_FR))
    assert francaise.text == "20 ans"


@pytest.mark.asyncio
async def test_une_conversion_qui_echoue_garde_le_texte_dorigine():
    """⛔ A conversion failure never costs the call."""
    processeur = ConversionNombresProcessor(langue_agent_francaise=True)
    with patch.object(
        conversion_nombres, "_alpha2digit", side_effect=RuntimeError("panne")
    ):
        (trame,) = await _sortie(processeur, _finale(PHRASE_DU_15_09))
    assert trame.text == PHRASE_DU_15_09


# --------------------------------------------------------------------------- #
# 4. The agent's language
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "language,indications,attendu",
    [
        ("fr", None, True),
        ("fr-FR", None, True),
        ("multi", None, False),
        ("multi", ["fr"], True),
        ("", ["en", "fr"], True),
        ("en", ["fr"], False),
        ("en", None, False),
    ],
)
def test_langue_agent_francaise(language, indications, attendu):
    stt = SimpleNamespace(language=language, language_hints=indications)
    assert langue_agent_francaise(stt) is attendu

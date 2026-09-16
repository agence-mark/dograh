"""[.mark] Non-regression test for writing dictated numbers as digits.

The questions this file answers:

    With both switches off, is the pipeline exactly the one of before? With
    either on, is the ONE caller reading step right before the model, and
    nothing before the aggregator? Through the real aggregator, does the model
    read the digits while the recorded transcript keeps the caller's words?
    Does a reference get its note only at a step that collects one? Is every
    number recorded for the bench, once?

Why it exists
-------------
On 2026-09-15 a phone number dictated in words was transcribed correctly by
Flux and then stitched into eleven wrong digits by the model, twice. The
conversion hands the model digits instead. Since the plan nombres-dictes
(2026-09-16, N1) it is done after the aggregator, together with the town
check, by ``lecture_appelant.py``: before the aggregator, ``text2num`` froze
ONE reading of a postal code ("soixante sept cent quarante" -> 67140).

🔑 Tested at the level of the feature: a transcript goes THROUGH the real user
aggregator and the step; what the model reads AND what is recorded are read.
That the step is built with the agent's configuration is asserted in
``test_transmission_de_la_configuration.py``.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from pipecat.frames.frames import (
    LLMContextFrame,
    ProposedUserStartedSpeakingFrame,
    ProposedUserStoppedSpeakingFrame,
    TranscriptionFrame,
)
from pipecat.pipeline.pipeline import Pipeline
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import (
    LLMAssistantAggregator,
    LLMUserAggregator,
    LLMUserAggregatorParams,
)
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor
from pipecat.tests import run_test
from pipecat.tests.utils import SleepFrame
from pipecat.turns.user_turn_strategies import ExternalUserTurnStrategies

from api.schemas.organization_preferences import AdresseEtablissement
from api.schemas.workflow_configurations import WorkflowConfigurationDefaults
from api.services.nombres import lecture
from api.services.pipecat import lecture_appelant
from api.services.pipecat.conversion_nombres import (
    conversion_allumee,
    langue_agent_francaise,
)
from api.services.pipecat.lecture_appelant import (
    CLE_TRACE_NOMBRES,
    LectureAppelantProcessor,
    creer_lecture_appelant,
    etape_reference,
    lire_message_tape,
)
from api.services.pipecat.pipeline_builder import (
    build_pipeline,
    build_realtime_pipeline,
)
from api.services.pipecat.realtime_feedback_observer import register_turn_log_handlers
from api.services.pipecat.verification_communes import CLE_TRACE, consigner_dans
from api.services.workflow.conversation_history import build_conversation_history

PHRASE_DU_15_09 = "le zéro sept quatre vingt huit vingt six quatorze zéro neuf"
TELEPHONE = "zéro six douze trente-quatre cinquante-six soixante-dix-huit"
REFERENCE = "facture deux mille vingt-six tiret huit cent quarante-sept"
MENTION_REFERENCE = (
    "[Lecture des nombres : référence entendue « deux mille vingt-six tiret huit cent "
    "quarante-sept », écrite « 2026-847 ». Relis-la groupe par groupe et fais-la confirmer "
    "avant de la noter.]"
)

STT_FRANCAIS = SimpleNamespace(language="fr", language_hints=None)
MAGASIN = AdresseEtablissement(code_postal="60740", code_insee="60589", commune="Saint-Maximin")

NOEUD_COORDONNEES = SimpleNamespace(
    name="coordonnees",
    extraction_variables=[SimpleNamespace(name="numero_dicte"), SimpleNamespace(name="commune")],
)
NOEUD_FACTURE = SimpleNamespace(
    name="qualif_facture", extraction_variables=[SimpleNamespace(name="reference_facture")]
)
NOEUD_ACCUEIL = SimpleNamespace(name="accueil", extraction_variables=[SimpleNamespace(name="motif")])

DEMARRAGE_S = 15


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


def _processeur(noeud, consigner=None, conversion=True, verification=True, langue_francaise=True):
    return LectureAppelantProcessor(
        conversion=conversion,
        verification=verification,
        langue_francaise=langue_francaise,
        adresse=MAGASIN,
        etape_courante=lambda: noeud,
        consigner=consigner,
    )


async def _lu(processeur, texte):
    contexte = LLMContext(messages=[{"role": "user", "content": texte}])
    await run_test(processeur, frames_to_send=[LLMContextFrame(context=contexte)], start_timeout=DEMARRAGE_S)
    return contexte.messages[-1]["content"]


# --------------------------------------------------------------------------- #
# 1. Both off: today's pipeline, unchanged
# --------------------------------------------------------------------------- #


def test_deux_interrupteurs_eteints_aucune_etape():
    composants = _composants()
    etape = creer_lecture_appelant(
        {"conversion_nombres_transcription": False, "verification_communes": False},
        STT_FRANCAIS, None, lambda: None,
    )
    assert etape is None
    # ⚠️ Each Pipeline wraps the list in its own source and sink objects, so
    # the two ends differ by construction: the processors between them are
    # what is compared.
    sans = build_pipeline(**composants).processors[1:-1]
    avec = build_pipeline(**composants, lecture_appelant=etape).processors[1:-1]
    assert len(sans) == 11
    assert avec == sans
    # Nothing .mark between the transcription and the model.
    entre = avec[avec.index(composants["stt"]) + 1:avec.index(composants["llm"])]
    assert entre == [composants["user_context_aggregator"]]


def test_le_defaut_est_eteint():
    assert WorkflowConfigurationDefaults().conversion_nombres_transcription is False
    for configuration in ({}, None, {"conversion_nombres_transcription": None}):
        # ⛔ A stored null means "not filled in", not a value.
        assert conversion_allumee(configuration) is False
    assert conversion_allumee({"conversion_nombres_transcription": True}) is True


# --------------------------------------------------------------------------- #
# 2. Either on: one step, right before the model, nothing before the aggregator
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "conversion,verification", [(True, False), (False, True), (True, True)]
)
def test_letape_est_juste_avant_le_modele_rien_avant_lagregateur(conversion, verification):
    composants = _composants()
    etape = creer_lecture_appelant(
        {"conversion_nombres_transcription": conversion, "verification_communes": verification},
        STT_FRANCAIS, MAGASIN, lambda: None,
    )
    assert isinstance(etape, LectureAppelantProcessor)
    assert (etape._conversion, etape._verification) == (conversion, verification)

    processeurs = build_pipeline(**composants, lecture_appelant=etape).processors
    assert processeurs.index(etape) == processeurs.index(composants["llm"]) - 1
    assert processeurs.index(etape) > processeurs.index(composants["user_context_aggregator"])
    # Counted: exactly one .mark step, and the transcription feeds the aggregator directly.
    assert sum(1 for p in processeurs if isinstance(p, LectureAppelantProcessor)) == 1
    assert processeurs.index(composants["user_context_aggregator"]) == processeurs.index(composants["stt"]) + 1


def test_apres_la_porte_du_superviseur_de_decroche():
    composants = _composants()
    porte = FrameProcessor()
    superviseur = FrameProcessor()
    superviseur.llm_gate = lambda: porte
    etape = _processeur(NOEUD_COORDONNEES)
    processeurs = build_pipeline(**composants, lecture_appelant=etape, answer_supervisor=superviseur).processors
    assert processeurs.index(porte) < processeurs.index(etape) == processeurs.index(composants["llm"]) - 1


def test_le_pipeline_temps_reel_ne_contient_pas_letape():
    """No transcription step in realtime mode, so nothing to read."""
    pipeline = build_realtime_pipeline(_transport(), *[FrameProcessor() for _ in range(7)])
    assert not any(isinstance(p, LectureAppelantProcessor) for p in pipeline.processors)


# --------------------------------------------------------------------------- #
# 3. At the level of the feature: the real aggregator
# --------------------------------------------------------------------------- #


class _Capture(FrameProcessor):
    def __init__(self):
        super().__init__()
        self.lu_par_le_modele: list[str] = []

    async def process_frame(self, frame, direction: FrameDirection):
        await super().process_frame(frame, direction)
        if isinstance(frame, LLMContextFrame):
            self.lu_par_le_modele.append(frame.context.messages[-1]["content"])
        await self.push_frame(frame, direction)


async def _par_lagregateur(texte, noeud):
    contexte = LLMContext(messages=[{"role": "assistant", "content": "Je vous écoute."}])
    agregateur = LLMUserAggregator(
        contexte, params=LLMUserAggregatorParams(user_turn_strategies=ExternalUserTurnStrategies())
    )
    enregistre = []
    coordinateur = SimpleNamespace(
        record_user_transcript=AsyncMock(side_effect=lambda text, **_: enregistre.append(text)),
        record_assistant_transcript=AsyncMock(),
    )
    register_turn_log_handlers(coordinateur, agregateur, LLMAssistantAggregator(contexte))
    modele = _Capture()
    await run_test(
        Pipeline([agregateur, _processeur(noeud), modele]),
        frames_to_send=[
            ProposedUserStartedSpeakingFrame(),
            TranscriptionFrame(text=texte, user_id="", timestamp="now"),
            ProposedUserStoppedSpeakingFrame(),
            SleepFrame(sleep=1.0),
        ],
        start_timeout=DEMARRAGE_S,
    )
    return enregistre, modele.lu_par_le_modele, contexte


@pytest.mark.asyncio
async def test_telephone_enregistre_en_mots_lu_en_chiffres():
    """🔒 N1: the recorded transcript keeps the words, the model reads digits."""
    enregistre, lu, contexte = await _par_lagregateur(TELEPHONE, NOEUD_COORDONNEES)
    assert enregistre == [TELEPHONE]
    assert lu == ["06 12 34 56 78"]
    # The variable extraction reads the same history as the model.
    historique = build_conversation_history(contexte)
    assert "06 12 34 56 78" in historique and TELEPHONE not in historique


@pytest.mark.asyncio
async def test_code_postal_dicte_a_letape_coordonnees():
    texte = "Saint-Maximin soixante sept cent quarante"
    enregistre, lu, contexte = await _par_lagregateur(texte, NOEUD_COORDONNEES)
    assert enregistre == [texte]
    assert lu == [
        "Saint-Maximin 60740 [Vérification de la commune : « Saint-Maximin » correspond à "
        "Saint-Maximin (60740, Oise). Utilise ce nom sans le faire répéter.]"
    ]
    assert lu[0] in build_conversation_history(contexte)


# --------------------------------------------------------------------------- #
# 4. References (N4) and amounts (N3)
# --------------------------------------------------------------------------- #


def test_etape_reference():
    assert etape_reference(NOEUD_FACTURE) is True
    assert etape_reference(NOEUD_COORDONNEES) is False
    assert etape_reference(None) is False


@pytest.mark.asyncio
async def test_reference_mentionnee_seulement_a_letape_qui_la_recueille():
    assert await _lu(_processeur(NOEUD_FACTURE), REFERENCE) == f"facture 2026-847 {MENTION_REFERENCE}"
    assert await _lu(_processeur(NOEUD_ACCUEIL), REFERENCE) == "facture 2026-847"


@pytest.mark.asyncio
async def test_montant_ambigu_mentionne_a_toute_etape():
    assert await _lu(_processeur(NOEUD_ACCUEIL), "trois mille cinq euros") == (
        "3005 euros [Lecture des nombres : « trois mille cinq » peut être 3 500 € ou "
        "3 005 €. Si tu notes ce montant, note les deux.]"
    )


@pytest.mark.asyncio
async def test_conversion_eteinte_ni_chiffres_ni_mention_de_nombre():
    processeur = _processeur(NOEUD_FACTURE, conversion=False)
    assert await _lu(processeur, REFERENCE) == REFERENCE


# --------------------------------------------------------------------------- #
# 5. Records, idempotence, provisional contexts, failures
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_traces_ecrites_une_seule_fois_contexte_renvoye_deux_fois():
    recueilli: dict = {}
    processeur = _processeur(NOEUD_COORDONNEES, consigner=consigner_dans(lambda: recueilli))
    contexte = LLMContext(messages=[{"role": "user", "content": "Saint-Maximin soixante sept cent quarante"}])
    await run_test(
        processeur,
        frames_to_send=[LLMContextFrame(context=contexte), LLMContextFrame(context=contexte)],
        start_timeout=DEMARRAGE_S,
    )
    contenu = contexte.messages[-1]["content"]
    assert contenu.count("60740") == 2  # once written, once in the town note
    assert contenu.count("[Vérification de la commune") == 1
    (nombre,) = recueilli[CLE_TRACE_NOMBRES]
    assert nombre == {
        "etape": "coordonnees",
        "entendu": "soixante sept cent quarante",
        "type": "code_postal",
        "ecrit": "60740",
        "lectures": ["60740", "67140"],
        "retenu": "60740",
        "statut": "sure",
    }
    (commune,) = recueilli[CLE_TRACE]
    assert commune["commune_retenue"]["nom"] == "Saint-Maximin"


@pytest.mark.asyncio
async def test_contexte_provisoire_marque():
    recueilli: dict = {}
    contexte = LLMContext(messages=[{"role": "user", "content": TELEPHONE}])
    await run_test(
        _processeur(NOEUD_COORDONNEES, consigner=consigner_dans(lambda: recueilli)),
        frames_to_send=[LLMContextFrame(context=contexte, speculation=True)],
        start_timeout=DEMARRAGE_S,
    )
    (nombre,) = recueilli[CLE_TRACE_NOMBRES]
    assert nombre["provisoire"] is True
    assert nombre["type"] == "telephone"


@pytest.mark.asyncio
async def test_un_echec_du_lecteur_laisse_le_message_intact():
    """⛔ T9: a failure never costs the call."""
    with patch.object(lecture, "lire_nombres", side_effect=RuntimeError("panne")):
        assert await _lu(_processeur(NOEUD_COORDONNEES), PHRASE_DU_15_09) == PHRASE_DU_15_09


@pytest.mark.asyncio
async def test_une_autre_langue_aucune_reecriture():
    processeur = _processeur(NOEUD_ACCUEIL, langue_francaise=False)
    assert await _lu(processeur, PHRASE_DU_15_09) == PHRASE_DU_15_09


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "phrase,attendu",
    [
        (PHRASE_DU_15_09, "le 07 88 26 14 09"),
        ("il me reste deux bûches", "il me reste deux bûches"),
        ("une fois par an", "une fois par an"),
        ("un poêle tout neuf", "un poêle tout neuf"),
    ],
)
async def test_les_phrases_du_15_09(phrase, attendu):
    assert await _lu(_processeur(NOEUD_ACCUEIL), phrase) == attendu


# --------------------------------------------------------------------------- #
# 6. The keyboard (R5)
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_clavier_meme_traitement_que_lappel():
    allume = {"conversion_nombres_transcription": True}
    recueilli: dict = {}
    consigner = consigner_dans(lambda: recueilli)
    assert await lire_message_tape(TELEPHONE, allume, STT_FRANCAIS, MAGASIN, NOEUD_ACCUEIL, consigner) == (
        "06 12 34 56 78"
    )
    assert await lire_message_tape(REFERENCE, allume, STT_FRANCAIS, MAGASIN, NOEUD_FACTURE, consigner) == (
        f"facture 2026-847 {MENTION_REFERENCE}"
    )
    assert await lire_message_tape(REFERENCE, allume, STT_FRANCAIS, MAGASIN, NOEUD_ACCUEIL, consigner) == (
        "facture 2026-847"
    )
    # Conversion off: words kept, the town note still there.
    assert await lire_message_tape(
        "Saint-Maximin soixante sept cent quarante", {}, STT_FRANCAIS, MAGASIN, NOEUD_COORDONNEES, consigner
    ) == (
        "Saint-Maximin soixante sept cent quarante [Vérification de la commune : « Saint-Maximin » "
        "correspond à Saint-Maximin (60740, Oise). Utilise ce nom sans le faire répéter.]"
    )
    # Not French: nothing rewritten.
    anglais = SimpleNamespace(language="en", language_hints=None)
    assert await lire_message_tape(TELEPHONE, allume, anglais, MAGASIN, NOEUD_ACCUEIL, consigner) == TELEPHONE
    # Counted: three messages read with the conversion on.
    assert [n["type"] for n in recueilli[CLE_TRACE_NOMBRES]] == ["telephone", "reference", "reference"]


# --------------------------------------------------------------------------- #
# 7. The agent's language
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


def test_le_module_ne_fabrique_plus_detape_avant_lagregateur():
    """T5: the old step is gone, not left as dead code."""
    from api.services.pipecat import conversion_nombres

    assert not hasattr(conversion_nombres, "ConversionNombresProcessor")
    assert not hasattr(conversion_nombres, "creer_conversion_nombres")
    assert not hasattr(lecture_appelant, "ConversionNombresProcessor")

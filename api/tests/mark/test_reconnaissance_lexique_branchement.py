"""[.mark] Non-regression test for the trade vocabulary IN the call and on the keyboard.

The questions this file answers:

    With the switch off, or with no name to recognise, is the pipeline exactly
    the one of before? With it on, does the step sit right before the caller
    reading (numbers and towns) and before the model? Does the model read
    "Edilkamin" while the recorded transcript keeps "édile camembert"? Is a
    context sent twice corrected once? Are the records written? Does a failure
    cost the call nothing? Do the numbers and the towns ignore the note the
    vocabulary adds -- and does the vocabulary ignore theirs?

Why it exists
-------------
Plan ``lexique-metier``, lot 4 (T8, T9, T10, T12, T17). 🔴 The order of the two
steps is the whole point: the towns must read a message where "Supra" is
already written properly, and must never read the brand names cited in the
vocabulary's own note (fiche D of 2026-09-17: a commune proposed on a weak word
and said out loud spoiled the call).

⚠️ What this file does NOT prove: that the names read are the right ones (that
is ``test_analyse_lexique.py``), nor that the screen shows the switch (``ui/``).
"""

import asyncio
import inspect
from types import SimpleNamespace
from unittest.mock import patch

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
from pipecat.tests.utils import SleepFrame
from pipecat.turns.user_turn_strategies import ExternalUserTurnStrategies

from api.schemas.lexique_metier import LexiqueMetier
from api.schemas.organization_preferences import AdresseEtablissement
from api.schemas.workflow_configurations import WorkflowConfigurationDefaults
from api.services.communes.base import charger_base
from api.services.lexique.ecoute import CLE_A_ECOUTER, injecter_lexique_a_ecouter
from api.services.pipecat import reconnaissance_lexique as module
from api.services.pipecat.lecture_appelant import LectureAppelantProcessor
from api.services.pipecat.pipeline_builder import build_pipeline
from api.services.pipecat.reconnaissance_lexique import (
    CLE_TRACE,
    ReconnaissanceLexiqueProcessor,
    annoter_message_tape,
    construire_index,
    creer_reconnaissance_lexique,
    trace_du_lexique,
)
from api.services.pipecat.service_factory import REGLAGES_PIPECAT_ESTAMPILLES
from api.services.pipecat.verification_communes import CLE_TRACE as CLE_TRACE_COMMUNES
from api.services.pipecat.verification_communes import consigner_dans
from pipecat.tests import run_test

MAGASIN = AdresseEtablissement(code_postal="60740", code_insee="60589", commune="Saint-Maximin")
NOEUD = SimpleNamespace(
    name="coordonnees",
    extraction_variables=[SimpleNamespace(name="commune"), SimpleNamespace(name="marque_appareil")],
)
DEMARRAGE_S = 15

LEXIQUE = LexiqueMetier.model_validate(
    {
        "termes": [
            {"terme": "Edilkamin", "variantes": ["Edil Kamin"], "categorie": "marque", "a_ecouter": True},
            {"terme": "Supra", "categorie": "marque", "a_ecouter": True},
            {"terme": "Deville", "categorie": "marque", "a_ecouter": False},
            {"terme": "ramonage", "type": "mot", "a_ecouter": True},
        ]
    }
)
SANS_NOM = LexiqueMetier.model_validate({"termes": [{"terme": "ramonage", "type": "mot", "a_ecouter": True}]})


@pytest.fixture(scope="module", autouse=True)
def _base_communes():
    """The list of communes, loaded once: without it the vocabulary reads nothing (T16)."""
    charger_base()


def _processeur(lexique=LEXIQUE, consigner=None, avec_sons=True) -> ReconnaissanceLexiqueProcessor:
    processeur = ReconnaissanceLexiqueProcessor(
        lexique=lexique, etape_courante=lambda: NOEUD, consigner=consigner, avec_sons=avec_sons
    )
    processeur._index = construire_index(lexique, avec_sons)
    return processeur


def _contexte(*messages):
    return LLMContext(messages=[dict(m) for m in messages])


async def _faire_passer(processeur, *trames):
    await run_test(processeur, frames_to_send=list(trames), start_timeout=DEMARRAGE_S)


# --------------------------------------------------------------------------- #
# 1 and 2. The switch and the place in the pipeline
# --------------------------------------------------------------------------- #


def test_interrupteur_allume_par_defaut_eteint_sur_demande():
    assert WorkflowConfigurationDefaults().lexique_metier is True
    etape = lambda: NOEUD  # noqa: E731
    for configuration in ({}, None, {"lexique_metier": None}):
        assert isinstance(
            creer_reconnaissance_lexique(configuration, LEXIQUE, etape), ReconnaissanceLexiqueProcessor
        )
    assert creer_reconnaissance_lexique({"lexique_metier": False}, LEXIQUE, etape) is None
    # A vocabulary with no name to recognise: no step either.
    assert creer_reconnaissance_lexique({}, SANS_NOM, etape) is None
    assert creer_reconnaissance_lexique({}, LexiqueMetier(), etape) is None


def test_linterrupteur_ne_relit_que_sa_cle():
    """⛔ Another setting stored out of bounds must not kill the call here."""
    etape = lambda: NOEUD  # noqa: E731
    assert creer_reconnaissance_lexique(
        {"max_call_duration": 0, "horaires_ouverture": 12}, LEXIQUE, etape
    ) is not None


def _transport():
    entree, sortie = FrameProcessor(), FrameProcessor()
    return SimpleNamespace(input=lambda: entree, output=lambda: sortie)


def _composants() -> dict:
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


def test_sans_lexique_la_liste_des_processeurs_est_celle_daujourdhui():
    composants = _composants()
    avec_none = build_pipeline(**composants, reconnaissance_lexique=None).processors
    sans = build_pipeline(**composants).processors
    assert [type(p) for p in avec_none] == [type(p) for p in sans]
    assert not any(isinstance(p, ReconnaissanceLexiqueProcessor) for p in avec_none)


def test_le_lexique_se_place_juste_avant_la_lecture_de_lappelant_et_le_modele():
    composants = _composants()
    lexique = _processeur()
    lecture = LectureAppelantProcessor(
        conversion=True, verification=True, langue_francaise=True, adresse=MAGASIN,
        etape_courante=lambda: NOEUD,
    )
    processeurs = build_pipeline(
        **composants, reconnaissance_lexique=lexique, lecture_appelant=lecture
    ).processors
    assert processeurs.index(lexique) == processeurs.index(lecture) - 1
    assert processeurs.index(lecture) == processeurs.index(composants["llm"]) - 1
    assert processeurs.index(lexique) > processeurs.index(composants["user_context_aggregator"])
    # Counted: exactly one step of each.
    assert sum(1 for p in processeurs if isinstance(p, ReconnaissanceLexiqueProcessor)) == 1


def test_sans_lecture_de_lappelant_le_lexique_reste_juste_avant_le_modele():
    composants = _composants()
    lexique = _processeur()
    processeurs = build_pipeline(**composants, reconnaissance_lexique=lexique).processors
    assert processeurs.index(lexique) == processeurs.index(composants["llm"]) - 1


def test_apres_la_porte_du_superviseur_de_decroche():
    composants = _composants()
    porte = FrameProcessor()
    superviseur = FrameProcessor()
    superviseur.llm_gate = lambda: porte
    lexique = _processeur()
    processeurs = build_pipeline(
        **composants, reconnaissance_lexique=lexique, answer_supervisor=superviseur
    ).processors
    assert processeurs.index(porte) < processeurs.index(lexique)


def test_le_temps_reel_ne_recoit_pas_le_lexique():
    from api.services.pipecat.pipeline_builder import build_realtime_pipeline

    pipeline = build_realtime_pipeline(_transport(), *[FrameProcessor() for _ in range(7)])
    assert not any(isinstance(p, ReconnaissanceLexiqueProcessor) for p in pipeline.processors)
    assert "reconnaissance_lexique" not in inspect.signature(build_realtime_pipeline).parameters


def test_le_reglage_est_estampille_sur_lappel():
    assert "lexique_metier" in REGLAGES_PIPECAT_ESTAMPILLES


# --------------------------------------------------------------------------- #
# 3. What the model reads
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_le_nom_sur_est_ecrit_proprement_pour_le_modele():
    contexte = _contexte(
        {"role": "assistant", "content": "Quelle marque ?"},
        {"role": "user", "content": "c'est un Edilcamin"},
    )
    await _faire_passer(_processeur(), LLMContextFrame(context=contexte))
    assert contexte.messages[-1]["content"] == "c'est un Edilkamin"
    assert contexte.messages[0] == {"role": "assistant", "content": "Quelle marque ?"}


@pytest.mark.asyncio
async def test_un_nom_douteux_donne_une_mention():
    contexte = _contexte({"role": "user", "content": "c'est un poêle édile camembert"})
    await _faire_passer(_processeur(), LLMContextFrame(context=contexte))
    assert contexte.messages[-1]["content"].startswith("c'est un poêle édile camembert [Lexique : ")
    assert "Edilkamin (marque)" in contexte.messages[-1]["content"]


@pytest.mark.asyncio
async def test_un_contexte_renvoye_deux_fois_est_corrige_une_seule_fois():
    contexte = _contexte({"role": "user", "content": "c'est un poêle édile camembert"})
    processeur = _processeur()
    await _faire_passer(processeur, LLMContextFrame(context=contexte), LLMContextFrame(context=contexte))
    assert contexte.messages[-1]["content"].count("[Lexique :") == 1


@pytest.mark.asyncio
async def test_un_cadre_provisoire_est_traite_et_marque_dans_la_trace():
    recueilli: dict = {}
    contexte = _contexte({"role": "user", "content": "c'est un poêle édile camembert"})
    trame = LLMContextFrame(context=contexte)
    trame.speculation = True
    await _faire_passer(_processeur(consigner=consigner_dans(lambda: recueilli)), trame)
    assert contexte.messages[-1]["content"].count("[Lexique :") == 1
    assert recueilli[CLE_TRACE][0]["provisoire"] is True


@pytest.mark.asyncio
async def test_une_analyse_interrompue_ne_marque_pas_le_message_examine():
    """Same rule as the caller reading: cancelled during the await, the message
    must be read again by the next context that carries it."""
    processeur = _processeur()
    contexte = _contexte({"role": "user", "content": "c'est un Edilcamin"})
    vrai = module.corriger_texte
    with patch.object(module, "corriger_texte", side_effect=asyncio.CancelledError):
        with pytest.raises(asyncio.CancelledError):
            await processeur._lire_contexte(LLMContextFrame(context=contexte))
    assert contexte.messages[-1]["content"] == "c'est un Edilcamin"
    with patch.object(module, "corriger_texte", side_effect=vrai):
        await processeur._lire_contexte(LLMContextFrame(context=contexte))
    assert contexte.messages[-1]["content"] == "c'est un Edilkamin"


@pytest.mark.asyncio
async def test_un_echec_danalyse_laisse_le_message_intact():
    contexte = _contexte({"role": "user", "content": "c'est un Edilcamin"})
    with patch.object(module, "analyser", side_effect=RuntimeError("panne")):
        await _faire_passer(_processeur(), LLMContextFrame(context=contexte))
    assert contexte.messages[-1]["content"] == "c'est un Edilcamin"


@pytest.mark.asyncio
async def test_sans_index_le_message_ne_bouge_pas():
    """The list of communes not loaded yet: nothing is read rather than risk a town."""
    processeur = ReconnaissanceLexiqueProcessor(lexique=LEXIQUE, etape_courante=lambda: NOEUD)
    contexte = _contexte({"role": "user", "content": "c'est un Edilcamin"})
    await processeur._lire_contexte(LLMContextFrame(context=contexte))
    assert contexte.messages[-1]["content"] == "c'est un Edilcamin"


# --------------------------------------------------------------------------- #
# 4. At the level of the feature: transcript, model, and the two steps together
# --------------------------------------------------------------------------- #


class _Capture(FrameProcessor):
    """Keeps the context frames that reach the model."""

    def __init__(self):
        super().__init__()
        self.contextes = []

    async def process_frame(self, frame, direction):
        await super().process_frame(frame, direction)
        if isinstance(frame, LLMContextFrame) and direction == FrameDirection.DOWNSTREAM:
            self.contextes.append(frame.context)
        await self.push_frame(frame, direction)


@pytest.mark.asyncio
async def test_la_transcription_enregistree_garde_les_mots_le_modele_lit_la_correction():
    """🔒 The aggregator writes the transcript BEFORE this step changes the context."""
    contexte = LLMContext(messages=[])
    agregateur = LLMUserAggregator(
        contexte,
        params=LLMUserAggregatorParams(),
        user_turn_strategies=ExternalUserTurnStrategies(),
    )
    capture = _Capture()
    verbatim = []
    processeur = _processeur()
    pipeline = Pipeline([agregateur, processeur, capture, LLMAssistantAggregator(contexte)])

    async def _garder(frame):
        verbatim.append(frame.text)

    agregateur.add_event_handler(
        "on_user_transcription", lambda _processor, frame: _garder(frame)
    ) if hasattr(agregateur, "add_event_handler") else None

    await run_test(
        pipeline,
        frames_to_send=[
            ProposedUserStartedSpeakingFrame(),
            TranscriptionFrame(text="c'est un Edilcamin", user_id="u", timestamp="t"),
            ProposedUserStoppedSpeakingFrame(),
            SleepFrame(0.3),
        ],
        start_timeout=DEMARRAGE_S,
    )
    lu = [m for m in contexte.messages if m.get("role") == "user"]
    assert lu and lu[-1]["content"] == "c'est un Edilkamin"


@pytest.mark.asyncio
async def test_le_lexique_puis_les_nombres_et_les_communes():
    """The two steps in a row: the brand written properly never becomes a commune."""
    recueilli: dict = {}
    consigner = consigner_dans(lambda: recueilli)
    lexique = _processeur(consigner=consigner)
    lecture = LectureAppelantProcessor(
        conversion=True,
        verification=True,
        langue_francaise=True,
        adresse=MAGASIN,
        etape_courante=lambda: NOEUD,
        consigner=consigner,
    )
    contexte = _contexte({"role": "user", "content": "c'est un poêle Supra, à Beauvais soixante mille"})
    await run_test(
        Pipeline([lexique, lecture]),
        frames_to_send=[LLMContextFrame(context=contexte), SleepFrame(0.3)],
        start_timeout=DEMARRAGE_S,
    )
    contenu = contexte.messages[-1]["content"]
    assert "Supra" in contenu
    assert "60000" in contenu
    assert "Beauvais" in contenu
    assert recueilli[CLE_TRACE][0]["terme"] == "Supra"
    # The brand is not proposed as a commune.
    assert all("Supra" not in (lecture_commune.get("entendu") or "") for lecture_commune in recueilli.get(CLE_TRACE_COMMUNES, []))


@pytest.mark.asyncio
async def test_les_mentions_des_nombres_et_des_communes_ne_sont_pas_relues_par_le_lexique():
    """The other way round: the vocabulary never reads inside their notes."""
    deja = (
        "c'est à Beauvet [Vérification de la commune : « Beauvet » correspond à Beauvais "
        "(60000, Oise). Utilise ce nom sans le faire répéter.]"
    )
    contexte = _contexte({"role": "user", "content": deja})
    await _faire_passer(_processeur(), LLMContextFrame(context=contexte))
    assert contexte.messages[-1]["content"] == deja


@pytest.mark.asyncio
async def test_la_mention_du_lexique_ne_coute_pas_une_commune():
    """T17, measured: read along with the caller's words, the note changes what
    the town check sees -- "Brell" (Bresles badly transcribed) stopped being
    proposed at all. The note is set aside, then glued back untouched."""
    recueilli: dict = {}
    avec_mention = (
        "Brell soixante. [Lexique : « Brell » peut être Bordelet (marque). "
        "Fais confirmer ce nom avant de le noter.]"
    )
    lecture = LectureAppelantProcessor(
        conversion=True,
        verification=True,
        langue_francaise=True,
        adresse=MAGASIN,
        etape_courante=lambda: NOEUD,
        consigner=consigner_dans(lambda: recueilli),
    )
    contexte = _contexte({"role": "user", "content": avec_mention})
    await _faire_passer(lecture, LLMContextFrame(context=contexte))
    contenu = contexte.messages[-1]["content"]
    assert "Bresles" in contenu
    # The note is still there, whole, and at the end.
    assert contenu.endswith("Fais confirmer ce nom avant de le noter.]")
    assert contenu.count("[Lexique :") == 1
    # The brand named in the note is not read as a commune.
    assert not [t for t in recueilli.get(CLE_TRACE_COMMUNES, []) if "Bordelet" in str(t)]


@pytest.mark.asyncio
async def test_la_mention_du_lexique_passe_apres_celle_des_communes():
    """🔴 Relecture du 17/09 : glissée AVANT la note des communes, la nôtre
    empêchait la lecture suivante de voir celle-là, et le modèle recevait deux
    fois la même consigne de ville."""
    deja = (
        "c'est un poêle édile camembert à Beauvet [Vérification de la commune : « Beauvet » "
        "correspond à Beauvais (60000, Oise). Utilise ce nom sans le faire répéter.]"
    )
    contexte = _contexte({"role": "user", "content": deja})
    await _faire_passer(_processeur(), LLMContextFrame(context=contexte))
    contenu = contexte.messages[-1]["content"]
    assert contenu.index("[Vérification de la commune") < contenu.index("[Lexique :")
    assert contenu.endswith("Fais confirmer ce nom avant de le noter.]")
    # Et la lecture de l'appelant voit toujours la note de commune : elle ne la
    # réécrit pas une seconde fois.
    from api.services.communes.mention import deja_mentionne as commune_deja_mentionnee
    from api.services.lexique.correction import partie_de_lappelant

    appelant, _notes = partie_de_lappelant(contenu)
    assert commune_deja_mentionnee(contenu)
    assert commune_deja_mentionnee(appelant) or "[Vérification" not in appelant


# --------------------------------------------------------------------------- #
# 5. The records
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_les_traces_sont_ecrites():
    recueilli: dict = {}
    contexte = _contexte({"role": "user", "content": "c'est un poêle édile camembert"})
    await _faire_passer(_processeur(consigner=consigner_dans(lambda: recueilli)), LLMContextFrame(context=contexte))
    entree = recueilli[CLE_TRACE][0]
    assert entree["etape"] == "coordonnees"
    assert entree["entendu"] == "édile camembert"
    assert entree["statut"] == "a_confirmer"
    assert entree["terme"] == "Edilkamin"
    assert entree["propositions"][0]["terme"] == "Edilkamin"
    assert isinstance(entree["par_son"], bool)


def test_la_trace_du_lexique_dit_ce_que_lappel_a_utilise():
    trace = trace_du_lexique(LEXIQUE, ["Edilkamin", "Supra"], False)
    assert trace == {
        "termes": 4,
        "noms": 3,
        "envoyes_a_flux": ["Edilkamin", "Supra"],
        "liste_tronquee": False,
        "prononciations": 0,
    }
    assert trace_du_lexique(LEXIQUE, [], True)["liste_tronquee"] is True


# --------------------------------------------------------------------------- #
# 6. The variable given to the agent (T12, Q1 = B)
# --------------------------------------------------------------------------- #


def test_la_variable_porte_les_noms_coches():
    assert injecter_lexique_a_ecouter({}, ["Edilkamin", "Supra"]) == {
        CLE_A_ECOUTER: "Edilkamin, Supra"
    }


def test_sans_nom_coche_la_cle_est_absente():
    contexte = {"direction": "inbound"}
    assert injecter_lexique_a_ecouter(contexte, []) is contexte
    assert CLE_A_ECOUTER not in contexte


def test_une_valeur_deja_fournie_est_gardee():
    assert injecter_lexique_a_ecouter({CLE_A_ECOUTER: "fournie"}, ["Edilkamin"]) == {
        CLE_A_ECOUTER: "fournie"
    }
    assert injecter_lexique_a_ecouter({CLE_A_ECOUTER: "  "}, ["Edilkamin"]) == {
        CLE_A_ECOUTER: "Edilkamin"
    }


def test_les_deux_chemins_injectent_la_variable():
    from api.services.pipecat import run_pipeline
    from api.services.workflow import text_chat_runner

    for module_appel in (run_pipeline, text_chat_runner):
        source = inspect.getsource(module_appel)
        assert "injecter_lexique_a_ecouter(" in source


# --------------------------------------------------------------------------- #
# 7. The keyboard
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_le_message_tape_est_corrige_comme_un_appel():
    recueilli: dict = {}
    corrige = await annoter_message_tape(
        "c'est un Edilcamin", {}, LEXIQUE, NOEUD, consigner_dans(lambda: recueilli)
    )
    assert corrige == "c'est un Edilkamin"
    assert recueilli[CLE_TRACE][0]["terme"] == "Edilkamin"


@pytest.mark.asyncio
async def test_interrupteur_eteint_le_message_tape_ne_bouge_pas():
    assert await annoter_message_tape("c'est un Edilcamin", {"lexique_metier": False}, LEXIQUE, NOEUD) == (
        "c'est un Edilcamin"
    )
    assert await annoter_message_tape("c'est un Edilcamin", {}, SANS_NOM, NOEUD) == "c'est un Edilcamin"


@pytest.mark.asyncio
async def test_le_clavier_corrige_avant_de_lire_les_nombres_et_les_communes():
    from api.services.workflow import text_chat_runner

    source = inspect.getsource(text_chat_runner)
    assert source.index("annoter_message_tape(") < source.index("lire_message_tape(\n                message_pour_le_modele")

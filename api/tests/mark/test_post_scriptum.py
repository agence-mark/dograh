"""[.mark] Le processeur du post-scriptum (plan mode-prise-de-notes, lot 4).

Plan `Labo-agent-vocal/plans/mode-prise-de-notes/`, D4 à D7. Chaque test a été vu ROUGE avant
d'être vert (R7) : un processeur de flux qui passe ses tests sans les avoir vus échouer peut
être vert et inopérant (le filtre du nom l'a appris le 22/09).

| Test | Ce qu'il prouve |
|---|---|
| séparateur | entier, coupé en deux, en trois morceaux : la phrase part à la voix, la note jamais |
| sans séparateur | D7 : tout part à la voix, rien n'est noté, la trace dit « absent » |
| JSON sans séparateur | D7 : la ligne de JSON n'est jamais envoyée à la voix |
| `{}`, clôtures, illisible | rien à noter / note lue malgré ``` / rien noté, trace « illisible », jamais d'exception |
| guillemets | « » qui encadrent toute la phrase sont retirés (runs 889 et 893) |
| interruption | avant et après le séparateur : rien ne reste en tampon, aucune note du tour coupé |
| phrase figée, ne pas dire | `TTSSpeakFrame` et `skip_tts` passent intacts, même au milieu d'une note |
| porte | une réponse qui ne parle pas ne laisse ni trace ni note (D5) |
| filtre du nom | combiné au filtre allumé : le nom part, la note n'arrive jamais au filtre |
| vrais modules | la note passe par `noter` : commune vérifiée par le module, notices au tour suivant |
| mémoire | la correction de la mémoire par le texte de référence n'y fait jamais entrer la note |
| montage | le processeur se place juste avant le filtre du nom ; hors mode post-scriptum, rien |
"""

import asyncio

import pytest
from pipecat.frames.frames import (
    Frame,
    InterruptionFrame,
    LLMFullResponseEndFrame,
    LLMFullResponseStartFrame,
    LLMTextFrame,
    TTSSpeakFrame,
)
from pipecat.pipeline.pipeline import Pipeline
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor
from pipecat.tests.utils import SleepFrame

from api.services.pipecat.filtre_nom_civilite import FiltreNomCiviliteProcessor
from api.services.pipecat.pipeline_builder import build_agent_generation_pipeline
from api.services.pipecat.post_scriptum import (
    ABSENT,
    ILLISIBLE,
    PRESENT,
    TRACE_POST_SCRIPTUM,
    VIDE,
    PostScriptumProcessor,
    attendre_les_notes,
    creer_post_scriptum,
    lire_la_note,
)
from api.services.workflow.fiche_au_fil_de_leau import (
    CLE_JOURNAL,
    CLE_MODE,
    MODE_OUTIL,
    MODE_POST_SCRIPTUM,
    Notices,
    ReglagesFiche,
)
from api.services.workflow.pipecat_engine_callbacks import (
    create_aggregation_correction_callback,
)
from api.tests.mark.test_modules_derriere_outil import (  # noqa: F401 -- fixture
    REGLAGES,
    _appel,
    index_de_test,
)
from pipecat.tests import run_test

DEMARRAGE_S = 15
FICHE_SIMPLE = {
    "fiche_au_fil_de_leau": True,
    CLE_MODE: MODE_POST_SCRIPTUM,
    "fiche_champs": [
        {"nom": "nom", "origine": "dicte", "description": "Nom de famille"},
        {
            "nom": "motif",
            "origine": "dicte",
            "description": "Ce que la personne demande",
        },
    ],
}
PAROLE = "Bonjour, je suis monsieur Dupont, c'est pour un entretien."


class _Aval(FrameProcessor):
    """Ce que la voix recevrait (et donc ce dont la mémoire du modèle sera faite)."""

    def __init__(self):
        super().__init__()
        self.textes: list[str] = []
        self.figees: list[str] = []
        self.ne_pas_dire: list[str] = []

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)
        if isinstance(frame, TTSSpeakFrame):
            self.figees.append(frame.text)
        elif isinstance(frame, LLMTextFrame):
            (self.ne_pas_dire if frame.skip_tts else self.textes).append(frame.text)
        await self.push_frame(frame, direction)


class _Montage:
    """Un processeur et tout ce qu'il touche : fiche, conversation, notices."""

    def __init__(
        self, config: dict = FICHE_SIMPLE, fiche: dict | None = None, attendu=True
    ):
        self.reglages = ReglagesFiche.depuis(config)
        self.fiche: dict = fiche if fiche is not None else {}
        self.messages = [{"role": "user", "content": PAROLE}]
        self.notices = Notices()
        self.notes: set[asyncio.Task] = set()
        self.processeur = creer_post_scriptum(
            self.reglages,
            lambda: self.fiche,
            lambda: self.messages,
            self.notices,
            attendu=lambda: attendu,
            notes_en_cours=self.notes,
        )

    async def jouer(self, *frames: Frame, avant: list[FrameProcessor] = ()) -> _Aval:
        aval = _Aval()
        await run_test(
            Pipeline([*avant, self.processeur, aval]),
            frames_to_send=[*frames, SleepFrame(sleep=0.3)],
            start_timeout=DEMARRAGE_S,
        )
        await attendre_les_notes(self.notes)
        return aval

    async def reponse(self, *morceaux: str) -> _Aval:
        return await self.jouer(
            LLMFullResponseStartFrame(),
            *[LLMTextFrame(m) for m in morceaux],
            LLMFullResponseEndFrame(),
        )

    @property
    def traces(self) -> list[dict]:
        return self.fiche.get(TRACE_POST_SCRIPTUM) or []


# --------------------------------------------------------------------------- #
# 1. Le séparateur, entier ou coupé
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "morceaux",
    [
        ["Très bien, et votre numéro ?", "\n|||\n", '{"nom": "Dupont"}'],
        ["Très bien, et votre numéro ?\n|", "||\n", '{"nom": "Dupont"}'],
        ["Très bien, et votre numéro ?\n|", "|", "|", '\n{"nom": ', '"Dupont"}'],
        ["Très bien, et votre numéro ?|||", '{"nom": "Dupont"}'],
    ],
    ids=["entier", "coupe-en-deux", "coupe-en-trois", "colle-a-la-phrase"],
)
async def test_la_phrase_part_a_la_voix_la_note_jamais(morceaux):
    montage = _Montage()
    aval = await montage.reponse(*morceaux)
    dit = "".join(aval.textes)
    assert dit == "Très bien, et votre numéro ?"
    assert "|" not in dit and "{" not in dit
    assert montage.fiche.get("nom") == "Dupont"
    assert montage.traces == [{"tour": None, "etat": PRESENT, "champs": ["nom"]}]
    journal = [
        e for e in montage.fiche.get(CLE_JOURNAL) or [] if e.get("champ") == "nom"
    ]
    assert journal and journal[-1]["source"] == MODE_POST_SCRIPTUM


@pytest.mark.asyncio
async def test_la_phrase_n_est_pas_retenue_avant_le_separateur():
    """La voix ne doit pas attendre la note : chaque morceau sûr part aussitôt."""
    montage = _Montage()
    aval = await montage.reponse("Très", " bien,", " et votre", " numéro ?", "\n|||{}")
    assert aval.textes[:3] == ["Très", " bien,", " et votre"]


@pytest.mark.asyncio
async def test_un_tuyau_seul_dans_la_phrase_est_rendu():
    montage = _Montage()
    aval = await montage.reponse("Choix A |", " B, lequel ?", "\n|||\n{}")
    assert "".join(aval.textes) == "Choix A | B, lequel ?"


# --------------------------------------------------------------------------- #
# 2. D7 : sans séparateur
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_D7_sans_separateur_tout_part_a_la_voix_rien_n_est_note():
    montage = _Montage()
    aval = await montage.reponse("Très bien,", " et votre numéro ?")
    assert "".join(aval.textes) == "Très bien, et votre numéro ?"
    assert "nom" not in montage.fiche
    assert montage.traces == [{"tour": None, "etat": ABSENT, "champs": []}]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "morceaux",
    [
        ["Très bien, et votre numéro ?", "\n", '{"nom": "Dupont"}'],
        ["Très bien, et votre numéro ?\n```json\n", '{"nom": "Dupont"}\n```'],
        ['{"nom": "Dupont"}'],
    ],
    ids=["ligne-json", "bloc-de-code", "json-seul"],
)
async def test_D7_une_ligne_de_json_sans_separateur_n_est_jamais_dite(morceaux):
    montage = _Montage()
    aval = await montage.reponse(*morceaux)
    dit = "".join(aval.textes)
    assert "{" not in dit and "Dupont" not in dit and "`" not in dit
    assert "nom" not in montage.fiche
    assert montage.traces[-1]["etat"] == ABSENT


# --------------------------------------------------------------------------- #
# 3. La note : vide, clôturée, illisible
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "brut, attendu",
    [
        ("{}", {}),
        ("", {}),
        ('\n```json\n{"nom": "Dupont"}\n```', {"nom": "Dupont"}),
        ('Note : {"nom": "Dupont"} voilà', {"nom": "Dupont"}),
        ("pas du json", None),
        ('["Dupont"]', None),
        ('{"nom": ', None),
    ],
)
def test_lire_la_note(brut, attendu):
    assert lire_la_note(brut) == attendu


@pytest.mark.asyncio
async def test_une_note_vide_ne_note_rien_et_efface_les_notices():
    montage = _Montage()
    montage.notices.derniere = {"consigne": "ancienne"}
    await montage.reponse("D'accord.", "\n|||\n{}")
    assert montage.traces == [{"tour": None, "etat": VIDE, "champs": []}]
    assert montage.notices.derniere is None


@pytest.mark.asyncio
async def test_une_note_illisible_ne_coute_pas_l_appel():
    montage = _Montage()
    aval = await montage.reponse("D'accord.", "\n|||\n{nom: Dupont")
    assert "".join(aval.textes) == "D'accord."
    assert "nom" not in montage.fiche
    assert montage.traces == [{"tour": None, "etat": ILLISIBLE, "champs": []}]


# --------------------------------------------------------------------------- #
# 4. Guillemets, interruptions, phrases figées, portes
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "morceaux",
    [
        ["« Très bien, et votre numéro ? »", "\n|||\n{}"],
        ["«", " Très bien, et votre numéro ?", " »", "\n|||\n{}"],
        ["« Très bien, et votre numéro ? »"],
    ],
    ids=["en-un-morceau", "en-morceaux", "sans-separateur"],
)
async def test_les_guillemets_qui_encadrent_la_phrase_sont_retires(morceaux):
    montage = _Montage()
    aval = await montage.reponse(*morceaux)
    assert "".join(aval.textes) == "Très bien, et votre numéro ?"


@pytest.mark.asyncio
async def test_des_guillemets_dans_la_phrase_restent():
    montage = _Montage()
    aval = await montage.reponse(
        "Vous avez dit « Creil », c'est bien ça ?", "\n|||\n{}"
    )
    assert "".join(aval.textes) == "Vous avez dit « Creil », c'est bien ça ?"


@pytest.mark.asyncio
async def test_une_interruption_avant_le_separateur_ne_soude_pas_deux_tours():
    montage = _Montage()
    aval = await montage.jouer(
        LLMFullResponseStartFrame(),
        LLMTextFrame("Très bien\n|"),
        InterruptionFrame(),
        LLMFullResponseStartFrame(),
        LLMTextFrame("Oui ?"),
        LLMTextFrame("\n|||\n{}"),
        LLMFullResponseEndFrame(),
    )
    assert "".join(aval.textes) == "Très bienOui ?"
    assert "|" not in "".join(aval.textes)


@pytest.mark.asyncio
async def test_une_interruption_apres_le_separateur_ne_note_rien():
    montage = _Montage()
    aval = await montage.jouer(
        LLMFullResponseStartFrame(),
        LLMTextFrame("Très bien.\n|||\n"),
        LLMTextFrame('{"nom": "Dup'),
        InterruptionFrame(),
        LLMFullResponseStartFrame(),
        LLMTextFrame("Oui ?\n|||\n{}"),
        LLMFullResponseEndFrame(),
    )
    assert "".join(aval.textes) == "Très bien.Oui ?"
    assert "nom" not in montage.fiche
    assert [t["etat"] for t in montage.traces] == [VIDE]


@pytest.mark.asyncio
async def test_phrase_figee_et_ne_pas_dire_passent_intacts_meme_dans_une_note():
    montage = _Montage()
    marqueur = LLMTextFrame("● rec_1 [transcription]")
    marqueur.skip_tts = True
    aval = await montage.jouer(
        TTSSpeakFrame("Je vous mets en relation."),
        LLMFullResponseStartFrame(),
        LLMTextFrame("D'accord.\n|||\n"),
        TTSSpeakFrame("Un instant."),
        marqueur,
        LLMTextFrame('{"nom": "Dupont"}'),
        LLMFullResponseEndFrame(),
    )
    assert aval.figees == ["Je vous mets en relation.", "Un instant."]
    assert aval.ne_pas_dire == ["● rec_1 [transcription]"]
    assert "".join(aval.textes) == "D'accord."
    assert montage.fiche.get("nom") == "Dupont"


@pytest.mark.asyncio
async def test_D5_une_reponse_qui_ne_parle_pas_ne_laisse_rien():
    montage = _Montage()
    montage.notices.derniere = {"consigne": "toujours valable"}
    await montage.jouer(LLMFullResponseStartFrame(), LLMFullResponseEndFrame())
    assert montage.traces == []
    assert montage.notices.derniere == {"consigne": "toujours valable"}


@pytest.mark.asyncio
async def test_une_etape_de_fin_sans_separateur_n_est_pas_un_oubli():
    montage = _Montage(attendu=False)
    await montage.reponse("Au revoir et bonne journée.")
    assert montage.traces == []


# --------------------------------------------------------------------------- #
# 5. Avec le filtre du nom, et par les vrais modules
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_combine_au_filtre_du_nom_la_note_n_arrive_jamais_au_filtre():
    montage = _Montage(fiche={"nom": "Dupont"})
    filtre = FiltreNomCiviliteProcessor(
        retirer_nom=True, retirer_civilite=True, variables=lambda: montage.fiche
    )
    aval = _Aval()
    await run_test(
        Pipeline([montage.processeur, filtre, aval]),
        frames_to_send=[
            LLMFullResponseStartFrame(),
            LLMTextFrame("C'est noté, monsieur"),
            LLMTextFrame(" Dupont."),
            LLMTextFrame(" Et votre numéro ?\n||"),
            LLMTextFrame('|\n{"motif": "entretien"}'),
            LLMFullResponseEndFrame(),
            SleepFrame(sleep=0.3),
        ],
        start_timeout=DEMARRAGE_S,
    )
    await attendre_les_notes(montage.notes)
    dit = "".join(aval.textes)
    assert dit.strip() == "C'est noté. Et votre numéro ?"
    assert "motif" not in dit and "|" not in dit
    assert montage.fiche.get("motif") == "entretien"


@pytest.mark.asyncio
async def test_la_note_passe_par_les_vrais_modules_et_ses_notices_suivent():
    """« creil » noté : le module des communes, qui a lu « creil 60100 » dans la
    phrase, l'écrit sous son nom officiel ; la consigne de l'outil part au tour suivant."""
    fiche, _ = await _appel("c'est à creil 60100")
    montage = _Montage({**REGLAGES, CLE_MODE: MODE_POST_SCRIPTUM}, fiche=fiche)
    montage.messages = [{"role": "user", "content": "c'est à creil 60100"}]
    await montage.reponse("Merci, et la rue ?", '\n|||\n{"commune": "creil"}')
    assert montage.fiche["commune"] == "Creil"
    assert montage.fiche["commune_insee"] == "60175"
    assert montage.fiche["fiche_etat"]["commune"] == {
        "sure": True,
        "source": MODE_POST_SCRIPTUM,
    }
    assert montage.notices.derniere == {"statut": "note", "ecrits": ["commune"]}
    # Une valeur jamais dite : refusée, et la consigne de l'outil part au tour suivant.
    await montage.reponse("Et votre nom ?", '\n|||\n{"nom": "Martin"}')
    assert "nom" not in montage.fiche
    assert montage.notices.derniere["refuses"] == [
        {"champ": "nom", "raison": "non_dit"}
    ]
    assert "consigne" in montage.notices.derniere


# --------------------------------------------------------------------------- #
# 6. La mémoire du modèle
# --------------------------------------------------------------------------- #


def test_la_correction_de_la_memoire_ne_fait_jamais_entrer_la_note():
    """Le moteur garde le texte du modèle AVANT le processeur (note comprise) et
    s'en sert pour corriger la phrase que l'agrégateur met en mémoire. Elle ne
    doit jamais y remettre la note."""
    moteur = type("M", (), {})()
    corriger = create_aggregation_correction_callback(moteur)
    phrase = "Très bien, et votre numéro de téléphone ?"
    for reference in (
        f'{phrase}\n|||\n{{"nom": "Dupont", "motif": "entretien"}}',
        f'{phrase}|||{{"nom": "Dupont"}}',
    ):
        moteur._current_llm_generation_reference_text = reference
        for dite in (phrase, "Très bien et votre numéro de téléphone"):
            corrigee = corriger(dite)
            assert (
                "Dupont" not in corrigee and "|" not in corrigee and "{" not in corrigee
            )


# --------------------------------------------------------------------------- #
# 7. Le montage
# --------------------------------------------------------------------------- #


def test_hors_mode_post_scriptum_pas_de_processeur():
    outil = ReglagesFiche.depuis({**FICHE_SIMPLE, CLE_MODE: MODE_OUTIL})
    assert creer_post_scriptum(outil, dict, list, None) is None
    assert creer_post_scriptum(None, dict, list, None) is None
    assert isinstance(_Montage().processeur, PostScriptumProcessor)


def test_le_processeur_se_place_juste_avant_le_filtre_du_nom():
    composants = {
        "llm": FrameProcessor(),
        "tts": FrameProcessor(),
        "generation_callback_processor": FrameProcessor(),
        "recording_router": FrameProcessor(),
    }
    filtre = FrameProcessor()
    post_scriptum = _Montage().processeur
    pipeline = build_agent_generation_pipeline(
        **composants, filtre_nom_civilite=filtre, post_scriptum=post_scriptum
    )
    ordre = list(pipeline.processors)[1:-1]
    assert ordre[-4:] == [
        composants["recording_router"],
        post_scriptum,
        filtre,
        composants["tts"],
    ]
    sans = build_agent_generation_pipeline(**composants)
    assert post_scriptum not in list(sans.processors)


def test_le_chemin_telephonique_construit_le_post_scriptum():
    """``run_pipeline`` ne se monte pas en test : le branchement est lu au source
    (patron de ``test_filtre_nom_civilite_branchement``), le reste est joué ci-dessus."""
    import inspect

    from api.services.pipecat import agent_runtime_factory, run_pipeline

    assert "agent.post_scriptum = creer_post_scriptum(" in inspect.getsource(
        run_pipeline
    )
    assert "post_scriptum=runtime.post_scriptum" in inspect.getsource(
        agent_runtime_factory
    )

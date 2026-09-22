"""[.mark] Le filtre du nom est-il BRANCHÉ, et au bon endroit ?

Le fichier voisin (`test_filtre_nom_civilite.py`) prouve que la fonction
retire ce qu'il faut. Celui-ci répond aux deux questions que la fonction ne
peut pas se poser à elle-même :

    ① le processeur voit-il une PHRASE, là où le modèle envoie des morceaux ?
    ② ce qu'il retire reste-t-il retiré dans la MÉMOIRE DU MODÈLE ?

Pourquoi ② décide de tout
-------------------------
Si le texte filtré n'entre pas dans la mémoire du modèle, l'agent croit avoir
dit le nom et son tour suivant part de faux. C'est le seul résultat qui peut
rouvrir la décision du 22/09 sur l'emplacement du module, et il doit être
obtenu **par un test qui joue la chaîne**, jamais par la lecture du code : le
21/09, une lecture de code avait conclu l'inverse de ce que la sonde a montré.
"""

from types import SimpleNamespace

import pytest
from pipecat.frames.frames import (
    Frame,
    LLMFullResponseEndFrame,
    LLMFullResponseStartFrame,
    LLMTextFrame,
)
from pipecat.pipeline.pipeline import Pipeline
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor
from pipecat.tests.utils import SleepFrame

from api.services.pipecat.filtre_nom_civilite import (
    FiltreNomCiviliteProcessor,
    creer_filtre_nom_civilite,
)
from api.services.pipecat.pipeline_builder import build_pipeline
from pipecat.tests import run_test

DEMARRAGE_S = 15

# Ce que le modèle pousse réellement pour « D'accord, c'est noté, monsieur
# Dupont. Je transmets. » -- mesuré par sonde le 22/09 : un morceau par delta
# de flux, avec le nom coupé en deux.
MORCEAUX = [
    "D'accord",
    ", c'est",
    " noté,",
    " monsieur",
    " Dupont",
    ".",
    " Je",
    " transmets",
    ".",
]


class _Aval(FrameProcessor):
    """Ce que la voix recevrait, et donc ce que la mémoire du modèle verra."""

    def __init__(self):
        super().__init__()
        self.textes: list[str] = []

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)
        if isinstance(frame, LLMTextFrame):
            self.textes.append(frame.text)
        await self.push_frame(frame, direction)


def _filtre(nom="Dupont", mode="sentence", **interrupteurs):
    return FiltreNomCiviliteProcessor(
        retirer_nom=interrupteurs.get("retirer_nom", True),
        retirer_civilite=interrupteurs.get("retirer_civilite", True),
        variables=lambda: {"nom": nom} if nom else {},
        mode_envoi=mode,
    )


async def _jouer(processeur, morceaux=MORCEAUX):
    aval = _Aval()
    await run_test(
        Pipeline([processeur, aval]),
        frames_to_send=[
            LLMFullResponseStartFrame(),
            *[LLMTextFrame(morceau) for morceau in morceaux],
            LLMFullResponseEndFrame(),
            SleepFrame(sleep=0.3),
        ],
        start_timeout=DEMARRAGE_S,
    )
    return "".join(aval.textes)


# ─── ① Le processeur voit une phrase, pas des morceaux ───────────────────────


@pytest.mark.asyncio
async def test_le_nom_coupe_en_DEUX_morceaux_est_quand_meme_retire():
    """🔴 Le piège qui a fait changer d'emplacement le 22/09.

    Le modèle envoie ``, monsieur`` et `` Dupont`` dans deux frames séparées.
    Un filtre qui regarde chaque frame isolément ne verrait jamais le nom et
    resterait vert en test tout en étant inopérant en production.
    """
    sortie = await _jouer(_filtre())

    assert "Dupont" not in sortie
    assert "monsieur" not in sortie.lower()
    assert sortie.strip() == "D'accord, c'est noté. Je transmets."


@pytest.mark.asyncio
async def test_rien_ne_reste_coince_en_tampon_a_la_fin_de_la_reponse():
    """Une réponse qui ne finit pas par un point doit quand même être dite."""
    sortie = await _jouer(_filtre(), ["Très bien", " monsieur", " Dupont"])

    assert sortie.strip() == "Très bien"


@pytest.mark.asyncio
async def test_une_phrase_sans_nom_traverse_INCHANGEE():
    """Zéro perte, au niveau de la chaîne cette fois : la phrase ressort
    identique, y compris son découpage."""
    morceaux = ["Est-ce", " que le poêle", " est allumé ?"]

    sortie = await _jouer(_filtre(), morceaux)

    assert sortie == "".join(morceaux)


@pytest.mark.asyncio
async def test_en_mode_mot_a_mot_le_filtre_est_INERTE():
    """⛔ Décision du 22/09 : un agent qui hache ses phrases est pire qu'un
    agent qui prononce un nom. En envoi mot à mot, chaque morceau passe tel
    quel -- et le journal le dit au montage."""
    sortie = await _jouer(_filtre(mode="token"))

    assert sortie == "".join(MORCEAUX)
    assert "Dupont" in sortie


@pytest.mark.asyncio
async def test_sans_nom_extrait_seule_la_civilite_part():
    """Le filtre ne connaît le nom qu'une fois extrait : avant, il n'a rien à
    retirer de ce côté. Limite écrite dans la notice de l'écran."""
    sortie = await _jouer(_filtre(nom=None))

    assert "monsieur" not in sortie.lower()
    assert "Dupont" in sortie


# ─── ② La mémoire du modèle ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_ce_qui_est_retire_ne_revient_PAS_dans_la_memoire_du_modele():
    """🔴 L'étape 2.4 du plan, et la seule preuve qui pouvait rouvrir le choix
    d'emplacement.

    La mémoire du modèle se construit à partir de ce qui descend vers la voix.
    Le filtre étant AVANT elle, le texte qui la nourrit est déjà filtré : le
    tour suivant de l'agent ne part pas de l'idée qu'il a dit un nom qu'il n'a
    pas dit.
    """
    aval = _Aval()
    await run_test(
        Pipeline([_filtre(), aval]),
        frames_to_send=[
            LLMFullResponseStartFrame(),
            *[LLMTextFrame(morceau) for morceau in MORCEAUX],
            LLMFullResponseEndFrame(),
            SleepFrame(sleep=0.3),
        ],
        start_timeout=DEMARRAGE_S,
    )

    # Tout ce qui a franchi le filtre -- donc tout ce dont la mémoire du modèle
    # peut être faite -- est exempt du nom et de la civilité.
    assert all("Dupont" not in texte for texte in aval.textes)
    assert all("monsieur" not in texte.lower() for texte in aval.textes)


# ─── Le montage du pipeline ──────────────────────────────────────────────────


def _composants():
    transport = SimpleNamespace(
        input=lambda: FrameProcessor(), output=lambda: FrameProcessor()
    )
    return {
        "transport": transport,
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


def test_le_filtre_se_place_JUSTE_avant_la_voix():
    composants = _composants()
    etape = _filtre()

    processeurs = build_pipeline(**composants, filtre_nom_civilite=etape).processors

    assert processeurs[processeurs.index(etape) + 1] is composants["tts"], (
        "le filtre n'est plus immédiatement avant la voix : un processeur "
        "inséré entre les deux pourrait redire le nom."
    )


def test_sans_filtre_le_pipeline_est_celui_daujourdhui():
    """Les deux interrupteurs éteints -- le défaut, et le cas de tous les
    agents existants -- ne doivent RIEN changer à la chaîne."""
    composants = _composants()

    sans = build_pipeline(**composants).processors
    avec_none = build_pipeline(**composants, filtre_nom_civilite=None).processors

    assert [type(p) for p in sans] == [type(p) for p in avec_none]


def test_les_deux_interrupteurs_sont_ETEINTS_par_defaut():
    """⛔ On les allume à la construction d'un agent client, jamais avant."""
    from api.schemas.workflow_configurations import WorkflowConfigurationDefaults

    defauts = WorkflowConfigurationDefaults()

    assert defauts.interdire_nom_appelant is False
    assert defauts.interdire_civilite_appelant is False
    assert creer_filtre_nom_civilite({}, dict) is None
    assert creer_filtre_nom_civilite(None, dict) is None


def test_chaque_interrupteur_construit_le_filtre_a_lui_seul():
    assert creer_filtre_nom_civilite({"interdire_nom_appelant": True}, dict) is not None
    assert (
        creer_filtre_nom_civilite({"interdire_civilite_appelant": True}, dict)
        is not None
    )


def test_le_chemin_telephonique_construit_bien_le_filtre():
    """⛔ Un module que personne ne branche n'existe pas (leçon du 11/09).

    ⚠️ Lu honnêtement : ceci lit la source du runner plutôt que de l'exécuter,
    parce que l'exécuter demande toute la pile. Ça attrape la panne qui nous
    menace vraiment -- l'appel retiré par un remaniement.
    """
    import inspect

    from api.services.pipecat import run_pipeline

    source = inspect.getsource(run_pipeline)

    assert "filtre_nom_civilite=creer_filtre_nom_civilite(" in source, (
        "run_pipeline ne construit plus le filtre : les deux interrupteurs "
        "seraient à l'écran et sans effet, ce qui est pire que leur absence."
    )
    assert "extracted_variables" in source, (
        "le filtre ne reçoit plus les variables extraites : il ne connaîtrait "
        "jamais le nom de l'appelant."
    )

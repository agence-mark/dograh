"""[.mark] SA-35 (M77, M81) : ce que l'agent DIT après un geste d'outil n'est plus abîmé.

Constats (production, « Tester au clavier », workflow 299 -> agent 300) :

- M81, appel 2569, tour 9 : la personne dicte son numéro, ``finaliser`` le reçoit ; la réplique est retenue par la garde des chiffres
  (journal : « réplique retenue (chiffre_sans_source) : réponse rendue par la relance ») ; la relance, SANS flux, rend tout son texte en
  UN morceau (``reponse_avalee.en_morceaux``). L'agent dit « C'est bien cela ?C'est bien cela ? » : la relecture du numéro a disparu et la
  dernière phrase est doublée. Même motif sur 2568 (tour 15) et 2569 (tour 12) : « Puis-je faire autre chose pour vous ? » deux fois.
  Cause : ``FiltreNomCiviliteProcessor._emettre`` réutilise la frame d'origine pour chaque phrase ; quand un morceau porte DEUX phrases,
  la même frame est poussée deux fois et son texte réécrit entre les deux poussées, avant que l'aval ne la lise.
- M77, appel 2568, tour 9 : « C'est noté pour Julien. » rendu « C'est noté pour. » : le filtre retirait le prénom et laissait sa
  préposition orpheline.

| Test | Ce qu'il prouve |
|---|---|
| doublon | un morceau à deux phrases (la relance) : chaque phrase dite une fois, dans l'ordre, la relecture du numéro intacte |
| trois phrases | même chose sur trois phrases dans un morceau |
| drapeaux | la phrase suivante garde les drapeaux de la frame d'origine (``skip_tts`` de côté, ``append_to_context``) |
| prénom | « C'est noté pour Julien. Quel est votre numéro ? » avec ``prenom: Julien`` donne une phrase correcte |
| numéro | une relecture de numéro avec ``telephone`` en argument d'outil reste intacte |
"""

import pytest
from pipecat.frames.frames import (
    LLMFullResponseEndFrame,
    LLMFullResponseStartFrame,
    LLMTextFrame,
)
from pipecat.pipeline.pipeline import Pipeline
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor
from pipecat.tests import run_test
from pipecat.tests.utils import SleepFrame

from api.services.pipecat.filtre_nom_civilite import FiltreNomCiviliteProcessor, retirer_nom_et_civilite
from api.services.workflow.fiche_au_fil_de_leau import CLE_TOUR
from api.tests.mark.test_filtre_nom_civilite_branchement import DEMARRAGE_S


class _AvalQuiGardeLesFrames(FrameProcessor):
    """Garde les FRAMES reçues (pas leur texte) : le texte est lu à la fin, comme un aval qui consomme plus tard."""

    def __init__(self):
        super().__init__()
        self.frames: list[LLMTextFrame] = []

    async def process_frame(self, frame, direction: FrameDirection):
        await super().process_frame(frame, direction)
        if isinstance(frame, LLMTextFrame):
            self.frames.append(frame)
        await self.push_frame(frame, direction)


def _filtre(contexte: dict | None = None):
    return FiltreNomCiviliteProcessor(
        retirer_nom=True,
        retirer_civilite=False,
        variables=lambda: {},
        contexte=lambda: contexte or {},
        mode_envoi="sentence",
    )


def _contexte(arguments: dict) -> dict:
    return {
        CLE_TOUR: 9,
        "tool_results": [{"function_name": "finaliser", "arguments": arguments, "status": "completed", "result": {}, "tour": 9}],
    }


async def _jouer(processeur, frames):
    aval = _AvalQuiGardeLesFrames()
    await run_test(
        Pipeline([processeur, aval]),
        frames_to_send=[LLMFullResponseStartFrame(), *frames, LLMFullResponseEndFrame(), SleepFrame(sleep=0.3)],
        start_timeout=DEMARRAGE_S,
    )
    return aval.frames


RELECTURE = "Je relis : zéro six, dix, vingt, trente, quarante. C'est bien cela ?"
ARGUMENTS_2569 = {"articles": [], "en_plus": False, "prenom": "Claire", "telephone": "0610203040"}


@pytest.mark.asyncio
async def test_un_morceau_a_deux_phrases_est_dit_une_fois_dans_l_ordre():
    # M81 (appel 2569) : la relance rend la réplique entière en un seul morceau.
    frames = await _jouer(_filtre(_contexte(ARGUMENTS_2569)), [LLMTextFrame(RELECTURE)])
    textes = [f.text for f in frames]
    assert "".join(textes) == RELECTURE, textes
    assert "".join(textes).count("C'est bien cela ?") == 1
    assert len({id(f) for f in frames}) == len(frames), "la même frame est poussée deux fois"


@pytest.mark.asyncio
async def test_trois_phrases_dans_un_morceau_aucune_n_est_redite():
    # M81 (appels 2568 et 2569) : « Puis-je faire autre chose pour vous ? » deux fois.
    texte = "C'est noté. Je relance la commande. Puis-je faire autre chose pour vous ?"
    frames = await _jouer(_filtre(), [LLMTextFrame(texte)])
    assert "".join(f.text for f in frames) == texte
    assert "".join(f.text for f in frames).count("Puis-je faire autre chose pour vous ?") == 1


@pytest.mark.asyncio
async def test_la_phrase_suivante_garde_les_drapeaux_de_la_frame_d_origine():
    origine = LLMTextFrame("Première phrase. Seconde phrase.")
    origine.append_to_context = False
    frames = await _jouer(_filtre(), [origine])
    assert [f.text for f in frames] == ["Première phrase. ", "Seconde phrase."]
    assert all(f.append_to_context is False for f in frames)
    assert all(f.includes_inter_frame_spaces is True for f in frames)


@pytest.mark.asyncio
async def test_le_prenom_donne_a_l_outil_part_sans_laisser_de_phrase_cassee():
    # M77 (appel 2568) : « C'est noté pour. Quel est votre numéro de téléphone ? »
    frames = await _jouer(
        _filtre(_contexte({"prenom": "Julien"})),
        [LLMTextFrame("C'est noté pour Julien. Quel est votre numéro ?")],
    )
    assert "".join(f.text for f in frames) == "C'est noté. Quel est votre numéro ?"


@pytest.mark.parametrize(
    "texte, nom, attendu",
    [
        ("C'est noté pour Julien.", "Julien", "C'est noté."),
        ("C'est noté pour Julien, à quelle heure ?", "Julien", "C'est noté, à quelle heure ?"),
        ("Je mets la commande au nom de Julien.", "Julien", "Je mets la commande."),
        ("Une pizza pour Julien et une pour Claire.", "Julien", "Une pizza et une pour Claire."),
        ("Merci Julien, quel est votre numéro ?", "Julien", "Merci, quel est votre numéro ?"),
        ("Je livre au 8 rue Julien à Chantilly.", "Julien", "Je livre au 8 rue Julien à Chantilly."),
    ],
)
def test_la_preposition_part_avec_le_nom(texte, nom, attendu):
    assert retirer_nom_et_civilite(texte, nom, retirer_nom=True) == attendu


@pytest.mark.asyncio
async def test_la_relecture_du_numero_reste_intacte_avec_le_telephone_en_argument():
    frames = await _jouer(_filtre(_contexte(ARGUMENTS_2569)), [LLMTextFrame(RELECTURE)])
    assert "".join(f.text for f in frames) == RELECTURE

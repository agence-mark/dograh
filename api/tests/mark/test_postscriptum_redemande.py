"""[.mark] Le Postscript : la phrase qui redemande ce que la note du même tour vient d'écrire (B5).

Constat (runs 1048, 1051) : en « porte, note, phrase », la note du tour écrit un champ et la phrase
pose la question de ce même champ. Le filet, derrière un interrupteur PAR AGENT éteint par défaut
(``phrase_sans_redemande``) : la phrase est retenue jusqu'à sa fin quand la note du tour a écrit au
moins un champ ; si elle POSE UNE QUESTION sur l'un d'eux, elle n'est pas dite et le modèle est
relancé une fois (trace ``relance_redemande: <champ>``). Un doute : la phrase est dite.

Preuve sur une fiche d'un autre métier (un garage) : le code ne connaît que les noms et les
descriptions de champs que l'agent déclare.

| Test | Ce qu'il prouve |
|---|---|
| question sur le champ noté | rien à la voix, une relance, trace avec le champ |
| question sur un autre champ, phrase sans question | dite en entier |
| interrupteur éteint | dite au fil des morceaux, sans tampon |
| tampon | allumé, la phrase attend sa fin ; la note n'a rien écrit : elle part au fil des morceaux |
| déjà relancé | pas de seconde relance : la phrase est dite |
| ordre d'avant, autres modes | l'interrupteur est sans effet |
"""

import pytest
from pipecat.frames.frames import (
    LLMFullResponseStartFrame,
    LLMTextFrame,
)

from api.services.pipecat.post_scriptum import TRACE_POST_SCRIPTUM
from api.services.workflow.fiche_au_fil_de_leau import ReglagesFiche
from api.tests.mark.test_porte_parlee_processeur import _MontagePortes
from api.tests.mark.test_postscriptum_prose import _MoteurQuiRelance

GARAGE = {
    "fiche_au_fil_de_leau": True,
    "fiche_mode_de_note": "post_scriptum",
    "ordre_de_la_reponse": "porte_note_phrase",
    "portes_dans_la_reponse": True,
    "phrase_sans_redemande": True,
    "fiche_champs": [
        {
            "nom": "immatriculation",
            "origine": "dicte",
            "description": "Plaque d'immatriculation du véhicule",
        },
        {"nom": "kilometrage", "origine": "dicte", "description": "Kilométrage au compteur"},
        {"nom": "motif", "origine": "deduit", "description": "Ce que la personne demande"},
    ],
}
PAROLE = "C'est pour une vidange, la plaque est AB-123-CD."
NOTE = '{"immatriculation": "AB-123-CD"}\n|||\n'


def _montage(config=GARAGE):
    montage = _MontagePortes(config)
    montage.moteur = _MoteurQuiRelance()
    montage.processeur._portes = montage.moteur
    montage.processeur._moteur = montage.moteur
    montage.messages[:] = [{"role": "user", "content": PAROLE}]
    return montage


def _trace(montage):
    return montage.fiche[TRACE_POST_SCRIPTUM][-1]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "phrase",
    [
        "Quelle est la plaque d'immatriculation ?",
        "Merci. Pouvez-vous me donner votre immatriculation ?",
        "Pour finir, quelle est l'immatriculation du véhicule ?",
    ],
)
async def test_la_question_sur_le_champ_note_au_meme_tour_relance_le_modele(phrase):
    montage = _montage()
    ordre = await montage.reponse(NOTE, phrase)
    assert montage.fiche.get("immatriculation") == "AB-123-CD"
    assert not ordre.dit.strip()
    assert montage.moteur.relances == 1
    assert _trace(montage).get("relance_redemande") == "immatriculation"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "phrase",
    [
        "Quel est le kilométrage ?",
        "Merci pour l'immatriculation. Quel est le kilométrage ?",
        "C'est noté pour la plaque d'immatriculation.",
        "Quelle est la marque ?",
    ],
)
async def test_une_autre_question_ou_aucune_question_est_dite(phrase):
    montage = _montage()
    ordre = await montage.reponse(NOTE, phrase)
    assert montage.fiche.get("immatriculation") == "AB-123-CD"
    assert ordre.dit.strip() == phrase
    assert montage.moteur.relances == 0
    assert "relance_redemande" not in _trace(montage)


@pytest.mark.asyncio
async def test_interrupteur_eteint_la_phrase_part_au_fil_des_morceaux_sans_tampon():
    montage = _montage({**GARAGE, "phrase_sans_redemande": False})
    # Sans frame de fin : ce qui est parti est parti au fil des morceaux.
    ordre = await montage.jouer(
        LLMFullResponseStartFrame(),
        LLMTextFrame(NOTE),
        LLMTextFrame("Quelle est la plaque d'immatriculation ?"),
    )
    assert ordre.dit.strip() == "Quelle est la plaque d'immatriculation ?"
    assert montage.processeur._tampon is None
    ordre = await _montage({**GARAGE, "phrase_sans_redemande": False}).reponse(
        NOTE, "Quelle est la plaque d'immatriculation ?"
    )
    assert ordre.dit.strip() == "Quelle est la plaque d'immatriculation ?"


@pytest.mark.asyncio
async def test_allume_la_phrase_attend_sa_fin_quand_la_note_a_ecrit_un_champ():
    montage = _montage()
    ordre = await montage.jouer(
        LLMFullResponseStartFrame(),
        LLMTextFrame(NOTE),
        LLMTextFrame("Quel est le kilométrage ?"),
    )
    assert not ordre.dit.strip()  # retenue jusqu'à la fin de la réponse


@pytest.mark.asyncio
async def test_allume_sans_champ_ecrit_la_phrase_part_au_fil_des_morceaux():
    montage = _montage()
    ordre = await montage.jouer(
        LLMFullResponseStartFrame(),
        LLMTextFrame('{"marque": "inconnue"}\n|||\n'),  # champ inconnu : rien d'écrit
        LLMTextFrame("Quelle est la plaque d'immatriculation ?"),
    )
    assert ordre.dit.strip() == "Quelle est la plaque d'immatriculation ?"
    assert montage.processeur._tampon is None


@pytest.mark.asyncio
async def test_deja_relance_a_cette_replique_la_phrase_est_dite():
    montage = _montage()
    await montage.moteur.relancer_une_reponse_muette()  # la relance du tour est prise
    ordre = await montage.reponse(NOTE, "Quelle est la plaque d'immatriculation ?")
    assert ordre.dit.strip() == "Quelle est la plaque d'immatriculation ?"
    assert "relance_redemande" not in _trace(montage)


@pytest.mark.asyncio
async def test_dans_l_ordre_d_avant_l_interrupteur_est_sans_effet():
    config = {**GARAGE, "ordre_de_la_reponse": "porte_phrase_note"}
    assert ReglagesFiche.depuis(config).note_d_abord is False
    montage = _montage(config)
    ordre = await montage.reponse(
        "Quelle est la plaque d'immatriculation ?\n|||\n", '{"immatriculation": "AB-123-CD"}'
    )
    assert ordre.dit.strip() == "Quelle est la plaque d'immatriculation ?"
    assert montage.moteur.relances == 0


def test_l_interrupteur_est_eteint_par_defaut_et_hors_postscript():
    sans = {k: v for k, v in GARAGE.items() if k != "phrase_sans_redemande"}
    assert ReglagesFiche.depuis(sans).phrase_sans_redemande is False
    assert ReglagesFiche.depuis(GARAGE).phrase_sans_redemande is True
    for mode in ("outil", "greffier"):
        reglages = ReglagesFiche.depuis({**GARAGE, "fiche_mode_de_note": mode})
        assert reglages.phrase_sans_redemande is False

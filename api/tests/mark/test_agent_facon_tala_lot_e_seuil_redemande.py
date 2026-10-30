"""[.mark] agent-facon-tala, revue 2 (R-13) : le seuil du signe « redemande reformulée » du détecteur d'impasse.

Mesure sur les 216 runs des bancs du chantier (lots 9 et 10) : sept signes écrits au journal de l'impasse, un seul vrai (la même
question d'adresse redite cinq fois, run 380) ; avec UN mot plein commun, des questions qui avancent (la référence de la facture,
puis sa date, puis sa question) comptaient comme une redemande parce qu'elles nomment toutes « facture ». Avec DEUX mots pleins
communs : un vrai gardé, quatre faux positifs en moins (restent deux faux : l'entretien, des questions sur des champs différents qui
partagent trois noms).

| Test | Ce qu'il prouve |
|---|---|
| avance | des questions de champs différents qui ne partagent qu'un mot (« facture ») ne sont pas une redemande |
| redemande | la même question d'adresse redite avec deux mots pleins communs reste un signe |
| liste | « habitez » est un verbe de contenu (un mot plein) ; « pourriez » n'est écrit qu'une fois |
"""

from types import SimpleNamespace

import pytest

from api.services.workflow import sortie_d_impasse as impasse
from api.tests.mark.test_sortie_d_impasse import Banc, _entrer, _repliques


async def _signes(*questions):
    banc = Banc()
    banc.active_agent.llm = SimpleNamespace(_mark_derniers_outils=())
    _entrer(banc)
    await _repliques(banc, *questions)
    return [e.get("signe") for e in banc.etat()["journal"] if e.get("signe")]


@pytest.mark.asyncio
async def test_des_questions_de_champs_differents_qui_ne_partagent_qu_un_mot_ne_sont_pas_une_redemande():
    # run 378 des bancs : la référence, la date, puis la question sur la facture, chacune répondue
    signes = await _signes(
        "D'accord. Pouvez-vous me donner la référence de cette facture ?",
        "Et la date de cette facture, s'il vous plaît ?",
        "Que souhaitez-vous savoir précisément sur cette facture ?",
    )
    assert signes == []


@pytest.mark.asyncio
async def test_la_meme_question_redite_avec_deux_mots_pleins_communs_reste_un_signe():
    # run 380 des bancs : l'adresse d'intervention redite
    signes = await _signes(
        "Votre adresse d'intervention est bien huit rue des Tilleuls, à Senlis ?",
        "C'est bien l'adresse d'intervention : huit rue des Tilleuls ?",
        "Pouvez-vous confirmer l'adresse d'intervention, huit rue des Tilleuls ?",
    )
    assert signes == ["redemande_reformulee"]


def test_la_liste_des_mots_de_tournure_compte_habitez_comme_un_mot_plein_et_pourriez_une_fois():
    assert "habitez" not in impasse.MOTS_DE_TOURNURE
    assert "habitez" in impasse._mots_pleins("ou habitez vous")
    assert impasse.MOTS_COMMUNS_POUR_UNE_REDEMANDE == 2
    source = open(impasse.__file__, encoding="utf-8").read()
    assert source.count('"pourriez"') == 1

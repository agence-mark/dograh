"""[.mark] Lot 7a, ligne 60 : le fait accompli est construit SANS la question finale ; la question s'ajoute à UNE seule place (``textes_du_code``) : celle en attente au registre,
sinon celle du réglage ; réglage vide, aucune. Plus de ``endswith`` pour retrouver la question dans le texte. Le texte dit est le même au caractère près."""

from __future__ import annotations

import json

from api.services.actions_communes import conversation as CONV
from api.services.commande import moteur
from api.services.commande.porte import _faits_gardes, textes_du_code
from api.services.commande.resultat import Resultat

from .aides_de_la_commande import a_emporter, jusqu_a_l_enregistrement, premier_article, refuser_la_proposition

QUESTION = "Puis-je faire autre chose pour vous ?"
FAIT = "Votre commande est enregistrée, elle sera prête pour dix-neuf heures."


def _enregistree(avec_la_question: bool = True) -> Resultat:
    return Resultat("ENREGISTREE", {moteur.CLE_CONFIRMATION: FAIT}, f"{FAIT} {QUESTION}" if avec_la_question else FAIT)


def test_la_question_du_reglage_suit_le_fait():
    assert textes_du_code({}, _enregistree(), None, [], False, None, QUESTION)["avant"] == f"{FAIT} {QUESTION}"


def test_la_question_en_attente_prend_la_place_de_celle_du_reglage():
    p: dict = {}
    CONV.poser_question(p, {"id": "Q-1", "type": "variante", "texte": "Quelle taille pour la margherita ?"})
    assert textes_du_code(p, _enregistree(), None, [], False, None, QUESTION)["avant"] == f"{FAIT} Quelle taille pour la margherita ?"


def test_reglage_vide_le_fait_est_dit_seul_meme_avec_une_question_en_attente():
    p: dict = {}
    CONV.poser_question(p, {"id": "Q-1", "type": "variante", "texte": "Quelle taille ?"})
    assert textes_du_code(p, _enregistree(False), None, [], False, None, None)["avant"] == FAIT
    assert textes_du_code(p, _enregistree(False), None, [], False, None, "  ")["avant"] == FAIT


def test_le_changement_garde_sa_question_et_une_question_en_attente_la_remplace():
    p = {"enregistree": {"total": 21.8}}
    dit = textes_du_code(p, Resultat("ENREGISTREE", {"remplace": 12}, FAIT), None, [], True, 10.9, QUESTION)["avant"]
    assert dit.endswith(f" {QUESTION}") and dit.count("?") == 1
    CONV.poser_question(p, {"id": "Q-2", "type": "variante", "texte": "Quelle taille ?"})
    pose = textes_du_code(p, Resultat("ENREGISTREE", {"remplace": 12}, FAIT), None, [], True, 10.9, QUESTION)["avant"]
    assert pose == dit[: -len(QUESTION)] + "Quelle taille ?"


def test_le_modele_ne_recoit_jamais_le_fait_garde_a_part():
    assert moteur.CLE_CONFIRMATION in _faits_gardes()


async def test_de_bout_en_bout_la_confirmation_porte_sa_question_une_fois(essai_de):
    e = await essai_de()
    await a_emporter(e)
    await premier_article(e)
    await refuser_la_proposition(e)
    r = await jusqu_a_l_enregistrement(e)
    dit = (e.fiche_de_l_appel.get("textes_du_code_de_la_fiche") or {}).get("avant") or ""
    assert dit.startswith("Votre commande est enregistrée") and dit.count("?") == 1, dit
    assert moteur.CLE_CONFIRMATION not in json.dumps(r, ensure_ascii=False, default=str)  # rien de plus pour le modèle

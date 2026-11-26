"""[.mark] Lot 7a, ligne 60 : le fait accompli est construit SANS la question finale ; la question s'ajoute à UNE seule place (``textes_du_code``) : celle en attente au registre,
sinon celle du réglage ; réglage vide, aucune. Plus de ``endswith`` pour retrouver la question dans le texte. Le texte dit est le même au caractère près.

C6 n° 5 (décision d'Evan 25/11 9 h 30 ; P4) : la confirmation est dite par le modèle ; le code ne dit plus après elle que le rendu et la question M108 (``suffixe``), et seulement si aucune
question n'attend (sinon le modèle la pose : une seule question, la sienne)."""

from __future__ import annotations

import json

from api.services.actions_communes import conversation as CONV
from api.services.actions_communes import journal_du_dit as J
from api.services.commande.porte import textes_du_code
from api.services.commande.resultat import Resultat

from .aides_de_la_commande import a_emporter, jusqu_a_l_enregistrement, premier_article, refuser_la_proposition

QUESTION = "Puis-je faire autre chose pour vous ?"


def _enregistree() -> Resultat:
    return Resultat("ENREGISTREE", {"quand_dit": "pour dix-neuf heures", "mode": "emporter"})


def test_la_question_du_reglage_suit_le_fait():
    textes = textes_du_code({}, _enregistree(), None, [], False, None, QUESTION)
    assert not textes.get("avant") and textes["suffixe"] == QUESTION and textes["chiffres_exiges"] == {"quand": "pour dix-neuf heures"}, textes


def test_la_question_en_attente_prend_la_place_de_celle_du_reglage():
    p: dict = {}
    CONV.poser_question(p, {"id": "Q-1", "type": "variante", "texte": "Quelle taille pour la margherita ?"})
    assert textes_du_code(p, _enregistree(), None, [], False, None, QUESTION)["suffixe"] == ""  # le modèle pose la question en attente, M108 ne s'y ajoute pas


def test_reglage_vide_le_fait_est_dit_seul_meme_avec_une_question_en_attente():
    p: dict = {}
    CONV.poser_question(p, {"id": "Q-1", "type": "variante", "texte": "Quelle taille ?"})
    assert textes_du_code(p, _enregistree(), None, [], False, None, None)["suffixe"] == ""
    assert textes_du_code({}, _enregistree(), None, [], False, None, "  ")["suffixe"] == ""


def test_le_changement_garde_sa_question_et_une_question_en_attente_la_remplace():
    # C6 n° 6 (décision d'Evan 25/11 9 h 30) : le modèle dit le changement ; le code dit le nouveau total (motif réglé) puis M108, que la question en attente remplace (le modèle la pose)
    p = {"enregistree": {"total": 2180}}
    total = "Votre commande fait maintenant vingt et un euros quatre-vingts."
    textes = textes_du_code(p, Resultat("ENREGISTREE", {"remplace": 12}), None, [], True, 1090, QUESTION, phrase_du_changement=total)
    assert not textes.get("avant") and textes["suffixe"] == f"{total} {QUESTION}", textes
    CONV.poser_question(p, {"id": "Q-2", "type": "variante", "texte": "Quelle taille ?"})
    pose = textes_du_code(p, Resultat("ENREGISTREE", {"remplace": 12}), None, [], True, 1090, QUESTION, phrase_du_changement=total)
    assert pose["suffixe"] == total, pose


async def test_de_bout_en_bout_la_confirmation_porte_sa_question_une_fois(essai_de):
    e = await essai_de()
    await a_emporter(e)
    await premier_article(e)
    await refuser_la_proposition(e)
    r = await jusqu_a_l_enregistrement(e)
    suite = (e.fiche_de_l_appel.get("textes_du_code_de_la_fiche") or {}).get("suffixe") or ""
    assert suite == QUESTION, suite  # après la phrase du modèle : la question M108, une fois
    assert (J.fait_accompli(e.p) or {}).get("fait") == "enregistree", J.fait_accompli(e.p)  # le fait gardé au journal en faits seulement (reprise R1 : jamais redit par le code ; B9)
    assert "Votre commande est enregistrée" not in json.dumps(r, ensure_ascii=False, default=str)  # le texte de secours n'est jamais donné au modèle

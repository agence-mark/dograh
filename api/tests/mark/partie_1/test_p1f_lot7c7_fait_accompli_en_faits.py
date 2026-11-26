"""[.mark] Lot 7b-C7 B9 : le fait accompli de la commande se garde au journal en FAITS, jamais en phrase.

Reprise R1 de C6 : le fait accompli ne va plus jamais à la voix ; le journal en garde l'identité (ce qui se dit : livrée ou prête, l'heure ; le nouveau total ; l'annulation) pour
savoir si un changement redit quelque chose. Les conditions de ``textes_du_code`` lisent ces faits et le statut, plus le texte de secours de la source (supprimé en B9).
"""

from __future__ import annotations

import json

from api.services.actions_communes import journal_du_dit as J
from api.services.commande import porte
from api.services.commande.porte import textes_du_code
from api.services.commande.resultat import Resultat

from .aides_de_la_commande import a_emporter, jusqu_a_l_enregistrement, premier_article, refuser_la_proposition

QUESTION = "Puis-je faire autre chose pour vous ?"


def _enregistree(quand: str = "pour dix-neuf heures", mode: str = "emporter", **plus) -> Resultat:
    return Resultat("ENREGISTREE", {"quand_dit": quand, "mode": mode, **plus})  # aucune phrase : la source n'en écrit plus


async def test_la_confirmation_garde_au_journal_ses_faits_sans_phrase(essai_de):
    e = await essai_de()
    await a_emporter(e)
    await premier_article(e)
    await refuser_la_proposition(e)
    await jusqu_a_l_enregistrement(e)
    fait = J.fait_accompli(e.p)
    assert isinstance(fait, dict) and fait["fait"] == "enregistree" and fait["livree"] is False and fait["quand_dit"], fait
    assert "texte" not in (J.entree(e.p, J.FAIT_ACCOMPLI) or {}), J.entree(e.p, J.FAIT_ACCOMPLI)
    assert "est enregistrée" not in json.dumps(J.entree(e.p, J.FAIT_ACCOMPLI), ensure_ascii=False, default=str)


def test_une_confirmation_sans_texte_de_la_source_est_dite_par_le_modele():
    textes = textes_du_code({}, _enregistree(), None, [], False, None, QUESTION)
    assert textes["a_faire"] == porte.A_FAIRE_DE_LA_CONFIRMATION and textes["suffixe"] == QUESTION, textes
    assert textes["fait_accompli"] == {"fait": "enregistree", "livree": False, "quand_dit": "pour dix-neuf heures"}, textes


def test_un_changement_qui_ne_change_rien_de_dit_ne_redit_pas_la_confirmation():
    """RC3 : même total, même heure, même « prête » : le changement se dit sans le total ; l'heure change : la confirmation ; le total change : le changement avec le total."""
    p = {"enregistree": {"total": 1090}}
    J.dire_le_fait(p, {"fait": "enregistree", "livree": False, "quand_dit": "pour dix-neuf heures"})
    meme = textes_du_code(p, _enregistree(remplace=12), None, [], True, 1090, QUESTION, phrase_du_changement="TOTAL")
    assert meme["a_faire"] == porte.A_FAIRE_DU_CHANGEMENT and meme["suffixe"] == QUESTION, meme
    autre_heure = textes_du_code(p, _enregistree("pour vingt heures", remplace=12), None, [], True, 1090, QUESTION, phrase_du_changement="TOTAL")
    assert autre_heure["a_faire"] == porte.A_FAIRE_DE_LA_CONFIRMATION, autre_heure
    autre_total = textes_du_code(p, _enregistree(remplace=12), None, [], True, 990, QUESTION, phrase_du_changement="TOTAL")
    assert autre_total["suffixe"] == f"TOTAL {QUESTION}" and autre_total["fait_accompli"] == {"fait": "changee", "total": 1090}, autre_total


def test_emporter_puis_sur_place_a_la_meme_heure_ne_change_rien_de_dit():
    """Voisin : « prête » se dit pour tout mode hors livraison ; seul « livrée » change ce qui se dit."""
    p = {"enregistree": {"total": 1090}}
    J.dire_le_fait(p, {"fait": "enregistree", "livree": False, "quand_dit": "pour dix-neuf heures"})
    sur_place = textes_du_code(p, _enregistree(mode="sur_place", remplace=12), None, [], True, 1090, QUESTION)
    assert sur_place["a_faire"] == porte.A_FAIRE_DU_CHANGEMENT, sur_place
    livree = textes_du_code(p, _enregistree(mode="livraison", remplace=12), None, [], True, 1090, QUESTION)
    assert livree["a_faire"] == porte.A_FAIRE_DE_LA_CONFIRMATION, livree


def test_l_annulation_en_cours_se_lit_sur_son_fait():
    textes = textes_du_code({}, Resultat("OK", {"annulee": True}), None, [], False)
    assert textes["a_faire"] == porte.A_FAIRE_DE_L_ANNULATION_EN_COURS and textes["fait_accompli"] == {"fait": "annulee_en_cours"}, textes
    faite = textes_du_code({}, Resultat("OK", {"commande_annulee": True}), None, [], False)
    assert faite["a_faire"] == porte.A_FAIRE_DE_L_ANNULATION_FAITE and faite["fait_accompli"] == {"fait": "annulee"}, faite

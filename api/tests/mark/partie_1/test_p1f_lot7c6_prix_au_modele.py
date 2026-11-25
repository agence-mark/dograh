"""[.mark] Lot 7b-C6, commit 11 (décision d'Evan 25/11 9 h 30, § 8 bis : les prix D33 passent au modèle, vérifiés par la barrière des chiffres).

Prix lu (PRX5). Avant : modèle « Le tacos, vous le voulez en quelle taille ? » + code « Pour Tacos, c'est à partir de sept euros. ».
Après : modèle « Le tacos est à partir de sept euros, en quelle taille ? » : le prix est un fait de la lecture, que la barrière laisse passer ; un autre prix est retenu.
Sur la vraie source et la vraie porte, sans modèle.
"""

from __future__ import annotations

from types import SimpleNamespace

from api.services.actions_communes import parole as PAROLE
from api.services.workflow import parole_de_la_fiche as PF

from .test_l12_briques import brique


async def _apres_la_lecture(essai_de):
    e = await brique(essai_de, "PRX5")
    e.dit("C'est combien le tacos ?")
    r = await e.lecture(sujet="article", article="tacos")
    return e, r


async def test_la_lecture_donne_le_prix_au_modele_et_le_code_ne_le_dit_plus(essai_de):
    e, r = await _apres_la_lecture(essai_de)
    assert r["faits"]["prix"] == {"montant": 700, "a_partir_de": True}, r
    assert "prix_dit_par_le_code_apres_ta_phrase" not in r and "suffixe_du_code" not in r, r
    assert not PAROLE.etat_du_tour(e.fiche_de_l_appel).suffixe, PAROLE.etat_du_tour(e.fiche_de_l_appel)  # rien n'attend d'être dit par le code


def _second_passage(e, retour, phrase: str):
    """Le modèle répond à la lecture par une fiche vide (sa phrase ``a_dire``) : elle vaut une phrase sans outil, le modèle repasse ; sa phrase est jugée au second passage."""
    d = PF.decider_apres_la_fiche(e.fiche_de_l_appel, retour, {"a_dire": phrase})
    assert d.mode == PAROLE.SECOND_PASSAGE, d
    return PF.VerificateurDeLaFiche(SimpleNamespace(_gathered_context=e.fiche_de_l_appel)).controler(phrase)


async def test_la_phrase_du_modele_qui_dit_le_prix_lu_passe_la_barriere(essai_de):
    e, _ = await _apres_la_lecture(essai_de)
    phrase = "Le tacos est à partir de sept euros, en quelle taille ?"
    retour = await e.fiche(a_dire=phrase)
    assert _second_passage(e, retour, phrase) is None  # dite telle quelle, rien d'ajouté par le code


async def test_un_autre_prix_que_celui_lu_est_retenu(essai_de):
    e, _ = await _apres_la_lecture(essai_de)
    phrase = "Le tacos est à neuf euros."
    retour = await e.fiche(a_dire=phrase)
    retenue = _second_passage(e, retour, phrase)
    assert retenue is not None and retenue.raison == PAROLE.CHIFFRE, retenue

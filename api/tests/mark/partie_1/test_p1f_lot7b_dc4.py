"""[.mark] Lot 7b, DC4 (Q2 = A) : la question « vous êtes sûr de vouloir annuler ? » est dite par le modèle ; le « oui » donne toujours la confirmation du code.

Avant : Client « Laissez tomber, j'annule tout. » / Agent (le code) « Vous êtes sûr de vouloir annuler votre commande de dix euros quatre-vingt-dix ? ».
Après : le modèle dit « D'accord, j'annule votre commande de dix euros quatre-vingt-dix, c'est bien ça ? » d'après ``faits.annulation_a_confirmer`` (le montant) ; Client « Oui. » / Agent
« Je vous confirme l'annulation de votre commande. » (le code, sans changement : un fait accompli qui engage).
"""

from __future__ import annotations

from api.services.actions_communes import conversation as CONV
from api.services.actions_communes import du as DU
from api.services.actions_communes import parole as PAROLE
from api.services.actions_communes.barriere_des_chiffres import chiffre_dans_la_phrase
from api.services.commande import porte as PORTE
from api.services.commande import registre as RQ
from api.services.workflow import parole_de_la_fiche as PF
from api.tests.mark.partie_1.aides_de_la_commande import (
    jusqu_a_l_enregistrement_de_la_proposition as _jusqu_a_l_enregistrement,
)


async def test_la_question_d_annulation_est_dite_par_le_modele_avec_le_montant_en_fait(essai_de):
    e = await essai_de()
    await _jusqu_a_l_enregistrement(e)
    r = await e.tour("laissez tomber, j'annule tout", annuler_une_commande_enregistree=True)
    q = CONV.question_de(e.p)
    assert q["type"] == RQ.TYPE_ANNULATION and e.p.get("enregistree") and not e.p.get("annulee"), e.p  # rien n'est annulé avant le « oui »
    assert not (e.fiche_de_l_appel.get(PORTE.CLE_TEXTES_DU_CODE) or {}).get("avant"), e.fiche_de_l_appel.get(PORTE.CLE_TEXTES_DU_CODE)  # le code ne pose pas la question
    assert r["faits"]["annulation_a_confirmer"]["montant"] == e.p["enregistree"]["total"], r["faits"]
    assert PORTE.A_FAIRE_DE_L_ANNULATION in r["a_faire"], r["a_faire"]
    d = PF.decider_apres_la_fiche(e.fiche_de_l_appel, r, {"a_dire": "D'accord, j'annule votre commande de dix euros quatre-vingt-dix, c'est bien ça ?"})
    assert d.mode != PAROLE.A_DIRE_SEUL, d
    assert not chiffre_dans_la_phrase("D'accord, j'annule votre commande de dix euros quatre-vingt-dix, c'est bien ça ?", faits=DU.faits_du_refus(r)), "le montant est un fait du retour"


async def test_le_oui_donne_toujours_la_confirmation_du_code(essai_de):
    e = await essai_de()
    await _jusqu_a_l_enregistrement(e)
    await e.tour("j'annule tout", annuler_une_commande_enregistree=True)
    q = CONV.question_de(e.p)
    await e.tour("oui", reponse={"question_id": q["id"], "sens": "accepte"})
    assert e.p.get("annulee") and (e.fiche_de_l_appel.get(PORTE.CLE_TEXTES_DU_CODE) or {}).get("avant") == RQ.TEXTE_ANNULATION_CONFIRMEE, e.fiche_de_l_appel.get(PORTE.CLE_TEXTES_DU_CODE)


async def test_la_question_d_annulation_ne_change_pas_le_verdict_de_la_commande(essai_de):
    """R1 : la question posée sous la conversation ne compte que par son numéro et son texte ; la rouvrir à l'identique (le même texte du jour) ne bouge pas ``ce_qui_se_voit``."""
    e = await essai_de()
    await _jusqu_a_l_enregistrement(e)
    await e.tour("j'annule tout", annuler_une_commande_enregistree=True)
    vu = DU.ce_qui_se_voit(e.p)
    RQ.demander_l_annulation(e.p)
    assert DU.ce_qui_se_voit(e.p) == vu

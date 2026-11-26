"""[.mark] Lot 7b-C6, commit 7 (décision d'Evan 25/11 9 h 30, § 8 bis) : l'annulation de la commande passe au modèle ; DC4 garde ses deux temps.

Avant : code « Vous êtes sûr de vouloir annuler votre commande de vingt-quatre euros ? » / après : modèle « Vous voulez vraiment annuler la commande de vingt-quatre euros ? »
(le montant est exigé de sa phrase : faux ou absent, le modèle est relancé).
Avant : code « Je vous confirme l'annulation de votre commande. » / après : modèle « C'est annulé. »
Avant : code « Je ne l'enregistre pas. » / après : modèle « D'accord, je ne la passe pas. »
Sur la vraie source et la vraie porte, sans modèle.
"""

from __future__ import annotations

from types import SimpleNamespace

from api.services.actions_communes import conversation as CONV
from api.services.actions_communes import parole as PAROLE
from api.services.commande import porte as PORTE
from api.services.commande import registre as RQ
from api.services.mots_dits import montant_en_lettres
from api.services.workflow import parole_de_la_fiche as PF

from .aides_de_la_commande import a_emporter, jusqu_a_l_enregistrement, premier_article, refuser_la_proposition


async def _enregistree(essai_de):
    e = await essai_de("casa-italia")
    await a_emporter(e)
    await premier_article(e)
    await refuser_la_proposition(e)
    await jusqu_a_l_enregistrement(e)
    return e


def _textes(e) -> dict:
    return dict(e.fiche_de_l_appel.get(PORTE.CLE_TEXTES_DU_CODE) or {})


def _dire(e, r, phrase: str, relance: str | None = None) -> str | None:
    d = PF.decider_apres_la_fiche(e.fiche_de_l_appel, r, {"a_dire": phrase})
    if d.mode == PAROLE.A_DIRE_SEUL:
        return d.a_dire
    verif = PF.VerificateurDeLaFiche(SimpleNamespace(_gathered_context=e.fiche_de_l_appel))
    texte = relance if relance is not None else phrase
    retenue = verif.controler(texte)
    if retenue is None:
        return texte
    if retenue.a_dire is not None or not retenue.consigne:
        return retenue.a_dire
    suite = verif.controler_la_relance(texte)
    return suite.a_dire if suite is not None else texte


async def test_la_question_dc4_est_posee_par_le_modele_avec_le_montant(essai_de):
    e = await _enregistree(essai_de)
    montant = montant_en_lettres(e.p["enregistree"]["total"])
    r = await e.tour("annulez ma commande", annuler_une_commande_enregistree=True)
    q = CONV.question_de(e.p) or {}
    assert q.get("type") == RQ.TYPE_ANNULATION and not e.p.get("annulee"), (q, r)  # premier temps : rien n'est annulé
    assert not _textes(e).get("avant") and "Vous êtes sûr" not in str(r), (_textes(e), r)  # le code ne pose plus la question
    phrase = f"Vous voulez vraiment annuler la commande de {montant} ?"
    assert _dire(e, r, phrase) == phrase


async def test_un_montant_faux_dans_la_question_est_relance(essai_de):
    e = await _enregistree(essai_de)
    montant = montant_en_lettres(e.p["enregistree"]["total"])
    r = await e.tour("annulez ma commande", annuler_une_commande_enregistree=True)
    bonne = f"Vous êtes sûr d'annuler la commande de {montant} ?"
    assert _dire(e, r, "Vous voulez vraiment annuler la commande de trois euros ?", relance=bonne) == bonne


async def test_une_question_dc4_sans_le_montant_est_relancee(essai_de):
    """Le montant est exigé de la question du modèle : « Vous voulez vraiment annuler ? » n'est pas dite, le modèle repasse ; sa relance avec le montant part."""
    e = await _enregistree(essai_de)
    montant = montant_en_lettres(e.p["enregistree"]["total"])
    r = await e.tour("annulez ma commande", annuler_une_commande_enregistree=True)
    bonne = f"Vous voulez vraiment annuler la commande de {montant} ?"
    assert _dire(e, r, "Vous voulez vraiment annuler ?", relance="Vous êtes sûr ?") is None  # relancée, puis rien du code : la phrase réglée de l'agent
    e2 = await _enregistree(essai_de)
    r2 = await e2.tour("annulez ma commande", annuler_une_commande_enregistree=True)
    assert _dire(e2, r2, "Vous voulez vraiment annuler ?", relance=bonne.replace(montant, montant_en_lettres(e2.p["enregistree"]["total"]))) == \
        bonne.replace(montant, montant_en_lettres(e2.p["enregistree"]["total"]))
    assert CONV.question_de(e.p)["type"] == RQ.TYPE_ANNULATION and not e.p.get("annulee")  # DC4 garde ses deux temps : la question reste posée


async def test_le_oui_annule_et_le_modele_le_dit(essai_de):
    """Second temps : « oui » annule ; le modèle le dit, le code ne dit plus « Je vous confirme l'annulation de votre commande. »."""
    e = await _enregistree(essai_de)
    await e.tour("annulez ma commande", annuler_une_commande_enregistree=True)
    q = CONV.question_de(e.p)
    r = await e.tour("oui", reponse={"question_id": q["id"], "sens": "accepte"})
    assert (e.p.get("enregistree") or {}).get("annulee") is True or e.p.get("numero_de_la_commande_annulee"), (e.p.get("enregistree"), r)
    assert not _textes(e).get("avant"), _textes(e)
    assert _dire(e, r, "C'est annulé.") == "C'est annulé."


async def test_la_commande_en_cours_annulee_est_dite_par_le_modele(essai_de):
    e = await essai_de("casa-italia")
    await a_emporter(e)
    await premier_article(e)
    await refuser_la_proposition(e)
    r = await e.tour("laissez tomber, je ne commande plus", annuler_la_commande=True)
    assert e.p.get("annulee"), r
    assert not _textes(e).get("avant"), _textes(e)  # le code ne dit plus « Je ne l'enregistre pas. »
    assert _dire(e, r, "D'accord, je ne la passe pas.") == "D'accord, je ne la passe pas."

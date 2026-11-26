"""[.mark] Lot 7b-C6, commit 6 (décision d'Evan 25/11 9 h 30, § 8 bis) : le changement d'une commande déjà enregistrée passe au modèle.

Avant : code « C'est changé : votre commande fait maintenant trente euros. Puis-je faire autre chose pour vous ? ».
Après : modèle « C'est fait, j'ai changé la commande. » + code « Votre commande fait maintenant trente euros. » (motif ``total_apres_changement``) + code « Puis-je faire autre chose
pour vous ? » (M108). Le total n'est jamais dit par le modèle (barrière) : il est dit par la phrase réglée. Sur la vraie source et la vraie porte, sans modèle.
"""

from __future__ import annotations

from types import SimpleNamespace

from api.services.actions_communes import parole as PAROLE
from api.services.commande import porte as PORTE
from api.services.mots_dits import montant_en_lettres
from api.services.phrases.catalogue import APRES_ENREGISTREMENT, MOTIFS
from api.services.workflow import parole_de_la_fiche as PF

from .aides_de_la_commande import a_emporter, jusqu_a_l_enregistrement, premier_article, refuser_la_proposition

QUESTION_M108 = MOTIFS[APRES_ENREGISTREMENT].variantes_defaut[0]
CHANGEE_PAR_LE_MODELE = "C'est fait, j'ai changé la commande."


async def _changee(essai_de):
    e = await essai_de("casa-italia")
    await a_emporter(e)
    await premier_article(e)
    await refuser_la_proposition(e)
    await jusqu_a_l_enregistrement(e)
    ligne = e.p["lignes"][0]["n"]
    r = await e.tour("finalement mettez-en deux", changer_quantite=[{"ligne": ligne, "quantite": 2}])
    assert (e.p.get("enregistree") or {}).get("total") and r["resultats"], r
    return e, r


def _phrases_du_total(e) -> list[str]:
    from api.services.phrases.catalogue import TOTAL_APRES_CHANGEMENT

    total = montant_en_lettres(e.p["enregistree"]["total"])
    return [v.replace("{total}", total) for v in MOTIFS[TOTAL_APRES_CHANGEMENT].variantes_defaut]


def _dire(e, r, phrase: str) -> str | None:
    d = PF.decider_apres_la_fiche(e.fiche_de_l_appel, r, {"a_dire": phrase})
    if d.mode == PAROLE.A_DIRE_SEUL:
        return d.a_dire
    retenue = PF.VerificateurDeLaFiche(SimpleNamespace(_gathered_context=e.fiche_de_l_appel)).controler(phrase)
    return retenue.a_dire if retenue is not None else phrase


async def test_le_changement_est_dit_par_le_modele_le_code_dit_le_nouveau_total_puis_m108(essai_de):
    e, r = await _changee(essai_de)
    textes = e.fiche_de_l_appel.get(PORTE.CLE_TEXTES_DU_CODE) or {}
    assert not textes.get("avant"), textes  # le code ne dit plus « C'est changé »
    dit = _dire(e, r, CHANGEE_PAR_LE_MODELE) or ""
    assert dit.startswith(CHANGEE_PAR_LE_MODELE), dit
    reste = dit[len(CHANGEE_PAR_LE_MODELE):].strip()
    assert any(reste == f"{t} {QUESTION_M108}" for t in _phrases_du_total(e)), dit


async def test_le_total_dit_par_le_modele_est_retenu_la_phrase_du_code_le_dit(essai_de):
    """Le modèle qui dit le nouveau total : sa phrase n'est pas dite (barrière des chiffres) ; le total ne part que par la phrase réglée."""
    e, r = await _changee(essai_de)
    total = montant_en_lettres(e.p["enregistree"]["total"])
    dit = _dire(e, r, f"C'est changé, ça fait {total}.") or ""
    assert not dit.startswith("C'est changé, ça fait"), dit

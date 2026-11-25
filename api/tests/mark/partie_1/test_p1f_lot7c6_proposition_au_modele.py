"""[.mark] Lot 7b-C6, commit 11c (décision d'Evan 25/11 9 h 30, § 8 bis : les prix D33 passent au modèle, vérifiés par la barrière des chiffres).

Prix de la proposition. Avant : modèle « Avec ça, un Coca ? » + code « Il est à deux euros. ».
Après : modèle « Avec ça, un Coca à deux euros ? » : le prix est un fait du retour, exigé de la question du modèle (même ligne de table que DC4) ; absent ou faux, le modèle est
relancé une fois. Sur la vraie source et la vraie porte, sans modèle.
"""

from __future__ import annotations

from types import SimpleNamespace

from api.services.actions_communes import conversation as CONV
from api.services.actions_communes import parole as PAROLE
from api.services.commande import porte as PORTE
from api.services.mots_dits import montant_en_lettres
from api.services.workflow import parole_de_la_fiche as PF

from .aides_de_la_commande import a_emporter, premier_article


async def _proposition(essai_de):
    e = await essai_de()
    await a_emporter(e)
    r = await premier_article(e)
    q = CONV.question_de(e.p) or {}
    assert q.get("type") == "proposition" and not q.get("offerte"), (q, r)
    return e, r, q


def _textes(e) -> dict:
    return dict(e.fiche_de_l_appel.get(PORTE.CLE_TEXTES_DU_CODE) or {})


def _dire(e, r, phrase: str, relance: str | None = None) -> str | None:
    """Ce qui part à la voix : la phrase du premier passage, sinon celle du second (``relance``, la phrase du modèle relancé)."""
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


def _prix(r) -> int:
    return r["faits"]["proposition_a_poser"]["prix"]


async def test_la_proposition_donne_le_prix_au_modele_et_le_code_ne_le_dit_plus(essai_de):
    e, r, q = await _proposition(essai_de)
    assert r["faits"]["proposition_a_poser"] == {"article": q["article_propose"], "prix": _prix(r)} and _prix(r) > 0, r["faits"]
    assert "prix_dit_par_le_code_apres_ta_phrase" not in r and "sans aucun chiffre" not in (r.get("a_faire") or ""), r
    assert not _textes(e).get("suffixe") and not q.get("chiffre"), (_textes(e), q)  # le code ne compose plus « Il est à deux euros. »
    assert _textes(e).get("chiffres_exiges") == {"prix": montant_en_lettres(_prix(r))}, _textes(e)


async def test_la_question_du_modele_avec_le_prix_est_dite_telle_quelle(essai_de):
    e, r, q = await _proposition(essai_de)
    phrase = f"Avec ça, {q['article_propose']} à {montant_en_lettres(_prix(r))} ?"
    assert _dire(e, r, phrase) == phrase  # rien d'ajouté par le code


async def test_une_question_sans_le_prix_est_relancee(essai_de):
    e, r, q = await _proposition(essai_de)
    bonne = f"Avec ça, {q['article_propose']} à {montant_en_lettres(_prix(r))} ?"
    assert _dire(e, r, f"Avec ça, {q['article_propose']} ?", relance=bonne) == bonne


async def test_un_autre_prix_est_relance(essai_de):
    e, r, q = await _proposition(essai_de)
    bonne = f"Avec ça, {q['article_propose']} à {montant_en_lettres(_prix(r))} ?"
    assert _dire(e, r, f"Avec ça, {q['article_propose']} à {montant_en_lettres(_prix(r) + 700)} ?", relance=bonne) == bonne


async def test_une_relance_encore_sans_le_prix_laisse_la_phrase_reglee_et_la_question_posee(essai_de):
    """La relance est unique (C5) : encore sans le prix, la phrase du modèle n'est pas dite ; rien du code (la phrase réglée de l'agent, jamais un tour muet) ; la question reste posée."""
    e, r, q = await _proposition(essai_de)
    assert _dire(e, r, f"Avec ça, {q['article_propose']} ?", relance=f"Je vous ajoute {q['article_propose']} ?") is None
    assert (CONV.question_de(e.p) or {}).get("type") == "proposition"


async def test_la_consigne_de_relance_demande_le_prix_sans_retirer_la_question(essai_de):
    """La relance d'une question dont un chiffre est exigé (rien n'est dit par le code après elle) demande la valeur exigée ; elle ne dit plus « sans prix et sans question »,
    écrit pour un fait accompli suivi de la suite du code (même consigne pour DC4)."""
    e, r, q = await _proposition(essai_de)
    phrase = f"Avec ça, {q['article_propose']} ?"
    assert PF.decider_apres_la_fiche(e.fiche_de_l_appel, r, {"a_dire": phrase}).mode == PAROLE.SECOND_PASSAGE
    retenue = PF.VerificateurDeLaFiche(SimpleNamespace(_gathered_context=e.fiche_de_l_appel)).controler(phrase)
    assert retenue is not None and retenue.raison == PAROLE.CHIFFRES_EXIGES, retenue
    assert montant_en_lettres(_prix(r)) in retenue.consigne and "sans question" not in retenue.consigne and "sans prix" not in retenue.consigne, retenue.consigne

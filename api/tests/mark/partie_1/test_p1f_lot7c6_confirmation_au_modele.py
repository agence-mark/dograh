"""[.mark] Lot 7b-C6, commit 5 (décision d'Evan 25/11 9 h 30, § 8 bis ; P4 : M108 reste au code) : la confirmation de l'enregistrement passe au modèle.

Avant : code « Votre commande est enregistrée, elle sera prête pour dix-neuf heures. Sur votre billet de cinquante euros, on vous rendra vingt-six euros. Puis-je faire autre chose pour vous ? ».
Après : modèle « C'est enregistré, prête à dix-neuf heures. » + code « Sur votre billet de cinquante euros, on vous rend vingt-six euros. » (motif ``rendu_de_monnaie``) + code « Puis-je faire
autre chose pour vous ? » (M108). L'ordre est fixe : la phrase du modèle, le rendu, M108. La phrase du modèle doit dire l'heure (barrière) : sans elle, le modèle est relancé une fois, puis le code
redit le fait accompli. Sur la vraie source et la vraie porte, sans modèle.
"""

from __future__ import annotations

from types import SimpleNamespace

from api.services.actions_communes import journal_du_dit as J
from api.services.actions_communes import parole as PAROLE
from api.services.commande import porte as PORTE
from api.services.mots_dits import montant_en_lettres
from api.services.phrases.catalogue import APRES_ENREGISTREMENT, MOTIFS
from api.services.workflow import parole_de_la_fiche as PF

from .aides_de_la_commande import a_emporter, jusqu_a_l_enregistrement, premier_article, refuser_la_proposition

QUESTION_M108 = MOTIFS[APRES_ENREGISTREMENT].variantes_defaut[0]


async def _jusqu_a_la_confirmation(essai_de, **reglement):
    e = await essai_de("casa-italia")
    await a_emporter(e)
    await premier_article(e)
    await refuser_la_proposition(e)
    r = await jusqu_a_l_enregistrement(e, **reglement)
    return e, r


def _rendus(e) -> list[str]:
    from api.services.phrases.catalogue import RENDU_DE_MONNAIE

    enregistree = e.p["enregistree"]
    billet, monnaie = montant_en_lettres(enregistree["rendu"]["billet"]), montant_en_lettres(enregistree["rendu"]["monnaie"])
    return [v.replace("{billet}", billet).replace("{monnaie}", monnaie) for v in MOTIFS[RENDU_DE_MONNAIE].variantes_defaut]


def _quand(e) -> str:
    return str(e.p["enregistree"]["quand_dit"])


def _dire(e, r, phrase: str, relance: str | None = None) -> str | None:
    """Ce qui part à la voix quand le modèle écrit ``phrase`` avec la fiche, puis ``relance`` au second passage (``None`` : la même phrase)."""
    d = PF.decider_apres_la_fiche(e.fiche_de_l_appel, r, {"a_dire": phrase})
    if d.mode == PAROLE.A_DIRE_SEUL:
        return d.a_dire
    verif = PF.VerificateurDeLaFiche(SimpleNamespace(_gathered_context=e.fiche_de_l_appel))
    retenue = verif.controler(relance if relance is not None else phrase)
    if retenue is None:
        return relance if relance is not None else phrase
    if retenue.a_dire is not None or not retenue.consigne:
        return retenue.a_dire
    suite = verif.controler_la_relance(relance if relance is not None else phrase)
    return suite.a_dire if suite is not None else (relance if relance is not None else phrase)


async def test_la_confirmation_est_dite_par_le_modele_le_code_ne_dit_que_le_rendu_puis_m108(essai_de):
    """Client « Oui, en espèces, un billet de cinquante. » / modèle « C'est enregistré, prête {quand}. » + code « Sur votre billet …, on vous rend … » + code « Puis-je faire autre chose pour vous ? »."""
    e, r = await _jusqu_a_la_confirmation(essai_de, moyen="especes", rendu_sur=50)
    textes = e.fiche_de_l_appel.get(PORTE.CLE_TEXTES_DU_CODE) or {}
    assert not textes.get("avant"), textes  # le code ne dit plus la confirmation
    assert "Votre commande est enregistrée" not in str(textes.get("suffixe")), textes  # le fait accompli n'est gardé qu'au journal (repli), jamais dit à la place du modèle
    phrase = f"C'est enregistré, prête {_quand(e)}."
    dit = _dire(e, r, phrase) or ""
    assert dit.startswith(phrase), dit
    reste = dit[len(phrase):].strip()
    assert any(reste == f"{rendu} {QUESTION_M108}" for rendu in _rendus(e)), dit  # l'ordre : modèle, rendu, M108


async def test_sans_monnaie_a_rendre_seule_m108_suit_la_phrase_du_modele(essai_de):
    e, r = await _jusqu_a_la_confirmation(essai_de)
    phrase = f"C'est noté, votre commande sera prête {_quand(e)}."
    assert _dire(e, r, phrase) == f"{phrase} {QUESTION_M108}"


async def test_une_confirmation_sans_l_heure_est_relancee_puis_le_code_redit_le_fait_accompli(essai_de):
    """Heure exigée (barrière) : « C'est enregistré. » n'est pas dit ; la relance le redit sans l'heure : le fait accompli gardé au journal, puis M108. Jamais un tour muet."""
    e, r = await _jusqu_a_la_confirmation(essai_de)
    dit = _dire(e, r, "C'est enregistré.") or ""
    assert dit.endswith(QUESTION_M108) and _quand(e) in dit, dit
    assert not dit.startswith("C'est enregistré."), dit
    assert J.fait_accompli(e.p) and dit.startswith(J.fait_accompli(e.p)), (dit, J.fait_accompli(e.p))


async def test_la_relance_qui_dit_l_heure_part_avec_la_suite_du_code(essai_de):
    e, r = await _jusqu_a_la_confirmation(essai_de)
    bonne = f"Parfait, c'est enregistré, prête {_quand(e)}."
    assert _dire(e, r, "Je l'enregistre.", relance=bonne) == f"{bonne} {QUESTION_M108}"

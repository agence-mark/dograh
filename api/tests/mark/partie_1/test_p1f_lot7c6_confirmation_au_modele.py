"""[.mark] Lot 7b-C6, commit 5 (décision d'Evan 25/11 9 h 30, § 8 bis ; P4 : M108 reste au code) : la confirmation de l'enregistrement passe au modèle.

Avant : code « Votre commande est enregistrée, elle sera prête pour dix-neuf heures. Sur votre billet de cinquante euros, on vous rendra vingt-six euros. Puis-je faire autre chose pour vous ? ».
Après : modèle « C'est enregistré, prête à dix-neuf heures. » + code « Sur votre billet de cinquante euros, on vous rend vingt-six euros. » (motif ``rendu_de_monnaie``) + code « Puis-je faire
autre chose pour vous ? » (M108). L'ordre est fixe : la phrase du modèle, le rendu, M108. La phrase du modèle doit dire l'heure (barrière) : sans elle, le modèle est relancé une fois, puis le code
ne dit que la suite réglée (reprise R1 : jamais le fait accompli). Sur la vraie source et la vraie porte, sans modèle.
"""

from __future__ import annotations

from types import SimpleNamespace

from api.services.actions_communes import conversation as CONV
from api.services.actions_communes import journal_du_dit as J
from api.services.actions_communes import parole as PAROLE
from api.services.commande import porte as PORTE
from api.services.mots_dits import montant_en_lettres
from api.services.phrases.catalogue import APRES_ENREGISTREMENT, MOTIFS
from api.services.workflow import parole_de_la_fiche as PF

from .aides_de_la_commande import QUESTION_M108, dire_du_modele, jusqu_a_la_confirmation, quand_dit

def _rendus(e) -> list[str]:
    from api.services.phrases.catalogue import RENDU_DE_MONNAIE

    enregistree = e.p["enregistree"]
    billet, monnaie = montant_en_lettres(enregistree["rendu"]["billet"]), montant_en_lettres(enregistree["rendu"]["monnaie"])
    return [v.replace("{billet}", billet).replace("{monnaie}", monnaie) for v in MOTIFS[RENDU_DE_MONNAIE].variantes_defaut]


async def test_la_confirmation_est_dite_par_le_modele_le_code_ne_dit_que_le_rendu_puis_m108(essai_de):
    """Client « Oui, en espèces, un billet de cinquante. » / modèle « C'est enregistré, prête {quand}. » + code « Sur votre billet …, on vous rend … » + code « Puis-je faire autre chose pour vous ? »."""
    e, r = await jusqu_a_la_confirmation(essai_de, moyen="especes", rendu_sur=50)
    textes = e.fiche_de_l_appel.get(PORTE.CLE_TEXTES_DU_CODE) or {}
    assert not textes.get("avant"), textes  # le code ne dit plus la confirmation
    assert "Votre commande est enregistrée" not in str(textes.get("suffixe")), textes  # le fait accompli n'est gardé qu'au journal, jamais dit à la voix (reprise R1)
    phrase = f"C'est enregistré, prête {quand_dit(e)}."
    dit = dire_du_modele(e, r, phrase) or ""
    assert dit.startswith(phrase), dit
    reste = dit[len(phrase):].strip()
    assert any(reste == f"{rendu} {QUESTION_M108}" for rendu in _rendus(e)), dit  # l'ordre : modèle, rendu, M108


async def test_sans_monnaie_a_rendre_seule_m108_suit_la_phrase_du_modele(essai_de):
    e, r = await jusqu_a_la_confirmation(essai_de)
    phrase = f"C'est noté, votre commande sera prête {quand_dit(e)}."
    assert dire_du_modele(e, r, phrase) == f"{phrase} {QUESTION_M108}"


async def test_une_confirmation_sans_l_heure_est_relancee_puis_le_code_ne_dit_que_la_suite_reglee(essai_de):
    """Heure exigée (barrière) : « C'est enregistré. » n'est pas dit ; la relance le redit sans l'heure : décisions d'Evan 25/11 8 h 45 et 9 h 30 (P3), C5 § 2, coordinateur 26/11 2 h 05 (P3 tel quel) : reprise R1 de C6 : la suite réglée seule (M108), jamais le fait accompli
    gardé au journal. Jamais un tour muet."""
    e, r = await jusqu_a_la_confirmation(essai_de)
    dit = dire_du_modele(e, r, "C'est enregistré.") or ""
    assert dit == f"C'est enregistré. {QUESTION_M108}", dit  # PE-2 Q4 (BILAN:270 : le motif réglé « C'est enregistré. » dit la confirmation quand la relance échoue) ; avant : la question seule
    assert (J.fait_accompli(e.p) or {}).get("fait") == "enregistree" and "est enregistrée" not in dit, (dit, J.fait_accompli(e.p))  # le fait gardé au journal en faits (B9), jamais redit par le code (reprise R1 de C6)


async def test_la_relance_qui_dit_l_heure_part_avec_la_suite_du_code(essai_de):
    e, r = await jusqu_a_la_confirmation(essai_de)
    bonne = f"Parfait, c'est enregistré, prête {quand_dit(e)}."
    assert dire_du_modele(e, r, "Je l'enregistre.", relance=bonne) == f"{bonne} {QUESTION_M108}"


async def test_la_consigne_de_relance_de_la_confirmation_garde_sans_question(essai_de):
    """Voisin de la consigne de la proposition (C6 n° 11) : la confirmation est suivie de la suite du code (M108) ; sa relance dit toujours « sans question »."""
    e, r = await jusqu_a_la_confirmation(essai_de)
    assert PF.decider_apres_la_fiche(e.fiche_de_l_appel, r, {"a_dire": "C'est enregistré."}).mode == PAROLE.SECOND_PASSAGE
    retenue = PF.VerificateurDeLaFiche(SimpleNamespace(_gathered_context=e.fiche_de_l_appel)).controler("C'est enregistré.")
    assert retenue is not None and retenue.raison == PAROLE.CHIFFRES_EXIGES and "sans question" in retenue.consigne and quand_dit(e) in retenue.consigne, retenue


async def test_mineur_tranche_aucune_question_n_attend_apres_l_enregistrement_avec_monnaie_a_rendre(essai_de):
    """Mineur (3) de l'audit de la tranche : Client « Oui, en espèces, un billet de cinquante. » ; après l'enregistrement, aucune question n'attend dans le dossier : M108, dite par
    le code après le rendu, reste la seule question et la dernière (la question toujours en dernier ; ``_textes_de_la_confirmation`` ne la dit que si aucune n'attend)."""
    e, _ = await jusqu_a_la_confirmation(essai_de, moyen="especes", rendu_sur=50)
    assert CONV.question_de(e.p) is None, CONV.question_de(e.p)
    suffixe = str((e.fiche_de_l_appel.get(PORTE.CLE_TEXTES_DU_CODE) or {}).get("suffixe") or "")
    assert suffixe.endswith(QUESTION_M108) and suffixe.count("?") == 1, suffixe

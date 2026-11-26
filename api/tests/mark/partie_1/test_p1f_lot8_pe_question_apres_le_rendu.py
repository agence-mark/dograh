"""[.mark] Lot 8, PE-2, Q5 (point d'étape du 26/11, bilan Q5, choix A) : la question du modèle attend le tour suivant quand le code dit une suite (le rendu de monnaie).

Aucun parcours réel ne produit ce cas (sondé sur 3 parcours) : l'état est construit à la main (la fiche de l'appel, la question qui attend, la phrase réglée du code, les Entrees de la table).
Client « Je paie en liquide, j'ai cinquante euros. » / modèle « C'est noté. Vous voulez une boisson ? » + code « Sur votre billet de cinquante euros, on vous rendra vingt-six euros. »
Avant : le client entend la question du modèle, puis le rendu (deux phrases, la question au milieu). Après : la phrase du modèle sans question est relancée (consigne
``SANS_LA_SUITE_DU_CODE``), ou le rendu part seul ; la question reste au registre pour le tour suivant. Jamais deux questions, jamais la question avant le rendu."""

from __future__ import annotations

from types import SimpleNamespace

from api.services.actions_communes import conversation as CONV
from api.services.actions_communes import parole as PAROLE
from api.services.actions_communes import table_de_parole as TABLE
from api.services.actions_communes.repli import CLE_DU_TOUR
from api.services.commande import panier as P
from api.services.workflow import parole_de_la_fiche as PF
from api.services.workflow.cases_selon_l_etat import CLE_DES_CASES_MONTREES

RENDU = "Sur votre billet de cinquante euros, on vous rendra vingt-six euros."
QUESTION_DU_MODELE = "Vous voulez une boisson ?"
QUESTION = {"id": "Q-1", "type": "variante", "texte": "", "nee_au_tour": 0, "article_en_question": "Regina"}


def _fiche_avec_la_question() -> dict:
    fiche: dict = {CLE_DES_CASES_MONTREES: {"fiche": True}, CLE_DU_TOUR: 1, PF.CLE_DES_PAROLES: ["Je paie en liquide, j'ai cinquante euros."]}
    CONV.poser_question(P.du_dossier(fiche), dict(QUESTION))
    return fiche


def _entrees(fiche: dict, phrase: str, *, textes: dict, rien_change: bool, suffixe_avant: str | None = None):
    etat = PAROLE.etat_du_tour(fiche)
    p = P.du_dossier(fiche)
    retour = {"statut": "FAIT", "resultats": [], "faits": {}, "rien_change": rien_change}
    ancre = TABLE.ancre_de_la_question(p) if suffixe_avant else None
    return TABLE.entrees_du_retour(retour, phrase, etat, [], p, textes, True, suffixe_avant, ancre)


def test_la_confirmation_qui_pose_une_question_avant_le_rendu_n_est_pas_dite():
    """La fiche enregistre avec monnaie (suite du code : le rendu) ; la phrase du modèle pose une question : jetée, le modèle repasse avec la consigne « sans question »."""
    fiche = _fiche_avec_la_question()
    textes = {"suffixe": RENDU, "chiffres_exiges": {}, "fait_accompli": {"fait": "enregistree"}, "a_faire": "confirme"}
    entrees = _entrees(fiche, f"C'est noté. {QUESTION_DU_MODELE}", textes=textes, rien_change=False)
    decision = TABLE.decider(entrees)
    assert decision.mode == PAROLE.SECOND_PASSAGE, decision
    assert entrees.etat.suffixe == RENDU, entrees.etat  # le rendu n'est pas perdu : il suit la phrase du second passage


def test_la_phrase_du_modele_sans_question_part_avec_le_rendu_et_la_question_attend_le_tour_suivant():
    fiche = _fiche_avec_la_question()
    textes = {"suffixe": RENDU, "chiffres_exiges": {}, "fait_accompli": {"fait": "enregistree"}, "a_faire": "confirme"}
    decision = TABLE.decider(_entrees(fiche, "C'est noté.", textes=textes, rien_change=False))
    assert (decision.mode, decision.a_dire) == (PAROLE.A_DIRE_SEUL, f"C'est noté. {RENDU}"), decision
    assert CONV.question_de(P.du_dossier(fiche)) is not None  # la question reste au registre


def test_une_question_qui_attend_ne_force_pas_la_question_avant_le_rendu_d_un_passage_d_avant():
    """Le rendu est posé par un passage d'avant du tour ; la fiche suivante change quelque chose, la question attend toujours : la phrase du modèle (sans question) part avec le rendu,
    le modèle n'est pas relancé pour poser la question avant lui."""
    fiche = _fiche_avec_la_question()
    decision = TABLE.decider(_entrees(fiche, "C'est noté.", textes={}, rien_change=False, suffixe_avant=RENDU))
    assert (decision.mode, decision.a_dire) == (PAROLE.A_DIRE_SEUL, f"C'est noté. {RENDU}"), decision


def test_le_modele_qui_pose_encore_sa_question_apres_la_relance_le_rendu_part_seul():
    """Au second passage le modèle pose encore une question : sa phrase n'est pas dite (la question avant le rendu), le rendu part seul, jamais un tour muet."""
    fiche = _fiche_avec_la_question()
    etat = PAROLE.etat_du_tour(fiche)
    etat.suffixe = RENDU
    PAROLE.garder(fiche, etat)
    verificateur = PF.VerificateurDeLaFiche(SimpleNamespace(_gathered_context=fiche))
    premiere = verificateur.controler(f"C'est noté. {QUESTION_DU_MODELE}")
    assert premiere is not None and premiere.consigne and premiere.a_dire is None, premiere  # relancé une fois, sans question
    seconde = verificateur.controler_la_relance(f"C'est noté. {QUESTION_DU_MODELE}")
    assert seconde is not None and seconde.a_dire == RENDU, seconde

"""[.mark] Lot 7b-C6, commit 2 (décision d'Evan 25/11 9 h 30) : le total est toujours un fait donné au modèle ; le CODE le dit, avec la question, juste après la phrase du modèle.

Le modèle qui dit le total, ou qui pose la question que le code pose, est retenu et relancé UNE fois (la relance du fait de C5) ; une relance qui dit encore la question n'est pas dite.
La réservation : le code vérifie que la phrase porte les personnes et l'heure (``porte_les_chiffres``). Aucun modèle : des fiches d'appel en mémoire.
"""

from __future__ import annotations

from types import SimpleNamespace

from api.services.actions_communes import parole as PAROLE
from api.services.actions_communes.barriere_des_chiffres import porte_les_chiffres
from api.services.actions_communes.repli import CLE_DU_TOUR
from api.services.commande import etat_pour_le_modele as ETAT
from api.services.commande import panier as P
from api.services.workflow import parole_de_la_fiche as PF
from api.services.workflow.cases_selon_l_etat import CLE_DES_CASES_MONTREES

TOTAL_DIT = "Cela fait vingt-quatre euros, c'est bon pour vous ?"
RELECTURE = "Alors deux Regina, sans oignons."


def _fiche_avec_relecture(total: int = 2400) -> dict:
    p = P.nouveau()
    p["lignes"] = [{"n": 1, "quantite": 2, "code": "x", "nom": "Regina"}]
    p["mode"] = "emporter"
    p["relecture"] = {"empreinte": "e", "jeton": "j", "version": 1, "total": total}
    return {P.CLE: p, CLE_DES_CASES_MONTREES: {"fiche": True}, CLE_DU_TOUR: 1, PF.CLE_DES_PAROLES: ["C'est tout."]}


def _verificateur(fiche: dict, suffixe: str | None = TOTAL_DIT) -> PF.VerificateurDeLaFiche:
    etat = PAROLE.etat_du_tour(fiche)
    etat.fiches, etat.suffixe = 1, suffixe
    PAROLE.garder(fiche, etat)
    return PF.VerificateurDeLaFiche(SimpleNamespace(_gathered_context=fiche))


def test_le_total_est_dans_l_etat_donne_au_modele():
    """Le modèle sait le total (« vingt-quatre euros ») et que c'est le code qui le dit."""
    texte = ETAT.texte(_fiche_avec_relecture()) or ""
    assert "Total de la commande : vingt-quatre euros" in texte and "tu ne le dis pas" in texte


def test_pas_de_total_sans_relecture_ni_enregistrement_et_pas_pour_une_commande_annulee():
    fiche = _fiche_avec_relecture()
    fiche[P.CLE]["relecture"] = None
    assert "Total de la commande" not in (ETAT.texte(fiche) or "")
    fiche = _fiche_avec_relecture()
    fiche[P.CLE]["annulee"] = True
    assert "Total de la commande" not in (ETAT.texte(fiche) or "")


def test_une_relecture_du_modele_sans_prix_ni_question_est_dite_puis_suivie_de_la_phrase_du_code():
    retenue = _verificateur(_fiche_avec_relecture()).controler(RELECTURE)
    assert retenue is not None and retenue.raison == PAROLE.SUFFIXE and retenue.a_dire == f"{RELECTURE} {TOTAL_DIT}"


def test_une_relecture_qui_pose_la_question_du_code_est_retenue_et_relancee_une_fois():
    """Client « C'est tout. », le modèle dit « Alors deux Regina, c'est bon ? » : le code pose la question, la phrase n'est pas dite, le modèle repasse."""
    verificateur = _verificateur(_fiche_avec_relecture())
    retenue = verificateur.controler("Alors deux Regina, c'est bon ?")
    assert retenue is not None and retenue.raison == PAROLE.CE_QUE_LE_CODE_DIT and retenue.consigne and retenue.a_dire is None
    # la relance dit la phrase sans question : dite, suivie du total du code
    relance = verificateur.controler_la_relance(RELECTURE)
    assert relance is not None and relance.a_dire == f"{RELECTURE} {TOTAL_DIT}"


def test_une_relance_qui_pose_encore_la_question_laisse_dire_la_seule_phrase_du_code():
    """R0 : relance échouée, la phrase du modèle n'est pas dite, la phrase réglée du total part seule (jamais un tour muet) ; pas de seconde relance."""
    fiche = _fiche_avec_relecture()
    verificateur = _verificateur(fiche)
    assert verificateur.controler("Alors deux Regina, c'est bon ?").consigne
    relance = verificateur.controler_la_relance("Deux Regina, c'est bon ?")
    assert relance is not None and relance.a_dire == TOTAL_DIT and not relance.consigne
    assert PAROLE.etat_du_tour(fiche).suffixe is None


def test_le_total_dit_par_le_modele_est_retenu_par_la_barriere_des_chiffres():
    retenue = _verificateur(_fiche_avec_relecture()).controler("Alors deux Regina, ça fait vingt-quatre euros.")
    assert retenue is not None and retenue.raison in (PAROLE.CHIFFRE, PAROLE.SANS_OUTIL, PAROLE.CE_QUE_LE_CODE_DIT) and retenue.a_dire is None


def test_un_suffixe_sans_question_ne_retient_pas_une_phrase_qui_pose_une_question():
    """Le prix d'une proposition (D33) suit une phrase qui pose la question : le code n'y change rien."""
    fiche = _fiche_avec_relecture()
    retenue = _verificateur(fiche, suffixe="Il est à deux euros.").controler("Avec ça, un Coca ?")
    assert retenue is not None and retenue.raison == PAROLE.SUFFIXE and retenue.a_dire == "Avec ça, un Coca ? Il est à deux euros."


def test_la_reservation_exige_les_personnes_et_l_heure_dans_la_phrase_du_modele():
    attendus = {"personnes": "quatre personnes", "heure": "vingt heures"}
    assert porte_les_chiffres("Samedi vingt heures pour quatre personnes, au nom de Paul : je confirme ?", attendus)
    assert not porte_les_chiffres("Samedi pour quatre personnes, au nom de Paul : je confirme ?", attendus)  # l'heure manque
    assert not porte_les_chiffres("Samedi vingt heures, au nom de Paul : je confirme ?", attendus)  # les personnes manquent
    assert porte_les_chiffres("Midi, au nom de Paul.", {"heure": "midi", "personnes": None})  # une valeur sans nombre se cherche telle quelle

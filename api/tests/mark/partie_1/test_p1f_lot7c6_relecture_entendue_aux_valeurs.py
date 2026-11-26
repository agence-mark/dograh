"""[.mark] Lot 7b-C6, avant le commit 8 (P2, décision d'Evan 25/11 : le code vérifie personnes et heure de la réservation) : une relecture que le MODÈLE dit en entier (la réservation)
n'a pas de phrase réglée qui la prouve ; elle est entendue quand la phrase partie à la voix dit les valeurs exigées (``porte_les_chiffres``). Mécanisme commun (journal du dit, au jeton),
le même que la phrase du total de la commande : aucun drapeau neuf."""

from __future__ import annotations

from api.services.actions_communes import parole as PAROLE


def test_une_relecture_n_est_entendue_que_si_la_phrase_dit_les_valeurs_exigees():
    etat = PAROLE.EtatDuTour(tour=1, total_a_dire={"jeton": "j", "texte": None, "exiges": {"personnes": "4", "heure": "vingt heures"}})
    p: dict = {}
    PAROLE.noter_le_total_dit(p, etat, "Pour quatre, au nom de Paul.")
    assert not PAROLE.total_dit(p, "j")
    PAROLE.noter_le_total_dit(p, etat, "Samedi vingt heures pour quatre, au nom de Paul.")
    assert PAROLE.total_dit(p, "j") and not PAROLE.total_dit(p, "k")


def test_la_phrase_reglee_et_les_valeurs_sont_toutes_deux_exigees_quand_les_deux_sont_donnees():
    question = "Je note ce numéro de téléphone pour vous joindre en cas de problème, c'est bon ?"
    etat = PAROLE.EtatDuTour(tour=1, total_a_dire={"jeton": "j", "texte": question, "exiges": {"personnes": "4", "heure": "vingt heures"}})
    p: dict = {}
    PAROLE.noter_le_total_dit(p, etat, question)  # la question seule (relance échouée) : la relecture n'est pas entendue
    assert not PAROLE.total_dit(p, "j")
    PAROLE.noter_le_total_dit(p, etat, f"Samedi vingt heures pour quatre. {question}")
    assert PAROLE.total_dit(p, "j")


def test_la_phrase_du_total_de_la_commande_reste_seule_exigee_sans_valeurs():
    etat = PAROLE.EtatDuTour(tour=1, total_a_dire={"jeton": "j", "texte": "Cela fait trente euros, c'est bon pour vous ?"})
    p: dict = {}
    PAROLE.noter_le_total_dit(p, etat, "Alors trois Margherita. Cela fait trente euros, c'est bon pour vous ?")
    assert PAROLE.total_dit(p, "j")

"""[.mark] Lot 7b-B, constat 0.1 : la barrière des chiffres accepte les valeurs que portent les faits du retour de CE tour (montants, heures, quantités), et elles seules.

Sans cela, rendre au modèle le minimum, l'heure complète ou le maximum ramène le défaut du lot 20 (n2) : sa phrase est retenue jusqu'au « Pardon ». Règle de valeur, jamais de sens.
"""

from __future__ import annotations

from api.services.actions_communes import parole as PAROLE
from api.services.actions_communes.barriere_des_chiffres import chiffre_dans_la_phrase
from api.services.workflow import parole_de_la_fiche as PF

PHRASE = "Pour Chantilly il faut cinquante euros minimum, il vous manque trente-neuf euros dix ; vous ajoutez quelque chose ?"


def _retour(minimum: int, manque: int) -> dict:
    return {"statut": "PARTIEL", "resultats": [{"operation": "informations", "statut_du_module": "HORS_ZONE", "faits": {"minimum": minimum, "manque": manque}}],
            "faits": {"fait_bloquant": {"statut_du_module": "HORS_ZONE", "manque": None},
                      "refus_de_la_fiche": [{"statut_du_module": "HORS_ZONE", "faits": {"minimum": minimum, "manque": manque}}]}}


def test_les_valeurs_des_faits_passent_la_barriere_les_autres_non():
    faits = [{"minimum": 5000, "manque": 3910}]
    assert chiffre_dans_la_phrase(PHRASE, (), (), faits=faits) is False
    assert chiffre_dans_la_phrase(PHRASE, (), (), faits=[{"minimum": 5000, "manque": 1000}]) is True  # un autre montant que celui du fait : retenu
    assert chiffre_dans_la_phrase(PHRASE, (), ()) is True  # sans faits : retenu comme avant


def test_la_relance_qui_dit_les_chiffres_du_refus_n_est_pas_retenue():
    """Scénario : le refus du tour porte le minimum et ce qui manque ; la phrase libre du modèle qui les dit est dite, pas retenue jusqu'au « Pardon »."""
    fiche: dict = {"tour_de_la_personne": 3, "paroles_de_la_personne": ["deux reines à Chantilly"]}
    PF.decider_apres_la_fiche(fiche, _retour(5000, 3910), {"a_dire": "ok"})
    etat = PAROLE.etat_du_tour(fiche)
    etat.rattrapage_refus_joue = True  # le rattrapage du refus a déjà joué : reste la barrière des chiffres
    retenue = PAROLE.phrase_libre_retenue(PHRASE, etat, objet_en_cours=True, question_en_attente=False, paroles=fiche["paroles_de_la_personne"])
    assert retenue is None, retenue


def test_les_faits_d_un_autre_tour_ne_comptent_pas():
    fiche: dict = {"tour_de_la_personne": 3}
    PF.decider_apres_la_fiche(fiche, _retour(5000, 3910), {"a_dire": "ok"})
    fiche["tour_de_la_personne"] = 4
    etat = PAROLE.etat_du_tour(fiche)
    assert PAROLE.phrase_libre_retenue(PHRASE, etat, objet_en_cours=False, question_en_attente=False, paroles=[]) == PAROLE.CHIFFRE

"""[.mark] Lot 7b-C4, reprise R1 (5e canal) : l'état donné au modèle à chaque tour ne porte jamais la phrase de secours d'une question que le code ne dit pas lui-même.

Une question hors ``QUESTIONS_DITES_PAR_LE_CODE`` n'a dans l'état que des faits bruts (son objet, ses candidats) ; une question dite par le code garde son texte.
"""

from __future__ import annotations

import pytest

from api.services.actions_communes import conversation as CONV
from api.services.actions_communes.enveloppe import QUESTIONS_DITES_PAR_LE_CODE
from api.services.commande import etat_pour_le_modele as ETAT_COMMANDE
from api.services.commande import moteur
from api.services.commande import panier as P
from api.services.reservation import etat_pour_le_modele as ETAT_RESERVATION

PHRASE = "Quelle taille pour la Regina ?"


def _etat_de_la_commande(question: dict) -> str:
    p = P.nouveau()
    CONV.poser_question(p, {"id": "Q-2", "nee_au_tour": 1, **question})
    return ETAT_COMMANDE.texte({P.CLE: p}) or ""


def _etat_de_la_reservation(question: dict) -> str:
    fiche: dict = {}
    CONV.poser_question(ETAT_RESERVATION.moteur.etat_du_dossier(fiche), {"id": "Q-2", "nee_au_tour": 1, **question})
    return ETAT_RESERVATION.texte(fiche) or ""


QUESTIONS_DE_LA_COMMANDE = [
    {"type": "variante", "texte": PHRASE, "article_en_question": "Regina"},
    {"type": "ambiguite", "texte": PHRASE, "choix": ["Regina", "Reine"]},
    {"type": "heure_proposee", "texte": PHRASE, "heure": "18:00"},
    {"type": "etape", "texte": PHRASE, "article_en_question": "Menu midi"},
    {"type": "reprise", "texte": PHRASE},
    {"type": "numero_affiche", "texte": PHRASE},
]


@pytest.mark.parametrize("question", QUESTIONS_DE_LA_COMMANDE, ids=lambda q: q["type"])
def test_commande_la_phrase_de_secours_n_est_pas_dans_l_etat(question):
    assert PHRASE not in _etat_de_la_commande(question)


def test_commande_l_ambiguite_donne_ses_candidats_en_faits_bruts():
    etat = _etat_de_la_commande({"type": "ambiguite", "texte": PHRASE, moteur.CLE_CANDIDATS: [{"libelle": "Regina", "id": 1}, {"libelle": "Reine", "id": 2}]})
    assert "(précision) : Regina ; Reine ;" in etat, etat


def test_commande_la_variante_donne_l_article_en_question():
    assert "(variante) : Regina ;" in _etat_de_la_commande({"type": "variante", "texte": PHRASE, "article_en_question": "Regina"})


@pytest.mark.parametrize("type_", sorted(QUESTIONS_DITES_PAR_LE_CODE))
def test_commande_une_question_dite_par_le_code_garde_son_texte(type_):
    assert PHRASE in _etat_de_la_commande({"type": type_, "texte": PHRASE})


def test_reservation_la_phrase_de_secours_du_choix_n_est_pas_dans_l_etat():
    assert PHRASE not in _etat_de_la_reservation({"type": "choix", "texte": PHRASE, "candidats_dits": ["jeudi à 19 h"]})


@pytest.mark.parametrize("type_", sorted(QUESTIONS_DITES_PAR_LE_CODE & {"recapitulatif", "annulation"}))
def test_reservation_une_question_dite_par_le_code_garde_son_texte(type_):
    assert PHRASE in _etat_de_la_reservation({"type": type_, "texte": PHRASE})

"""[.mark] Lot 7c : les rouges du passage des combinaisons longues sur la chaîne ``16fe7cc1``, un test court par cause (jamais la seule combinaison longue)."""

from __future__ import annotations

from api.services.actions_communes import table_de_parole as T
from api.services.actions_communes import conversation as CONV
from api.services.actions_communes.du import RIEN_CHANGE
from api.services.actions_communes.parole import A_DIRE_SEUL, QUESTION_DEJA_DONNEE, SUFFIXE, EtatDuTour
from api.services.phrases.catalogue import REPONSE_PERDUE

QUESTION_NEE = {"lignes": [{}], CONV.CLE: {CONV.CLE_QUESTION: {"id": "Q-1", "type": "heure_proposee", "nee_au_tour": 3, "texte": ""}}}


def _joue(retour: dict, phrase: str, textes: dict | None = None, **etat):
    e = EtatDuTour(tour=3, **etat)
    entrees = T.entrees_du_retour(retour, phrase, e, [], QUESTION_NEE, textes or {}, None, None)
    return T.decider(entrees)


def test_rc4_la_question_deja_donnee_et_une_fiche_qui_ne_change_rien_apres_la_relance_est_une_relance_ratee():
    """T12 (coordinateur 26/11 10 h 45) : la fiche rejouée qui ne change rien, une fois la relance du tour faite, est une relance ratée, même quand la question née dans ce tour a
    déjà été donnée au modèle. Client (fermé, « je vous la prépare pour dix-huit heures ? » posée) : le modèle rejoue deux fois la même fiche / avant : « C'est noté. » seul, rien
    n'est noté / après : la suite réglée gardée, sinon P3."""
    d = _joue({RIEN_CHANGE: True}, "C'est noté.", question_donnee="Q-1", relance_du_fait=True)
    assert (d.mode, d.a_dire, d.motif) == (A_DIRE_SEUL, None, REPONSE_PERDUE)
    d = _joue({RIEN_CHANGE: True}, "C'est noté.", {"suffixe": "Puis-je faire autre chose pour vous ?"}, question_donnee="Q-1", relance_du_fait=True)
    assert (d.mode, d.a_dire, d.motif) == (A_DIRE_SEUL, "Puis-je faire autre chose pour vous ?", SUFFIXE)


def test_rc4_la_question_deja_donnee_que_la_phrase_pose_reste_dite():
    """Le cas voisin ne bouge pas : la phrase du modèle pose la question déjà donnée, elle est dite (une question, en dernier)."""
    d = _joue({RIEN_CHANGE: True}, "On vous la prépare pour la réouverture, ça vous va ?", question_donnee="Q-1", relance_du_fait=True)
    assert (d.mode, d.motif) == (A_DIRE_SEUL, QUESTION_DEJA_DONNEE)

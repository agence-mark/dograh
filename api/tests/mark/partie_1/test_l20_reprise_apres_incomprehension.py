"""Lot 20 (Evan, 21/11 : « l'agent dit "je n'ai pas compris", puis reprend ce qu'il faisait ») : un tour où rien n'a changé (aucune fiche) alors qu'une question
attend : la phrase du modèle est suivie de la question en attente, dite par le code ; sauf si sa phrase pose déjà une question (une question à la fois).
Critère sur l'état du tour et la forme de la phrase, jamais sur ses mots."""

from api.services.actions_communes import parole as PA
from api.services.actions_communes import conversation as CONV

QUESTION = {"id": "Q-2", "type": "relecture", "texte": "Je vous relis : deux Margherita Normale, à emporter. C'est bon ?"}
RELECTURE = {"lignes": [{"n": 1}], "mode": "emporter", CONV.CLE: {CONV.CLE_QUESTION: QUESTION}}


def test_apres_une_phrase_sans_rien_changer_la_question_en_attente_est_reposee():
    etat = PA.EtatDuTour(tour=3)
    assert PA.reprise_apres_la_phrase("Ça, je ne peux pas le faire, je suis désolée.", etat, RELECTURE) == QUESTION["texte"]


def test_pas_de_reprise_si_la_phrase_pose_deja_une_question_ou_si_une_fiche_a_joue():
    assert PA.reprise_apres_la_phrase("Pardon, vous pouvez répéter ?", PA.EtatDuTour(tour=3), RELECTURE) is None
    assert PA.reprise_apres_la_phrase("C'est noté.", PA.EtatDuTour(tour=3, fiches=1), RELECTURE) is None
    assert PA.reprise_apres_la_phrase("Je ne peux pas.", PA.EtatDuTour(tour=3), {"lignes": []}) is None

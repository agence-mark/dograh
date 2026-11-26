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


async def test_rc4_c_est_tout_redonne_l_heure_proposee_au_modele(faire_monde, monkeypatch):
    """n° 45 (aparté d'Evan 20/11) : « c'est tout » quand la relecture attend l'heure proposée la redonne dans ce tour ; depuis C7 B3 (la même question par sa structure, plus par son
    texte), elle ne renaissait plus. Client (fermé) « Une regina. » puis « C'est tout. » / avant : « C'est noté. » seul, l'heure n'est plus demandée / après : le modèle repasse avec la
    question de l'heure, née dans ce tour."""
    from api.services.actions_communes.parole import SECOND_PASSAGE
    from api.tests.mark.partie_1 import combinaisons as C

    monde = await faire_monde("casa-italia")
    with C.horloge.remplacer(monde.base, C.FERMETURE):
        partie = C.Partie(monde, monkeypatch)
        assert await partie.recette("E9")
        await partie.geste("G1")
        o = await partie.geste("G20")
    q = C.question(o.apres)
    assert q.get("type") == "heure_proposee" and q.get("nee_au_tour") == CONV.de(o.apres).get("tour_de_l_appel"), q
    assert o.decision.mode == SECOND_PASSAGE, o.decision


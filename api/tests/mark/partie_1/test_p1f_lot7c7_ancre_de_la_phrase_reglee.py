"""[.mark] C7 (a), point de l'audit de C6 (troisième passage) : « la question qui portait la phrase réglée » se lit sur UNE ancre, l'identité de la question (son numéro, son
type, son objet : ``CONV.identite_de_la_question``) posée par la table avec la phrase ; plus sur trois signes (la question donnée, son texte dans la phrase, le jeton à entendre),
dont un lisait l'identité par le texte (refus 4, C5 § 1.3).

Client « Ah, et une margherita aussi. » juste après la relecture (même tour) / avant : la relecture reposée garde son numéro, la question donnée « attendait toujours » et l'ancien
total suivait la phrase du modèle / après : la relecture reposée a un autre jeton, donc une autre identité : l'ancien total est jeté.
"""

from __future__ import annotations

from api.services.actions_communes import conversation as CONV
from api.services.actions_communes import parole as P
from api.services.actions_communes.parole import SECOND_PASSAGE, EtatDuTour

ANCIEN = "Cela fait dix euros quatre-vingt-dix, c'est bon pour vous ?"
NUMERO = "Je note le zéro six, douze, trente-quatre, cinquante-six, soixante-dix-huit, c'est bon ?"


def _dossier(q: dict) -> dict:
    p = {"lignes": [{}]}
    CONV.poser_question(p, {**q, "nee_au_tour": 3})
    return p


def _deux_passages(premiere: dict, seconde: dict, suffixe: str) -> EtatDuTour:
    """Passage 1 : la question naît, sa phrase réglée est posée ; passage 2 : une fiche qui change quelque chose, ``seconde`` attend."""
    etat = EtatDuTour(tour=3)
    d = P._decision_du_tour({"question": premiere}, "Très bien.", etat, [], _dossier(premiere), None, {"suffixe": suffixe}, True)
    assert d.mode == SECOND_PASSAGE and etat.suffixe == suffixe, (d, etat)
    P._decision_du_tour({}, "Très bien.", etat, [], _dossier(seconde), None, {}, True)
    return etat


def test_la_relecture_reposee_sous_le_meme_numero_jette_l_ancien_total():
    relecture = {"id": "Q-4", "type": "relecture", "texte": "", "jeton": "j1"}
    etat = _deux_passages(relecture, {**relecture, "jeton": "j2"}, ANCIEN)
    assert etat.suffixe is None, etat.suffixe


def test_voisin_la_meme_question_attend_la_phrase_reglee_tient():
    relecture = {"id": "Q-4", "type": "relecture", "texte": "", "jeton": "j1"}
    etat = _deux_passages(relecture, relecture, ANCIEN)
    assert etat.suffixe == ANCIEN, etat.suffixe


def test_voisin_une_autre_question_au_meme_texte_ne_porte_pas_la_phrase():
    """Le texte d'une question que le code dit (DC10) n'est pas son identité : une autre question au même texte n'est pas celle qui portait la phrase."""
    dc10 = {"id": "Q-2", "type": "numero_dicte", "texte": NUMERO}
    etat = _deux_passages(dc10, {**dc10, "id": "Q-5"}, NUMERO)
    assert etat.suffixe is None, etat.suffixe


def test_voisin_la_question_dc10_qui_attend_toujours_garde_sa_phrase():
    dc10 = {"id": "Q-2", "type": "numero_dicte", "texte": NUMERO}
    etat = _deux_passages(dc10, dc10, NUMERO)
    assert etat.suffixe == NUMERO, etat.suffixe

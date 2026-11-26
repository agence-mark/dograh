"""[.mark] C7 B3 : les questions que le modèle dit n'ont plus de texte de secours ; leur identité se lit dans leur structure.

Décisions d'Evan 25/11 (8 h 45, 9 h) : le code ne compose aucune phrase, le modèle pose la question avec ses mots ; « pas juste une suppression » (10 h) : ce que le texte
apprenait (les candidats, le groupe à choisir) reste dans la question donnée au modèle. Refus 11 : deux « laquelle ? » sur des objets différents restent deux questions ;
audit du lot A de C7 : deux ``CHOIX_OBLIGATOIRE`` de la base sur deux groupes, à deux tours, ne se confondent plus par leur texte (vide pour les deux).
"""

from __future__ import annotations

from api.services.actions_communes import conversation as CONV
from api.services.actions_communes.repli import question_pour_la_relance
from api.services.commande import panier as P
from api.services.commande import porte
from api.services.commande import registre as RQ
from api.services.commande.resultat import Resultat

TOUR = "tour_de_l_appel"


def test_b3_une_ambiguite_nee_d_un_refus_n_a_plus_de_texte_et_garde_ses_candidats():
    """Client « Une reine. » (Regina ou Reine) : la question au registre n'a plus le texte « Vous voulez dire… » ; la relance garde les candidats."""
    r = Resultat("AMBIGU", {"candidats": ["Regina", "Reine"], "dit": "reine"}, "Vous voulez dire Regina ou Reine ?")
    q = porte._question_de(r, 1, 1)
    assert q["texte"] == "", q
    assert question_pour_la_relance(q)["choix"] == ["Regina", "Reine"]


def test_b3_voisin_le_numero_dicte_que_le_code_dit_garde_son_texte():
    """Voisin : la question du numéro dicté (``QUESTIONS_DITES_PAR_LE_CODE``, M108) garde son texte, dit par le code."""
    r = Resultat("INCOMPLETE", {}, "Je note le zéro six, douze, trente-quatre, cinquante-six, soixante-dix-huit, c'est bon ?", "confirmer_numero_dicte")
    assert porte._question_de(r, 1, 1)["texte"].startswith("Je note")


def _choix_de_la_base(groupe: str, nom: str, tour: int) -> dict:
    """La question née d'un ``CHOIX_OBLIGATOIRE`` de la base (``restauration_commande.py``, ``_refus`` : ni texte ni manque)."""
    return porte._question_de(Resultat("CHOIX_OBLIGATOIRE", {"groupe": groupe, "nom": nom, "minimum": 1}, ""), tour, tour)


def test_b3_deux_choix_obligatoires_de_la_base_sur_deux_groupes_sont_deux_questions():
    """Deux naissances : la sauce au tour 1, la boisson au tour 2 (aucune ligne n'attend au panier) : deux objets au registre ; avant, le même (« variante: »)."""
    p = P.nouveau()
    CONV.de(p)[TOUR] = 1
    sauce = _choix_de_la_base("G-SAUCE", "Sauce", 1)
    RQ.ouvrir(p, sauce)
    CONV.de(p)[TOUR] = 2
    boisson = _choix_de_la_base("G-BOISSON", "Boisson", 2)
    assert RQ.objet(boisson, p) != RQ.objet(sauce, p), (RQ.objet(boisson, p), RQ.objet(sauce, p))
    assert CONV.identite_de_la_question({**sauce, "id": None}) != CONV.identite_de_la_question({**boisson, "id": None})


def test_b3_voisin_le_meme_groupe_redonne_est_la_meme_question():
    """Voisin : le même groupe redonné au tour suivant reste la même question (pas née une seconde fois, RC3)."""
    p = P.nouveau()
    CONV.de(p)[TOUR] = 1
    RQ.ouvrir(p, _choix_de_la_base("G-SAUCE", "Sauce", 1))
    CONV.de(p)[TOUR] = 2
    encore = _choix_de_la_base("G-SAUCE", "Sauce", 2)
    RQ.ouvrir(p, encore)
    assert RQ.est_deja_ouverte(p, {**encore, "nee_au_tour": 1})
    assert (CONV.de(p)[RQ.CLE_DES_QUESTIONS][RQ.objet(encore, p)])["nee_au_tour"] == 1

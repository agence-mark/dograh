"""[.mark] Lot 7b-C7, A5 (point C5) : la valeur de ce qui manque, que la relance du modèle reçoit, se choisit dans une liste fermée, jamais selon qu'une phrase existe.

``valeur_du_manque`` (commande et réservation) rendait la valeur seulement quand le catalogue avait une phrase pour elle : vider le catalogue (lot B) aurait fait taire la
relance. La commande rend toute valeur sauf celles qu'une question porte (la variante, l'accord) et le mode sans mode ouvert ; la réservation lit sa liste fermée.
"""

from __future__ import annotations

import pytest

from api.services.commande import etat_pour_le_modele as ETAT_COMMANDE
from api.services.commande import panier as P
from api.services.commande import phrases_du_manque as PM
from api.services.commande.phrases_du_manque import Manque
from api.services.reservation import etat_pour_le_modele as ETAT_RESERVATION
from api.services.reservation import phrases_du_manque as PMR

DITES = [m for m in Manque if m not in (Manque.VARIANTE, Manque.ACCORD)]
MANQUES_DE_LA_RESERVATION = ["le nombre de personnes", "le jour", "l'heure", "le nom", "le numéro de téléphone", "le nom et le jour de sa réservation d'avant"]


def _commande(monkeypatch, manque: Manque, modes: list[str]) -> str | None:
    monkeypatch.setattr(ETAT_COMMANDE, "ce_qui_manque", lambda p, connu: (manque, modes))
    return PM.valeur_du_manque(P.nouveau())


@pytest.mark.parametrize("manque", DITES, ids=lambda m: m.name)
def test_commande_la_valeur_sort_meme_sans_aucune_phrase_au_catalogue(monkeypatch, manque):
    assert _commande(monkeypatch, manque, ["à emporter", "en livraison"]) == manque.value


@pytest.mark.parametrize("manque", [Manque.VARIANTE, Manque.ACCORD], ids=lambda m: m.name)
def test_commande_une_valeur_portee_par_une_question_ne_sort_pas(monkeypatch, manque):
    assert _commande(monkeypatch, manque, ["à emporter"]) is None


def test_commande_le_mode_sans_mode_ouvert_ne_sort_pas(monkeypatch):
    assert _commande(monkeypatch, Manque.MODE, []) is None


def test_commande_une_question_qui_attend_passe_avant(monkeypatch):
    monkeypatch.setattr(PM.CONV, "question_de", lambda p: {"id": "Q-1"})
    assert _commande(monkeypatch, Manque.ARTICLES, []) is None


@pytest.mark.parametrize("manque", MANQUES_DE_LA_RESERVATION)
def test_reservation_la_valeur_sort_meme_sans_aucune_phrase_au_catalogue(monkeypatch, manque):
    monkeypatch.setattr(ETAT_RESERVATION, "ce_qui_manque_ensuite", lambda etat, affiche: manque)
    assert PMR.valeur_du_manque({}) == manque


@pytest.mark.parametrize("manque", [None, "la relecture"])
def test_reservation_une_valeur_hors_de_la_liste_ne_sort_pas(monkeypatch, manque):
    monkeypatch.setattr(ETAT_RESERVATION, "ce_qui_manque_ensuite", lambda etat, affiche: manque)
    assert PMR.valeur_du_manque({}) is None


def test_reservation_la_liste_fermee_est_celle_de_l_etat():
    """La liste lue par ``valeur_du_manque`` est exactement ce que l'état peut rendre (``ce_qui_manque_ensuite``), le jour compris par sa constante."""
    assert ETAT_RESERVATION.LE_JOUR in PMR.VALEURS_DU_MANQUE and set(PMR.VALEURS_DU_MANQUE) == set(MANQUES_DE_LA_RESERVATION)


ETATS_DE_LA_RESERVATION = [
    ({"recherche": True}, True), ({}, True), ({"brouillon": {"personnes": 2}}, True), ({"brouillon": {"personnes": 2, "jour": "samedi"}}, True),
    ({"brouillon": {"personnes": 2, "jour": "samedi", "heure": "20h"}}, True), ({"brouillon": {"personnes": 2, "jour": "samedi", "heure": "20h", "prenom": "Alice"}}, False),
]


def test_reservation_les_valeurs_sont_les_constantes_du_module_d_etat():
    """Audit du lot A de C7 (A5) : ``VALEURS_DU_MANQUE`` ne recopie plus les mots de l'état ; elle lit ses constantes (une seule écriture), et chaque valeur que l'état rend en est une."""
    assert PMR.VALEURS_DU_MANQUE == frozenset(ETAT_RESERVATION.MANQUES)
    rendues = [ETAT_RESERVATION.ce_qui_manque_ensuite(etat, affiche) for etat, affiche in ETATS_DE_LA_RESERVATION]
    assert rendues == list(ETAT_RESERVATION.MANQUES[-1:] + ETAT_RESERVATION.MANQUES[:-1]), rendues

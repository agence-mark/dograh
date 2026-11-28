"""[.mark] Partie 1, lot 8a (T1) : la famille de phrase d'attente d'un geste se lit sur l'action et les cases remplies, jamais sur les mots.

Écrit avant de toucher au rangement (8a, 8c) : il fige ce que ``famille_de_la_case`` rend aujourd'hui, case par case. Depuis 8c-2 (128) la fonction vit dans ``restauration/attentes.py``.
"""

from __future__ import annotations

import pytest

from api.services.outils_mark import attente_par_case as MECANISME
from api.services.restauration import attentes as AT


@pytest.mark.parametrize(
    "action, arguments, attendue",
    [
        ("lire", {}, AT.LECTURE),
        ("lire", {"sujet": "x"}, AT.LECTURE),
        ("retrouver_une_reservation", {}, AT.RESERVATION),
        ("fiche", {"retrouver_une_reservation_enregistree": True}, AT.RESERVATION),
        ("fiche", {"c_est_tout": True}, AT.ENREGISTREMENT),
        ("fiche", {"reponse": {"sens": "oui"}, "moyen_de_paiement": "carte"}, AT.ENREGISTREMENT),
        ("fiche", {"adresse": "3 rue de Paris"}, AT.ZONE),
        ("fiche", {"commune": "Beauvais"}, AT.ZONE),
        ("fiche", {"c_est_tout": True, "adresse": "3 rue de Paris"}, AT.ENREGISTREMENT),  # l'enregistrement passe devant la zone
    ],
)
def test_chaque_case_a_sa_famille(action, arguments, attendue):
    assert AT.famille_de_la_case(action, arguments) == attendue


@pytest.mark.parametrize(
    "action, arguments",
    [
        ("fiche", {}),
        ("fiche", {"reponse": {"sens": "oui"}}),  # une réponse sans moyen de paiement n'est pas l'enregistrement
        ("fiche", {"ajouter": [{"nom": "x"}]}),
        ("autre_action", {"adresse": "3 rue de Paris"}),  # une adresse hors de la fiche ne porte pas la famille
        (None, {}),
        ("fiche", None),
        ("fiche", "pas un dictionnaire"),
    ],
)
def test_une_case_sans_famille_rend_rien(action, arguments):
    assert AT.famille_de_la_case(action, arguments) is None


def test_chaque_famille_rendue_a_ses_phrases_et_une_case_sans_famille_garde_la_config():
    for famille in (AT.LECTURE, AT.ZONE, AT.RESERVATION, AT.ENREGISTREMENT):
        assert AT.familles()[famille]
    config = {"phrases_attente": ["Un instant."]}
    assert MECANISME.config_avec_l_attente(config, "commande", "fiche", {}) == config
    assert MECANISME.config_avec_l_attente(config, "commande", "lire", {})["phrases_attente"] == AT.familles()[AT.LECTURE]

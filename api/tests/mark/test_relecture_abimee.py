"""[.mark] Chantier modules-et-cerveaux, lot 4 (M6) : la correction des numéros relus élargie.

Pourquoi : run vocal 1462 (18/10). L'agent relit « zéro sept, cinquante, quatre-vingt-cinq,
sept-huit, deux » pour 0750857872, trois fois. Moins de dix chiffres et des mots non lus
(« sept-huit ») : le module des nombres n'y voit plus un téléphone, la correction d'avant ne
s'appliquait pas. Une suite de nombres consécutifs proche du numéro de référence est
maintenant remplacée par lui, en lettres si l'agent écrivait en lettres.
"""

import pytest

from api.services.pipecat.relecture_numeros import corriger_relecture

REFERENCE = "0750857872"
CONTEXTE = {"nombres_lus": [{"type": "telephone", "ecrit": "07/50/857872"}]}


def test_la_relecture_du_1462_est_corrigee_en_lettres():
    phrase = "Je relis : zéro sept, cinquante, quatre-vingt-cinq, sept-huit, deux. C'est bien ça ?"
    assert corriger_relecture(phrase, REFERENCE, CONTEXTE) == (
        "Je relis : zéro sept, cinquante, quatre-vingt-cinq, soixante-dix-huit, soixante-douze."
        " C'est bien ça ?"
    )


def test_une_relecture_abimee_en_chiffres_est_corrigee_en_chiffres():
    assert corriger_relecture("Le 07 50 85 78 2, c'est ça ?", REFERENCE, CONTEXTE) == (
        "Le 07 50 85 78 72, c'est ça ?"
    )


@pytest.mark.parametrize(
    "phrase",
    [
        "Je relis : zéro sept, cinquante, quatre-vingt-cinq, soixante-dix-huit, soixante-douze.",
        "Le 07 50 85 78 72, c'est ça ?",
    ],
)
def test_une_relecture_juste_nest_pas_touchee(phrase):
    assert corriger_relecture(phrase, REFERENCE, CONTEXTE) == phrase


@pytest.mark.parametrize(
    "phrase",
    [
        # Un autre numéro : plus de deux écarts.
        "Le magasin, c'est le zéro trois, quarante-quatre, vingt-deux, dix, soixante.",
        "Rappelez le 03 44 22 10 6.",
        # Trop court pour être une relecture.
        "Vers sept heures, cinquante minutes.",
        # Un montant, un code postal : jamais.
        "Ça fait zéro sept cinquante euros, au 60200.",
    ],
)
def test_ni_un_autre_numero_ni_un_montant_ni_un_code_postal(phrase):
    assert corriger_relecture(phrase, REFERENCE, CONTEXTE) == phrase


def test_jamais_un_numero_que_lappelant_a_dicte():
    contexte = {
        "nombres_lus": [
            {"type": "telephone", "ecrit": "0750857802"},
            {"type": "telephone", "ecrit": "0750857872"},
        ]
    }
    # « 07 50 85 78 02 » est un numéro dicté : jamais remplacé.
    phrase = "Le 07 50 85 78 02, c'est ça ?"
    assert corriger_relecture(phrase, REFERENCE, contexte) == phrase


def test_sans_reference_rien_ne_change():
    phrase = "Je relis : zéro sept, cinquante, quatre-vingt-cinq, sept-huit, deux."
    assert corriger_relecture(phrase, None, CONTEXTE) == phrase


# Revue du 18/10 : trois phrases que la première mesure abîmait.
@pytest.mark.parametrize(
    "phrase",
    [
        # Un autre numéro du même secteur : la suite commune le rapprochait du numéro.
        "Le magasin : zéro trois, quarante-quatre, cinquante, quatre-vingt-cinq, sept-huit.",
        # La phrase suivante commence par un nombre : le point arrête la relecture.
        "Je relis : zéro sept, cinquante, quatre-vingt-cinq, sept-huit, deux. 14 h 30, ça vous va ?",
    ],
)
def test_ni_le_numero_du_magasin_ni_la_phrase_suivante(phrase):
    corrige = corriger_relecture(phrase, REFERENCE, CONTEXTE)
    assert "soixante-douze h" not in corrige
    if phrase.startswith("Le magasin"):
        assert corrige == phrase
    else:
        assert corrige.endswith(". 14 h 30, ça vous va ?")


def test_un_nombre_en_chiffres_apres_la_relecture_en_lettres_reste_hors_du_numero():
    phrase = "Je relis : zéro sept, cinquante, quatre-vingt-cinq, sept-huit, deux, 2 personnes ?"
    assert corriger_relecture(phrase, REFERENCE, CONTEXTE) == (
        "Je relis : zéro sept, cinquante, quatre-vingt-cinq, soixante-dix-huit, soixante-douze,"
        " 2 personnes ?"
    )

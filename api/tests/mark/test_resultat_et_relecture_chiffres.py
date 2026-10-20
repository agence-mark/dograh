"""[.mark] Chantier fiabilite-orchestration, lot 7 (R4, R16) : le résultat nettoyé et la relecture rattrapée.

R4, run 1468 : le cerveau de fond répond en markdown (« **Résultat** : … »), le cerveau de
conversation l'imite et la voix lit les astérisques. Le résultat est remis en texte simple.
R16, run 1466 : le modèle relit « sept, sept, huit, cinq, deux, sept, trois, quatre, neuf » pour
0778527349 (le zéro manque) ; la correction des relectures abîmées ne le rattrapait pas.

| Test | La garantie |
|---|---|
| markdown | gras, italique, titres, puces, liens, accents graves retirés ; mots, sens et ordre gardés |
| crochets | les crochets du résultat restent des parenthèses (lot 6 d'avant) |
| route | le résultat qui entre dans la conversation est en texte simple |
| 1466 | la phrase exacte du run est corrigée par paires en lettres |
| chiffres | la même relecture en chiffres est corrigée en chiffres |
| intacts | une relecture juste, un autre numéro, un numéro dicté, une suite trop courte : jamais touchés |
"""

import pytest

from api.services.pipecat.relecture_numeros import corriger_relecture
from api.services.travail.retour import (
    PREFIXE_RESULTAT_DU_TRAVAIL,
    message_du_resultat,
    sans_mise_en_forme,
)

REFERENCE = "0778527349"
CONTEXTE = {"nombres_lus": [{"type": "telephone", "ecrit": "07 78 52 73 49"}]}


# --- R4 : le markdown ------------------------------------------------------------


def test_le_resultat_du_1468_est_remis_en_texte_simple():
    assert sans_mise_en_forme("**Résultat** : *jeudi 22 octobre* est libre") == (
        "Résultat : jeudi 22 octobre est libre"
    )


def test_titres_puces_liens_et_accents_graves():
    brut = "## Résultat\n- **Manque** : l'adresse\n* le contrat\n> note\n[la fiche](http://x.fr) et `code`"
    assert sans_mise_en_forme(brut).split("\n") == [
        "Résultat",
        "Manque : l'adresse",
        "le contrat",
        "note",
        "la fiche et code",
    ]


def test_la_phrase_d_attente_en_italique_perd_ses_asterisques():
    assert sans_mise_en_forme("*(Un instant…)* Voici") == "(Un instant…) Voici"


@pytest.mark.parametrize(
    "texte",
    ["Rendez-vous jeudi à 10 h, 3 * 4 = 12 n'est pas du texte", "un_nom_de_champ reste", "100 % sûr"],
)
def test_le_reste_du_texte_est_inchange_hors_asterisques(texte):
    assert sans_mise_en_forme(texte) == texte.replace("*", "")


def test_le_message_du_resultat_est_en_texte_simple_et_garde_les_parentheses():
    message = message_du_resultat("**Résultat** : *confirmé* [voir] \n- **Manque** : rien")
    assert message == f"{PREFIXE_RESULTAT_DU_TRAVAIL} Résultat : confirmé (voir) Manque : rien]"
    assert "*" not in message


def test_un_resultat_vide_reste_vide():
    assert "**" not in message_du_resultat("****")


# --- R16 : les chiffres dits un par un -------------------------------------------


def test_la_relecture_du_1466_est_corrigee_par_paires_en_lettres():
    phrase = "Donc votre numéro est sept, sept, huit, cinq, deux, sept, trois, quatre, neuf, c'est bien ça ?"
    assert corriger_relecture(phrase, REFERENCE, CONTEXTE) == (
        "Donc votre numéro est zéro sept, soixante-dix-huit, cinquante-deux, soixante-treize,"
        " quarante-neuf, c'est bien ça ?"
    )


def test_un_chiffre_faux_dit_un_par_un_est_corrige_aussi():
    phrase = "Le zéro, sept, sept, huit, cinq, deux, sept, trois, quatre, huit. Correct ?"
    assert corriger_relecture(phrase, REFERENCE, CONTEXTE) == (
        "Le zéro sept, soixante-dix-huit, cinquante-deux, soixante-treize, quarante-neuf. Correct ?"
    )


def test_la_meme_relecture_en_chiffres_est_corrigee_en_chiffres():
    assert corriger_relecture("Donc 7, 7, 8, 5, 2, 7, 3, 4, 9, c'est bien ça ?", REFERENCE, CONTEXTE) == (
        "Donc 07 78 52 73 49, c'est bien ça ?"
    )


@pytest.mark.parametrize(
    "phrase",
    [
        # Une relecture juste, zéro compris.
        "Le zéro, sept, sept, huit, cinq, deux, sept, trois, quatre, neuf. Correct ?",
        "Le 0, 7, 7, 8, 5, 2, 7, 3, 4, 9. Correct ?",
        # Un autre numéro : plus de deux écarts.
        "Le magasin, c'est le zéro, trois, quatre, quatre, deux, deux, un, zéro, six.",
        # Trop court pour une relecture.
        "Un, deux, trois.",
        "Pour la première, deuxième, troisième fois",
    ],
)
def test_une_relecture_juste_un_autre_numero_une_suite_courte_ne_sont_pas_touches(phrase):
    assert corriger_relecture(phrase, REFERENCE, CONTEXTE) == phrase


def test_un_numero_dicte_par_l_appelant_n_est_jamais_corrige():
    # L'appelant a dicté un fixe à un chiffre près du mobile : relire le fixe ne fait pas dire le mobile.
    contexte = {
        "nombres_lus": [
            {"type": "telephone", "ecrit": "07 78 52 73 49"},
            {"type": "telephone", "ecrit": "07 78 52 73 48"},
        ]
    }
    phrase = "Le zéro, sept, sept, huit, cinq, deux, sept, trois, quatre, huit. Correct ?"
    assert corriger_relecture(phrase, REFERENCE, contexte) == phrase

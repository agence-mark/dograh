"""[.mark] Non-regression test: a spelled brand is never written as a person's name (L5).

The questions this file answers:

    When the caller spells a term of the vocabulary (« c'est un M C Z »), does
    the record refuse to write it in a field with no reader (the name), and
    keep the name already there? Is it written as the official term in a brand
    field? Does a name spelled that is NOT a term still go in? Is a letter
    heard wrong (« P A L A Z E T T I ») still recognised, and two short
    sequences close by chance not? And, without the record, does the note to the
    model say the letters are the term, never the person's name?

Why it exists
-------------
Plan « le lexique » (2026-09-26), L5 / Q6, question 216 of the labo: run 803,
« c'est un M C Z » turned the record's ``nom`` from « Caron » into « Mcz ».

⚠️ The call's own route is proven in ``test_traversants_appel.py``
(``test_une_marque_epelee_ne_remplace_pas_le_nom``).
"""

import pytest

from api.schemas.fiche_agent import ChampFiche
from api.schemas.lexique_metier import LexiqueMetier
from api.services.epellation.lecture import lire
from api.services.epellation.mention import mentionner_epellations
from api.services.lexique.epellation import formes_des_termes, terme_epele
from api.services.pipecat.lecture_appelant import _trace_epellation
from api.services.workflow.fiche_au_fil_de_leau import ReglagesFiche, ecrire_dans_la_fiche

LEXIQUE = LexiqueMetier.model_validate(
    {
        "termes": [
            {"terme": "MCZ", "categorie": "marque"},
            {"terme": "Palazzetti", "categorie": "marque"},
            {"terme": "Jøtul", "variantes": ["Jotul"], "categorie": "marque"},
            {"terme": "ramonage", "type": "mot"},
        ]
    }
)
TERMES = formes_des_termes(LEXIQUE)
REGLAGES = ReglagesFiche(
    champs=(ChampFiche(nom="nom"), ChampFiche(nom="marque")), termes_du_lexique=TERMES
)


def _fiche_apres(phrase: str, **deja) -> dict:
    """The record once the spelling reader has read ``phrase`` (its trace), like a call."""
    return {
        "epellations_lues": [
            {"etape": "accueil", "entendu": e.entendu, "epele": e.epele, "tour": 1} for e in lire(phrase)
        ],
        **deja,
    }


def test_la_phrase_reelle_du_run_803_ne_touche_pas_au_nom():
    phrase = "c'est un M C Z"
    fiche = _fiche_apres(phrase, nom="Caron")
    verdict = ecrire_dans_la_fiche(fiche, REGLAGES, "nom", "MCZ", paroles=["je m'appelle Caron", phrase])
    assert (verdict.statut, verdict.raison) == ("refuse", "terme_du_lexique_epele")
    assert fiche["nom"] == "Caron"


def test_la_meme_epellation_va_dans_la_marque_sous_son_ecriture_officielle():
    phrase = "c'est un M C Z"
    fiche = _fiche_apres(phrase)
    verdict = ecrire_dans_la_fiche(fiche, REGLAGES, "marque", "Mcz", paroles=[phrase])
    assert verdict.statut == "ecrit"
    assert fiche["marque"] == "MCZ"


def test_un_champ_qui_nest_pas_un_nom_recoit_le_terme():
    """Relecture du 26/09 : Q6 vise le nom ; un champ `modele` sans lecteur garde la marque."""
    reglages = ReglagesFiche(champs=(ChampFiche(nom="modele"),), termes_du_lexique=TERMES)
    phrase = "c'est un M C Z"
    fiche = _fiche_apres(phrase)
    assert ecrire_dans_la_fiche(fiche, reglages, "modele", "MCZ", paroles=[phrase]).statut == "ecrit"


def test_un_champ_de_quantite_nest_pas_un_nom():
    reglages = ReglagesFiche(champs=(ChampFiche(nom="nombre_appareils"),), termes_du_lexique=TERMES)
    phrase = "c'est un M C Z"
    fiche = _fiche_apres(phrase)
    verdict = ecrire_dans_la_fiche(fiche, reglages, "nombre_appareils", "MCZ", paroles=[phrase])
    assert verdict.raison != "terme_du_lexique_epele"


@pytest.mark.parametrize("champ", ["prenom", "nom_client"])
def test_un_autre_champ_de_nom_refuse_aussi(champ):
    reglages = ReglagesFiche(champs=(ChampFiche(nom=champ),), termes_du_lexique=TERMES)
    phrase = "c'est un M C Z"
    fiche = _fiche_apres(phrase)
    assert ecrire_dans_la_fiche(fiche, reglages, champ, "MCZ", paroles=[phrase]).raison == "terme_du_lexique_epele"


def test_un_nom_epele_qui_nest_pas_une_marque_secrit_toujours():
    phrase = "je m'appelle Caron, C A R O N"
    fiche = _fiche_apres(phrase)
    verdict = ecrire_dans_la_fiche(fiche, REGLAGES, "nom", "CARON", paroles=[phrase])
    assert verdict.statut == "ecrit"
    assert fiche["nom"].lower() == "caron"


@pytest.mark.parametrize(
    "epele,attendu",
    [
        ("MCZ", "MCZ"),
        ("mcz", "MCZ"),
        ("Palazetti", "Palazzetti"),  # one letter heard once instead of twice
        ("JOTUL", "Jøtul"),  # through its other spelling
        ("RAMONAGE", "ramonage"),
        ("CARON", None),
        ("MCC", None),  # short: an exact match only
        ("", None),
    ],
)
def test_ce_que_des_lettres_epellent(epele, attendu):
    assert terme_epele(epele, TERMES) == attendu


def test_sans_lexique_rien_nest_une_marque():
    assert terme_epele("MCZ", {}) is None
    assert terme_epele("MCZ", None) is None


def test_sans_fiche_la_note_dit_que_cest_le_terme_jamais_le_nom():
    phrase = "c'est un M C Z"
    epellations = lire(phrase)
    note = mentionner_epellations(phrase, epellations, TERMES)
    assert "c'est « MCZ » (lexique de l'entreprise) : ce n'est jamais le nom de la personne" in note
    assert "Note exactement ces lettres" not in note
    # A name spelled keeps the note of before, word for word.
    autre = mentionner_epellations("C A R O N", lire("C A R O N"), TERMES)
    assert "Note exactement ces lettres, sans les corriger" in autre


def test_la_trace_de_lepellation_nomme_le_terme():
    epellation = lire("c'est un M C Z")[0]
    assert _trace_epellation(epellation, "accueil", TERMES)["terme_du_lexique"] == "MCZ"
    assert "terme_du_lexique" not in _trace_epellation(lire("C A R O N")[0], "accueil", TERMES)

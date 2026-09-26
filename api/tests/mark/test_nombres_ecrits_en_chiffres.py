"""[.mark] Non-regression test: numbers the transcription wrote in digits (N1).

The questions this file answers:

    When the transcription writes a number in digits (« 60000 », « 06 12 34 56
    78 », « +33 6… », « 06.12.34.56.78 », « 3500€ », « 14bis », « n°14 »),
    is it classified as the same number said in words -- phone, amount, postal
    code, street number, reference? On the corpus of dictated numbers, does
    writing each expected number in digits give the same type and value as the
    words? And does nothing of a sentence without digits change?

Why it exists
-------------
Plan « le lexique » (2026-09-26), N1 / Q8, in preparation of Soniox (which
writes numbers in digits). Measured before this chantier: an international
phone in digits was an ordinary number, a phone with dots gave the model a
false « référence 06 » note, « 3500€ » and « 14bis » were not read at all.

⚠️ The call's own route is proven in ``test_traversants_appel.py``
(``test_un_telephone_ecrit_en_chiffres_arrive_au_modele_sans_fausse_reference``).
"""

import json
from pathlib import Path

import pytest

from api.services.communes.base import charger_base
from api.services.nombres.lecture import (
    CODE_POSTAL,
    MONTANT,
    REFERENCE,
    TELEPHONE,
    decoller_les_chiffres,
    lire_nombres,
)

DONNEES = Path(__file__).parent / "donnees"


@pytest.fixture(scope="module")
def base():
    return charger_base()


def _lus(texte: str, base) -> list[tuple[str, str]]:
    """(type, value without spaces) of every number, the way the reader gets the text."""
    return [
        (n.type, n.ecrit.replace(" ", "").replace("plus", "+"))
        for n in lire_nombres(decoller_les_chiffres(texte), base.par_cp, base.departements)
    ]


LETTRES_ET_CHIFFRES = {
    "telephone": (
        "mon numéro c'est 06 12 34 56 78",
        "mon numéro c'est zéro six douze trente-quatre cinquante-six soixante-dix-huit",
    ),
    "telephone-colle": (
        "mon numéro c'est 0612345678",
        "mon numéro c'est zéro six douze trente-quatre cinquante-six soixante-dix-huit",
    ),
    "telephone-a-points": (
        "mon numéro c'est 06.12.34.56.78",
        "mon numéro c'est zéro six douze trente-quatre cinquante-six soixante-dix-huit",
    ),
    "telephone-international": (
        "mon numéro c'est +33 6 12 34 56 78",
        "mon numéro c'est plus trente-trois six douze trente-quatre cinquante-six soixante-dix-huit",
    ),
    "telephone-international-colle": (
        "mon numéro c'est +33612345678",
        "mon numéro c'est plus trente-trois six douze trente-quatre cinquante-six soixante-dix-huit",
    ),
    "telephone-plus-en-mot": (
        "mon numéro c'est plus 33 6 12 34 56 78",
        "mon numéro c'est plus trente-trois six douze trente-quatre cinquante-six soixante-dix-huit",
    ),
    "code-postal": ("c'est 60000 Beauvais", "c'est soixante mille Beauvais"),
    "code-postal-groupe": ("c'est 60 100 Creil", "c'est soixante mille cent Creil"),
    "montant": ("le devis est de 3500 euros", "le devis est de trois mille cinq cents euros"),
    "montant-symbole-colle": ("le devis est de 3500€", "le devis est de trois mille cinq cents euros"),
    "numero-de-rue": ("j'habite au 14 rue de la gare", "j'habite au quatorze rue de la gare"),
    "numero-bis-colle": ("au 14bis rue de Paris", "au quatorze bis rue de Paris"),
    "numero-annonce": ("au n°14 rue de Paris", "au numéro quatorze rue de Paris"),
}


@pytest.mark.parametrize(
    "en_chiffres,en_lettres", list(LETTRES_ET_CHIFFRES.values()), ids=list(LETTRES_ET_CHIFFRES)
)
def test_en_chiffres_comme_en_lettres(base, en_chiffres, en_lettres):
    chiffres, lettres = _lus(en_chiffres, base), _lus(en_lettres, base)
    assert [t for t, _ in chiffres] == [t for t, _ in lettres]
    # The value too (a reference keeps its « n° » in digits: the words have none to keep).
    assert [v.removeprefix("n°") for _, v in chiffres] == [v for _, v in lettres]


def test_le_corpus_des_nombres_dictes_ecrit_en_chiffres(base):
    """Every number of the corpus with a known written form: the same type, the
    same value, written in digits in place of the words."""
    corpus = json.loads((DONNEES / "nombres_dictes.json").read_text("utf-8"))
    joues = 0
    for phrase in corpus["phrases"]:
        for nombre in phrase["nombres"]:
            attendu = nombre.get("ecrit") or nombre.get("code_attendu")
            entendu = nombre.get("entendu")
            if not attendu or not entendu or entendu not in phrase["phrase"]:
                continue
            joues += 1
            texte = phrase["phrase"].replace(entendu, attendu, 1)
            lus = [
                n
                for n in lire_nombres(decoller_les_chiffres(texte), base.par_cp, base.departements)
                if n.entendu.replace(" ", "") == attendu.replace(" ", "")
            ]
            assert lus, texte
            assert lus[0].type == nombre["type"], texte
            assert lus[0].ecrit.replace(" ", "") == attendu.replace(" ", "") or (
                nombre["type"] == CODE_POSTAL and attendu in lus[0].lectures_cp
            ), texte
    assert joues >= 13


def test_un_montant_a_decimales_reste_un_montant(base):
    assert _lus("ça fait 3 500,50 euros", base)[0] == (MONTANT, "3500")


@pytest.mark.parametrize(
    "texte",
    [
        "bonjour, je voudrais un rendez-vous",
        "il y a de la fumée, c'est urgent !",
        "au quatorze bis rue de Paris",
        "c'est pour un devis, merci.",
    ],
)
def test_une_phrase_sans_chiffre_ne_change_pas(texte):
    assert decoller_les_chiffres(texte) == texte


@pytest.mark.parametrize(
    "texte,attendu",
    [
        ("3500€", "3500 €"),
        ("20%", "20 %"),
        ("14bis", "14 bis"),
        ("14TER", "14 TER"),
        ("n°14", "n° 14"),
        ("+33 6 12 34 56 78", "plus 33 6 12 34 56 78"),
        ("+33612345678", "plus 33612345678"),
        ("06.12.34.56.78", "06 12 34 56 78"),
        # Left as they are: a decimal, a date, a version, a phone of another country.
        ("3,5 kW", "3,5 kW"),
        ("le 12.03.2024", "le 12.03.2024"),
        ("+32 470 12 34 56", "+32 470 12 34 56"),
    ],
)
def test_ce_que_la_remise_en_forme_change_et_ne_change_pas(texte, attendu):
    assert decoller_les_chiffres(texte) == attendu


def test_les_types_du_module_sont_ceux_attendus():
    # Guard: the constants the table above relies on.
    assert {TELEPHONE, MONTANT, REFERENCE, CODE_POSTAL} == {"telephone", "montant", "reference", "code_postal"}

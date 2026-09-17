"""[.mark] Non-regression test for reading the numbers a caller dictates.

The questions this file answers:

    Said either way ("soixante sept cent quarante", "soixante mille sept cent
    quarante"), is the right postal code ALWAYS among the readings, for every
    postal code of France? Is each number of the bench classified phone,
    amount, reference, postal code or department as the plan says, and does
    the model read, outside postal codes and references, exactly what the
    conversion of 2026-09-15 gave it?

Why it exists
-------------
The bench of 2026-09-16: ``text2num`` reads "soixante sept cent quarante" as
67140, wrong for 69 % of the Oise's postal codes said that way; "le devis
faisait quinze mille euros" made the town check announce Devise (80) as sure.
A reader that keeps one reading, or that takes an amount for a postal code,
tells the model a wrong place. Only a replay of every code and every bench
sentence sees it.
"""

import json
from pathlib import Path

import pytest

from api.services.communes.base import charger_base
from api.services.nombres import lecture
from api.services.nombres.lecture import (
    AUTRE,
    CODE_POSTAL,
    MONTANT,
    REFERENCE,
    TELEPHONE,
    lire_nombres,
    reecrire,
)
from api.services.nombres.mention import MARQUE, deja_mentionne, mentionner_nombres

JEU = json.loads(
    (Path(__file__).parent / "donnees" / "nombres_dictes.json").read_text(encoding="utf-8")
)["phrases"]


@pytest.fixture(scope="module")
def base():
    return charger_base()


def _lire(texte, base):
    return lire_nombres(texte, base.par_cp, base.departements)


def _en_lettres(n: int) -> str:
    if n < 1000:
        return lecture._en_lettres_1000(n)
    k, r = divmod(n, 1000)
    t = "mille" if k == 1 else lecture._en_lettres_1000(k) + " mille"
    return t if r == 0 else t + " " + lecture._en_lettres_1000(r)


# --------------------------------------------------------------------------- #
# 1. Every postal code of France, said both ways
# --------------------------------------------------------------------------- #


def test_tous_les_codes_postaux_dits_des_deux_facons(base):
    codes = sorted(base.par_cp)
    stats = {"A": [0, 0, 0], "B": [0, 0, 0]}  # read, right one among readings, single reading
    manques = []
    for cp in codes:
        dep, reste = int(cp[:2]), int(cp[2:])
        dictions = {"B": _en_lettres(int(cp))}
        # A: the department then three digits ("soixante sept cent quarante").
        if reste >= 100 and cp[0] != "0":
            dictions["A"] = _en_lettres(dep) + " " + _en_lettres(reste)
        for forme, dit in dictions.items():
            (nombre,) = _lire("code postal " + dit, base)
            st = stats[forme]
            st[0] += 1
            if nombre.type == CODE_POSTAL and cp in nombre.lectures_cp:
                st[1] += 1
            else:
                manques.append((cp, forme, dit, nombre.type, nombre.lectures_cp))
            if nombre.lectures_cp == (cp,):
                st[2] += 1

    # Counted: a test that stopped reading its codes would pass empty.
    assert stats["A"][0] == 5728
    assert stats["B"][0] == 6310
    assert manques == []
    # Single-reading rate, for the record (plan: 90 % and 93 % without
    # "code postal"; the leading zero of departments 01 to 09 is restored here).
    unique_a = stats["A"][2] / stats["A"][0]
    unique_b = stats["B"][2] / stats["B"][0]
    print(f"lecture unique : diction A {unique_a:.1%}, diction B {unique_b:.1%}")
    assert unique_a >= 0.90
    assert unique_b >= 0.93


def test_sans_code_postal_dit_le_zero_initial_nest_pas_ajoute(base):
    """A 4-digit number gets a leading zero only after "code postal" (or when a
    town of that code is said, decided by the caller of the reader)."""
    (nombre,) = _lire("mille deux cents", base)
    assert nombre.type == AUTRE
    assert nombre.lectures_cp == ()
    assert nombre.lectures_cp_zero == ("01200",)
    (nombre,) = _lire("code postal mille deux cents", base)
    assert nombre.type == CODE_POSTAL
    assert nombre.lectures_cp == ("01200",)


# --------------------------------------------------------------------------- #
# 2. Digit by digit, and digits already written
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "phrase", ["six zéro sept quatre zéro", "60 740", "60740", "soixante sept quatre zéro"]
)
def test_chiffre_par_chiffre_et_chiffres_ecrits(base, phrase):
    (nombre,) = _lire(phrase, base)
    assert nombre.type == CODE_POSTAL
    assert nombre.lectures_cp == ("60740",)
    assert reecrire(phrase, [nombre]) == "60740"


def test_le_code_choisi_est_ce_que_le_modele_lit(base):
    texte = "Saint-Maximin soixante sept cent quarante"
    (nombre,) = _lire(texte, base)
    assert nombre.lectures_cp == ("60740", "67140")
    assert reecrire(texte, [nombre], {nombre.debut: "60740"}) == "Saint-Maximin 60740"
    # Without a choice, the model would read text2num's single reading.
    assert reecrire(texte, [nombre]) == "Saint-Maximin 67 140"


# --------------------------------------------------------------------------- #
# 3. The bench sentences, classified
# --------------------------------------------------------------------------- #


def test_classement_des_phrases_du_banc(base):
    lues = 0
    ecarts = []
    for element in JEU:
        phrase = element["phrase"]
        nombres = _lire(phrase, base)
        attendus = element["nombres"]
        if len(nombres) != len(attendus):
            ecarts.append((phrase, [(n.type, n.entendu) for n in nombres], attendus))
            continue
        for nombre, attendu in zip(nombres, attendus):
            obtenu = {
                "type": nombre.type,
                "entendu": nombre.entendu,
                "ecrit": nombre.ecrit,
                "lectures_cp": list(nombre.lectures_cp),
                "montants": list(nombre.montants),
                "departement": nombre.departement,
            }
            for cle, valeur in attendu.items():
                if cle == "code_attendu":
                    ok = valeur in nombre.lectures_cp
                else:
                    ok = obtenu[cle] == valeur
                if not ok:
                    ecarts.append((phrase, cle, obtenu.get(cle), valeur))
        if "lu" in element and reecrire(phrase, nombres) != element["lu"]:
            ecarts.append((phrase, "lu", reecrire(phrase, nombres), element["lu"]))
        lues += 1
    assert ecarts == []
    # Counted: the 30 elements of sheet B, 2 more of the measures, 3 of the
    # 16/09 bench, 4 of the 15/09 conversion test.
    assert lues == len(JEU) == 39
    assert sum(1 for e in JEU if e["origine"].startswith("fiche B")) == 30


def test_un_nombre_de_facturation_nest_jamais_un_code_postal(base):
    """N6: classified amount, reference or phone, never a postal code."""
    for phrase in [
        "le devis faisait quinze mille euros",
        "ma facture numéro douze mille",
        "c'est la commande 60300",
        "commande numéro soixante mille trois cents",
    ]:
        for nombre in _lire(phrase, base):
            assert nombre.type in (MONTANT, REFERENCE, TELEPHONE), phrase
            assert nombre.lectures_cp == (), phrase


def test_un_telephone_colle_a_un_code_postal_est_coupe(base):
    texte = "Compiègne soixante deux cents zéro six douze trente-quatre cinquante-six soixante-dix-huit"
    cp, tel = _lire(texte, base)
    assert (cp.type, cp.entendu) == (CODE_POSTAL, "soixante deux cents")
    assert (tel.type, tel.ecrit) == (TELEPHONE, "06 12 34 56 78")


# --------------------------------------------------------------------------- #
# 4. Outside postal codes and references: exactly the conversion of 15/09
# --------------------------------------------------------------------------- #


def test_invariant_text2num_hors_codes_postaux_et_references(base):
    """Both ways and counted: where no postal code, reference or fixed
    expression is read, the model reads ``alpha2digit`` on the whole sentence;
    where one is, it does not."""
    from text_to_num import alpha2digit

    identiques = 0
    differentes = []
    for element in JEU:
        phrase = element["phrase"]
        nombres = _lire(phrase, base)
        lu = reecrire(phrase, nombres)
        speciaux = [n for n in nombres if n.type in (CODE_POSTAL, REFERENCE)]
        figees = lecture._positions_figees([j.mot for j in lecture.jetons(phrase)])
        if not speciaux and not figees:
            assert lu == alpha2digit(phrase, "fr"), phrase
            identiques += 1
        elif lu != alpha2digit(phrase, "fr"):
            differentes.append(phrase)
    assert identiques == 20
    # Where the reader departs from text2num on this set, named. The postal
    # codes with two readings are not here: without a choice (lot 2), they are
    # written like text2num.
    assert differentes == [
        "six zéro sept quatre zéro",  # text2num: "6 07 4 0"
        "facture deux mille vingt-six tiret huit cent quarante-sept",  # "2026 tiret 847"
        "mille mercis",  # "1000 mercis"
    ]

    for phrase in ["le zéro sept quatre vingt huit vingt six quatorze zéro neuf",
                   "il me reste deux bûches", "une fois par an", "vingt ans"]:
        assert reecrire(phrase, _lire(phrase, base)) == alpha2digit(phrase, "fr")


# --------------------------------------------------------------------------- #
# 5. Ambiguous amount (N3)
# --------------------------------------------------------------------------- #


def test_montant_ambigu(base):
    (ambigu,) = _lire("trois mille cinq euros", base)
    assert ambigu.type == MONTANT
    assert ambigu.montants == (3500, 3005)
    assert ambigu.montant_ambigu

    (net,) = _lire("trois mille cinq cents euros", base)
    assert net.montants == (3500,)
    assert not net.montant_ambigu

    (mille,) = _lire("mille cinq euros", base)
    assert mille.montants == (1500, 1005)


# --------------------------------------------------------------------------- #
# 6. Fixed expressions (N8)
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "phrase",
    ["un poêle tout neuf", "c'est à neuf", "il est remis à neuf", "on a du neuf",
     "quoi de neuf", "mille mercis", "mille excuses", "je vous l'ai dit mille fois"],
)
def test_expressions_figees_restent_en_mots(base, phrase):
    assert reecrire(phrase, _lire(phrase, base)) == phrase


def test_a_neuf_heures_est_un_nombre(base):
    phrase = "c'est remis à neuf, venez à neuf heures"
    assert reecrire(phrase, _lire(phrase, base)) == "c'est remis à neuf, venez à 9 heures"


# --------------------------------------------------------------------------- #
# 7. The notes, word for word
# --------------------------------------------------------------------------- #


def test_mention_montant_ambigu_au_mot_pres(base):
    texte = "trois mille cinq euros"
    assert mentionner_nombres(texte, _lire(texte, base)) == (
        "trois mille cinq euros [Lecture des nombres : « trois mille cinq » peut être "
        "3 500 € ou 3 005 €. Si tu notes ce montant, note les deux.]"
    )


def test_mention_reference_au_mot_pres(base):
    texte = "facture deux mille vingt-six tiret huit cent quarante-sept"
    nombres = _lire(texte, base)
    assert mentionner_nombres(texte, nombres) == (
        "facture deux mille vingt-six tiret huit cent quarante-sept [Lecture des nombres : "
        "référence entendue « deux mille vingt-six tiret huit cent quarante-sept », écrite "
        "« 2026-847 ». Relis-la en recopiant « 2026-847 » tel quel, en chiffres, et fais-la "
        "confirmer avant de la noter.]"
    )
    # N4: at a step that collects no reference, no note.
    assert mentionner_nombres(texte, nombres, avec_references=False) == texte


@pytest.mark.parametrize(
    "phrase",
    ["zéro six douze trente-quatre cinquante-six soixante-dix-huit", "c'est dans le soixante",
     "à Bresles, dans l'Oise", "trois mille cinq cents euros", "vingt ans", "soixante deux cents"],
)
def test_aucune_mention_pour_telephone_departement_montant_net(base, phrase):
    assert mentionner_nombres(phrase, _lire(phrase, base)) == phrase


def test_la_marque_ouvre_chaque_mention(base):
    texte = "trois mille cinq euros"
    mentionne = mentionner_nombres(texte, _lire(texte, base))
    assert MARQUE == "[Lecture des nombres"
    assert mentionne.count(MARQUE) == 1
    assert deja_mentionne(mentionne) and not deja_mentionne(texte)


def test_un_n_elide_nest_pas_un_numero(base):
    """Review of 2026-09-16: « je n'ai plus » made a postal code a reference."""
    (nombre,) = _lire("je n'ai plus soixante sept cent quarante", base)
    assert nombre.type == CODE_POSTAL
    (nombre,) = _lire("facture n° quatre cent douze", base)
    assert nombre.type == REFERENCE


@pytest.mark.parametrize(
    "phrase,attendu",
    [
        # Decision of Evan, 2026-09-16: "somme" naming the department is not an amount word.
        ("dans la Somme quatre vingt mille quatre cent quarante", CODE_POSTAL),
        ("dans la somme de trois mille euros", MONTANT),
        ("la somme était de deux mille", MONTANT),
        # "bon" counts only in "bon de ..." or "bon numéro".
        ("euh bon, Saint-Maximin soixante sept cent quarante", CODE_POSTAL),
        ("bon Saint-Maximin soixante sept cent quarante", CODE_POSTAL),
        ("le bon de commande quarante-deux", REFERENCE),
        ("le bon numéro douze", REFERENCE),
    ],
)
def test_somme_et_bon_selon_la_decision_devan(base, phrase, attendu):
    nombres = [n for n in _lire(phrase, base) if n.type != "departement"]
    assert [n.type for n in nombres] == [attendu], phrase

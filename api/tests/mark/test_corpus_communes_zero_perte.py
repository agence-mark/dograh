"""[.mark] Non-regression net: no commune meant by a caller lost against production.

The question this file answers:

    On every real sentence of the benches and calls (runs 230 to 273, bench of
    2026-09-16, fiche A v3, the badly transcribed names of the benches in the
    usual ways of saying them, the review and counter-review of 2026-09-17),
    for FIVE shops (Saint-Maximin, Compiègne, Coignières, Marseille, and no
    shop address), is the commune the caller meant still announced sure, or
    proposed at the same rank or better, than on the production fork
    (657a365b)? Is no town announced sure in addition? Does no parasite return?

Why it exists
-------------
Rule of Evan, 2026-09-17: « Tu casses l'outil à chaque chantier de réparation. »
A repair of the town check is judged by this file FIRST: a rule that removes a
parasite at the cost of one real commune, for any shop, is refused. A rule
measured on one shop only is not enough: a 40 km radius was zero loss for
Saint-Maximin and lost 17 communes for Compiègne (counter-review of 17/09).
⛔ Never edit ``rang_production`` to make this file pass: a worse rank is a
regression. A better rank, or a parasite that stops proposing, may be recorded
(regenerate the file and say so in the commit).

The data (``donnees/communes_corpus_reel_2026-09-17.json``) holds texts only,
without any person's name nor dictated phone number.
"""

import json
from pathlib import Path

import pytest

from api.services.communes.analyse import SURE
from api.services.communes.base import charger_base
from api.services.nombres.lecture import analyser_message

CORPUS = json.loads(
    (Path(__file__).parent / "donnees" / "communes_corpus_reel_2026-09-17.json").read_text(encoding="utf-8")
)
ABSENTE = 99
MAGASINS = ["60589", "60159", "78168", "13055", "sans"]


@pytest.fixture(scope="module")
def base():
    return charger_base()


def _magasin(base, cle):
    return None if cle == "sans" else base.coordonnees(cle)


def _rang(detections, commune, departement):
    """-1 announced sure, 0 proposed first, 1 second, 2 third; ABSENTE otherwise."""
    rang = ABSENTE
    for d in detections:
        for k, l in enumerate(d.lectures[:3]):
            if (l.commune.nom, l.commune.dep) == (commune, departement):
                rang = min(rang, -1 if (d.statut == SURE and k == 0) else k)
    return rang


def test_le_corpus_couvre_les_cinq_magasins():
    assert sorted(CORPUS["magasins"]) == sorted(MAGASINS)
    assert len(CORPUS["vraies"]) == 680 and len(CORPUS["parasites"]) == 220
    assert {k: sum(1 for e in CORPUS["vraies"] if e["rang_production"][k] is not None) for k in MAGASINS} == {
        "60589": 513, "60159": 514, "78168": 487, "13055": 458, "sans": 466,
    }


@pytest.mark.parametrize("cle", MAGASINS)
def test_aucune_commune_voulue_perdue_ni_sure_a_tort_de_plus(base, cle):
    magasin = _magasin(base, cle)
    lues, pertes, sures_en_plus = 0, [], []
    for e in CORPUS["vraies"]:
        detections = analyser_message(e["phrase"], base, magasin).detections
        lues += 1
        avant = ABSENTE if e["rang_production"][cle] is None else e["rang_production"][cle]
        apres = _rang(detections, e["commune"], e["departement"])
        if apres > avant:
            pertes.append((e["source"], e["phrase"], e["commune"], avant, apres))
        autres = [
            d for d in detections
            if d.statut == SURE and not d.code_postal_entendu
            and (d.lectures[0].commune.nom, d.lectures[0].commune.dep) != (e["commune"], e["departement"])
        ]
        if len(autres) > e["autres_sures_production"][cle]:
            sures_en_plus.append(e["phrase"])
    # Counted: a net that stopped reading its sentences would pass empty.
    assert lues == len(CORPUS["vraies"])
    assert (pertes, sures_en_plus) == ([], [])


@pytest.mark.parametrize("cle", MAGASINS)
def test_aucun_parasite_ne_revient(base, cle):
    """The sentences without a commune: only the known limits still propose one."""
    magasin = _magasin(base, cle)
    lues, proposent, sures_en_plus = 0, set(), []
    for e in CORPUS["parasites"]:
        detections = analyser_message(e["phrase"], base, magasin).detections
        lues += 1
        if any(d.statut != SURE and not d.code_postal_entendu for d in detections):
            proposent.add(e["phrase"])
        if sum(1 for d in detections if d.statut == SURE) > e["sures_production"][cle]:
            sures_en_plus.append(e["phrase"])
    assert lues == len(CORPUS["parasites"])
    assert sures_en_plus == []
    assert sorted(proposent) == CORPUS["parasites_restants_connus"][cle]

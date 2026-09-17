"""[.mark] Non-regression net: no commune meant by a caller lost against production.

The question this file answers:

    On every real sentence of the benches and calls (runs 230 to 273, bench of
    2026-09-16, fiche A v3, the badly transcribed names of the benches in the
    usual ways of saying them, the review of 2026-09-17), is the commune the
    caller meant still announced sure, or proposed at the same rank or better,
    than on the production fork (657a365b)? And does no parasite come back?

Why it exists
-------------
Rule of Evan, 2026-09-17: « Tu casses l'outil à chaque chantier de réparation. »
A repair of the town check (weak words, thresholds, grammar rules) is judged by
this file FIRST: a rule that removes a parasite at the cost of one real commune
is refused. ⛔ Never edit ``rang_production`` to make this file pass: a worse
rank is a regression. A better rank, or a parasite that stops proposing, may be
recorded (regenerate the file and say so in the commit).

Each sentence is read alone, shop at Saint-Maximin (60589). The data
(``donnees/communes_corpus_reel_2026-09-17.json``) holds texts only, without
any person's name nor dictated phone number.
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


@pytest.fixture(scope="module")
def base():
    return charger_base()


@pytest.fixture(scope="module")
def magasin(base):
    return base.coordonnees(CORPUS["magasin_insee"])


def _rang(detections, commune, departement):
    """-1 announced sure, 0 proposed first, 1 second, 2 third; ABSENTE otherwise."""
    rang = ABSENTE
    for d in detections:
        for k, l in enumerate(d.lectures[:3]):
            if (l.commune.nom, l.commune.dep) == (commune, departement):
                rang = min(rang, -1 if (d.statut == SURE and k == 0) else k)
    return rang


def test_aucune_commune_voulue_perdue_par_rapport_a_la_production(base, magasin):
    lues, pertes = 0, []
    for e in CORPUS["vraies"]:
        r = analyser_message(e["phrase"], base, magasin)
        lues += 1
        avant = ABSENTE if e["rang_production"] is None else e["rang_production"]
        apres = _rang(r.detections, e["commune"], e["departement"])
        if apres > avant:
            pertes.append((e["source"], e["phrase"], e["commune"], avant, apres))
    # Counted: a net that stopped reading its sentences would pass empty.
    assert lues == len(CORPUS["vraies"]) == 675
    assert sum(1 for e in CORPUS["vraies"] if e["rang_production"] is not None) == 508
    assert pertes == []


def test_aucune_commune_annoncee_sure_a_tort_de_plus(base, magasin):
    """No town announced sure other than the one meant, beyond production's own
    (« Accueil » -> Arcueil, « Saint-Luc Destronc » -> Saint-Luc: transcription)."""
    nouvelles = []
    for e in CORPUS["vraies"]:
        autres = [
            d.lectures[0].commune.nom
            for d in analyser_message(e["phrase"], base, magasin).detections
            if d.statut == SURE and not d.code_postal_entendu
            and (d.lectures[0].commune.nom, d.lectures[0].commune.dep) != (e["commune"], e["departement"])
        ]
        if len(autres) > len(e["autres_sures_production"]):
            nouvelles.append((e["phrase"], autres))
    for e in CORPUS["parasites"]:
        sures = [d.lectures[0].commune.nom for d in analyser_message(e["phrase"], base, magasin).detections
                 if d.statut == SURE]
        if len(sures) > len(e["sures_production"]):
            nouvelles.append((e["phrase"], sures))
    assert nouvelles == []


def test_aucun_parasite_ne_revient(base, magasin):
    """The sentences without a commune: only the known limits still propose one."""
    lues, proposent = 0, []
    for e in CORPUS["parasites"]:
        r = analyser_message(e["phrase"], base, magasin)
        lues += 1
        if any(d.statut != SURE and not d.code_postal_entendu for d in r.detections):
            proposent.append(e["phrase"])
    assert lues == len(CORPUS["parasites"]) == 192
    assert sum(1 for e in CORPUS["parasites"] if e["proposee_en_production"]) == 55
    assert sorted(set(proposent)) == CORPUS["parasites_restants_connus"]

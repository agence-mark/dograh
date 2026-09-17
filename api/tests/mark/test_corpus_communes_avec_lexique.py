"""[.mark] Non-regression net: the trade vocabulary costs no commune (T16).

The question this file answers:

    On every real sentence of the benches and calls, for the five shops, is the
    commune the caller meant still announced sure -- or proposed at the same
    rank or better -- when the trade vocabulary runs BEFORE the town check? And
    is a commune that happens to carry a brand's name ("Chazelles", "Deville",
    "Barbas") still recognised as a town?

Why it exists
-------------
Rule of Evan, 2026-09-17: zero loss against production. The vocabulary rewrites
what it hears before the towns are read; a brand named like a commune would
turn "j'habite à Chazelles" into "j'habite à Cheminées de Chazelles" and the
commune would be lost. ⛔ A rule that makes this file red is removed, never
bent: stop, record, ask.

The vocabulary used here is the 135 brands of the 2026-09-16 trial, EVERY term
ticked -- the worst case for the towns.

⚠️ Measured on the French path only (``analyser_message``), like the net it
mirrors (``test_corpus_communes_zero_perte.py``).
"""

import json
from pathlib import Path

import pytest

from api.schemas.lexique_metier import LexiqueMetier
from api.services.communes.analyse import SURE
from api.services.communes.base import charger_base
from api.services.lexique.analyse import HOMONYME_COMMUNE, Index, analyser
from api.services.lexique.correction import corriger, partie_de_lappelant
from api.services.nombres.lecture import analyser_message

DONNEES = Path(__file__).parent / "donnees"
CORPUS = json.loads((DONNEES / "communes_corpus_reel_2026-09-17.json").read_text(encoding="utf-8"))
ABSENTE = 99
MAGASINS = ["60589", "60159", "78168", "13055", "sans"]

# Communes that carry a brand's name, read on the national list on 2026-09-17.
PHRASES_HOMONYMES = [
    ("j'habite à Chazelles", "Chazelles"),
    ("c'est à Deville", "Deville"),
    ("je suis sur Barbas", "Barbas"),
]


@pytest.fixture(scope="module")
def base():
    return charger_base()


@pytest.fixture(scope="module")
def index(base) -> Index:
    lexique = LexiqueMetier.model_validate(
        json.loads((DONNEES / "lexique_poeles_2026-09-16.json").read_text(encoding="utf-8"))
    )
    coches = lexique.model_copy(
        update={"termes": [t.model_copy(update={"a_ecouter": True}) for t in lexique.termes]}
    )
    return Index.construire(coches, base.par_nom)


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


def _passe_par_le_lexique(phrase: str, index: Index) -> str:
    """The sentence as the town check receives it in a call.

    The vocabulary runs first and may add a note; the town check then reads the
    caller's words ONLY -- the note is set aside and glued back after (T17).
    That is what ``lecture_appelant`` does, and what this net replays.
    """
    appelant, _note = partie_de_lappelant(corriger(phrase, analyser(phrase, index)))
    return appelant


@pytest.mark.parametrize("cle", MAGASINS)
def test_avec_le_lexique_aucune_commune_voulue_nest_perdue(base, index, cle):
    magasin = _magasin(base, cle)
    lues, pertes, sures_en_plus = 0, [], []
    for e in CORPUS["vraies"]:
        lu = _passe_par_le_lexique(e["phrase"], index)
        detections = analyser_message(lu, base, magasin).detections
        lues += 1
        avant = ABSENTE if e["rang_production"][cle] is None else e["rang_production"][cle]
        apres = _rang(detections, e["commune"], e["departement"])
        if apres > avant:
            pertes.append((e["source"], e["phrase"], lu, e["commune"], avant, apres))
        autres = [
            d for d in detections
            if d.statut == SURE and not d.code_postal_entendu
            and (d.lectures[0].commune.nom, d.lectures[0].commune.dep) != (e["commune"], e["departement"])
        ]
        if len(autres) > e["autres_sures_production"][cle]:
            sures_en_plus.append((e["phrase"], lu))
    # Counted: a net that stopped reading its sentences would pass empty.
    assert lues == len(CORPUS["vraies"])
    assert (pertes, sures_en_plus) == ([], [])


@pytest.mark.parametrize("cle", MAGASINS)
def test_avec_le_lexique_aucun_parasite_ne_revient(base, index, cle):
    magasin = _magasin(base, cle)
    lues, proposent, sures_en_plus = 0, set(), []
    for e in CORPUS["parasites"]:
        lu = _passe_par_le_lexique(e["phrase"], index)
        detections = analyser_message(lu, base, magasin).detections
        lues += 1
        if any(d.statut != SURE and not d.code_postal_entendu for d in detections):
            proposent.add(e["phrase"])
        if sum(1 for d in detections if d.statut == SURE) > e["sures_production"][cle]:
            sures_en_plus.append((e["phrase"], lu))
    assert lues == len(CORPUS["parasites"])
    assert sures_en_plus == []
    assert sorted(proposent - set(CORPUS["parasites_restants_connus"][cle])) == []


@pytest.mark.parametrize("phrase,commune", PHRASES_HOMONYMES, ids=[p[1] for p in PHRASES_HOMONYMES])
def test_une_commune_qui_porte_le_nom_dune_marque_reste_une_commune(base, index, phrase, commune):
    lectures = analyser(phrase, index)
    assert all(d.statut == HOMONYME_COMMUNE for d in lectures), [
        (d.entendu, d.terme, d.statut) for d in lectures
    ]
    lu = corriger(phrase, lectures)
    assert lu == phrase
    detections = analyser_message(lu, base, base.coordonnees("60589")).detections
    proposees = {l.commune.nom for d in detections for l in d.lectures[:3]}
    assert commune in proposees, proposees


def test_le_lexique_de_ce_filet_contient_bien_les_homonymes(index):
    homonymes = {f.norm for f in index.formes if f.homonyme_commune}
    assert {"chazelles", "deville", "barbas"} <= homonymes

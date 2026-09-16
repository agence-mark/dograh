"""[.mark] Sweeps over dictated postal codes and numbers: no town announced sure and wrong.

The questions this file answers:

    Over EVERY postal code of the Oise and the Somme said both ways, after the
    words a caller really says before them ("donc", "ouais", "très bien"...),
    with or without the town, in one message or over two turns, and over every
    number from 1 000 to 9 999 said in a sentence: is any town or postal code
    announced SURE and wrong? And is a plain number still written exactly as
    the conversion of 2026-09-15 wrote it?

Why it exists
-------------
Two independent reviews of 2026-09-16 found, by sweeping realistic sentences,
paths the hand-written cases never met: a postal code confirming itself,
"donc soixante cinq cents" -> Ourdon (65100) sure, "c'est deux mille" ->
21000, Dijon sure, "Abbécourt" then "deux mille trois cents" -> Chenôve sure.
Before this chantier (digits from ``text2num``), those sweeps gave 0. 🔴 A
single case would have missed them; only a sweep keeps them at 0.

⚠️ Slow on purpose (tens of seconds): it is the whole Oise and Somme.
"""

import json
from pathlib import Path

import pytest
from text_to_num import alpha2digit

from api.services.communes.analyse import SURE
from api.services.communes.base import charger_base
from api.services.communes.mention import mentionner
from api.services.nombres.lecture import (
    _en_lettres_100,
    _en_lettres_1000,
    analyser_message,
    reecrire,
)
from api.services.pipecat.verification_communes import trace_de

BANC = json.loads(
    (Path(__file__).parent / "donnees" / "communes_banc_2026-09-16.json").read_text(encoding="utf-8")
)

# Words callers say before a postal code (the reviews' sweep, "donc" added).
AMORCES = [
    "donc ", "ben ", "bah ", "ouais ", "hum ", "mon code postal ", "au ", "le ", "moi c'est ",
    "d'accord ", "exactement ", "écoutez ", "attendez ", "alors c'est le ", "très bien ",
    "merci ", "c'est bon ", "non ", "il y a ", "c'est au ", "normalement ", "je crois que c'est ",
]


@pytest.fixture(scope="module")
def base():
    return charger_base()


@pytest.fixture(scope="module")
def magasin(base):
    return base.coordonnees(BANC["magasin_de_reference"]["insee"])


def _diction_a(cp):
    """The department then the rest: "soixante sept cent quarante"."""
    dep, reste = int(cp[:2]), int(cp[2:])
    return _en_lettres_100(dep) + " " + _en_lettres_1000(reste) if reste else None


def _diction_b(cp):
    """The whole number: "soixante mille sept cent quarante"."""
    a, b = divmod(int(cp), 1000)
    return _en_lettres_1000(a) + " mille" + (" " + _en_lettres_1000(b) if b else "")


def _codes(base, deps):
    return sorted({cp for c in base.communes if c.dep in deps for cp in c.cps})


def _fausses_sures(lecture, cp):
    fausses = [("code", c.code, c.par) for c in lecture.choix.values() if c.statut == "sure" and c.code != cp]
    fausses += [
        ("commune", d.entendu, d.lectures[0].commune.nom)
        for d in lecture.detections
        if d.statut == SURE and cp not in d.lectures[0].commune.cps
    ]
    return fausses


@pytest.mark.parametrize("departement", ["60", "80"])
def test_amorces_devant_un_code_postal_aucune_fausse_sure(base, magasin, departement):
    phrases = [
        (amorce + dit, cp)
        for cp in _codes(base, {departement})
        for dit in (_diction_a(cp), _diction_b(cp))
        if dit
        for amorce in AMORCES
    ]
    fausses = [(p, f) for p, cp in phrases for f in _fausses_sures(analyser_message(p, base, magasin), cp)]
    # Counted: a sweep that stopped reading would pass empty.
    assert len(phrases) == {"60": 4158, "80": 3630}[departement]
    assert fausses == []


@pytest.mark.parametrize("departements", [("60", "95"), ("80",)])
def test_commune_et_code_dans_le_meme_message_aucune_fausse_sure(base, magasin, departements):
    phrases = [
        (f"{c.nom} {dit}", cp)
        for c in base.communes if c.dep in departements
        for cp in c.cps
        for dit in (_diction_a(cp), _diction_b(cp))
        if dit
    ]
    fausses = [(p, f) for p, cp in phrases for f in _fausses_sures(analyser_message(p, base, magasin), cp)]
    assert len(phrases) == {("60", "95"): 1726, ("80",): 1545}[departements]
    assert fausses == []


@pytest.mark.parametrize("departements,diction", [(("60",), "ab"), (("02", "08"), "b")])
def test_commune_puis_code_au_tour_suivant_aucune_fausse_sure(base, magasin, departements, diction):
    """The method of lot 5 (town, then postal code), through the REAL record
    ``trace_de``: departments 01 to 09 are said "deux mille deux cents"."""
    faux = []
    n = 0
    for c in base.communes:
        if c.dep not in departements:
            continue
        for cp in c.cps:
            dictions = ([_diction_a(cp)] if "a" in diction else []) + [_diction_b(cp)]
            for dit in filter(None, dictions):
                n += 1
                avant = analyser_message(c.nom, base, magasin, [])
                trace = [trace_de(d, base, "coordonnees") for d in avant.detections]
                faux += [(c.nom, dit, f) for f in _fausses_sures(analyser_message(dit, base, magasin, trace), cp)]
    assert n == {("60",): 1356, ("02", "08"): 1248}[departements]
    assert faux == []


def test_un_nombre_de_1000_a_9999_reste_un_nombre(base, magasin):
    """« mille » opens a number only (decision of Evan): "c'est deux mille" is
    2000, never 21000 (Dijon). Written exactly as the conversion of 15/09."""
    ecarts, sures = [], []
    n = 0
    for v in range(1000, 10000, 10):
        a, b = divmod(v, 1000)
        mots = ("mille" if a == 1 else _en_lettres_1000(a) + " mille") + (" " + _en_lettres_1000(b) if b else "")
        texte = "c'est " + mots
        n += 1
        lecture = analyser_message(texte, base, magasin, [])
        if reecrire(texte, lecture.nombres, lecture.choix_cp) != alpha2digit(texte, "fr"):
            ecarts.append(texte)
        sures += [(texte, d.lectures[0].commune.nom) for d in lecture.detections if d.statut == SURE]
    assert n == 900
    assert ecarts == []
    assert sures == []


# --------------------------------------------------------------------------- #
# The cases the reviews named
# --------------------------------------------------------------------------- #


def _lu(texte, base, magasin, trace=None):
    r = analyser_message(texte, base, magasin, trace or [])
    return mentionner(reecrire(texte, r.nombres, r.choix_cp), r.detections, base), r


@pytest.mark.parametrize(
    "texte",
    ["donc soixante cinq cents", "d'accord, soixante deux cent cinquante", "ouais soixante trois cent vingt",
     "très bien soixante deux cent cinquante", "attendez quatre vingt deux cent soixante"],
)
def test_un_mot_colle_a_un_code_ambigu_ne_devient_pas_une_commune_sure(base, magasin, texte):
    lu, _ = _lu(texte, base, magasin)
    assert "correspond à" not in lu, lu


@pytest.mark.parametrize(
    "texte,ecrit",
    [("c'est deux mille", "c'est 2000"), ("on m'a dit cinq mille cent", "on m'a dit 5100"),
     ("ça fait deux mille cinq cents", "ça fait 2500")],
)
def test_un_nombre_nest_pas_decoupe_en_code_postal(base, magasin, texte, ecrit):
    lu, r = _lu(texte, base, magasin)
    assert lu.startswith(ecrit)
    assert r.choix == {}
    # « ça fait » may still be proposed as a town to confirm (short answer),
    # as before the chantier; never as a sure one.
    assert all(d.statut != SURE for d in r.detections)


def test_zero_initial_par_la_commune_du_tour_precedent(base, magasin):
    avant = analyser_message("Abbécourt", base, magasin, [])
    trace = [trace_de(d, base, "coordonnees") for d in avant.detections]
    lu, r = _lu("deux mille trois cents", base, magasin, trace)
    (choix,) = r.choix.values()
    assert (choix.code, choix.statut) == ("02300", "sure")
    assert lu.startswith("02300 [Vérification de la commune : « deux mille trois cents » correspond à Abbécourt")


def test_en_somme_nest_pas_le_departement(base, magasin):
    lu, r = _lu("en somme, quinze mille", base, magasin)
    assert "correspond à" not in lu
    assert all(n.type != "departement" for n in r.nombres)
    _, r = _lu("dans la Somme", base, magasin)
    assert [n.departement for n in r.nombres] == ["80"]


def test_une_commune_a_confirmer_mal_entendue_nest_pas_promue_par_un_code_ambigu(base, magasin):
    """Branch ① guard, tested directly: no realistic sentence reaches it today
    (the candidate and bonus rules act first), so it is exercised on a built
    detection. A town to confirm, heard loosely (phon 75), that carries one of
    two readings must not become sure; heard almost exactly (phon 95), it may."""
    from api.services.communes.analyse import A_CONFIRMER, Detection, Lecture
    from api.services.nombres.lecture import PAR_COMMUNE_DITE, choisir_code_postal, lire_nombres

    (nombre,) = lire_nombres("soixante deux cent cinquante", base.par_cp, base.departements)
    assert len(nombre.lectures_cp) == 2
    beugin = next(c for c in base.communes_du_code_postal("62150") if c.nom == "Beugin")

    def detection(phon):
        return Detection(entendu="bien", debut=0, fin=1, statut=A_CONFIRMER,
                         lectures=(Lecture(beugin, 80, phon, 70),), codes_postaux_dits=frozenset())

    loin = choisir_code_postal(nombre, [detection(75)], [], set(), magasin, base)
    assert loin.par != PAR_COMMUNE_DITE
    proche = choisir_code_postal(nombre, [detection(95)], [], set(), magasin, base)
    assert (proche.par, proche.code) == (PAR_COMMUNE_DITE, "62150")

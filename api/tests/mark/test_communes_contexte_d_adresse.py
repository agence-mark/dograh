"""[.mark] Non-regression test: « à » after a noun is not an address context for a commune.

The question this file answers:

    Does the town reader still invent a commune on « un poêle à granulés » (Grandrû, Grans,
    Grane), WITHOUT losing a commune a caller meant (« à Brel » for Bresles, « je suis à ... »,
    a postal code said), and is « Pont-Saint-Maxence » the sure Pont-Sainte-Maxence (Saint = Sainte)?

Why it exists
-------------
Run 1048 (``reading_modules``, constat B1 of the global repair): the readings « granulés » ->
Grandrû and « Delaunay » -> Launay were proposed aloud by the agent. « à » alone does not say a
place: it does after a being or living verb (« je suis à », « j'habite à »), or at the head of the
answer. After a noun it is « poêle à granulés ».

⛔ What is NOT done, and why. The plan also asked to keep a proposal without address context only
if its sound is close to a commune of the shop's radius. That rule was built and measured on the
real corpus (4 shops): it loses « Grand Villiers » -> Grandvilliers, « Abrel dans l'Oise » -> Bresles
and fails ``test_aucune_regle_ne_depend_du_magasin``, i.e. it reverses the decision of Evan of
2026-09-17 (option d: zero loss, no radius). It waits for his word; the two cases it would fix
(« Delaunay » alone -> Launay) are below as strict expected failures, to flip with that decision.

The words are common words and real communes of France; no trade word is in the code.
"""

import pytest

from api.services.communes.analyse import SURE
from api.services.communes.base import charger_base
from api.services.nombres.lecture import analyser_message


@pytest.fixture(scope="module")
def base():
    return charger_base()


@pytest.fixture(scope="module")
def saint_maximin(base):
    return base.coordonnees("60589")


@pytest.fixture(scope="module")
def marseille(base):
    return base.coordonnees("13055")


def _noms(r):
    return [[l.commune.nom for l in d.lectures] for d in r.detections if not d.code_postal_entendu]


@pytest.mark.parametrize(
    "texte",
    [
        "Un poêle à granulés",
        "Je voudrais un poêle à granulés pour ma maison",
        "Il me faut un tuyau à granulés",
    ],
)
def test_a_apres_un_nom_ne_propose_aucune_commune(base, saint_maximin, texte):
    assert _noms(analyser_message(texte, base, saint_maximin)) == []


@pytest.mark.parametrize("magasin", ["saint_maximin", "marseille"])
def test_la_regle_ne_depend_pas_de_l_etablissement(base, saint_maximin, marseille, magasin):
    position = saint_maximin if magasin == "saint_maximin" else marseille
    assert _noms(analyser_message("Un poêle à granulés", base, position)) == []
    assert _noms(analyser_message("Un poêle à granulés", base, None)) == []


@pytest.mark.parametrize(
    "texte, premiere",
    [
        ("Brel", "Bresles"),  # alone, badly heard
        ("à Brel", "Bresles"),  # « à » at the head of the answer
        ("j'habite à Brel", "Bresles"),
        ("oui c'est à Brel", "Bresles"),
        ("je suis à Brel", "Bresles"),
        ("nous habitons à Brel", "Bresles"),
    ],
)
def test_la_commune_voulue_et_mal_transcrite_reste_proposee(base, saint_maximin, texte, premiere):
    noms = _noms(analyser_message(texte, base, saint_maximin))
    assert noms and noms[0][0] == premiere


def test_un_code_postal_dit_garde_la_proposition_meme_apres_un_nom(base, saint_maximin):
    """The postal code is a context of its own: the rule leaves the sentence alone."""
    r = analyser_message("la maison à Brel 60510", base, saint_maximin)
    assert any(d.lectures for d in r.detections)


def test_saint_et_sainte_sont_la_meme_commune_et_elle_est_sure(base, saint_maximin):
    r = analyser_message("c'est à Pont-Saint-Maxence", base, saint_maximin)
    [d] = [d for d in r.detections if not d.code_postal_entendu]
    assert d.statut == SURE and d.lectures[0].commune.nom == "Pont-Sainte-Maxence"
    r = analyser_message("oui Pont Saint Maxence", base, saint_maximin)
    [d] = [d for d in r.detections if not d.code_postal_entendu]
    assert d.statut == SURE and d.lectures[0].commune.nom == "Pont-Sainte-Maxence"


def test_une_autre_ville_un_autre_metier_un_garage_a_marseille(base, marseille):
    """Same rule elsewhere, nothing about a trade in the code."""
    for texte in ("Un moteur à pistons", "Un joint à remplacer", "Un contrat à durée"):
        assert _noms(analyser_message(texte, base, marseille)) == [], texte
    r = analyser_message("j'habite à Aubagne", base, marseille)
    [d] = [d for d in r.detections if not d.code_postal_entendu]
    assert d.statut == SURE and d.lectures[0].commune.nom == "Aubagne"


@pytest.mark.xfail(
    strict=True,
    reason="Radius + close sound (plan B1): reverses the decision of 17/09, waits for Evan. See the module docstring.",
)
@pytest.mark.parametrize("texte", ["oui Delaunay", "Delaunay", "Delaunay Jean"])
def test_une_reponse_seule_sans_son_proche_d_une_commune_du_rayon_ne_propose_rien(base, saint_maximin, texte):
    assert _noms(analyser_message(texte, base, saint_maximin)) == []

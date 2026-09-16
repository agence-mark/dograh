"""[.mark] Non-regression test for the national list of communes.

The questions this file answers:

    Does the embedded list load, with the whole country in it? Are the sound
    keys stored in the file still the ones the code computes today?

Why it exists
-------------
The keys are computed once, by ``api/scripts/mark/generer_base_communes.py``,
and stored in the file (computing them at start-up costs about 7 seconds). 🔴
Change ``normaliser`` or ``cle_sonore`` without regenerating, and every call
would compare today's key of what the caller said against yesterday's key of
the towns: nothing fails, the towns simply stop matching. Test 2 is the only
thing that turns red on that.
"""

import asyncio
import gzip
import json
import random

import pytest

from api.services.communes import base as module_base
from api.services.communes.base import (
    FICHIER_BASE,
    VERSION_CLES,
    charger_base,
    cle_phonetique,
    cle_sonore,
    normaliser,
    obtenir_base,
)


def test_le_fichier_se_charge_avec_toute_la_france():
    base = charger_base()
    assert 34_000 <= len(base.communes) <= 36_000
    assert len(base.norms) == len(base.phons) == len(base.sons) == len(base.communes)

    saint_maximin = base.commune("60589")
    assert saint_maximin is not None
    assert saint_maximin.nom == "Saint-Maximin"
    assert saint_maximin.dep == "60"
    assert "60740" in saint_maximin.cps
    assert base.coordonnees("60589") is not None
    assert base.nom_departement("60") == "Oise"

    # The header says where the data comes from, under which licence, and
    # with which version of the keys.
    assert base.entete["licence"] == "Licence Ouverte"
    assert base.entete["version_cles"] == VERSION_CLES
    assert base.entete["nombre"] == len(base.communes)


def test_les_cles_du_fichier_sont_celles_que_le_code_calcule():
    """🔴 An algorithm change without regeneration turns this red."""
    with gzip.open(FICHIER_BASE, "rt", encoding="utf-8") as f:
        lignes = json.load(f)["communes"]
    tirees = random.Random(20260916).sample(lignes, 200)
    # Plus the names the trial cared about, so the sample always holds some.
    noms = {"Beauvais", "Senlis", "Clermont-Ferrand", "Saint-Leu-d'Esserent"}
    tirees += [l for l in lignes if l[1] in noms]
    assert len(tirees) >= 200 + len(noms)

    ecarts = [
        (insee, nom)
        for insee, nom, _cps, _pop, _dep, _lon, _lat, norm, phon, son in tirees
        if (norm, phon, son)
        != (normaliser(nom), cle_phonetique(normaliser(nom)), cle_sonore(normaliser(nom)))
    ]
    assert ecarts == []


def test_communes_dun_code_postal():
    base = charger_base()
    assert [c.nom for c in base.communes_du_code_postal("60740")] == ["Saint-Maximin"]
    assert base.communes_du_code_postal("00000") == []
    assert base.commune("00000") is None
    assert base.coordonnees("00000") is None
    # A shared code: every commune that carries it, largest first.
    partage = base.communes_du_code_postal("60300")
    assert "Senlis" in [c.nom for c in partage]
    assert len(partage) > 1
    assert [c.population for c in partage] == sorted(
        (c.population for c in partage), reverse=True
    )


@pytest.mark.parametrize(
    "ecrits",
    [("Beauvais", "Beauvet", "Bovet"), ("Senlis", "Sanlis")],
)
def test_cle_sonore_rapproche_ce_que_la_transcription_ecrit(ecrits):
    """The two transcriptions of 2026-09-15 and 16 sound like Beauvais."""
    cles = {cle_sonore(normaliser(e)) for e in ecrits}
    assert len(cles) == 1


def test_normaliser():
    assert normaliser("Saint-Leu-d'Esserent") == "saint leu d esserent"
    assert normaliser("St Just en Chaussée") == "saint just en chaussee"
    assert normaliser("Ste-Geneviève") == "sainte genevieve"


@pytest.mark.asyncio
async def test_obtenir_base_charge_hors_de_la_boucle(monkeypatch):
    """T4: the first read happens in a worker thread, never on the loop."""
    monkeypatch.setattr(module_base, "_base", None)
    appels = []
    vrai = module_base.charger_base

    def espion():
        # A worker thread has no running loop; the loop's own thread has one.
        try:
            asyncio.get_running_loop()
            appels.append(True)
        except RuntimeError:
            appels.append(False)
        return vrai()

    monkeypatch.setattr(module_base, "charger_base", espion)
    base = await obtenir_base()
    assert appels == [False]
    assert len(base.communes) > 34_000
    # Loaded once: the second call does not read again.
    await obtenir_base()
    assert appels == [False]

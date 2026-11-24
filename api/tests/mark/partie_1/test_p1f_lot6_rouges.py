"""[.mark] Lot 6, première étape : les deux rouges de départ (RC1, RC2) vus avant tout correctif, puis tenus verts par le registre commun des questions."""

from __future__ import annotations

import pytest

from api.tests.mark.partie_1 import combinaisons as C

# RC1 : une seule question dans le tour (celle du registre), jamais la question du registre ET « Pour quel jour ? » du code
RC1 = [("E9", ("G2", "G26")), ("E9", ("G4", "G26"))]
# RC2 : le panier attendu après le geste est le panier réel
RC2 = [("E5", ("G5", "G32")), ("E5", ("G6", "G32")), ("E18", ("G12", "G2+G23")), ("E5", ("G5+G2", "G32")), ("E14", ("G2+G1", "G32")), ("E18", ("G1+G2", "G32"))]


@pytest.mark.parametrize("etat,suite", RC1, ids=[f"{e}-{'-'.join(s)}" for e, s in RC1])
async def test_rc1_une_seule_question_dans_le_tour(faire_monde, monkeypatch, etat, suite):
    monde = await faire_monde("casa-italia")
    r = await C.jouer(monde, monkeypatch, etat, suite)
    assert r.atteint
    assert not [f for f in r.fautes if f[1] == "RC1"], r.fautes


RAISON_RC2 = ("lot 6 non fini : le rejeu d'une fiche (G32) est lu par ``article_remis_pour_sa_ligne`` d'après les mots de la personne (n° 53) ; "
              "le remplacer sans changer Pierre 8 demande une décision d'Evan")
CAS_RC2 = [pytest.param(e, s, id=f"{e}-{'-'.join(s)}", marks=([pytest.mark.xfail(strict=True, reason=RAISON_RC2)] if "G32" in s else [])) for e, s in RC2]


@pytest.mark.parametrize("etat,suite", CAS_RC2)
async def test_rc2_le_panier_attendu_est_le_panier_reel(faire_monde, monkeypatch, etat, suite):
    monde = await faire_monde("casa-italia")
    r = await C.jouer(monde, monkeypatch, etat, suite)
    assert r.atteint
    assert not [f for f in r.fautes if f[1] == "RC2"], r.fautes

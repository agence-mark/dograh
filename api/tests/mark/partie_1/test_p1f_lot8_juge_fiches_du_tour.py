"""[.mark] Plan final Partie 1, lot 8b-2 (T28 (a), registre) : le juge des combinaisons garde les fiches appliquées du tour comme le code (``porte.CLE_DES_FICHES_AJOUTEES``, plusieurs), et
ne les vide qu'au changement de tour ; avant, il ne gardait que la dernière, et une fiche appliquée plus tôt dans le même tour, redite au tour d'après (« je répète »), passait pour
nouvelle : une fausse faute RC2 (jamais un vert muet).

| Test | Ce qu'il prouve |
|---|---|
| deux fiches dans un tour | la première, redite au tour suivant, est « identique au tour d'avant » pour le juge, comme pour le code |
| changement de tour | au tour suivant la liste ne garde que ce tour-là : la fiche du tour d'avant, redite deux tours plus tard, n'est plus identique |
"""

from __future__ import annotations

from api.tests.mark.partie_1 import combinaisons as C

MARGHERITA_DITE = {"ajouter": [{"article": "margherita", "quantite": 1, "variante": "Normale"}]}
REGINA_DITE = {"ajouter": [{"article": "regina", "quantite": 1, "variante": "Normale"}]}


async def _deux_fiches_dans_un_tour(faire_monde, monkeypatch) -> C.Partie:
    partie = C.Partie(await faire_monde("casa-italia"), monkeypatch)
    await partie._executer("recette", "à emporter", {"mode_de_retrait": "emporter"}, C._inchange)
    await partie._executer("A", "une margherita normale", MARGHERITA_DITE, C._plus(C.MARGHERITA))
    await partie._executer("B", None, REGINA_DITE, C._plus(C.REGINA))  # la même phrase, un second passage du modèle : le même tour
    return partie


async def test_deux_fiches_appliquees_dans_un_tour_sont_toutes_deux_celles_du_tour_d_avant(faire_monde, monkeypatch):
    partie = await _deux_fiches_dans_un_tour(faire_monde, monkeypatch)
    partie.e.dit("je répète")  # le tour suivant
    assert partie._identique_au_tour_d_avant(MARGHERITA_DITE, partie.p), "la première fiche du tour d'avant n'est plus vue"
    assert partie._identique_au_tour_d_avant(REGINA_DITE, partie.p)


async def test_au_changement_de_tour_la_liste_ne_garde_que_le_tour_d_avant(faire_monde, monkeypatch):
    partie = await _deux_fiches_dans_un_tour(faire_monde, monkeypatch)
    partie.e.dit("je répète")
    await partie._executer("C", None, {"ajouter": [{"article": "margherita", "quantite": 2, "variante": "Normale"}]}, C._plus(C.MARGHERITA, 2))
    partie.e.dit("encore")
    assert not partie._identique_au_tour_d_avant(MARGHERITA_DITE, partie.p), "deux tours plus tard, la fiche du premier tour n'est plus celle du tour d'avant"

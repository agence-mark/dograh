"""[.mark] Plan final Partie 1, lot 8b-2 (T28 (a), registre) : le juge des combinaisons garde les fiches appliquées du tour comme le code (``porte.CLE_DES_FICHES_AJOUTEES``, plusieurs), et
ne les vide qu'au changement de tour ; avant, il ne gardait que la dernière, et une fiche appliquée plus tôt dans le même tour, redite au tour d'après (« je répète »), passait pour
nouvelle : une fausse faute RC2 (jamais un vert muet).

| Test | Ce qu'il prouve |
|---|---|
| deux fiches dans un tour | la première, redite au tour suivant, est « identique au tour d'avant » pour le juge, comme pour le code |
| changement de tour | au tour suivant la liste ne garde que ce tour-là : la fiche du tour d'avant, redite deux tours plus tard, n'est plus identique |
"""

from __future__ import annotations

import copy

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


async def test_vider_et_annuler_dans_la_fiche_puis_redire_un_article_garde_n_est_pas_une_faute_rc2(faire_monde, monkeypatch):
    """§ 17 l.407 (annuler = vider, l'article dit ensuite entre) : E2 (livraison, pas d'adresse), « une regina normale » (gardée de côté, faute d'adresse), puis « on vide et on annule, une
    regina normale » : l'ancien article gardé part avec le vidage, le nouveau est gardé à son tour. Le compte des articles gardés ne bouge pas (1 avant, 1 après) : le juge RC2 ne doit
    pas y voir un article perdu (suite tirée E2 → G1 · G14+G1, ``test_suites_tirees``)."""
    partie = C.Partie(await faire_monde("casa-italia"), monkeypatch)
    assert await partie.recette("E2")
    await partie.geste("G1")
    o = await partie.fusion(("G14", "G1"))
    assert o is not None and C.en_attente(o.avant) == 1 == C.en_attente(o.apres) and not C.lignes_de(o.apres), (C.en_attente(o.avant), C.en_attente(o.apres))
    assert C.rc2(o) == [], C.rc2(o)


async def test_le_vidage_qui_garde_un_article_d_avant_est_une_faute_rc2(faire_monde, monkeypatch):
    """R1 de l'audit 8b-2 : « on recommence, une regina » : la fiche vide le panier ET ajoute une regina. Si le vidage laisse l'ancien article gardé de côté (mutation : ``vider_commande``
    garde l'attente), l'ancien reste en plus du nouveau : le juge ne doit pas excuser cela comme « gardé de côté », même quand le compte gardé ne baisse pas."""
    from api.services.commande import moteur

    vrai_vidage = moteur.vider_commande

    async def vidage_qui_garde_l_attente(source, p, regles):
        gardes = copy.deepcopy(p.get("dits_en_attente"))
        resultat = await vrai_vidage(source, p, regles)
        p["dits_en_attente"] = gardes  # la faute : ce qui était gardé avant la fiche survit au vidage
        return resultat

    monkeypatch.setattr(moteur, "vider_commande", vidage_qui_garde_l_attente)
    partie = C.Partie(await faire_monde("casa-italia"), monkeypatch)
    assert await partie.recette("E2")
    await partie.geste("G1")
    o = await partie.fusion(("G14", "G1"))
    assert o is not None and C.en_attente(o.apres) == 2, C.en_attente(o.apres)  # l'ancien reste et le nouveau s'ajoute
    assert any(code == "RC2" for code, _ in C.rc2(o)), "le juge excuse un article d'avant gardé après le vidage"

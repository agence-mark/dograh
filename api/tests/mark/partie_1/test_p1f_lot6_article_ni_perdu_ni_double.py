"""[.mark] Lot 6 (n° 39, 40, 54) : la garde du doublon est la règle du constat « un article n'est ni perdu ni en double ». Quelle que soit la façon dont la taille de
l'article en attente est donnée (la réponse du modèle, l'article redit avec la réponse ; une entrée d'``ajouter`` sans article est refusée par le format), la commande garde UNE ligne de
cet article, jamais zéro, jamais deux. Un article de plus, lui, est bien un article de plus."""

from __future__ import annotations

import pytest

FACONS = {
    "reponse": lambda q: {"reponse": {"question_id": q, "sens": "autre", "valeurs": ["Normale"]}},
    "article redit avec sa reponse": lambda q: {"ajouter": [{"article": "regina", "quantite": 1}], "reponse": {"question_id": q, "sens": "autre", "valeurs": ["Normale"]}},
}


@pytest.mark.parametrize("facon", sorted(FACONS))
async def test_la_taille_donnee_ne_perd_ni_ne_double_l_article(essai_de, facon):
    e = await essai_de()
    await e.tour("à emporter", mode_de_retrait="emporter")
    await e.tour("une regina", ajouter=[{"article": "regina", "quantite": 1}])
    assert e.p["question"]["type"] == "variante", e.p.get("question")
    await e.tour("normale", **FACONS[facon](e.p["question"]["id"]))
    lignes = [(l["nom"], l["quantite"]) for l in e.p["lignes"]]
    assert lignes == [("Regina Normale", 1)], f"{facon} : {lignes}"
    assert not any(l.get("attente") for l in e.p["lignes"]), e.p["lignes"]

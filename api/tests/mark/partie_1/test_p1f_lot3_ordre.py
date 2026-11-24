"""[.mark] Chantier final, lot 3 : le résultat d'une fiche ne dépend pas de l'ordre des articles dits."""


async def test_le_resultat_de_la_fiche_ne_depend_pas_de_l_ordre_des_articles(essai_de):
    """Un article pris et un article refusé : que le refus vienne avant ou après, la fiche rend la même chose (l'état du panier après l'ajout : total, proposition) ; seuls les
    résultats se rangent dans l'ordre dit."""
    import json

    async def jouer(articles):
        e = await essai_de()
        await e.tour("à emporter", mode_de_retrait="emporter")
        return await e.tour("deux articles", ajouter=articles)

    refuse, pris = {"article": "zzzuno", "quantite": 1}, {"article": "margherita", "quantite": 1, "variante": "Normale"}
    avant, apres = await jouer([refuse, pris]), await jouer([pris, refuse])

    def sans_ordre(r):
        return sorted(json.dumps(x, sort_keys=True, ensure_ascii=False) for x in r["resultats"])

    assert sans_ordre(avant) == sans_ordre(apres), (avant["resultats"], apres["resultats"])
    assert any("total" in (x.get("faits") or {}) for x in apres["resultats"]), apres["resultats"]
    for cle in ("statut", "faits", "question", "a_faire"):
        assert avant.get(cle) == apres.get(cle), (cle, avant.get(cle), apres.get(cle))

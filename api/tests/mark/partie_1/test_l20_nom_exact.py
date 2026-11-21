"""Lot 20 (porte du chantier, appels 456 à 458, a307) : « un kebab » sur la carte du kebab (Kebab, Assiette kebab, Barquette de kebab) posait
« Vous voulez dire : … ? » ; la réponse « Kebab » relançait la même recherche, qui reposait la même question, sans fin. Un candidat dont le nom est
EXACTEMENT celui qui est dit (même forme) est retenu : une égalité de valeur, jamais une devinette."""


async def test_un_nom_exact_de_la_carte_est_retenu_sans_question(essai_de):
    k = await essai_de("kebab-demo")
    await k.tour("à emporter", mode_de_retrait="emporter")
    await k.tour("un kebab", ajouter=[{"article": "kebab", "quantite": 1}])
    assert (k.p.get("question") or {}).get("type") != "ambiguite", k.retours[-1]
    assert [l["ref"] for l in k.p["lignes"]], k.retours[-1]  # la ligne du Kebab est prise (sa taille peut rester à demander)


async def test_un_nom_qui_n_est_exact_pour_aucun_candidat_reste_une_question(essai_de):
    k = await essai_de("kebab-demo")
    await k.tour("à emporter", mode_de_retrait="emporter")
    await k.tour("un keb", ajouter=[{"article": "keb", "quantite": 1}])
    assert (k.p.get("question") or {}).get("type") in ("ambiguite", None), k.retours[-1]

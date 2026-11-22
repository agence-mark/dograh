"""Lot 20 (porte du chantier, appels 456 à 458, a307) : « un kebab » sur la carte du kebab (Kebab, Assiette kebab, Barquette de kebab) posait
« Vous voulez dire : … ? » ; la réponse « Kebab » relançait la même recherche, qui reposait la même question, sans fin.

B5 (N1 de l'audit des rustines) : la rustine du moteur (le nom exact retenu après la recherche) est retirée : elle rendait sûr à tort ce que la
recherche, mesurée à zéro faux sûr, demande quand deux rangements portent le nom (« pesto »). La question est posée une fois ; la réponse « Kebab »
choisit le candidat de même nom (même norme que la recherche) : la boucle est réglée là où elle naissait."""


async def test_un_nom_exact_repondu_a_la_question_est_retenu_sans_la_reposer(essai_de):
    k = await essai_de("kebab-demo")
    await k.tour("à emporter", mode_de_retrait="emporter")
    await k.tour("un kebab", ajouter=[{"article": "kebab", "quantite": 1}])
    q = k.p.get("question") or {}
    assert q.get("type") == "ambiguite" and "Kebab" in (q.get("choix") or []), k.retours[-1]
    await k.tour("Kebab", reponse={"question_id": q["id"], "valeurs": ["Kebab"]})
    assert [l["nom"] for l in k.p["lignes"]] == ["Kebab"], k.retours[-1]
    assert (k.p.get("question") or {}).get("type") != "ambiguite", k.retours[-1]  # la même question n'est pas reposée


async def test_un_nom_qui_n_est_exact_pour_aucun_candidat_reste_une_question(essai_de):
    k = await essai_de("kebab-demo")
    await k.tour("à emporter", mode_de_retrait="emporter")
    await k.tour("un keb", ajouter=[{"article": "keb", "quantite": 1}])
    assert (k.p.get("question") or {}).get("type") in ("ambiguite", None), k.retours[-1]

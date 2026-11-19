"""[.mark] Banc A, volet généricité : les mêmes cas rejoués sur les QUATRE cartes de démo (Casa Italia, Étoile d'Or, Kebab, Lusitalia).

Décision d'Evan (18/11) : un restaurateur = un formulaire ; le code lit n'importe quelle carte ; un formulaire incomplet ne bloque jamais l'agent.
Les cartes sont figées dans ``cartes/*.json`` (lues en GET sur la caisse de démo le 18/11, aucun secret). Les produits de chaque cas sont CHOISIS
dans la carte par ``profil`` (jamais un nom de plat écrit dans le test) : le cas est le même, le plat change. Un cas sans objet pour une carte
(Étoile d'Or n'a ni tailles, ni ingrédients, ni formules ; seule Casa a la moitié-moitié) est rendu « sauté » avec sa raison.

| Cas | Ce que le client voulait |
|---|---|
| g0 | une commande à emporter menée jusqu'à l'enregistrement (la carte, même pauvre, ne bloque jamais) |
| g1 | un article simple dit par son nom : une ligne, au bon prix |
| g2 | un article à tailles dit sans taille : la taille est demandée, la réponse la pose |
| g3 | un article à choix obligatoire : le choix est demandé, la réponse le pose |
| g4 | « sans X » : le retrait est posé sur la ligne |
| g5 | moitié-moitié (si la carte en a) : prise avec les noms courants |
| g6 | une formule (si la carte en a) : prise, ou ses choix demandés, jamais « introuvable » |
| g7 | minimum de zone : le manque exact est dit, puis atteint |
| g8a, g8b | vente en plus : l'accord ajoute la proposition, le refus ne l'ajoute pas |
| g9 | donnée facultative absente (allergènes, ingrédients retirables, description) : l'agent continue |

Lot 3 (D48) : chaque cas envoie des fiches à la vraie porte (``commun.Appel``) ; les valeurs sont celles des anciens appels.
"""

import math

import pytest

from api.tests.mark.banc_a.commun import CARTES, appel_de, base_essai, base_prete, carte_de, faire_monde, statuts_du_module, trace  # noqa: F401

pytestmark = pytest.mark.banc_a
SLUGS = ["casa-italia", "etoile-d-or", "kebab-demo", "lusitalia"]
REFUS = ("HORS_CARTE", "INTROUVABLE", "ARGUMENT_INVALIDE", "INDISPONIBLE", "AMBIGU")  # statuts du module


def profil(slug: str) -> dict:
    """Les produits de la carte qui servent à chaque cas, choisis par leur FORME (jamais par leur nom)."""
    c = carte_de(slug)
    groupes = {g["id"]: g for g in c["groupes"]}
    obligatoire = lambda p: any((groupes.get(g) or {}).get("min", 0) >= 1 for g in p.get("groupes") or [])  # noqa: E731
    hors_offres = lambda p: not any(m in p["categorie_id"] for m in ("menu", "offre", "moitie"))  # noqa: E731
    prix = lambda p: min(d["prix"] for d in p["declinaisons"]) if p["declinaisons"] else 0  # noqa: E731
    noms = [x["nom"].casefold() for x in [*c["produits"], *(c["formules"] or [])]]
    # Un plat dit par son nom ne doit pas être le morceau du nom d'un autre (« un Kebab » est ambigu entre Kebab et Assiette kebab : vrai doute, pas le cas testé).
    sans_homonyme = lambda p: sum(1 for n in noms if p["nom"].casefold() in n) == 1  # noqa: E731
    produits = [p for p in c["produits"] if p["declinaisons"] and prix(p) > 0 and hors_offres(p) and sans_homonyme(p)]
    simples = [p for p in produits if len(p["declinaisons"]) == 1 and not obligatoire(p)]
    a_tailles = [p for p in produits if len(p["declinaisons"]) > 1 and not obligatoire(p)]
    a_choix = [p for p in produits if obligatoire(p) and len(p["declinaisons"]) == 1]
    a_retrait = [p for p in produits if any(i.get("retirable") for i in p.get("ingredients") or []) and not obligatoire(p)]
    sans_ingredients = [p for p in produits if not p.get("ingredients") and not obligatoire(p)]
    sans_allergenes = [p for p in produits if not p.get("allergenes")]
    return {
        "simple": simples[0] if simples else None, "a_tailles": a_tailles[0] if a_tailles else None, "a_choix": a_choix[0] if a_choix else None,
        "a_retrait": a_retrait[0] if a_retrait else None, "sans_ingredients": sans_ingredients[0] if sans_ingredients else None,
        "sans_allergenes": sans_allergenes[0] if sans_allergenes else None,
        "formule": next(iter(c["formules"] or []), None), "moitie": next((p for p in c["produits"] if "moitie" in p["categorie_id"]), None), "prix": prix,
    }


def nom_du_plat(p: dict) -> str:
    return p["nom"]


def art(nom: str, quantite: int = 1, variante: str | None = None, **plus) -> dict:
    return {"article": nom, "quantite": quantite, **({"variante": variante} if variante else {}), **plus}


def options_de(r: dict) -> list[str]:
    """Les choix de la question qu'un ajout rend (taille, choix obligatoire), tels que le module les donne."""
    for x in r.get("resultats") or []:
        q = (x.get("faits") or {}).get("question")
        if isinstance(q, dict) and q.get("options"):
            return list(q["options"])
    return []


async def emporter(a) -> None:
    r = await a.jouer_la_fiche("à emporter", {"mode_de_retrait": "emporter"})
    assert r["statut"] != "REJETEE" and a.p.get("mode") == "emporter", f"précondition : mode emporter pris\n{trace(a)}"


async def livraison(a) -> None:
    rue, _, reste = a.monde.adresse.partition(", ")
    commune = reste.split(" ", 1)[1] if reste[:1].isdigit() else reste  # « 60300 Senlis » : la commune ; le code postal n'a pas de case
    r = await a.jouer_la_fiche(f"en livraison au {a.monde.adresse}", {"mode_de_retrait": "livraison", "adresse": rue, "commune": commune})
    assert "RETENU" in statuts_du_module(r), f"précondition : livraison retenue à l'adresse de démo\n{trace(a)}"


def sauter_si_aucun(p, raison: str):
    if p is None:
        pytest.skip(f"sans objet pour cette carte : {raison}")


async def refuser_la_proposition(a) -> None:
    q = a.p.get("question") or {}
    if q.get("type") == "proposition":
        await a.jouer_la_fiche("non merci", {"reponse": {"question_id": "?", "sens": "refuse"}})


# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("slug", SLUGS)
async def test_g0_une_commande_menee_jusqu_a_l_enregistrement(appel_de, slug):
    a = await appel_de(slug)
    f = profil(slug)
    await emporter(a)
    r = await a.jouer_la_fiche(f"un {nom_du_plat(f['simple'])}", {"ajouter": [art(nom_du_plat(f["simple"]))]})
    assert "OK" in statuts_du_module(r), trace(a)
    fin = {"c_est_tout": True}
    for _ in range(8):
        if r["statut"] == "ENREGISTREE":
            break
        q = (a.p.get("question") or {}).get("type")
        manques = {x.get("manque") for x in r.get("resultats") or []}
        if q == "proposition":
            r = await a.jouer_la_fiche("non merci, c'est tout", {**fin, "reponse": {"question_id": "?", "sens": "refuse"}})
        elif q == "relecture":
            r = await a.jouer_la_fiche("oui c'est bon, par carte", {"reponse": {"question_id": "?", "sens": "accepte"}, "moyen_de_paiement": "carte_bancaire"})
        elif "telephone" in manques or "confirmer_numero" in manques:
            r = await a.jouer_la_fiche("zéro six zéro zéro zéro zéro zéro zéro zéro zéro", {"telephone": "0600000000"})
        elif "prenom" in manques:
            r = await a.jouer_la_fiche("Léa", {"prenom": "Léa"})
        elif "paiement" in manques:
            r = await a.jouer_la_fiche("par carte", {"moyen_de_paiement": "carte_bancaire"})
        else:
            r = await a.jouer_la_fiche("non c'est tout", fin)
        fin = {}
    assert r["statut"] == "ENREGISTREE", f"l'agent est bloqué\n{trace(a)}"


@pytest.mark.parametrize("slug", SLUGS)
async def test_g1_un_article_simple(appel_de, slug):
    a = await appel_de(slug)
    f = profil(slug)
    await emporter(a)
    r = await a.jouer_la_fiche(f"deux {nom_du_plat(f['simple'])}", {"ajouter": [art(nom_du_plat(f["simple"]), 2)]})
    assert statuts_du_module(r)[:1] == ["OK"] and a.quantite_de(f["simple"]["nom"]) == 2, trace(a)


@pytest.mark.parametrize("slug", SLUGS)
async def test_g2_la_taille_est_demandee_puis_posee(appel_de, slug):
    a = await appel_de(slug)
    f = profil(slug)
    sauter_si_aucun(f["a_tailles"], "aucun produit à plusieurs tailles")
    p = f["a_tailles"]
    options = [d["nom"] for d in p["declinaisons"]]
    await emporter(a)
    r = await a.jouer_la_fiche(f"un {p['nom']}", {"ajouter": [art(p["nom"])]})
    assert "CHOIX_OBLIGATOIRE" in statuts_du_module(r) and (a.p.get("question") or {}).get("type") == "variante", "la taille n'est pas demandée\n" + trace(a)
    assert options == options_de(r), trace(a)
    await a.jouer_la_fiche(options[-1], {"reponse": {"question_id": "?", "sens": "accepte", "valeurs": [options[-1]]}})
    assert a.quantite_de(f"{p['nom']} {options[-1]}") == 1, trace(a)


@pytest.mark.parametrize("slug", SLUGS)
async def test_g2b_la_taille_dite_dans_la_phrase_n_est_pas_redemandee(appel_de, slug):
    a = await appel_de(slug)
    f = profil(slug)
    sauter_si_aucun(f["a_tailles"], "aucun produit à plusieurs tailles")
    p = f["a_tailles"]
    taille = p["declinaisons"][0]["nom"]
    await emporter(a)
    r = await a.jouer_la_fiche(f"un {p['nom']} en {taille}", {"ajouter": [art(p["nom"])]})  # comme l'ancien appel : la taille dans les mots seulement
    assert "CHOIX_OBLIGATOIRE" not in statuts_du_module(r) and a.quantite_de(f"{p['nom']} {taille}") == 1, "la taille dite dans les mots est redemandée\n" + trace(a)


@pytest.mark.parametrize("slug", SLUGS)
async def test_g3_le_choix_obligatoire_est_demande_puis_pose(appel_de, slug):
    a = await appel_de(slug)
    f = profil(slug)
    sauter_si_aucun(f["a_choix"], "aucun produit à choix obligatoire")
    p = f["a_choix"]
    await emporter(a)
    r = await a.jouer_la_fiche(f"un {p['nom']}", {"ajouter": [art(p["nom"])]})
    assert "CHOIX_OBLIGATOIRE" in statuts_du_module(r), "le choix obligatoire n'est pas demandé\n" + trace(a)
    options = options_de(r)
    assert options, trace(a)
    await a.jouer_la_fiche(options[0], {"reponse": {"question_id": "?", "sens": "accepte", "valeurs": [options[0]]}})
    assert a.quantite_de(p["nom"]) == 1, trace(a)


@pytest.mark.parametrize("slug", SLUGS)
async def test_g4_le_retrait_sans_x(appel_de, slug):
    a = await appel_de(slug)
    f = profil(slug)
    sauter_si_aucun(f["a_retrait"], "aucun ingrédient retirable dans la carte")
    p = f["a_retrait"]
    ingredient = next(i["nom"] for i in p["ingredients"] if i.get("retirable"))
    taille = p["declinaisons"][0]["nom"] if len(p["declinaisons"]) > 1 else None
    await emporter(a)
    r = await a.jouer_la_fiche(f"un {p['nom']} {taille or ''} sans {ingredient}", {"ajouter": [art(p["nom"], 1, taille, sans=[ingredient])]})
    assert statuts_du_module(r)[:1] == ["OK"], trace(a)
    assert any(ingredient.lower() in " ".join(l.get("retires") or []).lower() for l in a.p["lignes"]), f"« sans {ingredient} » n'est pas posé\n" + trace(a)


@pytest.mark.parametrize("slug", SLUGS)
async def test_g5_la_moitie_moitie(appel_de, slug):
    a = await appel_de(slug)
    f = profil(slug)
    sauter_si_aucun(f["moitie"], "la carte n'a pas de moitié-moitié")
    await emporter(a)
    r = await a.jouer_la_fiche("moitié reine moitié 4 fromages, en mega", {"ajouter": [art(f["moitie"]["nom"], 1, "Mega", moities=["reine", "4 fromages"])]})
    assert statuts_du_module(r)[:1] == ["OK"] and a.quantite_de(f["moitie"]["nom"]) == 1, "moitiés dites avec les noms courants" + trace(a)


@pytest.mark.parametrize("slug", SLUGS)
async def test_g6_une_formule(appel_de, slug):
    a = await appel_de(slug)
    f = profil(slug)
    sauter_si_aucun(f["formule"], "la carte n'a pas de formule")
    await emporter(a)
    r = await a.jouer_la_fiche(f"un {f['formule']['nom']}", {"ajouter": [art(f["formule"]["nom"])]})
    assert not set(statuts_du_module(r)) & set(REFUS), f"la formule « {f['formule']['nom']} » n'est pas prise\n" + trace(a)
    assert a.quantite_de(f["formule"]["nom"]) >= 1, "la formule n'est pas au panier\n" + trace(a)


@pytest.mark.parametrize("slug", SLUGS)
async def test_g7_le_minimum_de_zone(appel_de, slug):
    a = await appel_de(slug, minimum=3000)
    f = profil(slug)
    await livraison(a)
    r = await a.jouer_la_fiche(f"un {nom_du_plat(f['simple'])}", {"ajouter": [art(nom_du_plat(f["simple"]))]})
    sous_total = f["prix"](f["simple"])
    manques = [((x.get("faits") or {}).get("minimum_non_atteint") or {}).get("manque") for x in r.get("resultats") or []]
    assert 3000 - sous_total in manques, f"manque attendu {3000 - sous_total}, rendu {manques}\n" + trace(a)
    await refuser_la_proposition(a)
    n = math.ceil(3000 / sous_total)
    r = await a.jouer_la_fiche(f"{n} de plus", {"ajouter": [art(nom_du_plat(f["simple"]), n)]})
    assert not any((x.get("faits") or {}).get("minimum_non_atteint") for x in r.get("resultats") or []), "minimum atteint mais toujours dit manquant\n" + trace(a)


async def _premier_article_et_proposition(appel_de, slug):
    f = profil(slug)
    a = await appel_de(slug)
    await emporter(a)
    await a.jouer_la_fiche(f"un {nom_du_plat(f['simple'])}", {"ajouter": [art(nom_du_plat(f["simple"]))]})
    q = a.p.get("question") or {}
    if q.get("type") != "proposition":
        pytest.skip("la carte ne propose rien en plus (aucune proposition rendue après le premier article) : le cas est vide, pas rouge")
    return a, q.get("article_propose")


@pytest.mark.parametrize("slug", SLUGS)
async def test_g8a_la_vente_en_plus_acceptee(appel_de, slug):
    a, proposee = await _premier_article_et_proposition(appel_de, slug)
    await a.jouer_la_fiche("oui", {"reponse": {"question_id": "?", "sens": "accepte"}})
    assert a.quantite_de(proposee) >= 1, f"« oui » à la proposition « {proposee} » : elle n'est pas au panier" + trace(a)


@pytest.mark.parametrize("slug", SLUGS)
async def test_g8b_la_vente_en_plus_refusee(appel_de, slug):
    a, proposee = await _premier_article_et_proposition(appel_de, slug)
    await a.jouer_la_fiche("non merci", {"reponse": {"question_id": "?", "sens": "refuse"}})
    assert a.quantite_de(proposee) == 0, "« non » à la proposition : elle est au panier" + trace(a)


@pytest.mark.parametrize("slug", SLUGS)
async def test_g9a_sans_x_sur_un_produit_sans_ingredients_ne_bloque_pas(appel_de, slug):
    a = await appel_de(slug)
    f = profil(slug)
    sauter_si_aucun(f["sans_ingredients"], "tous les produits ont des ingrédients")
    p = f["sans_ingredients"]
    await emporter(a)
    r = await a.jouer_la_fiche(f"un {p['nom']} sans piment", {"ajouter": [art(p["nom"], sans=["piment"])]})
    assert not set(statuts_du_module(r)) & set(REFUS) and a.quantite_de(p["nom"]) == 1, "un « sans » sur un produit sans liste d'ingrédients bloque\n" + trace(a)


@pytest.mark.parametrize("slug", SLUGS)
async def test_g9b_une_question_sur_un_produit_sans_allergenes_ne_bloque_pas(appel_de, slug):
    a = await appel_de(slug)
    f = profil(slug)
    sauter_si_aucun(f["sans_allergenes"], "tous les produits ont des allergènes")
    p = f["sans_allergenes"]
    await emporter(a)
    r = await a.jouer_la_fiche(f"il y a quoi dans le {p['nom']} ?", {"_lire": {"sujet": "article", "article": p["nom"]}})
    assert r["statut"] in ("LU", "A_PRECISER"), f"lire un produit sans allergènes ni description plante ou refuse : {r['statut']}\n" + str(r)[:300]
    r = await a.jouer_la_fiche(f"un {p['nom']}", {"ajouter": [art(p["nom"])]})
    assert a.quantite_de(p["nom"]) >= 1 or "CHOIX_OBLIGATOIRE" in statuts_du_module(r), trace(a)

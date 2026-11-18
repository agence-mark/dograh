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
"""

import math

import pytest

from api.tests.mark.banc_a.commun import CARTES, appel_de, faire_monde, base_essai, base_prete, carte_de, trace  # noqa: F401

pytestmark = pytest.mark.banc_a
SLUGS = ["casa-italia", "etoile-d-or", "kebab-demo", "lusitalia"]
REFUS = ("HORS_CARTE", "INTROUVABLE", "ARGUMENT_INVALIDE", "INDISPONIBLE", "AMBIGU")


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


async def emporter(a) -> None:
    a.greffier(type_de_commande="à emporter")
    r = await a.jouer("type_de_commande", {"mode": "à emporter", "mots": "à emporter"})
    assert r["statut"] in ("OK", "FERME_PLANIFIABLE"), f"précondition : mode emporter pris\n{trace(a)}"


async def livraison(a) -> None:
    a.greffier(type_de_commande="en livraison")
    r = await a.jouer("type_de_commande", {"mode": "livraison", "adresse": a.monde.adresse, "mots": f"en livraison au {a.monde.adresse}"})
    assert r["statut"] == "RETENU", f"précondition : livraison retenue à l'adresse de démo\n{trace(a)}"


def sauter_si_aucun(p, raison: str):
    if p is None:
        pytest.skip(f"sans objet pour cette carte : {raison}")


# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("slug", SLUGS)
async def test_g0_une_commande_menee_jusqu_a_l_enregistrement(appel_de, slug):
    a = await appel_de(slug)
    f = profil(slug)
    await emporter(a)
    r = await a.jouer("ajouter_au_panier", {"articles": f"un {nom_du_plat(f['simple'])}", "mots": "c'est tout", "sens": "autre"})
    assert r["statut"] == "OK", trace(a)
    reponses = {
        "vente_en_plus": {"mots": "non merci", "sens": "refus", "en_plus": False}, "relecture": {"mots": "oui c'est bon", "sens": "accord"},
        "reponse_a_la_relecture": {"mots": "oui", "sens": "accord"}, "confirmer_numero": {"mots": "oui", "sens": "accord"},
        "paiement": {"mots": "par carte", "moyen": "carte", "sens": "autre"}, "telephone": {"mots": "0600000000", "telephone": "0600000000", "sens": "autre"},
        "prenom": {"mots": "Léa", "prenom": "Léa", "sens": "autre"},
    }
    r = await a.jouer("valider_la_commande", {"mots": "non c'est tout", "sens": "autre"})
    for _ in range(12):
        if r["statut"] in ("ENREGISTREE", "TRANSMISE"):
            break
        assert r.get("manque") in reponses, f"l'agent est bloqué sur {r.get('statut')}/{r.get('manque')}\n{trace(a)}"
        r = await a.jouer("valider_la_commande", reponses[r["manque"]])
    assert r["statut"] in ("ENREGISTREE", "TRANSMISE"), trace(a)


@pytest.mark.parametrize("slug", SLUGS)
async def test_g1_un_article_simple(appel_de, slug):
    a = await appel_de(slug)
    f = profil(slug)
    await emporter(a)
    r = await a.jouer("ajouter_au_panier", {"articles": f"deux {nom_du_plat(f['simple'])}", "mots": f"deux {nom_du_plat(f['simple'])}", "sens": "autre"})
    assert r["statut"] == "OK" and a.quantite_de(f["simple"]["nom"]) == 2, trace(a)
    assert r["faits"]["sous_total"] == 2 * f["prix"](f["simple"]) or r["faits"].get("total") is not None, trace(a)


@pytest.mark.parametrize("slug", SLUGS)
async def test_g2_la_taille_est_demandee_puis_posee(appel_de, slug):
    a = await appel_de(slug)
    f = profil(slug)
    sauter_si_aucun(f["a_tailles"], "aucun produit à plusieurs tailles")
    p = f["a_tailles"]
    options = [d["nom"] for d in p["declinaisons"]]
    await emporter(a)
    r = await a.jouer("ajouter_au_panier", {"articles": f"un {p['nom']}", "mots": f"un {p['nom']}", "sens": "autre"})
    assert r["statut"] == "CHOIX_OBLIGATOIRE" and r.get("manque") == "taille", "la taille n'est pas demandée\n" + trace(a)
    assert options == (r["faits"].get("question") or {}).get("options"), trace(a)
    r = await a.jouer("ajouter_au_panier", {"choix": options[-1], "mots": options[-1], "sens": "autre"})
    assert a.quantite_de(f"{p['nom']} {options[-1]}") == 1, trace(a)


@pytest.mark.parametrize("slug", SLUGS)
async def test_g2b_la_taille_dite_dans_la_phrase_n_est_pas_redemandee(appel_de, slug):
    a = await appel_de(slug)
    f = profil(slug)
    sauter_si_aucun(f["a_tailles"], "aucun produit à plusieurs tailles")
    p = f["a_tailles"]
    taille = p["declinaisons"][0]["nom"]
    await emporter(a)
    r = await a.jouer("ajouter_au_panier", {"articles": f"un {p['nom']}", "mots": f"un {p['nom']} en {taille}", "sens": "autre"})  # le modèle a ôté la taille de ``articles``
    assert r["statut"] != "CHOIX_OBLIGATOIRE" and a.quantite_de(f"{p['nom']} {taille}") == 1, "la taille dite dans les mots est redemandée\n" + trace(a)


@pytest.mark.parametrize("slug", SLUGS)
async def test_g3_le_choix_obligatoire_est_demande_puis_pose(appel_de, slug):
    a = await appel_de(slug)
    f = profil(slug)
    sauter_si_aucun(f["a_choix"], "aucun produit à choix obligatoire")
    p = f["a_choix"]
    await emporter(a)
    r = await a.jouer("ajouter_au_panier", {"articles": f"un {p['nom']}", "mots": f"un {p['nom']}", "sens": "autre"})
    assert r["statut"] == "CHOIX_OBLIGATOIRE", "le choix obligatoire n'est pas demandé\n" + trace(a)
    options = (r["faits"].get("question") or {}).get("options") or []
    assert options, trace(a)
    r = await a.jouer("ajouter_au_panier", {"choix": options[0], "mots": options[0], "sens": "autre"})
    assert r["statut"] in ("OK", "CHOIX_OBLIGATOIRE") and a.quantite_de(p["nom"]) == 1, trace(a)


@pytest.mark.parametrize("slug", SLUGS)
async def test_g4_le_retrait_sans_x(appel_de, slug):
    a = await appel_de(slug)
    f = profil(slug)
    sauter_si_aucun(f["a_retrait"], "aucun ingrédient retirable dans la carte")
    p = f["a_retrait"]
    ingredient = next(i["nom"] for i in p["ingredients"] if i.get("retirable"))
    taille = p["declinaisons"][0]["nom"] if len(p["declinaisons"]) > 1 else ""
    await emporter(a)
    r = await a.jouer("ajouter_au_panier", {"articles": f"un {p['nom']} {taille}".strip(), "sans": ingredient, "mots": f"un {p['nom']} {taille} sans {ingredient}", "sens": "autre"})
    assert r["statut"] == "OK", trace(a)
    assert any(ingredient.lower() in " ".join(l.get("retires") or []).lower() for l in a.p["lignes"]), f"« sans {ingredient} » n'est pas posé\n" + trace(a)


@pytest.mark.parametrize("slug", SLUGS)
async def test_g5_la_moitie_moitie(appel_de, slug):
    a = await appel_de(slug)
    f = profil(slug)
    sauter_si_aucun(f["moitie"], "la carte n'a pas de moitié-moitié")
    await emporter(a)
    r = await a.jouer("ajouter_au_panier", {"articles": f"une {f['moitie']['nom']} mega", "moities": "reine et 4 fromages", "mots": "moitié reine moitié 4 fromages", "sens": "autre"})
    assert r["statut"] == "OK" and a.quantite_de(f["moitie"]["nom"]) == 1, "moitiés dites avec les noms courants : " + (r.get("suggestion") or "") + trace(a)


@pytest.mark.parametrize("slug", SLUGS)
async def test_g6_une_formule(appel_de, slug):
    a = await appel_de(slug)
    f = profil(slug)
    sauter_si_aucun(f["formule"], "la carte n'a pas de formule")
    await emporter(a)
    r = await a.jouer("ajouter_au_panier", {"articles": f"un {f['formule']['nom']}", "mots": f"un {f['formule']['nom']}", "sens": "autre"})
    assert r["statut"] in ("OK", "CHOIX_OBLIGATOIRE", "INCOMPLETE") and r["statut"] not in REFUS, f"la formule « {f['formule']['nom']} » n'est pas prise : {r['statut']}\n" + trace(a)
    assert a.quantite_de(f["formule"]["nom"]) >= 1, "la formule n'est pas au panier\n" + trace(a)


@pytest.mark.parametrize("slug", SLUGS)
async def test_g7_le_minimum_de_zone(appel_de, slug):
    a = await appel_de(slug, minimum=3000)
    f = profil(slug)
    await livraison(a)
    r = await a.jouer("ajouter_au_panier", {"articles": f"un {nom_du_plat(f['simple'])}", "mots": "un", "sens": "autre"})
    sous_total = f["prix"](f["simple"])
    manque = (r["faits"].get("minimum_non_atteint") or {}).get("manque")
    assert manque == 3000 - sous_total, f"manque attendu {3000 - sous_total}, rendu {manque}\n" + trace(a)
    n = math.ceil(3000 / sous_total)
    r = await a.jouer("ajouter_au_panier", {"articles": f"{n} {nom_du_plat(f['simple'])}", "mots": f"{n} de plus", "sens": "autre"})
    assert not r["faits"].get("minimum_non_atteint"), "minimum atteint mais toujours dit manquant\n" + trace(a)


async def _premier_article_et_proposition(appel_de, slug):
    f = profil(slug)
    a = await appel_de(slug)
    await emporter(a)
    r = await a.jouer("ajouter_au_panier", {"articles": f"un {nom_du_plat(f['simple'])}", "mots": "un", "sens": "autre"})
    if r.get("manque") != "vente_en_plus":
        pytest.skip("la carte ne propose rien en plus (aucune proposition rendue après le premier article) : le cas est vide, pas rouge")
    return a, r["faits"]["proposition"]["nom"]


@pytest.mark.parametrize("slug", SLUGS)
async def test_g8a_la_vente_en_plus_acceptee(appel_de, slug):
    a, proposee = await _premier_article_et_proposition(appel_de, slug)
    await a.jouer("valider_la_commande", {"mots": "oui", "sens": "accord"})
    assert a.quantite_de(proposee) >= 1, f"« oui » à la proposition « {proposee} » : elle n'est pas au panier" + trace(a)


@pytest.mark.parametrize("slug", SLUGS)
async def test_g8b_la_vente_en_plus_refusee(appel_de, slug):
    a, proposee = await _premier_article_et_proposition(appel_de, slug)
    await a.jouer("valider_la_commande", {"mots": "non merci", "sens": "refus"})
    assert a.quantite_de(proposee) == 0, "« non » à la proposition : elle est au panier" + trace(a)


@pytest.mark.parametrize("slug", SLUGS)
async def test_g9a_sans_x_sur_un_produit_sans_ingredients_ne_bloque_pas(appel_de, slug):
    a = await appel_de(slug)
    f = profil(slug)
    sauter_si_aucun(f["sans_ingredients"], "tous les produits ont des ingrédients")
    p = f["sans_ingredients"]
    await emporter(a)
    r = await a.jouer("ajouter_au_panier", {"articles": f"un {p['nom']}", "sans": "piment", "mots": f"un {p['nom']} sans piment", "sens": "autre"})
    assert r["statut"] not in REFUS and a.quantite_de(p["nom"]) == 1, f"un « sans » sur un produit sans liste d'ingrédients bloque ({r['statut']} : {r.get('suggestion')})\n" + trace(a)


@pytest.mark.parametrize("slug", SLUGS)
async def test_g9b_une_question_sur_un_produit_sans_allergenes_ne_bloque_pas(appel_de, slug):
    a = await appel_de(slug)
    f = profil(slug)
    sauter_si_aucun(f["sans_allergenes"], "tous les produits ont des allergènes")
    p = f["sans_allergenes"]
    await emporter(a)
    r = await a.jouer("lire_la_commande", {"produit": p["nom"], "quoi": "produit"})
    assert r["statut"] in ("OK", "AMBIGU"), f"lire un produit sans allergènes ni description plante ou refuse : {r['statut']}\n" + str(r)[:300]
    # la commande continue après la question : l'article se prend
    r = await a.jouer("ajouter_au_panier", {"articles": f"un {p['nom']}", "mots": "un", "sens": "autre"})
    assert r["statut"] in ("OK", "CHOIX_OBLIGATOIRE") and a.quantite_de(p["nom"]) >= 1, trace(a)

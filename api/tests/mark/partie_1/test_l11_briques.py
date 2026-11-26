"""[.mark] Chantier Partie 1, lot 11 : les briques formules et menus (``services/commande/briques/for*.py``, ``formule.py``).

Une classe par brique (``TestFOR1`` ... ``TestFOR15``), chacune avec sa règle, son aller-retour en caisse (un deal HubRise : un article par choix, ``fixed_price``) et son test de
rendu de la fiche (D66) ; plus la migration 040, le plat de formule (ses choix, ses retraits, son alcool et sa TVA), ``placer_les_choix``, ``remplacer_un_choix``, les deux gardes
de la fiche (B10, B11) et les trois conflits de D34. Un test = un essai à la fois.
"""

from __future__ import annotations

import json

import pytest

from api.db.bases_clients import restauration_commande as RC
from api.db.bases_clients import restauration_ecran
from api.services.actions_communes import conversation as CONV
from api.services.restauration.caisse.prises.hubrise_traduction import carte_de_hubrise, carte_vers_hubrise, centimes, commande_vers_hubrise
from api.tests.mark.banc_a.commun import carte_de
from api.tests.mark.partie_1.aides_briques import brique, fait, la_brique_change_la_fiche, descendre_jusqu_a
from api.tests.mark.test_base_client import base_essai  # noqa: F401
from api.services.commande.moteur import socle as _socle


def _choix(*codes: str, **sous) -> list[dict]:
    return [{"option_code": c, "quantite": 1, "choix": list(sous.get(c, []))} for c in codes]


async def _chiffrer(e, code: str, choix: list[dict], quantite: int = 1, mode: str = "emporter"):
    return await RC.chiffrer_panier(e.monde.c, e.monde.a, mode, [{"code_caisse": code, "quantite": quantite, "choix": choix}])


def _total_hubrise(corps: dict) -> int:
    """Ce que HubRise recalcule : la somme des articles et de leurs options (documentation order-management : HubRise ne calcule rien sur un deal)."""
    total = 0
    for a in corps["items"]:
        q = int(a["quantity"])
        total += (centimes(a["price"]) + sum(centimes(o["price"]) * int(o.get("quantity", 1)) for o in a.get("options") or [])) * q
    return total


async def formule_en_caisse(e, code: str, choix: list[dict], quantite: int = 1, mode: str = "emporter") -> dict:
    """L'aller-retour en caisse d'une formule : la ligne chiffrée, la commande, le corps ``POST /location/orders`` (un deal, un article par choix) ; la caisse retrouve
    notre prix."""
    r = await _chiffrer(e, code, choix, quantite, mode)
    assert r.statut == "OK", r
    corps = commande_vers_hubrise({"numero": "n-1", "mode": mode, "client": {}, "lignes": r.faits["lignes"]})
    assert _total_hubrise(corps) == r.faits["lignes"][0]["prix_unitaire"] * quantite, corps
    assert all(a["deal_line"]["pricing_effect"] == "fixed_price" for a in corps["items"]) and len(corps["deals"]) == 1, corps
    return corps


def catalogue_aller_retour(code: str) -> dict:
    """La carte de la brique écrite au catalogue HubRise puis relue (format commun) : les formules gardent leurs lignes, leurs suppléments et leurs réglages."""
    carte = carte_de(f"briques/{code}")
    ecrite = carte_vers_hubrise(carte)
    relue = carte_de_hubrise({"categories": ecrite.donnees["categories"], "products": ecrite.donnees["products"], "option_lists": ecrite.donnees["option_lists"],
                              "deals": ecrite.donnees["deals"]}).carte
    return {"ecrite": ecrite.donnees, "relue": relue, "carte": carte}


async def objets_charges(e) -> None:
    """Les objets de la carte tels que le chargement de l'appel les calcule (lot 5) : une case de brique (``personnes``) n'existe que si la carte en a l'objet."""
    from api.services.commande import contrat

    _, objets = await e.source.charger_pour_l_appel()
    e.fiche_de_l_appel[contrat.CLE_DES_OBJETS] = objets


async def _ajouter(e, parole: str, **article):
    return await e.tour(parole, ajouter=[article])


# --------------------------------------------------------------------------- #
# L11-01 : la migration 040
# --------------------------------------------------------------------------- #


async def test_migration_040_montee_descente(base_prete):
    from api.db.bases_clients import connexion as schema

    colonnes = [("resto_formule", c) for c in ("modes", "age_max", "public", "personnes", "tailles", "par_lot")] + [("resto_categorie", "inclus")]

    async def presentes(c) -> list[bool]:
        return [bool(await c.fetchval("SELECT 1 FROM information_schema.columns WHERE table_schema='mark' AND table_name=$1 AND column_name=$2", t, col)) for t, col in colonnes]

    c = await schema.connecter_proprietaire(base_prete)
    try:
        assert all(await presentes(c))
        for _ in range(2):  # descente, remontée, deux fois (rejouable)
            await descendre_jusqu_a(c, 40)  # de la tête à 040, dans l'ordre inverse
            assert not any(await presentes(c)) and 40 not in [r["version"] for r in await c.fetch("SELECT version FROM mark.schema_version")]
            assert 40 in await schema.appliquer_migrations(c)
            assert all(await presentes(c))
    finally:
        await c.close()


# --------------------------------------------------------------------------- #
# L11-02 à L11-04 : le plat de formule garde son article
# --------------------------------------------------------------------------- #


async def test_plat_de_formule_garde_ses_choix(essai_de):
    """Casa Italia, Menu burger : le cheeseburger choisi garde son groupe « Sauce » obligatoire : la sauce est demandée (avant : jamais), puis posée sur le plat."""
    e = await essai_de("casa-italia")
    await e.tour("à emporter", mode_de_retrait="emporter")
    r = await _ajouter(e, "un menu burger avec un cheeseburger et un coca", article="menu burger", quantite=1, composition=["cheeseburger", "coca"])
    ligne = e.p["lignes"][-1]
    assert ligne.get("attente") and ligne["attente"]["nom"] == "Sauce", fait(r)
    q = CONV.question_de(e.p)
    r = await e.tour("ketchup", reponse={"question_id": q["id"], "valeurs": ["ketchup"]} if q["type"] == "etape" else {"question_id": q["id"], "sens": "accepte",
                                                                                                                         "valeurs": ["ketchup"]})
    plat = next(c for c in e.p["lignes"][-1]["choix"] if c["option_code"].startswith("BUR"))
    assert [s["nom"].lower() for s in plat["choix"]] == ["ketchup"], fait(r)


async def test_plat_de_formule_garde_ses_retraits(essai_de):
    """Lusitalia, offre Prima : « sans olives » dit sur l'offre se retire de la pizza choisie qui a les olives (avant : refusé, une formule n'avait aucun retirable)."""
    e = await essai_de("lusitalia")
    await e.tour("à emporter", mode_de_retrait="emporter")
    carte = e.monde.carte
    olives = [p for p in carte["produits"] if p.get("categorie_id") == "pizzas-prima" and any("olive" in (i["nom"] or "").lower() and i.get("retirable") for i in p.get("ingredients") or [])]
    sans = [p for p in carte["produits"] if p.get("categorie_id") == "pizzas-prima" and p not in olives]
    assert olives and sans, "la carte de Lusitalia a des pizzas Prima avec et sans olives retirables"
    noms = [olives[0]["nom"], sans[0]["nom"]]
    r = await _ajouter(e, f"l'offre prima, une {noms[0]} sans olives et une {noms[1]}", article="offre prima deux pizzas sénior", quantite=1, composition=noms, sans=["olives"])
    assert any(l.get("formule_id") for l in e.p["lignes"]), fait(r)
    ligne = next(l for l in e.p["lignes"] if l.get("formule_id"))
    avec = next(c for c in ligne["choix"] if c["nom"].startswith(noms[0]))
    assert any("olive" in x.lower() for x in avec.get("retires") or []), fait(r)
    assert not any(c.get("retires") for c in ligne["choix"] if c is not avec)


async def test_formule_porte_alcool_et_tva():
    """Une formule dont un choix est une boisson alcoolisée porte l'alcool ; son taux est celui de la plus grande part de ses produits (avant : alcool faux, taux absent)."""
    biere = {"id": "PB", "nom": "Bière", "categorie_id": "B", "ingredients": [], "alcool": True, "groupes": [], "tva_par_mode": {"emporter": 20000},
             "declinaisons": [{"id": "DB", "nom": "Unique", "code_caisse": "BIERE", "prix": 400, "vendable": True, "prix_par_mode": None}]}
    plat = {"id": "PP", "nom": "Plat", "categorie_id": "P", "ingredients": [], "alcool": False, "groupes": [], "tva_par_mode": {"emporter": 10000},
            "declinaisons": [{"id": "DP", "nom": "Unique", "code_caisse": "PLAT", "prix": 1200, "vendable": True, "prix_par_mode": None}]}
    carte = {"produits": [biere, plat], "groupes": [], "categories": [], "formules": [
        {"id": "F", "nom": "Menu", "code_caisse": "MENU", "prix": 1400, "vendable": True, "categorie_id": None,
         "lignes": [{"nom": "Plat", "codes": ["PLAT"]}, {"nom": "Boisson", "codes": ["BIERE"]}]}]}
    calculees, total, erreur = RC._lignes(RC._Panier(carte, "emporter", set()), [{"code_caisse": "MENU", "quantite": 1, "choix": _choix("PLAT", "BIERE")}])
    assert erreur is None and total == 1400
    assert calculees[0]["alcool"] is True and calculees[0]["taux_tva"] == 10000
    assert [c["taux_tva"] for c in calculees[0]["choix"]] == [10000, 20000]


# --------------------------------------------------------------------------- #
# L11-20 à L11-23 : placer, remplacer, les gardes de la fiche
# --------------------------------------------------------------------------- #


async def test_placer_les_choix(essai_de):
    """Chaque mot de ``composition`` sur son étape (B10) : « nems, pad thaï » rangés sur l'entrée et le plat ; un mot choix de deux étapes est refusé, rien n'est deviné."""
    e = await brique(essai_de, "FOR2")
    await _ajouter(e, "la formule midi, des nems et un pad thaï", article="formule midi", quantite=1, composition=["nems", "pad thaï"])
    ligne = e.p["lignes"][-1]
    assert [(c["option_code"]) for c in ligne["choix"]] == ["P-NEMS-UNIQUE", "P-PADTHAI-UNIQUE"] and not ligne.get("attente"), e.retours[-1]
    from api.services.commande import moteur

    article = await e.source.article("F-MIDI", "emporter")
    double = {**article, "groupes": [*article["groupes"], {**article["groupes"][0], "id": "Entrée 2", "nom": "Entrée 2"}]}
    double["groupes"][-1]["options"] = [{**o, "code": o["code"] + "-2"} for o in double["groupes"][-1]["options"]]  # une autre étape, même nom de choix
    refus, _ = moteur.placer_les_choix(double, {"nom": "Formule midi", "choix": []}, "nems", None)
    assert refus is not None and refus.faits["raison"] == "choix_de_plusieurs_etapes" and refus.faits["etapes"] == ["Entrée", "Entrée 2"]


async def test_remplacer_un_choix(essai_de):
    """Elle change d'avis sur une étape (B11 7c) : ``changer_quantite`` avec la ligne et ``composition`` ; seul le choix de cette étape change, l'autre est gardé."""
    e = await brique(essai_de, "FOR2")
    await _ajouter(e, "la formule midi, des nems et un pad thaï", article="formule midi", quantite=1, composition=["nems", "pad thaï"])
    n = e.p["lignes"][-1]["n"]
    r = await e.tour("finalement un bo bun", changer_quantite=[{"ligne": n, "composition": ["bo bun"]}])
    assert [c["option_code"] for c in e.p["lignes"][-1]["choix"]] == ["P-NEMS-UNIQUE", "P-BOBUN-UNIQUE"], fait(r)


async def test_article_aussi_choix_d_une_etape(essai_de):
    """Dans la même fiche, la formule sans son plat et le plat à part : rien n'est ajouté, refus de la fiche avec la raison et les deux choix (B10 § 2)."""
    e = await brique(essai_de, "FOR2")
    r = await e.tour("la formule midi avec des nems, et un pad thaï", ajouter=[{"article": "formule midi", "quantite": 1, "composition": ["nems"]},
                                                                                 {"article": "pad thaï", "quantite": 1}])
    assert r.get("raison") == "article_aussi_choix_d_une_etape" and not e.p["lignes"], fait(r)
    assert len(r["refus"][0]["choix"]) == 2


async def test_article_deja_choix_de_la_formule(essai_de):
    """Le choix déjà rangé dans la formule ET le même article à part dans la même fiche : refusé (B11 point 6) ; un autre article, ajouté ; le même article au tour
    suivant, ajouté (B11 § 3)."""
    e = await brique(essai_de, "FOR2")
    fiche = [{"article": "formule midi", "quantite": 1, "composition": ["nems", "pad thaï"]}, {"article": "pad thaï", "quantite": 1}]
    r = await e.tour("la formule midi nems pad thaï, et un pad thaï", ajouter=fiche)
    assert r.get("raison") == "article_deja_choix_de_la_formule" and not e.p["lignes"], fait(r)
    r = await e.tour("la formule midi nems pad thaï, et un bo bun", ajouter=[fiche[0], {"article": "bo bun", "quantite": 1}])
    assert len(e.p["lignes"]) == 2, fait(r)
    r = await _ajouter(e, "et un pad thaï à part", article="pad thaï", quantite=1)
    assert len(e.p["lignes"]) == 3, fait(r)


# --------------------------------------------------------------------------- #
# L11-24 à L11-26 : les conflits de D34
# --------------------------------------------------------------------------- #


async def test_du_moment_coche_dans_la_ligne(essai_de):
    """ART3 et FOR3 : le dessert du jour (à 2 €) n'entre dans la ligne limitée que s'il y est coché (``inclus``), jamais déduit de son prix."""
    e = await brique(essai_de, "FOR3")
    assert await restauration_ecran.poser_le_produit_du_moment(e.monde.c, e.monde.a, "P-DESSERT-JOUR", "fondant au chocolat", "essai")
    e.monde.c.instantane = None
    article = await e.source.article("F-COMPLETE", "emporter")
    dessert = next(g for g in article["groupes"] if g["nom"] == "Dessert")
    assert "P-DESSERT-JOUR-UNIQUE" not in [o["code"] for o in dessert["options"]]
    carte = carte_de("briques/FOR3")
    carte["formules"][0]["lignes"][1]["inclus"] = ["P-COOKIE-UNIQUE", "P-DONUT-UNIQUE", "P-DESSERT-JOUR-UNIQUE"]
    e2 = await brique(essai_de, "FOR3", carte=carte)
    assert await restauration_ecran.poser_le_produit_du_moment(e2.monde.c, e2.monde.a, "P-DESSERT-JOUR", "fondant au chocolat", "essai")
    e2.monde.c.instantane = None
    article = await e2.source.article("F-COMPLETE", "emporter")
    assert "P-DESSERT-JOUR-UNIQUE" in [o["code"] for o in next(g for g in article["groupes"] if g["nom"] == "Dessert")["options"]]


async def test_jouet_compris_ou_vendu_seul(essai_de):
    """FOR7 et FOR8 : la surprise est comprise dans le menu enfant (posée d'office, 0 €) ; vendue seule à 1,50 € ; jamais facturée deux fois."""
    e = await brique(essai_de, "FOR8")
    r = await _chiffrer(e, "F-ENFANT", _choix("P-NUGGETS-UNIQUE", "P-SURPRISE-UNIQUE"))
    assert r.faits["sous_total"] == 590, r
    r = await RC.chiffrer_panier(e.monde.c, e.monde.a, "emporter", [{"code_caisse": "P-SURPRISE-UNIQUE", "quantite": 1, "choix": []}])
    assert r.faits["sous_total"] == 150
    await _ajouter(e, "un menu enfant avec des nuggets", article="menu enfant", quantite=1, composition=["nuggets"])
    assert {c["option_code"] for c in e.p["lignes"][-1]["choix"]} == {"P-NUGGETS-UNIQUE", "P-SURPRISE-UNIQUE"}, e.retours[-1]
    r = await e.tour("un menu enfant nuggets avec la surprise, et une surprise", ajouter=[
        {"article": "menu enfant", "quantite": 1, "composition": ["nuggets", "surprise"]}, {"article": "surprise", "quantite": 1}])
    assert r.get("raison") == "article_deja_choix_de_la_formule", fait(r)


async def test_maxi_garde_les_choix(essai_de):
    """FOR6 et OPT1 : passer le menu en maxi garde les choix faits et ne change que leur déclinaison ; un choix sans grande taille est refusé avec les choix."""
    e = await brique(essai_de, "FOR6")
    await _ajouter(e, "un menu whopper normal, frites, coca", article="menu whopper", quantite=1, variante="Normal", composition=["frites", "coca"])
    n = e.p["lignes"][-1]["n"]
    r = await e.tour("finalement en maxi", changer_quantite=[{"ligne": n, "variante": "Maxi"}])
    codes = {c["option_code"] for c in e.p["lignes"][-1]["choix"]}
    assert {"P-FRITES-GRANDE", "P-COCA-GRANDE"} <= codes, fait(r)
    e2 = await brique(essai_de, "FOR6")
    await _ajouter(e2, "un menu whopper normal, frites, jus", article="menu whopper", quantite=1, variante="Normal", composition=["frites", "jus d'orange"])
    n = e2.p["lignes"][-1]["n"]
    r = await e2.tour("en maxi", changer_quantite=[{"ligne": n, "variante": "Maxi"}])
    assert "choix_sans_la_taille" in fait(r) and "P-JUS-MOYENNE" in {c["option_code"] for c in e2.p["lignes"][-1]["choix"]}, fait(r)


# --------------------------------------------------------------------------- #
# L11-05 à L11-19 : les quinze briques
# --------------------------------------------------------------------------- #


class TestFOR1:
    async def test_for1_prix_de_la_formule(self, essai_de):
        """« le menu », burger, frites, coca : le prix de la formule (11,90 €), jamais la somme (14,40 €) ; « le menu » sur une carte à deux menus : départagé par la
        composition ; la sauce du burger demandée."""
        e = await brique(essai_de, "FOR1")
        r = await _ajouter(e, "le menu avec un burger, des frites et un coca", article="menu", quantite=1, composition=["burger classique", "frites", "coca"])
        assert e.p["lignes"], fait(r)
        ligne = e.p["lignes"][-1]
        assert ligne["ref"] == "F-MENU-BURGER" and ligne.get("attente", {}).get("nom") == "Sauce", fait(r)
        r = await _chiffrer(e, "F-MENU-BURGER", _choix("P-BURGER-UNIQUE", "P-FRITES-UNIQUE", "P-COCA-UNIQUE", **{"P-BURGER-UNIQUE": [{"option_code": "G-SAUCE-KETCHUP", "quantite": 1}]}))
        assert r.faits["sous_total"] == 1190
        r = await _chiffrer(e, "F-MENU-BURGER", _choix("P-BURGER-UNIQUE", "P-FRITES-UNIQUE", "P-COCA-UNIQUE", **{"P-BURGER-UNIQUE": [
            {"option_code": "G-SAUCE-KETCHUP", "quantite": 1}, {"option_code": "G-SUPPL-BACON", "quantite": 1}]}))
        assert r.faits["sous_total"] == 1190 + 150  # un supplément du plat reste payant

    async def test_for1_menu_et_ses_choix_dans_le_nom_de_l_article(self, essai_de):
        """Conversation du lot 11 (FOR1-A) : le modèle écrit toute la phrase dans ``article`` (« menu avec un burger, des frites et un coca »), sans
        ``composition`` ; la recherche rend Menu burger, Frites et Coca. Ce ne sont pas trois possibilités : la formule et deux choix de ses étapes. Le code
        retient la formule, les deux autres candidats y sont rangés, jamais la question « Menu burger, Frites ou Coca ? »."""
        e = await brique(essai_de, "FOR1")
        r = await _ajouter(e, "le menu avec un burger, des frites et un coca", article="menu avec un burger, des frites et un coca", quantite=1)
        assert e.p["lignes"], fait(r)
        ligne = e.p["lignes"][-1]
        assert ligne["ref"] == "F-MENU-BURGER" and ligne.get("attente", {}).get("nom") == "Sauce", fait(r)
        assert {"P-BURGER-UNIQUE", "P-FRITES-UNIQUE", "P-COCA-UNIQUE"} <= {c["option_code"] for c in ligne["choix"]}, fait(r)

    async def test_for1_deux_formules_candidates_le_doute_reste(self, essai_de):
        """Deux formules parmi les candidats (« un menu burger ou salade avec un coca ») : aucune n'a l'autre pour choix, le doute reste."""
        e = await brique(essai_de, "FOR1")
        r = await _ajouter(e, "un menu burger ou salade avec un coca", article="menu burger menu salade coca", quantite=1)
        assert not e.p["lignes"] and r["statut"] != "FAIT", fait(r)

    async def test_for1_aller_retour_caisse(self, essai_de):
        e = await brique(essai_de, "FOR1")
        choix = _choix("P-BURGER-UNIQUE", "P-FRITES-UNIQUE", "P-COCA-UNIQUE", **{"P-BURGER-UNIQUE": [{"option_code": "G-SAUCE-KETCHUP", "quantite": 1}]})
        corps = await formule_en_caisse(e, "F-MENU-BURGER", choix)
        assert [a["sku_ref"] for a in corps["items"]] == ["P-BURGER-UNIQUE", "P-FRITES-UNIQUE", "P-COCA-UNIQUE"] and corps["items"][0]["price"] == "11.90 EUR"
        assert corps["items"][0]["options"][0]["name"] == "Ketchup" and corps["deals"]["0"]["ref"] == "F-MENU-BURGER"
        assert catalogue_aller_retour("FOR1")["ecrite"]["deals"][0]["lines"][0]["skus"]

    async def test_for1_fiche_du_modele(self, essai_de):
        assert await la_brique_change_la_fiche("FOR1", essai_de)


class TestFOR2:
    async def test_for2_une_etape_a_la_fois(self, essai_de):
        """« la formule midi, entrée plat » sans le plat : une question numérotée de type étape (``sens`` caché), posée par le modèle ; la réponse range le plat."""
        e = await brique(essai_de, "FOR2")
        r = await _ajouter(e, "la formule midi avec des nems", article="formule midi", quantite=1, composition=["nems"])
        q = CONV.question_de(e.p)
        assert q and q["type"] == "etape" and r["statut"] == "A_PRECISER" and r["question"]["reponses"] == ["son choix, dans valeurs"], fait(r)
        r = await e.tour("un bo bun", reponse={"question_id": q["id"], "valeurs": ["bo bun"]})
        assert [c["option_code"] for c in e.p["lignes"][-1]["choix"]] == ["P-NEMS-UNIQUE", "P-BOBUN-UNIQUE"] and not e.p["lignes"][-1].get("attente"), fait(r)

    async def test_for2_reponse_d_etape_une_seule_valeur(self, essai_de):
        e = await brique(essai_de, "FOR2")
        await _ajouter(e, "la formule midi avec des nems", article="formule midi", quantite=1, composition=["nems"])
        q = CONV.question_de(e.p)
        r = await e.tour("un bo bun et un pad thaï", reponse={"question_id": q["id"], "valeurs": ["bo bun", "pad thaï"]})
        assert "plusieurs_choix" in fait(r) and CONV.question_de(e.p)["id"] == q["id"], fait(r)

    async def test_for2_aller_retour_caisse(self, essai_de):
        e = await brique(essai_de, "FOR2")
        corps = await formule_en_caisse(e, "F-MIDI", _choix("P-NEMS-UNIQUE", "P-BOBUN-UNIQUE"))
        assert [a["deal_line"]["label"] for a in corps["items"]] == ["Entrée", "Plat"]

    async def test_for2_fiche_du_modele(self, essai_de):
        assert await la_brique_change_la_fiche("FOR2", essai_de)


class TestFOR3:
    async def test_for3_refuser_hors_liste(self, essai_de):
        """Un dessert à 3,50 € dans la formule complète : refusé (``hors_sous_ensemble``) avec les choix de l'étape ; la règle chiffrée est un fait du retour que le modèle
        dit avec ses mots (lot 7b, Q1) ; le code ne dit rien avant."""
        e = await brique(essai_de, "FOR3")
        r = await _ajouter(e, "la formule complète avec un tiramisu", article="formule complète", quantite=1, composition=["tacos", "tiramisu"])
        assert "hors_sous_ensemble" in fait(r) and not e.p["lignes"], fait(r)
        assert r["faits"]["regle_de_la_ligne"]["prix_max"] == 200 and set(r["faits"]["regle_de_la_ligne"]) == {"formule", "etape", "prix_max"} and not _prefixe(e), fait(r)

    async def test_for3_menu_bambino_mega_refusee(self, essai_de):
        """Lusitalia, Menu Bambino : la Méga écartée de la ligne (donnée posée en mémoire, la vraie au formulaire de démo du lot 18) ; la Sénior acceptée."""
        carte = carte_de("lusitalia")
        bambino = next(f for f in carte["formules"] if f["nom"] == "Menu Bambino")
        megas = [d["code_caisse"] for p in carte["produits"] if p.get("categorie_id") == "pizzas-prima" for d in p["declinaisons"] if d["nom"] == "Méga"]
        bambino["lignes"][0]["exclus"] = megas
        e = await essai_de("lusitalia", carte=carte)
        await e.tour("à emporter", mode_de_retrait="emporter")
        article = await e.source.article(bambino["id"], "emporter")
        ligne = article["groupes"][0]
        assert ligne["options"] and not any(o["code"] in megas for o in ligne["options"]) and {h["code"] for h in ligne["hors_ligne"]} == set(megas)

    async def test_for3_aller_retour_caisse(self, essai_de):
        e = await brique(essai_de, "FOR3")
        await formule_en_caisse(e, "F-COMPLETE", _choix("P-TACOS-UNIQUE", "P-COOKIE-UNIQUE"))
        r = await _chiffrer(e, "F-COMPLETE", _choix("P-TACOS-UNIQUE", "P-TIRAMISU-UNIQUE"))
        assert r.statut == "HORS_CARTE" and r.faits.get("raison") == "hors_sous_ensemble"
        assert catalogue_aller_retour("FOR3")["relue"]["formules"][0]["lignes"][1]["prix_max"] == 200

    async def test_for3_fiche_du_modele(self, essai_de):
        assert await la_brique_change_la_fiche("FOR3", essai_de)


class TestFOR4:
    async def test_for4_ajouter_le_supplement_de_ligne(self, essai_de):
        e = await brique(essai_de, "FOR4")
        assert (await _chiffrer(e, "F-MIDI", _choix("P-NEMS-UNIQUE", "P-PADTHAI-UNIQUE"))).faits["sous_total"] == 1700 + 100
        assert (await _chiffrer(e, "F-MIDI", _choix("P-NEMS-UNIQUE", "P-BOBUN-UNIQUE"))).faits["sous_total"] == 1700

    async def test_for4_aller_retour_caisse(self, essai_de):
        e = await brique(essai_de, "FOR4")
        corps = await formule_en_caisse(e, "F-MIDI", _choix("P-NEMS-UNIQUE", "P-PADTHAI-UNIQUE"))
        assert [a["price"] for a in corps["items"]] == ["17.00 EUR", "1.00 EUR"]
        lignes = catalogue_aller_retour("FOR4")
        skus = lignes["ecrite"]["deals"][0]["lines"][1]["skus"]
        assert {"ref": "P-PADTHAI-UNIQUE", "extra_charge": "1.00 EUR"} in skus
        assert lignes["relue"]["formules"][0]["lignes"][1]["supplements"] == {"P-PADTHAI-UNIQUE": 100}

    async def test_for4_fiche_du_modele(self, essai_de):
        assert not await la_brique_change_la_fiche("FOR4", essai_de)


class TestFOR5:
    async def test_for5_prix_en_menu(self, essai_de):
        """« le Texas en menu » : la formule trouvée par la composition, au prix du menu de ce produit (12,40 €), le double à 13,90 €."""
        e = await brique(essai_de, "FOR5")
        r = await _ajouter(e, "le texas en menu avec un coca", article="menu", quantite=1, composition=["texas", "coca"])
        assert e.p["lignes"] and e.p["lignes"][-1]["ref"] == "F-MENU", fait(r)
        assert (await _chiffrer(e, "F-MENU", _choix("P-TEXAS-UNIQUE", "P-COCA-UNIQUE"))).faits["sous_total"] == 1240
        assert (await _chiffrer(e, "F-MENU", _choix("P-TEXAS-DOUBLE-UNIQUE", "P-COCA-UNIQUE"))).faits["sous_total"] == 1390

    async def test_for5_aller_retour_caisse(self, essai_de):
        e = await brique(essai_de, "FOR5")
        await formule_en_caisse(e, "F-MENU", _choix("P-TEXAS-DOUBLE-UNIQUE", "P-COCA-UNIQUE"))

    async def test_for5_fiche_du_modele(self, essai_de):
        assert not await la_brique_change_la_fiche("FOR5", essai_de)


class TestFOR6:
    async def test_for6_passer_en_maxi(self, essai_de):
        """« un menu whopper maxi » : la taille collée au nom lue (lot 8), frites et coca en grand, 80 centimes de plus."""
        e = await brique(essai_de, "FOR6")
        r = await _ajouter(e, "un menu whopper maxi frites coca", article="menu whopper maxi", quantite=1, composition=["frites", "coca"])
        assert e.p["lignes"], fait(r)
        ligne = e.p["lignes"][-1]
        assert ligne["code"].endswith("@Maxi") and {"P-FRITES-GRANDE", "P-COCA-GRANDE"} <= {c["option_code"] for c in ligne["choix"]}, fait(r)
        r = await _chiffrer(e, ligne["code"], _choix("P-WHOPPER-UNIQUE", "P-FRITES-GRANDE", "P-COCA-GRANDE"))
        assert r.faits["sous_total"] == 990 + 80, r

    async def test_for6_aller_retour_caisse(self, essai_de):
        e = await brique(essai_de, "FOR6")
        corps = await formule_en_caisse(e, "F-MENU-KS@Maxi", _choix("P-WHOPPER-UNIQUE", "P-FRITES-GRANDE", "P-COCA-GRANDE"))
        assert corps["items"][0]["price"] == "10.70 EUR"

    async def test_for6_fiche_du_modele(self, essai_de):
        assert await la_brique_change_la_fiche("FOR6", essai_de)


class TestFOR7:
    async def test_for7_dire_la_condition(self, essai_de):
        """Le menu enfant : la condition d'âge est un fait (jamais vérifiée) ; à emporter (mode non permis) : refusé avec les modes permis ; sur place : pris."""
        e = await brique(essai_de, "FOR7")
        article = await e.source.article("F-ENFANT", "emporter")
        assert article["condition"] == {"age_max": 10}
        r = await _ajouter(e, "un menu enfant", article="menu enfant", quantite=1, composition=["trois ailes de poulet", "jus de fruit"])
        assert "mode_non_permis" in fait(r) and not e.p["lignes"], fait(r)
        e2 = await essai_de("briques/FOR7")
        await e2.tour("sur place", mode_de_retrait="sur_place")
        r = await _ajouter(e2, "un menu enfant", article="menu enfant", quantite=1, composition=["trois ailes de poulet", "jus de fruit"])
        assert e2.p["lignes"], fait(r)

    async def test_for7_aller_retour_caisse(self, essai_de):
        e = await brique(essai_de, "FOR7")
        await formule_en_caisse(e, "F-ENFANT", _choix("P-AILES-UNIQUE", "P-JUS-UNIQUE"), mode="sur_place")  # lot 12 (PRX3) : le menu enfant ne se chiffre pas à emporter
        relue = catalogue_aller_retour("FOR7")["relue"]["formules"][0]
        assert relue["age_max"] == 10 and relue["modes"] == ["sur_place"]

    async def test_for7_fiche_du_modele(self, essai_de):
        assert await la_brique_change_la_fiche("FOR7", essai_de)


class TestFOR8:
    async def test_for8_inclus_ou_vendu_seul(self, essai_de):
        e = await brique(essai_de, "FOR8")
        article = await e.source.article("F-ENFANT", "emporter")
        surprise = next(g for g in article["groupes"] if g["nom"] == "Surprise")
        assert surprise["options"][0]["par_defaut"] is True and surprise["options"][0]["prix"] == 0

    async def test_for8_aller_retour_caisse(self, essai_de):
        e = await brique(essai_de, "FOR8")
        corps = await formule_en_caisse(e, "F-ENFANT", _choix("P-NUGGETS-UNIQUE", "P-SURPRISE-UNIQUE"))
        assert corps["items"][1]["price"] == "0.00 EUR"

    async def test_for8_fiche_du_modele(self, essai_de):
        assert not await la_brique_change_la_fiche("FOR8", essai_de)


class TestFOR9:
    async def test_for9_dire_le_justificatif(self, essai_de):
        e = await brique(essai_de, "FOR9")
        article = await e.source.article("F-ETUDIANT", "emporter")
        assert article["justificatif"] == "présentation de la carte étudiante ou d'identité"
        r = await _ajouter(e, "le menu étudiant, un panini et un coca", article="menu étudiant", quantite=1, composition=["panini", "coca"])
        assert e.p["lignes"], fait(r)  # jamais refusé sur ce motif

    async def test_for9_aller_retour_caisse(self, essai_de):
        e = await brique(essai_de, "FOR9")
        await formule_en_caisse(e, "F-ETUDIANT", _choix("P-PANINI-UNIQUE", "P-COCA-UNIQUE"))
        assert catalogue_aller_retour("FOR9")["relue"]["formules"][0]["public"] == "présentation de la carte étudiante ou d'identité"

    async def test_for9_fiche_du_modele(self, essai_de):
        assert await la_brique_change_la_fiche("FOR9", essai_de)


class TestFOR10:
    async def test_for10_pour_combien(self, essai_de):
        """« le seau pour quatre » (sous-case ``personnes``) : 29,90 € ; sans nombre : la question « pour combien de personnes » ; « pour trois » : redemandé avec 2 et 4."""
        e = await brique(essai_de, "FOR10")
        await objets_charges(e)
        r = await _ajouter(e, "le seau pour quatre", article="seau", quantite=1, personnes=4)
        assert e.p["lignes"][-1]["code"] == "F-SEAU@4" and not e.p["lignes"][-1].get("attente"), fait(r)
        assert (await _chiffrer(e, "F-SEAU@4", _choix("P-TENDERS-UNIQUE"))).faits["sous_total"] == 2990
        e2 = await brique(essai_de, "FOR10")
        r = await _ajouter(e2, "un seau", article="seau", quantite=1)
        assert e2.p["lignes"][-1]["attente"]["options"] == ["2", "4"], fait(r)
        e3 = await brique(essai_de, "FOR10")
        await objets_charges(e3)
        r = await _ajouter(e3, "un seau pour trois", article="seau", quantite=1, personnes=3)
        assert "personnes_hors_liste" in fait(r) and not e3.p["lignes"], fait(r)

    async def test_for10_aller_retour_caisse(self, essai_de):
        e = await brique(essai_de, "FOR10")
        await formule_en_caisse(e, "F-SEAU@2", _choix("P-TENDERS-UNIQUE"))

    async def test_for10_fiche_du_modele(self, essai_de):
        assert await la_brique_change_la_fiche("FOR10", essai_de)


class TestFOR11:
    async def test_for11_compter_les_lots(self, essai_de):
        """Trois seniors : 30 € ; quatre : un lot (30 €) et une à l'unité (au prix de la carte), dans l'ordre du panier."""
        e = await brique(essai_de, "FOR11")
        trois = [{"code_caisse": "P-REINE-SENIOR", "quantite": 2, "choix": []}, {"code_caisse": "P-MARGHERITA-SENIOR", "quantite": 1, "choix": []}]
        r = await RC.chiffrer_panier(e.monde.c, e.monde.a, "emporter", trois)
        assert r.faits["sous_total"] == 3000, r
        quatre = [*trois, {"code_caisse": "P-REINE-SENIOR", "quantite": 1, "choix": []}]
        r = await RC.chiffrer_panier(e.monde.c, e.monde.a, "emporter", quatre)
        assert r.faits["sous_total"] == 3000 + 1200, r
        junior = [{"code_caisse": "P-REINE-JUNIOR", "quantite": 3, "choix": []}]
        assert (await RC.chiffrer_panier(e.monde.c, e.monde.a, "emporter", junior)).faits["sous_total"] == 2700  # hors du lot : à l'unité

    async def test_for11_aller_retour_caisse(self, essai_de):
        e = await brique(essai_de, "FOR11")
        r = await RC.chiffrer_panier(e.monde.c, e.monde.a, "emporter", [{"code_caisse": "P-REINE-SENIOR", "quantite": 3, "choix": []}])
        corps = commande_vers_hubrise({"numero": "n-1", "mode": "emporter", "client": {}, "lignes": r.faits["lignes"]})
        assert _total_hubrise(corps) == 3000 and corps["deals"]["0"]["ref"] == "F-LOT"

    async def test_for11_fiche_du_modele(self, essai_de):
        assert not await la_brique_change_la_fiche("FOR11", essai_de)


class TestFOR12:
    async def test_for12_une_alternative(self, essai_de):
        """« trois canettes » (un coca dit : la quantité de l'alternative) ; une bouteille et une canette : refusé, jamais un mélange."""
        e = await brique(essai_de, "FOR12")
        r = await _ajouter(e, "le menu partage avec des canettes de coca", article="menu partage", quantite=1, composition=["coca canette"])
        boissons = [c for c in e.p["lignes"][-1]["choix"] if c["option_code"].startswith("P-COCA")] if e.p["lignes"] else []
        assert boissons and boissons[0]["quantite"] == 3, fait(r)
        r = await _chiffrer(e, "F-PARTAGE", [*_choix("P-BUCKET-UNIQUE", "P-COCA-BOUTEILLE"), {"option_code": "P-FANTA-CANETTE", "quantite": 1, "choix": []}])
        assert r.statut == "HORS_CARTE" and r.faits.get("raison") == "alternatives_melangees", r
        assert (await _chiffrer(e, "F-PARTAGE", _choix("P-BUCKET-UNIQUE", "P-COCA-BOUTEILLE"))).faits["sous_total"] == 2190

    async def test_for12_aller_retour_caisse(self, essai_de):
        e = await brique(essai_de, "FOR12")
        corps = await formule_en_caisse(e, "F-PARTAGE", [*_choix("P-BUCKET-UNIQUE"), {"option_code": "P-COCA-CANETTE", "quantite": 3, "choix": []}])
        assert sum(int(a["quantity"]) for a in corps["items"] if a["sku_ref"] == "P-COCA-CANETTE") == 3

    async def test_for12_fiche_du_modele(self, essai_de):
        assert await la_brique_change_la_fiche("FOR12", essai_de)


class TestFOR13:
    async def test_for13_inclus_de_la_rubrique(self, essai_de):
        e = await brique(essai_de, "FOR13")
        assert (await e.source.article("P-YAKITORI", "emporter"))["servi_avec"] == ["1 soupe", "1 salade", "1 riz"]
        assert "servi_avec" not in await e.source.article("P-MOCHI", "emporter")

    async def test_for13_aller_retour_caisse(self, essai_de):
        e = await brique(essai_de, "FOR13")
        r = await RC.chiffrer_panier(e.monde.c, e.monde.a, "emporter", [{"code_caisse": "P-YAKITORI-UNIQUE", "quantite": 1, "choix": []}])
        corps = commande_vers_hubrise({"numero": "n-1", "mode": "emporter", "client": {}, "lignes": r.faits["lignes"]})
        assert corps["items"][0]["customer_notes"] == "servi avec : 1 soupe, 1 salade, 1 riz"

    async def test_for13_fiche_du_modele(self, essai_de):
        assert await la_brique_change_la_fiche("FOR13", essai_de)


class TestFOR14:
    async def test_for14_relire_le_contenu(self, essai_de):
        e = await brique(essai_de, "FOR14")
        article = await e.source.article("F-SAKURA", "emporter")
        assert article["contenu"] == ["8 California saumon avocat", "6 Maki saumon"]
        r = await _ajouter(e, "le plateau sakura", article="plateau sakura", quantite=1)
        assert e.p["lignes"] and not e.p["lignes"][-1].get("attente"), fait(r)  # tout est posé d'office, rien n'est demandé
        assert (await _chiffrer(e, "F-SAKURA", [{"option_code": "P-CALIFORNIA-UNIQUE", "quantite": 8, "choix": []},
                                                {"option_code": "P-MAKI-UNIQUE", "quantite": 6, "choix": []}])).faits["sous_total"] == 1890

    async def test_for14_aller_retour_caisse(self, essai_de):
        e = await brique(essai_de, "FOR14")
        await formule_en_caisse(e, "F-SAKURA", [{"option_code": "P-CALIFORNIA-UNIQUE", "quantite": 8, "choix": []}, {"option_code": "P-MAKI-UNIQUE", "quantite": 6, "choix": []}])

    async def test_for14_fiche_du_modele(self, essai_de):
        assert not await la_brique_change_la_fiche("FOR14", essai_de)


class TestFOR15:
    async def test_for15_a_volonte(self, essai_de):
        e = await brique(essai_de, "FOR15")
        une = await _chiffrer(e, "F-VOLONTE", _choix("P-MAX-UNIQUE", "P-COCA-UNIQUE"))
        trois = await _chiffrer(e, "F-VOLONTE", [*_choix("P-MAX-UNIQUE"), {"option_code": "P-COCA-UNIQUE", "quantite": 3, "choix": []}])
        assert une.faits["sous_total"] == trois.faits["sous_total"] == 1090, trois
        assert "Boisson à volonté" in (une.faits["lignes"][0]["note"] or "")

    async def test_for15_aller_retour_caisse(self, essai_de):
        e = await brique(essai_de, "FOR15")
        await formule_en_caisse(e, "F-VOLONTE", _choix("P-MAX-UNIQUE", "P-COCA-UNIQUE"))

    async def test_for15_fiche_du_modele(self, essai_de):
        assert not await la_brique_change_la_fiche("FOR15", essai_de)


@pytest.mark.parametrize("code", [f"FOR{n}" for n in range(1, 16)])
def test_for_au_registre(code):
    """Chaque brique de formule est au registre avec sa déclaration « change la fiche du modèle » (D66) et sa carte d'essai."""
    from api.services.commande.briques import registre

    b = registre.BRIQUES[code]
    assert b.change_la_fiche_du_modele is not None and b.vue_sur_carte is True and b.carte_d_essai == f"briques/{code}"


# --------------------------------------------------------------------------- conversations du lot 11 (D66) : défauts trouvés face au modèle


def _prefixe(e) -> str:
    from api.services.actions_communes.parole import CLE_TEXTES_DU_CODE

    return str((e.fiche_de_l_appel.get(CLE_TEXTES_DU_CODE) or {}).get("prefixe") or "")


def _regles(r: dict) -> list[dict]:
    """Les règles de l'article que le retour donne au modèle, en faits bruts (lot 7b, Q1 ; reprise de l'audit : § 2, le modèle parle, jamais une phrase finie)."""
    return list((r.get("faits") or {}).get("regles_a_dire") or [])


async def test_conv_la_lecture_d_une_formule_rend_ses_etapes_ses_regles_et_son_prix(essai_de):
    """FOR9-B, FOR7 : « c'est quoi le menu étudiant ? » ; la lecture d'une formule ne rendait rien (« je ne peux pas le confirmer »). Elle rend ses étapes et
    leurs choix, son justificatif, sa condition, et son prix (PRX5, D33). C6 n° 11 (décision d'Evan 25/11 9 h 30, § 8 bis) : le prix est un fait que le modèle dit, la barrière le vérifie."""
    e = await brique(essai_de, "FOR9")
    r = await e.lecture(sujet="article", article="menu étudiant")
    f = r["faits"]
    assert f["renseigne"] is True and [x["etape"] for x in f["etapes"]] == ["Sandwich", "Boisson"] and f["etapes"][0]["choix"] == ["Panini"], r
    assert f["justificatif"].startswith("présentation") and f["prix"] == {"montant": 850, "a_partir_de": False}, r
    assert "prix_dit_par_le_code_apres_ta_phrase" not in r and "prix_a_dire" not in f, r
    e7 = await brique(essai_de, "FOR7")
    f7 = (await e7.lecture(sujet="article", article="menu enfant"))["faits"]
    assert f7["condition"] == {"age_max": 10} and f7["modes"] == ["sur_place"], f7
    e10 = await brique(essai_de, "FOR10")
    f10 = (await e10.lecture(sujet="article", article="seau"))["faits"]
    assert f10["personnes"] == [{"personnes": 2, "prix": 1690}, {"personnes": 4, "prix": 2990}] and f10["prix"] == {"montant": 1690, "a_partir_de": True}, f10


async def test_conv_la_lecture_d_un_produit_de_la_rubrique_dit_ce_qui_est_servi_avec(essai_de):
    """FOR13-A : « qu'est-ce qui est servi avec les brochettes yakitori ? » ; la lecture ne rendait pas ``servi_avec`` (le modèle a dit « un riz blanc »)."""
    e = await brique(essai_de, "FOR13")
    f = (await e.lecture(sujet="article", article="brochettes yakitori"))["faits"]
    assert f["servi_avec"] == ["1 soupe", "1 salade", "1 riz"], f


async def test_d11_ce_que_la_lecture_a_dit_n_est_pas_redit_a_l_ajout(essai_de):
    """B5 (D11, FOR13-A) : « servi avec » rendu par la lecture (le modèle le dit) puis l'ajout : le code ne le redit pas (avant : dit deux fois)."""
    e = await brique(essai_de, "FOR13")
    await e.lecture(sujet="article", article="brochettes yakitori")
    r = await _ajouter(e, "des brochettes yakitori", article="brochettes yakitori", quantite=1)
    assert not _regles(r), fait(r)


async def test_conv_la_condition_le_justificatif_et_le_servi_avec_sont_dits_par_le_code_une_fois(essai_de):
    """FOR7-B, FOR9-A, FOR13-B : le fait seul n'était jamais dit (la phrase du modèle, écrite avant le retour, est dite seule). Le code le dit avant la phrase du
    modèle, une fois par appel ; lot 7b (Q1) : le retour les donne au modèle (``regles_a_dire``), le code ne les dit plus."""
    e = await brique(essai_de, "FOR13")
    r = await _ajouter(e, "des brochettes yakitori", article="brochettes yakitori", quantite=1)
    assert _regles(r) == [{"servi_avec": ["1 soupe", "1 salade", "1 riz"]}] and not _prefixe(e), fait(r)
    assert r["resultats"][0]["faits"]["servi_avec"] == ["1 soupe", "1 salade", "1 riz"] and "regle_a_dire" not in r["resultats"][0]["faits"], fait(r)
    r = await _ajouter(e, "et encore une", article="brochettes yakitori", quantite=1)
    assert not _regles(r), fait(r)  # une seule fois par appel
    e9 = await brique(essai_de, "FOR9")
    r9 = await _ajouter(e9, "un menu étudiant panini coca", article="menu étudiant", quantite=1, composition=["panini", "coca"])
    assert _regles(r9) == [{"justificatif": "présentation de la carte étudiante ou d'identité"}], fait(r9)
    e7 = await brique(essai_de, "FOR7")
    await e7.tour("sur place", mode_de_retrait="sur_place")
    r = await _ajouter(e7, "un menu enfant", article="menu enfant", quantite=1, composition=["ailes de poulet", "jus de fruit"])
    assert e7.p["lignes"] and _regles(r) == [{"condition": {"age_max": 10}}], fait(r)


async def test_conv_un_choix_decline_se_dit_declinaison_d_abord(essai_de):
    """FOR12-B : « une bouteille de coca et une canette de fanta » ; « bouteille de coca » n'était pas reconnu (« Coca Bouteille ou Coca Canette ? »), le refus
    du mélange n'était jamais atteint. Le nom d'un choix décliné se dit aussi déclinaison d'abord : le mélange est refusé, la bouteille seule est prise."""
    e = await brique(essai_de, "FOR12")
    r = await _ajouter(e, "un menu partage bouteille de coca canette de fanta", article="menu partage", quantite=1, composition=["bouteille de coca", "canette de fanta"])
    assert not e.p["lignes"] and "alternatives_melangees" in fait(r), fait(r)
    e2 = await brique(essai_de, "FOR12")
    r = await _ajouter(e2, "un menu partage avec une bouteille de coca", article="menu partage", quantite=1, composition=["bouteille de coca"])
    assert e2.p["lignes"] and "P-COCA-BOUTEILLE" in {c["option_code"] for c in e2.p["lignes"][-1]["choix"]} and not e2.p["lignes"][-1].get("attente"), fait(r)


async def test_conv_la_lecture_des_offres_rend_les_formules(essai_de):
    """FOR2-B : « la formule midi », le modèle lit les offres ; elles ne rendaient que les remises (« pas d'offre ») et il disait que la formule n'existait pas."""
    e = await brique(essai_de, "FOR2")
    r = await e.lecture(sujet="offres")
    assert r["faits"]["formules"] == ["Formule midi"] and r["faits"]["remises"] == [], r


async def test_conv_le_nombre_de_personnes_ecrit_aussi_dans_le_nom(essai_de):
    """FOR10-A : ``article`` « seau pour quatre personnes » et ``personnes`` 4 : la recherche gardait le doute (« Vous voulez dire : Seau ? ») ; le seul
    candidat vendu par personnes est retenu, à quatre."""
    e = await brique(essai_de, "FOR10")
    await objets_charges(e)
    r = await _ajouter(e, "un seau pour quatre personnes", article="seau pour quatre personnes", quantite=1, personnes=4)
    assert e.p["lignes"] and e.p["lignes"][-1]["code"] == "F-SEAU@4" and not e.p["lignes"][-1].get("attente"), fait(r)


async def test_conv_une_variante_sur_une_formule_sans_taille_est_refusee(essai_de):
    """FOR12-A : « Bouteille » mis en ``variante`` d'une formule sans taille : la question « Quelle taille pour votre Menu partage : Menu partage ? » ;
    la fiche est refusée avec la raison, rien n'est ajouté ; sans variante, la même fiche est prise."""
    e = await brique(essai_de, "FOR12")
    r = await _ajouter(e, "un menu partage bouteille", article="menu partage", quantite=1, composition=["bouteille de coca"], variante="Bouteille")
    assert not e.p["lignes"] and r.get("raison") == "formule_sans_variante" and not CONV.question_de(e.p), fait(r)


async def test_conv_une_formule_et_un_choix_hors_de_sa_ligne_dans_le_nom(essai_de):
    """FOR3-A : ``article`` « formule complète avec un tiramisu », sans composition : « Tiramisu ou Formule complète ? ». Le tiramisu est dans la base de
    l'étape Dessert, écarté par son filtre de prix : la formule est retenue, le tiramisu refusé, la règle est un fait du retour que le modèle dit (lot 7b, Q1)."""
    e = await brique(essai_de, "FOR3")
    r = await _ajouter(e, "une formule complète avec un tiramisu", article="formule complète avec un tiramisu", quantite=1)
    assert not e.p["lignes"] and "hors_sous_ensemble" in fait(r), fait(r)
    assert r["faits"]["regle_de_la_ligne"]["prix_max"] == 200 and set(r["faits"]["regle_de_la_ligne"]) == {"formule", "etape", "prix_max"} and not _prefixe(e), fait(r)


async def test_conv_le_refus_du_melange_dit_chaque_alternative_a_sa_quantite(essai_de):
    """FOR12-B : le refus disait « Menu partage : Coca Bouteille ou Coca Canette ou Fanta ? » (trois choix au lieu de deux alternatives). Chaque
    alternative est dite à sa quantité."""
    e = await brique(essai_de, "FOR12")
    r = await _ajouter(e, "un menu partage bouteille de coca canette de fanta", article="menu partage", quantite=1, composition=["bouteille de coca", "canette de fanta"])
    faits = r["resultats"][0]["faits"]
    assert faits["raison"] == "alternatives_melangees" and faits["alternatives"] == [{"quantite": 1, "options": ["Coca Bouteille"]}, {"quantite": 3, "options": ["Coca Canette", "Fanta"]}], fait(r)


async def test_conv_une_formule_ajoutee_prend_le_second_passage(essai_de):
    """Mesure finale du lot 11 : sur une formule ajoutée FAIT, ``a_dire`` (écrite avant le retour) était dite seule et inventait la composition (« vous avez le
    choix entre une boisson et un dessert » pour entrée et plat). Le retour porte la composition de la ligne (``composition``, étape et choix) : le modèle
    repasse avec lui (motif nommé, critère sur la forme du retour, jamais sur les mots). Un article qui n'est pas une formule garde ``a_dire`` seule."""
    from api.services.actions_communes import parole as PAROLE
    from api.services.workflow import parole_de_la_fiche as PF

    e = await brique(essai_de, "FOR2")
    a_dire = "Je note la formule midi. Vous avez le choix entre une boisson et un dessert ?"
    cases = {"ajouter": [{"article": "formule midi", "quantite": 1, "composition": ["nems", "pad thaï"]}]}
    r = await e.dit("la formule midi avec des nems et un pad thaï").fiche(a_dire=a_dire, **cases)
    assert r["statut"] == "FAIT" and r["resultats"][0]["faits"]["composition"] == [{"etape": "Entrée", "choix": ["Nems"]}, {"etape": "Plat", "choix": ["Pad thaï"]}], r
    d = PF.decider_apres_la_fiche(e.fiche_de_l_appel, r, {"a_dire": a_dire, **cases})
    assert d.mode == PAROLE.SECOND_PASSAGE and d.motif == PAROLE.FORMULE_AJOUTEE and d.a_dire is None, d
    # mesure finale 2 (FOR10-A) : au second passage, le modèle recopiait sa phrase jetée ; recopiée, elle n'est jamais dite
    etat = PAROLE.etat_du_tour(e.fiche_de_l_appel)
    assert PAROLE.phrase_libre_retenue(a_dire, etat, objet_en_cours=True, question_en_attente=False, paroles=[], p=e.p) == PAROLE.REPLI_A
    assert PAROLE.phrase_libre_retenue("C'est noté : des nems et un pad thaï.", PAROLE.etat_du_tour(e.fiche_de_l_appel), objet_en_cours=True,
                                       question_en_attente=False, paroles=[], p=e.p) is None
    e2 = await brique(essai_de, "FOR13")
    phrase = "Très bien pour le mochi. Autre chose ?"  # B2 (règle 1) : une phrase dite seule demande ce qui manque
    r = await e2.dit("un mochi").fiche(a_dire=phrase, ajouter=[{"article": "mochi", "quantite": 1}])
    d = PF.decider_apres_la_fiche(e2.fiche_de_l_appel, r, {"a_dire": phrase, "ajouter": [{"article": "mochi", "quantite": 1}]})
    assert r["statut"] == "FAIT" and d.mode == PAROLE.A_DIRE_SEUL, (r, d)


def test_conv_la_question_d_etape_redite_par_le_repli_finit_par_un_seul_point_d_interrogation():
    """Série 2 du lot 11 (FOR3-A) : « … cookie, donut ou dessert du jour ? ? » ; décision d'Evan 25/11 8 h 45 (lot 7b-C5) : le code ne redit plus la question d'étape, le modèle est relancé
    avec son objet (l'article en question) : aucune phrase du code, donc aucun « ? ? »."""
    import json

    from api.services.actions_communes.parole import EtatDuTour
    from api.services.actions_communes.repli import consigne_de_relance

    texte = "Pour votre Formule complète, qu'est-ce que vous prenez comme dessert : Cookie, Donut ou Dessert du jour ?"
    p = {CONV.CLE: {CONV.CLE_QUESTION: {"id": "Q-1", "type": "etape", "texte": texte, "article_en_question": "Formule complète"}}}
    consigne = consigne_de_relance(p, {}, EtatDuTour(tour=1))
    assert json.loads(consigne[consigne.index("{"):])["puis"] == {"question": {"id": "Q-1", "type": "etape", "article_en_question": "Formule complète"}} and texte not in consigne


async def _parole_de(e, a_dire, **cases):
    from api.services.workflow import parole_de_la_fiche as PF

    r = await e.dit("x").fiche(a_dire=a_dire, **cases)
    return r, PF.decider_apres_la_fiche(e.fiche_de_l_appel, r, {"a_dire": a_dire, **cases})


async def test_conv_lot_9_une_ambiguite_est_rendue_au_modele_avec_ses_candidats(essai_de):
    """Lot 7b-C4, E1 = A (Evan, 25/11 ; avant : lot 9, OPT3-A, le code disait « Vous voulez dire : Bubble tea ? » mot pour mot à la place de la phrase du modèle) : une question d'ambiguïté
    née dans le tour suit la ligne de toute question née : le modèle repasse avec les candidats (``faits.candidats``, ``faits.dit``) et dit le doute avec ses mots ; si le modèle se tait, le repli
    est relancé avec le doute (lot 7b-C5), jamais avec le texte du registre, que le modèle ne reçoit jamais."""
    import json

    from api.services.actions_communes import parole as PAROLE
    from api.services.actions_communes.repli import consigne_de_relance

    e = await brique(essai_de, "OPT3")
    r, d = await _parole_de(e, "Je ne trouve pas de bubble tea sur notre carte.", ajouter=[{"article": "bubble tea avec des perles", "quantite": 1}])
    assert r["question"]["type"] == "ambiguite", r
    assert d.mode == PAROLE.SECOND_PASSAGE and d.motif == "fait_bloquant" and d.a_dire is None, d
    assert r["resultats"][0]["faits"] == {"candidats": ["Bubble tea"], "dit": "bubble tea avec des perles"}, r["resultats"]
    consigne = consigne_de_relance(e.p, e.fiche_de_l_appel, PAROLE.etat_du_tour(e.fiche_de_l_appel))  # le modèle muet : relancé avec le doute en faits
    assert json.loads(consigne[consigne.index("{"):])["puis"]["question"]["candidats"] == ["Bubble tea"] and "Vous voulez dire" not in consigne, consigne


async def test_conv_lot_9_un_maximum_refuse_est_dit_par_le_modele(essai_de):
    """Lot 9 (OPT8-B) : le refus d'un maximum (« pas plus de trois ») n'était pas dit ; lot 7b (Q1) : le modèle repasse avec le refus et son nombre, le code ne dit rien."""
    from api.services.actions_communes import parole as PAROLE

    e = await brique(essai_de, "OPT8")
    cases = {"ajouter": [{"article": "coupe de glace", "variante": "3 boules", "quantite": 1, "composition": ["vanille", "chocolat", "café", "pistache"]}]}
    r, d = await _parole_de(e, "C'est noté pour la coupe.", **cases)
    assert any(x.get("statut_du_module") == "MAXIMUM_ATTEINT" for x in r["resultats"]), r
    assert d.mode == PAROLE.SECOND_PASSAGE and d.a_dire is None, (d, r["faits"])
    refus = r["faits"]["refus_de_la_fiche"]  # lot 7b-C4 (R = A) : le maximum est un fait (« pas plus de trois » est le texte de secours du repli), sans phrase
    assert [(x["statut_du_module"], x["faits"]["maximum"]) for x in refus] == [("MAXIMUM_ATTEINT", 3)], refus


async def test_conv_l_article_en_question_n_est_jamais_ajoute_deux_fois(essai_de):
    """Lot 19, D01 (FOR10-B, OPT8-B, n7 de B12) : « un seau » ouvre « pour combien de personnes » ; la fiche suivante porte la réponse ET remet le seau dans
    ``ajouter`` : la réponse complète le seau, le seau remis n'est pas ajouté une seconde fois (refus de la case, la raison dite au modèle) ; le code ne devine pas."""
    e = await brique(essai_de, "FOR10")
    await objets_charges(e)
    await _ajouter(e, "un seau", article="seau", quantite=1)
    q = CONV.question_de(e.p)
    r = await e.tour("pour deux", reponse={"question_id": q["id"], "sens": "autre", "valeurs": ["2"]}, ajouter=[{"article": "seau", "quantite": 1, "personnes": 2}])
    assert [l["code"] for l in e.p["lignes"]] == ["F-SEAU@2"], fait(r)
    assert "article_deja_en_question" in fait(r), fait(r)


async def test_oui_a_une_hesitation_ajoute_le_candidat_avec_la_quantite_dite(essai_de):
    """Lot 19, D24 (note de Pierre du 20/11, point 2 ; appel 2670) : « Vous voulez dire : Bubble tea ? » puis « oui » (``accepte``) : le candidat entre au
    panier avec la quantité dite au départ ; avant, la réponse visait une ligne qui n'existait pas : panier vide, question perdue."""
    e = await brique(essai_de, "OPT3")
    await e.tour("deux bubble tea avec des perles", ajouter=[{"article": "bubble tea avec des perles", "quantite": 2}])
    q = CONV.question_de(e.p)
    assert q["type"] == "ambiguite", q
    r = await e.tour("oui", reponse={"question_id": q["id"], "sens": "accepte"})
    assert [(l["nom"], l["quantite"]) for l in e.p["lignes"]] == [("Bubble tea", 2)], fait(r)
    # B5 (N1, décision D03 : « le code ne devine jamais un reste "avec" ») : « avec des perles », glissé par le modèle dans le NOM, n'est plus rejoué
    # en choix par une liste de mots de liaison (T4 du lot 19 bis, retiré) : le choix vient des cases du modèle, ou de la question de l'article
    assert "erles" not in fait(e.p["lignes"][0].get("choix") or ""), e.p["lignes"]


async def test_hesitation_sur_le_premier_article_est_posee(essai_de):
    """Lot 19, D25 (note de Pierre du 20/11, point 3 ; famille de 2643) : un doute sur le premier article dit et un second article pris : la question et
    le statut portent sur le premier résultat qui demande quelque chose, pas sur le dernier ; l'article en doute n'est jamais perdu en silence."""
    e = await brique(essai_de, "OPT3")
    r = await e.tour("x", ajouter=[{"article": "bubble tea avec des perles", "quantite": 1}, {"article": "bubble tea", "quantite": 1, "composition": ["perles"]}])
    assert r["statut"] != "FAIT" and (CONV.question_de(e.p) or {}).get("type") == "ambiguite", fait(r)


async def test_heure_refusee_dite_et_relecture_gardee(essai_de, monkeypatch):
    """Lot 19, D33 (conversation 7, run 208) : « changez l'heure… et c'est tout » ; la réponse ouvre la relecture, puis l'heure posée est refusée par son
    créneau (``ARGUMENT_INVALIDE``, manque ``heure_voulue`` : « Je ne prends pas de commande pour plus tard. », la réponse vue dans l'appel). Avant : le
    refus écrasait la relecture (aucune question, l'appel tournait en rond) et sa phrase n'était jamais dite (le modèle confirmait l'heure). Le refus de
    l'heure est dit par le code ; la question posée reste la relecture.
    Lot 7b, ligne 12 (fiche relue, Q1) : l'attente d'avant (« le code dit l'heure devant la relecture ») contredit Q1 (le code ne dit plus rien avant la phrase du modèle) ; l'heure
    refusée reste un manque, la question posée est l'heure (avant la relecture), le modèle la dit."""
    from api.services.commande import moteur
    from api.services.commande.porte import CLE_TEXTES_DU_CODE

    e = await essai_de("casa-italia")
    await e.dit("trois margherita à emporter").fiche(ajouter=[{"article": "margherita", "quantite": 3, "variante": "Normale"}], mode_de_retrait="emporter")
    q = CONV.question_de(e.p) or {}

    async def refusee(_source, p, _texte):
        return _socle._avec(moteur.Resultat("ARGUMENT_INVALIDE", {}, "Je ne prends pas de commande pour plus tard.", "heure_voulue"), p)

    monkeypatch.setattr(moteur, "poser_l_heure", refusee)
    r = await e.dit("non merci, mettez-les pour vingt et une heures, c'est tout").fiche(
        c_est_tout=True, heure="vingt et une heures", **({"reponse": {"question_id": q["id"], "sens": "refuse"}} if q else {}))
    assert any(x.get("manque") == "heure_voulue" for x in r["resultats"]), r["resultats"]
    assert (CONV.question_de(e.p) or {}).get("type") == "heure_proposee", (CONV.question_de(e.p), r["resultats"])
    textes = e.fiche_de_l_appel.get(CLE_TEXTES_DU_CODE) or {}
    assert not textes.get("prefixe") and not textes.get("avant"), textes  # le code ne dit rien : le refus de l'heure est un fait que le modèle dit, avant la relecture


async def test_ferme_planifiable_au_c_est_tout_demande_l_heure_par_le_code(essai_de, monkeypatch):
    """Lot 19, D34 (point 5 de Pierre, 3e partie, 20/11 après 14 h, Casa fermée jusqu'à 18 h, commande pour plus tard permise) : « c'est tout » rend
    ``FERME_PLANIFIABLE`` (D15 : l'heure voulue est LA question) ; sa phrase n'était pas dite (l'agent : « Très bien, voici votre récapitulatif. »). Elle
    est un fait que le modèle dit avec ses mots, comme le refus d'une heure (D33 ; lot 7b, Q1)."""
    from api.services.commande import moteur, porte
    from api.services.commande.porte import CLE_TEXTES_DU_CODE

    e = await essai_de("casa-italia")
    await e.dit("deux reines à emporter").fiche(ajouter=[{"article": "regina", "quantite": 2, "variante": "Normale"}], mode_de_retrait="emporter")
    q = CONV.question_de(e.p) or {}
    phrase = "Nous sommes fermés pour le moment, nous rouvrons à dix-huit heures. Pour quel jour et à quelle heure ?"

    async def ferme(_source, p, _regles, _appelant, confirmer=False):
        return _socle._avec(moteur.Resultat("FERME_PLANIFIABLE", {"raison": "ferme_horaires", "a_planifier": True}, phrase, "heure_voulue"), p)

    monkeypatch.setattr(porte, "mener_a_la_fin", ferme)
    r = await e.dit("non merci, c'est tout").fiche(c_est_tout=True, **({"reponse": {"question_id": q["id"], "sens": "refuse"}} if q else {}))
    textes = e.fiche_de_l_appel.get(CLE_TEXTES_DU_CODE) or {}
    assert not textes.get("prefixe") and phrase not in str(textes), textes  # le code ne dit rien (lot 7b, Q1)
    assert r["faits"]["heure_a_dire"][0]["faits"]["a_planifier"] is True and porte.A_FAIRE_DE_L_HEURE in r["a_faire"], r  # le modèle demande le jour et l'heure avec ses mots


async def test_ferme_propose_le_prochain_service_et_le_fait_confirmer(essai_de, monkeypatch):
    """Lot 19, aparté d'Evan (20/11) : « quand le restau est fermé, le plus naturel c'est de proposer une commande pour le prochain service qui commence à
    telle heure, et de faire confirmer par le client ». Fermé mais planifiable au « c'est tout » : le code propose l'heure de la réouverture et pose la
    question ; « oui » pose cette heure et la relecture suit."""
    from datetime import datetime, timedelta

    e = await essai_de("casa-italia")
    await e.dit("deux reines à emporter").fiche(ajouter=[{"article": "regina", "quantite": 2, "variante": "Normale"}], mode_de_retrait="emporter")
    q = CONV.question_de(e.p) or {}
    vrai_etat = e.source.etat
    from api.services.restauration import source_commande as SC

    maintenant = (await SC.maintenant(e.source.c)).astimezone()
    dix_huit = maintenant.replace(hour=18, minute=0, second=0, microsecond=0)  # le service du soir de la carte d'essai
    reouverture = {"a": dix_huit if maintenant.hour < 17 else dix_huit + timedelta(days=1)}

    async def ferme(mode):
        etat = dict(await vrai_etat(mode))
        return {**etat, "ouvert": False, "statut": "FERME", "raison": "ferme_horaires", "planifiee_permise": True, "prochaine_ouverture": reouverture["a"]}

    monkeypatch.setattr(e.source, "etat", ferme)
    await e.dit("non merci, c'est tout").fiche(c_est_tout=True, **({"reponse": {"question_id": q["id"], "sens": "refuse"}} if q else {}))
    q = CONV.question_de(e.p) or {}
    # C7 B3 (décision d'Evan 25/11 8 h 45) : le modèle pose la question avec ses mots ; la question du registre porte l'heure de la réouverture en fait, plus de texte
    assert q.get("type") == "heure_proposee" and q["texte"] == "" and q.get("heure") and q.get("heure_dite"), q
    monkeypatch.setattr(e.source, "etat", vrai_etat)
    r = await e.dit("oui").fiche(reponse={"question_id": q["id"], "sens": "accepte"})
    assert e.p.get("heure_voulue"), r["resultats"]
    assert e.p.get("heure_voulue") and datetime.fromisoformat(e.p["heure_voulue"]) == reouverture["a"], (e.p.get("heure_voulue"), reouverture)
    assert (CONV.question_de(e.p) or {}).get("type") == "relecture", CONV.question_de(e.p)

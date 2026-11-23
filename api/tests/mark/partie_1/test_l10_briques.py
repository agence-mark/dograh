"""[.mark] Chantier Partie 1, lot 10 : les briques retrait et ajout (``services/commande/briques/ret*.py``).

Une classe par brique (``TestRET1`` ...), chacune avec sa règle, son aller-retour en caisse et son test de rendu de la fiche (D66). Un test = un essai à la fois.
"""

from __future__ import annotations

from api.db.bases_clients import restauration_commande as RC
from api.services.restauration.caisse.prises.hubrise_traduction import commande_vers_hubrise
from api.tests.mark.partie_1.aides_briques import article_en_caisse, brique, fait, la_brique_change_la_fiche, descendre_jusqu_a
from api.tests.mark.partie_1.test_l08_briques import _carte, _groupe, _option  # noqa: F401  (la petite carte au format que rend carte_du_restaurant)
from api.tests.mark.test_base_client import base_essai  # noqa: F401


def _total(r) -> int:
    assert r.statut == "OK", r
    return r.faits["sous_total"]


# --------------------------------------------------------------------------- #
# L10-01 à L10-03 : la migration 039, le retrait d'une option, la règle des moitiés de l'établissement
# --------------------------------------------------------------------------- #


async def test_migration_039_montee_descente(base_prete):
    from api.db.bases_clients import connexion as schema

    colonnes = [("resto_option", "prix_par_declinaison"), ("resto_option", "prix_retrait"), ("resto_reglage", "moities_prix")]

    async def presentes(c) -> list[bool]:
        return [bool(await c.fetchval("SELECT 1 FROM information_schema.columns WHERE table_schema='mark' AND table_name=$1 AND column_name=$2", t, col)) for t, col in colonnes]

    c = await schema.connecter_proprietaire(base_prete)
    try:
        assert all(await presentes(c))
        for _ in range(2):  # descente, remontée, deux fois (rejouable)
            await descendre_jusqu_a(c, 39)  # de la tête à 039, dans l'ordre inverse
            assert not any(await presentes(c)) and 39 not in [r["version"] for r in await c.fetch("SELECT version FROM mark.schema_version")]
            assert 39 in await schema.appliquer_migrations(c)
            assert all(await presentes(c))
    finally:
        await c.close()


async def test_retirable_de_l_option_lu(essai_de):
    """« sans la sauce blanche » : une option marquée retirable se retire (avant : refusée, « on peut retirer » ne listait que les ingrédients) ; une option qui ne l'est pas, refusée."""
    e = await brique(essai_de, "RET5")
    await e.tour("un burger sans sauce blanche", ajouter=[{"article": "burger", "quantite": 1, "sans": ["sauce blanche"]}])
    ligne = e.p["lignes"][-1]
    assert "Sauce blanche" in ligne["retires"], e.retours[-1]
    article = await e.source.article("P-BURGER", "emporter")
    assert "Sauce blanche" in article["retirables"] and "oignons" in article["retirables"]


async def test_regle_des_moities_a_l_etablissement(essai_de):
    """La règle de prix des moitiés est celle de l'établissement (``resto_reglage.moities_prix``), jamais celle de l'agent : « la plus chère » par défaut, « la somme » une fois réglée."""
    e = await brique(essai_de, "RET6")
    choix = [{"option_code": "G-MOITIES-REGINA", "quantite": 1}, {"option_code": "G-MOITIES-CALZONE", "quantite": 1}]
    ligne = [{"code_caisse": "P-MM-UNIQUE", "quantite": 1, "choix": choix}]
    assert _total(await RC.chiffrer_panier(e.monde.c, e.monde.a, "emporter", ligne)) == 1400
    await e.monde.c.execute("UPDATE mark.resto_reglage SET moities_prix = 'somme' WHERE site_id = $1", e.monde.a)
    e.monde.c.instantane = None
    assert _total(await RC.chiffrer_panier(e.monde.c, e.monde.a, "emporter", ligne)) == 1200 + 1400
    await e.monde.c.execute("UPDATE mark.resto_reglage SET moities_prix = 'moyenne' WHERE site_id = $1", e.monde.a)
    assert _total(await RC.chiffrer_panier(e.monde.c, e.monde.a, "emporter", ligne)) == 1300


async def test_regle_des_moities_repartie_en_somme_exacte():
    """Quelle que soit la règle, la somme des parts est le supplément ; aucune part négative."""
    for regle in RC.REGLES_MOITIES:
        for prix in ([1200, 1400], [999, 1000], [0, 0], [1000]):
            parts = RC.repartir_les_moities(prix, regle)
            assert len(parts) == len(prix) and min(parts, default=0) >= 0
            attendu = {"plus_chere": max(prix), "somme": sum(prix), "moyenne": -(-sum(prix) // len(prix))}[regle]
            assert sum(parts) == attendu, (regle, prix, parts)


# --------------------------------------------------------------------------- #
# Les briques
# --------------------------------------------------------------------------- #


class TestRET1:
    async def test_ret1_ajouter_le_supplement(self, essai_de):
        """« avec du bacon » : l'option payante est prise au prix de la carte."""
        e = await brique(essai_de, "RET1")
        await e.tour("un burger avec du bacon", ajouter=[{"article": "burger", "quantite": 1, "supplements": ["bacon"]}])
        assert [c["option_code"] for c in e.p["lignes"][-1]["choix"]] == ["G-SUPPL-BACON"], e.retours[-1]
        assert _total(await RC.chiffrer_panier(e.monde.c, e.monde.a, "emporter", [{"code_caisse": "P-BURGER-UNIQUE", "quantite": 1, "choix": [{"option_code": "G-SUPPL-BACON", "quantite": 1}]}])) == 890 + 150

    async def test_ret1_aller_retour_caisse(self, essai_de):
        e = await brique(essai_de, "RET1")
        article = await article_en_caisse(e, "P-BURGER-UNIQUE", 1, [{"option_code": "G-SUPPL-BACON", "quantite": 1}])
        assert article["price"] == "8.90 EUR" and article["options"] == [{"option_list_name": "Suppléments", "ref": "G-SUPPL-BACON", "name": "Bacon", "price": "1.50 EUR"}]

    async def test_ret1_fiche_du_modele(self, essai_de):
        assert await la_brique_change_la_fiche("RET1", essai_de)


class TestRET2:
    async def test_ret2_prix_a_la_declinaison(self, essai_de):
        """Un ingrédient en plus : 1 € en Junior, 1,50 € en Senior ; la taille de la ligne décide."""
        e = await brique(essai_de, "RET2")
        jambon = [{"option_code": "G-EN-PLUS-JAMBON", "quantite": 1}]
        assert _total(await RC.chiffrer_panier(e.monde.c, e.monde.a, "emporter", [{"code_caisse": "P-REGINA-JUNIOR", "quantite": 1, "choix": jambon}])) == 1050 + 100
        assert _total(await RC.chiffrer_panier(e.monde.c, e.monde.a, "emporter", [{"code_caisse": "P-REGINA-SENIOR", "quantite": 1, "choix": jambon}])) == 1250 + 150

    async def test_ret2_aller_retour_caisse(self, essai_de):
        e = await brique(essai_de, "RET2")
        article = await article_en_caisse(e, "P-REGINA-SENIOR", 1, [{"option_code": "G-EN-PLUS-JAMBON", "quantite": 1}])
        assert article["price"] == "12.50 EUR" and article["options"][0]["price"] == "1.50 EUR"

    async def test_ret2_fiche_du_modele(self, essai_de):
        assert not await la_brique_change_la_fiche("RET2", essai_de)


class TestRET3:
    async def test_ret3_prix_de_l_option(self, essai_de):
        """« du saumon fumé en plus » : le prix premium de l'option ; un standard à son prix."""
        e = await brique(essai_de, "RET3")
        for code, prix in (("G-CLASSES-SAUMON-FUMÉ", 400), ("G-CLASSES-CHAMPIGNONS", 100), ("G-CLASSES-OLIVES", 150)):
            assert _total(await RC.chiffrer_panier(e.monde.c, e.monde.a, "emporter", [{"code_caisse": "P-MARGHE-UNIQUE", "quantite": 1, "choix": [{"option_code": code, "quantite": 1}]}])) == 1090 + prix
        await e.tour("une margherita avec du saumon fumé", ajouter=[{"article": "margherita", "quantite": 1, "supplements": ["saumon fumé"]}])
        assert [c["option_code"] for c in e.p["lignes"][-1]["choix"]] == ["G-CLASSES-SAUMON-FUMÉ"], e.retours[-1]

    async def test_ret3_aller_retour_caisse(self, essai_de):
        e = await brique(essai_de, "RET3")
        article = await article_en_caisse(e, "P-MARGHE-UNIQUE", 1, [{"option_code": "G-CLASSES-BRESAOLA", "quantite": 1}])
        assert article["price"] == "10.90 EUR" and article["options"][0]["price"] == "4.00 EUR"

    async def test_ret3_fiche_du_modele(self, essai_de):
        assert not await la_brique_change_la_fiche("RET3", essai_de)


class TestRET4:
    async def test_ret4_difference_de_prix(self, essai_de):
        """Le riz blanc est inclus ; « du riz rouge à la place » ajoute la DIFFÉRENCE (5,50 − 3 €), jamais le prix absolu ; le défaut ne coûte rien de plus."""
        e = await brique(essai_de, "RET4")
        await e.tour("une grillade", ajouter=[{"article": "grillade", "quantite": 1}])
        assert [c["option_code"] for c in e.p["lignes"][-1]["choix"]] == ["G-ACC-RIZ-BLANC"] and not e.p["lignes"][-1].get("attente"), e.retours[-1]
        assert _total(await RC.chiffrer_panier(e.monde.c, e.monde.a, "emporter", [{"code_caisse": "P-GRILLADE-UNIQUE", "quantite": 1, "choix": [{"option_code": "G-ACC-RIZ-BLANC", "quantite": 1}]}])) == 1450
        assert _total(await RC.chiffrer_panier(e.monde.c, e.monde.a, "emporter", [{"code_caisse": "P-GRILLADE-UNIQUE", "quantite": 1, "choix": [{"option_code": "G-ACC-RIZ-ROUGE", "quantite": 1}]}])) == 1450 + 250
        await e.tour("du riz rouge à la place", ajouter=[{"article": "grillade", "quantite": 1, "composition": ["riz rouge"]}])
        assert any([c["option_code"] for c in l["choix"]] == ["G-ACC-RIZ-ROUGE"] for l in e.p["lignes"]), e.retours[-1]

    async def test_ret4_aller_retour_caisse(self, essai_de):
        e = await brique(essai_de, "RET4")
        article = await article_en_caisse(e, "P-GRILLADE-UNIQUE", 1, [{"option_code": "G-ACC-ATTIÉKÉ", "quantite": 1}])
        assert article["price"] == "14.50 EUR" and article["options"][0]["price"] == "3.00 EUR"

    async def test_ret4_fiche_du_modele(self, essai_de):
        assert not await la_brique_change_la_fiche("RET4", essai_de)


class TestRET7:
    async def test_ret7_composer(self, essai_de):
        """Poké : 1 base, 1 protéine, 4 légumes, 1 fruit ; complet, il est pris ; un cinquième légume est refusé avec la raison ; sans le fruit, la question reste."""
        e = await brique(essai_de, "RET7")
        complet = ["riz", "saumon", "avocat", "concombre", "edamame", "carotte", "mangue"]
        await e.tour("un poké", ajouter=[{"article": "poké création", "quantite": 1, "composition": complet}])
        ligne = e.p["lignes"][-1]
        assert not ligne.get("attente") and len(ligne["choix"]) == 7, e.retours[-1]
        e2 = await brique(essai_de, "RET7")
        r = await e2.tour("un poké avec cinq légumes", ajouter=[{"article": "poké création", "quantite": 1, "composition": ["riz", "saumon", "avocat", "concombre", "edamame", "carotte", "radis", "mangue"]}])
        assert "MAXIMUM_ATTEINT" in fait(r), r
        e3 = await brique(essai_de, "RET7")
        await e3.tour("un poké sans fruit", ajouter=[{"article": "poké création", "quantite": 1, "composition": complet[:-1]}])
        assert e3.p["lignes"][-1]["attente"]["nom"] == "Fruit", e3.retours[-1]

    async def test_ret7_aller_retour_caisse(self, essai_de):
        e = await brique(essai_de, "RET7")
        choix = [{"option_code": c, "quantite": 1} for c in ("G-BASE-RIZ", "G-PROT-SAUMON", "G-LEG-AVOCAT", "G-LEG-CONCOMBRE", "G-LEG-EDAMAME", "G-LEG-CAROTTE", "G-FRUIT-MANGUE")]
        article = await article_en_caisse(e, "P-POKE-UNIQUE", 1, choix)
        assert article["price"] == "13.90 EUR" and len(article["options"]) == 7

    async def test_ret7_fiche_du_modele(self, essai_de):
        assert await la_brique_change_la_fiche("RET7", essai_de)


class TestRET8:
    async def test_ret8_base_plus_ingredients(self, essai_de):
        """Pizza créative : la base plus 1 € l'ingrédient, relue."""
        from api.services.commande.briques.composition_a_l_unite import brique_ret8_base_plus_ingredients

        assert brique_ret8_base_plus_ingredients(800, [{"prix": 100, "quantite": 1}, {"prix": 100, "quantite": 2}]) == 1100
        e = await brique(essai_de, "RET8")
        await e.tour("une pizza avec jambon, champignons, olives", ajouter=[{"article": "pizza créative", "quantite": 1, "supplements": ["jambon", "champignons", "olives"]}])
        assert len(e.p["lignes"][-1]["choix"]) == 3, e.retours[-1]
        codes = [{"option_code": f"G-INGR-{i}", "quantite": 1} for i in ("JAMBON", "CHAMPIGNONS", "OLIVES")]
        assert _total(await RC.chiffrer_panier(e.monde.c, e.monde.a, "emporter", [{"code_caisse": "P-CREATIVE-UNIQUE", "quantite": 1, "choix": codes}])) == 1100

    async def test_ret8_aller_retour_caisse(self, essai_de):
        e = await brique(essai_de, "RET8")
        article = await article_en_caisse(e, "P-CREATIVE-UNIQUE", 1, [{"option_code": "G-INGR-JAMBON", "quantite": 1}, {"option_code": "G-INGR-OLIVES", "quantite": 1}])
        assert article["price"] == "8.00 EUR" and [o["price"] for o in article["options"]] == ["1.00 EUR", "1.00 EUR"]

    async def test_ret8_fiche_du_modele(self, essai_de):
        assert await la_brique_change_la_fiche("RET8", essai_de)


# --------------------------------------------------------------------------- #
# Les briques jamais vues sur une carte : en dernier, côté code seulement, sans case nouvelle (D66)
# --------------------------------------------------------------------------- #


class TestRET5:
    async def test_ret5_retirer(self, essai_de):
        """« sans oignons » ne change pas le prix ; un retrait à prix (« sans cornichons », -0,30 €) le change ; ce qui n'est ni ingrédient ni option retirable est refusé avec ce qu'on peut retirer."""
        e = await brique(essai_de, "RET5")
        await e.tour("un burger sans oignons", ajouter=[{"article": "burger", "quantite": 1, "sans": ["oignons"]}])
        assert e.p["lignes"][-1]["retires"] == ["oignons"], e.retours[-1]
        assert _total(await RC.chiffrer_panier(e.monde.c, e.monde.a, "emporter", [{"code_caisse": "P-BURGER-UNIQUE", "quantite": 1, "choix": [], "retires": ["oignons"]}])) == 890
        r = await RC.chiffrer_panier(e.monde.c, e.monde.a, "emporter", [{"code_caisse": "P-BURGER-UNIQUE", "quantite": 1, "choix": [], "retires": ["Cornichons"]}])
        assert _total(r) == 890 - 30 and r.faits["lignes"][0]["choix"][0]["retire"] is True
        r = await RC.chiffrer_panier(e.monde.c, e.monde.a, "emporter", [{"code_caisse": "P-BURGER-UNIQUE", "quantite": 1, "choix": [], "retires": ["fromage"]}])
        assert r.statut == "HORS_CARTE", r

    async def test_ret5_aller_retour_caisse(self, essai_de):
        e = await brique(essai_de, "RET5")
        r = await RC.chiffrer_panier(e.monde.c, e.monde.a, "emporter", [{"code_caisse": "P-BURGER-UNIQUE", "quantite": 1, "choix": [], "retires": ["Cornichons", "oignons"]}])
        corps = commande_vers_hubrise({"numero": "n-1", "mode": "emporter", "client": {}, "lignes": [{**r.faits["lignes"][0]}]})
        article = corps["items"][0]
        assert article["price"] == "8.90 EUR"
        assert article["options"] == [
            {"option_list_name": "Retraits", "ref": "G-SAUCES-CORNICHONS", "name": "Cornichons", "price": "0.00 EUR", "removed": True},
            {"option_list_name": "Retraits", "name": "oignons", "price": "0.00 EUR", "removed": True},
        ]
        # Lot 19 bis (N5, prouvé en 204 : HubRise refuse un prix d'option négatif, 422) : le retrait remboursé part en remise, la cuisine lit toujours le retrait
        assert corps["discounts"] == [{"name": "Cornichons", "price_off": "0.30 EUR"}]

    async def test_ret5_fiche_du_modele(self, essai_de):
        assert not await la_brique_change_la_fiche("RET5", essai_de)


class TestRET6:
    async def test_ret6_deux_moities(self, essai_de):
        """« moitié reine, moitié calzone » : prises par les noms courants, au prix de la règle (la plus chère) ; chaque moitié part à la caisse."""
        e = await brique(essai_de, "RET6")
        await e.tour("moitié regina moitié calzone", ajouter=[{"article": "pizza moitié-moitié", "quantite": 1, "moities": ["regina", "calzone"]}])
        ligne = e.p["lignes"][-1]
        assert not ligne.get("attente") and sorted(c["option_code"] for c in ligne["choix"]) == ["G-MOITIES-CALZONE", "G-MOITIES-REGINA"], e.retours[-1]

    async def test_ret6_aller_retour_caisse(self, essai_de):
        e = await brique(essai_de, "RET6")
        choix = [{"option_code": "G-MOITIES-REGINA", "quantite": 1}, {"option_code": "G-MOITIES-CALZONE", "quantite": 1}]
        article = await article_en_caisse(e, "P-MM-UNIQUE", 1, choix)
        assert article["price"] == "0.00 EUR" and [(o["name"], o["price"]) for o in article["options"]] == [("Regina", "0.00 EUR"), ("Calzone", "14.00 EUR")]

    async def test_ret6_fiche_du_modele(self, essai_de):
        assert not await la_brique_change_la_fiche("RET6", essai_de)


async def test_briques_jamais_vues_sans_case_nouvelle(essai_de):
    """RET5 et RET6 : le rendu de la fiche est identique avec et sans leurs données, aucune case de plus au schéma ; déclarées « non vues sur carte »."""
    from api.services.commande.briques import registre
    from api.tests.mark.banc_a.commun import carte_de
    from api.tests.mark.partie_1 import rendu_de_la_fiche as RF

    for code in ("RET5", "RET6"):
        b = registre.BRIQUES[code]
        assert b.vue_sur_carte is False and b.change_la_fiche_du_modele is False, code
        avec = await essai_de(f"briques/{code}")
        sans = await essai_de(f"briques/{code}-sans", carte=RF.sans_la_brique(code, carte_de(f"briques/{code}")))
        rendu_avec, rendu_sans = await RF.rendu_de_la_fiche(avec), await RF.rendu_de_la_fiche(sans)
        assert rendu_avec["cases"] == rendu_sans["cases"] and rendu_avec["objets"] == rendu_sans["objets"], code


async def test_supplement_pas_compte_deux_fois_en_formule():
    """Un supplément porté par la ligne d'une formule n'est compté qu'une fois : la formule plus ce supplément, jamais deux fois (la ligne de formule gagne sur le supplément de taille)."""
    cola = {"id": "PC", "nom": "Cola", "categorie_id": "C", "ingredients": [], "alcool": False, "groupes": [], "tva_par_mode": {}, "declinaisons": [
        {"id": "DP", "nom": "Petit", "code_caisse": "COLA-P", "prix": 200, "vendable": True, "prix_par_mode": None},
        {"id": "DG", "nom": "Grand", "code_caisse": "COLA-G", "prix": 250, "vendable": True, "prix_par_mode": None}]}
    carte = {"produits": [cola], "groupes": [], "categories": [], "formules": [
        {"id": "F", "nom": "Menu", "code_caisse": "MENU", "prix": 1000, "vendable": True, "categorie_id": None,
         "lignes": [{"nom": "Boisson", "codes": ["COLA-P", "COLA-G"], "supplements": {"COLA-G": 150}}]}]}
    panier = RC._Panier(carte, "emporter", set(), "plus_chere")
    _, total, erreur = RC._lignes(panier, [{"code_caisse": "MENU", "quantite": 1, "choix": [{"option_code": "COLA-G", "quantite": 1}]}])
    assert erreur is None and total == 1000 + 150

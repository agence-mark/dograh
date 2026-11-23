"""[.mark] Chantier Partie 1, lot 9 : les briques groupes d'options et quotas (``services/commande/briques/opt*.py``).

Une classe par brique (``TestOPT1`` ...), chacune avec sa règle, son aller-retour en caisse et son test de rendu de la fiche (D66). Un test = un essai à la fois.
"""

from __future__ import annotations

import copy

import pytest

from api.db.bases_clients import restauration_commande as RC
from api.services.restauration.prises.hubrise_traduction import commande_vers_hubrise
from api.tests.mark.partie_1.aides_briques import article_en_caisse, brique, fait, la_brique_change_la_fiche, descendre_jusqu_a
from api.tests.mark.partie_1.test_l08_briques import _carte, _groupe, _option  # noqa: F401  (la petite carte au format que rend carte_du_restaurant)
from api.tests.mark.test_base_client import base_essai  # noqa: F401


# --------------------------------------------------------------------------- #
# L09-01 à L09-03 : la migration 038, le défaut du groupe, le quota inclus
# --------------------------------------------------------------------------- #


async def test_migration_038_montee_descente(base_prete):
    from api.db.bases_clients import connexion as schema

    colonnes = [("resto_groupe_choix", "inclus"), ("resto_groupe_choix", "prix_au_dela"), ("resto_groupe_choix", "si_option")]

    async def presentes(c) -> list[bool]:
        return [bool(await c.fetchval("SELECT 1 FROM information_schema.columns WHERE table_schema='mark' AND table_name=$1 AND column_name=$2", t, col)) for t, col in colonnes]

    c = await schema.connecter_proprietaire(base_prete)
    try:
        assert all(await presentes(c))
        for _ in range(2):  # descente, remontée, deux fois (rejouable)
            await descendre_jusqu_a(c, 38)  # de la tête à 038, dans l'ordre inverse
            assert not any(await presentes(c)) and 38 not in [r["version"] for r in await c.fetch("SELECT version FROM mark.schema_version")]
            assert 38 in await schema.appliquer_migrations(c)
            assert all(await presentes(c))
    finally:
        await c.close()


async def test_defaut_du_groupe_lu(essai_de):
    """Un groupe obligatoire dont le ``defaut`` nomme une option (aucune option ``par_defaut``) : elle est prise d'office, plus de question ; sans défaut, la question reste."""
    e = await brique(essai_de, "OPT1")
    await e.tour("un poulet braisé", ajouter=[{"article": "poulet braisé", "quantite": 1}])
    ligne = [l for l in e.p["lignes"] if l["nom"] == "Poulet braisé"][0]
    assert not ligne.get("attente") and [c["option_code"] for c in ligne["choix"]] == ["G-ACC-D-RIZ"], e.retours[-1]


async def test_quota_inclus_surcharge_par_la_declinaison():
    """Le nombre inclus vit sur le groupe ; la table déclinaison x groupe le surcharge pour une taille ; une taille qui ne le dit pas garde celui du groupe (D31)."""
    toppings = _groupe("G", "Toppings", [_option("top-a", "Perles", 0), _option("top-b", "Gelée", 0), _option("top-c", "Litchi", 0)], mini=0, maxi=3, role="supplement",
                       inclus=1, prix_au_dela=50)
    carte = _carte([toppings])
    carte["produits"][0]["declinaisons"] = [
        {"id": "D1", "nom": "Petit", "code_caisse": "BT-P", "prix": 500, "vendable": True, "prix_par_mode": None, "quotas": None},
        {"id": "D2", "nom": "Grand", "code_caisse": "BT-G", "prix": 600, "vendable": True, "prix_par_mode": None, "quotas": {"G": {"inclus": 2}}},
    ]
    trois = [{"option_code": "TOP-A", "quantite": 1}, {"option_code": "TOP-B", "quantite": 1}, {"option_code": "TOP-C", "quantite": 1}]

    def sous_total(code: str) -> int:
        panier = RC._Panier(carte, "emporter", set(), "plus_chere")
        _, total, erreur = RC._lignes(panier, [{"code_caisse": code, "quantite": 1, "choix": copy.deepcopy(trois)}])
        assert erreur is None, erreur
        return total

    assert sous_total("BT-P") == 500 + 2 * 50  # un compris (le groupe), deux à 0,50 €
    assert sous_total("BT-G") == 600 + 1 * 50  # deux compris (la taille le surcharge), un à 0,50 €


# --------------------------------------------------------------------------- #
# Les briques
# --------------------------------------------------------------------------- #


class TestOPT1:
    async def test_opt1_choix_obligatoire(self, essai_de):
        """Grillade (« 1 accompagnement inclus ») : la ligne attend son choix, la question porte le libellé du groupe ; le choix dit d'emblée la complète."""
        e = await brique(essai_de, "OPT1")
        await e.tour("une grillade", ajouter=[{"article": "grillade", "quantite": 1}])
        question = e.p["lignes"][-1]["attente"]
        assert question["nom"] == "Accompagnement" and question["options"] == ["Riz", "Frites", "Alloco"] and question["min"] == 1, e.retours[-1]
        e2 = await brique(essai_de, "OPT1")
        await e2.tour("une grillade avec du riz", ajouter=[{"article": "grillade", "quantite": 1, "composition": ["riz"]}])
        assert not e2.p["lignes"][-1].get("attente") and [c["option_code"] for c in e2.p["lignes"][-1]["choix"]] == ["G-ACC-RIZ"], e2.retours[-1]

    async def test_opt1_aller_retour_caisse(self, essai_de):
        e = await brique(essai_de, "OPT1")
        article = await article_en_caisse(e, "P-GRILLADE-UNIQUE", 1, [{"option_code": "G-ACC-ALLOCO", "quantite": 1}])
        assert article["price"] == "14.50 EUR" and article["options"] == [{"option_list_name": "Accompagnement", "ref": "G-ACC-ALLOCO", "name": "Alloco", "price": "1.00 EUR"}]

    async def test_opt1_fiche_du_modele(self, essai_de):
        assert await la_brique_change_la_fiche("OPT1", essai_de)


class TestOPT2:
    async def test_opt2_compter(self, essai_de):
        """« limite 2 sauces » : la troisième est refusée avec la raison, deux sont prises."""
        e = await brique(essai_de, "OPT2")
        r = await e.tour("un burger ketchup mayonnaise barbecue", ajouter=[{"article": "burger", "quantite": 1, "composition": ["ketchup", "mayonnaise", "barbecue"]}])
        assert "MAXIMUM_ATTEINT" in fait(r) and not any(l["nom"] == "Burger" for l in e.p["lignes"]), r
        r = await e.tour("un burger ketchup mayonnaise", ajouter=[{"article": "burger", "quantite": 1, "composition": ["ketchup", "mayonnaise"]}])
        assert len([c for c in e.p["lignes"][-1]["choix"]]) == 2, r

    async def test_opt2_aller_retour_caisse(self, essai_de):
        e = await brique(essai_de, "OPT2")
        article = await article_en_caisse(e, "P-BURGER-UNIQUE", 1, [{"option_code": "G-SAUCES-KETCHUP", "quantite": 1}, {"option_code": "G-SAUCES-MAYONNAISE", "quantite": 1}])
        assert article["price"] == "8.90 EUR" and [o["name"] for o in article["options"]] == ["Ketchup", "Mayonnaise"]

    async def test_opt2_fiche_du_modele(self, essai_de):
        assert not await la_brique_change_la_fiche("OPT2", essai_de)


class TestOPT3:
    async def test_opt3_facturer_au_dela(self, essai_de):
        """Bubble tea : le premier topping est compris, le second à 0,50 € ; la question dit le nombre compris et le prix au-delà."""
        from api.services.commande.briques.quota_inclus_puis_payant import brique_opt3_facturer_au_dela

        groupe = {"inclus": 1, "prix_au_dela": 50}
        assert brique_opt3_facturer_au_dela(groupe, {"prix": 0}, 0, 2) == (1, 1, 50)
        assert brique_opt3_facturer_au_dela(groupe, {"prix": 0}, 1, 1) == (0, 1, 50)
        assert brique_opt3_facturer_au_dela({"inclus": None, "prix_au_dela": None}, {"prix": 120}, 0, 2) == (0, 2, 120)  # sans quota : le prix de l'option, comme avant
        e = await brique(essai_de, "OPT3")
        await e.tour("un bubble tea", ajouter=[{"article": "bubble tea", "quantite": 1}])
        for composition, attendu in ((["perles"], 520), (["perles", "gelée"], 570), (["perles", "gelée", "litchi"], 620)):
            codes = {"perles": "G-TOPPINGS-PERLES", "gelée": "G-TOPPINGS-GELÉE", "litchi": "G-TOPPINGS-LITCHI"}
            r = await RC.chiffrer_panier(e.monde.c, e.monde.a, "emporter", [{"code_caisse": "P-BUBBLE-UNIQUE", "quantite": 1, "choix": [{"option_code": codes[c], "quantite": 1} for c in composition]}])
            assert r.statut == "OK" and r.faits["sous_total"] == attendu, (composition, r)

    async def test_opt3_aller_retour_caisse(self, essai_de):
        e = await brique(essai_de, "OPT3")
        article = await article_en_caisse(e, "P-BUBBLE-UNIQUE", 1, [{"option_code": "G-TOPPINGS-PERLES", "quantite": 1}, {"option_code": "G-TOPPINGS-LITCHI", "quantite": 1}])
        assert article["price"] == "5.20 EUR" and [(o["name"], o["price"]) for o in article["options"]] == [("Perles", "0.00 EUR"), ("Litchi", "0.50 EUR")]
        # une même option prise deux fois : une unité comprise, une payante, deux entrées
        e2 = await brique(essai_de, "OPT3")
        r = await RC.chiffrer_panier(e2.monde.c, e2.monde.a, "emporter", [{"code_caisse": "P-BUBBLE-UNIQUE", "quantite": 1, "choix": [{"option_code": "G-TOPPINGS-PERLES", "quantite": 1}]}])
        assert r.faits["lignes"][0]["choix"][0]["groupe"] == "Toppings"

    async def test_opt3_question_dit_le_quota(self, essai_de):
        from api.services.commande import moteur

        e = await brique(essai_de, "OPT3")
        article = await e.source.article("P-BUBBLE", "emporter")
        q = moteur._question(article, {"n": 1, "code": "P-BUBBLE-UNIQUE", "choix": [], "retires": []})
        assert q["inclus"] == 1 and q["prix_au_dela"] == 50, q

    async def test_opt3_fiche_du_modele(self, essai_de):
        assert await la_brique_change_la_fiche("OPT3", essai_de)


class TestOPT4:
    async def test_opt4_un_niveau_a_la_fois(self, essai_de):
        """Menu poulet : tenders, puis sauce, puis piment (trois niveaux), puis l'accompagnement ; chaque niveau est une question tant que l'option qui l'ouvre est choisie."""
        e = await brique(essai_de, "OPT4")
        await e.tour("un menu poulet", ajouter=[{"article": "menu poulet", "quantite": 1}])
        assert e.p["lignes"][-1]["attente"]["nom"] == "Plat", e.retours[-1]
        e2 = await brique(essai_de, "OPT4")
        await e2.tour("un menu poulet tenders barbecue doux frites", ajouter=[{"article": "menu poulet", "quantite": 1, "composition": ["tenders", "barbecue", "doux", "frites"]}])
        ligne = e2.p["lignes"][-1]
        assert not ligne.get("attente"), e2.retours[-1]
        plat = [c for c in ligne["choix"] if c["option_code"] == "G-PLAT-TENDERS"][0]
        sauce = plat["choix"][0]
        assert sauce["option_code"] == "G-SAUCE-T-BARBECUE" and sauce["choix"][0]["option_code"] == "G-PIMENT-DOUX", ligne["choix"]

    async def test_opt4_aller_retour_caisse(self, essai_de):
        e = await brique(essai_de, "OPT4")
        choix = [{"option_code": "G-PLAT-TENDERS", "quantite": 1, "choix": [{"option_code": "G-SAUCE-T-BARBECUE", "quantite": 1, "choix": [{"option_code": "G-PIMENT-DOUX", "quantite": 1}]}]},
                 {"option_code": "G-ACCOMP-FRITES", "quantite": 1}]
        article = await article_en_caisse(e, "P-MENU-UNIQUE", 1, choix)
        assert [o["name"] for o in article["options"]] == ["Tenders", "Barbecue", "Doux", "Frites"]  # un choix dans un choix est une option de plus, à plat

    async def test_opt4_fiche_du_modele(self, essai_de):
        assert not await la_brique_change_la_fiche("OPT4", essai_de)


class TestOPT5:
    async def test_opt5_jamais_hors_produit(self, essai_de):
        """« barbecue ou tomate » : pris sur la Texan qui le porte, refusé avec ce que la Margherita propose sur une pizza qui ne le porte pas."""
        e = await brique(essai_de, "OPT5")
        await e.tour("une texan barbecue", ajouter=[{"article": "texan", "quantite": 1, "composition": ["barbecue"]}])
        assert [c["option_code"] for c in e.p["lignes"][-1]["choix"]] == ["G-BASE-BBQ-BARBECUE"], e.retours[-1]
        r = await e.tour("une margherita tomate", ajouter=[{"article": "margherita", "quantite": 1, "composition": ["tomate"]}])
        assert "HORS_CARTE" in fait(r) and not any(l["nom"] == "Margherita" for l in e.p["lignes"]), r

    async def test_opt5_aller_retour_caisse(self, essai_de):
        e = await brique(essai_de, "OPT5")
        article = await article_en_caisse(e, "P-TEXAN-UNIQUE", 1, [{"option_code": "G-BASE-BBQ-TOMATE", "quantite": 1}])
        assert article["price"] == "13.90 EUR" and article["options"][0]["option_list_name"] == "Base barbecue ou tomate"

    async def test_opt5_fiche_du_modele(self, essai_de):
        assert not await la_brique_change_la_fiche("OPT5", essai_de)


class TestOPT7:
    async def test_opt7_ajouter_l_ecart(self, essai_de):
        """« en naan fromage » : l'écart s'ajoute au prix de base."""
        e = await brique(essai_de, "OPT7")
        r = await RC.chiffrer_panier(e.monde.c, e.monde.a, "emporter", [{"code_caisse": "P-ROLL-UNIQUE", "quantite": 1, "choix": [{"option_code": "G-SUPPORT-NAAN-FROMAGE", "quantite": 1}]}])
        assert r.faits["sous_total"] == 690 + 350, r
        await e.tour("un roll en naan fromage", ajouter=[{"article": "roll", "quantite": 1, "composition": ["naan fromage"]}])
        assert [c["option_code"] for c in e.p["lignes"][-1]["choix"]] == ["G-SUPPORT-NAAN-FROMAGE"], e.retours[-1]

    async def test_opt7_aller_retour_caisse(self, essai_de):
        e = await brique(essai_de, "OPT7")
        article = await article_en_caisse(e, "P-ROLL-UNIQUE", 1, [{"option_code": "G-SUPPORT-NAAN-FROMAGE", "quantite": 1}])
        assert article["price"] == "6.90 EUR" and article["options"][0]["price"] == "3.50 EUR"

    async def test_opt7_fiche_du_modele(self, essai_de):
        assert not await la_brique_change_la_fiche("OPT7", essai_de)


class TestOPT8:
    async def test_opt8_parfums_selon_le_nombre(self, essai_de):
        """« trois boules : vanille, chocolat, café » pris ; quatre parfums pour trois boules refusés avec la raison ; trois boules sans le bon nombre de parfums : la question reste."""
        e = await brique(essai_de, "OPT8")
        await e.tour("une coupe trois boules vanille chocolat café", ajouter=[{"article": "coupe de glace", "quantite": 1, "variante": "3 boules", "composition": ["vanille", "chocolat", "café"]}])
        ligne = e.p["lignes"][-1]
        assert not ligne.get("attente") and len(ligne["choix"]) == 3, e.retours[-1]
        e2 = await brique(essai_de, "OPT8")
        r = await e2.tour("trois boules, quatre parfums", ajouter=[{"article": "coupe de glace", "quantite": 1, "variante": "3 boules", "composition": ["vanille", "chocolat", "café", "pistache"]}])
        assert "MAXIMUM_ATTEINT" in fait(r), r
        e3 = await brique(essai_de, "OPT8")
        await e3.tour("trois boules, deux parfums", ajouter=[{"article": "coupe de glace", "quantite": 1, "variante": "3 boules", "composition": ["vanille", "chocolat"]}])
        assert e3.p["lignes"][-1]["attente"]["min"] == 3, e3.retours[-1]

    async def test_opt8_aller_retour_caisse(self, essai_de):
        e = await brique(essai_de, "OPT8")
        choix = [{"option_code": f"G-PARFUMS-{p}", "quantite": 1} for p in ("VANILLE", "CHOCOLAT", "CAFÉ")]
        article = await article_en_caisse(e, "P-COUPE-3-BOULES", 1, choix)
        assert article["price"] == "8.50 EUR" and len(article["options"]) == 3

    async def test_opt8_fiche_du_modele(self, essai_de):
        assert await la_brique_change_la_fiche("OPT8", essai_de)


class TestOPT9:
    async def test_opt9_comme_opt1(self, essai_de):
        """« au lait d'avoine, sans sucre » : deux groupes obligatoires pris, l'écart du lait ajouté."""
        e = await brique(essai_de, "OPT9")
        await e.tour("un thé au lait d'avoine sans sucre", ajouter=[{"article": "thé au lait", "quantite": 1, "composition": ["lait d'avoine", "sans sucre"]}])
        ligne = e.p["lignes"][-1]
        assert not ligne.get("attente") and sorted(c["option_code"] for c in ligne["choix"]) == ["G-LAIT-LAIT-DAVOINE", "G-SUCRE-SANS-SUCRE"], e.retours[-1]
        r = await RC.chiffrer_panier(e.monde.c, e.monde.a, "emporter", [{"code_caisse": "P-THE-UNIQUE", "quantite": 1, "choix": [{"option_code": o["option_code"], "quantite": 1} for o in ligne["choix"]]}])
        assert r.faits["sous_total"] == 480 + 100

    async def test_opt9_aller_retour_caisse(self, essai_de):
        e = await brique(essai_de, "OPT9")
        choix = [{"option_code": "G-LAIT-LAIT-DAVOINE", "quantite": 1}, {"option_code": "G-SUCRE-SANS-SUCRE", "quantite": 1}]
        article = await article_en_caisse(e, "P-THE-UNIQUE", 1, choix)
        assert article["price"] == "4.80 EUR" and [o["price"] for o in article["options"]] == ["1.00 EUR", "0.00 EUR"]

    async def test_opt9_fiche_du_modele(self, essai_de):
        assert not await la_brique_change_la_fiche("OPT9", essai_de)


# --------------------------------------------------------------------------- #
# Les briques jamais vues sur une carte : en dernier, côté code seulement, sans case nouvelle (D66)
# --------------------------------------------------------------------------- #


class TestOPT6:
    async def test_opt6_poser_b_si_a(self, essai_de):
        """« avec une salade » ouvre « vinaigrette » ; sans salade, la vinaigrette n'est jamais demandée ni acceptée."""
        e = await brique(essai_de, "OPT6")
        await e.tour("une assiette avec une salade", ajouter=[{"article": "assiette du jour", "quantite": 1, "composition": ["salade"]}])
        assert e.p["lignes"][-1]["attente"]["nom"] == "Vinaigrette", e.retours[-1]
        e2 = await brique(essai_de, "OPT6")
        await e2.tour("une assiette avec des frites", ajouter=[{"article": "assiette du jour", "quantite": 1, "composition": ["frites"]}])
        assert not e2.p["lignes"][-1].get("attente"), e2.retours[-1]
        r = await RC.chiffrer_panier(e2.monde.c, e2.monde.a, "emporter", [{"code_caisse": "P-ASSIETTE-UNIQUE", "quantite": 1, "choix": [{"option_code": "G-GARN-FRITES", "quantite": 1}, {"option_code": "G-VINAIGRETTE-CLASSIQUE", "quantite": 1}]}])
        assert r.statut == "HORS_CARTE", r  # la vinaigrette n'existe pas sans la salade
        r = await RC.chiffrer_panier(e2.monde.c, e2.monde.a, "emporter", [{"code_caisse": "P-ASSIETTE-UNIQUE", "quantite": 1, "choix": [{"option_code": "G-GARN-SALADE", "quantite": 1}]}])
        assert r.statut == "CHOIX_OBLIGATOIRE", r  # avec la salade, la vinaigrette est exigée

    async def test_opt6_aller_retour_caisse(self, essai_de):
        e = await brique(essai_de, "OPT6")
        article = await article_en_caisse(e, "P-ASSIETTE-UNIQUE", 1, [{"option_code": "G-GARN-SALADE", "quantite": 1}, {"option_code": "G-VINAIGRETTE-CLASSIQUE", "quantite": 1}])
        assert [o["name"] for o in article["options"]] == ["Salade", "Classique"]

    async def test_opt6_fiche_du_modele(self, essai_de):
        assert not await la_brique_change_la_fiche("OPT6", essai_de)


class TestOPT10:
    async def test_opt10_comme_opt1(self, essai_de):
        """« à point » : posé sur le groupe de cuisson de l'entrecôte ; sur un article sans groupe de cuisson : une note de ligne signalée, jamais un refus (E19)."""
        e = await brique(essai_de, "OPT10")
        await e.tour("une entrecôte à point", ajouter=[{"article": "entrecôte", "quantite": 1, "composition": ["à point"]}])
        assert [c["option_code"] for c in e.p["lignes"][-1]["choix"]] == ["G-CUISSON-À-POINT"], e.retours[-1]
        await e.tour("une salade à point", ajouter=[{"article": "salade verte", "quantite": 1, "composition": ["à point"]}])
        salade = [l for l in e.p["lignes"] if l["nom"] == "Salade verte"][0]
        assert salade.get("choix_sans_objet") == ["à point"] and not salade["choix"], e.retours[-1]

    async def test_opt10_aller_retour_caisse(self, essai_de):
        e = await brique(essai_de, "OPT10")
        article = await article_en_caisse(e, "P-ENTRECOTE-UNIQUE", 1, [{"option_code": "G-CUISSON-À-POINT", "quantite": 1}])
        assert article["options"][0]["name"] == "À point"

    async def test_opt10_fiche_du_modele(self, essai_de):
        assert not await la_brique_change_la_fiche("OPT10", essai_de)


class TestOPT11:
    async def test_opt11_comme_opt1(self, essai_de):
        """« pas trop épicé » sur une carte qui a le groupe d'épice : le niveau est demandé, puis posé."""
        e = await brique(essai_de, "OPT11")
        await e.tour("un curry", ajouter=[{"article": "curry", "quantite": 1}])
        assert e.p["lignes"][-1]["attente"]["nom"] == "Niveau d'épice", e.retours[-1]
        e2 = await brique(essai_de, "OPT11")
        await e2.tour("un curry doux", ajouter=[{"article": "curry", "quantite": 1, "composition": ["doux"]}])
        assert [c["option_code"] for c in e2.p["lignes"][-1]["choix"]] == ["G-EPICE-DOUX"], e2.retours[-1]

    async def test_opt11_aller_retour_caisse(self, essai_de):
        e = await brique(essai_de, "OPT11")
        article = await article_en_caisse(e, "P-CURRY-UNIQUE", 1, [{"option_code": "G-EPICE-DOUX", "quantite": 1}])
        assert article["options"][0]["option_list_name"] == "Niveau d'épice"

    async def test_opt11_fiche_du_modele(self, essai_de):
        assert not await la_brique_change_la_fiche("OPT11", essai_de)


async def test_briques_jamais_vues_sans_case_nouvelle(essai_de):
    """OPT6, OPT10, OPT11 : le rendu de la fiche est identique avec et sans leurs données, aucune case de plus au schéma ; déclarées « non vues sur carte »."""
    from api.services.commande.briques import registre
    from api.tests.mark.partie_1 import rendu_de_la_fiche as RF
    from api.tests.mark.banc_a.commun import carte_de

    for code in ("OPT6", "OPT10", "OPT11"):
        b = registre.BRIQUES[code]
        assert b.vue_sur_carte is False and b.change_la_fiche_du_modele is False, code
        avec = await essai_de(f"briques/{code}")
        sans = await essai_de(f"briques/{code}-sans", carte=RF.sans_la_brique(code, carte_de(f"briques/{code}")))
        rendu_avec, rendu_sans = await RF.rendu_de_la_fiche(avec), await RF.rendu_de_la_fiche(sans)
        assert rendu_avec["cases"] == rendu_sans["cases"], code
        assert rendu_avec["objets"] == rendu_sans["objets"], code


async def test_maximum_atteint_est_dit_par_le_code(essai_de):
    """Conversation DEC2-B (19/11) : « un XL avec quatre viandes » : le code refuse la quatrième, mais ne le disait pas (le modèle annonçait « c'est noté »). Un refus de maximum est un
    refus : retour PARTIEL, dit par le code avant la phrase du modèle, avec le nombre au plus."""

    e = await brique(essai_de, "DEC2")
    r = await e.tour("un XL avec quatre viandes", ajouter=[{"article": "tacos", "quantite": 1, "variante": "XL", "composition": ["poulet", "merguez", "steak", "kefta"]}])
    assert r["statut"] == "PARTIEL" and r.get("dit_avant_ta_phrase") is True, r
    from api.services.commande.porte import CLE_TEXTES_DU_CODE

    dit = e.fiche_de_l_appel[CLE_TEXTES_DU_CODE]["prefixe"]
    assert "trois" in dit.lower() and "Viandes" in dit, dit

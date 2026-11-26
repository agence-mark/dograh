"""[.mark] Chantier Partie 1, lot 8 : les briques article et déclinaison (``services/commande/briques/``) et l'envoi des options à la caisse (D50).

Une classe par brique (``TestART1`` ...), chacune avec sa règle, son aller-retour en caisse et son test de rendu de la fiche (D66).
"""

from __future__ import annotations

from api.services.actions_communes import conversation as CONV
from api.db.bases_clients import restauration_commande as RC
from api.services.restauration.caisse.prises.hubrise_traduction import commande_vers_hubrise
from api.services.commande import textes_de_secours as TS


# --------------------------------------------------------------------------- #
# Une petite carte au format que rend ``carte_du_restaurant`` (pas de base : le calcul d'un panier est pur)
# --------------------------------------------------------------------------- #


def _option(ref: str, nom: str, prix: int, **plus) -> dict:
    return {"id": ref, "groupe_id": "G", "nom": nom, "code_caisse": ref.upper(), "prix": prix, "par_defaut": False, "retirable": False, "vendable": True, **plus}


def _carte(groupes: list[dict], declinaison_prix: int = 1250) -> dict:
    return {
        "produits": [{"id": "P1", "nom": "Reine", "categorie_id": "C", "ingredients": [], "alcool": False, "groupes": [g["id"] for g in groupes],
                      "declinaisons": [{"id": "D1", "nom": "Senior", "code_caisse": "REINE-S", "prix": declinaison_prix, "vendable": True, "prix_par_mode": None}],
                      "tva_par_mode": {}}],
        "groupes": groupes, "formules": [], "categories": [],
    }


def _groupe(gid: str, nom: str, options: list[dict], *, mini: int = 0, maxi: int = 3, role: str = "supplement", parent: str | None = None, **plus) -> dict:
    return {"id": gid, "nom": nom, "min": mini, "max": maxi, "max_par_option": 3, "role": role, "defaut": [], "parent_option_id": parent, "options": options, **plus}


def _lignes(carte: dict, choix: list[dict], regle: str = "plus_chere"):
    panier = RC._Panier(carte, "emporter", set(), regle)
    calculees, sous_total, erreur = RC._lignes(panier, [{"code_caisse": "REINE-S", "quantite": 1, "choix": choix}])
    assert erreur is None, erreur
    return calculees, sous_total


def _corps_caisse(calculees: list[dict]) -> dict:
    return commande_vers_hubrise({"numero": "n-1", "mode": "emporter", "client": {}, "lignes": calculees})


# --------------------------------------------------------------------------- #
# L08-18 et L08-19 : les options partent à la caisse sous leur nom et leur prix (D50)
# --------------------------------------------------------------------------- #


def test_options_sous_leur_nom_et_prix():
    """« Tiramisu pistache » et son prix, jamais « TIR-PISTACHE » à 0 € ; le groupe de l'option est sa liste côté caisse."""
    carte = _carte([_groupe("G", "Suppléments", [_option("sup-oeuf", "Œuf", 100), _option("sup-fromage", "Fromage", 150)])])
    calculees, _ = _lignes(carte, [{"option_code": "SUP-FROMAGE", "quantite": 1}])
    assert calculees[0]["choix"] == [{"option_code": "SUP-FROMAGE", "quantite": 1, "choix": [], "nom": "Fromage", "prix": 150, "groupe": "Suppléments"}]
    option = _corps_caisse(calculees)["items"][0]["options"][0]
    assert option == {"option_list_name": "Suppléments", "ref": "SUP-FROMAGE", "name": "Fromage", "price": "1.50 EUR"}


def test_prix_unitaire_sans_supplements():
    """Le corps envoyé porte le prix du produit seul ; les suppléments sont dans leurs options ; la caisse retrouve le même total."""
    carte = _carte([_groupe("G", "Suppléments", [_option("sup-oeuf", "Œuf", 100), _option("sup-fromage", "Fromage", 150)])])
    calculees, sous_total = _lignes(carte, [{"option_code": "SUP-FROMAGE", "quantite": 1}, {"option_code": "SUP-OEUF", "quantite": 2}])
    assert calculees[0]["prix_unitaire"] == 1250 + 150 + 200 == sous_total  # le calcul interne reste tout compris
    article = _corps_caisse(calculees)["items"][0]
    assert article["price"] == "12.50 EUR"
    total_caisse = 1250 + sum(int(round(float(o["price"].split()[0]) * 100)) * o.get("quantity", 1) for o in article["options"])
    assert total_caisse == sous_total


def test_sous_option_et_moities_gardent_la_somme_des_choix():
    """Une sous-option et les moitiés (règle « la plus chère ») : la somme des prix des choix vaut le supplément, la caisse ne recalcule pas un autre total."""
    sauces = _groupe("GS", "Sauces", [_option("sau-bbq", "Barbecue", 50)], role="supplement", parent="moitie-a")
    moities = _groupe("GM", "Moitiés", [_option("moitie-a", "Regina", 1200), _option("moitie-b", "Calzone", 1400)], role="moities", maxi=2, mini=2)
    carte = _carte([moities, sauces])
    calculees, sous_total = _lignes(carte, [{"option_code": "MOITIE-A", "quantite": 1, "choix": [{"option_code": "SAU-BBQ", "quantite": 1}]}, {"option_code": "MOITIE-B", "quantite": 1}])
    assert sous_total == 1250 + 1400 + 50

    def somme(choix: list[dict]) -> int:
        return sum((c["prix"] + somme(c["choix"])) * c["quantite"] for c in choix)

    assert 1250 + somme(calculees[0]["choix"]) == sous_total
    assert _corps_caisse(calculees)["items"][0]["price"] == "12.50 EUR"


# --------------------------------------------------------------------------- #
# L08-03 : la migration 037, montée, descente, remontée
# --------------------------------------------------------------------------- #

COLONNES_037 = [("resto_declinaison", "type"), ("resto_declinaison", "libelle_question"), ("resto_declinaison", "quotas"), ("resto_categorie", "role"),
                ("resto_surcouche", "genre"), ("resto_surcouche", "nom_commun"), ("resto_surcouche", "du_moment"), ("resto_surcouche", "texte_du_jour")]


async def _colonnes(c, colonnes) -> list[bool]:
    return [bool(await c.fetchval("SELECT 1 FROM information_schema.columns WHERE table_schema='mark' AND table_name=$1 AND column_name=$2", t, col)) for t, col in colonnes]


async def test_migration_037_montee_descente(base_prete):
    from api.db.bases_clients import connexion as schema

    c = await schema.connecter_proprietaire(base_prete)
    try:
        assert all(await _colonnes(c, COLONNES_037)) and await c.fetchval("SELECT to_regclass('mark.resto_signalement_carte')") is not None
        assert (await c.fetchval("SELECT max(version) FROM mark.schema_version")) >= 37
        for _ in range(2):  # descente, remontée, deux fois (rejouable)
            await descendre_jusqu_a(c, 37)  # dans l'ordre inverse des versions, de la tête à 037
            assert not any(await _colonnes(c, COLONNES_037)) and await c.fetchval("SELECT to_regclass('mark.resto_signalement_carte')") is None
            assert 37 not in [r["version"] for r in await c.fetch("SELECT version FROM mark.schema_version")]
            assert 37 in await schema.appliquer_migrations(c)
            assert all(await _colonnes(c, COLONNES_037))
    finally:
        await c.close()


# --------------------------------------------------------------------------- #
# L08-12 à L08-14 : plus aucun mot de restaurant dans le code (E17)
# --------------------------------------------------------------------------- #


def _declinaisons(*noms: str, **plus) -> list[dict]:
    return [{"nom": n, "vendable": True, "rupture": False, **plus} for n in noms]


def test_question_de_declinaison_au_libelle_de_la_carte():
    """Kebab : plus jamais « Quelle taille » sur « Classic, Royal » ; le mot vient du libellé de la carte, sinon du type, sinon « taille » (carte ancienne)."""
    from api.services.commande import moteur
    from api.services.commande.briques import declinaison_nommee

    def phrase(declinaisons, article="Kefta"):
        # C7 B3 (Evan 25/11 8 h 45) : le moteur ne compose plus la question ; ses faits (la question de la carte, l'article) refont le texte d'avant
        return TS.question_d_un_choix({"question": declinaison_nommee.brique_dec1_demander_la_declinaison(declinaisons), "article_de_la_carte": article})

    assert phrase(_declinaisons("Classic", "Royal", type="variante")) == "Quelle version pour votre Kefta : Classic ou Royal ?"
    assert phrase(_declinaisons("4 pièces", "8 pièces", type="pieces"), "Nuggets") == "Combien de pièces pour votre Nuggets : 4 pièces ou 8 pièces ?"
    assert phrase(_declinaisons("Classic", "Royal", libelle_question="Quelle formule")) == "Quelle formule pour votre Kefta : Classic ou Royal ?"
    assert phrase(_declinaisons("Normale", "Grande")) == "Quelle taille pour votre Kefta : Normale ou Grande ?"  # carte ancienne : le comportement d'avant
    question = declinaison_nommee.brique_dec1_demander_la_declinaison(_declinaisons("Classic", "Royal", type="variante"))
    assert question["type"] == "declinaison" and question["options"] == ["Classic", "Royal"] and question["nom"] == "version"


def test_vente_en_plus_par_role_de_categorie():
    """Une catégorie « Rafraîchissements » de rôle ``boisson`` est proposée ; « Vins » de rôle ``jamais_propose`` ne l'est pas, ni ses sous-catégories."""
    from api.db.bases_clients import restauration_en_plus as EP

    categories = {
        "c1": {"id": "c1", "nom": "Rafraîchissements", "parent_id": None, "role": "boisson"},
        "c2": {"id": "c2", "nom": "Vins", "parent_id": None, "role": "jamais_propose"},
        "c3": {"id": "c3", "nom": "Vins rouges", "parent_id": "c2", "role": "boisson"},
        "c4": {"id": "c4", "nom": "Boissons", "parent_id": None, "role": None},  # un nom qui ressemble à un rôle n'en est pas un : jamais deviné
        "c5": {"id": "c5", "nom": "Glaces", "parent_id": "c1", "role": None},
    }
    assert EP._famille(categories, "c1") == "boisson"
    assert EP._famille(categories, "c2") is None and EP._famille(categories, "c3") is None
    assert EP._famille(categories, "c4") is None
    assert EP._famille(categories, "c5") == "boisson"  # la catégorie sans rôle prend celui de son parent


def test_aucun_mot_de_restaurant_dans_le_code():
    """Aucune des constantes retirées (genre, noms communs, catégories de plats, familles de la vente en plus) n'est revenue dans le code générique."""
    import ast
    import re
    from pathlib import Path

    from api.tests.mark.partie_1.mots_de_restaurant import CATEGORIES_DE_PLATS, COMMUNS, PROPRES

    api = Path(__file__).resolve().parents[3]
    assert not (api / "services" / "restauration" / "mots_du_metier.py").exists()
    interdits = set(COMMUNS) | set(PROPRES) | set(CATEGORIES_DE_PLATS)
    # Les rôles de catégorie (migration 037) et « formule » (une rubrique du format commun de la carte, lots 11 et 12) sont du vocabulaire de la donnée, pas
    # des mots écrits dans la cuisine pour accorder ce que l'agent dit.
    interdits -= {"boisson", "dessert", "formule"}
    fichiers = [*(api / "services" / "commande").rglob("*.py"), api / "db" / "bases_clients" / "restauration_en_plus.py"]
    trouves = []
    for fichier in fichiers:
        arbre = ast.parse(fichier.read_text(encoding="utf-8"))
        docstrings = {id(n.body[0].value) for n in ast.walk(arbre) if isinstance(n, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and n.body
                      and isinstance(n.body[0], ast.Expr) and isinstance(n.body[0].value, ast.Constant)}
        for noeud in ast.walk(arbre):
            if isinstance(noeud, ast.Constant) and isinstance(noeud.value, str) and id(noeud) not in docstrings:
                mots = set(re.split(r"[^a-zà-ÿ]+", noeud.value.lower()))
                trouves += [(fichier.name, mot) for mot in sorted(mots & interdits)]
    assert not trouves, trouves


# --------------------------------------------------------------------------- #
# Les briques : une classe chacune, sur sa carte d'essai (``banc_a/cartes/briques/<CODE>.json``)
# --------------------------------------------------------------------------- #

import json  # noqa: E402

import pytest  # noqa: E402

from api.db.bases_clients import restauration, restauration_ecran  # noqa: E402
from api.services.commande import moteur  # noqa: E402
from api.tests.mark.equipe_commun import sans_preparation_des_organisations  # noqa: E402,F401
from api.tests.mark.test_base_client import base_essai  # noqa: E402,F401
from api.tests.mark.test_contacts_portail import seconde_base  # noqa: E402,F401
from api.tests.mark.partie_1.aides_briques import article_en_caisse, brique, fait, la_brique_change_la_fiche, statuts, descendre_jusqu_a  # noqa: E402,F401


class TestART1:
    async def test_art1_chiffrer(self, essai_de):
        """« deux tiramisus » : une ligne au prix de la carte ; « une 1664 » (un nom fait de chiffres) est un article, jamais une quantité."""
        from api.services.commande.briques.article_simple import brique_art1_chiffrer

        assert brique_art1_chiffrer(300, 2) == 600
        e = await brique(essai_de, "ART1")
        await e.tour("deux tiramisus", ajouter=[{"article": "tiramisu", "quantite": 2}])
        await e.tour("et une 1664", ajouter=[{"article": "1664", "quantite": 1}])
        assert [(l["nom"], l["quantite"]) for l in e.p["lignes"]] == [("Tiramisu", 2), ("1664", 1)], e.retours[-1]
        r = await RC.chiffrer_panier(e.monde.c, e.monde.a, "emporter", [{"code_caisse": "P-TIRAMISU-UNIQUE", "quantite": 2}, {"code_caisse": "P-1664-UNIQUE", "quantite": 1}])
        assert r.faits["sous_total"] == 600 + 400

    async def test_art1_aller_retour_caisse(self, essai_de):
        e = await brique(essai_de, "ART1")
        article = await article_en_caisse(e, "P-TIRAMISU-UNIQUE", 2)
        assert (article["price"], article["quantity"]) == ("3.00 EUR", "2") and "options" not in article

    async def test_art1_fiche_du_modele(self, essai_de):
        assert not await la_brique_change_la_fiche("ART1", essai_de)


class TestART2:
    async def test_art2_format_en_declinaison(self, essai_de):
        """« un seau de dix » : le format dix (10 pièces), jamais dix articles ; sans format dit, la question porte les formats."""
        e = await brique(essai_de, "ART2")
        await e.tour("un seau de tenders de dix", ajouter=[{"article": "tenders", "quantite": 1, "variante": "10 pièces"}])
        assert [(l["nom"], l["quantite"]) for l in e.p["lignes"]] == [("Tenders 10 pièces", 1)], e.retours[-1]
        await e.tour("et des nuggets", ajouter=[{"article": "nuggets", "quantite": 1}])
        question = e.p["lignes"][-1].get("attente") or {}
        assert question.get("options") == ["6 pièces", "10 pièces"] and question.get("nom") == "pièces", e.retours[-1]

    async def test_art2_aller_retour_caisse(self, essai_de):
        e = await brique(essai_de, "ART2")
        article = await article_en_caisse(e, "P-TENDERS-10-PIÈCES")
        assert article["price"] == "11.00 EUR" and article["sku_ref"] == "P-TENDERS-10-PIÈCES"

    async def test_art2_fiche_du_modele(self, essai_de):
        assert await la_brique_change_la_fiche("ART2", essai_de)  # la question parle de pièces, plus de taille


class TestDEC1:
    async def test_dec1_demander_la_declinaison(self, essai_de):
        """Sur la carte Kebab-like : « un Kefta » demande la version (Classic ou Royal), « une Regina » la taille ; jamais l'un pour l'autre."""
        e = await brique(essai_de, "DEC1")
        r = await e.tour("un kefta", ajouter=[{"article": "kefta", "quantite": 1}])
        # C7 B3 (Evan 25/11 8 h 45) : aucun texte, ni au registre ni au modèle ; les faits du retour refont la question d'avant
        assert e.p["lignes"][-1]["attente"]["nom"] == "version" and CONV.question_de(e.p)["texte"] == "" and r["question"]["texte"] == "", r
        assert "Quelle version pour votre Kefta : Classic ou Royal" in TS.question_d_un_choix(r["resultats"][0]["faits"]), r
        r = await e.tour("une regina", ajouter=[{"article": "regina", "quantite": 1}])
        faits = next(x["faits"] for x in r["resultats"] if "question" in (x.get("faits") or {}))  # le retour qui pose la question (la Regina)
        assert "Quelle taille pour votre Regina : Junior ou Senior" in TS.question_d_un_choix(faits), r

    async def test_dec1_aller_retour_caisse(self, essai_de):
        e = await brique(essai_de, "DEC1")
        article = await article_en_caisse(e, "P-KEFTA-ROYAL")
        assert article["price"] == "7.00 EUR"

    async def test_dec1_fiche_du_modele(self, essai_de):
        assert await la_brique_change_la_fiche("DEC1", essai_de)


class TestDEC3:
    async def test_dec3_demander_la_contenance(self, essai_de):
        """« un coca » sur une carte à 33 cl et à la bouteille : la contenance est demandée, jamais supposée ; la réponse la pose."""
        e = await brique(essai_de, "DEC3")
        r = await e.tour("un coca", ajouter=[{"article": "coca", "quantite": 1}])
        assert e.p["lignes"][-1]["attente"]["nom"] == "contenance" and r["question"]["texte"] == "", r  # C7 B3 : aucun texte ; les faits refont la question d'avant
        assert "Quelle contenance pour votre Coca : 33 centilitres ou Bouteille" in TS.question_d_un_choix(r["resultats"][0]["faits"]), r
        await e.tour("la bouteille", ajouter=[{"article": "coca", "quantite": 1, "variante": "Bouteille"}])
        assert [(l["nom"], l["quantite"]) for l in e.p["lignes"] if not l.get("attente")] == [("Coca Bouteille", 1)], e.retours[-1]

    async def test_dec3_aller_retour_caisse(self, essai_de):
        e = await brique(essai_de, "DEC3")
        assert (await article_en_caisse(e, "P-COCA-33-CL"))["price"] == "1.80 EUR"

    async def test_dec3_fiche_du_modele(self, essai_de):
        assert await la_brique_change_la_fiche("DEC3", essai_de)  # la question parle de contenance, plus de taille


class TestDEC4:
    async def test_dec4_une_base_par_article(self, essai_de):
        """« base crème » sur une pizza qui la porte : la base est posée ; sur une pizza qui a d'autres choix mais pas celle-là : refus avec les choix ; sur un article qui
        n'a aucun choix : jamais un refus, la demande devient une note de ligne et est signalée (E19, lot 4)."""
        e = await brique(essai_de, "DEC4")
        await e.tour("un texan base crème", ajouter=[{"article": "texan", "quantite": 1, "supplements": ["crème"]}])
        assert [c["option_code"] for c in e.p["lignes"][0]["choix"]] == ["G-BASE-CRÈME"], e.retours[-1]
        r = await e.tour("une margherita base crème", ajouter=[{"article": "margherita", "quantite": 1, "supplements": ["crème"]}])
        assert "HORS_CARTE" in fait(r) and not any(l["nom"] == "Margherita" for l in e.p["lignes"]), r
        r = await e.tour("un tiramisu base crème", ajouter=[{"article": "tiramisu", "quantite": 1, "supplements": ["crème"]}])
        tiramisu = [l for l in e.p["lignes"] if l["nom"] == "Tiramisu"]
        assert tiramisu and not tiramisu[0]["choix"] and tiramisu[0].get("choix_sans_objet") == ["crème"], r

    async def test_dec4_surcout_ajoute(self, essai_de):
        e = await brique(essai_de, "DEC4")
        r = await RC.chiffrer_panier(e.monde.c, e.monde.a, "emporter", [{"code_caisse": "P-PIZZA-UNIQUE", "quantite": 1, "choix": [{"option_code": "G-BASE-CHEEZY-CRUST", "quantite": 1}]}])
        assert r.faits["sous_total"] == 1390 + 300

    async def test_dec4_aller_retour_caisse(self, essai_de):
        e = await brique(essai_de, "DEC4")
        article = await article_en_caisse(e, "P-PIZZA-UNIQUE", 1, [{"option_code": "G-BASE-CHEEZY-CRUST", "quantite": 1}])
        assert article["price"] == "13.90 EUR" and article["options"] == [{"option_list_name": "Base", "ref": "G-BASE-CHEEZY-CRUST", "name": "Cheezy Crust", "price": "3.00 EUR"}]

    async def test_dec4_fiche_du_modele(self, essai_de):
        assert await la_brique_change_la_fiche("DEC4", essai_de)


class TestDEC5:
    async def test_dec5_double_produit_ou_supplement(self, essai_de):
        """« un double steak » : le produit au grammage double OU le supplément, selon la carte ; jamais compté deux fois."""
        e = await brique(essai_de, "DEC5")
        await e.tour("un master 2 steaks", ajouter=[{"article": "master", "quantite": 1, "variante": "2 x 120 g"}])
        assert [(l["nom"], l["quantite"]) for l in e.p["lignes"]] == [("Master 2 x 120 g", 1)], e.retours[-1]
        await e.tour("un cheese avec double steak", ajouter=[{"article": "cheese", "quantite": 1, "supplements": ["double steak"]}])
        cheese = [l for l in e.p["lignes"] if l["nom"] == "Cheese"][0]
        assert [c["option_code"] for c in cheese["choix"]] == ["G-SUPPL-DOUBLE-STEAK"], e.retours[-1]

    async def test_dec5_aller_retour_caisse(self, essai_de):
        e = await brique(essai_de, "DEC5")
        article = await article_en_caisse(e, "P-CHEESE-UNIQUE", 1, [{"option_code": "G-SUPPL-DOUBLE-STEAK", "quantite": 1}])
        assert article["price"] == "5.90 EUR" and article["options"][0]["price"] == "4.00 EUR"

    async def test_dec5_fiche_du_modele(self, essai_de):
        assert await la_brique_change_la_fiche("DEC5", essai_de)


class TestART3:
    async def test_art3_texte_du_jour(self, essai_de):
        """« c'est quoi le plat du jour ? » rend le texte saisi, tel quel ; sans texte, rien n'est inventé."""
        e = await brique(essai_de, "ART3")
        r = await e.lecture(sujet="article", article="plat du jour")
        assert '"renseigne": false' in fait(r) and "gratin" not in fait(r), r
        assert await restauration_ecran.poser_le_produit_du_moment(e.monde.c, e.monde.a, "P-PLAT-DU-JOUR", "  gratin de courgettes   et riz ", "essai")
        e.source.c.instantane = None  # un nouvel appel : la carte chargée change à l'appel suivant, jamais au milieu (D61, point 3)
        r = await e.lecture(sujet="article", article="plat du jour")
        assert "gratin de courgettes et riz" in fait(r) and '"renseigne": true' in fait(r), r

    async def test_art3_aller_retour_caisse(self, essai_de):
        e = await brique(essai_de, "ART3")
        assert (await article_en_caisse(e, "P-PLAT-DU-JOUR-UNIQUE"))["price"] == "15.00 EUR"

    async def test_art3_fiche_du_modele(self, essai_de):
        assert await la_brique_change_la_fiche("ART3", essai_de)


class TestDEC2:
    async def test_dec2_quota_selon_la_declinaison(self, essai_de):
        """Tacos : M une viande, L deux, XL trois ; « un XL, poulet, merguez, steak » pris ; quatre viandes refusées avec la raison."""
        e = await brique(essai_de, "DEC2")
        await e.tour("un XL poulet merguez steak", ajouter=[{"article": "tacos", "quantite": 1, "variante": "XL", "composition": ["poulet", "merguez", "steak"]}])
        ligne = e.p["lignes"][0]
        assert not ligne.get("attente") and sorted(c["option_code"] for c in ligne["choix"]) == ["G-VIANDES-MERGUEZ", "G-VIANDES-POULET", "G-VIANDES-STEAK"], e.retours[-1]
        e2 = await brique(essai_de, "DEC2")
        r = await e2.tour("un XL avec quatre viandes", ajouter=[{"article": "tacos", "quantite": 1, "variante": "XL", "composition": ["poulet", "merguez", "steak", "kefta"]}])
        assert "MAXIMUM_ATTEINT" in fait(r), r
        e3 = await brique(essai_de, "DEC2")
        await e3.tour("un M", ajouter=[{"article": "tacos", "quantite": 1, "variante": "M"}])
        assert e3.p["lignes"][0]["attente"]["min"] == 1 and e3.p["lignes"][0]["attente"]["max"] == 1
        e4 = await brique(essai_de, "DEC2")
        await e4.tour("un L", ajouter=[{"article": "tacos", "quantite": 1, "variante": "L", "composition": ["poulet"]}])
        assert e4.p["lignes"][0]["attente"]["nom"] == "Viandes", e4.retours[-1]  # il en manque une : la question reste ouverte au minimum de la taille

    async def test_dec2_aller_retour_caisse(self, essai_de):
        e = await brique(essai_de, "DEC2")
        choix = [{"option_code": "G-VIANDES-POULET", "quantite": 1}, {"option_code": "G-VIANDES-MERGUEZ", "quantite": 1}]
        article = await article_en_caisse(e, "P-TACOS-L", 1, choix)
        assert article["price"] == "9.50 EUR" and len(article["options"]) == 2
        r = await RC.chiffrer_panier(e.monde.c, e.monde.a, "emporter", [{"code_caisse": "P-TACOS-L", "quantite": 1, "choix": choix[:1]}])
        assert r.statut == "CHOIX_OBLIGATOIRE", r  # la taille L en exige deux : le quota de la déclinaison tient aussi à l'enregistrement

    async def test_dec2_fiche_du_modele(self, essai_de):
        assert await la_brique_change_la_fiche("DEC2", essai_de)


# --------------------------------------------------------------------------- #
# L08-16 et L08-17 : la taille collée au nom (B12, décision 2)
# --------------------------------------------------------------------------- #

CARTES_DE_DEMO = ["casa-italia", "etoile-d-or", "kebab-demo", "lusitalia"]


async def _lue(e, texte: str):
    from api.services.commande.briques.taille import lire_la_taille_collee_au_nom

    return await lire_la_taille_collee_au_nom(e.source, texte, "emporter")


async def test_taille_collee_lue(essai_de):
    """« reine normale » -> Regina, variante Normale ; « mega calzone » -> Calzone, Mega ; « menu kebab maxi » -> Menu kebab, Maxi, mot pour mot."""
    e = await essai_de("casa-italia")
    assert await _lue(e, "reine normale") == ("reine", "Normale")
    assert await _lue(e, "reines normales") == ("reines", "Normale")
    assert await _lue(e, "calzone mega") == ("calzone", "Mega")
    assert await _lue(e, "mega calzone") == ("calzone", "Mega")
    # par la fiche : le produit plus sa variante, jamais une question de taille de plus
    await e.tour("à emporter", mode_de_retrait="emporter")
    await e.tour("une reine normale", ajouter=[{"article": "reine normale", "quantite": 1}])
    assert [(l["nom"], l["quantite"]) for l in e.p["lignes"] if not l.get("attente")] == [("Regina Normale", 1)], e.retours[-1]
    k = await essai_de("kebab-demo")
    assert await _lue(k, "kebab maxi") == ("kebab", "Maxi")  # « menu kebab maxi » (formule) est la brique FOR du lot 11 : la carte 307b des menus y est jouée


async def test_vrai_nom_jamais_coupe(essai_de):
    """Aucun nom de produit des cartes de démo et des cartes de briques n'est coupé (« Petite salade verte » de Lusitalia compris)."""
    from pathlib import Path

    from api.tests.mark.banc_a.commun import CARTES, carte_de

    slugs = CARTES_DE_DEMO + [f"briques/{f.stem}" for f in sorted((CARTES / "briques").glob("*.json"))]
    coupes = []
    for slug in slugs:
        e = await essai_de(slug)
        for p in carte_de(slug)["produits"]:
            lu = await _lue(e, p["nom"])
            if lu is not None:
                coupes.append((slug, p["nom"], lu))
    assert not coupes, coupes
    assert "Petite salade verte" in {p["nom"] for p in carte_de("lusitalia")["produits"]}
    assert Path


async def test_taille_d_un_autre_produit_ignoree(essai_de):
    """Une taille que le produit n'a pas, ou « géante », ne change rien : le code redemande la taille."""
    e = await essai_de("casa-italia")
    assert await _lue(e, "regina géante") is None
    assert await _lue(e, "reine junior") is None
    assert await _lue(e, "reine verte") is None
    await e.tour("à emporter", mode_de_retrait="emporter")
    await e.tour("une reine géante", ajouter=[{"article": "reine géante", "quantite": 1}])
    assert not any(l["nom"].endswith("Normale") for l in e.p["lignes"]), e.retours[-1]


async def test_variante_de_la_fiche_jamais_remplacee(essai_de):
    """Une variante déjà dans la fiche n'est jamais remplacée par un mot du nom."""
    e = await essai_de("casa-italia")
    await e.tour("à emporter", mode_de_retrait="emporter")
    await e.tour("une reine normale en mega", ajouter=[{"article": "reine normale", "quantite": 1, "variante": "Mega"}])
    assert not any(l["nom"] == "Regina Normale" for l in e.p["lignes"]), e.retours[-1]


# --------------------------------------------------------------------------- #
# L08-20 et L08-21 : le registre des briques
# --------------------------------------------------------------------------- #


async def test_donnees_des_briques_dans_le_chargement(essai_de):
    """Chaque champ de carte qu'une brique déclare est dans la carte chargée au décroché (D61, point 1), et aucune fiche ne le relit à la base."""
    from api.db.bases_clients.instantane import Instantane
    from api.services.commande.briques import registre

    for code, brique in registre.BRIQUES.items():
        if not brique.champs_de_la_carte or not brique.carte_d_essai:
            continue
        e = await essai_de(brique.carte_d_essai)
        e.monde.c.instantane = Instantane(e.monde.a)
        await e.source.charger_pour_l_appel()
        carte = await restauration.carte_du_restaurant(e.monde.c, e.monde.a)
        for rubrique, champ in brique.champs_de_la_carte:
            # les déclinaisons sont dans leurs produits, les options dans leurs groupes (lot 10 : RET2, RET5 déclarent des champs d'option)
            lignes = ([d for p in carte["produits"] for d in p["declinaisons"]] if rubrique == "declinaisons"
                      else [o for g in carte["groupes"] for o in g["options"]] if rubrique == "options" else carte[rubrique])
            assert lignes and all(champ in l for l in lignes), (code, rubrique, champ)
        # chargée : relire l'article et la carte ne demande plus rien à la base pendant la fiche
        avant = []
        vrai = e.monde.c.fetch

        async def compte(*a, **k):
            avant.append(a[0][:60])
            return await vrai(*a, **k)

        e.monde.c.fetch = compte
        await restauration.carte_du_restaurant(e.monde.c, e.monde.a)
        assert not avant, (code, avant)


async def test_champ_declare_mais_non_charge_est_vu(essai_de):
    """Vu rouge (R7) : un champ déclaré qu'aucune lecture ne charge est refusé par la vérification."""
    from api.services.commande.briques import registre

    faux = registre.Brique("ZZZ0", "essai", champs_de_la_carte=(("declinaisons", "champ_qui_n_existe_pas"),), carte_d_essai="briques/ART1")
    e = await essai_de("briques/ART1")
    carte = await restauration.carte_du_restaurant(e.monde.c, e.monde.a)
    lignes = [d for p in carte["produits"] for d in p["declinaisons"]]
    assert not all(faux.champs_de_la_carte[0][1] in l for l in lignes)


async def test_chaque_brique_declare_le_changement_de_fiche(essai_de):
    """Chaque entrée du registre porte ``change_la_fiche_du_modele`` et ``vue_sur_carte`` ; le rendu de la fiche avec et sans la carte de la brique confirme la déclaration (D66)."""
    from api.services.commande.briques import registre

    fautes = []
    for code, brique in registre.BRIQUES.items():
        if brique.change_la_fiche_du_modele is None or brique.vue_sur_carte is None:
            fautes.append((code, "sans déclaration"))
            continue
        if not brique.carte_d_essai:
            continue
        rendu = await la_brique_change_la_fiche(code, essai_de)
        if rendu != brique.change_la_fiche_du_modele:
            fautes.append((code, f"déclarée {brique.change_la_fiche_du_modele}, rendu {rendu}"))
    assert not fautes, fautes


def test_une_brique_sans_declaration_est_vue():
    """Vu rouge (R7) : une entrée sans déclaration est refusée par la vérification (``None`` n'est ni oui ni non)."""
    from api.services.commande.briques import registre

    sans = registre.Brique("ZZZ1", "essai")
    assert sans.change_la_fiche_du_modele is None and sans.vue_sur_carte is None
    with pytest.raises(ValueError):
        registre.enregistrer(registre.BRIQUES["ART1"])  # un code en double est refusé


# --------------------------------------------------------------------------- #
# L08-01 et L08-02 : une règle inconnue ne bloque jamais (E29) : note de ligne, signalement, route
# --------------------------------------------------------------------------- #


async def test_regle_inconnue_en_note(essai_de):
    """Une règle que la carte ne sait pas exprimer : la ligne reste vendable et porte la note ; le signalement est écrit une seule fois par produit et par texte."""
    from api.db.bases_clients import restauration_signalement_carte as SC
    from api.services.commande.briques.inconnue import regle_inconnue_en_note

    ligne = {"nom": "Tiramisu", "note": None}
    regle_inconnue_en_note(ligne, "  gratuit le mardi  ", True)
    regle_inconnue_en_note(ligne, "gratuit le mardi", True)  # rejouée : rien de plus
    assert ligne == {"nom": "Tiramisu", "note": "gratuit le mardi", "regles_inconnues": ["gratuit le mardi"]}
    sans_note = {"nom": "Tiramisu", "note": None}
    regle_inconnue_en_note(sans_note, "gratuit le mardi", notes_libres=False)
    assert sans_note["note"] is None and sans_note["regles_inconnues"] == ["gratuit le mardi"]  # signalée même quand les notes libres ne sont pas permises
    e = await essai_de("briques/ART1")
    assert await e.source.signaler_une_regle_inconnue("P-TIRAMISU", "gratuit le mardi") is True
    assert await e.source.signaler_une_regle_inconnue("P-TIRAMISU", "gratuit le mardi") is False  # sans effet double
    assert await e.source.signaler_une_regle_inconnue("P-TIRAMISU", "  ") is False
    page = await SC.signalements_de_la_carte(e.monde.c, e.monde.a)
    assert [(s["produit"], s["texte"]) for s in page["signalements"]] == [("P-TIRAMISU", "gratuit le mardi")] and page["suivant"] is None


async def test_route_signalements_de_carte(db_session, seconde_base, sans_preparation_des_organisations):  # noqa: F811
    """La vraie route : 401 sans clé ; les signalements de l'établissement de la clé, paginés ; 404 pour l'établissement d'une autre organisation ; rien ne fuit entre bases."""
    from api.db.bases_clients import connexion as schema
    from api.db.bases_clients import restauration_signalement_carte as SC
    from api.tests.mark.equipe_commun import client_http
    from api.tests.mark.test_contacts_portail import _cle
    from api.tests.mark.test_restauration_flux import _deux_organisations_avec_des_etablissements

    racine = "/api/v1/restauration/etablissements"
    cas = await _deux_organisations_avec_des_etablissements(db_session, seconde_base)
    a, b = cas.sites_a[0], cas.sites_b[0]
    for base, site, textes in ((cas.base_a, a, ["règle A1", "règle A2", "règle A3"]), (cas.base_b, b, ["règle B1"])):
        c = await schema.connecter(base)
        try:
            for t in textes:
                assert await SC.signaler_une_regle_inconnue(c, site, "P-1", t)
        finally:
            await c.close()
    async with client_http() as c:
        assert (await c.get(f"{racine}/{a}/signalements-de-carte")).status_code == 401
        r = await c.get(f"{racine}/{a}/signalements-de-carte?limite=2", headers=_cle(cas.cle_a))
        assert r.status_code == 200, r.text
        page = r.json()
        assert [s["texte"] for s in page["signalements"]] == ["règle A3", "règle A2"] and page["suivant"] is not None
        suite = (await c.get(f"{racine}/{a}/signalements-de-carte?limite=2&avant={page['suivant']}", headers=_cle(cas.cle_a))).json()
        assert [s["texte"] for s in suite["signalements"]] == ["règle A1"] and suite["suivant"] is None
        chez_b = max(cas.sites_a + cas.sites_b) + 1000
        for etab in (chez_b, 999_999_999):
            assert (await c.get(f"{racine}/{etab}/signalements-de-carte", headers=_cle(cas.cle_a))).status_code == 404
        assert (await c.get(f"{racine}/{a}/signalements-de-carte?limite=0", headers=_cle(cas.cle_a))).status_code == 422
        # la clé de B ne lit que sa base : « règle A1 » n'y est jamais
        propres = (await c.get(f"{racine}/{b}/signalements-de-carte", headers=_cle(cas.cle_b))).json()
        assert [s["texte"] for s in propres["signalements"]] == ["règle B1"]


async def test_lire_la_carte_sans_article_rend_un_fait_lisible(essai_de):
    """Conversation ART3 (19/11) : la liste fermée de ``lire`` offre ``carte`` ; sans article, le code l'honore (les rubriques de la carte et le texte du jour tel quel), jamais une erreur.
    Sans texte du jour, la lecture le dit et rien n'est inventé."""
    e = await brique(essai_de, "ART3")
    r = await e.lecture(sujet="carte")
    assert "ARGUMENT_INVALIDE" not in fait(r) and r["statut"] == "LU", r
    rubriques = r["faits"]["rubriques"]
    assert rubriques and all(x["nom"] and x["articles"] for x in rubriques), rubriques
    assert sorted(a for x in rubriques for a in x["articles"]) == ["Dessert du moment", "Plat du jour", "Soupe"], rubriques
    assert "du_moment" not in r["faits"] and "gratin" not in fait(r), r  # aucun texte saisi : le produit n'est pas « du moment », rien n'est inventé
    assert await restauration_ecran.poser_le_produit_du_moment(e.monde.c, e.monde.a, "P-PLAT-DU-JOUR", "  gratin de courgettes   et riz ", "essai")
    e.source.c.instantane = None  # un nouvel appel (D61, point 3)
    r = await e.lecture(sujet="carte")
    assert {"article": "Plat du jour", "renseigne": True, "texte_du_jour": "gratin de courgettes et riz"} in r["faits"]["du_moment"], r
    # une carte sans produit du moment : aucun fait du moment
    e2 = await brique(essai_de, "ART1")
    assert "du_moment" not in (await e2.lecture(sujet="carte"))["faits"]


async def test_un_mot_inconnu_dit_ce_que_l_article_propose(essai_de):
    """Conversation DEC4-B (19/11) : « une margherita base crème » : le refus donne au modèle les choix de la margherita (ses sauces), pas seulement qu'elle n'a pas la crème ; lot 7b (Q1) : le code ne les dit plus."""
    e = await brique(essai_de, "DEC4")
    r = await e.tour("une margherita base crème", ajouter=[{"article": "margherita", "quantite": 1, "supplements": ["crème"]}])
    refus = [x for x in r["resultats"] if x["statut_du_module"] == "HORS_CARTE"][0]
    from api.services.commande.porte import CLE_TEXTES_DU_CODE

    assert not e.fiche_de_l_appel[CLE_TEXTES_DU_CODE].get("prefixe"), "le code ne dit rien avant la phrase du modèle"
    dit = json.dumps((r.get("faits") or {}).get("refus_de_la_fiche"), ensure_ascii=False)
    assert "Ketchup" in dit and "Samouraï" in dit and "crème" in dit, (dit, refus)

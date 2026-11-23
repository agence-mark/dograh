"""[.mark] Chantier Partie 1, lot 13 : les briques quantité et unité (``services/commande/briques/qte*.py``).

Une classe par brique (``TestQTE1`` à ``TestQTE3``), chacune avec sa règle, son aller-retour en caisse et son test de rendu de la fiche (D66) ; plus la migration 043 en ajout
(``poids_g``, la quantité entière ne change pas, D55) et la preuve qu'une ligne sans poids se chiffre et part à la caisse comme avant. Un test = un essai à la fois.
"""

from __future__ import annotations
import pytest


from api.db.bases_clients import restauration_commande as RC
from api.services.commande import porte
from api.services.restauration.prises.hubrise_traduction import carte_de_hubrise, carte_vers_hubrise, centimes, commande_vers_hubrise
from api.tests.mark.banc_a.commun import carte_de
from api.tests.mark.partie_1.aides_briques import brique, descendre_jusqu_a, fait, la_brique_change_la_fiche
from api.tests.mark.test_base_client import base_essai  # noqa: F401


async def _ajouter(e, parole: str, **article):
    return await e.tour(parole, ajouter=[article])


async def _objets_charges(e) -> None:
    """Les objets de la carte tels que le chargement de l'appel les calcule (lot 5) : la sous-case ``poids`` n'existe que si la carte vend au poids."""
    from api.services.commande import contrat

    _, objets = await e.source.charger_pour_l_appel()
    e.fiche_de_l_appel[contrat.CLE_DES_OBJETS] = objets
    assert objets["poids"] is True


def _suffixe(e) -> str | None:
    return (e.fiche_de_l_appel.get(porte.CLE_TEXTES_DU_CODE) or {}).get("suffixe")


def _corps(lignes: list[dict]) -> dict:
    return commande_vers_hubrise({"numero": "n-1", "mode": "emporter", "client": {}, "lignes": lignes})


def _total_hubrise(corps: dict) -> int:
    """Ce que HubRise recalcule : prix × quantité de chaque article (la quantité peut être décimale), plus ses options."""
    from decimal import Decimal

    total = Decimal(0)
    for a in corps["items"]:
        total += (Decimal(centimes(a["price"])) + sum(centimes(o["price"]) * int(o.get("quantity", 1)) for o in a.get("options") or [])) * Decimal(a["quantity"])
    return int(total)


# --------------------------------------------------------------------------- #
# L13-05, L13-06 : la migration 043 en ajout, la quantité entière inchangée (D55)
# --------------------------------------------------------------------------- #

COLONNES_043 = [("resto_commande_ligne", "poids_g")] + [("resto_produit", c) for c in ("unite", "prix_par_unite", "arrondi", "lot_de_vente")]


async def test_migration_043_poids_g_montee_descente(base_prete):
    """Montée, descente, remontée ; la colonne ``quantite`` reste un entier ; une ligne entière existante est la même avant et après (même quantité, ``poids_g`` vide)."""
    from api.db.bases_clients import connexion as schema

    async def presentes(c) -> list[bool]:
        return [bool(await c.fetchval("SELECT 1 FROM information_schema.columns WHERE table_schema='mark' AND table_name=$1 AND column_name=$2", t, col)) for t, col in COLONNES_043]

    c = await schema.connecter_proprietaire(base_prete)
    try:
        assert all(await presentes(c))
        assert await c.fetchval("SELECT data_type FROM information_schema.columns WHERE table_schema='mark' AND table_name='resto_commande_ligne' AND column_name='quantite'") == "integer"
        for _ in range(2):
            await descendre_jusqu_a(c, 43)
            assert not any(await presentes(c)) and 43 not in [r["version"] for r in await c.fetch("SELECT version FROM mark.schema_version")]
            assert await c.fetchval("SELECT data_type FROM information_schema.columns WHERE table_schema='mark' AND table_name='resto_commande_ligne' AND column_name='quantite'") == "integer"
            assert 43 in await schema.appliquer_migrations(c)
            assert all(await presentes(c))
    finally:
        await c.close()


async def test_quantite_entiere_inchangee(essai_de):
    """Une ligne sans poids se chiffre et part à la caisse comme avant le lot : quantité entière, prix inchangé, ``poids_g`` vide, aucune quantité décimale."""
    e = await brique(essai_de, "QTE1")
    r = await RC.chiffrer_panier(e.monde.c, e.monde.a, "emporter", [{"code_caisse": "P-PITA-UNIQUE", "quantite": 2, "choix": []}])
    ligne = r.faits["lignes"][0]
    assert r.statut == "OK" and ligne["prix_unitaire"] == 150 and ligne["quantite"] == 2 and ligne["poids_g"] is None
    article = _corps(r.faits["lignes"])["items"][0]
    assert article["price"] == "1.50 EUR" and article["quantity"] == "2" and article["product_name"] == "Pita"


async def test_le_poids_s_enregistre_et_se_relit(essai_de):
    """La commande enregistrée garde ``poids_g`` sur sa ligne (le poids d'une portion) et sa quantité entière."""
    e = await brique(essai_de, "QTE1")
    brouillon = {"mode": "emporter", "client": {"telephone": "+33600000001"}, "lignes": [{"code_caisse": "P-HOUMOUS-UNIQUE", "quantite": 1, "poids_g": 300}],
                 "paiement": {"moyens": [{"moyen": "carte", "montant": 540}], "reste_par_moyen": {}}}
    r = await RC.enregistrer_commande(e.monde.c, e.monde.a, brouillon, "jeton")
    assert r.statut == "ENREGISTREE" and r.faits["total"] == 540, r
    ligne = await e.monde.c.fetchrow("SELECT quantite, poids_g, prix_unitaire FROM mark.resto_commande_ligne WHERE site_id = $1", e.monde.a)
    assert (ligne["quantite"], ligne["poids_g"], ligne["prix_unitaire"]) == (1, 300, 540)


# --------------------------------------------------------------------------- #
# L13-02 : QTE1, le produit au poids
# --------------------------------------------------------------------------- #


class TestQTE1:
    def test_qte1_lire_le_poids(self):
        """Les formes de la fiche et du banc : mots, chiffres, kilo, demi-kilo, virgule ; sans unité (« deux cents »), rien n'est deviné."""
        from api.services.commande.briques.produit_au_poids import lire_poids

        assert lire_poids("trois cents grammes") == 300 and lire_poids("300 g") == 300 and lire_poids("un demi-kilo") == 500
        assert lire_poids("1,2 kg") == 1200 and lire_poids("quatre-vingts grammes") == 80 and lire_poids("deux cent cinquante grammes") == 250 and lire_poids("un kilo") == 1000
        assert lire_poids("deux cents") is None and lire_poids("") is None and lire_poids("beaucoup") is None

    async def test_qte1_chiffrer_au_poids(self, essai_de):
        """« Trois cents grammes de houmous » (A33) : 1,8 € les cent grammes au kilo, soit 5,40 € ; le code dit le prix ; un demi-kilo : 9 € ; la quantité reste 1."""
        e = await brique(essai_de, "QTE1")
        await _objets_charges(e)
        r = await _ajouter(e, "trois cents grammes de houmous", article="houmous", quantite=1, poids="trois cents grammes")
        ligne = e.p["lignes"][-1]
        assert ligne["poids_g"] == 300 and ligne["quantite"] == 1, fait(r)
        assert '"grammes": 300' in fait(r) and "prix_a_dire" not in fait(r) and r["prix_dit_par_le_code_apres_ta_phrase"] is True
        assert _suffixe(e) == "trois cents grammes de houmous : cinq euros quarante.", _suffixe(e)
        chiffre = await RC.chiffrer_panier(e.monde.c, e.monde.a, "emporter", [{"code_caisse": "P-HOUMOUS-UNIQUE", "quantite": 1, "poids_g": 300}])
        assert chiffre.faits["lignes"][0]["prix_unitaire"] == 540
        r = await _ajouter(e, "un demi-kilo de houmous", article="houmous", quantite=1, poids="un demi-kilo")
        assert e.p["lignes"][-1]["poids_g"] == 500 and len(e.p["lignes"]) == 2, fait(r)  # un autre poids est une autre ligne

    async def test_qte1_arrondi_dit(self, essai_de):
        """Le taboulé se vend au pas de 50 g : 230 g deviennent 250 g, et le retour le dit (``arrondi_a``) ; jamais en silence."""
        e = await brique(essai_de, "QTE1")
        await _objets_charges(e)
        r = await _ajouter(e, "deux cent trente grammes de taboulé", article="taboulé", quantite=1, poids="deux cent trente grammes")
        assert e.p["lignes"][-1]["poids_g"] == 250 and '"arrondi_a": 250' in fait(r), fait(r)
        assert _suffixe(e) == "Arrondi à deux cent cinquante grammes de taboulé : six euros vingt-cinq.", _suffixe(e)

    async def test_qte1_refus_avec_la_raison(self, essai_de):
        """« Deux cents » sans unité, un poids sur un article à la pièce, un article au poids sans poids : refusés avec leur raison, jamais devinés."""
        e = await brique(essai_de, "QTE1")
        await _objets_charges(e)
        r = await _ajouter(e, "deux cents de houmous", article="houmous", quantite=1, poids="deux cents")
        assert "poids_illisible" in fait(r) and not e.p["lignes"], fait(r)
        r = await _ajouter(e, "trois cents grammes de pita", article="pita", quantite=1, poids="trois cents grammes")
        assert "pas_vendu_au_poids" in fait(r) and not e.p["lignes"], fait(r)
        r = await _ajouter(e, "du houmous", article="houmous", quantite=1)
        assert "poids_a_dire" in fait(r) and not e.p["lignes"], fait(r)

    async def test_qte1_aller_retour_caisse(self, essai_de):
        """300 g à 18 € le kilo : l'article part à 18 € avec la quantité 0.300 (HubRise multiplie, 5,40 €) ; 333 g à 25 € le kilo (non exact) : quantité 1 au total, le poids dans le nom ;
        la carte voyage par son étiquette."""
        e = await brique(essai_de, "QTE1")
        r = await RC.chiffrer_panier(e.monde.c, e.monde.a, "emporter", [{"code_caisse": "P-HOUMOUS-UNIQUE", "quantite": 1, "poids_g": 300}])
        corps = _corps(r.faits["lignes"])
        assert corps["items"][0]["price"] == "18.00 EUR" and corps["items"][0]["quantity"] == "0.300" and _total_hubrise(corps) == 540
        r = await RC.chiffrer_panier(e.monde.c, e.monde.a, "emporter", [{"code_caisse": "P-TABOULE-UNIQUE", "quantite": 1, "poids_g": 333}])
        corps = _corps(r.faits["lignes"])
        assert corps["items"][0]["quantity"] == "1" and corps["items"][0]["product_name"] == "Taboulé 333 g" and _total_hubrise(corps) == r.faits["lignes"][0]["prix_unitaire"] == 833
        relue = carte_de_hubrise(carte_vers_hubrise(carte_de("briques/QTE1")).donnees).carte
        houmous = next(p for p in relue["produits"] if p["id"] == "P-HOUMOUS")
        assert (houmous["unite"], houmous["prix_par_unite"]) == ("kg", 1800) and next(p for p in relue["produits"] if p["id"] == "P-TABOULE")["arrondi"] == 50

    async def test_qte1_fiche_du_modele(self, essai_de):
        assert await la_brique_change_la_fiche("QTE1", essai_de)


# --------------------------------------------------------------------------- #
# L13-03 : QTE2, le lot de vente
# --------------------------------------------------------------------------- #


class TestQTE2:
    def test_qte2_les_multiples_voisins(self):
        from api.services.commande.briques.lot_de_vente import brique_qte2_multiple_du_lot as regle, multiples_voisins

        assert multiples_voisins(6, 4) == [6, 12] and multiples_voisins(6, 7) == [6, 12] and multiples_voisins(6, 13) == [12, 18] and multiples_voisins(12, 1) == [12, 24]
        assert regle({"nom": "Maki", "lot_de_vente": 6}, 12) == {"lots": 2, "pieces": 12}
        assert regle({"nom": "Maki"}, 4) == {}

    async def test_qte2_multiple_du_lot(self, essai_de):
        """« Quatre maki » sur un lot de 6 : refus avec 6 ou 12 en choix (A20) ; « douze » : deux lots au prix de deux lots ; la soupe (sans lot) est inchangée."""
        e = await brique(essai_de, "QTE2")
        r = await _ajouter(e, "quatre maki", article="maki", quantite=4)
        assert "multiple_du_lot" in fait(r) and '"choix": [6, 12]' in fait(r) and not e.p["lignes"], fait(r)
        r = await _ajouter(e, "douze maki", article="maki", quantite=12)
        ligne = e.p["lignes"][-1]
        assert ligne["quantite"] == 2 and '"lots": 2' in fait(r) and '"pieces": 12' in fait(r), fait(r)
        chiffre = await RC.chiffrer_panier(e.monde.c, e.monde.a, "emporter", [{"code_caisse": ligne["code"], "quantite": ligne["quantite"], "choix": []}])
        assert chiffre.faits["sous_total"] == 1200
        await _ajouter(e, "une soupe", article="soupe miso", quantite=3)
        assert any(l["nom"] == "Soupe miso" and l["quantite"] == 3 for l in e.p["lignes"])

    async def test_qte2_aller_retour_caisse(self, essai_de):
        """La ligne part en nombre de lots (le code de caisse est celui du lot) : deux lots de 6 à 6 € ; la donnée voyage par l'étiquette."""
        e = await brique(essai_de, "QTE2")
        r = await RC.chiffrer_panier(e.monde.c, e.monde.a, "emporter", [{"code_caisse": "P-MAKI-UNIQUE", "quantite": 2, "choix": []}])
        article = _corps(r.faits["lignes"])["items"][0]
        assert article["price"] == "6.00 EUR" and article["quantity"] == "2" and article["sku_ref"] == "P-MAKI-UNIQUE"
        relue = carte_de_hubrise(carte_vers_hubrise(carte_de("briques/QTE2")).donnees).carte
        assert next(p for p in relue["produits"] if p["id"] == "P-MAKI")["lot_de_vente"] == 6

    async def test_qte2_fiche_du_modele(self, essai_de):
        assert await la_brique_change_la_fiche("QTE2", essai_de)


# --------------------------------------------------------------------------- #
# L13-04, L13-08 : QTE3, la quantité par option (brique déjà prise : le test la prouve)
# --------------------------------------------------------------------------- #


class TestQTE3:
    async def test_qte3_compter_par_option(self, essai_de):
        """Jusqu'à deux algériennes (le maximum par option du groupe), pas trois : refus avec la raison ; le chiffrage compte la quantité de chaque option."""
        e = await brique(essai_de, "QTE3")
        deux = await RC.chiffrer_panier(e.monde.c, e.monde.a, "emporter", [{"code_caisse": "P-TACOS-UNIQUE", "quantite": 1, "choix": [{"option_code": "G-SAUCES-ALGÉRIENNE", "quantite": 2}]}])
        assert deux.statut == "OK" and deux.faits["lignes"][0]["choix"][0]["quantite"] == 2
        trois = await RC.chiffrer_panier(e.monde.c, e.monde.a, "emporter", [{"code_caisse": "P-TACOS-UNIQUE", "quantite": 1, "choix": [{"option_code": "G-SAUCES-ALGÉRIENNE", "quantite": 3}]}])
        assert trois.statut == "MAXIMUM_ATTEINT", trois

    async def test_qte3_aller_retour_caisse(self, essai_de):
        """La quantité de l'option part à la caisse, UN OBJET PAR UNITÉ (lot 19 bis, N2 : le guide d'intégration le préfère à ``quantity``) et la somme reste la nôtre."""
        e = await brique(essai_de, "QTE3")
        r = await RC.chiffrer_panier(e.monde.c, e.monde.a, "emporter", [{"code_caisse": "P-TACOS-UNIQUE", "quantite": 1, "choix": [{"option_code": "G-SAUCES-ALGÉRIENNE", "quantite": 2}]}])
        article = _corps(r.faits["lignes"])["items"][0]
        assert len(article["options"]) == 2 and all("quantity" not in o for o in article["options"]) and _total_hubrise(_corps(r.faits["lignes"])) == 700

    async def test_qte3_la_regle_se_voit_rouge(self):
        """R7 : la fonction nommée refuse au-delà du maximum et accepte jusqu'à lui."""
        from api.services.commande.briques.quantite_par_option import brique_qte3_compter_par_option as regle

        assert regle({"max_par_option": 2}, 2) is True and regle({"max_par_option": 2}, 3) is False and regle({}, 2) is False


async def test_briques_jamais_vues_sans_case_nouvelle(essai_de):
    """L13-08 : QTE3 ne change pas la fiche du modèle ; la déclaration du registre le dit."""
    from api.services.commande.briques import registre

    b = registre.BRIQUES["QTE3"]
    assert b.change_la_fiche_du_modele is False and b.vue_sur_carte is False
    assert not await la_brique_change_la_fiche("QTE3", essai_de)


@pytest.mark.parametrize("dit", ["coca 1,5 litre", "coca-cola 1,5 litres", "coca 1.5 l"])
async def test_la_taille_dite_en_lettres_comme_l_agent_la_dit(essai_de, dit):
    """Lot 19, D21 : l'agent propose « 33 centilitres, 1,5 litre ou 2 litres » ; le modèle qui recopie « 1,5 litre » retrouve la taille « 1,5 l » de la carte
    (même norme que la recherche, ``norme_de_recherche``), au lieu de reposer la même question."""
    e = await essai_de("kebab-demo")
    await e.tour(dit, ajouter=[{"article": dit, "quantite": 1}], mode_de_retrait="emporter")
    assert [l.get("code") for l in e.p["lignes"]] == ["BOIS-COCA-COLA-1-5-L"], (e.p["lignes"], e.p.get("question"))

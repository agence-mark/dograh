"""[.mark] Chantier Partie 1, lot 12 : les briques prix et conditions (``services/commande/briques/prx*.py``).

Une classe par brique (``TestPRX1`` ... ``TestPRX9``), chacune avec sa règle, son aller-retour en caisse et son test de rendu de la fiche (D66) ; plus la migration 042, l'alcool du
format commun importé et la quantité maximale lue dans la donnée. Un test = un essai à la fois.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest

from api.db.bases_clients import restauration
from api.db.bases_clients import restauration_commande as RC
from api.services.commande.briques.prx5 import brique_prx5_jamais_le_prix_de_depart_comme_final as brique_prx5
from api.services.commande.briques.prx9 import brique_prx9_date_la_plus_proche as brique_prx9
from api.services.restauration.prises.hubrise_traduction import carte_de_hubrise, carte_vers_hubrise, commande_vers_hubrise
from api.tests.mark.banc_a.commun import carte_de
from api.tests.mark.partie_1.aides_briques import article_en_caisse, brique, descendre_jusqu_a, fait, la_brique_change_la_fiche
from api.tests.mark.test_base_client import base_essai  # noqa: F401
from api.tests.mark.test_restauration_classeur_carte import PARIS

REPONSES = Path(__file__).resolve().parent.parent / "reponses_hubrise"


async def _ajouter(e, parole: str, **article):
    return await e.tour(parole, ajouter=[article])


# --------------------------------------------------------------------------- #
# L12-01 : la migration 042
# --------------------------------------------------------------------------- #

COLONNES_042 = [("resto_produit", c) for c in ("disponibilite", "modes", "alcool", "degre", "frais", "max_par_commande", "delai_minimal_heures", "personnes_min")] + [
    ("resto_categorie", "disponibilite"), ("resto_option", "disponibilite"), ("resto_option", "modes"), ("resto_option", "prix_par_mode")]


async def test_migration_042_montee_descente(base_prete):
    from api.db.bases_clients import connexion as schema

    async def presentes(c, colonnes) -> list[bool]:
        return [bool(await c.fetchval("SELECT 1 FROM information_schema.columns WHERE table_schema='mark' AND table_name=$1 AND column_name=$2", t, col)) for t, col in colonnes]

    c = await schema.connecter_proprietaire(base_prete)
    try:
        assert all(await presentes(c, COLONNES_042))
        for _ in range(2):  # descente, remontée, deux fois (rejouable)
            await descendre_jusqu_a(c, 42)
            assert not any(await presentes(c, COLONNES_042)) and 42 not in [r["version"] for r in await c.fetch("SELECT version FROM mark.schema_version")]
            assert await presentes(c, [("resto_formule", "modes")]) == [True]  # le mode de la formule appartient à la 040
            assert 42 in await schema.appliquer_migrations(c)
            assert all(await presentes(c, COLONNES_042))
    finally:
        await c.close()


async def test_les_conditions_de_vente_sont_importees_et_chargees(essai_de):
    """Le format commun porte les conditions ; l'import les écrit, la carte chargée les rend (D61 point 1), ``None`` = non dit."""
    e = await essai_de("briques/PRX1")
    carte = await restauration.carte_du_restaurant(e.monde.c, e.monde.a)
    salade = next(p for p in carte["produits"] if p["id"] == "P-SALADE")
    assert salade["disponibilite"]["jours"] == [1, 2, 3, 4, 5] and salade["modes"] is None and salade["max_par_commande"] is None
    assert next(c for c in carte["categories"] if c["id"] == "petitdej")["disponibilite"] == {"heures": [["07:00", "11:00"]]}
    truffe = next(o for g in carte["groupes"] for o in g["options"] if o["nom"] == "Truffe")
    assert truffe["disponibilite"] == {"jours": [6, 7]} and truffe["modes"] is None and truffe["prix_par_mode"] is None


# --------------------------------------------------------------------------- #
# L12-02 et L12-09 : l'alcool dans le format commun, PRX6
# --------------------------------------------------------------------------- #


async def test_alcool_dans_le_format_importe(essai_de):
    """L'alcool et le degré du format commun sont importés ; l'alcool écrit à l'écran (surcouche) s'y ajoute, jamais effacé par un réimport."""
    e = await essai_de("briques/PRX6")
    carte = await restauration.carte_du_restaurant(e.monde.c, e.monde.a)
    cidre = next(p for p in carte["produits"] if p["id"] == "P-CIDRE")
    assert cidre["alcool"] is True and cidre["degre"] == 5.0
    galette = next(p for p in carte["produits"] if p["id"] == "P-GALETTE")
    assert galette["alcool"] is False and galette["degre"] is None
    await e.monde.c.execute("INSERT INTO mark.resto_surcouche (site_id, objet, ref, alcool) VALUES ($1, 'produit', 'P-GALETTE', true)", e.monde.a)
    from api.db.bases_clients.restauration_carte import importer_carte

    await importer_carte(e.monde.c, e.monde.a, carte_de("briques/PRX6"), "caisse")  # le réimport de la carte
    carte = await restauration.carte_du_restaurant(e.monde.c, e.monde.a)
    assert next(p for p in carte["produits"] if p["id"] == "P-GALETTE")["alcool"] is True  # la surcouche d'une personne reste


class TestPRX6:
    async def test_prx6_regle_d_age_dite(self, essai_de):
        """« Un verre de cidre » : le fait ``alcool`` est rendu (la règle d'âge est dite à la remise, jamais vérifiée) ; une galette n'en rend aucun ; le titre-restaurant ne le paie pas."""
        e = await brique(essai_de, "PRX6")
        r = await _ajouter(e, "un verre de cidre", article="verre de cidre", quantite=1)
        faits = r["resultats"][0]["faits"] if r.get("resultats") and "faits" in r["resultats"][0] else None
        assert '"alcool": true' in fait(r) and '"degre": 5.0' in fait(r), fait(r)
        assert e.p["lignes"][-1]["nom"] == "Verre de cidre"
        e2 = await brique(essai_de, "PRX6")
        r = await _ajouter(e2, "une galette", article="galette", quantite=1)
        assert '"alcool"' not in fait(r), fait(r)
        c = await RC.chiffrer_panier(e.monde.c, e.monde.a, "emporter", [{"code_caisse": "P-CIDRE-UNIQUE", "quantite": 1, "choix": []}])
        assert c.faits["lignes"][0]["alcool"] is True  # la ligne porte l'alcool : le titre-restaurant ne le paie pas (règle du module, inchangée)

    async def test_prx6_aller_retour_caisse(self, essai_de):
        """Le catalogue HubRise (``nutrition.alcohol_percentage``, documentation catalog-management) donne l'alcool et le degré ; la carte les réécrit à l'identique."""
        catalogue = json.loads((REPONSES / "50-catalogue-conditions-de-vente.json").read_text(encoding="utf-8"))
        relue = carte_de_hubrise(catalogue).carte
        cidre = next(p for p in relue["produits"] if p["id"] == "P-CIDRE")
        assert cidre["alcool"] is True and cidre["degre"] == 5.0
        ecrite = carte_vers_hubrise(relue).donnees
        assert next(p for p in ecrite["products"] if p["ref"] == "P-CIDRE")["nutrition"] == {"alcohol_percentage": "5.0"}
        assert not next(p for p in relue["produits"] if p["id"] == "P-JUS").get("alcool")

    async def test_prx6_fiche_du_modele(self, essai_de):
        assert not await la_brique_change_la_fiche("PRX6", essai_de)


# --------------------------------------------------------------------------- #
# L12-04 : PRX1, la disponibilité par jour et heure
# --------------------------------------------------------------------------- #


def _plage(r: dict) -> dict:
    """La plage rendue par un refus ``indisponible_a_ce_moment`` (dans les faits du premier résultat refusé)."""
    texte = fait(r)
    assert "indisponible_a_ce_moment" in texte, texte
    return next(x for x in _faits_des_refus(r) if x.get("raison") == "indisponible_a_ce_moment")["plage"]


def _faits_des_refus(r: dict) -> list[dict]:
    sortie = []

    def parcourir(x):
        if isinstance(x, dict):
            if "raison" in x and "plage" in x:
                sortie.append(x)
            for v in x.values():
                parcourir(v)
        elif isinstance(x, list):
            for v in x:
                parcourir(v)

    parcourir(r)
    return sortie


class TestPRX1:
    async def test_prx1_servi_a_l_instant(self, essai_de):
        """Jeudi midi : la salade du midi se sert ; le brunch (samedi et dimanche), le croissant (rubrique du petit déjeuner) et l'option truffe (samedi et dimanche) sont refusés avec leur plage."""
        e = await brique(essai_de, "PRX1")
        r = await _ajouter(e, "une salade du midi", article="salade du midi", quantite=1)
        assert any(l["nom"] == "Salade du midi" for l in e.p["lignes"]), fait(r)
        r = await _ajouter(e, "un brunch", article="brunch", quantite=1)
        assert _plage(r) == {"jours": [6, 7], "heures": [["11:00", "15:00"]]} and not any(l["nom"] == "Brunch" for l in e.p["lignes"])
        r = await _ajouter(e, "un croissant", article="croissant", quantite=1)
        assert _plage(r) == {"heures": [["07:00", "11:00"]]}
        r = await _ajouter(e, "un burger sauce truffe", article="burger", quantite=1, composition=["truffe"])
        assert _plage(r) == {"jours": [6, 7]} and not any(l["nom"] == "Burger" for l in e.p["lignes"]), fait(r)

    async def test_prx1_formule_du_midi_a_19_h(self, essai_de):
        """« La formule du midi » pour ce soir à 19 h : refus avec la plage (A29) ; la plage est celle de la donnée, jamais une phrase."""
        e = await brique(essai_de, "PRX1")
        r = await e.tour("pour ce soir à 19 h", heure="ce soir à 19 h")
        assert str(e.p.get("heure_voulue") or "").startswith("2026-11-12T19:00"), (e.p.get("heure_voulue"), fait(r))
        r = await _ajouter(e, "la formule midi avec un burger", article="formule midi", quantite=1, composition=["burger"])
        assert _plage(r) == {"jours": [1, 2, 3, 4, 5], "heures": [["11:30", "14:30"]]} and not e.p["lignes"], fait(r)

    async def test_prx1_precommande_pour_demain_midi(self, essai_de):
        """La même formule, pour demain midi (vendredi) : acceptée, car la carte se lit à l'heure voulue, pas à l'instant de l'appel."""
        e = await brique(essai_de, "PRX1")
        await e.tour("pour demain midi", heure="demain midi")
        assert str(e.p.get("heure_voulue") or "").startswith("2026-11-13T12:00"), e.p.get("heure_voulue")
        r = await _ajouter(e, "la formule midi avec un burger", article="formule midi", quantite=1, composition=["burger"])
        assert e.p["lignes"] and e.p["lignes"][-1].get("formule_id") == "F-MIDI", fait(r)

    async def test_prx1_la_regle_se_voit_rouge(self):
        """R7 : une plage inversée est refusée à midi, donc la fonction refuse bien ce qu'elle doit refuser (le test n'est pas vert par construction)."""
        from datetime import datetime
        from zoneinfo import ZoneInfo

        from api.services.commande.briques.prx1 import brique_prx1_servi_a_l_instant

        midi = datetime(2026, 11, 12, 12, 0, tzinfo=ZoneInfo("Europe/Paris"))
        assert brique_prx1_servi_a_l_instant({"disponibilite": {"heures": [["11:30", "14:30"]]}}, midi) is None
        assert brique_prx1_servi_a_l_instant({"disponibilite": {"heures": [["14:30", "18:00"]]}}, midi) == {"heures": [["14:30", "18:00"]]}
        assert brique_prx1_servi_a_l_instant({"disponibilite": {"jours": [6, 7]}}, midi) == {"jours": [6, 7]}
        assert brique_prx1_servi_a_l_instant({"disponibilite": None}, midi) is None

    async def test_prx1_aller_retour_caisse(self, essai_de):
        """Le catalogue HubRise (``restrictions`` : ``dow``, ``start_time``, ``end_time``, documentation) donne la plage de la déclinaison ; la carte la réécrit à l'identique."""
        catalogue = json.loads((REPONSES / "50-catalogue-conditions-de-vente.json").read_text(encoding="utf-8"))
        relue = carte_de_hubrise(catalogue).carte
        brunch = next(p for p in relue["produits"] if p["id"] == "P-BRUNCH")
        assert brunch["declinaisons"][0]["disponibilite"] == {"jours": [6, 7], "heures": [["11:00", "15:00"]]}
        ecrite = carte_vers_hubrise(relue).donnees
        sku = next(p for p in ecrite["products"] if p["ref"] == "P-BRUNCH")["skus"][0]
        assert sku["restrictions"] == {"dow": "-----67", "start_time": "11:00", "end_time": "15:00"}
        e = await brique(essai_de, "PRX1")
        carte = carte_de("briques/PRX1")
        aller_retour = carte_de_hubrise(carte_vers_hubrise(carte).donnees).carte
        assert next(c for c in aller_retour["categories"] if c["id"] == "petitdej")["disponibilite"] == {"heures": [["07:00", "11:00"]]}
        assert next(o for g in aller_retour["groupes"] for o in g["options"] if o["nom"] == "Truffe")["disponibilite"] == {"jours": [6, 7]}
        assert next(f for f in aller_retour["formules"])["disponibilite"]["jours"] == [1, 2, 3, 4, 5]
        assert e.p["mode"] == "emporter"

    async def test_prx1_fiche_du_modele(self, essai_de):
        assert not await la_brique_change_la_fiche("PRX1", essai_de)


# --------------------------------------------------------------------------- #
# L12-05 : PRX2, « hors jours fériés » en règle inconnue
# --------------------------------------------------------------------------- #

MARDI_10_NOVEMBRE = datetime(2026, 11, 10, 12, 0, tzinfo=PARIS)


def test_les_jours_feries_de_france_sont_calcules():
    from datetime import date

    from api.services.commande.briques.prx2 import jours_feries

    f26 = jours_feries(2026)
    assert {date(2026, 4, 6), date(2026, 5, 14), date(2026, 5, 25), date(2026, 11, 11), date(2026, 12, 25), date(2026, 5, 1)} <= f26 and len(f26) == 11
    assert {date(2027, 3, 29), date(2027, 5, 6), date(2027, 5, 17)} <= jours_feries(2027)  # lundi de Pâques, Ascension, lundi de Pentecôte
    assert date(2026, 11, 12) not in f26


class TestPRX2:
    @pytest.mark.parametrize("faire_monde", [MARDI_10_NOVEMBRE], indirect=True)
    async def test_prx2_jamais_un_refus(self, essai_de):
        """« Demain midi » est le 11 novembre (férié) : le plat « hors jours fériés » est PRIS, avec une note de ligne et un signalement au portail ; rien n'est refusé."""
        e = await brique(essai_de, "PRX2")
        await e.tour("pour demain midi", heure="demain midi")
        assert str(e.p.get("heure_voulue") or "").startswith("2026-11-11T12:00"), e.p.get("heure_voulue")
        r = await _ajouter(e, "un plat du midi", article="plat du midi", quantite=1)
        ligne = e.p["lignes"][-1]
        assert ligne["nom"] == "Plat du midi" and "hors jours fériés" in (ligne.get("note") or ""), fait(r)
        signalements = await e.monde.c.fetch("SELECT texte FROM mark.resto_signalement_carte WHERE site_id = $1", e.monde.a)
        assert [s["texte"] for s in signalements] == ["Plat du midi : hors jours fériés, à vérifier"]
        await _ajouter(e, "un plat du midi", article="plat du midi", quantite=1)
        assert len(await e.monde.c.fetch("SELECT 1 FROM mark.resto_signalement_carte WHERE site_id = $1", e.monde.a)) == 1  # rejouable sans doublon

    async def test_prx2_un_jour_ordinaire_aucune_note(self, essai_de):
        e = await brique(essai_de, "PRX2")
        await _ajouter(e, "un plat du midi", article="plat du midi", quantite=1)
        assert not e.p["lignes"][-1].get("note")
        assert not await e.monde.c.fetch("SELECT 1 FROM mark.resto_signalement_carte WHERE site_id = $1", e.monde.a)

    async def test_prx2_aller_retour_caisse(self, essai_de):
        """La clé ``hors_feries`` voyage dans l'étiquette du catalogue (HubRise ne l'exprime pas) et revient intacte ; la note de ligne part à la caisse."""
        carte = carte_de("briques/PRX2")
        relue = carte_de_hubrise(carte_vers_hubrise(carte).donnees).carte
        assert next(p for p in relue["produits"] if p["id"] == "P-PLAT")["disponibilite"]["hors_feries"] is True
        e = await brique(essai_de, "PRX2")
        r = await RC.chiffrer_panier(e.monde.c, e.monde.a, "emporter", [{"code_caisse": "P-PLAT-UNIQUE", "quantite": 1, "choix": [], "note": "Plat du midi : hors jours fériés, à vérifier"}])
        corps = commande_vers_hubrise({"numero": "n-1", "mode": "emporter", "client": {}, "lignes": r.faits["lignes"]})
        assert corps["items"][0]["customer_notes"] == "Plat du midi : hors jours fériés, à vérifier"

    async def test_prx2_fiche_du_modele(self, essai_de):
        assert not await la_brique_change_la_fiche("PRX2", essai_de)


# --------------------------------------------------------------------------- #
# L12-06 : PRX3, la disponibilité par mode
# --------------------------------------------------------------------------- #


class TestPRX3:
    async def test_prx3_refuser_des_que_le_mode_est_connu(self, essai_de):
        """Produit, option et formule « sur place et à emporter » : la pizza à emporter est prise ; l'option truffe (sur place seulement) est refusée avec ses modes ; le mode livraison posé après
        l'article refuse la pizza dès la pose (``a_revoir``), jamais au total."""
        e = await brique(essai_de, "PRX3")
        r = await _ajouter(e, "une pizza du soir", article="pizza du soir", quantite=1, composition=["tomate"])
        assert any(l["nom"] == "Pizza du soir" for l in e.p["lignes"]), fait(r)
        r = await _ajouter(e, "une pizza truffe", article="pizza du soir", quantite=1, composition=["truffe"])
        assert "mode_non_permis" in fait(r) and '"sur_place"' in fait(r), fait(r)
        r = await e.tour("finalement en livraison", mode_de_retrait="livraison")
        assert "mode_non_permis" in fait(r) and "a_revoir" in fait(r), fait(r)

    async def test_prx3_la_formule_est_refusee_par_la_meme_regle(self, essai_de):
        e = await brique(essai_de, "PRX3")
        article = await e.source.article("F-SOIR", "livraison")
        from api.services.commande.briques.prx3 import brique_prx3_refuser_des_que_le_mode_est_connu as regle

        assert regle(article, "livraison") == {"raison": "mode_non_permis", "article": "Offre du soir", "mode": "livraison", "choix": ["sur_place", "emporter"]}
        assert regle(article, "emporter") is None and regle(article, None) is None

    async def test_prx3_aller_retour_caisse(self, essai_de):
        relue = carte_de_hubrise(carte_vers_hubrise(carte_de("briques/PRX3")).donnees).carte
        assert next(p for p in relue["produits"] if p["id"] == "P-PIZZA")["modes"] == ["sur_place", "emporter"]
        assert next(o for g in relue["groupes"] for o in g["options"] if o["nom"] == "Truffe")["modes"] == ["sur_place"]
        assert relue["formules"][0]["modes"] == ["sur_place", "emporter"]
        e = await brique(essai_de, "PRX3")
        await article_en_caisse(e, "P-PIZZA-UNIQUE", 1, [{"option_code": "G-BASE-TOMATE", "quantite": 1}])

    async def test_prx3_fiche_du_modele(self, essai_de):
        assert not await la_brique_change_la_fiche("PRX3", essai_de)


# --------------------------------------------------------------------------- #
# L12-08 : PRX5, le prix « à partir de »
# --------------------------------------------------------------------------- #


class TestPRX5:
    async def test_prx5_jamais_le_prix_de_depart_comme_final(self, essai_de):
        """Le tacos (3 tailles, une viande payante) : « à partir de » ; les frites (prix unique) : le prix, sans « à partir de » ; le bol (choix gratuits) : le prix."""
        e = await brique(essai_de, "PRX5")
        tacos = await e.source.article("P-TACOS", "emporter")
        assert brique_prx5(tacos) == {"montant": 700, "a_partir_de": True}
        assert brique_prx5(await e.source.article("P-FRITES", "emporter")) == {"montant": 300, "a_partir_de": False}
        assert brique_prx5(await e.source.article("P-BOWL", "emporter")) == {"montant": 900, "a_partir_de": False}

    async def test_prx5_la_lecture_rend_le_prix_et_le_code_le_dit(self, essai_de):
        """« C'est combien le tacos ? » : la lecture rend le fait ``prix`` (jamais la phrase) ; le code dit le chiffre après la phrase du modèle (D33)."""
        from api.services.commande import porte

        e = await brique(essai_de, "PRX5")
        r = await e.lecture(sujet="article", article="tacos")
        assert r["faits"]["prix"] == {"montant": 700, "a_partir_de": True}, r
        assert "suffixe_du_code" not in r and "prix_a_dire" not in fait(r) and r["prix_dit_par_le_code_apres_ta_phrase"] is True
        assert e.fiche_de_l_appel[porte.CLE_TEXTES_DU_CODE]["suffixe"] == "Le Tacos est à partir de sept euros."
        r = await e.lecture(sujet="article", article="frites")
        assert r["faits"]["prix"] == {"montant": 300, "a_partir_de": False}
        assert e.fiche_de_l_appel[porte.CLE_TEXTES_DU_CODE]["suffixe"] == "Les Frites est à trois euros." or "à trois euros" in e.fiche_de_l_appel[porte.CLE_TEXTES_DU_CODE]["suffixe"]

    async def test_prx5_aller_retour_caisse(self, essai_de):
        """Le prix de départ n'est jamais celui de la commande : le tacos XL avec steak se chiffre à sa taille et à son choix, et la caisse retrouve ce total."""
        e = await brique(essai_de, "PRX5")
        article = await article_en_caisse(e, "P-TACOS-XL", 1, [{"option_code": "G-VIANDE-STEAK", "quantite": 1}])
        assert article["price"] == "10.00 EUR" and article["options"][0]["price"] == "1.00 EUR"

    async def test_prx5_fiche_du_modele(self, essai_de):
        assert await la_brique_change_la_fiche("PRX5", essai_de)


# --------------------------------------------------------------------------- #
# L12-07, L12-10, L12-11, L12-12 : PRX4, PRX7, PRX8, PRX9 (jamais vues sur une carte : code seulement, aucune case nouvelle)
# --------------------------------------------------------------------------- #


class TestPRX4:
    async def test_prx4_prix_au_mode(self, essai_de):
        """Le burger à 8,90 € passe à 9,90 € en livraison ; le cheddar à 1 € passe à 1,50 € ; à emporter, les prix de base."""
        e = await brique(essai_de, "PRX4")
        ligne = [{"code_caisse": "P-BURGER-UNIQUE", "quantite": 1, "choix": [{"option_code": "G-SAUCE-CHEDDAR", "quantite": 1}]}]
        emporter = await RC.chiffrer_panier(e.monde.c, e.monde.a, "emporter", ligne)
        livraison = await RC.chiffrer_panier(e.monde.c, e.monde.a, "livraison", ligne)
        assert emporter.faits["lignes"][0]["prix_unitaire"] == 990
        assert livraison.faits["lignes"][0]["prix_unitaire"] == 1140 and livraison.faits["lignes"][0]["choix"][0]["prix"] == 150

    async def test_prx4_aller_retour_caisse(self, essai_de):
        """Les règles ``price_overrides`` à ``service_types`` (documentation) donnent le prix par mode ; la carte les réécrit ; en livraison, la caisse retrouve le total."""
        relue = carte_de_hubrise(json.loads((REPONSES / "50-catalogue-conditions-de-vente.json").read_text(encoding="utf-8"))).carte
        burger = next(p for p in relue["produits"] if p["id"] == "P-BURGER")
        assert burger["declinaisons"][0]["prix_par_mode"] == {"livraison": 990}
        assert next(o for g in relue["groupes"] for o in g["options"] if o["nom"] == "Cheddar")["prix_par_mode"] == {"livraison": 150}
        ecrite = carte_vers_hubrise(relue).donnees
        assert next(p for p in ecrite["products"] if p["ref"] == "P-BURGER")["skus"][0]["price_overrides"] == [{"service_types": ["delivery"], "price": "9.90 EUR"}]
        e = await brique(essai_de, "PRX4")
        r = await RC.chiffrer_panier(e.monde.c, e.monde.a, "livraison", [{"code_caisse": "P-BURGER-UNIQUE", "quantite": 1, "choix": [{"option_code": "G-SAUCE-CHEDDAR", "quantite": 1}]}])
        article = commande_vers_hubrise({"numero": "n-1", "mode": "livraison", "client": {}, "adresse": {}, "lignes": r.faits["lignes"]})["items"][0]
        assert article["price"] == "9.90 EUR" and article["options"][0]["price"] == "1.50 EUR"

    async def test_prx4_fiche_du_modele(self, essai_de):
        assert not await la_brique_change_la_fiche("PRX4", essai_de)


class TestPRX7:
    async def test_prx7_ligne_de_frais(self, essai_de):
        """Une bouteille consignée ajoute sa ligne de frais (0,50 €) par unité ; « avec couverts » dit par le client reste une note de ligne."""
        e = await brique(essai_de, "PRX7")
        r = await RC.chiffrer_panier(e.monde.c, e.monde.a, "emporter", [{"code_caisse": "P-BOUTEILLE-UNIQUE", "quantite": 2, "choix": []}, {"code_caisse": "P-CANETTE-UNIQUE", "quantite": 1, "choix": []}])
        bouteille, canette = r.faits["lignes"]
        assert bouteille["prix_unitaire"] == 350 and [c["nom"] for c in bouteille["choix"]] == ["Consigne"] and r.faits["sous_total"] == 900
        assert canette["prix_unitaire"] == 200 and not canette["choix"]
        await _ajouter(e, "une bouteille d'eau avec couverts", article="bouteille d'eau", quantite=1, precision_article="avec couverts")
        assert e.p["lignes"][-1]["note"] == "avec couverts"

    async def test_prx7_aller_retour_caisse(self, essai_de):
        """Le frais part comme une option « Frais » sans ``ref`` ; le prix de l'article est le produit seul, et la caisse retrouve le total ; la donnée voyage par l'étiquette."""
        e = await brique(essai_de, "PRX7")
        article = await article_en_caisse(e, "P-BOUTEILLE-UNIQUE", 2)
        assert article["price"] == "3.00 EUR" and article["quantity"] == "2"
        assert article["options"] == [{"option_list_name": "Frais", "name": "Consigne", "price": "0.50 EUR"}]
        relue = carte_de_hubrise(carte_vers_hubrise(carte_de("briques/PRX7")).donnees).carte
        assert next(p for p in relue["produits"] if p["id"] == "P-BOUTEILLE")["frais"] == [{"nom": "Consigne", "prix": 50}]

    async def test_prx7_fiche_du_modele(self, essai_de):
        assert not await la_brique_change_la_fiche("PRX7", essai_de)


class TestPRX8:
    async def test_prx8_refuser_au_dela(self, essai_de):
        """Tenders à quatre au plus par commande : trois sont pris, deux de plus sont refusés avec le maximum (les quantités du même produit s'additionnent) ; les frites n'ont aucun plafond de carte."""
        e = await brique(essai_de, "PRX8")
        await _ajouter(e, "trois tenders", article="tenders", quantite=3)
        r = await _ajouter(e, "deux tenders de plus", article="tenders", quantite=2)
        assert "quantite_au_dela_du_maximum" in fait(r) and '"maximum": 4' in fait(r) and e.p["lignes"][-1]["quantite"] == 3, fait(r)
        await _ajouter(e, "un tender de plus", article="tenders", quantite=1)
        assert sum(l["quantite"] for l in e.p["lignes"] if l["nom"] == "Tenders") == 4
        r = await _ajouter(e, "dix frites", article="frites", quantite=10)
        assert any(l["nom"] == "Frites" and l["quantite"] == 10 for l in e.p["lignes"]), fait(r)

    async def test_prx8_aller_retour_caisse(self, essai_de):
        """``max_per_order`` (restrictions d'un sku, documentation) donne le maximum ; la carte le réécrit ; le chiffrage refuse aussi au-delà."""
        relue = carte_de_hubrise(json.loads((REPONSES / "50-catalogue-conditions-de-vente.json").read_text(encoding="utf-8"))).carte
        assert next(p for p in relue["produits"] if p["id"] == "P-BURGER")["max_par_commande"] == 4
        ecrite = carte_vers_hubrise(relue).donnees
        assert next(p for p in ecrite["products"] if p["ref"] == "P-BURGER")["skus"][0]["restrictions"]["max_per_order"] == 4
        e = await brique(essai_de, "PRX8")
        refus = await RC.chiffrer_panier(e.monde.c, e.monde.a, "emporter", [{"code_caisse": "P-TENDERS-UNIQUE", "quantite": 3, "choix": []}, {"code_caisse": "P-TENDERS-UNIQUE", "quantite": 2, "choix": []}])
        assert refus.statut == "INTERDIT" and refus.faits["raison"] == "quantite_au_dela_du_maximum" and refus.faits["maximum"] == 4

    async def test_prx8_fiche_du_modele(self, essai_de):
        assert not await la_brique_change_la_fiche("PRX8", essai_de)


async def test_quantite_maximale_de_la_donnee(essai_de):
    """L12-03 : un produit à ``max_par_commande`` 4 refuse le cinquième ; sans la donnée, le comportement d'avant (bornes de sécurité 20 et 99) est inchangé."""
    e = await brique(essai_de, "PRX8")
    ok = await RC.chiffrer_panier(e.monde.c, e.monde.a, "emporter", [{"code_caisse": "P-TENDERS-UNIQUE", "quantite": 4, "choix": []}])
    assert ok.statut == "OK"
    trop = await RC.chiffrer_panier(e.monde.c, e.monde.a, "emporter", [{"code_caisse": "P-TENDERS-UNIQUE", "quantite": 5, "choix": []}])
    assert trop.statut == "INTERDIT" and trop.faits["maximum"] == 4
    beaucoup = await RC.chiffrer_panier(e.monde.c, e.monde.a, "emporter", [{"code_caisse": "P-FRITES-UNIQUE", "quantite": 99, "choix": []}])
    assert beaucoup.statut == "OK"
    trop_de_frites = await RC.chiffrer_panier(e.monde.c, e.monde.a, "emporter", [{"code_caisse": "P-FRITES-UNIQUE", "quantite": 100, "choix": []}])
    assert trop_de_frites.statut == "ARGUMENT_INVALIDE"


class TestPRX9:
    async def test_prx9_date_la_plus_proche(self, essai_de):
        """Un buffet à commander 48 heures à l'avance, un jeudi midi : pour vendredi midi, refusé avec la date la plus proche (samedi midi) ; pour dimanche, accepté."""
        e = await brique(essai_de, "PRX9")
        await e.tour("pour demain midi", heure="demain midi")
        r = await _ajouter(e, "un buffet froid", article="buffet froid", quantite=1)
        assert "delai_minimal_non_respecte" in fait(r) and "2026-11-14T12:00" in fait(r) and not e.p["lignes"], fait(r)
        e2 = await brique(essai_de, "PRX9")
        await e2.tour("pour dimanche midi", heure="dimanche midi")
        r = await _ajouter(e2, "un buffet froid", article="buffet froid", quantite=1)
        assert any(l["nom"] == "Buffet froid" for l in e2.p["lignes"]), fait(r)

    async def test_prx9_la_regle_pure(self):
        from datetime import timedelta

        maintenant = datetime(2026, 11, 12, 12, 0, tzinfo=PARIS)
        buffet = {"nom": "Buffet froid", "delai_minimal_heures": 48, "personnes_min": 8}
        assert brique_prx9(buffet, maintenant, maintenant + timedelta(hours=47))["date_la_plus_proche"] == (maintenant + timedelta(hours=48)).isoformat()
        assert brique_prx9(buffet, maintenant, maintenant + timedelta(hours=48)) is None
        assert brique_prx9(buffet, maintenant, maintenant + timedelta(hours=72), personnes=5)["raison"] == "personnes_minimales_non_atteintes"
        assert brique_prx9(buffet, maintenant, maintenant + timedelta(hours=72), personnes=8) is None
        assert brique_prx9(buffet, maintenant, maintenant + timedelta(hours=72)) is None  # sans la case ``personnes``, la donnée est lue et n'agit pas
        assert brique_prx9({"nom": "Plateau"}, maintenant, None) is None

    async def test_prx9_aller_retour_caisse(self, essai_de):
        """Le délai et le minimum de personnes voyagent par l'étiquette du catalogue (HubRise ne dit qu'un montant minimum) et reviennent intacts."""
        relue = carte_de_hubrise(carte_vers_hubrise(carte_de("briques/PRX9")).donnees).carte
        buffet = next(p for p in relue["produits"] if p["id"] == "P-BUFFET")
        assert buffet["delai_minimal_heures"] == 48 and buffet["personnes_min"] == 8
        e = await brique(essai_de, "PRX9")
        r = await RC.chiffrer_panier(e.monde.c, e.monde.a, "emporter", [{"code_caisse": "P-BUFFET-UNIQUE", "quantite": 1, "choix": []}], servi_le=datetime(2026, 11, 15, 12, 0, tzinfo=PARIS))
        assert r.statut == "OK" and r.faits["lignes"][0]["prix_unitaire"] == 2400

    async def test_prx9_fiche_du_modele(self, essai_de):
        assert not await la_brique_change_la_fiche("PRX9", essai_de)


async def test_briques_jamais_vues_sans_case_nouvelle(essai_de):
    """L12-14 : PRX4, PRX7, PRX8, PRX9 ne changent pas la fiche du modèle et ne lui ajoutent aucune case ; la déclaration du registre le dit."""
    from api.services.commande.briques import registre

    for code in ("PRX4", "PRX7", "PRX8", "PRX9"):
        b = registre.BRIQUES[code]
        assert b.change_la_fiche_du_modele is False and b.vue_sur_carte is False, code
        assert not await la_brique_change_la_fiche(code, essai_de), code

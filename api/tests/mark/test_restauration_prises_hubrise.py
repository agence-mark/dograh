"""[.mark] Module Restauration, lot 3 : les traducteurs HubRise <-> format commun (fonctions pures), d'après les réponses
enregistrées le 15/11 (``reponses_hubrise/``, aucun appel réel).

| Test | Ce qu'il prouve |
|---|---|
| montants | ``12.50 EUR`` s'écrit et se relit ; une virgule, une autre monnaie, un flottant sont refusés |
| aller et retour | la carte de l'essai (82 produits) écrite pour HubRise puis relue est identique, objet pour objet |
| sans code de caisse | un produit ou une option sans code est signalé, jamais écrit |
| la caisse est maître | un nom ou un prix changé à la caisse prévaut sur l'étiquette ``mark:`` |
| vraie réponse | la carte relue de HubRise (04) est lue sans perte d'identité ; allergènes inconnus, prix de formule dit inconnu |
| correspondance | la table dit si un code est un sku ou une option |
| commande | la demande part au format des demandes enregistrées (12, 13, 14) ; notre numéro = ``private_ref`` |
| commande lue | étape, total, lignes de la réponse 21 ; ``cree_par`` ; statut inconnu = ``inconnu`` |
| état, ruptures | aller et retour avec les réponses 05 à 08 |
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path

import pytest

from api.services.restauration.prises import hubrise_traduction as ht

REPONSES = Path(__file__).parent / "reponses_hubrise"
CARTE_ESSAI = Path(__file__).parent / "cartes_essai" / "carte-reference.json"


def _reponse(nom: str) -> dict:
    return json.loads((REPONSES / nom).read_text(encoding="utf-8"))


def _demande(nom: str) -> dict:
    return _reponse(nom)["demande"]["corps"]


def _corps(nom: str) -> dict:
    return _reponse(nom)["reponse"]["corps"]


def _carte() -> dict:
    return json.loads(CARTE_ESSAI.read_text(encoding="utf-8"))


def test_les_montants_s_ecrivent_comme_hubrise_et_se_relisent():
    assert ht.euros(1250) == "12.50 EUR" and ht.euros(5) == "0.05 EUR" and ht.euros(-275) == "-2.75 EUR"
    assert ht.centimes("12.50 EUR") == 1250 and ht.centimes("0.00 EUR") == 0 and ht.centimes("19 EUR") == 1900
    for faux in ("12,50 EUR", "12.50", "12.50 USD", None, "", "12.505 EUR"):
        with pytest.raises(ht.TraductionImpossible):
            ht.centimes(faux)
    for faux in (12.5, "12", True):
        with pytest.raises(ht.TraductionImpossible):
            ht.euros(faux)


def test_la_carte_de_l_essai_fait_l_aller_et_retour_sans_perte():
    carte = _carte()
    ecrite = ht.carte_vers_hubrise(carte)
    assert ecrite.signales == []
    donnees = ecrite.donnees
    produit = donnees["products"][0]
    assert produit["skus"][0]["ref"] == carte["produits"][0]["declinaisons"][0]["code_caisse"]
    assert re.fullmatch(r"\d+\.\d\d EUR", produit["skus"][0]["price"])
    relue = ht.carte_de_hubrise(json.loads(json.dumps(donnees)))
    for rubrique in ("categories", "produits", "groupes", "formules"):
        assert relue.carte[rubrique] == carte[rubrique], rubrique
    deal = next(d for d in donnees["deals"] if d["ref"] == "F-MENU-BUR")
    assert {"ref": "BUR-CHE"} in deal["lines"][0]["skus"] and len(deal["lines"][1]["skus"]) > 0


def test_un_produit_ou_une_option_sans_code_de_caisse_est_signale_jamais_envoye():
    carte = _carte()
    produit = carte["produits"][0]
    produit["declinaisons"][0]["code_caisse"] = None
    option = carte["groupes"][0]["options"][0]
    option["code_caisse"] = ""
    ecrite = ht.carte_vers_hubrise(carte)
    assert produit["declinaisons"][0]["id"] in ecrite.signales and option["id"] in ecrite.signales
    refs = {s["ref"] for p in ecrite.donnees["products"] for s in p["skus"]}
    assert not any(r in ("", None) for r in refs)
    assert len(ecrite.donnees["products"][0]["skus"]) == len(produit["declinaisons"]) - 1
    assert len(ecrite.donnees["option_lists"][0]["options"]) == len(carte["groupes"][0]["options"]) - 1
    for d in produit["declinaisons"]:
        d["code_caisse"] = None
    assert produit["id"] not in {p["ref"] for p in ht.carte_vers_hubrise(carte).donnees["products"]}


def test_la_caisse_est_maitre_de_ce_qu_elle_porte_l_etiquette_ne_le_contredit_pas():
    carte = _carte()
    donnees = json.loads(json.dumps(ht.carte_vers_hubrise(carte).donnees))
    donnees["products"][0]["name"] = "Renommée à la caisse"
    donnees["products"][0]["skus"][0]["price"] = "99.00 EUR"
    relue = ht.carte_de_hubrise(donnees).carte["produits"][0]
    assert relue["nom"] == "Renommée à la caisse" and relue["declinaisons"][0]["prix"] == 9900
    assert relue["allergenes"] == carte["produits"][0]["allergenes"] and relue["ingredients"] == carte["produits"][0]["ingredients"]


def test_la_carte_relue_de_la_vraie_reponse_hubrise():
    lue = ht.carte_de_hubrise(_corps("04-carte-relue.json"))
    carte = lue.carte
    assert [c["id"] for c in carte["categories"]] == ["PIZ", "BOI", "DES"]
    reine = next(p for p in carte["produits"] if p["id"] == "REINE")
    assert reine["categorie_id"] == "PIZ" and reine["allergenes"] is None  # inconnu, jamais « aucun »
    assert [(d["code_caisse"], d["prix"]) for d in reine["declinaisons"]] == [("REINE-J", 1050), ("REINE-S", 1250)]
    assert reine["groupes"] == ["SANS", "SUPP"]
    supp = next(g for g in carte["groupes"] if g["id"] == "SUPP")
    assert [(o["code_caisse"], o["prix"]) for o in supp["options"]] == [("SUPP-FROMAGE", 150), ("SUPP-OEUF", 100)] and supp["max"] == 2  # HubRise rend 2 : le plafond demandé (3) dépassait les options
    formule = carte["formules"][0]
    assert formule["id"] == "DUO" and [x["effet"] for x in formule["lignes"]] == ["inchange", "pourcentage"]
    assert any("DUO" in s for s in lue.signales)  # HubRise ne porte pas le prix d'une formule : dit, pas inventé


def test_la_correspondance_des_codes_dit_sku_ou_option():
    t = ht.correspondance_de_la_carte(_corps("04-carte-relue.json"))
    assert t.genre("REINE-S") == "declinaison" and t.genre("SUPP-OEUF") == "option"
    assert t.code_de_id[t.id_de_code["COCA-33"]] == "COCA-33"
    with pytest.raises(KeyError):
        t.genre("INCONNU")


def _commande_essai(**plus):
    base = {
        "numero": "8f0d6c64-6d62-4a42-9c0e-0c1c2c3c4c5c", "mode": "emporter", "client": {"telephone": "+33600000001", "prenom": "Camille"},
        "note": "Commande d'essai",
        "lignes": [
            {"code_caisse": "REINE-S", "nom": "Reine (Test)", "prix_unitaire": 1250, "quantite": 1, "note": "Bien cuite",
             "choix": [{"option_code": "SUPP-FROMAGE", "nom": "Supplément fromage", "prix": 150, "quantite": 1}], "retires": ["Sans olives"]},
            {"code_caisse": "COCA-33", "nom": "Coca-Cola (Test)", "prix_unitaire": 250, "quantite": 2},
        ],
        "paiement": {"moyens": [{"moyen": "carte", "montant": 1900}]},
    }
    return {**base, **plus}


def test_la_commande_part_au_format_de_la_demande_enregistree():
    enregistree = _demande("12-commande-simple.json")
    corps = ht.commande_vers_hubrise(_commande_essai())
    assert corps["status"] == "new" and corps["service_type"] == enregistree["service_type"] == "collection"
    assert corps["private_ref"] == "8f0d6c64-6d62-4a42-9c0e-0c1c2c3c4c5c"  # NOTRE numéro (anti-doublon, 20)
    assert [(a["sku_ref"], a["price"], a["quantity"]) for a in corps["items"]] == [(a["sku_ref"], a["price"], a["quantity"]) for a in enregistree["items"]]
    option = corps["items"][0]["options"]
    assert option[0]["ref"] == "SUPP-FROMAGE" and option[0]["price"] == "1.50 EUR"
    assert option[1] == {"option_list_name": "Retraits", "name": "Sans olives", "price": "0.00 EUR", "removed": True}  # ``option_list_name`` obligatoire (documentation), ``ref`` non
    assert option[0]["option_list_name"] == "Options"
    assert corps["payments"][0]["amount"] == enregistree["payments"][0]["amount"] == "19.00 EUR"
    assert corps["customer"]["phone"] == "+33600000001" and "total" not in corps  # HubRise recalcule : on n'envoie pas le nôtre
    assert corps["customer_notes"] == "Commande d'essai" and "expected_time" not in corps


def test_livraison_remises_frais_et_heure_voulue():
    enregistree = _demande("13-commande-remises.json")
    heure = datetime(2026, 11, 15, 19, 30, tzinfo=UTC)
    corps = ht.commande_vers_hubrise(
        _commande_essai(
            mode="livraison", frais=200, heure_voulue=heure,
            remises=[{"nom": "-10 % le midi (Test)", "montant": 275, "ref_caisse": "MIDI10"}, {"nom": "Dessert offert", "montant": 450, "ref_caisse": None}],
        )
    )
    assert corps["service_type"] == "delivery" and corps["expected_time"] == heure.isoformat()
    assert corps["discounts"][0] == {"name": "-10 % le midi (Test)", "price_off": "2.75 EUR", "ref": "MIDI10"}
    assert corps["discounts"][1] == {"name": "Dessert offert", "price_off": "4.50 EUR"}  # sans référence : acceptée (13)
    assert corps["charges"] == [{"name": "Livraison", "price": enregistree["charges"][0]["price"]}]


def test_une_formule_part_en_deals_et_deal_line_comme_la_demande_enregistree():
    enregistree = _demande("14-commande-formule.json")
    commande = _commande_essai(
        lignes=[
            {"code_caisse": "REINE-S", "nom": "Reine (Test)", "prix_unitaire": 1250, "quantite": 1, "formule_id": "DUO", "etiquette_formule": "1re pizza"},
            {"code_caisse": "MARG-S", "nom": "Margherita (Test)", "prix_unitaire": 575, "quantite": 1, "formule_id": "DUO", "etiquette_formule": "2e pizza"},
        ]
    )
    corps = ht.commande_vers_hubrise(commande, formules={"DUO": {"nom": "2e pizza à moitié prix (Test)"}})
    assert list(corps["deals"]) == ["0"] and corps["deals"]["0"]["ref"] == enregistree["deals"]["0"]["ref"] == "DUO"
    assert [a["deal_line"]["deal_key"] for a in corps["items"]] == ["0", "0"]
    assert [a["deal_line"]["label"] for a in corps["items"]] == ["1re pizza", "2e pizza"]
    assert set(corps["items"][0]["deal_line"]) == set(enregistree["items"][0]["deal_line"])


def test_un_mode_inconnu_ou_un_montant_flottant_est_refuse():
    with pytest.raises(ht.TraductionImpossible):
        ht.commande_vers_hubrise(_commande_essai(mode="drive"))
    with pytest.raises(ht.TraductionImpossible):
        ht.commande_vers_hubrise(_commande_essai(frais=2.5))


def test_une_commande_lue_chez_hubrise_dit_etape_total_et_lignes():
    lue = ht.commande_de_hubrise(_corps("21-commande-acceptee.json"))
    assert lue["etape"] == "acceptee" and lue["numero"] == "mark-test-1" and lue["ref_fournisseur"] == "8qknnxn"
    assert lue["total"] == 1900 and lue["mode"] == "emporter" and lue["cree_par"] == "agent" and lue["heure_annoncee"] is None
    assert [(l["code_caisse"], l["quantite"], l["prix_unitaire"]) for l in lue["lignes"]] == [("REINE-S", 1, 1250), ("COCA-33", 2, 250)]
    assert lue["lignes"][0]["retires"] == ["Sans olives"] and lue["lignes"][0]["choix"][0]["option_code"] == "SUPP-FROMAGE"
    sans_ref = {**_corps("21-commande-acceptee.json"), "private_ref": None, "status": "weird"}
    assert ht.commande_de_hubrise(sans_ref)["cree_par"] == "caisse" and ht.commande_de_hubrise(sans_ref)["etape"] == "inconnu"
    for statut, etape in (("received", "recue"), ("rejected", "refusee"), ("cancelled", "annulee"), ("completed", "terminee"), ("awaiting_collection", "prete")):
        assert ht.etape_de_statut(statut) == etape


def test_l_etat_du_restaurant_aller_et_retour_avec_les_reponses_enregistrees():
    deborde = ht.etat_de_hubrise(_corps("07-point-de-vente-deborde.json"))
    assert deborde["mode"] == "deborde" and deborde["minutes_en_plus"] == 15 and deborde["reprise"] is None
    assert ht.etat_vers_hubrise(deborde) == {"order_acceptance": {"mode": "busy", "extra_preparation_time": 15}}
    assert _demande("07-point-de-vente-deborde.json")["order_acceptance"] == {"mode": "busy", "extra_preparation_time": 15}
    normal = ht.etat_de_hubrise(_corps("08-point-de-vente-normal.json"))
    assert normal["mode"] == "normal" and normal["temps_preparation"] == 20
    assert ht.etat_vers_hubrise(normal) == _demande("08-point-de-vente-normal.json")
    assert ht.etat_de_hubrise({"order_acceptance": {"mode": "inattendu"}})["mode"] == "pause"  # le plus prudent
    reprise = datetime(2026, 11, 15, 21, 0, tzinfo=UTC)
    assert ht.etat_vers_hubrise({"mode": "pause", "reprise": reprise})["order_acceptance"]["resume_at"] == reprise.isoformat()


def test_les_ruptures_aller_et_retour_avec_les_reponses_enregistrees():
    lues = ht.ruptures_de_hubrise(_corps("06-inventaire-lu.json"))
    assert [(r["code_caisse"], r["genre"], r["disponible"]) for r in lues] == [("TIRA-1", "declinaison", False), ("SUPP-OEUF", "option", False)]
    ecrites = [ht.rupture_vers_hubrise("TIRA-1", "declinaison", False), ht.rupture_vers_hubrise("SUPP-OEUF", "option", False)]
    assert ecrites == _demande("05-inventaire-ecrit.json")
    assert ht.rupture_vers_hubrise("TIRA-1", "declinaison", True) == {"sku_ref": "TIRA-1", "stock": None}
    assert ht.ruptures_de_hubrise([{"sku_ref": "A", "stock": "4.0", "expires_at": None}])[0]["disponible"] is True


def test_les_quatre_valeurs_verifiees_a_la_documentation_officielle_le_15_11():
    """Les quatre valeurs que SA-2 n'avait pas pu confirmer, vérifiées dans la documentation publique de HubRise (pages accounts, catalogs,
    inventories, orders) : le mode « pause » se dit ``paused`` ; un parent de catégorie s'écrit ``parent_ref`` ; un retrait n'a pas besoin de ``ref``
    mais d'un ``option_list_name`` ; ``stock: null`` ne retire une limite que par ``PATCH`` (``PUT`` l'ignore)."""
    assert ht.etat_vers_hubrise({"mode": "pause"}) == {"order_acceptance": {"mode": "paused"}}
    assert ht.etat_de_hubrise({"order_acceptance": {"mode": "paused"}})["mode"] == "pause"
    carte = {"format": ht.FORMAT_CARTE, "categories": [{"id": "pizzas", "nom": "Pizzas", "parent_id": None, "ordre": 0, "portee": "etablissement"},
                                                       {"id": "classiques", "nom": "Classiques", "parent_id": "pizzas", "ordre": 1, "portee": "etablissement"}],
             "produits": [], "groupes": [], "formules": []}
    ecrites = ht.carte_vers_hubrise(carte).donnees["categories"]
    assert "parent_ref" not in ecrites[0] and ecrites[1]["parent_ref"] == "pizzas"
    assert ht.rupture_vers_hubrise("REINE-S", "declinaison", True) == {"sku_ref": "REINE-S", "stock": None}  # à envoyer en PATCH


def test_nuit_18_11_une_adresse_en_texte_n_est_plus_devinee_par_la_traduction():
    """Nuit du 18/11 (essais 2635-2637) : le moteur posait l'adresse en TEXTE et la traduction l'envoyait telle quelle dans ``address_1`` (sans
    commune ni code postal, audit caisse § 3.1). Chantier Partie 1, lot 1 (S03) : l'adresse est toujours une ``Adresse`` structurée posée par la
    vérification ; un texte est refusé, jamais deviné (sens repris par ``partie_1/test_l01_types.py::test_traducteur_sans_branche_texte`` et
    ``::test_caisse_recoit_rue_code_postal_ville``)."""
    with pytest.raises(ht.TraductionImpossible):
        ht.commande_vers_hubrise(_commande_essai(mode="livraison", adresse="12 rue de la République à Senlis"))
    corps = ht.commande_vers_hubrise(_commande_essai(mode="livraison", adresse={"voie": "12 rue de la République", "code_postal": "60300", "commune": "Senlis"}))
    assert corps["service_type"] == "delivery" and corps["customer"]["address_1"] == "12 rue de la République" and corps["customer"]["city"] == "Senlis"
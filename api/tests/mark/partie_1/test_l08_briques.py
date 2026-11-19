"""[.mark] Chantier Partie 1, lot 8 : les briques article et déclinaison (``services/commande/briques/``) et l'envoi des options à la caisse (D50).

Une classe par brique (``TestART1`` ...), chacune avec sa règle, son aller-retour en caisse et son test de rendu de la fiche (D66).
"""

from __future__ import annotations

from api.db.bases_clients import restauration_commande as RC
from api.services.restauration.prises.hubrise_traduction import commande_vers_hubrise


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


def _groupe(gid: str, nom: str, options: list[dict], *, mini: int = 0, maxi: int = 3, role: str = "supplement", parent: str | None = None) -> dict:
    return {"id": gid, "nom": nom, "min": mini, "max": maxi, "max_par_option": 3, "role": role, "defaut": [], "parent_option_id": parent, "options": options}


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

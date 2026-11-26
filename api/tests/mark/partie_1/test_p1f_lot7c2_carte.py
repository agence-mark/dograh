"""[.mark] Lot 7b-C2, la carte (``restauration_commande`` : choix, formules, lignes) : chaque refus fermé ne porte plus de texte (lot 7b-C7, A3) ; le texte d'avant se refait toujours de ses seuls faits
(``textes_de_secours_commande``). Calcul pur, sans base."""

from __future__ import annotations

from api.db.bases_clients import restauration_commande as RC
from api.db.bases_clients import textes_de_secours_commande as TSC
from api.services.commande import textes_de_secours as TS


def _option(ref: str, nom: str, prix: int = 100, **plus) -> dict:
    return {"id": ref, "groupe_id": "G", "nom": nom, "code_caisse": ref.upper(), "prix": prix, "par_defaut": False, "retirable": False, "vendable": True, **plus}


def _groupe(nom: str, options: list[dict], *, mini: int = 0, maxi: int = 3, par_option: int = 3) -> dict:
    return {"id": "G", "nom": nom, "min": mini, "max": maxi, "max_par_option": par_option, "role": "supplement", "defaut": [], "parent_option_id": None, "options": options}


def _produit(code: str, nom: str, groupes: list[str]) -> dict:
    return {"id": "P-" + code, "nom": nom, "categorie_id": "C", "ingredients": [], "alcool": False, "groupes": groupes, "tva_par_mode": {},
            "declinaisons": [{"id": "D-" + code, "nom": "Unique", "code_caisse": code, "prix": 1000, "vendable": True, "prix_par_mode": None}]}


def _carte(groupes: list[dict] | None = None, formules: list[dict] | None = None, extra: list[dict] | None = None) -> dict:
    return {"produits": [_produit("PIZZA", "Pizza", [g["id"] for g in groupes or []]), *(extra or [])], "groupes": groupes or [], "formules": formules or [],
            "categories": []}


def _refus(carte: dict, ligne: dict, ruptures: set[str] | None = None):
    calculees, total, erreur = RC._lignes(RC._Panier(carte, "emporter", ruptures or set()), [ligne])
    assert erreur is not None, calculees
    return erreur


def _verifie(r, statut: str, texte: str, secours, manque: str | None = None):
    """C7 (A3) : le refus ne porte plus de texte ; le texte d'avant se refait toujours de ses seuls faits (il sort avec le catalogue, lot B)."""
    assert (r.statut, r.suggestion, r.manque) == (statut, "", manque), r
    assert secours(r.faits) == texte, r


def _pizza(choix: list[dict], **plus) -> dict:
    return {"code_caisse": "PIZZA", "quantite": 1, "choix": choix, **plus}


GROUPE = _groupe("Suppléments", [_option("oeuf", "Œuf"), _option("fromage", "Fromage")])


def test_choix_inconnu():
    r = _refus(_carte([GROUPE]), _pizza([{"option_code": "INCONNU", "quantite": 1}]))
    _verifie(r, "HORS_CARTE", "Ce choix n'existe pas pour ce produit.", TSC.choix_hors_produit)
    assert r.faits == {"code": "INCONNU"}


def test_quantite_de_choix_invalide():
    r = _refus(_carte([GROUPE]), _pizza([{"option_code": "OEUF", "quantite": 0}]))
    _verifie(r, "ARGUMENT_INVALIDE", "Quantité de choix invalide.", TSC.quantite_de_choix_invalide, "quantite")


def test_choix_en_rupture():
    r = _refus(_carte([GROUPE]), _pizza([{"option_code": "OEUF", "quantite": 1}]), {"OEUF"})
    _verifie(r, "RUPTURE", "Œuf n'est plus disponible.", TS.n_est_plus_disponible)
    assert r.faits == {"code": "OEUF", "nom": "Œuf"}


def test_choix_pris_trop_de_fois():
    g = _groupe("Suppléments", [_option("oeuf", "Œuf")], par_option=1)
    r = _refus(_carte([g]), _pizza([{"option_code": "OEUF", "quantite": 2}]))
    _verifie(r, "MAXIMUM_ATTEINT", "Œuf ne se prend pas plus de 1 fois.", TSC.option_trop_de_fois)
    assert r.faits == {"groupe": "G", "code": "OEUF", "nom": "Œuf", "maximum": 1}


def test_choix_obligatoire_du_groupe():
    g = _groupe("Cuisson", [_option("saignant", "Saignant")], mini=1)
    r = _refus(_carte([g]), _pizza([]))
    _verifie(r, "CHOIX_OBLIGATOIRE", "Il faut choisir : Cuisson.", TSC.choix_obligatoire)


def test_trop_de_choix_dans_le_groupe():
    g = _groupe("Suppléments", [_option("oeuf", "Œuf"), _option("fromage", "Fromage")], maxi=1)
    r = _refus(_carte([g]), _pizza([{"option_code": "OEUF", "quantite": 1}, {"option_code": "FROMAGE", "quantite": 1}]))
    _verifie(r, "MAXIMUM_ATTEINT", "Pas plus de 1 pour : Suppléments.", TSC.pas_plus_pour)
    assert r.faits == {"groupe": "G", "nom": "Suppléments", "maximum": 1}


# --- la formule ------------------------------------------------------------------------------------------------------------------------------------


def _menu(lignes: list[dict]) -> dict:
    formule = {"id": "F", "nom": "Menu", "code_caisse": "MENU", "prix": 1400, "vendable": True, "categorie_id": None, "lignes": lignes}
    return _carte(formules=[formule], extra=[_produit("PLAT", "Plat", []), _produit("DESSERT", "Dessert", [])])


def _du_menu(choix: list[dict]) -> dict:
    return {"code_caisse": "MENU", "quantite": 1, "choix": choix}


def _c(code: str, quantite: int = 1, **plus) -> dict:
    return {"option_code": code, "quantite": quantite, "choix": [], **plus}


LIGNES = [{"nom": "Plat", "codes": ["PLAT"]}, {"nom": "Dessert", "codes": ["DESSERT"]}]


def test_formule_quantite_de_choix_invalide():
    r = _refus(_menu(LIGNES), _du_menu([_c("PLAT", 0)]))
    _verifie(r, "ARGUMENT_INVALIDE", "Quantité de choix invalide.", TSC.quantite_de_choix_invalide, "quantite")


def test_choix_hors_formule():
    r = _refus(_menu(LIGNES), _du_menu([_c("PIZZA")]))
    _verifie(r, "HORS_CARTE", "Ce choix n'existe pas dans cette formule.", TSC.choix_hors_formule)
    assert r.faits["code"] == "PIZZA" and r.faits["raison"] == "choix_hors_liste"


def test_element_de_formule_en_rupture():
    r = _refus(_menu(LIGNES), _du_menu([_c("PLAT")]), {"PLAT"})
    _verifie(r, "RUPTURE", "Un élément de la formule n'est plus disponible.", TSC.element_de_formule_indisponible)
    assert r.faits == {"code": "PLAT"}


def test_trop_de_choix_pour_la_ligne_de_la_formule():
    r = _refus(_menu(LIGNES), _du_menu([_c("PLAT", 2)]))
    _verifie(r, "MAXIMUM_ATTEINT", "Pas plus de 1 pour : Plat.", TSC.pas_plus_pour)
    assert r.faits == {"groupe": "Plat", "nom": "Plat", "maximum": 1}


def test_ligne_de_formule_obligatoire():
    r = _refus(_menu(LIGNES), _du_menu([_c("PLAT")]))
    _verifie(r, "CHOIX_OBLIGATOIRE", "Il faut choisir : Dessert.", TSC.choix_obligatoire)


def test_retrait_inconnu_dans_la_formule():
    r = _refus(_menu(LIGNES), _du_menu([_c("PLAT", retires=["sauce"]), _c("DESSERT")]))
    _verifie(r, "HORS_CARTE", "On ne peut pas retirer : sauce.", TSC.ne_peut_pas_retirer)
    assert r.faits == {"code": "PLAT", "retire": "sauce"}


def test_une_seule_alternative():
    lignes = [{"nom": "Plat", "codes": ["PLAT", "DESSERT"], "alternatives": [{"codes": ["PLAT"], "quantite": 2}, {"codes": ["DESSERT"], "quantite": 2}]}]
    r = _refus(_menu(lignes), _du_menu([_c("PLAT"), _c("DESSERT")]))
    _verifie(r, "HORS_CARTE", "Une seule alternative.", TSC.une_seule_alternative)


# --- les lignes -------------------------------------------------------------------------------------------------------------------------------------


def test_quantite_de_ligne_invalide():
    r = _refus(_carte(), {"code_caisse": "PIZZA", "quantite": 0})
    _verifie(r, "ARGUMENT_INVALIDE", "Quantité invalide.", TSC.quantite_invalide, "quantite")
    assert r.faits == {"ligne": 1}


def test_produit_hors_carte():
    r = _refus(_carte(), {"code_caisse": "FANTOME", "quantite": 1})
    _verifie(r, "HORS_CARTE", "Ce produit n'est pas à la carte.", TSC.produit_hors_carte)
    assert r.faits == {"code": "FANTOME"}


def test_produit_en_rupture():
    r = _refus(_carte(), {"code_caisse": "PIZZA", "quantite": 1}, {"PIZZA"})
    _verifie(r, "RUPTURE", "Pizza n'est plus disponible.", TS.n_est_plus_disponible)
    assert r.faits == {"code": "PIZZA", "nom": "Pizza"}


def test_prix_different_de_la_carte():
    r = _refus(_carte(), {"code_caisse": "PIZZA", "quantite": 1, "prix_unitaire": 1})
    _verifie(r, "REFUSEE", "Le prix ne correspond pas à la carte.", TSC.prix_different)
    assert r.faits == {"raison": "prix_different", "code": "PIZZA"}


def test_retrait_inconnu_sur_la_ligne():
    r = _refus(_carte(), {"code_caisse": "PIZZA", "quantite": 1, "retires": ["olives"]})
    _verifie(r, "HORS_CARTE", "On ne peut pas retirer : olives.", TSC.ne_peut_pas_retirer)
    assert r.faits == {"code": "PIZZA", "retire": "olives"}

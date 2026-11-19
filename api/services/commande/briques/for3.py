"""[.mark] Brique FOR3 : la ligne de formule limitée à un sous-ensemble (inventaire, famille 5 ; 7 cartes sur 44).

Une ligne n'accepte pas toute sa catégorie : ``inclus`` (les seuls codes permis), ``exclus`` (les codes écartés), ``prix_max`` (le prix seul du produit, au plus).
Un produit hors de la ligne est refusé avec la raison ``hors_sous_ensemble`` et les choix de l'étape. Un produit « du moment » (ART3) n'entre dans une ligne limitée
que s'il y est coché (``inclus``), jamais déduit d'un prix ni d'une catégorie (D34, conflit 1). La règle qui porte un chiffre (``prix_max``) est dite par le code avant
la phrase du modèle, dans sa forme prouvée au banc B11 (point 2) ; le nom de la formule et celui de l'étape viennent de la carte.
"""

from __future__ import annotations

from typing import Any

from api.db.bases_clients import recherche_liste
from api.db.bases_clients.recherche_liste import Element
from api.services.commande.briques.registre import Brique, enregistrer

RAISON = "hors_sous_ensemble"


def _limitee(ligne: dict[str, Any]) -> bool:
    return bool(ligne.get("inclus") or ligne.get("exclus") or ligne.get("prix_max") is not None)


def brique_for3_refuser_hors_liste(ligne: dict[str, Any], produit: dict[str, Any], declinaison: dict[str, Any], prix: int) -> bool:
    """Vrai : la ligne accepte ce produit à cette déclinaison ; faux : son filtre l'écarte."""
    code = declinaison["code_caisse"]
    if code in (ligne.get("exclus") or []):
        return False
    if ligne.get("inclus"):
        return code in ligne["inclus"]
    if produit.get("du_moment") and _limitee(ligne):
        return False  # D34 (conflit 1) : un produit du moment n'entre dans une ligne limitée que coché dans ``inclus``
    if ligne.get("prix_max") is not None and prix > int(ligne["prix_max"]):
        return False
    return True


def hors_de_la_ligne(etapes: list[dict[str, Any]], mot: str) -> dict[str, Any] | None:
    """Le mot est un produit que le filtre d'une étape écarte : le refus (raison, étape, choix de l'étape) ; ``None`` sinon."""
    for g in etapes:
        hors = g.get("hors_ligne") or []
        if not hors:
            continue
        elements = [Element(h["code"], h["nom"], (h["produit"],), g["nom"]) for h in hors]
        if recherche_liste.chercher(elements, mot)["statut"] == "RETENU":
            return {"raison": RAISON, "valeur": mot, "etape": g["nom"], "choix": [o["nom"] for o in g["options"] if o["vendable"] and not o["rupture"]],
                    "prix_max": g.get("prix_max")}
    return None


def phrase_de_la_regle(formule: str, etape: str, prix_max: int) -> str:
    """La règle chiffrée, dite par le code, dans la forme prouvée en B11 (« Dans la formule complète, le dessert se choisit parmi ceux à deux euros. ») ; le nom de
    la formule et celui de l'étape sont ceux de la carte (D72 et la consigne du 19/11 : le texte prouvé ne change pas, ses mots viennent de la donnée)."""
    from api.services.mots_dits import montant_en_lettres

    return f"Dans la {formule.lower()}, le {etape.lower()} se choisit parmi ceux à {montant_en_lettres(int(prix_max))}."


def _sans(carte: dict) -> dict:
    for f in carte["formules"]:
        for ligne in f["lignes"]:
            for cle in ("inclus", "exclus", "prix_max"):
                ligne.pop(cle, None)
    return carte


enregistrer(Brique(
    "FOR3", "formules", "C", (("formules", "lignes"),), brique_for3_refuser_hors_liste,
    change_la_fiche_du_modele=True, vue_sur_carte=True, sans_la_brique=_sans, carte_d_essai="briques/FOR3",
    phrase="un produit hors de la ligne est refusé (hors_sous_ensemble) avec les choix ; la règle chiffrée est dite par le code",
))

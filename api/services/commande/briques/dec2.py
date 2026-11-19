"""[.mark] Brique DEC2 : la taille qui fixe le nombre d'éléments (inventaire, famille 2 ; règle du conflit D31).

Le minimum et le maximum d'un groupe viennent d'abord de la déclinaison choisie (``declinaison.quotas[groupe]``), sinon du groupe. Le nombre vit sur le
groupe ; une table « déclinaison x groupe » le surcharge pour une taille ; une formule ne le change jamais. Une seule règle, ici.
"""

from __future__ import annotations

from typing import Any

from api.services.commande.briques.registre import Brique, enregistrer


def brique_dec2_quota_selon_la_declinaison(groupe: dict[str, Any], declinaison: dict[str, Any] | None) -> dict[str, Any]:
    """Le groupe tel que CETTE déclinaison le veut : ``min`` et ``max`` surchargés quand elle les fixe pour ce groupe, le groupe sinon (aucune copie de trop)."""
    fixe = ((declinaison or {}).get("quotas") or {}).get(groupe["id"])
    if not fixe:
        return groupe
    return {**groupe, "min": fixe.get("min", groupe["min"]), "max": fixe.get("max", groupe["max"])}


def appliquer_les_quotas(groupes: list[dict[str, Any]], declinaison: dict[str, Any] | None) -> list[dict[str, Any]]:
    return [brique_dec2_quota_selon_la_declinaison(g, declinaison) for g in groupes]


def _sans(carte: dict) -> dict:
    for p in carte["produits"]:
        for d in p["declinaisons"]:
            d.pop("quotas", None)
    return carte


enregistrer(Brique(
    "DEC2", "declinaison", "C", (("declinaisons", "quotas"),), brique_dec2_quota_selon_la_declinaison,
    change_la_fiche_du_modele=True, vue_sur_carte=True, sans_la_brique=_sans, carte_d_essai="briques/DEC2",
    phrase="la question d'un groupe porte le minimum et le maximum de la taille choisie",
))

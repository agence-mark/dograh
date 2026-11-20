"""[.mark] Brique INF7 : la nutrition et le degré (inventaire, famille 9).

La donnée est celle du format HubRise (``nutrition.per_100_values`` : ``per``, ``energy`` {unit, lower, upper?}, nutriments « nombre + unité » ; ``degre`` = ``alcohol_percentage``).
Elle est rendue telle quelle ; sans donnée : ``None`` (« je ne peux pas vous le confirmer »). Jamais calculée ni arrondie par le code.
"""

from __future__ import annotations

from typing import Any

from api.services.commande.briques.registre import Brique, enregistrer


def brique_inf7_depuis_la_donnee(nutrition: dict[str, Any] | None, degre: float | None) -> dict[str, Any] | None:
    """``{"pour": "100 g", "energie": {...}, "nutriments": {...}, "degre": x}`` avec ce que la donnée dit ; ``None`` quand elle ne dit rien."""
    valeurs = dict((nutrition or {}).get("per_100_values") or {})
    sortie: dict[str, Any] = {}
    if valeurs:
        if valeurs.get("per"):
            sortie["pour"] = valeurs.pop("per")
        if valeurs.get("energy"):
            sortie["energie"] = valeurs.pop("energy")
        if valeurs:
            sortie["nutriments"] = valeurs
    if degre is not None:
        sortie["degre"] = degre
    return sortie or None


def _sans(carte: dict) -> dict:
    for p in carte["produits"]:
        p["nutrition"] = None
        p["degre"] = None
    return carte


enregistrer(Brique(
    "INF7", "informations", "C", (("produits", "nutrition"),), brique_inf7_depuis_la_donnee,
    change_la_fiche_du_modele=False, vue_sur_carte=True, sans_la_brique=_sans, carte_d_essai="briques/INF7",
    phrase="la nutrition et le degré sont dits d'après la donnée ; sans donnée : « je ne peux pas vous le confirmer »",
))

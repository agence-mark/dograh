"""[.mark] Brique PRX9 : le délai minimal et le nombre minimal de personnes (inventaire, famille 6 ; traiteur, extraits de recherche, aucune carte lue).

``delai_minimal_heures`` : un article se commande au plus tôt ce nombre d'heures après maintenant ; la règle rend la date la plus proche. ``personnes_min`` : un nombre de
personnes en dessous du minimum est refusé, QUAND la case ``personnes`` existe dans la fiche (objet ouvert par la carte, FOR10) ; sans cette case, la donnée est lue et n'agit
pas (jamais un refus que le modèle ne pourrait pas corriger). Code seulement, aucune case nouvelle.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from api.services.commande.briques.registre import Brique, enregistrer

RAISON_DU_DELAI = "delai_minimal_non_respecte"
RAISON_DES_PERSONNES = "personnes_minimales_non_atteintes"


def brique_prx9_date_la_plus_proche(produit: dict[str, Any], maintenant: datetime, voulu: datetime | None, personnes: int | None = None) -> dict[str, Any] | None:
    """Le refus quand ``voulu`` (l'heure voulue, ou maintenant) est avant ``maintenant`` plus le délai minimal, avec ``date_la_plus_proche`` ; ou quand ``personnes`` est sous
    le minimum ; sinon ``None``."""
    delai = produit.get("delai_minimal_heures")
    if delai:
        plus_proche = maintenant + timedelta(hours=int(delai))
        if (voulu or maintenant) < plus_proche:
            return {"raison": RAISON_DU_DELAI, "article": produit["nom"], "delai_minimal_heures": int(delai), "date_la_plus_proche": plus_proche.isoformat()}
    minimum = produit.get("personnes_min")
    if minimum and personnes is not None and personnes < int(minimum):
        return {"raison": RAISON_DES_PERSONNES, "article": produit["nom"], "personnes_min": int(minimum)}
    return None


def _sans(carte: dict) -> dict:
    for p in carte["produits"]:
        p["delai_minimal_heures"], p["personnes_min"] = None, None
    return carte


enregistrer(Brique(
    "PRX9", "prix_et_conditions", "C", (("produits", "delai_minimal_heures"), ("produits", "personnes_min")), brique_prx9_date_la_plus_proche,
    change_la_fiche_du_modele=False, vue_sur_carte=False, sans_la_brique=_sans, carte_d_essai="briques/PRX9",
    phrase="avant le délai minimal, refus avec la date la plus proche ; sous le minimum de personnes, refus quand la case existe",
))

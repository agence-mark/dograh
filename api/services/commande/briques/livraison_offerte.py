"""[.mark] Brique OFF4 : la livraison offerte (inventaire, famille 8 ; A9 : « livraison offerte dès 25 € »).

La zone de livraison porte ``gratuite_des`` (le sous-total à partir duquel les frais sont à zéro). Au-delà, le code retire les frais et le pose en fait (``livraison_offerte``), que le modèle dit (C6 n° 11) ; sous
le seuil, les frais de la zone restent ; à emporter ou sur place, il n'y a rien à offrir. Code seulement : le seuil se règle déjà sur la zone, aucune case de la fiche ne change.
"""

from __future__ import annotations

from typing import Any

from api.services.commande.briques.registre import Brique, enregistrer


def brique_off4_frais_retires(zone: dict[str, Any], sous_total: int) -> dict[str, Any]:
    """``{"frais", "livraison_offerte"}`` : les frais de la zone pour ce sous-total ; ``livraison_offerte`` quand le seuil est atteint ET que la zone avait des frais à retirer."""
    seuil = zone.get("gratuite_des")
    frais = int(zone.get("frais") or 0)
    if seuil is not None and sous_total >= seuil:
        return {"frais": 0, "livraison_offerte": frais > 0}
    return {"frais": frais, "livraison_offerte": False}


enregistrer(Brique(
    "OFF4", "offres", "C", (), brique_off4_frais_retires, change_la_fiche_du_modele=False, vue_sur_carte=True, sans_la_brique=lambda carte: carte, carte_d_essai="briques/OFF4",
    phrase="au-delà du seuil de la zone, les frais de livraison sont à zéro : un fait (livraison_offerte) que le modèle dit",
))

"""[.mark] Brique INF2 : les allergènes d'une option (inventaire, famille 9 ; audit de généricité § 2 : « La sauce algérienne contient de la moutarde ? »).

Jamais vue sur une carte : côté code seulement, aucune case nouvelle. Les allergènes d'une OPTION sont une donnée comme ceux du produit (``None`` = inconnu, ``[]`` = aucun, validés
seulement). La règle combine le produit et les options choisies : un allergène que l'un d'eux porte est présent ; sans présence, un seul inconnu rend l'ensemble inconnu.
Le nom d'une option qui dit un allergène (« Pistache ») prouve une présence, jamais une absence.
"""

from __future__ import annotations

from typing import Any

from api.services.commande.briques.registre import Brique, enregistrer


def brique_inf2_produit_et_options(allergenes_du_produit: list[str] | None, options_choisies: list[dict[str, Any]], code: str) -> str:
    """``present`` | ``absent_de_la_fiche`` | ``inconnu`` pour ``code``, le produit et les options choisies ensemble (chaque option : ``allergenes``, ``signalements_du_nom``)."""
    donnees = [allergenes_du_produit, *(o.get("allergenes") for o in options_choisies)]
    if any(d is not None and code in d for d in donnees) or any(code in (o.get("signalements_du_nom") or []) for o in options_choisies):
        return "present"
    return "inconnu" if any(d is None for d in donnees) else "absent_de_la_fiche"


def _sans(carte: dict) -> dict:
    for g in carte["groupes"]:
        for o in g["options"]:
            o["allergenes"] = None
    return carte


enregistrer(Brique(
    "INF2", "informations", "C", (("options", "allergenes"),), brique_inf2_produit_et_options,
    change_la_fiche_du_modele=False, vue_sur_carte=False, sans_la_brique=_sans, carte_d_essai="briques/INF2",
    phrase="les allergènes de l'option s'ajoutent à ceux du produit ; une option sans donnée reste inconnue ; aucune case nouvelle",
))

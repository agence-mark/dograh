"""[.mark] Les conditions de vente d'une ligne (chantier Partie 1, lot 12 : briques PRX1, PRX3, PRX8, PRX9), appelées en un seul endroit.

Chaque règle reste sa fonction nommée dans son module (``disponibilite_jour_heure.py``, ``disponibilite_par_mode.py``, ``quantite_maximale.py``, ``delai_minimal.py``) ; ce module n'en ajoute aucune : il les enchaîne dans l'ordre où le
client les rencontre (la plage, le mode, le maximum, le délai) et rend le premier refus, ou ``None``. Les refus rendent des faits (raison, plage, maximum, modes, date), jamais
une phrase : c'est le modèle qui parle.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from api.services.commande.briques import disponibilite_jour_heure, disponibilite_par_mode, quantite_maximale, delai_minimal


def refus_de_la_ligne(
    objet: dict[str, Any], declinaison: dict[str, Any] | None, mode: str | None, quantite: int, deja_pris: int, maintenant: datetime | None, servi_le: datetime | None,
) -> dict[str, Any] | None:
    """Le premier refus d'une ligne (``objet`` : le produit ou la formule, ``declinaison`` : celle de la ligne) ; ``deja_pris`` : la quantité du même produit dans les lignes d'avant."""
    refus = disponibilite_jour_heure.refus_de_l_article(objet)
    if refus is None and declinaison is not None and declinaison.get("indisponible") is not None:
        refus = {"raison": disponibilite_jour_heure.RAISON, "article": f"{objet['nom']} {declinaison['nom']}", "plage": declinaison["indisponible"]}
    refus = refus or disponibilite_par_mode.brique_prx3_refuser_des_que_le_mode_est_connu(objet, mode) or quantite_maximale.brique_prx8_refuser_au_dela(objet, deja_pris, quantite)
    if refus is None and maintenant is not None:
        refus = delai_minimal.brique_prx9_date_la_plus_proche(objet, maintenant, servi_le)
    return refus


def refus_de_l_option(option: dict[str, Any], mode: str | None) -> dict[str, Any] | None:
    """Le refus d'une option hors de sa plage à ce moment, ou qui ne se vend pas dans ce mode ; ``None`` sinon."""
    if option.get("indisponible") is not None:
        return {"raison": disponibilite_jour_heure.RAISON, "article": option["nom"], "plage": option["indisponible"]}
    return disponibilite_par_mode.brique_prx3_refuser_des_que_le_mode_est_connu(option, mode)

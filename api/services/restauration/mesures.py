"""[.mark] Module Restauration, lot 7 (W13) : ce que les outils du module MESURENT, écrit dans la fiche de l'appel (le Dashboard du lot 23 les lit).

Le mécanisme (liste fermée des noms, écriture, décompte) est commun : ``integrations/connectors/mesures.py``. Ici, la correspondance entre le retour fermé d'un
outil (statut, faits) et le nom de la mesure :

| Mesure | Quand |
|---|---|
| ``commande.hors_zone`` | l'adresse est hors des zones livrées |
| ``commande.minimum_non_atteint`` | le minimum de la zone ou du mode n'est pas atteint |
| ``commande.rupture`` | un article demandé est en rupture |
| ``commande.hors_catalogue`` | l'article demandé n'existe pas au catalogue |
| ``commande.fermeture`` | établissement fermé, type de commande en pause, livraison terminée |
| ``commande.moyen_refuse`` | le moyen de paiement n'est pas accepté, ou dépasse le plafond d'un titre-restaurant |
| ``commande.enregistree`` / ``commande.transmise`` | la commande est passée (détail : le mode) / transmise à l'équipe |
| ``commande.remise_appliquee`` | une remise vient du comptoir, une fois par tâche |
| ``commande.indisponible`` | la base ou la caisse ne répond pas |
| ``reservation.enregistree`` | la réservation est faite |
| ``reservation.complet`` / ``reservation.refusee`` | complet / refusée par une règle (détail : la raison) |
| ``reservation.indisponible`` | la base ne répond pas |

⛔ Ne lève jamais.
"""

from __future__ import annotations

from typing import Any

from api.services.integrations.connectors import mesures

_COMMANDE = {
    "HORS_ZONE": "commande.hors_zone", "MINIMUM_NON_ATTEINT": "commande.minimum_non_atteint", "RUPTURE": "commande.rupture",
    "HORS_CARTE": "commande.hors_catalogue", "FERME": "commande.fermeture", "PAUSE_TYPE": "commande.fermeture", "LIVRAISON_TERMINEE": "commande.fermeture",
    "MOYEN_NON_ACCEPTE": "commande.moyen_refuse", "PLAFOND_TITRE_RESTAURANT": "commande.moyen_refuse", "ENREGISTREE": "commande.enregistree",
    "TRANSMISE": "commande.transmise", "INDISPONIBLE": "commande.indisponible",
}
MODES = frozenset({"emporter", "livraison", "sur_place"})


def est_un_refus(retour: dict[str, Any]) -> bool:
    """Un refus compté dans l'état de la tâche : tout échec typé du retour (hors panne : ce n'est pas la faute de la demande)."""
    from api.services.integrations.connectors import typage

    return typage.type_du_statut(retour.get("statut"), retour.get("faits") if isinstance(retour.get("faits"), dict) else None) not in (None, "outage")


def de_la_commande(fiche: Any, outil: str, retour: dict[str, Any]) -> None:
    try:
        statut = retour.get("statut")
        faits = retour.get("faits") if isinstance(retour.get("faits"), dict) else {}
        nom = f"commande.{outil}"
        mesure = _COMMANDE.get(statut)
        if mesure is not None:
            mode = faits.get("mode")
            mesures.ecrire(fiche, mesure, nom, mode if mode in MODES and mesure == "commande.enregistree" else None)
        if (faits.get("total_remises") or 0) > 0 and not any(
            m["mesure"] == "commande.remise_appliquee" and m["tache"] == mesures.tache_en_cours(fiche) for m in mesures.lues(fiche)
        ):
            mesures.ecrire(fiche, "commande.remise_appliquee", nom)
    except Exception:  # noqa: BLE001
        pass


def de_la_reservation(fiche: Any, outil: str, retour: dict[str, Any]) -> None:
    try:
        statut = retour.get("statut")
        faits = retour.get("faits") if isinstance(retour.get("faits"), dict) else {}
        nom = f"reservation.{outil}"
        if statut == "ENREGISTREE":
            mesures.ecrire(fiche, "reservation.enregistree", nom)
        elif statut == "REFUSEE":
            if faits.get("detail") == "complet":
                mesures.ecrire(fiche, "reservation.complet", nom)
            else:
                mesures.ecrire(fiche, "reservation.refusee", nom, str(faits.get("detail") or faits.get("raison") or "") or None)
        elif statut == "INDISPONIBLE":
            mesures.ecrire(fiche, "reservation.indisponible", nom)
    except Exception:  # noqa: BLE001
        pass

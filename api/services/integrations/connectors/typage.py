"""[.mark] Module Restauration, lot 7 (W21) : les appels aux systèmes TYPÉS. Un échec porte un type d'une liste fermée, jamais le texte d'un fournisseur.

- ``slot_taken`` : la place ou l'article est pris (complet, rupture, fermé) ; ``bad_request`` : la demande ne tient pas (hors zone, minimum, argument,
  moyen refusé) ; ``not_found`` : rien de tel ; ``outage`` : le système ne répond pas ; ``uncertain_outcome`` : une ÉCRITURE a dépassé son délai, on ne
  sait pas si elle a eu lieu (jamais rejouée à l'aveugle).
- Une seule nouvelle tentative, et seulement sur une opération SÛRE (une lecture) en panne (``outage``) : jamais une écriture (``peut_rejouer``).
- Chaque échec typé et chaque délai dépassé est mesuré (``mesures``).
"""

from __future__ import annotations

from typing import Any

TYPES = ("slot_taken", "bad_request", "not_found", "outage", "uncertain_outcome")

_PAR_STATUT = {
    "RUPTURE": "slot_taken", "FERME": "slot_taken", "PAUSE_TYPE": "slot_taken", "LIVRAISON_TERMINEE": "slot_taken", "MAXIMUM_ATTEINT": "slot_taken",
    "INTROUVABLE": "not_found", "HORS_CARTE": "not_found",
    "ARGUMENT_INVALIDE": "bad_request", "HORS_ZONE": "bad_request", "MINIMUM_NON_ATTEINT": "bad_request", "MOYEN_NON_ACCEPTE": "bad_request",
    "PLAFOND_TITRE_RESTAURANT": "bad_request", "INTERDIT": "bad_request",
    "INDISPONIBLE": "outage",
}


def type_du_statut(statut: str | None, faits: dict[str, Any] | None = None) -> str | None:
    """Le type de l'échec d'un retour fermé d'outil, ``None`` si ce n'est pas un échec (``OK``, ``INCOMPLETE``, ``ENREGISTREE``…)."""
    if statut in _PAR_STATUT:
        return _PAR_STATUT[statut]
    if statut == "REFUSEE":
        if (faits or {}).get("detail") == "complet":
            return "slot_taken"
        return "outage" if (faits or {}).get("raison") == "caisse_injoignable" else "bad_request"
    return None


def type_de_l_echec(statut: str, donnees: dict[str, Any] | None, message: str | None, ecrit: bool) -> str | None:
    """Le type d'un résultat d'exécution (``ok`` | ``repli`` | ``erreur``) ; ``None`` : pas un échec."""
    if statut == "repli":
        return "uncertain_outcome" if ecrit and message == "deadline passed" else "outage"
    if statut == "erreur":
        return "bad_request"
    if isinstance(donnees, dict):
        faits = donnees.get("faits")
        return type_du_statut(donnees.get("statut"), faits if isinstance(faits, dict) else None)
    return None


def peut_rejouer(ecrit: bool, type_: str | None) -> bool:
    """Une seule nouvelle tentative : une lecture, en panne. Jamais une écriture, jamais un autre type."""
    return (not ecrit) and type_ == "outage"

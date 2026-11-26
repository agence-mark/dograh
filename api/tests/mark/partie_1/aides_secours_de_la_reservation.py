"""[.mark] Aide des tests du lot 7b-C3 : les faits qu'un refus de la réservation donne au modèle (``resultats[].faits`` de la porte), sur lesquels un texte de secours se refait."""

from __future__ import annotations

from typing import Any

from api.services.actions_communes.resultat import Resultat
from api.services.reservation import porte as PORTE


def faits_publics(r: Resultat, operation: str = "reserver") -> dict[str, Any]:
    """Ce que le modèle lit d'un résultat du module : ``PORTE._resultat_public`` (les faits sans ``candidats``, ``reservations`` ni ``tables``)."""
    return PORTE._resultat_public(operation, r)["faits"]

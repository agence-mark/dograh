"""[.mark] Module Restauration, lot 20 : l'ADRESSE INTERNE de la caisse de démo (la seule que la prise HubRise puisse appeler en plus de HubRise, Labo seulement, D4 et D5)."""

from __future__ import annotations

from api.constants import BACKEND_API_ENDPOINT

CHEMIN_DE_LA_CAISSE = "/api/v1/restauration/caisse-demo/v1"


def adresse_de_la_caisse() -> str:
    """L'adresse de la caisse de démo sur CE serveur (sans barre finale)."""
    return BACKEND_API_ENDPOINT.rstrip("/") + CHEMIN_DE_LA_CAISSE

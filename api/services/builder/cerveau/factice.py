"""[.mark] Builder : le cerveau factice (tests et essais sans dépense).

Il rejoue des tours écrits d'avance. Chaque tour est une liste d'événements du contrat de ``appel.py`` ; les
raccourcis ``texte(...)``, ``appel(...)`` et ``tour(...)`` évitent de les écrire à la main. Il garde les
requêtes reçues (``requetes``) pour qu'un test vérifie ce que le moteur lui a envoyé.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from api.services.builder.cerveau.appel import ErreurCerveau


def texte(contenu: str) -> dict[str, Any]:
    return {"type": "texte", "texte": contenu}


def appel(nom: str, arguments: dict[str, Any] | None = None, identifiant: str | None = None) -> dict[str, Any]:
    return {"type": "appel", "id": identifiant or f"appel-{nom}", "nom": nom, "arguments": arguments or {}}


def tour(*evenements: dict[str, Any], entree: int = 100, sortie: int = 50) -> list[dict[str, Any]]:
    """Un tour complet : ses événements, puis l'usage et la fin (« outils » s'il y a des appels)."""
    a_des_appels = any(e["type"] == "appel" for e in evenements)
    return [
        *evenements,
        {"type": "usage", "entree": entree, "sortie": sortie, "cache_lu": 0, "cache_ecrit": 0},
        {"type": "fin", "raison": "outils" if a_des_appels else "fin"},
    ]


class CerveauFactice:
    def __init__(self, *tours: list[dict[str, Any]] | ErreurCerveau):
        self._tours = list(tours)
        self.requetes: list[dict[str, Any]] = []

    async def tour(
        self, *, systeme: str, messages: list[dict[str, Any]], outils: list[dict[str, Any]]
    ) -> AsyncIterator[dict[str, Any]]:
        self.requetes.append({"systeme": systeme, "messages": [dict(m) for m in messages], "outils": outils})
        if not self._tours:
            raise AssertionError("The fake brain has no turn left to play.")
        suivant = self._tours.pop(0)
        if isinstance(suivant, ErreurCerveau):
            raise suivant
        for evenement in suivant:
            yield evenement

"""[.mark] Clôture, SA-3 : un problème de la fenêtre « Publier » qui se traduit PAR IDENTIFIANT.

``Probleme`` est une ``str`` (la phrase anglaise, que l'API, le MCP et les journaux continuent de lire) qui porte en plus son
``code`` et ses ``parametres`` : l'écran traduit le code dans les deux langues et remplit les paramètres, et ne montre la phrase
anglaise que pour un code qu'il ne connaît pas. Aucun texte n'est traduit côté serveur.
"""

from __future__ import annotations

from typing import Any


class Probleme(str):
    code: str | None
    parametres: dict[str, Any]
    etape: str | None
    forme: str | None  # "prefixe" : « étape · message » ; "suffixe" : « message [étape] » ; None : le message seul

    def __new__(cls, message: str, code: str | None = None, *, etape: str | None = None, forme: str | None = None, **parametres: Any):
        objet = super().__new__(cls, message)
        objet.code = code
        objet.parametres = parametres
        objet.etape = etape
        objet.forme = forme
        return objet


def detail_de(probleme: Any) -> dict[str, Any]:
    """La part structurée d'un problème (``code`` vide : l'écran garde la phrase telle qu'elle est)."""
    return {
        "code": getattr(probleme, "code", None),
        "parametres": dict(getattr(probleme, "parametres", None) or {}),
        "etape": getattr(probleme, "etape", None),
        "forme": getattr(probleme, "forme", None),
    }

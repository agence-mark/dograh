"""[.mark] U3 sexies point 2 : les réponses simulées d'un outil HTTP.

Servies à l'essai et au banc SEULEMENT. ``execute_http_tool`` ne les lit que si l'appelant passe ``simuler=True`` ; un
appel réel ne le passe jamais.
"""

from __future__ import annotations

from typing import Any


def choisir(config: dict[str, Any], arguments: dict[str, Any]) -> dict[str, Any] | None:
    """La première réponse simulée dont ``quand`` correspond aux arguments (vide = toujours), ``None`` s'il n'y en a pas."""
    for r in config.get("reponses_simulees") or []:
        quand = r.get("quand") or {}
        if all(str((arguments or {}).get(k)) == str(v) for k, v in quand.items()):
            return r
    return None


def en_reponse(simulee: dict[str, Any]) -> dict[str, Any]:
    statut = int(simulee.get("statut") or 200)
    donnees = simulee.get("donnees")
    return {
        "status": "error" if statut >= 400 else "success",
        "status_code": statut,
        "data": donnees if donnees is not None else {},
        "simulee": True,
    }

"""[.mark] Clôture, lot A (D23) : le « quoi » d'une ligne du journal : le GESTE (un verbe) et l'OBJET touché (son type et son nom).

``acces.py`` écrit dans ``detail`` la route et les paramètres d'adresse de la requête (``cible``), jamais le corps. À la lecture, une page du journal
résout les noms des objets en UNE requête (``db_client.noms_des_cibles``, filtrée par l'organisation de chaque ligne). Une ligne d'avant, sans cible,
reste lisible : l'écran retombe sur le libellé de sa permission. Pur : aucune base ici.
"""

from __future__ import annotations

from typing import Any

# Le paramètre d'adresse qui désigne l'objet, du plus précis au moins précis.
TYPES_DE_CIBLE: dict[str, str] = {
    "tool_uuid": "outil",
    "document_uuid": "document",
    "campaign_id": "campagne",
    "folder_id": "dossier",
    "workflow_id": "agent",
}

# Le dernier segment fixe de la route dit le geste ; sans lui : supprimer (DELETE), créer (POST sur la collection), modifier (le reste).
VERBES_DES_SEGMENTS: dict[str, str] = {
    "publish": "publier",
    "publier": "publier",
    "fusion": "publier",
    "start": "lancer",
    "resume": "lancer",
    "redial": "lancer",
    "pause": "suspendre",
    "duplicate": "dupliquer",
    "copier": "dupliquer",
    "restaurer": "restaurer",
    "archiver": "archiver",
    "unarchive": "restaurer",
    "essai": "tester",
    "test": "tester",
    "premier-essai": "tester",
    "refresh": "actualiser",
    "create-draft": "modifier",
    "runs": "tester",
    "sessions": "tester",
}


def cible_de(detail: Any) -> tuple[str, str] | None:
    """``(type, identifiant)`` de l'objet d'une ligne, ou ``None`` pour une ligne sans cible (d'avant, ou une route sans paramètre)."""
    cible = detail.get("cible") if isinstance(detail, dict) else None
    if not isinstance(cible, dict):
        return None
    for parametre, type_ in TYPES_DE_CIBLE.items():
        if parametre in cible and cible[parametre] not in (None, ""):
            return type_, str(cible[parametre])
    return None


def verbe_de(detail: Any) -> str | None:
    """Le geste d'une ligne d'écriture : ``publier``, ``supprimer``, ``creer``, ``modifier``... ``None`` si la ligne n'a pas de route."""
    route = detail.get("route") if isinstance(detail, dict) else None
    if not isinstance(route, str) or " " not in route:
        return None
    methode, chemin = route.split(" ", 1)
    segments = [s for s in chemin.strip("/").split("/") if s]
    for segment in reversed(segments):
        if not segment.startswith("{") and segment in VERBES_DES_SEGMENTS:
            return VERBES_DES_SEGMENTS[segment]
    if methode == "DELETE":
        return "supprimer"
    if methode == "POST" and (not segments or segments[-1] in {"create", "definition", "template"} or chemin.endswith("/") or not any(s.startswith("{") for s in segments)):
        return "creer"
    return "modifier"

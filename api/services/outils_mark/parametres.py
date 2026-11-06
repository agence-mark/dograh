"""[.mark] U3 sexies point 2 : l'emplacement, les valeurs permises et le défaut de chaque paramètre d'un outil HTTP."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

EMPLACEMENTS = ("chemin", "requete", "corps", "en_tete")


@dataclass
class Repartition:
    """Où part chaque valeur. ``non_declares`` : ce qu'aucun paramètre ne place (valeurs préréglées, hors liste) suit le
    comportement d'avant : corps pour POST/PUT/PATCH, requête pour GET/DELETE."""

    chemin: dict[str, Any] = field(default_factory=dict)
    requete: dict[str, Any] = field(default_factory=dict)
    corps: dict[str, Any] = field(default_factory=dict)
    en_tete: dict[str, Any] = field(default_factory=dict)
    non_declares: dict[str, Any] = field(default_factory=dict)


def _declares(config: dict[str, Any]) -> list[dict[str, Any]]:
    return [p for p in (config.get("parameters") or []) if isinstance(p, dict) and p.get("name")]


def appliquer_les_defauts(config: dict[str, Any], arguments: dict[str, Any]) -> dict[str, Any]:
    """Les arguments du modèle, complétés par le défaut des paramètres qu'il n'a pas donnés."""
    complets = dict(arguments or {})
    for p in _declares(config):
        nom = p["name"]
        if complets.get(nom) in (None, "") and p.get("defaut") is not None:
            complets[nom] = p["defaut"]
    return complets


def verifier_les_valeurs(config: dict[str, Any], arguments: dict[str, Any]) -> str | None:
    """Un message si une valeur donnée sort de la liste permise de son paramètre, sinon ``None``."""
    for p in _declares(config):
        permises = p.get("valeurs_permises") or []
        nom = p["name"]
        if not permises or nom not in arguments or arguments[nom] in (None, ""):
            continue
        if str(arguments[nom]) not in [str(v) for v in permises]:
            return f"The value of '{nom}' must be one of: {', '.join(str(v) for v in permises)}."
    return None


def repartir(config: dict[str, Any], arguments: dict[str, Any]) -> Repartition:
    """Range chaque valeur à l'emplacement que son paramètre déclare."""
    place = {p["name"]: p.get("emplacement") for p in _declares(config)}
    r = Repartition()
    for nom, valeur in (arguments or {}).items():
        emplacement = place.get(nom)
        if emplacement == "chemin":
            r.chemin[nom] = valeur
        elif emplacement == "requete":
            r.requete[nom] = valeur
        elif emplacement == "corps":
            r.corps[nom] = valeur
        elif emplacement == "en_tete":
            r.en_tete[nom] = valeur
        else:
            r.non_declares[nom] = valeur
    return r


def valeur_d_en_tete(valeur: Any) -> str:
    if isinstance(valeur, bool):
        return "true" if valeur else "false"
    return str(valeur)

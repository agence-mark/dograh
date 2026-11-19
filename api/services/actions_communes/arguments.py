"""[.mark] La lecture des arguments d'une action, en une seule copie (chantier Partie 1, lot 3 ; S11 de l'audit des rustines).

Reprise de ``commande/action.py`` (``_texte``, ``_entier``, ``_jsonable``), elle-même dupliquée dans ``reservation/action.py`` : la commande et le
service lisent ici ; la réservation y passe au lot 7 (R14).
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any


def lire_un_texte(arguments: dict[str, Any], cle: str) -> str | None:
    """Le texte d'une case, sans espaces autour ; ``None`` pour une case absente ou vide."""
    valeur = arguments.get(cle) if isinstance(arguments, dict) else None
    return (str(valeur).strip() or None) if valeur is not None else None


def lire_un_entier(valeur: Any) -> int | None:
    """Une quantité : ``3``, ``3.0`` ; jamais un booléen, jamais une fraction, jamais un texte (``"2"`` est une faute de forme, lot 3)."""
    if isinstance(valeur, (bool, str)):
        return None
    try:
        nombre = float(valeur)
    except (TypeError, ValueError):
        return None
    return int(nombre) if nombre.is_integer() else None


def en_json(valeur: Any) -> Any:
    """Une copie écrivable en JSON : une date ou une heure devient son texte ISO."""
    if isinstance(valeur, (datetime, date)):
        return valeur.isoformat()
    if isinstance(valeur, dict):
        return {str(k): en_json(v) for k, v in valeur.items()}
    if isinstance(valeur, (list, tuple, set, frozenset)):
        return [en_json(v) for v in valeur]
    return valeur

"""[.mark] Chantier Partie 1, lot 6 (D24) : la phrase d'attente choisie par la case exécutée (lecture de la carte, adresse et zone, réservation
retrouvée, enregistrement), tirée de sa famille (``gabarits/restauration/attentes.json``) sans répétition dans l'appel (``variantes_d_attente``).

Le seuil reste celui de l'outil (``seuil_patience_ms``, 1 200 ms par défaut) : rien n'est dit si l'outil répond avant. Une case sans famille garde
la phrase d'attente de l'outil, comme avant. ⛔ Ne lève jamais.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

FICHIER = Path(__file__).resolve().parents[1] / "gabarits" / "restauration" / "attentes.json"
LECTURE, ZONE, RESERVATION, ENREGISTREMENT = "lecture_de_la_carte", "adresse_et_zone", "reservation_retrouvee", "enregistrement"


@lru_cache(maxsize=1)
def familles() -> dict[str, list[str]]:
    donnees = json.loads(FICHIER.read_text(encoding="utf-8"))
    return {k: [str(v) for v in vs] for k, vs in donnees.items() if not k.startswith("_") and isinstance(vs, list)}


def famille_de_la_case(action: str | None, arguments: Any) -> str | None:
    """La famille d'attente de ce geste, d'après l'action et les cases remplies (jamais d'après les mots)."""
    arguments = arguments if isinstance(arguments, dict) else {}
    if action == "lire":
        return LECTURE
    if action == "retrouver_une_reservation" or arguments.get("retrouver_une_reservation_enregistree"):
        return RESERVATION
    if action == "fiche":
        if arguments.get("c_est_tout") or (isinstance(arguments.get("reponse"), dict) and arguments.get("moyen_de_paiement")):
            return ENREGISTREMENT
        if arguments.get("adresse") or arguments.get("commune"):
            return ZONE
    return None


def config_avec_l_attente(config: dict[str, Any], action: str | None, arguments: Any) -> dict[str, Any]:
    """La configuration de l'outil, avec les variantes d'attente de la famille du geste (sinon telle quelle)."""
    try:
        famille = famille_de_la_case(action, arguments)
        variantes = familles().get(famille) if famille else None
        return {**config, "phrases_attente": list(variantes)} if variantes else config
    except Exception:  # noqa: BLE001
        return config

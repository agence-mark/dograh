"""[.mark] Lot 8, 8c-2 (128) : les phrases d'attente de la restauration, par case exécutée (chantier Partie 1, lot 6, D24).

Les familles sont lues dans ``gabarits/restauration/attentes.json`` ; la famille d'un geste se lit sur l'action et les cases remplies (jamais sur les mots). Le module
« restauration » les pose (``Module.attentes`` = ``api.services.restauration.attentes:attentes``) ; le mécanisme (``outils_mark/attente_par_case.py``) ne connaît ni ce fichier ni
ces noms de cases.
"""

from __future__ import annotations

import json
from collections.abc import Callable
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


def attentes() -> tuple[dict[str, list[str]], Callable[[str | None, Any], str | None]]:
    """Ce que le module donne au mécanisme : les familles de phrases et la fonction qui rend la famille d'un geste."""
    return familles(), famille_de_la_case

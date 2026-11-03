"""[.mark] Marquer un déclenchement de sécurité dans le run (U3 quinquies : « chaque déclenchement est marqué sur la réplique et envoie
l'appel dans À améliorer »).

Écrit pendant l'appel dans ``gathered_context["securite_declenchements"]`` (téléphone ET clavier : le moteur est le même). La file
« À améliorer » (``services/tri/donnees.lire_les_signalements``) lit cette clé ; la page d'un appel affiche chaque entrée avec la
réplique concernée. ⛔ Ne lève jamais.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from loguru import logger

CLE = "securite_declenchements"
MAX_PAR_APPEL = 50
COUCHE_SORTIE = "sortie"
COUCHE_ECOUTE = "ecoute"


def noter(contexte: Any, *, couche: str, nom: str, detail: str = "", extrait: str = "", tour: int | None = None) -> bool:
    """Ajoute un déclenchement. ``False`` : pas de contexte, ou plafond atteint."""
    try:
        if not isinstance(contexte, dict):
            return False
        liste = contexte.setdefault(CLE, [])
        if not isinstance(liste, list) or len(liste) >= MAX_PAR_APPEL:
            return False
        if tour is None:
            from api.services.fiche.traces import CLE_TOUR

            valeur = contexte.get(CLE_TOUR)
            tour = valeur if isinstance(valeur, int) else None
        liste.append(
            {
                "couche": couche,
                "nom": nom,
                "detail": " ".join(str(detail).split())[:200],
                "extrait": " ".join(str(extrait).split())[:200],
                "tour": tour,
                "heure": datetime.now(UTC).isoformat(),
            }
        )
        return True
    except Exception as erreur:  # noqa: BLE001
        logger.warning(f"[securite] déclenchement non noté : {erreur!r}")
        return False

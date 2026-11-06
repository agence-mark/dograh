"""[.mark] Builder, K7 : la dépense du mois (Réglages du Labo > Builder IA > « Par mois (Labo) »).

Une seule lecture, celle des conversations du builder (leur coût est écrit tour après tour par le moteur). Le mois est le mois civil
en UTC. Le plafond lui-même vit dans les réglages du cerveau (``plafond_mois``, 0 = aucun) et se vérifie au démarrage d'un travail
(``fil.lancer``).
"""

from __future__ import annotations

from datetime import UTC, datetime

from api.db import db_client


def debut_du_mois(maintenant: datetime | None = None) -> datetime:
    n = maintenant or datetime.now(UTC)
    return datetime(n.year, n.month, 1, tzinfo=UTC)


async def du_mois(organisation: int | None = None) -> float:  # noqa: ARG001 -- toutes organisations : le coût est celui de .mark
    return round(await db_client.somme_des_couts_depuis(debut_du_mois()), 6)

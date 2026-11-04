"""[.mark] U10 / S3 : la conservation de ce que le widget garde sur le visiteur dans la base de Dograh.

Les sessions du widget portent l'adresse IP et le navigateur du visiteur : ``CONSERVATION_SESSIONS_JOURS`` jours,
puis la ligne est effacée par la purge de nuit (la même tâche que la conservation des appels). L'avis suit son appel
(effacé avec lui, y compris à la demande d'une personne) ; les événements du portail (base du client) se purgent
à 30 jours par ``mark.purger()``. Les compteurs anonymes du widget ne sont pas des données personnelles.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from api.db import db_client
from api.services.site_mark.conversations import CONSERVATION_SESSIONS_JOURS


async def reduire_avis_anciens(maintenant: datetime | None = None) -> int:
    """Réduit les avis gardés en entier sur un run depuis plus de ``CONSERVATION_SESSIONS_JOURS`` jours (point 8 de la revue de contrôle)."""
    avant = (maintenant or datetime.now(UTC)) - timedelta(days=CONSERVATION_SESSIONS_JOURS)
    return await db_client.reduire_avis_gardes_en_entier(avant)


async def purger_sessions(maintenant: datetime | None = None) -> int:
    """Efface les sessions de widget plus vieilles que la durée de conservation ; rend le nombre de lignes."""
    avant = (maintenant or datetime.now(UTC)) - timedelta(days=CONSERVATION_SESSIONS_JOURS)
    return await db_client.purger_sessions_du_widget(avant)

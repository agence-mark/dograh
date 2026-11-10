"""[.mark] Clôture, lot A (D23, D24) : le journal complet de l'équipe, sa durée de garde réglable et sa purge de nuit.

Qui, quoi, quand, où, et d'où (écran, API, MCP). Gardé 12 mois par défaut ; la durée se règle à l'écran (1 à 120 mois, bornes contre la faute
de frappe). La purge est idempotente : la rejouer ne retire que ce qui a passé l'âge.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from loguru import logger

from api.db import db_client

CLE_DUREE = "MARK_JOURNAL_MOIS"
DUREE_PAR_DEFAUT_MOIS = 12
DUREE_MIN_MOIS, DUREE_MAX_MOIS = 1, 120
ORIGINES = ("ecran", "api", "mcp")
JOUR_PAR_MOIS = 30


async def duree_de_garde_en_mois() -> int:
    valeur = await db_client.lire_reglage_equipe(CLE_DUREE)
    if isinstance(valeur, bool) or not isinstance(valeur, int) or not DUREE_MIN_MOIS <= valeur <= DUREE_MAX_MOIS:
        return DUREE_PAR_DEFAUT_MOIS
    return valeur


async def regler_la_duree(mois: int, user_id: int | None) -> int:
    """Pose la durée de garde ; ``ValueError`` hors des bornes (la route répond 422)."""
    if isinstance(mois, bool) or not isinstance(mois, int) or not DUREE_MIN_MOIS <= mois <= DUREE_MAX_MOIS:
        raise ValueError(f"The journal is kept {DUREE_MIN_MOIS} to {DUREE_MAX_MOIS} months")
    await db_client.poser_reglage_equipe(CLE_DUREE, mois, user_id)
    return mois


async def purger_le_journal(maintenant: datetime | None = None) -> int:
    """Retire les lignes plus vieilles que la durée de garde. Rend le nombre retiré."""
    maintenant = maintenant or datetime.now(UTC)
    limite = maintenant - timedelta(days=JOUR_PAR_MOIS * await duree_de_garde_en_mois())
    retirees = await db_client.purger_journal(limite)
    if retirees:
        logger.info(f"[journal] {retirees} ligne(s) du journal de l'équipe purgée(s)")
    return retirees


async def purge_de_nuit(ctx) -> int:  # noqa: ARG001 -- signature des tâches ARQ
    return await purger_le_journal()

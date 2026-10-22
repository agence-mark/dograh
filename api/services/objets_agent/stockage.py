"""[.mark] Lot F7 : ce que Dograh garde des objets, dans ``organization_configurations`` (aucune migration).

``OBJETS_AGENT_NOMS`` : les noms techniques que Dograh a vus dans la base du client à sa dernière lecture
complète (écran, publication, resynchronisation). Ils ne servent qu'à un appel qui ne peut pas lire la base :
ses ``{{nom}}`` restent écrits tels quels (plan F7 : « la variable reste {{nom}} »), au lieu d'être rendus
vides par le moteur. Le plafond, lui, vit dans la base du client (019, lu par le portail).

Rien ici ne lève.
"""

from __future__ import annotations

from loguru import logger

from api.db import db_client
from api.enums import OrganizationConfigurationKey

CLE_NOMS = OrganizationConfigurationKey.OBJETS_AGENT_NOMS.value


async def lire_noms(organization_id: int | None) -> list[str]:
    """The names last seen. Unreadable = none known."""
    if organization_id is None:
        return []
    try:
        ligne = await db_client.get_configuration(organization_id, CLE_NOMS)
        noms = (ligne.value or {}).get("noms") if ligne is not None else None
        return [n for n in noms if isinstance(n, str)] if isinstance(noms, list) else []
    except Exception as erreur:  # noqa: BLE001 -- read at pick-up
        logger.warning(f"[.mark] Known object names of organization {organization_id} unreadable: {erreur!r}")
        return []


async def retenir_noms(organization_id: int, noms: list[str]) -> None:
    """Keep the names read from the database, written only when they changed."""
    try:
        propres = sorted(set(noms))
        if propres == sorted(await lire_noms(organization_id)):
            return
        await db_client.upsert_configuration(organization_id, CLE_NOMS, {"noms": propres})
    except Exception as erreur:  # noqa: BLE001 -- a mirror never fails a screen
        logger.warning(f"[.mark] Known object names of organization {organization_id} not kept: {erreur!r}")

"""[.mark] The in-memory copy of the establishments, read by every call (B3).

Decision B3 of the chantier: the agent never reads a database while it is on
the phone. It reads a COPY kept in Redis -- a few milliseconds -- and every
write updates that copy at once. A missing copy (Redis restarted, first call
after a deploy) is rebuilt from the stored catalogue and written back.

What the call reads is stamped on the run (``etablissement`` in
``runtime_configuration``), with where it came from: ``copie`` or ``stockage``.

⛔ ``lire_copie`` never raises: Redis down and database down is « no
establishment », and the call behaves exactly as before the feature.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

import redis.asyncio as aioredis
from loguru import logger

from api.constants import REDIS_URL
from api.schemas.etablissements import CatalogueEtablissements

PREFIXE = "mark:etablissements:v1:"
# Short on purpose: Redis is local to the call. A copy that takes longer than
# this is treated as absent and the stored catalogue is read instead.
DELAI_REDIS_S = 0.25

_client: aioredis.Redis | None = None


async def _redis() -> aioredis.Redis:
    global _client
    if _client is None:
        _client = aioredis.from_url(
            REDIS_URL,
            decode_responses=True,
            socket_timeout=DELAI_REDIS_S,
            socket_connect_timeout=DELAI_REDIS_S,
        )
    return _client


def cle_copie(organization_id: int) -> str:
    return f"{PREFIXE}{organization_id}"


async def publier_copie(organization_id: int, catalogue: CatalogueEtablissements) -> bool:
    """Write the copy. Never raises: a copy not written is rebuilt at the next call."""
    try:
        document = {
            "ecrite_le": datetime.now(UTC).isoformat(),
            "catalogue": catalogue.model_dump(mode="json"),
        }
        await (await _redis()).set(cle_copie(organization_id), json.dumps(document))
        return True
    except Exception as erreur:  # noqa: BLE001
        logger.warning(
            f"[.mark] Copy of the establishments of organization {organization_id} not written "
            f"(rebuilt at the next call): {erreur!r}"
        )
        return False


async def lire_copie(organization_id: int | None) -> tuple[CatalogueEtablissements, str]:
    """The catalogue a call uses, and where it was read: ``copie``, ``stockage``
    or ``aucune``. Never raises."""
    if organization_id is None:
        return CatalogueEtablissements(), "aucune"
    try:
        brut = await (await _redis()).get(cle_copie(organization_id))
        if brut:
            return CatalogueEtablissements.model_validate(json.loads(brut)["catalogue"]), "copie"
    except Exception as erreur:  # noqa: BLE001 -- the stored catalogue takes over
        logger.warning(
            f"[.mark] Copy of the establishments of organization {organization_id} unreadable, "
            f"stored catalogue read instead: {erreur!r}"
        )
    from api.services.etablissements.stockage import lire_etablissements

    catalogue = await lire_etablissements(organization_id)
    await publier_copie(organization_id, catalogue)
    return catalogue, "stockage"

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
from dataclasses import dataclass, field
from datetime import UTC, datetime

import redis.asyncio as aioredis
from loguru import logger

from api.constants import REDIS_URL
from api.schemas.etablissements import CatalogueEtablissements
from api.schemas.phrases import CataloguePhrases

# v2 (L2): the copy carries the establishments AND the catalogue of sentences. A v1
# copy left in Redis is simply never read again (rebuilt from the source).
PREFIXE = "mark:etablissements:v2:"
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


@dataclass
class CopieOrganisation:
    """What a call reads at pick-up, and where it was read."""

    etablissements: CatalogueEtablissements = field(
        default_factory=CatalogueEtablissements
    )
    phrases: CataloguePhrases = field(default_factory=CataloguePhrases)
    lu_depuis: str = "aucune"  # copie | stockage | aucune
    source: str = "dograh"  # dograh | base_client (L3)
    # L3: values written in the client's database that Dograh refused (the previous
    # value was kept). Shown on the « Client data » theme.
    refus: list[str] = field(default_factory=list)
    # Revue 9: the last line of the client database's journal read with these values.
    journal_id: int | None = None


async def lire_source(organization_id: int) -> CopieOrganisation:
    """The source of truth, read in full. Never raises (each part falls back to empty).

    L3: with a client database attached, the source is that database; when it does not
    answer, the mirror kept in Dograh (the last values known good) takes over.
    """
    from api.services.etablissements.stockage import (
        lire_etablissements,
        lire_phrases,
        nom_de_la_base_strict,
    )

    miroir = CopieOrganisation(
        etablissements=await lire_etablissements(organization_id),
        phrases=await lire_phrases(organization_id),
        lu_depuis="stockage",
    )
    try:
        from api.services.base_client.synchro import lire_depuis_la_base

        nom = await nom_de_la_base_strict(organization_id)
        if nom:
            return await lire_depuis_la_base(
                organization_id, nom, miroir.etablissements
            )
    except Exception as erreur:  # noqa: BLE001 -- the mirror takes over, the call goes on
        logger.warning(
            f"[.mark] Client database of organization {organization_id} not read, mirror used: {erreur}"
        )
    return miroir


async def publier_copie(
    organization_id: int, copie: CopieOrganisation | None = None
) -> bool:
    """Write the copy (read from the source when not given). Never raises: a copy
    not written is rebuilt at the next call."""
    try:
        if copie is None:
            copie = await lire_source(organization_id)
        document = {
            "ecrite_le": datetime.now(UTC).isoformat(),
            "source": copie.source,
            "catalogue": copie.etablissements.model_dump(mode="json"),
            "phrases": copie.phrases.model_dump(mode="json"),
            "refus": copie.refus,
            "journal_id": copie.journal_id,
        }
        redis = await _redis()
        if copie.journal_id is not None:
            # Revue 9: never over a copy that read a LATER line of the journal.
            brut = await redis.get(cle_copie(organization_id))
            publie = (json.loads(brut) if brut else {}).get("journal_id")
            if isinstance(publie, int) and publie > copie.journal_id:
                return False
        await redis.set(cle_copie(organization_id), json.dumps(document))
        return True
    except Exception as erreur:  # noqa: BLE001
        logger.warning(
            f"[.mark] Copy of the establishments of organization {organization_id} not written "
            f"(rebuilt at the next call): {erreur!r}"
        )
        return False


async def lire_copie_complete(organization_id: int | None) -> CopieOrganisation:
    """Everything a call uses. Never raises."""
    if organization_id is None:
        return CopieOrganisation()
    try:
        brut = await (await _redis()).get(cle_copie(organization_id))
        if brut:
            document = json.loads(brut)
            return CopieOrganisation(
                etablissements=CatalogueEtablissements.model_validate(
                    document["catalogue"]
                ),
                phrases=CataloguePhrases.model_validate(document.get("phrases") or {}),
                lu_depuis="copie",
                source=document.get("source", "dograh"),
                refus=list(document.get("refus") or []),
            )
    except Exception as erreur:  # noqa: BLE001 -- the source takes over
        logger.warning(
            f"[.mark] Copy of the establishments of organization {organization_id} unreadable, "
            f"source read instead: {erreur!r}"
        )
    copie = await lire_source(organization_id)
    await publier_copie(organization_id, copie)
    return copie


async def lire_copie(
    organization_id: int | None,
) -> tuple[CatalogueEtablissements, str]:
    """The establishments a call uses, and where they were read. Never raises."""
    copie = await lire_copie_complete(organization_id)
    return copie.etablissements, copie.lu_depuis

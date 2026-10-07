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

import asyncio
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime

import redis.asyncio as aioredis
from loguru import logger

from api.constants import REDIS_URL
from api.schemas.base_client import Equipe
from api.schemas.etablissements import CatalogueEtablissements
from api.schemas.phrases import CataloguePhrases

# v2 (L2): the copy carries the establishments AND the catalogue of sentences. A v1
# copy left in Redis is simply never read again (rebuilt from the source).
# v3 (l-agent-collegue, L1, C3): it carries the TEAM and its subjects too (read from the
# client's database; none without one). A v2 copy is never read again either.
PREFIXE = "mark:etablissements:v3:"
# Short on purpose: Redis is local to the call. A copy that takes longer than
# this is treated as absent and the stored catalogue is read instead.
DELAI_REDIS_S = 0.25
# Revue 10: at pick-up, with no copy in memory, the client's database gets this long; past
# it the mirror kept in Dograh answers and the copy is rebuilt in the background (B3).
DELAI_DECROCHE_S = 0.5
_EN_ARRIERE_PLAN: set[asyncio.Task] = set()

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
    # v3 (C3): the people and the subjects. They live in the client's database only: no
    # database (or a database that does not answer), no team.
    equipe: Equipe = field(default_factory=Equipe)
    lu_depuis: str = "aucune"  # copie | stockage | aucune
    source: str = "dograh"  # dograh | base_client (L3)
    # L3: values written in the client's database that Dograh refused (the previous
    # value was kept). Shown on the « Client data » theme.
    refus: list[str] = field(default_factory=list)
    # Revue 9: the last line of the client database's journal read with these values.
    journal_id: int | None = None
    # Revue 10: the client's database is attached but slower than the pick-up delay.
    repli: bool = False


async def lire_source(
    organization_id: int, delai_s: float | None = None
) -> CopieOrganisation:
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
            lecture = lire_depuis_la_base(
                organization_id, nom, miroir.etablissements, miroir.phrases
            )
            if delai_s is None:
                return await lecture
            try:
                return await asyncio.wait_for(lecture, delai_s)
            except TimeoutError:
                # Slow, not down: the mirror now, the database in the background.
                miroir.repli = True
                logger.warning(
                    f"[.mark] Client database of organization {organization_id} slower than "
                    f"{delai_s} s at pick-up: mirror used, copy rebuilt in the background"
                )
                return miroir
    except Exception as erreur:  # noqa: BLE001 -- the mirror takes over, the call goes on
        logger.warning(
            f"[.mark] Client database of organization {organization_id} not read, mirror used: {erreur!r}"
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
            "equipe": copie.equipe.model_dump(mode="json"),
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
                equipe=_equipe(document.get("equipe")),
                lu_depuis="copie",
                source=document.get("source", "dograh"),
                refus=list(document.get("refus") or []),
            )
    except Exception as erreur:  # noqa: BLE001 -- the source takes over
        logger.warning(
            f"[.mark] Copy of the establishments of organization {organization_id} unreadable, "
            f"source read instead: {erreur!r}"
        )
    copie = await lire_source(organization_id, delai_s=DELAI_DECROCHE_S)
    if copie.repli:
        # The database is slow or down: never publish the mirror as the copy; rebuild it
        # from the database, without the short delay, after the call has its answer.
        tache = asyncio.get_running_loop().create_task(
            _refaire_depuis_la_base(organization_id)
        )
        _EN_ARRIERE_PLAN.add(tache)
        tache.add_done_callback(_EN_ARRIERE_PLAN.discard)
    else:
        await publier_copie(organization_id, copie)
    return copie


async def _refaire_depuis_la_base(organization_id: int) -> None:
    """The background rebuild of revue 10: published ONLY when the client's database
    answered (never the mirror: the next call would then read it as the copy)."""
    try:
        copie = await lire_source(organization_id)
        if copie.source == "base_client":
            await publier_copie(organization_id, copie)
    except Exception as erreur:  # noqa: BLE001
        logger.warning(
            f"[.mark] Background rebuild of the copy of organization {organization_id} failed: {erreur!r}"
        )


def _equipe(brut) -> Equipe:
    """The team kept in the copy. Unreadable: no team (the call goes on without it)."""
    try:
        return Equipe.model_validate(brut or {})
    except Exception as erreur:  # noqa: BLE001
        logger.warning(f"[.mark] Team of the copy unreadable, none used: {erreur!r}")
        return Equipe()


async def lire_copie(
    organization_id: int | None,
) -> tuple[CatalogueEtablissements, str]:
    """The establishments a call uses, and where they were read. Never raises."""
    copie = await lire_copie_complete(organization_id)
    return copie.etablissements, copie.lu_depuis

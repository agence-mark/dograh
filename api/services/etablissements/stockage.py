"""[.mark] Where an organization's establishments are read and written.

One row of ``organization_configurations``, key ``ETABLISSEMENTS`` (no
migration). Format and bounds: ``api/schemas/etablissements.py``.

⛔ Two readings, the same rule as the announcement and the vocabulary:

- ``lire_etablissements`` (the CALL side, through the copy) never raises: a
  missing or unreadable row is « no establishment », so the call behaves exactly
  as it did before the feature;
- ``lire_etablissements_strict`` (the SCREEN side) raises on an unreadable row:
  shown empty, the next save would replace establishments that are really there.
"""

from __future__ import annotations

from loguru import logger

from api.db import db_client
from api.enums import OrganizationConfigurationKey
from api.schemas.etablissements import CatalogueEtablissements
from api.schemas.phrases import CataloguePhrases

CLE = OrganizationConfigurationKey.ETABLISSEMENTS.value
CLE_PHRASES = OrganizationConfigurationKey.PHRASES.value


async def lire_etablissements(organization_id: int | None) -> CatalogueEtablissements:
    if organization_id is None:
        return CatalogueEtablissements()
    try:
        ligne = await db_client.get_configuration(organization_id, CLE)
        if ligne is None or not ligne.value:
            return CatalogueEtablissements()
        return CatalogueEtablissements.model_validate(ligne.value)
    except Exception as erreur:  # noqa: BLE001 -- an establishment is never worth a call
        logger.warning(
            f"[.mark] Establishments of organization {organization_id} unreadable, "
            f"none used: {erreur!r}"
        )
        return CatalogueEtablissements()


async def lire_etablissements_strict(organization_id: int) -> CatalogueEtablissements:
    ligne = await db_client.get_configuration(organization_id, CLE)
    if ligne is None or not ligne.value:
        return CatalogueEtablissements()
    return CatalogueEtablissements.model_validate(ligne.value)


async def enregistrer_etablissements(
    organization_id: int, catalogue: CatalogueEtablissements
) -> CatalogueEtablissements:
    await db_client.upsert_configuration(
        organization_id, CLE, catalogue.model_dump(mode="json")
    )
    # The copy the calls read follows at once (B3): the next pick-up hears it.
    from api.services.etablissements.copie import publier_copie

    await publier_copie(organization_id)
    return catalogue


# The catalogue of sentences (E5): same two readings, same row table.


async def lire_phrases(organization_id: int | None) -> CataloguePhrases:
    if organization_id is None:
        return CataloguePhrases()
    try:
        ligne = await db_client.get_configuration(organization_id, CLE_PHRASES)
        if ligne is None or not ligne.value:
            return CataloguePhrases()
        return CataloguePhrases.model_validate(ligne.value)
    except Exception as erreur:  # noqa: BLE001 -- a sentence is never worth a call
        logger.warning(f"[.mark] Sentences of organization {organization_id} unreadable, none used: {erreur!r}")
        return CataloguePhrases()


async def lire_phrases_strict(organization_id: int) -> CataloguePhrases:
    ligne = await db_client.get_configuration(organization_id, CLE_PHRASES)
    if ligne is None or not ligne.value:
        return CataloguePhrases()
    return CataloguePhrases.model_validate(ligne.value)


async def enregistrer_phrases(organization_id: int, catalogue: CataloguePhrases) -> CataloguePhrases:
    await db_client.upsert_configuration(organization_id, CLE_PHRASES, catalogue.model_dump(mode="json"))
    from api.services.etablissements.copie import publier_copie

    await publier_copie(organization_id)
    return catalogue

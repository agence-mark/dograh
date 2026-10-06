"""[.mark] Where an organization's establishments are read and written.

One row of ``organization_configurations``, key ``ETABLISSEMENTS`` (no
migration). Format and bounds: ``api/schemas/etablissements.py``.

⛔ Two readings, the same rule as the announcement and the vocabulary:

- ``lire_etablissements`` (the CALL side, through the copy) never raises: a
  missing or unreadable row is « no establishment », so the call behaves exactly
  as it did before the feature;
- ``lire_etablissements_strict`` (the SCREEN side) raises on an unreadable row:
  shown empty, the next save would replace establishments that are really there.

L3 (B2): when the organization has a client database attached, THAT database is the
source. The screen reads and writes there (unreachable: ``BaseClientIndisponible``,
nothing written), and the row of ``organization_configurations`` is kept as a MIRROR
of the last values known good: the call falls back on it when the database does not
answer and no copy is in memory.
"""

from __future__ import annotations

from loguru import logger

from api.db import db_client
from api.enums import OrganizationConfigurationKey
from api.schemas.etablissements import CatalogueEtablissements
from api.schemas.phrases import CataloguePhrases

CLE = OrganizationConfigurationKey.ETABLISSEMENTS.value
CLE_PHRASES = OrganizationConfigurationKey.PHRASES.value
CLE_BASE_CLIENT = OrganizationConfigurationKey.BASE_CLIENT.value


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


async def _miroir_etablissements_strict(
    organization_id: int,
) -> CatalogueEtablissements:
    ligne = await db_client.get_configuration(organization_id, CLE)
    if ligne is None or not ligne.value:
        return CatalogueEtablissements()
    return CatalogueEtablissements.model_validate(ligne.value)


async def _referentiel_de_la_base(organization_id: int, nom_base: str):
    """The client's database read for the screen (raises ``BaseClientIndisponible``)."""
    from api.services.base_client.referentiel import lire_referentiel
    from api.db.bases_clients.connexion import connecter

    connexion = await connecter(nom_base)
    try:
        return await lire_referentiel(
            connexion, await lire_etablissements(organization_id)
        )
    finally:
        await connexion.close()


async def nom_de_la_base_strict(organization_id: int) -> str | None:
    """The attached database's name, read through THIS module's handle. ⛔ Strict: an
    unreadable attachment raises (writing only to the mirror while a database is the
    source would split the two in silence)."""
    from api.schemas.base_client import RattachementBaseClient

    ligne = await db_client.get_configuration(organization_id, CLE_BASE_CLIENT)
    if ligne is None or not ligne.value:
        return None
    return RattachementBaseClient.model_validate(ligne.value).nom_base


async def lire_etablissements_strict(organization_id: int) -> CatalogueEtablissements:
    nom = await nom_de_la_base_strict(organization_id)
    if nom:
        return (await _referentiel_de_la_base(organization_id, nom)).etablissements
    return await _miroir_etablissements_strict(organization_id)


async def enregistrer_miroir(
    organization_id: int, etablissements=None, phrases=None
) -> None:
    """The mirror of the last values known good (written after the database accepted them)."""
    if etablissements is not None:
        await db_client.upsert_configuration(
            organization_id, CLE, etablissements.model_dump(mode="json")
        )
    if phrases is not None:
        await db_client.upsert_configuration(
            organization_id, CLE_PHRASES, phrases.model_dump(mode="json")
        )


async def enregistrer_etablissements(
    organization_id: int, catalogue: CatalogueEtablissements, auteur: str = "dograh"
) -> CatalogueEtablissements:
    nom = await nom_de_la_base_strict(organization_id)
    if nom:
        from api.db.bases_clients.referentiel import ecrire_etablissements
        from api.db.bases_clients.connexion import connecter

        connexion = await connecter(nom)
        try:
            await ecrire_etablissements(connexion, catalogue, auteur)
        finally:
            await connexion.close()
    await enregistrer_miroir(organization_id, etablissements=catalogue)
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
        logger.warning(
            f"[.mark] Sentences of organization {organization_id} unreadable, none used: {erreur!r}"
        )
        return CataloguePhrases()


async def lire_phrases_strict(organization_id: int) -> CataloguePhrases:
    nom = await nom_de_la_base_strict(organization_id)
    if nom:
        return (await _referentiel_de_la_base(organization_id, nom)).phrases
    ligne = await db_client.get_configuration(organization_id, CLE_PHRASES)
    if ligne is None or not ligne.value:
        return CataloguePhrases()
    return CataloguePhrases.model_validate(ligne.value)


async def enregistrer_phrases(
    organization_id: int, catalogue: CataloguePhrases, auteur: str = "dograh"
) -> CataloguePhrases:
    nom = await nom_de_la_base_strict(organization_id)
    if nom:
        from api.db.bases_clients.referentiel import ecrire_phrases
        from api.db.bases_clients.connexion import connecter

        connexion = await connecter(nom)
        try:
            await ecrire_phrases(connexion, catalogue, auteur)
        finally:
            await connexion.close()
    await enregistrer_miroir(organization_id, phrases=catalogue)
    from api.services.etablissements.copie import publier_copie

    await publier_copie(organization_id)
    return catalogue

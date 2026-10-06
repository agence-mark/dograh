"""[.mark] Which database an organization is attached to, and what its screen shows (B4).

``BASE_CLIENT`` in ``organization_configurations`` holds the NAME only; the server,
user and password are the installation's (``MARK_BASES_CLIENTS_URL``).

⛔ Tenant isolation: the name is the organization's own setting, read by its
``organization_id``; nothing in a request can point a call or a screen at another
organization's database.
"""

from __future__ import annotations

from datetime import UTC, datetime

from loguru import logger

from api.db import db_client
from api.db.bases_clients.connexion import (
    BaseClientIndisponible,
    connecter,
    serveur_configure,
    verifier_nom,
    version_attendue,
)
from api.enums import OrganizationConfigurationKey
from api.schemas.base_client import Conservation, EtatBaseClient, RattachementBaseClient

CLE = OrganizationConfigurationKey.BASE_CLIENT.value


def auteur_de(user) -> str:
    """Who wrote, as ``journal_modif`` records it: never a name or an address, the account's id."""
    return f"dograh:{getattr(user, 'provider_id', None) or getattr(user, 'id', '?')}"


async def lire_rattachement(organization_id: int | None) -> RattachementBaseClient:
    """Never raises: unreadable = not attached (the call of before)."""
    if organization_id is None:
        return RattachementBaseClient()
    try:
        ligne = await db_client.get_configuration(organization_id, CLE)
        if ligne is None or not ligne.value:
            return RattachementBaseClient()
        return RattachementBaseClient.model_validate(ligne.value)
    except Exception as erreur:  # noqa: BLE001
        logger.warning(
            f"[.mark] Client database attachment of organization {organization_id} unreadable: {erreur!r}"
        )
        return RattachementBaseClient()


async def nom_de_la_base(organization_id: int | None) -> str | None:
    return (await lire_rattachement(organization_id)).nom_base


async def rattacher(
    organization_id: int, nom_base: str | None
) -> RattachementBaseClient:
    if nom_base:
        verifier_nom(nom_base)
    reglage = RattachementBaseClient(
        nom_base=nom_base or None, rattachee_le=datetime.now(UTC) if nom_base else None
    )
    await db_client.upsert_configuration(
        organization_id, CLE, reglage.model_dump(mode="json")
    )
    return reglage


async def organisations_rattachees() -> list[tuple[int, str]]:
    """Every (organization, database name) attached: the night resync's list."""
    lignes = await db_client.get_all_configurations_by_key(CLE)
    sortie = []
    for ligne in lignes:
        try:
            reglage = RattachementBaseClient.model_validate(ligne["value"] or {})
        except Exception:  # noqa: BLE001
            continue
        if reglage.nom_base:
            sortie.append((ligne["organization_id"], reglage.nom_base))
    return sortie


async def etat(organization_id: int, refus: list[str] | None = None) -> EtatBaseClient:
    from api.db.bases_clients.etat import lire_etat

    nom = await nom_de_la_base(organization_id)
    resultat = EtatBaseClient(
        serveur_configure=serveur_configure(),
        nom_base=nom,
        version_attendue=version_attendue(),
        refus=refus or [],
    )
    if not nom:
        return resultat
    try:
        connexion = await connecter(nom)
    except BaseClientIndisponible as erreur:
        resultat.erreur = str(erreur)
        return resultat
    try:
        resultat.joignable = True
        (
            resultat.version,
            resultat.derniere_ecriture,
            resultat.conservation,
        ) = await lire_etat(connexion)
    finally:
        await connexion.close()
    return resultat


async def regler_conservation(
    organization_id: int, lignes: list[Conservation], auteur: str
) -> None:
    """Change durations only (B2: bounded, logged). A table not already in the policy is refused."""
    from api.db.bases_clients.etat import regler_conservation as ecrire_conservation

    nom = await nom_de_la_base(organization_id)
    if not nom:
        raise BaseClientIndisponible(
            "No client database is attached to this organization."
        )
    connexion = await connecter(nom)
    try:
        await ecrire_conservation(connexion, lignes, auteur)
    finally:
        await connexion.close()

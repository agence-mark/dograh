"""[.mark] The integrations .mark proposes to a client (builder partie 2, U3 sexies point 9, E77).

Chez un client, « Proposer au client » (account name, message) writes a proposal in the settings of
HIS organization (key ``PROPOSITIONS_CONNECTEURS``, a free-text key of the existing table: no
migration). The client's portal reads it through the API, shows it « À autoriser », and its window
« Autoriser » opens Nango's connection window with the link made here, for this organization only.

⛔ Tenant isolation (D6): every function takes the organization FROM THE SERVER (the signed-in user).
A proposal is looked up in that organization's own list: the identifier of another organization's
proposal is simply unknown (404). The link is made for the proposal's organization, never for one
named in a request. Nothing here holds a secret.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Literal

from loguru import logger
from pydantic import BaseModel, Field

from api.db import db_client
from api.enums import OrganizationConfigurationKey
from api.services.integrations.connectors import nango

CLE = OrganizationConfigurationKey.PROPOSITIONS_CONNECTEURS.value
MAX_PROPOSITIONS = 100


class Proposition(BaseModel):
    identifiant: str
    connecteur: str
    compte: str = Field(min_length=1, max_length=nango.LONGUEUR_ETIQUETTE)
    message: str = Field(default="", max_length=500)
    # « a_autoriser » until a connection of that software carries this account's name.
    etat: Literal["a_autoriser", "autorisee"] = "a_autoriser"
    propose_par: str | None = None
    propose_le: str
    relances: int = 0
    relance_le: str | None = None
    # Filled when the account is connected: who authorized (the tag of the connection).
    autorise_par: str | None = None


class Propositions(BaseModel):
    propositions: list[Proposition] = Field(default_factory=list)


class NouvelleProposition(BaseModel):
    connecteur: str = Field(min_length=1, max_length=60)
    compte: str = Field(min_length=1, max_length=nango.LONGUEUR_ETIQUETTE)
    message: str = Field(default="", max_length=500)


class DemandeLienProposition(BaseModel):
    # Who authorizes, when it is not the signed-in person (a link copied to a client who has no
    # account on the portal). Free text, kept with the connection.
    autorise_par: str | None = Field(default=None, max_length=nango.LONGUEUR_ETIQUETTE)


class PropositionIntrouvable(LookupError):
    pass


class PropositionDejaPresente(ValueError):
    pass


def _maintenant() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


async def lire(organization_id: int) -> Propositions:
    """Never raises: unreadable or absent = none."""
    try:
        ligne = await db_client.get_configuration(organization_id, CLE)
        if ligne is None or not ligne.value:
            return Propositions()
        return Propositions.model_validate(ligne.value)
    except Exception as erreur:  # noqa: BLE001 -- logged, the list is shown empty
        logger.error(f"[.mark] Proposals of organization {organization_id} unreadable: {erreur!r}")
        return Propositions()


async def _ecrire(organization_id: int, valeur: Propositions) -> None:
    await db_client.upsert_configuration(organization_id, CLE, valeur.model_dump(mode="json"))


async def avec_etat(organization_id: int) -> list[Proposition]:
    """The proposals with their state: « autorisee » when a connection of that software holds the
    account's name. Nango unreachable: the stored state, never an error."""
    liste = (await lire(organization_id)).propositions
    if not liste or not nango.nango_configure():
        return liste
    try:
        connexions = await nango.connexions(organization_id)
    except nango.NangoIndisponible:
        return liste
    sortie = []
    for p in liste:
        from api.services.integrations.connectors.catalogue import connecteur

        c = connecteur(p.connecteur)
        trouvee = next(
            (x for x in connexions if c and x.integration == c.integration and x.compte == p.compte),
            None,
        )
        if trouvee is not None:
            p = p.model_copy(update={"etat": "autorisee", "autorise_par": trouvee.autorise_par})
        sortie.append(p)
    return sortie


async def proposer(
    organization_id: int, nouvelle: NouvelleProposition, propose_par: str | None
) -> Proposition:
    from api.services.integrations.connectors.catalogue import connecteur

    c = connecteur(nouvelle.connecteur)
    if c is None or c.interne or c.etat == "a_activer":
        raise ValueError(f"« {nouvelle.connecteur} » cannot be proposed: no connection to make.")
    compte = nango.etiquette_propre(nouvelle.compte)
    if not compte:
        raise ValueError("The account needs a name.")
    existantes = await avec_etat(organization_id)
    if len(existantes) >= MAX_PROPOSITIONS:
        raise ValueError("Too many proposals: remove some first.")
    if any(p.connecteur == c.nom and p.compte == compte and p.etat == "a_autoriser" for p in existantes):
        raise PropositionDejaPresente(f"« {compte} » is already proposed for {c.libelle}.")
    proposition = Proposition(
        identifiant=uuid.uuid4().hex,
        connecteur=c.nom,
        compte=compte,
        message=nouvelle.message.strip(),
        propose_par=nango.etiquette_propre(propose_par),
        propose_le=_maintenant(),
    )
    stockees = (await lire(organization_id)).propositions
    await _ecrire(organization_id, Propositions(propositions=[*stockees, proposition]))
    return proposition


async def _trouver(organization_id: int, identifiant: str) -> tuple[Propositions, Proposition]:
    stockees = await lire(organization_id)
    for p in stockees.propositions:
        if p.identifiant == identifiant:
            return stockees, p
    raise PropositionIntrouvable(identifiant)


async def relancer(organization_id: int, identifiant: str) -> Proposition:
    stockees, p = await _trouver(organization_id, identifiant)
    p2 = p.model_copy(update={"relances": p.relances + 1, "relance_le": _maintenant()})
    stockees.propositions = [p2 if x.identifiant == identifiant else x for x in stockees.propositions]
    await _ecrire(organization_id, stockees)
    return p2


async def retirer(organization_id: int, identifiant: str) -> None:
    stockees, _ = await _trouver(organization_id, identifiant)
    stockees.propositions = [x for x in stockees.propositions if x.identifiant != identifiant]
    await _ecrire(organization_id, stockees)


async def lien(
    organization_id: int, identifiant: str, autorise_par: str | None
) -> dict:
    """The connection link of THIS proposal: for the proposal's organization (the signed-in one's),
    its software, its account name, and who authorizes."""
    from api.services.integrations.connectors.catalogue import connecteur

    _, p = await _trouver(organization_id, identifiant)
    c = connecteur(p.connecteur)
    if c is None:
        raise PropositionIntrouvable(identifiant)
    return await nango.lien_d_autorisation(
        organization_id, [c.integration], compte=p.compte, autorise_par=autorise_par
    )

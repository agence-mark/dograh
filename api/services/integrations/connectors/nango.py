"""[.mark] The Nango client of the connectors (chantier l-agent-travaille, L5; plan connecteurs-agent D1, D2, D4, D6).

Nango keeps each client's keys (authorization, encrypted storage, renewal) and presents them in
our place through its relay. One Nango per installation (D2), reached at ``NANGO_URL`` with the
installation's secret key ``NANGO_SECRET_KEY`` (environment, never on screen, never in a
database). No migration (D4): a client's connection is found in Nango by its tag
``organization_id``.

⛔ Tenant isolation (D6): every function takes the organization FROM THE SERVER (the call's
engine, the signed-in user); a connection is used only if Nango lists it under that
organization's tag. Nothing the model says chooses a connection.
⛔ The secret key never appears in a log or an error.

``httpx`` only, already a dependency (R5).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import httpx

VARIABLE_URL = "NANGO_URL"
VARIABLE_CLE = "NANGO_SECRET_KEY"
ETIQUETTE = "organization_id"
DELAI_GESTION_S = 10.0


class NangoIndisponible(RuntimeError):
    """Not configured, unreachable, or refused. Message safe to show."""


class ConnexionAbsente(RuntimeError):
    """The organization has no connection to this software yet. Message safe to show."""


def nango_configure() -> bool:
    return bool(
        os.environ.get(VARIABLE_URL, "").strip()
        and os.environ.get(VARIABLE_CLE, "").strip()
    )


def nouveau_client(**options) -> httpx.AsyncClient:
    """The HTTP client of Nango (a test gives its stand-in here)."""
    return httpx.AsyncClient(**options)


def _base() -> tuple[str, dict[str, str]]:
    url = os.environ.get(VARIABLE_URL, "").strip().rstrip("/")
    cle = os.environ.get(VARIABLE_CLE, "").strip()
    if not url or not cle:
        raise NangoIndisponible(
            f"Nango is not configured on this installation ({VARIABLE_URL}, {VARIABLE_CLE})."
        )
    return url, {"Authorization": f"Bearer {cle}"}


async def _requete(
    methode: str, chemin: str, *, delai: float = DELAI_GESTION_S, **options
) -> httpx.Response:
    url, entetes = _base()
    entetes = {**entetes, **(options.pop("headers", None) or {})}
    try:
        async with nouveau_client(timeout=delai) as client:
            return await client.request(
                methode, f"{url}{chemin}", headers=entetes, **options
            )
    except httpx.TimeoutException:
        raise NangoIndisponible("Nango did not answer in time.") from None
    except httpx.HTTPError as erreur:
        raise NangoIndisponible(
            f"Nango does not answer ({type(erreur).__name__})."
        ) from None


@dataclass(frozen=True)
class Connexion:
    connection_id: str
    integration: str  # Nango's provider_config_key
    provider: str | None
    creee_le: str | None
    erreurs: int = 0


def _organisation(organization_id: int) -> str:
    if not isinstance(organization_id, int) or isinstance(organization_id, bool):
        raise ValueError("The organization comes from the server, as an integer.")
    return str(organization_id)


async def connexions(organization_id: int) -> list[Connexion]:
    """The connections of THIS organization (found by its tag, D4)."""
    reponse = await _requete(
        "GET",
        "/connections",
        params={f"tags[{ETIQUETTE}]": _organisation(organization_id)},
    )
    if reponse.status_code != 200:
        raise NangoIndisponible(
            f"Nango refused the list of connections (HTTP {reponse.status_code})."
        )
    sortie = []
    for c in (reponse.json() or {}).get("connections") or []:
        # Belt and braces: the tag is checked again here, a listing filter never trusted alone.
        etiquettes = c.get("tags") or {}
        if etiquettes and str(etiquettes.get(ETIQUETTE)) != _organisation(
            organization_id
        ):
            continue
        sortie.append(
            Connexion(
                connection_id=str(c.get("connection_id")),
                integration=str(c.get("provider_config_key")),
                provider=c.get("provider"),
                creee_le=c.get("created") or c.get("created_at"),
                erreurs=len(c.get("errors") or []),
            )
        )
    return sortie


async def connexion_de(organization_id: int, integration: str) -> Connexion:
    for connexion in await connexions(organization_id):
        if connexion.integration == integration:
            return connexion
    raise ConnexionAbsente(
        f"This organization is not connected to « {integration} » yet: generate its authorization link."
    )


async def lien_d_autorisation(
    organization_id: int, integrations: list[str]
) -> dict[str, Any]:
    """A connect session tagged with THIS organization: the link the client opens to
    authorize (D11). ``{"lien", "expire_le"}``."""
    corps = {
        "tags": {ETIQUETTE: _organisation(organization_id)},
        "allowed_integrations": list(integrations),
        # Older Nango versions read the end user instead of the tags.
        "end_user": {
            "id": f"organisation-{_organisation(organization_id)}",
            "tags": {ETIQUETTE: _organisation(organization_id)},
        },
    }
    reponse = await _requete("POST", "/connect/sessions", json=corps)
    if reponse.status_code not in (200, 201):
        raise NangoIndisponible(
            f"Nango refused the authorization link (HTTP {reponse.status_code})."
        )
    donnees = (reponse.json() or {}).get("data") or {}
    return {"lien": donnees.get("connect_link"), "expire_le": donnees.get("expires_at")}


@dataclass(frozen=True)
class Requete:
    """What an action sends through the relay: a path of the software's API, never a host."""

    methode: str
    chemin: str
    params: dict[str, Any] | None = None
    json: Any = None


async def relayer(
    organization_id: int,
    integration: str,
    requete: Requete,
    *,
    delai: float,
    base_url: str | None = None,
) -> Any:
    """Call the software of THIS organization through Nango's relay. Returns the JSON body.

    ``base_url``: the « Base-Url-Override » of a test connector only (an unauthenticated
    integration), set by the catalogue, never by a request."""
    if not requete.chemin.startswith("/") or "://" in requete.chemin:
        raise ValueError("An action calls a path of the software's API, never a host.")
    connexion = await connexion_de(organization_id, integration)
    entetes = {
        "Connection-Id": connexion.connection_id,
        "Provider-Config-Key": integration,
    }
    if base_url:
        entetes["Base-Url-Override"] = base_url
    reponse = await _requete(
        requete.methode,
        f"/proxy{requete.chemin}",
        delai=delai,
        headers=entetes,
        params=requete.params,
        json=requete.json,
    )
    if reponse.status_code >= 400:
        raise NangoIndisponible(
            f"The software refused the action (HTTP {reponse.status_code})."
        )
    try:
        return reponse.json()
    except ValueError:
        return {}

"""[.mark] U2 ter : outils communs des tests de l'équipe (vraie base de test, vraie application, vrai ``get_user``)."""

from __future__ import annotations

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from api.app import app
from api.utils.auth import create_jwt_token, hash_password

MOT_DE_PASSE = "un-mot-de-passe-long-12"


@pytest.fixture(autouse=False)
def sans_preparation_des_organisations():
    """``ensure_organization_bootstrapped`` appelle des services externes : jamais dans ces tests."""
    with patch(
        "api.services.auth.depends.ensure_organization_bootstrapped", new=AsyncMock(return_value=True)
    ):
        yield


async def creer_compte(db, email: str, *, role: str | None = None, organisations=()):
    """Un compte réel, son rôle d'équipe (par nom) et ses organisations ; rend (user, jeton)."""
    user = await db.create_user_with_email(email, hash_password(MOT_DE_PASSE))
    if role is not None:
        roles = {r["nom"]: r["id"] for r in await db.lister_roles()}
        await db.poser_membre(user.id, roles[role])
    for organisation_id in organisations:
        await db.add_user_to_organization(user.id, organisation_id)
    if organisations:
        await db.update_user_selected_organization(user.id, organisations[0])
    return user, create_jwt_token(user.id, email)


async def creer_organisation(db, nom: str) -> int:
    organisation, _ = await db.get_or_create_organization_by_provider_id(
        org_provider_id=nom, user_id=None
    )
    return organisation.id


@asynccontextmanager
async def client_http():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client


def entetes(jeton: str, organisation: int | None = None) -> dict:
    h = {"Authorization": f"Bearer {jeton}"}
    if organisation is not None:
        h["X-Mark-Organisation"] = str(organisation)
    return h

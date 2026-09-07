"""[.mark] Which organizations a user holds, and which one is current.

Upstream, an organization is only ever born from a signup (``routes/auth.py``
for local auth, ``_handle_stack_auth`` for hosted): there is no way to create a
second one, and no way to move between them. One customer therefore costs one
account and one email address.

Everything needed is already in the database — ``organization_users`` is a
many-to-many table, ``selected_organization_id`` alone decides the current
organization, and ``provider_id`` is a free unique string. This module is the
door, and it opens onto functions that already existed.

Scope of the door, deliberately narrow:

* It is OSS-only. Under Stack Auth the identity provider owns teams and
  ``_handle_stack_auth`` re-derives ``selected_organization_id`` from the token
  on every request, so a create here would exist on one side only and a switch
  would be undone by the next request. The routes answer 404 there.
* An organization has no display name of its own upstream, and adding a column
  would put a migration of ours in the middle of upstream's revision chain.
  ``provider_id`` is the handle and the label both; callers are expected to
  pass something a human can read.
"""

from pydantic import BaseModel, Field, field_validator

from api.db import db_client
from api.db.models import UserModel


class OrganizationProviderIdTakenError(Exception):
    """The requested identifier already belongs to an organization.

    Raised instead of joining it. ``get_or_create_organization_by_provider_id``
    returns the existing row on conflict, so a caller that ignored the
    was-created flag would let anyone into any organization by guessing its
    identifier.
    """


class OrganizationNotAccessibleError(Exception):
    """The user does not belong to the organization they asked for."""


class OrganizationSummary(BaseModel):
    id: int
    provider_id: str
    is_selected: bool


class OrganizationListResponse(BaseModel):
    organizations: list[OrganizationSummary]


class OrganizationCreateRequest(BaseModel):
    provider_id: str = Field(min_length=1, max_length=255)
    select: bool = False

    @field_validator("provider_id")
    @classmethod
    def _reject_blank(cls, value: str) -> str:
        # An all-whitespace identifier would create an organization nobody can
        # name or find again, and the unique index would happily accept it.
        stripped = value.strip()
        if not stripped:
            raise ValueError("provider_id must not be blank")
        return stripped


class SelectOrganizationRequest(BaseModel):
    organization_id: int


async def list_organizations_for_user(user: UserModel) -> OrganizationListResponse:
    organizations = await db_client.list_organizations_for_user(user.id)
    return OrganizationListResponse(
        organizations=[
            OrganizationSummary(
                id=organization.id,
                provider_id=organization.provider_id,
                is_selected=organization.id == user.selected_organization_id,
            )
            for organization in organizations
        ]
    )


async def create_organization_for_user(
    user: UserModel, *, provider_id: str, select: bool
) -> OrganizationSummary:
    """Create an organization and make the caller a member of it.

    Refuses a taken identifier rather than joining the organization behind it.
    """
    organization, was_created = await db_client.get_or_create_organization_by_provider_id(
        org_provider_id=provider_id, user_id=user.id
    )
    if not was_created:
        raise OrganizationProviderIdTakenError(provider_id)

    await db_client.add_user_to_organization(user.id, organization.id)

    if select:
        await db_client.update_user_selected_organization(user.id, organization.id)

    return OrganizationSummary(
        id=organization.id,
        provider_id=organization.provider_id,
        is_selected=select,
    )


async def select_organization_for_user(
    user: UserModel, *, organization_id: int
) -> OrganizationSummary:
    """Move the caller's current organization.

    Membership is resolved from the caller's own list rather than from the id
    in the request: an id in a request body proves the row exists, never that
    the caller may reach it.
    """
    organizations = await db_client.list_organizations_for_user(user.id)
    target = next(
        (
            organization
            for organization in organizations
            if organization.id == organization_id
        ),
        None,
    )
    if target is None:
        raise OrganizationNotAccessibleError(organization_id)

    await db_client.update_user_selected_organization(user.id, target.id)

    return OrganizationSummary(
        id=target.id,
        provider_id=target.provider_id,
        is_selected=True,
    )

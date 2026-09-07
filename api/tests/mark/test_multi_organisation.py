"""[.mark] Non-regression test for user-owned organization management.

The question this file answers, and it answers only this one:

    Can one person hold several organizations and switch between them,
    without ever reaching an organization that is not theirs?

Why it exists
-------------
Upstream, an organization is only ever born from a signup: there is no create
route and no switcher. One customer therefore costs one account and one email
address, which does not scale and — because model-provider keys are stored one
configuration per organization — makes per-customer BYOK impossible.

The database already supports it: ``organization_users`` is a many-to-many
table, ``selected_organization_id`` alone decides the current organization, and
``provider_id`` is a free unique string. What is missing is the door, not the
room.

Two guarantees are pinned here, and the second matters more than the first:

1. the door exists — create, list, switch;
2. the door is not a hole — a user cannot switch into, nor join, an
   organization that is not theirs.

Guarantee 2 is the one an upstream refactor could quietly remove while every
screen keeps working.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routes.organization import router
from api.services.auth import depends as auth_depends
from api.services.auth.depends import get_user

USER_ID = 7
OWN_ORGANIZATION = SimpleNamespace(id=1, provider_id="client-nuances-de-feu")
OTHER_OWN_ORGANIZATION = SimpleNamespace(id=2, provider_id="client-vie-veranda")
SOMEONE_ELSES_ORGANIZATION = SimpleNamespace(id=99, provider_id="client-de-pierre")


def _make_client(monkeypatch, *, selected_organization_id=OWN_ORGANIZATION.id):
    monkeypatch.setattr(auth_depends, "AUTH_PROVIDER", "local")
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_user] = lambda: SimpleNamespace(
        id=USER_ID,
        email="evan@example.com",
        provider_id="oss_1757000000_2f0a1b7c",
        selected_organization_id=selected_organization_id,
    )
    return TestClient(app)


@pytest.fixture
def membership(monkeypatch):
    """One user, two organizations of their own, one that is not.

    Returns the recorder so a test can assert on what was written, not only on
    what was answered.

    The ImportError branch is deliberate. On code where the patch is gone the
    fixture must not blow up during setup: the run then reaches the request
    below and fails on the answer it got — a 404 saying the door is missing —
    which is the sentence a reader needs, rather than a collection error.
    """
    owned = [OWN_ORGANIZATION, OTHER_OWN_ORGANIZATION]
    selected: list[tuple[int, int]] = []
    joined: list[tuple[int, int]] = []

    async def _list_for_user(user_id):
        return list(owned)

    async def _update_selected(user_id, organization_id):
        selected.append((user_id, organization_id))

    async def _add_to_organization(user_id, organization_id):
        joined.append((user_id, organization_id))

    try:
        from api.services import organization_membership as service
    except ImportError:
        service = None

    if service is not None:
        monkeypatch.setattr(
            service.db_client, "list_organizations_for_user", _list_for_user
        )
        monkeypatch.setattr(
            service.db_client, "update_user_selected_organization", _update_selected
        )
        monkeypatch.setattr(
            service.db_client, "add_user_to_organization", _add_to_organization
        )
    return SimpleNamespace(owned=owned, selected=selected, joined=joined)


def _stub_creation(monkeypatch, *, organization, was_created):
    """Point organization creation at a fixed answer, if the service exists.

    Tolerant of the module being absent for the same reason the fixture is: on
    unpatched code the test must fail on the route's answer, not on an import.
    """
    try:
        from api.services import organization_membership as service
    except ImportError:
        return
    monkeypatch.setattr(
        service.db_client,
        "get_or_create_organization_by_provider_id",
        AsyncMock(return_value=(organization, was_created)),
    )


# --------------------------------------------------------------------------
# 1. The door exists
# --------------------------------------------------------------------------


def test_a_user_sees_every_organization_they_hold(monkeypatch, membership):
    response = _make_client(monkeypatch).get("/organizations")

    assert response.status_code == 200
    assert response.json() == {
        "organizations": [
            {"id": 1, "provider_id": "client-nuances-de-feu", "is_selected": True},
            {"id": 2, "provider_id": "client-vie-veranda", "is_selected": False},
        ]
    }


def test_a_second_organization_can_be_created(monkeypatch, membership):
    created = SimpleNamespace(id=3, provider_id="client-sinea")
    _stub_creation(monkeypatch, organization=created, was_created=True)

    response = _make_client(monkeypatch).post(
        "/organizations", json={"provider_id": "client-sinea"}
    )

    assert response.status_code == 200
    assert response.json() == {
        "id": 3,
        "provider_id": "client-sinea",
        "is_selected": False,
    }
    assert membership.joined == [(USER_ID, 3)], (
        "The creator was not linked to the organization they just created"
    )
    assert membership.selected == [], (
        "Creating an organization must not move the current one under the user"
    )


def test_creating_can_switch_in_one_call(monkeypatch, membership):
    created = SimpleNamespace(id=3, provider_id="client-sinea")
    _stub_creation(monkeypatch, organization=created, was_created=True)

    response = _make_client(monkeypatch).post(
        "/organizations", json={"provider_id": "client-sinea", "select": True}
    )

    assert response.status_code == 200
    assert response.json()["is_selected"] is True
    assert membership.selected == [(USER_ID, 3)]


def test_switching_moves_the_current_organization(monkeypatch, membership):
    response = _make_client(monkeypatch).put(
        "/organizations/selected", json={"organization_id": OTHER_OWN_ORGANIZATION.id}
    )

    assert response.status_code == 200
    assert response.json() == {
        "id": 2,
        "provider_id": "client-vie-veranda",
        "is_selected": True,
    }
    assert membership.selected == [(USER_ID, OTHER_OWN_ORGANIZATION.id)]


# --------------------------------------------------------------------------
# 2. The door is not a hole
# --------------------------------------------------------------------------


def test_switching_into_someone_elses_organization_is_refused(
    monkeypatch, membership
):
    """Tenant isolation. An id in a request body proves nothing about ownership."""
    response = _make_client(monkeypatch).put(
        "/organizations/selected",
        json={"organization_id": SOMEONE_ELSES_ORGANIZATION.id},
    )

    assert response.status_code == 404
    assert membership.selected == [], (
        "A user was moved into an organization they do not belong to"
    )


def test_claiming_an_existing_identifier_does_not_join_its_organization(
    monkeypatch, membership
):
    """The sharpest edge of this patch, and the reason it is not three lines.

    ``get_or_create_organization_by_provider_id`` returns the *existing* row
    when the identifier is taken. Creating and then linking without looking at
    the was-created flag would let anyone join any organization by guessing its
    identifier. The route must refuse instead.
    """
    _stub_creation(
        monkeypatch, organization=SOMEONE_ELSES_ORGANIZATION, was_created=False
    )

    response = _make_client(monkeypatch).post(
        "/organizations", json={"provider_id": "client-de-pierre"}
    )

    assert response.status_code == 409
    assert membership.joined == [], (
        "Claiming a taken identifier let the caller into another organization"
    )
    assert membership.selected == []


def test_an_identifier_is_required_and_not_blank(monkeypatch, membership):
    """A blank identifier would create an unnameable, unfindable organization."""
    client = _make_client(monkeypatch)

    assert client.post("/organizations", json={}).status_code == 422
    assert (
        client.post("/organizations", json={"provider_id": "   "}).status_code == 422
    )


# --------------------------------------------------------------------------
# 3. Where the door is NOT opened, and why
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "method,path,payload",
    [
        ("get", "/organizations", None),
        ("post", "/organizations", {"provider_id": "client-sinea"}),
        ("put", "/organizations/selected", {"organization_id": 2}),
    ],
)
def test_hosted_deployments_keep_owning_their_teams(
    monkeypatch, membership, method, path, payload
):
    """Deliberately closed outside OSS auth, and this pins that on purpose.

    With Stack Auth, the identity provider owns teams: ``_handle_stack_auth``
    re-derives ``selected_organization_id`` from the token on every single
    request. An organization created here would exist on one side only, and a
    switch would be silently undone by the next request. Answering 404 is
    honest; answering 200 and doing nothing is not.
    """
    monkeypatch.setattr(auth_depends, "AUTH_PROVIDER", "stack")
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)

    response = getattr(client, method)(
        path, **({"json": payload} if payload is not None else {})
    )

    assert response.status_code == 404

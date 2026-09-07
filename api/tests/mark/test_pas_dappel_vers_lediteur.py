"""[.mark] Non-regression test for the ENABLE_DOGRAH_MANAGED_SERVICES switch.

The question this file answers, and it answers only this one:

    When Dograh-managed services are switched off, does an authenticated
    request still reach out to the vendor's servers?

Why it exists
-------------
The .mark deployment sells "everything runs on your own accounts, nothing
leaves the installation" (BYOK on every provider: telephony, reasoning,
speech-to-text, text-to-speech). Upstream, ``ensure_organization_bootstrapped``
runs on every authenticated request and, until it succeeds, calls
``services.dograh.com`` to mint a model-service key and to provision managed
SIP. That makes the sentence false.

The failure mode this guards against is silent. If upstream moves the
provisioning call somewhere else, our lines survive, nothing conflicts, the
agent answers calls normally, and the outbound call comes back without anyone
noticing. Neither git nor a diff review catches that.

So the assertion is deliberately made at the transport layer rather than on a
named function: *nothing goes out over HTTP*, whichever internal function would
have sent it.

This test must fail on unpatched code. If it has never been red, it proves
nothing.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest

from api.services import organization_bootstrap as bootstrap

ORGANIZATION_ID = 4242
CREATED_BY = "oss_1757000000_2f0a1b7c"


@pytest.fixture
def attempted_requests(monkeypatch):
    """Record every outbound HTTP request instead of letting it leave.

    Requests are recorded *and then refused*, so the code under test walks its
    normal "the vendor is unreachable" path. What the test measures is the
    attempt, never the success.
    """
    attempts: list[str] = []

    async def _refuse(self, request, *args, **kwargs):
        attempts.append(f"{request.method} {request.url}")
        raise httpx.ConnectError("outbound blocked by test", request=request)

    monkeypatch.setattr(httpx.AsyncClient, "send", _refuse)
    return attempts


@pytest.fixture
def unprovisioned_organization(monkeypatch):
    """An organization with nothing provisioned yet, and a free lease.

    This is the state in which upstream calls out. Anything that returned
    early — a completed bootstrap, a lease held elsewhere — would make the test
    pass for the wrong reason.
    """
    monkeypatch.setattr(
        bootstrap.db_client, "get_configuration", AsyncMock(return_value=None)
    )
    monkeypatch.setattr(
        bootstrap,
        "get_organization_ai_model_configuration_v2",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        bootstrap.db_client, "list_telephony_configurations", AsyncMock(return_value=[])
    )
    monkeypatch.setattr(
        bootstrap.db_client,
        "claim_configuration_lease",
        AsyncMock(return_value="lease-token"),
    )
    monkeypatch.setattr(
        bootstrap.db_client, "complete_configuration_lease", AsyncMock()
    )
    monkeypatch.setattr(bootstrap.db_client, "release_configuration_lease", AsyncMock())
    monkeypatch.setattr(
        bootstrap, "upsert_organization_ai_model_configuration_v2", AsyncMock()
    )


@pytest.mark.asyncio
async def test_switched_off_nothing_leaves_the_installation(
    monkeypatch, attempted_requests, unprovisioned_organization
):
    """THE test. Switched off, bootstrap must not touch the network at all.

    ``raising=False`` is load-bearing, not laziness: it keeps this test measuring
    *behaviour* rather than the presence of a symbol. On code where the patch is
    gone, the run reaches the assertion below and fails with the outbound call it
    caught — which is the sentence a reader needs — instead of an AttributeError
    that says nothing about what left the machine.
    """
    monkeypatch.setattr(
        bootstrap, "ENABLE_DOGRAH_MANAGED_SERVICES", False, raising=False
    )

    await bootstrap.ensure_organization_bootstrapped(
        ORGANIZATION_ID, created_by=CREATED_BY
    )

    assert attempted_requests == [], (
        "An authenticated request reached the vendor while Dograh-managed "
        f"services were switched off: {attempted_requests}"
    )


@pytest.mark.asyncio
async def test_switched_off_the_caller_is_not_asked_to_retry(
    monkeypatch, attempted_requests, unprovisioned_organization
):
    """Switched off, there is nothing left to provision — so say so.

    Returning False would be read as "not provisioned yet", and the five-minute
    lease would have every later request re-enter bootstrap forever.
    """
    monkeypatch.setattr(
        bootstrap, "ENABLE_DOGRAH_MANAGED_SERVICES", False, raising=False
    )

    assert (
        await bootstrap.ensure_organization_bootstrapped(
            ORGANIZATION_ID, created_by=CREATED_BY
        )
        is True
    )


@pytest.mark.asyncio
async def test_switched_on_upstream_behaviour_is_unchanged(
    monkeypatch, attempted_requests, unprovisioned_organization
):
    """The other half of the guarantee, and the one that makes it contributable.

    A switch that also changes the default is not a switch, it is a fork. With
    managed services on, the vendor call must still happen exactly as upstream
    does it.

    It is the one test here that passes on unpatched code, and that is the
    point: it proves the harness above really does observe an outbound call, so
    an empty list in the test that matters means silence rather than a broken
    spy.
    """
    monkeypatch.setattr(
        bootstrap, "ENABLE_DOGRAH_MANAGED_SERVICES", True, raising=False
    )

    await bootstrap.ensure_organization_bootstrapped(
        ORGANIZATION_ID, created_by=CREATED_BY
    )

    assert any("services.dograh.com" in attempt for attempt in attempted_requests), (
        "With managed services enabled, upstream provisioning no longer runs: "
        f"{attempted_requests}"
    )


def test_the_switch_defaults_to_upstream_behaviour(monkeypatch):
    """An operator who sets nothing gets Dograh's own behaviour, not ours."""
    import importlib

    from api import constants

    monkeypatch.delenv("ENABLE_DOGRAH_MANAGED_SERVICES", raising=False)
    reloaded = importlib.reload(constants)
    try:
        assert reloaded.ENABLE_DOGRAH_MANAGED_SERVICES is True
    finally:
        importlib.reload(constants)


def test_the_switch_reads_the_environment(monkeypatch):
    """`false` in the environment reaches the constant. Nothing subtler."""
    import importlib

    from api import constants

    monkeypatch.setenv("ENABLE_DOGRAH_MANAGED_SERVICES", "false")
    reloaded = importlib.reload(constants)
    try:
        assert reloaded.ENABLE_DOGRAH_MANAGED_SERVICES is False
    finally:
        monkeypatch.delenv("ENABLE_DOGRAH_MANAGED_SERVICES", raising=False)
        importlib.reload(constants)


def test_the_only_switch_that_exists_is_ours():
    """Guard the assumption the whole patch rests on.

    If upstream ever ships its own way to disable managed provisioning, this
    patch becomes redundant and should leave the fork rather than be carried
    (rule 8 of the fork registry). This test is the reminder to check.
    """
    assert hasattr(bootstrap, "ENABLE_DOGRAH_MANAGED_SERVICES"), (
        "The switch is gone from api/services/organization_bootstrap.py. Either "
        "an upstream merge dropped the .mark patch — in which case the "
        "installation is calling services.dograh.com again — or upstream now "
        "provides its own switch and this patch should leave the fork."
    )


@pytest.mark.asyncio
async def test_bootstrap_still_runs_on_authenticated_requests(monkeypatch):
    """Where the patch is NOT placed, and why that matters.

    The switch sits inside ``ensure_organization_bootstrapped`` rather than at
    its call sites, so it covers every caller including ones upstream adds
    later. This test pins the call site itself, so a future upstream refactor
    that stops routing OSS authentication through bootstrap is noticed rather
    than silently absorbed — at which point the switch would be guarding a code
    path nothing calls.
    """
    from api.services.auth import depends as auth_depends

    calls: list[tuple] = []

    async def _record(organization_id, *, created_by):
        calls.append((organization_id, created_by))
        return True

    monkeypatch.setattr(auth_depends, "ensure_organization_bootstrapped", _record)
    monkeypatch.setattr(auth_depends, "decode_jwt_token", lambda token: {"sub": "7"})
    monkeypatch.setattr(
        auth_depends.db_client,
        "get_user_by_id",
        AsyncMock(
            return_value=SimpleNamespace(
                id=7,
                provider_id=CREATED_BY,
                selected_organization_id=ORGANIZATION_ID,
            )
        ),
    )

    await auth_depends._handle_oss_auth("Bearer token")

    assert calls == [(ORGANIZATION_ID, CREATED_BY)], (
        "OSS authentication no longer routes through "
        "ensure_organization_bootstrapped; the switch may now be guarding a "
        "code path nothing calls."
    )

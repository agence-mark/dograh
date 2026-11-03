"""[.mark] U10 : outils communs des tests du widget public (vraie base de test, vraie application)."""

from __future__ import annotations

import uuid
from contextlib import contextmanager
from unittest.mock import patch

from api.db.models import OrganizationModel, UserModel


async def creer_agent(db_session, async_session, *, organisation_id: int | None = None, nom: str = "Agent de site"):
    """Une organisation (ou la donnée), un compte, un agent ; rend (organisation_id, user, workflow)."""
    suffixe = uuid.uuid4().hex[:10]
    if organisation_id is None:
        organisation = OrganizationModel(provider_id=f"site-org-{suffixe}")
        async_session.add(organisation)
        await async_session.flush()
        organisation_id = organisation.id
    user = UserModel(provider_id=f"site-user-{suffixe}", selected_organization_id=organisation_id)
    async_session.add(user)
    await async_session.flush()
    workflow = await db_session.create_workflow(
        name=nom, workflow_definition={}, user_id=user.id, organization_id=organisation_id
    )
    return organisation_id, user, workflow


async def creer_agent_avec_jeton(db_session, async_session, *, reglages_mark=None, allowed_domains=None, settings=None, **kw):
    organisation_id, user, workflow = await creer_agent(db_session, async_session, **kw)
    jeton = await db_session.create_embed_token(
        workflow_id=workflow.id,
        organization_id=organisation_id,
        created_by=user.id,
        allowed_domains=allowed_domains,
        settings=settings or {},
    )
    if reglages_mark is not None:
        jeton = await db_session.regler_jeton_mark(jeton.id, organisation_id, reglages_mark=reglages_mark)
    return organisation_id, user, workflow, jeton


class LimiteurEnMemoire:
    """Une fenêtre glissante en mémoire, à la place de Redis : mêmes arguments que ``RateLimiter.acquire_token``."""

    def __init__(self):
        self.appels: list[tuple] = []
        self.compte: dict[str, int] = {}

    async def acquire_token(self, organization_id, rate_limit=1, *, scope_key=None, window_seconds=1.0):
        cle = scope_key or str(organization_id)
        self.appels.append((cle, rate_limit, window_seconds))
        if self.compte.get(cle, 0) >= rate_limit:
            return False
        self.compte[cle] = self.compte.get(cle, 0) + 1
        return True


@contextmanager
def limiteur_en_memoire():
    limiteur = LimiteurEnMemoire()
    with (
        patch("api.services.site_mark.limite_ip.rate_limiter", limiteur),
        patch("api.routes.agents_site.rate_limiter", limiteur),
    ):
        yield limiteur

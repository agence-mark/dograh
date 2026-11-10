"""[.mark] Clôture, SA-9 (mineur 5) : la liste des motifs du filtre « Tous les motifs » est bornée comme la recherche d'appels.

| Test | Ce qu'il prouve |
|---|---|
| tous les clients | seuls les appels les plus récents des organisations ouvertes donnent des motifs (borne ``RECHERCHE_APPELS_MAX``) |
| un agent | de même pour la liste d'un agent |
"""

from __future__ import annotations

import pytest

from api.db import appels_liste
from api.tests.mark.test_cloture_sa5_listes_appels import _monde, _run


@pytest.fixture
async def monde(db_session, async_session):
    return await _monde(async_session, db_session, "sa9")


async def test_les_motifs_de_tous_les_clients_ne_lisent_que_les_appels_les_plus_recents(db_session, async_session, monde, monkeypatch):
    org, agent = monde
    await _run(async_session, agent, fiche={"motif": "Ancien"}, jours=10)
    await _run(async_session, agent, fiche={"motif": "Récent un"}, jours=2)
    await _run(async_session, agent, fiche={"motif": "Récent deux"}, jours=1)
    assert await db_session.lister_motifs_des_organisations([org.id]) == ["Ancien", "Récent deux", "Récent un"]  # sous la borne : tout
    monkeypatch.setattr(appels_liste, "RECHERCHE_APPELS_MAX", 2)
    assert await db_session.lister_motifs_des_organisations([org.id]) == ["Récent deux", "Récent un"]


async def test_les_motifs_d_un_agent_ne_lisent_que_ses_appels_les_plus_recents(db_session, async_session, monde, monkeypatch):
    org, agent = monde
    await _run(async_session, agent, fiche={"motif": "Ancien"}, jours=10)
    await _run(async_session, agent, fiche={"motif": "Récent un"}, jours=2)
    await _run(async_session, agent, fiche={"motif": "Récent deux"}, jours=1)
    assert len(await db_session.lister_motifs_de_l_agent(agent.id, organization_id=org.id)) == 3
    monkeypatch.setattr(appels_liste, "RECHERCHE_APPELS_MAX", 2)
    assert await db_session.lister_motifs_de_l_agent(agent.id, organization_id=org.id) == ["Récent deux", "Récent un"]

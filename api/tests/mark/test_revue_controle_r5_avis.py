"""[.mark] Revue de contrôle, points 8 et 9 (avis du visiteur) : jamais gardé en entier sans limite, jamais fermé pour toujours.

| Test | Ce qu'il prouve |
|---|---|
| base injoignable | l'avis gardé en entier sur le run porte sa date de garde |
| réduction | la purge de nuit réduit un avis gardé en entier depuis plus de la durée de conservation, pas un récent |
| envoi à la base | la date de garde ne part jamais chez le client |
| réservation expirée | un avis ``en_cours`` vieux de plus du délai peut être redonné ; un récent ferme la place |
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

from api.services.site_mark.conservation import reduire_avis_anciens
from api.services.site_mark.conversations import (
    CONSERVATION_SESSIONS_JOURS,
    DELAI_RESERVATION_AVIS_SECONDES,
    champs_du_site,
)
from api.tests.mark.site_commun import creer_agent_avec_jeton, limiteur_en_memoire
from api.tests.mark.equipe_commun import client_http
from api.tests.mark.test_site_conversations_routes import API, AVIS, CLIENT, _session, _widget


async def _avis_sur_le_run(db_session, w, session, avis):
    await db_session.update_workflow_run(session["workflow_run_id"], annotations={"embed": {"source": "embed_widget", "avis": avis}})
    return await db_session.get_workflow_run(session["workflow_run_id"], organization_id=w.org)


async def test_point_8_base_injoignable_l_avis_garde_en_entier_porte_sa_date(db_session, async_session):
    from api.routes import public_embed_conversations as routes

    w = await _widget(db_session, async_session)
    with limiteur_en_memoire(), patch.object(routes, "_base_rattachee", AsyncMock(return_value=True)), patch.object(
        routes, "_ecrire_dans_la_base", AsyncMock(return_value=None)
    ):
        async with client_http() as c:
            session = await _session(c, w)
            await db_session.update_workflow_run(session["workflow_run_id"], is_completed=True)
            r = await c.post(f"{API}/public/embed/avis/{session['session_token']}", json=AVIS, headers=CLIENT)
    assert r.status_code == 200
    run = await db_session.get_workflow_run(session["workflow_run_id"], organization_id=w.org)
    avis = run.annotations["embed"]["avis"]
    assert avis["commentaire"] == "Merci" and "garde_le" in avis  # entier, mais daté
    assert "garde_le" not in champs_du_site(run).get("avis", {})  # jamais envoyé chez le client


async def test_point_8_la_purge_reduit_un_avis_garde_trop_longtemps_et_pas_un_recent(db_session, async_session):
    w = await _widget(db_session, async_session)
    with limiteur_en_memoire():
        async with client_http() as c:
            vieux = await _session(c, w)
            recent = await _session(c, w)
    ancien = (datetime.now(UTC) - timedelta(days=CONSERVATION_SESSIONS_JOURS + 1)).isoformat()
    await _avis_sur_le_run(db_session, w, vieux, {"etoiles": 4, "commentaire": "Merci", "contact": {"mail": "a@b.fr"}, "garde_le": ancien})
    await _avis_sur_le_run(db_session, w, recent, {"etoiles": 5, "commentaire": "Super", "garde_le": datetime.now(UTC).isoformat()})
    assert await reduire_avis_anciens() >= 1
    r_vieux = await db_session.get_workflow_run(vieux["workflow_run_id"], organization_id=w.org)
    r_recent = await db_session.get_workflow_run(recent["workflow_run_id"], organization_id=w.org)
    assert r_vieux.annotations["embed"]["avis"] == {"etoiles": 4}
    assert r_recent.annotations["embed"]["avis"]["commentaire"] == "Super"


async def test_point_9_une_reservation_expiree_laisse_redonner_l_avis(db_session, async_session):
    org, user, wf, _ = await creer_agent_avec_jeton(db_session, async_session)
    run = await db_session.create_workflow_run(name="r", workflow_id=wf.id, mode="chat", user_id=user.id, organization_id=org)
    assert await db_session.reserver_avis(run.id, org) is True
    assert await db_session.reserver_avis(run.id, org) is False  # récente : la place est prise
    vieux = (datetime.now(UTC) - timedelta(seconds=DELAI_RESERVATION_AVIS_SECONDES + 5)).isoformat()
    await db_session.update_workflow_run(run.id, annotations={"embed": {"avis": {"en_cours": True, "le": vieux}}})
    assert await db_session.reserver_avis(run.id, org) is True  # expirée : le visiteur peut redonner son avis
    await db_session.update_workflow_run(run.id, annotations={"embed": {"avis": {"etoiles": 4}}})
    assert await db_session.reserver_avis(run.id, org) is False  # un vrai avis ne s'écrase jamais

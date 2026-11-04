"""[.mark] Passe de vérification V3 : la liste des clients du Hub donne, en lecture groupée, ce que l'accueil et la liste montrent
(agents, appels des 7 jours, note du juge, signalements, pannes), jamais ceux d'un autre client.

| Test | Ce qu'il prouve |
|---|---|
| statistiques par client | agents, appels 7 j, note moyenne, signalements et pannes à traiter, état « installation » sans agent |
| cloisonnement | les chiffres d'un client ne contiennent rien de l'autre ; un client sans activité est à zéro |
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text

from api.db import db_client
from api.tests.mark.equipe_commun import (  # noqa: F401
    client_http,
    creer_compte,
    creer_organisation,
    entetes,
    sans_preparation_des_organisations,
)

R = "/api/v1/relation"
pytestmark = pytest.mark.usefixtures("sans_preparation_des_organisations")


async def _probleme(org, wf, cle, par, etat="a_trier"):
    await db_client.ajouter_un_cas_d_amelioration(
        org, wf, cle, {"releve_par": par, "titre": f"Problème {cle}", "gravite": 2}, {"run_id": 1, "le": datetime.now(UTC).isoformat()}
    )
    if etat != "a_trier":
        ligne = await db_client.lire_une_amelioration_par_cle(org, wf, cle)
        await db_client.modifier_une_amelioration(org, ligne["id"], etat=etat)


async def test_la_liste_des_clients_donne_les_chiffres_de_chacun_sans_melange(db_session):
    a = await creer_organisation(db_session, "stats-a")
    b = await creer_organisation(db_session, "stats-b")
    admin, jeton = await creer_compte(db_session, "stats-admin@example.com", role="Administrateur", organisations=[a, b])
    agent = await db_session.create_workflow(name="Standard", workflow_definition={}, user_id=admin.id, organization_id=a)
    for note, il_y_a in ((4.0, 1), (5.0, 2), (1.0, 20)):  # le troisième appel date de plus de 7 jours : ignoré
        run = await db_session.create_workflow_run(f"appel-{il_y_a}", agent.id, "smallwebrtc", admin.id, organization_id=a)
        async with db_session.async_session() as s:
            await s.execute(
                text("update workflow_runs set created_at = :d, note_juge = :n where id = :i"),
                {"d": datetime.now(UTC) - timedelta(days=il_y_a), "n": note, "i": run.id},
            )
            await s.commit()
    await _probleme(a, agent.id, "client:ton:accueil", "client")
    await _probleme(a, agent.id, "deploiement:version:accueil", "deploiement")
    await _probleme(a, agent.id, "client:vieux:accueil", "client", etat="publiee")  # déjà réglé : ne compte pas

    async with client_http() as c:
        brut = await c.get(f"{R}/clients", headers=entetes(jeton))
    assert brut.status_code == 200, brut.text
    lignes = {x["id"]: x for x in brut.json()}
    assert lignes[a]["agents"] == 1 and lignes[a]["appels_7j"] == 2 and lignes[a]["note"] == 4.5
    assert lignes[a]["signalements"] == 1 and lignes[a]["pannes"] == 1
    assert lignes[a]["etat"] == "actif"  # un agent publié
    assert lignes[b]["etat"] == "installation"  # aucun agent
    assert lignes[b]["agents"] == 0 and lignes[b]["appels_7j"] == 0 and lignes[b]["note"] is None
    assert lignes[b]["signalements"] == 0 and lignes[b]["pannes"] == 0

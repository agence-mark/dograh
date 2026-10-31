"""[.mark] builder-agent-vocal, lot 6 : le tri (assigné, origine) contre la VRAIE base de test.

L'assigné et l'origine se rangent dans ``annotations["tri"]`` du run, sous verrou, sans toucher à rien d'autre ; on n'assigne qu'une
personne de l'organisation ; le filtre par origine passe avant la coupe de la page.
"""

from __future__ import annotations



async def test_l_assigne_et_l_origine_sont_ecrits_dans_les_annotations_sans_rien_toucher_d_autre(db_session, async_session, test_client_factory):
    from api.tests.mark.test_passages_fiables_signalements_et_alertes import FICHE, _monter, _run

    user, workflow = await _monter(db_session, async_session, dict(FICHE))
    contexte = {"signalements": [{"source": "agent", "motif": "m", "categorie": "autre"}]}
    run = await _run(db_session, async_session, user, workflow, contexte, annotations={"mark_apres_appel": {"etapes": {"a": 1}}})
    async with test_client_factory(user) as client:
        assigne = await client.put(f"/api/v1/tri/{run.id}", json={"identifiant": "agent:0", "assigne": user.id, "origine": "client"})
        statut = await client.put(f"/api/v1/tri/{run.id}", json={"identifiant": "agent:0", "statut": "en cours"})
        etranger = await client.put(f"/api/v1/tri/{run.id}", json={"identifiant": "agent:0", "assigne": 987654})
        par_origine = (await client.get("/api/v1/tri", params={"origine": "client"})).json()["lignes"]
        autre_origine = (await client.get("/api/v1/tri", params={"origine": "code"})).json()["lignes"]
    assert assigne.status_code == 200 and assigne.json()["assigne"] == user.id and assigne.json()["origine"] == "client"
    assert statut.json()["statut"] == "en cours" and statut.json()["assigne"] == user.id  # un statut seul garde l'assigné et l'origine
    assert etranger.status_code == 404
    assert [(l["id"], l["assigne"], l["origine"]) for l in par_origine] == [("agent:0", user.id, "client")] and autre_origine == []
    relu = await db_session.get_workflow_run_by_id(run.id)
    assert relu.annotations["mark_apres_appel"] == {"etapes": {"a": 1}} and relu.annotations["tri"]["agent:0"]["assigne"] == user.id

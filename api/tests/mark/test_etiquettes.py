"""[.mark] builder partie 2, U3 (E30) : les étiquettes des agents.

| Test | Ce qu'il prouve |
|---|---|
| poser et relire | une étiquette nouvelle est créée pour toute l'organisation, une existante garde sa casse |
| filtre | une étiquette sans agent reste proposée à la pose mais n'a plus d'agent au filtre (``nb_agents`` 0) |
| agent supprimé ou archivé | ses étiquettes ne comptent plus |
| limites | nom vide, trop long, trop d'étiquettes : 422 |
| cloisonnement | une autre organisation ne lit ni n'écrit les étiquettes, et ne pose rien sur l'agent d'un autre |
| droit | poser exige ``agents.modifier`` (membre sans la permission : 403), lire est ouvert aux membres |
| stockage | clé ``MARK_ETIQUETTES`` de ``organization_configurations``, aucune migration ; valeur abîmée = vide |
| builder | l'action ``etiquettes_agent`` lit et pose par le même code, et refuse l'agent d'un autre client |
"""

import pytest

from api.services.builder.actions.registre import Contexte, executer
from api.services.etiquettes import stockage
from api.tests.mark.equipe_commun import (
    client_http,
    creer_compte,
    creer_organisation,
    entetes,
    sans_preparation_des_organisations,  # noqa: F401
)

pytestmark = pytest.mark.usefixtures("sans_preparation_des_organisations")


async def _agent(db, org: int, user_id: int, nom: str):
    return await db.create_workflow(name=nom, workflow_definition={}, user_id=user_id, organization_id=org)


async def _monde(db, suffixe: str):
    org = await creer_organisation(db, f"etq-{suffixe}")
    user, jeton = await creer_compte(db, f"etq-{suffixe}@example.com", role="Administrateur", organisations=[org])
    return org, user, jeton


async def _poser(c, jeton, org, agent_id, etiquettes):
    return await c.put(f"/api/v1/etiquettes/agents/{agent_id}", headers=entetes(jeton, org), json={"etiquettes": etiquettes})


async def test_poser_puis_relire_cree_l_etiquette_pour_toute_l_organisation(db_session):
    org, user, jeton = await _monde(db_session, "poser")
    a = await _agent(db_session, org, user.id, "A")
    b = await _agent(db_session, org, user.id, "B")
    async with client_http() as c:
        assert (await _poser(c, jeton, org, a.id, ["Recette", "Banc"])).status_code == 200
        # « recette » en minuscules désigne l'étiquette existante : elle garde sa casse et ne se duplique pas.
        reponse = await _poser(c, jeton, org, b.id, [" recette  ", "recette"])
        relu = await c.get("/api/v1/etiquettes", headers=entetes(jeton, org))
    assert reponse.status_code == 200
    corps = relu.json()
    assert [e["nom"] for e in corps["etiquettes"]] == ["Recette", "Banc"]
    assert {e["nom"]: e["nb_agents"] for e in corps["etiquettes"]} == {"Recette": 2, "Banc": 1}
    assert corps["par_agent"] == {str(a.id): ["Recette", "Banc"], str(b.id): ["Recette"]}


async def test_une_etiquette_sans_agent_disparait_du_filtre_mais_reste_proposee(db_session):
    org, user, jeton = await _monde(db_session, "filtre")
    a = await _agent(db_session, org, user.id, "A")
    async with client_http() as c:
        await _poser(c, jeton, org, a.id, ["Banc"])
        retiree = await _poser(c, jeton, org, a.id, [])
    corps = retiree.json()
    assert corps["par_agent"] == {}
    # Elle reste dans la liste de l'organisation (à cocher), mais plus aucun agent ne la porte : le filtre ne la montre pas.
    assert corps["etiquettes"] == [{"nom": "Banc", "nb_agents": 0}]


async def test_un_agent_archive_ne_compte_plus(db_session):
    org, user, jeton = await _monde(db_session, "archive")
    a = await _agent(db_session, org, user.id, "A")
    b = await _agent(db_session, org, user.id, "B")
    async with client_http() as c:
        await _poser(c, jeton, org, a.id, ["Banc"])
        await _poser(c, jeton, org, b.id, ["Banc"])
        await db_session.update_workflow_status(a.id, "archived", organization_id=org)
        relu = await c.get("/api/v1/etiquettes", headers=entetes(jeton, org))
    corps = relu.json()
    assert corps["etiquettes"] == [{"nom": "Banc", "nb_agents": 1}]
    assert list(corps["par_agent"]) == [str(b.id)]


async def test_les_limites_sont_refusees(db_session):
    org, user, jeton = await _monde(db_session, "limites")
    a = await _agent(db_session, org, user.id, "A")
    async with client_http() as c:
        vide = await _poser(c, jeton, org, a.id, ["   "])
        long = await _poser(c, jeton, org, a.id, ["x" * (stockage.NOM_MAX + 1)])
        trop = await _poser(c, jeton, org, a.id, [f"e{i}" for i in range(stockage.PAR_AGENT_MAX + 1)])
        limite = await _poser(c, jeton, org, a.id, ["x" * stockage.NOM_MAX])
    assert vide.status_code == 422 and long.status_code == 422 and trop.status_code == 422
    assert limite.status_code == 200


async def test_une_autre_organisation_ne_lit_ni_n_ecrit_les_etiquettes(db_session):
    org_a, user_a, jeton_a = await _monde(db_session, "cloison-a")
    org_b, user_b, jeton_b = await _monde(db_session, "cloison-b")
    agent_a = await _agent(db_session, org_a, user_a.id, "Agent A")
    agent_b = await _agent(db_session, org_b, user_b.id, "Agent B")
    async with client_http() as c:
        await _poser(c, jeton_a, org_a, agent_a.id, ["Secret-de-A"])
        # B ne lit pas celles de A...
        vue_b = await c.get("/api/v1/etiquettes", headers=entetes(jeton_b, org_b))
        # ... ne pose rien sur l'agent de A (404, comme un agent inconnu)...
        croise = await _poser(c, jeton_b, org_b, agent_a.id, ["Intrus"])
        # ... et A garde exactement ce qu'il avait.
        vue_a = await c.get("/api/v1/etiquettes", headers=entetes(jeton_a, org_a))
        # Un compte de B sans rôle d'équipe ne peut pas non plus viser l'organisation de A dans l'adresse.
        _, jeton_intrus = await creer_compte(db_session, "etq-intrus@example.com", organisations=[org_b])
        interdit = await c.get("/api/v1/etiquettes", headers=entetes(jeton_intrus, org_a))
        ecrit_interdit = await _poser(c, jeton_intrus, org_a, agent_a.id, ["Intrus"])
    assert vue_b.json() == {"etiquettes": [], "par_agent": {}}
    assert croise.status_code == 404
    assert [e["nom"] for e in vue_a.json()["etiquettes"]] == ["Secret-de-A"]
    assert interdit.status_code in (401, 403) and ecrit_interdit.status_code in (401, 403)
    assert [e["nom"] for e in (await stockage.lire(org_a))["etiquettes"]] == ["Secret-de-A"]
    # Et rien d'autre que la clé de l'organisation n'a été écrit pour B.
    assert await db_session.get_configuration(org_b, stockage.CLE) is None
    assert agent_b.id not in {int(k) for k in vue_a.json()["par_agent"]}


async def test_poser_exige_modifier_les_agents_lire_reste_ouvert(db_session):
    org, user, jeton_admin = await _monde(db_session, "droit")
    a = await _agent(db_session, org, user.id, "A")
    lecteur = await db_session.creer_role(
        nom="Lecteur-etiquettes-test", labo_ouvert=True, tous_les_clients=True, permissions=["conversations.voir"], organisations=[]
    )
    membre, jeton_lecteur = await creer_compte(db_session, "etq-lecteur@example.com", organisations=[org])
    await db_session.poser_membre(membre.id, lecteur)
    async with client_http() as c:
        refuse = await _poser(c, jeton_lecteur, org, a.id, ["Banc"])
        lit = await c.get("/api/v1/etiquettes", headers=entetes(jeton_lecteur, org))
        ok = await _poser(c, jeton_admin, org, a.id, ["Banc"])
    assert refuse.status_code == 403
    assert lit.status_code == 200
    assert ok.status_code == 200


async def test_le_stockage_est_une_cle_de_la_configuration_de_l_organisation(db_session):
    org, user, jeton = await _monde(db_session, "stockage")
    a = await _agent(db_session, org, user.id, "A")
    async with client_http() as c:
        await _poser(c, jeton, org, a.id, ["Banc"])
    ligne = await db_session.get_configuration(org, "MARK_ETIQUETTES")
    assert ligne.value == {"etiquettes": ["Banc"], "agents": {str(a.id): ["Banc"]}}
    # Une valeur abîmée se lit comme vide au lieu de casser l'écran, et se réécrit proprement.
    await db_session.upsert_configuration(org, "MARK_ETIQUETTES", ["pas", "un", "dictionnaire"])
    async with client_http() as c:
        relu = await c.get("/api/v1/etiquettes", headers=entetes(jeton, org))
        reecrit = await _poser(c, jeton, org, a.id, ["Recette"])
    assert relu.json() == {"etiquettes": [], "par_agent": {}}
    assert reecrit.status_code == 200 and [e["nom"] for e in reecrit.json()["etiquettes"]] == ["Recette"]


async def test_une_ecriture_qui_se_croise_est_reprise_sans_rien_perdre(db_session, monkeypatch):
    """La session de test n'a qu'une connexion : on rejoue le croisement. Une autre écriture passe entre la lecture et
    l'écriture ; la comparaison échoue, l'étiquette est reprise depuis la nouvelle valeur et AUCUNE des deux ne se perd."""
    org, user, _ = await _monde(db_session, "course")
    a = await _agent(db_session, org, user.id, "A")
    b = await _agent(db_session, org, user.id, "B")
    await stockage.poser(org, a.id, ["Premiere"])

    vraie_lecture = stockage._valeur
    appels = {"n": 0}

    async def lecture_perimee(organisation_id):
        appels["n"] += 1
        if appels["n"] == 1:
            # Entre-temps, une autre pose a écrit : cette première lecture est périmée.
            await db_session.upsert_configuration(
                org, stockage.CLE, {"etiquettes": ["Premiere", "Concurrente"], "agents": {str(a.id): ["Premiere", "Concurrente"]}}
            )
            return {"etiquettes": ["Premiere"], "agents": {str(a.id): ["Premiere"]}}
        return await vraie_lecture(organisation_id)

    monkeypatch.setattr(stockage, "_valeur", lecture_perimee)
    vue = await stockage.poser(org, b.id, ["Seconde"])
    assert appels["n"] >= 2  # la première tentative a échoué, la seconde est repartie de la valeur à jour
    assert sorted(e["nom"] for e in vue["etiquettes"]) == ["Concurrente", "Premiere", "Seconde"]
    assert vue["par_agent"][a.id] == ["Premiere", "Concurrente"] and vue["par_agent"][b.id] == ["Seconde"]


async def test_l_action_du_builder_lit_pose_et_refuse_l_agent_d_un_autre_client(db_session):
    org_a, user_a, _ = await _monde(db_session, "action-a")
    org_b, user_b, _ = await _monde(db_session, "action-b")
    agent_a = await _agent(db_session, org_a, user_a.id, "A")
    agent_b = await _agent(db_session, org_b, user_b.id, "B")
    contexte = Contexte(user=await db_session.get_user_by_id(user_a.id), workflow_id=agent_a.id)

    pose = await executer("etiquettes_agent", {"etiquettes": ["Recette", "Banc"]}, contexte)
    assert pose["ok"] and pose["etiquettes_de_l_agent"] == ["Recette", "Banc"]
    lecture = await executer("etiquettes_agent", {}, contexte)
    assert lecture["ok"] and lecture["etiquettes_de_l_organisation"] == ["Recette", "Banc"]
    # L'écran voit la même chose : une seule source.
    assert (await stockage.lire(org_a))["par_agent"] == {agent_a.id: ["Recette", "Banc"]}

    autre = await executer("etiquettes_agent", {"workflow_id": agent_b.id, "etiquettes": ["Intrus"]}, contexte)
    assert autre["ok"] is False and autre["code"] == "introuvable"
    assert await db_session.get_configuration(org_b, stockage.CLE) is None
    vide = await executer("etiquettes_agent", {"etiquettes": ["   "]}, contexte)
    assert vide["ok"] is False

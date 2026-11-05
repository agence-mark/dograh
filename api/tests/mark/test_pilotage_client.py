"""[.mark] Builder partie 3, L5b : la page de pilotage d'un client (décision 16), par la vraie application et la vraie base.

| Test | Ce qu'il prouve |
|---|---|
| droits | un rôle à « clients choisis » lit SON client (200) et reçoit 404 pour un autre ; une clé d'API, un compte sans rôle, aucune session : refusés ; période hors liste : 422 ; 7 jours par défaut |
| chiffres | appels, résolus sans transfert, transférés, note, coût moyen et durée moyenne sont ceux de la page Qualité ; la tendance compare à la période de même durée d'avant ; un appel d'un autre client ne compte pas |
| indisponible | sans appel, chaque chiffre dit « aucun appel » ; avec des appels sans coût, le coût dit « prix » (comment l'activer) |
| motifs | par motif : appels, résolus, transférés, note |
| agents | branche en ligne (version), part du trafic, autres branches, appels, note, état « Prêt à publier » ; une lecture de la liste par agent au plus, une seule lecture des branches pour tous |
| prêt | un agent dont la liste ne répond pas rend ``null`` (jamais un état inventé) |
| alertes | seules les alertes levées depuis moins de 7 jours sont actives, la plus récente d'abord |
| problèmes graves | les problèmes à trier de gravité haute de CE client |
| installation | un client en installation rend ses étapes (titre, état), jamais un résultat ; un client servi n'en rend pas |
| lecture illisible | une lecture qui échoue rend ``null`` et son nom dans ``illisibles`` ; le reste s'affiche |
| inventaire | la route a une décision de permission au registre |
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import update

from api.db.models import WorkflowModel, WorkflowRunModel
from api.services import pilotage_client
from api.services.equipe_mark import espaces, registre_routes as registre
from api.tests.mark.equipe_commun import (
    client_http,
    creer_compte,
    creer_organisation,
    entetes,
    sans_preparation_des_organisations,  # noqa: F401
)

pytestmark = pytest.mark.usefixtures("sans_preparation_des_organisations")

GRAPHE = {"nodes": [{"id": "1", "type": "agentNode", "position": {"x": 0, "y": 0}, "data": {"name": "Accueil", "prompt": "Bonjour"}}], "edges": []}


@pytest.fixture(autouse=True)
def _cache_du_labo_propre():
    espaces.reinitialiser_cache()
    yield
    espaces.reinitialiser_cache()


def bilan(issue, *, motif=None, transfert=False, cout=0.2, duree=60.0):
    return {
        "boucle": {
            "indicateurs": {
                "issue_obtenue": issue,
                "transfert": transfert,
                "raccroche_avant_la_fin": False,
                "latence_mediane": 1.0,
                "impasses": 0,
                "motif": motif,
                "cout": cout,
                "duree": duree,
            }
        }
    }


def juge(*verdicts):
    return {"juge": {"etat": "juge", "verdicts": [{"verdict": v} for v in verdicts]}}


async def _appel(db, agent, user, org, *, annotations, il_y_a_jours=0.0):
    run = await db.create_workflow_run("appel", agent.id, "smallwebrtc", user.id, organization_id=org)
    await db.update_workflow_run(run.id, annotations=annotations)
    if il_y_a_jours:
        async with db.async_session() as session:
            await session.execute(
                update(WorkflowRunModel).where(WorkflowRunModel.id == run.id).values(created_at=datetime.now(UTC) - timedelta(days=il_y_a_jours))
            )
            await session.commit()
    return run


async def _cas(db, s: str):
    """Deux clients (A, B), chacun avec un agent publié ; un rôle « A seulement », un rôle « tous », un compte sans rôle, une clé de A."""
    a = await creer_organisation(db, f"pi-a-{s}")
    b = await creer_organisation(db, f"pi-b-{s}")
    role_a = await db.creer_role(nom=f"Pilote-A-{s}", labo_ouvert=False, tous_les_clients=False, permissions=["conversations.voir"], organisations=[a])
    limite, j_limite = await creer_compte(db, f"pi-limite-{s}@example.com", organisations=[a, b])
    await db.poser_membre(limite.id, role_a)
    large, j_large = await creer_compte(db, f"pi-large-{s}@example.com", role="Administrateur", organisations=[a, b])
    _, j_sans = await creer_compte(db, f"pi-sans-{s}@example.com", organisations=[a, b])
    _, cle = await db.create_api_key(a, "portail", large.id)
    agents = {}
    for org, nom in ((a, f"Standard A {s}"), (b, f"Standard B {s}")):
        agent = await db.create_workflow(nom, GRAPHE, large.id, org)
        agents[org] = agent
    return SimpleNamespace(a=a, b=b, limite=j_limite, large=j_large, sans=j_sans, cle=cle, agents=agents, user=large)


def _url(org: int, periode: str | None = None) -> str:
    return f"/api/v1/vues-equipe/pilotage/{org}" + (f"?periode={periode}" if periode else "")


async def _lire(cas, org, periode=None, jeton=None):
    async with client_http() as c:
        r = await c.get(_url(org, periode), headers=entetes(jeton or cas.large))
    assert r.status_code == 200, r.text
    return r.json()


def _chiffre(corps, identifiant):
    return next(c for c in corps["chiffres"] if c["id"] == identifiant)


async def test_les_droits_et_la_periode(db_session):
    cas = await _cas(db_session, "droits")
    async with client_http() as c:
        assert (await c.get(_url(cas.a), headers=entetes(cas.limite))).status_code == 200
        assert (await c.get(_url(cas.b), headers=entetes(cas.limite))).status_code == 404
        assert (await c.get(_url(cas.a), headers={"X-API-Key": cas.cle})).status_code == 403
        assert (await c.get(_url(cas.b), headers={"X-API-Key": cas.cle})).status_code == 403
        assert (await c.get(_url(cas.a), headers=entetes(cas.sans))).status_code == 403
        assert (await c.get(_url(cas.a))).status_code in (401, 403)
        assert (await c.get(_url(cas.a, "14j"), headers=entetes(cas.large))).status_code == 422
        for ecriture in ("post", "put", "delete"):
            assert (await getattr(c, ecriture)(_url(cas.a), headers=entetes(cas.large))).status_code in (404, 405)
    assert (await _lire(cas, cas.a))["periode"] == "7j" and (await _lire(cas, cas.a, "24h"))["jours"] == 1


async def test_les_chiffres_sont_ceux_de_la_qualite_avec_la_tendance_et_sans_les_appels_d_un_autre_client(db_session):
    cas = await _cas(db_session, "chiffres")
    agent, user = cas.agents[cas.a], cas.user
    # Période courante (7 j) : 4 appels. Résolu seul, résolu puis transféré, raté, résolu (note 2,5).
    await _appel(db_session, agent, user, cas.a, annotations={**bilan(True, motif="Dépannage", cout=0.1, duree=60), **juge("reussi", "reussi")}, il_y_a_jours=1)
    await _appel(db_session, agent, user, cas.a, annotations={**bilan(True, motif="Dépannage", transfert=True, cout=0.3, duree=120)}, il_y_a_jours=2)
    await _appel(db_session, agent, user, cas.a, annotations={**bilan(False, motif="Devis", cout=0.2, duree=30)}, il_y_a_jours=3)
    await _appel(db_session, agent, user, cas.a, annotations={**bilan(True, motif="Devis", cout=0.4, duree=90), **juge("reussi", "rate")}, il_y_a_jours=4)
    # Période d'avant (7 à 14 j) : 2 appels.
    await _appel(db_session, agent, user, cas.a, annotations=bilan(True, cout=0.2, duree=100), il_y_a_jours=9)
    await _appel(db_session, agent, user, cas.a, annotations=bilan(False, cout=0.2, duree=100), il_y_a_jours=10)
    # Un appel du client B : jamais compté chez A.
    await _appel(db_session, cas.agents[cas.b], user, cas.b, annotations=bilan(True), il_y_a_jours=1)

    corps = await _lire(cas, cas.a)
    assert corps["en_service"] is True and corps["tronque"] is False and corps["illisibles"] == []
    appels = _chiffre(corps, "appels")
    assert appels["valeur"] == 4 and appels["precedente"] == 2 and appels["tendance"] == 100
    assert _chiffre(corps, "resolus")["valeur"] == 50.0  # 2 résolus sans transfert sur 4
    assert _chiffre(corps, "resolus")["precedente"] == 50.0 and _chiffre(corps, "resolus")["tendance"] == 0
    assert _chiffre(corps, "transferes")["valeur"] == 25.0
    assert _chiffre(corps, "note")["valeur"] == 3.75 and _chiffre(corps, "note")["disponible"] is True
    assert _chiffre(corps, "note")["precedente"] is None and _chiffre(corps, "note")["tendance"] is None
    assert _chiffre(corps, "cout")["valeur"] == 0.25  # (0,1 + 0,3 + 0,2 + 0,4) / 4
    assert _chiffre(corps, "duree")["valeur"] == 75.0  # (60 + 120 + 30 + 90) / 4
    # Les mêmes chiffres que la page Qualité (même fonction), sur la même fenêtre.
    from api.services.boucle import qualite

    q = (await qualite.calculer(cas.a, jours=7))["global"]
    assert q["appels"] == appels["valeur"] and round(q["part_resolu_sans_transfert"] * 100, 1) == _chiffre(corps, "resolus")["valeur"] and q["note"] == 3.75
    # 24 h : seul l'appel d'il y a un jour est hors fenêtre de 24 h pile ; rien dans les 24 dernières heures.
    court = await _lire(cas, cas.a, "24h")
    assert _chiffre(court, "appels")["valeur"] is None and _chiffre(court, "appels")["raison"] == "aucun_appel"
    # 30 j : les six appels de A comptent, la période d'avant est vide (tendance absente, jamais inventée).
    long = await _lire(cas, cas.a, "30j")
    assert _chiffre(long, "appels")["valeur"] == 6 and _chiffre(long, "appels")["tendance"] is None


async def test_un_chiffre_indisponible_dit_pourquoi(db_session):
    cas = await _cas(db_session, "indispo")
    vide = await _lire(cas, cas.a)
    assert {c["raison"] for c in vide["chiffres"]} == {"aucun_appel"} and all(not c["disponible"] for c in vide["chiffres"])
    # Des appels sans coût ni note ni durée : chaque chiffre dit ce qui manque, pas seulement « aucun appel ».
    sans = {"boucle": {"indicateurs": {"issue_obtenue": True, "transfert": False, "raccroche_avant_la_fin": False, "latence_mediane": 1.0, "impasses": 0}}}
    await _appel(db_session, cas.agents[cas.a], cas.user, cas.a, annotations=sans, il_y_a_jours=1)
    corps = await _lire(cas, cas.a)
    assert _chiffre(corps, "appels")["valeur"] == 1
    assert _chiffre(corps, "cout")["raison"] == "prix" and _chiffre(corps, "note")["raison"] == "juge" and _chiffre(corps, "duree")["raison"] == "duree"


async def test_les_motifs_donnent_appels_resolus_transferes_et_note(db_session):
    cas = await _cas(db_session, "motifs")
    agent, user = cas.agents[cas.a], cas.user
    await _appel(db_session, agent, user, cas.a, annotations={**bilan(True, motif="Dépannage"), **juge("reussi", "reussi")}, il_y_a_jours=1)
    await _appel(db_session, agent, user, cas.a, annotations=bilan(True, motif="Dépannage", transfert=True), il_y_a_jours=1)
    await _appel(db_session, agent, user, cas.a, annotations=bilan(False, motif="Devis"), il_y_a_jours=1)
    motifs = (await _lire(cas, cas.a))["motifs"]
    assert motifs == [
        {"motif": "Dépannage", "appels": 2, "part_resolu": 1.0, "part_transferts": 0.5, "note": 5.0},
        {"motif": "Devis", "appels": 1, "part_resolu": 0.0, "part_transferts": 0.0, "note": None},
    ]


async def test_les_agents_disent_branche_part_autres_appels_note_et_pret(db_session, monkeypatch):
    cas = await _cas(db_session, "agents")
    agent, user, a = cas.agents[cas.a], cas.user, cas.a
    await db_session.save_workflow_draft(agent.id, workflow_definition=GRAPHE)
    await db_session.publish_workflow_draft(agent.id)
    branche, _ = await db_session.creer_une_branche(a, agent.id, "Accueil court", depuis_definition_id=None, user_id=user.id)
    principale = await db_session.obtenir_la_principale(a, agent.id)
    await db_session.regler_la_repartition(a, agent.id, {principale.id: 90, branche.id: 10})
    await _appel(db_session, agent, user, a, annotations={**bilan(True), **juge("reussi", "reussi")}, il_y_a_jours=1)
    # Un second agent jamais publié, sans appel.
    brouillon = await db_session.create_workflow("Brouillon A", GRAPHE, user.id, a)
    async with db_session.async_session() as session:
        await session.execute(update(WorkflowModel).where(WorkflowModel.id == brouillon.id).values(released_definition_id=None))
        await session.commit()

    lectures_du_pret: list[int] = []

    async def liste_factice(org, workflow_id):
        assert org == a
        lectures_du_pret.append(workflow_id)
        return [{"etat": "bloquant"}, {"etat": "a_faire"}, {"etat": "fait"}] if workflow_id == agent.id else [{"etat": "fait"}]

    monkeypatch.setattr("api.services.preparation.liste.lire_la_liste", liste_factice)
    lectures_des_branches = []
    vraie = db_session.agents_et_branches_pour_le_pilotage

    async def comptee(org):
        lectures_des_branches.append(org)
        return await vraie(org)

    monkeypatch.setattr(type(db_session), "agents_et_branches_pour_le_pilotage", lambda self, org: comptee(org))

    corps = await _lire(cas, a)
    lignes = {x["id"]: x for x in corps["agents"]}
    ligne = lignes[agent.id]
    assert ligne["publie"] is True and ligne["version"] is not None and ligne["part"] == 90
    assert ligne["autres"] == [{"nom": "Accueil court", "part": 10, "version": ligne["autres"][0]["version"]}]
    assert ligne["appels"] == 1 and ligne["note"] == 5.0
    assert ligne["pret"] == {"etat": "bloque", "n": 1}
    assert lignes[brouillon.id]["publie"] is False and lignes[brouillon.id]["appels"] == 0 and lignes[brouillon.id]["pret"] == {"etat": "pret", "n": 0}
    # Pas de requête en cascade : les branches de tous les agents en une lecture, la liste « prêt » une fois par agent.
    assert len(lectures_des_branches) == 1
    assert sorted(lectures_du_pret) == sorted([agent.id, brouillon.id])
    # Aucun agent de B chez A.
    assert cas.agents[cas.b].id not in lignes


async def test_un_agent_dont_la_liste_pret_ne_repond_pas_rend_null(db_session, monkeypatch):
    cas = await _cas(db_session, "pretnull")

    async def casse(org, workflow_id):
        raise RuntimeError("secret interne")

    monkeypatch.setattr("api.services.preparation.liste.lire_la_liste", casse)
    corps = await _lire(cas, cas.a)
    assert corps["agents"][0]["pret"] is None
    assert "secret interne" not in str(corps)


async def test_seules_les_alertes_levees_depuis_moins_de_sept_jours_sont_actives(db_session):
    from api.services.alertes_agent import reglages

    cas = await _cas(db_session, "alertes")
    wf = cas.agents[cas.a].id
    maintenant = datetime.now(UTC)

    def alerte(identifiant, jours):
        return {"id": identifiant, "type": "hausse_rates", "workflow_id": wf, "workflow_nom": "Standard", "resume": f"Résumé {identifiant}", "levee_le": (maintenant - timedelta(days=jours)).isoformat()}

    await db_session.upsert_configuration(
        cas.a, reglages.cle(wf), {"levees": [alerte("recente", 1), alerte("ancienne", 20), alerte("avant-hier", 2)]}
    )
    # Une alerte de B n'apparaît jamais chez A.
    await db_session.upsert_configuration(cas.b, reglages.cle(cas.agents[cas.b].id), {"levees": [alerte("autre", 0.5)]})
    alertes = (await _lire(cas, cas.a))["alertes"]
    assert alertes["total"] == 2 and [x["id"] for x in alertes["liste"]] == ["recente", "avant-hier"]
    assert alertes["liste"][0]["resume"] == "Résumé recente"


async def test_les_problemes_graves_sont_ceux_a_trier_de_gravite_haute_du_client(db_session):
    cas = await _cas(db_session, "graves")
    wf = cas.agents[cas.a].id
    for cle, gravite in (("g1", 3), ("g2", 3), ("n1", 2)):
        await db_session.ajouter_un_cas_d_amelioration(cas.a, wf, f"juge:{cle}:", {"releve_par": "juge", "titre": cle, "gravite": gravite}, {"run_id": 1})
    await db_session.ajouter_un_cas_d_amelioration(cas.b, cas.agents[cas.b].id, "juge:b:", {"releve_par": "juge", "titre": "b", "gravite": 3}, {"run_id": 1})
    assert (await _lire(cas, cas.a))["problemes_graves"] == 2
    assert (await _lire(cas, cas.b))["problemes_graves"] == 1


async def test_un_client_en_installation_rend_ses_etapes_et_un_client_servi_n_en_rend_pas(db_session):
    cas = await _cas(db_session, "install")
    assert (await _lire(cas, cas.a))["installation"] is None
    await db_session.creer_installation(cas.a, "Client A", cas.user.id)
    installation = (await _lire(cas, cas.a))["installation"]
    assert installation["total"] == 9 and installation["faites"] == 1 and installation["prochaine"] == 2
    assert installation["etapes"][0] == {"numero": 1, "titre": installation["etapes"][0]["titre"], "etat": "faite"}
    assert set(installation["etapes"][1]) == {"numero", "titre", "etat"}  # jamais un résultat d'étape
    assert {"en", "fr"} <= set(installation["etapes"][1]["titre"])
    # Chez B, qui n'a pas d'installation ouverte : rien.
    assert (await _lire(cas, cas.b))["installation"] is None


async def test_une_lecture_qui_echoue_est_illisible_et_le_reste_s_affiche(db_session, monkeypatch):
    cas = await _cas(db_session, "illisible")

    async def casse(*_a, **_k):
        raise RuntimeError("détail interne")

    monkeypatch.setattr("api.services.boucle.qualite.calculer_deux_periodes", casse)
    corps = await _lire(cas, cas.a)
    assert corps["chiffres"] is None and corps["motifs"] is None and "chiffres" in corps["illisibles"]
    assert corps["agents"] is not None and corps["alertes"] is not None
    assert "détail interne" not in str(corps)


def test_la_route_a_une_decision_de_permission():
    trouvee = registre.decision_de("GET", "/vues-equipe/pilotage/{organization_id}")
    assert trouvee is not None and getattr(trouvee[0], "cle", None) == "conversations.voir"


def test_la_tendance_est_relative_et_absente_sans_base():
    assert pilotage_client.tendance(150, 100) == 50 and pilotage_client.tendance(50, 100) == -50
    assert pilotage_client.tendance(None, 100) is None and pilotage_client.tendance(10, None) is None and pilotage_client.tendance(10, 0) is None


async def test_la_relation_compte_les_non_lus_du_client_et_cite_la_derniere_phrase_recue(db_session):
    cas = await _cas(db_session, "relation")
    vide = (await _lire(cas, cas.a))["relation"]
    assert vide == {"ouverts": 0, "non_lus": 0, "demandes_nouvelles": 0, "dernier": None}
    fil = await db_session.creer_fil_relation(cas.a, sorte="message", sujet="Week-end", auteur="Paul", texte="L'agent ne sait pas dire si vous intervenez le week-end.")
    await db_session.ajouter_message_relation(cas.a, fil["id"], cote="interne", auteur="Evan", texte="Note interne à ne jamais montrer")
    await db_session.creer_fil_relation(cas.b, sorte="message", sujet="Autre", auteur="Marie", texte="Texte de B")
    relation = (await _lire(cas, cas.a))["relation"]
    assert relation["non_lus"] == 1 and relation["ouverts"] == 1
    assert relation["dernier"]["texte"].startswith("L'agent ne sait pas") and relation["dernier"]["auteur"] == "Paul"
    assert "Note interne" not in str(relation) and "Texte de B" not in str(relation)
    assert (await _lire(cas, cas.b))["relation"]["dernier"]["texte"] == "Texte de B"


async def test_l_activite_recente_ne_garde_que_les_gestes_du_client_avec_leur_auteur(db_session):
    cas = await _cas(db_session, "activite")
    await db_session.ecrire_journal(user_id=cas.user.id, auteur=str(cas.user.id), action="agents.publier", organization_id=cas.a, detail={"route": "POST /x"})
    await db_session.ecrire_journal(user_id=None, auteur="builder", action="agents.branche_creee", organization_id=cas.a, detail={"par": "builder"})
    await db_session.ecrire_journal(user_id=cas.user.id, auteur=str(cas.user.id), action="agents.modifier", organization_id=cas.a, detail={})  # trop bruyant : écarté
    await db_session.ecrire_journal(user_id=cas.user.id, auteur=str(cas.user.id), action="agents.publier", organization_id=cas.b, detail={})  # un autre client
    activite = (await _lire(cas, cas.a))["activite"]
    assert [g["action"] for g in activite] == ["agents.branche_creee", "agents.publier"]
    assert activite[0]["par_builder"] is True and activite[1]["par_builder"] is False
    assert all("@" not in str(g["qui"]) for g in activite)  # jamais une adresse


def test_l_activite_nomme_l_auteur_sans_adresse():
    from datetime import UTC, datetime

    ligne = {"id": 1, "action": "agents.publier", "prenom": "Evan", "nom": "D.", "detail": None, "quand": datetime(2026, 11, 4, tzinfo=UTC)}
    assert pilotage_client.activite_recente([ligne])[0]["qui"] == "Evan D."
    assert pilotage_client.activite_recente([{**ligne, "prenom": None, "nom": None}])[0]["qui"] is None

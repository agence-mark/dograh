"""[.mark] Builder partie 3, sous-lot 10 : les vues « tous clients » de l'équipe (SE-3, E-3), par la vraie application.

| Test | Ce qu'il prouve |
|---|---|
| cloisonnement | un rôle à « clients choisis » ne voit, sur chacune des cinq vues, que ses clients : ni problèmes, ni appels, ni conversations du builder, ni lignes de compteurs d'un autre client |
| filtre refusé | demander un client que le rôle n'ouvre pas : 404 (comme s'il n'existait pas), sur chaque vue |
| tous les clients | un rôle « tous les clients » voit les deux clients, avec le nom du client sur chaque ligne ; la pagination borne la page |
| refus | une clé d'API (même créée par un Administrateur) et un compte sans rôle d'équipe : 403 sur chaque vue |
| lecture seule | aucune écriture n'existe sur le préfixe (405) ; les lectures n'écrivent rien |
| inventaire | chaque route du préfixe a une décision de permission au registre |
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from api.services.equipe_mark import espaces, registre_routes as registre
from api.tests.mark.equipe_commun import (
    client_http,
    creer_compte,
    creer_organisation,
    entetes,
    sans_preparation_des_organisations,  # noqa: F401
)

pytestmark = pytest.mark.usefixtures("sans_preparation_des_organisations")

VUES = ("ameliorations", "qualite", "compteurs", "conversations", "chat")


@pytest.fixture(autouse=True)
def _cache_du_labo_propre():
    espaces.reinitialiser_cache()
    yield
    espaces.reinitialiser_cache()


async def _le_cas(db, s: str):
    """Deux clients (A, B), chacun avec un agent, un appel, un problème relevé par le client et une conversation du builder ;
    un rôle « tous les clients », un rôle « A seulement », un compte sans rôle, une clé du client A."""
    a = await creer_organisation(db, f"ve-a-{s}")
    b = await creer_organisation(db, f"ve-b-{s}")
    role_a = await db.creer_role(nom=f"Voit-A-{s}", labo_ouvert=False, tous_les_clients=False, permissions=["conversations.voir"], organisations=[a])
    role_tous = await db.creer_role(nom=f"Voit-tous-{s}", labo_ouvert=False, tous_les_clients=True, permissions=["conversations.voir"], organisations=[])
    limite, j_limite = await creer_compte(db, f"ve-limite-{s}@example.com", organisations=[a, b])
    await db.poser_membre(limite.id, role_a)
    large, j_large = await creer_compte(db, f"ve-large-{s}@example.com", organisations=[a, b])
    await db.poser_membre(large.id, role_tous)
    _, j_sans = await creer_compte(db, f"ve-sans-{s}@example.com", organisations=[a, b])
    admin, _ = await creer_compte(db, f"ve-admin-{s}@example.com", role="Administrateur", organisations=[a, b])
    _, cle = await db.create_api_key(a, "portail", admin.id)
    definition = {"nodes": [], "edges": []}
    agents = {}
    for org, nom in ((a, f"agent A {s}"), (b, f"agent B {s}")):
        wf = await db.create_workflow(nom, definition, large.id, org)
        await db.create_workflow_run("run " + nom, wf.id, "chat", large.id, organization_id=org)
        await db.ajouter_un_cas_d_amelioration(
            org, wf.id, f"client:signalement-{org}:", {"releve_par": "client", "titre": f"Signalement {nom}", "gravite": 2}, {"run_id": 1}
        )
        await db.creer_fil(org, large.id, wf.id, f"Fil {nom}")
        agents[org] = wf.id
    return SimpleNamespace(a=a, b=b, limite=j_limite, large=j_large, sans=j_sans, cle=cle, agents=agents, large_id=large.id)


def _chemin(vue: str, **filtre) -> str:
    q = "&".join(f"{k}={v}" for k, v in filtre.items())
    return f"/api/v1/vues-equipe/{vue}" + (f"?{q}" if q else "")


def _orgs_vues(vue: str, corps: dict) -> set[int]:
    cle = {"ameliorations": "lignes", "conversations": "conversations", "chat": "fils", "compteurs": "clients", "qualite": "par_client"}[vue]
    return {x["organization_id"] for x in corps[cle]}


async def test_un_role_a_clients_choisis_ne_voit_que_les_siens_sur_chaque_vue(db_session):
    cas = await _le_cas(db_session, "1")
    async with client_http() as c:
        for vue in VUES:
            r = await c.get(_chemin(vue), headers=entetes(cas.limite))
            assert r.status_code == 200, (vue, r.text)
            vues_org = _orgs_vues(vue, r.json())
            assert cas.b not in vues_org, vue
            if vue != "qualite":  # la qualité ne compte que les appels notés ; les quatre autres ont une ligne chez A
                assert cas.a in vues_org, vue
        # Le détail ne fuit pas non plus : le nom d'un agent de B n'apparaît nulle part.
        corps = (await c.get(_chemin("ameliorations"), headers=entetes(cas.limite))).text
        assert "agent B" not in corps
        compteurs = (await c.get(_chemin("compteurs"), headers=entetes(cas.limite))).json()
        assert compteurs["total"] == 1 and compteurs["totaux"]["agents"] == 1


async def test_demander_un_client_que_le_role_n_ouvre_pas_est_un_404_sur_chaque_vue(db_session):
    cas = await _le_cas(db_session, "2")
    async with client_http() as c:
        for vue in VUES:
            r = await c.get(_chemin(vue, organization_id=cas.b), headers=entetes(cas.limite))
            assert r.status_code == 404, (vue, r.text)
            ok = await c.get(_chemin(vue, organization_id=cas.a), headers=entetes(cas.limite))
            assert ok.status_code == 200, (vue, ok.text)


async def test_un_role_tous_les_clients_voit_les_deux_avec_le_nom_du_client(db_session):
    cas = await _le_cas(db_session, "3")
    async with client_http() as c:
        for vue in ("ameliorations", "conversations", "chat", "compteurs"):
            r = await c.get(_chemin(vue), headers=entetes(cas.large))
            assert r.status_code == 200, (vue, r.text)
            assert {cas.a, cas.b} <= _orgs_vues(vue, r.json()), vue
        chat = (await c.get(_chemin("chat"), headers=entetes(cas.large))).json()
        assert all(f["organization_nom"] for f in chat["fils"])
        # La pagination borne la page et dit le total.
        page = (await c.get(_chemin("chat", limit=1), headers=entetes(cas.large))).json()
        assert len(page["fils"]) == 1 and page["total"] >= 2
        lignes = (await c.get(_chemin("ameliorations"), headers=entetes(cas.large))).json()
        assert {l["organization_nom"] for l in lignes["lignes"]} >= {"ve-a-3", "ve-b-3"}
        assert lignes["compteurs"]["a_trier"] >= 2
        assert (await c.get(_chemin("qualite", jours=9), headers=entetes(cas.large))).status_code == 422


async def test_une_cle_d_api_et_un_compte_sans_role_sont_refuses_sur_chaque_vue(db_session):
    cas = await _le_cas(db_session, "4")
    async with client_http() as c:
        for vue in VUES:
            assert (await c.get(_chemin(vue), headers={"X-API-Key": cas.cle})).status_code == 403, vue
            assert (await c.get(_chemin(vue, organization_id=cas.b), headers={"X-API-Key": cas.cle})).status_code == 403, vue
            assert (await c.get(_chemin(vue), headers=entetes(cas.sans))).status_code == 403, vue
            assert (await c.get(_chemin(vue))).status_code in (401, 403), vue


async def test_aucune_ecriture_n_existe_sur_les_vues_de_l_equipe(db_session):
    cas = await _le_cas(db_session, "5")
    async with client_http() as c:
        for vue in VUES:
            for methode in ("post", "put", "patch", "delete"):
                r = await getattr(c, methode)(_chemin(vue), headers=entetes(cas.large))
                assert r.status_code in (404, 405), (methode, vue, r.status_code)
    # Une lecture n'écrit rien : le nombre de problèmes de chaque client est le même avant et après.
    avant = await db_session.compter_ameliorations_des_organisations([cas.a, cas.b])
    async with client_http() as c:
        for vue in VUES:
            await c.get(_chemin(vue), headers=entetes(cas.large))
    assert await db_session.compter_ameliorations_des_organisations([cas.a, cas.b]) == avant


def test_chaque_route_des_vues_a_une_decision_de_permission():
    from api.app import app

    chemins = [r.path for r in app.routes if getattr(r, "path", "").startswith("/api/v1/vues-equipe")]
    assert len(chemins) == len(VUES)
    for chemin in chemins:
        decision, _ = registre.decision_de("GET", chemin.removeprefix("/api/v1"))
        assert isinstance(decision, registre.Permission) and decision.cle == "conversations.voir"


async def test_la_garde_de_la_route_refuse_aussi_seule_une_cle_et_un_compte_sans_role():
    """Deuxième verrou : même si le registre des permissions s'ouvrait, la route refuse (la garde est testée seule)."""
    from unittest.mock import AsyncMock, patch

    from fastapi import HTTPException

    from api.routes import vues_equipe

    cle = SimpleNamespace(id=1, par_cle_api=True)
    with pytest.raises(HTTPException) as e:
        await vues_equipe.equipe(user=cle, x_api_key=None)
    assert e.value.status_code == 403
    session = SimpleNamespace(id=2, par_cle_api=False)
    with patch.object(vues_equipe, "acces_de", AsyncMock(return_value=None)):
        with pytest.raises(HTTPException) as e:
            await vues_equipe.equipe(user=session, x_api_key=None)
        assert e.value.status_code == 403
    with patch.object(vues_equipe, "acces_de", AsyncMock(return_value=object())):
        assert await vues_equipe.equipe(user=session, x_api_key=None) is session


async def test_les_totaux_de_la_barre_comptent_les_clients_que_le_role_ouvre(db_session):
    """Les pastilles « Chat » et « À améliorer » du Labo : problèmes à trier et conversations qui attendent, tous clients ouverts."""
    cas = await _le_cas(db_session, "6")
    for org in (cas.a, cas.b):
        fil = (await db_session.lister_fils(org))[0]
        await db_session.modifier_fil(org, fil.id, changements=2, etat="terminee")
    async with client_http() as c:
        large = (await c.get(_chemin("compteurs"), headers=entetes(cas.large))).json()["totaux"]
        limite = (await c.get(_chemin("compteurs"), headers=entetes(cas.limite))).json()["totaux"]
    assert large["chat_en_attente"] >= 2 and large["a_trier"] >= 2
    assert limite["chat_en_attente"] == 1 and limite["a_trier"] == 1

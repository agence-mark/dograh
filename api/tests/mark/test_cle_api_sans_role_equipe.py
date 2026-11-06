"""[.mark] Revue serveur B1 : une clé d'API n'a jamais le rôle d'équipe de la personne qui l'a créée.

Le cas réel : la clé du portail du client A est créée par un Administrateur (tous les clients ouverts). Avant la correction,
la clé se présentait comme lui et voyait tous les clients.

| Test | Ce qu'il prouve |
|---|---|
| espaces | ``/espaces`` et ``/espaces/conversations`` refusent la clé (403), même créée par un Administrateur |
| organisations | ``/organizations`` refuse la clé (ou ne rendrait que A) ; ses appels ne changent aucune appartenance du créateur |
| sélection | la clé ne déplace pas l'organisation choisie de son créateur vers un autre client |
| profil | ``/equipe-mark/moi`` par la clé : aucun rôle, aucune permission |
| builder | la clé du client ne lance pas le builder (cerveau et clé du Labo) : 403 ; ``est_membre_de_l_equipe`` est faux |
"""

from types import SimpleNamespace

import pytest

from api.services.builder.bibliotheque import droits
from api.services.equipe_mark import espaces
from api.tests.mark.equipe_commun import (
    client_http,
    creer_compte,
    creer_organisation,
    sans_preparation_des_organisations,  # noqa: F401
)

pytestmark = pytest.mark.usefixtures("sans_preparation_des_organisations")


@pytest.fixture(autouse=True)
def _cache_du_labo_propre():
    espaces.reinitialiser_cache()
    yield
    espaces.reinitialiser_cache()


async def _le_cas_du_portail(db, suffixe: str):
    """Labo, clients A et B, un Administrateur membre des trois, une clé du client A créée par lui."""
    labo = await creer_organisation(db, f"b1-labo-{suffixe}")
    a = await creer_organisation(db, f"b1-client-a-{suffixe}")
    b = await creer_organisation(db, f"b1-client-b-{suffixe}")
    await espaces.definir_labo(labo, True)
    admin, _ = await creer_compte(
        db, f"b1-admin-{suffixe}@example.com", role="Administrateur", organisations=[labo, a, b]
    )
    _, cle = await db.create_api_key(a, "portail", admin.id)
    definition = {"nodes": [], "edges": []}
    agents = {}
    for org, nom in ((a, "agent A"), (b, "agent B")):
        wf = await db.create_workflow(nom, definition, admin.id, org)
        await db.create_workflow_run("run " + nom, wf.id, "chat", admin.id, organization_id=org)
        agents[org] = wf.id
    return SimpleNamespace(labo=labo, a=a, b=b, admin=admin, cle=cle, agents=agents)


async def test_la_cle_d_un_client_n_ouvre_pas_les_espaces(db_session):
    cas = await _le_cas_du_portail(db_session, "1")
    en_tete = {"X-API-Key": cas.cle}
    async with client_http() as c:
        conversations = await c.get("/api/v1/espaces/conversations", headers=en_tete)
        une_autre = await c.get(f"/api/v1/espaces/conversations?organization_id={cas.b}", headers=en_tete)
        liste = await c.get("/api/v1/espaces", headers=en_tete)
    assert conversations.status_code == 403
    assert une_autre.status_code == 403
    assert liste.status_code == 403
    assert cas.cle not in conversations.text


async def test_la_cle_ne_liste_que_son_organisation_et_ne_touche_pas_aux_appartenances(db_session):
    cas = await _le_cas_du_portail(db_session, "2")
    avant = set(await db_session.organisations_du_compte(cas.admin.id))
    async with client_http() as c:
        r = await c.get("/api/v1/organizations", headers={"X-API-Key": cas.cle})
    # La route de l'amont refuse déjà les clés (``reject_api_key_auth``) ; si elle s'ouvrait, seule A serait permise.
    assert r.status_code == 403 or [o["id"] for o in r.json()["organizations"]] == [cas.a]
    assert set(await db_session.organisations_du_compte(cas.admin.id)) == avant


async def test_la_cle_ne_deplace_pas_son_createur_vers_un_autre_client(db_session):
    cas = await _le_cas_du_portail(db_session, "3")
    async with client_http() as c:
        r = await c.put(
            "/api/v1/organizations/selected", headers={"X-API-Key": cas.cle}, json={"organization_id": cas.b}
        )
    assert r.status_code in (403, 404)
    createur = await db_session.get_user_by_id(cas.admin.id)
    assert createur.selected_organization_id != cas.b


async def test_la_cle_n_a_ni_role_ni_permission_au_profil(db_session):
    cas = await _le_cas_du_portail(db_session, "4")
    async with client_http() as c:
        r = await c.get("/api/v1/equipe-mark/moi", headers={"X-API-Key": cas.cle})
    assert r.status_code == 200
    assert r.json()["role"] is None
    assert r.json()["permissions"] == []


async def test_la_cle_d_un_client_ne_lance_pas_le_builder_avec_le_cerveau_du_labo(db_session):
    cas = await _le_cas_du_portail(db_session, "5")
    async with client_http() as c:
        r = await c.post(
            "/api/v1/builder/conversation",
            headers={"X-API-Key": cas.cle},
            json={"workflow_id": cas.agents[cas.a], "message": "Bonjour"},
        )
    assert r.status_code == 403
    cle = SimpleNamespace(id=cas.admin.id, selected_organization_id=cas.a, par_cle_api=True)
    session = SimpleNamespace(id=cas.admin.id, selected_organization_id=cas.a)
    assert await droits.est_membre_de_l_equipe(cle) is False
    assert await droits.est_membre_de_l_equipe(session) is True

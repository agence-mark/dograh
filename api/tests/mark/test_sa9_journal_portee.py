"""[.mark] Clôture, SA-9 (revue, important 1) : le journal de l'équipe ne rend que les organisations que le rôle ouvre.

| Test | Ce qu'il prouve |
|---|---|
| role_a_ne_lit_pas_b | un rôle qui n'ouvre que le client A ne lit pas les lignes de B, ni en ciblant B dans l'adresse (réponse vide) |
| lignes_d_equipe | sans ``equipe.gerer``, aucune ligne sans organisation ; avec, elles y sont |
| types | la liste des types de gestes suit la même portée |
"""

from __future__ import annotations

import pytest

from api.services.equipe_mark import espaces
from api.tests.mark.equipe_commun import (
    client_http,
    creer_compte,
    creer_organisation,
    entetes,
    sans_preparation_des_organisations,  # noqa: F401
)

pytestmark = pytest.mark.usefixtures("sans_preparation_des_organisations")


@pytest.fixture(autouse=True)
def _cache_du_labo_propre():
    espaces.reinitialiser_cache()
    yield
    espaces.reinitialiser_cache()


async def _monde(db):
    labo = await creer_organisation(db, "sa9j-labo")
    a = await creer_organisation(db, "sa9j-a")
    b = await creer_organisation(db, "sa9j-b")
    await espaces.definir_labo(labo, True)
    for org, action in ((a, "sa9.geste_a"), (b, "sa9.geste_b"), (labo, "sa9.geste_labo"), (None, "sa9.geste_equipe")):
        await db.ecrire_journal(user_id=None, auteur="t", action=action, organization_id=org, detail=None, origine="ecran")
    return labo, a, b


def _actions(reponse):
    return {ligne["action"] for ligne in reponse.json()["lignes"] if ligne["action"].startswith("sa9.")}


async def test_role_a_ne_lit_pas_b(db_session):
    db = db_session
    labo, a, b = await _monde(db)
    await db.creer_role(nom="sa9j-role-a", labo_ouvert=False, tous_les_clients=False, permissions=["journal.lire"], organisations=[a])
    _, jeton = await creer_compte(db, "sa9j-a@example.com", role="sa9j-role-a", organisations=[a])
    _, jeton_admin = await creer_compte(db, "sa9j-admin@example.com", role="Administrateur", organisations=[labo, a, b])
    async with client_http() as c:
        tout = await c.get("/api/v1/equipe-mark/journal?limit=100", headers=entetes(jeton, a))
        cible_b = await c.get(f"/api/v1/equipe-mark/journal?organization_id={b}", headers=entetes(jeton, a))
        cible_labo = await c.get(f"/api/v1/equipe-mark/journal?organization_id={labo}", headers=entetes(jeton, a))
        admin = await c.get("/api/v1/equipe-mark/journal?limit=100", headers=entetes(jeton_admin, a))
    assert tout.status_code == 200
    assert _actions(tout) == {"sa9.geste_a"}  # ni B, ni le Labo, ni les gestes de l'équipe
    assert cible_b.status_code == 200 and cible_b.json()["total"] == 0 and cible_b.json()["lignes"] == []
    assert cible_labo.json()["total"] == 0
    assert {"sa9.geste_a", "sa9.geste_b", "sa9.geste_labo", "sa9.geste_equipe"} <= _actions(admin)


async def test_sans_equipe_gerer_pas_de_lignes_d_equipe_et_avec_elles_y_sont(db_session):
    db = db_session
    labo, a, b = await _monde(db)
    await db.creer_role(nom="sa9j-tous", labo_ouvert=True, tous_les_clients=True, permissions=["journal.lire"], organisations=[])
    await db.creer_role(nom="sa9j-tous-gere", labo_ouvert=True, tous_les_clients=True, permissions=["journal.lire", "equipe.gerer"], organisations=[])
    _, sans = await creer_compte(db, "sa9j-sans@example.com", role="sa9j-tous", organisations=[labo, a])
    _, avec = await creer_compte(db, "sa9j-avec@example.com", role="sa9j-tous-gere", organisations=[labo, a])
    async with client_http() as c:
        r_sans = await c.get("/api/v1/equipe-mark/journal?limit=100", headers=entetes(sans, a))
        r_avec = await c.get("/api/v1/equipe-mark/journal?limit=100", headers=entetes(avec, a))
        t_sans = await c.get("/api/v1/equipe-mark/journal/types", headers=entetes(sans, a))
        t_avec = await c.get("/api/v1/equipe-mark/journal/types", headers=entetes(avec, a))
    assert _actions(r_sans) == {"sa9.geste_a", "sa9.geste_b", "sa9.geste_labo"}
    assert "sa9.geste_equipe" in _actions(r_avec)
    assert "sa9.geste_equipe" not in t_sans.json() and "sa9.geste_equipe" in t_avec.json()


async def test_un_role_sans_le_labo_ne_lit_pas_les_lignes_du_labo(db_session):
    db = db_session
    labo, a, b = await _monde(db)
    await db.creer_role(nom="sa9j-clients", labo_ouvert=False, tous_les_clients=True, permissions=["journal.lire"], organisations=[])
    _, jeton = await creer_compte(db, "sa9j-clients@example.com", role="sa9j-clients", organisations=[a])
    async with client_http() as c:
        r = await c.get("/api/v1/equipe-mark/journal?limit=100", headers=entetes(jeton, a))
    assert _actions(r) == {"sa9.geste_a", "sa9.geste_b"}

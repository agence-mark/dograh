"""[.mark] Clôture, SA-9 (mineur 8) : la clé du portail appartient à la personne qui l'a régénérée ; la liste des membres le dit.

| Test | Ce qu'il prouve |
|---|---|
| compte | ``GET /equipe-mark/membres`` rend, par membre, le nombre de clés du portail actives qu'il porte (en une requête groupée) ; une clé archivée ne compte plus |
| blocage | bloquer cette personne coupe bien la clé du portail (c'est ce que la fenêtre de blocage annonce) |
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


async def test_la_liste_des_membres_dit_qui_porte_une_cle_de_portail_et_bloquer_cette_personne_la_coupe(db_session):
    db = db_session
    labo = await creer_organisation(db, "sa9p-labo")
    client = await creer_organisation(db, "sa9p-client")
    await espaces.definir_labo(labo, True)
    _, jeton_a = await creer_compte(db, "sa9p-a@example.com", role="Administrateur", organisations=[labo, client])
    autre, jeton_b = await creer_compte(db, "sa9p-b@example.com", role="Administrateur", organisations=[labo, client])
    async with client_http() as c:
        cle = (await c.post("/api/v1/user/api-keys/portail/regenerer", headers=entetes(jeton_b, client))).json()
        membres = (await c.get("/api/v1/equipe-mark/membres?limit=100", headers=entetes(jeton_a, client))).json()["membres"]
        par_id = {m["user_id"]: m["cles_portail"] for m in membres}
        assert par_id[autre.id] == 1 and sum(par_id.values()) == 1
        # bloquer cette personne coupe le portail
        assert (await c.get("/api/v1/auth/me", headers={"X-API-Key": cle["api_key"]})).status_code == 200
        await c.put(f"/api/v1/equipe-mark/membres/{autre.id}/acces", headers=entetes(jeton_a, client), json={"actif": False})
        assert (await c.get("/api/v1/auth/me", headers={"X-API-Key": cle["api_key"]})).status_code in {401, 403}
        # une clé archivée ne compte plus
        await c.delete(f"/api/v1/user/api-keys/{cle['id']}", headers=entetes(jeton_a, client))
        membres = (await c.get("/api/v1/equipe-mark/membres?limit=100", headers=entetes(jeton_a, client))).json()["membres"]
    assert all(m["cles_portail"] == 0 for m in membres)

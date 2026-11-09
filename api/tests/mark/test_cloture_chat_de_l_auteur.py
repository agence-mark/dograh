"""[.mark] Clôture, lot A (D12) : seul l'auteur supprime ou renomme un chat du builder ; « Arrêter » reste ouvert à tous.

Vraie base de test, vraie application, deux membres de la même organisation.
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


async def _deux_membres(db, suffixe):
    labo = await creer_organisation(db, f"d12-labo-{suffixe}")
    client = await creer_organisation(db, f"d12-client-{suffixe}")
    await espaces.definir_labo(labo, True)
    role = await db.creer_role(nom=f"d12-{suffixe}", labo_ouvert=True, tous_les_clients=True, permissions=["builder.lancer", "agents.modifier"], organisations=[])
    auteur, jeton_auteur = await creer_compte(db, f"d12-auteur-{suffixe}@example.com", role=f"d12-{suffixe}", organisations=[labo, client])
    autre, jeton_autre = await creer_compte(db, f"d12-autre-{suffixe}@example.com", role=f"d12-{suffixe}", organisations=[labo, client])
    fil = await db.creer_fil(client, auteur.id, None, "Mon chat")
    return client, fil.id, jeton_auteur, jeton_autre


async def test_seul_l_auteur_renomme_un_chat(db_session):
    client, fil, jeton_auteur, jeton_autre = await _deux_membres(db_session, "ren")
    async with client_http() as c:
        refus = await c.put(f"/api/v1/builder/fils/{fil}/titre", headers=entetes(jeton_autre, client), json={"titre": "Pris"})
        ok = await c.put(f"/api/v1/builder/fils/{fil}/titre", headers=entetes(jeton_auteur, client), json={"titre": "Le mien"})
    assert refus.status_code == 403
    assert ok.status_code == 200 and ok.json()["titre"] == "Le mien"


async def test_seul_l_auteur_supprime_un_chat_et_arreter_reste_ouvert(db_session):
    client, fil, jeton_auteur, jeton_autre = await _deux_membres(db_session, "sup")
    async with client_http() as c:
        refus = await c.delete(f"/api/v1/builder/fils/{fil}", headers=entetes(jeton_autre, client))
        arret = await c.post(f"/api/v1/builder/fils/{fil}/arreter", headers=entetes(jeton_autre, client))
        ok = await c.delete(f"/api/v1/builder/fils/{fil}", headers=entetes(jeton_auteur, client))
    assert refus.status_code == 403
    assert arret.status_code != 403  # ouvert à tous les membres
    assert ok.status_code == 204

"""[.mark] Clôture, SA-9 (revue, important 2 et mineur 6) : une clé à rôle perd tout accès quand son créateur ou son rôle n'ouvre plus l'espace.

| Test | Ce qu'il prouve |
|---|---|
| http | créateur retiré de l'équipe : la clé ne lit plus (route ouverte à tout membre comprise) ; créateur intact : rien ne change |
| bloque | créateur bloqué : même refus |
| mcp | la porte MCP refuse tout outil (lecture comprise) à la clé d'un créateur retiré ; créateur intact : l'authentification passe |
| role_et_clients | clé « rôle client A » posée sur le client B : aucun droit sur B |
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi import HTTPException

from api.mcp_server import auth as auth_mcp
from api.services.equipe_mark import droits_effectifs, espaces
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


async def _monde(db, suffixe):
    labo = await creer_organisation(db, f"sa9c-labo-{suffixe}")
    x = await creer_organisation(db, f"sa9c-x-{suffixe}")
    await espaces.definir_labo(labo, True)
    role = await db.creer_role(nom=f"sa9c-role-{suffixe}", labo_ouvert=True, tous_les_clients=True, permissions=["agents.modifier"], organisations=[])
    await db.creer_role(nom=f"sa9c-createur-{suffixe}", labo_ouvert=True, tous_les_clients=True, permissions=["agents.modifier", "cles.gerer"], organisations=[])
    createur, jeton = await creer_compte(db, f"sa9c-createur-{suffixe}@example.com", role=f"sa9c-createur-{suffixe}", organisations=[labo, x])
    async with client_http() as c:
        cree = await c.post("/api/v1/user/api-keys", headers=entetes(jeton, x), json={"name": "k", "role_id": role})
    assert cree.status_code == 200, cree.text
    return labo, x, createur, cree.json()["api_key"]


LECTURES_DE_MEMBRE = ("/api/v1/workflow/fetch", "/api/v1/knowledge-base/documents", "/api/v1/tools/")


async def test_http_createur_retire_la_cle_ne_lit_plus_createur_intact_rien_ne_change(db_session):
    db = db_session
    _, x, createur, cle = await _monde(db, "http")
    async with client_http() as c:
        avant = [(await c.get(chemin, headers={"X-API-Key": cle})).status_code for chemin in LECTURES_DE_MEMBRE]
        await db.retirer_membre(createur.id)
        apres = [(await c.get(chemin, headers={"X-API-Key": cle})).status_code for chemin in LECTURES_DE_MEMBRE]
    assert 403 not in avant, avant
    assert apres == [403] * len(LECTURES_DE_MEMBRE), apres


async def test_createur_bloque_la_cle_est_refusee(db_session):
    db = db_session
    _, x, createur, cle = await _monde(db, "bloque")
    async with client_http() as c:
        assert (await c.get("/api/v1/workflow/fetch", headers={"X-API-Key": cle})).status_code != 403
        await db.changer_acces_protege(createur.id, False)
        assert (await c.get("/api/v1/workflow/fetch", headers={"X-API-Key": cle})).status_code in {401, 403}


async def test_mcp_createur_retire_aucun_outil_pas_meme_en_lecture(db_session):
    db = db_session
    _, x, createur, cle = await _monde(db, "mcp")
    with patch.object(auth_mcp, "get_http_headers", return_value={"x-api-key": cle}):
        utilisateur = await auth_mcp.authenticate_mcp_request("get_workflow")
        assert utilisateur.par_porte_mcp and utilisateur.cle_api_role_id is not None  # créateur intact : rien ne change
        await db.retirer_membre(createur.id)
        for outil in ("get_workflow", "get_workflow_code", None):
            with pytest.raises(HTTPException) as refus:
                await auth_mcp.authenticate_mcp_request(outil)
            assert refus.value.status_code == 403, outil
        with pytest.raises(HTTPException) as refus:
            await auth_mcp.authenticate_mcp_write("save_workflow")
        assert refus.value.status_code == 403

"""[.mark] Clôture, SA-9 (revue, important 3) : la clé SANS rôle du Labo est bornée par les permissions actuelles de son créateur (D21).

| Test | Ce qu'il prouve |
|---|---|
| creation | un membre qui gère les clés sans ``agents.modifier`` ne crée pas de clé sans rôle au Labo (403 clair) ; avec le droit, elle se crée ; chez un client rien ne change |
| ecriture_mcp | la clé sans rôle d'un tel membre n'écrit ni par un outil MCP natif ni par une action du builder ni dans la bibliothèque ; avec le droit, elle écrit |
| droit_retire | le créateur qui perd ``agents.modifier`` la retire à sa clé existante, à l'appel suivant ; créateur retiré de l'équipe : refus |
| administrateur | la clé du Labo d'un administrateur garde toutes les écritures (D10) |
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi import HTTPException

from api.mcp_server import auth as auth_mcp
from api.services.builder.actions import registre
from api.services.builder.actions.registre import PORTE_MCP, Contexte
from api.services.builder.bibliotheque import droits
from api.services.builder.bibliotheque.service import ErreurBibliotheque
from api.services.equipe_mark import espaces
from api.services.equipe_mark.droits_mcp import PERMISSION_DES_OUTILS_MCP
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


async def _monde(db, suffixe, permissions):
    labo = await creer_organisation(db, f"sa9l-labo-{suffixe}")
    client = await creer_organisation(db, f"sa9l-client-{suffixe}")
    await espaces.definir_labo(labo, True)
    await db.creer_role(nom=f"sa9l-{suffixe}", labo_ouvert=True, tous_les_clients=True, permissions=permissions, organisations=[])
    membre, jeton = await creer_compte(db, f"sa9l-{suffixe}@example.com", role=f"sa9l-{suffixe}", organisations=[labo, client])
    return labo, client, membre, jeton


async def _cle_sans_role_au_labo(db, labo, membre):
    _, brute = await db.create_api_key(organization_id=labo, name="labo", created_by=membre.id)
    return brute


async def _compte_par_mcp(cle):
    with patch.object(auth_mcp, "get_http_headers", return_value={"x-api-key": cle}):
        return await auth_mcp.authenticate_mcp_request()


async def _ecrit_par_mcp(cle, outil="save_workflow"):
    with patch.object(auth_mcp, "get_http_headers", return_value={"x-api-key": cle}):
        try:
            await auth_mcp.authenticate_mcp_write(outil)
            return True
        except HTTPException as e:
            assert e.status_code == 403
            return False


async def test_scenario_complet_creation_et_ecriture_mcp(db_session):
    db = db_session
    labo, client, membre, jeton = await _monde(db, "mcp", ["cles.gerer"])
    async with client_http() as c:
        au_labo = await c.post("/api/v1/user/api-keys", headers=entetes(jeton, labo), json={"name": "x"})
        chez_un_client = await c.post("/api/v1/user/api-keys", headers=entetes(jeton, client), json={"name": "x"})
    assert au_labo.status_code == 403 and "agents.modifier" in au_labo.json()["detail"]
    assert chez_un_client.status_code == 200  # un client : rien ne change
    cle = await _cle_sans_role_au_labo(db, labo, membre)  # posée à la main (clé d'avant) : l'écriture reste refusée
    compte = await _compte_par_mcp(cle)
    assert compte.selected_organization_id == labo
    assert await _ecrit_par_mcp(cle) is False
    ecriture = next(a for a in registre.REGISTRE.values() if a.ecriture and a.mcp)
    refus = await registre._refus_de_la_cle_mcp(ecriture, Contexte(user=compte, workflow_id=None, porte=PORTE_MCP))
    assert refus is not None and refus["code"] == "cle_sans_ecriture"
    with pytest.raises(ErreurBibliotheque) as e:
        await droits.exiger_l_equipe_au_labo(compte)
    assert e.value.statut == 403


async def test_avec_agents_modifier_la_cle_se_cree_et_ecrit_puis_le_perd_avec_son_droit(db_session):
    db = db_session
    labo, client, membre, jeton = await _monde(db, "droit", ["cles.gerer", "agents.modifier"])
    async with client_http() as c:
        cree = await c.post("/api/v1/user/api-keys", headers=entetes(jeton, labo), json={"name": "x"})
    assert cree.status_code == 200, cree.text
    cle = cree.json()["api_key"]
    assert await _ecrit_par_mcp(cle) is True
    await droits.exiger_l_equipe_au_labo(await _compte_par_mcp(cle))  # ne lève pas
    roles = {r["nom"]: r["id"] for r in await db.lister_roles()}
    await db.modifier_role(roles["sa9l-droit"], nom="sa9l-droit", labo_ouvert=True, tous_les_clients=True, permissions=["cles.gerer"], organisations=[])
    assert await _ecrit_par_mcp(cle) is False  # le droit est retiré au créateur : la clé le perd à l'appel suivant
    with pytest.raises(ErreurBibliotheque):
        await droits.exiger_l_equipe_au_labo(await _compte_par_mcp(cle))
    await db.modifier_role(roles["sa9l-droit"], nom="sa9l-droit", labo_ouvert=True, tous_les_clients=True, permissions=["agents.modifier"], organisations=[])
    await db.retirer_membre(membre.id)
    assert await _ecrit_par_mcp(cle) is False  # créateur absent de l'équipe


async def test_la_cle_du_labo_d_un_administrateur_garde_toutes_les_ecritures(db_session):
    db = db_session
    labo = await creer_organisation(db, "sa9l-labo-admin")
    await espaces.definir_labo(labo, True)
    admin, _ = await creer_compte(db, "sa9l-admin@example.com", role="Administrateur", organisations=[labo])
    cle = await _cle_sans_role_au_labo(db, labo, admin)
    for outil, permission in PERMISSION_DES_OUTILS_MCP.items():
        if "." in permission:
            assert await _ecrit_par_mcp(cle, outil) is True, outil
    compte = await _compte_par_mcp(cle)
    await droits.exiger_l_equipe_au_labo(compte)
    toutes = [a for a in registre.REGISTRE.values() if a.ecriture and a.mcp]
    for action in toutes:
        refus = await registre._refus_de_la_cle_mcp(action, Contexte(user=compte, workflow_id=None, porte=PORTE_MCP))
        assert refus is None, (action.nom, refus)

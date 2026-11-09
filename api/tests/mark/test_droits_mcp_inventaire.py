"""[.mark] Clôture, lot A (D21) : chaque outil du serveur MCP a sa permission dans LA table de droits (celle de l'écran et de l'API).

Un outil sans ligne échoue ici : on ne livre pas un outil MCP sans décision de droits. Les actions du builder lisent la leur dans la table des
familles (``familles_actions``), les outils natifs dans ``droits_mcp``.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from api.mcp_server import auth
from api.mcp_server.server import mcp
from api.services.builder.actions import familles_actions
from api.services.builder.actions.registre import REGISTRE
from api.services.equipe_mark import droits_effectifs
from api.services.equipe_mark.droits_mcp import LECTURE_AGENTS, OUVERT, PERMISSION_DES_OUTILS_MCP
from api.services.equipe_mark.permissions import PERMISSIONS, PERMISSIONS_JAMAIS_PAR_CLE_A_ROLE


def _utilisateur(role_id):
    return type(
        "U",
        (),
        {"id": 1, "selected_organization_id": 5, "par_cle_api": True, "par_porte_mcp": True, "cle_api_id": 1, "cle_api_role_id": role_id},
    )()


async def test_chaque_outil_mcp_a_sa_permission():
    outils = {o.name for o in await mcp.list_tools()}
    sans_ligne = sorted(n for n in outils if n not in PERMISSION_DES_OUTILS_MCP and not (n in REGISTRE and REGISTRE[n].mcp))
    assert not sans_ligne, f"Outils MCP sans décision de droits : {sans_ligne}"


def test_les_permissions_de_la_table_existent():
    for nom, valeur in PERMISSION_DES_OUTILS_MCP.items():
        assert valeur in (LECTURE_AGENTS, OUVERT) or valeur in PERMISSIONS, nom
    for action in REGISTRE.values():
        permission = familles_actions.permission_de(action.nom, action.famille or "irreversible")
        assert permission is None or permission in PERMISSIONS, action.nom


def test_aucun_outil_n_exige_un_geste_de_l_equipe():
    exigees = {v for v in PERMISSION_DES_OUTILS_MCP.values() if v in PERMISSIONS}
    exigees |= {familles_actions.permission_de(a.nom, a.famille or "irreversible") for a in REGISTRE.values() if a.mcp}
    assert not (exigees & PERMISSIONS_JAMAIS_PAR_CLE_A_ROLE)


async def _ecrire_avec(role_id, permissions_du_role):
    """Un appel d'écriture par la porte MCP avec une clé à rôle dont les droits sont ``permissions_du_role``."""
    with (
        patch.object(auth, "authenticate_mcp_request", AsyncMock(return_value=_utilisateur(role_id))),
        patch.object(droits_effectifs, "permissions_de", AsyncMock(return_value=frozenset(permissions_du_role))),
    ):
        return await auth.authenticate_mcp_write("save_workflow")


async def test_une_cle_a_role_ecrit_par_mcp_si_son_role_porte_la_permission():
    assert await _ecrire_avec(3, {"agents.modifier"})
    with pytest.raises(HTTPException) as erreur:
        await _ecrire_avec(3, {"conversations.voir"})
    assert erreur.value.status_code == 403


async def test_une_cle_sans_role_garde_la_regle_de_la_cle_du_labo():
    with (
        patch.object(auth, "authenticate_mcp_request", AsyncMock(return_value=_utilisateur(None))),
        patch("api.services.builder.bibliotheque.droits._cle_du_labo_par_mcp", AsyncMock(return_value=False)),
        pytest.raises(HTTPException) as erreur,
    ):
        await auth.authenticate_mcp_write("save_workflow")
    assert erreur.value.status_code == 403


async def test_la_lecture_des_agents_est_fermee_a_une_cle_de_client_sans_role():
    with (
        patch.object(auth, "get_http_headers", return_value={"x-api-key": "k"}),
        patch.object(auth, "_handle_api_key_auth", AsyncMock(return_value=_utilisateur(None))),
        patch("api.services.builder.constantes.organisation_bibliotheque", return_value=99),
    ):
        with pytest.raises(HTTPException) as erreur:
            await auth.authenticate_mcp_request("list_workflows")
        assert erreur.value.status_code == 403
        await auth.authenticate_mcp_request("list_node_types")  # documentation et types de nœuds restent ouverts


def test_les_trois_interrupteurs_lisent_la_meme_table_de_permissions():
    """Décision d'Evan du 09/11 : chaque geste qui coûte ou engage a UN interrupteur, et sa permission est celle de la table des familles."""
    from api.services.equipe_mark.droits_mcp import ACTIONS_DE_TESTS_PAYANTS, GESTES_MCP, geste_de_l_action

    assert set(GESTES_MCP) == {"publier", "tests_payants", "appels_reels"}
    assert all(permission in PERMISSIONS for permissions in GESTES_MCP.values() for permission in permissions)
    for action in REGISTRE.values():
        geste = geste_de_l_action(action.nom, action.famille)
        if geste is not None:  # la permission de chaque action est l'une de celles du geste : allumer l'interrupteur exige de les avoir toutes
            assert familles_actions.permission_de(action.nom, action.famille or "irreversible") in GESTES_MCP[geste], action.nom
    assert ACTIONS_DE_TESTS_PAYANTS <= set(REGISTRE)
    publies = {a.nom for a in REGISTRE.values() if a.famille == "publication" and a.mcp}
    assert publies and all(geste_de_l_action(n, "publication") == "publier" for n in publies)
    assert geste_de_l_action("agent_archiver", "irreversible") is None  # supprimer reste fermé à la porte MCP

"""[.mark] builder-agent-vocal, lot 1 : un moteur, deux portes (écran et Claude Code par le serveur MCP).

Chaque action du builder est exposée au serveur MCP avec le même schéma, et les deux portes appellent la MÊME
fonction. Les outils que le serveur MCP expose déjà (lire, créer, enregistrer en brouillon...) sont appelés par le
moteur comme fonctions : la fonction appelée est celle du serveur.
"""

from __future__ import annotations

import dataclasses
from unittest.mock import AsyncMock

import pytest
from fastmcp import Client

from api.mcp_server.server import mcp
from api.services.builder.actions import registre
from api.services.builder.actions.registre import Contexte
from api.services.builder.identite import UTILISATEUR_DIRECT
from api.tests.mark.builder_commun import AGENT, utilisateur

# Des arguments valides pour chaque action exposée au MCP (le test échoue si une action n'a pas sa ligne).
ARGUMENTS = {
    "bibliotheque_lister": {},
    "bibliotheque_lire": {"famille": "moules-etape", "slug": "a"},
    "bibliotheque_appliquer": {"famille": "moules-etape", "slug": "a", "workflow_id": AGENT},
    "bibliotheque_ecrire_candidat": {"famille": "moules-etape", "slug": "a", "titre": "A", "contenu": {}},
    "bibliotheque_proposer": {"type": "rejet", "famille": "moules-etape", "slug": "a", "justification": "x", "version": 1},
    "fiche_lire": {"workflow_id": AGENT},
    "fiche_ecrire": {"workflow_id": AGENT, "champs": {"a": {"valeur": 1, "source": "s"}}},
    "conception_lire": {"workflow_id": AGENT},
    "conception_ecrire": {"workflow_id": AGENT, "objectif": "o", "reussite": "r"},
    "contexte_lire": {"workflow_id": AGENT},
    "contexte_ecrire": {"workflow_id": AGENT, "notes": "n"},
    "phrases_catalogue": {},
    "phrases_regler": {"workflow_id": AGENT, "depuis": "a"},
    "reglages_lire": {"workflow_id": AGENT},
    "reglages_regler": {"workflow_id": AGENT, "valeurs": {"relecture_des_numeros": True}},
    "lexique_remplir_depuis_fiche": {"workflow_id": AGENT},
    "modeles_reglages_lister": {},
    "modeles_reglages_appliquer": {"workflow_id": AGENT, "modele_id": "m", "sections": ["s"]},
    "brouillon_operation": {"workflow_id": AGENT, "operations": [{"op": "supprimer_noeud", "id": "1"}]},
    "brouillon_voir": {"workflow_id": AGENT},
    "brouillon_enregistrer": {"workflow_id": AGENT},
    "brouillon_jeter": {"workflow_id": AGENT},
    "fiche_tirer_des_documents": {"workflow_id": AGENT},
    "prompt_controler": {"workflow_id": AGENT},
    "outil_essayer": {"workflow_id": AGENT, "outil": "noter"},
    "tests_creer": {"workflow_id": AGENT, "nom": "t", "scenario": "s"},
    "tests_rejouer": {"workflow_id": AGENT},
    # Lot 3 (dossiers, fiche classée, base de connaissances) et B48 (objets de l'agent).
    "depot_ajouter_site": {"workflow_id": AGENT, "adresse": "https://exemple.test"},
    "fiche_creer_les_objets": {"workflow_id": AGENT},
    "base_lister": {"workflow_id": AGENT},
    "base_proposer": {
        "workflow_id": AGENT,
        "titre": "t",
        "contenu": "c",
        "sources": [{"document": "d.md", "extrait": "un passage assez long"}],
    },
    "base_rattacher": {"workflow_id": AGENT, "proposition": "p", "noeud": "1"},
    "objets_agent_lister": {},
    "objets_agent_ecrire": {"depuis": "a"},
}


def actions_mcp() -> list[str]:
    return [nom for nom, action in registre.REGISTRE.items() if action.mcp]


def test_chaque_action_exposee_au_mcp_a_ses_arguments_d_essai():
    assert sorted(ARGUMENTS) == sorted(actions_mcp())


async def test_chaque_action_du_builder_est_un_outil_mcp_au_meme_schema():
    async with Client(mcp) as client:
        outils = {o.name: o for o in await client.list_tools()}
    for nom in actions_mcp():
        assert nom in outils, f"{nom} manque au serveur MCP"
        # FastMCP déroule les ``$defs`` du schéma : on compare les paramètres et ceux qui sont obligatoires.
        schema, attendu = outils[nom].input_schema, registre.REGISTRE[nom].schema()
        assert set(schema["properties"]) == set(attendu["properties"]), nom
        assert schema.get("required", []) == attendu.get("required", []), nom
        assert outils[nom].description == registre.REGISTRE[nom].description


@pytest.mark.parametrize("nom", sorted(ARGUMENTS))
async def test_les_deux_portes_appellent_la_meme_fonction(nom, monde, monkeypatch):
    appels = []

    async def espion(contexte, parametres):
        appels.append((contexte.porte, contexte.user.id, parametres))
        return {"ok": True, "vu": nom}

    monkeypatch.setitem(registre.REGISTRE, nom, dataclasses.replace(registre.REGISTRE[nom], fonction=espion))
    user = utilisateur(1)
    monkeypatch.setattr("api.mcp_server.tools.builder.authenticate_mcp_request", AsyncMock(return_value=user))

    par_l_ecran = await registre.executer(nom, ARGUMENTS[nom], Contexte(user=user, workflow_id=AGENT))
    async with Client(mcp) as client:
        par_le_mcp = (await client.call_tool(nom, ARGUMENTS[nom])).structured_content
    assert par_l_ecran == par_le_mcp == {"ok": True, "vu": nom}
    assert [a[0] for a in appels] == ["ecran", "mcp"]
    assert appels[0][1] == appels[1][1] == 1 and appels[0][2] == appels[1][2]  # même utilisateur, mêmes paramètres validés


async def test_les_deux_portes_refusent_pareil_un_argument_invalide(monde, monkeypatch):
    monkeypatch.setattr("api.mcp_server.tools.builder.authenticate_mcp_request", AsyncMock(return_value=utilisateur(1)))
    ecran = await registre.executer("bibliotheque_lire", {"famille": "moules-etape"}, Contexte(user=utilisateur(1)))
    async with Client(mcp) as client:
        par_le_mcp = (await client.call_tool("bibliotheque_lire", {"famille": "moules-etape"}, raise_on_error=False)).structured_content
    assert ecran["ok"] is False and ecran == par_le_mcp  # même validation, même refus


# --- les outils que le serveur MCP expose déjà, appelés comme fonctions -------------------------------------------------

EXISTANTS = {
    "list_workflows": ("workflows", {}),
    "get_workflow": ("workflows", {"workflow_id": AGENT}),
    "get_workflow_code": ("get_workflow_code", {"workflow_id": AGENT}),
    "list_node_types": ("node_types", {}),
    "get_node_type": ("node_types", {"name": "startCall"}),
    "list_tools": ("catalog", {}),
    "list_documents": ("catalog", {}),
    "list_credentials": ("catalog", {}),
    "list_recordings": ("catalog", {}),
    "get_voice_prompting_guide": ("voice_prompting_guide", {"stage": "plan"}),
}


def test_les_outils_deja_exposes_sont_dans_le_registre_et_pas_inscrits_deux_fois():
    existants = {n for n, a in registre.REGISTRE.items() if not a.mcp}
    assert existants == set(EXISTANTS) | {"create_tool", "save_workflow", "create_workflow"}


@pytest.mark.parametrize("nom", sorted(EXISTANTS))
async def test_le_moteur_appelle_la_fonction_du_serveur_mcp_au_nom_de_l_utilisateur(nom, monde, monkeypatch):
    import importlib

    module_nom, arguments = EXISTANTS[nom]
    module = importlib.import_module(f"api.mcp_server.tools.{module_nom}")
    vus = []

    async def espion(**kwargs):
        vus.append((UTILISATEUR_DIRECT.get(), kwargs))
        return {"vu": nom}

    # La fonction exposée par le serveur est celle du module (pas une copie).
    outil = await mcp.get_tool(nom)
    assert outil.fn is getattr(module, nom)
    monkeypatch.setattr(module, nom, espion)

    user = utilisateur(1)
    resultat = await registre.executer(nom, arguments, Contexte(user=user, workflow_id=AGENT))
    assert resultat == {"vu": nom}
    assert vus[0][0] is user and UTILISATEUR_DIRECT.get() is None  # posé pour l'appel seulement, puis retiré
    attendu = dict(arguments)
    if nom in ("get_workflow", "get_workflow_code"):
        attendu["workflow_id"] = AGENT
    if nom in ("list_workflows", "list_tools"):
        attendu["status"] = "active"  # la valeur par défaut du modèle de paramètres, comme côté serveur
    assert {k: v for k, v in vus[0][1].items() if v is not None} == attendu


async def test_save_workflow_et_create_tool_passent_par_la_fonction_du_serveur_et_la_conception_est_exigee(monde, monkeypatch):
    import importlib

    from api.services.builder import conception

    sauvegarde = importlib.import_module("api.mcp_server.tools.save_workflow")
    espion = AsyncMock(return_value={"saved": True})
    monkeypatch.setattr(sauvegarde, "save_workflow", espion)
    ctx = Contexte(user=utilisateur(1), workflow_id=AGENT)
    refus = await registre.executer("save_workflow", {"code": "..."}, ctx)
    assert refus["ok"] is False and refus["code"] == "conception" and espion.await_count == 0
    await conception.ecrire(7, AGENT, conception.Conception(objectif="o", reussite="r"))
    await conception.decider(7, AGENT, True, "evan")
    assert (await registre.executer("save_workflow", {"code": "..."}, ctx)) == {"saved": True}
    espion.assert_awaited_once_with(workflow_id=AGENT, code="...")


async def test_create_workflow_n_est_permis_que_dans_une_conversation_sans_agent(monde, monkeypatch):
    import importlib

    creation = importlib.import_module("api.mcp_server.tools.create_workflow")
    espion = AsyncMock(return_value={"created": True})
    monkeypatch.setattr(creation, "create_workflow", espion)
    avec_agent = await registre.executer("create_workflow", {"code": "x"}, Contexte(user=utilisateur(1), workflow_id=AGENT))
    assert avec_agent["ok"] is False and espion.await_count == 0
    assert (await registre.executer("create_workflow", {"code": "x"}, Contexte(user=utilisateur(1)))) == {"created": True}


async def test_la_vraie_fonction_du_serveur_authentifie_l_utilisateur_pose_par_le_moteur(monde):
    """Sans moquer la fonction ni l'authentification : le moteur lit les agents de SON organisation, par la fonction du serveur."""
    monde.ajouter_agent(organization_id=8, identifiant=77)  # un agent d'une autre organisation n'apparaît pas
    resultat = await registre.executer("list_workflows", {}, Contexte(user=utilisateur(1)))
    assert [a["id"] for a in resultat["resultat"]] == [AGENT]


async def test_sans_utilisateur_pose_la_fonction_du_serveur_exige_toujours_la_cle_d_api():
    from fastapi import HTTPException

    from api.mcp_server.auth import authenticate_mcp_request

    assert UTILISATEUR_DIRECT.get() is None
    with pytest.raises(HTTPException) as erreur:
        await authenticate_mcp_request()
    assert erreur.value.status_code == 401
    jeton = UTILISATEUR_DIRECT.set(utilisateur(5))
    try:
        assert (await authenticate_mcp_request()).id == 5
    finally:
        UTILISATEUR_DIRECT.reset(jeton)

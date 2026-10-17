"""[.mark] Chantier agents-specialises, lot 10 : les sous-dossiers et le groupe d'agents.

Plan `Labo-agent-vocal/plans/agents-specialises/` (A9, A10). Les routes sont jouées par le VRAI
routeur sur la base de test (l'utilisateur est celui de l'organisation d'essai, comme
l'écran) ; chaque test lit ensuite ce que la base dit, pas la réponse seule (R1).

| Test | Ce qu'il prouve |
|---|---|
| sous-dossiers | créer avec parent, lister avec ``parent_id``, déplacer, refuser un cycle |
| organisation | un parent d'une autre organisation n'existe pas ; un dossier d'une autre organisation non plus |
| suppression | un sous-dossier qui disparaît remonte ses agents et ses sous-dossiers ; un dossier de premier niveau fait comme avant |
| création | un principal + son sous-dossier ; un spécialisé : graphe, clés copiées, lien, outil de passation |
| recopie | l'enregistrement du principal recopie les clés communes, idempotent, propres intacts |
| cerveau | détaché : jamais écrasé ; décoché : rattaché à nouveau à l'enregistrement suivant |
| retrait | un spécialisé retiré redevient un agent seul, sans outil de passation chez le principal |
| suppression d'agent | archiver un spécialisé retire l'outil qui le vise ; archiver un principal : garder ou archiver |
| publication | tout le groupe, spécialisés d'abord ; s'arrête au premier refus et le dit |
| duplication | dupliquer un principal duplique son groupe, outils repointés ; un agent seul : inchangé |
| clés | chaque clé du schéma et de l'inventaire de l'écran est commune ou propre |
"""

from __future__ import annotations

import copy
import re
from pathlib import Path

import pytest
from sqlalchemy import select

from api.db.models import FolderModel, ToolModel
from api.enums import ToolCategory
from api.schemas.workflow_configurations import WorkflowConfigurationDefaults
from api.services.groupe import groupe as service
from api.services.groupe.passations import (
    CLE_AGENT_PRINCIPAL,
    CLE_AGENTS_SPECIALISES,
    MARQUEUR_RETOUR,
)
from api.services.groupe.reglages import (
    CLE_CERVEAU_PROPRE,
    CLES_COMMUNES,
    CLES_PROPRES,
    cles_sans_classement,
    recopier,
)
from api.services.workflow.dto import ReactFlowDTO
from api.services.workflow.workflow_graph import WorkflowGraph
from api.tests.mark.test_apres_appel import _organisation, base_v4, smtp  # noqa: F401  (fixtures)

# ---------------------------------------------------------------------------
# Gabarits
# ---------------------------------------------------------------------------

COMMUNES = {
    "user_speech_timeout": 1.4,
    "tts_cache_enabled": True,
    "fiche_au_fil_de_leau": True,
    "model_overrides": {
        "llm": {"provider": "mistral", "model": "principal-llm"},
        "tts": {"provider": "mistral", "voice": "voix-du-groupe"},
    },
    "reflexion_de_relance": True,
}


async def _oublier(async_session):
    """Un appel de l'API ouvre sa propre session ; dans le test une seule sert à tout : on
    l'oublie entre deux appels pour lire ce que la base dit (et non sa mémoire)."""
    await async_session.flush()
    async_session.expunge_all()


async def _agent(db_session, org, nom, reglages=None, definition=None):
    agent = await db_session.create_workflow(
        name=nom,
        workflow_definition=definition or service.graphe_minimal_du_principal(),
        user_id=org.utilisateur.id,
        organization_id=org.organisation.id,
    )
    if reglages:
        await db_session.update_workflow(
            workflow_id=agent.id,
            name=None,
            workflow_definition=None,
            template_context_variables=None,
            workflow_configurations=reglages,
            organization_id=org.organisation.id,
        )
    return agent


async def _reglages(db_session, org, agent_id):
    agent = await service.lire_agent(agent_id, org.organisation.id)
    return agent.reglages


async def _outils_de_passation(db_session, org, agent_id):
    """Les cibles des outils de passation posés sur le graphe de travail de l'agent."""
    agent = await service.lire_agent(agent_id, org.organisation.id)
    uuids = [
        u
        for n in agent.definition.get("nodes", [])
        for u in (n.get("data") or {}).get("tool_uuids") or []
    ]
    outils = await db_session.get_tools_by_uuids(uuids, org.organisation.id)
    return sorted(
        o.definition["config"]["workflow_id"]
        for o in outils
        if o.category == ToolCategory.TRANSFER_AGENT.value
    )


@pytest.fixture
async def org(async_session, db_session):
    return await _organisation(async_session, db_session)


@pytest.fixture
async def autre_org(async_session, db_session):
    return await _organisation(async_session, db_session)


async def _creer_groupe(client, db_session, org, nom="Groupe", specialises=("Premier",)):
    reponse = await client.post("/api/v1/workflow/groupe", json={"name": nom})
    assert reponse.status_code == 200, reponse.text
    principal_id = reponse.json()["workflow_id"]
    ids = []
    for s in specialises:
        r = await client.post(
            f"/api/v1/workflow/{principal_id}/groupe/specialise", json={"name": s}
        )
        assert r.status_code == 200, r.text
        ids.append(r.json()["workflow_id"])
    return principal_id, reponse.json()["folder_id"], ids


# ---------------------------------------------------------------------------
# 1. Sous-dossiers
# ---------------------------------------------------------------------------


async def test_sous_dossiers_creation_liste_deplacement_cycle(
    org, db_session, test_client_factory
):
    async with test_client_factory(org.utilisateur) as client:
        racine = (await client.post("/api/v1/folder/", json={"name": "Racine"})).json()
        assert racine["parent_id"] is None
        fils = (
            await client.post(
                "/api/v1/folder/", json={"name": "Fils", "parent_id": racine["id"]}
            )
        ).json()
        assert fils["parent_id"] == racine["id"]

        liste = (await client.get("/api/v1/folder/")).json()
        assert {f["name"]: f["parent_id"] for f in liste} == {
            "Racine": None,
            "Fils": racine["id"],
        }

        # Un dossier de premier niveau créé sans parent : comme avant.
        seul = (await client.post("/api/v1/folder/", json={"name": "Seul"})).json()
        assert seul["parent_id"] is None

        # Déplacer le fils sous « Seul », puis le remettre au premier niveau.
        deplace = await client.put(
            f"/api/v1/folder/{fils['id']}/parent", json={"parent_id": seul["id"]}
        )
        assert deplace.json()["parent_id"] == seul["id"]
        remis = await client.put(
            f"/api/v1/folder/{fils['id']}/parent", json={"parent_id": None}
        )
        assert remis.json()["parent_id"] is None

        # Un cycle : la racine dans son propre fils, ou dans elle-même.
        await client.put(
            f"/api/v1/folder/{fils['id']}/parent", json={"parent_id": racine["id"]}
        )
        cycle = await client.put(
            f"/api/v1/folder/{racine['id']}/parent", json={"parent_id": fils["id"]}
        )
        assert cycle.status_code == 409
        soi = await client.put(
            f"/api/v1/folder/{racine['id']}/parent", json={"parent_id": racine["id"]}
        )
        assert soi.status_code == 409
    base = await db_session.get_folder(racine["id"], organization_id=org.organisation.id)
    assert base.parent_id is None, "le refus n'a rien écrit"


async def test_un_dossier_ou_un_parent_d_une_autre_organisation_n_existe_pas(
    org, autre_org, db_session, test_client_factory
):
    async with test_client_factory(autre_org.utilisateur) as client:
        etranger = (await client.post("/api/v1/folder/", json={"name": "Etranger"})).json()
    async with test_client_factory(org.utilisateur) as client:
        # Créer sous un parent d'une autre organisation : 404.
        r = await client.post(
            "/api/v1/folder/", json={"name": "Intrus", "parent_id": etranger["id"]}
        )
        assert r.status_code == 404
        mien = (await client.post("/api/v1/folder/", json={"name": "Mien"})).json()
        # Déplacer le mien sous un dossier étranger, ou déplacer un dossier étranger : 404.
        assert (
            await client.put(
                f"/api/v1/folder/{mien['id']}/parent", json={"parent_id": etranger["id"]}
            )
        ).status_code == 404
        assert (
            await client.put(
                f"/api/v1/folder/{etranger['id']}/parent", json={"parent_id": None}
            )
        ).status_code == 404
        # La liste ne montre que mes dossiers.
        assert [f["name"] for f in (await client.get("/api/v1/folder/")).json()] == ["Mien"]


async def test_supprimer_un_sous_dossier_remonte_ses_agents_et_ses_sous_dossiers(
    org, db_session, async_session, test_client_factory
):
    orgid = org.organisation.id
    async with test_client_factory(org.utilisateur) as client:
        parent = (await client.post("/api/v1/folder/", json={"name": "Parent"})).json()
        milieu = (
            await client.post(
                "/api/v1/folder/", json={"name": "Milieu", "parent_id": parent["id"]}
            )
        ).json()
        petit = (
            await client.post(
                "/api/v1/folder/", json={"name": "Petit", "parent_id": milieu["id"]}
            )
        ).json()
        agent = await _agent(db_session, org, "Agent du milieu")
        await db_session.move_workflow_to_folder(
            workflow_id=agent.id, folder_id=milieu["id"], organization_id=orgid
        )
        assert (await client.delete(f"/api/v1/folder/{milieu['id']}")).status_code == 200
    await _oublier(async_session)
    assert (await db_session.get_folder(milieu["id"], organization_id=orgid)) is None
    recu = await db_session.get_workflow(agent.id, organization_id=orgid)
    assert recu.folder_id == parent["id"], "l'agent est remonté dans le parent"
    remonte = await db_session.get_folder(petit["id"], organization_id=orgid)
    assert remonte.parent_id == parent["id"], "le sous-dossier est remonté dans le parent"


async def test_supprimer_un_dossier_de_premier_niveau_fait_comme_avant(
    org, db_session, async_session, test_client_factory
):
    orgid = org.organisation.id
    async with test_client_factory(org.utilisateur) as client:
        racine = (await client.post("/api/v1/folder/", json={"name": "Racine"})).json()
        fils = (
            await client.post(
                "/api/v1/folder/", json={"name": "Fils", "parent_id": racine["id"]}
            )
        ).json()
        agent = await _agent(db_session, org, "Agent")
        await db_session.move_workflow_to_folder(
            workflow_id=agent.id, folder_id=racine["id"], organization_id=orgid
        )
        assert (await client.delete(f"/api/v1/folder/{racine['id']}")).status_code == 200
    await _oublier(async_session)
    recu = await db_session.get_workflow(agent.id, organization_id=orgid)
    assert recu.folder_id is None, "Uncategorized, comme avant"
    assert (await db_session.get_folder(fils["id"], organization_id=orgid)).parent_id is None


# ---------------------------------------------------------------------------
# 2. Créer un groupe et un spécialisé
# ---------------------------------------------------------------------------


async def test_creer_un_groupe_puis_un_specialise(
    org, db_session, async_session, test_client_factory
):
    orgid = org.organisation.id
    async with test_client_factory(org.utilisateur) as client:
        principal_id, dossier_id, [specialise_id] = await _creer_groupe(
            client, db_session, org, specialises=("Spécialisé un",)
        )
    await _oublier(async_session)

    principal = await service.lire_agent(principal_id, orgid)
    specialise = await service.lire_agent(specialise_id, orgid)

    # Le lien, des deux côtés ; le sous-dossier est celui du groupe pour les deux.
    assert principal.reglages[CLE_AGENTS_SPECIALISES] == [specialise_id]
    assert specialise.reglages[CLE_AGENT_PRINCIPAL] == principal_id
    assert principal.folder_id == specialise.folder_id == dossier_id

    # Le graphe minimal : trois étapes, la dernière marquée, rien d'autre.
    noeuds = specialise.definition["nodes"]
    assert [n["data"]["name"] for n in noeuds] == [
        "Qualification",
        "Coordonnées",
        "Retour au principal",
    ]
    assert noeuds[-1]["data"][MARQUEUR_RETOUR] is True
    assert not any(n["type"] == "endCall" for n in noeuds), "sans nœud de fin"
    assert not any(n["type"] == "globalNode" for n in noeuds), "sans prompt global"
    assert not any((n.get("data") or {}).get("tool_uuids") for n in noeuds), "sans outil"
    # Le graphe de départ est un graphe valide (celui que la publication exige).
    WorkflowGraph(ReactFlowDTO.model_validate(specialise.definition))
    WorkflowGraph(ReactFlowDTO.model_validate(principal.definition))

    # L'outil de passation vers lui, posé sur l'étape de qualification du principal.
    assert await _outils_de_passation(db_session, org, principal_id) == [specialise_id]
    qualification = next(n for n in principal.definition["nodes"] if n["type"] == "startCall")
    assert len(qualification["data"]["tool_uuids"]) == 1
    outil = (await db_session.get_tools_by_uuids(qualification["data"]["tool_uuids"], orgid))[0]
    assert outil.definition["config"]["message"] == "", "aucune annonce : une seule voix"
    assert outil.definition["config"]["play_greeting"] is False


async def test_le_specialise_copie_les_cles_communes_du_principal(
    org, db_session, async_session, test_client_factory
):
    orgid = org.organisation.id
    async with test_client_factory(org.utilisateur) as client:
        principal_id, _, _ = await _creer_groupe(client, db_session, org, specialises=())
        await db_session.update_workflow(
            workflow_id=principal_id,
            name=None,
            workflow_definition=None,
            template_context_variables=None,
            workflow_configurations={
                **COMMUNES,
                CLE_AGENTS_SPECIALISES: [],
                "etablissement_id": "fiche-du-principal",
            },
            organization_id=orgid,
        )
        r = await client.post(
            f"/api/v1/workflow/{principal_id}/groupe/specialise", json={"name": "Copie"}
        )
        specialise_id = r.json()["workflow_id"]
    await _oublier(async_session)
    reglages = await _reglages(db_session, org, specialise_id)
    for cle, valeur in COMMUNES.items():
        assert reglages[cle] == valeur, cle
    assert "etablissement_id" not in reglages, "un spécialisé lit la fiche de l'appel"
    assert reglages[CLE_AGENT_PRINCIPAL] == principal_id


async def test_un_specialise_ne_peut_pas_etre_principal_et_l_agent_doit_exister(
    org, autre_org, db_session, test_client_factory
):
    async with test_client_factory(org.utilisateur) as client:
        principal_id, _, [specialise_id] = await _creer_groupe(client, db_session, org)
        refus = await client.post(
            f"/api/v1/workflow/{specialise_id}/groupe/specialise", json={"name": "Trop"}
        )
        assert refus.status_code == 409
    async with test_client_factory(autre_org.utilisateur) as client:
        # Le principal d'une autre organisation n'existe pas pour cet appelant.
        r = await client.post(
            f"/api/v1/workflow/{principal_id}/groupe/specialise", json={"name": "Intrus"}
        )
        assert r.status_code == 404


async def test_un_agent_seul_n_est_pas_un_groupe(org, db_session, test_client_factory):
    agent = await _agent(db_session, org, "Seul")
    async with test_client_factory(org.utilisateur) as client:
        r = await client.get(f"/api/v1/workflow/{agent.id}/groupe")
        assert r.status_code == 200
        assert r.json() == {"principal": None, "agent_principal_id": None, "specialises": []}
    assert CLE_AGENTS_SPECIALISES not in await _reglages(db_session, org, agent.id)


async def test_lire_le_groupe_depuis_le_principal_et_depuis_un_specialise(
    org, db_session, async_session, test_client_factory
):
    async with test_client_factory(org.utilisateur) as client:
        principal_id, _, ids = await _creer_groupe(
            client, db_session, org, specialises=("Un", "Deux")
        )
        await _oublier(async_session)
        depuis_principal = (await client.get(f"/api/v1/workflow/{principal_id}/groupe")).json()
        depuis_specialise = (await client.get(f"/api/v1/workflow/{ids[1]}/groupe")).json()
    assert depuis_principal["principal"]["id"] == principal_id
    assert [m["id"] for m in depuis_principal["specialises"]] == ids
    assert depuis_specialise == depuis_principal


async def test_les_liens_des_groupes_pour_la_liste_d_agents(
    org, autre_org, db_session, async_session, test_client_factory
):
    seul = await _agent(db_session, org, "Seul")
    async with test_client_factory(autre_org.utilisateur) as client:
        await _creer_groupe(client, db_session, autre_org, nom="Ailleurs")
    async with test_client_factory(org.utilisateur) as client:
        principal_id, _, ids = await _creer_groupe(
            client, db_session, org, specialises=("Un", "Deux")
        )
        await _oublier(async_session)
        liens = {a["id"]: a for a in (await client.get("/api/v1/workflow/groupes")).json()["agents"]}
    assert seul.id not in liens, "un agent seul n'est pas dans un groupe"
    assert liens[principal_id]["role"] == "principal"
    assert liens[principal_id]["agents_specialises"] == ids
    for sid in ids:
        assert liens[sid]["role"] == "specialise"
        assert liens[sid]["agent_principal_id"] == principal_id
    assert set(liens) == {principal_id, *ids}, "seulement mon organisation"


async def test_un_specialise_que_son_principal_ne_liste_plus_n_est_plus_specialise():
    """Revue du 16/10 : archivé puis restauré, il garde son lien écrit, mais son principal ne le
    liste plus ; la liste d'agents ne le montre plus comme spécialisé."""
    from unittest.mock import AsyncMock, patch

    from api.services.groupe import groupe as module_groupe

    reglages = [
        (1, {CLE_AGENTS_SPECIALISES: [2]}),
        (2, {CLE_AGENT_PRINCIPAL: 1}),
        (3, {CLE_AGENT_PRINCIPAL: 1}),
    ]
    with patch.object(
        module_groupe.db_client, "list_agent_configurations", AsyncMock(return_value=reglages)
    ):
        liens = {a["id"]: a for a in await module_groupe.liens_des_groupes(7)}
    assert liens[2]["role"] == "specialise"
    assert 3 not in liens


# ---------------------------------------------------------------------------
# 3. Recopie et cerveau détachable
# ---------------------------------------------------------------------------


async def test_l_enregistrement_du_principal_recopie_les_cles_communes_par_la_vraie_route(
    org, db_session, async_session, test_client_factory
):
    orgid = org.organisation.id
    async with test_client_factory(org.utilisateur) as client:
        principal_id, _, [s1, s2] = await _creer_groupe(
            client, db_session, org, specialises=("Un", "Deux")
        )
        await _oublier(async_session)
        principal = await service.lire_agent(principal_id, orgid)
        # Le geste de l'écran : PUT du principal avec un réglage commun changé.
        r = await client.put(
            f"/api/v1/workflow/{principal_id}",
            json={
                "workflow_definition": principal.definition,
                "workflow_configurations": {
                    **principal.reglages,
                    "user_speech_timeout": 1.9,
                    "tts_cache_enabled": True,
                },
            },
        )
        assert r.status_code == 200, r.text
    await _oublier(async_session)
    for sid in (s1, s2):
        reglages = await _reglages(db_session, org, sid)
        assert reglages["user_speech_timeout"] == 1.9, "recopié dans chaque spécialisé"
        assert reglages["tts_cache_enabled"] is True
        assert reglages[CLE_AGENT_PRINCIPAL] == principal_id, "le lien n'est jamais recopié"
        assert CLE_AGENTS_SPECIALISES not in reglages


async def test_la_recopie_est_idempotente_et_n_ecrit_pas_deux_fois(
    org, db_session, async_session, test_client_factory
):
    orgid = org.organisation.id
    async with test_client_factory(org.utilisateur) as client:
        principal_id, _, [sid] = await _creer_groupe(client, db_session, org)
    await db_session.update_workflow(
        workflow_id=principal_id,
        name=None,
        workflow_definition=None,
        template_context_variables=None,
        workflow_configurations={
            **(await _reglages(db_session, org, principal_id)),
            "user_speech_timeout": 2.2,
        },
        organization_id=orgid,
    )
    assert await service.recopier_dans_les_specialises(principal_id, orgid) == [sid]
    avant = await _reglages(db_session, org, sid)
    assert await service.recopier_dans_les_specialises(principal_id, orgid) == [], (
        "déjà à jour : rien n'est réécrit"
    )
    assert await _reglages(db_session, org, sid) == avant


def test_recopier_garde_les_cles_propres_et_retire_ce_que_le_principal_n_a_plus():
    principal = {"user_speech_timeout": 1.5, CLE_AGENTS_SPECIALISES: [7]}
    specialise = {
        CLE_AGENT_PRINCIPAL: 3,
        "etablissement_id": "x",
        "horaires_ouverture": "lundi : fermé",
        "mute_always": True,  # commun, absent chez le principal : le défaut revient
        "cle_inconnue_du_futur": 42,  # ni commune ni propre : jamais perdue
    }
    entree_principal, entree_specialise = copy.deepcopy(principal), copy.deepcopy(specialise)
    neuf = recopier(principal, specialise)
    assert neuf["user_speech_timeout"] == 1.5
    assert "mute_always" not in neuf
    assert neuf[CLE_AGENT_PRINCIPAL] == 3
    assert neuf["etablissement_id"] == "x"
    assert neuf["horaires_ouverture"] == "lundi : fermé"
    assert neuf["cle_inconnue_du_futur"] == 42
    assert CLE_AGENTS_SPECIALISES not in neuf
    assert recopier(principal, neuf) == neuf, "idempotente"
    assert principal == entree_principal and specialise == entree_specialise, "pure"


def test_le_cerveau_detache_n_est_jamais_ecrase_et_la_voix_reste_commune():
    principal = {
        "model_overrides": {
            "llm": {"model": "du-principal"},
            "tts": {"voice": "voix-commune"},
        },
        "reflexion_de_relance": False,
        "user_speech_timeout": 1.1,
    }
    specialise = {
        CLE_AGENT_PRINCIPAL: 3,
        CLE_CERVEAU_PROPRE: True,
        "model_overrides": {
            "llm": {"model": "propre-au-specialise"},
            "tts": {"voice": "ancienne-voix"},
        },
        "reflexion_de_relance": True,
    }
    neuf = recopier(principal, specialise)
    assert neuf["model_overrides"]["llm"] == {"model": "propre-au-specialise"}
    assert neuf["model_overrides"]["tts"] == {"voice": "voix-commune"}, "une seule voix"
    assert neuf["reflexion_de_relance"] is True, "suit le cerveau détaché"
    assert neuf["user_speech_timeout"] == 1.1

    # Case décochée : le spécialisé reprend le cerveau du principal à l'enregistrement suivant.
    decoche = {**neuf, CLE_CERVEAU_PROPRE: False}
    rattache = recopier(principal, decoche)
    assert rattache["model_overrides"]["llm"] == {"model": "du-principal"}
    assert rattache["reflexion_de_relance"] is False


def test_le_cerveau_detache_ne_cree_pas_de_branche_que_le_principal_n_a_pas():
    principal = {"model_configuration_v2_override": {"mode": "dograh", "dograh": {"voice": "v"}}}
    specialise = {
        CLE_CERVEAU_PROPRE: True,
        "model_configuration_v2_override": {
            "mode": "byok",
            "byok": {"mode": "pipeline", "pipeline": {"llm": {"model": "propre"}}},
        },
    }
    neuf = recopier(principal, specialise)
    # Le principal est en mode géré : pas de branche de modèle de langage à regreffer.
    assert neuf["model_configuration_v2_override"] == principal["model_configuration_v2_override"]


def test_le_cerveau_detache_survit_a_un_principal_sans_configuration_de_modeles():
    """Revue du 16/10 : le principal hérite des modèles de l'organisation (aucune surcharge) ;
    le cerveau propre du spécialisé n'est jamais effacé à l'enregistrement du principal."""
    principal = {"user_speech_timeout": 1.1}
    specialise = {
        CLE_AGENT_PRINCIPAL: 3,
        CLE_CERVEAU_PROPRE: True,
        "model_overrides": {"llm": {"model": "propre-au-specialise"}},
    }
    neuf = recopier(principal, specialise)
    assert neuf["model_overrides"]["llm"] == {"model": "propre-au-specialise"}
    assert recopier(principal, neuf) == neuf, "idempotente"
    # Case décochée : il reprend l'héritage du principal.
    assert "model_overrides" not in recopier(principal, {**neuf, CLE_CERVEAU_PROPRE: False})


async def test_le_cerveau_detache_survit_a_l_enregistrement_du_principal(
    org, db_session, async_session, test_client_factory
):
    orgid = org.organisation.id
    async with test_client_factory(org.utilisateur) as client:
        principal_id, _, [sid] = await _creer_groupe(client, db_session, org)
    await db_session.update_workflow(
        workflow_id=principal_id,
        name=None,
        workflow_definition=None,
        template_context_variables=None,
        workflow_configurations={
            **(await _reglages(db_session, org, principal_id)),
            "model_overrides": {"llm": {"model": "du-principal"}, "tts": {"voice": "v1"}},
        },
        organization_id=orgid,
    )
    specialise = await service.lire_agent(sid, orgid)
    await db_session.update_workflow(
        workflow_id=sid,
        name=None,
        workflow_definition=None,
        template_context_variables=None,
        workflow_configurations={
            **specialise.reglages,
            CLE_CERVEAU_PROPRE: True,
            "model_overrides": {"llm": {"model": "propre"}, "tts": {"voice": "ancienne"}},
        },
        organization_id=orgid,
    )
    await service.recopier_dans_les_specialises(principal_id, orgid)
    detache = (await _reglages(db_session, org, sid))["model_overrides"]
    assert detache == {"llm": {"model": "propre"}, "tts": {"voice": "v1"}}

    # Décocher la case, puis un enregistrement du principal : le cerveau du principal revient.
    reglages = await _reglages(db_session, org, sid)
    await db_session.update_workflow(
        workflow_id=sid,
        name=None,
        workflow_definition=None,
        template_context_variables=None,
        workflow_configurations={**reglages, CLE_CERVEAU_PROPRE: False},
        organization_id=orgid,
    )
    await service.recopier_dans_les_specialises(principal_id, orgid)
    rattache = (await _reglages(db_session, org, sid))["model_overrides"]
    assert rattache["llm"] == {"model": "du-principal"}


# ---------------------------------------------------------------------------
# 4. Retirer, supprimer
# ---------------------------------------------------------------------------


async def test_un_specialise_retire_redevient_un_agent_seul(
    org, db_session, async_session, test_client_factory
):
    orgid = org.organisation.id
    async with test_client_factory(org.utilisateur) as client:
        principal_id, dossier_id, [s1, s2] = await _creer_groupe(
            client, db_session, org, specialises=("Un", "Deux")
        )
        await _oublier(async_session)
        r = await client.post(f"/api/v1/workflow/{s1}/groupe/retirer")
        assert r.status_code == 200
        # Un agent seul ne se retire de rien.
        assert (await client.post(f"/api/v1/workflow/{principal_id}/groupe/retirer")).status_code == 409
    await _oublier(async_session)
    seul = await _reglages(db_session, org, s1)
    assert CLE_AGENT_PRINCIPAL not in seul
    assert (await service.lire_agent(s1, orgid)).definition["nodes"], "son graphe est gardé"
    principal = await _reglages(db_session, org, principal_id)
    assert principal[CLE_AGENTS_SPECIALISES] == [s2]
    assert await _outils_de_passation(db_session, org, principal_id) == [s2]


async def test_archiver_un_specialise_retire_l_outil_de_passation_qui_le_vise(
    org, db_session, async_session, test_client_factory
):
    orgid = org.organisation.id
    async with test_client_factory(org.utilisateur) as client:
        principal_id, _, [s1, s2] = await _creer_groupe(
            client, db_session, org, specialises=("Un", "Deux")
        )
        await _oublier(async_session)
        # La vraie route d'archivage de l'écran (celle de la liste d'agents).
        r = await client.put(f"/api/v1/workflow/{s1}/status", json={"status": "archived"})
        assert r.status_code == 200, r.text
    await _oublier(async_session)
    assert (await db_session.get_workflow(s1, organization_id=orgid)).status == "archived"
    assert await _outils_de_passation(db_session, org, principal_id) == [s2]
    assert (await _reglages(db_session, org, principal_id))[CLE_AGENTS_SPECIALISES] == [s2]


@pytest.mark.parametrize("choix", ["garder", "archiver"])
async def test_archiver_un_principal_garde_ou_archive_ses_specialises(
    choix, org, db_session, async_session, test_client_factory
):
    orgid = org.organisation.id
    async with test_client_factory(org.utilisateur) as client:
        principal_id, _, [s1, s2] = await _creer_groupe(
            client, db_session, org, specialises=("Un", "Deux")
        )
        await _oublier(async_session)
        r = await client.post(
            f"/api/v1/workflow/{principal_id}/groupe/archiver", json={"specialises": choix}
        )
        assert r.status_code == 200, r.text
        assert r.json()["specialises"] == [s1, s2]
        mauvais = await client.post(
            f"/api/v1/workflow/{principal_id}/groupe/archiver", json={"specialises": "autre"}
        )
        assert mauvais.status_code == 422
    await _oublier(async_session)
    assert (await db_session.get_workflow(principal_id, organization_id=orgid)).status == "archived"
    for sid in (s1, s2):
        statut = (await db_session.get_workflow(sid, organization_id=orgid)).status
        if choix == "archiver":
            assert statut == "archived"
        else:
            assert statut == "active"
            assert CLE_AGENT_PRINCIPAL not in await _reglages(db_session, org, sid), (
                "gardé comme agent seul"
            )


async def test_archiver_un_agent_seul_est_inchange(org, db_session, async_session, test_client_factory):
    agent = await _agent(db_session, org, "Seul", reglages={"user_speech_timeout": 1.3})
    await _oublier(async_session)
    async with test_client_factory(org.utilisateur) as client:
        r = await client.put(f"/api/v1/workflow/{agent.id}/status", json={"status": "archived"})
        assert r.status_code == 200, r.text
    await _oublier(async_session)
    assert (await db_session.get_workflow(agent.id, organization_id=org.organisation.id)).status == "archived"
    assert (await _reglages(db_session, org, agent.id)) == {"user_speech_timeout": 1.3}


# ---------------------------------------------------------------------------
# 5. Publier le groupe
# ---------------------------------------------------------------------------


async def test_publier_le_groupe_publie_les_specialises_puis_le_principal(
    org, db_session, async_session, test_client_factory
):
    orgid = org.organisation.id
    async with test_client_factory(org.utilisateur) as client:
        principal_id, _, [s1, s2] = await _creer_groupe(
            client, db_session, org, specialises=("Un", "Deux")
        )
        await _oublier(async_session)
        r = await client.post(f"/api/v1/workflow/{principal_id}/groupe/publier")
        assert r.status_code == 200, r.text
        corps = r.json()
        assert corps["refus"] is None
        assert [p["id"] for p in corps["publies"]] == [s1, s2, principal_id], (
            "spécialisés d'abord, principal en dernier"
        )
        # Rejouer : plus de brouillon, tout est déjà à jour.
        encore = (await client.post(f"/api/v1/workflow/{principal_id}/groupe/publier")).json()
        assert encore["publies"] == [] and sorted(encore["deja_a_jour"]) == sorted([s1, s2, principal_id])
    await _oublier(async_session)
    for agent_id in (s1, s2, principal_id):
        assert await db_session.get_draft_version(agent_id) is None
        publie = (await db_session.get_workflow(agent_id, organization_id=orgid)).released_definition
        assert publie.workflow_json["nodes"]


async def test_publier_le_groupe_s_arrete_au_premier_refus_et_le_dit(
    org, db_session, async_session, test_client_factory
):
    orgid = org.organisation.id
    async with test_client_factory(org.utilisateur) as client:
        principal_id, _, [s1, s2] = await _creer_groupe(
            client, db_session, org, specialises=("Un", "Deux")
        )
        await _oublier(async_session)
        # Le premier spécialisé reçoit un brouillon invalide (une étape sans prompt).
        cassé = await service.lire_agent(s1, orgid)
        cassé.definition["nodes"][1]["data"]["prompt"] = ""
        await db_session.save_workflow_draft(s1, workflow_definition=cassé.definition)
        await _oublier(async_session)
        corps = (await client.post(f"/api/v1/workflow/{principal_id}/groupe/publier")).json()
    assert corps["refus"]["id"] == s1
    assert corps["refus"]["name"] == "Un"
    assert corps["refus"]["detail"], "la raison est dite"
    assert corps["publies"] == [], "on s'arrête : ni le suivant ni le principal"
    await _oublier(async_session)
    assert await db_session.get_draft_version(principal_id) is not None, "le principal reste en brouillon"


# ---------------------------------------------------------------------------
# 6. Dupliquer
# ---------------------------------------------------------------------------


async def test_dupliquer_un_principal_duplique_son_groupe(
    org, db_session, async_session, test_client_factory
):
    orgid = org.organisation.id
    async with test_client_factory(org.utilisateur) as client:
        principal_id, dossier_id, [s1, s2] = await _creer_groupe(
            client, db_session, org, nom="Origine", specialises=("Un", "Deux")
        )
        await _oublier(async_session)
        r = await client.post(f"/api/v1/workflow/{principal_id}/duplicate")
        assert r.status_code == 200, r.text
        copie_id = r.json()["id"]
    await _oublier(async_session)

    copie = await service.lire_agent(copie_id, orgid)
    nouveaux = copie.reglages[CLE_AGENTS_SPECIALISES]
    assert len(nouveaux) == 2 and not set(nouveaux) & {s1, s2}, "de nouveaux agents"
    for nid in nouveaux:
        reglages = await _reglages(db_session, org, nid)
        assert reglages[CLE_AGENT_PRINCIPAL] == copie_id, "lien des deux côtés"
    # Les outils de passation de la copie mènent aux copies, jamais aux originaux.
    assert await _outils_de_passation(db_session, org, copie_id) == sorted(nouveaux)
    # Les originaux gardent les leurs.
    assert await _outils_de_passation(db_session, org, principal_id) == sorted([s1, s2])
    assert (await _reglages(db_session, org, principal_id))[CLE_AGENTS_SPECIALISES] == [s1, s2]
    # Un nouveau sous-dossier pour la copie, distinct de celui de l'original.
    dossier_copie = (await db_session.get_workflow(copie_id, organization_id=orgid)).folder_id
    assert dossier_copie is not None and dossier_copie != dossier_id
    for nid in nouveaux:
        assert (await db_session.get_workflow(nid, organization_id=orgid)).folder_id == dossier_copie
    # Aucun outil original n'a été modifié.
    outils = (await async_session.execute(select(ToolModel).where(ToolModel.organization_id == orgid))).scalars().all()
    cibles = sorted(o.definition["config"]["workflow_id"] for o in outils if o.category == "transfer_agent")
    assert cibles == sorted([s1, s2, *nouveaux])


async def test_dupliquer_un_agent_seul_ou_un_specialise_ne_cree_pas_de_groupe(
    org, db_session, async_session, test_client_factory
):
    orgid = org.organisation.id
    seul = await _agent(db_session, org, "Seul", reglages={"user_speech_timeout": 1.3})
    await _oublier(async_session)
    async with test_client_factory(org.utilisateur) as client:
        copie = (await client.post(f"/api/v1/workflow/{seul.id}/duplicate")).json()["id"]
        principal_id, _, [sid] = await _creer_groupe(client, db_session, org)
        await _oublier(async_session)
        copie_specialise = (await client.post(f"/api/v1/workflow/{sid}/duplicate")).json()["id"]
    await _oublier(async_session)
    assert await _reglages(db_session, org, copie) == {"user_speech_timeout": 1.3}
    reglages = await _reglages(db_session, org, copie_specialise)
    assert CLE_AGENT_PRINCIPAL not in reglages, "la copie d'un spécialisé est un agent seul"
    assert (await _reglages(db_session, org, principal_id))[CLE_AGENTS_SPECIALISES] == [sid]
    assert (await db_session.get_workflow(copie, organization_id=orgid)).folder_id is None


# ---------------------------------------------------------------------------
# 7. Les listes de clés
# ---------------------------------------------------------------------------

RACINE = Path(__file__).resolve().parents[3]


def test_chaque_cle_du_schema_et_de_l_inventaire_est_commune_ou_propre():
    du_schema = set(WorkflowConfigurationDefaults.model_fields)
    inventaire = (RACINE / "ui/src/components/mark/reglages-agent/inventaire-agent.ts").read_text(
        encoding="utf-8"
    )
    de_l_inventaire = set(re.findall(r"^    ([a-z_0-9]+): \{", inventaire, re.M))
    sans = cles_sans_classement(du_schema | de_l_inventaire)
    assert sans == [], f"clés ni communes ni propres (reglages.py) : {sans}"
    assert not set(CLES_COMMUNES) & set(CLES_PROPRES), "une clé ne peut pas être des deux"

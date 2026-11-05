"""[.mark] Builder partie 3, SA-L3d, sous-lot 1 (décision 21) : les versions des outils.

| Test | Ce qu'il prouve |
|---|---|
| version un | un outil naît avec sa version 1 ; la migration l'a posée pour les outils existants |
| nouvelle version | enregistrer un outil modifié crée la version suivante ; un contenu identique, une note de tenue ou une icône n'en crée pas |
| épinglage | un agent est épinglé à sa création et à sa publication ; publier ne le fait JAMAIS suivre la dernière version ; un outil ajouté prend la courante à la publication |
| vrai chemin d'appel (R1) | un appel d'un agent publié joue l'ANCIENNE version d'un outil après l'enregistrement d'une nouvelle (graphe monté comme en production, gestionnaire d'outils du moteur, base réelle) |
| garde des sites | chaque endroit qui monte le graphe d'un appel passe les épingles à ``WorkflowGraph`` (un oubli rendrait l'agent « suiveur » en silence) |
| cache de l'appel | deux agents d'un même appel qui épinglent deux versions du même outil ne se servent pas le contenu de l'autre |
| passer à la v2 | écrit dans le BROUILLON (jamais la version en ligne), la publication la fige ; un outil inconnu, d'une autre organisation ou un agent qui ne l'utilise pas : refus |
| branches | « passer à la v2 » sur une branche ne touche ni la principale ni les autres branches ; la fusion ramène la bonne version et la montre dans l'aperçu |
| prêt à publier | la ligne conseillée « outils à jour » n'existe que s'il reste un outil en retard, et nomme l'outil |
| usage | qui utilise quelle version, et combien d'agents en ligne restent en retard ; cloisonné par organisation |
"""

from __future__ import annotations

import ast
import pathlib
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from api.db import branche_ouverte
from api.db.outils_versions_client import ErreurOutilVersion
from api.enums import ToolCategory
from api.services.groupe.prechauffage import Precharge
from api.services.workflow.dto import ReactFlowDTO
from api.services.workflow.pipecat_engine_custom_tools import CustomToolManager
from api.services.workflow.run_creation import definition_to_run
from api.services.workflow.workflow_graph import WorkflowGraph
from api.tests.mark.test_apres_appel import _organisation, base_v4, smtp  # noqa: F401  (fixtures)
from api.tests.mark.test_sous_dossiers_et_groupe import _oublier, autre_org, org  # noqa: F401


@pytest.fixture(autouse=True)
def _branche_fermee():
    branche_ouverte.ouvrir(None, None)
    yield
    branche_ouverte.ouvrir(None, None)


def _definition_d_outil(url: str = "https://agenda.example.test/v1") -> dict:
    return {"schema_version": 1, "type": "http_api", "config": {"method": "POST", "url": url, "parameters": []}}


def _graphe(*uuids: str) -> dict:
    return {
        "nodes": [
            {
                "id": "1",
                "type": "startCall",
                "position": {"x": 0, "y": 0},
                "data": {"name": "Accueil", "prompt": "Bonjour", "tool_uuids": list(uuids)},
            },
            {"id": "2", "type": "endCall", "position": {"x": 0, "y": 100}, "data": {"name": "Fin", "prompt": "Au revoir"}},
        ],
        "edges": [{"id": "1-2", "source": "1", "target": "2", "data": {"label": "Fini", "condition": "La personne a fini"}}],
    }


async def _outil(db, org, nom="reserver", url="https://agenda.example.test/v1", description="Réserve un créneau."):
    return await db.create_tool(
        organization_id=org.organisation.id,
        user_id=org.utilisateur.id,
        name=nom,
        definition=_definition_d_outil(url),
        category=ToolCategory.HTTP_API.value,
        description=description,
    )


async def _agent(db, org, *uuids, nom="Agent"):
    return await db.create_workflow(
        name=nom, workflow_definition=_graphe(*uuids), user_id=org.utilisateur.id, organization_id=org.organisation.id
    )


async def _publier(db, agent, graphe=None):
    await db.save_workflow_draft(agent.id, workflow_definition=graphe)
    return await db.publish_workflow_draft(agent.id)


# --- les versions ----------------------------------------------------------------------------------------------------------------


async def test_un_outil_nait_avec_sa_version_un(org, db_session):
    outil = await _outil(db_session, org)
    lu, versions = await db_session.versions_d_un_outil(org.organisation.id, outil.tool_uuid)
    assert lu.version_courante == 1
    assert [(v.version, v.name, v.definition["config"]["url"]) for v in versions] == [(1, "reserver", "https://agenda.example.test/v1")]


async def test_enregistrer_un_outil_modifie_cree_la_version_suivante_et_le_reste_non(org, db_session):
    outil = await _outil(db_session, org)
    organisation = org.organisation.id
    # même contenu, icône, statut : aucune version
    await db_session.update_tool(outil.tool_uuid, organisation, definition=_definition_d_outil(), icon="phone", user_id=org.utilisateur.id)
    assert (await db_session.versions_d_un_outil(organisation, outil.tool_uuid))[0].version_courante == 1
    # une note de tenue (dernier essai) : aucune version
    await db_session.update_tool(
        outil.tool_uuid, organisation, definition={**_definition_d_outil(), "note": "essai"}, sans_version=True
    )
    assert (await db_session.versions_d_un_outil(organisation, outil.tool_uuid))[0].version_courante == 1
    # un vrai changement : la v2, puis la v3 (description)
    await db_session.update_tool(outil.tool_uuid, organisation, definition=_definition_d_outil("https://agenda.example.test/v2"), user_id=org.utilisateur.id)
    await db_session.update_tool(outil.tool_uuid, organisation, description="Réserve un créneau, version 3.", user_id=org.utilisateur.id)
    lu, versions = await db_session.versions_d_un_outil(organisation, outil.tool_uuid)
    assert lu.version_courante == 3
    assert [v.version for v in versions] == [3, 2, 1]
    assert versions[2].definition["config"]["url"] == "https://agenda.example.test/v1"  # la v1 n'a pas bougé
    assert versions[1].definition["config"]["url"] == "https://agenda.example.test/v2"
    assert versions[0].description == "Réserve un créneau, version 3."


# --- l'épinglage -----------------------------------------------------------------------------------------------------------------


async def test_un_agent_est_epingle_a_sa_creation_et_publier_ne_le_fait_jamais_suivre(org, db_session):
    outil = await _outil(db_session, org)
    agent = await _agent(db_session, org, outil.tool_uuid)
    en_ligne = await db_session.get_workflow_definition(agent.id, agent.released_definition_id, org.organisation.id)
    assert en_ligne.outils_epingles == {outil.tool_uuid: 1}
    await db_session.update_tool(outil.tool_uuid, org.organisation.id, definition=_definition_d_outil("https://agenda.example.test/v2"), user_id=org.utilisateur.id)
    # on publie un autre changement de l'agent : l'outil reste sur la v1
    publiee = await _publier(db_session, agent, _graphe(outil.tool_uuid))
    assert publiee.outils_epingles == {outil.tool_uuid: 1}


async def test_un_outil_ajoute_prend_la_version_courante_a_la_publication_et_un_outil_retire_perd_son_epingle(org, db_session):
    a = await _outil(db_session, org, "a")
    b = await _outil(db_session, org, "b")
    await db_session.update_tool(b.tool_uuid, org.organisation.id, description="b v2", user_id=org.utilisateur.id)
    agent = await _agent(db_session, org, a.tool_uuid)
    publiee = await _publier(db_session, agent, _graphe(a.tool_uuid, b.tool_uuid))
    assert publiee.outils_epingles == {a.tool_uuid: 1, b.tool_uuid: 2}
    publiee = await _publier(db_session, agent, _graphe(b.tool_uuid))
    assert publiee.outils_epingles == {b.tool_uuid: 2}


async def test_un_identifiant_d_une_autre_organisation_n_est_jamais_epingle(org, autre_org, db_session):
    etranger = await _outil(db_session, autre_org, "etranger")
    agent = await _agent(db_session, org, etranger.tool_uuid)
    en_ligne = await db_session.get_workflow_definition(agent.id, agent.released_definition_id, org.organisation.id)
    assert not en_ligne.outils_epingles


# --- le vrai chemin d'appel (R1) -------------------------------------------------------------------------------------------------


async def _graphe_d_un_appel(db, org, agent_id):
    """Le graphe monté comme les sites de production : la définition que l'appel joue, ses épingles passées à ``WorkflowGraph``."""
    agent = await db.get_workflow(agent_id, organization_id=org.organisation.id)
    definition = await definition_to_run(db, agent)
    return WorkflowGraph(
        ReactFlowDTO.model_validate(definition.workflow_json),
        skip_instance_constraints_for={"trigger"},
        outils_epingles=definition.outils_epingles,
    )


def _gestionnaire(org, graphe):
    agent = SimpleNamespace(workflow=graphe, mcp_sessions={})
    moteur = SimpleNamespace(_get_organization_id=AsyncMock(return_value=org.organisation.id), active_agent=agent)
    return CustomToolManager(moteur, agent)


async def test_un_appel_d_un_agent_publie_joue_l_ancienne_version_apres_l_enregistrement_d_une_nouvelle(org, db_session):
    outil = await _outil(db_session, org, description="Version un.")
    agent = await _agent(db_session, org, outil.tool_uuid)
    await db_session.update_tool(
        outil.tool_uuid,
        org.organisation.id,
        description="Version deux.",
        definition=_definition_d_outil("https://agenda.example.test/v2"),
        user_id=org.utilisateur.id,
    )
    graphe = await _graphe_d_un_appel(db_session, org, agent.id)
    gestionnaire = _gestionnaire(org, graphe)
    lus = await gestionnaire._lire_outils([outil.tool_uuid], org.organisation.id)
    assert [(o.description, o.definition["config"]["url"]) for o in lus] == [("Version un.", "https://agenda.example.test/v1")]
    schemas = await gestionnaire.get_tool_schemas([outil.tool_uuid])
    assert [s.description for s in schemas] == ["Version un."]
    # le contenu courant, lui, est bien la v2 : seule l'épingle retient l'appel en arrière
    courant = await db_session.get_tools_by_uuids([outil.tool_uuid], org.organisation.id)
    assert courant[0].description == "Version deux."
    # la copie lue pour l'appel n'est jamais réécrite en base
    relu, _ = await db_session.versions_d_un_outil(org.organisation.id, outil.tool_uuid)
    assert relu.description == "Version deux." and relu.version_courante == 2


async def test_apres_avoir_passe_a_la_v2_et_publie_l_appel_joue_la_v2(org, db_session, async_session):
    outil = await _outil(db_session, org, description="Version un.")
    agent = await _agent(db_session, org, outil.tool_uuid)
    await db_session.update_tool(outil.tool_uuid, org.organisation.id, description="Version deux.", user_id=org.utilisateur.id)
    await db_session.passer_un_outil_a_la_version(org.organisation.id, agent.id, outil.tool_uuid, 2)
    # avant la publication, l'agent en ligne joue encore la v1
    graphe = await _graphe_d_un_appel(db_session, org, agent.id)
    assert [o.description for o in await _gestionnaire(org, graphe)._lire_outils([outil.tool_uuid], org.organisation.id)] == ["Version un."]
    await db_session.publish_workflow_draft(agent.id)
    await _oublier(async_session)  # la session de test garde les objets : on relit la base comme un appel neuf
    graphe = await _graphe_d_un_appel(db_session, org, agent.id)
    assert [o.description for o in await _gestionnaire(org, graphe)._lire_outils([outil.tool_uuid], org.organisation.id)] == ["Version deux."]


async def test_le_moteur_lit_les_outils_de_l_agent_actif_avec_ses_epingles(org, db_session):
    from api.services.workflow.pipecat_engine import PipecatEngine

    outil = await _outil(db_session, org, description="Version un.")
    agent = await _agent(db_session, org, outil.tool_uuid)
    await db_session.update_tool(outil.tool_uuid, org.organisation.id, description="Version deux.", user_id=org.utilisateur.id)
    graphe = await _graphe_d_un_appel(db_session, org, agent.id)
    faux_moteur = SimpleNamespace(active_agent=SimpleNamespace(workflow=graphe))
    lus = await PipecatEngine.lire_outils(faux_moteur, [outil.tool_uuid], org.organisation.id)
    assert [o.description for o in lus] == ["Version un."]


def test_chaque_site_qui_monte_le_graphe_d_un_appel_passe_les_epingles():
    """Un site qui l'oublierait rendrait l'agent « suiveur » en silence : le garde lit le code (R1)."""
    racine = pathlib.Path(__file__).resolve().parents[2]
    sites = {
        "services/pipecat/run_pipeline.py": None,
        "services/pipecat/agent_runtime_factory.py": None,
        "services/workflow/text_agent_factory.py": None,
        "services/workflow/text_chat_runner.py": {"extract_text_chat_final_variables"},  # l'extraction de fin de chat n'appelle aucun outil
    }
    manque = []
    for chemin, exemptees in sites.items():
        arbre = ast.parse((racine / chemin).read_text(encoding="utf-8"))
        for fonction in [n for n in ast.walk(arbre) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]:
            for appel in [n for n in ast.walk(fonction) if isinstance(n, ast.Call)]:
                nom = getattr(appel.func, "id", None) or getattr(appel.func, "attr", None)
                if nom != "WorkflowGraph":
                    continue
                if any(k.arg == "outils_epingles" for k in appel.keywords):
                    continue
                if exemptees and any(e in fonction.name for e in exemptees):
                    continue
                manque.append(f"{chemin}:{appel.lineno} ({fonction.name})")
    assert manque == []


# --- le cache de l'appel ---------------------------------------------------------------------------------------------------------


async def test_le_cache_de_l_appel_est_cle_par_version(org, db_session):
    outil = await _outil(db_session, org, description="Version un.")
    await db_session.update_tool(outil.tool_uuid, org.organisation.id, description="Version deux.", user_id=org.utilisateur.id)
    cache = Precharge(organization_id=org.organisation.id)
    lire = db_session.get_tools_by_uuids
    ancien = await cache.outils([outil.tool_uuid], org.organisation.id, lire, {outil.tool_uuid: 1})
    courant = await cache.outils([outil.tool_uuid], org.organisation.id, lire, None)
    encore_ancien = await cache.outils([outil.tool_uuid], org.organisation.id, lire, {outil.tool_uuid: 1})
    assert [o.description for o in ancien] == ["Version un."]
    assert [o.description for o in courant] == ["Version deux."]
    assert [o.description for o in encore_ancien] == ["Version un."]


# --- passer à une version --------------------------------------------------------------------------------------------------------


async def test_passer_a_la_v2_ecrit_dans_le_brouillon_et_jamais_dans_la_version_en_ligne(org, db_session):
    outil = await _outil(db_session, org)
    agent = await _agent(db_session, org, outil.tool_uuid)
    await db_session.update_tool(outil.tool_uuid, org.organisation.id, description="v2", user_id=org.utilisateur.id)
    assert await db_session.get_draft_version(agent.id) is None
    fait = await db_session.passer_un_outil_a_la_version(org.organisation.id, agent.id, outil.tool_uuid, 2)
    assert fait["version"] == 2 and fait["courante"] == 2
    brouillon = await db_session.get_draft_version(agent.id)
    assert brouillon.outils_epingles == {outil.tool_uuid: 2}
    en_ligne = await db_session.get_workflow_definition(agent.id, agent.released_definition_id, org.organisation.id)
    assert en_ligne.outils_epingles == {outil.tool_uuid: 1}
    # on peut revenir en arrière dans le brouillon
    await db_session.passer_un_outil_a_la_version(org.organisation.id, agent.id, outil.tool_uuid, 1)
    assert (await db_session.get_draft_version(agent.id)).outils_epingles == {outil.tool_uuid: 1}


async def test_passer_a_une_version_refuse_l_inconnu_l_etranger_et_l_outil_non_utilise(org, autre_org, db_session):
    outil = await _outil(db_session, org)
    libre = await _outil(db_session, org, "libre")
    etranger = await _outil(db_session, autre_org, "etranger")
    agent = await _agent(db_session, org, outil.tool_uuid)
    organisation = org.organisation.id
    with pytest.raises(ErreurOutilVersion):  # une version qui n'existe pas
        await db_session.passer_un_outil_a_la_version(organisation, agent.id, outil.tool_uuid, 9)
    with pytest.raises(ErreurOutilVersion):  # un outil d'une autre organisation
        await db_session.passer_un_outil_a_la_version(organisation, agent.id, etranger.tool_uuid, 1)
    with pytest.raises(ErreurOutilVersion) as e:  # un outil que l'agent ne cite pas
        await db_session.passer_un_outil_a_la_version(organisation, agent.id, libre.tool_uuid, 1)
    assert e.value.code == "pas_utilise"
    with pytest.raises(ErreurOutilVersion):  # un agent d'une autre organisation : rien n'est écrit
        await db_session.passer_un_outil_a_la_version(autre_org.organisation.id, agent.id, outil.tool_uuid, 1)


async def test_les_routes_et_le_cloisonnement(org, autre_org, db_session, async_session, test_client_factory):
    outil = await _outil(db_session, org)
    agent = await _agent(db_session, org, outil.tool_uuid)
    await db_session.update_tool(outil.tool_uuid, org.organisation.id, description="v2", user_id=org.utilisateur.id)
    await _oublier(async_session)
    async with test_client_factory(org.utilisateur) as client:
        versions = await client.get(f"/api/v1/builder/outils/{outil.tool_uuid}/versions")
        assert versions.status_code == 200, versions.text
        corps = versions.json()
        assert corps["courante"] == 2 and [v["version"] for v in corps["versions"]] == [2, 1]
        assert corps["agents_en_retard"] == 1  # l'agent en ligne reste sur la v1
        assert [(u["agent"], u["branche"], u["version_outil"], u["en_ligne"]) for u in corps["usage"]] == [("Agent", "Principale", 1, True)]
        de_l_agent = (await client.get(f"/api/v1/builder/outils/agent/{agent.id}")).json()
        assert de_l_agent["source"] == "en_ligne"
        assert [(o["epinglee"], o["courante"]) for o in de_l_agent["outils"]] == [(1, 2)]
        ecrit = await client.put(f"/api/v1/builder/outils/agent/{agent.id}/version", json={"tool_uuid": outil.tool_uuid, "version": 2})
        assert ecrit.status_code == 200, ecrit.text
        de_l_agent = (await client.get(f"/api/v1/builder/outils/agent/{agent.id}")).json()
        assert de_l_agent["source"] == "brouillon" and de_l_agent["outils"][0]["epinglee"] == 2
        assert (await client.put(f"/api/v1/builder/outils/agent/{agent.id}/version", json={"tool_uuid": outil.tool_uuid, "version": 9})).status_code == 404
        assert (await client.put(f"/api/v1/builder/outils/agent/{agent.id}/version", json={"tool_uuid": outil.tool_uuid, "version": 0})).status_code == 422
    async with test_client_factory(autre_org.utilisateur) as client:
        assert (await client.get(f"/api/v1/builder/outils/{outil.tool_uuid}/versions")).status_code == 404
        assert (await client.get(f"/api/v1/builder/outils/agent/{agent.id}")).status_code == 404
        assert (await client.put(f"/api/v1/builder/outils/agent/{agent.id}/version", json={"tool_uuid": outil.tool_uuid, "version": 2})).status_code == 404
    assert (await db_session.get_draft_version(agent.id)).outils_epingles == {outil.tool_uuid: 2}


# --- les branches ----------------------------------------------------------------------------------------------------------------


async def test_passer_a_la_v2_sur_une_branche_ne_touche_ni_la_principale_ni_les_autres(org, db_session):
    outil = await _outil(db_session, org)
    agent = await _agent(db_session, org, outil.tool_uuid)
    await db_session.update_tool(outil.tool_uuid, org.organisation.id, description="v2", user_id=org.utilisateur.id)
    organisation, utilisateur = org.organisation.id, org.utilisateur.id
    branche, brouillon = await db_session.creer_une_branche(organisation, agent.id, "Essai", depuis_definition_id=None, user_id=utilisateur)
    autre, autre_brouillon = await db_session.creer_une_branche(organisation, agent.id, "Autre", depuis_definition_id=None, user_id=utilisateur)
    assert brouillon.outils_epingles == {outil.tool_uuid: 1}  # une branche part des épingles de sa version de départ
    branche_ouverte.ouvrir(branche.id, utilisateur)
    await db_session.passer_un_outil_a_la_version(organisation, agent.id, outil.tool_uuid, 2)
    branche_ouverte.ouvrir(None, None)
    assert (await db_session.get_draft_version(agent.id)) is None  # la principale n'a pas de brouillon
    en_ligne = await db_session.get_workflow_definition(agent.id, agent.released_definition_id, organisation)
    assert en_ligne.outils_epingles == {outil.tool_uuid: 1}
    branche_ouverte.ouvrir(autre.id, utilisateur)
    assert (await db_session.get_draft_version(agent.id)).outils_epingles == {outil.tool_uuid: 1}
    branche_ouverte.ouvrir(None, None)
    # la publication de la branche fige l'épingle choisie
    version = await db_session.publier_le_brouillon_de_branche(organisation, agent.id, branche.id, utilisateur)
    assert version.outils_epingles == {outil.tool_uuid: 2}


async def test_la_fusion_ramene_la_bonne_version_d_outil_et_la_montre_dans_l_apercu(org, db_session):
    from api.services.branches import fusion

    outil = await _outil(db_session, org, "reserver")
    agent = await _agent(db_session, org, outil.tool_uuid)
    await db_session.update_tool(outil.tool_uuid, org.organisation.id, description="v2", user_id=org.utilisateur.id)
    organisation, utilisateur = org.organisation.id, org.utilisateur.id
    branche, _ = await db_session.creer_une_branche(organisation, agent.id, "Essai", depuis_definition_id=None, user_id=utilisateur)
    branche_ouverte.ouvrir(branche.id, utilisateur)
    await db_session.passer_un_outil_a_la_version(organisation, agent.id, outil.tool_uuid, 2)
    branche_ouverte.ouvrir(None, None)
    await db_session.publier_le_brouillon_de_branche(organisation, agent.id, branche.id, utilisateur)
    agent = await db_session.get_workflow(agent.id, organization_id=organisation)
    apercu = await fusion.apercu_de_la_fusion(organisation, agent, branche.id)
    lignes = [c for c in apercu["champs"] if c["famille"] == "outils"]
    assert [(c["libelle"], c["avant"], c["source"], c["cible"], c["statut"]) for c in lignes] == [("reserver", "v1", "v2", "v1", "reprise")]
    ecrit = await fusion.fusionner(
        organisation,
        agent,
        branche.id,
        choix={},
        relue=False,
        version_branche=apercu["branche"]["id_version"],
        version_cible=apercu["cible"]["id_version"],
        user=org.utilisateur,
    )
    agent = await db_session.get_workflow(agent.id, organization_id=organisation)
    en_ligne = await db_session.get_workflow_definition(agent.id, agent.released_definition_id, organisation)
    assert en_ligne.version_number == ecrit["version"] and en_ligne.outils_epingles == {outil.tool_uuid: 2}


def test_la_fusion_a_trois_traite_la_version_d_un_outil_comme_un_champ():
    from api.services.branches import champs

    graphe = _graphe("u1")
    base = champs.Etat(graphe, {}, {}, {"u1": 1})
    source = champs.Etat(graphe, {}, {}, {"u1": 3})
    cible = champs.Etat(graphe, {}, {}, {"u1": 2})
    (ligne,) = [l for l in champs.comparer(base, source, cible) if l["famille"] == "outils"]
    assert ligne["statut"] == "conflit" and (ligne["avant"], ligne["source"], ligne["cible"]) == ("v1", "v3", "v2")
    with pytest.raises(champs.ChoixIncomplet):
        champs.resoudre(base, source, cible, {})
    assert champs.resoudre(base, source, cible, {"outil:u1": "source"}).outils == {"u1": 3}
    assert champs.resoudre(base, source, cible, {"outil:u1": "cible"}).outils == {"u1": 2}


# --- prêt à publier --------------------------------------------------------------------------------------------------------------


async def test_la_ligne_outils_a_jour_n_existe_que_s_il_reste_un_outil_en_retard(org, db_session):
    from api.services.preparation import lire

    outil = await _outil(db_session, org, "reserver")
    agent = await _agent(db_session, org, outil.tool_uuid)
    organisation = org.organisation.id
    assert "outils_a_jour" not in [e.id for e in await lire(organisation, agent.id)]
    await db_session.update_tool(outil.tool_uuid, organisation, description="v2", user_id=org.utilisateur.id)
    (ligne,) = [e for e in await lire(organisation, agent.id) if e.id == "outils_a_jour"]
    assert ligne.niveau == "conseille" and ligne.etat == "a_faire" and ligne.noms == ["reserver"] and ligne.noeud_id == "1"
    await db_session.passer_un_outil_a_la_version(organisation, agent.id, outil.tool_uuid, 2)
    assert "outils_a_jour" not in [e.id for e in await lire(organisation, agent.id)]


async def test_la_ligne_outils_a_jour_est_dans_la_liste_pret_a_publier_avec_son_onglet(org, db_session):
    from api.services.preparation import liste

    outil = await _outil(db_session, org, "reserver")
    agent = await _agent(db_session, org, outil.tool_uuid)
    await db_session.update_tool(outil.tool_uuid, org.organisation.id, description="v2", user_id=org.utilisateur.id)
    lignes = await liste.lire_la_liste(org.organisation.id, agent.id)
    (ligne,) = [l for l in lignes if l["id"] == "outils_a_jour"]
    assert ligne["niveau"] == "conseille" and ligne["onglet"] == "outils" and ligne["noeud_id"] == "1" and ligne["etat"] == "a_faire"


# --- l'usage ---------------------------------------------------------------------------------------------------------------------


async def test_l_usage_dit_qui_utilise_quelle_version_et_reste_cloisonne(org, autre_org, db_session):
    outil = await _outil(db_session, org)
    for nom in ("A", "B"):
        await _agent(db_session, org, outil.tool_uuid, nom=nom)
    await db_session.update_tool(outil.tool_uuid, org.organisation.id, description="v2", user_id=org.utilisateur.id)
    c = await _agent(db_session, org, outil.tool_uuid, nom="C")  # créé après : épinglé sur la v2
    usage = await db_session.usage_d_un_outil(org.organisation.id, outil.tool_uuid)
    assert [(u["agent"], u["version_outil"], u["en_ligne"], u["brouillon"]) for u in usage] == [
        ("A", 1, True, False),
        ("B", 1, True, False),
        ("C", 2, True, False),
    ]
    with pytest.raises(ErreurOutilVersion):
        await db_session.usage_d_un_outil(autre_org.organisation.id, outil.tool_uuid)
    assert c.id  # l'agent C existe


# --- la migration ----------------------------------------------------------------------------------------------------------------


def _charger_la_migration():
    import importlib.util

    chemin = pathlib.Path(__file__).resolve().parents[2] / "alembic" / "versions" / "d4b8f1a6c9e3_mark_versions_des_outils.py"
    spec = importlib.util.spec_from_file_location("migration_versions_des_outils", chemin)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


async def test_la_migration_pose_la_version_un_et_epingle_les_agents_existants_et_se_rejoue_sans_effet_double(org, db_session, async_session):
    from sqlalchemy import text

    migration = _charger_la_migration()
    outil = await _outil(db_session, org)
    agent = await _agent(db_session, org, outil.tool_uuid)
    # l'état d'avant la migration : aucune version d'outil, aucune épingle
    await async_session.execute(text("DELETE FROM tool_versions WHERE tool_id = :t"), {"t": outil.id})
    await async_session.execute(
        text("UPDATE workflow_definitions SET outils_epingles = NULL WHERE workflow_id = :w"), {"w": agent.id}
    )
    await async_session.flush()

    def jouer(connexion):
        migration.poser_les_versions_un(connexion)
        migration.epingler_les_versions_existantes(connexion)

    for _ in range(2):  # deux fois : rejouable, aucun effet double
        await async_session.run_sync(lambda sync: jouer(sync.connection()))
    compte = (await async_session.execute(text("SELECT count(*) FROM tool_versions WHERE tool_id = :t"), {"t": outil.id})).scalar()
    epingles = (
        await async_session.execute(text("SELECT outils_epingles FROM workflow_definitions WHERE workflow_id = :w"), {"w": agent.id})
    ).scalars().all()
    assert compte == 1
    assert epingles == [{outil.tool_uuid: 1}]
    # une épingle déjà posée n'est jamais retouchée
    await async_session.execute(
        text("UPDATE workflow_definitions SET outils_epingles = CAST(:v AS json) WHERE workflow_id = :w"),
        {"v": f'{{"{outil.tool_uuid}": 7}}', "w": agent.id},
    )
    await async_session.run_sync(lambda sync: jouer(sync.connection()))
    epingles = (
        await async_session.execute(text("SELECT outils_epingles FROM workflow_definitions WHERE workflow_id = :w"), {"w": agent.id})
    ).scalars().all()
    assert epingles == [{outil.tool_uuid: 7}]

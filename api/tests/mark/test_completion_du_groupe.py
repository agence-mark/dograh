"""[.mark] Lot 2 d'orchestrateur-trois-cerveaux (D5, D6) : les deux sorties et la complétion des groupes.

Plan `Labo-agent-vocal/plans/orchestrateur-trois-cerveaux/` (lot 2). Un collègue a deux sorties (clore
l'appel, rendre la main) ; un accueil a une étape de retour. Les groupes qui existent déjà (graphes du
16/10) sont complétés par le code, en brouillon, **sans rien retirer ni réécrire**, avec des prompts
« à rédiger avec Evan ».

La première moitié du fichier ne demande aucune base (la logique est pure, et la validité des graphes
se juge avec le vrai ``WorkflowGraph``). La seconde joue la vraie route ``/groupe/completer`` sur la base
de test (Postgres) : elle ne tourne pas sur un poste sans base, la CI la joue.

| Test | Ce qu'il prouve |
|---|---|
| gabarit | un nouveau collègue a le nœud de fin et deux portes depuis sa dernière étape ; graphe valide |
| collègue du 16/10 | le nœud de fin est ajouté et relié, rien n'est retiré, rejoué rien ne change |
| accueil du 16/10 | l'étape de retour est ajoutée, sans arête entrante, avec les outils de passation et ses sorties |
| rien à faire | déjà complet, sans retour, agent seul : le graphe est rendu tel quel |
| noms de portes | deux portes d'une même étape ne portent jamais le même nom |
| prompt à rédiger | l'étape de retour posée n'est pas choisie tant que son prompt est « à rédiger », même après que l'enregistrement y a ajouté ses blocs générés |
| bloc d'équipe | le collègue qui a les deux sorties les cite ; sans nœud de fin : le texte d'avant |
| la route | brouillon seulement, publié intact, rejouée sans effet, agent seul 200 sans rien |
"""

from __future__ import annotations

import copy

import pytest

from api.services.groupe import groupe as service
from api.services.groupe.completion import completer_un_accueil, completer_un_collegue
from api.services.groupe.passations import (
    A_REDIGER,
    CLE_AGENT_PRINCIPAL,
    CLE_AGENTS_SPECIALISES,
    MARQUEUR_ETAPE_DE_RETOUR,
    MARQUEUR_RETOUR,
    etape_de_retour_du_graphe,
)
from api.services.workflow import schema_du_parcours
from api.services.workflow.dto import ReactFlowDTO
from api.services.workflow.workflow_graph import WorkflowGraph

# Le graphe d'un collègue tel qu'il était le 16/10 : trois étapes, aucun nœud de fin.
COLLEGUE_DU_16_10 = {
    "nodes": [
        {
            "id": "1",
            "type": "startCall",
            "position": {"x": 175, "y": 60},
            "data": {
                "name": "Qualification",
                "prompt": "Qualifie.",
                "is_start": True,
                "allow_interrupt": False,
                "add_global_prompt": True,
            },
        },
        {
            "id": "2",
            "type": "agentNode",
            "position": {"x": 175, "y": 260},
            "data": {"name": "Coordonnées", "prompt": "Recueille.", "allow_interrupt": False},
        },
        {
            "id": "3",
            "type": "agentNode",
            "position": {"x": 175, "y": 460},
            "data": {
                "name": "Retour au principal",
                "prompt": "Retour.",
                "allow_interrupt": False,
                MARQUEUR_RETOUR: True,
            },
        },
    ],
    "edges": [
        {"id": "1-2", "source": "1", "target": "2", "data": {"label": "Coordonnées", "condition": "c"}},
        {"id": "2-3", "source": "2", "target": "3", "data": {"label": "Retour au principal", "condition": "c"}},
    ],
    "viewport": {"x": 0, "y": 0, "zoom": 0.75},
}

OUTIL = "tool-uuid-passation"


def un_accueil_du_16_10() -> dict:
    definition = service.graphe_minimal_du_principal()
    definition["nodes"][0]["data"]["tool_uuids"] = [OUTIL]
    return definition


def valide(definition: dict) -> WorkflowGraph:
    return WorkflowGraph(ReactFlowDTO.model_validate(definition))


def est_conserve(avant: dict, apres: dict) -> None:
    """Rien n'est retiré ni réécrit : chaque nœud et chaque arête d'avant est là, à l'identique."""
    for cle in ("nodes", "edges"):
        for element in avant.get(cle) or []:
            assert element in apres[cle], f"{cle} réécrit ou retiré : {element}"
    assert apres.get("viewport") == avant.get("viewport")


# --------------------------------------------------------------------------- #
# Le gabarit d'un nouveau collègue
# --------------------------------------------------------------------------- #


def test_un_nouveau_collegue_a_deux_sorties():
    definition = service.graphe_minimal_du_specialise()
    graphe = valide(definition)
    fin = next(n for n in graphe.nodes.values() if n.is_end)
    assert fin.name == "Fin" and fin.prompt == A_REDIGER
    deuxieme = graphe.nodes["2"]
    assert sorted(e.target for e in deuxieme.out_edges) == ["3", "4"]
    # Aucune phrase figée posée à la place d'Evan (elle serait DITE par le code).
    assert not getattr(fin.data, "fins", None)
    # Un collègue n'a pas besoin d'être complété.
    assert completer_un_collegue(definition)[1] == []


# --------------------------------------------------------------------------- #
# Un collègue du 16/10
# --------------------------------------------------------------------------- #


def test_un_collegue_du_16_10_recoit_son_noeud_de_fin():
    avant = copy.deepcopy(COLLEGUE_DU_16_10)
    apres, ajouts = completer_un_collegue(avant)
    assert avant == COLLEGUE_DU_16_10, "l'entrée n'est jamais modifiée"
    assert len(ajouts) == 1 and "Fin" in ajouts[0]
    est_conserve(COLLEGUE_DU_16_10, apres)
    fin = [n for n in apres["nodes"] if n["type"] == "endCall"]
    assert len(fin) == 1 and fin[0]["data"]["prompt"] == A_REDIGER and fin[0]["data"]["is_end"]
    # Relié depuis l'étape qui mène au retour, avec une condition « à rédiger ».
    porte = next(a for a in apres["edges"] if a["target"] == fin[0]["id"])
    assert porte["source"] == "2" and porte["data"]["condition"] == A_REDIGER
    valide(apres)
    # Rejoué : rien ne change.
    encore, ajouts = completer_un_collegue(apres)
    assert ajouts == [] and encore == apres


def test_rien_a_completer_rend_le_graphe_tel_quel():
    deja = service.graphe_minimal_du_specialise()
    sans_retour = copy.deepcopy(COLLEGUE_DU_16_10)
    del sans_retour["nodes"][2]["data"][MARQUEUR_RETOUR]
    for definition in (deja, sans_retour, {}, None):
        apres, ajouts = completer_un_collegue(definition)
        assert ajouts == [] and apres == (definition or {})


# --------------------------------------------------------------------------- #
# Un accueil du 16/10
# --------------------------------------------------------------------------- #


def test_un_accueil_du_16_10_recoit_son_etape_de_retour():
    avant = un_accueil_du_16_10()
    apres, ajouts = completer_un_accueil(avant, [OUTIL, OUTIL])
    assert len(ajouts) == 1
    est_conserve(un_accueil_du_16_10(), apres)
    retour = [n for n in apres["nodes"] if n["data"].get(MARQUEUR_ETAPE_DE_RETOUR)]
    assert len(retour) == 1
    assert retour[0]["type"] == "agentNode" and retour[0]["data"]["prompt"] == A_REDIGER
    assert retour[0]["data"]["tool_uuids"] == [OUTIL], "les outils de passation, sans doublon"
    # Aucune arête entrante (le code la choisit) ; une sortie vers la fin de l'accueil.
    assert not [a for a in apres["edges"] if a["target"] == retour[0]["id"]]
    sorties = [a for a in apres["edges"] if a["source"] == retour[0]["id"]]
    assert [a["target"] for a in sorties] == ["2"]
    graphe = valide(apres)
    # Tant que son prompt est « à rédiger », le moteur ne la choisit pas (retour comme avant).
    assert etape_de_retour_du_graphe(graphe) is None
    # Rejoué : rien ne change.
    encore, ajouts = completer_un_accueil(apres, [OUTIL])
    assert ajouts == [] and encore == apres


def test_une_etape_de_retour_posee_n_est_choisie_qu_une_fois_son_prompt_redige():
    apres, _ = completer_un_accueil(un_accueil_du_16_10(), [OUTIL])
    retour = next(n for n in apres["nodes"] if n["data"].get(MARQUEUR_ETAPE_DE_RETOUR))
    # L'enregistrement de l'écran ajoute ses blocs générés au prompt : ce n'est pas du texte rédigé.
    enrichie = schema_du_parcours.appliquer(apres, True)
    prompt = next(
        n for n in enrichie["nodes"] if n["data"].get(MARQUEUR_ETAPE_DE_RETOUR)
    )["data"]["prompt"]
    assert prompt != A_REDIGER and "Tu es ici" in prompt
    assert etape_de_retour_du_graphe(valide(enrichie)) is None
    # Evan rédige : elle devient celle du retour.
    retour["data"]["prompt"] = "Reprends la conversation."
    assert etape_de_retour_du_graphe(valide(apres)).name == "Reprise"


def test_deux_portes_d_une_meme_etape_ne_portent_jamais_le_meme_nom():
    definition = copy.deepcopy(COLLEGUE_DU_16_10)
    definition["edges"][1]["data"]["label"] = "Fin"  # la porte vers le retour s'appelle déjà « Fin »
    apres, _ = completer_un_collegue(definition)
    noms = [a["data"]["label"] for a in apres["edges"] if a["source"] == "2"]
    assert sorted(noms) == ["Fin", "Fin 2"]


def test_un_accueil_sans_etape_de_depart_ou_deja_complet_n_est_pas_touche():
    complet, _ = completer_un_accueil(un_accueil_du_16_10(), [OUTIL])
    assert completer_un_accueil(complet, [OUTIL])[1] == []
    sans_depart = {"nodes": [n for n in un_accueil_du_16_10()["nodes"] if n["type"] != "startCall"], "edges": []}
    assert completer_un_accueil(sans_depart, [OUTIL])[1] == []


# --------------------------------------------------------------------------- #
# Le bloc d'équipe cite les deux sorties
# --------------------------------------------------------------------------- #


def test_le_bloc_d_equipe_d_un_collegue_cite_les_deux_sorties():
    apres, _ = completer_un_collegue(COLLEGUE_DU_16_10)
    bloc = schema_du_parcours.parcours(apres, schema_du_parcours.TYPE_SPECIALISTE)
    assert (
        "Tu as deux sorties : pour clore l'appel, tu écris la sortie Fin ; "
        "pour rendre la main à l'accueil, tu écris la sortie Retour au principal."
    ) in bloc


def test_sans_noeud_de_fin_le_bloc_d_equipe_est_celui_d_avant():
    bloc = schema_du_parcours.parcours(COLLEGUE_DU_16_10, schema_du_parcours.TYPE_SPECIALISTE)
    assert "deux sorties" not in bloc
    assert "Pour rendre la main à l'accueil, tu écris la sortie Retour au principal" in bloc


# --------------------------------------------------------------------------- #
# La route (Postgres)
# --------------------------------------------------------------------------- #

from api.tests.mark.test_sous_dossiers_et_groupe import (  # noqa: E402
    _agent,
    _creer_groupe,
    _oublier,
    org,  # noqa: F401  (fixture)
)
from api.tests.mark.test_apres_appel import base_v4, smtp  # noqa: E402,F401  (fixtures)


async def _retirer_la_fin(db_session, orgid, agent_id):
    """Ramène un collègue à son graphe du 16/10 (sans nœud de fin)."""
    agent = await service.lire_agent(agent_id, orgid)
    definition = copy.deepcopy(COLLEGUE_DU_16_10)
    await db_session.save_workflow_draft(agent_id, workflow_definition=definition)
    return agent


async def test_la_route_complete_en_brouillon_et_rejouee_ne_change_rien(
    org, db_session, async_session, test_client_factory
):
    orgid = org.organisation.id
    async with test_client_factory(org.utilisateur) as client:
        principal_id, _, [s1] = await _creer_groupe(client, db_session, org, specialises=("Un",))
        await _retirer_la_fin(db_session, orgid, s1)
        # L'accueil n'a pas encore d'étape de retour (gabarit).
        await _oublier(async_session)
        publie_avant = (
            await db_session.get_workflow(s1, organization_id=orgid)
        ).released_definition.workflow_json

        reponse = await client.post(f"/api/v1/workflow/{principal_id}/groupe/completer")
        assert reponse.status_code == 200, reponse.text
        corps = reponse.json()
        assert corps[str(principal_id)] and corps[str(s1)], "l'accueil et le collègue sont complétés"
        await _oublier(async_session)

        accueil = await service.lire_agent(principal_id, orgid)
        retour = [n for n in accueil.definition["nodes"] if n["data"].get(MARQUEUR_ETAPE_DE_RETOUR)]
        assert len(retour) == 1 and retour[0]["data"]["prompt"] == A_REDIGER
        assert retour[0]["data"]["tool_uuids"], "l'étape de retour porte l'outil de passation"
        collegue = await service.lire_agent(s1, orgid)
        assert any(n["type"] == "endCall" for n in collegue.definition["nodes"])
        valide(collegue.definition)
        valide(accueil.definition)

        # Brouillon seulement : la version publiée du collègue n'a pas bougé.
        assert collegue.a_un_brouillon
        publie_apres = (
            await db_session.get_workflow(s1, organization_id=orgid)
        ).released_definition.workflow_json
        assert publie_apres == publie_avant

        # Rejouée : rien à ajouter.
        encore = await client.post(f"/api/v1/workflow/{principal_id}/groupe/completer")
        assert encore.status_code == 200
        assert all(v == [] for v in encore.json().values())


async def test_la_route_sur_un_agent_seul_ne_fait_rien(
    org, db_session, async_session, test_client_factory
):
    seul = await _agent(db_session, org, "Seul")
    async with test_client_factory(org.utilisateur) as client:
        reponse = await client.post(f"/api/v1/workflow/{seul.id}/groupe/completer")
        assert reponse.status_code == 200
        assert reponse.json() == {str(seul.id): []}
    await _oublier(async_session)
    assert (await service.lire_agent(seul.id, org.organisation.id)).a_un_brouillon is False


async def test_creer_un_collegue_pose_aussi_l_outil_sur_l_etape_de_retour_de_l_accueil(
    org, db_session, async_session, test_client_factory
):
    orgid = org.organisation.id
    async with test_client_factory(org.utilisateur) as client:
        principal_id, _, [s1] = await _creer_groupe(client, db_session, org, specialises=("Un",))
        await client.post(f"/api/v1/workflow/{principal_id}/groupe/completer")
        await _oublier(async_session)
        r = await client.post(f"/api/v1/workflow/{principal_id}/groupe/specialise", json={"name": "Deux"})
        assert r.status_code == 200, r.text
    await _oublier(async_session)
    accueil = await service.lire_agent(principal_id, orgid)
    depart = next(n for n in accueil.definition["nodes"] if n["type"] == "startCall")
    retour = next(n for n in accueil.definition["nodes"] if n["data"].get(MARQUEUR_ETAPE_DE_RETOUR))
    assert len(depart["data"]["tool_uuids"]) == 2
    assert retour["data"]["tool_uuids"] == depart["data"]["tool_uuids"]
    assert CLE_AGENTS_SPECIALISES in accueil.reglages and CLE_AGENT_PRINCIPAL not in accueil.reglages

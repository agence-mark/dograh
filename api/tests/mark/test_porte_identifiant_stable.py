"""[.mark] Builder partie 3, L6+ (audit 01 A8) : la porte à identifiant stable, et l'annonce d'ouverture en étiquette (02 B5).

| Test | Ce qu'il prouve |
|---|---|
| ancien graphe | une liaison sans identifiant se lit comme avant : le nom vient du libellé |
| renommer | renommer le libellé d'une porte qui a son identifiant ne change pas le nom de la fonction (moteur, consigne des portes) |
| condition | la porte fermée par la fiche est retrouvée par son identifiant après le renommage |
| trace | les portes d'une version (analyse d'un appel) gardent le nom des traces passées |
| test rejouable | un critère « outil » qui vise la porte reste juste après le renommage |
| renommage | un renommage (écran, opération ou code du builder) pose l'identifiant ; un graphe non renommé n'est pas réécrit |
| builder | une liaison renommée dans le code du builder garde son identifiant (champs cachés) |
| unicité | deux portes d'une étape au même identifiant sont refusées |
| migration | le script est idempotent, n'écrit rien sans sauvegarde, et sauvegarde avant d'écrire |
| annonce d'ouverture | elle est au catalogue des variables sous la forme que le moteur rend sans la réclamer aux campagnes |
"""

from __future__ import annotations

import json

import pytest

from api.db import db_client
from api.services.workflow.dto import ReactFlowDTO
from api.services.workflow.portes import nom_de_porte, poser_les_identifiants
from api.services.workflow.workflow_graph import WorkflowGraph, extract_template_variables


def _graphe(label="Prendre rendez-vous", identifiant=None, condition_fiche=None) -> dict:
    donnees = {"label": label, "condition": "La personne veut un rendez-vous"}
    if identifiant:
        donnees["identifiant"] = identifiant
    if condition_fiche:
        donnees["condition_sur_la_fiche"] = condition_fiche
    return {
        "nodes": [
            {"id": "1", "type": "startCall", "position": {"x": 0, "y": 0}, "data": {"name": "Accueil", "prompt": "Bonjour", "is_start": True}},
            {"id": "2", "type": "endCall", "position": {"x": 0, "y": 1}, "data": {"name": "Rendez-vous", "prompt": "Fin"}},
        ],
        "edges": [{"id": "e1", "source": "1", "target": "2", "data": donnees}],
    }


def _porte(graphe: dict):
    return WorkflowGraph(ReactFlowDTO.model_validate(graphe)).nodes["1"].out_edges[0]


def test_un_ancien_graphe_se_lit_comme_avant():
    assert _porte(_graphe()).get_function_name() == "prendre_rendez_vous"


def test_renommer_le_libelle_ne_change_pas_le_nom_de_la_porte():
    pose, n = poser_les_identifiants(_graphe())
    assert n == 1
    pose["edges"][0]["data"]["label"] = "Réserver un créneau"
    graphe = WorkflowGraph(ReactFlowDTO.model_validate(pose))
    assert graphe.nodes["1"].out_edges[0].get_function_name() == "prendre_rendez_vous"
    from api.services.workflow.porte_parlee import consigne_des_portes

    assert "- prendre_rendez_vous (vers l'étape Rendez-vous)" in consigne_des_portes(graphe.nodes["1"], graphe, lambda t: t)


def test_la_condition_sur_la_fiche_et_le_moteur_retrouvent_la_porte_renommee(three_node_workflow):
    from types import SimpleNamespace

    from api.services.workflow.pipecat_engine import PipecatEngine

    pose, _ = poser_les_identifiants(_graphe(condition_fiche={"etape_complete": True}))
    pose["edges"][0]["data"]["label"] = "Réserver un créneau"
    graphe = WorkflowGraph(ReactFlowDTO.model_validate(pose))
    engine = PipecatEngine(llm=SimpleNamespace(), context=SimpleNamespace(), workflow=graphe, call_context_vars={}, workflow_run_id=1)
    engine.active_agent.current_node = graphe.nodes["1"]
    assert engine._porte_de_l_etape("prendre_rendez_vous") is graphe.nodes["1"].out_edges[0]
    assert engine._porte_de_l_etape("reserver_un_creneau") is None
    assert engine.est_une_porte_de_l_etape("prendre_rendez_vous")


def test_les_traces_gardent_le_nom_de_la_porte_apres_le_renommage():
    from types import SimpleNamespace

    from api.services.analyse_run.du_run import _portes

    pose, _ = poser_les_identifiants(_graphe())
    pose["edges"][0]["data"]["label"] = "Réserver un créneau"
    assert _portes(SimpleNamespace(workflow_json=pose)) == {"prendre_rendez_vous"}


def test_un_test_rejouable_qui_vise_la_porte_reste_juste():
    from api.services.builder.tests_agent.verdict import ObservationConversation, evaluer_un

    pose, _ = poser_les_identifiants(_graphe())
    pose["edges"][0]["data"]["label"] = "Réserver un créneau"
    appelee = _porte(pose).get_function_name()  # ce que le modèle appelle, donc ce que la trace du test porte
    obs = ObservationConversation(texte="", outils=[{"nom": appelee, "arguments": {}}])
    assert evaluer_un({"type": "outil", "nom": "prendre_rendez_vous"}, obs).reussi


def test_poser_est_idempotent_et_ne_touche_jamais_un_identifiant_pose():
    une, n1 = poser_les_identifiants(_graphe())
    deux, n2 = poser_les_identifiants(une)
    assert (n1, n2) == (1, 0) and une == deux
    garde, n = poser_les_identifiants(_graphe(label="Autre", identifiant="porte_choisie"))
    assert n == 0 and garde["edges"][0]["data"]["identifiant"] == "porte_choisie"
    assert poser_les_identifiants(None) == (None, 0)
    assert nom_de_porte({"label": "Ça va", "identifiant": "PAS-VALIDE"}) == "_a_va"


def test_deux_portes_d_une_etape_au_meme_identifiant_sont_refusees():
    from api.services.workflow.workflow_graph import validate_unique_transition_tool_names

    erreurs = validate_unique_transition_tool_names([("a", "1", "porte"), ("b", "1", "porte")])
    assert len(erreurs) == 2


def test_le_builder_qui_renomme_une_liaison_garde_son_identifiant():
    from api.services.workflow.champs_caches import fusionner_champs_caches

    precedent, _ = poser_les_identifiants(_graphe())
    nouveau = _graphe(label="Réserver un créneau")
    fusionne = fusionner_champs_caches(nouveau, precedent)
    assert fusionne["edges"][0]["data"]["identifiant"] == "prendre_rendez_vous"


def test_un_renommage_pose_l_identifiant_et_un_graphe_non_renomme_ne_bouge_pas():
    from api.services.builder.brouillon import Operation, appliquer
    from api.services.workflow.portes import renommer

    donnees = {"label": "Prendre rendez-vous", "condition": "c"}
    assert renommer(donnees, "Prendre rendez-vous") == donnees  # libellé inchangé : rien de posé
    assert renommer(donnees, "Réserver")["identifiant"] == "prendre_rendez_vous"
    graphe = appliquer(_graphe(), [Operation(op="modifier_liaison", id="e1", label="Réserver un créneau")])
    assert graphe["edges"][0]["data"] == {"label": "Réserver un créneau", "condition": "La personne veut un rendez-vous", "identifiant": "prendre_rendez_vous"}


def test_le_builder_qui_renomme_une_liaison_sans_identifiant_garde_son_nom():
    from api.services.workflow.champs_caches import fusionner_champs_caches

    fusionne = fusionner_champs_caches(_graphe(label="Réserver un créneau"), _graphe())
    assert fusionne["edges"][0]["data"]["identifiant"] == "prendre_rendez_vous"


@pytest.mark.asyncio
async def test_la_migration_douce_sauvegarde_puis_ecrit_une_seule_fois(tmp_path, db_session, sans_preparation_des_organisations):  # noqa: F811
    from sqlalchemy import text

    from api.tests.mark.equipe_commun import creer_compte, creer_organisation
    from scripts.mark.poser_identifiants_des_portes import executer

    org = await creer_organisation(db_session, "org-portes-migration")
    user, _ = await creer_compte(db_session, "portes-m@example.test", role="Administrateur", organisations=[org])
    agent = await db_client.create_workflow("Agent ancien", _graphe(), user.id, org)
    async with db_client.async_session() as session:
        # Un graphe d'AVANT la porte stable : sans identifiant, comme en production aujourd'hui.
        await session.execute(text("UPDATE workflow_definitions SET workflow_json = CAST(:g AS json) WHERE workflow_id = :w"), {"g": json.dumps(_graphe()), "w": agent.id})
        copie = tmp_path / "portes.json"
        a_blanc = await executer(session, False, None)
        assert any(t["table"] == "workflow_definitions" for t in a_blanc) and not copie.exists()
        with pytest.raises(ValueError):
            await executer(session, True, None)  # jamais d'écriture sans sauvegarde
        existante = tmp_path / "deja.json"  # RV (point 10) : une sauvegarde qui existe déjà n'est jamais écrasée, et rien n'est réécrit
        existante.write_text("ancienne", encoding="utf-8")
        with pytest.raises(FileExistsError):
            await executer(session, True, existante)
        assert existante.read_text(encoding="utf-8") == "ancienne"
        fait = await executer(session, True, copie)
        sauve = json.loads(copie.read_text(encoding="utf-8"))
        assert {(s["table"], s["id"]) for s in sauve} == {(t["table"], t["id"]) for t in fait}
        assert all("identifiant" not in s["avant"]["edges"][0]["data"] for s in sauve if s["avant"].get("edges"))
        assert await executer(session, True, copie) == []  # seconde passe : plus rien
    relu = await db_client.get_workflow(agent.id, organization_id=org)
    graphe = (relu.released_definition or relu.current_definition).workflow_json
    assert graphe["edges"][0]["data"]["identifiant"] == "prendre_rendez_vous"


from api.tests.mark.equipe_commun import sans_preparation_des_organisations  # noqa: E402,F401


# --- L6+ (a) : l'annonce d'ouverture, étiquette de l'accueil -----------------------------------------------------------------


def test_l_annonce_d_ouverture_est_une_etiquette_que_les_campagnes_ne_reclament_pas():
    from api.services.variables_agent.catalogue import construire

    annonce = next(v for v in construire() if v.libelle == "Annonce d'ouverture")
    assert annonce.cle == "initial_context.annonce_ouverture" and annonce.exemple
    assert extract_template_variables("Bonjour. {{" + annonce.cle + "}}") == set()

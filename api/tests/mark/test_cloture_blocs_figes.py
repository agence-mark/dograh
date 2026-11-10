"""[.mark] Clôture, lot B (D17) : un bloc réutilisable se suit en direct ou se fige à la publication, par agent et par bloc.

| Test | Ce qu'il prouve |
|---|---|
| modes | défaut figé sur un agent protégé, direct sinon ; réglage de l'agent ; réglage du bloc plus fort que l'agent ; seuls les ``{{bloc:x}}`` sans ``@vN`` sont suivis |
| résolveur | l'épingle de la version jouée l'emporte sur la dernière Recette ; ``@vN`` l'emporte sur l'épingle ; sans épingle, la dernière Recette |
| publication | figé : l'épingle ``bloc:x`` = la dernière Recette, une nouvelle Recette ne change pas la version publiée ; direct : aucune épingle |
| défaut | un agent protégé fige sans réglage ; levée la protection, il suit en direct ; un réglage de bloc le contredit |
| outils | les clés ``bloc:`` ne sont jamais lues comme des outils (``sans_blocs``, fusion) |
| fusion | la fusion garde l'épingle du bloc de la branche ; « Revenir avant » rend les épingles de blocs |
| schéma | les réglages sont validés par liste fermée |
"""

from __future__ import annotations

import copy

import pytest
from pydantic import ValidationError

from api.db import outils_epingles as pins
from api.db.models import WorkflowDefinitionModel
from api.schemas.workflow_configurations import WorkflowConfigurationDefaults
from api.services.branches import champs
from api.services.etiquettes_prompt import blocs_modes, resolution, table
from api.tests.mark.test_apres_appel import _organisation, base_v4, smtp  # noqa: F401
from api.tests.mark.test_principale_protegee import AUTRE, GRAPHE, _agent, _branche_fermee, labo_est  # noqa: F401
from api.tests.mark.test_sous_dossiers_et_groupe import autre_org, org  # noqa: F401


def _bloc(*versions: tuple[int, str, str]) -> resolution.BlocLu:
    return resolution.BlocLu("politesse", "Politesse", "prompt-general", tuple(resolution.VersionDeBloc(n, s, t) for n, s, t in versions))


def _graphe_avec(texte: str) -> dict:
    g = copy.deepcopy(GRAPHE)
    g["nodes"][0]["data"]["prompt"] = texte
    return g


@pytest.fixture
def recettes(monkeypatch):
    """La bibliothèque : ``recettes.v = {slug: BlocLu}`` ; la dernière Recette se change entre deux publications."""
    etat = type("Etat", (), {"v": {}})()

    async def lire(slug):
        return etat.v.get(slug)

    monkeypatch.setattr(table, "lire_un_bloc", lire)
    return etat


# --- les modes ------------------------------------------------------------------------------------------------------------------
def test_le_defaut_est_fige_sur_un_agent_protege_et_direct_sinon_puis_l_agent_puis_le_bloc():
    assert blocs_modes.mode_effectif({}, "x", True) == "fige"
    assert blocs_modes.mode_effectif({}, "x", False) == "direct"
    assert blocs_modes.mode_effectif({"blocs_mode": "direct"}, "x", True) == "direct"  # l'agent l'emporte sur le défaut
    assert blocs_modes.mode_effectif({"blocs_mode": "fige"}, "x", False) == "fige"
    assert blocs_modes.mode_effectif({"blocs_mode": "fige", "blocs_modes": {"x": "direct"}}, "x", True) == "direct"  # le bloc l'emporte
    assert blocs_modes.mode_effectif({"blocs_mode": "fige", "blocs_modes": {"x": "direct"}}, "y", True) == "fige"
    assert blocs_modes.mode_effectif({"blocs_mode": "n'importe quoi"}, "x", True) == "fige"  # valeur inconnue : le défaut


def test_seuls_les_blocs_sans_version_sont_suivis():
    g = _graphe_avec("Bonjour {{bloc:politesse}} {{bloc:fixe@v2}} {{bloc:politesse}} {{outil:abc}}")
    assert blocs_modes.blocs_suivis(g) == ["politesse"]


def test_les_reglages_sont_valides_par_liste_fermee():
    assert WorkflowConfigurationDefaults(blocs_mode="fige", blocs_modes={"politesse": "direct"}).blocs_mode == "fige"
    with pytest.raises(ValidationError):
        WorkflowConfigurationDefaults(blocs_mode="souvent")
    with pytest.raises(ValidationError):
        WorkflowConfigurationDefaults(blocs_modes={"politesse": "plus tard"})
    assert blocs_modes.valider_les_reglages("fige", {"x": "direct"}) is None
    assert blocs_modes.valider_les_reglages("zzz", None) is not None


# --- le résolveur ----------------------------------------------------------------------------------------------------------------
def test_l_epingle_de_la_version_jouee_l_emporte_sur_la_derniere_recette_et_arobase_v_sur_l_epingle():
    bloc = _bloc((1, "recette", "ancien"), (2, "recette", "nouveau"))
    sans = resolution.Table(blocs={"politesse": bloc})
    fige = resolution.Table(blocs={"politesse": bloc}, epingles_blocs={"politesse": 1})
    assert resolution.rendre("{{bloc:politesse}}", sans) == "nouveau"  # en direct : la dernière Recette
    assert resolution.rendre("{{bloc:politesse}}", fige) == "ancien"  # figé : l'épingle
    assert resolution.rendre("{{bloc:politesse@v2}}", fige) == "nouveau"  # @vN plus fort que tout


def test_une_epingle_dont_la_version_a_disparu_ou_est_rejetee_se_lit_comme_avant():
    rejete = resolution.Table(blocs={"politesse": _bloc((1, "rejete", "mauvais"), (2, "recette", "bon"))}, epingles_blocs={"politesse": 1})
    assert resolution.rendre("[{{bloc:politesse}}]", rejete) == "[]"
    disparue = resolution.Table(blocs={"politesse": _bloc((2, "recette", "bon"))}, epingles_blocs={"politesse": 1})
    assert resolution.rendre("[{{bloc:politesse}}]", disparue) == "[]"


async def test_la_table_lit_les_epingles_de_blocs_et_les_outils_ne_les_voient_pas(recettes):
    recettes.v["politesse"] = _bloc((1, "recette", "a"))
    t = await table.construire(None, ["{{bloc:politesse}}"], outils_epingles={"bloc:politesse": 1, "uuid-d-un-outil": 3})
    assert t.epingles_blocs == {"politesse": 1}
    assert pins.sans_blocs({"bloc:politesse": 1, "uuid-d-un-outil": 3}) == {"uuid-d-un-outil": 3}
    assert pins.seulement_blocs({"bloc:politesse": 1, "uuid-d-un-outil": 3}) == {"politesse": 1}


def test_la_fusion_ne_lit_pas_une_cle_de_bloc_comme_un_outil():
    etat = champs.Etat(None, None, None, {"bloc:politesse": 2, "uuid-d-un-outil": 3})
    assert etat.outils == {"uuid-d-un-outil": 3}


# --- la publication, sur une vraie base --------------------------------------------------------------------------------------------
async def _publier(db_session, agent, graphe, configurations):
    await db_session.save_workflow_draft(agent.id, workflow_definition=graphe, workflow_configurations=configurations)
    return await db_session.publish_workflow_draft(agent.id)


async def _epingles(db_session, version_id):
    async with db_session.async_session() as s:
        return (await s.get(WorkflowDefinitionModel, version_id)).outils_epingles


async def test_fige_ecrit_la_derniere_recette_et_une_nouvelle_recette_ne_change_pas_la_version_publiee(org, db_session, recettes, labo_est):
    agent = await _agent(db_session, org)
    labo_est(org.organisation.id)  # Labo : pas protégé par défaut
    recettes.v["politesse"] = _bloc((1, "recette", "a"), (2, "recette", "b"))
    graphe = _graphe_avec("Dis {{bloc:politesse}} et {{bloc:autre@v1}}")
    publiee = await _publier(db_session, agent, graphe, {"blocs_mode": "fige"})
    assert (await _epingles(db_session, publiee.id)) == {"bloc:politesse": 2}  # @vN n'est pas épinglé
    recettes.v["politesse"] = _bloc((1, "recette", "a"), (2, "recette", "b"), (3, "recette", "c"))
    assert (await _epingles(db_session, publiee.id)) == {"bloc:politesse": 2}  # la version déjà publiée ne bouge jamais
    suivante = await _publier(db_session, agent, graphe, {"blocs_mode": "fige"})
    assert (await _epingles(db_session, suivante.id)) == {"bloc:politesse": 3}  # la publication suivante prend la nouvelle Recette


async def test_direct_n_ecrit_aucune_epingle(org, db_session, recettes, labo_est):
    agent = await _agent(db_session, org)
    labo_est(org.organisation.id)
    recettes.v["politesse"] = _bloc((1, "recette", "a"))
    publiee = await _publier(db_session, agent, _graphe_avec("{{bloc:politesse}}"), {})  # Labo : direct par défaut
    assert not (await _epingles(db_session, publiee.id))


async def test_un_agent_protege_fige_sans_reglage_levee_la_protection_il_suit_et_un_reglage_de_bloc_contredit(org, autre_org, db_session, recettes, labo_est):
    agent = await _agent(db_session, org)
    labo_est(autre_org.organisation.id)  # l'agent est chez un client, en ligne : protégé par la règle
    recettes.v["politesse"] = _bloc((1, "recette", "a"))
    graphe = _graphe_avec("{{bloc:politesse}}")
    await db_session.regler_la_protection_de_la_principale(org.organisation.id, agent.id, False)
    publiee = await _publier(db_session, agent, graphe, {})
    assert not (await _epingles(db_session, publiee.id))  # non protégé : direct
    await db_session.regler_la_protection_de_la_principale(org.organisation.id, agent.id, None)  # retour à la règle : protégé
    async with db_session.async_session() as s:
        definition = WorkflowDefinitionModel(workflow_id=agent.id, workflow_json=graphe, workflow_configurations={}, status="draft")
        assert (await pins.figer(s, definition, org.organisation.id)) == {"bloc:politesse": 1}  # protégé : figé sans réglage
        definition.workflow_configurations = {"blocs_modes": {"politesse": "direct"}}
        assert not (await pins.figer(s, definition, org.organisation.id))  # le réglage du bloc contredit


async def test_la_fusion_garde_l_epingle_du_bloc_de_la_branche(org, db_session, recettes, labo_est):
    agent = await _agent(db_session, org)
    labo_est(org.organisation.id)
    recettes.v["politesse"] = _bloc((1, "recette", "a"), (2, "recette", "b"))
    async with db_session.async_session() as s:
        definition = WorkflowDefinitionModel(
            workflow_id=agent.id, workflow_json=_graphe_avec("{{bloc:politesse}}"), workflow_configurations={"blocs_mode": "fige"}, status="published"
        )
        recalcule = await pins.figer(s, definition, org.organisation.id, choix={"bloc:politesse": 1})
        assert recalcule == {"bloc:politesse": 2}  # une publication ordinaire prend la dernière Recette
        gardee = await pins.figer(s, definition, org.organisation.id, choix={"bloc:politesse": 1}, garder_les_blocs=True)
        assert gardee == {"bloc:politesse": 1}  # la fusion garde celle de la branche


async def test_revenir_avant_rend_les_epingles_de_blocs_du_brouillon(org, db_session, recettes, labo_est):
    agent = await _agent(db_session, org)
    labo_est(org.organisation.id)
    await db_session.save_workflow_draft(agent.id, workflow_definition=AUTRE)
    await db_session.remplacer_les_epingles_du_brouillon(org.organisation.id, agent.id, {"bloc:politesse": 2})
    brouillon = await db_session.get_draft_version(agent.id)
    assert (await _epingles(db_session, brouillon.id)) == {"bloc:politesse": 2}
    vue = await db_session.outils_epingles_de_l_agent(org.organisation.id, agent.id)
    assert vue["blocs"] == {"politesse": 2} and vue["outils"] is not None


# --- l'écran lit et pose le mode d'un bloc sur un agent ----------------------------------------------------------------------------
def test_la_correction_pose_ou_retire_le_mode_d_un_bloc_sur_l_agent_et_la_citation_le_dit():
    from api.services.etiquettes_prompt import corrections

    graphe = _graphe_avec("{{bloc:politesse}}")
    _, configs, n = corrections.appliquer(graphe, {"autre": 1}, {"type": "mode_fige", "cle": "bloc:politesse"})
    assert n == 1 and configs == {"autre": 1, "blocs_modes": {"politesse": "fige"}}
    citations = corrections.citations_dans("bloc:politesse", [(7, "Agent", graphe, configs)])
    assert citations[0]["mode_du_bloc"] == "fige" and citations[0]["mode_de_l_agent"] is None
    _, direct, _ = corrections.appliquer(graphe, configs, {"type": "mode_direct", "cle": "bloc:politesse"})
    assert direct["blocs_modes"] == {"politesse": "direct"}
    _, retire, _ = corrections.appliquer(graphe, direct, {"type": "mode_defaut", "cle": "bloc:politesse"})
    assert "blocs_modes" not in retire and retire["autre"] == 1  # retour au réglage de l'agent
    with pytest.raises(corrections.CorrectionRefusee):
        corrections.appliquer(graphe, {}, {"type": "mode_fige", "cle": "outil:abc"})
    _, agent_fige, _ = corrections.appliquer(graphe, {}, {"type": "agent_fige", "cle": "bloc:politesse"})
    assert agent_fige == {"blocs_mode": "fige"}
    _, agent_defaut, _ = corrections.appliquer(graphe, agent_fige, {"type": "agent_defaut", "cle": "bloc:politesse"})
    assert agent_defaut == {}

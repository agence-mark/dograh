"""[.mark] Builder partie 3, lot 8 (§ 3 bis du plan) : les étiquettes d'objets des prompts.

| Test | Ce qu'il prouve (critère du § 3 bis) |
|---|---|
| (a) résolution | chaque famille donne le texte attendu ; un outil donne le nom EXACT de sa fonction (classique et MCP préfixé) |
| (a) sans étiquette | un prompt sans étiquette ressort à l'identique ; (f) un texte à variables seules se rend comme avant |
| R1 | le VRAI moteur (``PipecatEngine``, pipeline et cerveau simulé) envoie au modèle une étiquette de chaque famille résolue |
| (b) renommage | renommer un outil (base réelle) ou une étape ne casse aucun prompt : la clé est l'identifiant |
| (c) blocage | inconnue, supprimée, archivée, non rattachée bloquent la publication ; la correction en un clic la rend possible |
| (d) cloisonnement | une étiquette ne résout jamais l'outil d'une autre organisation ; le catalogue est filtré dans la requête |
| (e) Utilisé dans | exact après ajout, retrait et suppression |
| règle du prompt | ``nom_d_outil_dans_le_texte`` n'attrape pas ``{{outil:…}}`` et refuse toujours le nom brut |
| variables | une étiquette d'objet n'est jamais comptée comme variable inconnue (garde, extraction des variables requises) |
| tests | un outil cité jamais appelé pendant un test = un avertissement, jamais un échec |
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from api.enums import ToolCategory
from api.services.etiquettes_prompt import catalogue as cat
from api.services.etiquettes_prompt import corrections, essais
from api.services.etiquettes_prompt import familles as f
from api.services.etiquettes_prompt import resolution as res
from api.services.etiquettes_prompt.table import construire
from api.utils.template_renderer import render_template

UUID = "3f2a0000-0000-0000-0000-000000000001"
MCP = "3f2a0000-0000-0000-0000-0000000000aa"
DOC = "9c100000-0000-0000-0000-000000000001"


def _table() -> res.Table:
    return res.Table(
        outils={UUID: "reserver_creneau", f"{MCP}/chercher": "mcp__agenda__chercher"},
        agents={"42": "Entretien"},
        documents={DOC: "faq-entretien.md"},
        blocs={
            "politesse": res.BlocLu(
                "politesse",
                "Règles de politesse",
                "prompt-general",
                (res.VersionDeBloc(1, "recette", "Vouvoie toujours."), res.VersionDeBloc(2, "candidat", "Tutoie.")),
            )
        },
    )


# --- (a) résolution -------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "texte, attendu",
    [
        ("Appelle {{outil:" + UUID + "}}.", "Appelle reserver_creneau."),
        ("Cherche avec {{outil:" + MCP + "/chercher}}.", "Cherche avec mcp__agenda__chercher."),
        ("Va à {{etape:n2}}.", "Va à Tri du motif."),
        ("Confie à {{agent:42}}.", "Confie à Entretien."),
        ("Transfère pour {{equipe:devis}}.", "Transfère pour devis."),
        ("Lis {{document:" + DOC + "}}.", "Lis faq-entretien.md."),
        ("Dis {{phrase:outil_echec}}", "Dis Un instant."),
        ("{{bloc:politesse}}", "Vouvoie toujours."),
        ("{{bloc:politesse@v2}}", "Tutoie."),
    ],
)
def test_a_chaque_famille_donne_le_texte_attendu(texte, attendu):
    rendu = res.rendre(texte, _table(), etapes={"n2": "Tri du motif"}, phrase=lambda c: "Un instant." if c == "outil_echec" else None)
    assert rendu == attendu


def test_a_un_prompt_sans_etiquette_ressort_identique_et_f_les_variables_comme_avant():
    texte = "Bonjour {{nom | fallback:vous}}, il est {{heure}}."
    assert res.rendre(texte, _table()) is texte
    assert render_template(res.rendre(texte, _table()), {"heure": "9 h"}) == render_template(texte, {"heure": "9 h"})


def test_un_bloc_ne_cite_pas_un_bloc_et_garde_ses_autres_etiquettes():
    table = _table()
    table.blocs["gabarit"] = res.BlocLu("gabarit", "Gabarit", "moules-etape", (res.VersionDeBloc(1, "recette", "A {{bloc:politesse}} B {{outil:" + UUID + "}}"),))
    assert res.rendre("{{bloc:gabarit}}", table) == "A  B reserver_creneau"


def test_un_bloc_suit_la_derniere_recette_et_une_version_epinglee_reste_lisible():
    bloc = _table().blocs["politesse"]
    assert bloc.choisie(None).numero == 1  # la v2 est Candidat : suivre = dernière RECETTE
    assert bloc.choisie(2).texte == "Tutoie."
    assert bloc.choisie(9) is None


# --- R1 : le vrai moteur --------------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_R1_le_vrai_moteur_envoie_chaque_famille_resolue_au_modele():
    from pipecat.pipeline.pipeline import Pipeline
    from pipecat.pipeline.worker import PipelineParams, PipelineWorker
    from pipecat.processors.aggregators.llm_context import LLMContext
    from pipecat.processors.aggregators.llm_response_universal import LLMContextAggregatorPair
    from pipecat.tests import MockLLMService, MockTTSService
    from pipecat.tests.mock_transport import MockTransport
    from pipecat.transports.base_transport import TransportParams

    from api.services.etiquettes_prompt import moteur
    from api.services.workflow.dto import ReactFlowDTO
    from api.services.workflow.pipecat_engine import PipecatEngine
    from api.services.workflow.workflow_graph import WorkflowGraph
    from api.tests.pipecat_test_utils import run_engine_test_pipeline

    prompt = (
        "Outil {{outil:" + UUID + "}} ; MCP {{outil:" + MCP + "/chercher}} ; étape {{etape:fin}} ; agent {{agent:42}} ; "
        "équipe {{equipe:devis}} ; document {{document:" + DOC + "}} ; phrase {{phrase:outil_echec}} ; bloc {{bloc:politesse}} ; "
        "client {{client}}."
    )
    graphe = WorkflowGraph(
        ReactFlowDTO.model_validate(
            {
                "nodes": [
                    {"id": "debut", "type": "startCall", "position": {"x": 0, "y": 0},
                     "data": {"name": "Accueil", "prompt": prompt, "is_start": True, "add_global_prompt": False}},
                    {"id": "fin", "type": "endCall", "position": {"x": 0, "y": 1}, "data": {"name": "Au revoir", "prompt": "Fin."}},
                ],
                "edges": [{"id": "e", "source": "debut", "target": "fin", "data": {"label": "Fini", "condition": "fini"}}],
            }
        )
    )
    llm = MockLLMService(mock_steps=MockLLMService.create_multi_step_responses(MockLLMService.create_text_chunks("Bonjour"), num_text_steps=1, step_prefix="R"), chunk_delay=0.001)
    transport = MockTransport(params=TransportParams(audio_in_enabled=True, audio_out_enabled=True, audio_in_sample_rate=16000, audio_out_sample_rate=16000, audio_out_end_silence_secs=0))
    context = LLMContext()
    engine = PipecatEngine(llm=llm, context=context, workflow=graphe, call_context_vars={"client": "Durand"}, workflow_run_id=1)
    task = PipelineWorker(
        Pipeline([transport.input(), llm, MockTTSService(mock_audio_duration_ms=40, frame_delay=0), transport.output(), LLMContextAggregatorPair(context).assistant()]),
        params=PipelineParams(),
        enable_rtvi=False,
    )
    engine.call_worker = task
    lue = AsyncMock(return_value=_table())
    with (
        patch("api.db:db_client.get_organization_id_by_workflow_run_id", new_callable=AsyncMock, return_value=1),
        patch.object(moteur, "construire", lue),
    ):
        await run_engine_test_pipeline(task, engine, transport)

    envoye = llm._settings.system_instruction
    for attendu in ("Outil reserver_creneau", "MCP mcp__agenda__chercher", "étape Au revoir", "agent Entretien", "équipe devis",
                    "document faq-entretien.md", "bloc Vouvoie toujours.", "client Durand"):
        assert attendu in envoye, (attendu, envoye)
    assert "phrase " in envoye and "{{" not in envoye
    assert lue.await_count == 1  # une seule lecture pour l'appel (le graphe est mis en table une fois)


# --- (b) renommage, (d) cloisonnement : base réelle -------------------------------------------------------------------------

from api.tests.mark.test_apres_appel import _organisation, base_v4, smtp  # noqa: E402,F401  (fixtures)
from api.tests.mark.test_sous_dossiers_et_groupe import autre_org, org  # noqa: E402,F401


async def _outil(db, o, nom, categorie=ToolCategory.HTTP_API.value, definition=None):
    return await db.create_tool(
        organization_id=o.organisation.id,
        user_id=o.utilisateur.id,
        name=nom,
        definition=definition or {"schema_version": 1, "type": "http_api", "config": {"method": "POST", "url": "https://x.example.test", "parameters": []}},
        category=categorie,
        description="Réserve.",
    )


async def test_b_renommer_un_outil_ne_casse_aucun_prompt(org, db_session):  # noqa: F811
    outil = await _outil(db_session, org, "Réserver créneau")
    texte = "Appelle {{outil:" + outil.tool_uuid + "}}."
    avant = await construire(org.organisation.id, [texte])
    assert res.rendre(texte, avant) == "Appelle r_server_cr_neau."  # le nom exact que le moteur donne à la fonction
    await db_session.update_tool(tool_uuid=outil.tool_uuid, organization_id=org.organisation.id, name="Prendre rendez-vous")
    apres = await construire(org.organisation.id, [texte])
    assert res.rendre(texte, apres) == "Appelle prendre_rendez_vous."


def test_b_renommer_une_etape_ne_casse_aucun_prompt():
    texte = "Passe à {{etape:n7}}."
    assert res.rendre(texte, res.Table(), etapes={"n7": "Rappel"}) == "Passe à Rappel."
    assert res.rendre(texte, res.Table(), etapes={"n7": "Proposer un rappel"}) == "Passe à Proposer un rappel."


async def test_d_une_etiquette_ne_resout_jamais_l_outil_d_une_autre_organisation(org, autre_org, db_session):  # noqa: F811
    etranger = await _outil(db_session, autre_org, "secret_d_autrui")
    texte = "{{outil:" + etranger.tool_uuid + "}}"
    assert (await construire(org.organisation.id, [texte])).outils == {}
    assert (await construire(autre_org.organisation.id, [texte])).outils == {etranger.tool_uuid: "secret_d_autrui"}
    with patch.object(cat, "_sujets", AsyncMock(return_value=[])), patch.object(cat, "lire_les_blocs", AsyncMock(return_value=[])):
        catalogue, _ = await cat.catalogue_de(org.organisation.id, None)
    assert f"outil:{etranger.tool_uuid}" not in catalogue
    graphe = {"nodes": [{"id": "1", "type": "startCall", "data": {"name": "A", "prompt": texte}}]}
    probleme = cat.diagnostiquer(graphe, None, catalogue)
    assert [p.motif for p in probleme] == [cat.INTROUVABLE]  # rouge côté prompt


# --- (c) blocage et correction ---------------------------------------------------------------------------------------------


def _catalogue() -> dict[str, cat.ObjetCitable]:
    return {
        f"outil:{UUID}": cat.ObjetCitable(f"outil:{UUID}", "outil", "reserver", rendu="reserver"),
        "outil:vieux": cat.ObjetCitable("outil:vieux", "outil", "vieux", statut=cat.ARCHIVE),
        "outil:neuf": cat.ObjetCitable("outil:neuf", "outil", "neuf", statut=cat.BROUILLON),
    }


def _graphe(prompt: str, outils=()) -> dict:
    return {
        "nodes": [
            {"id": "1", "type": "startCall", "position": {"x": 0, "y": 0}, "data": {"name": "Accueil", "prompt": prompt, "tool_uuids": list(outils)}},
            {"id": "2", "type": "endCall", "position": {"x": 0, "y": 1}, "data": {"name": "Fin", "prompt": "Fin."}},
        ],
        "edges": [{"id": "e", "source": "1", "target": "2", "data": {"label": "Fini", "condition": "fini"}}],
    }


@pytest.mark.parametrize(
    "prompt, outils, motif",
    [
        ("{{outil:inexistant}}", (), cat.INTROUVABLE),
        ("{{outil:vieux}}", ("vieux",), cat.ARCHIVE),
        ("{{outil:neuf}}", ("neuf",), cat.BROUILLON),
        ("{{outil:" + UUID + "}}", (), cat.NON_RATTACHE),
        ("{{agent:999}}", (), cat.INTROUVABLE),
    ],
)
def test_c_chaque_cas_bloque_et_porte_sa_correction(prompt, outils, motif):
    problemes = cat.diagnostiquer(_graphe(prompt, outils), None, _catalogue())
    assert [p.motif for p in problemes] == [motif] and problemes[0].bloquant
    assert problemes[0].corrections[-1]["type"] == "retirer"
    correction = problemes[0].corrections[0]
    graphe, configs, n = corrections.appliquer(_graphe(prompt, outils), {}, correction)
    assert n == 1 and cat.diagnostiquer(graphe, configs, _catalogue()) == []


def test_c_une_famille_illisible_ne_bloque_jamais_a_tort():
    assert cat.diagnostiquer(_graphe("{{equipe:devis}}"), None, {}, illisibles={"equipe"}) == []
    assert [p.motif for p in cat.diagnostiquer(_graphe("{{equipe:devis}}"), None, {})] == [cat.INTROUVABLE]


async def test_c_la_publication_est_bloquee_puis_possible_une_fois_corrigee(banc):  # noqa: F811
    from api.services.builder.tests_agent import publication
    from api.services.publication import controles
    from api.tests.mark.builder_commun import AGENT, ORG_CLIENT, sans_les_lignes_de_pret

    wf = banc.workflows[AGENT]
    configs = sans_les_lignes_de_pret({"moteur_sortie_d_impasse": False})
    casse = SimpleNamespace(workflow_json=_graphe("Appelle {{outil:" + UUID + "}}."), version_number=2, workflow_configurations=configs)
    with patch.object(cat, "catalogue_de", AsyncMock(return_value=(_catalogue(), set()))):
        vue = await controles.evaluer(wf, casse, ORG_CLIENT)
        bloc = next(c for c in vue["controles"] if c["cle"] == "etiquettes")
        assert (bloc["position"], bloc["statut"]) == ("bloque", "echec") and vue["bloque"]
        ligne = next(l for l in vue["lignes"] if l["id"] == "etiquettes")
        assert ligne["etat"] == "bloquant"
        refus = await publication.verifier_avant_publication(wf, casse, ORG_CLIENT)
        assert refus is not None and any("Étiquettes des prompts" in e["message"] for e in refus["errors"])

        graphe, _, _ = corrections.appliquer(casse.workflow_json, {}, {"type": "rattacher", "cle": f"outil:{UUID}", "noeud_id": "1"})
        corrige = SimpleNamespace(workflow_json=graphe, version_number=2, workflow_configurations=configs)
        assert await publication.verifier_avant_publication(wf, corrige, ORG_CLIENT) is None


async def test_c_aucun_reglage_ne_peut_eteindre_le_controle_des_etiquettes(banc):  # noqa: F811
    from api.services.publication import controles
    from api.tests.mark.builder_commun import AGENT, ORG_CLIENT, sans_les_lignes_de_pret

    configs = sans_les_lignes_de_pret({"moteur_sortie_d_impasse": False, "publication": {"controles": {"etiquettes": "eteint"}}})
    casse = SimpleNamespace(workflow_json=_graphe("{{outil:inexistant}}"), version_number=2, workflow_configurations=configs)
    with patch.object(cat, "catalogue_de", AsyncMock(return_value=(_catalogue(), set()))):
        vue = await controles.evaluer(banc.workflows[AGENT], casse, ORG_CLIENT)
    assert next(c for c in vue["controles"] if c["cle"] == "etiquettes")["statut"] == "echec"


async def test_c_un_agent_sans_etiquette_n_a_pas_de_ligne(banc):  # noqa: F811
    from api.services.publication import controles
    from api.tests.mark.builder_commun import AGENT, ORG_CLIENT, sans_les_lignes_de_pret

    propre = SimpleNamespace(workflow_json=_graphe("Bonjour."), version_number=2, workflow_configurations=sans_les_lignes_de_pret({}))
    vue = await controles.evaluer(banc.workflows[AGENT], propre, ORG_CLIENT)
    assert not any(c["cle"] in ("etiquettes", "blocs_a_jour") for c in vue["controles"])


from api.tests.mark.test_builder_tests_agent import banc  # noqa: E402,F401


# --- (e) Utilisé dans ---------------------------------------------------------------------------------------------------


def test_e_utilise_dans_suit_l_ajout_le_retrait_et_la_suppression():
    cle = f"outil:{UUID}"
    vide: list = []
    assert corrections.citations_dans(cle, [(1, "A", _graphe("Bonjour."), None)]) == vide
    graphe = _graphe("Appelle {{outil:" + UUID + "}}.", (UUID,))
    trouves = corrections.citations_dans(cle, [(1, "A", graphe, None), (2, "B", _graphe("Rien."), None)])
    assert [(t["agent_id"], t["noeud_id"], t["champ"]) for t in trouves] == [(1, "1", "nodes[1].prompt")]
    retire, _, _ = corrections.appliquer(graphe, {}, {"type": "retirer", "cle": cle})
    assert corrections.citations_dans(cle, [(1, "A", retire, None)]) == vide
    assert "{{" not in retire["nodes"][0]["data"]["prompt"]


# --- règle du prompt, variables -------------------------------------------------------------------------------------------


def test_la_regle_du_nom_d_outil_n_attrape_pas_l_etiquette_et_refuse_le_nom_brut():
    from api.services.builder.controle.regles import nom_d_outil_dans_le_texte

    def _entree(prompt):
        return SimpleNamespace(
            outils={"x": SimpleNamespace(nom="reserver_creneau")},
            noms_d_outils_du_moteur=(),
            graphe={"nodes": [{"id": "1", "type": "agentNode", "data": {"name": "E", "prompt": prompt}}]},
        )

    assert nom_d_outil_dans_le_texte(_entree("Appelle {{outil:reserver_creneau}}.")) == []
    assert [d.code for d in nom_d_outil_dans_le_texte(_entree("Appelle reserver_creneau."))] == ["nom_d_outil_dans_le_texte"]


def test_une_etiquette_n_est_jamais_une_variable_inconnue():
    from api.services.builder.controle.regles import variables_ecrites
    from api.services.variables_agent.citations import cles_citees
    from api.services.workflow.workflow_graph import extract_template_variables

    texte = "{{client}} {{outil:" + UUID + "}} {{bloc:politesse@v2}}"
    assert extract_template_variables(texte) == {"client"}
    assert [c for c, _ in cles_citees(texte)] == ["client"]
    assert variables_ecrites(texte) == ["client"]
    assert f.est_une_etiquette("outil:x") and not f.est_une_etiquette("initial_context.x") and not f.est_une_etiquette("x:y")


# --- tests : un outil cité jamais appelé -----------------------------------------------------------------------------------


def test_un_outil_cite_jamais_appele_est_un_avertissement_jamais_un_echec():
    cites = {"reserver_creneau": "reserver_creneau", "sms": "sms"}
    essais_ = [{"reussi": True, "outils_appeles": ["sms"]}, {"erreur": "panne", "reussi": False}]
    avert = essais.outils_cites_jamais_appeles(cites, essais_)
    assert [a["outil"] for a in avert] == ["reserver_creneau"] and avert[0]["type"] == "outil_cite_jamais_appele"
    assert essais.outils_cites_jamais_appeles(cites, [{"erreur": "x"}]) == []
    assert essais.outils_cites_jamais_appeles({}, essais_) == []

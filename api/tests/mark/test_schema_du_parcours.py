"""[.mark] Chantier correctifs-modules, lot 4 bis : le schéma du parcours.

Plan : ``Labo-agent-vocal/plans/correctifs-modules/2026-09-28-plan-correctifs-modules.md``.
Réglage d'agent « Generate the flow map » (``generer_schema_parcours``), éteint par
défaut. Allumé : à chaque enregistrement, le code lit le graphe et écrit un bloc
``<parcours_genere>`` à la fin du prompt global (« # Les étapes de l'appel », une ligne par
étape et son rôle) et « Tu es ici : <étape> » dans le prompt de chaque étape, sauf en greffier
avec les portes dans la réponse (chantier schema-parcours-unique, C1 et C4). Blocs délimités,
remplacés à chaque enregistrement, jamais empilés ; seuls les noms d'étapes et leur rôle y entrent.

| Test | Ce qu'il prouve |
|---|---|
| traversant | la vraie route d'enregistrement, puis ``_run_pipeline`` sur la base : le bloc et « Tu es ici » sont dans les prompts enregistrés ET dans la requête au modèle |
| deux enregistrements | aucun doublon |
| étape renommée, porte ajoutée | le bloc suit le graphe |
| case éteinte | l'enregistrement est identique à aujourd'hui ; des blocs laissés sont retirés |
| texte écrit à la main | jamais touché |
| ancienne carte | disparue : ni porte ni « → » dans la carte, quel que soit le mode |
| C4, traversant | greffier avec portes : carte des rôles, pas de « Tu es ici » ; la case seule enregistrée lit le mode enregistré |
| types (agents-specialises) | accueil : « # Ton équipe » + une ligne par outil de passation (nom et description lus en base) puis « # Tes étapes » ; spécialiste : mission de l'étape de départ et sortie marquée retour ; agent seul inchangé ; dans un groupe la case est ignorée (forcé allumé) ; bloc remplacé, jamais empilé ; aucun mot de métier (noms neutres) |
"""

import copy
import re
import uuid

import pytest
from pipecat.tests import ContextCapturingMockLLM

from api.db.models import OrganizationModel, UserModel
from api.enums import OrganizationConfigurationKey, WorkflowRunMode
from api.schemas.ai_model_configuration import EffectiveAIModelConfiguration
from api.services.configuration.ai_model_configuration import (
    convert_legacy_ai_model_configuration_to_v2,
)
from api.services.workflow.fiche_au_fil_de_leau import (
    CLE_MODE,
    CLE_PORTES_DANS_LA_REPONSE,
    MODE_GREFFIER,
)
from api.services.workflow.schema_du_parcours import (
    TYPE_ACCUEIL,
    TYPE_SEUL,
    TYPE_SPECIALISTE,
    appliquer,
    reglage_allume,
    type_de_workflow,
)
from api.tests.integrations._run_pipeline_helpers import USER_CONFIGURATION
from api.tests.mark.test_outil_noter import CONFIG_ALLUMEE
from api.tests.mark.test_traversants_appel import ACCUEIL, _appeler, _borne, _texte

GLOBAL = "Tu es l'agent d'accueil. Sois bref."


def _definition() -> dict:
    return {
        "nodes": [
            {
                "id": "global",
                "type": "globalNode",
                "position": {"x": 0, "y": -200},
                "data": {"name": "Global", "prompt": GLOBAL},
            },
            {
                "id": "start",
                "type": "startCall",
                "position": {"x": 0, "y": 0},
                "data": {
                    "name": "Accueil",
                    "prompt": "Comprends la demande.",
                    "is_start": True,
                    "allow_interrupt": False,
                    "add_global_prompt": True,
                    "greeting": ACCUEIL,
                    "greeting_type": "text",
                },
            },
            {
                "id": "demande",
                "type": "agentNode",
                "position": {"x": 0, "y": 100},
                "data": {"name": "Demande", "prompt": "Note la demande.", "add_global_prompt": True},
            },
            {
                "id": "end",
                "type": "endCall",
                "position": {"x": 0, "y": 200},
                "data": {
                    "name": "Fin",
                    "prompt": "Termine l'appel poliment.",
                    "is_end": True,
                    "allow_interrupt": False,
                    "add_global_prompt": False,
                },
            },
        ],
        "edges": [
            {
                "id": "e1",
                "source": "start",
                "target": "demande",
                "data": {"label": "Aller a la demande", "condition": "Quand la demande est claire."},
            },
            {
                "id": "e2",
                "source": "demande",
                "target": "end",
                "data": {"label": "End Call", "condition": "Quand l'appelant veut raccrocher."},
            },
        ],
    }


def _prompt(definition: dict, identifiant: str) -> str:
    return next(n for n in definition["nodes"] if n["id"] == identifiant)["data"]["prompt"]


# --- Le module seul -------------------------------------------------------------


def _carte(definition: dict) -> list[str]:
    bloc = _prompt(definition, "global").split("<parcours_genere>", 1)[1]
    return bloc.split("</parcours_genere>", 1)[0].strip().splitlines()


def test_allume_le_parcours_et_la_position_sont_ecrits():
    d = appliquer(_definition(), True)
    parcours = _prompt(d, "global")
    assert parcours.startswith(GLOBAL + "\n\n<parcours_genere>") and parcours.endswith("</parcours_genere>")
    assert _carte(d) == ["# Les étapes de l'appel", "Accueil", "Demande", "Fin"]
    assert "→" not in parcours
    assert _prompt(d, "demande") == "Note la demande.\n\n<position_generee>Tu es ici : Demande</position_generee>"
    assert _prompt(d, "start").endswith("<position_generee>Tu es ici : Accueil</position_generee>")


def test_deux_enregistrements_ne_font_aucun_doublon():
    une = appliquer(_definition(), True)
    assert appliquer(copy.deepcopy(une), True) == une


def test_une_etape_renommee_ou_une_porte_ajoutee_met_le_bloc_a_jour():
    d = appliquer(_definition(), True)
    d["nodes"][2]["data"]["name"] = "Dossier"
    d["edges"].append(
        {"id": "e3", "source": "start", "target": "end", "data": {"label": "Raccrocher", "condition": "c"}}
    )
    d = appliquer(d, True)
    parcours = _prompt(d, "global")
    assert "Demande" not in parcours and "Dossier" in _carte(d)
    assert "→" not in parcours
    assert _prompt(d, "demande").count("<position_generee>") == 1 and "Tu es ici : Dossier" in _prompt(d, "demande")


def test_eteint_rien_ne_change_et_les_blocs_laisses_sont_retires():
    assert appliquer(_definition(), False) == _definition()
    assert appliquer(appliquer(_definition(), True), False) == _definition()


def test_le_texte_ecrit_a_la_main_n_est_jamais_touche():
    d = _definition()
    d["nodes"][0]["data"]["prompt"] = GLOBAL + "\n\nMa note : parcours à revoir."
    allume = appliquer(d, True)
    assert _prompt(allume, "global").startswith(GLOBAL + "\n\nMa note : parcours à revoir.\n\n<parcours_genere>")
    assert appliquer(allume, False) == d


def test_un_parcours_ecrit_a_la_main_survit_case_eteinte_comme_allumee():
    """Revue du 28/09 (bloquant) : l'agent n° 34 porte un ``<parcours>`` écrit par
    ``schema.js``. Des repères identiques l'effaçaient à tout enregistrement, case
    éteinte. Les repères du code ne peuvent pas être ceux d'un texte écrit à la main."""
    d = _definition()
    main = GLOBAL + "\n\n<parcours>\naccueil : comprendre la demande\n</parcours>"
    d["nodes"][0]["data"]["prompt"] = main
    assert appliquer(d, False) == d
    allume = appliquer(d, True)
    assert _prompt(allume, "global").startswith(main + "\n\n")
    assert appliquer(allume, False) == d


def test_l_ancienne_carte_a_disparu_quel_que_soit_le_mode():
    """Chantier schema-parcours-unique (C1) : une seule carte, celle des rôles. Ni le nom
    d'une porte ni « → » n'y entrent, avec ou sans « Tu es ici »."""
    for position in (True, False):
        global_ = _prompt(appliquer(_definition(), True, position), "global")
        assert "→" not in global_ and "aller_a_la_demande" not in global_
        assert "# Les étapes de l'appel" in global_


def test_C4_greffier_avec_portes_pas_de_tu_es_ici():
    d = appliquer(_definition(), True, False)
    assert _carte(d)[0] == "# Les étapes de l'appel"
    assert all("<position_generee>" not in (n["data"].get("prompt") or "") for n in d["nodes"])
    # Revenir à un autre mode remet « Tu es ici », sans doublon de carte.
    autre = appliquer(d, True, True)
    assert autre == appliquer(_definition(), True)



# --- Les trois types de workflow (chantier agents-specialises) ---------------------

COLLEGUES = [("outil_a", "Passe l'appel à l'agent a."), ("outil_b", "")]
EQUIPE_ACCUEIL = (
    "# Ton équipe\n"
    "Tu es l'accueil. Pour passer la main à un collègue, tu appelles son outil, sans rien dire. "
    "Quand un collègue te rend la main, tu lis la réponse à sa dernière question.\n"
    "Tes collègues :\n"
    "- outil_a : Passe l'appel à l'agent a.\n"
    "- outil_b"
)


def _bloc(definition: dict) -> str:
    bloc = _prompt(definition, "global").split("<parcours_genere>", 1)[1]
    return bloc.split("</parcours_genere>", 1)[0].strip()


def _definition_specialiste(avec_retour: bool = True) -> dict:
    d = _definition()
    d["nodes"][1]["data"]["prompt"] = "# Ta mission ici\nun spécialiste de la mission a.\n\nFais ceci."
    if avec_retour:
        d["nodes"][2]["data"]["retour_au_principal"] = True
    return d


def test_le_type_se_lit_dans_les_reglages():
    assert type_de_workflow(None) == TYPE_SEUL and type_de_workflow({}) == TYPE_SEUL
    assert type_de_workflow({"agents_specialises": []}) == TYPE_SEUL
    assert type_de_workflow({"agents_specialises": [7, 8]}) == TYPE_ACCUEIL
    assert type_de_workflow({"agent_principal_id": 3}) == TYPE_SPECIALISTE
    assert type_de_workflow({"agent_principal_id": None}) == TYPE_SEUL


def test_accueil_le_bloc_equipe_precede_les_etapes_avec_les_collegues():
    d = appliquer(_definition(), True, True, TYPE_ACCUEIL, COLLEGUES)
    assert _bloc(d) == EQUIPE_ACCUEIL + "\n\n# Tes étapes\nAccueil\nDemande\nFin"
    assert "# Les étapes de l'appel" not in _prompt(d, "global")
    # « Tu es ici » en fin d'étape, inchangé.
    assert _prompt(d, "demande").endswith("<position_generee>Tu es ici : Demande</position_generee>")


def test_accueil_sans_outil_de_passation_pas_de_liste():
    bloc = _bloc(appliquer(_definition(), True, True, TYPE_ACCUEIL, []))
    assert "Tes collègues" not in bloc and bloc.startswith("# Ton équipe\nTu es l'accueil.")


def test_specialiste_mission_de_depart_et_sortie_de_retour():
    d = appliquer(_definition_specialiste(), True, True, TYPE_SPECIALISTE)
    assert _bloc(d) == (
        "# Ton équipe\n"
        "Tu es un spécialiste de la mission a. "
        "Tu reçois un appel déjà commencé : tout ce qui a été dit compte. "
        "Pour rendre la main à l'accueil, tu écris la sortie Demande, "
        "dès que la demande n'est pas la tienne ou que ton travail est fini.\n\n"
        "# Tes étapes\nAccueil : un spécialiste de la mission a\nDemande\nFin"
    )


def test_specialiste_sans_etape_de_retour_pas_de_phrase_pour_rendre_la_main():
    bloc = _bloc(appliquer(_definition_specialiste(avec_retour=False), True, True, TYPE_SPECIALISTE))
    assert "rendre la main" not in bloc and "écris la sortie" not in bloc
    assert "Tu reçois un appel déjà commencé" in bloc


def test_agent_seul_reste_inchange_quel_que_soit_le_type_passe_par_defaut():
    assert appliquer(_definition(), True) == appliquer(_definition(), True, True, TYPE_SEUL, COLLEGUES)
    assert _bloc(appliquer(_definition(), True)).startswith("# Les étapes de l'appel")


def test_le_bloc_est_remplace_jamais_empile_meme_en_changeant_de_type():
    accueil = appliquer(_definition(), True, True, TYPE_ACCUEIL, COLLEGUES)
    deux_fois = appliquer(copy.deepcopy(accueil), True, True, TYPE_ACCUEIL, COLLEGUES)
    assert deux_fois == accueil and _prompt(accueil, "global").count("<parcours_genere>") == 1
    # D'accueil à spécialiste, puis à agent seul : un seul bloc à chaque fois.
    specialiste = appliquer(copy.deepcopy(accueil), True, True, TYPE_SPECIALISTE)
    assert _prompt(specialiste, "global").count("<parcours_genere>") == 1
    assert "Tes collègues" not in _prompt(specialiste, "global")
    assert appliquer(specialiste, True) == appliquer(_definition(), True)
    assert appliquer(accueil, False) == _definition()


def test_dans_un_groupe_la_case_est_ignoree_forcee_allumee():
    assert reglage_allume({"agents_specialises": [2], "generer_schema_parcours": False}) is True
    assert reglage_allume({"agent_principal_id": 2}) is True
    assert reglage_allume({"generer_schema_parcours": False}) is False
    assert reglage_allume({"generer_schema_parcours": True}) is True
    assert reglage_allume({"fiche_mode_de_note": "outil"}) is None


def test_aucun_mot_de_metier_dans_le_bloc_genere():
    """Tout ce qui entre dans le bloc vient du graphe, des descriptions d'outils ou des phrases
    fixes du code : les mots de l'exemple en sont la seule matière, rien d'autre ne s'y glisse."""
    d = _definition_specialiste()
    for texte in (
        _bloc(appliquer(d, True, True, TYPE_SPECIALISTE)),
        _bloc(appliquer(_definition(), True, True, TYPE_ACCUEIL, COLLEGUES)),
    ):
        reste = texte
        for connu in (
            "spécialiste de la mission a", "outil_a", "outil_b", "Passe l'appel à l'agent a",
            "Accueil", "Demande", "Fin",
        ):
            reste = reste.replace(connu, "")
        assert not re.search(r"poêle|magasin|panne|entretien|rendez|véranda", reste, re.IGNORECASE)


# --- Traversant : la route d'enregistrement, puis l'appel ---------------------------


async def _agent_en_base(db_session, async_session):
    suffixe = uuid.uuid4().hex[:10]
    org = OrganizationModel(provider_id=f"test-org-parcours-{suffixe}")
    async_session.add(org)
    await async_session.flush()
    user = UserModel(provider_id=f"test-user-parcours-{suffixe}", selected_organization_id=org.id)
    async_session.add(user)
    await async_session.flush()
    modeles = copy.deepcopy(USER_CONFIGURATION)
    modeles["stt"]["language"] = "fr"
    await db_session.upsert_configuration(
        org.id,
        OrganizationConfigurationKey.MODEL_CONFIGURATION_V2.value,
        convert_legacy_ai_model_configuration_to_v2(
            EffectiveAIModelConfiguration.model_validate(modeles)
        ).model_dump(mode="json", exclude_none=True),
    )
    workflow = await db_session.create_workflow(
        name="Parcours", workflow_definition=_definition(), user_id=user.id, organization_id=org.id
    )
    return user, workflow


async def _enregistrer(client, workflow_id: int, corps: dict) -> dict:
    reponse = await client.put(f"/api/v1/workflow/{workflow_id}", json={"name": "Parcours", **corps})
    assert reponse.status_code == 200, reponse.text
    return reponse.json()


@pytest.mark.asyncio
@_borne
async def test_traversant_la_route_ecrit_le_parcours_et_le_modele_le_recoit(
    db_session, async_session, test_client_factory
):
    user, workflow = await _agent_en_base(db_session, async_session)
    async with test_client_factory(user) as client:
        await _enregistrer(
            client,
            workflow.id,
            {"workflow_definition": _definition(), "workflow_configurations": {"generer_schema_parcours": True}},
        )
        # Deuxième enregistrement, le graphe seul : la case enregistrée s'applique, sans doublon.
        await _enregistrer(client, workflow.id, {"workflow_definition": _definition()})

    brouillon = await db_session.get_draft_version(workflow.id)
    enregistre = brouillon.workflow_json
    assert _prompt(enregistre, "global").count("<parcours_genere>") == 1
    assert "Tu es ici : Accueil" in _prompt(enregistre, "start")

    publiee = await db_session.publish_workflow_draft(workflow.id)
    run = await db_session.create_workflow_run(
        name="Parcours",
        workflow_id=workflow.id,
        mode=WorkflowRunMode.SMALLWEBRTC.value,
        user_id=user.id,
        definition_id=publiee.id,
    )
    llm = ContextCapturingMockLLM(mock_steps=[_texte("Très bien.")], chunk_delay=0.001)
    await _appeler((run, user, workflow), llm, ["Bonjour"])
    # Le prompt de l'étape arrive au modèle comme consigne système (``system_prompt``).
    recu = llm.captured_contexts[0]
    systeme = str(recu["system_prompt"]) + str(recu["messages"])
    assert "<parcours_genere>" in systeme and "# Les étapes de l'appel" in systeme
    assert "→" not in systeme.split("<parcours_genere>", 1)[1].split("</parcours_genere>", 1)[0]
    assert "Tu es ici : Accueil" in systeme


@pytest.mark.asyncio
async def test_traversant_la_case_seule_enregistree_met_le_graphe_a_jour_et_eteinte_le_rend(
    db_session, async_session, test_client_factory
):
    user, workflow = await _agent_en_base(db_session, async_session)
    async with test_client_factory(user) as client:
        await _enregistrer(client, workflow.id, {"workflow_configurations": {"generer_schema_parcours": True}})
        allume = (await db_session.get_draft_version(workflow.id)).workflow_json
        assert "<parcours_genere>" in _prompt(allume, "global")
        await _enregistrer(client, workflow.id, {"workflow_configurations": {"generer_schema_parcours": False}})
    eteint = (await db_session.get_draft_version(workflow.id)).workflow_json
    assert _prompt(eteint, "global") == GLOBAL and _prompt(eteint, "demande") == "Note la demande."


GREFFIER_AVEC_PORTES = {**CONFIG_ALLUMEE, CLE_MODE: MODE_GREFFIER, CLE_PORTES_DANS_LA_REPONSE: True}


@pytest.mark.asyncio
async def test_traversant_C4_greffier_avec_portes_carte_sans_tu_es_ici(
    db_session, async_session, test_client_factory
):
    """C4 par la vraie route : greffier avec portes, la carte des rôles est écrite et aucun
    « Tu es ici » (le bloc de fin d'étape le dit pendant l'appel). Le graphe seul, enregistré
    ensuite, suit la configuration enregistrée ; passer en mode outil remet la position."""
    user, workflow = await _agent_en_base(db_session, async_session)
    async with test_client_factory(user) as client:
        await _enregistrer(
            client, workflow.id, {"workflow_configurations": {**GREFFIER_AVEC_PORTES, "generer_schema_parcours": True}}
        )
        await _enregistrer(client, workflow.id, {"workflow_definition": _definition()})
        greffier = (await db_session.get_draft_version(workflow.id)).workflow_json
        assert "# Les étapes de l'appel" in _prompt(greffier, "global")
        assert "<position_generee>" not in _prompt(greffier, "start")
        await _enregistrer(
            client,
            workflow.id,
            {"workflow_configurations": {**GREFFIER_AVEC_PORTES, CLE_MODE: "outil", CLE_PORTES_DANS_LA_REPONSE: False, "generer_schema_parcours": True}},
        )
    outil = (await db_session.get_draft_version(workflow.id)).workflow_json
    assert _prompt(outil, "start").endswith("<position_generee>Tu es ici : Accueil</position_generee>")
    assert _prompt(outil, "global").count("<parcours_genere>") == 1


@pytest.mark.asyncio
async def test_traversant_une_configuration_envoyee_fait_foi(db_session, async_session, test_client_factory):
    """Revue du 15/10 : une configuration envoyée REMPLACE l'enregistrée. Envoyer la case du
    schéma seule éteint donc la fiche pendant l'appel : « Tu es ici » doit être écrit, jamais
    retiré sur la foi d'un mode qui n'existe plus."""
    user, workflow = await _agent_en_base(db_session, async_session)
    async with test_client_factory(user) as client:
        await _enregistrer(
            client, workflow.id, {"workflow_configurations": {**GREFFIER_AVEC_PORTES, "generer_schema_parcours": True}}
        )
        await _enregistrer(client, workflow.id, {"workflow_configurations": {"generer_schema_parcours": True}})
    brouillon = await db_session.get_draft_version(workflow.id)
    assert "fiche_mode_de_note" not in (brouillon.workflow_configurations or {})
    assert _prompt(brouillon.workflow_json, "start").endswith("<position_generee>Tu es ici : Accueil</position_generee>")


@pytest.mark.asyncio
async def test_traversant_case_jamais_allumee_l_enregistrement_est_identique(
    db_session, async_session, test_client_factory
):
    user, workflow = await _agent_en_base(db_session, async_session)
    async with test_client_factory(user) as client:
        await _enregistrer(client, workflow.id, {"workflow_definition": _definition()})
    enregistre = (await db_session.get_draft_version(workflow.id)).workflow_json
    assert [n["data"].get("prompt") for n in enregistre["nodes"]] == [
        n["data"].get("prompt") for n in _definition()["nodes"]
    ]


# --- L'autre chemin d'enregistrement : l'outil MCP ``save_workflow`` ------------

CODE_MCP = '''import { Workflow } from "@dograh/sdk";
import { startCall, endCall } from "@dograh/sdk/typed";

const wf = new Workflow({ name: "Parcours" });

const accueil = wf.addTyped(startCall({ name: "Accueil", prompt: "Comprends la demande." }));
const fin = wf.addTyped(endCall({ name: "Fin", prompt: "Termine l'appel poliment." }));

wf.edge(accueil, fin, { label: "End Call", condition: "Quand l'appelant veut raccrocher." });
'''


@pytest.mark.asyncio
@pytest.mark.skipif(__import__("shutil").which("node") is None, reason="node absent")
async def test_traversant_l_outil_mcp_ecrit_aussi_le_parcours(db_session, async_session):
    """On modifie les agents depuis Claude Code par l'outil MCP : il n'emprunte pas
    la route de l'écran. Case allumée, ses enregistrements portent aussi les blocs."""
    from unittest.mock import AsyncMock, patch

    from api.mcp_server.tools.save_workflow import save_workflow

    user, workflow = await _agent_en_base(db_session, async_session)
    await db_session.save_workflow_draft(
        workflow.id, workflow_definition=_definition(), workflow_configurations={"generer_schema_parcours": True}
    )
    with patch(
        "api.mcp_server.tools.save_workflow.authenticate_mcp_request", AsyncMock(return_value=user)
    ):
        resultat = await save_workflow(workflow_id=workflow.id, code=CODE_MCP)
    assert resultat["saved"] is True, resultat
    enregistre = (await db_session.get_draft_version(workflow.id)).workflow_json
    accueil = next(n for n in enregistre["nodes"] if n["type"] == "startCall")
    assert accueil["data"]["prompt"].endswith("<position_generee>Tu es ici : Accueil</position_generee>")


# --- Traversant : l'accueil lit en base les outils de passation de son graphe -----


@pytest.mark.asyncio
async def test_traversant_l_accueil_ecrit_ses_collegues_depuis_les_outils_en_base(
    db_session, async_session, test_client_factory
):
    """La vraie route : un accueil (``agents_specialises``) dont l'étape porte un outil de
    passation ``transfer_agent`` (nom et description lus en base) et un outil d'une autre
    catégorie (ignoré) ; la case est éteinte et le bloc est écrit quand même (forcé allumé)."""
    from api.enums import ToolCategory

    user, workflow = await _agent_en_base(db_session, async_session)
    org = user.selected_organization_id
    passation = await db_session.create_tool(
        organization_id=org,
        user_id=user.id,
        name="Outil A",
        description="Passe l'appel\nà l'agent a.",
        category=ToolCategory.TRANSFER_AGENT.value,
        definition={
            "schema_version": 1,
            "type": "transfer_agent",
            "config": {"workflow_id": workflow.id + 1000, "message": "", "play_greeting": False},
        },
    )
    autre = await db_session.create_tool(
        organization_id=org,
        user_id=user.id,
        name="Outil C",
        description="Ne doit pas apparaître.",
        category=ToolCategory.HTTP_API.value,
        definition={"schema_version": 1, "type": "http_api", "config": {"method": "GET", "url": "https://example.com"}},
    )
    definition = _definition()
    definition["nodes"][1]["data"]["tool_uuids"] = [passation.tool_uuid, autre.tool_uuid]
    reglages = {"agents_specialises": [workflow.id + 1000], "generer_schema_parcours": False}
    async with test_client_factory(user) as client:
        await _enregistrer(client, workflow.id, {"workflow_definition": definition, "workflow_configurations": reglages})
        # Le graphe seul, ensuite : les réglages enregistrés disent encore « accueil ».
        await _enregistrer(client, workflow.id, {"workflow_definition": definition})
    global_ = _prompt((await db_session.get_draft_version(workflow.id)).workflow_json, "global")
    assert global_.count("<parcours_genere>") == 1
    assert "# Ton équipe\nTu es l'accueil." in global_
    assert "Tes collègues :\n- outil_a : Passe l'appel à l'agent a.\n\n# Tes étapes" in global_
    assert "outil_c" not in global_ and "Ne doit pas apparaître" not in global_


@pytest.mark.asyncio
async def test_traversant_le_specialiste_recoit_son_bloc_equipe_case_eteinte(
    db_session, async_session, test_client_factory
):
    user, workflow = await _agent_en_base(db_session, async_session)
    definition = _definition_specialiste()
    async with test_client_factory(user) as client:
        await _enregistrer(
            client,
            workflow.id,
            {"workflow_definition": definition, "workflow_configurations": {"agent_principal_id": workflow.id + 1000}},
        )
    global_ = _prompt((await db_session.get_draft_version(workflow.id)).workflow_json, "global")
    assert "Tu es un spécialiste de la mission a." in global_
    assert "tu écris la sortie Demande" in global_ and "# Tes étapes" in global_

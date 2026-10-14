"""[.mark] Le parcours lisible (chantier repliques-coupees, lot 4 ter, D11 à D15 du 14/10).

Plan `Labo-agent-vocal/plans/repliques-coupees/`, liste `verification-allegement.md`. Case
``parcours_lisible`` (greffier, portes dans la réponse), éteinte par défaut :

- la carte du global ne garde que les étapes et leur rôle (la ligne sous « # Ta mission ici »),
  sans portes ni « → » ; plus de « Tu es ici » à part ;
- chaque étape finit par un seul bloc : où l'on est, la règle, puis chaque sortie avec sa
  condition et sa phrase d'arrivée dessous ; « (vers l'étape X) » seulement si le nom diffère ;
- le bloc de prise de notes disparaît.

| Test | Ce qu'il prouve |
|---|---|
| réglage | allumée seulement en greffier avec les portes dans la réponse |
| éteinte | carte, position, portes, prise de notes : identiques à l'octet à une configuration sans la clé |
| carte | une ligne par étape dans l'ordre de l'appel, le rôle lu sous « # Ta mission ici », ni porte ni flèche |
| bloc de fin d'étape (vrai ``_prepare_node``) | où l'on est, la règle, chaque sortie et sa phrase d'arrivée ; nom = étape sans redite ; plus de prise de notes |
| clavier (R1) | par les vraies routes, case allumée : la ligne « → » écrite par le modèle fait changer d'étape |
"""

import copy
from unittest.mock import patch

import pytest

from api.services.pipecat import greffier as module_greffier
from api.services.workflow import schema_du_parcours as schema
from api.services.workflow.dto import ReactFlowDTO
from api.services.workflow.fiche_au_fil_de_leau import (
    CLE_MODE,
    CLE_PARCOURS_LISIBLE,
    CLE_PORTES_DANS_LA_REPONSE,
    DEBUT_PRISE_DE_NOTES,
    MODE_GREFFIER,
    MODE_POST_SCRIPTUM,
    ReglagesFiche,
)
from api.services.workflow.pipecat_engine import PipecatEngine
from api.services.workflow.workflow_graph import WorkflowGraph
from api.tests.mark.test_clavier_porte_la_fiche import FICHE, _monter
from api.tests.mark.test_fiche_montree import _contexte, _mistral
from api.tests.mark.test_greffier import _Modele
from api.tests.mark.test_greffier_portes import TOUR_1
from api.tests.mark.test_outil_noter import CONFIG_ALLUMEE
from api.tests.mark.test_porte_parlee_premiere_replique import (
    _definition_a_trois_etapes,
    _noeud,
)
from api.tests.mark.test_portes_souples import _messages

GREFFIER = {**CONFIG_ALLUMEE, CLE_MODE: MODE_GREFFIER, CLE_PORTES_DANS_LA_REPONSE: True}
LISIBLE = {**GREFFIER, CLE_PARCOURS_LISIBLE: True}


def _definition() -> dict:
    """Start → Etape (porte nommée comme l'étape) → End (porte nommée autrement)."""
    definition = copy.deepcopy(_definition_a_trois_etapes())
    definition["nodes"].append(
        {
            "id": "global",
            "type": "globalNode",
            "position": {"x": 0, "y": -200},
            "data": {"name": "Global", "prompt": "Tu es l'agent d'accueil."},
        }
    )
    _noeud(definition, "start")["data"]["prompt"] = (
        "# Ta mission ici\nComprendre la demande.\n\n# Ce que tu dis\nTu écoutes."
    )
    etape = _noeud(definition, "etape")["data"]
    etape["prompt"] = (
        "# Ta mission ici\nappareil, marque, ce qui se passe\n\n# Ce que tu dis\nTu demandes."
    )
    etape["premiere_replique"] = "« Quelle est la marque ? »"
    for arete in definition["edges"]:
        if arete["id"] == "start-etape":
            arete["data"] = {
                "label": "Etape",
                "condition": "La personne décrit une panne.",
            }
    return definition


async def _systeme(config: dict, etape: str = "etape") -> str:
    """Ce que le vrai ``_prepare_node`` donne au modèle comme prompt système."""
    definition = schema.appliquer(
        _definition(), True, config.get(CLE_PARCOURS_LISIBLE) is True
    )
    graphe = WorkflowGraph(ReactFlowDTO.model_validate(definition))
    engine = PipecatEngine(
        llm=_mistral(),
        context=_contexte(),
        workflow=graphe,
        call_context_vars={},
        workflow_run_id=1,
        fiche=ReglagesFiche.depuis(config),
    )
    agent = engine.active_agent
    await engine._prepare_node(agent, graphe.nodes[etape], apply_settings=False)
    return agent.system_prompt


# --------------------------------------------------------------------------- #
# 1. Le réglage
# --------------------------------------------------------------------------- #


def test_la_case_ne_s_allume_qu_en_greffier_avec_les_portes():
    assert ReglagesFiche.depuis(LISIBLE).parcours_lisible is True
    assert ReglagesFiche.depuis(GREFFIER).parcours_lisible is False
    sans_portes = {**LISIBLE, CLE_PORTES_DANS_LA_REPONSE: False}
    assert ReglagesFiche.depuis(sans_portes).parcours_lisible is False
    postscript = {**LISIBLE, CLE_MODE: MODE_POST_SCRIPTUM}
    assert ReglagesFiche.depuis(postscript).parcours_lisible is False


# --------------------------------------------------------------------------- #
# 2. Éteinte : rien ne change
# --------------------------------------------------------------------------- #


def test_eteinte_la_carte_et_la_position_sont_celles_d_avant():
    assert schema.appliquer(_definition(), True, False) == schema.appliquer(
        _definition(), True
    )


@pytest.mark.asyncio
async def test_eteinte_le_prompt_de_l_etape_est_celui_d_avant():
    sans_cle = await _systeme(GREFFIER)
    eteinte = await _systeme({**GREFFIER, CLE_PARCOURS_LISIBLE: False})
    assert eteinte == sans_cle
    assert DEBUT_PRISE_DE_NOTES in sans_cle
    assert "# Les portes de cette étape" in sans_cle


# --------------------------------------------------------------------------- #
# 3. La carte
# --------------------------------------------------------------------------- #


def test_la_carte_liste_les_etapes_et_leur_role_sans_portes():
    definition = schema.appliquer(_definition(), True, True)
    globale = next(n for n in definition["nodes"] if n["type"] == "globalNode")
    carte = globale["data"]["prompt"].split(schema.DEBUT_PARCOURS, 1)[1]
    carte = carte.split(schema.FIN_PARCOURS, 1)[0].strip()
    # Dans l'ordre d'un appel : la fin est atteinte aussi depuis l'accueil, elle vient avant.
    depart = _noeud(definition, "start")["data"]["name"]
    assert carte.splitlines() == [
        "# Les étapes de l'appel",
        f"{depart} : Comprendre la demande",
        _noeud(definition, "end")["data"]["name"],
        "Etape : appareil, marque, ce qui se passe",
    ]
    assert "→" not in carte
    assert all(
        schema.DEBUT_POSITION not in (n["data"].get("prompt") or "")
        for n in definition["nodes"]
    )


def test_la_carte_se_regenere_sans_s_empiler():
    une = schema.appliquer(_definition(), True, True)
    deux = schema.appliquer(une, True, True)
    assert deux == une
    # Et revenir en arrière rend la carte d'avant.
    assert schema.appliquer(une, True, False) == schema.appliquer(_definition(), True)


# --------------------------------------------------------------------------- #
# 4. Le bloc de fin d'étape
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_le_bloc_de_fin_d_etape_dit_ou_l_on_est_et_chaque_sortie():
    systeme = await _systeme(LISIBLE)
    bloc = systeme[systeme.index("# Tu es à l'étape : Etape") :]
    assert "« → » et le nom de la sortie" in bloc
    assert "Dès qu'une condition est remplie, tu passes dans cette réponse." in bloc
    fin = _noeud(_definition(), "end")["data"]["name"]
    assert f"- vers_fin (vers l'étape {fin}), quand Quand c'est fini." in bloc
    assert "  Phrase d'arrivée : " in bloc
    # Plus de prise de notes, plus d'ancien bloc, plus de « Tu es ici » à part.
    assert DEBUT_PRISE_DE_NOTES not in systeme
    assert "# Les portes de cette étape" not in systeme
    assert "# La première réplique" not in systeme
    assert schema.DEBUT_POSITION not in systeme


@pytest.mark.asyncio
async def test_une_porte_nommee_comme_son_etape_n_est_pas_redite():
    systeme = await _systeme(LISIBLE, etape="start")
    assert (
        "- etape, quand La personne décrit une panne.\n  Phrase d'arrivée : « Quelle est la marque ? »"
        in systeme
    )
    assert "(vers l'étape Etape)" not in systeme


@pytest.mark.asyncio
async def test_le_parcours_lisible_est_plus_court():
    avant, apres = await _systeme(GREFFIER), await _systeme(LISIBLE)
    assert len(apres) < len(avant)


# --------------------------------------------------------------------------- #
# 5. Au clavier, par les vraies routes (R1)
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_au_clavier_case_allumee_la_ligne_de_porte_change_d_etape(
    db_session, async_session, test_client_factory
):
    from api.tests.mark.test_porte_parlee_consigne import (
        _definition as definition_ecran,
    )

    config = {
        **FICHE,
        CLE_MODE: MODE_GREFFIER,
        CLE_PORTES_DANS_LA_REPONSE: True,
        CLE_PARCOURS_LISIBLE: True,
    }
    user, workflow = await _monter(
        db_session, async_session, config, definition_ecran()
    )
    with patch.object(
        module_greffier,
        "service_du_greffier",
        return_value=(_Modele({}), {"provider": "mistral", "model": "m"}),
    ):
        charge = await _messages(test_client_factory, user, workflow, [TOUR_1])
    assert charge["checkpoint"]["current_node_id"] == "etape", charge["checkpoint"]

"""[.mark] La consigne des portes et les portes retirées des fonctions (plan porte-parlee, lot 3).

Plan `Labo-agent-vocal/plans/porte-parlee/`, D4, D5, D11 : case allumée, les portes ne sont plus
offertes comme fonctions ; le code les liste après la consigne du post-scriptum (``nom → étape :
condition``), puis une fois les premières répliques de toutes les étapes où mène une porte.

Joué par le vrai ``_prepare_node`` du moteur (ce qui part au modèle : prompt système et outils).

| Test | Ce qu'il prouve |
|---|---|
| éteinte | case éteinte en Postscript : prompt et outils identiques à ceux d'une configuration sans la clé, sur le code de la branche (portes en fonctions). ⚠️ La preuve « identique à la production » est le rejeu 861-904, pas ce test |
| allumée | aucune fonction de porte ; les autres outils restent ; bloc après la consigne du post-scriptum |
| contenu | les portes de l'étape, la phrase D11, les premières répliques rendues avec les variables, la ligne générique D3 |
| accueil | l'accueil a le bloc (ses portes coûtaient deux ou trois passes) |
| fin | une étape de fin n'a ni bloc ni fonction de porte |
| hors fiche | sans la fiche ou dans un autre mode, rien ne change |
| vocabulaire | le bloc n'est fait que du gabarit fixe et de ce que donne le graphe : aucun autre texte n'y entre. L'absence de mot de métier dans le gabarit lui-même se relit (`CONSIGNE_DES_PORTES`), ce test ne la prouve pas |
"""

import copy

import pytest

from api.services.workflow.dto import ReactFlowDTO
from api.services.workflow.fiche_au_fil_de_leau import (
    CLE_MODE,
    CLE_PORTES_DANS_LA_REPONSE,
    FIN_PRISE_DE_NOTES,
    MODE_OUTIL,
    MODE_POST_SCRIPTUM,
    ReglagesFiche,
)
from api.services.workflow.pipecat_engine import PipecatEngine
from api.services.workflow.porte_parlee import (
    CONSIGNE_DES_PORTES,
    SANS_PREMIERE_REPLIQUE,
    consigne_des_portes,
)
from api.services.workflow.workflow_graph import WorkflowGraph
from api.tests.mark.test_fiche_montree import _contexte, _mistral
from api.tests.mark.test_outil_noter import CONFIG_ALLUMEE
from api.tests.mark.test_porte_parlee_premiere_replique import (
    _definition_a_trois_etapes,
    _noeud,
)

PHRASE_D11 = "tu ne poses jamais la question de l'étape suivante sans prendre sa porte"


def _definition() -> dict:
    """Accueil → Etape → End, accueil → End ; une première réplique avec variable sur
    l'étape, aucune sur la fin ; un outil de recherche sur l'étape."""
    definition = _definition_a_trois_etapes()
    etape = _noeud(definition, "etape")["data"]
    etape["premiere_replique"] = "Bienvenue chez {{magasin}}, quelle marque ?"
    etape["document_uuids"] = ["doc-1"]
    return definition


def _graphe(definition: dict | None = None) -> WorkflowGraph:
    return WorkflowGraph(ReactFlowDTO.model_validate(definition or _definition()))


def _reglages(mode: str | None, portes: bool) -> ReglagesFiche | None:
    if mode is None:
        return None
    return ReglagesFiche.depuis(
        {**CONFIG_ALLUMEE, CLE_MODE: mode, CLE_PORTES_DANS_LA_REPONSE: portes}
    )


async def _requete(etape: str, mode: str | None, portes: bool, graphe=None):
    """Ce que le vrai ``_prepare_node`` donne au modèle : (prompt, noms des outils)."""
    graphe = graphe or _graphe()
    engine = PipecatEngine(
        llm=_mistral(),
        context=_contexte(),
        workflow=graphe,
        call_context_vars={"magasin": "Le Comptoir"},
        workflow_run_id=1,
        fiche=_reglages(mode, portes),
    )
    agent = engine.active_agent
    await engine._prepare_node(agent, graphe.nodes[etape], apply_settings=False)
    noms = [outil.name for outil in agent.tools.standard_tools]
    return agent.system_prompt, noms


# --------------------------------------------------------------------------- #
# 1. Éteinte : rien ne change
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
@pytest.mark.parametrize("etape", ["start", "etape", "end"])
async def test_case_eteinte_la_requete_est_celle_d_aujourd_hui(etape):
    """Même requête qu'une configuration sans la clé, sur le code de la branche. La preuve
    « identique à la production » est le rejeu 861-904 (revue du 05/10)."""
    graphe = _graphe()
    avant = PipecatEngine(
        llm=_mistral(),
        context=_contexte(),
        workflow=graphe,
        call_context_vars={"magasin": "Le Comptoir"},
        workflow_run_id=1,
        fiche=ReglagesFiche.depuis({**CONFIG_ALLUMEE, CLE_MODE: MODE_POST_SCRIPTUM}),
    )
    await avant._prepare_node(
        avant.active_agent, graphe.nodes[etape], apply_settings=False
    )
    prompt, noms = await _requete(etape, MODE_POST_SCRIPTUM, False)
    assert prompt == avant.active_agent.system_prompt
    assert noms == [o.name for o in avant.active_agent.tools.standard_tools]
    assert "# Les portes de cette étape" not in prompt


@pytest.mark.asyncio
async def test_case_eteinte_les_portes_restent_des_fonctions():
    _, noms = await _requete("etape", MODE_POST_SCRIPTUM, False)
    assert "vers_fin" in noms


# --------------------------------------------------------------------------- #
# 2. Allumée : les portes passent dans la consigne
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_case_allumee_aucune_fonction_de_porte_les_autres_outils_restent():
    _, noms = await _requete("etape", MODE_POST_SCRIPTUM, True)
    assert "vers_fin" not in noms
    assert "retrieve_from_knowledge_base" in noms


@pytest.mark.asyncio
async def test_case_allumee_le_bloc_suit_la_consigne_du_post_scriptum():
    prompt, _ = await _requete("etape", MODE_POST_SCRIPTUM, True)
    eteinte, _ = await _requete("etape", MODE_POST_SCRIPTUM, False)
    assert prompt.startswith(eteinte)
    assert eteinte.rstrip().endswith(FIN_PRISE_DE_NOTES)
    bloc = prompt[len(eteinte) :].strip()
    assert bloc.startswith("# Les portes de cette étape")
    assert prompt.count("# Les portes de cette étape") == 1


@pytest.mark.asyncio
async def test_le_bloc_porte_les_portes_de_l_etape_et_les_premieres_repliques():
    prompt, _ = await _requete("etape", MODE_POST_SCRIPTUM, True)
    assert "- vers_fin → étape End : Quand c'est fini." in prompt
    # Seulement les portes de l'étape en cours.
    assert "- vers_etape →" not in prompt
    assert PHRASE_D11 in prompt
    # La première réplique des seules étapes d'arrivée (D21) : ici la ligne générique de
    # End ; celle d'Etape, où cette étape ne mène pas, n'y est jamais.
    assert f"- End : {SANS_PREMIERE_REPLIQUE}" in prompt
    assert "Bienvenue chez" not in prompt


@pytest.mark.asyncio
async def test_d21_seules_les_premieres_repliques_des_etapes_d_arrivee():
    """Une première réplique peut porter ce que l'agent ne doit pas avoir sous les yeux
    ailleurs (l'adresse du magasin) : elle n'apparaît que là où une porte y mène."""
    accueil, _ = await _requete("start", MODE_POST_SCRIPTUM, True)
    # Rendue avec les variables de l'appel, depuis l'accueil qui y mène.
    assert "- Etape : Bienvenue chez Le Comptoir, quelle marque ?" in accueil
    assert f"- End : {SANS_PREMIERE_REPLIQUE}" in accueil
    assert "{{magasin}}" not in accueil
    etape, _ = await _requete("etape", MODE_POST_SCRIPTUM, True)
    assert "Le Comptoir" not in etape


@pytest.mark.asyncio
async def test_l_accueil_a_le_bloc_et_aucune_fonction_de_porte():
    prompt, noms = await _requete("start", MODE_POST_SCRIPTUM, True)
    assert "- vers_etape → étape Etape : Quand il faut." in prompt
    assert "- fin → étape End : Quand c'est fini." in prompt
    assert not {"vers_etape", "fin"} & set(noms)


@pytest.mark.asyncio
async def test_une_etape_de_fin_n_a_ni_bloc_ni_porte():
    prompt, _ = await _requete("end", MODE_POST_SCRIPTUM, True)
    assert "# Les portes de cette étape" not in prompt


# --------------------------------------------------------------------------- #
# 3. Hors Postscript, ou sans fiche : rien
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", [None, MODE_OUTIL])
async def test_hors_post_scriptum_la_case_ecrite_a_la_main_ne_change_rien(mode):
    prompt, noms = await _requete("etape", mode, True)
    assert "# Les portes de cette étape" not in prompt
    assert "vers_fin" in noms


# --------------------------------------------------------------------------- #
# 4. Zéro vocabulaire métier
# --------------------------------------------------------------------------- #


def test_hors_du_graphe_le_bloc_est_fixe():
    graphe = _graphe()
    bloc = consigne_des_portes(graphe.nodes["etape"], graphe, lambda texte: texte)
    assert bloc == CONSIGNE_DES_PORTES.format(
        portes="- vers_fin → étape End : Quand c'est fini.",
        premieres=f"- End : {SANS_PREMIERE_REPLIQUE}",
    )
    # Une étape d'arrivée n'apparaît qu'une fois, même atteinte par plusieurs portes.
    accueil = consigne_des_portes(graphe.nodes["start"], graphe, lambda texte: texte)
    assert accueil.count("- End :") == 1
    assert consigne_des_portes(graphe.nodes["end"], graphe, str) is None


def test_une_accolade_dans_une_premiere_replique_ne_casse_rien():
    definition = copy.deepcopy(_definition())
    _noeud(definition, "etape")["data"]["premiere_replique"] = "Code {x} ?"
    graphe = _graphe(definition)
    bloc = consigne_des_portes(graphe.nodes["start"], graphe, lambda texte: texte)
    assert "- Etape : Code {x} ?" in bloc

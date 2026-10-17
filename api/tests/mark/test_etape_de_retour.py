"""[.mark] Lot 2 d'orchestrateur-trois-cerveaux (D1, D2) : l'étape de retour de l'accueil.

Plan `Labo-agent-vocal/plans/orchestrateur-trois-cerveaux/` (lot 2). Quand un collègue rend la main,
le code ramène l'appel sur une étape de l'accueil faite pour ça (le marqueur ``etape_de_retour``),
et non plus sur l'étape de départ. Ces tests passent par le VRAI moteur et le VRAI coordinateur de
passation (le banc fendu de `test_agent_transfer.py`) ; seuls les modèles, la voix et la base sont
remplacés. Ils ne demandent ni Postgres ni Redis.

| Test | Ce qu'il prouve |
|---|---|
| graphe | l'étape de retour est valide sans arête entrante ; une autre étape sans arête entrante reste refusée |
| choix | graphe avec étape de retour : l'accueil reprend dessus, note de retour dans son prompt ; sans étape de retour : étape de départ, prompt inchangé ; prompt « à rédiger » : étape de départ |
| demande | le retour du collègue demande l'étape de retour ; une passation ordinaire non |
| agent seul | hors d'un groupe, aucune note, aucune étape de retour choisie |
| porte réécrite | une porte mal écrite n'est jamais réécrite vers l'étape de retour de l'accueil |
| ouverture | l'ouverture de l'agent appelé se fait sur l'étape préparée, pas sur l'étape de départ |
"""

import pytest

from api.services.groupe.passations import (
    A_REDIGER,
    MARQUEUR_ETAPE_DE_RETOUR,
    est_une_etape_de_retour,
    est_une_etape_de_retour_de_l_accueil,
    etape_de_retour_du_graphe,
    porte_reecrite_vers_le_retour,
)
from api.services.workflow.agent_transfer import TransferRequest
from api.services.workflow.dto import (
    AgentNodeData,
    EdgeDataDTO,
    EndCallNodeData,
    Position,
    ReactFlowDTO,
    RFEdgeDTO,
    RFNodeDTO,
    StartCallNodeData,
)
from api.services.workflow.fiche_au_fil_de_leau import ReglagesFiche
from api.services.workflow.workflow_graph import WorkflowGraph
from api.tests.mark.test_passation_rapide_groupe import _monter_groupe, _passer
from api.tests.test_agent_transfer import (
    DESTINATION_WORKFLOW_ID,
    TransferHarness,
    build_agent_workflow,
)
from pipecat.tests import MockLLMService

PRINCIPAL = DESTINATION_WORKFLOW_ID  # l'accueil, ici l'agent construit à la passation
COLLEGUE = 1  # l'agent qui rend la main (le premier agent du banc)


def _noeud(identifiant: str, type_: str, nom: str, prompt: str, **donnees):
    classe = {"startCall": StartCallNodeData, "endCall": EndCallNodeData}.get(type_, AgentNodeData)
    base = dict(name=nom, prompt=prompt, allow_interrupt=False, add_global_prompt=False)
    if type_ == "startCall":
        base["is_start"] = True
    if type_ == "endCall":
        base["is_end"] = True
    return RFNodeDTO(
        id=identifiant,
        type=type_,
        position=Position(x=0, y=0),
        data=classe(**{**base, **donnees}),
    )


def _arete(source: str, cible: str, nom: str):
    return RFEdgeDTO(
        id=f"{source}-{cible}",
        source=source,
        target=cible,
        data=EdgeDataDTO(label=nom, condition=f"Quand {nom}."),
    )


def graphe_de_l_accueil(*, avec_retour: bool = True, prompt_retour: str = "Reprends la main.") -> WorkflowGraph:
    """L'accueil : une étape de départ, une fin, et (au choix) l'étape de retour, sans arête entrante."""
    noeuds = [
        _noeud("accueil", "startCall", "Accueil", "Tu accueilles."),
        _noeud("fin", "endCall", "Fin", "Tu remercies."),
    ]
    aretes = [_arete("accueil", "fin", "Fin")]
    if avec_retour:
        noeuds.append(
            _noeud("retour", "agentNode", "Reprise", prompt_retour, **{MARQUEUR_ETAPE_DE_RETOUR: True})
        )
        aretes.append(_arete("retour", "fin", "Fin"))
    return WorkflowGraph(ReactFlowDTO(nodes=noeuds, edges=aretes))


FICHE_REGLAGES = {
    "fiche_au_fil_de_leau": True,
    "fiche_champs": [
        {"nom": "nom", "origine": "dicte", "description": "Nom de famille"},
        {"nom": "objet", "origine": "dicte", "description": "Ce que la personne demande"},
        {"nom": "detail", "origine": "dicte", "description": "Un détail de la demande"},
    ],
}


async def _monter(accueil: WorkflowGraph, reglages: dict | None = None, *, fiche: bool = True):
    """Le banc fendu : le premier agent est le collègue (id 1), l'agent construit à la passation
    est l'accueil (id 99), dont on fournit le graphe. L'appel est un groupe."""
    harness = TransferHarness()
    await harness.build(
        source_llm=MockLLMService(mock_steps=[], chunk_delay=0.001),
        destination_llm=MockLLMService(mock_steps=[], chunk_delay=0.001),
        source_workflow=build_agent_workflow(name="Collegue", greeting="Je note."),
        destination_workflow=accueil,
    )
    engine = harness.engine
    groupe = {"agents_specialises": [COLLEGUE], **(reglages or {})}
    engine.reglages_appel = dict(groupe)
    engine.active_agent.reglages = {"agent_principal_id": PRINCIPAL}
    engine._get_organization_id = lambda: None  # jamais appelée ici
    if fiche:
        engine._fiche = ReglagesFiche.depuis(dict(FICHE_REGLAGES))
    # Le collègue a pris la main depuis l'accueil, a traversé deux étapes, noté un champ.
    engine._gathered_context.update(
        {
            "objet": "une fuite",
            "passations": [
                {"de": PRINCIPAL, "vers": COLLEGUE, "raison": "Passer à Support", "issue": "completed"}
            ],
            "parcours_etapes": [
                {"agent": "Accueil", "agent_id": PRINCIPAL, "etape": "Accueil"},
                {"agent": "Support", "agent_id": COLLEGUE, "etape": "Qualification"},
                {"agent": "Support", "agent_id": COLLEGUE, "etape": "Retour au principal"},
            ],
        }
    )
    await harness.start()
    return harness


def _retour(**options) -> dict:
    return dict(
        etape_de_retour=True,
        silencieuse=True,
        sans_resume=True,
        raison="retour",
        ouverture="si_l_appelant_attend",
        **options,
    )


# --------------------------------------------------------------------------- #
# Le graphe
# --------------------------------------------------------------------------- #


def test_l_etape_de_retour_est_valide_sans_arete_entrante():
    graphe = graphe_de_l_accueil()
    noeud = graphe.nodes["retour"]
    assert est_une_etape_de_retour_de_l_accueil(noeud)
    # Un marqueur distinct de celui du collègue : jamais confondus.
    assert not est_une_etape_de_retour(noeud)
    assert etape_de_retour_du_graphe(graphe) is noeud


def test_une_autre_etape_sans_arete_entrante_reste_refusee():
    noeuds = [
        _noeud("accueil", "startCall", "Accueil", "Tu accueilles."),
        _noeud("fin", "endCall", "Fin", "Tu remercies."),
        _noeud("seule", "agentNode", "Seule", "Je ne sers à rien."),
    ]
    with pytest.raises(Exception, match="at least 1 incoming"):
        WorkflowGraph(ReactFlowDTO(nodes=noeuds, edges=[_arete("accueil", "fin", "Fin")]))


def test_sans_etape_de_retour_ou_a_rediger_le_graphe_n_en_a_pas():
    assert etape_de_retour_du_graphe(graphe_de_l_accueil(avec_retour=False)) is None
    assert etape_de_retour_du_graphe(graphe_de_l_accueil(prompt_retour=A_REDIGER)) is None


def test_une_porte_mal_ecrite_n_est_jamais_reecrite_vers_l_etape_de_retour_de_l_accueil():
    graphe = graphe_de_l_accueil()
    depart = graphe.nodes["accueil"]
    # « reprise » est bien le nom d'une autre étape du graphe, mais l'accueil n'a aucune sortie vers
    # elle (aucune arête entrante) et le marqueur n'est pas celui du collègue.
    assert porte_reecrite_vers_le_retour(graphe, depart, "reprise") is None


# --------------------------------------------------------------------------- #
# Le choix de l'étape au retour (R1 : la vraie route de passation)
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_le_retour_arrive_sur_l_etape_de_retour_avec_sa_note():
    harness = await _monter(graphe_de_l_accueil())
    try:
        resultat = await _passer(harness, PRINCIPAL, **_retour())
        assert resultat["outcome"] == "completed"
        agent = harness.engine.active_agent
        assert agent.workflow_id == PRINCIPAL
        assert agent.current_node.id == "retour"
        prompt = agent.system_prompt
        assert prompt.startswith("Reprends la main.")
        assert "# Retour du collègue « Support »" in prompt
        assert "Motif de départ : Passer à Support" in prompt
        assert "Fait : étapes traversées : Qualification ; champs remplis : objet" in prompt
        assert "En attente : detail" in prompt
        assert "Déjà connu : objet" in prompt
        assert "L'appelant a une autre demande" in prompt
        # Jamais de crochets (le filtre agit sur ce que dit le modèle) ni de valeur de la fiche.
        assert "[" not in prompt.split("# Retour")[1]
        assert "une fuite" not in prompt
        # La note est dans le prompt système, jamais dans l'historique.
        assert all(
            "Retour du collègue" not in str(m.get("content"))
            for m in harness.engine.context.get_messages()
        )
    finally:
        await harness.stop()


@pytest.mark.asyncio
async def test_le_retour_ouvre_l_agent_sur_l_etape_preparee():
    harness = await _monter(graphe_de_l_accueil())
    try:
        await _passer(harness, PRINCIPAL, **_retour())
        # Ni l'étape de départ de l'accueil, ni son accueil dit : l'étape de retour est celle qui est
        # courante pour le moteur après l'ouverture.
        assert harness.engine.active_agent.current_node.id == "retour"
    finally:
        await harness.stop()


@pytest.mark.asyncio
async def test_sans_etape_de_retour_l_accueil_reprend_sur_son_etape_de_depart_comme_avant():
    harness = await _monter(graphe_de_l_accueil(avec_retour=False))
    try:
        await _passer(harness, PRINCIPAL, **_retour())
        agent = harness.engine.active_agent
        assert agent.current_node.id == "accueil"
        assert "Retour du collègue" not in agent.system_prompt
    finally:
        await harness.stop()


@pytest.mark.asyncio
async def test_une_etape_de_retour_encore_a_rediger_n_est_pas_choisie():
    harness = await _monter(graphe_de_l_accueil(prompt_retour=A_REDIGER))
    try:
        await _passer(harness, PRINCIPAL, **_retour())
        agent = harness.engine.active_agent
        assert agent.current_node.id == "accueil"
        assert A_REDIGER not in agent.system_prompt
    finally:
        await harness.stop()


@pytest.mark.asyncio
async def test_une_passation_ordinaire_ne_demande_pas_l_etape_de_retour():
    harness = await _monter(graphe_de_l_accueil())
    try:
        # Une passation « vers » l'accueil qui n'est pas un retour (pas de marque) : l'étape de départ.
        await _passer(harness, PRINCIPAL)
        assert harness.engine.active_agent.current_node.id == "accueil"
    finally:
        await harness.stop()


@pytest.mark.asyncio
async def test_hors_d_un_groupe_aucune_note_et_aucune_etape_de_retour_demandee():
    harness = await _monter_groupe(None)  # un agent SEUL : aucun réglage
    try:
        engine = harness.engine
        assert engine._note_de_passation(engine.active_agent, engine.active_agent.current_node) is None
        assert engine._retour_demande() is False
    finally:
        await harness.stop()


@pytest.mark.asyncio
async def test_le_retour_du_collegue_demande_l_etape_de_retour():
    """Le geste du code (``_rendre_au_principal``) marque sa demande : sans cela, l'accueil reprendrait
    sur son étape de départ."""
    harness = await _monter(graphe_de_l_accueil())
    try:
        engine = harness.engine
        demandes: list[TransferRequest] = []
        coordinateur = engine.transfer_coordinator
        coordinateur.accept = lambda demande: demandes.append(demande) or True
        coordinateur.start = lambda demande, **_: True
        assert engine._rendre_au_principal(engine.active_agent, PRINCIPAL) is True
        assert len(demandes) == 1
        assert demandes[0].etape_de_retour is True
        assert demandes[0].raison == "retour" and demandes[0].silencieuse
    finally:
        await harness.stop()

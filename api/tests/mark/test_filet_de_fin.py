"""[.mark] Lot 2 d'orchestrateur-trois-cerveaux (B2, D5) : le filet de fin d'appel d'un collègue.

Plan `Labo-agent-vocal/plans/orchestrateur-trois-cerveaux/` (lot 2). Un collègue qui dit « au revoir »
sans prendre aucune porte laisse l'appel pendre dans une étape sans issue. Case « End-of-call safety net »
allumée : le code prend lui-même la sortie « retour », l'accueil reçoit l'appel sur son étape de retour et
conclut. Ces tests passent par le VRAI moteur et le VRAI coordinateur de passation (banc fendu de
`test_agent_transfer.py`) ; seuls les modèles, la voix et la base sont remplacés. Ni Postgres ni Redis.

| Test | Ce qu'il prouve |
|---|---|
| formules | casse, accents et ponctuation ignorés ; mots entiers ; liste de l'organisation ou, à défaut, celle par défaut |
| la route (R1) | formule + aucune porte + case allumée : l'appel revient à l'accueil, qui prend sa sortie ``fin`` sans tour de modèle (correctifs-apres-banc-commun, K4 ; le détail dans `test_correctifs_passations.py`) ; trace ``porte_reecrite`` = ``filet_de_fin`` |
| rien à faire | pas de formule ; une porte déjà prise ; case éteinte ; agent non collègue ; étape sans sortie retour |
| formules de l'organisation | la phrase ``formules_de_fin`` du catalogue remplace la liste par défaut |
| branchement | l'agrégateur de l'assistant appelle le filet à la fin d'une réplique, avec l'état du début |
"""

import asyncio
from unittest.mock import AsyncMock

import pytest

from api.services.groupe.filet_de_fin import (
    FORMULES_PAR_DEFAUT,
    TRACE_FILET,
    brancher_le_filet_de_fin,
    contient_une_formule,
    filet_allume,
    formules_de,
)
from api.services.workflow.dto import ReactFlowDTO
from api.services.workflow.workflow_graph import WorkflowGraph
from api.tests.mark.test_etape_de_retour import (
    COLLEGUE,
    FICHE_REGLAGES,
    PRINCIPAL,
    _arete,
    _noeud,
    graphe_de_l_accueil,
)
from api.services.workflow.fiche_au_fil_de_leau import ReglagesFiche
from api.tests.test_agent_transfer import TransferHarness
from pipecat.tests import MockLLMService


def graphe_du_collegue(*, avec_retour: bool = True, avec_fin: bool = True, fins: list | None = None) -> WorkflowGraph:
    """Un collègue : une étape de départ avec deux sorties (rendre la main, clore). ``avec_fin`` faux : le collègue n'a que
    le retour (agent-facon-tala, C2 : le filet prend sa fin propre quand elle existe)."""
    noeuds = [_noeud("etape", "startCall", "Qualification", "Tu qualifies.")]
    aretes = []
    if avec_fin:
        noeuds.append(_noeud("fin", "endCall", "Fin", "Tu remercies.", **({"fins": fins} if fins else {})))
        aretes.append(_arete("etape", "fin", "Fin"))
    if avec_retour:
        noeuds.append(
            _noeud("retour", "agentNode", "Retour au principal", "Retour.", retour_au_principal=True)
        )
        aretes.append(_arete("etape", "retour", "Retour"))
    return WorkflowGraph(ReactFlowDTO(nodes=noeuds, edges=aretes))


# --------------------------------------------------------------------------- #
# Les formules
# --------------------------------------------------------------------------- #


def test_une_formule_se_trouve_sans_egard_a_la_casse_aux_accents_ni_a_la_ponctuation():
    formules = list(FORMULES_PAR_DEFAUT)
    assert contient_une_formule("Très bien, bonne journée !", formules)
    assert contient_une_formule("BONNE JOURNEE", formules)
    assert contient_une_formule("Je vous souhaite une bonne soirée.", formules)
    assert contient_une_formule("Alors, au revoir.", formules)
    assert contient_une_formule("Merci, au   revoir ;)", formules)


def test_une_formule_est_cherchee_en_mots_entiers_et_comme_un_tout():
    formules = list(FORMULES_PAR_DEFAUT)
    assert not contient_une_formule("Quelle est votre adresse ?", formules)
    assert not contient_une_formule("Je prends le revoir au pluriel", formules)  # « au » et « revoir » séparés
    assert not contient_une_formule("Avez-vous besoin d'autre chose ?", formules)
    assert not contient_une_formule("", formules) and not contient_une_formule(None, formules)
    assert not contient_une_formule("bonne journée", [])  # aucune formule, aucun filet
    assert not contient_une_formule("bonne journée", ["", "  "])


def test_les_formules_sont_celles_de_l_organisation_sinon_celles_par_defaut():
    assert formules_de({}) == list(FORMULES_PAR_DEFAUT) == ["au revoir", "bonne journée", "bonne soirée"]
    assert formules_de(None) == list(FORMULES_PAR_DEFAUT)
    assert formules_de({"formules_de_fin": "à bientôt\n\n  ciao  \n"}) == ["à bientôt", "ciao"]
    assert formules_de({"formules_de_fin": "   "}) == list(FORMULES_PAR_DEFAUT)
    assert formules_de({"formules_de_fin": 12}) == list(FORMULES_PAR_DEFAUT)


def test_la_phrase_du_catalogue_arrive_dans_le_contexte_de_l_appel_par_la_vraie_injection():
    """La route des formules : la fiche ``formules_de_fin`` du catalogue de l'organisation devient une
    variable du contexte de l'appel (``injecter_phrases``, au décroché), lue par le filet."""
    from api.schemas.phrases import CataloguePhrases, Phrase
    from api.services.etablissements.phrases import injecter_phrases

    catalogue = CataloguePhrases(
        phrases=[Phrase(variable="formules_de_fin", contenu="à bientôt\nciao", niveau="organisation")]
    )
    assert formules_de(injecter_phrases({}, catalogue, None)) == ["à bientôt", "ciao"]
    # Sans cette fiche dans le catalogue : la liste par défaut.
    assert formules_de(injecter_phrases({}, CataloguePhrases(), None)) == list(FORMULES_PAR_DEFAUT)


def test_la_case_n_existe_que_pour_un_collegue_et_est_eteinte_par_defaut():
    assert not filet_allume({}) and not filet_allume(None)
    assert not filet_allume({"filet_de_fin": True})  # l'accueil ou un agent seul : aucun filet
    assert not filet_allume({"agent_principal_id": 3})
    assert not filet_allume({"agent_principal_id": 3, "filet_de_fin": "oui"})
    assert filet_allume({"agent_principal_id": 3, "filet_de_fin": True})


# --------------------------------------------------------------------------- #
# La route : le collègue dit au revoir sans porte
# --------------------------------------------------------------------------- #


async def _monter(*, filet: bool = True, collegue: WorkflowGraph | None = None, contexte: dict | None = None):
    """Le collègue (id 1) parle ; l'accueil (id 99) est construit à la passation, avec son étape de
    retour. L'appel est un groupe, la fiche est allumée."""
    harness = TransferHarness()
    await harness.build(
        source_llm=MockLLMService(mock_steps=[], chunk_delay=0.001),
        destination_llm=MockLLMService(mock_steps=[], chunk_delay=0.001),
        source_workflow=collegue or graphe_du_collegue(avec_fin=False),
        destination_workflow=graphe_de_l_accueil(),
    )
    engine = harness.engine
    engine.reglages_appel = {"agents_specialises": [COLLEGUE]}
    engine.active_agent.workflow_name = "Support"
    engine.active_agent.reglages = {"agent_principal_id": PRINCIPAL, **({"filet_de_fin": True} if filet else {})}
    engine._fiche = ReglagesFiche.depuis(dict(FICHE_REGLAGES))
    engine._call_context_vars.update(contexte or {})
    engine._gathered_context.update(
        {
            "objet": "une fuite",
            "passations": [
                {"de": PRINCIPAL, "vers": COLLEGUE, "raison": "Passer à Support", "issue": "completed"}
            ],
            "parcours_etapes": [
                {"agent": "Accueil", "agent_id": PRINCIPAL, "etape": "Accueil"},
                {"agent": "Support", "agent_id": COLLEGUE, "etape": "Qualification"},
            ],
        }
    )
    await harness.start()
    # L'étape de départ du banc fendu est celle du graphe du collègue.
    await harness.engine.set_node("etape")
    return harness


async def _attendre_la_passation(harness):
    coordinateur = harness.engine.transfer_coordinator
    assert coordinateur.in_progress, "le filet aurait dû lancer le retour"
    await asyncio.wait_for(coordinateur._task, 20)
    return coordinateur.completed[-1]


@pytest.mark.asyncio
async def test_une_formule_de_fin_sans_porte_ramene_l_appel_a_l_accueil_qui_prend_sa_sortie_fin():
    harness = await _monter()
    try:
        engine = harness.engine
        # K4 : la sortie fin se prend sans tour de modèle (ni voix, ni téléphonie ici : on observe).
        engine.end_call_with_reason = AsyncMock()
        engine.queue_node_opening = AsyncMock()
        depart = engine.etat_pour_le_filet()
        assert await engine.filet_de_fin("Très bien, je vous souhaite une bonne journée.", depart) is True
        resultat = await _attendre_la_passation(harness)
        assert resultat["outcome"] == "completed" and resultat["destination_workflow_id"] == PRINCIPAL
        accueil = engine.active_agent
        assert accueil.workflow_id == PRINCIPAL and accueil.current_node.id == "fin"
        engine.queue_node_opening.assert_not_called()
        # La trace dit pourquoi, et la passation est celle du retour (silencieuse, du code).
        trace = engine._gathered_context["porte_reecrite"]
        assert [t["ecrite"] for t in trace] == [TRACE_FILET]
        assert trace[0]["etape"] == "Qualification" and trace[0]["vers"] == "Retour au principal"
        assert engine._gathered_context["passations"][-1]["raison"] == "retour"
    finally:
        await harness.stop()


@pytest.mark.asyncio
async def test_les_formules_de_l_organisation_remplacent_celles_par_defaut():
    harness = await _monter(contexte={"formules_de_fin": "à la prochaine"})
    try:
        engine = harness.engine
        engine.end_call_with_reason = AsyncMock()
        engine.queue_node_opening = AsyncMock()
        depart = engine.etat_pour_le_filet()
        # « au revoir » n'est plus une formule reconnue chez cette organisation.
        assert await engine.filet_de_fin("Alors au revoir.", depart) is False
        assert not engine.transfer_coordinator.in_progress
        assert await engine.filet_de_fin("Ok, à la prochaine !", depart) is True
        await _attendre_la_passation(harness)
        assert engine.active_agent.workflow_id == PRINCIPAL
    finally:
        await harness.stop()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "cas",
    ["pas de formule", "porte prise", "case éteinte", "pas de sortie retour", "réplique vide", "aucun état de départ"],
)
async def test_le_filet_ne_fait_rien_hors_de_son_cas(cas):
    harness = await _monter(
        filet=cas != "case éteinte",
        collegue=graphe_du_collegue(avec_retour=cas != "pas de sortie retour", avec_fin=False),
    )
    try:
        engine = harness.engine
        depart = engine.etat_pour_le_filet()
        texte = "Quelle est votre adresse ?" if cas == "pas de formule" else "Bonne journée !"
        if cas == "porte prise":
            depart = (depart[0], "une-autre-etape")  # l'étape a changé pendant la réplique
        if cas == "réplique vide":
            texte = "   "
        if cas == "aucun état de départ":
            depart = None
        assert await engine.filet_de_fin(texte, depart) is False
        assert not engine.transfer_coordinator.in_progress
        assert engine.active_agent.workflow_id == COLLEGUE
        assert "porte_reecrite" not in engine._gathered_context
    finally:
        await harness.stop()


@pytest.mark.asyncio
async def test_l_accueil_n_a_jamais_de_filet():
    """La case ne vaut que pour un collègue : le principal d'un groupe qui l'aurait cochée ne bouge pas."""
    harness = await _monter()
    try:
        engine = harness.engine
        engine.active_agent.reglages = {"filet_de_fin": True, "agents_specialises": [COLLEGUE]}
        assert await engine.filet_de_fin("Au revoir !", engine.etat_pour_le_filet()) is False
        assert not engine.transfer_coordinator.in_progress
    finally:
        await harness.stop()


# --------------------------------------------------------------------------- #
# Le branchement sur l'agrégateur de l'assistant (téléphone et clavier)
# --------------------------------------------------------------------------- #


class _Agregateur:
    """Garde les gestionnaires comme le fait ``event_handler`` de Pipecat."""

    def __init__(self):
        self.gestionnaires: dict[str, list] = {}

    def event_handler(self, nom):
        def poser(fonction):
            self.gestionnaires.setdefault(nom, []).append(fonction)
            return fonction

        return poser


class _Message:
    def __init__(self, content):
        self.content = content


class _Moteur:
    def __init__(self):
        self.etat = ("v", "etape")
        self.appels = []

    def etat_pour_le_filet(self):
        return self.etat

    async def filet_de_fin(self, texte, depart):
        self.appels.append((texte, depart))
        return True


@pytest.mark.asyncio
async def test_la_fin_d_une_replique_appelle_le_filet_avec_l_etat_du_debut():
    agregateur, moteur = _Agregateur(), _Moteur()
    brancher_le_filet_de_fin(moteur, agregateur)
    [debut] = agregateur.gestionnaires["on_assistant_turn_started"]
    [fin] = agregateur.gestionnaires["on_assistant_turn_stopped"]
    await debut(agregateur)
    moteur.etat = ("v", "une-autre-etape")  # une porte est prise pendant la réplique
    await fin(agregateur, _Message("Bonne journée"))
    assert moteur.appels == [("Bonne journée", ("v", "etape"))]
    # Une fin sans début (réplique coupée avant d'avoir commencé) : l'état est absent, le filet ne fait rien.
    await fin(agregateur, _Message("Au revoir"))
    assert moteur.appels[-1] == ("Au revoir", None)


@pytest.mark.asyncio
async def test_un_branchement_qui_echoue_ne_coute_jamais_l_appel():
    class _Casse:
        def event_handler(self, nom):
            raise RuntimeError("agrégateur inattendu")

    brancher_le_filet_de_fin(_Moteur(), _Casse())  # ne lève pas


# --------------------------------------------------------------------------- #
# agent-facon-tala, C2 : la sortie de fin du collègue, et un seul au revoir
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_c2_le_collegue_a_une_sortie_fin_le_filet_la_prend_au_lieu_du_retour():
    harness = await _monter(collegue=graphe_du_collegue())
    try:
        engine = harness.engine
        engine.end_call_with_reason = AsyncMock()
        engine.queue_node_opening = AsyncMock()
        depart = engine.etat_pour_le_filet()
        assert await engine.filet_de_fin("Très bien, bonne journée.", depart) is True
        for tache in list(engine._taches_de_porte):
            await asyncio.wait_for(tache, 5)
        # Pas de retour à l'accueil : le collègue clôt lui-même, l'appel raccroche.
        assert not engine.transfer_coordinator.in_progress and not engine.transfer_coordinator.completed
        assert engine.active_agent.workflow_id == COLLEGUE and engine.active_agent.current_node.id == "fin"
        engine.end_call_with_reason.assert_awaited_once()
        trace = engine._gathered_context["porte_reecrite"]
        assert [t["ecrite"] for t in trace] == [TRACE_FILET] and trace[0]["vers"] == "Fin"
    finally:
        await harness.stop()


@pytest.mark.asyncio
async def test_c2_la_fin_figee_du_collegue_n_est_pas_redite_apres_son_au_revoir():
    harness = await _monter(collegue=graphe_du_collegue(fins=[{"phrase": "Au revoir et merci."}]))
    try:
        engine = harness.engine
        engine.end_call_with_reason = AsyncMock()
        engine._dire_la_fin_figee = AsyncMock()
        depart = engine.etat_pour_le_filet()
        assert engine._phrase_de_fin_figee(engine.active_agent, "fin") is not None  # le nœud a bien une phrase figée
        assert await engine.filet_de_fin("Bonne journée !", depart) is True
        for tache in list(engine._taches_de_porte):
            await asyncio.wait_for(tache, 5)
        engine._dire_la_fin_figee.assert_not_called()
        engine.end_call_with_reason.assert_awaited_once()
    finally:
        await harness.stop()


@pytest.mark.asyncio
async def test_c2_une_porte_fin_ordinaire_dit_toujours_sa_fin_figee():
    harness = await _monter(collegue=graphe_du_collegue(fins=[{"phrase": "Au revoir et merci."}]))
    try:
        engine = harness.engine
        engine.end_call_with_reason = AsyncMock()
        engine._dire_la_fin_figee = AsyncMock()
        assert await engine.prendre_porte_ecrite("fin") == "prise"
        for tache in list(engine.__dict__.get("_taches_du_groupe", ())):
            await asyncio.wait_for(tache, 5)
        engine._dire_la_fin_figee.assert_called_once()
    finally:
        await harness.stop()


@pytest.mark.asyncio
async def test_c2_au_retour_filet_l_accueil_ne_redit_pas_sa_fin_figee_le_collegue_a_dit_au_revoir():
    accueil = graphe_de_l_accueil()
    accueil.nodes["fin"].data.fins = [{"phrase": "Au revoir et bonne journée."}]
    harness = TransferHarness()
    await harness.build(
        source_llm=MockLLMService(mock_steps=[], chunk_delay=0.001),
        destination_llm=MockLLMService(mock_steps=[], chunk_delay=0.001),
        source_workflow=graphe_du_collegue(avec_fin=False),
        destination_workflow=accueil,
    )
    try:
        engine = harness.engine
        engine.reglages_appel = {"agents_specialises": [COLLEGUE]}
        engine.active_agent.reglages = {"agent_principal_id": PRINCIPAL, "filet_de_fin": True}
        engine._fiche = ReglagesFiche.depuis(dict(FICHE_REGLAGES))
        await harness.start()
        await engine.set_node("etape")
        engine.end_call_with_reason = AsyncMock()
        engine._dire_la_fin_figee = AsyncMock()
        engine.queue_node_opening = AsyncMock()
        assert await engine.filet_de_fin("Bonne journée.", engine.etat_pour_le_filet()) is True
        await _attendre_la_passation(harness)
        for tache in list(engine._taches_de_porte) + list(engine.__dict__.get("_taches_du_groupe", ())):
            await asyncio.wait_for(tache, 5)
        assert engine.active_agent.workflow_id == PRINCIPAL and engine.active_agent.current_node.id == "fin"
        engine._dire_la_fin_figee.assert_not_called()
        engine.end_call_with_reason.assert_awaited_once()
    finally:
        await harness.stop()

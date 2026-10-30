"""[.mark] figeage-v12, lot A2 : D4 côté code (plan `Labo-agent-vocal/plans/figeage-v12/`, `lot-0-causes.md` § D4).

Cause prouvée : l'état de la fiche arrivait comme un message DE LA PERSONNE juste avant sa dernière parole ; le modèle (Small
3.2) redemandait ce que la fiche tenait déjà (16 cas sur 21). Posé à la fin de l'instruction système : 0 redemande sur 64.
Deux correctifs, deux cases, éteintes par défaut :

- case de l'agent ``fiche_dans_le_systeme`` : l'état est rangé en dernier dans l'instruction système du service, à chaque requête,
  par la trame ``LLMContextFrame`` (téléphone et clavier), avec l'API de composition de Pipecat : aucune famille de
  fournisseurs, aucun message ``system`` au milieu de la conversation ;
- moment du passage d'une étape de collecte ``attendre_a_chaque_tour`` : la requête attend (au plus le délai de l'étape) la
  passe du greffier sur la dernière parole, pour que l'état montré porte ce que la personne vient de dire (la fiche avait un
  tour de retard : le greffier part en même temps que la requête).

| Test | Ce qu'il prouve |
|---|---|
| système, deux familles | case allumée : l'instruction système de la requête se termine par l'état de la fiche ; il est remplacé (jamais empilé) à la requête suivante ; l'historique n'est pas touché |
| famille OpenAI, requête réelle | la requête construite porte l'état dans le message système et NON comme message de la personne |
| accueil | sans parole de la personne, aucun bloc |
| éteinte | case éteinte : comportement d'avant (état en message de la personne, instruction système intacte), aucun processeur posé sans étape qui réclame le code |
| case seule | case allumée sur un agent dont aucune étape ne réclame le code : les processeurs sont posés |
| éteindre | la case éteinte après avoir été allumée retire le bloc |
| zéro perte | service sans composition d'instruction : l'état reste un message de la personne |
| chaque tour, deux familles | moment « chaque tour » : la requête attend le greffier même quand deux champs manquent, et l'état montré porte ce qu'il vient de noter |
| chaque tour, délai | le greffier en retard : la requête part de l'état d'avant, tracée |
| écran | le moment est une option de l'étape, la case est dans le schéma des réglages de l'agent, éteinte par défaut |
| clavier | une vraie session au clavier, case allumée : l'instruction système du service porte l'état |
"""

from __future__ import annotations

import copy

import pytest

from api.schemas.workflow_configurations import WorkflowConfigurationDefaults
from api.services.pipecat.avant_la_requete import autour_du_cerveau
from api.services.workflow import fiche_dans_le_systeme as systeme
from api.services.workflow.champs_conditionnels import champs_actifs
from api.services.workflow.fiche_au_fil_de_leau import montrer_la_fiche
from api.services.workflow import passage_sur_la_fiche as passage
from api.tests.mark.test_passages_fiables_agnostique import FAMILLES, CerveauOpenAI, _requete
from api.tests.mark.test_passages_fiables_fiche import (
    GreffierFactice,
    _etape,
    definition_clavier,
    graphe,
    monter,
)
from pipecat.tests import MockLLMService
from pipecat.utils.types import assert_given

PAROLE = [{"role": "assistant", "content": "Quelle est la demande ?"}, {"role": "user", "content": "une demande"}]
ACCUEIL = [{"role": "assistant", "content": "Bonjour."}]
ETAT = "[Fiche de l'appel"  # début du bloc de l'état de la fiche (``entete_etat``)


class CerveauRequetes(MockLLMService):
    """Un cerveau de la famille OpenAI qui garde la requête construite telle qu'elle partirait (enveloppes du moteur comprises)."""

    def __init__(self):
        super().__init__(mock_steps=[MockLLMService.create_text_chunks("D'accord.")] * 6, chunk_delay=0)
        self.vues: list[dict] = []

    async def get_chat_completions(self, context):  # type: ignore[override]
        adapter = self.get_llm_adapter()
        invocation = adapter.get_llm_invocation_params(
            context,
            system_instruction=assert_given(self._settings.system_instruction),
            convert_developer_to_user=not self.supports_developer_role,
        )
        self.vues.append(self.build_chat_completion_params(invocation))
        return await super().get_chat_completions(context)


async def _monter_avec_la_case(famille, *, case=True, etape=None, fiche=None, greffier=None, cerveau=None):
    harness = await monter(graphe(etape) if etape is not None else None, fiche=fiche, greffier=greffier or GreffierFactice())
    engine = harness.engine
    cerveau = cerveau or famille()
    engine.active_agent.llm = cerveau
    engine.active_agent.reglages = {systeme.CLE_FICHE_DANS_LE_SYSTEME: True} if case else {}
    # La vraie fonction du moteur (``_porter_la_fiche``) : l'état de la fiche est porté par le service, quelle que soit sa
    # famille. Appelée directement : ``_porter_la_fiche`` ferait aussi du service celui de la passe de fin d'appel.
    montrer_la_fiche(
        cerveau,
        engine._fiche,
        lambda: engine._gathered_context,
        engine._notices_fiche,
        lambda: champs_actifs(engine.active_agent.current_node, engine._gathered_context),
        lambda: bool(engine.active_agent.current_node.out_edges),
        lambda: (),
    )
    await engine.set_node(_etape(engine))
    return harness, engine, cerveau


def _systeme(cerveau, i=-1):
    return cerveau.requetes[i]["systeme"] or ""


# --------------------------------------------------------------------------- #
# La fiche dans l'instruction système
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
@pytest.mark.parametrize("famille", FAMILLES)
async def test_d4_la_fiche_finit_l_instruction_systeme_remplacee_a_chaque_requete_avec_toute_famille(famille):
    harness, engine, cerveau = await _monter_avec_la_case(famille, fiche={"nom": "Lemaire"})
    try:
        historique = [dict(m) for m in PAROLE]
        contexte, _ = await _requete(engine, cerveau, historique)
        instruction = _systeme(cerveau)
        assert instruction.startswith("Tu es l'étape Collecte.")
        assert ETAT in instruction and "Lemaire" in instruction
        assert instruction.rstrip().endswith(instruction.split("\n\n")[-1].rstrip())  # le bloc est le dernier
        assert contexte.get_messages() == PAROLE  # l'historique n'est pas touché
        # La fiche change : le bloc d'avant est remplacé, jamais empilé.
        engine._gathered_context["objet"] = "une demande"
        await _requete(engine, cerveau, [dict(m) for m in PAROLE])
        assert "une demande" in _systeme(cerveau, 1) and instruction != _systeme(cerveau, 1)
        assert _systeme(cerveau, 1).count(ETAT) == 1
    finally:
        await harness.stop()


@pytest.mark.asyncio
async def test_d4_requete_reelle_l_etat_est_dans_le_message_systeme_et_pas_un_message_de_la_personne():
    harness, engine, cerveau = await _monter_avec_la_case(CerveauRequetes, fiche={"nom": "Lemaire"})
    try:
        await _requete(engine, cerveau, [dict(m) for m in PAROLE])
        requete = cerveau.vues[-1]
        systemes = [m for m in requete["messages"] if m.get("role") == "system"]
        assert len(systemes) == 1 and "Lemaire" in systemes[0]["content"]
        paroles = [m for m in requete["messages"] if m.get("role") == "user"]
        assert [m["content"] for m in paroles] == ["une demande"]  # rien de glissé avant la dernière parole
        # Aucun message système au milieu de la conversation (Mistral le refuse).
        assert requete["messages"][0]["role"] == "system" and all(m["role"] != "system" for m in requete["messages"][1:])
    finally:
        await harness.stop()


@pytest.mark.asyncio
async def test_d4_case_eteinte_comportement_d_avant_l_etat_reste_un_message_de_la_personne():
    harness, engine, cerveau = await _monter_avec_la_case(CerveauRequetes, case=False, fiche={"nom": "Lemaire"})
    try:
        await _requete(engine, cerveau, [dict(m) for m in PAROLE])
        requete = cerveau.vues[-1]
        assert all("Lemaire" not in (m["content"] or "") for m in requete["messages"] if m.get("role") == "system")
        paroles = [m["content"] for m in requete["messages"] if m.get("role") == "user"]
        assert len(paroles) == 2 and "Lemaire" in paroles[0] and paroles[1] == "une demande"
        assert getattr(cerveau, systeme.EN_SYSTEME) is False
    finally:
        await harness.stop()


@pytest.mark.asyncio
@pytest.mark.parametrize("famille", FAMILLES)
async def test_d4_l_accueil_sans_parole_de_la_personne_n_a_pas_de_bloc(famille):
    harness, engine, cerveau = await _monter_avec_la_case(famille, fiche={"nom": "Lemaire"})
    try:
        await _requete(engine, cerveau, [dict(m) for m in ACCUEIL])
        assert ETAT not in _systeme(cerveau)
    finally:
        await harness.stop()


@pytest.mark.asyncio
async def test_d4_eteindre_la_case_retire_le_bloc():
    harness, engine, cerveau = await _monter_avec_la_case(CerveauOpenAI, fiche={"nom": "Lemaire"})
    try:
        await _requete(engine, cerveau, [dict(m) for m in PAROLE])
        assert "Lemaire" in _systeme(cerveau)
        engine.active_agent.reglages = {}
        await _requete(engine, cerveau, [dict(m) for m in PAROLE])
        assert "Lemaire" not in _systeme(cerveau, 1)
    finally:
        await harness.stop()


@pytest.mark.asyncio
async def test_d4_service_sans_composition_zero_perte_l_etat_reste_un_message():
    harness, engine, cerveau = await _monter_avec_la_case(CerveauRequetes, fiche={"nom": "Lemaire"})
    try:
        del cerveau._appended_system_instructions  # un service qui ne compose pas son instruction
        assert systeme.placer_la_fiche(engine, cerveau, [dict(m) for m in PAROLE]) is False
        assert getattr(cerveau, systeme.EN_SYSTEME) is False
    finally:
        await harness.stop()


def test_d4_la_case_seule_pose_les_processeurs_et_sans_case_un_agent_tout_eteint_n_en_a_pas():
    class Agent:
        def __init__(self, reglages):
            self.reglages, self.llm, self.visit_id = reglages, object(), "v"
            self.workflow = type("W", (), {"nodes": {}})()

    class Moteur:
        reglages_appel: dict = {}

    avant, apres = autour_du_cerveau(Moteur(), Agent({systeme.CLE_FICHE_DANS_LE_SYSTEME: True}))
    assert avant is not None and apres is not None
    assert autour_du_cerveau(Moteur(), Agent({})) == (None, None)


# --------------------------------------------------------------------------- #
# Attendre le greffier à chaque tour
# --------------------------------------------------------------------------- #


def _etape_chaque_tour(**plus):
    return {
        "qui_decide_du_passage": "collecte",
        "moment_du_passage": "attendre_a_chaque_tour",
        "champs_etape": "nom,objet",
        **plus,
    }


@pytest.mark.asyncio
@pytest.mark.parametrize("famille", FAMILLES)
async def test_d4_chaque_tour_la_requete_attend_le_greffier_et_montre_ce_qu_il_vient_de_noter(famille):
    greffier = GreffierFactice()
    harness, engine, cerveau = await _monter_avec_la_case(famille, etape=_etape_chaque_tour(), fiche={}, greffier=greffier)
    try:
        greffier.pendant = lambda: engine._gathered_context.update(nom="Lemaire")  # DEUX champs manquaient : option 2 n'aurait pas attendu
        await _requete(engine, cerveau, [dict(m) for m in PAROLE])
        assert len(greffier.appels) >= 1 and _etape(engine) == "etape"
        assert "Lemaire" in _systeme(cerveau)  # l'état montré porte la dernière parole
    finally:
        await harness.stop()


@pytest.mark.asyncio
async def test_d4_chaque_tour_greffier_en_retard_la_requete_part_de_l_etat_d_avant_tracee():
    greffier = GreffierFactice(reponse=False)
    harness, engine, cerveau = await _monter_avec_la_case(
        CerveauOpenAI, etape=_etape_chaque_tour(delai_du_passage=0.2), fiche={}, greffier=greffier
    )
    try:
        await _requete(engine, cerveau, [dict(m) for m in PAROLE])
        assert greffier.appels == pytest.approx([0.2], abs=0.05)
        assert engine._gathered_context[passage.CLE_PASSAGES][-1]["resultat"] == "delai_option_1_jouera"
        assert len(cerveau.requetes) == 1  # elle part quand même
    finally:
        await harness.stop()


@pytest.mark.asyncio
async def test_d4_option_2_inchangee_deux_champs_manquent_le_greffier_n_est_pas_attendu():
    greffier = GreffierFactice()
    harness = await monter(graphe({"qui_decide_du_passage": "collecte", "moment_du_passage": "attendre_le_dernier_champ", "champs_etape": "nom,objet"}), fiche={}, greffier=greffier)
    try:
        engine = harness.engine
        assert await passage.avant_la_requete(engine, engine.active_agent.llm, type("C", (), {"get_messages": lambda self: [dict(m) for m in PAROLE]})()) is False
        assert greffier.appels == []
    finally:
        await harness.stop()


# --------------------------------------------------------------------------- #
# L'écran et les schémas
# --------------------------------------------------------------------------- #


def test_d4_le_moment_est_une_option_de_l_etape_et_la_case_est_eteinte_par_defaut():
    from api.services.workflow.dto import MOMENTS_DU_PASSAGE, AgentNodeData

    assert "attendre_a_chaque_tour" in MOMENTS_DU_PASSAGE
    assert AgentNodeData(name="x", prompt="y", moment_du_passage="attendre_a_chaque_tour").moment_du_passage == "attendre_a_chaque_tour"
    with pytest.raises(ValueError):
        AgentNodeData(name="x", prompt="y", moment_du_passage="jamais")
    assert WorkflowConfigurationDefaults().fiche_dans_le_systeme is False
    assert passage.reglages_du_passage(
        type("N", (), {"data": AgentNodeData(name="x", prompt="y", qui_decide_du_passage="collecte", moment_du_passage="attendre_a_chaque_tour")})()
    ).attend_a_chaque_tour


# --------------------------------------------------------------------------- #
# Clavier : une vraie session
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_d4_clavier_l_instruction_systeme_du_service_porte_l_etat(db_session, async_session, test_client_factory):
    from api.tests.mark.test_clavier_porte_la_fiche import FICHE, _monter, _noter
    from api.tests.mark.test_passation_clavier import _dit, _session, _texte, _vide

    configuration = {**copy.deepcopy(FICHE), systeme.CLE_FICHE_DANS_LE_SYSTEME: True}
    etape = {"champs_etape": "nom", "qui_decide_du_passage": "collecte"}
    user, workflow = await _monter(db_session, async_session, configuration, definition_clavier(etape))
    tour_1 = _dit(_noter({"nom": "Lemaire"}, "n1"), _texte("Je note Lemaire, c'est bien ça ?"))
    tour_2 = _dit(_texte("Parfait."), _texte("Voici la suite."))
    reponses = await _session(test_client_factory, user, workflow, [_vide(), tour_1, tour_2], ["je m'appelle Lemaire", "oui"])
    assert reponses  # la session a tourné
    # Le service du second tour a reçu l'état de la fiche (le nom noté au premier) dans son instruction système.
    instruction = tour_2._settings.system_instruction or ""
    assert "Lemaire" in instruction and ETAT in instruction, instruction

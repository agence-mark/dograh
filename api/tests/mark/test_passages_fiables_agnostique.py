"""[.mark] passages-fiables : l'option 2 et la notice d'un tour marchent avec N'IMPORTE QUEL cerveau, et le décideur de fin
de tour n'ajoute aucune latence.

Décision d'Evan (29/10) : « je ne veux pas du code spécifique à une brique, cela doit marcher avec n'importe quel LLM ».
Les deux fonctions passent désormais par les trames (``LLMContextFrame``) et le contexte partagé de Pipecat, par deux
processeurs posés autour du cerveau (``pipecat/avant_la_requete.py``). Chaque test tourne avec DEUX familles de services :

- ``CerveauOpenAI`` : la famille compatible OpenAI (``MockLLMService`` de Pipecat, sous-classe d'``OpenAILLMService``) ;
- ``CerveauGenerique`` : un ``LLMService`` de Pipecat d'une autre famille, sans ``get_chat_completions`` ni
  ``build_chat_completion_params``.

Ils passent par le VRAI moteur (banc de ``test_passages_fiables_fiche.py``) et un vrai circuit Pipecat (``run_test``).

| Test | Ce qu'il prouve |
|---|---|
| option 2, deux familles | un seul champ manque, le greffier le note pendant l'attente : la requête part DÉJÀ dans l'étape d'arrivée (prompt de l'étape d'arrivée), sans relance |
| notice, deux familles | après un passage par le code, la requête de relance (trame montante) porte la notice une fois, avant la dernière parole ; l'historique n'est pas touché ; la requête suivante ne la porte plus |
| tout éteint | aucun processeur posé : le circuit de la base |
| circuit du téléphone | le constructeur pose les deux processeurs de part et d'autre du cerveau, et rien quand ils sont absents |
| latence (a) | ``on_assistant_turn_stopped`` n'est pas synchrone : le circuit n'attend pas le décideur |
| latence (b) | étape tout éteinte : ni porte en cours, ni greffier, ni arbitre attendus ; décision en quelques millisecondes |
| latence (c) | la durée de la décision est écrite dans ``passages_par_le_code`` quand il agit |
"""

import asyncio
import time
from types import SimpleNamespace

import pytest

from api.services.pipecat.avant_la_requete import AvantLaRequete, autour_du_cerveau
from api.services.pipecat.pipeline_builder import build_agent_generation_pipeline
from api.services.workflow import decideur_de_fin_de_tour as decideur
from api.services.workflow import passage_sur_la_fiche as passage
from api.tests.mark.test_passages_fiables_fiche import (
    GreffierFactice,
    _complete,
    _etape,
    _etape_option_2,
    _fin_de_reponse,
    graphe,
    monter,
)
from pipecat.frames.frames import (
    LLMContextFrame,
    LLMFullResponseEndFrame,
    LLMFullResponseStartFrame,
    LLMTextFrame,
)
from pipecat.pipeline.pipeline import Pipeline
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import LLMAssistantAggregator
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor
from pipecat.services.llm_service import LLMService
from pipecat.tests import MockLLMService, run_test

NOTICE = "Ce qui vient de se passer"


class CerveauOpenAI(MockLLMService):
    """La famille compatible OpenAI : la requête est lue là où elle part (``get_chat_completions``)."""

    def __init__(self):
        super().__init__(mock_steps=[MockLLMService.create_text_chunks("D'accord.")] * 4, chunk_delay=0)
        self.requetes: list[dict] = []

    async def get_chat_completions(self, context):  # type: ignore[override]
        self.requetes.append(
            {"systeme": self._settings.system_instruction, "messages": list(context.get_messages())}
        )
        return await super().get_chat_completions(context)


class CerveauGenerique(LLMService):
    """Une autre famille : un service Pipecat générique, qui ne connaît que la trame ``LLMContextFrame``."""

    def __init__(self):
        super().__init__()
        self.requetes: list[dict] = []

    async def process_frame(self, frame, direction):
        await super().process_frame(frame, direction)
        if isinstance(frame, LLMContextFrame):
            self.requetes.append(
                {"systeme": self._settings.system_instruction, "messages": list(frame.context.get_messages())}
            )
            await self.push_frame(LLMFullResponseStartFrame())
            await self.push_frame(LLMTextFrame("D'accord."))
            await self.push_frame(LLMFullResponseEndFrame())
        else:
            await self.push_frame(frame, direction)


FAMILLES = [pytest.param(CerveauOpenAI, id="famille-openai"), pytest.param(CerveauGenerique, id="autre-famille")]


def test_l_autre_famille_n_a_aucune_methode_de_la_famille_openai():
    cerveau = CerveauGenerique()
    assert not hasattr(cerveau, "build_chat_completion_params") and not hasattr(cerveau, "get_chat_completions")


async def _brancher(engine, famille):
    """Le cerveau de l'agent devient celui de la famille testée, avec le prompt de l'étape où l'on est."""
    cerveau = famille()
    engine.active_agent.llm = cerveau
    await engine.set_node(_etape(engine))
    return cerveau


async def _requete(engine, cerveau, messages, sens=FrameDirection.DOWNSTREAM):
    """Une requête de conversation, à travers le circuit [avant, cerveau, juste après] que pose ``autour_du_cerveau``."""
    avant, apres = autour_du_cerveau(engine, engine.active_agent)
    assert isinstance(avant, AvantLaRequete) and isinstance(apres, AvantLaRequete)
    contexte = LLMContext(messages=messages)
    descendues, _ = await run_test(
        Pipeline([avant, cerveau, apres]),
        frames_to_send=[LLMContextFrame(contexte)],
        frames_to_send_direction=sens,
    )
    return contexte, descendues


# --------------------------------------------------------------------------- #
# L'option 2
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
@pytest.mark.parametrize("famille", FAMILLES)
async def test_option_2_la_requete_part_deja_dans_l_etape_d_arrivee_avec_toute_famille(famille):
    greffier = GreffierFactice()
    harness = await monter(graphe(_etape_option_2()), fiche={"nom": "Lemaire"}, greffier=greffier)
    try:
        engine = harness.engine
        cerveau = await _brancher(engine, famille)
        greffier.pendant = lambda: engine._gathered_context.update(objet="une demande")
        messages = [{"role": "assistant", "content": "Quelle est la demande ?"}, {"role": "user", "content": "une demande"}]
        await _requete(engine, cerveau, messages)
        assert _etape(engine) == "suite"
        [requete] = cerveau.requetes
        assert "Tu es l'étape Suite." in requete["systeme"]  # le passage a eu lieu AVANT que la requête parte
        engine.active_agent.queue_frame.assert_not_awaited()  # aucune relance : un seul tour
        assert greffier.appels == [passage.DELAI_PAR_DEFAUT]
        trace = engine._gathered_context[passage.CLE_PASSAGES][-1]
        assert trace["option"] == 2 and trace["resultat"] == "prise"
    finally:
        await harness.stop()


@pytest.mark.asyncio
@pytest.mark.parametrize("famille", FAMILLES)
async def test_option_2_au_delai_la_requete_part_de_l_etape_d_avant_avec_toute_famille(famille):
    greffier = GreffierFactice(reponse=False)
    harness = await monter(graphe(_etape_option_2(delai_du_passage=0.2)), fiche={"nom": "Lemaire"}, greffier=greffier)
    try:
        engine = harness.engine
        cerveau = await _brancher(engine, famille)
        await _requete(engine, cerveau, [{"role": "user", "content": "une demande"}])
        assert _etape(engine) == "etape" and greffier.appels == [0.2]
        [requete] = cerveau.requetes
        assert "Tu es l'étape Collecte." in requete["systeme"]
    finally:
        await harness.stop()


# --------------------------------------------------------------------------- #
# La notice d'un tour
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
@pytest.mark.parametrize("famille", FAMILLES)
async def test_la_notice_est_montree_une_fois_dans_la_requete_jamais_dans_l_historique_avec_toute_famille(famille):
    harness = await monter(fiche=_complete(), greffier=GreffierFactice())
    try:
        engine = harness.engine
        cerveau = await _brancher(engine, famille)
        qui, _, _ = await _fin_de_reponse(engine, "Bien noté, merci.")
        assert qui == "fiche" and _etape(engine) == "suite"
        historique = [{"role": "assistant", "content": "Bien noté."}, {"role": "user", "content": "voilà"}]
        # La relance (``LLMRunFrame``) revient de l'agrégateur de l'assistant : la trame MONTE vers le cerveau.
        contexte, _ = await _requete(engine, cerveau, list(historique), sens=FrameDirection.UPSTREAM)
        envoyes = cerveau.requetes[0]["messages"]
        notices = [m for m in envoyes if NOTICE in str(m.get("content"))]
        assert len(notices) == 1
        assert "L'appelant a entendu : « Bien noté, merci. »" in notices[0]["content"]
        assert "Ne la répète pas" in notices[0]["content"]
        assert envoyes[-1] == {"role": "user", "content": "voilà"} and envoyes[-2] is notices[0]
        assert contexte.get_messages() == historique  # l'historique partagé n'a pas bougé
        # Une seule requête : la suivante ne la porte plus.
        await _requete(engine, cerveau, list(historique))
        assert not any(NOTICE in str(m.get("content")) for m in cerveau.requetes[1]["messages"])
    finally:
        await harness.stop()


# --------------------------------------------------------------------------- #
# Tout éteint, et le circuit du téléphone
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_tout_eteint_aucun_processeur_le_circuit_de_la_base():
    harness = await monter(graphe({"champs_etape": "nom,objet"}), fiche=_complete(), greffier=GreffierFactice())
    try:
        assert autour_du_cerveau(harness.engine, harness.engine.active_agent) == (None, None)
        assert autour_du_cerveau(None, SimpleNamespace(llm=object())) == (None, None)
    finally:
        await harness.stop()


def test_le_circuit_d_un_agent_pose_les_processeurs_de_part_et_d_autre_du_cerveau():
    llm, rappels = FrameProcessor(name="cerveau"), FrameProcessor(name="rappels")
    avant, apres = FrameProcessor(name="avant"), FrameProcessor(name="apres")
    noms = [p.name for p in build_agent_generation_pipeline(llm, rappels, autour_du_cerveau=(avant, apres)).processors]
    assert noms[1:-1] == ["avant", "cerveau", "apres", "rappels"]
    noms = [p.name for p in build_agent_generation_pipeline(llm, rappels).processors]
    assert noms[1:-1] == ["cerveau", "rappels"]


def test_parite_les_processeurs_sont_poses_au_telephone_et_au_clavier_et_aucun_crochet_ne_reste():
    from pathlib import Path

    racine = Path(passage.__file__).resolve().parents[1]
    usine = (racine / "pipecat" / "agent_runtime_factory.py").read_text(encoding="utf-8")
    clavier = (racine / "workflow" / "text_chat_runner.py").read_text(encoding="utf-8")
    assert "autour_du_cerveau=autour_du_cerveau(" in usine
    assert "autour_du_cerveau(engine, engine.active_agent)" in clavier
    assert "(avant_le_cerveau or agent.llm).queue_frame(LLMContextFrame(context))" in clavier
    source = Path(passage.__file__).read_text(encoding="utf-8")
    assert "build_chat_completion_params" not in source and "get_chat_completions" not in source


# --------------------------------------------------------------------------- #
# La latence du décideur
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_latence_a_le_circuit_n_attend_jamais_le_decideur(monkeypatch):
    agregateur = LLMAssistantAggregator(LLMContext())
    assert agregateur._event_handlers["on_assistant_turn_stopped"].is_sync is False
    fini = asyncio.Event()

    async def decision_lente(*_args, **_kwargs):
        await asyncio.sleep(0.5)
        fini.set()

    monkeypatch.setattr(decideur, "decider", decision_lente)
    moteur = SimpleNamespace(arbitre=object(), etat_pour_le_filet=lambda: None, jeton_de_visite=lambda: None)
    decideur.brancher_le_decideur_de_fin_de_tour(moteur, agregateur)
    debut = time.monotonic()
    await agregateur._call_event_handler("on_assistant_turn_stopped", SimpleNamespace(content="Au revoir."))
    assert time.monotonic() - debut < 0.05  # rendu tout de suite : la décision tourne dans sa tâche
    assert not fini.is_set()
    await asyncio.wait_for(fini.wait(), 2)


@pytest.mark.asyncio
async def test_latence_b_etape_tout_eteinte_aucune_attente(monkeypatch):
    greffier = GreffierFactice()
    harness = await monter(graphe({"champs_etape": "nom,objet"}), fiche=_complete(), greffier=greffier)
    try:
        engine = harness.engine
        consultes = []

        async def resultat(jeton):
            consultes.append(jeton)

        monkeypatch.setattr(engine.arbitre, "resultat", resultat, raising=False) if getattr(
            engine, "arbitre", None
        ) else setattr(engine, "arbitre", SimpleNamespace(resultat=resultat, oublier=lambda: None))
        porte_lente = asyncio.get_running_loop().create_task(asyncio.sleep(1))
        engine.portes_du_post_scriptum.append({porte_lente})
        debut = time.monotonic()
        qui, _, _ = await _fin_de_reponse(engine)
        duree = time.monotonic() - debut
        porte_lente.cancel()
        assert qui is None and _etape(engine) == "etape"
        assert duree < 0.1, duree  # la porte lente (1 s) n'a pas été attendue
        assert greffier.appels == [] and consultes == []
        assert passage.CLE_PASSAGES not in engine._gathered_context
    finally:
        await harness.stop()


@pytest.mark.asyncio
async def test_latence_c_la_duree_de_la_decision_est_tracee_quand_il_agit():
    harness = await monter(fiche=_complete(), greffier=GreffierFactice())
    try:
        engine = harness.engine
        qui, _, _ = await _fin_de_reponse(engine)
        assert qui == "fiche"
        trace = engine._gathered_context[passage.CLE_PASSAGES][-1]
        assert trace["resultat"] == "prise" and isinstance(trace["duree_decision"], float)
        assert 0 <= trace["duree_decision"] < 1
    finally:
        await harness.stop()

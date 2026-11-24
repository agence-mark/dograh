"""[.mark] Lot 7a, ligne 124 : des cases illisibles retiennent la requête ; la même fonction (``avant_la_requete.requete_retenue``) écrit le journal au tour et à l'ouverture.
Le tour dit la phrase du repli ; l'ouverture la dit aussi depuis la ligne 29 de la tranche 7b (fiche 7b : « l'ouverture aux cases illisibles dit la phrase de repli », plus de silence)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

from pipecat.frames.frames import LLMContextFrame, TTSSpeakFrame
from pipecat.processors.frame_processor import FrameDirection

from api.services.pipecat import avant_la_requete as AR
from api.services.workflow.agent_runtime import AgentRuntime
from api.services.workflow.cases_selon_l_etat import CasesIllisibles


async def _illisible(*_a, **_k):
    raise CasesIllisibles("état illisible")


async def test_l_ouverture_et_le_tour_ecrivent_le_meme_journal(monkeypatch):
    lignes: list[str] = []
    monkeypatch.setattr(AR.logger, "error", lambda message, *a, **k: lignes.append(str(message)))
    monkeypatch.setattr(AR, "preparer_la_forme", _illisible)
    monkeypatch.setattr(AR, "preparer_la_requete", _illisible)
    moteur = SimpleNamespace(_gathered_context={})
    queued = AsyncMock()
    speak = AsyncMock()
    agent = SimpleNamespace(llm=SimpleNamespace(queue_frame=queued), speak=speak)
    agent.preparer_la_forme = lambda trame: AR._forme_de_l_ouverture(moteur, object(), trame)  # ce que ``autour_du_cerveau`` pose sur l'agent
    await AgentRuntime.run_llm(agent, SimpleNamespace(get_messages=lambda: []))
    ouverture = list(lignes)
    lignes.clear()
    dites: list = []
    processeur = AR.AvantLaRequete(moteur, object(), FrameDirection.DOWNSTREAM)

    async def pousser(trame, direction=FrameDirection.DOWNSTREAM):
        dites.append(trame)

    monkeypatch.setattr(processeur, "push_frame", pousser)
    await processeur.process_frame(LLMContextFrame(context=SimpleNamespace(get_messages=lambda: [])), FrameDirection.DOWNSTREAM)
    assert ouverture and ouverture == lignes, (ouverture, lignes)  # le même journal aux deux endroits
    assert queued.await_count == 0  # la requête d'ouverture ne part pas
    speak.assert_awaited_once()  # ligne 29 : la phrase du repli est dite, jamais une ouverture muette
    assert len(dites) == 1 and isinstance(dites[0], TTSSpeakFrame) and dites[0].text  # le tour dit la phrase du repli, comme avant

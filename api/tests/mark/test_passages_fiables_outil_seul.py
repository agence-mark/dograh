"""[.mark] passages-fiables, correction du banc local (29/10) : un outil du chantier appelé SEUL ne bloque plus l'appel.

Runs 22, 30 et 33 du banc local : « laisser la parole » appelé sans aucune phrase dans la même réponse, au moment où la
personne venait de répondre (« Oui, pourquoi pas, je veux bien. », une adresse). L'outil rendait ``run_llm=False`` sans
condition : l'historique finissait par le résultat de l'outil, la parole suivante de la personne suivait un rôle
``tool``, et Scaleway refusait chaque requête (400 « Unexpected role 'user' after role 'tool' »).

Correction : la règle R15 (``parole_avant_outil``), déjà celle de « confier » : pas de relance seulement si la même
réponse a parlé ; « signaler un problème » appelé seul relance le modèle, qui continue.

Depuis le 29/10 (décision d'Evan après le rebanc), « laisser la parole » n'est plus un outil : la demande de temps est
reconnue par l'arbitre (``test_passages_fiables_avant_la_reponse.py``) ; ses tests d'outil sont retirés.

| Test | Ce qu'il prouve |
|---|---|
| signalement, service réel, deux API | seul : relance, l'historique finit par la parole du modèle ; avec une phrase : pas de relance |
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from pipecat.pipeline.pipeline import Pipeline
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import LLMContextAggregatorPair
from pipecat.adapters.schemas.tools_schema import ToolsSchema
from pipecat.frames.frames import LLMContextFrame
from pipecat.tests.utils import SleepFrame, run_test

from api.services.pipecat.call_monitor_processor import CallMonitorProcessor
from api.services.workflow.signaler_un_probleme import brancher_signaler_un_probleme
from api.tests.mark.test_fournisseur_responses import DEMARRAGE_S, DEUX_API, Rep, _Dit, _service

REPONSE = "Très bien, je note."


class _Agent:
    def __init__(self, llm, reglages):
        self.llm = llm
        self.reglages = reglages
        self.current_node = SimpleNamespace(name="Étape", is_end=False)

    def bind_tool(self, moteur, f):
        return f


def _moniteur():
    moniteur = CallMonitorProcessor(
        response_source=lambda: None, on_response_timeout=lambda _s: None, on_user_idle=None,
        conversation_enabled=lambda: True,
    )
    moniteur.user_idle_timeout = 10.0
    return moniteur


def _contexte(schema) -> LLMContext:
    return LLMContext(
        messages=[
            {"role": "system", "content": "Tu es Marie."},
            {"role": "assistant", "content": "Souhaitez-vous continuer ?"},
            {"role": "user", "content": "Oui, pourquoi pas, je veux bien."},
        ],
        tools=ToolsSchema(standard_tools=[schema]),
    )


async def _jouer(api, reponses, brancher, reglage):
    service, faux = _service(api, reponses)
    moteur = SimpleNamespace(call_monitor=_moniteur(), _gathered_context={})
    agent = _Agent(service, {reglage: True})
    schema = brancher(moteur, agent, agent.current_node)
    contexte = _contexte(schema)
    pair = LLMContextAggregatorPair(contexte)
    voix = _Dit()
    await run_test(
        Pipeline([service, voix, pair.assistant()]),
        frames_to_send=[LLMContextFrame(contexte), SleepFrame(sleep=0.8)],
        start_timeout=DEMARRAGE_S,
    )
    moteur.call_monitor._cancel_deadline()
    return faux, contexte, voix, moteur


def _nature(m) -> str | None:
    if not isinstance(m, dict):
        return None
    if m.get("role") == "tool" or m.get("type") == "function_call_output":
        return "outil"
    if m.get("role") == "assistant" and m.get("content") and not m.get("tool_calls"):
        return "parole"
    return m.get("role") or m.get("type")


def _apres_la_personne_qui_parle(contexte: LLMContext) -> list:
    """L'historique tel que la prochaine requête l'enverra, quand la personne reparle."""
    return [*contexte.get_messages(), {"role": "user", "content": "Allô ?"}]


def _jamais_la_personne_apres_un_outil(messages: list) -> bool:
    natures = [_nature(m) for m in messages]
    return not any(a == "outil" and b == "user" for a, b in zip(natures, natures[1:]))


# --------------------------------------------------------------------------- #
# Signaler un problème : même règle
# --------------------------------------------------------------------------- #

SIGNAL = '{"motif": "Je ne sais pas trancher.", "categorie": "ambigu"}'


@pytest.mark.asyncio
@pytest.mark.parametrize("api", DEUX_API)
async def test_signaler_seul_le_modele_est_relance_et_continue(api):
    faux, contexte, voix, _ = await _jouer(
        api,
        [Rep(appels=[("signaler_un_probleme", SIGNAL, "s1")]), Rep(texte=REPONSE)],
        brancher_signaler_un_probleme,
        "signaler_un_probleme",
    )
    assert len(faux.vus) == 2
    assert voix.texte == REPONSE
    assert _jamais_la_personne_apres_un_outil(_apres_la_personne_qui_parle(contexte))


@pytest.mark.asyncio
@pytest.mark.parametrize("api", DEUX_API)
async def test_signaler_avec_une_phrase_pas_de_relance(api):
    faux, _, voix, _ = await _jouer(
        api,
        [Rep(texte=REPONSE, appels=[("signaler_un_probleme", SIGNAL, "s1")]), Rep(texte="jamais demandé")],
        brancher_signaler_un_probleme,
        "signaler_un_probleme",
    )
    assert len(faux.vus) == 1
    assert voix.texte == REPONSE

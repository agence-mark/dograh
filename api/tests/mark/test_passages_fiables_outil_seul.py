"""[.mark] passages-fiables, correction du banc local (29/10) : un outil du chantier appelé SEUL ne bloque plus l'appel.

Runs 22, 30 et 33 du banc local : « laisser la parole » appelé sans aucune phrase dans la même réponse, au moment où la
personne venait de répondre (« Oui, pourquoi pas, je veux bien. », une adresse). L'outil rendait ``run_llm=False`` sans
condition : l'historique finissait par le résultat de l'outil, la parole suivante de la personne suivait un rôle
``tool``, et Scaleway refusait chaque requête (400 « Unexpected role 'user' after role 'tool' »).

Correction : la règle R15 (``parole_avant_outil``), déjà celle de « confier » : pas de relance seulement si la même
réponse a parlé. « Laisser la parole » appelé seul n'accorde rien (l'attente se demande avec une phrase) et le modèle
répond ; « signaler un problème » appelé seul relance le modèle, qui continue.

| Test | Ce qu'il prouve |
|---|---|
| service réel, deux API | outil seul : le modèle est relancé, l'historique finit par sa parole, jamais par l'outil |
| service réel, deux API | outil avec une phrase : une seule requête, pas de relance (comme avant) |
| clavier | outil seul : l'agent parle dans le même tour, la parole suivante ne suit jamais un résultat d'outil |
| clavier | outil avec une phrase : l'attente est accordée, sans relance |
| signalement | seul : relance ; avec une phrase : pas de relance |
| description | dit qu'il faut une phrase et que l'outil ne fait passer à aucune étape ; aucun mot de métier |
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
from api.services.workflow import laisser_la_parole as parole
from api.services.workflow.laisser_la_parole import brancher_laisser_la_parole
from api.services.workflow.signaler_un_probleme import brancher_signaler_un_probleme
from api.tests.mark.test_clavier_porte_la_fiche import FICHE, _monter
from api.tests.mark.test_fournisseur_responses import DEMARRAGE_S, DEUX_API, Rep, _Dit, _entrees, _service
from api.tests.mark.test_passation_clavier import _appel, _dit, _session, _texte

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
# Laisser la parole, sur le service réel (fournisseur imité)
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
@pytest.mark.parametrize("api", DEUX_API)
async def test_laisser_la_parole_seul_le_modele_est_relance_et_parle(api):
    """Rouge avant : une seule requête, l'historique finit par le résultat d'outil, puis « user » après « tool »."""
    faux, contexte, voix, moteur = await _jouer(
        api,
        [Rep(appels=[(parole.NOM_OUTIL, "{}", "a1")]), Rep(texte=REPONSE)],
        brancher_laisser_la_parole,
        "laisser_la_parole",
    )
    assert len(faux.vus) == 2, "le modèle doit être relancé après l'outil appelé seul"
    assert voix.texte == REPONSE
    assert _nature(contexte.get_messages()[-1]) == "parole"
    assert _jamais_la_personne_apres_un_outil(_apres_la_personne_qui_parle(contexte))
    # La relance a reçu le refus, pas l'ordre de se taire ; rien n'est accordé.
    assert any("Rien n" in str(e) for e in _entrees(api, faux.vus[1]) if _nature(e) == "outil")
    assert moteur.call_monitor.attente_accordee is False
    assert [t["evenement"] for t in moteur._gathered_context[parole.CLE_TRACE]] == ["refusee_sans_phrase"]


@pytest.mark.asyncio
@pytest.mark.parametrize("api", DEUX_API)
async def test_laisser_la_parole_avec_une_phrase_pas_de_relance(api):
    faux, contexte, voix, moteur = await _jouer(
        api,
        [Rep(texte="Je vous attends.", appels=[(parole.NOM_OUTIL, "{}", "a1")]), Rep(texte="jamais demandé")],
        brancher_laisser_la_parole,
        "laisser_la_parole",
    )
    assert len(faux.vus) == 1
    assert voix.texte == "Je vous attends."
    assert moteur.call_monitor.attente_accordee is True
    assert [t["evenement"] for t in moteur._gathered_context[parole.CLE_TRACE]] == ["accordee"]


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


# --------------------------------------------------------------------------- #
# Au clavier (même moteur, vraie session)
# --------------------------------------------------------------------------- #


def _messages(charge) -> list:
    return charge["checkpoint"]["messages"]


@pytest.mark.asyncio
async def test_clavier_laisser_la_parole_seul_l_agent_parle_et_l_historique_reste_valide(
    db_session, async_session, test_client_factory
):
    user, workflow = await _monter(db_session, async_session, {**FICHE, "laisser_la_parole": True})
    reponses = await _session(
        test_client_factory,
        user,
        workflow,
        [_dit(_texte("Bonjour.")), _dit(_appel(parole.NOM_OUTIL, "a1"), _texte(REPONSE)), _dit(_texte("Merci."))],
        ["Oui, pourquoi pas, je veux bien.", "Marc Henry."],
    )
    messages = _messages(reponses[-1])
    assert any(m.get("role") == "assistant" and m.get("content") == REPONSE for m in messages), messages
    assert _jamais_la_personne_apres_un_outil(messages), messages
    trace = reponses[-1]["checkpoint"]["gathered_context"].get(parole.CLE_TRACE) or []
    assert [t["evenement"] for t in trace] == ["refusee_sans_phrase"], trace


@pytest.mark.asyncio
async def test_clavier_laisser_la_parole_avec_une_phrase_accordee_sans_relance(
    db_session, async_session, test_client_factory
):
    user, workflow = await _monter(db_session, async_session, {**FICHE, "laisser_la_parole": True})
    reponses = await _session(
        test_client_factory,
        user,
        workflow,
        [_dit(_texte("Bonjour.")), _dit([*_texte("Je vous attends."), *_appel(parole.NOM_OUTIL, "a1")])],
        ["Attendez, je cherche mon numéro."],
    )
    messages = _messages(reponses[-1])
    assert any(m.get("role") == "assistant" and m.get("content") == "Je vous attends." for m in messages), messages
    assert _nature(messages[-1]) == "outil", "pas de relance : rien n'est dit après le résultat"
    trace = reponses[-1]["checkpoint"]["gathered_context"].get(parole.CLE_TRACE) or []
    assert [t["evenement"] for t in trace] == ["accordee"], trace


# --------------------------------------------------------------------------- #
# La description de l'outil
# --------------------------------------------------------------------------- #


def test_la_description_demande_une_phrase_et_ne_fait_passer_a_aucune_etape():
    d = parole.DESCRIPTION_OUTIL
    assert "sans cette phrase, rien n'est accordé" in d
    assert "ne fait passer à aucune autre étape" in d
    assert "explicitement" in d

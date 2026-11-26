"""[.mark] Lot 7b, ligne 29 (Q3) : « Pardon, je n'ai pas bien saisi » n'est plus écrit en dur : quand le modèle ne rend rien et qu'aucune question n'attend, l'agent dit la phrase
RÉGLÉE du restaurant (le diseur de phrases), la valeur du catalogue seulement si le réglage manque (une ligne au journal). À l'ouverture, des cases illisibles disent aussi cette phrase
(avant : le silence).

Avant : Client « Allô ? » (le modèle ne rend rien deux fois) / Agent « Pardon, je n'ai pas bien saisi. Vous pouvez répéter ? » même si le restaurant a réglé une autre phrase ;
à l'ouverture, le silence. Après : la phrase réglée du restaurant, aux deux endroits.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

from api.services.pipecat import avant_la_requete as AR
from api.services.pipecat.reponse_avalee import ATTRIBUT_PHRASE_DE_REPLI, RepliqueVerifiee, phrase_de_repli_par_defaut
from api.services.workflow.agent_runtime import AgentRuntime
from api.services.workflow.cases_selon_l_etat import CasesIllisibles

REGLEE = "Excusez-moi, je n'ai pas compris, vous pouvez redire ?"


def _morceau(texte):
    return SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content=texte, tool_calls=None), finish_reason=None)], usage=None)


async def _dit(**plus) -> str:
    async def flux():
        yield _morceau("Ça vous fera 15 euros.")

    async def relance_429(_retenue):
        raise RuntimeError("429 Too Many Requests")

    retenue = SimpleNamespace(a_dire=None, raison="chiffre", outil=None, appel_par_le_code=False)
    return "".join(m.choices[0].delta.content or "" for m in [m async for m in RepliqueVerifiee(flux(), lambda t: retenue, relance_429, **plus)])


async def test_la_relance_qui_echoue_dit_la_phrase_reglee_du_restaurant():
    assert await _dit(phrase_reglee=lambda: REGLEE) == REGLEE


async def test_sans_reglage_la_phrase_du_catalogue_et_une_ligne_au_journal(monkeypatch):
    lignes: list[str] = []
    monkeypatch.setattr("api.services.pipecat.reponse_avalee.logger.warning", lambda m, *a, **k: lignes.append(str(m)))
    assert await _dit() == phrase_de_repli_par_defaut()
    assert any("phrase de repli" in l for l in lignes), lignes


def test_des_cases_illisibles_disent_la_phrase_reglee_sans_fait_accompli():  # décision d'Evan 25/11 8 h 45 (lot 7b-C5) : plus de repli composé
    llm = SimpleNamespace(**{ATTRIBUT_PHRASE_DE_REPLI: lambda: REGLEE})
    moteur = SimpleNamespace(_gathered_context={})
    assert AR.phrase_si_les_cases_sont_illisibles(moteur, llm) == REGLEE


async def test_l_ouverture_aux_cases_illisibles_dit_la_phrase_reglee(monkeypatch):
    async def illisible(*_a, **_k):
        raise CasesIllisibles("état illisible")

    monkeypatch.setattr(AR, "preparer_la_forme", illisible)
    llm = SimpleNamespace(**{ATTRIBUT_PHRASE_DE_REPLI: lambda: REGLEE})
    moteur = SimpleNamespace(_gathered_context={})
    queued, speak = AsyncMock(), AsyncMock()
    agent = SimpleNamespace(llm=SimpleNamespace(queue_frame=queued), speak=speak)
    agent.preparer_la_forme = lambda trame: AR._forme_de_l_ouverture(moteur, llm, trame)
    await AgentRuntime.run_llm(agent, SimpleNamespace(get_messages=lambda: []))
    assert queued.await_count == 0  # la requête ne part pas
    speak.assert_awaited_once_with(REGLEE)  # mais l'ouverture n'est plus muette

"""[.mark] Aide publique des tests : le flux du vrai cerveau (le mixin de reprise sans flux, sur un faux fournisseur de Pipecat), partagé par plusieurs fichiers."""

from __future__ import annotations


async def flux_du_cerveau(reponse: str, verificateur=None) -> str:
    from pipecat.processors.aggregators.llm_context import LLMContext
    from pipecat.tests import MockLLMService

    from api.services.pipecat.reponse_avalee import ATTRIBUT_VERITE, RepriseSansFluxMixin

    class Cerveau(RepriseSansFluxMixin, MockLLMService):
        pass

    cerveau = Cerveau(mock_steps=[MockLLMService.create_text_chunks(reponse, chunk_size=4)], chunk_delay=0)
    if verificateur is not None:
        setattr(cerveau, ATTRIBUT_VERITE, verificateur)
    contexte = LLMContext(messages=[{"role": "user", "content": "bonjour"}])
    return "".join(m.choices[0].delta.content or "" for m in [m async for m in await cerveau.get_chat_completions(contexte)] if m.choices)

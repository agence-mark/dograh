"""[.mark] Chantier agents-specialises, D1 (rejeu du 16/10, run 1404) : le cerveau autour d'une passation.

| Test | Ce qu'il prouve |
|---|---|
| agent muet | après la main passée, aucune requête ne part, flux vide, ni relance ni repli |
| parole rendue | l'agent qui reprend la main (ou garde l'appel) reparle |
| note au dernier moment | une requête finie par l'assistant reçoit la note, la requête seulement |
| sans objet | fin par l'appelant, par un résultat d'outil ou par un appel d'outil : rien d'ajouté |
| branchement | le cerveau compatible OpenAI porte le garde-fou, sous la trace, au-dessus de la relance |
"""

from __future__ import annotations

from api.services.groupe.passations import NOTE_DE_PASSATION
from api.services.pipecat.main_passee import (
    MainPasseeMixin,
    avec_la_note,
    muter,
    rendre_la_parole,
)


class _Base:
    def __init__(self):
        self.appels = 0

    async def get_chat_completions(self, context):
        self.appels += 1
        return ["réponse"]

    def build_chat_completion_params(self, params):
        return {"model": "m", "messages": list(params["messages"])}


class _Service(MainPasseeMixin, _Base):
    pass


async def test_un_agent_qui_a_passe_la_main_ne_demande_plus_de_reponse():
    service = _Service()
    muter(service)
    assert [m async for m in await service.get_chat_completions([])] == []
    assert service.appels == 0
    rendre_la_parole(service)
    assert await service.get_chat_completions([]) == ["réponse"]
    assert service.appels == 1


def test_une_requete_finie_par_l_assistant_recoit_la_note():
    service = _Service()
    messages = [
        {"role": "system", "content": "consigne"},
        {"role": "user", "content": "Je voudrais changer mon poêle."},
        {"role": "assistant", "content": "Très bien."},
    ]
    params = service.build_chat_completion_params({"messages": messages})
    assert params["messages"] == [*messages, {"role": "user", "content": NOTE_DE_PASSATION}]
    assert len(messages) == 3, "le contexte n'est jamais touché"


def test_rien_n_est_ajoute_hors_d_une_fin_par_l_assistant():
    for fin in (
        {"role": "user", "content": "Allô ?"},
        {"role": "tool", "content": "{}", "tool_call_id": "t"},
        {"role": "assistant", "content": None, "tool_calls": [{"id": "t"}]},
    ):
        messages = [{"role": "user", "content": "a"}, fin]
        assert avec_la_note(messages) is messages
    assert avec_la_note([{"role": "assistant", "content": "b"}, {"role": "system", "content": "s"}])[-1][
        "content"
    ] == NOTE_DE_PASSATION


def test_le_cerveau_compatible_openai_porte_le_garde_fou():
    from api.services.pipecat.reponse_avalee import RepriseSansFluxMixin
    from api.services.pipecat.service_factory import DograhOpenAILLMService
    from api.services.pipecat.trace_modele import TraceModeleMixin

    ordre = DograhOpenAILLMService.__mro__
    assert ordre.index(TraceModeleMixin) < ordre.index(MainPasseeMixin) < ordre.index(RepriseSansFluxMixin)

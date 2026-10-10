"""[.mark] Does an OpenAI-compatible model (Scaleway) get the settings the screen shows?

The question this file answers, and only this one:

    On the ``openai`` provider (any OpenAI-compatible address, Scaleway first), do the
    sampling settings, the reasoning effort and the prompt cache key set on screen reach
    the request that leaves the machine, does the model-delay guard of the outage module
    apply -- and does a request with nothing set stay exactly as before?

Why it exists
-------------
Chantier ``agent-leger-greffier``, lot C (B7 and B9 of ``reparation-globale``). Until
then the ``openai`` branch of the factory hardcoded ``temperature=0.1``, sent
``reasoning_effort`` to "gpt-5" models only, and had neither the delay guard nor the
cache key, all of which lived in ``DograhMistralLLMService``. On Scaleway, gpt-oss-120b
reasoned at its default level, 2 627 output tokens over 8 turns, voice 2 to 6 s late
(run 1055); a "Reasoning: low" line in the prompt was ignored (run 1056).
"""

import inspect
from types import SimpleNamespace

from api.services.configuration.registry import OpenAILLMService as OpenAIConfig
from api.services.pipecat.service_factory import (
    DograhOpenAILLMService,
    create_llm_service,
    stamp_prompt_cache_key,
    stamp_sampling_settings,
)

CONTEXTE = {
    "messages": [{"role": "user", "content": "bonjour"}],
    "tools": [],
    "tool_choice": None,
}
SCALEWAY = "https://api.scaleway.ai/v1"


def _openai(model="gpt-oss-120b", **reglages):
    return SimpleNamespace(
        llm=OpenAIConfig(
            api_key="cle-de-test-jamais-envoyee",
            model=model,
            base_url=SCALEWAY,
            **reglages,
        )
    )


def _parametres(user_config, **options) -> dict:
    return create_llm_service(user_config, **options).build_chat_completion_params(
        CONTEXTE
    )


def _acceptes_par_le_client() -> set[str]:
    from openai.resources.chat.completions import AsyncCompletions

    return set(inspect.signature(AsyncCompletions.create).parameters)


def test_le_service_porte_le_garde_du_delai():
    service = create_llm_service(_openai())
    assert isinstance(service, DograhOpenAILLMService)
    # The outage module plugs its delay only on a service that declares it.
    assert hasattr(service, "mark_delai_modele_s")


def test_les_reglages_d_echantillonnage_partent():
    p = _parametres(
        _openai(
            temperature=0.4,
            top_p=0.9,
            seed=7,
            max_tokens=300,
            frequency_penalty=0.2,
            presence_penalty=0.1,
        )
    )
    assert (p["temperature"], p["top_p"], p["seed"], p["max_tokens"]) == (
        0.4,
        0.9,
        7,
        300,
    )
    assert (p["frequency_penalty"], p["presence_penalty"]) == (0.2, 0.1)


def test_le_raisonnement_part_dans_la_requete():
    p = _parametres(_openai(reasoning_effort="low"))
    assert p["reasoning_effort"] == "low"
    # Gate of 2026-09-11: a keyword the client library refuses silences the agent.
    assert set(p) <= _acceptes_par_le_client() | {"extra_body"}


def test_la_cle_de_cache_part_si_elle_est_demandee():
    p = _parametres(_openai(prompt_cache=True), prompt_cache_key="mark-wf-46")
    assert p["prompt_cache_key"] == "mark-wf-46"
    assert "prompt_cache_key" in _acceptes_par_le_client()


def test_rien_regle_requete_inchangee():
    p = _parametres(_openai(), prompt_cache_key="mark-wf-46")
    assert p["temperature"] == 0.1
    assert "reasoning_effort" not in p
    assert "prompt_cache_key" not in p


def test_gpt5_garde_son_raisonnement_minimal_sauf_reglage():
    assert _parametres(_openai(model="gpt-5-mini"))["reasoning_effort"] == "minimal"
    assert (
        _parametres(_openai(model="gpt-5-mini", reasoning_effort="low"))[
            "reasoning_effort"
        ]
        == "low"
    )


def test_l_estampille_dit_les_reglages_joues():
    config = _openai(temperature=0.3, reasoning_effort="low", prompt_cache=True)
    estampille = stamp_sampling_settings({}, config.llm)
    assert estampille["llm_sampling"]["temperature"] == 0.3
    assert estampille["llm_sampling"]["reasoning_effort"] == "low"
    assert (
        stamp_prompt_cache_key({}, config.llm, "mark-wf-46")["llm_prompt_cache_key"]
        == "mark-wf-46"
    )
    # No key asked for: no stamp claiming one.
    assert stamp_prompt_cache_key({}, _openai().llm, "mark-wf-46") == {}


def test_les_champs_sont_a_l_ecran():
    proprietes = OpenAIConfig.model_json_schema()["properties"]
    for champ in (
        "temperature",
        "top_p",
        "seed",
        "max_tokens",
        "reasoning_effort",
        "prompt_cache",
    ):
        assert "mark_groupe" in proprietes[champ], champ

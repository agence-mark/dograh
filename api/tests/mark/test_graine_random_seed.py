"""[.mark] The seed must reach Mistral instead of silencing the agent.

The question this file answers, and it answers only this one:

    When a sampling setting is filled in, does the agent still answer?

⛔ That is deliberately NOT the question the sibling file answers. The
settings file proves a filled-in setting reaches the request builder. This one
proves the request the builder produces can actually be sent.

Why it exists
-------------
Measured on 2026-09-11, at the first bench run with a seed. The setting was
exposed on screen the day before, plumbed end to end, stamped on every run,
and covered by tests that were all green. The agent still went mute:

    Error during completion: AsyncCompletions.create()
    got an unexpected keyword argument 'random_seed'

Mistral wants ``random_seed`` and pipecat names it correctly, but the call
goes out through OpenAI's client library, which refuses a keyword it does not
know and rejects the request before it leaves the machine. Four S7 replays
(runs 112-115) produced the greeting line and nothing else, zero tokens.

🚨 The error is NOT fatal, so nothing surfaces: the agent stays up and says
nothing. At the keyboard that is visible at once. On the phone it is a caller
talking into the void, with nothing in the call report to say so.

🔑 Why the green tests missed it: the closest one asserts that the string
``random_seed`` appears in the source of the request builder. It did appear.
Reading the code is not running it -- the same gap as the service overrides
the day before, where nine tests passed without crossing the route that
writes. So this test does not read anything: it checks the produced parameters
against what the client will actually accept.
"""

import inspect

import pytest

# Shape of what the engine hands the builder; only the keys it reads.
CONTEXTE = {
    "messages": [{"role": "user", "content": "bonjour"}],
    "tools": [],
    "tool_choice": None,
}


def _parametres(**reglages) -> dict:
    """Build the request parameters exactly as a live call would.

    🔑 Deliberately through the factory rather than by instantiating a class
    by hand: what matters is the service the engine actually gets, not the one
    the test picked. Naming the class here would let the factory drift back to
    an uncorrected one with every test still green -- which is the shape of
    failure this file exists to catch.
    """
    from api.services.configuration.registry import ServiceProviders
    from api.services.pipecat.service_factory import (
        create_llm_service_from_provider,
    )

    service = create_llm_service_from_provider(
        ServiceProviders.MISTRAL.value,
        "mistral-large-2512",
        "cle-de-test-jamais-envoyee",
        sampling=dict(reglages),
    )
    return service.build_chat_completion_params(CONTEXTE)


def _acceptes_par_le_client() -> set[str]:
    """Every keyword OpenAI's client will accept on a chat completion.

    This is the gate that rejected the call: the SDK raises TypeError on any
    keyword outside its signature, before any network call. Reading the
    signature is reading the same rule the SDK enforces, not a copy of it.
    """
    from openai.resources.chat.completions import AsyncCompletions

    return set(inspect.signature(AsyncCompletions.create).parameters)


def test_la_graine_remplie_produit_une_requete_que_le_client_accepte():
    """The failure of 2026-09-11, at the level where it hurt: the agent went mute."""
    refuses = set(_parametres(seed=1)) - _acceptes_par_le_client()
    assert not refuses, (
        f"the request carries parameters OpenAI's client refuses: {sorted(refuses)}. "
        f"The SDK raises TypeError before sending, the error is non-fatal, and the "
        f"agent answers nothing at all."
    )


def test_aucun_reglage_ne_produit_un_parametre_refuse():
    """Same gate, for the five other settings and any future one.

    The point is not to re-test the seed. It is that the next setting exposed
    on screen cannot reach production untested: whatever is filled in, the
    request must stay sendable.
    """
    tous = {
        "temperature": 0.7,
        "seed": 12345,
        "max_tokens": 200,
        "top_p": 0.9,
        "frequency_penalty": 0.5,
        "presence_penalty": 0.5,
    }
    refuses = set(_parametres(**tous)) - _acceptes_par_le_client()
    assert not refuses, (
        f"with every setting filled in, the request carries parameters OpenAI's "
        f"client refuses: {sorted(refuses)}."
    )


def test_la_graine_part_bien_dans_la_requete():
    """Sendable is not enough: it must still be the seed Mistral reads.

    Without this, dropping the parameter entirely would turn the two tests
    above green while the bench went back to being irreproducible.
    """
    params = _parametres(seed=4242)
    corps = params.get("extra_body") or {}
    assert corps.get("random_seed") == 4242, (
        f"the seed no longer reaches Mistral: extra_body={corps!r}. Mistral reads "
        f"'random_seed' and refuses 'seed' (HTTP 422, verified 2026-09-11), so it "
        f"travels in extra_body, which the client passes through untouched."
    )


@pytest.mark.parametrize("graine", [0, 1, 12345])
def test_toute_graine_valide_part_y_compris_zero(graine):
    """Zero is a seed like any other, and it was silently dropped.

    The screen accepts 0 (``ge=0``) but the builder only sent the parameter
    when it was truthy, so a bench pinned to seed 0 drew afresh every time and
    nothing said so. Found by reading the code on 2026-09-11, never measured:
    the agent was mute at every seed.
    """
    corps = _parametres(seed=graine).get("extra_body") or {}
    assert corps.get("random_seed") == graine, (
        f"seed {graine} never reaches the request: extra_body={corps!r}. A setting "
        f"the screen accepts and the request drops is a setting we believe we hold."
    )

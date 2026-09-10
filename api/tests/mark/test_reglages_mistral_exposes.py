"""[.mark] Non-regression test for the six Mistral sampling settings.

The question this file answers, and it answers only this one:

    Are the six sampling settings declared on the Mistral configuration, and
    do the ones that are filled in actually reach the request sent to Mistral?

⛔ Read that scope literally. This file does NOT prove that a given value
improves the agent. It proves the value is not silently dropped between the
screen and the wire, which is exactly the failure that was there before:
``temperature`` was written as a literal ``0.1`` in the factory, and the five
other settings were never sent at all.

Why it exists
-------------
Three settings that command the quality of the agent were neither on screen
nor in the request: the temperature nobody chose, ``max_tokens``, and the
random seed. The seed is the one that hurts the most -- without it the test
bench is not reproducible, and a verdict measured once is an example, not a
measurement.

The screen is generated from the Pydantic schema, so declaring the fields is
what puts them on screen. That is why this file asserts on the schema as well
as on the request: a field that leaves the schema disappears from the screen
without breaking anything else.

What "not sent" looks like
--------------------------
``build_chat_completion_params`` always puts ``temperature``, ``top_p``,
``max_tokens`` and both penalties in the returned dict. What decides whether
they leave the machine is their VALUE: the OpenAI client strips any argument
whose value is its own ``NOT_GIVEN`` sentinel. So "this setting is not sent"
is asserted as "its value is an ``openai.NotGiven``", never as "the key is
absent". ``seed`` is the exception: Mistral renames it ``random_seed`` and the
upstream code adds that key only when a seed is set, so there the assertion is
on the key itself.

⛔ Expected RED before the patch, and it fails on the schema first: the six
fields do not exist yet on ``MistralLLMConfiguration``. That is the intended
failure -- a rouge that names what is missing.
"""

from types import SimpleNamespace

import pytest
from openai import NotGiven as OpenAINotGiven
from pydantic import TypeAdapter, ValidationError

from api.services.configuration.registry import (
    MISTRAL_SAMPLING_FIELDS,
    LLMConfig,
    MistralLLMConfiguration,
)
from api.services.pipecat.service_factory import create_llm_service

# The six settings, in the order they are declared. ⛔ `top_k` and the system
# instruction are deliberately NOT here: Mistral's request builder does not
# send them, and exposing a setting without effect is worse than not exposing
# it at all (decision of 2026-09-10).
LES_SIX = (
    "temperature",
    "seed",
    "max_tokens",
    "top_p",
    "frequency_penalty",
    "presence_penalty",
)

# The value that runs today, written as a literal in the factory before this
# patch. Declaring it as the default is what makes it visible without changing
# a single call.
TEMPERATURE_ACTUELLE = 0.1


def _service(**reglages):
    """Build the Mistral service the runtime builds, through create_llm_service.

    Going through the public entry point rather than the lower-level helper is
    deliberate: routing a setting correctly in one and not the other is exactly
    how a green test hides a broken product.
    """
    user_config = SimpleNamespace(
        llm=MistralLLMConfiguration(api_key="mistral-key", **reglages)
    )
    return create_llm_service(user_config)


def _params(**reglages):
    """The parameters that would be handed to the Mistral endpoint."""
    return _service(**reglages).build_chat_completion_params(
        {"messages": [], "tools": [], "tool_choice": None}
    )


def _non_transmis(valeur) -> bool:
    """True when the OpenAI client would strip this argument from the request."""
    return isinstance(valeur, OpenAINotGiven)


# --------------------------------------------------------------------------- #
# 1. Declared -- which is what puts them on screen
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("champ", LES_SIX)
def test_le_reglage_est_declare_donc_affiche(champ):
    """The settings screen is generated from this schema, field by field.

    A field missing here is a field missing on screen, and a setting that is
    not on screen is one we have agreed never to touch.
    """
    proprietes = MistralLLMConfiguration.model_json_schema()["properties"]

    assert champ in proprietes, (
        f"'{champ}' is not declared on MistralLLMConfiguration, so it cannot "
        f"appear on the model settings screen."
    )
    assert proprietes[champ].get("description"), (
        f"'{champ}' carries no description: the screen would show a bare input "
        f"with no sentence explaining what it does."
    )


def test_la_temperature_garde_la_valeur_qui_tourne_aujourdhui():
    """0.1 is not a taste, it is the literal that was in the factory.

    Declaring it as the default is what makes this patch invisible in
    behaviour and visible on screen at the same time.
    """
    config = MistralLLMConfiguration(api_key="mistral-key")

    assert config.temperature == TEMPERATURE_ACTUELLE


@pytest.mark.parametrize("champ", [c for c in LES_SIX if c != "temperature"])
def test_les_cinq_autres_sont_absents_par_defaut(champ):
    """Absent means not sent, which means today's request, unchanged."""
    config = MistralLLMConfiguration(api_key="mistral-key")

    assert getattr(config, champ) is None


# --------------------------------------------------------------------------- #
# 2. Bounded -- the bounds come from Mistral's own OpenAPI schema
# --------------------------------------------------------------------------- #

# Source: https://docs.mistral.ai/openapi.yaml, schema ChatCompletionRequest,
# read on 2026-09-10. Not guessed, not copied from OpenAI: Mistral's ranges
# differ (temperature stops at 1.5, top_p excludes 0).
HORS_BORNES = [
    ("temperature", -0.1),
    ("temperature", 1.6),
    ("top_p", 0.0),  # exclusiveMinimum: 0
    ("top_p", 1.1),
    ("max_tokens", -1),
    ("seed", -1),
    ("frequency_penalty", -2.1),
    ("frequency_penalty", 2.1),
    ("presence_penalty", -2.1),
    ("presence_penalty", 2.1),
]

DANS_LES_BORNES = [
    ("temperature", 0.0),
    ("temperature", 1.5),
    ("top_p", 0.95),
    ("top_p", 1.0),
    ("max_tokens", 120),
    ("seed", 0),
    ("frequency_penalty", -2.0),
    ("presence_penalty", 2.0),
]


@pytest.mark.parametrize("champ,valeur", HORS_BORNES)
def test_une_valeur_hors_bornes_est_refusee(champ, valeur):
    """Refused at the door rather than by Mistral, mid-call, on a live line."""
    with pytest.raises(ValidationError):
        MistralLLMConfiguration(api_key="mistral-key", **{champ: valeur})


@pytest.mark.parametrize("champ,valeur", DANS_LES_BORNES)
def test_une_valeur_aux_bornes_est_acceptee(champ, valeur):
    """The bounds Mistral accepts must be reachable from the screen."""
    config = MistralLLMConfiguration(api_key="mistral-key", **{champ: valeur})

    assert getattr(config, champ) == valeur


def test_le_discriminateur_accepte_ce_que_lecran_enverra():
    """The screen POSTs a plain dict; it is parsed through the union."""
    config = TypeAdapter(LLMConfig).validate_python(
        {
            "provider": "mistral",
            "api_key": "mistral-key",
            "model": "mistral-large-2512",
            "temperature": 0.3,
            "seed": 424242,
            "max_tokens": 180,
            "top_p": 0.9,
            "frequency_penalty": 0.4,
            "presence_penalty": 0.2,
        }
    )

    assert isinstance(config, MistralLLMConfiguration)
    assert config.seed == 424242


# --------------------------------------------------------------------------- #
# 3. Transmitted -- the point of the whole patch
# --------------------------------------------------------------------------- #


def test_les_six_reglages_arrivent_dans_la_requete():
    """One assertion per setting, so a rouge names the one that was dropped."""
    params = _params(
        temperature=0.3,
        seed=424242,
        max_tokens=180,
        top_p=0.9,
        frequency_penalty=0.4,
        presence_penalty=0.2,
    )

    assert params["temperature"] == 0.3
    assert params["max_tokens"] == 180
    assert params["top_p"] == 0.9
    assert params["frequency_penalty"] == 0.4
    assert params["presence_penalty"] == 0.2
    # Mistral's own name for the seed. Upstream maps it; we only check it made
    # the trip, because a seed that never leaves is the exact bug that made
    # the test bench non-reproducible.
    assert params["random_seed"] == 424242


def test_la_temperature_configuree_remplace_le_zero_un_ecrit_en_dur():
    """The literal in the factory is what this patch removes.

    Without this test the field could be declared, stored, shown on screen and
    still overwritten by 0.1 on the way out -- configured then ignored, the
    worst of both worlds.
    """
    assert _params(temperature=0.9)["temperature"] == 0.9


# --------------------------------------------------------------------------- #
# 4. Nothing else moves -- the part that must stay boring
# --------------------------------------------------------------------------- #


def test_sans_reglage_la_requete_est_celle_daujourdhui():
    """Default configuration: 0.1 sent, the five others not sent at all."""
    params = _params()

    assert params["temperature"] == TEMPERATURE_ACTUELLE
    assert _non_transmis(params["max_tokens"])
    assert _non_transmis(params["top_p"])
    assert _non_transmis(params["frequency_penalty"])
    assert _non_transmis(params["presence_penalty"])
    assert "random_seed" not in params


def test_un_reglage_seul_nentraine_pas_les_autres():
    """Filling one field must not start sending the five others.

    This is the failure mode of a "collect everything and pass it on" patch:
    it is easy to hand Mistral a wall of None or 0 values and change the
    behaviour of every agent that never touched the screen.
    """
    params = _params(seed=7)

    assert params["random_seed"] == 7
    assert params["temperature"] == TEMPERATURE_ACTUELLE
    assert _non_transmis(params["max_tokens"])
    assert _non_transmis(params["top_p"])
    assert _non_transmis(params["frequency_penalty"])
    assert _non_transmis(params["presence_penalty"])


def test_les_autres_fournisseurs_ne_bougent_pas():
    """Thirteen other providers go through the same factory.

    OpenAI is the witness: it keeps its own hardcoded 0.1 and gains nothing,
    because nothing was declared on its configuration.
    """
    from api.services.configuration.registry import OpenAILLMService as OpenAIConfig

    service = create_llm_service(
        SimpleNamespace(llm=OpenAIConfig(api_key="openai-key"))
    )
    params = service.build_chat_completion_params(
        {"messages": [], "tools": [], "tool_choice": None}
    )

    assert params["temperature"] == 0.1
    assert _non_transmis(params["top_p"])
    assert _non_transmis(params["max_tokens"])
    assert _non_transmis(params["seed"])


# --------------------------------------------------------------------------- #
# 5. The collection point cannot drift away from the declaration
# --------------------------------------------------------------------------- #


def test_le_point_de_collecte_dit_la_meme_chose_que_la_declaration():
    """Two lists of field names is two chances to be right and one to be wrong.

    A field declared on the configuration but missing from the collection tuple
    is shown on screen, saved, and never sent -- and nothing complains.
    """
    assert MISTRAL_SAMPLING_FIELDS == LES_SIX

    declares = MistralLLMConfiguration.model_json_schema()["properties"]
    for champ in MISTRAL_SAMPLING_FIELDS:
        assert champ in declares


def test_le_point_de_collecte_ne_ramasse_que_ce_qui_part():
    """Every collected name must be one Mistral's request builder sends.

    Collecting a setting the builder ignores would put it on screen with no
    effect, which is precisely what the top_k decision refused.
    """
    import inspect

    from pipecat.services.mistral.llm import MistralLLMService

    source = inspect.getsource(MistralLLMService.build_chat_completion_params)

    for champ in MISTRAL_SAMPLING_FIELDS:
        # `seed` travels under Mistral's own name.
        attendu = "random_seed" if champ == "seed" else champ
        assert attendu in source, (
            f"'{champ}' is collected but never appears in Mistral's request "
            f"builder: it would be a setting on screen that changes nothing."
        )

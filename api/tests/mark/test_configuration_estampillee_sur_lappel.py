"""[.mark] Non-regression test for the sampling settings stamped on a run.

The question this file answers, and it answers only this one:

    Does a run record the sampling settings it was actually played with, on
    both paths -- the phone call and the keyboard bench?

Why it exists
-------------
Dograh already stamps the resolved providers and models on every run, which is
what lets a recorded call say which model produced it. The sampling settings
were missing from that stamp, so two runs of the same scenario at two
temperatures were indistinguishable after the fact.

That is not a documentation nicety. Measured on 2026-09-10, the same scenario
replayed four times at an identical configuration gave four different verdicts.
Until a run carries what it was played with, every comparison is an anecdote
being read as a measurement.

It also closes an asymmetry: a setting held on the agent is versioned with the
agent, while the same setting held on the organization is overwritten in place
with no history whatsoever. Stamped on the run, it is traceable either way.

⛔ What this file does NOT prove: that a real call reaches the database with
this stamp. It proves the value is built, and that both code paths call the
function that builds it. Playing a real call is a paid action and belongs to a
bench session, not to a test suite.
"""

import inspect

from api.services.configuration.registry import MistralLLMConfiguration
from api.services.pipecat.service_factory import stamp_sampling_settings


def _configuration_de_base() -> dict:
    """What Dograh stamps today, before ours is added to it."""
    return {
        "stt_provider": "deepgram",
        "stt_model": "nova-3",
        "tts_provider": "mistral",
        "tts_model": "voxtral-mini-tts-latest",
        "llm_provider": "mistral",
        "llm_model": "mistral-large-2512",
    }


def test_un_essai_porte_la_configuration_avec_laquelle_il_a_ete_joue():
    stampe = stamp_sampling_settings(
        _configuration_de_base(),
        MistralLLMConfiguration(
            api_key="mistral-key",
            temperature=0.3,
            seed=424242,
            max_tokens=180,
        ),
    )

    assert stampe["llm_sampling"] == {
        "temperature": 0.3,
        "seed": 424242,
        "max_tokens": 180,
    }


def test_ce_qui_etait_deja_estampille_reste_intact():
    """The stamp is added to what Dograh records, it does not replace it."""
    avant = _configuration_de_base()

    stampe = stamp_sampling_settings(dict(avant), MistralLLMConfiguration(api_key="k"))

    for cle, valeur in avant.items():
        assert stampe[cle] == valeur


def test_la_temperature_seule_suffit_a_declencher_lestampille():
    """The default configuration already carries a temperature, so every
    Mistral run says at least that much -- there is no silent case."""
    stampe = stamp_sampling_settings(
        _configuration_de_base(), MistralLLMConfiguration(api_key="k")
    )

    assert stampe["llm_sampling"] == {"temperature": 0.1}


def test_un_fournisseur_sans_reglage_declare_nest_pas_estampille_a_vide():
    """An empty dict would read as "played with no settings", which is false:
    OpenAI still receives the 0.1 written in the factory. Saying nothing is the
    honest answer until that provider declares its settings too."""
    from api.services.configuration.registry import OpenAILLMService as OpenAIConfig

    stampe = stamp_sampling_settings(
        _configuration_de_base(), OpenAIConfig(api_key="openai-key")
    )

    assert "llm_sampling" not in stampe


def test_les_deux_chemins_estampillent():
    """The phone call and the keyboard bench are two separate code paths.

    ⚠️ Read honestly: this reads the source of both runners rather than running
    them, because running either one needs the full stack. It catches the
    failure that actually threatens us -- one path being wired and the other
    forgotten, or an upstream refactor dropping the call from one of them.
    """
    from api.services.pipecat import run_pipeline
    from api.services.workflow import text_chat_runner

    for module in (run_pipeline, text_chat_runner):
        source = inspect.getsource(module)
        assert "stamp_sampling_settings(" in source, (
            f"{module.__name__} no longer stamps the sampling settings: runs "
            f"through this path would not say what they were played with."
        )

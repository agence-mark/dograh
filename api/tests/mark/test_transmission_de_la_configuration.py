"""[.mark] Does the pipeline actually hand the agent's configuration over?

The question this file answers, once, for every setting this fork exposes:

    Each collection point resolves an agent's settings correctly -- but is it
    CALLED with that agent's configuration, or with nothing?

Why a file of its own
---------------------
🚨 Measured three times on 2026-09-14, on three different lots. Dropping
``run_configs`` at the call site in ``run_pipeline.py`` left every other test
GREEN: the collection points are tested directly, so they keep answering
correctly about a configuration the pipeline no longer gives them. The agent
would then run on the defaults, whatever the client typed on screen, and
nothing anywhere would say so.

⛔ Asserted on the source text, and that is a deliberate limit, not laziness.
These calls live inside functions of several hundred lines that cannot be
invoked without a live pipeline, a database and a websocket. A weak assertion
that catches the failure beats a strong one that does not exist.

⚠️ What it does NOT catch: a call passing a configuration that is real but
wrong (another agent's, say). Nothing short of an end-to-end call would.
"""

import inspect
import re

import pytest

from api.services.pipecat import run_pipeline

# Every place the pipeline must hand the agent's configuration over, with what
# each one would silently fall back to if it did not.
TRANSMISSIONS = [
    (
        r"collecter_reglages_tour_de_parole\(run_configs\)",
        (
            "turn taking: the pause before the agent answers, the voice "
            "detector, Smart Turn, the aggregator timeouts"
        ),
    ),
    (
        r"run_configs=run_configs,",
        (
            "the voice settings and the incoming-noise filter reaching the "
            "transports and the voice factory"
        ),
    ),
    (
        # Upstream 4e6cb22b: the call monitor decides, the engine holds the
        # agent's prompts for it.
        r"engine\.regler_relances\(run_configs\)",
        "the idle prompts and how many times they are sent before hanging up",
    ),
    (
        # E1 (25/09/2026): the agent's configuration, with only the opening
        # sentence protection lifted when its greeting is interruptible.
        r"collecter_strategies_de_coupure\(\s*\{\*\*\(run_configs or \{\}\), "
        r"\"mute_until_first_bot_complete\": False\}\s*if accueil_ouvert\s*"
        r"else run_configs,",
        "which strategies may mute the caller's microphone",
    ),
    (
        r"stamp_pipeline_settings\(\s*runtime_configuration,\s*run_configs,",
        (
            "the record of which settings a call was played with -- without it "
            "an A/B result cannot be read back six weeks later"
        ),
    ),
    (
        r"creer_lecture_appelant\(\s*run_configs,\s*user_config\.stt,\s*adresse_etablissement,",
        (
            "reading the caller's numbers and towns: the two switches would be "
            "ignored, dictated numbers read in words again and stitched back "
            "wrong, postal codes said in words never checked, the agent's "
            "language and business address no longer taken into account"
        ),
    ),
    (
        r"lire_lexique_de_lappel\(run_configs, workflow\.organization_id\)",
        (
            "the organization's trade vocabulary: the agent's switch would be "
            "ignored and the vocabulary of another organization -- or none -- "
            "used to correct the names"
        ),
    ),
    (
        r'construire_liste_ecoutee\(\s*\(run_configs or \{\}\)\.get\("dictionary"\),\s*lexique_metier,\s*plafond_du_lexique\(',
        (
            "the terms the transcription listens for, within the ceiling of its "
            "provider: the ticked names of the trade would never reach Deepgram"
        ),
    ),
    (
        r"armer_filet_lexique\(\s*create_stt_service\(",
        (
            "the safety net of the list: a list the transcription refuses would "
            "make the call fall silent again, as on 2026-09-18"
        ),
    ),
    (
        r"injecter_lexique_propose\(\s*merged_call_context_vars,\s*termes_proposes\(lexique_metier\)",
        (
            "the names the business offers: the agent would no longer know "
            "which brands it may say the business offers"
        ),
    ),
    (
        r"reconnaissance_lexique=creer_reconnaissance_lexique\(\s*run_configs,\s*lexique_metier,",
        (
            "the step that corrects the trade names: the agent would read "
            "« édile camembert » again, and the towns would read it too"
        ),
    ),
    (
        r"lexique=lexique_metier,",
        (
            "the pronunciations: the voice would go on saying the brand names "
            "as they are spelled"
        ),
    ),
    (
        r'event_handler\("on_latency_breakdown"\)',
        (
            "the per-service latency breakdown: a total latency says a call was "
            "slow, it does not say where the time went"
        ),
    ),
]


@pytest.mark.parametrize(
    "appel,ce_qui_serait_perdu", TRANSMISSIONS, ids=lambda v: v[:40]
)
def test_le_pipeline_transmet_la_configuration(appel, ce_qui_serait_perdu):
    # ⚠️ Motifs, et non chaînes exactes : une assertion qui dépend de
    # l'indentation est un filet qu'un formateur décroche sans bruit. Relevé
    # par la relecture du 14/09.
    source = inspect.getsource(run_pipeline)
    assert re.search(appel, source), (
        f"The pipeline no longer hands the agent's configuration to this "
        f"collection point. What falls back to defaults, silently: "
        f"{ce_qui_serait_perdu}."
    )


def test_le_transport_navigateur_et_la_voix_recoivent_chacun_la_configuration():
    """``run_configs=run_configs`` has to appear at each site, not just once."""
    source = inspect.getsource(run_pipeline)
    assert len(re.findall(r"run_configs=run_configs,", source)) >= 3, (
        "Fewer call sites forward the configuration than expected: the voice "
        "factory, the browser transport and the telephony transports each need "
        "it. One of them is now running on defaults."
    )

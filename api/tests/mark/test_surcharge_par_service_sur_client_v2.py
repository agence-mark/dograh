"""[.mark] Non-regression test for a per-service override on a v2 client.

The question this file answers, and it answers only this one:

    Can an agent replace ONE service while still inheriting everything else
    from its client's configuration -- and does that inheritance stay alive
    when the client changes something?

Why it exists
-------------
Upstream never served this case. On their screens the two override formats
were exclusive: a client on the old format saw the per-service form, a client
on the new one saw the all-or-nothing replacement. We want both available to
the SAME client, because the offer is one organization per client and one
agent that changes its voice without freezing a copy of everything else.

The server side supports it -- the field-by-field merge is on the execution
path -- but "supports it" is a reading of the code, and a reading is not a
guarantee. This file turns it into one.

🚨 The part that was NOT supported, and that this file fixes
------------------------------------------------------------
Saving the organization's model configuration runs a migration over every
agent in that organization, which converts each per-service override into a
complete copy and then deletes it. That migration is not a one-off: it runs on
EVERY save of the organization configuration.

So a per-service override was silently converted into a frozen copy the next
time anyone touched the client's configuration -- and from that moment the
agent stopped inheriting anything. Nothing on any screen said so.

A per-service override written on purpose now carries a marker, and the
migration leaves marked overrides alone. Their own migration path, for the
legacy overrides it was built for, is unchanged.
"""

from pathlib import Path

import pytest

from api.schemas.ai_model_configuration import (
    BYOKAIModelConfiguration,
    BYOKPipelineAIModelConfiguration,
    OrganizationAIModelConfigurationV2,
    compile_ai_model_configuration_v2,
)
from api.services.configuration.ai_model_configuration import (
    DELIBERATE_PER_SERVICE_OVERRIDE_KEY,
    WORKFLOW_MODEL_CONFIGURATION_V2_OVERRIDE_KEY,
    migrate_workflow_configuration_model_override_to_v2,
)
from api.services.configuration.registry import (
    DeepgramSTTConfiguration,
    MistralLLMConfiguration,
    MistralTTSConfiguration,
)
from api.services.configuration.resolve import resolve_effective_config

# The marker the agent screen writes next to a deliberate per-service override.
# Written as a literal on purpose: this file is one of the two sides of the
# contract, so importing the constant here would make the comparison below
# compare a value to itself.
MARQUEUR = "mark_per_service_override"


def _client_au_nouveau_format(modele="mistral-medium-latest") -> OrganizationAIModelConfigurationV2:
    """One client, configured the way .mark configures a client."""
    return OrganizationAIModelConfigurationV2(
        mode="byok",
        byok=BYOKAIModelConfiguration(
            mode="pipeline",
            pipeline=BYOKPipelineAIModelConfiguration(
                llm=MistralLLMConfiguration(api_key="cle-client", model=modele, temperature=0.2),
                tts=MistralTTSConfiguration(api_key="cle-client", voice="fr_marie_neutral"),
                stt=DeepgramSTTConfiguration(api_key="cle-client", model="nova-3-general"),
            ),
        ),
    )


# The agent replaces the voice, and nothing else.
SURCHARGE_VOIX_SEULE = {
    "tts": {
        "provider": "mistral",
        "api_key": "cle-client",
        "voice": "fr_marie_curious",
    }
}


# --------------------------------------------------------------------------- #
# 1. One service replaced, the rest inherited
# --------------------------------------------------------------------------- #


def test_lagent_remplace_la_voix_et_herite_de_tout_le_reste():
    client = compile_ai_model_configuration_v2(_client_au_nouveau_format())

    effective = resolve_effective_config(client, SURCHARGE_VOIX_SEULE)

    # What the agent changed.
    assert effective.tts.voice == "fr_marie_curious"
    # What it must still inherit, field by field -- a rouge here names exactly
    # which part of the client's configuration stopped being inherited.
    assert effective.llm.model == "mistral-medium-latest"
    assert effective.llm.temperature == 0.2
    assert effective.stt.model == "nova-3-general"
    assert effective.tts.model == "voxtral-mini-tts-latest"


def test_le_client_reste_intact_quand_lagent_surcharge():
    """The client's own configuration is never mutated by an agent's override."""
    client = compile_ai_model_configuration_v2(_client_au_nouveau_format())

    resolve_effective_config(client, SURCHARGE_VOIX_SEULE)

    assert client.tts.voice == "fr_marie_neutral"


def test_lheritage_suit_le_client_quand_il_change_de_modele():
    """The whole point of inheriting rather than copying.

    A complete override would have frozen the model of the day it was written.
    """
    apres = compile_ai_model_configuration_v2(
        _client_au_nouveau_format(modele="mistral-large-2512")
    )

    effective = resolve_effective_config(apres, SURCHARGE_VOIX_SEULE)

    assert effective.llm.model == "mistral-large-2512"
    assert effective.tts.voice == "fr_marie_curious"


def test_les_reglages_du_client_traversent_la_surcharge():
    """The six settings live on the client. An agent that overrides only its
    voice must still be played with the client's sampling settings."""
    client = compile_ai_model_configuration_v2(_client_au_nouveau_format())
    client.llm = client.llm.model_copy(update={"seed": 424242, "max_tokens": 180})

    effective = resolve_effective_config(client, SURCHARGE_VOIX_SEULE)

    assert effective.llm.seed == 424242
    assert effective.llm.max_tokens == 180


# --------------------------------------------------------------------------- #
# 2. The migration, which used to eat the override on the next save
# --------------------------------------------------------------------------- #


def test_une_surcharge_deliberee_survit_a_lenregistrement_du_client():
    """⛔ Without the marker this is destructive, and destructive in silence.

    Saving the organization configuration converts the override into a frozen
    copy and deletes it. The agent then stops inheriting, and no screen says a
    word about it.
    """
    configurations = {
        "ambient_noise_configuration": {"enabled": False},
        "model_overrides": SURCHARGE_VOIX_SEULE,
        MARQUEUR: True,
    }

    migrees, change = migrate_workflow_configuration_model_override_to_v2(
        configurations,
        compile_ai_model_configuration_v2(_client_au_nouveau_format()),
    )

    assert change is False
    assert migrees["model_overrides"] == SURCHARGE_VOIX_SEULE
    assert WORKFLOW_MODEL_CONFIGURATION_V2_OVERRIDE_KEY not in migrees


def test_leur_migration_dorigine_nest_pas_touchee():
    """An override with no marker is one of theirs, and keeps their behaviour.

    We are going against their interface, not against their product: an agent
    they migrated must still migrate exactly as before.
    """
    configurations = {
        "ambient_noise_configuration": {"enabled": False},
        "model_overrides": SURCHARGE_VOIX_SEULE,
    }

    migrees, change = migrate_workflow_configuration_model_override_to_v2(
        configurations,
        compile_ai_model_configuration_v2(_client_au_nouveau_format()),
    )

    assert change is True
    assert "model_overrides" not in migrees
    assert WORKFLOW_MODEL_CONFIGURATION_V2_OVERRIDE_KEY in migrees


@pytest.mark.parametrize("valeur", [False, None])
def test_le_marqueur_ne_protege_que_sil_dit_oui(valeur):
    """A marker left over as false must not accidentally freeze the migration."""
    configurations = {"model_overrides": SURCHARGE_VOIX_SEULE, MARQUEUR: valeur}

    _, change = migrate_workflow_configuration_model_override_to_v2(
        configurations, compile_ai_model_configuration_v2(_client_au_nouveau_format())
    )

    assert change is True


def test_lecran_et_le_serveur_parlent_du_meme_marqueur():
    """Two files, two languages, one string. Nothing else ties them together.

    A rename on either side would silently switch the protection off: the
    screen would keep writing a key nobody reads, and the next save of the
    client's configuration would eat the override again.
    """
    assert DELIBERATE_PER_SERVICE_OVERRIDE_KEY == MARQUEUR

    composant = (
        Path(__file__).resolve().parents[3]
        / "ui"
        / "src"
        / "components"
        / "mark"
        / "PerServiceModelOverride.tsx"
    )
    assert composant.exists(), f"the agent screen block is gone: {composant}"
    assert f'"{MARQUEUR}"' in composant.read_text(encoding="utf-8"), (
        "the agent screen no longer writes the marker: an override saved there "
        "would be converted into a frozen copy on the next save of the client's "
        "configuration."
    )

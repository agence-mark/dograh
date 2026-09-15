"""[.mark] Non-regression test for duplicating an agent.

The question this file answers, and only this one:

    Does the copy carry the original's ``workflow_configurations`` intact --
    the per-service override marker and every Pipecat setting included?

Why it exists
-------------
Nothing tested duplication before today (checked 2026-09-14), and the button
added on the agent list makes it a routine gesture: an A/B branch IS a copy of
the agent. A copy that quietly dropped a setting would produce two branches
that differ by something nobody configured, and the bench result would be read
as if it came from the setting under test.

⛔ Duplication is a WRITE path for the configuration, and a write path nobody
guards is where settings go to disappear -- the lesson of the patch of
2026-09-10, where saving an agent wiped its per-service overrides on every
save, in silence.

⚠️ What this file does NOT prove: that the copy runs. It asserts what the
duplication hands the database, with the database mocked out.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from api.services.workflow.duplicate import duplicate_workflow

ORGANISATION = 11
UTILISATEUR = 3

# An agent configured the way a real .mark agent is: a marked per-service
# override, the Pipecat settings of this patch, and the ambient noise block.
CONFIGURATION = {
    "mark_per_service_override": True,
    "model_overrides": {
        "tts": {"provider": "mistral", "voice": "fr_marie_neutral"},
    },
    "user_speech_timeout": 1.2,
    "vad_stop_secs": 0.35,
    "audio_in_noise_filter": "rnnoise",
    "tts_markdown_filter_enabled": True,
    "tts_replacements": ["SAV:S. A. V."],
    "mute_always": False,
    "user_idle_max_prompts": 2,
    "conversion_nombres_transcription": True,
    "horaires_ouverture": "lundi : fermé\nmardi : 10:00-12:30 et 14:00-18:30\n",
    "ambient_noise_configuration": {"enabled": False, "volume": 0.3},
}

DEFINITION = {"nodes": [], "edges": []}


async def _dupliquer(configuration):
    """Run the duplication with the database mocked, and report the write."""
    source = SimpleNamespace(
        id=1,
        name="Agent de test",
        released_definition=SimpleNamespace(
            workflow_json=DEFINITION,
            workflow_configurations=configuration,
            template_context_variables={"ville": "Beauvais"},
        ),
    )
    copie = SimpleNamespace(id=2)

    with (
        patch("api.services.workflow.duplicate.db_client") as base,
    ):
        base.get_workflow = AsyncMock(side_effect=[source, copie])
        base.get_draft_version = AsyncMock(return_value=None)
        base.create_workflow = AsyncMock(return_value=copie)
        base.update_workflow = AsyncMock(return_value=copie)
        base.sync_triggers_for_workflow = AsyncMock()

        await duplicate_workflow(
            workflow_id=1, organization_id=ORGANISATION, user_id=UTILISATEUR
        )
        return base.update_workflow.await_args


@pytest.mark.asyncio
async def test_la_copie_garde_la_configuration_a_lidentique():
    ecriture = await _dupliquer(CONFIGURATION)
    assert ecriture is not None, (
        "The duplication wrote no configuration at all. The copy would start "
        "on the defaults, and an A/B branch made from it would differ from its "
        "original by every setting that was configured."
    )
    assert ecriture.kwargs["workflow_configurations"] == CONFIGURATION


@pytest.mark.asyncio
async def test_la_copie_garde_le_marqueur_de_surcharge_par_service():
    """⛔ The marker is what keeps the override from being frozen into a copy.

    Lost here, the duplicated agent stops inheriting from its client the first
    time it is saved -- and nothing on any screen would say so.
    """
    ecrite = (await _dupliquer(CONFIGURATION)).kwargs["workflow_configurations"]
    assert ecrite["mark_per_service_override"] is True
    assert ecrite["model_overrides"] == CONFIGURATION["model_overrides"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "reglage",
    [
        "user_speech_timeout",
        "vad_stop_secs",
        "audio_in_noise_filter",
        "tts_markdown_filter_enabled",
        "tts_replacements",
        "user_idle_max_prompts",
        "conversion_nombres_transcription",
        "horaires_ouverture",
    ],
)
async def test_chaque_reglage_pipecat_survit_a_la_copie(reglage):
    ecrite = (await _dupliquer(CONFIGURATION)).kwargs["workflow_configurations"]
    assert ecrite[reglage] == CONFIGURATION[reglage]


@pytest.mark.asyncio
async def test_la_copie_est_independante_de_loriginal():
    """A deep copy, not a shared reference.

    Two A/B branches sharing one dictionary would move together, and the bench
    would compare an agent with itself without anything looking wrong.
    """
    ecrite = (await _dupliquer(CONFIGURATION)).kwargs["workflow_configurations"]
    ecrite["user_speech_timeout"] = 99
    ecrite["model_overrides"]["tts"]["voice"] = "autre"
    assert CONFIGURATION["user_speech_timeout"] == 1.2
    assert CONFIGURATION["model_overrides"]["tts"]["voice"] == "fr_marie_neutral"


@pytest.mark.asyncio
async def test_un_agent_sans_configuration_se_duplique_sans_erreur():
    """The plain case, which must not raise on its way through the copy."""
    ecriture = await _dupliquer(None)
    # Nothing to copy but the context variables, which are still written.
    assert ecriture.kwargs["workflow_configurations"] is None

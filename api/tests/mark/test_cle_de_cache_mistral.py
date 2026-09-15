"""[.mark] Does every conversation request to Mistral carry the agent's cache key?

The question this file answers, and only this one:

    On a Mistral agent, does the request that actually leaves the machine name
    the agent's prompt cache key -- and does nothing change for anyone else?

Why it exists
-------------
Measured on 2026-09-15: Mistral serves the start of a request from its cache
only when the request names a ``prompt_cache_key``. Without one, 0 input tokens
from the cache; with one, 2,560 of 2,624 and 160 ms less to the first token. On
five real calls, 8 % of input tokens came from the cache. The fork never sent a
key, and none of the six Mistral settings on screen can carry one: a patch.

The three levels, stated honestly
---------------------------------
1. The request builder: parameters produced by the factory, compared with what
   the client library accepts (the gate that silenced the agent on 2026-09-11).
2. The body that is SENT: OpenAI's client run against an intercepted transport.
   ``extra_body`` is merged by that library; asserting on the parameters alone
   would trust it.
3. The wiring: the keyboard runner RUN up to the engine (key handed to the
   factory, stamp persisted); the phone runner asserted on its source, because
   running it needs a live pipeline.

⚠️ What it does NOT cover, and why that is accepted
---------------------------------------------------
For Mistral, variable extraction and context summarisation reuse the
conversation service object itself (``variable_extraction_llm = ... or llm``),
and ``run_inference`` goes through the same request builder: those requests
carry the key too. Decision D6 is kept at the level of the call sites, where it
can be kept without building a second service. A key changes no answer.
"""

import inspect
import json
import re
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from api.services.configuration.registry import MistralLLMConfiguration
from api.services.configuration.registry import OpenAILLMService as OpenAIConfig
from api.services.pipecat import run_pipeline
from api.services.pipecat.service_factory import (
    cle_de_cache,
    create_llm_service,
    create_llm_service_from_provider,
)
from api.services.workflow import text_chat_runner
from api.services.workflow.text_chat_runner import execute_text_chat_pending_turn

CONTEXTE = {
    "messages": [{"role": "user", "content": "bonjour"}],
    "tools": [],
    "tool_choice": None,
}


def _mistral(**reglages):
    return SimpleNamespace(
        llm=MistralLLMConfiguration(
            api_key="cle-de-test-jamais-envoyee", model="mistral-large-2512", **reglages
        )
    )


def _parametres(user_config, **options) -> dict:
    """Through ``create_llm_service``, the entry point both runners call."""
    return create_llm_service(user_config, **options).build_chat_completion_params(CONTEXTE)


def _acceptes_par_le_client() -> set[str]:
    from openai.resources.chat.completions import AsyncCompletions

    return set(inspect.signature(AsyncCompletions.create).parameters)


# --------------------------------------------------------------------------- #
# The key itself
# --------------------------------------------------------------------------- #


def test_la_cle_est_celle_de_lagent_et_ne_porte_que_son_numero():
    """D1. ⛔ The only input is the agent id: a key travels to Mistral."""
    assert cle_de_cache(6) == "mark-wf-6"
    assert list(inspect.signature(cle_de_cache).parameters) == ["workflow_id"]


# --------------------------------------------------------------------------- #
# 1. The request builder
# --------------------------------------------------------------------------- #


def test_une_requete_mistral_porte_la_cle_de_lagent():
    params = _parametres(_mistral(), prompt_cache_key=cle_de_cache(6))
    assert params["extra_body"]["prompt_cache_key"] == "mark-wf-6"
    refuses = set(params) - _acceptes_par_le_client()
    assert not refuses, (
        f"the request carries parameters OpenAI's client refuses: {sorted(refuses)}. "
        f"The SDK raises before sending, the error is non-fatal, the agent is mute."
    )


def test_la_graine_et_la_cle_partent_ensemble():
    """Both travel in ``extra_body``: one must not overwrite the other."""
    params = _parametres(_mistral(seed=0), prompt_cache_key="mark-wf-6")
    assert params["extra_body"] == {"random_seed": 0, "prompt_cache_key": "mark-wf-6"}


@pytest.mark.parametrize("sans_cle", [{}, {"prompt_cache_key": None}, {"prompt_cache_key": ""}])
def test_sans_cle_la_requete_mistral_est_celle_daujourdhui(sans_cle):
    """🔒 Compared with the upstream builder on the same service: with no seed,
    the .mark subclass added nothing to it before this patch."""
    from pipecat.services.mistral.llm import MistralLLMService

    service = create_llm_service(_mistral(), **sans_cle)
    params = service.build_chat_completion_params(CONTEXTE)
    assert "extra_body" not in params
    assert params == MistralLLMService.build_chat_completion_params(service, CONTEXTE)


@pytest.mark.parametrize(
    "fabrique",
    [
        lambda cle: create_llm_service(
            SimpleNamespace(llm=OpenAIConfig(api_key="openai-key")), prompt_cache_key=cle
        ),
        lambda cle: create_llm_service_from_provider(
            "openai", "gpt-4.1", "openai-key", prompt_cache_key=cle
        ),
    ],
)
def test_un_autre_fournisseur_ne_recoit_rien(fabrique):
    """D5: Mistral only. OpenAI is the witness for the thirteen others."""
    avec = fabrique("mark-wf-6").build_chat_completion_params(CONTEXTE)
    sans = fabrique(None).build_chat_completion_params(CONTEXTE)
    assert avec == sans
    assert "mark-wf-6" not in repr(avec)


# --------------------------------------------------------------------------- #
# 2. The body actually sent
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_le_corps_reellement_envoye_porte_la_cle():
    import httpx
    from pipecat.processors.aggregators.llm_context import LLMContext

    service = create_llm_service(_mistral(seed=3), prompt_cache_key=cle_de_cache(6))
    envoyes = []

    def repondre(requete: httpx.Request) -> httpx.Response:
        envoyes.append((str(requete.url), json.loads(requete.content)))
        return httpx.Response(
            200, headers={"content-type": "text/event-stream"}, content=b"data: [DONE]\n\n"
        )

    # The service's own OpenAI client, with only its network layer replaced.
    service._client._client = httpx.AsyncClient(transport=httpx.MockTransport(repondre))
    service._settings.system_instruction = "Tu es Marie."
    flux = await service.get_chat_completions(
        LLMContext(messages=[{"role": "user", "content": "bonjour"}])
    )
    await flux.close()

    assert len(envoyes) == 1
    adresse, corps = envoyes[0]
    assert adresse.startswith("https://api.eu.mistral.ai/v1/chat/completions")
    assert corps["prompt_cache_key"] == "mark-wf-6"
    assert corps["random_seed"] == 3
    assert "extra_body" not in corps


# --------------------------------------------------------------------------- #
# 3. The wiring
# --------------------------------------------------------------------------- #


def _appels(source: str, fonction: str) -> list[tuple[str, str]]:
    """Every ``fonction(...)`` call: (what it is assigned to, full call text)."""
    trouves = []
    for m in re.finditer(rf"\b{fonction}\(", source):
        profondeur, i = 0, m.end() - 1
        while True:
            profondeur += {"(": 1, ")": -1}.get(source[i], 0)
            if profondeur == 0:
                break
            i += 1
        debut_ligne = source.rfind("\n", 0, m.start()) + 1
        trouves.append((source[debut_ligne : m.start()].strip(), source[m.start() : i + 1]))
    return trouves


@pytest.mark.parametrize(
    "module,autres_attendus",
    [
        # phone: realtime side channel, variable extraction, voicemail
        (run_pipeline, {"inference_llm =", "", "voicemail_llm ="}),
        # keyboard: variable extraction
        (text_chat_runner, {""}),
    ],
)
def test_seul_lappel_de_conversation_recoit_la_cle(module, autres_attendus):
    """D6 in both directions, and counted: the conversation call gets the key,
    every other call site does not, and no call site is left unclassified."""
    appels = _appels(inspect.getsource(module), "create_llm_service")
    conversation = [texte for cible, texte in appels if cible == "llm ="]
    autres = [(cible, texte) for cible, texte in appels if cible != "llm ="]

    assert len(conversation) == 1, f"{module.__name__}: {len(conversation)} conversation calls"
    assert "prompt_cache_key=cle_de_cache(workflow_id)" in conversation[0]
    assert {cible for cible, _ in autres} == autres_attendus
    for cible, texte in autres:
        assert "prompt_cache_key" not in texte, f"{module.__name__}: key handed to '{cible}'"
    assert len(appels) == 1 + len(autres_attendus)


def test_le_chemin_telephonique_estampille_la_cle_hors_temps_reel():
    source = inspect.getsource(run_pipeline)
    appels = _appels(source, "stamp_prompt_cache_key")
    assert len(appels) == 1
    assert "cle_de_cache(workflow_id)" in appels[0][1]
    # INSIDE the non-realtime block, not merely after it: moved out one indent,
    # a realtime call with a Mistral side channel would stamp a key that never
    # left (independent review of 2026-09-16). The block is cut at the first
    # line indented no deeper than the guard itself.
    garde = source.index("    if not is_realtime:\n", source.index("stamp_sampling_settings(runtime_configuration"))
    lignes = source[garde:].split("\n")
    bloc = [lignes[0]]
    for ligne in lignes[1:]:
        if ligne.strip() and len(ligne) - len(ligne.lstrip()) <= 4:
            break
        bloc.append(ligne)
    assert "stamp_prompt_cache_key(" in "\n".join(bloc), (
        "the cache-key stamp is no longer inside the non-realtime guard of run_pipeline"
    )


class _Arret(Exception):
    """Raised by the mocked engine: everything asserted here is decided before."""


def _definition() -> dict:
    return {
        "nodes": [
            {
                "id": "start",
                "type": "startCall",
                "position": {"x": 0, "y": 0},
                "data": {
                    "name": "Start",
                    "prompt": "Accueille.",
                    "is_start": True,
                    "allow_interrupt": False,
                    "add_global_prompt": False,
                    "greeting_type": "text",
                    "greeting": "Bonjour.",
                },
            },
            {
                "id": "end",
                "type": "endCall",
                "position": {"x": 0, "y": 200},
                "data": {
                    "name": "End",
                    "prompt": "Termine.",
                    "is_end": True,
                    "allow_interrupt": False,
                    "add_global_prompt": False,
                },
            },
        ],
        "edges": [
            {
                "id": "start-end",
                "source": "start",
                "target": "end",
                "data": {"label": "End Call", "condition": "Quand c'est fini."},
            }
        ],
    }


async def _jouer_au_clavier(llm_config):
    """Run the keyboard path of agent 6 up to the engine; return (persisted, factory calls)."""
    run = SimpleNamespace(
        workflow_id=6,
        name="essai",
        initial_context={"direction": "inbound"},
        definition=SimpleNamespace(workflow_json=_definition(), workflow_configurations={}),
        workflow=SimpleNamespace(organization_id=11, user=SimpleNamespace(id=1)),
    )
    agent = SimpleNamespace(id=6, organization_id=11, workflow_configurations={})
    fabrique = MagicMock()
    with (
        patch.object(text_chat_runner, "db_client") as base,
        patch.object(text_chat_runner, "PipecatEngine", MagicMock(side_effect=_Arret)),
        patch.object(text_chat_runner, "create_llm_service", fabrique),
        patch.object(text_chat_runner, "execute_pre_call_fetch", AsyncMock(return_value=None)),
        patch(
            "api.services.configuration.ai_model_configuration.get_effective_ai_model_configuration_for_workflow",
            AsyncMock(return_value=SimpleNamespace(llm=llm_config, embeddings=None)),
        ),
        patch(
            "api.services.managed_model_services.ensure_mps_correlation_id",
            AsyncMock(return_value=None),
        ),
    ):
        base.get_workflow_run_with_context = AsyncMock(return_value=(run, None))
        base.get_workflow = AsyncMock(return_value=agent)
        base.update_workflow_run = AsyncMock()
        base.has_active_recordings = AsyncMock(return_value=False)
        with pytest.raises(_Arret):
            await execute_text_chat_pending_turn(
                workflow_run_id=7,
                workflow_id=6,
                session_data={"turns": [{"status": "pending", "user_message": None}]},
                checkpoint=None,
            )
        return base.update_workflow_run.await_args.kwargs["initial_context"], fabrique.call_args_list


@pytest.mark.asyncio
async def test_clavier_mistral_la_conversation_recoit_la_cle_et_le_run_lestampille():
    persiste, appels = await _jouer_au_clavier(
        MistralLLMConfiguration(api_key="k", model="mistral-large-2512")
    )
    assert appels[0].kwargs["prompt_cache_key"] == "mark-wf-6"
    assert persiste["runtime_configuration"]["llm_prompt_cache_key"] == "mark-wf-6"


@pytest.mark.asyncio
async def test_clavier_autre_fournisseur_aucune_estampille():
    """🔒 Exact dictionary: the stamp of before, not one key more."""
    persiste, _ = await _jouer_au_clavier(OpenAIConfig(api_key="k", model="gpt-4.1"))
    assert persiste["runtime_configuration"] == {
        "llm_provider": "openai",
        "llm_model": "gpt-4.1",
    }

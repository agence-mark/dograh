"""Lot 4 (n° 127) : le client du cerveau naît borné par la création du client, jamais par une écriture de ``llm._client`` après coup."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from api.services.pipecat.borne_du_tour import DELAI_D_UNE_PASSE_S, NOUVELLES_TENTATIVES_AU_PLUS, CerveauBorneMixin, service_borne


def _borne(client) -> bool:
    return client.max_retries == NOUVELLES_TENTATIVES_AU_PLUS and client.timeout == DELAI_D_UNE_PASSE_S


def test_le_cerveau_de_la_fabrique_nait_borne():
    from api.services.configuration.registry import MistralLLMConfiguration
    from api.services.pipecat.service_factory import create_llm_service

    service = create_llm_service(SimpleNamespace(llm=MistralLLMConfiguration(api_key="cle-de-test-jamais-envoyee", model="mistral-large-2512")))
    assert isinstance(service, CerveauBorneMixin)
    assert _borne(service._client)


@pytest.mark.parametrize("nom", ["groq.llm.GroqLLMService", "openrouter.llm.OpenRouterLLMService", "sarvam.llm.SarvamLLMService"])
def test_les_autres_fournisseurs_compatibles_naissent_bornes(nom):
    import importlib

    module, classe = nom.rsplit(".", 1)
    cls = getattr(importlib.import_module(f"pipecat.services.{module}"), classe)
    service = service_borne(cls)(api_key="cle-de-test-jamais-envoyee")
    assert _borne(service._client)
    assert not _borne(cls(api_key="cle-de-test-jamais-envoyee")._client)  # sans la surcharge : le délai et les tentatives du client par défaut


def test_une_seule_sous_classe_par_classe():
    from pipecat.services.groq.llm import GroqLLMService

    assert service_borne(GroqLLMService) is service_borne(GroqLLMService)


def test_les_services_du_chemin_de_production_naissent_bornes():
    """Le cerveau de production (chat completions Scaleway/OpenAI et Responses) porte le mixin : sans lui, le client garde ses deux nouvelles tentatives et son délai par défaut."""
    from pipecat.services.openai.base_llm import OpenAILLMSettings
    from pipecat.services.openai.responses.llm import OpenAIResponsesLLMSettings

    from api.services.pipecat.responses_llm import MarkOpenAIResponsesLLMService
    from api.services.pipecat.service_factory import DograhOpenAILLMService

    chat = DograhOpenAILLMService(api_key="cle-de-test-jamais-envoyee", settings=OpenAILLMSettings(model="gemma"), prompt_cache_key=None)
    assert isinstance(chat, CerveauBorneMixin) and _borne(chat._client)
    responses = MarkOpenAIResponsesLLMService(api_key="cle-de-test-jamais-envoyee", settings=OpenAIResponsesLLMSettings(model="gemma"), prompt_cache_key=None, extra_body={})
    assert isinstance(responses, CerveauBorneMixin) and _borne(responses._client)

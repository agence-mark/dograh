"""[.mark] Garde de non-régression du greffier (Evan, 17/11 : « il faut qu'il reste bon »). Une passe médiane était de 0,3 à 1 s jusqu'au
11/11, puis de 6 à 20 s par moments sans que personne le voie. Ces tests échouent si la passe peut de nouveau attendre longtemps.

| Test | Ce qu'il prouve |
|---|---|
| N1 | le délai d'une passe reste court (≤ 4 s) |
| N2 | le client du greffier ne réessaie jamais en silence, et sa requête est bornée au délai d'une passe |
| N3 | un service sans client ne casse rien |
"""

from __future__ import annotations

from types import SimpleNamespace

from openai import AsyncOpenAI

from api.services.pipecat import greffier


def test_n1_le_delai_d_une_passe_reste_court():
    assert greffier.DELAI_D_UNE_PASSE <= 4.0


def test_n2_aucune_nouvelle_tentative_cachee():
    service = SimpleNamespace(_client=AsyncOpenAI(api_key="essai", base_url="https://exemple.invalid/v1"))
    assert service._client.max_retries == 2  # le défaut du client, celui qui cachait les attentes
    greffier.sans_nouvelle_tentative(service)
    assert service._client.max_retries == 0
    assert float(service._client.timeout) <= greffier.DELAI_D_UNE_PASSE


def test_n3_sans_client_rien_ne_casse():
    greffier.sans_nouvelle_tentative(SimpleNamespace())

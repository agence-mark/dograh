"""[.mark] Les refus du modèle et ses nouvelles tentatives silencieuses sont notés
(chantier langwatch-et-fenetre-du-run, lot 2, étape 2).

Question : quand Mistral refuse une requête (429) et que la bibliothèque cliente la refait en
silence, le run garde-t-il chaque refus, chaque tentative et le temps perdu ?

Le test traverse la VRAIE logique de nouvelles tentatives de la bibliothèque d'OpenAI : le service
est construit par la fabrique (``create_llm_service``), seul le réseau est remplacé par un
transport qui répond 429, 429, puis 200. Aucune requête ne sort de la machine.
"""

import inspect
from types import SimpleNamespace

import httpx2
import pytest

from api.services.analyse_run.analyse import analyser_run
from api.services.analyse_run.requetes_modele import (
    TYPE_EVENEMENT,
    brancher_le_journal_des_requetes,
)
from api.services.configuration.registry import MistralLLMConfiguration
from api.services.pipecat import run_pipeline
from api.services.pipecat.service_factory import create_llm_service


class _Journal:
    def __init__(self):
        self.evenements = []

    async def append(self, evenement):
        self.evenements.append(evenement)


def _service():
    return create_llm_service(
        SimpleNamespace(
            llm=MistralLLMConfiguration(
                api_key="cle-de-test-jamais-envoyee", model="mistral-large-2512"
            )
        )
    )


def _reponses(*statuts):
    file = list(statuts)

    def repondre(requete):
        statut = file.pop(0)
        if statut == 200:
            return httpx2.Response(
                200,
                json={
                    "id": "x",
                    "object": "chat.completion",
                    "created": 0,
                    "model": "mistral-large-2512",
                    "choices": [
                        {
                            "index": 0,
                            "message": {"role": "assistant", "content": "Bonjour"},
                            "finish_reason": "stop",
                        }
                    ],
                },
            )
        return httpx2.Response(
            statut,
            headers={"retry-after-ms": "5"},
            json={"object": "error", "message": "Rate limit exceeded", "code": "1300"},
        )

    return repondre


async def _appeler(service):
    return await service._client.chat.completions.create(
        model="mistral-large-2512", messages=[{"role": "user", "content": "bonjour"}]
    )


@pytest.mark.asyncio
async def test_deux_refus_puis_reussite_sont_notes_avec_le_temps_perdu():
    service = _service()
    journal = _Journal()
    assert brancher_le_journal_des_requetes(service, journal) is True
    service._client._client._transport = httpx2.MockTransport(_reponses(429, 429, 200))
    reponse = await _appeler(service)
    assert reponse.choices[0].message.content == "Bonjour"
    notes = [e["payload"] for e in journal.evenements]
    assert all(e["type"] == TYPE_EVENEMENT for e in journal.evenements)
    assert [(n["status"], n["attempt"]) for n in notes] == [
        (429, 0),
        (429, 1),
        (200, 2),
    ]
    assert notes[0]["lost_secs"] == 0
    assert notes[-1]["lost_secs"] > 0  # deux attentes de 5 ms au moins
    assert notes[-1]["service"] == "DograhMistralLLMService"


@pytest.mark.asyncio
async def test_une_reponse_du_premier_coup_ne_note_rien():
    service = _service()
    journal = _Journal()
    brancher_le_journal_des_requetes(service, journal)
    service._client._client._transport = httpx2.MockTransport(_reponses(200))
    await _appeler(service)
    assert journal.evenements == []


def test_un_service_sans_client_http_accessible_le_dit_sans_lever():
    assert brancher_le_journal_des_requetes(SimpleNamespace(), _Journal()) is False


def test_l_appel_vocal_branche_le_journal_sur_le_modele_de_conversation():
    source = inspect.getsource(run_pipeline)
    assert "brancher_le_journal_des_requetes(llm, in_memory_logs_buffer)" in source
    assert source.index("in_memory_logs_buffer = InMemoryLogsBuffer(") < source.index(
        "brancher_le_journal_des_requetes(llm, in_memory_logs_buffer)"
    )


def test_la_fenetre_compte_les_refus_et_le_temps_perdu():
    def evenement(tour, statut, tentative, perdu):
        return {
            "type": TYPE_EVENEMENT,
            "turn": tour,
            "timestamp": "2026-10-05T10:00:00.000+00:00",
            "payload": {
                "service": "DograhMistralLLMService",
                "status": statut,
                "attempt": tentative,
                "secs": 0.2,
                "lost_secs": perdu,
            },
        }

    run = {
        "id": 1,
        "logs": {
            "realtime_feedback_events": [
                evenement(3, 429, 0, 0.0),
                evenement(3, 200, 1, 1.4),
            ]
        },
    }
    analyse = analyser_run(run)
    erreurs = analyse["providers"]["model_requests"]
    assert erreurs == {
        "refused": 1,
        "retries": 1,
        "lost_secs": 1.4,
        "by_status": {"429": 1},
    }
    assert any(
        i["kind"] == "model_retried" and i["detail"] == 1.4
        for i in analyse["incidents"]["items"]
    )

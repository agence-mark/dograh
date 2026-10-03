"""[.mark] Chantier communes-cp-et-lexique-soniox, lot 5 (S3, question n° 273).
Plan : ``Labo-agent-vocal/plans/communes-cp-et-lexique-soniox/2026-10-02-plan-communes-cp-et-lexique-soniox.md``.

Soniox refuses a context by a MESSAGE inside the session (``error_code``), not
by refusing the connection: the net of the list (Deepgram, ``filet_lexique.py``)
never saw it, and a refusal cost the call (run 1016, a 402: three reconnections
refused, the call closed). Here the REAL connector built by the factory reads a
simulated socket:

| Test | Proof |
|---|---|
| a refused context is dropped: the next connection sends none, the stamp says « refusé » | S3 |
| the refusal is not passed on as an error of the call | S3 |
| any other error (402: no credit) is left to the engine, the context kept | témoin |
| the net is armed with a description alone, no term | S4 + S3 |
"""

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from api.services.pipecat.filet_lexique import armer_filet_lexique
from api.tests.mark.test_soniox_description_du_domaine import PETIT_PLAFOND
from api.tests.mark.test_soniox_expose import (
    _audio_config,
    _config,
    _message_de_configuration,
)

# The refusal exactly as the probe of 2026-10-03 received it.
REFUS_DU_CONTEXTE = {
    "tokens": [],
    "error_code": 400,
    "error_message": "Context is too long: 8021 tokens, the maximum is 8000 tokens.",
}
PLUS_DE_CREDIT = {
    "tokens": [],
    "error_code": 402,
    "error_message": "Organization balance exhausted.",
}


@pytest.fixture(autouse=True)
def plafond_soniox(monkeypatch):
    from api.services.pipecat import service_factory

    monkeypatch.setattr(service_factory, "plafond_du_lexique", lambda *_: PETIT_PLAFOND)


class _Socket:
    """The socket Soniox answers on: the messages, then the server closes."""

    def __init__(self, *messages):
        self.messages = [json.dumps(m) for m in messages]
        self.state = None

    def __aiter__(self):
        return self._lire()

    async def _lire(self):
        for message in self.messages:
            yield message


def _service_arme(keyterms=("Edilkamin",), description=None):
    from api.services.pipecat.service_factory import create_stt_service

    service = create_stt_service(
        SimpleNamespace(stt=_config(domain_description=description)),
        _audio_config(),
        keyterms=list(keyterms) if keyterms else None,
        description_domaine=description,
    )
    refus = []
    service = armer_filet_lexique(
        service, list(keyterms) if keyterms else None, refus.append
    )
    service.push_error = AsyncMock()
    return service, refus


async def _recevoir(service, *messages):
    service._websocket = _Socket(*messages)
    await service._receive_messages()


@pytest.mark.asyncio
async def test_un_contexte_refuse_en_session_est_retire_et_la_reconnexion_part_sans():
    service, refus = _service_arme()
    assert (await _message_de_configuration(service))["context"]["terms"] == [
        "Edilkamin"
    ]
    await _recevoir(service, REFUS_DU_CONTEXTE)
    assert refus and "Context is too long" in refus[0], refus
    assert service._settings.context is None
    assert (await _message_de_configuration(service))["context"] is None


@pytest.mark.asyncio
async def test_le_refus_n_est_pas_remonte_comme_une_erreur_de_l_appel():
    service, _ = _service_arme()
    await _recevoir(service, REFUS_DU_CONTEXTE)
    service.push_error.assert_not_awaited()


@pytest.mark.asyncio
async def test_temoin_une_autre_erreur_reste_au_moteur_et_le_contexte_reste():
    service, refus = _service_arme()
    await _recevoir(service, PLUS_DE_CREDIT)
    assert not refus
    assert service._settings.context is not None


@pytest.mark.asyncio
async def test_temoin_un_refus_sans_contexte_reste_au_moteur():
    from api.services.pipecat.service_factory import create_stt_service

    service = create_stt_service(SimpleNamespace(stt=_config()), _audio_config())
    refus = []
    service = armer_filet_lexique(service, None, refus.append)
    await _recevoir(service, REFUS_DU_CONTEXTE)
    assert not refus


@pytest.mark.asyncio
async def test_le_filet_s_arme_avec_une_description_seule():
    service, refus = _service_arme(
        keyterms=(), description="Poêles à bois et ramonage."
    )
    assert (await _message_de_configuration(service))["context"]["general"]
    await _recevoir(service, REFUS_DU_CONTEXTE)
    assert refus and service._settings.context is None


class _SocketQuiResteOuverte(_Socket):
    """Soniox envoie son refus et ne ferme pas la session."""

    async def _lire(self):
        for message in self.messages:
            yield message
        await asyncio.Event().wait()


@pytest.mark.asyncio
async def test_le_filet_n_attend_pas_que_soniox_ferme_la_session():
    """Relecture du 03/10 : la reprise ne dépend pas d'une fermeture par Soniox."""
    service, refus = _service_arme()
    service._websocket = _SocketQuiResteOuverte(REFUS_DU_CONTEXTE)
    await asyncio.wait_for(service._receive_messages(), timeout=2)
    assert refus and service._settings.context is None


@pytest.mark.asyncio
async def test_temoin_un_400_sans_rapport_au_milieu_de_l_appel_reste_au_moteur():
    """Relecture du 03/10 : après des mots transcrits, un 400 qui ne parle pas du
    contexte n'est pas un refus de la liste ; la liste reste."""
    service, refus = _service_arme()
    jetons = {"tokens": [{"text": "Bonjour", "is_final": False}]}
    autre = {"tokens": [], "error_code": 400, "error_message": "Invalid audio format."}
    await _recevoir(service, jetons, autre)
    assert not refus
    assert service._settings.context is not None

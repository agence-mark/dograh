"""[.mark] Lot 3 de cloture-code-avant-migration (22/10/2026) : le découpage en phrases de la voix.

Pipecat 1.12 découpe le texte envoyé à la voix avec ``sentencex`` (NLTK retiré), dans la langue de
``TTSSettings.language``, **anglais** quand la voix n'en reçoit aucune (ElevenLabs et Mistral chez
nous). Le plan prévoyait de régler ``fr`` pour un agent français ; mesuré le 22/10 sur
``sentencex`` 1.0.31, le découpage français **coupe après les titres** (« Très bien M. » puis
« Dupont, … », « Le Dr. », « St. Maximin »), l'anglais non. Le réglage n'est donc pas posé (constat
au formulaire) : ces tests figent ce que la voix d'un agent français reçoit aujourd'hui, par le
service construit par la fabrique, et deviennent rouges le jour où la langue ou ``sentencex``
change ce découpage.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from api.services.configuration.registry import (
    DeepgramSTTConfiguration,
    ElevenlabsTTSConfiguration,
    MistralTTSConfiguration,
)
from api.services.pipecat.audio_config import AudioConfig
from api.services.pipecat.service_factory import create_tts_service

PHRASE = "Très bien M. Dupont, je note le rendez-vous à 3 h 30. Autre chose ?"


def _voix(configuration):
    return create_tts_service(
        SimpleNamespace(
            tts=configuration,
            stt=DeepgramSTTConfiguration(api_key="cle", model="nova-3", language="fr"),
        ),
        AudioConfig(transport_in_sample_rate=8000, transport_out_sample_rate=8000),
    )


async def _phrases(service, texte: str) -> list[str]:
    agregateur = service._text_aggregator
    phrases = [a.text async for a in agregateur.aggregate(texte)]
    reste = await agregateur.flush()
    if reste is not None and reste.text:
        phrases.append(reste.text)
    return [p.strip() for p in phrases if p.strip()]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "configuration",
    [
        ElevenlabsTTSConfiguration(api_key="cle", voice="Marie - abc123"),
        MistralTTSConfiguration(api_key="cle", voice="fr_marie_neutral"),
    ],
    ids=["elevenlabs", "mistral"],
)
async def test_monsieur_dupont_et_l_heure_restent_dans_la_meme_phrase(configuration):
    service = _voix(configuration)
    assert await _phrases(service, PHRASE) == [
        "Très bien M. Dupont, je note le rendez-vous à 3 h 30.",
        "Autre chose ?",
    ]


def test_la_voix_d_un_agent_francais_ne_recoit_aucune_langue():
    """La voie publique (``TTSSettings.language``) reste vide : ElevenLabs n'ajoute donc pas
    ``language_code`` à son adresse et la requête est celle d'avant la montée."""
    service = _voix(ElevenlabsTTSConfiguration(api_key="cle", voice="Marie - abc123"))
    assert not service._settings.language
    assert "language_code=" not in service._build_websocket_url()

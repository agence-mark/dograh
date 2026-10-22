"""[.mark] Lot 8 de cloture-code-avant-migration (22/10/2026) : la voix découpe ses phrases en français.

Pipecat 1.12 découpe le texte envoyé à la voix avec ``sentencex``, dans la langue de
``TTSSettings.language`` (anglais sans langue). En ``fr``, ``sentencex`` coupe après « M. », « Dr. »,
« St. ». Décision d'Evan du 22/10 : la voix parle français, le défaut se corrige dans notre code
(``api/services/pipecat/decoupage_francais.py``), la langue ``fr`` est posée.

Tout passe par le service construit par la fabrique (ElevenLabs et Mistral), pas par le module seul.
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

FOURNISSEURS = [
    ElevenlabsTTSConfiguration(api_key="cle", voice="Marie - abc123"),
    MistralTTSConfiguration(api_key="cle", voice="fr_marie_neutral"),
]
IDS = ["elevenlabs", "mistral"]


def _voix(configuration, langue_stt: str = "fr"):
    return create_tts_service(
        SimpleNamespace(
            tts=configuration,
            stt=DeepgramSTTConfiguration(api_key="cle", model="nova-3", language=langue_stt),
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
@pytest.mark.parametrize("configuration", FOURNISSEURS, ids=IDS)
async def test_monsieur_dupont_et_l_heure_restent_dans_la_meme_phrase(configuration):
    assert await _phrases(_voix(configuration), PHRASE) == [
        "Très bien M. Dupont, je note le rendez-vous à 3 h 30.",
        "Autre chose ?",
    ]


# Chaque abréviation de la liste : jamais de coupe après elle.
ABREVIATIONS = [
    "Bonjour M. Dupont est arrivé. Merci.",
    "Les MM. Durand et Petit sont là. Merci.",
    "Je vois Mme. Martin demain. Merci.",
    "J'appelle Mlle. Roux ce soir. Merci.",
    "Rendez-vous avec le Dr. Leroy mardi. Merci.",
    "Je pars chez le Pr. Garnier lundi. Merci.",
    "On voit Me. Lambert pour l'acte. Merci.",
    "Direction St. Maximin demain. Merci.",
    "Direction Ste. Geneviève demain. Merci.",
    "J'habite av. Foch à Beauvais. Merci.",
    "Il est au bd. Haussmann ce matin. Merci.",
    "Il y a des chaises, des tables, etc. Et un parking. Merci.",
    "Je peux venir, p. ex. mardi matin. Merci.",
    "Je suis au n° 12 de la rue. Merci.",
    "J'ai écrit à J. Dupont ce matin. Merci.",
]


@pytest.mark.asyncio
@pytest.mark.parametrize("configuration", FOURNISSEURS, ids=IDS)
@pytest.mark.parametrize("texte", ABREVIATIONS)
async def test_aucune_coupe_apres_une_abreviation(configuration, texte):
    phrases = await _phrases(_voix(configuration), texte)
    # Le texte se termine toujours par « Merci. » : une seule coupe est attendue, juste avant, jamais après l'abréviation.
    assert phrases[-1] == "Merci."
    assert " ".join(phrases) == texte
    assert len(phrases) == 2, phrases


@pytest.mark.asyncio
@pytest.mark.parametrize("configuration", FOURNISSEURS, ids=IDS)
async def test_trois_phrases_ordinaires_donnent_trois_morceaux(configuration):
    phrases = await _phrases(
        _voix(configuration), "Bonjour, ici l'agence. Je vous écoute. Quelle est votre demande."
    )
    assert phrases == ["Bonjour, ici l'agence.", "Je vous écoute.", "Quelle est votre demande."]


@pytest.mark.asyncio
@pytest.mark.parametrize("configuration", FOURNISSEURS, ids=IDS)
async def test_point_d_interrogation_et_d_exclamation_coupent(configuration):
    phrases = await _phrases(_voix(configuration), "Vous êtes là ? Parfait ! Je commence. Voilà")
    assert phrases == ["Vous êtes là ?", "Parfait !", "Je commence.", "Voilà"]


@pytest.mark.asyncio
@pytest.mark.parametrize("configuration", FOURNISSEURS, ids=IDS)
async def test_les_nombres_et_les_heures_restent_entiers(configuration):
    phrases = await _phrases(
        _voix(configuration), "Cela fait 12,50 € pour 1.5 kg. Venez à 3 h 30. Merci."
    )
    assert phrases == ["Cela fait 12,50 € pour 1.5 kg.", "Venez à 3 h 30.", "Merci."]


@pytest.mark.asyncio
@pytest.mark.parametrize("configuration", FOURNISSEURS, ids=IDS)
async def test_le_decoupage_tient_quand_le_texte_arrive_en_morceaux(configuration):
    """Le modèle écrit par petits bouts : « M. » coupé entre deux morceaux ne coupe rien non plus."""
    service = _voix(configuration)
    agregateur = service._text_aggregator
    phrases = []
    for morceau in ["Très bien M", ".", " Dup", "ont, c'est noté", ". Autre ", "chose ?"]:
        phrases += [a.text async for a in agregateur.aggregate(morceau)]
    reste = await agregateur.flush()
    if reste is not None:
        phrases.append(reste.text)
    assert [p.strip() for p in phrases] == ["Très bien M. Dupont, c'est noté.", "Autre chose ?"]


def test_elevenlabs_recoit_la_langue_francaise():
    service = _voix(ElevenlabsTTSConfiguration(api_key="cle", voice="Marie - abc123"))
    assert str(service._settings.language) in ("fr", "Language.FR")
    assert "language_code=fr" in service._build_websocket_url()


def test_mistral_recoit_la_langue_francaise():
    service = _voix(MistralTTSConfiguration(api_key="cle", voice="fr_marie_neutral"))
    assert str(service._settings.language) in ("fr", "Language.FR")


@pytest.mark.parametrize("configuration", FOURNISSEURS, ids=IDS)
def test_un_agent_non_francais_garde_le_comportement_de_l_amont(configuration):
    service = _voix(configuration, langue_stt="en")
    assert type(service._text_aggregator).__name__ == "SimpleTextAggregator"
    assert not service._settings.language

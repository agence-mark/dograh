"""[.mark] Chantier voix-soniox, D19 : la clé Soniox part dans l'en-tête de connexion.

Soniox refuse, à partir du 15/01/2027, toute connexion qui ne porte pas sa clé
dans l'en-tête ``Authorization: Bearer`` (transcription comprise). Notre Pipecat
(1.10) l'envoie encore seulement dans le premier message : sans correctif, la
transcription de production tombe ce jour-là. Note de Pierre du 21/10 :
``plans/propositions-pierre/2026-10-21-pipecat-cle-soniox-et-montee.md`` § 1.

⛔ Ce que ce fichier ne remplace pas : l'aide ``_message_de_configuration`` de
``test_soniox_expose.py`` remplace ``_websocket_connect`` SUR L'INSTANCE, donc
elle masquerait la surcharge. Ici c'est ``websocket_connect`` du MODULE de
Pipecat qui est remplacé : ce qui est vérifié, c'est l'appel que la
bibliothèque de connexion recevrait vraiment.

| Test | Preuve |
|---|---|
| la fabrique de transcription rend notre sous-classe, et l'en-tête part | D19 |
| le message de configuration garde sa clé (Soniox accepte la même clé) | D19 |
| une reconnexion porte aussi l'en-tête | D19 |
| le filet du lexique (`armer_filet_lexique`) n'enlève pas l'en-tête | D19 |
| un en-tête passé explicitement n'est pas écrasé (`setdefault`) | D19 |
| la sonde du lexique envoie l'en-tête | D19 |
| la voix reprend la même mécanique (classe prête pour le lot 3) | D19 |
"""

import json
from types import SimpleNamespace

import pytest

from api.services.pipecat.audio_config import AudioConfig

CLE = "soniox-key"
EN_TETE_ATTENDU = {"Authorization": f"Bearer {CLE}"}
ADRESSE_EUROPE = "wss://stt-rt.eu.soniox.com/transcribe-websocket"


class _FausseConnexion:
    def __init__(self):
        self.envois = []
        self.state = None

    async def send(self, message):
        self.envois.append(message)

    async def close(self):
        return None


@pytest.fixture
def connexions(monkeypatch):
    """Remplace ``websocket_connect`` au niveau du MODULE de Pipecat.

    ⛔ Pas ``service._websocket_connect`` : c'est justement la méthode que la
    surcharge redéfinit, la remplacer la ferait disparaître du test.
    """
    from pipecat.services import websocket_service

    appels = []

    async def faux_connect(adresse, **kwargs):
        appels.append({"adresse": adresse, "kwargs": kwargs, "connexion": _FausseConnexion()})
        return appels[-1]["connexion"]

    monkeypatch.setattr(websocket_service, "websocket_connect", faux_connect)
    return appels


def _service_de_transcription(keyterms=None, **reglages):
    from api.services.configuration.registry import SonioxSTTConfiguration
    from api.services.pipecat.service_factory import create_stt_service

    config = SonioxSTTConfiguration(api_key=CLE, **reglages)
    return create_stt_service(
        SimpleNamespace(stt=config),
        AudioConfig(transport_in_sample_rate=8000, transport_out_sample_rate=24000),
        keyterms=keyterms,
    )


@pytest.mark.asyncio
async def test_la_cle_part_dans_lentete_par_la_vraie_fabrique(connexions):
    service = _service_de_transcription()
    await service._connect_websocket()

    assert len(connexions) == 1, "la connexion n'a pas atteint websocket_connect"
    assert connexions[0]["adresse"] == ADRESSE_EUROPE
    assert connexions[0]["kwargs"].get("additional_headers") == EN_TETE_ATTENDU


@pytest.mark.asyncio
async def test_le_message_de_configuration_garde_sa_cle(connexions):
    """Soniox : « Omit it, or repeat the same key ». On garde le message tel quel."""
    service = _service_de_transcription()
    await service._connect_websocket()

    message = json.loads(connexions[0]["connexion"].envois[0])
    assert message["api_key"] == CLE
    assert message["model"] == "stt-rt-v5"


@pytest.mark.asyncio
async def test_une_reconnexion_porte_aussi_lentete(connexions):
    service = _service_de_transcription()
    await service._connect_websocket()
    service._websocket = None  # la connexion est tombée
    await service._connect_websocket()

    assert len(connexions) == 2
    for appel in connexions:
        assert appel["kwargs"].get("additional_headers") == EN_TETE_ATTENDU


@pytest.mark.asyncio
async def test_le_filet_du_lexique_nenleve_pas_lentete(connexions):
    from api.services.pipecat.filet_lexique import armer_filet_lexique

    termes = ["poêle", "insert"]
    service = _service_de_transcription(keyterms=termes)
    # ⛔ Le filet n'arme que si une liste part vraiment : sans elle le test ne
    # prouverait rien sur la cohabitation.
    assert service._settings.context is not None
    avant = service._get_websocket
    armer_filet_lexique(service, termes)
    assert service._get_websocket is not avant, "le filet n'est pas armé"
    await service._connect_websocket()

    assert connexions[0]["kwargs"].get("additional_headers") == EN_TETE_ATTENDU


@pytest.mark.asyncio
async def test_un_en_tete_donne_explicitement_nest_pas_ecrase(connexions):
    """``setdefault`` : l'appelant qui passe son propre en-tête garde la main."""
    service = _service_de_transcription()
    propre = {"Authorization": "Bearer autre"}
    await service._websocket_connect(ADRESSE_EUROPE, additional_headers=propre)

    assert connexions[0]["kwargs"]["additional_headers"] == propre


def test_la_classe_est_une_sous_classe_du_connecteur_et_vit_dans_api():
    from pipecat.services.soniox.stt import SonioxSTTService

    from api.services.pipecat.soniox_cle_en_entete import MarkSonioxSTTService

    service = _service_de_transcription()
    assert isinstance(service, MarkSonioxSTTService)
    assert isinstance(service, SonioxSTTService)
    assert MarkSonioxSTTService.__module__.startswith("api.")


@pytest.mark.asyncio
async def test_la_sonde_du_lexique_envoie_lentete(monkeypatch):
    """La sonde ouvre sa propre connexion (``websockets.connect`` direct)."""
    from api.scripts.mark import sonde_lexique_soniox as sonde

    appels = []

    class _Socket:
        def __init__(self):
            self.vus = []

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def send(self, message):
            self.vus.append(message)

        def __aiter__(self):
            async def _rien():
                yield json.dumps({"finished": True})

            return _rien()

    def faux_connect(adresse, **kwargs):
        appels.append({"adresse": adresse, "kwargs": kwargs})
        return _Socket()

    monkeypatch.setattr(sonde.websockets, "connect", faux_connect)
    resultat = await sonde._essai(ADRESSE_EUROPE, CLE, ["poêle"], None)

    assert resultat["accepte"] is True
    assert appels[0]["kwargs"].get("additional_headers") == EN_TETE_ATTENDU


@pytest.mark.asyncio
async def test_la_voix_reprend_la_meme_mecanique(connexions):
    """Prêt pour le lot 3 : la classe de la voix porte la même surcharge."""
    from pipecat.services.soniox.tts import SonioxTTSService

    from api.services.pipecat.soniox_cle_en_entete import MarkSonioxTTSService

    service = MarkSonioxTTSService(api_key=CLE, sample_rate=24000)
    assert isinstance(service, SonioxTTSService)
    await service._connect_websocket()

    assert connexions[0]["kwargs"].get("additional_headers") == EN_TETE_ATTENDU

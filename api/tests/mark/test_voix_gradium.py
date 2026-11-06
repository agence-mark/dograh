"""[.mark] Lot GT (builder partie 3) : Gradium, fournisseur de voix choisissable avec tous ses réglages.

Parcours A de ``reference/18-ajout-fournisseur.md``. R9 : ``GradiumTTSService`` existe dans la copie épinglée de
Pipecat (``gradium/tts.py``) ; le fork n'en copie rien, il le sous-classe (``gradium_voix.py``).

Documentation officielle lue le 05/11/2026 (aucun appel réel, aucune clé) :
- https://docs.gradium.ai/guides/voice-settings : ``temp`` (0,7, 0 à 1,4), ``padding_bonus`` (0, -4 à 4),
  ``rewrite_rules`` (fr, fr-be, fr-ch, en, de, es, pt, none), ``pronunciation_id`` (au niveau du ``setup``) ;
- https://docs.gradium.ai/guides/websocket-lifecycle.md : message ``setup`` (``voice_id``, ``output_format``,
  ``model_name``, ``close_ws_on_eos``), ``end_of_stream``, ``error`` ;
- https://docs.gradium.ai/guides/recipes/telephony-audio.md : ``ulaw_8000`` ;
- https://docs.gradium.ai/api-reference/endpoint/get-credits.md : ``GET /usages/credits`` (en-tête ``x-api-key``).

| Test | Preuve |
|---|---|
| Gradium est au registre des voix, n'est le défaut de personne, les autres voix ne changent pas | parcours A, 4.2 |
| chaque réglage est borné dans le schéma ET refusé par le serveur | 7 (1) |
| vitesse en facteur -> padding_bonus (C5), borné à ±4 | C5 |
| la fabrique (porte du produit) envoie au connecteur ce que l'écran déclare | 4.3 |
| l'estampille lit la même fonction que la requête | 5.4 |
| le μ-law du téléphone est décodé en PCM | téléphone |
| la clé se vérifie sur la région de l'adresse, jamais en clair | clé |
| l'extra ``gradium`` est dans les trois chemins d'installation | 4.4 |
| une session rouverte avant sa limite, entre deux tours, jamais au milieu d'une phrase | C2 |
| de bout en bout par un vrai pipeline : l'audio du deuxième tour passe sur la connexion rouverte | R1 |
"""

import asyncio
import base64
import json
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from pydantic import ValidationError
from websockets.protocol import State

from api.services.configuration.registry import (
    REGISTRY,
    GradiumTTSConfiguration,
    ServiceProviders,
    ServiceType,
    region_gradium_voix,
)
from api.services.pipecat.audio_config import AudioConfig
from api.services.pipecat.gradium_voix import (
    MarkGradiumTTSService,
    format_et_frequence,
    padding_bonus_de_la_vitesse,
    reglages_gradium_voix,
)
from api.services.pipecat.service_factory import create_tts_service, stamp_voice_settings

RACINE = Path(__file__).resolve().parents[3]
ROMANE = "jBULVCDhf05tOJN5"
GASPARD = "iEu63s1rhn_kegTr"


def _config(**kwargs):
    return GradiumTTSConfiguration(api_key="cle-de-test", **kwargs)


def _audio(taux=24000):
    return AudioConfig(transport_in_sample_rate=taux, transport_out_sample_rate=taux)


def _voix(taux=24000, **kwargs):
    return create_tts_service(SimpleNamespace(tts=_config(**kwargs)), _audio(taux))


# --------------------------------------------------------------------------- #
# Registre
# --------------------------------------------------------------------------- #


def test_gradium_est_au_registre_des_voix_seulement():
    assert "gradium" in REGISTRY[ServiceType.TTS]
    for autre in (ServiceType.LLM, ServiceType.STT, ServiceType.EMBEDDINGS, ServiceType.REALTIME):
        assert "gradium" not in REGISTRY[autre]
    assert REGISTRY[ServiceType.TTS]["gradium"] is GradiumTTSConfiguration


def test_gradium_n_est_le_defaut_de_personne_et_les_autres_voix_restent():
    from api.services.configuration.defaults import DEFAULT_SERVICE_PROVIDERS

    assert all(
        str(getattr(p, "value", p)) != "gradium"
        for p in DEFAULT_SERVICE_PROVIDERS.values()
    )
    for ancien in ("elevenlabs", "soniox", "cartesia", "mistral", "deepgram", "openai", "google"):
        assert ancien in REGISTRY[ServiceType.TTS]


def test_les_voix_francaises_nommees_sont_le_menu_et_la_saisie_libre_reste_ouverte():
    voix = GradiumTTSConfiguration.model_json_schema()["properties"]["voice"]
    assert voix["examples"] == [ROMANE, GASPARD]
    assert voix["allow_custom_input"] is True
    assert "Romane" in voix["mark_valeurs"][ROMANE]["fr"]
    assert "Gaspard" in voix["mark_valeurs"][GASPARD]["en"]
    assert _config().voice == ROMANE


def test_le_schema_declare_tous_les_reglages_avec_leurs_bornes_et_leur_francais():
    p = GradiumTTSConfiguration.model_json_schema()["properties"]
    for champ in ("voice", "speed", "temp", "rewrite_rules", "pronunciation_id", "output_format", "base_url", "region"):
        assert p[champ]["mark_libelle"]["fr"] and p[champ]["mark_libelle"]["en"], champ
        assert p[champ]["mark_aide"]["fr"], champ
        assert p[champ]["mark_groupe"], champ
    assert p["temp"]["default"] == 0.7 and p["temp"]["minimum"] == 0.0 and p["temp"]["maximum"] == 1.4
    vitesse = p["speed"]["anyOf"][0]
    assert vitesse["minimum"] == 0.5 and vitesse["maximum"] == 2.0 and p["speed"]["mark_facteur"] is True
    assert p["rewrite_rules"]["default"] == "fr"
    assert set(p["rewrite_rules"]["enum"]) == {"fr", "fr-be", "fr-ch", "en", "de", "es", "pt", "none"}
    assert p["output_format"]["enum"] == ["auto", "pcm_8000", "ulaw_8000"]
    assert p["region"]["readonly"] is True
    assert p["base_url"]["default"] == "wss://eu.api.gradium.ai/api/speech/tts"


def test_la_bulle_du_choix_dit_les_conditions_du_fournisseur_en_deux_langues():
    schema = GradiumTTSConfiguration.model_json_schema()
    fr = schema["mark_aide"]["fr"]
    assert "Résidence UE" in fr and "zéro conservation" in fr and "300 secondes" in fr
    assert "zero data retention" in schema["mark_aide"]["en"]


@pytest.mark.parametrize(
    "champ, valeur",
    [
        ("speed", 0.4),
        ("speed", 2.1),
        ("temp", -0.1),
        ("temp", 1.5),
        ("rewrite_rules", "klingon"),
        ("output_format", "mp3"),
        ("pronunciation_id", "a b;c"),
        ("pronunciation_id", "x" * 65),
        ("base_url", "https://eu.api.gradium.ai"),
    ],
)
def test_une_valeur_hors_bornes_est_refusee_a_l_ecriture(champ, valeur):
    with pytest.raises(ValidationError):
        _config(**{champ: valeur})


@pytest.mark.parametrize(
    "champ, valeur",
    [("speed", 0.5), ("speed", 2.0), ("temp", 0.0), ("temp", 1.4), ("rewrite_rules", "none"), ("output_format", "ulaw_8000")],
)
def test_les_bornes_elles_memes_sont_permises(champ, valeur):
    assert getattr(_config(**{champ: valeur}), champ) == valeur


def test_la_region_suit_l_adresse():
    assert _config().region == "eu"
    assert _config(base_url="wss://api.gradium.ai/api/speech/tts").region == "global"
    assert _config(base_url="wss://us.api.gradium.ai/api/speech/tts").region == "us"
    assert region_gradium_voix("") == "eu"
    # Une région écrite à la main ne gagne pas sur l'adresse.
    assert _config(region="us").region == "eu"


def test_le_fournisseur_est_dans_l_enum_et_se_relit_par_le_discriminant():
    from pydantic import TypeAdapter

    from api.services.configuration.registry import TTSConfig

    relu = TypeAdapter(TTSConfig).validate_python({"provider": "gradium", "api_key": "k"})
    assert isinstance(relu, GradiumTTSConfiguration)
    assert ServiceProviders.GRADIUM.value == "gradium"


# --------------------------------------------------------------------------- #
# C5 : la vitesse en facteur
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "vitesse, attendu",
    [(1.0, 0.0), (1.2, -0.8), (0.8, 0.8), (1.5, -2.0), (2.0, -4.0), (0.5, 2.0), (3.0, -4.0), (-5.0, 4.0)],
)
def test_c5_la_vitesse_devient_un_padding_bonus_borne(vitesse, attendu):
    assert padding_bonus_de_la_vitesse(vitesse) == pytest.approx(attendu)


def test_sans_vitesse_aucun_padding_bonus_n_est_envoye():
    assert "padding_bonus" not in reglages_gradium_voix(_config())
    assert reglages_gradium_voix(_config(speed=1.2))["padding_bonus"] == pytest.approx(-0.8)


# --------------------------------------------------------------------------- #
# La fabrique, par la porte du produit
# --------------------------------------------------------------------------- #


def test_la_fabrique_envoie_au_connecteur_ce_que_l_ecran_declare():
    service = _voix(
        voice=GASPARD, speed=1.25, temp=0.5, rewrite_rules="fr-be", pronunciation_id="bb1ckYhNHCcIJjdK",
        output_format="pcm_8000",
    )
    assert isinstance(service, MarkGradiumTTSService)
    setup = service._build_setup_msg("ctx-1")
    assert setup["type"] == "setup"
    assert setup["voice_id"] == GASPARD
    assert setup["model_name"] == "default"
    assert setup["output_format"] == "pcm_8000"
    assert setup["pronunciation_id"] == "bb1ckYhNHCcIJjdK"
    assert setup["close_ws_on_eos"] is False and setup["client_req_id"] == "ctx-1"
    # Un objet, comme le montre la documentation, jamais une chaîne.
    assert setup["json_config"] == {"temp": 0.5, "rewrite_rules": "fr-be", "padding_bonus": pytest.approx(-1.0)}
    assert service._init_sample_rate == 8000
    assert service._url == "wss://eu.api.gradium.ai/api/speech/tts"


def test_un_ecran_intact_envoie_les_defauts_documentes_et_ni_vitesse_ni_dictionnaire():
    setup = _voix()._build_setup_msg("c")
    assert setup["voice_id"] == ROMANE
    assert setup["json_config"] == {"temp": 0.7, "rewrite_rules": "fr"}
    assert "pronunciation_id" not in setup


def test_une_voix_videe_retombe_sur_la_voix_du_produit_pas_sur_celle_du_connecteur():
    reglages = reglages_gradium_voix(SimpleNamespace(voice="", model="", base_url="", rewrite_rules=None, temp=None))
    assert reglages["voice"] == ROMANE
    assert reglages["base_url"].startswith("wss://eu.")
    assert reglages["rewrite_rules"] == "fr" and reglages["temp"] == 0.7


@pytest.mark.parametrize(
    "format_, taux, attendu",
    [
        ("auto", 8000, ("pcm_8000", 8000)),
        ("auto", 16000, ("pcm_16000", 16000)),
        ("auto", 24000, ("pcm_24000", 24000)),
        ("auto", 48000, ("pcm_48000", 48000)),
        ("auto", 22050, ("pcm", 48000)),
        ("auto", None, ("pcm", 48000)),
        ("ulaw_8000", 24000, ("ulaw_8000", 8000)),
        ("pcm_8000", 48000, ("pcm_8000", 8000)),
    ],
)
def test_le_format_automatique_suit_la_ligne(format_, taux, attendu):
    assert format_et_frequence(format_, taux) == attendu


def test_l_adresse_est_controlee_par_la_fabrique_avant_l_appel(monkeypatch):
    from fastapi import HTTPException

    from api.services.pipecat import service_factory

    vues = []

    def _refuse(url, **kwargs):
        vues.append(url)
        raise ValueError("adresse refusée")

    monkeypatch.setattr(service_factory, "validate_user_configured_service_url", _refuse)
    with pytest.raises(HTTPException) as erreur:
        _voix()
    assert erreur.value.status_code == 400
    assert vues == ["wss://eu.api.gradium.ai/api/speech/tts"]


def test_l_estampille_lit_la_meme_fonction_que_la_requete():
    config = _config(speed=1.5, temp=0.3, rewrite_rules="en", pronunciation_id="dico_1", voice=GASPARD)
    service = create_tts_service(SimpleNamespace(tts=config), _audio())
    json_envoye = service._build_setup_msg("c")["json_config"]
    estampille = stamp_voice_settings({}, config)["tts_settings"]
    assert estampille["voice"] == GASPARD
    assert estampille["temp"] == json_envoye["temp"] == 0.3
    assert estampille["rewrite_rules"] == json_envoye["rewrite_rules"] == "en"
    assert estampille["padding_bonus"] == json_envoye["padding_bonus"] == pytest.approx(-2.0)
    assert estampille["pronunciation_id"] == "dico_1"
    assert estampille["endpoint"] == "wss://eu.api.gradium.ai/api/speech/tts"
    assert estampille["output_format"] == "auto"
    assert "cle-de-test" not in json.dumps(estampille)


def test_aucune_autre_voix_n_est_touchee_par_l_estampille():
    ancien = SimpleNamespace(provider="cartesia", voice="v", base_url="")
    assert stamp_voice_settings({}, ancien) == {"tts_settings": {"voice": "v"}}


# --------------------------------------------------------------------------- #
# Le téléphone : μ-law
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_le_mu_law_du_telephone_est_decode_en_pcm_16_bits():
    from pipecat.frames.frames import TTSAudioRawFrame

    service = _voix(taux=8000, output_format="ulaw_8000")
    recu = []

    async def _noter(self, context_id, frame):
        recu.append(frame)

    from pipecat.services.tts_service import TTSService

    original = TTSService.append_to_audio_context
    TTSService.append_to_audio_context = _noter
    try:
        ulaw = bytes([0xFF, 0x7F, 0x00, 0x80] * 40)  # 160 échantillons
        await service.append_to_audio_context("c", TTSAudioRawFrame(audio=ulaw, sample_rate=8000, num_channels=1))
    finally:
        TTSService.append_to_audio_context = original
    assert len(recu) == 1 and len(recu[0].audio) == 2 * len(ulaw)
    assert recu[0].sample_rate == 8000


@pytest.mark.asyncio
async def test_le_pcm_n_est_pas_retouche():
    from pipecat.frames.frames import TTSAudioRawFrame
    from pipecat.services.tts_service import TTSService

    service = _voix(taux=8000, output_format="pcm_8000")
    recu = []

    async def _noter(self, context_id, frame):
        recu.append(frame)

    original = TTSService.append_to_audio_context
    TTSService.append_to_audio_context = _noter
    try:
        await service.append_to_audio_context("c", TTSAudioRawFrame(audio=b"\x01\x02" * 80, sample_rate=8000, num_channels=1))
    finally:
        TTSService.append_to_audio_context = original
    assert recu[0].audio == b"\x01\x02" * 80


# --------------------------------------------------------------------------- #
# Le builder : la clé n'est jamais lue, le genre de la voix est celui du catalogue
# --------------------------------------------------------------------------- #


def test_le_builder_ne_lit_jamais_la_cle_d_une_voix_gradium():
    from api.services.builder.reglages_agent import CLE_MASQUEE, masquer_les_cles

    vue = masquer_les_cles({"tts": _config(speed=1.2).model_dump(mode="json")})
    assert vue["tts"]["api_key"] == CLE_MASQUEE
    assert vue["tts"]["speed"] == 1.2 and vue["tts"]["voice"] == ROMANE
    assert "cle-de-test" not in json.dumps(vue)


@pytest.mark.parametrize("voix, genre", [(ROMANE, "f"), (GASPARD, "m"), ("inconnue", None)])
def test_le_genre_d_une_voix_gradium_vient_du_catalogue_jamais_devine(voix, genre):
    from api.services.builder.controle.service import genre_de_la_voix

    assert genre_de_la_voix({"model_overrides": {"tts": {"voice": voix}}}) == genre


# --------------------------------------------------------------------------- #
# La clé
# --------------------------------------------------------------------------- #


class _Reponse:
    """Une réponse enregistrée d'après le schéma ``CreditsSummary`` de la documentation (get-credits)."""

    def __init__(self, code):
        self.status_code = code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("x", request=httpx.Request("GET", "https://x"), response=self)


def _verificateur():
    from api.services.configuration.check_validity import UserConfigurationValidator

    return UserConfigurationValidator()


def test_la_cle_se_verifie_sur_l_hote_de_la_region_de_l_adresse(monkeypatch):
    vus = []

    def _get(url, headers=None, timeout=None):
        vus.append((url, dict(headers or {})))
        return _Reponse(200)

    monkeypatch.setattr(httpx, "get", _get)
    verificateur = _verificateur()
    assert verificateur._check_gradium_api_key("gradium", "k1", _config()) is True
    assert verificateur._check_gradium_api_key("gradium", "k2", _config(base_url="wss://api.gradium.ai/api/speech/tts"))
    assert vus[0][0] == "https://eu.api.gradium.ai/api/usages/credits" and vus[0][1] == {"x-api-key": "k1"}
    assert vus[1][0] == "https://api.gradium.ai/api/usages/credits"


@pytest.mark.parametrize("code", [401, 403])
def test_une_cle_refusee_est_dite_sans_la_montrer(monkeypatch, code):
    monkeypatch.setattr(httpx, "get", lambda *a, **k: _Reponse(code))
    with pytest.raises(ValueError) as erreur:
        _verificateur()._check_gradium_api_key("gradium", "cle-secrete-123", _config())
    assert "Invalid Gradium API key" in str(erreur.value) and "cle-secrete-123" not in str(erreur.value)


def test_le_fournisseur_est_dans_la_table_de_verification_des_cles():
    assert "gradium" in _verificateur()._validator_map


# --------------------------------------------------------------------------- #
# 4.4 : l'extra dans tous les chemins d'installation
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("fichier", ["api/Dockerfile", "scripts/setup_requirements.sh", "scripts/setup_requirements.ps1"])
def test_l_extra_gradium_est_dans_chaque_chemin_d_installation(fichier):
    texte = (RACINE / fichier).read_text(encoding="utf-8")
    lignes = [l for l in texte.splitlines() if "soniox" in l and "pipecat" in l and "[" in l]
    assert lignes and all(",gradium]" in l or ",gradium," in l for l in lignes), fichier


# --------------------------------------------------------------------------- #
# C2 : les sessions de 300 s
# --------------------------------------------------------------------------- #


class _FauxWebsocket:
    """Une connexion Gradium enregistrée : répond à ``text`` par de l'audio et à ``end_of_stream`` par sa fin."""

    ouvertes: list["_FauxWebsocket"] = []

    def __init__(self):
        self.state = State.OPEN
        self.envoyes: list[dict] = []
        self.file: asyncio.Queue = asyncio.Queue()
        _FauxWebsocket.ouvertes.append(self)

    async def send(self, message):
        msg = json.loads(message)
        self.envoyes.append(msg)
        ctx = msg.get("client_req_id")
        if msg["type"] == "text":
            audio = base64.b64encode(b"\x10\x00" * 480).decode()
            await self.file.put(json.dumps({"type": "audio", "audio": audio, "client_req_id": ctx}))
        elif msg["type"] == "end_of_stream":
            await self.file.put(json.dumps({"type": "end_of_stream", "client_req_id": ctx}))

    async def close(self):
        self.state = State.CLOSED
        await self.file.put(None)

    def __aiter__(self):
        return self._lire()

    async def _lire(self):
        while True:
            message = await self.file.get()
            if message is None:
                return
            yield message


class _Horloge:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


@pytest.fixture
def faux_gradium(monkeypatch):
    _FauxWebsocket.ouvertes = []

    async def _connecter(self, uri, **kwargs):
        return _FauxWebsocket()

    monkeypatch.setattr(MarkGradiumTTSService, "_websocket_connect", _connecter)
    monkeypatch.setattr(MarkGradiumTTSService, "INTERVALLE_VEILLE_S", 0.02)
    return _FauxWebsocket


async def _service_connecte(horloge):
    from pipecat.utils.asyncio.task_manager import TaskManager

    service = _voix()
    service._task_manager = TaskManager()
    service._horloge = horloge
    await service._connect()
    return service


@pytest.mark.asyncio
async def test_c2_la_session_n_est_pas_rouverte_avant_sa_limite(faux_gradium):
    horloge = _Horloge()
    service = await _service_connecte(horloge)
    try:
        horloge.t += 239
        assert await service.rouvrir_si_necessaire() is False
        assert len(faux_gradium.ouvertes) == 1 and service.reouvertures == 0
    finally:
        await service._disconnect()


@pytest.mark.asyncio
async def test_c2_la_session_est_rouverte_entre_deux_tours_avant_les_300_s(faux_gradium):
    horloge = _Horloge()
    service = await _service_connecte(horloge)
    try:
        horloge.t += 241
        assert await service.rouvrir_si_necessaire() is True
        assert service.reouvertures == 1
        assert len(faux_gradium.ouvertes) == 2
        assert faux_gradium.ouvertes[0].state is State.CLOSED
        assert faux_gradium.ouvertes[1].state is State.OPEN
        assert service.age_de_la_session() == 0
        # Le compteur repart : pas de nouvelle réouverture tout de suite.
        assert await service.rouvrir_si_necessaire() is False
    finally:
        await service._disconnect()


@pytest.mark.asyncio
async def test_c2_jamais_au_milieu_d_une_phrase(faux_gradium):
    horloge = _Horloge()
    service = await _service_connecte(horloge)
    try:
        horloge.t += 280
        service._setup_context_ids.add("phrase-en-cours")
        assert await service.rouvrir_si_necessaire() is False
        assert len(faux_gradium.ouvertes) == 1 and faux_gradium.ouvertes[0].state is State.OPEN
        service._setup_context_ids.clear()
        await service.create_audio_context("tour-en-cours")
        assert await service.rouvrir_si_necessaire() is False
        assert len(faux_gradium.ouvertes) == 1
        await service.remove_audio_context("tour-en-cours")
        service._audio_contexts.clear()
        assert await service.rouvrir_si_necessaire() is True
    finally:
        await service._disconnect()


@pytest.mark.asyncio
async def test_c2_la_premiere_phrase_d_un_tour_rouvre_avant_d_envoyer(faux_gradium):
    horloge = _Horloge()
    service = await _service_connecte(horloge)
    try:
        horloge.t += 250
        await service.create_audio_context("tour-2")
        async for _ in service.run_tts("Bonjour.", "tour-2"):
            pass
        assert len(faux_gradium.ouvertes) == 2
        assert [m["type"] for m in faux_gradium.ouvertes[0].envoyes] == []
        assert [m["type"] for m in faux_gradium.ouvertes[1].envoyes] == ["setup", "text"]
    finally:
        await service._disconnect()


@pytest.mark.asyncio
async def test_c2_une_reouverture_ratee_ne_leve_pas(faux_gradium, monkeypatch):
    horloge = _Horloge()
    service = await _service_connecte(horloge)
    try:
        horloge.t += 260

        async def _casse(self):
            raise RuntimeError("réseau coupé")

        monkeypatch.setattr(MarkGradiumTTSService, "_connect", _casse)
        assert await service.rouvrir_si_necessaire() is False
    finally:
        monkeypatch.undo()
        await service._disconnect()


@pytest.mark.asyncio
async def test_r1_par_un_vrai_pipeline_le_deuxieme_tour_passe_sur_la_connexion_rouverte(faux_gradium):
    """Traverse la fabrique du produit et un vrai pipeline Pipecat (R1) : deux tours, plus de 240 s de silence
    simulé entre les deux, l'audio du second revient par une NOUVELLE connexion, la première a été fermée.

    L'horloge simulée va 400 fois plus vite que la vraie : 0,9 s d'attente entre deux tours dépasse les 240 s.
    Le BotStoppedSpeakingFrame est celui que le transport enverrait : sans lui, Pipecat garde le tour suivant
    en attente (``pause_frame_processing``)."""
    import time

    from pipecat.frames.frames import (
        BotStoppedSpeakingFrame,
        LLMFullResponseEndFrame,
        LLMFullResponseStartFrame,
        LLMTextFrame,
        TTSAudioRawFrame,
        TTSStoppedFrame,
    )
    from pipecat.tests.utils import SleepFrame, run_test

    depart = time.monotonic()
    service = _voix()
    service._horloge = lambda: 1000.0 + (time.monotonic() - depart) * 400.0

    def _tour(texte):
        return [LLMFullResponseStartFrame(), LLMTextFrame(texte), LLMFullResponseEndFrame()]

    async with asyncio.timeout(25):
        descendus, _ = await run_test(
            service,
            frames_to_send=[
                *_tour("Bonjour, ici l'accueil."),
                SleepFrame(0.1),
                BotStoppedSpeakingFrame(),
                SleepFrame(0.9),
                *_tour("Je vous écoute."),
                SleepFrame(0.2),
                BotStoppedSpeakingFrame(),
            ],
            start_timeout=15,
        )
    assert len([f for f in descendus if isinstance(f, TTSAudioRawFrame)]) == 2
    assert len([f for f in descendus if isinstance(f, TTSStoppedFrame)]) == 2

    def _textes(connexion):
        return [m["text"] for m in connexion.envoyes if m["type"] == "text"]

    premiere = faux_gradium.ouvertes[0]
    seconde = next(c for c in faux_gradium.ouvertes if any("écoute" in t for t in _textes(c)))
    assert seconde is not premiere
    assert any("accueil" in t for t in _textes(premiere)) and not any("écoute" in t for t in _textes(premiere))
    assert premiere.state is State.CLOSED
    # Chaque connexion commence par son message de départ, avec ses réglages.
    assert premiere.envoyes[0]["type"] == "setup" and seconde.envoyes[0]["type"] == "setup"
    assert seconde.envoyes[0]["json_config"]["rewrite_rules"] == "fr"
    assert service.reouvertures >= 1

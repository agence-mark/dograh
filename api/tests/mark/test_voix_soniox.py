"""[.mark] Chantier voix-soniox, lot 1 : les tests de la voix Soniox, écrits AVANT le code.

La question de ce fichier (plan ``voix-soniox``, condition de sortie 1, 2 et 4) :

    La voix Soniox est-elle déclarée, chacun de ses réglages arrive-t-il de
    l'écran au connecteur Pipecat en passant par la porte du produit
    (``create_tts_service``), et aucun agent ElevenLabs ne change-t-il ?

⛔ Portée lue à la lettre : ce fichier ne prouve ni que Soniox parle bien, ni qu'il
accepte une valeur (aucun appel à Soniox dans ce chantier). Il prouve que rien
ne se perd entre l'écran et le message de configuration du flux, que la clé
part dans l'en-tête, et que les requêtes des agents existants ne bougent pas.

🟢 État au lot 3 : la voix Soniox est déclarée (lot 2) et branchée (lot 3). Les 17 fonctions (27 cas)
qui portaient la marque ``A_FAIRE`` (``xfail(strict=True)`` du lot 1) l'ont perdue, sans les
avoir lancés ici (consigne d'Evan du 22/10 : aucun test local ; la CI de GitHub les joue une
seule fois, à la fin). Ils ont été vus rouges pour la bonne raison au lot 1 (la voix Soniox
était absente, pas une erreur d'import).

| Test | Preuve |
|---|---|
| la voix Soniox est dans ``/user/configurations/defaults`` et dans le menu des voix | cond. 1 |
| chaque réglage de l'écran arrive au connecteur (message du flux) par la vraie fabrique | cond. 2 |
| un champ vide n'est pas transmis (défaut Soniox) | cond. 2 |
| adresse européenne par défaut, saisie libre, région en miroir | D6 |
| le mode d'envoi du texte : phrase par défaut, mot à mot sur demande | D3 |
| balayage : réglage exposé = champ déclaré par ``SonioxTTSSettings`` ou le constructeur | lot 1 |
| la clé part dans l'en-tête de la voix, par la vraie fabrique | D19 |
| ElevenLabs : mêmes réglages et même adresse qu'avant, octet pour octet | cond. 4 |
"""

import dataclasses
import inspect
from types import SimpleNamespace

import pytest

from api.services.pipecat.audio_config import AudioConfig
from api.tests.mark.test_soniox_cle_en_entete import connexions  # noqa: F401 (fixture)

ADRESSE_EUROPE = "wss://tts-rt.eu.soniox.com/tts-websocket"
ADRESSE_MONDIALE = "wss://tts-rt.soniox.com/tts-websocket"
CLE = "soniox-key"

# Les réglages que l'écran expose (tableau « Réglages et écran » du plan).
REGLAGES_EXPOSES = (
    "model",
    "voice",
    "language",
    "speed",
    "reduce_silence",
    "text_aggregation_mode",
    "base_url",
    "region",
)
# Ce qui arrive où : (« settings », champ de SonioxTTSSettings) ou (« ctor », paramètre du service).
CHEMIN = {
    "model": ("settings", "model"),
    "voice": ("settings", "voice"),
    "language": ("settings", "language"),
    "speed": ("settings", "speed"),
    "reduce_silence": ("settings", "reduce_silence"),
    "text_aggregation_mode": ("ctor", "text_aggregation_mode"),
    "base_url": ("ctor", "url"),
}
# Les champs de la configuration qui ne sont pas un réglage du connecteur.
PLOMBERIE = {"provider", "api_key", "adresse_libre", "region"}


def _classe():
    from api.services.configuration import registry

    classe = getattr(registry, "SonioxTTSConfiguration", None)
    assert classe is not None, (
        "SonioxTTSConfiguration n'existe pas dans registry.py : la voix Soniox n'est "
        "pas déclarée, donc elle n'est sur aucun écran et aucun appel ne peut la jouer."
    )
    return classe


def _config(**reglages):
    return _classe()(api_key=CLE, **reglages)


def _audio():
    return AudioConfig(transport_in_sample_rate=8000, transport_out_sample_rate=24000)


def _voix(config=None, **reglages):
    """Le connecteur que l'appel construit, par la porte du produit."""
    from api.services.pipecat.service_factory import create_tts_service

    return create_tts_service(SimpleNamespace(tts=config or _config(**reglages)), _audio())


def _flux(service):
    """Le message de configuration que Soniox reçoit à l'ouverture d'un flux."""
    return service._build_config_msg("flux-1")


# --------------------------------------------------------------------------- #
# 1. Déclarée : c'est ce qui la met à l'écran
# --------------------------------------------------------------------------- #


def test_la_voix_soniox_est_declaree_sous_le_nom_de_la_transcription():
    from api.services.configuration.registry import REGISTRY, ServiceProviders, ServiceType

    assert ServiceProviders.SONIOX.value == "soniox"
    assert REGISTRY[ServiceType.TTS]["soniox"] is _classe()


def test_la_route_des_defauts_sert_la_voix_soniox():
    from api.routes.user import get_default_configurations
    from api.tests.mark.boucle_isolee import executer_sans_toucher_la_boucle_courante

    reponse = executer_sans_toucher_la_boucle_courante(get_default_configurations())
    assert "soniox" in reponse.tts, "la voix Soniox n'est pas dans /user/configurations/defaults"
    proprietes = reponse.tts["soniox"]["properties"]
    for champ in REGLAGES_EXPOSES:
        assert champ in proprietes, f"{champ} n'est pas servi à l'écran"


def test_la_voix_soniox_est_dans_le_menu_des_voix_de_l_ecran_modeles():
    from api.routes.organization import _byok_provider_schemas
    from api.services.configuration.registry import ServiceType

    assert "soniox" in _byok_provider_schemas(ServiceType.TTS)


@pytest.mark.parametrize("champ", [c for c in REGLAGES_EXPOSES if c != "model"])
def test_le_reglage_est_range_en_sous_menu_et_libelle_dans_les_deux_langues(champ):
    proprietes = _classe().model_json_schema()["properties"]
    assert champ in proprietes
    assert proprietes[champ].get("mark_groupe"), f"{champ} n'a pas de sous-menu (E2)"
    libelle = proprietes[champ].get("mark_libelle") or {}
    assert libelle.get("en") and libelle.get("fr"), f"{champ} n'a pas ses deux langues (T2)"


def test_le_discriminateur_accepte_ce_que_l_ecran_enverra():
    from pydantic import TypeAdapter

    from api.services.configuration.registry import TTSConfig

    config = TypeAdapter(TTSConfig).validate_python(
        {"provider": "soniox", "api_key": CLE, "model": "tts-rt-v2", "voice": "Mathieu", "language": "fr"}
    )
    assert isinstance(config, _classe())


def test_les_valeurs_par_defaut_sont_celles_decidees():
    config = _config()
    assert config.model == "tts-rt-v2"
    assert config.language == "fr"
    assert (config.voice or "").strip(), "une voix par défaut est nécessaire : le connecteur n'a que celle d'Adrian"
    # ⛔ Aucune valeur choisie par le chantier : Soniox applique les siennes.
    assert config.speed is None
    assert config.reduce_silence is None
    # D3 : phrase par phrase, comme aujourd'hui.
    assert config.text_aggregation_mode == "sentence"
    # D6 : adresse européenne, région en miroir.
    assert config.base_url == ADRESSE_EUROPE
    assert config.region == "eu"


@pytest.mark.parametrize("valeur, ok", [(0.69, False), (0.7, True), (1.0, True), (1.3, True), (1.31, False)])
def test_la_vitesse_tient_les_bornes_de_la_documentation(valeur, ok):
    from pydantic import ValidationError

    if ok:
        assert _config(speed=valeur).speed == valeur
    else:
        with pytest.raises(ValidationError):
            _config(speed=valeur)


# --------------------------------------------------------------------------- #
# 2. Transmise : de l'écran au message du flux, par la porte du produit
# --------------------------------------------------------------------------- #


def test_sans_reglage_la_voix_parle_en_europe_en_francais_phrase_par_phrase():
    from pipecat.services.tts_service import TextAggregationMode

    service = _voix()
    assert service._url == ADRESSE_EUROPE
    message = _flux(service)
    assert message["model"] == "tts-rt-v2"
    assert message["language"] == "fr"
    assert message["audio_format"] == "pcm_s16le"
    assert service._text_aggregation_mode == TextAggregationMode.SENTENCE


def test_chaque_reglage_rempli_arrive_dans_le_message_du_flux():
    from pipecat.services.tts_service import TextAggregationMode

    service = _voix(
        model="tts-rt-v2",
        voice="Mathieu",
        language="en",
        speed=1.1,
        reduce_silence=True,
        text_aggregation_mode="token",
        base_url=ADRESSE_MONDIALE,
    )
    message = _flux(service)
    assert message["voice"] == "Mathieu"
    assert message["model"] == "tts-rt-v2"
    assert message["language"] == "en"
    assert message["speed"] == 1.1
    assert message["reduce_silence"] is True
    assert service._text_aggregation_mode == TextAggregationMode.TOKEN
    assert service._url == ADRESSE_MONDIALE


def test_un_champ_vide_n_est_pas_transmis_soniox_applique_son_defaut():
    message = _flux(_voix())
    assert "speed" not in message
    assert "reduce_silence" not in message


def test_la_voix_choisie_est_celle_qui_part():
    """Le menu propose les voix ; la saisie libre (voix clonée, nouvelle voix) part telle quelle."""
    assert _flux(_voix(voice="Celine"))["voice"] == "Celine"
    cloner = "3f2a9c1e-0000-4000-8000-000000000001"
    assert _flux(_voix(voice=cloner))["voice"] == cloner


def test_une_langue_inconnue_est_refusee_a_l_enregistrement():
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        _config(language="klingon")


# --------------------------------------------------------------------------- #
# 3. L'adresse : Europe par défaut, saisie libre, région en miroir
# --------------------------------------------------------------------------- #


def test_l_adresse_europeenne_est_le_defaut_et_une_adresse_vide_part_en_europe():
    assert _voix()._url == ADRESSE_EUROPE
    assert _voix(base_url="  ")._url == ADRESSE_EUROPE


def test_la_region_suit_l_adresse_saisie_quel_que_soit_le_schema():
    assert _config(base_url=ADRESSE_MONDIALE).region == "global"
    assert _config(base_url=ADRESSE_EUROPE).region == "eu"
    # La case « saisie libre » du lot 0 bis s'applique d'elle-même à l'adresse de la voix.
    assert _config(base_url="https://proxy.example.net/tts", adresse_libre=True).region == "proxy.example.net"
    assert _config(base_url=ADRESSE_MONDIALE, region="eu").region == "global"


def test_l_adresse_de_la_voix_porte_la_case_saisie_libre():
    proprietes = _classe().model_json_schema()["properties"]
    assert proprietes["base_url"].get("mark_adresse") is True
    assert proprietes["adresse_libre"].get("mark_adresse_libre") is True


# --------------------------------------------------------------------------- #
# 4. Balayage : un réglage exposé est un champ du connecteur, et inversement
# --------------------------------------------------------------------------- #

# Ce que Pipecat porte et qui n'est PAS un champ de la configuration, avec la raison.
NON_EXPOSES_ET_POURQUOI = {
    "audio_format": "technique : posé par la fabrique (pcm_s16le), comme pour ElevenLabs",
    "sample_rate": "technique : la fréquence du transport, posée par la fabrique",
    "settings": "l'objet de réglages lui-même",
    "client_reference_id": "identifiant de trace interne, pas un réglage",
}


def _reglages_de_pipecat():
    """Les champs propres à SonioxTTSSettings, plus les paramètres du constructeur."""
    from pipecat.services.soniox.tts import SonioxTTSService, SonioxTTSSettings
    from pipecat.services.tts_service import TTSSettings

    herites = {c.name for c in dataclasses.fields(TTSSettings)}
    settings = {c.name for c in dataclasses.fields(SonioxTTSSettings)}
    constructeur = {
        nom
        for nom, p in inspect.signature(SonioxTTSService.__init__).parameters.items()
        if nom not in ("self", "api_key", "kwargs") and p.kind is not inspect.Parameter.VAR_KEYWORD
    }
    return settings, settings - herites, constructeur


def test_le_balayage_voit_les_reglages_du_connecteur_de_notre_epinglage():
    """Garde du balayage lui-même (pas de marque) : s'il ne trouve rien, il ne prouve rien."""
    settings, propres, constructeur = _reglages_de_pipecat()
    assert {"voice", "model", "language"} <= settings
    assert {"speed", "reduce_silence"} <= propres
    assert {"url", "text_aggregation_mode", "audio_format", "sample_rate"} <= constructeur


def test_chaque_reglage_du_connecteur_est_expose_ou_ecarte_par_ecrit():
    """Un réglage que Pipecat gagne à la prochaine montée fait échouer ce test au lieu de
    quitter l'écran en silence."""
    settings, propres, constructeur = _reglages_de_pipecat()
    declares = set(_classe().model_fields)
    attendus_en_settings = {nom for sorte, nom in CHEMIN.values() if sorte == "settings"}
    attendus_en_ctor = {nom for sorte, nom in CHEMIN.values() if sorte == "ctor"}
    manquants = (propres | {"voice", "model", "language"}) - {
        champ for champ, (sorte, nom) in CHEMIN.items() if sorte == "settings" and champ in declares
    } - set(NON_EXPOSES_ET_POURQUOI)
    assert not manquants, f"réglages de SonioxTTSSettings ni exposés ni écartés par écrit : {sorted(manquants)}"
    ctor_manquants = (constructeur - set(NON_EXPOSES_ET_POURQUOI)) - {
        nom for champ, (sorte, nom) in CHEMIN.items() if sorte == "ctor" and champ in declares
    }
    assert not ctor_manquants, (
        f"paramètres du constructeur ni exposés ni écartés par écrit : {sorted(ctor_manquants)}"
    )
    # Et l'autre sens : tout champ exposé existe réellement chez Pipecat (jamais un réglage sans effet).
    assert attendus_en_settings <= settings, sorted(attendus_en_settings - settings)
    assert attendus_en_ctor <= constructeur, sorted(attendus_en_ctor - constructeur)
    inconnus = declares - set(CHEMIN) - PLOMBERIE
    assert not inconnus, f"champs déclarés sans chemin vers le connecteur : {sorted(inconnus)}"


# --------------------------------------------------------------------------- #
# 5. La clé part dans l'en-tête de la voix (D19), par la vraie fabrique
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_la_cle_de_la_voix_part_dans_l_en_tete(connexions):  # noqa: F811
    from api.services.pipecat.soniox_cle_en_entete import MarkSonioxTTSService

    service = _voix()
    assert isinstance(service, MarkSonioxTTSService)
    await service._connect_websocket()

    assert len(connexions) == 1
    assert connexions[0]["adresse"] == ADRESSE_EUROPE
    assert connexions[0]["kwargs"].get("additional_headers") == {"Authorization": f"Bearer {CLE}"}


# --------------------------------------------------------------------------- #
# 6. Aucun agent existant ne change : ElevenLabs octet pour octet
# --------------------------------------------------------------------------- #


def test_elevenlabs_garde_ses_reglages_et_son_adresse():
    """Gardé AU VERT depuis le lot 1 : brancher une voix de plus ne doit pas bouger celle-ci."""
    from api.services.configuration.registry import ElevenlabsTTSConfiguration

    service = _voix(
        ElevenlabsTTSConfiguration(
            api_key="el-key", model="eleven_flash_v2_5", voice="voix-eleven", speed=1.0
        )
    )
    reglages = service._settings
    assert reglages.voice == "voix-eleven"
    assert reglages.model == "eleven_flash_v2_5"
    assert reglages.stability == 0.8
    assert reglages.similarity_boost == 0.75
    assert reglages.speed == 1.0
    assert service._url == "wss://api.elevenlabs.io"


def test_la_porte_de_la_voix_garde_les_autres_fournisseurs():
    """Ni Deepgram ni Mistral ne passent par la voix Soniox, avec ou sans elle."""
    from api.services.configuration.registry import REGISTRY, ServiceType

    for nom in ("elevenlabs", "deepgram", "mistral", "openai"):
        assert nom in REGISTRY[ServiceType.TTS], nom
